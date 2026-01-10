"""Conversation management with persistence for LlamaTerm."""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from config import Config
from utils import get_current_datetime

logger = logging.getLogger("llamaterm")


SYSTEM_PROMPT = """You are LlamaTerm, a helpful AI assistant running in a terminal environment. You have access to tools that let you:
- Read, write, and manage files in the working directory
- Execute shell commands
- Store and recall information from long-term memory
- Get the current date and time

Current date and time: {datetime}
Working directory: {working_dir}

Guidelines:
- Be concise and helpful
- When working on complex tasks, work iteratively: plan, execute, verify, and correct as needed
- Use tools proactively to accomplish tasks
- Save important information to memory for future sessions
- When you complete a task, use the task_complete tool to signal completion
- If you encounter errors, try to fix them and continue

You can work autonomously on multi-step tasks. The user can interrupt you at any time by pressing Ctrl+C."""


class Message:
    """Represents a conversation message."""

    def __init__(self, role: str, content: str, tool_calls: Optional[list] = None,
                 tool_call_id: Optional[str] = None, name: Optional[str] = None):
        self.role = role
        self.content = content
        self.tool_calls = tool_calls
        self.tool_call_id = tool_call_id
        self.name = name
        self.timestamp = datetime.now().isoformat()

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        d = {
            "role": self.role,
            "content": self.content,
            "timestamp": self.timestamp,
        }
        if self.tool_calls:
            d["tool_calls"] = self.tool_calls
        if self.tool_call_id:
            d["tool_call_id"] = self.tool_call_id
        if self.name:
            d["name"] = self.name
        return d

    def to_api_format(self) -> dict:
        """Convert to API message format."""
        msg = {"role": self.role, "content": self.content}
        if self.tool_calls:
            msg["tool_calls"] = self.tool_calls
        if self.tool_call_id:
            msg["tool_call_id"] = self.tool_call_id
        if self.name:
            msg["name"] = self.name
        return msg

    @classmethod
    def from_dict(cls, d: dict) -> "Message":
        """Create from dictionary."""
        msg = cls(
            role=d["role"],
            content=d.get("content", ""),
            tool_calls=d.get("tool_calls"),
            tool_call_id=d.get("tool_call_id"),
            name=d.get("name"),
        )
        if "timestamp" in d:
            msg.timestamp = d["timestamp"]
        return msg


class Conversation:
    """Manages conversation history with auto-save."""

    def __init__(self, config: Config):
        self.config = config
        self.messages: list[Message] = []
        self.session_file = config.get_session_file()
        self._load_session()

    def _load_session(self) -> None:
        """Load session from file if exists."""
        if self.session_file.exists():
            try:
                with open(self.session_file, 'r') as f:
                    data = json.load(f)
                    self.messages = [Message.from_dict(m) for m in data.get("messages", [])]
                    logger.info(f"Loaded session with {len(self.messages)} messages")
            except (json.JSONDecodeError, IOError) as e:
                logger.warning(f"Could not load session: {e}")
                self.messages = []

    def save_session(self) -> None:
        """Save session to file."""
        if not self.config.get("auto_save", True):
            return

        try:
            self.session_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.session_file, 'w') as f:
                json.dump({
                    "messages": [m.to_dict() for m in self.messages],
                    "saved_at": datetime.now().isoformat(),
                }, f, indent=2)
        except IOError as e:
            logger.error(f"Could not save session: {e}")

    def add_user_message(self, content: str) -> Message:
        """Add a user message."""
        msg = Message(role="user", content=content)
        self.messages.append(msg)
        self.save_session()
        return msg

    def add_assistant_message(self, content: str, tool_calls: Optional[list] = None) -> Message:
        """Add an assistant message."""
        msg = Message(role="assistant", content=content, tool_calls=tool_calls)
        self.messages.append(msg)
        self.save_session()
        return msg

    def add_tool_result(self, tool_call_id: str, name: str, result: str) -> Message:
        """Add a tool result message."""
        msg = Message(role="tool", content=result, tool_call_id=tool_call_id, name=name)
        self.messages.append(msg)
        self.save_session()
        return msg

    def get_system_message(self) -> dict:
        """Get the system message with current context."""
        from utils import get_working_dir
        return {
            "role": "system",
            "content": SYSTEM_PROMPT.format(
                datetime=get_current_datetime(),
                working_dir=str(get_working_dir())
            )
        }

    def get_api_messages(self) -> list[dict]:
        """Get messages in API format with system message."""
        messages = [self.get_system_message()]
        for msg in self.messages:
            messages.append(msg.to_api_format())
        return messages

    def clear(self) -> None:
        """Clear conversation history."""
        self.messages = []
        self.save_session()

    def get_last_assistant_message(self) -> Optional[Message]:
        """Get the last assistant message."""
        for msg in reversed(self.messages):
            if msg.role == "assistant":
                return msg
        return None

    def truncate_if_needed(self, max_messages: int = 100) -> None:
        """Truncate old messages if conversation is too long."""
        if len(self.messages) > max_messages:
            # Keep first few and last many
            keep_start = 10
            keep_end = max_messages - keep_start
            self.messages = self.messages[:keep_start] + self.messages[-keep_end:]
            self.save_session()
            logger.info(f"Truncated conversation to {len(self.messages)} messages")

    def __len__(self) -> int:
        return len(self.messages)
