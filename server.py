"""Local filesystem MCP server with live-switchable state for GeminiMCP CLI.

Credits: Fikus & Hydrogen
"""

from __future__ import annotations

import os
import subprocess
import threading
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from mcp.server.mcpserver import Image, MCPServer
from mcp.server.transport_security import TransportSecuritySettings

DEFAULT_ROOT = Path(r"C:\Users\evgen\OneDrive\Desktop\GeminiMCP")


@dataclass
class ServerState:
    """Thread-safe mutable runtime state shared between CLI and MCP tools."""

    root_dir: Path
    allow_exec: bool = False
    session_name: str = "default"
    lock: threading.Lock = field(default_factory=threading.Lock)
    logs: deque[str] = field(default_factory=lambda: deque(maxlen=100))
    on_log: Callable[[str], None] | None = None

    def set_root(self, new_root: Path) -> Path:
        resolved = new_root.expanduser().resolve()
        resolved.mkdir(parents=True, exist_ok=True)
        with self.lock:
            self.root_dir = resolved
        self.record("cli", f"Switched folder -> {resolved}")
        return resolved

    def get_root(self) -> Path:
        with self.lock:
            return self.root_dir

    def set_exec(self, enabled: bool) -> None:
        with self.lock:
            self.allow_exec = enabled
        self.record("cli", f"run_command -> {'ON' if enabled else 'OFF'}")

    def is_exec_enabled(self) -> bool:
        with self.lock:
            return self.allow_exec

    def record(self, tool: str, detail: str) -> None:
        ts = datetime.now().strftime("%H:%M:%S")
        entry = f"[{ts}] {tool}: {detail}"
        with self.lock:
            self.logs.append(entry)
            cb = self.on_log
        if cb:
            cb(entry)

    def recent_logs(self, limit: int = 15) -> list[str]:
        with self.lock:
            return list(self.logs)[-limit:]


