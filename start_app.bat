@echo off
rem Starts Manager Co-Pilot: the backend and the frontend each in their own window, then opens the browser.
rem Close those two windows to stop the app.
setlocal
set ROOT=%~dp0

rem Remove two frontend files the new layout replaced (left over from before the redesign).
if exist "%ROOT%frontend\src\components\Sidebar.tsx" del /q "%ROOT%frontend\src\components\Sidebar.tsx"
if exist "%ROOT%frontend\src\components\DetailPanel.tsx" del /q "%ROOT%frontend\src\components\DetailPanel.tsx"
if exist "%ROOT%frontend\src\components\TypeBadge.tsx" del /q "%ROOT%frontend\src\components\TypeBadge.tsx"

rem First run only: create the Python environment.
if not exist "%ROOT%backend\.venv\Scripts\python.exe" (
  echo Setting up the backend for the first time...
  cd /d "%ROOT%backend"
  python -m venv .venv || goto :nopython
  ".venv\Scripts\python" -m pip install -r requirements-dev.txt || goto :failed
)

rem First run, or after a new package was added: install the frontend packages.
if not exist "%ROOT%frontend\node_modules\@fontsource-variable\plus-jakarta-sans" (
  echo Installing frontend packages...
  cd /d "%ROOT%frontend"
  call npm install || goto :nonode
)

start "Manager Co-Pilot backend" /d "%ROOT%backend" cmd /k ".venv\Scripts\python main.py --api"
start "Manager Co-Pilot frontend" /d "%ROOT%frontend" cmd /k "npm run dev"

echo Starting... the browser opens in a few seconds.
timeout /t 6 /nobreak >nul
start "" http://localhost:5173
exit /b 0

:nopython
echo Python was not found. Install Python 3.12 from python.org, then run this again.
pause
exit /b 1
:nonode
echo npm was not found. Install Node.js (LTS) from nodejs.org, then run this again.
pause
exit /b 1
:failed
echo Installing the backend packages failed; see the messages above.
pause
exit /b 1
