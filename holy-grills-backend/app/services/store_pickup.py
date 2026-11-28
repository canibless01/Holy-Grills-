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

def pickup_option(campus_id,store_id=None):
    if not campus_id or not is_feature_enabled('store_pickup',campus_id):return {'enabled':False}
    if is_feature_enabled('multi_store_ordering',campus_id):
        from app.services.store_fulfilment import resolve
        if not store_id:
            from app.services.store_fulfilment import options
            choices=options(campus_id,'store_pickup')
            if not choices['stores']:return {'enabled':False}
            if len(choices['stores'])>1:return {'enabled':True,'requires_store_selection':True,'name':MSG.STORE_PICKUP_CHOOSE_LOCATION,'address':'','instructions':'','fee':0}
        store=resolve(campus_id,'store_pickup',store_id)
        if not store:return {'enabled':False}
        return {'enabled':True,**store,'fee':0,'store':store}
    if store_id:raise ValueError(MSG.STORE_ORDERING_DISABLED)
    row=location_row(campus_id)
    try:location=normalize_location((row or {}).get('value'))
    except ValueError:return {'enabled':False}
    return {'enabled':True,**location,'fee':0}

def require_pickup(campus_id,store_id=None):
    option=pickup_option(campus_id,store_id)
    if not option.get('enabled'):raise ValueError(MSG.STORE_PICKUP_UNAVAILABLE)
    if option.get('requires_store_selection'):raise ValueError(MSG.STORE_SELECT_REQUIRED)
    return option