def create_server(state: ServerState, log_level: str = "WARNING") -> MCPServer:
    """Create an MCPServer bound to the shared ServerState."""
    state.get_root().mkdir(parents=True, exist_ok=True)

    mcp = MCPServer(
        name="local-files",
        title="Local PC Files (GeminiMCP)",
        instructions=(
            "You have access to the user's active local workspace folder via MCP tools. "
            "All paths must be relative to the workspace root."
        ),
        log_level=log_level,  # type: ignore[arg-type]
    )

    def _resolve_safe_path(rel_path: str = ".") -> tuple[Path, Path]:
        root = state.get_root()
        cleaned = (rel_path or ".").strip().lstrip("/\\")
        target = (root / cleaned).resolve()
        if not target.is_relative_to(root):
            raise ValueError(f"Access denied: '{rel_path}' escapes the allowed folder.")
        return root, target

    @mcp.tool()
    def list_files(path: str = ".") -> str:
        """List files and folders inside the active workspace directory."""
        root, target = _resolve_safe_path(path)
        state.record("list_files", path)
        if not target.exists():
            return f"Path does not exist: {path}"
        if not target.is_dir():
            return f"Not a directory: {path}"

        entries = sorted(target.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
        if not entries:
            return "(empty directory)"

        lines: list[str] = []
        for entry in entries:
            rel = entry.relative_to(root).as_posix()
            if entry.is_dir():
                lines.append(f"[DIR]  {rel}/")
            else:
                lines.append(f"[FILE] {rel} ({entry.stat().st_size} bytes)")
        return "\n".join(lines)

    @mcp.tool()
    def read_file(path: str, start_line: int = 1, end_line: int | None = None) -> str:
        """Read a UTF-8 text file inside the active workspace, optionally by 1-based line range."""
        _, target = _resolve_safe_path(path)
        state.record("read_file", path)
        if not target.is_file():
            return f"File not found: {path}"

        text = target.read_text(encoding="utf-8", errors="replace")
        if start_line <= 1 and end_line is None:
            return text

        lines = text.splitlines()
        start_idx = max(0, start_line - 1)
        end_idx = len(lines) if end_line is None else min(len(lines), end_line)
        return "\n".join(f"{i + 1}: {lines[i]}" for i in range(start_idx, end_idx))

    @mcp.tool()
    def read_image(path: str) -> Image | str:
        """Read an image file (PNG, JPG, WEBP, GIF) from the active workspace."""
        _, target = _resolve_safe_path(path)
        state.record("read_image", path)
        if not target.is_file():
            return f"Image not found: {path}"
        return Image(path=str(target))

    @mcp.tool()
    def write_file(path: str, content: str) -> str:
        """Create or overwrite a UTF-8 text file inside the active workspace."""
        root, target = _resolve_safe_path(path)
        if target == root:
            raise ValueError("Cannot overwrite the root directory itself.")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        rel = target.relative_to(root).as_posix()
        state.record("write_file", f"{rel} ({len(content)} chars)")
        return f"Saved {rel} ({len(content)} chars)."

    @mcp.tool()
    def edit_file(path: str, old_text: str, new_text: str) -> str:
        """Replace an exact occurrence of old_text with new_text in an existing file."""
        root, target = _resolve_safe_path(path)
        if not target.is_file():
            return f"File not found: {path}"

        content = target.read_text(encoding="utf-8")
        count = content.count(old_text)
        if count == 0:
            return "Error: old_text was not found in the file."
        if count > 1:
            return f"Error: old_text matched {count} times; provide more surrounding context."

        target.write_text(content.replace(old_text, new_text, 1), encoding="utf-8")
        rel = target.relative_to(root).as_posix()
        state.record("edit_file", rel)
        return f"Updated {rel}."

    @mcp.tool()
    def delete_file(path: str) -> str:
        """Delete a file inside the active workspace."""
        root, target = _resolve_safe_path(path)
        if target == root:
            raise ValueError("Cannot delete the root directory.")
        if not target.exists():
            return f"File not found: {path}"
        if target.is_dir():
            return "Error: target is a directory; only files can be deleted."
        rel = target.relative_to(root).as_posix()
        target.unlink()
        state.record("delete_file", rel)
        return f"Deleted {rel}."

    @mcp.tool()
    def search_files(query: str, path: str = ".") -> str:
        """Search filenames and UTF-8 text files for a case-insensitive substring."""
        root, base = _resolve_safe_path(path)
        state.record("search_files", f"'{query}' in {path}")
        if not base.exists():
            return f"Path does not exist: {path}"

        needle = query.lower()
        matches: list[str] = []
        for item in sorted(base.rglob("*")):
            rel = item.relative_to(root).as_posix()
            if needle in item.name.lower():
                matches.append(f"[NAME] {rel}")
            if item.is_file() and item.stat().st_size <= 1_000_000:
                try:
                    for line_no, line in enumerate(item.read_text(encoding="utf-8").splitlines(), start=1):
                        if needle in line.lower():
                            matches.append(f"{rel}:{line_no}: {line.strip()[:160]}")
                            if len(matches) >= 50:
                                return "\n".join(matches)
                except UnicodeDecodeError:
                    continue
        return "\n".join(matches) if matches else "No matches found."

    @mcp.tool()
    def run_command(command: str, timeout_seconds: int = 30) -> str:
        """Run a shell command inside the active workspace (requires /exec on or --allow-exec)."""
        if not state.is_exec_enabled():
            state.record("run_command", f"BLOCKED ({command})")
            return "Error: run_command is disabled. Enable it in GeminiMCP CLI with: /exec on"

        root = state.get_root()
        state.record("run_command", command)
        timeout = max(1, min(timeout_seconds, 120))
        proc = subprocess.run(
            command,
            cwd=root,
            shell=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
        parts = [f"Exit code: {proc.returncode}"]
        if proc.stdout.strip():
            parts.append(f"STDOUT:\n{proc.stdout.strip()[:8000]}")
        if proc.stderr.strip():
            parts.append(f"STDERR:\n{proc.stderr.strip()[:4000]}")
        return "\n\n".join(parts)

    return mcp


def run_server(
    state: ServerState,
    host: str = "127.0.0.1",
    port: int = 8000,
    log_level: str = "WARNING",
) -> None:
    """Run the stateless Streamable HTTP MCP server."""
    mcp = create_server(state=state, log_level=log_level)
    mcp.run(
        transport="streamable-http",
        host=host,
        port=port,
        streamable_http_path="/mcp",
        stateless_http=True,
        json_response=True,
        transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
    )


if __name__ == "__main__":
    root = Path(os.environ.get("GEMINI_MCP_ROOT", str(DEFAULT_ROOT)))
    host = os.environ.get("GEMINI_MCP_HOST", "127.0.0.1")
    port = int(os.environ.get("GEMINI_MCP_PORT", "8000"))
    allow_exec = os.environ.get("GEMINI_MCP_ALLOW_EXEC", "0") == "1"
    state = ServerState(root_dir=root.resolve(), allow_exec=allow_exec)
    print(f"Starting GeminiMCP server on http://{host}:{port}/mcp (root: {state.get_root()})")
    run_server(state=state, host=host, port=port, log_level="INFO")
