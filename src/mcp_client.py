"""MCP (Model Context Protocol) client for LlamaTerm.

Supports both stdio (subprocess) and SSE (HTTP) transports.
"""

import json
import logging
import subprocess
import threading
import urllib.request
import urllib.error
from queue import Queue, Empty
from typing import Any, Callable, Optional
from dataclasses import dataclass

logger = logging.getLogger("llamaterm")


@dataclass
class MCPTool:
    """Represents an MCP tool."""
    name: str
    description: str
    parameters: dict
    server_name: str


class MCPError(Exception):
    """MCP-related errors."""
    pass


class MCPStdioTransport:
    """MCP transport over stdio (subprocess)."""

    def __init__(self, command: list[str], env: Optional[dict] = None):
        self.command = command
        self.env = env
        self.process: Optional[subprocess.Popen] = None
        self.request_id = 0
        self.pending_responses: dict[int, Queue] = {}
        self.reader_thread: Optional[threading.Thread] = None
        self._running = False

    def connect(self) -> None:
        """Start the MCP server process."""
        try:
            self.process = subprocess.Popen(
                self.command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=self.env,
                bufsize=1,
            )
            self._running = True
            self.reader_thread = threading.Thread(target=self._read_responses, daemon=True)
            self.reader_thread.start()
            logger.info(f"MCP stdio process started: {' '.join(self.command)}")
        except Exception as e:
            raise MCPError(f"Failed to start MCP server: {e}")

    def _read_responses(self) -> None:
        """Read responses from the subprocess."""
        while self._running and self.process and self.process.stdout:
            try:
                line = self.process.stdout.readline()
                if not line:
                    break
                try:
                    msg = json.loads(line.strip())
                    req_id = msg.get("id")
                    if req_id is not None and req_id in self.pending_responses:
                        self.pending_responses[req_id].put(msg)
                except json.JSONDecodeError:
                    continue
            except Exception as e:
                logger.error(f"Error reading MCP response: {e}")
                break

    def send_request(self, method: str, params: Optional[dict] = None, timeout: int = 30) -> dict:
        """Send a JSON-RPC request and wait for response."""
        if not self.process or self.process.poll() is not None:
            raise MCPError("MCP server not running")

        self.request_id += 1
        req_id = self.request_id

        request = {
            "jsonrpc": "2.0",
            "id": req_id,
            "method": method,
        }
        if params:
            request["params"] = params

        response_queue: Queue = Queue()
        self.pending_responses[req_id] = response_queue

        try:
            self.process.stdin.write(json.dumps(request) + "\n")
            self.process.stdin.flush()

            try:
                response = response_queue.get(timeout=timeout)
                if "error" in response:
                    raise MCPError(f"MCP error: {response['error']}")
                return response.get("result", {})
            except Empty:
                raise MCPError(f"MCP request timed out: {method}")
        finally:
            del self.pending_responses[req_id]

    def disconnect(self) -> None:
        """Stop the MCP server process."""
        self._running = False
        if self.process:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
            self.process = None
        logger.info("MCP stdio process stopped")


class MCPSSETransport:
    """MCP transport over SSE (HTTP)."""

    def __init__(self, url: str, headers: Optional[dict] = None):
        self.url = url.rstrip('/')
        self.headers = headers or {}
        self.session_id: Optional[str] = None

    def connect(self) -> None:
        """Establish SSE connection (get session)."""
        # For SSE MCP, we typically need to initialize a session
        try:
            result = self._post("/initialize", {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "LlamaTerm", "version": "1.0.0"}
            })
            self.session_id = result.get("sessionId")
            logger.info(f"MCP SSE connected: {self.url}")
        except Exception as e:
            logger.warning(f"MCP SSE init (may not be required): {e}")

    def _post(self, endpoint: str, data: dict, timeout: int = 30) -> dict:
        """Make a POST request."""
        url = f"{self.url}{endpoint}"
        headers = {"Content-Type": "application/json", **self.headers}

        request_data = json.dumps(data).encode('utf-8')
        req = urllib.request.Request(url, data=request_data, headers=headers, method="POST")

        try:
            with urllib.request.urlopen(req, timeout=timeout) as response:
                return json.loads(response.read().decode('utf-8'))
        except urllib.error.HTTPError as e:
            error_body = e.read().decode('utf-8') if e.fp else str(e)
            raise MCPError(f"HTTP {e.code}: {error_body}")
        except urllib.error.URLError as e:
            raise MCPError(f"Connection error: {e.reason}")

    def send_request(self, method: str, params: Optional[dict] = None, timeout: int = 30) -> dict:
        """Send an MCP request via HTTP."""
        data = {"method": method}
        if params:
            data["params"] = params
        if self.session_id:
            data["sessionId"] = self.session_id

        return self._post("/message", data, timeout)

    def disconnect(self) -> None:
        """Close SSE connection."""
        self.session_id = None
        logger.info("MCP SSE disconnected")


