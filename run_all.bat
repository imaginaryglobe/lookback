@echo off
setlocal enabledelayedexpansion

echo ============================================
echo  Media Search -- starting everything
echo ============================================

if not exist ".env" (
    echo No .env found -- running first-time setup...
    venv\Scripts\python.exe setup.py
    if not exist ".env" (
        echo Setup did not complete. Exiting.
        pause
        exit /b 1
    )
)

set "OLLAMA_REMOTE="
for /f "usebackq tokens=1,* delims==" %%A in (".env") do (
    if "%%A"=="OLLAMA_REMOTE" set "OLLAMA_REMOTE=%%B"
)

echo [1/4] Starting Qdrant (Docker)...
docker compose up -d
if errorlevel 1 (
    echo Failed to start Qdrant. Is Docker Desktop running?
    pause
    exit /b 1
)

if /i "%OLLAMA_REMOTE%"=="true" (
    echo [2/4] Starting SSH tunnel to your Ollama machine in a new window...
    start "SSH Tunnel (keep open)" cmd /k start_tunnel.bat
    echo [3/4] Waiting a few seconds for the tunnel to connect...
    timeout /t 5 /nobreak >nul
) else (
    echo [2/4] Ollama configured as local -- skipping SSH tunnel.
    echo [3/4] Skipping tunnel wait.
)

echo [4/4] Starting the web server...
start "" http://localhost:8000
venv\Scripts\python.exe main.py

endlocal
