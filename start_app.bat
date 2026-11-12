@echo off
rem Starts Manager Co-Pilot: the backend and the frontend each in their own window, then opens the browser.
rem Close those two windows to stop the app.
setlocal
set ROOT=%~dp0
set "REINSTALL=0"
set "ENTRY=main.py --api"
if /I "%~1"=="--setup" set "REINSTALL=1"
if /I "%~2"=="--setup" set "REINSTALL=1"
if /I "%~1"=="--demo" set "ENTRY=demo_backend.py"
if /I "%~2"=="--demo" set "ENTRY=demo_backend.py"

rem First run only: create the Python environment.
if not exist "%ROOT%backend\.venv\Scripts\python.exe" (
  echo Setting up the backend for the first time...
  cd /d "%ROOT%backend"
  python -m venv .venv || goto :nopython
)
cd /d "%ROOT%backend"
".venv\Scripts\python" -c "import sys; assert sys.version_info[:2] == (3, 12), 'Use Python 3.12'" || goto :nopython
if not exist ".venv\.copilot-ready" set "REINSTALL=1"
if "%REINSTALL%"=="1" (
  if exist ".venv\.copilot-ready" del /q ".venv\.copilot-ready"
  ".venv\Scripts\python" -m pip install -r requirements-dev.txt || goto :failed
  echo ready> ".venv\.copilot-ready"
)

rem First run, or after a new package was added: install the frontend packages.
if not exist "%ROOT%frontend\node_modules\.copilot-ready" set "REINSTALL=1"
if "%REINSTALL%"=="1" (
  echo Installing frontend packages...
  cd /d "%ROOT%frontend"
  call npm ci || goto :nonode
  echo ready> "node_modules\.copilot-ready"
)

start "Manager Co-Pilot backend" /d "%ROOT%backend" cmd /k ".venv\Scripts\python %ENTRY%"
start "Manager Co-Pilot frontend" /d "%ROOT%frontend" cmd /k "npm run dev"

echo Starting... the browser opens in a few seconds.
echo After dependency changes, run start_app.bat --setup to refresh both environments.
timeout /t 6 /nobreak >nul
start "" http://localhost:5173
exit /b 0

:nopython
echo Python 3.12 is required. Check python --version and the backend .venv Python version.
echo If the existing .venv uses another version, recreate only that environment using Python 3.12.
pause
exit /b 1
:nonode
echo Frontend setup failed. Check Node.js/npm, the network and the error above, then rerun with --setup.
pause
exit /b 1
:failed
echo Installing the backend packages failed; see the messages above.
pause
exit /b 1
