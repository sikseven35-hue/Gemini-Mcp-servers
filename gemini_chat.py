"""Lightweight Gemini API client with local tool-calling for CLI vibe-coding.

Credits: Fikus & Hydrogen
"""

from __future__ import annotations

import base64
import json
import subprocess
import urllib.error
import urllib.request
from pathlib import Path

from server import ServerState

DEFAULT_MODELS = [
    "gemini-2.5-pro",
    "gemini-2.5-flash",
    "gemini-2.5-flash-lite",
    "gemini-2.0-flash",
]

TOOL_DECLARATIONS = [
    {
        "name": "list_files",
        "description": "List files and folders inside the active workspace directory.",
        "parameters": {
            "type": "OBJECT",
            "properties": {"path": {"type": "STRING", "description": "Relative path (default '.')"}},
        },
    },
    {
        "name": "read_file",
        "description": "Read a UTF-8 text file inside the active workspace.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "path": {"type": "STRING"},
                "start_line": {"type": "INTEGER"},
                "end_line": {"type": "INTEGER"},
            },
            "required": ["path"],
        },
    },
    {
        "name": "write_file",
        "description": "Create or overwrite a UTF-8 text file inside the active workspace.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "path": {"type": "STRING"},
                "content": {"type": "STRING"},
            },
            "required": ["path", "content"],
        },
    },
    {
        "name": "edit_file",
        "description": "Replace an exact occurrence of old_text with new_text in an existing file.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "path": {"type": "STRING"},
                "old_text": {"type": "STRING"},
                "new_text": {"type": "STRING"},
            },
            "required": ["path", "old_text", "new_text"],
        },
    },
    {
        "name": "delete_file",
        "description": "Delete a file inside the active workspace.",
        "parameters": {
            "type": "OBJECT",
            "properties": {"path": {"type": "STRING"}},
            "required": ["path"],
        },
    },
    {
        "name": "search_files",
        "description": "Search filenames and UTF-8 text files for a case-insensitive substring.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "query": {"type": "STRING"},
                "path": {"type": "STRING"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "run_command",
        "description": "Run a shell command inside the active workspace (only when /exec on is enabled).",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "command": {"type": "STRING"},
                "timeout_seconds": {"type": "INTEGER"},
            },
            "required": ["command"],
        },
    },
]


def fetch_available_models(api_key: str) -> list[str]:
    """Fetch models supporting generateContent from Gemini API, falling back to DEFAULT_MODELS."""
    if not api_key:
        return list(DEFAULT_MODELS)
    url = f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}"
    try:
        with urllib.request.urlopen(url, timeout=4.0) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        found: list[str] = []
        for item in data.get("models", []):
            methods = item.get("supportedGenerationMethods", [])
            name = item.get("name", "").removeprefix("models/")
            if "generateContent" in methods and name.startswith("gemini-"):
                found.append(name)
        return found[:20] if found else list(DEFAULT_MODELS)
    except Exception:
        return list(DEFAULT_MODELS)


def _resolve_safe(state: ServerState, rel_path: str = ".") -> tuple[Path, Path]:
    root = state.get_root()
    cleaned = (rel_path or ".").strip().lstrip("/\\")
    target = (root / cleaned).resolve()
    if not target.is_relative_to(root):
        raise ValueError(f"Access denied: '{rel_path}' escapes workspace.")
    return root, target


