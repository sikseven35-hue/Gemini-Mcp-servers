"""GeminiMCP CLI - Interactive vibe-coding MCP bridge for Gemini Web.

Credits: Fikus & Hydrogen
"""

from __future__ import annotations

import argparse
import json
import os
import shlex
import shutil
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import webbrowser
import zipfile
from pathlib import Path

from server import DEFAULT_ROOT, ServerState, run_server

VERSION = "0.2.0"
GITHUB_REPO = "sikseven35-hue/Gemini-Mcp-servers"
NGROK_TOKEN_URL = "https://dashboard.ngrok.com/get-started/your-authtoken"
NGROK_DOWNLOAD_URL = "https://bin.equinox.io/c/bNyj1mQVY4c/ngrok-v3-stable-windows-amd64.zip"


def get_app_dir() -> Path:
    """Return directory containing the executable (when frozen) or script."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def get_data_dir() -> Path:
    """Return persistent app data directory in %LOCALAPPDATA%\\GeminiMCP."""
    base = Path(os.environ.get("LOCALAPPDATA", str(get_app_dir())))
    data_dir = base / "GeminiMCP"
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir


def load_sessions() -> dict[str, dict]:
    """Load saved sessions from sessions.json."""
    sessions_file = get_data_dir() / "sessions.json"
    if not sessions_file.is_file():
        return {}
    try:
        data = json.loads(sessions_file.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def save_sessions(sessions: dict[str, dict]) -> None:
    """Persist sessions to sessions.json."""
    sessions_file = get_data_dir() / "sessions.json"
    sessions_file.write_text(json.dumps(sessions, indent=2, ensure_ascii=False), encoding="utf-8")


def print_banner() -> None:
    """Print CLI header and credits."""
    print("=" * 66)
    print(f"  GeminiMCP CLI v{VERSION}  |  Local PC Files Bridge for Gemini Web")
    print("  Credits: Fikus & Hydrogen")
    print("=" * 66)


def print_help() -> None:
    """Print interactive slash commands."""
    print(
        """
Available commands:
  /web                 Switch to Web Vibe-Coding mode (opens gemini.google.com + live logs)
  /attach <path>       Attach file/photo/video into _attachments/ (or just drag & drop!)
  /folder <path>       Switch active workspace folder live (keeps same MCP URL)
  /session <name>      Switch to or create a named session (saves folder + exec)
  /sessions            List all saved sessions
  /session del <name>  Delete a saved session
  /exec on | off       Enable or disable run_command tool live
  /url                 Show & copy the active MCP Server URL to clipboard
  /status              Show current session, folder, tools, and tunnel status
  /ls [subpath]        List files in the active workspace
  /logs [count]        Show recent MCP tool calls from Gemini (default: 15)
  /clear               Clear screen and reprint status
  /update              Check GitHub Releases for a new version
  /help                Show this help
  /exit                Stop tunnel and exit

