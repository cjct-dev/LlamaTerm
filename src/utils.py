"""Utility functions for LlamaTerm - colors, logging, helpers."""

import logging
import os
import sys
from datetime import datetime
from pathlib import Path

# ANSI color codes
class Colors:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"

    # Foreground colors
    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    MAGENTA = "\033[35m"
    CYAN = "\033[36m"
    WHITE = "\033[37m"

    # Bright variants
    BRIGHT_RED = "\033[91m"
    BRIGHT_GREEN = "\033[92m"
    BRIGHT_YELLOW = "\033[93m"
    BRIGHT_BLUE = "\033[94m"
    BRIGHT_MAGENTA = "\033[95m"
    BRIGHT_CYAN = "\033[96m"


def colorize(text: str, color: str) -> str:
    """Wrap text with ANSI color codes."""
    return f"{color}{text}{Colors.RESET}"


def print_error(msg: str) -> None:
    """Print error message in red."""
    print(colorize(f"[ERROR] {msg}", Colors.RED))


def print_warning(msg: str) -> None:
    """Print warning message in yellow."""
    print(colorize(f"[WARN] {msg}", Colors.YELLOW))


def print_info(msg: str) -> None:
    """Print info message in cyan."""
    print(colorize(f"[INFO] {msg}", Colors.CYAN))


def print_success(msg: str) -> None:
    """Print success message in green."""
    print(colorize(f"[OK] {msg}", Colors.GREEN))


def print_llm(msg: str) -> None:
    """Print LLM response."""
    print(colorize(msg, Colors.WHITE))


def print_tool(tool_name: str, msg: str) -> None:
    """Print tool execution info."""
    print(colorize(f"[{tool_name}] ", Colors.MAGENTA) + msg)


def get_log_dir() -> Path:
    """Get or create the log directory."""
    log_dir = Path.cwd() / ".llamaterm" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir


def setup_logging() -> logging.Logger:
    """Set up error logging to file."""
    log_dir = get_log_dir()
    log_file = log_dir / f"llamaterm_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

    logger = logging.getLogger("llamaterm")
    logger.setLevel(logging.DEBUG)

    # File handler for all logs
    fh = logging.FileHandler(log_file)
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    ))

    # Console handler for errors only (if needed)
    ch = logging.StreamHandler()
    ch.setLevel(logging.ERROR)
    ch.setFormatter(logging.Formatter('%(levelname)s: %(message)s'))

    logger.addHandler(fh)
    logger.addHandler(ch)

    logger.info(f"Logging initialized. Log file: {log_file}")
    return logger


def get_current_datetime() -> str:
    """Get current date and time as formatted string."""
    now = datetime.now()
    return now.strftime("%Y-%m-%d %H:%M:%S %Z").strip()


def get_working_dir() -> Path:
    """Get the current working directory."""
    return Path.cwd()


def is_safe_path(path: str) -> bool:
    """Check if a path is within the working directory (security check)."""
    try:
        working_dir = get_working_dir().resolve()
        target_path = (working_dir / path).resolve()
        return str(target_path).startswith(str(working_dir))
    except Exception:
        return False


def truncate_string(s: str, max_length: int = 500) -> str:
    """Truncate a string if it exceeds max length."""
    if len(s) <= max_length:
        return s
    return s[:max_length] + f"... [truncated, {len(s)} chars total]"
