"""Describe available tools and register their Python functions."""

from tools import (get_order_status, get_customer_orders, get_overdue_orders,
                   get_orders_at_risk, get_stage_output, compare_stage_output,
                   trace_order, query_orders)
from discovery import FINDING_TYPES, discover_issues
from period_output import compare_stage_periods, summarize_stage_output
from briefing import get_morning_briefing
from plan_context import get_current_plan, revise_order_plan
from production_estimates import WORKSHOP_ESTIMATORS, estimate_in_house, estimate_production_plan
from production_optimizer import (optimize_fastest_plan, optimize_cheapest_plan,
                                  optimize_orders_outsourced, optimize_orders_cheapest)
from rules import MAX_BASELINE_WORKDAYS, MAX_QUEUE_WORKDAYS, MAX_SCENARIO_PIECES, today_iso
from action_tools import (draft_chase_message, list_follow_ups, propose_order_note, propose_reminder,
                          propose_watch)
from data_loader import STAGES
from order_search import search_orders
from watches import CONDITIONS as WATCH_CONDITIONS

TOOLS = []
TOOL_FUNCTIONS = {}


def register_tool(function, description, properties, required):
    """Keep the model description and executable function together."""
    TOOL_FUNCTIONS[function.__name__] = function
    TOOLS.append({"type": "function", "function": {
        "name": function.__name__, "description": description,
        "parameters": {"type": "object", "properties": properties,
                       "required": required, "additionalProperties": False},
    }})


# 基础查询工具：每项只写用途、参数和必填字段。
# 带 as_of_date 的工具默认用数据日期；其他日期必须同时传 scenario=true，防止模型把现实日期当作“今天”。
_AS_OF_HELP = ('YYYY-MM-DD. Omit for today (the data date, 2026-04-01 for the course data). Another date only with '
               'scenario=true, when the manager explicitly asks about that date.')
_SCENARIO = {'type': 'boolean',
             'description': 'True only when the manager explicitly asks about a date other than today; the '
                            'result then uses unchanged snapshot statuses, not real events.'}


def _dated(function):
    """Default as_of_date to the dataset date and refuse any other date unless it is an explicit scenario."""
    def run(as_of_date=None, scenario=False, **kwargs):
        today = today_iso()
        as_of_date = as_of_date or today
        if as_of_date != today and not scenario:
            return {'status': 'error', 'message': f'Today is the data date {today}; omit as_of_date for today. '
                    f'{as_of_date} is only allowed with scenario=true, when the manager asked about that date.'}
        return function(as_of_date=as_of_date, **kwargs)
    run.__name__, run.__doc__ = function.__name__, function.__doc__
    return run


register_tool(get_current_plan,
              'Read the last successful multi-order plan in this conversation, including allocations, '
              'dates, quantities and charges. Failed revisions do not replace it. Not a fresh quote.', {}, [])
register_tool(revise_order_plan,
              'Revise the saved multi-order plan to minimize charges, preserving its start and order IDs. '
              'Add extra_days to the explicit date basis. Optionally narrow its orders by status. '
              'Returns comparison with saved charges only for unchanged order quantities. Read-only scenario.',
              {'extra_days': {'type': 'integer', 'minimum': 0, 'maximum': 3650},
               'deadline_basis': {'type': 'string', 'enum': ['completion_date', 'deadline_date']},
               'status': {'type': 'string', 'enum': ['IN_PROGRESS', 'COMPLETE']}},
              ['extra_days', 'deadline_basis'])

register_tool(
    optimize_orders_cheapest,
    'Minimize external processing charges for multiple orders within deadline_days, sharing '
    'workshop capacity across categories. Original quantities manufactured anew, not remaining work. '
    'Use selected for these orders or all plus explicit order_ids. Infeasible means no complete '
    'plan fits the deadline. No in-house production. Returns `risk` (defect and deadline risk per '
    'workshop and for the plan). Read-only; currency unspecified.',
    {'quantity_basis': {'type': 'string', 'enum': ['original_order_pieces']},
     'deadline_days': {'type': 'integer', 'minimum': 1, 'maximum': 3650,
                       'description': 'Required inclusive calendar days; start date is day one.'},
     'scope': {'type': 'string', 'enum': ['selected', 'all']},
     'order_ids': {'type': 'array', 'items': {'type': 'string'}},
     'start_date': {'type': 'string', 'description': 'YYYY-MM-DD; default 2026-04-01.'}},
    ['quantity_basis', 'deadline_days', 'expected_order_count'],
)

