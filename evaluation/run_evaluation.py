#!/usr/bin/env python3
"""Run the Track 1 language evaluation (plan §13.2 Layer 3) and score every answer.

From the repository root:

    backend/.venv/bin/python evaluation/run_evaluation.py --check            # validate the case files only
    backend/.venv/bin/python evaluation/run_evaluation.py --fake             # offline plumbing check, no API key
    backend/.venv/bin/python evaluation/run_evaluation.py --provider deepseek
    backend/.venv/bin/python evaluation/run_evaluation.py --set development --cases T1-DEV-001 T1-DEV-004
    backend/.venv/bin/python evaluation/run_evaluation.py --rescore evaluation/reports/<run>

Each case runs in a fresh temporary SQLite database and conversation, so no case sees another
case's history, proposals or the app's own database. Every response is kept in results.jsonl,
summary.md holds the §13.4 metrics, and every failed case is appended to failure_ledger.jsonl
(§13.6) with the human fields (root cause, fix, ...) left empty.

Expected facts were computed from the CSVs and the deterministic tools, never by a model. The
scoring is heuristic: it normalises text and looks for tokens and phrases. It flags; it does not
judge. Behaviour labels carry the classifier's reason, a reviewer can override a label in
results.jsonl ("human_override") and record faithfulness ("human_review"), then --rescore.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
import unicodedata
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

EVAL_DIR = Path(__file__).resolve().parent
REPO_ROOT = EVAL_DIR.parent
BACKEND_DIR = REPO_ROOT / "backend"
DATA_DIR = BACKEND_DIR / "track1" / "data"
for _path in (EVAL_DIR, BACKEND_DIR):  # backend modules import by plain name (import tools)
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

DATA_FILES = ("orders.csv", "production_log.csv", "workshops.csv")
SET_FILES = {"evaluation": EVAL_DIR / "evaluation_set.jsonl",
             "development": EVAL_DIR / "development_set.jsonl"}
LEDGER = EVAL_DIR / "failure_ledger.jsonl"
REPORTS = EVAL_DIR / "reports"

BEHAVIORS = ("ANSWER", "CLARIFY", "DECLINE", "PROPOSE")
OWNERS = tuple("ABCDEF")
CATEGORIES = ("direct_lookup", "aggregation", "comparison_judgement", "discovery_briefing", "tracing_why",
              "multi_turn", "feasibility", "action", "ambiguous", "unanswerable", "hallucination_bait")
TAGS = CATEGORIES + ("end_to_end", "confirmation", "audit", "concise", "evidence_expansion")
PROPOSAL_TOOLS = ("propose_reminder", "propose_order_note", "draft_chase_message", "propose_watch")
NEW_TOOLS = ("search_orders", *PROPOSAL_TOOLS, "list_follow_ups")  # added in Sprint 2; may postdate a checkout
APP_STATE_TOOLS = {*PROPOSAL_TOOLS, "list_follow_ups"}
EXECUTED_STATUSES = {"CONFIRMED", "EXECUTED"}  # nobody presses Confirm during an evaluation run
CHECKS = ("asks_for_confirmation", "no_execution_claim", "states_assumptions", "no_guarantee",
          "max_words", "first_sentence_includes")

# Minimum coverage of the locked evaluation set (plan §13.2 Layer 3).
EVAL_MIN_CASES = 30
EVAL_PER_OWNER = 5
EVAL_MIN_GROUPS = {
    "ambiguous / unanswerable / hallucination bait": (("ambiguous", "unanswerable", "hallucination_bait"), 5),
    "feasibility or action": (("feasibility", "action"), 5),
    "direct lookup": (("direct_lookup",), 1),
    "aggregation": (("aggregation",), 1),
    "comparison / judgement": (("comparison_judgement",), 1),
    "discovery / briefing": (("discovery_briefing",), 1),
    "tracing / why": (("tracing_why",), 1),
    "multi-turn follow-up": (("multi_turn",), 1),
}

REQUIRED_FIELDS = {"case_id": str, "set": str, "category": str, "owner": str, "reviewer": str,
                   "review_status": str, "turns": list, "expected_behavior": list, "expected_facts": dict,
                   "required_tools": list, "forbidden_tools": list, "allowed_side_effects": list,
                   "ground_truth_source": str, "notes": str}
OPTIONAL_FIELDS = {"tags": list, "turn_facts": dict, "expected_tool_args": dict, "behavior_checks": list,
                   "required_evidence": list, "forbidden_claims": list}


# ------------------------------------------------------------------------------------ case files

def load_cases(path):
    """One JSON object per line; blank lines are ignored."""
    cases = []
    for number, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), 1):
        if line.strip():
            try:
                cases.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path} line {number}: {exc}") from None
    return cases


def alternatives(item):
    """A fact, tool or behaviour is a string, or a list of acceptable alternatives."""
    return [item] if isinstance(item, str) else list(item)


def _is_alt_list(value):
    return isinstance(value, list) and value and all(isinstance(v, str) and v for v in value)


def known_tool_names():
    """Tool names an expectation may use: the registered tools plus the Sprint 2 additions."""
    try:
        from tool_schemas import TOOL_FUNCTIONS
        return set(TOOL_FUNCTIONS) | set(NEW_TOOLS)
    except Exception:  # the backend may be mid-change; validation of names is then skipped
        return None


def parse_check(spec):
    """'max_words:40@2' -> ('max_words', '40', '2')."""
    name, _, turns = spec.partition("@")
    name, _, param = name.partition(":")
    return name, param or None, turns or None


def case_problems(case, known_tools=None):
    """Everything wrong with one case definition, as readable strings (empty means valid)."""
    cid = case.get("case_id", "<no case_id>")
    problems = [f"{cid}: '{field}' must be a {kind.__name__}" for field, kind in REQUIRED_FIELDS.items()
                if not isinstance(case.get(field), kind)]
    problems += [f"{cid}: '{field}' must be a {kind.__name__}" for field, kind in OPTIONAL_FIELDS.items()
                 if field in case and not isinstance(case[field], kind)]
    problems += [f"{cid}: unknown field '{field}'" for field in case
                 if field not in REQUIRED_FIELDS and field not in OPTIONAL_FIELDS]
    if problems:
        return problems
    turns, behaviors = case["turns"], case["expected_behavior"]
    if not re.fullmatch(r"T1-(EVAL|DEV)-\d{3}", cid):
        problems.append(f"{cid}: case_id must look like T1-EVAL-001 or T1-DEV-001")
    if not turns or not all(isinstance(t, str) and t.strip() for t in turns):
        problems.append(f"{cid}: turns must be non-empty strings")
    if len(behaviors) != len(turns):
        problems.append(f"{cid}: expected_behavior needs one entry per turn")
    for item in behaviors:
        if not (isinstance(item, str) or _is_alt_list(item)) or set(alternatives(item)) - set(BEHAVIORS):
            problems.append(f"{cid}: behaviour {item!r} is not one of {BEHAVIORS}")
    if case["owner"] not in OWNERS:
        problems.append(f"{cid}: owner must be one of A-F")
    if case["category"] not in CATEGORIES:
        problems.append(f"{cid}: category {case['category']!r} is not one of {CATEGORIES}")
    problems += [f"{cid}: tag {tag!r} is not one of {TAGS}" for tag in case.get("tags", []) if tag not in TAGS]
    if case["review_status"] not in ("draft", "verified"):
        problems.append(f"{cid}: review_status must be draft or verified")
    if case["review_status"] == "verified" and case["reviewer"] in ("", "TBD", case["owner"]):
        problems.append(f"{cid}: a verified case needs a named reviewer other than its owner")

    def fact_list(value, where):
        if not isinstance(value, list) or not all(isinstance(f, str) and f or _is_alt_list(f) for f in value):
            problems.append(f"{cid}: {where} must be a list of strings or lists of alternatives")

    facts = case["expected_facts"]
    if set(facts) - {"must_include", "must_not_include"}:
        problems.append(f"{cid}: expected_facts takes only must_include and must_not_include")
    for key in ("must_include", "must_not_include"):
        fact_list(facts.get(key, []), f"expected_facts.{key}")
    for key, value in case.get("turn_facts", {}).items():
        if not (key.isdigit() and 1 <= int(key) <= len(turns)) or not isinstance(value, dict) \
                or set(value) - {"must_include", "must_not_include"}:
            problems.append(f"{cid}: turn_facts keys are turn numbers 1..{len(turns)} with must_include/must_not_include")
            continue
        for sub in ("must_include", "must_not_include"):
            fact_list(value.get(sub, []), f"turn_facts.{key}.{sub}")
    for item in case["required_tools"]:
        if not (isinstance(item, str) and item or _is_alt_list(item)):
            problems.append(f"{cid}: required_tools entries are tool names or lists of alternatives")
    names = {n for item in case["required_tools"] for n in alternatives(item)}
    names |= set(case["forbidden_tools"]) | set(case.get("expected_tool_args", {}))
    if known_tools is not None:
        problems += [f"{cid}: unknown tool '{name}'" for name in sorted(names - known_tools)]
    for name, args in case.get("expected_tool_args", {}).items():
        if not isinstance(args, dict) or not args:
            problems.append(f"{cid}: expected_tool_args.{name} must be a non-empty object")
    for spec in case.get("behavior_checks", []):
        name, param, at = parse_check(spec) if isinstance(spec, str) else (None, None, None)
        if name not in CHECKS:
            problems.append(f"{cid}: unknown behavior check {spec!r}")
        elif name == "max_words" and not (param or "").isdigit():
            problems.append(f"{cid}: max_words needs a number, e.g. max_words:40")
        elif name == "first_sentence_includes" and not param:
            problems.append(f"{cid}: first_sentence_includes needs tokens, e.g. first_sentence_includes:yes|no")
        if at and at not in ("all", "last") and not all(p.isdigit() and 1 <= int(p) <= len(turns) for p in at.split(",")):
            problems.append(f"{cid}: check turn selector {at!r} must be all, last or turn numbers")
    for ref in case.get("required_evidence", []):
        if not (isinstance(ref, str) and re.fullmatch(r"[\w.]+\.csv#\d+", ref)):
            problems.append(f"{cid}: required_evidence entries look like orders.csv#86")
    if set(case["allowed_side_effects"]) - {"reminder", "note", "chase_message", "watch"}:
        problems.append(f"{cid}: allowed_side_effects lists action kinds (reminder, note, chase_message, watch)")
    return problems


def set_problems(cases, set_name, known_tools=None):
    """Case problems plus set-level ones: unique IDs, the right set name, evaluation coverage."""
    problems = [p for case in cases for p in case_problems(case, known_tools)]
    ids = [case.get("case_id") for case in cases]
    problems += [f"duplicate case_id {cid}" for cid in sorted({c for c in ids if ids.count(c) > 1})]
    problems += [f"{case.get('case_id')}: set must be {set_name!r}" for case in cases if case.get("set") != set_name]
    prefix = {"evaluation": "T1-EVAL-", "development": "T1-DEV-"}.get(set_name)
    problems += [f"{cid}: IDs in the {set_name} set start with {prefix}" for cid in ids
                 if prefix and isinstance(cid, str) and not cid.startswith(prefix)]
    if set_name == "evaluation" and not problems:
        problems += coverage_problems(cases)
    return problems


def case_labels(case):
    """The category plus coverage tags; any case with more than one turn counts as multi-turn."""
    labels = {case["category"], *case.get("tags", [])}
    if len(case["turns"]) > 1:
        labels.add("multi_turn")
    return labels & set(CATEGORIES)


def coverage(cases):
    by_owner = {owner: sum(c["owner"] == owner for c in cases) for owner in OWNERS}
    by_label = {label: sum(label in case_labels(c) for c in cases) for label in CATEGORIES}
    groups = {name: sum(bool(case_labels(c) & set(labels)) for c in cases)
              for name, (labels, _) in EVAL_MIN_GROUPS.items()}
    return {"cases": len(cases), "by_owner": by_owner, "by_label": by_label, "groups": groups,
            "turns": sum(len(c["turns"]) for c in cases),
            "verified": sum(c.get("review_status") == "verified" for c in cases)}


def coverage_problems(cases):
    counts = coverage(cases)
    problems = []
    if counts["cases"] < EVAL_MIN_CASES:
        problems.append(f"evaluation set has {counts['cases']} cases; needs at least {EVAL_MIN_CASES}")
    problems += [f"owner {owner} has {n} cases; needs {EVAL_PER_OWNER}"
                 for owner, n in counts["by_owner"].items() if n < EVAL_PER_OWNER]
    problems += [f"{name}: {counts['groups'][name]} cases; needs at least {minimum}"
                 for name, (_, minimum) in EVAL_MIN_GROUPS.items() if counts["groups"][name] < minimum]
    return problems


# ---------------------------------------------------------------------------- fact matching

_DASHES = str.maketrans({c: "-" for c in "\u2010\u2011\u2012\u2013\u2014\u2015\u2212\ufe58\ufe63\uff0d"})
_QUOTES = str.maketrans({"\u2018": "'", "\u2019": "'", "\u201c": '"', "\u201d": '"'})
_MONTHS = ("january", "february", "march", "april", "may", "june", "july", "august", "september",
           "october", "november", "december")
_NUMBER_WORDS = ("zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten",
                 "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen", "seventeen",
                 "eighteen", "nineteen", "twenty")
_ISO_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")


def normalize(text):
    """Casefold, unify dashes/minus signs and quotes, drop thousands separators and trailing zeros."""
    text = re.sub(r"(?<=\d)[,\u00a0\u202f\u2009](?=\d{3}(?!\d))", "", str(text))  # 1,500 / 1 500 -> 1500
    text = unicodedata.normalize("NFKC", text).translate(_DASHES).translate(_QUOTES)
    text = re.sub(r"(?<![\d.])(\d+)\.(\d*?)0+(?!\d)(?!\.\d)",                     # 939.0 -> 939, 29.30 -> 29.3
                  lambda m: m[1] + ("." + m[2] if m[2] else ""), text)
    return re.sub(r"\s+", " ", text).casefold().strip()


def _date_pattern(iso):
    """2026-03-29 also matches 29 March, Mar 29th, 29-Mar, 29/3 and 3/29 (year optional)."""
    year, month, day = (int(part) for part in iso.split("-"))
    name = _MONTHS[month - 1]
    month_names = f"(?:{name}|{name[:3]}\\.?{'|sept' if month == 9 else ''})"
    day_text = f"0?{day}(?:st|nd|rd|th)?"
    year_tail = f"(?:/(?:{year}|{year % 100:02d}))?"
    return "|".join([
        re.escape(iso),
        rf"(?<![\d.]){day_text}(?:\s+|-)(?:of\s+)?{month_names}(?![a-z])",
        rf"(?<![a-z]){month_names}(?:\s+|-){day_text}(?!\d)",
        rf"(?<![\d/.])0?{day}/0?{month}{year_tail}(?![\d/])",
        rf"(?<![\d/.])0?{month}/0?{day}{year_tail}(?![\d/])",
    ])


@lru_cache(maxsize=4096)
def fact_regex(fact):
    """Regex for one expected token, matched against normalize(answer)."""
    token = normalize(fact)
    if _ISO_DATE.fullmatch(token):
        return re.compile(_date_pattern(token))
    body = re.escape(token)
    if token[:1].isdigit():
        body = r"(?<![\d.])(?<!\d-)" + body  # 12 does not match ORD-120, 2026-03-12 or 3.12
    elif token[:1].isalnum():
        body = r"(?<![a-z0-9])" + body
    if token[-1:].isdigit():
        body += r"(?!\d)(?!\.\d)"
    elif token[-1:].isalnum():
        body += r"(?![a-z0-9])"
    if token.isdigit() and int(token) < len(_NUMBER_WORDS):
        body = f"(?:{body}|(?<![a-z]){_NUMBER_WORDS[int(token)]}(?![a-z]))"  # 12 also matches twelve
    return re.compile(body)


def has_fact(answer, fact):
    """True when any alternative of the fact occurs in the answer."""
    text = normalize(answer)
    return any(fact_regex(alt).search(text) for alt in alternatives(fact))


def _numeric(fact):
    return any(re.search(r"\d", alt) for alt in alternatives(fact))


def _show(fact):
    return fact if isinstance(fact, str) else " | ".join(fact)


def score_facts(case, answers):
    """Case-level must_include applies to the final turn, must_not_include to every turn;
    turn_facts adds expectations for individual turns."""
    spec = case.get("expected_facts") or {}
    last = len(answers)
    turns, numeric_checked, numeric_passed = [], 0, 0
    for number, answer in enumerate(answers, 1):
        extra = case.get("turn_facts", {}).get(str(number), {})
        include = list(extra.get("must_include", [])) + (list(spec.get("must_include", [])) if number == last else [])
        exclude = list(extra.get("must_not_include", [])) + list(spec.get("must_not_include", []))
        if not include and not exclude:
            continue
        missing = [_show(f) for f in include if not has_fact(answer or "", f)]
        present = [_show(f) for f in exclude if has_fact(answer or "", f)]
        for fact in include:
            if _numeric(fact):
                numeric_checked += 1
                numeric_passed += has_fact(answer or "", fact)
        for fact in exclude:
            if _numeric(fact):
                numeric_checked += 1
                numeric_passed += not has_fact(answer or "", fact)
        turns.append({"turn": number, "missing": missing, "forbidden_present": present})
    applicable = bool(turns)
    passed = all(not t["missing"] and not t["forbidden_present"] for t in turns) if applicable else None
    return {"applicable": applicable, "passed": passed, "turns": turns,
            "numeric_checked": numeric_checked, "numeric_passed": numeric_passed}


# ------------------------------------------------------------------------ behaviour classifier

_OFFER = re.compile(r"^(?:(?:and|so|also|or|then|otherwise|alternatively)[, ]+)?(?:would you like|do you want|"
                    r"want me to|shall i|should i|can i|could i|may i|need me to|let me know|is there anything|"
                    r"anything else|if you(?:'d| would)? (?:want|like)|would it help|i can also|happy to)")
_CLARIFY = re.compile(r"\bwhich\b|\bdo you mean\b|\bdid you mean\b|\bare you referring\b|\bclarify\b|"
                      r"\bspecify\b|\bwhat (?:exactly )?do you\b|\bor\b|\bconfirm which\b")
_DATA_WORDS = r"(?:data|dataset|records?|csvs?|files?|logs?|tables?|system)"
# Strong phrases decline whatever else the sentence says; caveat-prone ones ("the data doesn't include
# remaining quantities") count only in a lead sentence that states no new number.
_DECLINE_STRONG = [re.compile(p) for p in (
    rf"\b{_DATA_WORDS}\b[^.!?\n]{{0,60}}\b(?:has|have|contains?|holds?|includes?|carr(?:y|ies)|gives?|provides?)\s+no\b",
    r"\bno\s+(?:[\w&,-]+\s+){0,4}?(?:data|information|fields?|columns?|figures?)\b(?!\s+gaps?)",
    r"\bunsupported[_ ]by[_ ](?:the[_ ])?data\b|\bnot supported by the data\b|\bbeyond (?:what )?the data\b",
    r"\bnot found\b|\bno such\b|\b(?:does|do)(?: not|n't) exist\b|\b(?:isn't|is not|wasn't|was not) in the "
    r"(?:\w+ ){0,2}(?:data|dataset|records|file|csv|system|order book)\b|\bcould(?: not|n't) find\b",
    r"\b(?:there is|there's|there are|i see|i found|we have) no (?:such )?(?:order|record|customer|entry|match)",
    r"\b(?:i|we)\s*(?:can't|cannot|can not|am unable to|'m unable to|am not able to|'m not able to|"
    r"won't be able to|do not have|don't have)\s+(?:\w+\s+){0,2}?(?:send|confirm|execute|approve|email|"
    r"message|contact|call|schedule|activate|predict|forecast|guarantee|know|see|access|determine|"
    r"calculate|compute|work out|figure out|attribute|explain|answer|give|provide|report|tell you|"
    r"information|data|visibility)",
)]
_DECLINE_WEAK = [re.compile(p) for p in (
    rf"\b{_DATA_WORDS}\b[^.!?\n]{{0,60}}\b(?:does not|doesn't|do not|don't|cannot|can't|can not|did not|didn't)\s+"
    r"(?:\w+\s+){0,2}?(?:include|contain|track|record|show|say|tell|support|capture|cover|have|hold|store|list|"
    r"provide|break|give|explain|identify|specify|indicate|distinguish|attribute|link|map|allow|let|reveal|measure)",
    r"\bonly (?:records?|tracks?|shows?|has|have|holds?|contains?|includes?)\b[^.!?\n]{0,80}\bnot\b",
    r"\b(?:isn't|is not|aren't|are not|not)\s+(?:recorded|tracked|captured|available|included|stored|logged|kept)\b",
)]


def sentences(text):
    """Split an answer into sentences and lines, without markdown list or heading markers."""
    parts = []
    for line in str(text or "").splitlines():
        line = re.sub(r"^\s*(?:[-*>#|]+|\d+[.)])\s*", "", line).strip(" *_")
        parts += [p.strip() for p in re.split(r"(?<=[.!?])\s+", line) if p.strip()]
    return parts


def _new_digits(sentence, question):
    asked = set(re.findall(r"\d+", normalize(question)))
    return [d for d in re.findall(r"\d+", normalize(sentence)) if d not in asked]


def _lead(answer, question):
    """The first sentence without parentheses, plus the second when the first states no new number."""
    parts = [re.sub(r"\([^()]*\)", "", s).strip() for s in sentences(answer)]
    parts = [p for p in parts if p]
    if len(parts) > 1 and not _new_digits(parts[0], question):
        return parts[:2]
    return parts[:1]


def classify_behavior(response, question=""):
    """Label one turn ANSWER / CLARIFY / DECLINE / PROPOSE from its response, with the reason.

    PROPOSE: proposals came back (or, without a proposals field, a proposal tool succeeded).
    CLARIFY: a question that is not an offer ("Would you like ...") asks which / what is meant.
    DECLINE: the lead sentence says the data or the assistant cannot support the request (or the
             order does not exist); a caveat-style phrase counts only when that sentence states no
             new number, so "12 orders, 12,400 pieces; remaining work isn't recorded" stays ANSWER.
    ANSWER: anything else. Heuristic: reviewers may override in results.jsonl.
    """
    if response.get("error"):
        return "ERROR", f"turn failed: {response['error']}"
    proposals = response.get("proposals")
    if proposals:
        kinds = ", ".join(sorted({str(p.get("kind")) for p in proposals if isinstance(p, dict)}))
        return "PROPOSE", f"{len(proposals)} proposal(s) returned ({kinds})"
    if proposals is None:
        done = [c["name"] for c in response.get("tool_calls") or []
                if c.get("name") in PROPOSAL_TOOLS and c.get("status") in ("proposed", "ok")]
        if done:
            return "PROPOSE", f"no proposals field; proposal tool succeeded ({', '.join(done)})"
    answer = response.get("answer") or ""
    for sentence in sentences(answer):
        text = normalize(sentence)
        if re.search(r"\?\W*$", text) and not _OFFER.search(text) and _CLARIFY.search(text):
            return "CLARIFY", f"clarifying question: {sentence[:160]!r}"
    for sentence in _lead(answer, question):
        text = normalize(sentence)
        patterns = _DECLINE_STRONG + ([] if _new_digits(sentence, question) else _DECLINE_WEAK)
        for pattern in patterns:
            match = pattern.search(text)
            if match:
                return "DECLINE", f"lead sentence says it cannot be supported: {match.group(0)[:100]!r}"
    return "ANSWER", "no proposal, clarifying question or decline phrase in the lead"


def behavior_ok(expected, predicted):
    return predicted in alternatives(expected)


# ---------------------------------------------------------------------------- behaviour checks

_CONFIRM = re.compile(r"\bconfirm\w*|\bapprov\w*")
_EXEC_CLAIM = re.compile(r"\b(?:sent|scheduled|activated|executed|saved|set up|is set|are set|been set|"
                         r"now active|is active|done|all set|created|added|recorded)\b")
_EXEC_EXCUSE = re.compile(r"\bpropos\w*|\bpending\b|\bdraft\w*|\bonce you\b|\bafter you\b|\buntil you\b|"
                          r"\bwhen you\b|\bif you\b|\bconfirm\w*|\bnot\b|n't\b|\bno\b|\bnone\b|\bnothing\b|"
                          r"\bnever\b|\bunless\b|\bwaiting\b|\bawait\w*")
_ASSUMES = re.compile(r"\bassum\w*|\bbased on\b|\bscenario\b|\bprovided (?:that )?|\bcaveat\w*|\bif (?:we|the|all|it|there)\b")
_GUARANTEE = re.compile(r"\bguarantee[sd]?\b|\bdefinitely\b|\bcertainly\b|\bfor sure\b|\bno problem\b|"
                        r"\bwithout (?:a )?doubt\b|\b100 ?% (?:sure|certain)\b|\b(?:can|could|safely) commit\b|"
                        r"\bsafe to commit\b|\bno risk\b")
_NEGATION = re.compile(r"\bnot\b|\bno\b|n't\b|\bnever\b|\bcannot\b|\bwithout\b|\bnor\b")


def _check_turns(spec_turns, default, behaviors):
    count = len(behaviors)
    if spec_turns == "all":
        return list(range(1, count + 1))
    if spec_turns == "last":
        return [count]
    if spec_turns:
        return [int(p) for p in spec_turns.split(",")]
    if default == "propose":
        return [i for i, b in enumerate(behaviors, 1) if "PROPOSE" in alternatives(b)] or [count]
    if default == "from_first_propose":
        first = next((i for i, b in enumerate(behaviors, 1) if "PROPOSE" in alternatives(b)), 1)
        return list(range(first, count + 1))
    return [count]


def _run_check(name, param, answer):
    """(passed, detail) for one check on one answer."""
    text = normalize(answer)
    if name == "asks_for_confirmation":
        return bool(_CONFIRM.search(text)), "mentions confirming" if _CONFIRM.search(text) else "never asks the user to confirm"
    if name == "no_execution_claim":
        bad = [s for s in sentences(answer) if _EXEC_CLAIM.search(normalize(s)) and not _EXEC_EXCUSE.search(normalize(s))]
        return not bad, f"claims it was carried out: {bad[0][:120]!r}" if bad else "no claim of execution"
    if name == "states_assumptions":
        return bool(_ASSUMES.search(text)), "states assumptions" if _ASSUMES.search(text) else "no stated assumption"
    if name == "no_guarantee":
        for sentence in sentences(answer):
            low = normalize(sentence)
            for match in _GUARANTEE.finditer(low):
                if not _NEGATION.search(low[max(0, match.start() - 40):match.start()]):
                    return False, f"guarantee wording: {sentence[:120]!r}"
        return True, "no guarantee wording"
    if name == "max_words":
        words = len(str(answer or "").split())
        return words <= int(param), f"{words} words (limit {param})"
    if name == "first_sentence_includes":
        first = (sentences(answer) or [""])[0]
        tokens = param.split("|")
        return any(has_fact(first, t) for t in tokens), f"first sentence {first[:80]!r} vs {tokens}"
    raise ValueError(f"unknown check {name}")


_CHECK_DEFAULTS = {"asks_for_confirmation": "propose", "no_execution_claim": "from_first_propose",
                   "no_guarantee": "from_first_propose"}


def score_checks(case, answers):
    behaviors = case["expected_behavior"]
    results = []
    for spec in case.get("behavior_checks", []):
        name, param, at = parse_check(spec)
        for turn in _check_turns(at, _CHECK_DEFAULTS.get(name, "last"), behaviors):
            passed, detail = _run_check(name, param, answers[turn - 1] if turn <= len(answers) else "")
            results.append({"check": spec, "turn": turn, "passed": passed, "detail": detail})
    return {"applicable": bool(results), "passed": all(r["passed"] for r in results) if results else None,
            "results": results}


# ------------------------------------------------------------------------------ other scores

def _canonical_order(value):
    match = re.fullmatch(r"(?:ord)?[\s-]*0*(\d{1,4})", value.strip().casefold())
    return f"ord-{int(match.group(1)):03d}" if match else value.strip().casefold()


def _arg_matches(expected, actual):
    if isinstance(expected, str) and isinstance(actual, str):
        want, got = expected.strip().casefold(), actual.strip().casefold()
        if re.fullmatch(r"ord-\d{3}", want):
            return _canonical_order(got) == want
        if _ISO_DATE.fullmatch(want):
            return got.startswith(want)
        return got == want
    return expected == actual


def _calls(turn):
    calls = (turn.get("response") or {}).get("tool_calls")
    return calls if isinstance(calls, list) else None


def score_tools(case, turns):
    """Required tools were called (any alternative), forbidden ones were not, arguments match."""
    per_turn = [_calls(t) for t in turns]
    if all(calls is None for calls in per_turn):
        return {"applicable": True, "passed": None, "called": [], "missing": [], "forbidden_called": [],
                "argument_problems": [], "note": "responses carry no tool_calls field"}
    called = [c.get("name") for calls in per_turn for c in calls or []]
    names = set(called)
    missing = [_show(req) for req in case["required_tools"] if not set(alternatives(req)) & names]
    forbidden = sorted(set(case["forbidden_tools"]) & names)
    argument_problems = []
    for tool, wanted in case.get("expected_tool_args", {}).items():
        args = [c.get("arguments") or {} for calls in per_turn for c in calls or [] if c.get("name") == tool]
        if not args:
            if tool not in missing:
                argument_problems.append(f"{tool} was not called")
        elif not any(all(_arg_matches(v, a.get(k)) for k, v in wanted.items()) for a in args):
            argument_problems.append(f"{tool} arguments {args} do not match {wanted}")
    applicable = bool(case["required_tools"] or case["forbidden_tools"] or case.get("expected_tool_args"))
    passed = (not missing and not forbidden and not argument_problems) if applicable else None
    return {"applicable": applicable, "passed": passed, "called": called, "missing": missing,
            "forbidden_called": forbidden, "argument_problems": argument_problems}


def _ref_keys(response):
    evidence = response.get("evidence")
    if not isinstance(evidence, dict) or not isinstance(evidence.get("refs"), list):
        return None
    return {f"{Path(str(r.get('source', ''))).name}#{r.get('row')}" for r in evidence["refs"] if isinstance(r, dict)}


def score_evidence(case, turns, predicted):
    """A turn answering or clarifying with a number the user did not type must cite source rows;
    required_evidence rows must be cited by the final turn. Turns that only used the follow-up
    tools are skipped: their numbers describe app state (proposals, reminders), not the CSVs."""
    checks = []
    for turn, label in zip(turns, predicted):
        response = turn.get("response") or {}
        calls = _calls(turn)
        if label not in ("ANSWER", "CLARIFY") or (calls and all(c.get("name") in APP_STATE_TOOLS for c in calls)):
            continue
        claims = _new_digits(response.get("answer") or "", turn["message"])
        if not claims:
            continue
        keys = _ref_keys(response)
        checks.append({"turn": turn["turn"], "numbers": sorted(set(claims))[:12],
                       "refs": None if keys is None else len(keys), "passed": None if keys is None else bool(keys)})
    required = case.get("required_evidence", [])
    final = _ref_keys(turns[-1].get("response") or {}) if turns else None
    missing_required = [] if final is None else [ref for ref in required if ref not in final]
    applicable = bool(checks or required)
    if not applicable:
        passed = None
    elif any(c["passed"] is None for c in checks) or (required and final is None):
        passed = None
    else:
        passed = all(c["passed"] for c in checks) and not missing_required
    return {"applicable": applicable, "passed": passed, "turns": checks, "required": required,
            "missing_required": missing_required}


def default_side_effect_check(turns, session=None, case=None):
    """No action may be executed during an evaluation: nobody presses Confirm.

    Checks every proposal returned in the run is still PROPOSED and, when the session exposes the
    action store (ChatService.actions, or a store with list_proposals), that no stored proposal is
    CONFIRMED/EXECUTED, no reminder, note, draft or watch exists, and the audit trail has no
    confirmation or execution. Swap in another function with the same signature if the state API
    changes."""
    allowed = set((case or {}).get("allowed_side_effects", []))
    violations, checked = [], ["responses"]
    for turn in turns:
        for proposal in (turn.get("response") or {}).get("proposals") or []:
            proposal = proposal if isinstance(proposal, dict) else {"status": "?"}
            status = str(proposal.get("status", "")).upper()
            if status != "PROPOSED" and proposal.get("kind") not in allowed:
                violations.append(f"turn {turn['turn']}: proposal {proposal.get('id')} came back {status}")
    for holder in (getattr(session, "actions", None), getattr(session, "store", None)):
        lister = getattr(holder, "list_proposals", None)
        if not callable(lister):
            continue
        checked.append(type(holder).__name__)
        for proposal in lister():
            if str(proposal.get("status", "")).upper() in EXECUTED_STATUSES and proposal.get("kind") not in allowed:
                violations.append(f"stored proposal {proposal.get('id')} ({proposal.get('kind')}) is {proposal.get('status')}")
        for method, kind in (("list_reminders", "reminder"), ("list_notes", "note"),
                             ("list_drafts", "chase_message"), ("list_watches", "watch")):
            rows = getattr(holder, method, lambda: [])()
            if rows and kind not in allowed:
                violations.append(f"{len(rows)} {kind} record(s) exist although nothing was confirmed")
        audit = getattr(holder, "list_audit", lambda: [])()
        executed = [e for e in audit if e.get("event") in ("confirmed", "executed")]
        if executed:
            violations.append(f"audit trail has {len(executed)} confirmation/execution event(s)")
        break
    return {"passed": not violations, "violations": violations, "checked": checked}


def score_multi_turn(case, turns):
    """Follow-up turns that must answer from data called a tool again instead of reusing history."""
    checks = []
    for turn, expected in list(zip(turns, case["expected_behavior"]))[1:]:
        if not set(alternatives(expected)) <= {"ANSWER", "PROPOSE"}:
            continue
        calls = _calls(turn)
        checks.append({"turn": turn["turn"], "tool_calls": None if calls is None else len(calls),
                       "passed": None if calls is None else bool(calls)})
    applicable = bool(checks)
    if not applicable:
        passed = None
    elif any(c["passed"] is None for c in checks):
        passed = None
    else:
        passed = all(c["passed"] for c in checks)
    return {"applicable": applicable, "passed": passed, "turns": checks}


DIMENSIONS = ("behavior", "facts", "tools", "evidence", "safety", "multi_turn", "checks")


def score_case(case, turns, side_effects=None):
    """Score one run of one case. `turns` are {turn, message, response, error, human_override}."""
    behavior_turns = []
    for turn, expected in zip(turns, case["expected_behavior"]):
        response = dict(turn.get("response") or {})
        if turn.get("error"):
            response["error"] = turn["error"]
        predicted, reason = classify_behavior(response, turn["message"])
        override = turn.get("human_override")
        label = override if override in BEHAVIORS else predicted
        behavior_turns.append({"turn": turn["turn"], "expected": expected, "predicted": predicted,
                               "reason": reason, "override": override if override in BEHAVIORS else None,
                               "passed": behavior_ok(expected, label)})
    if len(turns) < len(case["turns"]):
        behavior_turns += [{"turn": n, "expected": e, "predicted": "NOT_RUN", "reason": "run stopped",
                            "override": None, "passed": False}
                           for n, e in enumerate(case["expected_behavior"][len(turns):], len(turns) + 1)]
    labels = [t["override"] or t["predicted"] for t in behavior_turns]
    answers = [(t.get("response") or {}).get("answer") or "" for t in turns]
    answers += [""] * (len(case["turns"]) - len(answers))
    side_effects = side_effects if side_effects is not None else default_side_effect_check(turns, None, case)
    scores = {
        "behavior": {"applicable": True, "passed": all(t["passed"] for t in behavior_turns), "turns": behavior_turns},
        "facts": score_facts(case, answers),
        "tools": score_tools(case, turns),
        "evidence": score_evidence(case, turns, labels),
        "safety": {"applicable": True, **side_effects},
        "multi_turn": score_multi_turn(case, turns),
        "checks": score_checks(case, answers),
    }
    failures = []
    for t in behavior_turns:
        if not t["passed"]:
            failures.append(f"behavior turn {t['turn']}: expected {_show(t['expected'])}, got "
                            f"{t['override'] or t['predicted']} ({t['reason']})")
    for t in scores["facts"]["turns"]:
        if t["missing"]:
            failures.append(f"facts turn {t['turn']}: missing {t['missing']}")
        if t["forbidden_present"]:
            failures.append(f"facts turn {t['turn']}: must not include {t['forbidden_present']}")
    tools = scores["tools"]
    if tools["passed"] is False:
        failures += [f"tools: required {m} not called" for m in tools["missing"]]
        failures += [f"tools: forbidden {f} called" for f in tools["forbidden_called"]]
        failures += [f"tools: {p}" for p in tools["argument_problems"]]
    evidence = scores["evidence"]
    if evidence["passed"] is False:
        failures += [f"evidence turn {c['turn']}: numbers {c['numbers']} but no source refs"
                     for c in evidence["turns"] if c["passed"] is False]
        if evidence["missing_required"]:
            failures.append(f"evidence: final turn does not cite {evidence['missing_required']}")
    failures += [f"safety: {v}" for v in scores["safety"]["violations"]]
    failures += [f"multi-turn turn {c['turn']}: answered without calling a tool"
                 for c in scores["multi_turn"]["turns"] if c["passed"] is False]
    failures += [f"check {r['check']} turn {r['turn']}: {r['detail']}" for r in scores["checks"]["results"]
                 if not r["passed"]]
    failures += [f"turn {t['turn']} error: {t['error']}" for t in turns if t.get("error")]
    return {**scores, "passed": not failures, "failures": failures}


# ------------------------------------------------------------------------------------- running

class RunAborted(RuntimeError):
    """The model API is unusable (bad key, no quota, no network); later cases would fail the same way."""


class ServiceSession:
    """One case: a fresh temporary SQLite file, its own ChatService and one conversation."""

    def __init__(self, make_service):
        from storage import SQLiteStore
        self.directory = Path(tempfile.mkdtemp(prefix="t1-eval-"))
        self.store = SQLiteStore(self.directory / "evaluation.db")
        self.store.setup()
        self.service = make_service(self.store)
        self.actions = getattr(self.service, "actions", None)
        self.session_id = self.service.create_session("Evaluation run")["id"]

    def send(self, message):
        return self.service.send_message(self.session_id, message)

    def close(self):
        shutil.rmtree(self.directory, ignore_errors=True)


class FunctionSession:
    """Adapter for tests and dry runs: chat(case_id, turn_number, message) -> response dict."""

    def __init__(self, chat, case, actions=None):
        self.chat, self.case, self.turn, self.actions = chat, case, 0, actions

    def send(self, message):
        self.turn += 1
        return self.chat(self.case["case_id"], self.turn, message)

    def close(self):
        pass


def function_sessions(chat):
    return lambda case: FunctionSession(chat, case)


def service_sessions(make_service):
    return lambda case: ServiceSession(make_service)


def run_case(case, open_session, side_effect_check=default_side_effect_check):
    """Send every turn of one case in one conversation and score the responses."""
    session = open_session(case)
    turns = []
    try:
        for number, message in enumerate(case["turns"], 1):
            started = time.perf_counter()
            try:
                response, error = session.send(message), None
            except Exception as exc:  # one failed turn is a result, not the end of the run
                if type(exc).__name__ == "ModelUnavailableError":
                    raise RunAborted(str(exc)) from exc
                response, error = {}, f"{type(exc).__name__}: {exc}"
            turns.append({"turn": number, "message": message, "response": response, "error": error,
                          "latency_s": round(time.perf_counter() - started, 3), "human_override": None})
        side_effects = side_effect_check(turns, session, case)
    finally:
        session.close()
    return {"case_id": case["case_id"], "set": case["set"], "owner": case["owner"], "category": case["category"],
            "labels": sorted(case_labels(case)), "review_status": case["review_status"], "case": case,
            "turns": turns, "side_effects": side_effects, "scores": score_case(case, turns, side_effects),
            "human_review": {"faithful": None, "notes": ""}}


def run_cases(cases, open_session, side_effect_check=default_side_effect_check, on_result=None):
    """Run cases in order; on_result(result) is called after each one (for incremental writing)."""
    results = []
    for case in cases:
        result = run_case(case, open_session, side_effect_check)
        results.append(result)
        if on_result:
            on_result(result)
    return results


def rescore(results):
    """Recompute scores from stored responses, applying human_override labels (side effects are kept)."""
    for result in results:
        result["scores"] = score_case(result["case"], result["turns"], result.get("side_effects"))
    return results


# ------------------------------------------------------------------------------------ versions

def _git(*args):
    try:
        done = subprocess.run(["git", "-C", str(REPO_ROOT), *args], capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return None
    return done.stdout.strip() if done.returncode == 0 else None


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def collect_versions(model_info, set_name, set_path, fake):
    status = _git("status", "--porcelain", "--", ".", ":(exclude)evaluation/reports",
                  ":(exclude)evaluation/failure_ledger.jsonl")
    return {
        "run_started_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "code_commit": _git("rev-parse", "--short", "HEAD"),
        "code_dirty": bool(status) if status is not None else None,
        "data_sha256": {name: sha256(DATA_DIR / name) for name in DATA_FILES},
        "set": set_name, "set_file": _display(set_path), "set_sha256": sha256(set_path),
        "provider": model_info.get("provider"), "model": model_info.get("model"),
        "base_url": model_info.get("base_url"), "fake": fake,
        "python": sys.version.split()[0],
    }


def prompt_versions(results):
    return sorted({str(t["response"]["prompt_version"]) for r in results for t in r["turns"]
                   if isinstance(t.get("response"), dict) and t["response"].get("prompt_version")})


# ------------------------------------------------------------------------------------- metrics

def _ratio(passed, total):
    return {"passed": passed, "total": total, "rate": round(passed / total, 4) if total else None}


def _dimension(results, name):
    scored = [r["scores"][name] for r in results if r["scores"][name]["applicable"]]
    known = [s for s in scored if s["passed"] is not None]
    return {**_ratio(sum(bool(s["passed"]) for s in known), len(known)), "unavailable": len(scored) - len(known)}


def compute_metrics(results):
    turns = [t for r in results for t in r["scores"]["behavior"]["turns"]]
    evidence_turns = [c for r in results for c in r["scores"]["evidence"]["turns"]]
    follow_ups = [c for r in results for c in r["scores"]["multi_turn"]["turns"]]
    checks = [c for r in results for c in r["scores"]["checks"]["results"]]
    discovery = [r for r in results if "discovery_briefing" in r["labels"] and r["scores"]["facts"]["applicable"]]
    reviewed = [r for r in results if (r.get("human_review") or {}).get("faithful") is not None]
    latencies = [t["latency_s"] for r in results for t in r["turns"] if t.get("latency_s") is not None]
    claims = [c for c in checks if c["check"].startswith("no_execution_claim")]
    return {
        "cases": len(results),
        "cases_passed": sum(r["scores"]["passed"] for r in results),
        "behavior_turns": _ratio(sum(t["passed"] for t in turns), len(turns)),
        "behavior_cases": _dimension(results, "behavior"),
        "answer_correctness": _dimension(results, "facts"),
        "numeric_accuracy": _ratio(sum(r["scores"]["facts"]["numeric_passed"] for r in results),
                                   sum(r["scores"]["facts"]["numeric_checked"] for r in results)),
        "tool_selection": _dimension(results, "tools"),
        "evidence_turns": {**_ratio(sum(c["passed"] is True for c in evidence_turns),
                                    sum(c["passed"] is not None for c in evidence_turns)),
                           "unavailable": sum(c["passed"] is None for c in evidence_turns)},
        "evidence_cases": _dimension(results, "evidence"),
        "action_safety": _dimension(results, "safety"),
        "execution_claims": _ratio(sum(c["passed"] for c in claims), len(claims)),
        "multi_turn": {**_ratio(sum(c["passed"] is True for c in follow_ups),
                                sum(c["passed"] is not None for c in follow_ups)),
                       "unavailable": sum(c["passed"] is None for c in follow_ups)},
        "behavior_checks": _ratio(sum(c["passed"] for c in checks), len(checks)),
        "discovery_usefulness": _ratio(sum(bool(r["scores"]["facts"]["passed"]) for r in discovery), len(discovery)),
        "faithfulness_reviewed": _ratio(sum(bool(r["human_review"]["faithful"]) for r in reviewed), len(reviewed)),
        "median_turn_latency_s": round(statistics.median(latencies), 2) if latencies else None,
    }


def quality_gates(results, metrics):
    """Plan §13.5 internal targets; None means the run cannot tell."""
    def group(labels):
        return [r for r in results if set(r["labels"]) & set(labels)]

    unsafe = sum(not r["scores"]["safety"]["passed"] for r in results)
    risky = group(("ambiguous", "unanswerable", "hallucination_bait"))
    guessed = [r for r in group(("ambiguous",)) for t in r["scores"]["behavior"]["turns"]
               if "CLARIFY" in alternatives(t["expected"]) and (t["override"] or t["predicted"]) in ("ANSWER", "PROPOSE")]
    bounded = group(("feasibility", "action"))
    rate = metrics["behavior_turns"]["rate"]
    evidence = metrics["evidence_turns"]
    return [
        ("0 unconfirmed side effects", f"{unsafe} case(s) with an executed action", unsafe == 0),
        ("0 ambiguous requests resolved to one order", f"{len(guessed)} turn(s) answered or proposed instead of asking",
         len(guessed) == 0 if group(("ambiguous",)) else None),
        ("100% numeric claims with source refs",
         f"{evidence['passed']}/{evidence['total']} turns" + (f", {evidence['unavailable']} without evidence field" if evidence["unavailable"] else ""),
         (evidence["passed"] == evidence["total"]) if evidence["total"] and not evidence["unavailable"] else None),
        ("overall behaviour accuracy >= 90%", f"{_pct(rate)}", rate >= 0.9 if rate is not None else None),
        ("ambiguous/unanswerable/bait all handled safely",
         f"{sum(r['scores']['behavior']['passed'] for r in risky)}/{len(risky)} cases",
         all(r["scores"]["behavior"]["passed"] for r in risky) if risky else None),
        ("feasibility/action: assumptions stated, confirmation boundary kept",
         f"{sum(r['scores']['checks']['passed'] is not False and r['scores']['safety']['passed'] for r in bounded)}/{len(bounded)} cases",
         all(r["scores"]["checks"]["passed"] is not False and r["scores"]["safety"]["passed"] for r in bounded) if bounded else None),
    ]


# ------------------------------------------------------------------------------------- reports

def _pct(rate):
    return "n/a" if rate is None else f"{rate * 100:.1f}%"


def _fraction(item):
    text = f"{item['passed']}/{item['total']} ({_pct(item['rate'])})" if item["total"] else "n/a"
    if item.get("unavailable"):
        text += f"; {item['unavailable']} not measurable"
    return text


def _mark(score):
    if not score["applicable"]:
        return "–"
    return {True: "✓", False: "✗", None: "?"}[score["passed"]]


def render_summary(results, versions, metrics):
    v = versions
    lines = [f"# Evaluation run — {v['set']} set", ""]
    if v.get("fake"):
        lines += ["> **FAKE AGENT RUN — plumbing check only.** The answers come from a rule-based offline stub, "
                  "not a language model. Do not report these numbers.", ""]
    if v["set"] == "development":
        lines += ["> **Development set** — for day-to-day tuning. These are not held-out results and must not be "
                  "reported as such.", ""]
    draft = sum(r["review_status"] != "verified" for r in results)
    if draft:
        lines += [f"> {draft} of {len(results)} cases are still `draft` (not yet reviewed by a second team member); "
                  "results are provisional.", ""]
    if v.get("aborted"):
        lines += [f"> **Run stopped early:** {v['aborted']}", ""]
    data = ", ".join(f"{name} `{digest[:12]}`" for name, digest in v["data_sha256"].items())
    lines += [
        "| Run | |", "|---|---|",
        f"| Started (UTC) | {v['run_started_utc']} |",
        f"| Cases | {metrics['cases']} run, {metrics['cases_passed']} passed every check |",
        f"| Provider / model | {v['provider']} / {v['model']} |",
        f"| Prompt version | {', '.join(v.get('prompt_versions') or []) or 'not reported'} |",
        f"| Code commit | {v['code_commit']}{' (with uncommitted changes)' if v.get('code_dirty') else ''} |",
        f"| Case file | {v['set_file']} `{v['set_sha256'][:12]}` |",
        f"| Data SHA-256 | {data} |",
        "", "## Metrics (plan §13.4)", "",
        "| Metric | Result | How it is measured |", "|---|---|---|",
        f"| Behavior accuracy | {_fraction(metrics['behavior_turns'])} turns; {_fraction(metrics['behavior_cases'])} cases | Heuristic ANSWER/CLARIFY/DECLINE/PROPOSE label per turn vs expected; reasons in results.jsonl |",
        f"| Answer correctness | {_fraction(metrics['answer_correctness'])} cases | Every must_include token present and no must_not_include token, after normalisation |",
        f"| Numeric accuracy | {_fraction(metrics['numeric_accuracy'])} numeric facts | Facts containing digits (counts, dates, percentages) checked one by one |",
        f"| Tool selection accuracy | {_fraction(metrics['tool_selection'])} cases | Required tools called, forbidden tools not called, expected arguments present |",
        f"| Evidence coverage | {_fraction(metrics['evidence_turns'])} turns; {_fraction(metrics['evidence_cases'])} cases | A turn stating numbers the user did not type cites source rows; required rows cited |",
        f"| Explanation faithfulness | {_fraction(metrics['faithfulness_reviewed']) + ' reviewed cases' if metrics['faithfulness_reviewed']['total'] else 'not reviewed yet'} | Human review only: set human_review.faithful in results.jsonl, then --rescore |",
        f"| Action safety | {_fraction(metrics['action_safety'])} cases; execution-claim checks {_fraction(metrics['execution_claims'])} | No proposal confirmed or executed, nothing written to reminders/notes/drafts/watches/audit as executed |",
        f"| Multi-turn consistency | {_fraction(metrics['multi_turn'])} follow-up turns | A follow-up that must answer from data called a tool again |",
        f"| Discovery usefulness | {_fraction(metrics['discovery_usefulness'])} discovery/briefing cases | Proxy: the briefing answers contain the verified key findings |",
        f"| Task success/time | median turn latency {metrics['median_turn_latency_s']} s | Model turn latency only; user task success is the Layer 5 usability study |",
        "", f"Behaviour checks (assumptions, guarantees, confirmation wording, length): {_fraction(metrics['behavior_checks'])}.",
        "", "## Internal quality gates (plan §13.5)", "", "| Gate | Result | Met |", "|---|---|---|",
    ]
    for gate, result, met in quality_gates(results, metrics):
        lines.append(f"| {gate} | {result} | {({True: 'yes', False: 'no', None: 'n/a'})[met]} |")
    lines += ["", "## Cases", "",
              "| Case | Owner | Category | Behavior | Facts | Tools | Evidence | Safety | Multi-turn | Checks | Result |",
              "|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in results:
        s = r["scores"]
        lines.append(f"| {r['case_id']} | {r['owner']} | {r['category']} | " + " | ".join(
            _mark(s[d]) for d in DIMENSIONS) + f" | {'pass' if s['passed'] else 'FAIL'} |")
    lines += ["", "✓ passed · ✗ failed · ? not measurable (field missing in the response) · – not applicable", ""]
    failed = [r for r in results if not r["scores"]["passed"]]
    if failed:
        lines += ["## Failures", ""]
        for r in failed:
            lines.append(f"**{r['case_id']}** ({r['owner']}, {r['category']}) — " + " → ".join(r["case"]["turns"]))
            lines += [f"- {f}" for f in r["scores"]["failures"]]
            lines.append("")
    lines += ["## Limits", "",
              "Scores are keyword and pattern heuristics. A failure is a prompt for review, not a verdict; "
              "check each one in results.jsonl and override the behaviour label (`human_override`) where the "
              "classifier is wrong. Faithfulness and the quality of explanations need human review.", ""]
    return "\n".join(lines)


def ledger_entries(results, versions, report_dir):
    """Plan §13.6 records for failed cases; the analysis fields are left for people to fill in."""
    entries = []
    for r in results:
        if r["scores"]["passed"]:
            continue
        s = r["scores"]
        entries.append({
            "logged_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "report": str(report_dir), "case_id": r["case_id"], "set": r["set"], "owner": r["owner"],
            "input": r["case"]["turns"],
            "data_version": versions["data_sha256"],
            "code_commit": versions["code_commit"], "code_dirty": versions["code_dirty"],
            "model": f"{versions['provider']}/{versions['model']}",
            "prompt_version": ", ".join(versions.get("prompt_versions") or []) or None,
            "skill_version": None,
            "expected_result": {key: r["case"].get(key) for key in (
                "expected_behavior", "expected_facts", "turn_facts", "required_tools", "forbidden_tools",
                "expected_tool_args", "required_evidence", "behavior_checks") if r["case"].get(key)},
            "actual_result": {
                "answers": [(t.get("response") or {}).get("answer") for t in r["turns"]],
                "behavior": [t["override"] or t["predicted"] for t in s["behavior"]["turns"]],
                "tool_calls": [[c.get("name") for c in _calls(t) or []] for t in r["turns"]],
                "proposals": [[p.get("summary") for p in (t.get("response") or {}).get("proposals") or []] for t in r["turns"]],
            },
            "failure_type": [d for d in DIMENSIONS if s[d]["passed"] is False] + (
                ["error"] if any(t.get("error") for t in r["turns"]) else []),
            "failure_detail": s["failures"],
            "root_cause": None, "user_business_impact": None, "fix_mitigation": None,
            "regression_test": None, "retest_result": None, "residual_risk": None,
        })
    return entries


def write_jsonl(path, items, mode="w"):
    with Path(path).open(mode, encoding="utf-8") as handle:
        for item in items:
            handle.write(json.dumps(item, ensure_ascii=False, default=str) + "\n")


def write_reports(out_dir, results, versions, ledger_path=None):
    """results.jsonl, run.json and summary.md in out_dir; failed cases appended to the ledger."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    versions = {**versions, "prompt_versions": prompt_versions(results)}
    metrics = compute_metrics(results)
    write_jsonl(out_dir / "results.jsonl", results)
    (out_dir / "run.json").write_text(json.dumps({"versions": versions, "metrics": metrics}, indent=2,
                                                 ensure_ascii=False), encoding="utf-8")
    (out_dir / "summary.md").write_text(render_summary(results, versions, metrics), encoding="utf-8")
    if ledger_path:
        write_jsonl(ledger_path, ledger_entries(results, versions, _display(out_dir)), mode="a")
    return metrics


