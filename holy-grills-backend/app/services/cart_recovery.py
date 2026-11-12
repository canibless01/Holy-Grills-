"""Bounded reminder steps, shared ordering calendar and durable channel capture."""
from datetime import datetime, timedelta, timezone, time
from app.db import get_db
from app.utils.schedule import effective_windows_with_config
from app.utils.tz import WAT_OFFSET
from app.services.feature_flags import is_feature_enabled
from app.utils.logger import get_logger
logger = get_logger(__name__)
WAT = timezone(WAT_OFFSET)
DEFAULT_TIMING = {'initial_minutes': 30, 'repeat_minutes': 1440, 'max_hours': 48}


def timing(db, campus):
    row = db.table('system_settings').select('value').eq('key', 'campus_cart_recovery').eq('campus_id', campus).single().execute()
    value = row['value'] if row else DEFAULT_TIMING
    if not isinstance(value, dict):
        raise ValueError('Invalid cart recovery timing')
    result = {key: int(value.get(key, default)) for key, default in DEFAULT_TIMING.items()}
    if not 10 <= result['initial_minutes'] <= 1440 or not 30 <= result['repeat_minutes'] <= 1440 or not 1 <= result['max_hours'] <= 48:
        raise ValueError('Invalid cart recovery timing')
    return {'p_initial': result['initial_minutes'], 'p_repeat': result['repeat_minutes'], 'p_hours': result['max_hours']}


class CalendarSnapshot:
    """Three bounded calendar reads per job, never calendar queries per customer."""
    def __init__(self, db):
        self.rows = {name: db.table(name).select('*').execute() or [] for name in ('ordering_windows', 'operating_hour_overrides', 'operating_hours')}
    def table(self, name):
        return CalendarQuery(self.rows[name])


class CalendarQuery:
    def __init__(self, rows): self.rows = rows
    def select(self, *args): return self
    def eq(self, key, value):
        self.rows = [row for row in self.rows if row.get(key) == value]
        return self
    def execute(self): return self.rows


def deadline(cart, calendar):
    start = datetime.fromisoformat(str(cart['last_active_at']).replace('Z', '+00:00')).astimezone(WAT)
    # First ordering cutoff after this cart activity starts preparation for its
    # opportunity. Never revive a stale cart just because a later day reopens.
    scheduled = cart.get('recovery_scheduled_for')
    first_day = max(start.date(), datetime.fromisoformat(str(scheduled).replace('Z', '+00:00')).astimezone(WAT).date()) if scheduled else start.date()
    for offset in range(3):
        day = first_day + timedelta(days=offset)
        rows, _ = effective_windows_with_config(calendar, cart['campus_id'], day.isoformat(), day.weekday())
        closes = []
        for row in rows:
            if row.get('is_closed') or not row.get('closes_at'): continue
            close = datetime.combine(day, time.fromisoformat(str(row['closes_at'])), WAT)
            opens = time.fromisoformat(str(row.get('opens_at') or '00:00'))
            if close.time() <= opens: close += timedelta(days=1)
            if close > start: closes.append(close)
        if closes: return min(closes).isoformat()
    return (start + timedelta(hours=48)).isoformat()


def capture_cart(db, cart, schedule, limits):
    rpc = 'hg_capture_cart_recovery_step' if cart.get('user_id') else 'hg_capture_guest_cart_recovery_step'
    result = db.rpc(rpc, {
        'p_cart': cart['id'], 'p_step': cart['recovery_step'],
        'p_deadline': deadline(cart, schedule), **limits})
    if result and result.get('saved'):
        try:
            from app.tasks.scheduled import dispatch_cart_recovery
            dispatch_cart_recovery.delay(result['notification_ids'])
        except Exception:
            logger.warning('Cart reminder saved; immediate wake unavailable. Scheduled recovery will deliver it.')
    return result


def scan(db=None):
    db = db or get_db()
    campuses = db.table('campuses').select('id').eq('is_active', True).execute() or []
    calendar = None
    result = {'saved': 0, 'checked': 0}
    for campus in campuses:
        if not is_feature_enabled('abandoned_cart_nudge', campus['id']): continue
        limits = timing(db, campus['id'])
        carts = db.rpc('hg_due_cart_recovery', {'p_campus': campus['id'], **limits}) or []
        guests = db.rpc('hg_due_guest_cart_recovery', {'p_campus': campus['id'], **limits}) or []
        carts += guests
        if carts and calendar is None: calendar = CalendarSnapshot(db)
        for cart in carts:
            receipt = capture_cart(db, cart, calendar, limits)
            result['checked'] += 1
            result['saved'] += bool(receipt and receipt.get('saved'))
    # The existing durable notification recovery job delivers these saved rows.
    # A worker exit after capture cannot lose the reminder or count it twice.
    return result


def nudge(cart):
    db = get_db()
    limits = timing(db, cart['campus_id'])
    if not cart.get('user_id'):
        limits['p_initial'] = max(30, limits['p_initial'])
    now = datetime.now(timezone.utc)
    active = datetime.fromisoformat(str(cart['last_active_at']).replace('Z', '+00:00'))
    step = int(((now-active).total_seconds()/60-limits['p_initial']) // limits['p_repeat'])
    pending = (cart.get('cart_payload') or {}).get('pending_order_id')
    if pending:
        query = db.table('orders').select('scheduled_for,is_scheduled').eq('id', pending).eq('campus_id', cart['campus_id'])
        query = query.eq('user_id', cart['user_id']) if cart.get('user_id') else query.is_('user_id', 'null').eq('guest_email', cart.get('guest_email'))
        order = query.single().execute() or {}
        if order.get('is_scheduled'): cart = {**cart, 'recovery_scheduled_for': order.get('scheduled_for')}
    return capture_cart(db, {**cart, 'recovery_step': step}, CalendarSnapshot(db), limits)


def notification_still_valid(db, snapshot, now=None):
    meta = (snapshot.get('metadata') or {}).get('cart_recovery')
    if not meta: return False
    now = now or datetime.now(timezone.utc)
    try:
        expires = datetime.fromisoformat(meta['deadline'].replace('Z', '+00:00'))
        if now >= expires: return False
    except (ValueError, KeyError, TypeError): return False
    cart = db.table('abandoned_carts').select('*').eq('id', meta['cart_id']).single().execute()
    if not cart or cart.get('is_recovered') or cart.get('user_id') != snapshot.get('user_id'): return False
    if now-datetime.fromisoformat(str(cart['last_active_at']).replace('Z', '+00:00')) >= timedelta(hours=48): return False
    newer = db.table('orders').select('id').eq('user_id', cart['user_id']).eq('campus_id', cart['campus_id']).eq('payment_status', 'pending').gt('created_at', cart['last_active_at']).limit(1).execute() or []
    if newer: return False
    latest = db.table('cart_items').select('updated_at').eq('user_id', cart['user_id']).eq('campus_id', cart['campus_id']).order('updated_at', ascending=False).limit(1).execute() or []
    if latest:
        return datetime.fromisoformat(latest[0]['updated_at'].replace('Z', '+00:00')) <= datetime.fromisoformat(cart['last_active_at'].replace('Z', '+00:00'))
    pending = (cart.get('cart_payload') or {}).get('pending_order_id')
    if not pending: return False
    order = db.table('orders').select('payment_status,status,user_id,is_test').eq('id', pending).single().execute() or {}
    return order.get('payment_status') == 'pending' and order.get('status') == 'received' and order.get('user_id') == cart['user_id'] and not order.get('is_test')
