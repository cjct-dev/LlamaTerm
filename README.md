# LlamaTerm

An agentic terminal application that connects to a [llama.cpp](https://github.com/ggerganov/llama.cpp) server to provide an AI assistant with autonomous tool capabilities for file operations, command execution, and MCP server integration.

## Features

- **Model Selection**: Connects to llama.cpp server in router mode, allowing selection from multiple loaded models
- **Agentic Execution**: LLM works autonomously on complex multi-step tasks, iterating until completion
- **File Operations**: Read, write, append, list, and delete files within the working directory
- **Command Execution**: Run shell commands with timeout protection and output capture
- **Long-term Memory**: Persistent memory file that survives across sessions
- **MCP Integration**: Connect to Model Context Protocol servers via stdio or SSE transports
- **Session Persistence**: Conversation history auto-saves and restores between sessions
- **Configurable Parameters**: Adjust temperature, top_p, top_k, max_tokens, and other LLM settings
- **User Interrupt**: Press Ctrl+C to interrupt autonomous execution, twice to exit
- **Error Logging**: Debug logs saved for troubleshooting

## Requirements

### For the Standalone Executable
- Linux x86_64 system
- Network access to a llama.cpp server

### For Running from Source
- Python 3.10+
- Network access to a llama.cpp server

### llama.cpp Server Setup

LlamaTerm requires a llama.cpp server running with the OpenAI-compatible API. For router mode (multiple models):

```bash
llama-server --host 0.0.0.0 --port 8080 --router
```

See the [llama.cpp server documentation](https://github.com/ggerganov/llama.cpp/blob/master/examples/server/README.md) for detailed setup instructions.

## Installation

### Option 1: Build Standalone Executable

```bash
git clone https://github.com/yourusername/LlamaTerm.git
cd LlamaTerm

# Create virtual environment and install PyInstaller
uv venv .venv
source .venv/bin/activate
uv pip install pyinstaller

# Build executable
cd src && pyinstaller --onefile --name llamaterm --clean main.py
mv dist/llamaterm ..
rm -rf build dist llamaterm.spec
cd ..

./llamaterm
```

### Option 2: Run from Source

```bash
git clone https://github.com/yourusername/LlamaTerm.git
cd LlamaTerm
python src/main.py
```

## Usage

### Starting LlamaTerm

```bash
./llamaterm           # Standalone executable
python src/main.py    # From source
```

On first run, you'll be prompted to select a model from those available on the server.

### Example Session

```
============================================================
  LlamaTerm - Agentic Terminal Assistant
============================================================

[INFO] Connecting to server: http://localhost:8080
[OK] Server connected
[INFO] Available models: llama-3-8b, mistral-7b, codellama-13b

Select a model:
  1. llama-3-8b
  2. mistral-7b
  3. codellama-13b
Enter number: 1
[OK] Using model: llama-3-8b

[INFO] Type /help for commands, or start chatting
[INFO] Press Ctrl+C to interrupt, twice to exit

You: Create a Python script that prints the first 10 fibonacci numbers

[write_file] Executing with args: {"path": "fibonacci.py", "content": "..."}
  Result: Successfully wrote 245 characters to 'fibonacci.py'

[run_command] Executing with args: {"command": "python fibonacci.py"}
  Result: Exit code: 0
          STDOUT: 0, 1, 1, 2, 3, 5, 8, 13, 21, 34

[task_complete] Executing with args: {"summary": "Created fibonacci.py and verified it works"}

[OK] Created fibonacci.py and verified it works
```

## Commands

| Command | Description |
|---------|-------------|
| `/help` | Show help message |
| `/quit`, `/exit` | Exit LlamaTerm |
| `/clear` | Clear conversation history |
| `/config` | Show current configuration |
| `/set KEY VALUE` | Set a configuration value |
| `/model [NAME]` | Show or change current model |
| `/models` | List available models |
| `/mcp` | Manage MCP servers |
| `/tools` | List available tools |
| `/memory` | Show long-term memory contents |
| `/save` | Force save session |

### Configuration Keys

Use `/set KEY VALUE` to change these settings:

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `temperature` | float | 0.7 | Randomness of responses (0.0-2.0) |
| `top_p` | float | 0.9 | Nucleus sampling threshold |
| `top_k` | int | 40 | Top-k sampling |
| `max_tokens` | int | 4096 | Maximum response length |
| `repeat_penalty` | float | 1.1 | Penalty for repetition |
| `server_url` | string | - | llama.cpp server URL |
| `request_timeout` | int/null | null | API timeout in seconds (null = no timeout) |

**Note on timeouts:** By default, there is no timeout for API requests. This allows large models that are partially offloaded to system RAM (which can be very slow) to complete without timing out. Set `request_timeout` only if you need to limit wait time.

## Built-in Tools

The AI has access to these tools:

| Tool | Description |
|------|-------------|
| `run_command` | Execute a shell command (use for file ops: `cat`, `ls`, `echo >`, etc.) |
| `get_datetime` | Get current date and time |
| `read_memory` | Read long-term memory |
| `write_memory` | Write to long-term memory |
| `append_memory` | Append to long-term memory |
| `task_complete` | Signal task completion |

**Note:** File operations are handled via `run_command` using standard Linux commands (`cat`, `ls`, `echo`, `rm`, etc.). This keeps the tool set minimal while providing full filesystem access.

## Model Compatibility

Not all models support tool calling. Models with chat templates that require strict user/assistant alternation (like Gemma) cannot use the OpenAI-style tool calling format.

**Incompatible models are automatically detected** and marked with `[no tools]` in the model selection list. When using an incompatible model:
- A warning is displayed: "Running in chat-only mode"
- Tools are disabled (no file operations, commands, or MCP tools)
- The AI functions as a standard chatbot

**Known incompatible model patterns:**
- `gemma` (all variants)
- `phi-2`, `phi2`

To add custom models to the no-tools list, edit `.llamaterm/config.json`:
```json
{
  "no_tool_models": ["my-custom-model"]
}
```

## MCP Integration

LlamaTerm supports the [Model Context Protocol](https://modelcontextprotocol.io/) for extending capabilities with external tools.

### Adding MCP Servers

```bash
# Add a stdio-based MCP server (runs as subprocess)
/mcp add myserver /path/to/mcp-server

# Add an SSE-based MCP server (connects via HTTP)
/mcp add remoteserver https://example.com/mcp

# List connected servers
/mcp list

# Remove a server
/mcp remove myserver
```

MCP tools appear with the prefix `mcp_<server>_<tool>` and are automatically available to the AI.

## Data Storage

LlamaTerm creates a `.llamaterm/` directory in the working directory:

```
.llamaterm/
├── config.json      # Configuration settings
├── session.json     # Conversation history
├── memory.md        # Long-term memory file
└── logs/            # Debug log files
    └── llamaterm_YYYYMMDD_HHMMSS.log
```

## Architecture

```
src/
├── main.py          # REPL loop and agentic execution
├── api_client.py    # llama.cpp API client (streaming + non-streaming)
├── config.py        # Configuration management
├── conversation.py  # Message history and persistence
├── tools.py         # Built-in tool definitions
├── mcp_client.py    # MCP client (stdio + SSE transports)
└── utils.py         # Utilities (colors, logging, helpers)
```

### How the Agentic Loop Works

1. User enters a message
2. Message is added to conversation history
3. LLM receives full conversation + available tools
4. LLM responds with text and/or tool calls
5. Tool calls are executed, results added to conversation
6. Loop continues until LLM stops calling tools or calls `task_complete`
7. User can interrupt at any time with Ctrl+C

## Security Considerations

- **Path Safety**: File operations are restricted to the working directory and subdirectories
- **Command Logging**: All shell commands are logged for audit purposes
- **No Secrets**: Avoid running LlamaTerm in directories containing sensitive files
- **Network**: Only connects to the configured llama.cpp server

## Troubleshooting

### Cannot connect to server
- Verify the server URL with `/config`
- Check if llama.cpp server is running
- Try: `/set server_url http://your-server:port`

### Model not responding
- Check server logs for errors
- Try a different model with `/models` and `/model NAME`
- Reduce `max_tokens` if responses timeout

### Debug logs
Check `.llamaterm/logs/` for detailed error information.

## License

MIT License - See LICENSE file for details.

## Acknowledgments

- [llama.cpp](https://github.com/ggerganov/llama.cpp) - Efficient LLM inference
- [Model Context Protocol](https://modelcontextprotocol.io/) - Tool integration standard
- [PyInstaller](https://pyinstaller.org/) - Standalone executable bundling