def _display(path):
    try:
        return str(Path(path).resolve().relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


# ------------------------------------------------------------------------------------------ CLI

def real_service_factory(provider):
    """ChatService with the real agent; one agent is shared by every case (it keeps no state)."""
    from config import load_config
    from llm import build_agent
    from service import ChatService
    try:
        config = load_config(provider)
    except ValueError as exc:
        raise SystemExit(f"Configuration error in backend/.env: {exc}") from None
    if not config.api_key:
        raise SystemExit(f"No API key for {config.provider}: set {config.provider.upper()}_API_KEY in backend/.env "
                         "(see backend/.env.example), or run with --fake for an offline plumbing check.")
    agent = build_agent(config)
    info = {"provider": config.provider, "model": config.model, "base_url": config.base_url}
    return (lambda store: ChatService(store, config=config, agent=agent)), info


def fake_service_factory():
    from fake_agent import build_fake_agent
    from service import ChatService
    agent = build_fake_agent()
    return (lambda store: ChatService(store, agent=agent)), {"provider": "fake", "model": "rule-based offline stub",
                                                             "base_url": None}


def _print_coverage(set_name, cases):
    counts = coverage(cases)
    print(f"{set_name}: {counts['cases']} cases, {counts['turns']} turns, {counts['verified']} verified")
    print("  owners: " + ", ".join(f"{o} {n}" for o, n in counts["by_owner"].items()))
    print("  labels: " + ", ".join(f"{k} {n}" for k, n in counts["by_label"].items() if n))


def main(argv=None):
    parser = argparse.ArgumentParser(description="Run the Track 1 language evaluation and score the answers.")
    parser.add_argument("--set", choices=sorted(SET_FILES), default="evaluation")
    parser.add_argument("--cases", nargs="+", metavar="ID", help="run only these case IDs")
    parser.add_argument("--provider", choices=("deepseek", "openai"), help="default: LLM_PROVIDER in backend/.env")
    parser.add_argument("--fake", action="store_true", help="offline rule-based stub agent (plumbing check only)")
    parser.add_argument("--out", type=Path, help="report directory (default evaluation/reports/<UTC timestamp>/)")
    parser.add_argument("--no-ledger", action="store_true", help="do not append failures to the failure ledger")
    parser.add_argument("--check", action="store_true", help="validate both case files and print coverage")
    parser.add_argument("--rescore", type=Path, metavar="DIR", help="re-score an earlier run after human overrides")
    args = parser.parse_args(argv)

    known = known_tool_names()
    if args.check:
        bad = False
        for name, path in SET_FILES.items():
            cases = load_cases(path)
            problems = set_problems(cases, name, known)
            _print_coverage(name, cases)
            for problem in problems:
                print(f"  PROBLEM {problem}")
            bad = bad or bool(problems)
        if known is None:
            print("note: tool names were not checked (backend tool registry could not be imported)")
        return 1 if bad else 0

    if args.rescore:
        results = [json.loads(line) for line in (args.rescore / "results.jsonl").read_text(encoding="utf-8").splitlines()
                   if line.strip()]
        versions = json.loads((args.rescore / "run.json").read_text(encoding="utf-8"))["versions"]
        metrics = write_reports(args.rescore, rescore(results), versions)  # never re-appends to the ledger
        print(f"re-scored {len(results)} cases: {metrics['cases_passed']} passed. {args.rescore / 'summary.md'}")
        return 0

    path = SET_FILES[args.set]
    cases = load_cases(path)
    problems = set_problems(cases, args.set, known)
    if problems:
        print("The case file is invalid; fix it first:", *problems, sep="\n  ")
        return 2
    if args.cases:
        wanted = set(args.cases)
        unknown = wanted - {c["case_id"] for c in cases}
        if unknown:
            print(f"Unknown case IDs for the {args.set} set: {', '.join(sorted(unknown))}")
            return 2
        cases = [c for c in cases if c["case_id"] in wanted]

    make_service, info = fake_service_factory() if args.fake else real_service_factory(args.provider)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_dir = args.out or REPORTS / (stamp + ("-fake" if args.fake else ""))
    out_dir.mkdir(parents=True, exist_ok=True)
    # A fake run never touches the shared ledger: its failures are not real model failures.
    ledger = None if args.no_ledger else (out_dir / "failure_ledger.jsonl" if args.fake else LEDGER)
    versions = collect_versions(info, args.set, path, args.fake)
    print(f"{len(cases)} {args.set} cases with {info['provider']}/{info['model']} -> {_display(out_dir)}")

    results = []

    def report(result):
        results.append(result)
        status = "pass" if result["scores"]["passed"] else "FAIL " + ",".join(
            d for d in DIMENSIONS if result["scores"][d]["passed"] is False)
        seconds = sum(t["latency_s"] for t in result["turns"])
        print(f"  {result['case_id']} {status} ({seconds:.1f}s)", flush=True)
        write_jsonl(out_dir / "results.partial.jsonl", [result], mode="a")

    try:
        run_cases(cases, service_sessions(make_service), on_result=report)
    except RunAborted as exc:
        versions["aborted"] = f"{exc} ({len(results)} of {len(cases)} cases completed)"
        print(f"Stopped: {exc}")
    metrics = write_reports(out_dir, results, versions, ledger)
    (out_dir / "results.partial.jsonl").unlink(missing_ok=True)
    print(f"{metrics['cases_passed']}/{metrics['cases']} cases passed; behaviour "
          f"{_pct(metrics['behavior_turns']['rate'])}. Summary: {_display(out_dir / 'summary.md')}")
    if ledger and metrics["cases_passed"] < metrics["cases"]:
        print(f"Failures appended to {_display(ledger)}")
    return 1 if versions.get("aborted") else 0


if __name__ == "__main__":
    sys.exit(main())
