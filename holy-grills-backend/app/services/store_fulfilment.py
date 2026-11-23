"""Resolve a campus's fulfilling store without duplicating its menu or schedule."""
from app.db import get_db
from app.messages import MSG
from app.services.feature_flags import is_feature_enabled
from app.utils.validators import validate_uuid

SNAPSHOT=('id','name','address','instructions','lat','lon')


def snapshot(row):return {key:row.get(key) for key in SNAPSHOT}


def options(campus_id,delivery_type,lat=None,lon=None):
    if delivery_type not in ('on_campus','off_campus','store_pickup'):raise ValueError(MSG.DELIVERY_TYPE_INVALID)
    if not campus_id or not is_feature_enabled('multi_store_ordering',campus_id):return {'enabled':False,'stores':[],'suggested_store_id':None}
    if (lat is None)!=(lon is None):raise ValueError(MSG.STORE_COORDINATES_INVALID)
    if lat is not None or lon is not None:
        from app.routes.delivery import validate_coordinates
        lat,lon=validate_coordinates(lat,lon)
    rows=get_db().rpc('hg_order_store_choices',{'p_campus':campus_id,'p_pickup':delivery_type=='store_pickup'}) or []
    for row in rows:
        row['distance_km']=None
        if lat is not None and row.get('lat') is not None and row.get('lon') is not None:
            from app.routes.delivery import haversine_km
            row['distance_km']=round(haversine_km(row['lat'],row['lon'],lat,lon),3)
    if lat is not None and rows:
        radius=campus_radius(campus_id)
        rows=[row for row in rows if row['distance_km'] is None or row['distance_km']<=radius]
    rows.sort(key=lambda row:(row['distance_km'] is None,row['distance_km'] if row['distance_km'] is not None else 0,row['id']))
    suggested=rows[0]['id'] if rows and (rows[0]['distance_km'] is not None or len(rows)==1) else None
    return {'enabled':True,'stores':rows,'suggested_store_id':suggested}


def resolve(campus_id,delivery_type,store_id=None,lat=None,lon=None):
    result=options(campus_id,delivery_type,lat,lon)
    if not result['enabled']:
        if store_id:raise ValueError(MSG.STORE_ORDERING_DISABLED)
        return None
    if store_id and (not isinstance(store_id,str) or not validate_uuid(store_id)):raise ValueError(MSG.STORE_ORDER_UNAVAILABLE)
    if not result['stores']:raise ValueError(MSG.STORE_NO_STORES)
    selected=store_id.lower() if store_id else result['suggested_store_id']
    row=next((row for row in result['stores'] if row['id']==selected),None)
    if not row:raise ValueError(MSG.STORE_ORDER_UNAVAILABLE if store_id else MSG.STORE_SELECT_REQUIRED)
    return snapshot(row)


def staff_may_access(actor_id,store_id,campus_id):
    """Service-role callers still verify fresh role/campus and membership."""
    if not store_id:return True  # Historical unassigned work retains its existing access rules.
    db=get_db()
    profile=db.table('profiles').select('role,campus_id,is_active').eq('id',actor_id).single().execute() or {}
    if not profile.get('is_active'):return False
    if profile.get('role')=='super_admin':return True
    if profile.get('campus_id')!=campus_id:return False
    if profile.get('role')=='admin':return True
    if profile.get('role') not in ('kitchen','rider'):return False
    return db.rpc('hg_staff_has_store',{'p_actor':actor_id,'p_store':store_id}) is True


def campus_radius(campus_id):
    import math
    row=get_db().table('kitchen_settings').select('value').eq('key','max_delivery_radius_km').eq('campus_id',campus_id).single().execute() or {}
    radius=float(row.get('value') or 15)
    if not math.isfinite(radius) or radius<=0:raise ValueError(MSG.STORE_ORDER_UNAVAILABLE)
    return radius


def within_radius(store,campus_id,lat,lon):
    from app.routes.delivery import haversine_km
    origin=store
    if origin.get('lat') is None or origin.get('lon') is None:
        origin=get_db().table('campuses').select('lat,lon').eq('id',campus_id).single().execute() or {}
        if origin.get('lat') is None or origin.get('lon') is None:return True
    return haversine_km(origin['lat'],origin['lon'],lat,lon)<=campus_radius(campus_id)