Tip: Drag & drop any file, photo, or video into this window and press Enter!
"""
    )


def find_or_download_ngrok() -> Path | None:
    """Locate ngrok.exe or download it to %LOCALAPPDATA%\\GeminiMCP."""
    app_dir = get_app_dir()
    cache_dir = get_data_dir()
    for candidate in (app_dir / "ngrok.exe", cache_dir / "ngrok.exe"):
        if candidate.is_file():
            return candidate

    found = shutil.which("ngrok")
    if found:
        return Path(found)

    print("[*] ngrok.exe not found. Downloading ngrok for Windows...")
    try:
        zip_path = cache_dir / "ngrok.zip"
        urllib.request.urlretrieve(NGROK_DOWNLOAD_URL, zip_path)
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(cache_dir)
        zip_path.unlink(missing_ok=True)
        ngrok_exe = cache_dir / "ngrok.exe"
        if ngrok_exe.is_file():
            print(f"[+] ngrok downloaded to {ngrok_exe}")
            return ngrok_exe
    except Exception as exc:
        print(f"[!] Failed to download ngrok: {exc}")
    return None


def _parse_version(tag: str) -> tuple[int, ...]:
    cleaned = tag.strip().lstrip("vV")
    parts = []
    for part in cleaned.split("."):
        digits = "".join(ch for ch in part if ch.isdigit())
        parts.append(int(digits) if digits else 0)
    return tuple(parts)


def check_for_updates(interactive: bool = False) -> bool:
    """Check GitHub Releases for a newer version and self-update the .exe if available."""
    api_url = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
    try:
        req = urllib.request.Request(api_url, headers={"User-Agent": f"GeminiMCP-CLI/{VERSION}"})
        with urllib.request.urlopen(req, timeout=3.0) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:
        if interactive:
            print(f"[!] Update check failed: {exc}")
        return False

    latest_tag = data.get("tag_name", "")
    if not latest_tag or _parse_version(latest_tag) <= _parse_version(VERSION):
        if interactive:
            print(f"[+] You are on the latest version (v{VERSION}).")
        return False

    exe_asset_url = None
    for asset in data.get("assets", []):
        if asset.get("name", "").lower() == "gemini-mcp.exe":
            exe_asset_url = asset.get("browser_download_url")
            break

    print(f"\n[*] New version available: {latest_tag} (current: v{VERSION})")
    if not getattr(sys, "frozen", False) or not exe_asset_url:
        print(f"    Download at: {data.get('html_url', f'https://github.com/{GITHUB_REPO}/releases')}")
        return False

    choice = input("    Download and install update now? [Y/n]: ").strip().lower()
    if choice in ("n", "no"):
        return False

    current_exe = Path(sys.executable).resolve()
    new_exe = current_exe.with_name("gemini-mcp.exe.new")
    print(f"[*] Downloading {latest_tag}...")
    try:
        urllib.request.urlretrieve(exe_asset_url, new_exe)
    except Exception as exc:
        print(f"[!] Download failed: {exc}")
        new_exe.unlink(missing_ok=True)
        return False

    updater_bat = get_data_dir() / "apply_update.bat"
    pid = os.getpid()
    updater_bat.write_text(
        f'@echo off\r\n'
        f':wait\r\n'
        f'tasklist /FI "PID eq {pid}" 2>NUL | find /I "{pid}" >NUL\r\n'
        f'if not errorlevel 1 (\r\n'
        f'  timeout /t 1 /nobreak >NUL\r\n'
        f'  goto wait\r\n'
        f')\r\n'
        f'move /y "{new_exe}" "{current_exe}" >NUL\r\n'
        f'start "" "{current_exe}"\r\n'
        f'del "%~f0"\r\n',
        encoding="utf-8",
    )
    print("[+] Update downloaded! Restarting GeminiMCP CLI...")
    subprocess.Popen(
        ["cmd", "/c", str(updater_bat)],
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    return True


def has_ngrok_token() -> bool:
    """Return True if an ngrok authtoken is already saved in ngrok.yml."""
    local_app_data = Path(os.environ.get("LOCALAPPDATA", ""))
    cfg_candidates = [
        local_app_data / "ngrok" / "ngrok.yml",
        Path.home() / ".config" / "ngrok" / "ngrok.yml",
        Path.home() / ".ngrok2" / "ngrok.yml",
    ]
    return any(
        p.is_file() and "authtoken:" in p.read_text(encoding="utf-8", errors="ignore")
        for p in cfg_candidates
    )


def ensure_ngrok_token(ngrok_bin: Path, cli_token: str | None) -> bool:
    """Ensure ngrok has a valid authtoken, guiding the user automatically if missing."""
    if cli_token:
        token = cli_token.strip()
        res = subprocess.run(
            [str(ngrok_bin), "config", "add-authtoken", token],
            capture_output=True,
            text=True,
        )
        if res.returncode == 0 and "_" in token:
            print("[+] ngrok authtoken saved.")
            return True
        print(f"[!] Invalid ngrok authtoken: {(res.stderr or res.stdout).strip()}")
        return False

    if has_ngrok_token():
        return True

    print("\n" + "=" * 66)
    print("  FIRST-TIME SETUP: ngrok Authtoken")
    print("  1. Opening ngrok dashboard in your browser...")
    print(f"     {NGROK_TOKEN_URL}")
    print("  2. Sign in (Google 1-click) and copy 'Your Authtoken'.")
    print("  3. Paste it below and press Enter.")
    print("=" * 66)
    try:
        webbrowser.open(NGROK_TOKEN_URL)
    except Exception:
        pass

    while True:
        token = input("\nPaste your ngrok authtoken (or Enter to cancel): ").strip()
        if not token:
            return False
        if ensure_ngrok_token(ngrok_bin, token):
            return True
        print("[!] Please copy the full Authtoken (looks like 2x..._... ) and try again.")


def wait_for_local_port(host: str, port: int, timeout_sec: float = 10.0) -> bool:
    """Wait until local TCP port starts accepting connections."""
    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline:
        try:
            with socket.create_connection((host, port), timeout=0.5):
                return True
        except OSError:
            time.sleep(0.2)
    return False


def wait_for_ngrok_url(timeout_sec: float = 15.0) -> str | None:
    """Poll ngrok's local API for the public HTTPS tunnel URL."""
    deadline = time.monotonic() + timeout_sec
    api_url = "http://127.0.0.1:4040/api/tunnels"
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(api_url, timeout=1.5) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                for tunnel in data.get("tunnels", []):
                    public_url = tunnel.get("public_url", "")
                    if public_url.startswith("https://"):
                        return public_url
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
            pass
        time.sleep(0.5)
    return None


