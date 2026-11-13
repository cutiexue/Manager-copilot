#!/bin/bash
# Full real-model retest: the automated evaluation and development sets, then every Evaluation.pdf question.
# Everything is written under this evidence folder; the repository's failure ledger is not touched.
set -u
E="$(cd "$(dirname "$0")/.." && pwd)"
R="$E/../.."
export PYTHONDONTWRITEBYTECODE=1
cd "$R" || exit 1
mkdir -p "$E/automated" "$E/report_questions"
backend/.venv/bin/python evaluation/run_evaluation.py --set evaluation --out "$E/automated/evaluation_set" --no-ledger 2>&1 | tee "$E/automated/evaluation_set.log"
backend/.venv/bin/python evaluation/run_evaluation.py --set development --out "$E/automated/development_set" --no-ledger 2>&1 | tee "$E/automated/development_set.log"
cd backend || exit 1
.venv/bin/python "$E/harness/retest_report_questions.py" --out "$E/report_questions" 2>&1 | tee "$E/report_questions/run.log"
echo "retest finished"