def _execute_tool(name: str, args: dict, state: ServerState) -> str:
    """Execute a local workspace tool on behalf of the CLI model."""
    try:
        if name == "list_files":
            rel = str(args.get("path", "."))
            root, target = _resolve_safe(state, rel)
            state.record("cli:list_files", rel)
            if not target.is_dir():
                return f"Not a directory: {rel}"
            entries = sorted(target.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
            if not entries:
                return "(empty directory)"
            return "\n".join(
                f"[DIR]  {e.relative_to(root).as_posix()}/"
                if e.is_dir()
                else f"[FILE] {e.relative_to(root).as_posix()} ({e.stat().st_size} bytes)"
                for e in entries
            )

        if name == "read_file":
            rel = str(args["path"])
            _, target = _resolve_safe(state, rel)
            state.record("cli:read_file", rel)
            if not target.is_file():
                return f"File not found: {rel}"
            text = target.read_text(encoding="utf-8", errors="replace")
            start = args.get("start_line")
            end = args.get("end_line")
            if start is None and end is None:
                return text
            lines = text.splitlines()
            s_idx = max(0, int(start or 1) - 1)
            e_idx = len(lines) if end is None else min(len(lines), int(end))
            return "\n".join(f"{i + 1}: {lines[i]}" for i in range(s_idx, e_idx))

        if name == "write_file":
            rel = str(args["path"])
            content = str(args["content"])
            root, target = _resolve_safe(state, rel)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
            rel_out = target.relative_to(root).as_posix()
            state.record("cli:write_file", f"{rel_out} ({len(content)} chars)")
            return f"Saved {rel_out} ({len(content)} chars)."

        if name == "edit_file":
            rel = str(args["path"])
            old_text = str(args["old_text"])
            new_text = str(args["new_text"])
            root, target = _resolve_safe(state, rel)
            if not target.is_file():
                return f"File not found: {rel}"
            content = target.read_text(encoding="utf-8")
            count = content.count(old_text)
            if count == 0:
                return "Error: old_text not found."
            if count > 1:
                return f"Error: old_text matched {count} times."
            target.write_text(content.replace(old_text, new_text, 1), encoding="utf-8")
            rel_out = target.relative_to(root).as_posix()
            state.record("cli:edit_file", rel_out)
            return f"Updated {rel_out}."

        if name == "delete_file":
            rel = str(args["path"])
            root, target = _resolve_safe(state, rel)
            if not target.is_file():
                return f"File not found: {rel}"
            rel_out = target.relative_to(root).as_posix()
            target.unlink()
            state.record("cli:delete_file", rel_out)
            return f"Deleted {rel_out}."

        if name == "search_files":
            query = str(args["query"]).lower()
            rel = str(args.get("path", "."))
            root, base = _resolve_safe(state, rel)
            state.record("cli:search_files", query)
            matches: list[str] = []
            for item in sorted(base.rglob("*")):
                r = item.relative_to(root).as_posix()
                if query in item.name.lower():
                    matches.append(f"[NAME] {r}")
                if item.is_file() and item.stat().st_size <= 1_000_000:
                    try:
                        for ln, line in enumerate(item.read_text(encoding="utf-8").splitlines(), 1):
                            if query in line.lower():
                                matches.append(f"{r}:{ln}: {line.strip()[:160]}")
                                if len(matches) >= 50:
                                    return "\n".join(matches)
                    except UnicodeDecodeError:
                        continue
            return "\n".join(matches) if matches else "No matches found."

        if name == "run_command":
            cmd = str(args["command"])
            if not state.is_exec_enabled():
                return "Error: run_command is disabled. User can enable it with /exec on."
            state.record("cli:run_command", cmd)
            timeout = max(1, min(int(args.get("timeout_seconds", 30)), 120))
            proc = subprocess.run(
                cmd,
                cwd=state.get_root(),
                shell=True,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
            )
            out = [f"Exit code: {proc.returncode}"]
            if proc.stdout.strip():
                out.append(f"STDOUT:\n{proc.stdout.strip()[:8000]}")
            if proc.stderr.strip():
                out.append(f"STDERR:\n{proc.stderr.strip()[:4000]}")
            return "\n\n".join(out)

        return f"Unknown tool: {name}"
    except Exception as exc:
        return f"Tool error: {exc}"


def send_chat_message(
    prompt: str,
    model: str,
    api_key: str,
    history: list[dict],
    state: ServerState,
    attached_images: list[Path] | None = None,
) -> str:
    """Send a user prompt to Gemini API and run the tool-calling loop."""
    parts: list[dict] = [{"text": prompt}]
    for img_path in attached_images or []:
        if img_path.is_file() and img_path.stat().st_size <= 10_000_000:
            mime = "image/png" if img_path.suffix.lower() == ".png" else "image/jpeg"
            b64 = base64.b64encode(img_path.read_bytes()).decode("ascii")
            parts.append({"inlineData": {"mimeType": mime, "data": b64}})

    history.append({"role": "user", "parts": parts})
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"

    for _ in range(12):
        payload = {
            "systemInstruction": {
                "parts": [{
                    "text": (
                        f"You are a helpful coding assistant working inside {state.get_root()}. "
                        "Use the provided file tools to inspect and edit files directly."
                    )
                }]
            },
            "contents": history,
            "tools": [{"functionDeclarations": TOOL_DECLARATIONS}],
        }
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=60.0) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            err_body = exc.read().decode("utf-8", errors="replace")
            history.pop()
            return f"[API Error {exc.code}] {err_body[:400]}"
        except Exception as exc:
            history.pop()
            return f"[Network Error] {exc}"

        candidates = data.get("candidates", [])
        if not candidates:
            return "[!] Empty response from Gemini."

        content = candidates[0].get("content", {})
        model_parts = content.get("parts", [])
        history.append({"role": "model", "parts": model_parts})

        fn_calls = [p["functionCall"] for p in model_parts if "functionCall" in p]
        if not fn_calls:
            texts = [p.get("text", "") for p in model_parts if "text" in p]
            return "\n".join(texts).strip() or "(done)"

        fn_responses = []
        for call in fn_calls:
            fn_name = call["name"]
            fn_args = call.get("args", {})
            print(f"  [~] {fn_name}({json.dumps(fn_args, ensure_ascii=False)[:80]})")
            result_str = _execute_tool(fn_name, fn_args, state)
            fn_responses.append({
                "functionResponse": {
                    "name": fn_name,
                    "response": {"result": result_str},
                }
            })
        history.append({"role": "user", "parts": fn_responses})

    return "[!] Reached max tool steps."
