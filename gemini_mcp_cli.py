"""GeminiMCP CLI - Interactive vibe-coding MCP bridge & CLI agent for Gemini.

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

from gemini_chat import DEFAULT_MODELS, fetch_available_models, send_chat_message
from server import DEFAULT_ROOT, ServerState, run_server

VERSION = "0.3.1"
GITHUB_REPO = "sikseven35-hue/Gemini-Mcp-servers"
NGROK_TOKEN_URL = "https://dashboard.ngrok.com/get-started/your-authtoken"
AI_STUDIO_KEY_URL = "https://aistudio.google.com/apikey"
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


def load_json_file(filename: str) -> dict:
    path = get_data_dir() / filename
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def save_json_file(filename: str, data: dict) -> None:
    path = get_data_dir() / filename
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def print_banner() -> None:
    """Print CLI header and credits."""
    print("=" * 66)
    print(f"  GeminiMCP CLI v{VERSION}  |  Vibe-Coding CLI & Gemini Web Bridge")
    print("  Credits: Fikus & Hydrogen")
    print("=" * 66)


def print_help() -> None:
    """Print interactive slash commands."""
    print(
        """
Available commands:
  /model [name]        Choose Gemini model to vibe-code with directly in CLI
  /apikey [key]        Set or update Google AI Studio API key (for /model chat)
  /web                 Switch to Web mode (opens gemini.google.com + live logs)
  /attach <path>       Attach file/photo/video (or just drag & drop into window!)
  /folder <path>       Switch active workspace folder live (keeps same MCP URL)
  /session <name>      Switch to or create a named session (saves folder + exec)
  /sessions            List all saved sessions
  /session del <name>  Delete a saved session
  /exec on | off       Enable or disable run_command tool live
  /new                 Reset CLI chat conversation history
  /url                 Show & copy the active MCP Server URL to clipboard
  /status              Show current session, model, folder, and tunnel status
  /ls [subpath]        List files in the active workspace
  /logs [count]        Show recent MCP tool calls (default: 15)
  /clear               Clear screen and reprint status
  /update              Check GitHub Releases for a new version
  /help                Show this help
  /exit                Stop tunnel and exit

