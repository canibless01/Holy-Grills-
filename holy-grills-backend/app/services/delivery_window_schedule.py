"""Resolve configured delivery slots without confusing WAT clock rules with UTC instants."""
from datetime import date, datetime, time, timedelta, timezone

WAT = timezone(timedelta(hours=1))


def delivery_clock(window, start=True):
    """Return a configured WAT HH:MM clock, or None; never invent delivery hours."""
    if not isinstance(window, dict):
        return None
    value = window.get('opens_at' if start else 'closes_at') or window.get('starts_at' if start else 'ends_at')
    if not value:
        return None
    try:
        if 'T' in str(value):
            return datetime.fromisoformat(str(value).replace('Z', '+00:00')).astimezone(WAT).strftime('%H:%M')
        return time.fromisoformat(str(value)).strftime('%H:%M')
    except (ValueError, TypeError):
        return None


def upcoming_delivery_windows(rows, now=None, days=8, open_only=True):
    """Materialize each configured slot's next occurrence while retaining its DB id.

    Active date-specific rules override recurring rules on that date, including
    explicit closures. Historical one-off orders retain their original references.
    No row, status or schedule is persisted by this read helper.
    """
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    today = now.astimezone(WAT).date()
    active = [dict(row) for row in (rows or []) if row.get('is_active') is not False]
    dated = {(row.get('campus_id'), str(row['date'])) for row in active if row.get('date')}
    result = []
    for row in active:
        if row.get('is_closed') or row.get('status') == 'cancelled':
            continue
        if open_only and row.get('status', 'open') != 'open':
            continue
        if row.get('starts_at') and row.get('ends_at'):
            try:
                start = datetime.fromisoformat(str(row['starts_at']).replace('Z', '+00:00'))
                end = datetime.fromisoformat(str(row['ends_at']).replace('Z', '+00:00'))
                if start.tzinfo is None or end.tzinfo is None or end <= now:
                    continue
            except (ValueError, TypeError):
                continue
        else:
            try:
                opens = time.fromisoformat(str(row.get('opens_at')))
                closes = time.fromisoformat(str(row.get('closes_at')))
                if closes <= opens:
                    continue
                chosen = None
                for offset in range(days):
                    day = today + timedelta(days=offset)
                    if row.get('date'):
                        if str(row['date']) != day.isoformat():
                            continue
                    elif row.get('weekday') is not None:
                        if day.weekday() != row['weekday'] or (row.get('campus_id'), day.isoformat()) in dated:
                            continue
                    else:
                        continue
                    start = datetime.combine(day, opens, WAT)
                    end = datetime.combine(day, closes, WAT)
                    if end > now:
                        chosen = day
                        break
                if chosen is None:
                    continue
            except (ValueError, TypeError):
                continue
        occurrence = {**row, 'starts_at': start.astimezone(timezone.utc).isoformat(),
                      'ends_at': end.astimezone(timezone.utc).isoformat(),
                      'delivery_starts_at': delivery_clock(row), 'delivery_ends_at': delivery_clock(row, False)}
        result.append(occurrence)
    return sorted(result, key=lambda row: (row['starts_at'], str(row.get('id', ''))))


def bind_ordering_delivery(db, ordering, campus_id, day):
    """Attach that day's configured delivery slot and an effective intake cutoff.

    Existing campuses without a delivery configuration retain manual assignment.
    A configured closed/missing occurrence cannot promise delivery that day.
    """
    value = dict(ordering)
    target = date.fromisoformat(str(day)[:10])
    q = db.table('delivery_windows').select('*').eq('campus_id', campus_id)
    rows = q.execute() or []
    linked = value.get('linked_delivery_window_id')
    relevant = [r for r in rows if r.get('is_active') is not False and (
        r.get('id') == linked or str(r.get('date') or '') == target.isoformat()
        or (r.get('date') is None and r.get('weekday') == target.weekday())
        or (r.get('starts_at') and str(r['starts_at'])[:10] == target.isoformat()))]
    slots = upcoming_delivery_windows(rows, datetime.combine(target, time.min, WAT), days=1)
    if linked:
        selected = next((r for r in slots if r.get('id') == linked), None)
    else:
        selected = slots[0] if slots else None
    if not selected:
        if relevant:
            value['is_closed'] = True
        return value
    value['linked_delivery_window_id'] = selected['id']
    value['_delivery_starts_at'] = delivery_clock(selected)
    value['_delivery_ends_at'] = delivery_clock(selected, False)
    close = value.get('closes_at')
    if close and value['_delivery_ends_at']:
        # Do not accept today's orders after the last delivery has ended while
        # the original ordering configuration remains open until later at night.
        value['closes_at'] = min(str(close), value['_delivery_ends_at'] + ':00')
    return value
