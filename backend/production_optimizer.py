"""Optimize single batches and order groups under deterministic production estimates."""

from collections import deque
from datetime import date, timedelta
from decimal import Decimal
from math import ceil

from data_loader import load_orders, load_workshops
from production_estimates import SNAPSHOT, _finish, estimate_in_house, estimate_production_plan
from tools import query_orders


class _InHouseUnavailable(Exception):
    """The in-house estimate could not be made; carries its result so its status is not lost."""

    def __init__(self, result):
        super().__init__(result.get("message"))
        self.result = result


def _prepare(category, total_pieces, start_date, include_in_house, queue, baseline_days):
    if category not in ("TOPS", "ACCESSORIES"):
        raise ValueError("category must be TOPS or ACCESSORIES.")
    if type(total_pieces) is not int or not 1 <= total_pieces <= 1000000:
        raise ValueError("total_pieces must be an integer from 1 to 1000000.")
    if type(include_in_house) is not bool:
        raise ValueError("include_in_house must be a boolean.")
    start = date.fromisoformat(start_date)
    producers = []
    for row in load_workshops():
        if row["status"] != "ACTIVE" or category not in row["makes"].split("+"):
            continue
        producers.append({
            "id": row["workshop_id"], "cost": Decimal(row["cost_per_piece"]),
            "limit": min(total_pieces, int(row["max_batch_pieces"] or total_pieces)),
            "rate": Decimal(row["capacity_pieces_per_day"]),
            "queue": Decimal(row["current_queue_days"]),
            "transport": int(row["pickup_lead_days"]),
        })
    if include_in_house:
        sample = estimate_in_house(1, start_date, queue, baseline_days)
        if sample["status"] != "ok":
            raise _InHouseUnavailable(sample)
        totals = [sum(int(r["pieces_completed"]) for r in sample["baseline_records"]
                      if r["stage"] == stage["stage"]) for stage in sample["stages"]]
        producers.append({"id": "IN_HOUSE", "cost": Decimal(0), "limit": total_pieces,
                          "totals": totals, "baseline_days": baseline_days, "queue": ceil(queue)})
    return start, producers


def _capacity(producer, start, deadline):
    """Find the largest integer quantity deliverable by a date."""
    transport = producer.get("transport", 0)
    last_workday = deadline - timedelta(days=transport)
    count = max(0, (last_workday - start).days + 1)
    weeks, remainder = divmod(count, 7)
    available = weeks * 6 + sum((start.weekday() + i) % 7 != 6 for i in range(remainder))

    def duration(quantity):
        if "totals" in producer:
            return producer["queue"] + sum(
                (quantity * producer["baseline_days"] + total - 1) // total
                for total in producer["totals"])
        return ceil(producer["queue"] + Decimal(quantity) / producer["rate"])

    low, high = 0, producer["limit"]
    while low < high:
        middle = (low + high + 1) // 2
        if duration(middle) <= available:
            low = middle
        else:
            high = middle - 1
    return low


def _allocate(producers, start, deadline, quantity):
    """With independent capacities and linear costs, cheapest units go first."""
    assignments = []
    for producer in sorted(producers, key=lambda p: (p["cost"], p["id"])):
        pieces = min(quantity, _capacity(producer, start, deadline))
        if pieces:
            assignments.append({"workshop_id": producer["id"], "pieces": pieces})
            quantity -= pieces
    return assignments, quantity


