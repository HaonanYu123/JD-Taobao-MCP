@echo off
cd /d "%~dp0\.."
if not exist ".venv\Scripts\python.exe" (
  echo 未找到虚拟环境，请先运行 scripts\install_windows.ps1
  exit /b 1
)
".venv\Scripts\python.exe" server.py
