"""Keep the current order selection isolated within one conversation turn."""

import json
from contextlib import contextmanager
from contextvars import ContextVar

_selection = ContextVar('order_selection', default=None)
SELECTION_TOOLS = {'query_orders', 'get_order_status', 'get_customer_orders',
                   'get_overdue_orders', 'get_orders_at_risk'}


def selection_from_result(name, result):
    """Only explicit order queries change the selection, including empty results."""
    if name not in SELECTION_TOOLS or result.get('status') not in ('ok', 'not_found'):
        return None
    if name == 'query_orders':
        return result.get('selection')
    rows = result.get('data') or []
    if isinstance(rows, dict):
        rows = [rows]
    return {'order_ids': [row['order_id'] for row in rows], 'source_tool': name}


@contextmanager
def selection_context(saved_messages):
    """Rebuild the last selection from persisted tool evidence, not model prose."""
    selected = None
    for message in saved_messages:
        if message.type != 'tool' or message.name not in SELECTION_TOOLS:
            continue
        try:
            result = json.loads(message.content)
            candidate = selection_from_result(message.name, result)
            if candidate is not None:
                selected = candidate
        except (ValueError, TypeError, KeyError, AttributeError):
            continue
    token = _selection.set({'value': selected})
    try:
        yield
    finally:
        _selection.reset(token)


def current_selection():
    context = _selection.get()
    return context['value'] if context is not None else None


def remember_selection(name, result):
    context = _selection.get()
    candidate = selection_from_result(name, result)
    if context is not None and candidate is not None:
        context['value'] = candidate
