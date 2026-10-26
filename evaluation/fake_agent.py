"""Offline stand-in for the language model, used by `run_evaluation.py --fake`.

It routes each message to the real backend tools with keyword rules and writes a templated
answer from their results, so a fake run exercises the whole path offline: ChatService, the
LangChain agent loop, tool argument validation, evidence refs, proposals, the side-effect check
and the reports. It is deliberately simple. It is not a baseline, and its scores mean nothing.
"""

import json
import re
from datetime import date, timedelta
from uuid import uuid4

from langchain.agents import create_agent
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from data_loader import load_orders
from llm import SYSTEM_PROMPT, build_tools

TODAY = date(2026, 4, 1)
STAGES = ("KNITTING", "ASSEMBLY", "WASHING", "PACKING")
MONTHS = ("january", "february", "march", "april", "may", "june", "july", "august", "september",
          "october", "november", "december")
WEEKDAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
NUMBER_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "ten": 10}
PRODUCTS = ("hoodie", "beanie", "scarf", "vest", "cardigan", "polo", "crewneck", "sweater")
PROPOSE_TOOL = {"note": "propose_order_note", "chase": "draft_chase_message", "reminder": "propose_reminder",
                "watch": "propose_watch"}
DECLINE_TEXT = ("The data does not record that: the course data has no prices, revenue, worker names or "
                "per-order progress, only each order's current stage and factory-wide daily output.")
SEND_TEXT = ("I can't send messages. The draft stays pending until you confirm it in the app, and even then "
             "it is kept as a draft, never sent automatically.")


def _available(name):
    from tool_schemas import TOOL_FUNCTIONS
    return name in TOOL_FUNCTIONS


def _text(content):
    if isinstance(content, list):
        return "".join(block.get("text", "") for block in content if isinstance(block, dict))
    return str(content or "")


def _json(content):
    try:
        value = json.loads(_text(content))
    except ValueError:
        return {}
    return value if isinstance(value, dict) else {}


def _ids(text):
    return list(dict.fromkeys(f"ORD-{int(n):03d}" for n in re.findall(r"\bord[\s-]?0*(\d{1,3})\b", text, re.I)))


def _customers():
    return sorted({order["customer"] for order in load_orders()}, key=len, reverse=True)


def _customer(text):
    low = text.casefold()
    for name in _customers():
        first = name.split()[0].casefold()
        if name.casefold() in low or (len(first) >= 4 and re.search(rf"\b{re.escape(first)}\b", low)):
            return name
    return None


def _product(q):
    return next((p for p in PRODUCTS if p in q), None)


def _iso(day, month_name):
    return date(TODAY.year, MONTHS.index(month_name) + 1, int(day)).isoformat()


def _day_mention(q):
    """'yesterday', '30 march' or 'monday 30 march' as an ISO date, else None."""
    if "yesterday" in q:
        return (TODAY - timedelta(days=1)).isoformat()
    match = re.search(rf"\b(\d{{1,2}})(?:st|nd|rd|th)? ({'|'.join(MONTHS)})\b", q)
    return _iso(*match.groups()) if match else None


def _weekday_date(q):
    """A weekday name in the dataset calendar (today is Wednesday 2026-04-01)."""
    for index, name in enumerate(WEEKDAYS):
        if name in q:
            return (TODAY + timedelta(days=(index - TODAY.weekday()) % 7 or 7)).isoformat()
    return None


def _when(question):
    q = question.casefold()
    day = next((w for w in WEEKDAYS if w in q), "tomorrow")
    match = re.search(r"\b(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b", q)
    return f"{day} {match[1]}{':' + match[2] if match[2] else ''}{match[3]}" if match else f"{day} 09:00"


def _action(q):
    if re.search(r"\bnote\b", q):
        return "note"
    if re.search(r"keep an eye|\bwatch\b|hasn't moved|has not moved|tell me when|let me know when|flag it", q):
        return "watch"
    if re.search(r"\bremind", q):
        return "reminder"
    if re.search(r"\bchase|\bdraft", q):
        return "chase"
    return None


