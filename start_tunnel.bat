@echo off
setlocal enabledelayedexpansion

for /f "usebackq tokens=1,* delims==" %%A in (".env") do (
    if "%%A"=="OLLAMA_SSH_USER" set "OLLAMA_SSH_USER=%%B"
    if "%%A"=="OLLAMA_HOST" set "OLLAMA_HOST=%%B"
)

if "%OLLAMA_SSH_USER%"=="" (
    echo OLLAMA_SSH_USER not set in .env -- see .env.example
    pause
    exit /b 1
)
if "%OLLAMA_HOST%"=="" (
    echo OLLAMA_HOST not set in .env -- see .env.example
    pause
    exit /b 1
)

echo Starting SSH tunnel to %OLLAMA_HOST%...
ssh -N -L 11434:localhost:11434 %OLLAMA_SSH_USER%@%OLLAMA_HOST%
