"""Campus repeating pushes backed by atomic receipts and the existing outbox."""
import re
from datetime import date, datetime, timedelta, timezone
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo
from app.messages import MSG
from app.services.ambassador_promotions import image_url
from app.utils.logger import get_logger

WAT = ZoneInfo('Africa/Lagos')
logger = get_logger(__name__)
TOKENS = frozenset({'nickname', 'name', 'campus', 'order_cutoff'})
LINK = re.compile(r'^/(menu|dashboard|rewards|wallet|events|orders|leaderboard)(/[a-zA-Z0-9_-]+)?$')


def defaults():
    return {'id': str(uuid4()), 'name': MSG.ENGAGEMENT_CAMPAIGN_DEFAULT_NAME,
            'revision': 0, 'is_active': False, 'start_date': datetime.now(WAT).date().isoformat(),
            'morning_time': '09:00', 'afternoon_time': '15:00',
            'steps': [{'day': day, 'slot': slot,
                       'title': getattr(MSG, f'CYCLE_{day}_{slot.upper()}_TITLE'),
                       'body': getattr(MSG, f'CYCLE_{day}_{slot.upper()}_BODY'), 'action_url': '/menu', 'push_image': None}
                      for day in range(1, 15) for slot in ('morning', 'afternoon')]}


def validate(values):
    if not isinstance(values, dict):
        raise ValueError(MSG.ENGAGEMENT_CAMPAIGN_INVALID)
    try:
        UUID(values['id']); date.fromisoformat(values['start_date'])
        am = datetime.strptime(values['morning_time'][:5], '%H:%M').time()
        pm = datetime.strptime(values['afternoon_time'][:5], '%H:%M').time()
        assert am.hour < 12 <= pm.hour and am < pm
        assert type(values['revision']) is int and values['revision'] >= 0
        assert type(values['is_active']) is bool
        assert isinstance(values['name'], str) and 1 <= len(values['name'].strip()) <= 100
        assert isinstance(values['steps'], list) and len(values['steps']) == 28
        assert {(s['day'], s['slot']) for s in values['steps']} == {(d, slot) for d in range(1, 15) for slot in ('morning', 'afternoon')}
        for step in values['steps']:
            assert type(step['day']) is int
            for key, limit in [('title', 100), ('body', 500)]:
                text = step[key]
                assert isinstance(text, str) and 1 <= len(text.strip()) <= limit
                assert all(t.strip() in TOKENS for t in re.findall(r'{{(.*?)}}', text))
                assert '{{' not in re.sub(r'{{(.*?)}}', '', text) and '}}' not in re.sub(r'{{(.*?)}}', '', text)
            assert isinstance(step['action_url'], str) and LINK.fullmatch(step['action_url'])
            try:
                image_url(step.get('push_image'))
            except Exception:
                raise ValueError(MSG.ENGAGEMENT_CAMPAIGN_INVALID) from None
    except (KeyError, TypeError, ValueError, AssertionError, AttributeError):
        raise ValueError(MSG.ENGAGEMENT_CAMPAIGN_INVALID) from None
    return {k: values[k] for k in ('id', 'revision', 'name', 'start_date', 'morning_time', 'afternoon_time', 'is_active', 'steps')}


def render(step, profile, campus, cutoff):
    name = ' '.join(str(profile.get('full_name') or '').split())[:40]
    nickname = ' '.join(str(profile.get('nickname') or '').split())[:40] or (name.split(' ')[0] if name else MSG.ENGAGEMENT_CAMPAIGN_FRIEND)
    tokens = {'nickname': nickname, 'name': name or nickname, 'campus': campus, 'order_cutoff': cutoff}
    def replace(text):
        return re.sub(r'{{(.*?)}}', lambda m: str(tokens[m.group(1).strip()]), text)
    return {'title': replace(step['title']), 'body': replace(step['body']),
            'action_url': step['action_url'], 'push_image': step.get('push_image')}