def copy_to_clipboard(text: str) -> bool:
    """Copy text to Windows clipboard using clip.exe."""
    try:
        subprocess.run(["clip"], input=text, text=True, check=True)
        return True
    except Exception:
        return False


def resolve_initial_state(args: argparse.Namespace, sessions: dict[str, dict]) -> ServerState:
    """Determine initial session, folder, and exec setting."""
    session_name = args.session or "default"
    saved = sessions.get(session_name, {})

    raw_path = args.root_flag or args.path or saved.get("root")
    if raw_path:
        root_dir = Path(raw_path).expanduser().resolve()
    else:
        fallback = DEFAULT_ROOT if DEFAULT_ROOT.exists() else Path.cwd()
        entered = input(f"Folder to share with Gemini [{fallback}]: ").strip().strip('"')
        root_dir = Path(entered).expanduser().resolve() if entered else fallback.resolve()

    root_dir.mkdir(parents=True, exist_ok=True)
    allow_exec = args.allow_exec or bool(saved.get("allow_exec", False))

    sessions[session_name] = {"root": str(root_dir), "allow_exec": allow_exec}
    save_sessions(sessions)
    return ServerState(root_dir=root_dir, allow_exec=allow_exec, session_name=session_name)


def print_status(state: ServerState, mcp_url: str) -> None:
    """Print current active session, folder, and URL."""
    print("\n" + "-" * 66)
    print(f"  Session        : {state.session_name}")
    print(f"  Workspace      : {state.get_root()}")
    print(f"  run_command    : {'ON' if state.is_exec_enabled() else 'OFF (/exec on to enable)'}")
    print(f"  MCP Server URL : {mcp_url}")
    print("-" * 66)


