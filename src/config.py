"""Configuration management for LlamaTerm."""

import json
import os
from pathlib import Path
from typing import Any, Optional

DEFAULT_CONFIG = {
    "server_url": "http://100.82.203.89:8080",
    "model": None,  # Will be selected from available models
    "temperature": 0.7,
    "top_p": 0.9,
    "top_k": 40,
    "max_tokens": 4096,
    "repeat_penalty": 1.1,
    "stop": [],
    "mcp_servers": {},  # name -> {"transport": "stdio"|"sse", "command"|"url": ...}
    "memory_file": ".llamaterm/memory.md",
    "session_file": ".llamaterm/session.json",
    "auto_save": True,
}


class Config:
    """Configuration manager with persistence."""

    def __init__(self, config_path: Optional[str] = None):
        self.config_dir = Path.cwd() / ".llamaterm"
        self.config_dir.mkdir(parents=True, exist_ok=True)

        self.config_path = Path(config_path) if config_path else self.config_dir / "config.json"
        self.data: dict[str, Any] = DEFAULT_CONFIG.copy()
        self.load()

    def load(self) -> None:
        """Load configuration from file."""
        if self.config_path.exists():
            try:
                with open(self.config_path, 'r') as f:
                    saved = json.load(f)
                    # Merge with defaults (saved values override defaults)
                    for key, value in saved.items():
                        self.data[key] = value
            except (json.JSONDecodeError, IOError) as e:
                print(f"Warning: Could not load config: {e}")

    def save(self) -> None:
        """Save configuration to file."""
        try:
            with open(self.config_path, 'w') as f:
                json.dump(self.data, f, indent=2)
        except IOError as e:
            print(f"Warning: Could not save config: {e}")

    def get(self, key: str, default: Any = None) -> Any:
        """Get a configuration value."""
        return self.data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        """Set a configuration value and save."""
        self.data[key] = value
        self.save()

    def get_llm_params(self) -> dict[str, Any]:
        """Get LLM parameters for API calls."""
        return {
            "temperature": self.data.get("temperature", 0.7),
            "top_p": self.data.get("top_p", 0.9),
            "top_k": self.data.get("top_k", 40),
            "n_predict": self.data.get("max_tokens", 4096),
            "repeat_penalty": self.data.get("repeat_penalty", 1.1),
            "stop": self.data.get("stop", []),
        }

    def get_server_url(self) -> str:
        """Get the llama.cpp server URL."""
        return self.data.get("server_url", "http://localhost:8080")

    def get_model(self) -> Optional[str]:
        """Get the selected model."""
        return self.data.get("model")

    def set_model(self, model: str) -> None:
        """Set the model to use."""
        self.set("model", model)

    def get_memory_file(self) -> Path:
        """Get the path to the memory file."""
        return Path.cwd() / self.data.get("memory_file", ".llamaterm/memory.md")

    def get_session_file(self) -> Path:
        """Get the path to the session file."""
        return Path.cwd() / self.data.get("session_file", ".llamaterm/session.json")

    def add_mcp_server(self, name: str, transport: str, **kwargs) -> None:
        """Add an MCP server configuration."""
        servers = self.data.get("mcp_servers", {})
        servers[name] = {"transport": transport, **kwargs}
        self.set("mcp_servers", servers)

    def remove_mcp_server(self, name: str) -> bool:
        """Remove an MCP server configuration."""
        servers = self.data.get("mcp_servers", {})
        if name in servers:
            del servers[name]
            self.set("mcp_servers", servers)
            return True
        return False

    def get_mcp_servers(self) -> dict:
        """Get all MCP server configurations."""
        return self.data.get("mcp_servers", {})

    def __str__(self) -> str:
        """String representation of current config."""
        lines = ["Current Configuration:"]
        for key, value in self.data.items():
            if key == "mcp_servers" and value:
                lines.append(f"  {key}:")
                for name, cfg in value.items():
                    lines.append(f"    {name}: {cfg}")
            else:
                lines.append(f"  {key}: {value}")
        return "\n".join(lines)
