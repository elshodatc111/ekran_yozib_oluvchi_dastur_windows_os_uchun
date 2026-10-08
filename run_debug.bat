@echo off
rem Xatolarni konsolda ko'rish uchun
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Avval setup.bat ni ishga tushiring.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" main.py
pause
