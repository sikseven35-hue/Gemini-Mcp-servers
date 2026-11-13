"""GeminiMCP - Minimal one-click local PC files MCP bridge for Gemini Web.

Credits: Fikus & Hydrogen
"""

from __future__ import annotations

import argparse
import json
import os
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

VERSION = "0.5.0"
GITHUB_REPO = "sikseven35-hue/Gemini-Mcp-servers"
NGROK_TOKEN_URL = "https://dashboard.ngrok.com/get-started/your-authtoken"
NGROK_DOWNLOAD_URL = "https://bin.equinox.io/c/bNyj1mQVY4c/ngrok-v3-stable-windows-amd64.zip"
GEMINI_WEB_URL = "https://gemini.google.com/"


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


def print_banner() -> None:
    """Print header and credits."""
    print("=" * 64)
    print(f"  GeminiMCP v{VERSION}  |  Local PC Files Bridge for Gemini Web")
    print("  Credits: Fikus & Hydrogen")
    print("=" * 64)


def _parse_version(tag: str) -> tuple[int, ...]:
    cleaned = tag.strip().lstrip("vV")
    parts = []
    for part in cleaned.split("."):
        digits = "".join(ch for ch in part if ch.isdigit())
        parts.append(int(digits) if digits else 0)
    return tuple(parts)


def check_for_updates() -> bool:
    """Check GitHub Releases for a newer version and self-update the .exe if available."""
    api_url = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
    try:
        req = urllib.request.Request(api_url, headers={"User-Agent": f"GeminiMCP/{VERSION}"})
        with urllib.request.urlopen(req, timeout=3.0) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception:
        return False

    latest_tag = data.get("tag_name", "")
    if not latest_tag or _parse_version(latest_tag) <= _parse_version(VERSION):
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
    print("[+] Update downloaded! Restarting...")
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

    print("\n" + "=" * 64)
    print("  AUTO-SETUP: ngrok Authtoken")
    print("  1. Opening ngrok dashboard in your browser...")
    print(f"     {NGROK_TOKEN_URL}")
    print("  2. Sign in (Google 1-click) and copy 'Your Authtoken'.")
    print("  3. Paste it below and press Enter.")
    print("=" * 64)
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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="gemini-mcp",
        description="One-click local PC files MCP bridge for Gemini Web (by Fikus & Hydrogen).",
    )
    parser.add_argument("path", nargs="?", help="Folder path to expose to Gemini")
    parser.add_argument("--root", dest="root_flag", help="Folder path (alternative to positional path)")
    parser.add_argument("--port", type=int, default=8000, help="Local MCP server port (default: 8000)")
    parser.add_argument("--token", help="ngrok authtoken (saved for future runs)")
    parser.add_argument("--allow-exec", action="store_true", help="Enable run_command tool")
    parser.add_argument("--no-tunnel", action="store_true", help="Run local MCP server only")
    parser.add_argument("--no-open", action="store_true", help="Do not auto-open gemini.google.com on startup")
    parser.add_argument("--no-update-check", action="store_true", help="Skip GitHub update check")
    return parser.parse_args()


def main() -> int:
    print_banner()
    args = parse_args()

    if not args.no_update_check:
        if check_for_updates():
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

    raw_path = args.root_flag or args.path
    if raw_path:
        root_dir = Path(raw_path).expanduser().resolve()
    else:
        root_dir = (DEFAULT_ROOT if DEFAULT_ROOT.parent.exists() else Path.cwd()).resolve()
    root_dir.mkdir(parents=True, exist_ok=True)

    state = ServerState(
        root_dir=root_dir,
        allow_exec=args.allow_exec,
        on_log=lambda entry: print(f"  {entry}", flush=True),
    )

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

        print("\n" + "-" * 64)
        print(f"  Workspace      : {state.get_root()}")
        print(f"  MCP Server URL : {mcp_url}")
        print("-" * 64)

        if not args.no_open:
            print(f"[+] Opening {GEMINI_WEB_URL} ...")
            try:
                webbrowser.open(GEMINI_WEB_URL)
            except Exception:
                pass

        print("\nPaste the URL into Gemini -> Settings -> Connected Apps -> + (Next -> Connect).")
        print("Live MCP activity (press Ctrl+C or close window to stop):\n")

        while thread.is_alive() and (ngrok_proc is None or ngrok_proc.poll() is None):
            time.sleep(1.0)
        return 0

    except KeyboardInterrupt:
        print("\n[*] Stopping GeminiMCP...")
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