Tip: Type any message to chat with the selected /model, or drag & drop a file!
"""
    )


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
    updater_bat.write_text(
        f'@echo off\r\n'
        f'setlocal\r\n'
        f'set "NEW={new_exe}"\r\n'
        f'set "CUR={current_exe}"\r\n'
        f'set /a tries=0\r\n'
        f':retry\r\n'
        f'timeout /t 1 /nobreak >NUL\r\n'
        f'move /y "%NEW%" "%CUR%" >NUL 2>&1\r\n'
        f'if exist "%NEW%" (\r\n'
        f'  set /a tries+=1\r\n'
        f'  if %tries% LSS 20 goto retry\r\n'
        f')\r\n'
        f'start "" /D "{current_exe.parent}" "{current_exe}"\r\n'
        f'del "%~f0"\r\n',
        encoding="utf-8",
    )
    print("[+] Update downloaded! Restarting GeminiMCP CLI...")
    detached = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    subprocess.Popen(
        ["cmd", "/c", str(updater_bat)],
        creationflags=detached,
        close_fds=True,
    )
    return True


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

    print("[*] Downloading ngrok for Windows...")
    try:
        zip_path = cache_dir / "ngrok.zip"
        urllib.request.urlretrieve(NGROK_DOWNLOAD_URL, zip_path)
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(cache_dir)
        zip_path.unlink(missing_ok=True)
        ngrok_exe = cache_dir / "ngrok.exe"
        if ngrok_exe.is_file():
            print(f"[+] ngrok ready: {ngrok_exe}")
            return ngrok_exe
    except Exception as exc:
        print(f"[!] Failed to download ngrok: {exc}")
    return None


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
    print("  AUTO-SETUP: ngrok Authtoken")
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
        print("[!] Please copy the full Authtoken (looks like 2x..._...) and try again.")


def ensure_gemini_api_key(config: dict) -> str | None:
    """Ensure a Google AI Studio API key is saved in config.json for /model CLI chat."""
    if config.get("gemini_api_key"):
        return str(config["gemini_api_key"])

    print("\n" + "=" * 66)
    print("  CLI MODEL SETUP: Google AI Studio API Key")
    print("  1. Opening https://aistudio.google.com/apikey in your browser...")
    print("  2. Click 'Create API key' (free) and copy it.")
    print("  3. Paste it below and press Enter.")
    print("=" * 66)
    try:
        webbrowser.open(AI_STUDIO_KEY_URL)
    except Exception:
        pass

    key = input("\nPaste your Gemini API key (or Enter to cancel): ").strip()
    if not key:
        return None
    config["gemini_api_key"] = key
    save_json_file("config.json", config)
    print("[+] Gemini API key saved.")
    return key


def wait_for_local_port(host: str, port: int, timeout_sec: float = 10.0) -> bool:
    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline:
        try:
            with socket.create_connection((host, port), timeout=0.5):
                return True
        except OSError:
            time.sleep(0.2)
    return False


def wait_for_ngrok_url(timeout_sec: float = 15.0) -> str | None:
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
    try:
        subprocess.run(["clip"], input=text, text=True, check=True)
        return True
    except Exception:
        return False


def resolve_initial_state(args: argparse.Namespace, sessions: dict[str, dict]) -> ServerState:
    """Resolve initial session and folder immediately without blocking on prompts."""
    session_name = args.session or "default"
    saved = sessions.get(session_name, {})

    raw_path = args.root_flag or args.path or saved.get("root")
    if raw_path and not str(raw_path).startswith("/"):
        root_dir = Path(raw_path).expanduser().resolve()
    else:
        root_dir = (DEFAULT_ROOT if DEFAULT_ROOT.parent.exists() else Path.cwd()).resolve()

    root_dir.mkdir(parents=True, exist_ok=True)
    allow_exec = args.allow_exec or bool(saved.get("allow_exec", False))

    sessions[session_name] = {"root": str(root_dir), "allow_exec": allow_exec}
    save_json_file("sessions.json", sessions)
    return ServerState(root_dir=root_dir, allow_exec=allow_exec, session_name=session_name)


def print_status(state: ServerState, mcp_url: str, config: dict) -> None:
    model = config.get("model", DEFAULT_MODELS[1])
    print("\n" + "-" * 66)
    print(f"  Session        : {state.session_name}")
    print(f"  Workspace      : {state.get_root()}")
    print(f"  CLI Model      : {model} (/model to change)")
    print(f"  run_command    : {'ON' if state.is_exec_enabled() else 'OFF (/exec on to enable)'}")
    print(f"  MCP Server URL : {mcp_url}")
    print("-" * 66)


def attach_file(raw_path: str, state: ServerState, pending_images: list[Path]) -> None:
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
        kind = "image (attached for CLI & Gemini read_image)"
        pending_images.append(dest)
    elif ext in {".mp4", ".mov", ".mkv", ".webm", ".avi"}:
        kind = "video"
    else:
        kind = "file"

    copy_to_clipboard(rel)
    state.record("attach", f"{rel} ({src.stat().st_size} bytes)")
    print(f"[+] Attached {kind}: {rel} ({src.stat().st_size:,} bytes)")
    print("    Relative path copied to clipboard!")


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


def select_model(arg_str: str, config: dict) -> None:
    """Interactive /model selector."""
    if arg_str:
        config["model"] = arg_str
        save_json_file("config.json", config)
        print(f"[+] Active CLI model set to: {arg_str}")
        return

    api_key = str(config.get("gemini_api_key", ""))
    models = fetch_available_models(api_key)
    current = config.get("model", DEFAULT_MODELS[1])

    print("\nAvailable Gemini models:")
    for idx, name in enumerate(models, start=1):
        marker = "*" if name == current else " "
        print(f"  {marker} {idx:>2}. {name}")
    print()

    choice = input("Select model number or name (Enter to keep current): ").strip()
    if not choice:
        return
    if choice.isdigit() and 1 <= int(choice) <= len(models):
        chosen = models[int(choice) - 1]
    else:
        chosen = choice

    config["model"] = chosen
    save_json_file("config.json", config)
    print(f"[+] Active CLI model set to: {chosen}")
    if not api_key:
        ensure_gemini_api_key(config)


def handle_input(
    raw: str,
    state: ServerState,
    sessions: dict[str, dict],
    config: dict,
    history: list[dict],
    pending_images: list[Path],
    mcp_url: str,
) -> bool:
    """Handle slash commands, drag-and-drop paths, or direct CLI chat prompts."""
    line = raw.strip()
    if not line:
        return True

    if not line.startswith("/"):
        candidate = line.strip('"').strip("'")
        if candidate.startswith("& "):
            candidate = candidate[2:].strip().strip('"').strip("'")
        if Path(candidate).is_file():
            attach_file(candidate, state, pending_images)
            return True

        api_key = ensure_gemini_api_key(config)
        if not api_key:
            print("[*] Tip: Use /web to vibe-code on gemini.google.com, or /apikey to chat here.")
            return True

        model = config.get("model", DEFAULT_MODELS[1])
        imgs = list(pending_images)
        pending_images.clear()
        reply = send_chat_message(line, model, api_key, history, state, attached_images=imgs)
        print(f"\n[{model}]\n{reply}\n")
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

    if cmd == "/model":
        select_model(arg_str, config)
        return True

    if cmd == "/apikey":
        if arg_str:
            config["gemini_api_key"] = arg_str
            save_json_file("config.json", config)
            print("[+] Gemini API key saved.")
        else:
            config.pop("gemini_api_key", None)
            ensure_gemini_api_key(config)
        return True

    if cmd == "/new":
        history.clear()
        pending_images.clear()
        print("[+] CLI chat history cleared.")
        return True

    if cmd == "/web":
        enter_web_mode(state, mcp_url)
        return True

    if cmd == "/attach":
        if not arg_str:
            print("Usage: /attach <file_path>  (or drag & drop a file into this window)")
            return True
        attach_file(arg_str, state, pending_images)
        return True

    if cmd == "/clear":
        os.system("cls" if os.name == "nt" else "clear")
        print_banner()
        print_status(state, mcp_url, config)
        return True

    if cmd == "/status":
        print_status(state, mcp_url, config)
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
        save_json_file("sessions.json", sessions)
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
                save_json_file("sessions.json", sessions)
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
            save_json_file("sessions.json", sessions)
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
        save_json_file("sessions.json", sessions)
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
        description="Interactive vibe-coding CLI & Gemini Web MCP bridge (by Fikus & Hydrogen).",
    )
    parser.add_argument("path", nargs="?", help="Folder path to expose to Gemini")
    parser.add_argument("--root", dest="root_flag", help="Folder path (alternative to positional path)")
    parser.add_argument("--session", help="Named session to load or create (default: default)")
    parser.add_argument("--port", type=int, default=8000, help="Local MCP server port (default: 8000)")
    parser.add_argument("--token", help="ngrok authtoken (saved for future runs)")
    parser.add_argument("--allow-exec", action="store_true", help="Enable run_command tool")
    parser.add_argument("--no-tunnel", action="store_true", help="Run local MCP server only")
    parser.add_argument("--no-update-check", action="store_true", help="Skip GitHub update check")
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

    sessions = load_json_file("sessions.json")
    config = load_json_file("config.json")
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

        print_status(state, mcp_url, config)
        print("Ready! Paste URL into Gemini Connected Apps (+), type /web, or /model to chat here.")
        print("Type /help for all commands.\n")

        history: list[dict] = []
        pending_images: list[Path] = []
        while thread.is_alive() and (ngrok_proc is None or ngrok_proc.poll() is None):
            try:
                model_tag = config.get("model", DEFAULT_MODELS[1])
                raw = input(f"gemini-mcp [{state.session_name} | {model_tag}]> ")
            except EOFError:
                break
            if not handle_input(raw, state, sessions, config, history, pending_images, mcp_url):
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
