"""Restore and revise the last successful multi-order plan in one conversation."""

import json
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import date
from decimal import Decimal

from data_loader import load_orders
from production_optimizer import optimize_orders_cheapest

_plan = ContextVar('production_plan', default=None)
PLAN_TOOLS = {'optimize_orders_outsourced', 'optimize_orders_cheapest', 'revise_order_plan'}


@contextmanager
def plan_context(messages):
    """Recover successful plans from persisted tool results; never from assistant prose."""
    latest = None
    for message in messages:
        if message.type != 'tool' or message.name not in PLAN_TOOLS:
            continue
        try:
            result = json.loads(message.content)
            if result.get('status') == 'ok' and 'orders' in result:
                latest = result
        except (ValueError, TypeError, AttributeError):
            continue
    token = _plan.set({'value': latest})
    try:
        yield
    finally:
        _plan.reset(token)


def remember_plan(name, result):
    context = _plan.get()
    if context is not None and name in PLAN_TOOLS and result.get('status') == 'ok' and 'orders' in result:
        context['value'] = result


def get_current_plan():
    """Return the last successful multi-order plan; failed requests do not replace it."""
    context = _plan.get()
    if context is None or context['value'] is None:
        return {'status': 'needs_clarification', 'message': 'No successful multi-order plan exists in this conversation.'}
    return context['value']


def revise_order_plan(extra_days, deadline_basis, status=None):
    """Recompute cheapest delivery using the saved scope, start date and explicit date basis."""
    if type(extra_days) is not int or not 0 <= extra_days <= 3650:
        return {'status': 'error', 'message': 'extra_days must be an integer from 0 to 3650.'}
    if deadline_basis not in ('completion_date', 'deadline_date'):
        return {'status': 'error', 'message': 'Choose completion_date or deadline_date explicitly.'}
    if status not in (None, 'IN_PROGRESS', 'COMPLETE'):
        return {'status': 'error', 'message': 'Invalid status filter.'}
    previous = get_current_plan()
    if previous['status'] != 'ok':
        return previous
    basis = previous.get(deadline_basis)
    if not basis:
        return {'status': 'needs_clarification', 'message': 'The saved plan has no requested deadline. Specify whether to use its completion date.'}
    base_days = (date.fromisoformat(basis) - date.fromisoformat(previous['start_date'])).days + 1
    days = base_days + extra_days
    if days > 3650:
        # Say it in the terms the request used; the optimizer's own limit is on deadline_days.
        return {'status': 'error', 'message': f'extra_days is too large: the revised deadline would be {days} days '
                                              f'after the plan start, beyond the 3650-day limit. Use at most '
                                              f'{3650 - base_days} extra days for this plan.'}
    ids = [order['order_id'] for order in previous['orders']]
    if status is not None:
        matching = {order['order_id'] for order in load_orders() if order['status'] == status}
        ids = [order_id for order_id in ids if order_id in matching]
    result = optimize_orders_cheapest(previous['quantity_basis'], days, scope='all',
                                      order_ids=ids, start_date=previous['start_date'])
    comparison = {'base_start_date': previous['start_date'], 'base_date': basis,
                  'deadline_basis': deadline_basis, 'extra_days': extra_days,
                  'previous_external_processing_cost': previous['external_processing_cost']}
    if result['status'] == 'ok':
        old = [(o['order_id'], o['category'], o['pieces']) for o in previous['orders']]
        new = [(o['order_id'], o['category'], o['pieces']) for o in result['orders']]
        comparison['same_order_quantities'] = sorted(old) == sorted(new)
        if comparison['same_order_quantities']:
            comparison['external_processing_cost_reduction'] = float(
                Decimal(str(previous['external_processing_cost'])) - Decimal(str(result['external_processing_cost'])))
            comparison['note'] = 'Comparison against the saved quote, not a guarantee of savings caused only by extra time.'
        else:
            comparison['note'] = 'Order scope or quantities changed; no like-for-like savings calculated.'
    else:
        comparison['note'] = 'Revision failed; the last successful plan remains current.'
    result['comparison'] = comparison
    return result
