# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

LlamaTerm is an agentic terminal application connecting to a llama.cpp server (router mode) for AI-assisted file operations, command execution, and MCP server integration. Uses only Python standard library (no pip dependencies for runtime).

## Running

```bash
./llamaterm           # Standalone executable (no Python needed)
python src/main.py    # From source
```

Default server: `http://100.82.203.89:8080` (configurable via `/set server_url`)

## Building the Executable

```bash
source .venv/bin/activate
cd src && pyinstaller --onefile --name llamaterm --clean main.py
mv dist/llamaterm ..
rm -rf build dist llamaterm.spec
```

Results in ~8MB standalone Linux x86_64 executable.

## Development Workflow

**After any code changes:**
1. Syntax check: `python -m py_compile src/*.py`
2. Test: `python src/main.py`
3. Rebuild executable (see above)
4. Update README.md if features changed
5. Commit all changes to git

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

- **Tool Registration**: `@register_tool` decorator in `tools.py` populates `TOOLS` dict and `TOOL_HANDLERS` dict
- **Agentic Loop**: `run_agentic_loop()` in `main.py` streams responses, executes tool calls, loops until `task_complete` or no more calls (max 50 iterations safety limit)
- **MCP Tools**: Prefixed as `mcp_<server>_<tool>` to avoid collisions
- **Path Safety**: `is_safe_path()` in `utils.py` restricts file ops to working directory

## Implementation Details

### Streaming Tool Calls
Tool calls arrive chunked in `delta["tool_calls"]` with incremental `arguments` strings. Must accumulate across chunks before JSON parsing. See `run_agentic_loop()` in main.py.

### Content Can Be None
When LLM only returns tool calls (no text), `message["content"]` is `None`. Handle this in display logic - only print "Assistant:" prefix when there's actual content.

### Signal Handling
- Single Ctrl+C: Sets `interrupted = True`, breaks agentic loop gracefully
- Double Ctrl+C: Exits application
- Implemented via `signal.SIGINT` handler in `LlamaTerm.__init__()`

### Session Management
- Auto-saves to `.llamaterm/session.json` after each message
- Truncates at 100 messages (keeps first 10 + last 90)
- Restores on startup if session file exists

### llama.cpp Server API
- Uses OpenAI-compatible endpoints: `/v1/models`, `/v1/chat/completions`
- Router mode: model selected via `model` field in request
- Health check: `/health` returns `{"status": "ok"}`
- Supports both streaming (SSE) and non-streaming responses
- **No timeout by default** for chat completions - large models offloaded to RAM can be very slow
- Optional `request_timeout` config (seconds) if timeout is desired

### Model Compatibility
Not all models support tool calling. Models with chat templates requiring strict user/assistant role alternation (e.g., Gemma) fail with HTTP 500 when tool messages (`role: "tool"`) are included.

**Detection**: `config.model_supports_tools()` checks model name against `NO_TOOL_SUPPORT_PATTERNS` in `config.py`

**Behavior when tools unsupported**:
- `self.tools_enabled = False` in main.py
- Warning displayed to user
- `tools=None` passed to `chat_completion()` - runs as plain chatbot
- Model selection shows `[no tools]` marker

**To add new incompatible models**: Add pattern to `NO_TOOL_SUPPORT_PATTERNS` in `config.py` or user can add to `no_tool_models` list in config.json

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

Tool return values should be strings. For task completion signal, return `"TASK_COMPLETE: summary"`.

## Runtime Data

Created in working directory under `.llamaterm/`:
- `config.json` - Settings (server_url, model, temperature, etc.)
- `session.json` - Conversation history (auto-saved)
- `memory.md` - LLM long-term memory (persistent across sessions)
- `logs/` - Debug logs with timestamps

## Environment Notes

- System uses `uv` for venv/pip operations (not raw pip)
- PyInstaller installed in `.venv/` for building
- No external runtime dependencies - all stdlib