def _optimize(category, total_pieces, start_date, include_in_house, queue, baseline_days, days):
    try:
        start, producers = _prepare(category, total_pieces, start_date, include_in_house, queue, baseline_days)
        if days is not None and (type(days) is not int or not 1 <= days <= 3650):
            raise ValueError("deadline_days must be an integer from 1 to 3650.")
        # 第一天包含开始日期，10 天内即开始日期加 9 天。
        horizon = start + timedelta(days=(days or 3650) - 1)
        allocations, missing = _allocate(producers, start, horizon, total_pieces)
        if missing:
            return {"status": "infeasible" if days else "search_limit",
                    "message": "Insufficient modeled capacity within the requested horizon.",
                    "deadline_date": horizon.isoformat(), "unallocated_pieces": missing,
                    "maximum_deliverable_pieces": total_pieces - missing}
        if days is None:
            # 可行性随日期单调变化，二分寻找最早可交付日期。
            low, high = 0, (horizon - start).days
            while low < high:
                middle = (low + high) // 2
                _, missing = _allocate(producers, start, start + timedelta(days=middle), total_pieces)
                if missing:
                    low = middle + 1
                else:
                    high = middle
            horizon = start + timedelta(days=low)
            allocations, _ = _allocate(producers, start, horizon, total_pieces)
        in_house = sum(a["pieces"] for a in allocations if a["workshop_id"] == "IN_HOUSE")
        external = [a for a in allocations if a["workshop_id"] != "IN_HOUSE"]
        result = estimate_production_plan(category, total_pieces, in_house, external,
                                          start_date, queue, baseline_days)
        if result["status"] != "ok":
            return result
        result.update(
            objective="minimum_external_processing_cost_by_deadline" if days else "earliest_completion_then_external_processing_cost",
            optimality="Exact for independent producers, integer quantities, linear external costs and the stated deterministic model.",
            deadline_date=horizon.isoformat() if days else None,
            calendar_days_inclusive=result["elapsed_calendar_days"] + 1,
            allocations=external, in_house_pieces=in_house, include_in_house=include_in_house,
        )
        result["assumptions"] = result["assumptions"] + [
            "One batch per producer; arbitrary numbers of eligible workshops may run in parallel.",
            "In-house processing contributes zero to the external-charge objective, not zero real cost.",
            "No shared-resource contention, split fees or quality-risk optimization is modeled.",
            "Deadline days are inclusive calendar days; the start date is day one.",
            "This is not an existing-order forecast or an on-time probability estimate.",
        ]
        return result
    except _InHouseUnavailable as exc:
        # Keep the in-house status (e.g. insufficient_data) instead of reporting a generic error.
        detail = exc.result
        message = detail.get("message", "The in-house estimate is unavailable.")
        if detail.get("status") == "insufficient_data":
            message += " Use a later start date, or set include_in_house to false to plan with workshops only."
        return {"status": detail.get("status", "error"), "message": message}
    except (ValueError, TypeError, OverflowError) as exc:
        return {"status": "error", "message": str(exc)}


def optimize_fastest_plan(category, total_pieces, start_date=SNAPSHOT,
                          include_in_house=True, in_house_queue_workdays=0, baseline_days=7):
    """Find earliest full delivery; break date ties by external processing cost."""
    return _optimize(category, total_pieces, start_date, include_in_house,
                     in_house_queue_workdays, baseline_days, None)


def optimize_cheapest_plan(category, total_pieces, deadline_days, start_date=SNAPSHOT,
                           include_in_house=True, in_house_queue_workdays=0, baseline_days=7):
    """Minimize external processing charges within inclusive calendar deadline_days."""
    if deadline_days is None:
        return {"status": "error", "message": "deadline_days is required."}
    return _optimize(category, total_pieces, start_date, include_in_house,
                     in_house_queue_workdays, baseline_days, deadline_days)


