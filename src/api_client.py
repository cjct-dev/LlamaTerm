"""llama.cpp server API client with tool/function calling support."""

import json
import logging
import urllib.request
import urllib.error
from typing import Any, Generator, Optional
from config import Config

logger = logging.getLogger("llamaterm")


class APIError(Exception):
    """API-related errors."""
    pass


class LlamaClient:
    """Client for llama.cpp server API (OpenAI-compatible endpoints)."""

    def __init__(self, config: Config):
        self.config = config
        self.base_url = config.get_server_url().rstrip('/')

    def _request(self, endpoint: str, method: str = "GET",
                 data: Optional[dict] = None, timeout: int = 30) -> dict:
        """Make an HTTP request to the server."""
        url = f"{self.base_url}{endpoint}"
        headers = {"Content-Type": "application/json"}

        request_data = json.dumps(data).encode('utf-8') if data else None
        req = urllib.request.Request(url, data=request_data, headers=headers, method=method)

        try:
            with urllib.request.urlopen(req, timeout=timeout) as response:
                return json.loads(response.read().decode('utf-8'))
        except urllib.error.HTTPError as e:
            error_body = e.read().decode('utf-8') if e.fp else str(e)
            logger.error(f"HTTP error {e.code} for {endpoint}: {error_body}")
            raise APIError(f"HTTP {e.code}: {error_body}")
        except urllib.error.URLError as e:
            logger.error(f"URL error for {endpoint}: {e.reason}")
            raise APIError(f"Connection error: {e.reason}")
        except json.JSONDecodeError as e:
            logger.error(f"JSON decode error: {e}")
            raise APIError(f"Invalid JSON response: {e}")

    def _stream_request(self, endpoint: str, data: dict,
                        timeout: Optional[int] = None) -> Generator[dict, None, None]:
        """Make a streaming request and yield parsed SSE events.

        Note: timeout=None means no timeout (wait indefinitely).
        This is important for large models offloaded to system RAM.
        """
        url = f"{self.base_url}{endpoint}"
        headers = {"Content-Type": "application/json", "Accept": "text/event-stream"}

        request_data = json.dumps(data).encode('utf-8')
        req = urllib.request.Request(url, data=request_data, headers=headers, method="POST")

        try:
            # timeout=None allows indefinite wait for slow inference
            with urllib.request.urlopen(req, timeout=timeout) as response:
                buffer = ""
                for line in response:
                    line = line.decode('utf-8')
                    buffer += line

                    while '\n' in buffer:
                        line, buffer = buffer.split('\n', 1)
                        line = line.strip()

                        if line.startswith('data: '):
                            data_str = line[6:]
                            if data_str == '[DONE]':
                                return
                            try:
                                yield json.loads(data_str)
                            except json.JSONDecodeError:
                                continue
        except urllib.error.HTTPError as e:
            error_body = e.read().decode('utf-8') if e.fp else str(e)
            logger.error(f"HTTP error {e.code} for {endpoint}: {error_body}")
            raise APIError(f"HTTP {e.code}: {error_body}")
        except urllib.error.URLError as e:
            logger.error(f"URL error for {endpoint}: {e.reason}")
            raise APIError(f"Connection error: {e.reason}")

    def health_check(self) -> bool:
        """Check if the server is healthy."""
        try:
            result = self._request("/health", timeout=5)
            return result.get("status") == "ok"
        except APIError:
            return False

    def list_models(self) -> list[dict]:
        """List available models on the server."""
        try:
            result = self._request("/v1/models")
            return result.get("data", [])
        except APIError as e:
            logger.error(f"Failed to list models: {e}")
            return []

    def get_model_names(self) -> list[str]:
        """Get list of model names/IDs."""
        models = self.list_models()
        return [m.get("id", "unknown") for m in models]

    def chat_completion(
        self,
        messages: list[dict],
        tools: Optional[list[dict]] = None,
        stream: bool = True,
        model: Optional[str] = None,
    ) -> Generator[dict, None, None] | dict:
        """
        Send a chat completion request.

        Args:
            messages: List of message dicts with 'role' and 'content'
            tools: Optional list of tool definitions for function calling
            stream: Whether to stream the response
            model: Model to use (overrides config)

        Yields/Returns:
            Stream chunks or complete response
        """
        model = model or self.config.get_model()
        params = self.config.get_llm_params()

        payload = {
            "model": model,
            "messages": messages,
            "stream": stream,
            **params,
        }

        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"

        logger.debug(f"Chat completion request: model={model}, messages={len(messages)}, tools={len(tools) if tools else 0}")

        # Use configurable timeout, default None (no timeout) for slow inference
        timeout = self.config.get("request_timeout", None)

        if stream:
            # Streaming: no timeout by default - wait for tokens as they come
            return self._stream_request("/v1/chat/completions", payload, timeout=timeout)
        else:
            # Non-streaming: use timeout if set, otherwise no timeout
            return self._request("/v1/chat/completions", method="POST", data=payload,
                                timeout=timeout if timeout else 3600)

    def chat_completion_non_stream(
        self,
        messages: list[dict],
        tools: Optional[list[dict]] = None,
        model: Optional[str] = None,
    ) -> dict:
        """Non-streaming chat completion."""
        model = model or self.config.get_model()
        params = self.config.get_llm_params()

        payload = {
            "model": model,
            "messages": messages,
            "stream": False,
            **params,
        }

        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"

        logger.debug(f"Chat completion (non-stream): model={model}, messages={len(messages)}")
        # No timeout by default for slow inference (large models offloaded to RAM)
        timeout = self.config.get("request_timeout", None)
        return self._request("/v1/chat/completions", method="POST", data=payload,
                            timeout=timeout if timeout else 3600)


def format_tool_for_api(tool: dict) -> dict:
    """Format a tool definition for the OpenAI-compatible API."""
    return {
        "type": "function",
        "function": {
            "name": tool["name"],
            "description": tool["description"],
            "parameters": tool.get("parameters", {"type": "object", "properties": {}})
        }
    }
