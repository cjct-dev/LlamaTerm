# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

LlamaTerm is an agentic terminal application that connects to a llama.cpp server (in router mode) to provide an AI assistant with tool capabilities for file operations, command execution, and MCP server integration.

## Running the Application

```bash
# Standalone executable (no Python required)
./llamaterm

# Or run from source
python src/main.py
```

The application expects a llama.cpp server running with the OpenAI-compatible API. Configure the server URL via `/set server_url <url>` or edit `.llamaterm/config.json`.

## Project Structure

```
llamaterm           # Standalone executable (PyInstaller bundle)
src/                # Python source code
  main.py           # REPL loop, agentic execution cycle, signal handling
  api_client.py     # llama.cpp OpenAI-compatible API client (streaming + non-streaming)
  config.py         # Configuration persistence (.llamaterm/config.json)
  conversation.py   # Message history with auto-save (.llamaterm/session.json)
  tools.py          # Tool registry and built-in tools (file ops, commands, memory)
  mcp_client.py     # MCP client with stdio and SSE transports
  utils.py          # ANSI colors, logging setup, path safety checks
```

## Building the Executable

```bash
uv venv .venv
source .venv/bin/activate
uv pip install pyinstaller
cd src && pyinstaller --onefile --name llamaterm --clean main.py
mv dist/llamaterm ..
rm -rf build dist llamaterm.spec
```

## Key Design Patterns

- **Tool Registration**: Tools are registered via `@register_tool` decorator in `tools.py`. The decorator populates `TOOLS` dict and `TOOL_HANDLERS` dict.
- **Agentic Loop**: `run_agentic_loop()` in `main.py` streams LLM responses, parses tool calls, executes tools, adds results to conversation, and loops until no more tool calls or user interrupt.
- **Task Completion**: LLM calls `task_complete` tool to signal task completion, which breaks the agentic loop.
- **Conversation Persistence**: Messages auto-save to `.llamaterm/session.json` after each message.

## MCP Integration

MCP servers can be added via `/mcp add NAME COMMAND` (stdio) or `/mcp add NAME URL` (SSE). MCP tools are prefixed with `mcp_<server>_<tool>` to avoid name collisions.

## Configuration

All config lives in `.llamaterm/config.json`:
- `server_url`: llama.cpp server endpoint
- `model`: Selected model ID
- `temperature`, `top_p`, `top_k`, `max_tokens`, `repeat_penalty`: LLM parameters
- `mcp_servers`: Dict of configured MCP servers

## Data Files (created at runtime in working directory)

- `.llamaterm/config.json` - Configuration
- `.llamaterm/session.json` - Conversation history
- `.llamaterm/memory.md` - LLM long-term memory
- `.llamaterm/logs/` - Debug logs with timestamps

## Development

```bash
# Syntax check
python -m py_compile src/*.py

# Test server connectivity
cd src && python -c "from config import Config; from api_client import LlamaClient; c = LlamaClient(Config()); print(c.health_check())"
```

## Adding New Tools

Add to `src/tools.py`:
```python
@register_tool(
    name="tool_name",
    description="What this tool does",
    parameters={
        "type": "object",
        "properties": {
            "param": {"type": "string", "description": "Parameter description"}
        },
        "required": ["param"]
    }
)
def tool_name(param: str) -> str:
    # Implementation
    return "result"
```