def _messages(history, kind):
    return [m for m in history if m.type == kind]


def _previous_answer(history):
    answers = [m for m in history if m.type == "ai" and _text(m.content) and not getattr(m, "tool_calls", None)]
    return _text(answers[-1].content) if answers else ""


def _history_orders(history):
    """Every order-shaped record in earlier tool results, newest last."""
    found = []

    def walk(node):
        if isinstance(node, dict):
            if isinstance(node.get("order_id"), str):
                found.append(node)
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    for message in _messages(history, "tool"):
        walk(_json(message.content))
    return found


def _pending_action(history):
    """An action the previous turn could not place because it had to ask which order."""
    humans = _messages(history, "human")
    previous = _previous_answer(history)
    if humans and "?" in previous and re.search(r"\bwhich\b", previous, re.I):
        question = _text(humans[-1].content)
        kind = _action(question.casefold())
        if kind:
            return {"kind": kind, "question": question}
    return None


def _resolve(q, history):
    """The order a follow-up means: by due date, by product, or 'it' for the last order named."""
    candidates = _history_orders(history)
    shown = _ids(_previous_answer(history))
    due = re.search(rf"\b(\d{{1,2}})(?:st|nd|rd|th)? ({'|'.join(MONTHS)})\b", q)
    if due:
        wanted = _iso(*due.groups())
        ids = list(dict.fromkeys(o["order_id"] for o in candidates if o.get("due_date") == wanted))
        if len(ids) == 1:
            return ids[0]
    product = _product(q)
    if product:
        ids = list(dict.fromkeys(o["order_id"] for o in candidates if product in str(o.get("product", "")).casefold()
                                 and o.get("status", "IN_PROGRESS") == "IN_PROGRESS"))
        if len(ids) > 1:
            ids = [i for i in ids if i in shown] or ids
        if len(ids) == 1:
            return ids[0]
    if re.search(r"\b(?:it|that one|this one|that order|this order)\b", q) and shown:
        return shown[0]
    return None


def _proposal(kind, order_id, question):
    text = question.split(":", 1)[1].strip() if ":" in question else question.strip()
    if kind == "note":
        return "propose_order_note", {"order_id": order_id, "text": text}
    if kind == "chase":
        return "draft_chase_message", {"order_id": order_id, "text": f"Hello, could you confirm a firm finish "
                                                                       f"date for {order_id}? Thank you."}
    if kind == "reminder":
        return "propose_reminder", {"text": text, "when": _when(question), "order_id": order_id}
    q = question.casefold()
    if "complete" in q:
        return "propose_watch", {"order_id": order_id, "condition": "completed"}
    if "overdue" in q:
        return "propose_watch", {"order_id": order_id, "condition": "becomes_overdue"}
    return "propose_watch", {"order_id": order_id, "condition": "not_moved_by",
                             "deadline": _weekday_date(q) or (TODAY + timedelta(days=1)).isoformat()}


def _filters(q, customer):
    args = {}
    if re.search(r"\bopen\b|unfinished|not finished|aren't finished|in progress", q):
        args["status"] = "IN_PROGRESS"
    if re.search(r"accessor|beanie|scar", q):
        args["category"] = "ACCESSORIES"
    elif re.search(r"\btops?\b", q):
        args["category"] = "TOPS"
    if customer:
        args["customer"] = customer
    between = re.search(rf"between (\d{{1,2}}) and (\d{{1,2}}) ({'|'.join(MONTHS)})", q)
    if between:
        args["due_from"], args["due_to"] = _iso(between[1], between[3]), _iso(between[2], between[3])
    return args


def _refers_back(q):
    return bool(re.search(r"\bthese\b|\bthose\b|\bof them\b|\bamong\b|\bthat altogether\b|\bthat in total\b", q))


def _last_count(history):
    for message in reversed(_messages(history, "tool")):
        if message.name == "query_orders":
            return _json(message.content).get("count")
    return None