register_tool(
    optimize_orders_outsourced,
    'Find the fastest all-outsourced plan for a set of orders, sharing workshop capacity across '
    'both categories. Original quantities manufactured anew only, not remaining-order forecasting. '
    'Use selected for these orders, all for all orders, or all plus explicit order_ids. '
    'Report the quantity basis prominently. Cost is reported but not minimized. Returns `risk` '
    '(defect risk per workshop and for the plan). Read-only.',
    {'quantity_basis': {'type': 'string', 'enum': ['original_order_pieces']},
     'scope': {'type': 'string', 'enum': ['selected', 'all']},
     'order_ids': {'type': 'array', 'items': {'type': 'string'}},
     'start_date': {'type': 'string', 'description': 'YYYY-MM-DD; default 2026-04-01.'}},
    ['quantity_basis', 'expected_order_count'],
)

for _spec in TOOLS:
    if _spec['function']['name'] in {'optimize_orders_outsourced', 'optimize_orders_cheapest'}:
        _spec['function']['parameters']['properties']['expected_order_count'] = {
            'type': 'integer', 'minimum': 0,
            'description': 'Order count in the scope currently discussed with the user. Re-query if unknown; mismatches block planning.'}

register_tool(
    query_orders,
    'Count and filter orders and sum original ordered pieces, with status/category breakdowns. '
    'Successful queries select their resulting order IDs for follow-ups, even when empty. '
    'Use selected for these orders; all starts a fresh query including completed orders. '
    'Filters intersect. Quantities are not remaining workload. Read-only.',
    {'scope': {'type': 'string', 'enum': ['all', 'selected'], 'description': 'Default all.'},
     'status': {'type': 'string', 'enum': ['IN_PROGRESS', 'COMPLETE']},
     'customer': {'type': 'string', 'description': 'Exact full customer name, case insensitive.'},
     'category': {'type': 'string', 'enum': ['TOPS', 'ACCESSORIES']},
     'due_from': {'type': 'string', 'description': 'Inclusive due-date lower bound, YYYY-MM-DD.'},
     'due_to': {'type': 'string', 'description': 'Inclusive due-date upper bound, YYYY-MM-DD.'},
     'order_ids': {'type': 'array', 'items': {'type': 'string'},
                   'description': 'Exact order IDs; unknown IDs prevent partial totals.'}},
    [],
)

register_tool(
    get_order_status,
    'Look up one order by its exact ID in the factory CSV. Returns not_found if absent.',
    {'order_id': {'type': 'string', 'description': 'The order identifier, for example ORD-120.'}},
    ['order_id'],
)

register_tool(
    get_customer_orders,
    'Look up all orders for a customer by full name, ignoring case and outer spaces. Read-only.',
    {'customer': {'type': 'string',
                  'description': 'The full customer name, for example TrendCart.'}},
    ['customer'],
)

register_tool(
    _dated(get_overdue_orders),
    'Find all IN_PROGRESS orders with due dates strictly before the reference date. Returns calendar days overdue. Read-only snapshot query.',
    {'as_of_date': {'type': 'string', 'description': _AS_OF_HELP}, 'scenario': _SCENARIO},
    [],
)

register_tool(
    get_stage_output,
    'Read factory-wide output for one stage on one date. Not order-level output or a forecast. Missing records are not zero output.',
    {'stage': {'type': 'string',
               'enum': ['KNITTING', 'ASSEMBLY', 'WASHING', 'PACKING'],
               'description': 'The production stage.'},
     'production_date': {'type': 'string',
                         'description': 'YYYY-MM-DD. Yesterday means the workday before today\'s data date '
                                        '(2026-03-31 for the course data). Records cover 2026-01-01 through '
                                        '2026-03-31.'}},
    ['stage', 'production_date'],
)

