@echo off
rem Default: offline plumbing checks only. Pass --real explicitly for paid model runs.
rem Stored scores are provisional development results until labels and the final version are reviewed.
setlocal
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8
set "PY=%~dp0backend\.venv\Scripts\python.exe"
set "MODE=--fake"
if /I "%~1"=="--real" set "MODE="
if not "%~1"=="" if /I not "%~1"=="--real" if /I not "%~1"=="--fake" goto :usage
if not exist "%PY%" goto :missing
echo Mode: %MODE% ^(empty means real model; API charges apply^)
echo [%date% %time%] Tests > evaluation\last_run.log
pushd backend
"%PY%" -m pytest -q -p no:cacheprovider >> ..\evaluation\last_run.log 2>&1
set "TEST_EXIT=%ERRORLEVEL%"
popd
if not "%TEST_EXIT%"=="0" goto :failed
"%PY%" evaluation\run_evaluation.py --check >> evaluation\last_run.log 2>&1
if errorlevel 1 goto :failed
echo [%date% %time%] Evaluation >> evaluation\last_run.log
"%PY%" evaluation\run_evaluation.py %MODE% >> evaluation\last_run.log 2>&1
if errorlevel 1 goto :failed
echo [%date% %time%] Development set >> evaluation\last_run.log
"%PY%" evaluation\run_evaluation.py --set development %MODE% >> evaluation\last_run.log 2>&1
if errorlevel 1 goto :failed
echo [%date% %time%] Finished >> evaluation\last_run.log
echo Run completed. Read evaluation\last_run.log for actual pass/fail results.
pause
exit /b 0
:failed
echo Stopped after a failed step. No later evaluation was started. See evaluation\last_run.log
pause
exit /b 1
:missing
echo Python environment is missing. Run start_app.bat --setup first.
pause
exit /b 1
:usage
echo Usage: run_evaluation.bat [--fake ^| --real]
pause
exit /b 2
