#!/bin/bash
# Two more real-model runs of every scenario whose result differs from Evaluation.pdf, to test stability.
set -u
E="$(cd "$(dirname "$0")/.." && pwd)"
cd "$E/../../backend" || exit 1
export PYTHONDONTWRITEBYTECODE=1
for n in 2 3; do
  .venv/bin/python "$E/harness/retest_report_questions.py" --out "$E/reruns/run$n" --only Q08 Q14 Q20 Q36 Q42 Q43 Q49 Q50 Q60 Q69 2>&1 | tee "$E/reruns/run$n.log"
done
echo "reruns finished"
