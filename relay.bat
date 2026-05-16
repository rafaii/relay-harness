@echo off
REM Relay Framework Entry Point (Windows)

REM Check if venv exists, create if not
if not exist "%~dp0venv" (
    echo Virtual environment not found. Creating venv...
    python -m venv "%~dp0venv"
    echo Installing dependencies...
    "%~dp0venv\Scripts\pip" install --upgrade pip >nul 2>&1
    "%~dp0venv\Scripts\pip" install -r "%~dp0.relay-framework\requirements.txt" >nul 2>&1
    "%~dp0venv\Scripts\playwright" install chromium >nul 2>&1
    echo Setup complete!
)

REM Use venv Python
set PYTHON_BIN=%~dp0venv\Scripts\python.exe

REM Execute Python entry point with venv Python
"%PYTHON_BIN%" "%~dp0.relay-framework\relay.py" %*
