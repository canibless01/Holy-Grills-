"""Normalize persisted delivery facts for owner-authorized order views."""

def order_delivery_details(db, order):
    snapshot = order.get('delivery_address_snapshot') or {}
    if isinstance(snapshot, str):
        snapshot = {'line1': snapshot}
    if not isinstance(snapshot, dict):
        snapshot = {}
    address = dict(snapshot)
    if not address.get('line1') and order.get('delivery_location_id'):
        table = 'hostels' if order.get('delivery_type') == 'on_campus' else 'gates'
        row = db.table(table).select('id,name,campus_id').eq('id', order['delivery_location_id']).single().execute() or {}
        if row.get('campus_id') in (None, order.get('campus_id')):
            address['line1'] = row.get('name')
    window = order.get('delivery_windows') or order.get('delivery_window')
    if isinstance(window, list):
        window = window[0] if window else None
    window = dict(window or {})
    if not window and order.get('ordering_window_id'):
        row = db.table('ordering_windows').select('id,campus_id,linked_delivery_window_id').eq('id', order['ordering_window_id']).single().execute() or {}
        if row.get('campus_id') == order.get('campus_id') and row.get('linked_delivery_window_id'):
            candidate = db.table('delivery_windows').select('label,campus_id,opens_at,closes_at,starts_at,ends_at').eq('id', row['linked_delivery_window_id']).single().execute() or {}
            if candidate.get('campus_id') in (None, order.get('campus_id')):
                window = candidate
    start = window.get('opens_at') or window.get('starts_at')
    end = window.get('closes_at') or window.get('ends_at')
    from datetime import datetime, timezone, timedelta
    def clock(value):
        if not value:
            return None
        if 'T' in str(value):
            return datetime.fromisoformat(str(value).replace('Z', '+00:00')).astimezone(timezone(timedelta(hours=1))).strftime('%H:%M')
        return str(value)[:5]
    start, end = clock(start), clock(end)
    label = window.get('label')
    if start and end:
        window['label'] = f'{label} · {start}–{end}' if label else f'{start}–{end}'
    return address, window
