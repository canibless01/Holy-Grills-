"""Birthday rewards/notices share a durable annual receipt; staff mail uses the ops outbox."""
from flask import current_app
from app.db import get_db
from app.services.feature_flags import is_feature_enabled
from app.services.tier_service import resolve_perk
from app.utils.settings import get_validated_setting


def process_birthdays():
    db = get_db()
    results = {'processed': 0, 'hp_awarded': 0, 'batches': 0, 'skipped_profiles': 0}
    for _ in range(20):
        people = db.rpc('hg_due_birthdays', {'p_limit': 200}) or []
        if not people:
            return results
        results['batches'] += 1
        for person in people:
            amount = 0
            if is_feature_enabled('birthday_hp', person['campus_id']):
                base = int(get_validated_setting(db, 'birthday_hp', default=current_app.config.get('BIRTHDAY_HP', 150), minimum=0, campus_id=person['campus_id']))
                perk = resolve_perk(person['id'], 'birthday_hp')
                amount = int(perk) if perk is not None and perk > 0 else base
            result = db.rpc('hg_process_birthday', {'p_user': person['id'], 'p_hp': amount})
            if isinstance(result, dict) and result.get('skipped'):
                results['skipped_profiles'] += 1
                continue
            if not isinstance(result, dict) or not (result.get('processed') or result.get('replayed')):
                raise RuntimeError('Birthday capture remains pending')
            results['processed'] += int(bool(result.get('processed')))
            if result.get('processed'):
                results['hp_awarded'] += int(result.get('hp_awarded') or 0)
        if len(people) < 200:
            return results
    # A bound is explicit; do not mark a large unfinished birthday batch complete.
    raise RuntimeError('Birthday capture has more pending batches')


def queue_monthly_report():
    db = get_db()
    result = db.rpc('hg_queue_birthday_reports', {})
    if not isinstance(result, dict):
        raise RuntimeError('Monthly birthday capture remains pending')
    from app.services.operations_email import dispatch_pending
    return {**result, 'delivery': dispatch_pending(db)}
