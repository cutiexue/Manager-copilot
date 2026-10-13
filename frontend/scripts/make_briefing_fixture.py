"""Regenerate src/fixtures/briefing.json from the backend's own briefing tool.

The backend has no HTTP endpoint for the morning briefing yet, so the UI reads a
snapshot of `briefing.get_morning_briefing()` instead. Nothing here computes
business numbers: the briefing is taken verbatim, and every cited source row is
looked up in the CSV so the evidence drawer can show the raw data.

Usage:
    python3 scripts/make_briefing_fixture.py <backend_dir> [as_of_date]

<backend_dir> must contain briefing.py and track1/data/*.csv (the `src` branch
code plus the `data` branch CSVs).
"""

import csv
import os
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


def collect_refs(node, out):
    if isinstance(node, dict):
        if "source" in node and "row" in node:
            out.add((node["source"], node["row"]))
        elif "source_row" in node:
            out.add(("track1/data/production_log.csv", node["source_row"]))
        for value in node.values():
            collect_refs(value, out)
    elif isinstance(node, list):
        for value in node:
            collect_refs(value, out)


def main():
    backend = Path(sys.argv[1]).resolve()
    as_of = sys.argv[2] if len(sys.argv) > 2 else None
    sys.path.insert(0, str(backend))
    import briefing  # noqa: E402  (imported from the backend directory)

    result = briefing.get_morning_briefing(as_of) if as_of else briefing.get_morning_briefing()

    refs = set()
    collect_refs(result, refs)
    rows = {}
    for source, row in sorted(refs):
        with open(backend / source, newline="", encoding="utf-8") as handle:
            lines = list(csv.reader(handle))
        header, values = lines[0], lines[row - 1]  # `row` is the file line number
        rows[f"{source}#{row}"] = dict(zip(header, values))

    try:
        commit = subprocess.run(["git", "-C", str(backend), "rev-parse", "--short", "HEAD"],
                                capture_output=True, text=True).stdout.strip() or None
    except OSError:
        commit = None
    commit = commit or os.environ.get("BACKEND_COMMIT")  # e.g. when backend_dir is a git archive

    fixture = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "generator": "briefing.get_morning_briefing()",
        "backend_commit": commit,
        "briefing": result,
        "source_rows": rows,
        "briefing_text": briefing.render_briefing_text(result),
    }
    target = Path(__file__).resolve().parent.parent / "src" / "fixtures" / "briefing.json"
    target.write_text(json.dumps(fixture, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote {target} ({len(rows)} source rows)")


if __name__ == "__main__":
    main()
