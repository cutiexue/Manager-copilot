"""Check an answer against the tool results it was written from (deterministic, no model call).

Every order ID, date and figure the model writes should come from this turn's tool results (or the
manager's own message). This module pulls them out of the answer and looks each one up; what it
cannot find is reported as unverified, so the app can mark it and the evaluation can count it.

Matching is forgiving about form, never about value: 18,326 = 18326, 11.8 matches 11.77 (rounded to
the answer's precision), 9% matches a rate of 0.09, a fall of 11.8% matches -11.77, and "31 Mar" or
"March 31" matches 2026-03-31. Small counts (0 to 10), years and times of day are not checked: they
are too common in ordinary wording to be told apart from figures.
"""

import re
from datetime import date

ORDER = re.compile(r"\bORD[- ]?(\d{1,3})\b", re.IGNORECASE)
ISO_DATE = re.compile(r"\b(20\d\d)-(\d\d)-(\d\d)\b")
MONTHS = {m: i for i, m in enumerate(("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct",
                                       "nov", "dec"), 1)}
_MONTH = r"(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?"
DAY_MONTH = re.compile(r"\b(\d{1,2})(?:st|nd|rd|th)? " + _MONTH + r"(?: (20\d\d))?", re.IGNORECASE)
MONTH_DAY = re.compile(r"\b" + _MONTH + r" (\d{1,2})(?:st|nd|rd|th)?\b(?:,? (20\d\d))?", re.IGNORECASE)
# Day ranges: "27–31 March" or "March 27-31" name two dates.
DAY_RANGE = re.compile(r"\b(\d{1,2})\s*[–-]\s*(\d{1,2}) " + _MONTH, re.IGNORECASE)
RANGE_DAY = re.compile(r"\b" + _MONTH + r" (\d{1,2})\s*[–-]\s*(\d{1,2})\b", re.IGNORECASE)
TIME = re.compile(r"\b\d{1,2}:\d{2}\b")
LIST_MARKER = re.compile(r"(?m)^\s*\d+[.)]\s")
NUMBER = re.compile(r"(?<![\w.])-?\d{1,3}(?:,\d{3})+(?:\.\d+)?%?|(?<![\w.])-?\d+(?:\.\d+)?%?")
YEAR = 2026


def _order_id(digits):
    return f"ORD-{int(digits):03d}"


def _dates_in(text):
    found = {f"{y}-{m}-{d}" for y, m, d in ISO_DATE.findall(text)}
    for first, last, month in DAY_RANGE.findall(text):
        found |= {_iso(YEAR, MONTHS[month[:3].lower()], int(first)), _iso(YEAR, MONTHS[month[:3].lower()], int(last))}
    for month, first, last in RANGE_DAY.findall(text):
        found |= {_iso(YEAR, MONTHS[month[:3].lower()], int(first)), _iso(YEAR, MONTHS[month[:3].lower()], int(last))}
    for day, month, year in DAY_MONTH.findall(text):
        found.add(_iso(int(year or YEAR), MONTHS[month[:3].lower()], int(day)))
    for month, day, year in MONTH_DAY.findall(text):
        found.add(_iso(int(year or YEAR), MONTHS[month[:3].lower()], int(day)))
    found.discard(None)
    return found


def _iso(year, month, day):
    try:
        return date(year, month, day).isoformat()
    except ValueError:
        return None


def _strip_known(text):
    """Remove the parts that are not figures: order IDs, dates, times and list numbering."""
    for pattern in (ORDER, ISO_DATE, DAY_RANGE, RANGE_DAY, DAY_MONTH, MONTH_DAY, TIME, LIST_MARKER):
        text = pattern.sub(" ", text)
    return text


def _numbers_in(text):
    values = []
    for token in NUMBER.findall(_strip_known(text)):
        percent = token.endswith("%")
        raw = token.rstrip("%").replace(",", "")
        decimals = len(raw.split(".")[1]) if "." in raw else 0
        values.append((token, float(raw), decimals, percent))
    return values


class _Known:
    """Everything the tool results (and the manager's message) state."""

    def __init__(self, sources):
        self.orders, self.dates, self.numbers = set(), set(), []
        for source in sources:
            self._walk(source)

    def _walk(self, value):
        if isinstance(value, dict):
            for item in value.values():
                self._walk(item)
        elif isinstance(value, (list, tuple)):
            for item in value:
                self._walk(item)
        elif isinstance(value, bool) or value is None:
            return
        elif isinstance(value, (int, float)):
            self.numbers.append(float(value))
        elif isinstance(value, str):
            self.orders.update(_order_id(d) for d in ORDER.findall(value))
            self.dates.update(_dates_in(value))
            self.numbers.extend(number for _, number, _, _ in _numbers_in(value))

    def has_number(self, value, decimals, percent):
        targets = {abs(value)} | ({abs(value) / 100} if percent else set())
        for known in self.numbers:
            for target in targets:
                # Within half a unit of the answer's last digit: 704.8 and 704.9 both round 704.85.
                places = decimals + (2 if target != abs(value) else 0)
                if abs(abs(known) - target) <= 0.5 * 10 ** -places + 1e-9:
                    return True
        return False


def check(answer, tool_results, question="", today=None, earlier_results=()):
    """{checked, unverified: [{kind, text}]} for one answer and the tool results of its turn.

    earlier_results: tool results from earlier turns of the conversation. They vouch for order IDs only
    (naming an order looked up before is fine); figures must come from this turn's lookups."""
    known = _Known([*tool_results, question, today or ""])
    known.orders |= _Known(earlier_results).orders
    unverified, checked = [], 0
    for digits in sorted(set(ORDER.findall(answer))):
        checked += 1
        if _order_id(digits) not in known.orders:
            unverified.append({"kind": "order", "text": _order_id(digits)})
    for day in sorted(_dates_in(answer)):
        checked += 1
        if day not in known.dates:
            unverified.append({"kind": "date", "text": day})
    seen = set()
    for token, value, decimals, percent in _numbers_in(answer):
        year = re.fullmatch(r"20\d\d", token) is not None  # "2026", but not "2,000"
        if token in seen or (not percent and decimals == 0 and (0 <= value <= 10 or year)):
            continue
        seen.add(token)
        checked += 1
        if not known.has_number(value, decimals, percent):
            unverified.append({"kind": "number", "text": token})
    return {"checked": checked, "unverified": unverified}
