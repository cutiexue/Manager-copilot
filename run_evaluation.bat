@echo off
rem Double-click to run the tests, then both evaluation sets (30 held-out + 17 development cases) with the real model.
rem The model and key come from backend\.env. Progress goes to evaluation\last_run.log;
rem reports go to evaluation\reports\<time>\ (summary.md, results.jsonl).
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8
set PY=%~dp0backend\.venv\Scripts\python.exe
echo [%date% %time%] Tests > evaluation\last_run.log
pushd backend
"%PY%" -m pytest -q -p no:cacheprovider >> ..\evaluation\last_run.log 2>&1
popd
echo [%date% %time%] Evaluation (real model) >> evaluation\last_run.log
"%PY%" evaluation\run_evaluation.py >> evaluation\last_run.log 2>&1
echo [%date% %time%] Development set (real model) >> evaluation\last_run.log
"%PY%" evaluation\run_evaluation.py --set development >> evaluation\last_run.log 2>&1
echo [%date% %time%] Finished >> evaluation\last_run.log
echo Finished. See evaluation\last_run.log
pause
