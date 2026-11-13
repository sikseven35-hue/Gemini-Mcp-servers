# GeminiMCP CLI (`v0.4.0`)

**Credits:** Fikus & Hydrogen

A lightweight, zero-hassle Windows launcher that starts a local **MCP (Model Context Protocol)** file server + **ngrok** HTTPS tunnel, copies the MCP URL to your clipboard, and opens **Gemini Web (`gemini.google.com`)** so web models like **Hydrogen** and **Argon** can read, search, create, edit files, inspect images, and run commands inside your PC folder.

---

## Features
- **One-click launch** — starts the MCP server, brings up `ngrok`, copies the `https://.../mcp` URL, and opens `gemini.google.com` automatically.
- **Auto-setup `ngrok` wizard** — downloads `ngrok.exe` on first run, opens your browser to the token page, and saves your token.
- **Built-in Auto-Update (`/update`)** — checks GitHub Releases on startup and updates `gemini-mcp.exe` in place.
- **Live workspace switching (`/folder`)** — change folders on the fly **without reconnecting the MCP URL in Gemini**.
- **Named sessions (`/session`, `/sessions`)** — save multiple projects (folder + `/exec` permission) and switch between them.
- **Drag & Drop attachments (`/attach`)** — drag and drop any file, photo, or video into the CLI window to copy it into `_attachments/` (with `read_image` support for images).
- **On-demand terminal (`/exec on` / `off`)** — toggle `run_command` anytime.

---

## Quick Start

1. Download **`gemini-mcp.exe`** from [Releases](../../releases/latest).
2. Double-click `gemini-mcp.exe` (or run `gemini-mcp.exe "C:\Projects\MyApp"`).
3. On first launch, sign in to ngrok when the browser opens and paste your free authtoken.
4. It will copy `https://xxxx.ngrok-free.dev/mcp` to your clipboard and open `gemini.google.com`:
   - Go to **Menu → Settings → Connected Apps → `+`**
   - Paste the URL (leave OAuth Client ID & Secret blank) → **Next** → **Connect**.
   - Mention `@Local PC Files GeminiMCP` in any chat!

---

## CLI Commands

| Command | Description |
| :--- | :--- |
| `/web` | Open `gemini.google.com` & stream live MCP tool calls (`Enter` to return) |
| `/attach <path>` | Copy a file, photo, or video into `_attachments/` (or drag & drop into window) |
| `/folder <path>` | Switch active workspace folder live (keeps same MCP URL) |
| `/session <name>` | Switch to or create a named session |
| `/sessions` | List all saved sessions |
| `/session del <name>` | Delete a saved session |
| `/exec on` / `/exec off` | Enable or disable `run_command` tool live |
| `/url` | Show and copy the active `https://.../mcp` URL |
| `/ls [subpath]` | List files in the active workspace |
| `/logs [N]` | Show the last `N` MCP tool calls from Gemini |
| `/status` | Show active session, workspace folder, `/exec` state, and URL |
| `/update` | Check GitHub Releases and auto-update `gemini-mcp.exe` |
| `/clear` | Clear the terminal screen |
| `/help` | Show available commands |
| `/exit` | Stop the tunnel and server |

### Startup Flags
```powershell
gemini-mcp.exe [path] [--session name] [--port 8000] [--token NGROK_TOKEN] [--allow-exec] [--no-tunnel] [--no-open] [--no-update-check]
```