def _flow(demands, producers, start, deadline, minimize_cost=False):
    """Find maximum integer flow, optionally minimizing its linear processing cost."""
    residual = {}
    costs = {}

    def edge(a, b, capacity, cost=Decimal(0)):
        residual.setdefault(a, {})[b] = capacity
        residual.setdefault(b, {})[a] = 0
        costs[a, b] = cost
        costs[b, a] = -cost

    for category, quantity in demands.items():
        edge('SOURCE', category, quantity)
        for producer in producers:
            if category in producer['categories']:
                edge(category, producer['id'], quantity)
    for producer in producers:
        edge(producer['id'], 'SINK', _capacity(producer, start, deadline),
             producer['cost'] if minimize_cost else Decimal(0))
    delivered = 0
    while True:
        parent = {'SOURCE': None}
        if minimize_cost:
            # 反向边可撤回旧分配，费用取负；Bellman-Ford 支持负边。
            distance = {'SOURCE': Decimal(0)}
            for _ in range(len(residual) - 1):
                changed = False
                for node, neighbors in residual.items():
                    if node not in distance:
                        continue
                    for neighbor, capacity in neighbors.items():
                        candidate = distance[node] + costs[node, neighbor]
                        if capacity > 0 and candidate < distance.get(neighbor, Decimal('Infinity')):
                            distance[neighbor] = candidate
                            parent[neighbor] = node
                            changed = True
                if not changed:
                    break
        else:
            queue = deque(['SOURCE'])
            while queue and 'SINK' not in parent:
                node = queue.popleft()
                for neighbor, capacity in residual[node].items():
                    if capacity > 0 and neighbor not in parent:
                        parent[neighbor] = node
                        queue.append(neighbor)
        if 'SINK' not in parent:
            break
        amount = sum(demands.values())
        node = 'SINK'
        while parent[node] is not None:
            previous = parent[node]
            amount = min(amount, residual[previous][node])
            node = previous
        node = 'SINK'
        while parent[node] is not None:
            previous = parent[node]
            residual[previous][node] -= amount
            residual[node][previous] += amount
            node = previous
        delivered += amount
    assignments = {p['id']: {category: residual[p['id']].get(category, 0)
                            for category in demands} for p in producers}
    return delivered, assignments