class MCPClient:
    """MCP client managing multiple server connections."""

    def __init__(self):
        self.servers: dict[str, MCPStdioTransport | MCPSSETransport] = {}
        self.tools: dict[str, MCPTool] = {}  # tool_name -> MCPTool

    def add_stdio_server(self, name: str, command: list[str], env: Optional[dict] = None) -> None:
        """Add an MCP server via stdio transport."""
        transport = MCPStdioTransport(command, env)
        transport.connect()

        # Initialize and get capabilities
        try:
            init_result = transport.send_request("initialize", {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "LlamaTerm", "version": "1.0.0"}
            })
            logger.debug(f"MCP server {name} initialized: {init_result}")

            # Send initialized notification
            transport.send_request("notifications/initialized", {})
        except MCPError as e:
            logger.warning(f"MCP init handshake: {e}")

        self.servers[name] = transport
        self._refresh_tools(name)

    def add_sse_server(self, name: str, url: str, headers: Optional[dict] = None) -> None:
        """Add an MCP server via SSE transport."""
        transport = MCPSSETransport(url, headers)
        transport.connect()
        self.servers[name] = transport
        self._refresh_tools(name)

    def _refresh_tools(self, server_name: str) -> None:
        """Refresh tools from a server."""
        transport = self.servers.get(server_name)
        if not transport:
            return

        try:
            result = transport.send_request("tools/list", {})
            tools = result.get("tools", [])

            # Remove old tools from this server
            self.tools = {k: v for k, v in self.tools.items() if v.server_name != server_name}

            # Add new tools
            for tool in tools:
                tool_name = f"mcp_{server_name}_{tool['name']}"
                self.tools[tool_name] = MCPTool(
                    name=tool["name"],
                    description=tool.get("description", ""),
                    parameters=tool.get("inputSchema", {"type": "object", "properties": {}}),
                    server_name=server_name
                )
            logger.info(f"Loaded {len(tools)} tools from MCP server '{server_name}'")
        except MCPError as e:
            logger.warning(f"Could not list tools from {server_name}: {e}")

    def remove_server(self, name: str) -> bool:
        """Remove an MCP server."""
        if name not in self.servers:
            return False

        self.servers[name].disconnect()
        del self.servers[name]

        # Remove tools from this server
        self.tools = {k: v for k, v in self.tools.items() if v.server_name != name}
        return True

    def call_tool(self, tool_name: str, arguments: dict) -> str:
        """Call an MCP tool."""
        if tool_name not in self.tools:
            return f"Error: Unknown MCP tool '{tool_name}'"

        tool = self.tools[tool_name]
        transport = self.servers.get(tool.server_name)
        if not transport:
            return f"Error: MCP server '{tool.server_name}' not connected"

        try:
            result = transport.send_request("tools/call", {
                "name": tool.name,
                "arguments": arguments
            })

            # Handle MCP tool result format
            content = result.get("content", [])
            if isinstance(content, list):
                parts = []
                for item in content:
                    if isinstance(item, dict):
                        if item.get("type") == "text":
                            parts.append(item.get("text", ""))
                        else:
                            parts.append(json.dumps(item))
                    else:
                        parts.append(str(item))
                return "\n".join(parts)
            return str(result)
        except MCPError as e:
            return f"Error calling MCP tool: {e}"

    def get_tools_for_api(self) -> list[dict]:
        """Get all MCP tools in OpenAI API format."""
        return [
            {
                "type": "function",
                "function": {
                    "name": name,
                    "description": f"[MCP:{tool.server_name}] {tool.description}",
                    "parameters": tool.parameters
                }
            }
            for name, tool in self.tools.items()
        ]

    def disconnect_all(self) -> None:
        """Disconnect all MCP servers."""
        for name in list(self.servers.keys()):
            self.remove_server(name)

    def list_servers(self) -> list[str]:
        """List connected server names."""
        return list(self.servers.keys())
