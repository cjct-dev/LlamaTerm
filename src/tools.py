"""Tool definitions and handlers for LlamaTerm agentic capabilities."""

import json
import logging
import os
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Optional

from utils import get_working_dir, truncate_string

logger = logging.getLogger("llamaterm")


# Tool registry
TOOLS: dict[str, dict] = {}
TOOL_HANDLERS: dict[str, Callable] = {}


def register_tool(name: str, description: str, parameters: dict):
    """Decorator to register a tool with its handler."""
    def decorator(func: Callable):
        TOOLS[name] = {
            "name": name,
            "description": description,
            "parameters": parameters,
        }
        TOOL_HANDLERS[name] = func
        return func
    return decorator


def get_all_tools() -> list[dict]:
    """Get all registered tools in API format."""
    from api_client import format_tool_for_api
    return [format_tool_for_api(tool) for tool in TOOLS.values()]


def execute_tool(name: str, arguments: dict) -> str:
    """Execute a tool by name with given arguments."""
    if name not in TOOL_HANDLERS:
        return f"Error: Unknown tool '{name}'"

    try:
        logger.info(f"Executing tool: {name} with args: {arguments}")
        result = TOOL_HANDLERS[name](**arguments)
        logger.debug(f"Tool {name} result: {truncate_string(str(result), 200)}")
        return result
    except Exception as e:
        logger.error(f"Tool {name} failed: {e}", exc_info=True)
        return f"Error executing {name}: {str(e)}"


# ============================================================================
# Command Execution
# ============================================================================

@register_tool(
    name="run_command",
    description="Execute a shell command in the working directory. Use for running programs, scripts, build commands, etc. Commands are executed in a bash shell.",
    parameters={
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": "The shell command to execute"
            },
            "timeout": {
                "type": "integer",
                "description": "Timeout in seconds (default: 60, max: 300)",
                "default": 60
            }
        },
        "required": ["command"]
    }
)
def run_command(command: str, timeout: int = 60) -> str:
    """Execute a shell command."""
    timeout = min(timeout, 300)  # Cap at 5 minutes

    # Security: Log all commands
    logger.info(f"Executing command: {command}")

    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=get_working_dir(),
            env={**os.environ, "TERM": "dumb"}  # Prevent color codes in output
        )

        output_parts = []
        if result.stdout:
            output_parts.append(f"STDOUT:\n{result.stdout}")
        if result.stderr:
            output_parts.append(f"STDERR:\n{result.stderr}")

        output = "\n".join(output_parts) if output_parts else "(no output)"

        # Truncate if too long
        if len(output) > 20000:
            output = output[:20000] + f"\n\n[Output truncated - {len(output)} chars total]"

        return f"Exit code: {result.returncode}\n{output}"
    except subprocess.TimeoutExpired:
        return f"Error: Command timed out after {timeout} seconds"
    except Exception as e:
        return f"Error executing command: {e}"


# ============================================================================
# Date/Time
# ============================================================================

@register_tool(
    name="get_datetime",
    description="Get the current date and time.",
    parameters={
        "type": "object",
        "properties": {},
        "required": []
    }
)
def get_datetime() -> str:
    """Get current date and time."""
    now = datetime.now()
    return f"Current date and time: {now.strftime('%Y-%m-%d %H:%M:%S')} ({now.strftime('%A, %B %d, %Y')})"


# ============================================================================
# Long-term Memory
# ============================================================================

@register_tool(
    name="read_memory",
    description="Read the long-term memory file. Use this to recall important information from previous sessions.",
    parameters={
        "type": "object",
        "properties": {},
        "required": []
    }
)
def read_memory() -> str:
    """Read the long-term memory file."""
    memory_path = get_working_dir() / ".llamaterm" / "memory.md"
    if not memory_path.exists():
        return "Memory file is empty. Use write_memory to save important information."

    try:
        return memory_path.read_text(encoding='utf-8')
    except Exception as e:
        return f"Error reading memory: {e}"


@register_tool(
    name="write_memory",
    description="Write to the long-term memory file. Use this to save important information that should persist across sessions. Overwrites existing content.",
    parameters={
        "type": "object",
        "properties": {
            "content": {
                "type": "string",
                "description": "Content to write to memory"
            }
        },
        "required": ["content"]
    }
)
def write_memory(content: str) -> str:
    """Write to the long-term memory file."""
    memory_path = get_working_dir() / ".llamaterm" / "memory.md"
    try:
        memory_path.parent.mkdir(parents=True, exist_ok=True)
        memory_path.write_text(content, encoding='utf-8')
        return "Memory updated successfully"
    except Exception as e:
        return f"Error writing memory: {e}"


@register_tool(
    name="append_memory",
    description="Append to the long-term memory file. Use this to add new information without overwriting existing memories.",
    parameters={
        "type": "object",
        "properties": {
            "content": {
                "type": "string",
                "description": "Content to append to memory"
            }
        },
        "required": ["content"]
    }
)
def append_memory(content: str) -> str:
    """Append to the long-term memory file."""
    memory_path = get_working_dir() / ".llamaterm" / "memory.md"
    try:
        memory_path.parent.mkdir(parents=True, exist_ok=True)
        with open(memory_path, 'a', encoding='utf-8') as f:
            f.write("\n" + content)
        return "Memory appended successfully"
    except Exception as e:
        return f"Error appending to memory: {e}"


# ============================================================================
# Task Completion Signal
# ============================================================================

@register_tool(
    name="task_complete",
    description="Signal that the current task is complete. Use this when you have finished working on a task and want to return control to the user.",
    parameters={
        "type": "object",
        "properties": {
            "summary": {
                "type": "string",
                "description": "Brief summary of what was accomplished"
            }
        },
        "required": ["summary"]
    }
)
def task_complete(summary: str) -> str:
    """Signal task completion - handled specially by the main loop."""
    return f"TASK_COMPLETE: {summary}"
