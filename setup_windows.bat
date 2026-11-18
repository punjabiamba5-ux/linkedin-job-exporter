@echo off
setlocal
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" goto :install
where py >nul 2>nul
if not errorlevel 1 (
  py -3 -m venv .venv
  goto :install
)
if exist "%USERPROFILE%\.local\bin\python3.11.exe" (
  "%USERPROFILE%\.local\bin\python3.11.exe" -m venv .venv
  goto :install
)
where python >nul 2>nul
if not errorlevel 1 (
  python -m venv .venv
  goto :install
)
echo Python was not found. Install Python 3.11 or newer with Tcl/Tk from https://www.python.org/downloads/windows/
goto :failed
:install
if not exist ".venv\Scripts\python.exe" goto :failed
".venv\Scripts\python.exe" -c "import sys, tkinter; assert sys.version_info >= (3,11), 'Python 3.11 or newer is required'"
if errorlevel 1 goto :failed
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto :failed
".venv\Scripts\python.exe" -m playwright install chromium
if errorlevel 1 goto :failed
echo Setup complete. Double-click start_windows.bat to open the app.
pause
exit /b 0
:failed
echo Setup failed. Check the error above and your internet connection.
pause
exit /b 1
