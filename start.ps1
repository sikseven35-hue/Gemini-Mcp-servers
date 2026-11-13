$ErrorActionPreference = "Stop"
$dir = Split-Path -Parent $MyInvocation.MyCommand.Path
$py = if (Test-Path "$dir\.venv\Scripts\python.exe") { "$dir\.venv\Scripts\python.exe" } else { "python" }
& $py "$dir\gemini_mcp_cli.py" @args
