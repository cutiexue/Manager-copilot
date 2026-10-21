"""Describe available tools and register their Python functions."""

from tools import (get_order_status, get_customer_orders, get_overdue_orders,
                   get_orders_at_risk, get_stage_output, compare_stage_output,
                   trace_order, query_orders)
from discovery import discover_issues
from briefing import get_morning_briefing
from plan_context import get_current_plan, revise_order_plan
from production_estimates import WORKSHOP_ESTIMATORS, estimate_in_house, estimate_production_plan
from production_optimizer import (optimize_fastest_plan, optimize_cheapest_plan,
                                  optimize_orders_outsourced, optimize_orders_cheapest)

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
    'plan fits the deadline. No in-house production. Read-only; currency unspecified.',
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
    'Report the quantity basis prominently. Cost is reported but not minimized. Read-only.',
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
    get_overdue_orders,
    'Find all IN_PROGRESS orders with due dates strictly before the reference date. Returns calendar days overdue. Read-only snapshot query.',
    {'as_of_date': {'type': 'string',
                    'description': 'YYYY-MM-DD. Use 2026-04-01 for today. Other dates are '
                                   'scenarios using unchanged snapshot statuses.'}},
    ['as_of_date'],
)

register_tool(
    get_stage_output,
    'Read factory-wide output for one stage on one date. Not order-level output or a forecast. Missing records are not zero output.',
    {'stage': {'type': 'string',
               'enum': ['KNITTING', 'ASSEMBLY', 'WASHING', 'PACKING'],
               'description': 'The production stage.'},
     'production_date': {'type': 'string',
                         'description': 'YYYY-MM-DD. Yesterday means 2026-03-31 relative to the '
                                        'dataset reference date. Records cover 2026-01-01 through '
                                        '2026-03-31.'}},
    ['stage', 'production_date'],
)

register_tool(
    compare_stage_output,
    "Compare a stage's daily output with the requested number of previous workdays (default 7), excluding Sundays and the target day. Returns evidence and percentage change, not an anomaly diagnosis or forecast.",
    {'stage': {'type': 'string', 'enum': ['KNITTING', 'ASSEMBLY', 'WASHING', 'PACKING']},
     'production_date': {'type': 'string',
                         'description': 'YYYY-MM-DD. Yesterday means 2026-03-31.'},
     'baseline_days': {'type': 'integer',
                       'minimum': 1,
                       'description': 'Number of previous workdays requested by the user, for '
                                      'example 5. Omit to use 7.'}},
    ['stage', 'production_date'],
)

register_tool(
    get_orders_at_risk,
    'List unfinished orders that are overdue, due soon, or have gone quiet, with the reason for each. Read-only snapshot query; thresholds are defined in rules.py.',
    {'as_of_date': {'type': 'string',
                    'description': 'YYYY-MM-DD. Use 2026-04-01 for today. Other dates are '
                                   'scenarios using unchanged snapshot statuses.'},
     'due_within_days': {'type': 'integer',
                         'minimum': 1,
                         'description': 'Orders due within this many calendar days count as '
                                        'at risk. Omit to use 3.'}},
    ['as_of_date'],
)

register_tool(
    trace_order,
    'Expand one order into the evidence behind it: its source row, computed facts (idle days, overdue days), and recent factory output at its current stage. Use this to answer "why" about an order instead of paraphrasing an earlier answer. Read-only.',
    {'order_id': {'type': 'string', 'description': 'The order identifier, for example ORD-120.'}},
    ['order_id'],
)

register_tool(
    discover_issues,
    'Proactively scan the snapshot for stage output drops, overdue or quiet orders, and customers whose unfinished orders are all slipping. Returns findings grouped by type with source-row evidence for the morning briefing or "did anything go wrong?" questions. Read-only.',
    {'as_of_date': {'type': 'string',
                    'description': 'YYYY-MM-DD. Use 2026-04-01 for today.'},
     'max_findings': {'type': 'integer',
                      'minimum': 1,
                      'description': 'Maximum findings to return, selected across issue types. Omit to use 5.'}},
    ['as_of_date'],
)

register_tool(
    get_morning_briefing,
    "Assemble the structured morning briefing: yesterday's stage output versus baseline, orders at risk, and grouped findings each paired with a suggested follow-up check. Use for the 7 a.m. briefing or 'what do I need to know today?' questions. Read-only; every number comes from the underlying tools with source rows.",
    {'as_of_date': {'type': 'string',
                    'description': 'YYYY-MM-DD. Use 2026-04-01 for today.'},
     'max_findings': {'type': 'integer',
                      'minimum': 1,
                      'description': 'Maximum findings to include. Omit to use 5.'}},
    ['as_of_date'],
)


# 让每个工坊独立暴露为工具，同时共享字段定义。

ESTIMATION_FUNCTIONS = {
    f.__name__: f for f in [estimate_in_house, estimate_production_plan, *WORKSHOP_ESTIMATORS.values()]
}
_common = {
    "pieces": {"type": "integer", "minimum": 0},
    "category": {"type": "string", "enum": ["TOPS", "ACCESSORIES"]},
    "start_date": {"type": "string", "description": "YYYY-MM-DD; default scenario date is 2026-04-01."},
}
for _name, _function in ESTIMATION_FUNCTIONS.items():
    if _name == "estimate_in_house":
        _required = ["pieces"]
        _properties = {k: _common[k] for k in ("pieces", "start_date")}
        _properties.update(queue_workdays={"type": "number", "minimum": 0},
                           baseline_days={"type": "integer", "minimum": 1, "maximum": 90})
    elif _name == "estimate_production_plan":
        _required = ["category", "total_pieces", "in_house_pieces", "allocations"]
        _properties = {k: _common[k] for k in ("category", "start_date")}
        _properties.update(
            total_pieces={"type": "integer", "minimum": 1},
            in_house_pieces={"type": "integer", "minimum": 0},
            in_house_queue_workdays={"type": "number", "minimum": 0},
            baseline_days={"type": "integer", "minimum": 1, "maximum": 90},
            allocations={"type": "array", "items": {"type": "object", "properties": {
                "workshop_id": {"type": "string", "enum": list(WORKSHOP_ESTIMATORS)},
                "pieces": {"type": "integer", "minimum": 0}},
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
        "include_in_house": {"type": "boolean", "description": "Default true. In-house costs are excluded; immediate availability is assumed unless queue is supplied."},
        "in_house_queue_workdays": {"type": "number", "minimum": 0},
        "baseline_days": {"type": "integer", "minimum": 1, "maximum": 90},
    }
    _required = ["category", "total_pieces"]
    if _function is optimize_cheapest_plan:
        _properties["deadline_days"] = {"type": "integer", "minimum": 1, "maximum": 3650,
                                        "description": "Inclusive calendar days: start date is day one."}
        _required.append("deadline_days")
    register_tool(_function, _function.__doc__ + " Read-only new-batch scenario. Report assumptions; not total real cost or guaranteed delivery.", _properties, _required)
