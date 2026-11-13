# GeminiMCP (`v0.5.0`)

**Credits:** Fikus & Hydrogen

A minimal, one-click Windows launcher that starts a local **MCP (Model Context Protocol)** file server + **ngrok** HTTPS tunnel, copies the MCP URL to your clipboard, and opens **Gemini Web (`gemini.google.com`)** so web models like **Hydrogen** and **Argon** can read, search, create, edit files, and inspect images on your PC.

---

## Features
- **Zero-config launch** — starts the MCP server, brings up `ngrok`, copies `https://.../mcp` to clipboard, and opens `gemini.google.com` automatically.
- **Auto-setup `ngrok` wizard** — downloads `ngrok.exe` on first run, opens your browser to the token page, and saves your token.
- **Built-in Auto-Update** — checks GitHub Releases on startup and updates `gemini-mcp.exe` in place.
- **Live activity log** — shows every file read/write/edit call from Gemini in real time.

---

## Quick Start

1. Download **`gemini-mcp.exe`** from [Releases](../../releases/latest).
2. Double-click `gemini-mcp.exe` (or pass a folder path: `gemini-mcp.exe "C:\Projects\MyApp"`).
3. On first launch, sign in to ngrok when the browser opens and paste your free authtoken.
4. It will copy `https://xxxx.ngrok-free.dev/mcp` to your clipboard and open `gemini.google.com`:
   - Go to **Menu → Settings → Connected Apps → `+`**
   - Paste the URL (leave OAuth Client ID & Secret blank) → **Next** → **Connect**.
   - Mention `@Local PC Files GeminiMCP` in any chat!

### Optional Flags
```powershell
gemini-mcp.exe [path] [--port 8000] [--token NGROK_TOKEN] [--allow-exec] [--no-tunnel] [--no-open] [--no-update-check]
```

---

## Building from Source

```powershell
cd source
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt pyinstaller
.\.venv\Scripts\pyinstaller --noconfirm --onefile --console --name gemini-mcp `
  --hidden-import uvicorn.logging `
  --hidden-import uvicorn.loops.auto `
  --hidden-import uvicorn.protocols.http.auto `
  --hidden-import uvicorn.lifespan.on `
  gemini_mcp_cli.py
```
