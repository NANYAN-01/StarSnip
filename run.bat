@echo off
setlocal
cd /d %~dp0
set PYTHONPATH=%~dp0src

if exist ".venv\Scripts\pythonw.exe" (
  start "" ".venv\Scripts\pythonw.exe" -m starsnip %*
) else (
  where pythonw >nul 2>nul
  if %errorlevel%==0 (
    start "" pythonw -m starsnip %*
  ) else (
    python -m starsnip %*
  )
)