def first_step(question, history):
    """Tool calls for a new user message, or a direct reply."""
    q = question.casefold()
    ids = _ids(question)
    action = _action(q)
    pending = None if action else _pending_action(history)
    today = TODAY.isoformat()
    if not action and re.search(r"revenue|profit|margin|worker|salary|wage|percentage|percent\b|how far along", q):
        return DECLINE_TEXT
    if re.search(r"\bsend (?:it|this|that)\b|go ahead and send", q):
        return SEND_TEXT
    if re.search(r"follow-?ups?|waiting on me|\bpending\b", q) and _available("list_follow_ups"):
        return [("list_follow_ups", {})]
    kind = action or (pending and pending["kind"])
    if kind:
        target = ids[0] if ids else _resolve(q, history)
        if target and _available(PROPOSE_TOOL[kind]):
            return [_proposal(kind, target, pending["question"] if pending else question)]
        customer = _customer(question) or _customer(_previous_answer(history))
        query = " ".join(filter(None, [customer, _product(q)]))
        if query and _available("search_orders"):
            return [("search_orders", {"query": query, "limit": 8})]
        return "Which order do you mean? Please give its order ID."
    pieces = re.search(r"(\d[\d,]*)\s*(?:pieces|pcs|hoodies?|beanies?|cardigans?|scarf|scarves|vests?|sweaters?)", q)
    if pieces and re.search(r"\bcan we\b|\bcould\b|\bcommit\b|\btake on\b|\bhandle\b|\bturn around\b", q):
        category = "ACCESSORIES" if re.search(r"beanie|scar|accessor", q) else "TOPS"
        args = {"category": category, "total_pieces": int(pieces[1].replace(",", ""))}
        if re.search(r"outside|outsourc|workshops? alone", q):
            args["include_in_house"] = False
        return [("optimize_fastest_plan", args)]
    if re.search(r"briefing|problems|need to know|meeting", q):
        return [("get_morning_briefing", {"as_of_date": today})]
    if re.search(r"slow|drop|anomal|went wrong|slipping|unusual", q):
        return [("discover_issues", {"as_of_date": today})]
    stages = [s for s in STAGES if s.lower() in q]
    if not stages and re.search(r"each stage|every stage|all stages|the stages", q):
        stages = list(STAGES)
    if stages:
        day = _day_mention(q) or (TODAY - timedelta(days=1)).isoformat()
        return [("compare_stage_output", {"stage": s, "production_date": day}) for s in stages]
    if re.search(r"rows? behind|which line|line of orders|source rows?", q):
        if ids:
            return [("trace_order", {"order_id": i}) for i in ids]
        return [("get_orders_at_risk", {"as_of_date": today})]
    if ids:
        return [("trace_order", {"order_id": i}) for i in ids[:3]]
    context = _ids(_previous_answer(history))
    if re.search(r"\bwhy\b|\bit\b", q) and context:
        return [("trace_order", {"order_id": context[0]})]
    if re.search(r"no activity|recorded activity|idle|quiet|at[- ]risk|due within|due in the next|fall due", q):
        return [("get_orders_at_risk", {"as_of_date": today})]
    extra = re.search(r"\b(\d+|" + "|".join(NUMBER_WORDS) + r") (?:more|extra) days\b", q)
    if extra:
        days = int(extra[1]) if extra[1].isdigit() else NUMBER_WORDS[extra[1]]
        return [("revise_order_plan", {"extra_days": days, "deadline_basis": "completion_date"})]
    if re.search(r"outsourc|made again|from scratch", q) and _refers_back(q):
        return [("optimize_orders_outsourced", {"quantity_basis": "original_order_pieces", "scope": "selected",
                                                "expected_order_count": _last_count(history) or 0})]
    customer = _customer(question)
    if _refers_back(q):
        return [("query_orders", {"scope": "selected", **_filters(q, customer)})]
    if re.search(r"overdue|past (?:its|their) due|\blate\b", q):
        return [("get_overdue_orders", {"as_of_date": today})]
    if customer and _product(q):
        return [("search_orders", {"query": f"{customer} {_product(q)}", "limit": 8})]
    return [("query_orders", _filters(q, customer))]


