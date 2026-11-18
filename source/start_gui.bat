@echo off
setlocal
cd /d "%~dp0"
if not exist "%~dp0.venv\Scripts\python.exe" (
  echo Please run setup.ps1 first to create the Python environment.
  pause
  exit /b 1
)
"%~dp0.venv\Scripts\python.exe" "%~dp0desktop.py"
if errorlevel 1 pause
