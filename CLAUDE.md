# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

LlamaTerm is an agentic terminal application connecting to a llama.cpp server (router mode) for AI-assisted file operations, command execution, and MCP server integration.

## Running

```bash
./llamaterm           # Standalone executable (no Python needed)
python src/main.py    # From source
```

## Building the Executable

```bash
source .venv/bin/activate
cd src && pyinstaller --onefile --name llamaterm --clean main.py
mv dist/llamaterm ..
rm -rf build dist llamaterm.spec
```

## Development Workflow

**After any code changes:**
1. Test: `python src/main.py`
2. Rebuild executable (see above)
3. Update README.md if features changed
4. Commit all changes to git

**Syntax check:**
```bash
python -m py_compile src/*.py
```

## Architecture

```
src/
├── main.py          # REPL loop, agentic execution, signal handling (Ctrl+C)
├── api_client.py    # llama.cpp OpenAI-compatible API (streaming + non-streaming)
├── config.py        # Config persistence (.llamaterm/config.json)
├── conversation.py  # Message history with auto-save
├── tools.py         # Tool registry (@register_tool decorator)
├── mcp_client.py    # MCP client (stdio + SSE transports)
└── utils.py         # ANSI colors, logging, path safety
```

## Key Patterns

- **Tool Registration**: Use `@register_tool` decorator in `tools.py` - populates `TOOLS` and `TOOL_HANDLERS` dicts
- **Agentic Loop**: `run_agentic_loop()` in `main.py` streams responses, executes tool calls, loops until `task_complete` or no more calls
- **MCP Tools**: Prefixed as `mcp_<server>_<tool>` to avoid collisions

## Adding New Tools

```python
# In src/tools.py
@register_tool(
    name="tool_name",
    description="What this tool does",
    parameters={
        "type": "object",
        "properties": {
            "param": {"type": "string", "description": "Description"}
        },
        "required": ["param"]
    }
)
def tool_name(param: str) -> str:
    return "result"
```

## Runtime Data

Created in working directory under `.llamaterm/`:
- `config.json` - Settings (server_url, model, temperature, etc.)
- `session.json` - Conversation history
- `memory.md` - LLM long-term memory
- `logs/` - Debug logs