def _rows(result):
    return ", ".join(str(r["row"]) for r in result.get("source_rows", []) if isinstance(r, dict))


def _scope_customer(question, history):
    if re.search(r"\btheir\b|\bthey\b|\bthem\b", question.casefold()):
        return _customer(question) or _customer(_previous_answer(history))
    return _customer(question)


def describe(name, result, question, history):
    """One templated sentence (or a clarifying question) for one tool result."""
    q = question.casefold()
    status = result.get("status")
    if status == "proposed":
        return (f"Prepared for your confirmation: {result['proposal']['summary']}. Nothing is saved until you "
                "press Confirm in the app.")
    if status == "not_found":
        missing = _ids(question)
        return f"{missing[0] if missing else 'That order'} was not found in the order data."
    if status == "needs_clarification":
        return "Which orders do you mean? There is no earlier order list in this conversation."
    if status not in ("ok", None):
        return f"The {name} lookup did not work: {result.get('message', status)}."
    if name == "get_morning_briefing":
        return result["summary"]["text"]
    if name == "discover_issues":
        findings = result["findings"]
        if re.search(r"slow|drop|stage|line", q):
            findings = [f for f in findings if f["type"] == "stage_output_drop"] or findings
        elif "customer" in q:
            findings = [f for f in findings if f["type"] == "customer_slipping"] or findings
        return " ".join(f["summary"] + (f" ({', '.join(f['details']['order_ids'])})" if "order_ids" in f["details"] else "")
                        for f in findings)
    if name in ("get_orders_at_risk", "get_overdue_orders"):
        rows = list(result["data"])
        customer = _scope_customer(question, history)
        if customer:
            rows = [r for r in rows if r["customer"] == customer]
        if re.search(r"activity|idle|quiet", q):
            rows = sorted((r for r in rows if any("no recorded activity" in x for x in r.get("risk_reasons", []))),
                          key=lambda r: r["last_activity_date"])
        elif re.search(r"due within|due in the next|fall due", q):
            rows = [r for r in rows if any(x.startswith("due in") for x in r.get("risk_reasons", []))]
        if name == "get_overdue_orders":
            rows.sort(key=lambda r: -r["overdue_calendar_days"])
        if re.search(r"longest|furthest|most overdue|worst", q) and rows:
            r = rows[0]
            reason = (f"{r['overdue_calendar_days']} days overdue (due {r['due_date']})" if name == "get_overdue_orders"
                      else ", ".join(r["risk_reasons"]))
            return f"{r['order_id']} ({r['customer']}): {reason}."
        items = [f"{r['order_id']} ({r['customer']}, " + (f"{r['overdue_calendar_days']} days late, due {r['due_date']})"
                 if name == "get_overdue_orders" else ", ".join(r["risk_reasons"]) + ")") for r in rows]
        return f"{len(rows)} order(s): " + "; ".join(items) + f". Source: orders.csv rows {_rows(result)}."
    if name == "query_orders":
        statuses = ", ".join(f"{k} {v['order_count']}" for k, v in result["by_status"].items())
        categories = ", ".join(f"{k} {v['order_count']} ({v['original_order_pieces']} pcs)" for k, v in result["by_category"].items())
        return (f"{result['count']} orders, {result['original_order_pieces']} pieces in original ordered quantities "
                f"(by status: {statuses}; by category: {categories}): {', '.join(result['order_ids'][:20])}.")
    if name == "trace_order":
        o, facts = result["data"], result["facts"]
        row = result["evidence"]["order"][0]["row"]
        late = facts.get("overdue_calendar_days")
        if re.match(r"\s*is\b", q) and "late" in q:
            return (f"Yes — {o['order_id']} is {late} days overdue (due {o['due_date']})." if late
                    else f"No — {o['order_id']} is not overdue (due {o['due_date']}).")
        reasons = "; ".join(facts["risk_reasons"]) or "no risk rule applies"
        return (f"{o['order_id']} ({o['customer']}, {o['product']}, {o['pieces']} pcs) is at {o['current_stage']}, "
                f"due {o['due_date']}, last activity {o['last_activity_date']}; {reasons}. Source: orders.csv row {row}.")
    if name == "compare_stage_output":
        d = result["data"]
        if "one line" in q or "short" in q:
            return f"{d['stage']} {d['pieces_completed']} ({d['change_percent']:+.1f}%)."
        return (f"{d['stage']} on {d['date']}: {d['pieces_completed']} pieces vs {d['baseline_average']} average over "
                f"the previous {d['baseline_workdays']} workdays ({d['change_percent']:+.2f}%).")
    if name == "search_orders":
        open_orders = [o for o in result["orders"] if o["status"] == "IN_PROGRESS"]
        if len(open_orders) > 1:
            return "Which one do you mean: " + " or ".join(
                f"{o['order_id']} ({o['product']}, {o['current_stage']}, due {o['due_date']})" for o in open_orders) + "?"
        if open_orders:
            o = open_orders[0]
            return f"{o['order_id']} ({o['customer']}, {o['product']}) is at {o['current_stage']}, due {o['due_date']}."
        return "No open order matches that description."
    if name == "list_follow_ups":
        pending = result.get("pending_proposals") or []
        if not pending:
            return "Nothing is waiting for your confirmation."
        return f"{len(pending)} item(s) awaiting your confirmation: " + "; ".join(p["summary"] for p in pending) + "."
    if "completion_date" in result:
        allocation = ", ".join(f"{a['workshop_id']} {a['pieces']}" for a in result.get("allocations", []))
        if result.get("in_house_pieces"):
            allocation += f"{', ' if allocation else ''}in-house {result['in_house_pieces']}"
        assumptions = " ".join(result.get("assumptions", [])[:2])
        return (f"Estimated completion {result['completion_date']}, external processing cost "
                f"{result.get('external_processing_cost')} (currency unspecified)"
                + (f", allocation {allocation}" if allocation else "") + f". Assumptions: {assumptions} "
                "This is a scenario estimate, not a delivery promise.")
    return f"{name}: {json.dumps(result, default=str)[:200]}"


