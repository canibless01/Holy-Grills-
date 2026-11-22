"""Campus store-pickup configuration; existing settings and release flags only."""
from app.db import get_db
from app.messages import MSG
from app.services.feature_flags import is_feature_enabled

KEY = 'store_pickup_location'

def normalize_location(value):
    if not isinstance(value, dict) or set(value) - {'name','address','instructions'}:
        raise ValueError(MSG.STORE_PICKUP_CONFIG_INVALID)
    result = {}
    for key, limit in (('name',120),('address',500),('instructions',500)):
        item = value.get(key,'')
        if not isinstance(item,str) or len(item.strip())>limit:
            raise ValueError(MSG.STORE_PICKUP_CONFIG_INVALID)
        result[key]=item.strip()
    if not result['name'] or not result['address']:
        raise ValueError(MSG.STORE_PICKUP_CONFIG_INVALID)
    return result

def location_row(campus_id):
    if not campus_id:raise ValueError(MSG.STORE_PICKUP_CAMPUS_REQUIRED)
    return get_db().table('system_settings').select('key,value,updated_at').eq('key',KEY).eq('campus_id',campus_id).single().execute()

def pickup_option(campus_id):
    if not campus_id or not is_feature_enabled('store_pickup',campus_id):return {'enabled':False}
    row=location_row(campus_id)
    try:location=normalize_location((row or {}).get('value'))
    except ValueError:return {'enabled':False}
    return {'enabled':True,**location,'fee':0}

def require_pickup(campus_id):
    option=pickup_option(campus_id)
    if not option.get('enabled'):raise ValueError(MSG.STORE_PICKUP_UNAVAILABLE)
    return option