def _optimize_orders(quantity_basis, scope, order_ids, start_date, deadline_days=None,
                     expected_order_count=None):
    """Share order selection, capacity constraints and result formatting across objectives."""
    if quantity_basis != 'original_order_pieces':
        return {'status': 'error', 'message': 'Only original_order_pieces scenarios are supported.'}
    if deadline_days is not None and (type(deadline_days) is not int or not 1 <= deadline_days <= 3650):
        return {'status': 'error', 'message': 'deadline_days must be an integer from 1 to 3650.'}
    try:
        start = date.fromisoformat(start_date)
        horizon = start + timedelta(days=(deadline_days or 3650) - 1)
    except (TypeError, ValueError, OverflowError):
        return {'status': 'error', 'message': 'Invalid start date or date outside supported range.'}
    summary = query_orders(scope=scope, order_ids=order_ids)
    if summary['status'] != 'ok':
        return summary
    if expected_order_count is not None:
        if type(expected_order_count) is not int or expected_order_count < 0:
            return {'status': 'error', 'message': 'expected_order_count must be a nonnegative integer.'}
        if summary['count'] != expected_order_count:
            return {'status': 'scope_mismatch', 'expected_order_count': expected_order_count,
                    'actual_order_count': summary['count'],
                    'message': 'The selected scope differs from the discussed count. Re-query the intended orders before planning.'}
    total = summary['original_order_pieces']
    if total == 0:
        return {'status': 'empty_selection', 'message': 'The selected orders contain no pieces to schedule.'}
    if total > 1000000:
        return {'status': 'error', 'message': 'The scenario limit is 1000000 pieces.'}
    demands = {key: value['original_order_pieces'] for key, value in summary['by_category'].items()}
    producers = [
        {'id': row['workshop_id'], 'categories': row['makes'].split('+'),
         'cost': Decimal(row['cost_per_piece']), 'rate': Decimal(row['capacity_pieces_per_day']),
         'queue': Decimal(row['current_queue_days']), 'transport': int(row['pickup_lead_days']),
         'limit': min(total, int(row['max_batch_pieces'] or total))}
        for row in load_workshops() if row['status'] == 'ACTIVE'
    ]
    delivered, _ = _flow(demands, producers, start, horizon)
    if delivered < total:
        return {'status': 'infeasible' if deadline_days is not None else 'search_limit',
                'message': 'Insufficient compatible capacity within the requested horizon.',
                'quantity_basis': quantity_basis, 'total_pieces': total,
                'deadline_date': horizon.isoformat(), 'maximum_deliverable_pieces': delivered,
                'unallocated_pieces': total - delivered}
    if deadline_days is None:
        low, high = 0, 3649
        while low < high:
            middle = (low + high) // 2
            delivered, _ = _flow(demands, producers, start, start + timedelta(days=middle))
            if delivered == total:
                high = middle
            else:
                low = middle + 1
        horizon = start + timedelta(days=low)
    _, assignments = _flow(demands, producers, start, horizon,
                           minimize_cost=deadline_days is not None)
    workshop_plans = []
    cost = Decimal(0)
    for producer in producers:
        quantities = assignments[producer['id']]
        pieces = sum(quantities.values())
        if not pieces:
            continue
        finish = _finish(start, ceil(producer['queue'] + Decimal(pieces) / producer['rate']))
        finish += timedelta(days=producer['transport'])
        charge = producer['cost'] * pieces
        cost += charge
        workshop_plans.append({'workshop_id': producer['id'], 'pieces': pieces,
                               'by_category': quantities.copy(), 'completion_date': finish.isoformat(),
                               'external_processing_cost': float(charge)})
    selected = set(summary['order_ids'])
    order_plans = []
    for order in load_orders():
        if order['order_id'] not in selected:
            continue
        remaining = int(order['pieces'])
        splits = []
        for producer in producers:
            available = assignments[producer['id']][order['category']]
            pieces = min(remaining, available)
            if pieces:
                splits.append({'workshop_id': producer['id'], 'pieces': pieces})
                assignments[producer['id']][order['category']] -= pieces
                remaining -= pieces
        order_plans.append({'order_id': order['order_id'], 'category': order['category'],
                            'pieces': int(order['pieces']), 'allocations': splits})
    completion = max(date.fromisoformat(plan['completion_date']) for plan in workshop_plans)
    result = {'status': 'ok', 'quantity_basis': quantity_basis, 'order_count': summary['count'],
            'total_pieces': total, 'by_category': demands, 'start_date': start.isoformat(),
            'completion_date': completion.isoformat(), 'calendar_days_inclusive': (completion - start).days + 1,
            'external_processing_cost': float(cost), 'workshops': workshop_plans, 'orders': order_plans,
            'sources': ['track1/data/orders.csv', 'track1/data/workshops.csv'],
            'objective': 'earliest_full_external_delivery',
            'optimality': 'Earliest date under the stated shared-capacity model; cost is not optimized.',
            'assumptions': [
                'Original quantities are manufactured anew, including completed orders if selected; not remaining work.',
                'External workshops only; each workshop shares one capacity across categories and all selected orders.',
                'One pooled batch per workshop; its batch limit applies to the combined quantity.',
                'Orders may split freely. No category changeover time or order-specific priority/deadline constraint.',
                'Recorded queues apply once, assumed to be other work; selected orders are not already in those queues.',
                'Monday to Saturday workdays, inclusive start, transport added once after production.',
                'Fixed snapshot rates and queues; no holidays, rework or new competing orders. Not a delivery guarantee.',
                'Charges include external processing only, excluding transport/rework. Currency unspecified.',
            ]}
    if deadline_days is not None:
        result.update(
            deadline_days=deadline_days, deadline_date=horizon.isoformat(),
            objective='minimum_external_processing_cost_by_deadline',
            optimality='Minimum external processing cost under the stated integer shared-capacity model; no earliest-date tie-break.',
        )
        result['assumptions'].append('Deadline days are inclusive calendar days; the start date is day one.')
    return result


def optimize_orders_outsourced(quantity_basis, scope='selected', order_ids=None,
                               start_date=SNAPSHOT, expected_order_count=None):
    """Find earliest external delivery of original quantities, not remaining work."""
    return _optimize_orders(quantity_basis, scope, order_ids, start_date,
                            expected_order_count=expected_order_count)


def optimize_orders_cheapest(quantity_basis, deadline_days, scope='selected', order_ids=None,
                             start_date=SNAPSHOT, expected_order_count=None):
    """Minimize shared-workshop processing charges within an inclusive calendar deadline."""
    if deadline_days is None:
        return {'status': 'error', 'message': 'deadline_days is required.'}
    return _optimize_orders(quantity_basis, scope, order_ids, start_date, deadline_days,
                            expected_order_count)