register_tool(
    compare_stage_output,
    "Compare a stage's daily output with the requested number of previous workdays (default 7), excluding Sundays and the target day. Returns evidence and percentage change, not an anomaly diagnosis or forecast.",
    {'stage': {'type': 'string', 'enum': ['KNITTING', 'ASSEMBLY', 'WASHING', 'PACKING']},
     'production_date': {'type': 'string',
                         'description': 'YYYY-MM-DD. Yesterday means the workday before today\'s data date '
                                        '(2026-03-31 for the course data).'},
     'baseline_days': {'type': 'integer',
                       'minimum': 1,
                       'description': 'Number of previous workdays requested by the user, for '
                                      'example 5. Omit to use 7.'}},
    ['stage', 'production_date'],
)

register_tool(
    summarize_stage_output,
    'Total and per-workday average output of one stage (or all four) over a date range, for questions '
    'about a month, a week or any period. Lists the workdays counted and any missing. Use this instead of '
    'adding daily figures yourself. Factory-wide output, not order progress. Read-only.',
    {'date_from': {'type': 'string', 'description': 'YYYY-MM-DD, inclusive.'},
     'date_to': {'type': 'string', 'description': 'YYYY-MM-DD, inclusive. Records end 2026-03-31.'},
     'stage': {'type': 'string', 'enum': ['KNITTING', 'ASSEMBLY', 'WASHING', 'PACKING'],
               'description': 'Omit for all four stages.'}},
    ['date_from', 'date_to'],
)

register_tool(
    compare_stage_periods,
    'Compare stage output totals between two periods and name the largest decline and increase. Omit '
    'all four dates for the two most recent complete calendar weeks (Monday to Sunday) before today. Use '
    'this, not compare_stage_output, for week-on-week or period comparisons. Read-only.',
    {'first_from': {'type': 'string', 'description': 'YYYY-MM-DD, the earlier period.'},
     'first_to': {'type': 'string'},
     'second_from': {'type': 'string', 'description': 'YYYY-MM-DD, the later period.'},
     'second_to': {'type': 'string'},
     'stage': {'type': 'string', 'enum': ['KNITTING', 'ASSEMBLY', 'WASHING', 'PACKING'],
               'description': 'Omit for all four stages.'}},
    [],
)

register_tool(
    _dated(get_orders_at_risk),
    'List unfinished orders that are overdue, due soon, or have gone quiet, with the reason for each. Read-only snapshot query; thresholds are defined in rules.py.',
    {'as_of_date': {'type': 'string', 'description': _AS_OF_HELP},
     'scenario': _SCENARIO,
     'due_within_days': {'type': 'integer',
                         'minimum': 1,
                         'description': 'Orders due within this many calendar days count as '
                                        'at risk. Omit to use 3.'}},
    [],
)

register_tool(
    trace_order,
    'Expand one order into the evidence behind it: its source row, computed facts (idle days, overdue days), and recent factory output at its current stage. Use this to answer "why" about an order instead of paraphrasing an earlier answer. Read-only.',
    {'order_id': {'type': 'string', 'description': 'The order identifier, for example ORD-120.'}},
    ['order_id'],
)

register_tool(
    _dated(discover_issues),
    'Proactively scan the snapshot for stage output drops, overdue or quiet orders, and customers whose unfinished orders are all slipping. Returns findings grouped by type with source-row evidence for the morning briefing or "did anything go wrong?" questions. Read-only.',
    {'as_of_date': {'type': 'string', 'description': _AS_OF_HELP},
     'scenario': _SCENARIO,
     'max_findings': {'type': 'integer',
                      'minimum': 1,
                      'description': 'Maximum findings to return, selected across issue types. Omit to use 5.'},
     'finding_type': {'type': 'string', 'enum': list(FINDING_TYPES),
                      'description': 'Only this kind of finding, ranked by its own severity: use order_at_risk '
                                     'with max_findings=N for "the N orders that need the most attention".'}},
    [],
)

