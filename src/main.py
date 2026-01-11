#!/usr/bin/env python3
"""LlamaTerm - Agentic terminal application powered by llama.cpp server."""

import json
import logging
import signal
import sys
from typing import Optional

from api_client import LlamaClient, APIError
from config import Config
from conversation import Conversation
from mcp_client import MCPClient
from tools import get_all_tools, execute_tool, TOOLS
from utils import (
    Colors, colorize, print_error, print_warning, print_info,
    print_success, print_llm, print_tool, setup_logging
)

logger = logging.getLogger("llamaterm")


class LlamaTerm:
    """Main LlamaTerm application."""

    def __init__(self):
        self.config = Config()
        self.client = LlamaClient(self.config)
        self.conversation = Conversation(self.config)
        self.mcp_client = MCPClient()
        self.interrupted = False
        self.running = True
        self.tools_enabled = True  # Will be set based on model compatibility

        # Setup interrupt handler
        signal.signal(signal.SIGINT, self._handle_interrupt)

    def _check_tool_support(self) -> None:
        """Check if current model supports tools and update state."""
        model = self.config.get_model()
        self.tools_enabled = self.config.model_supports_tools(model)
        if not self.tools_enabled:
            print_warning(f"Model '{model}' does not support tool calling")
            print_warning("Running in chat-only mode (no file ops, commands, or MCP tools)")

    def _handle_interrupt(self, signum, frame):
        """Handle Ctrl+C interrupt."""
        if self.interrupted:
            # Double interrupt - exit
            print("\n" + colorize("Exiting...", Colors.YELLOW))
            self.shutdown()
            sys.exit(0)
        else:
            self.interrupted = True
            print("\n" + colorize("[Interrupted - press Ctrl+C again to exit]", Colors.YELLOW))

    def setup(self) -> bool:
        """Initialize the application."""
        print(colorize("=" * 60, Colors.CYAN))
        print(colorize("  LlamaTerm - Agentic Terminal Assistant", Colors.BOLD + Colors.CYAN))
        print(colorize("=" * 60, Colors.CYAN))
        print()

        # Setup logging
        setup_logging()

        # Check server connection
        print_info(f"Connecting to server: {self.config.get_server_url()}")
        if not self.client.health_check():
            print_error("Cannot connect to llama.cpp server")
            print_info("Make sure the server is running and accessible")
            return False
        print_success("Server connected")

        # Get available models
        models = self.client.get_model_names()
        if not models:
            print_warning("No models found on server")
            return False

        print_info(f"Available models: {', '.join(models)}")

        # Select model if not set
        current_model = self.config.get_model()
        if current_model not in models:
            if len(models) == 1:
                self.config.set_model(models[0])
                print_info(f"Using model: {models[0]}")
            else:
                print("\nSelect a model:")
                for i, model in enumerate(models, 1):
                    # Mark models that don't support tools
                    tool_marker = "" if self.config.model_supports_tools(model) else " [no tools]"
                    print(f"  {i}. {model}{tool_marker}")
                while True:
                    try:
                        choice = input("Enter number: ").strip()
                        idx = int(choice) - 1
                        if 0 <= idx < len(models):
                            self.config.set_model(models[idx])
                            print_success(f"Using model: {models[idx]}")
                            break
                    except (ValueError, EOFError):
                        pass
                    print_error("Invalid choice")
        else:
            print_info(f"Using model: {current_model}")

        # Check if selected model supports tools
        self._check_tool_support()

        # Load MCP servers from config
        self._load_mcp_servers()

        # Show session info
        if len(self.conversation) > 0:
            print_info(f"Restored session with {len(self.conversation)} messages")

        print()
        print_info("Type /help for commands, or start chatting")
        print_info("Press Ctrl+C to interrupt, twice to exit")
        print()
        return True

    def _load_mcp_servers(self) -> None:
        """Load MCP servers from configuration."""
        servers = self.config.get_mcp_servers()
        for name, cfg in servers.items():
            try:
                if cfg.get("transport") == "stdio":
                    command = cfg.get("command", [])
                    if isinstance(command, str):
                        command = command.split()
                    self.mcp_client.add_stdio_server(name, command, cfg.get("env"))
                    print_success(f"MCP server '{name}' connected (stdio)")
                elif cfg.get("transport") == "sse":
                    self.mcp_client.add_sse_server(name, cfg.get("url", ""), cfg.get("headers"))
                    print_success(f"MCP server '{name}' connected (SSE)")
            except Exception as e:
                print_warning(f"Failed to connect MCP server '{name}': {e}")

    def _get_all_tools(self) -> list[dict]:
        """Get all available tools including MCP tools."""
        tools = get_all_tools()
        tools.extend(self.mcp_client.get_tools_for_api())
        return tools

    def _execute_tool(self, name: str, arguments: dict) -> str:
        """Execute a tool (built-in or MCP)."""
        if name.startswith("mcp_"):
            return self.mcp_client.call_tool(name, arguments)
        return execute_tool(name, arguments)

    def process_command(self, cmd: str) -> bool:
        """Process a slash command. Returns True if should continue."""
        parts = cmd.split(maxsplit=1)
        command = parts[0].lower()
        args = parts[1] if len(parts) > 1 else ""

        if command in ("/help", "/h", "/?"):
            self._show_help()
        elif command in ("/quit", "/exit", "/q"):
            return False
        elif command == "/clear":
            self.conversation.clear()
            print_success("Conversation cleared")
        elif command == "/config":
            print(str(self.config))
        elif command == "/set":
            self._handle_set(args)
        elif command == "/model":
            self._handle_model(args)
        elif command == "/models":
            models = self.client.get_model_names()
            print("Available models:")
            for m in models:
                marker = " *" if m == self.config.get_model() else ""
                print(f"  - {m}{marker}")
        elif command == "/mcp":
            self._handle_mcp(args)
        elif command == "/tools":
            self._show_tools()
        elif command == "/memory":
            content = execute_tool("read_memory", {})
            print(content)
        elif command == "/save":
            self.conversation.save_session()
            print_success("Session saved")
        else:
            print_error(f"Unknown command: {command}")
            print_info("Type /help for available commands")

        return True

    def _show_help(self) -> None:
        """Show help message."""
        help_text = """
Commands:
  /help, /h       Show this help
  /quit, /exit    Exit LlamaTerm
  /clear          Clear conversation history
  /config         Show current configuration
  /set KEY VALUE  Set a configuration value
                  Keys: temperature, top_p, top_k, max_tokens, repeat_penalty
  /model [NAME]   Show or change current model
  /models         List available models
  /mcp            Manage MCP servers (add/remove/list)
  /tools          List available tools
  /memory         Show long-term memory contents
  /save           Force save session

Tips:
  - The AI can work autonomously on complex tasks
  - Press Ctrl+C once to interrupt, twice to exit
  - Session is auto-saved after each message
"""
        print(help_text)

    def _handle_set(self, args: str) -> None:
        """Handle /set command."""
        if not args:
            print("Usage: /set KEY VALUE")
            print("Keys: temperature, top_p, top_k, max_tokens, repeat_penalty, server_url")
            return

        parts = args.split(maxsplit=1)
        if len(parts) != 2:
            print_error("Usage: /set KEY VALUE")
            return

        key, value = parts
        try:
            if key in ("temperature", "top_p", "repeat_penalty"):
                self.config.set(key, float(value))
            elif key in ("top_k", "max_tokens"):
                self.config.set(key, int(value))
            elif key == "server_url":
                self.config.set(key, value)
                self.client = LlamaClient(self.config)
            else:
                print_error(f"Unknown setting: {key}")
                return
            print_success(f"Set {key} = {value}")
        except ValueError as e:
            print_error(f"Invalid value: {e}")

    def _handle_model(self, args: str) -> None:
        """Handle /model command."""
        if not args:
            model = self.config.get_model()
            tools_status = "enabled" if self.tools_enabled else "disabled"
            print(f"Current model: {model} (tools: {tools_status})")
            return

        models = self.client.get_model_names()
        if args in models:
            self.config.set_model(args)
            print_success(f"Model changed to: {args}")
            self._check_tool_support()
        else:
            print_error(f"Unknown model: {args}")
            print_info(f"Available: {', '.join(models)}")

    def _handle_mcp(self, args: str) -> None:
        """Handle /mcp command."""
        parts = args.split(maxsplit=2)
        subcmd = parts[0] if parts else "list"

        if subcmd == "list":
            servers = self.mcp_client.list_servers()
            if servers:
                print("Connected MCP servers:")
                for name in servers:
                    tools = [t.name for t in self.mcp_client.tools.values() if t.server_name == name]
                    print(f"  - {name}: {len(tools)} tools")
            else:
                print("No MCP servers connected")

        elif subcmd == "add" and len(parts) >= 3:
            name = parts[1]
            rest = parts[2]
            if rest.startswith("http"):
                # SSE transport
                self.mcp_client.add_sse_server(name, rest)
                self.config.add_mcp_server(name, "sse", url=rest)
                print_success(f"Added MCP server '{name}' (SSE)")
            else:
                # stdio transport
                command = rest.split()
                self.mcp_client.add_stdio_server(name, command)
                self.config.add_mcp_server(name, "stdio", command=command)
                print_success(f"Added MCP server '{name}' (stdio)")

        elif subcmd == "remove" and len(parts) >= 2:
            name = parts[1]
            if self.mcp_client.remove_server(name):
                self.config.remove_mcp_server(name)
                print_success(f"Removed MCP server '{name}'")
            else:
                print_error(f"Server '{name}' not found")

        else:
            print("Usage:")
            print("  /mcp list                    List connected servers")
            print("  /mcp add NAME COMMAND        Add stdio server")
            print("  /mcp add NAME URL            Add SSE server")
            print("  /mcp remove NAME             Remove server")

    def _show_tools(self) -> None:
        """Show available tools."""
        if not self.tools_enabled:
            print_warning("Tools are disabled for current model")
            print_info("Switch to a tool-compatible model to enable tools")
            print()

        print("Built-in tools:")
        for name, tool in TOOLS.items():
            print(f"  - {name}: {tool['description'][:60]}...")

        if self.mcp_client.tools:
            print("\nMCP tools:")
            for name, tool in self.mcp_client.tools.items():
                print(f"  - {name}: {tool.description[:60]}...")

    def run_agentic_loop(self, user_input: str) -> None:
        """Run the agentic loop for a user input."""
        self.interrupted = False

        # Add user message
        self.conversation.add_user_message(user_input)

        iteration = 0
        max_iterations = 50  # Safety limit

        while not self.interrupted and iteration < max_iterations:
            iteration += 1

            try:
                # Get response from LLM
                messages = self.conversation.get_api_messages()

                # Only include tools if the model supports them
                tools = self._get_all_tools() if self.tools_enabled else None

                response_text = ""
                tool_calls = []

                # Stream the response
                print()
                printed_prefix = False

                for chunk in self.client.chat_completion(messages, tools, stream=True):
                    if self.interrupted:
                        break

                    # Handle streaming response
                    choices = chunk.get("choices", [])
                    if not choices:
                        continue

                    delta = choices[0].get("delta", {})

                    # Text content
                    if "content" in delta and delta["content"]:
                        if not printed_prefix:
                            sys.stdout.write(colorize("Assistant: ", Colors.GREEN))
                            printed_prefix = True
                        text = delta["content"]
                        response_text += text
                        sys.stdout.write(text)
                        sys.stdout.flush()

                    # Tool calls
                    if "tool_calls" in delta:
                        for tc in delta["tool_calls"]:
                            idx = tc.get("index", 0)
                            while len(tool_calls) <= idx:
                                tool_calls.append({"id": "", "function": {"name": "", "arguments": ""}})

                            if "id" in tc:
                                tool_calls[idx]["id"] = tc["id"]
                            if "function" in tc:
                                if "name" in tc["function"]:
                                    tool_calls[idx]["function"]["name"] = tc["function"]["name"]
                                if "arguments" in tc["function"]:
                                    tool_calls[idx]["function"]["arguments"] += tc["function"]["arguments"]

                if printed_prefix:
                    print()  # Newline after response

                if self.interrupted:
                    print_warning("Interrupted by user")
                    # Still save partial response
                    if response_text:
                        self.conversation.add_assistant_message(response_text)
                    break

                # Save assistant message
                if response_text or tool_calls:
                    formatted_tool_calls = None
                    if tool_calls:
                        formatted_tool_calls = [
                            {
                                "id": tc["id"],
                                "type": "function",
                                "function": tc["function"]
                            }
                            for tc in tool_calls if tc["id"]
                        ]
                    self.conversation.add_assistant_message(response_text, formatted_tool_calls)

                # If no tool calls, we're done
                if not tool_calls or not any(tc["id"] for tc in tool_calls):
                    break

                # Execute tool calls
                for tc in tool_calls:
                    if not tc["id"]:
                        continue

                    if self.interrupted:
                        break

                    func_name = tc["function"]["name"]
                    try:
                        func_args = json.loads(tc["function"]["arguments"]) if tc["function"]["arguments"] else {}
                    except json.JSONDecodeError:
                        func_args = {}

                    print_tool(func_name, f"Executing with args: {json.dumps(func_args)[:100]}...")

                    result = self._execute_tool(func_name, func_args)

                    # Check for task completion signal
                    if result.startswith("TASK_COMPLETE:"):
                        print_success(result[14:].strip())
                        self.conversation.add_tool_result(tc["id"], func_name, result)
                        self.interrupted = True  # Exit loop
                        break

                    # Truncate long results for display
                    display_result = result[:200] + "..." if len(result) > 200 else result
                    print(colorize(f"  Result: {display_result}", Colors.DIM))

                    self.conversation.add_tool_result(tc["id"], func_name, result)

            except APIError as e:
                print_error(f"API error: {e}")
                logger.error(f"API error in agentic loop: {e}", exc_info=True)
                break
            except Exception as e:
                print_error(f"Error: {e}")
                logger.error(f"Error in agentic loop: {e}", exc_info=True)
                break

        if iteration >= max_iterations:
            print_warning("Reached maximum iterations limit")

        # Truncate conversation if needed
        self.conversation.truncate_if_needed()

    def run(self) -> None:
        """Main REPL loop."""
        while self.running:
            try:
                self.interrupted = False
                user_input = input(colorize("\nYou: ", Colors.BLUE)).strip()

                if not user_input:
                    continue

                # Handle commands
                if user_input.startswith("/"):
                    if not self.process_command(user_input):
                        break
                    continue

                # Run agentic loop
                self.run_agentic_loop(user_input)

            except EOFError:
                break
            except KeyboardInterrupt:
                # Handled by signal handler
                continue

        self.shutdown()

    def shutdown(self) -> None:
        """Clean up resources."""
        print_info("Shutting down...")
        self.mcp_client.disconnect_all()
        self.conversation.save_session()
        self.config.save()
        print_success("Goodbye!")


def main():
    """Entry point."""
    app = LlamaTerm()
    if app.setup():
        app.run()
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()
