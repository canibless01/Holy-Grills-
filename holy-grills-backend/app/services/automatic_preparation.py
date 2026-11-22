"""Start paid, due-day preparation after its own effective ordering cutoff.

Uses the normal compare-and-set status path. No ready/dispatch/collection or HP
is fabricated, and simultaneous scans cannot apply a transition twice.
"""
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo
from app.db import get_db
from app.messages import MSG
from app.services.feature_flags import is_feature_enabled
from app.utils.schedule import effective_windows_with_config
from app.utils.logger import get_logger

WAT = ZoneInfo('Africa/Lagos')
logger = get_logger(__name__)


def closed_windows(db, campus, now):
    rows, _ = effective_windows_with_config(db, campus, now.date().isoformat(), now.weekday(), strict=True)
    closed = []
    for row in rows:
        if row.get('is_closed'):
            continue  # An all-day/manual closure is not a timed preparation promise.
        opening = time.fromisoformat(str(row['opens_at']))
        closing = time.fromisoformat(str(row['closes_at']))
        if closing <= opening:
            continue  # Existing ordering windows do not support overnight cutoffs.
        if now >= datetime.combine(now.date(), closing, tzinfo=WAT):
            closed.append(row.get('id'))
    return closed


def prepare_closed_windows():
    from app.services.order_service import update_order_status, OrderConflictError, OrderForbiddenError, OrderNotFoundError
    db = get_db()
    now = datetime.now(WAT)
    start = datetime.combine(now.date(), time.min, tzinfo=WAT).isoformat()
    end = datetime.combine(now.date() + timedelta(days=1), time.min, tzinfo=WAT).isoformat()
    results = {}
    campuses = db.table('campuses').select('id').eq('is_active', True).execute() or []
    for campus in campuses:
        campus_id = campus['id']
        if not is_feature_enabled('auto_prepare_closed_windows', campus_id):
            continue
        try:
            windows = closed_windows(db, campus_id, now)
            if not windows:
                results[campus_id] = {'prepared': 0}
                continue
            ids = [str(value) for value in windows if value]
            query = (db.table('orders').select('id,ordering_window_id,is_scheduled,scheduled_for,created_at')
                     .eq('campus_id', campus_id).eq('is_test', False)
                     .in_('status', ['received', 'paid']).in_('payment_status', ['paid', 'partially_refunded']))
            if ids and None in windows:
                query = query.or_('ordering_window_id.is.null,ordering_window_id.in.(' + ','.join(ids) + ')')
            elif ids:
                query = query.in_('ordering_window_id', ids)
            else:
                query = query.is_('ordering_window_id', 'null')
            query = query.or_(f'and(is_scheduled.eq.true,scheduled_for.gte.{start},scheduled_for.lt.{end}),and(is_scheduled.eq.false,created_at.gte.{start},created_at.lt.{end})')
            rows = query.order('created_at').order('id').limit(200).execute() or []
            prepared = skipped = failed = 0
            for order in rows:
                try:
                    result = update_order_status(order['id'], 'preparing', notes=MSG.ORDER_AUTO_PREPARATION_NOTE, _system_task=True)
                    prepared += not result.get('unchanged', False)
                    skipped += bool(result.get('unchanged', False))
                except (OrderConflictError, OrderForbiddenError, OrderNotFoundError):
                    skipped += 1  # Another worker/staff action or financial exit won.
                except Exception:
                    failed += 1
                    logger.exception('Automatic preparation deferred for order %s', order['id'])
            results[campus_id] = {'prepared': prepared, 'skipped': skipped, 'failed': failed}
            if failed:
                results[campus_id]['error'] = 'preparation_retry_pending'
        except Exception:
            logger.exception('Automatic preparation scan failed for campus %s', campus_id)
            results[campus_id] = {'error': 'preparation_scan_failed'}
    return results