register_tool(
    _dated(get_morning_briefing),
    "Assemble the structured morning briefing: yesterday's stage output versus baseline, orders at risk, and grouped findings each paired with a suggested follow-up check. Use for the 7 a.m. briefing or 'what do I need to know today?' questions. Read-only; every number comes from the underlying tools with source rows.",
    {'as_of_date': {'type': 'string', 'description': _AS_OF_HELP},
     'scenario': _SCENARIO,
     'max_findings': {'type': 'integer',
                      'minimum': 1,
                      'description': 'Maximum findings to include. Omit to use 5.'}},
    [],
)


# 让每个工坊独立暴露为工具，同时共享字段定义。

ESTIMATION_FUNCTIONS = {
    f.__name__: f for f in [estimate_in_house, estimate_production_plan, *WORKSHOP_ESTIMATORS.values()]
}
_QUEUE = ("Omit (default) to queue in-house work behind the unfinished orders, stage by stage; that "
          "load counts each order in full from its current stage, so it is an upper bound. A number "
          "replaces it with one flat queue in workdays; give 0 only if the manager says the line is free.")
_common = {
    "pieces": {"type": "integer", "minimum": 0, "maximum": MAX_SCENARIO_PIECES},
    "category": {"type": "string", "enum": ["TOPS", "ACCESSORIES"]},
    "start_date": {"type": "string", "description": "YYYY-MM-DD; default scenario date is 2026-04-01."},
}
for _name, _function in ESTIMATION_FUNCTIONS.items():
    if _name == "estimate_in_house":
        _required = ["pieces"]
        _properties = {k: _common[k] for k in ("pieces", "start_date")}
        _properties.update(queue_workdays={"type": "number", "minimum": 0, "maximum": MAX_QUEUE_WORKDAYS,
                                           "description": _QUEUE},
                           baseline_days={"type": "integer", "minimum": 1, "maximum": MAX_BASELINE_WORKDAYS})
    elif _name == "estimate_production_plan":
        _required = ["category", "total_pieces", "in_house_pieces", "allocations"]
        _properties = {k: _common[k] for k in ("category", "start_date")}
        _properties.update(
            total_pieces={"type": "integer", "minimum": 1, "maximum": MAX_SCENARIO_PIECES},
            in_house_pieces={"type": "integer", "minimum": 0, "maximum": MAX_SCENARIO_PIECES},
            in_house_queue_workdays={"type": "number", "minimum": 0, "maximum": MAX_QUEUE_WORKDAYS,
                                     "description": _QUEUE},
            baseline_days={"type": "integer", "minimum": 1, "maximum": MAX_BASELINE_WORKDAYS},
            allocations={"type": "array", "items": {"type": "object", "properties": {
                "workshop_id": {"type": "string", "enum": list(WORKSHOP_ESTIMATORS)},
                "pieces": {"type": "integer", "minimum": 0, "maximum": MAX_SCENARIO_PIECES}},
                "required": ["workshop_id", "pieces"], "additionalProperties": False}},
        )
    else:
        _required = ["category", "pieces"]
        _properties = dict(_common)
    register_tool(_function, _function.__doc__ + " Read-only scenario estimate. In-house costs are excluded. Report assumptions and unspecified currency.", _properties, _required)


