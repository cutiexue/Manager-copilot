"""Check an answer against the tool results it was written from (deterministic, no model call).

Every order ID, date and figure the model writes should come from this turn's tool results (or the
manager's own message). This module pulls them out of the answer and looks each one up; what it
cannot find is reported as unverified, so the app can mark it and the evaluation can count it.

Matching is forgiving about form, never about value: 18,326 = 18326, 11.8 matches 11.77 (rounded to
the answer's precision), 9% matches a rate of 0.09, a fall of 11.8% matches -11.77, and "31 Mar" or
"March 31" matches 2026-03-31. Small counts (0 to 10), years and times of day are not checked: they
are too common in ordinary wording to be told apart from figures.

Boundaries are ASCII-only, so figures inside Chinese text ("共有12个订单") are found too. A source row
number vouches only for a figure cited as a row or line ("row 88", "第88行"), never for a count.
This is a value-matching heuristic, not a check that each figure describes the correct entity.
"""

import re
from datetime import date

# Not preceded or followed by an ASCII letter or digit. Python's \b and \w treat CJK characters as
# word characters, which would hide "12" in "共有12个".
_START, _END = r"(?<![A-Za-z0-9_])", r"(?![A-Za-z0-9_])"
ORDER = re.compile(_START + r"ORD[- ]?(\d{1,3})(?!\d)", re.IGNORECASE)
ISO_DATE = re.compile(_START + r"(20\d\d)-(\d\d)-(\d\d)(?!\d)")
MONTHS = {m: i for i, m in enumerate(("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct",
                                       "nov", "dec"), 1)}
# Whole month names and their usual abbreviations only, so "decreased", "marked" or "separate" are not
# months. Lower-case "may" is the verb ("12 may need a call"); only "May" names the month.
_MONTH = (r"(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|(?-i:May|MAY)|june?|july?|aug(?:ust)?"
          r"|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\.?(?![a-z])")
DAY_MONTH = re.compile(_START + r"(\d{1,2})(?:st|nd|rd|th)? " + _MONTH + r"(?: (20\d\d))?", re.IGNORECASE)
MONTH_DAY = re.compile(_START + _MONTH + r" (\d{1,2})(?:st|nd|rd|th)?(?!\d)(?:,? (20\d\d))?", re.IGNORECASE)
# Day ranges: "27–31 March" or "March 27-31" name two dates.
DAY_RANGE = re.compile(_START + r"(\d{1,2})\s*[–-]\s*(\d{1,2}) " + _MONTH, re.IGNORECASE)
RANGE_DAY = re.compile(_START + _MONTH + r" (\d{1,2})\s*[–-]\s*(\d{1,2})(?!\d)", re.IGNORECASE)
TIME = re.compile(_START + r"\d{1,2}:\d{2}" + _END)
LIST_MARKER = re.compile(r"(?m)^\s*\d+[.)]\s")
NUMBER = re.compile(r"(?<![A-Za-z0-9_.])-?\d{1,3}(?:,\d{3})+(?:\.\d+)?%?|(?<![A-Za-z0-9_.])-?\d+(?:\.\d+)?%?")
# A figure the answer cites as a source row or file line.
ROW_CITATION = re.compile(
    r"\b(?:rows?|lines?)\s*(?:#|no\.?|number)?\s*(\d+)"
    r"|(?<![A-Za-z0-9_])#\s*(\d+)"
    r"|第\s*(\d+)\s*行",
    re.IGNORECASE,
)
# Keys whose values are citations (file line numbers and evidence IDs), not facts.
_CITATION_KEYS = {"row", "source_row", "id", "row_key"}
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
    """Mask non-figures without moving the original text spans."""
    for pattern in (ORDER, ISO_DATE, DAY_RANGE, RANGE_DAY, DAY_MONTH, MONTH_DAY, TIME, LIST_MARKER):
        text = pattern.sub(lambda match: " " * len(match.group()), text)
    return text


def _number_mentions(text):
    for match in NUMBER.finditer(_strip_known(text)):
        token = match.group()
        percent = token.endswith("%")
        raw = token.rstrip("%").replace(",", "")
        decimals = len(raw.split(".")[1]) if "." in raw else 0
        yield token, float(raw), decimals, percent, match.span()


def _numbers_in(text):
    return [mention[:4] for mention in _number_mentions(text)]


class _Known:
    """Everything the tool results (and the manager's message) state."""

    def __init__(self, sources):
        self.orders, self.dates, self.numbers, self.rows = set(), set(), [], set()
        for source in sources:
            self._walk(source)

    def _walk(self, value):
        if isinstance(value, dict):
            for key, item in value.items():
                if key in _CITATION_KEYS:
                    if key in ("row", "source_row") and isinstance(item, int) and not isinstance(item, bool):
                        self.rows.add(item)
                    continue
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
    row_citations = {
        match.span(group)
        for match in ROW_CITATION.finditer(answer)
        for group in range(1, ROW_CITATION.groups + 1)
        if match.group(group) is not None
    }
    for token, value, decimals, percent, span in _number_mentions(answer):
        year = re.fullmatch(r"20[23]\d", token) is not None  # "2026", but not "2,000" or "2000" pieces
        cited_row = span in row_citations and value in known.rows
        # A verified row citation must not suppress a separate business figure of the same value.
        seen_key = (token, cited_row)
        if seen_key in seen or (not percent and decimals == 0 and (0 <= value <= 10 or year)):
            continue
        seen.add(seen_key)
        checked += 1
        if not cited_row and not known.has_number(value, decimals, percent):
            unverified.append({"kind": "number", "text": token})
    return {"checked": checked, "unverified": unverified}
