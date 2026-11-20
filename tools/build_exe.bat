@echo off
setlocal
cd /d %~dp0..

set PY=python
if exist ".venv\Scripts\python.exe" set PY=.venv\Scripts\python.exe

%PY% -m PyInstaller --noconfirm --clean StarSnip.spec
if errorlevel 1 exit /b 1

copy /y config.json dist\config.json >nul
xcopy /y /i /e assets dist\assets >nul

echo.
echo Built: dist\StarSnip.exe  (config.json + assets copied next to it)