for _function in (optimize_fastest_plan, optimize_cheapest_plan):
    ESTIMATION_FUNCTIONS[_function.__name__] = _function
    _properties = {
        "category": _common["category"],
        "total_pieces": {"type": "integer", "minimum": 1, "maximum": 1000000},
        "start_date": _common["start_date"],
        "include_in_house": {"type": "boolean", "description": "Default true. In-house costs are excluded; in-house work queues behind the unfinished orders."},
        "in_house_queue_workdays": {"type": "number", "minimum": 0, "maximum": MAX_QUEUE_WORKDAYS,
                                    "description": _QUEUE},
        "baseline_days": {"type": "integer", "minimum": 1, "maximum": MAX_BASELINE_WORKDAYS},
    }
    _required = ["category", "total_pieces"]
    if _function is optimize_cheapest_plan:
        _properties["deadline_days"] = {"type": "integer", "minimum": 1, "maximum": 3650,
                                        "description": "Inclusive calendar days: start date is day one."}
        _properties["include_in_house"] = {
            "type": "boolean",
            "description": "Default: outside workshops only, because in-house cost is not in the data. "
                           "In-house is compared only when in_house_cost_per_piece is given."}
        _properties["in_house_cost_per_piece"] = {
            "type": "number", "minimum": 0, "maximum": 1000,
            "description": "An in-house cost per piece the manager states (same unspecified currency as the "
                           "workshop charges). Never invent one."}
        _required.append("deadline_days")
    register_tool(_function, _function.__doc__ + " Read-only new-batch scenario. Returns `risk`: each workshop's defect rate, "
                  "dispatcher note and flags, and the plan's defect and deadline risk. Report assumptions; not total "
                  "real cost or guaranteed delivery.", _properties, _required)


# Order search and follow-up actions. The action tools only create proposals; the manager
# confirms them in the app, and no tool can confirm.
_ORDER = {"type": "string", "description": "Order ID such as ORD-107 (any spelling: ord107, 107)."}
register_tool(search_orders,
              "Find candidate orders for loose text: an order ID in any spelling, part of a customer name, "
              "a product or a stage. Returns ranked matches with risk reasons. Use it when the user names an "
              "order loosely or several orders could match, then ask which one they mean instead of guessing.",
              {"query": {"type": "string", "description": "What the user called the order(s)."},
               "limit": {"type": "integer", "minimum": 1, "maximum": 20}},
              ["query"])
register_tool(propose_reminder,
              "Propose an in-app reminder. Creates a PROPOSED item only: it is saved when the manager presses "
              "Confirm in the app, never by you. `when` uses the real calendar in Singapore time, not the dataset "
              "date: e.g. 'tomorrow 09:00', 'friday 3pm', 'in 2 hours', '2026-10-25T09:00' (default tomorrow 09:00).",
              {"text": {"type": "string", "description": "What to remind the manager about."},
               "when": {"type": "string"},
               "order_id": _ORDER,
               "subject": {"type": "string", "description": "Customer, stage or topic when there is no single order."}},
              ["text"])
register_tool(propose_order_note,
              "Propose a local note on an order (kept in the app, never written to the course CSV). "
              "PROPOSED only; the manager confirms it in the app.",
              {"order_id": _ORDER, "text": {"type": "string"}},
              ["order_id", "text"])
register_tool(draft_chase_message,
              "Propose a chase-up message draft for the order's customer; write the full text from tool facts. "
              "PROPOSED only; when confirmed it is saved as a draft and is never sent automatically.",
              {"order_id": _ORDER, "text": {"type": "string", "description": "The complete draft message."}},
              ["order_id", "text"])
register_tool(propose_watch,
              "Propose a standing watch on an order. Conditions: not_moved_by (alert if the order has no new "
              "activity by `deadline`, a YYYY-MM-DD date in the dataset calendar), becomes_overdue, completed, "
              "reaches_stage (needs `stage`). Watches are checked against scripted data snapshots, not live data. "
              "PROPOSED only; the manager confirms it in the app.",
              {"order_id": _ORDER,
               "condition": {"type": "string", "enum": list(WATCH_CONDITIONS)},
               "deadline": {"type": "string", "description": "YYYY-MM-DD, required for not_moved_by."},
               "stage": {"type": "string", "enum": list(STAGES), "description": "Required for reaches_stage."}},
              ["order_id", "condition"])
register_tool(list_follow_ups,
              "List the manager's follow-ups: pending proposals, reminders, notes, chase-up drafts, watches and "
              "unread alerts. Read-only.",
              {"kind": {"type": "string", "enum": ["pending_proposals", "reminders", "notes", "chase_drafts",
                                                  "watches", "unread_alerts"]}},
              [])