def attach_file(raw_path: str, state: ServerState) -> None:
    """Copy a dragged-and-dropped file, photo, or video into workspace/_attachments/."""
    cleaned = raw_path.strip().strip('"').strip("'")
    if cleaned.startswith("& "):
        cleaned = cleaned[2:].strip().strip('"').strip("'")
    src = Path(cleaned).expanduser()
    if not src.is_file():
        print(f"[!] File not found: {cleaned}")
        return

    dest_dir = state.get_root() / "_attachments"
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / src.name
    counter = 1
    while dest.exists():
        dest = dest_dir / f"{src.stem}_{counter}{src.suffix}"
        counter += 1

    shutil.copy2(src, dest)
    rel = dest.relative_to(state.get_root()).as_posix()
    ext = src.suffix.lower()
    if ext in {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"}:
        kind = "image (Gemini can inspect with read_image)"
    elif ext in {".mp4", ".mov", ".mkv", ".webm", ".avi"}:
        kind = "video"
    else:
        kind = "file"

    copy_to_clipboard(rel)
    state.record("attach", f"{rel} ({src.stat().st_size} bytes)")
    print(f"[+] Attached {kind}: {rel} ({src.stat().st_size:,} bytes)")
    print("    Relative path copied to clipboard! Mention it in your Gemini prompt.")


def enter_web_mode(state: ServerState, mcp_url: str) -> None:
    """Open Gemini Web and stream live MCP tool logs until Enter is pressed."""
    copy_to_clipboard(mcp_url)
    print("\n" + "=" * 66)
    print("  WEB VIBE-CODING MODE  |  Opening https://gemini.google.com/")
    print(f"  MCP URL copied: {mcp_url}")
    print("  Live tool calls from Gemini will appear below.")
    print("  Press [Enter] anytime to return to CLI command prompt...")
    print("=" * 66)
    try:
        webbrowser.open("https://gemini.google.com/")
    except Exception:
        pass

    state.on_log = lambda entry: print(f"  {entry}", flush=True)
    try:
        input()
    except EOFError:
        pass
    finally:
        state.on_log = None
    print("[*] Returned to CLI mode.\n")


def handle_command(
    raw: str,
    state: ServerState,
    sessions: dict[str, dict],
    mcp_url: str,
) -> bool:
    """Handle an interactive slash command or drag-and-drop path. Returns False to exit."""
    line = raw.strip()
    if not line:
        return True
    if not line.startswith("/"):
        candidate = line.strip('"').strip("'")
        if candidate.startswith("& "):
            candidate = candidate[2:].strip().strip('"').strip("'")
        if Path(candidate).is_file():
            attach_file(candidate, state)
        else:
            print("Type /help to see commands, or drag & drop a file/photo/video here.")
        return True

    try:
        parts = shlex.split(line, posix=False)
    except ValueError:
        parts = line.split()
    cmd = parts[0].lower()
    arg_str = line[len(parts[0]):].strip().strip('"')

    if cmd in ("/exit", "/quit", "/q"):
        return False

    if cmd == "/help":
        print_help()
        return True

    if cmd == "/update":
        if check_for_updates(interactive=True):
            return False
        return True

    if cmd == "/web":
        enter_web_mode(state, mcp_url)
        return True

    if cmd == "/attach":
        if not arg_str:
            print("Usage: /attach <file_path>  (or just drag & drop a file into this window)")
            return True
        attach_file(arg_str, state)
        return True

    if cmd == "/clear":
        os.system("cls" if os.name == "nt" else "clear")
        print_banner()
        print_status(state, mcp_url)
        return True

    if cmd == "/status":
        print_status(state, mcp_url)
        return True

    if cmd == "/url":
        copied = copy_to_clipboard(mcp_url)
        print(f"[+] MCP Server URL: {mcp_url}" + (" (copied to clipboard!)" if copied else ""))
        return True

    if cmd == "/folder":
        if not arg_str:
            print(f"[*] Current folder: {state.get_root()}")
            print("    Usage: /folder C:\\path\\to\\project")
            return True
        new_root = state.set_root(Path(arg_str))
        sessions[state.session_name] = {"root": str(new_root), "allow_exec": state.is_exec_enabled()}
        save_sessions(sessions)
        print(f"[+] Switched workspace -> {new_root} (MCP URL unchanged)")
        return True

    if cmd == "/sessions":
        if not sessions:
            print("[*] No saved sessions yet.")
            return True
        print("\nSaved sessions:")
        for name, info in sorted(sessions.items()):
            marker = "*" if name == state.session_name else " "
            exec_tag = " [exec]" if info.get("allow_exec") else ""
            print(f"  {marker} {name:<14} -> {info.get('root')}{exec_tag}")
        print()
        return True

    if cmd == "/session":
        if len(parts) < 2:
            print(f"[*] Active session: {state.session_name}")
            print("    Usage: /session <name>  |  /sessions  |  /session del <name>")
            return True
        if parts[1].lower() in ("del", "delete", "rm") and len(parts) >= 3:
            target = parts[2]
            if target == state.session_name:
                print("[!] Cannot delete the currently active session.")
            elif target in sessions:
                del sessions[target]
                save_sessions(sessions)
                print(f"[+] Deleted session '{target}'.")
            else:
                print(f"[!] Session '{target}' not found.")
            return True

        target_name = parts[1]
        if target_name in sessions:
            info = sessions[target_name]
            state.session_name = target_name
            state.set_root(Path(info["root"]))
            state.set_exec(bool(info.get("allow_exec", False)))
            print(f"[+] Switched to session '{target_name}' -> {state.get_root()}")
        else:
            folder_input = input(f"Folder for new session '{target_name}' [{state.get_root()}]: ").strip().strip('"')
            chosen = Path(folder_input) if folder_input else state.get_root()
            state.session_name = target_name
            resolved = state.set_root(chosen)
            sessions[target_name] = {"root": str(resolved), "allow_exec": state.is_exec_enabled()}
            save_sessions(sessions)
            print(f"[+] Created & switched to session '{target_name}' -> {resolved}")
        return True

    if cmd == "/exec":
        mode = parts[1].lower() if len(parts) >= 2 else ""
        if mode in ("on", "1", "true"):
            state.set_exec(True)
        elif mode in ("off", "0", "false"):
            state.set_exec(False)
        else:
            state.set_exec(not state.is_exec_enabled())
        sessions[state.session_name] = {
            "root": str(state.get_root()),
            "allow_exec": state.is_exec_enabled(),
        }
        save_sessions(sessions)
        print(f"[+] run_command is now {'ON' if state.is_exec_enabled() else 'OFF'}.")
        return True

    if cmd == "/ls":
        sub = arg_str or "."
        root = state.get_root()
        target = (root / sub.lstrip("/\\")).resolve()
        if not target.is_relative_to(root) or not target.exists():
            print(f"[!] Invalid path: {sub}")
            return True
        for entry in sorted(target.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower())):
            tag = "[DIR] " if entry.is_dir() else "[FILE]"
            print(f"  {tag} {entry.relative_to(root).as_posix()}")
        return True

    if cmd == "/logs":
        count = int(parts[1]) if len(parts) >= 2 and parts[1].isdigit() else 15
        logs = state.recent_logs(count)
        if not logs:
            print("[*] No MCP tool calls recorded yet.")
        else:
            print("\nRecent MCP activity:")
            for item in logs:
                print(f"  {item}")
            print()
        return True

    print(f"[!] Unknown command: {cmd}. Type /help for commands.")
    return True


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="gemini-mcp",
        description="Interactive local MCP bridge for Gemini Web (by Fikus & Hydrogen).",
    )
    parser.add_argument("path", nargs="?", help="Folder path to expose to Gemini")
    parser.add_argument("--root", dest="root_flag", help="Folder path (alternative to positional path)")
    parser.add_argument("--session", help="Named session to load or create (default: default)")
    parser.add_argument("--port", type=int, default=8000, help="Local MCP server port (default: 8000)")
    parser.add_argument("--token", help="ngrok authtoken (saved for future runs)")
    parser.add_argument(
        "--allow-exec",
        action="store_true",
        help="Enable run_command tool inside the shared folder",
    )
    parser.add_argument(
        "--no-tunnel",
        action="store_true",
        help="Run local MCP server only without starting ngrok",
    )
    parser.add_argument(
        "--no-update-check",
        action="store_true",
        help="Skip checking GitHub for updates on startup",
    )
    return parser.parse_args()


