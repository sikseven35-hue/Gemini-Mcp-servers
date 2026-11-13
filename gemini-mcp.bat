@echo off
setlocal
set "DIR=%~dp0"
if exist "%DIR%.venv\Scripts\python.exe" (
    "%DIR%.venv\Scripts\python.exe" "%DIR%gemini_mcp_cli.py" %*
) else (
    python "%DIR%gemini_mcp_cli.py" %*
)
