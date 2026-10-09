"""Describe available tools and register their Python functions."""

from tools import (get_order_status, get_customer_orders, get_overdue_orders,
                   get_stage_output, compare_stage_output)
from production_estimates import WORKSHOP_ESTIMATORS, estimate_in_house, estimate_production_plan
from production_optimizer import optimize_fastest_plan, optimize_cheapest_plan

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