def main() -> int:
    print_banner()
    args = parse_args()

    if not args.no_update_check:
        if check_for_updates(interactive=False):
            return 0

    ngrok_bin: Path | None = None
    if not args.no_tunnel:
        ngrok_bin = find_or_download_ngrok()
        if not ngrok_bin:
            print("[!] ngrok.exe unavailable.")
            return 1
        if not ensure_ngrok_token(ngrok_bin, args.token):
            print("[!] Cancelled: ngrok authtoken is required for public HTTPS URL.")
            return 1

    sessions = load_sessions()
    state = resolve_initial_state(args, sessions)

    print(f"\n[+] Starting MCP server on http://127.0.0.1:{args.port}/mcp ...")
    server_error: list[BaseException] = []

    def _serve() -> None:
        try:
            run_server(state=state, host="127.0.0.1", port=args.port, log_level="WARNING")
        except BaseException as exc:
            server_error.append(exc)

    thread = threading.Thread(target=_serve, daemon=True)
    thread.start()

    if not wait_for_local_port("127.0.0.1", args.port):
        detail = f" ({server_error[0]})" if server_error else ""
        print(f"[!] MCP server failed to start on port {args.port}{detail}.")
        return 1

    ngrok_proc: subprocess.Popen[bytes] | None = None
    try:
        if args.no_tunnel:
            mcp_url = f"http://127.0.0.1:{args.port}/mcp"
        else:
            assert ngrok_bin is not None
            print("[+] Starting ngrok HTTPS tunnel...")
            ngrok_proc = subprocess.Popen(
                [str(ngrok_bin), "http", str(args.port), "--log", "stdout"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.STDOUT,
            )
            public_base = wait_for_ngrok_url()
            if not public_base:
                print("[!] Could not obtain ngrok public URL within 15 seconds.")
                return 1
            mcp_url = f"{public_base}/mcp"
            if copy_to_clipboard(mcp_url):
                print("[+] MCP URL copied to clipboard!")

        print_status(state, mcp_url)
        print("Type /help for vibe-coding commands (/folder, /session, /exec, /logs, /exit).")

        while thread.is_alive() and (ngrok_proc is None or ngrok_proc.poll() is None):
            try:
                raw = input(f"gemini-mcp [{state.session_name}]> ")
            except EOFError:
                break
            if not handle_command(raw, state, sessions, mcp_url):
                break
        return 0

    except KeyboardInterrupt:
        print("\n[*] Stopping GeminiMCP CLI...")
        return 0
    finally:
        if ngrok_proc and ngrok_proc.poll() is None:
            ngrok_proc.terminate()
            try:
                ngrok_proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                ngrok_proc.kill()


if __name__ == "__main__":
    raise SystemExit(main())
