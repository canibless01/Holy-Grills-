"""One active gift bundle per scope; earned bundles use existing benefit ledgers."""
from datetime import datetime, timezone
from decimal import Decimal
from app.db import get_db
from app.messages import MSG
from app.utils.validators import validate_uuid

CONFIG_KEY = 'order_gift_campaign'
DEFAULT = {'id': None, 'name': '', 'enabled': False, 'eligibility': 'first_order',
           'starts_at': None, 'ends_at': None, 'validity_days': 60, 'benefits': []}


def validate_config(value):
    if not isinstance(value, dict) or set(value) != set(DEFAULT):
        raise ValueError(MSG.GIFT_CAMPAIGN_INVALID)
    if not validate_uuid(value.get('id')) or not isinstance(value['enabled'], bool):
        raise ValueError(MSG.GIFT_CAMPAIGN_INVALID)
    name = value['name']
    if not isinstance(name, str) or not 1 <= len(name.strip()) <= 100:
        raise ValueError(MSG.GIFT_CAMPAIGN_INVALID)
    if value['eligibility'] not in ('signup', 'first_order', 'everyone'):
        raise ValueError(MSG.GIFT_CAMPAIGN_INVALID)
    if type(value['validity_days']) is not int or not 1 <= value['validity_days'] <= 365:
        raise ValueError(MSG.GIFT_CAMPAIGN_INVALID)
    normalized = dict(value, name=name.strip())
    instants = []
    for key in ('starts_at', 'ends_at'):
        try:
            stamp = datetime.fromisoformat(str(value[key]).replace('Z', '+00:00'))
            if stamp.tzinfo is None: raise ValueError()
        except (TypeError, ValueError): raise ValueError(MSG.GIFT_CAMPAIGN_INVALID)
        normalized[key] = stamp.astimezone(timezone.utc).isoformat()
        instants.append(stamp)
    if not instants[0] < instants[1]: raise ValueError(MSG.GIFT_CAMPAIGN_INVALID)
    benefits = value['benefits']
    if not isinstance(benefits, list) or not 1 <= len(benefits) <= 4:
        raise ValueError(MSG.GIFT_CAMPAIGN_INVALID)
    seen, cleaned = set(), []
    fields = {'hp': {'amount'}, 'free_side': {'credits'}, 'delivery_discount': {'percent', 'cap'},
              'hp_multiplier': {'multiplier'}}
    for item in benefits:
        if not isinstance(item, dict): raise ValueError(MSG.GIFT_CAMPAIGN_INVALID)
        kind = item.get('kind')
        if not isinstance(kind, str) or kind not in fields or kind in seen or set(item) - {'kind', 'label'} != fields[kind]:
            raise ValueError(MSG.GIFT_CAMPAIGN_INVALID)
        seen.add(kind); entry = {'kind': kind}
        for key in fields[kind]:
            raw = item[key]
            if isinstance(raw, bool) or not isinstance(raw, (int, float)):
                raise ValueError(MSG.GIFT_CAMPAIGN_INVALID)
            number = Decimal(str(raw))
            bounds = {'amount': (1, 100000), 'credits': (1, 10), 'percent': (1, 100),
                      'cap': (1, 100000), 'multiplier': (1.01, 10)}
            low, high = bounds[key]
            if not number.is_finite() or not Decimal(str(low)) <= number <= Decimal(str(high)):
                raise ValueError(MSG.GIFT_CAMPAIGN_INVALID)
            if key in ('amount', 'credits') and type(raw) is not int:
                raise ValueError(MSG.GIFT_CAMPAIGN_INVALID)
            if number != number.quantize(Decimal('.01')):
                raise ValueError(MSG.GIFT_CAMPAIGN_INVALID)
            entry[key] = raw
        templates = {'hp': MSG.GIFT_LABEL_HP, 'free_side': MSG.GIFT_LABEL_SIDE,
                     'delivery_discount': MSG.GIFT_LABEL_DELIVERY, 'hp_multiplier': MSG.GIFT_LABEL_MULTIPLIER}
        entry['label'] = templates[kind].format(**entry)
        cleaned.append(entry)
    return {**normalized, 'benefits': cleaned}


def read_config(db, campus_id=None):
    query = db.table('system_settings').select('value,updated_at').eq('key', CONFIG_KEY)
    row = (query.eq('campus_id', campus_id) if campus_id else query.is_('campus_id', 'null')).single().execute()
    if row: return validate_config(row['value']), row.get('updated_at'), False
    if campus_id:
        config, _, _ = read_config(db)
        return config, None, True
    return dict(DEFAULT), None, True


def eligible_preview(db, user_id, config, verified_auth_user):
    """Read-only UI hint; the locked grant transaction remains authoritative."""
    starts = datetime.fromisoformat(config['starts_at'])
    if config['eligibility'] == 'everyone': return True
    if config['eligibility'] == 'signup':
        created = (verified_auth_user or {}).get('created_at')
        return bool(created and datetime.fromisoformat(str(created).replace('Z', '+00:00')) >= starts)
    rows = (db.table('orders').select('id,paid_at,created_at').eq('user_id', user_id)
            .in_('payment_status', ['paid', 'partially_refunded', 'refunded']).limit(2).execute()) or []
    if len(rows) > 1: return False
    if not rows: return True
    stamp = rows[0].get('paid_at') or rows[0].get('created_at')
    return bool(stamp and datetime.fromisoformat(str(stamp).replace('Z', '+00:00')) >= starts)


def features_ready(db, config):
    if not any(item['kind'] == 'free_side' for item in config['benefits']): return True
    flag = db.table('feature_flags').select('is_active').eq('feature_name', 'free_side_credits').is_('campus_id', 'null').single().execute()
    return bool(flag and flag.get('is_active') is True)


def claim(user_id, expected_campaign_id=None):
    if expected_campaign_id is not None and not validate_uuid(expected_campaign_id):
        raise ValueError(MSG.GIFT_CAMPAIGN_INVALID)
    result = get_db().rpc('hg_claim_gift_campaign_atomic', {
        'p_user_id': user_id, 'p_expected_campaign_id': expected_campaign_id,
    })
    if not isinstance(result, dict) or result.get('error'):
        raise RuntimeError(MSG.GIFT_CAMPAIGN_UNAVAILABLE)
    if result.get('granted'):
        try:
            from app.services.notification_service import send_notification
            send_notification(user_id, 'gift_campaign_granted', title=MSG.GIFT_CAMPAIGN_GRANTED,
                body=MSG.GIFT_CAMPAIGN_GRANTED_BODY.format(name=result['name']),
                reference_id=result['receipt_id'], reference_type='gift_campaign', action_url='/rewards')
        except Exception:
            pass  # Grant is committed; notification dispatch never instructs a second grant.
    return result