def respond(messages):
    """The model's next message: tool calls for a new question, then an answer from the results."""
    human = max(i for i, m in enumerate(messages) if m.type == "human")
    question, history = _text(messages[human].content), messages[:human]
    results = [(m.name, _json(m.content)) for m in messages[human + 1:] if m.type == "tool"]
    if not results:
        plan = first_step(question, history)
    else:
        name, result = results[-1]
        q = question.casefold()
        pending = None if _action(q) else _pending_action(history)
        kind = _action(q) or (pending and pending["kind"])
        open_orders = [o for o in result.get("orders", []) if o.get("status") == "IN_PROGRESS"]
        if name == "search_orders" and kind and len(open_orders) == 1 and _available(PROPOSE_TOOL[kind]):
            plan = [_proposal(kind, open_orders[0]["order_id"], pending["question"] if pending else question)]
        else:
            clarifying = [describe(n, r, question, history) for n, r in results]
            questions = [text for text in clarifying if text.endswith("?")]
            plan = questions[0] if questions else " ".join(clarifying)
    if isinstance(plan, str):
        return AIMessage(content=plan)
    return AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": f"fake_{uuid4().hex[:12]}",
                                              "type": "tool_call"} for name, args in plan])


class RuleBasedModel(BaseChatModel):
    """A chat model that never calls a network: see the module docstring."""

    @property
    def _llm_type(self):
        return "rule-based-fake"

    def bind_tools(self, tools, **kwargs):
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        return ChatResult(generations=[ChatGeneration(message=respond(messages))])


def build_fake_agent():
    """The real LangChain agent loop and tools, driven by the rule-based model."""
    return create_agent(RuleBasedModel(), tools=build_tools(), system_prompt=SYSTEM_PROMPT)
