# GeminiMCP CLI (`v0.2.0`)

**Credits:** Fikus & Hydrogen

An interactive CLI bridge that connects any local folder on your PC to **Gemini Web (`gemini.google.com`)** via **MCP (Model Context Protocol)** and **ngrok**.  
Allows Gemini web models (such as Hydrogen, Argon, etc.) to list, read, search, create, edit files, inspect images, and optionally run shell commands directly inside your project.

---

## Features
- **Single `.exe` binary** — runs on Windows without needing Python installed.
- **Auto-configured `ngrok` setup wizard** — on first launch, automatically downloads `ngrok.exe`, opens your browser to the ngrok token page, and saves your token.
- **Built-in Auto-Update (`/update`)** — checks GitHub Releases on startup and updates `gemini-mcp.exe` automatically.
- **Live workspace switching (`/folder`)** — switch folders on the fly **without reconnecting the MCP URL in Gemini**.
- **Named sessions (`/session`, `/sessions`)** — save multiple projects (folder + `/exec` permission) and switch between them with one command.
- **Web Vibe-Coding Mode (`/web`)** — opens `gemini.google.com`, copies the MCP URL, and streams live tool-call logs to your terminal.
- **Drag & Drop attachments (`/attach`)** — drag and drop any file, photo, or video into the CLI window to copy it into `_attachments/` (with `read_image` support for images).
- **On-demand terminal (`/exec on` / `off`)** — toggle `run_command` anytime during a session.

---

## Quick Start (Prebuilt `.exe`)

1. Download **`gemini-mcp.exe`** from [Releases](../../releases/latest).
2. Get a free `ngrok` authtoken at [dashboard.ngrok.com/get-started/your-authtoken](https://dashboard.ngrok.com/get-started/your-authtoken) (1-click Google sign-in).
3. Run `gemini-mcp.exe` (double-click or from terminal):
   ```powershell
   gemini-mcp.exe "C:\Projects\MyApp"
   ```
   On first launch, it downloads `ngrok.exe` to `%LOCALAPPDATA%\GeminiMCP`, asks for your token once, and **automatically copies the `https://.../mcp` URL to your clipboard**.

---

## Connecting to Gemini Web (`gemini.google.com`)

1. Open [gemini.google.com](https://gemini.google.com/) (make sure **Gemini Apps Activity / Keep Activity** is enabled in your Google Account).
2. Go to **Menu → Settings → Connected Apps**.
3. Click **`+`** (Custom / Add app) in the top-right corner.
4. Paste the copied MCP Server URL:
   ```text
   https://xxxx-xxxx.ngrok-free.dev/mcp
   ```
   Leave **Client ID** and **Client Secret** blank → click **Next** → **Connect**.
5. In any chat, mention `@Local PC Files GeminiMCP` and ask Gemini to inspect, create, or edit files in your folder!

---

## Interactive CLI Commands

| Command | Description |
| :--- | :--- |
| `/web` | Open `gemini.google.com`, copy MCP URL, and stream live MCP tool calls (press `Enter` to return to CLI) |
| `/attach <path>` | Copy a file, photo, or video into `_attachments/` (or simply **drag & drop** it into the terminal and press `Enter`) |
| `/folder <path>` | Switch the active workspace folder live (keeps the same MCP URL) |
| `/session <name>` | Switch to or create a named session (remembers folder + `/exec` setting) |
| `/sessions` | List all saved sessions |
| `/session del <name>` | Delete a saved session |
| `/exec on` / `/exec off` | Enable or disable `run_command` tool live |
| `/url` | Display and copy the active `https://.../mcp` URL to clipboard |
| `/ls [subpath]` | List files in the active workspace |
| `/logs [N]` | Show the last `N` MCP tool calls from Gemini |
| `/status` | Show active session, workspace folder, `/exec` state, and URL |
| `/clear` | Clear the terminal screen |
| `/update` | Check GitHub Releases and auto-update `gemini-mcp.exe` |
| `/help` | Show available commands |
| `/exit` | Stop the tunnel and server |

### Startup Flags
```powershell
gemini-mcp.exe [path] [--session name] [--port 8000] [--token NGROK_TOKEN] [--allow-exec] [--no-tunnel]
```

---

## Running & Building from Source

```powershell
cd source
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
.\.venv\Scripts\python gemini_mcp_cli.py
```

Build standalone `.exe` with PyInstaller:
```powershell
.\.venv\Scripts\pip install pyinstaller
.\.venv\Scripts\pyinstaller --noconfirm --onefile --console --name gemini-mcp `
  --hidden-import uvicorn.logging `
  --hidden-import uvicorn.loops.auto `
  --hidden-import uvicorn.protocols.http.auto `
  --hidden-import uvicorn.lifespan.on `
  gemini_mcp_cli.py
```

---

## Security
- All file operations (`list_files`, `read_file`, `read_image`, `write_file`, `edit_file`, `delete_file`, `search_files`) are strictly sandboxed inside the active workspace folder (path traversal `../` is blocked).
- `run_command` is **disabled by default** and only runs when explicitly enabled via `/exec on` or `--allow-exec`.
- The tunnel stays active only while `gemini-mcp.exe` is running.
