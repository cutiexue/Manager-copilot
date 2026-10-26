"""Serve the real backend API with a rule-based demo model, for UI checks without an LLM API key.

Only the language model is replaced. The agent loop, all tools, api.py, service.py, the
follow-up actions, the scheduler and SQLite are the real project code. The demo model does not
understand language; it reacts to a few keywords so every UI flow can be tried:
  - an order ID ("ORD-002", "ord 2")            -> trace_order, then a short answer
  - "remind" + order ID                          -> propose_reminder (confirm it on the card)
  - "note" + order ID                            -> propose_order_note
  - "chase" or "draft" + order ID                -> draft_chase_message
  - "watch", "tell me if" or "let me know" + ID  -> propose_watch (not moved by Thu 2 Apr)
  - "at risk"                                    -> get_orders_at_risk, answered as a table
  - "briefing"                                   -> get_morning_briefing
Anything else is echoed back. Every answer starts with [demo model].

It is for trying the app without an API key and for UI checks; its answers say nothing about
how a real model behaves (use evaluation/run_evaluation.py with a key for that).

Usage, from backend/ with the virtualenv active:
    python demo_backend.py
Then start the frontend as usual (npm run dev). Environment: PORT (default 8000) and DEMO_DB
(default backend/demo.db, git-ignored like every *.db file).
"""

import json
import os
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import uvicorn  # noqa: E402
from langchain.agents import create_agent  # noqa: E402
from langchain_core.language_models.chat_models import BaseChatModel  # noqa: E402
from langchain_core.messages import AIMessage  # noqa: E402
from langchain_core.outputs import ChatGeneration, ChatResult  # noqa: E402

from api import create_app  # noqa: E402
from llm import SYSTEM_PROMPT, build_tools  # noqa: E402
from scheduler import AppScheduler  # noqa: E402
from service import ChatService  # noqa: E402
from storage import SQLiteStore  # noqa: E402
from tools import canonical_order_id  # noqa: E402

ORDER = re.compile(r"\bord[\s-]*\d{1,4}\b", re.IGNORECASE)


def plan(question):
    """The tool calls the demo model makes for a question, in order."""
    text = question.lower()
    found = ORDER.search(question)
    order = canonical_order_id(found.group(0)) if found else None
    if order and "remind" in text:
        return [("trace_order", {"order_id": order}),
                ("propose_reminder", {"text": f"Follow up on {order}", "when": "tomorrow 09:00", "order_id": order})]
    if order and ("chase" in text or "draft" in text):
        return [("trace_order", {"order_id": order}),
                ("draft_chase_message", {"order_id": order, "text": f"Hello, we are checking on {order} and will send "
                                                                   "an update on its delivery shortly."})]
    if order and "note" in text:
        return [("propose_order_note", {"order_id": order, "text": question.strip()[:300]})]
    if order and any(word in text for word in ("watch", "tell me if", "let me know")):
        return [("propose_watch", {"order_id": order, "condition": "not_moved_by", "deadline": "2026-04-02"})]
    if order:
        return [("trace_order", {"order_id": order})]
    if "at risk" in text or "at-risk" in text:
        return [("get_orders_at_risk", {"as_of_date": "2026-04-01"})]
    if "briefing" in text:
        return [("get_morning_briefing", {"as_of_date": "2026-04-01"})]
    return []


def answer(question, results):
    """A short Markdown answer written only from the tool results."""
    parts = []
    for result in results:
        if result.get("status") == "proposed":
            parts.append(f"I've prepared this for you: *{result['proposal']['summary']}*. "
                         "It is saved only when you press **Confirm** on the card.")
        elif "facts" in result and result.get("status") == "ok":
            order, facts = result["data"], result["facts"]
            reasons = "; ".join(facts["risk_reasons"]) or "no risk reasons under the current rules"
            parts.append(f"**{order['order_id']}** ({order['customer']}, {order['pieces']} {order['product']}) is at "
                         f"{order['current_stage']}, due {order['due_date']}: {reasons}.")
        elif result.get("status") == "ok" and "data" in result and isinstance(result["data"], list):
            rows = ["| Order | Customer | Stage | Why |", "| --- | --- | --- | --- |"]
            rows += [f"| {o['order_id']} | {o['customer']} | {o['current_stage']} | {'; '.join(o['risk_reasons'])} |"
                     for o in result["data"]]
            parts.append(f"**{result['count']} orders are at risk** as of {result['as_of_date']}:\n\n" + "\n".join(rows))
        elif result.get("status") == "ok" and "at_risk" in result:
            parts.append(f"Morning briefing for {result['as_of_date']}: **{result['at_risk']['count']} orders at risk**, "
                         f"{result.get('act_count', 0)} to act on now. Open the Briefing page for the details.")
        elif result.get("status") in ("error", "not_found", "ambiguous", "unavailable"):
            parts.append(f"That did not work: {result.get('message', result['status'])}")
    if not parts:
        parts.append(f"received: {question}")
    return "[demo model] " + "\n\n".join(parts)


class DemoModel(BaseChatModel):
    """Keyword rules instead of a language model; see the module docstring."""

    @property
    def _llm_type(self):
        return "demo-rules"

    def bind_tools(self, tools, **kwargs):
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        last = max(i for i, m in enumerate(messages) if m.type == "human")
        question = messages[last].content
        done = [m for m in messages[last + 1:] if m.type == "tool"]
        steps = plan(question)
        if len(done) < len(steps):
            name, args = steps[len(done)]
            reply = AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": f"demo-{len(done)}",
                                                       "type": "tool_call"}])
        else:
            results = []
            for message in done:
                try:
                    results.append(json.loads(message.content))
                except (TypeError, ValueError):
                    continue
            reply = AIMessage(content=answer(question, results))
        return ChatResult(generations=[ChatGeneration(message=reply)])


def build_service(db_path):
    """ChatService over a SQLite file, with the demo model in place of the LLM."""
    store = SQLiteStore(Path(db_path))
    store.setup()
    agent = create_agent(DemoModel(), tools=build_tools(), system_prompt=SYSTEM_PROMPT)
    return ChatService(store, agent=agent)


def main(db_path, port):
    service = build_service(db_path)
    print(f"Demo-model backend on port {port}; data stored in {service.store.path}")
    uvicorn.run(create_app(service, scheduler=AppScheduler(service.actions)), host="127.0.0.1", port=port)


if __name__ == "__main__":
    main(os.environ.get("DEMO_DB", HERE / "demo.db"), int(os.environ.get("PORT", "8000")))
