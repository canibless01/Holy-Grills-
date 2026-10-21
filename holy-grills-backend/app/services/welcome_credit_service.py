"""Welcome free-side configuration and a replay-safe grant through the existing credit ledger."""
from app.db import get_db
from app.messages import MSG

CONFIG_KEY = 'signup_free_side_config'
DEFAULT_CONFIG = {'enabled': True, 'credits': 1, 'validity_days': 60}


def validate_config(value):
    if not isinstance(value, dict) or set(value) != set(DEFAULT_CONFIG):
        raise ValueError(MSG.WELCOME_CREDIT_CONFIG_INVALID)
    if not isinstance(value['enabled'], bool):
        raise ValueError(MSG.WELCOME_CREDIT_CONFIG_INVALID)
    for key, maximum in (('credits', 10), ('validity_days', 365)):
        if type(value[key]) is not int or not 1 <= value[key] <= maximum:
            raise ValueError(MSG.WELCOME_CREDIT_CONFIG_INVALID)
    return dict(value)


def read_config(db, campus_id=None):
    query = db.table('system_settings').select('value').eq('key', CONFIG_KEY)
    row = (query.eq('campus_id', campus_id) if campus_id else query.is_('campus_id', 'null')).single().execute()
    if row:
        return validate_config(row['value']), False
    if campus_id:
        config, _ = read_config(db)
        return config, True
    return dict(DEFAULT_CONFIG), True


def grant_signup_credit(user_id):
    result = get_db().rpc('hg_grant_signup_free_side_atomic', {'p_user_id': user_id})
    if not isinstance(result, dict) or result.get('error'):
        raise RuntimeError(MSG.WELCOME_CREDIT_UNAVAILABLE)
    return result