def ordering_cutoff(db, campus_id, now=None):
    """Fail closed on schedule reads; reuse checkout's capacity/override rules."""
    from app.utils.schedule import effective_windows_with_config
    from app.services.order_service import get_ordering_window_status
    now = (now or datetime.now(timezone.utc)).astimezone(WAT)
    windows, _ = effective_windows_with_config(db, campus_id, now.date().isoformat(), now.weekday(), strict=True)
    strict_closes = []
    for window in windows:
        opens = datetime.combine(now.date(), datetime.strptime(str(window.get('opens_at') or '00:00')[:5], '%H:%M').time(), WAT)
        closes = datetime.combine(now.date(), datetime.strptime(str(window.get('closes_at') or '23:59')[:5], '%H:%M').time(), WAT)
        if not window.get('is_closed') and opens <= now < closes:
            strict_closes.append(closes)
    if not strict_closes:
        return None
    status = get_ordering_window_status(db, campus_id)
    if status.get('is_open') is not True:
        return None
    closes = [datetime.combine(now.date(), datetime.strptime(w['closes_at'][:5], '%H:%M').time(), WAT)
              for w in status.get('windows', []) if w.get('is_open_now') and w.get('closes_at')]
    return min(closes + strict_closes) if closes else None


def enqueue_due(db, campus_id=None):
    """Bounded pages per campus/slot. Repeated cron ticks finish work, never replay."""
    if campus_id is not None:
        UUID(campus_id)
    now = datetime.now(timezone.utc)
    configs = db.rpc('hg_due_engagement_campaigns', {})
    if not isinstance(configs, list):
        raise RuntimeError('campaign_read_unavailable')
    configs = [c for c in configs if campus_id is None or c['campus_id'] == campus_id]
    counts = {'campaigns': len(configs), 'queued': 0, 'skipped': 0}
    for config in configs:
        try:
            cutoff = ordering_cutoff(db, config['campus_id'], now)
            if not cutoff:
                counts['skipped'] += 1
                continue
            validate(config)
            scheduled = datetime.fromisoformat(config['scheduled_at'].replace('Z', '+00:00'))
            expires = min(cutoff, scheduled + timedelta(minutes=45))
            step = next(s for s in config['steps'] if s['day'] == config['cycle_day'] and s['slot'] == config['slot'])
            after = None
            for _ in range(5):  # Max 1,000 recipients per slot per tick; no unbounded worker.
                people = db.rpc('hg_engagement_campaign_recipients', {'p_campaign': config['id'], 'p_slot': config['slot'], 'p_after': after})
                if not isinstance(people, list):
                    raise RuntimeError('campaign_recipients_unavailable')
                if not people:
                    break
                result = db.rpc('hg_enqueue_engagement_campaign', {
                    'p_campaign': config['id'], 'p_revision': config['revision'], 'p_slot': config['slot'],
                    'p_expires': expires.isoformat(), 'p_messages': [dict(user_id=p['id'], **render(step, p, config['campus_name'], cutoff.strftime('%H:%M'))) for p in people]})
                if not isinstance(result, dict) or result.get('error'):
                    break
                counts['queued'] += result.get('queued', 0)
                after = people[-1]['id']
                if len(people) < 200:
                    break
        except Exception as exc:
            logger.warning('Engagement cycle skipped safely: %s', type(exc).__name__)
            counts['skipped'] += 1
    return counts


def dispatch_ttl(db, snapshot, now=None):
    """Revalidate revision, user and operating state just before provider dispatch."""
    now = now or datetime.now(timezone.utc)
    meta = snapshot.get('metadata') or {}
    expires = datetime.fromisoformat(meta['expires_at'].replace('Z', '+00:00'))
    if expires <= now:
        return 0
    if db.rpc('hg_engagement_campaign_notice_valid', {'p_campaign': meta['campaign_id'], 'p_revision': meta['campaign_revision'], 'p_user': snapshot['user_id']}) is not True:
        return 0
    cutoff = ordering_cutoff(db, snapshot.get('campus_id') or db.table('profiles').select('campus_id').eq('id', snapshot['user_id']).single().execute()['campus_id'], now)
    return max(0, int((min(expires, cutoff) - now).total_seconds())) if cutoff else 0
