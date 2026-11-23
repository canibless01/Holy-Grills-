"""Private store setup; operational cutover remains disabled until fully wired."""
from functools import wraps
import math
import re
from flask import Blueprint,g,jsonify,request
from app.db import get_db,SupabaseError
from app.messages import MSG
from app.middleware.auth import require_role,resolve_scoped_campus_id
from app.utils.validators import validate_uuid

stores_bp=Blueprint('stores',__name__)


def errors(fn):
    @wraps(fn)
    def handle(*args,**kwargs):
        try:return fn(*args,**kwargs)
        except ValueError as exc:return jsonify({'error':str(exc)}),400
        except SupabaseError as exc:
            text=str(exc)
            for code,message,status in [('HG_STORE_ACCESS',MSG.RESOURCE_ACCESS_DENIED,403),('HG_STORE_NOT_FOUND',MSG.STORE_NOT_FOUND,404),('HG_STORE_CONFLICT',MSG.STORE_EDIT_CONFLICT,409),('HG_STORE_STAFF_INVALID',MSG.STORE_STAFF_INVALID,400),('HG_STORE_CAMPUS_UNAVAILABLE',MSG.STORE_CAMPUS_UNAVAILABLE,400),('HG_STORE_UNIVERSITY_UNAVAILABLE',MSG.STORE_UNIVERSITY_UNAVAILABLE,400)]:
                if code in text:return jsonify({'error':message}),status
            if str((exc.details or {}).get('code'))=='23505':return jsonify({'error':MSG.STORE_DUPLICATE}),409
            raise
    return handle


def uuid(value):
    if not isinstance(value,str) or not validate_uuid(value):raise ValueError(MSG.INVALID_INPUT)
    return value.lower()


def body(keys):
    data=request.get_json(silent=True)
    if not isinstance(data,dict) or set(data)-set(keys):raise ValueError(MSG.INVALID_INPUT)
    return data


def campus(value=None):
    if value is not None:uuid(value)
    scope=resolve_scoped_campus_id(value)
    if scope is None:raise ValueError(MSG.STORE_CAMPUS_REQUIRED)
    return uuid(scope)


def text(data,key,limit,required=True):
    value=data.get(key,'' if not required else None)
    if not isinstance(value,str) or len(value.strip())>limit or (required and not value.strip()):raise ValueError(MSG.STORE_FIELD_INVALID.format(field=key))
    return value.strip()


def normalized(data,university=False):
    fields={'name':text(data,'name',160 if university else 120),'slug':text(data,'slug',80)}
    if not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*',fields['slug']):raise ValueError(MSG.STORE_SLUG_INVALID)
    for key in (('is_active',) if university else ('is_active','pickup_enabled','delivery_enabled')):
        if not isinstance(data.get(key,True),bool):raise ValueError(MSG.INVALID_INPUT)
        fields[key]=data.get(key,True)
    if university:return fields
    fields.update(address=text(data,'address',500),instructions=text(data,'instructions',500,False))
    for key,limit in [('lat',90),('lon',180)]:
        value=data.get(key)
        if value is not None:
            try:
                if isinstance(value,bool):raise ValueError
                value=float(value)
                if not math.isfinite(value) or abs(value)>limit:raise ValueError
            except (ValueError,TypeError):raise ValueError(MSG.STORE_COORDINATES_INVALID)
        fields[key]=value
    if (fields['lat'] is None)!=(fields['lon'] is None):raise ValueError(MSG.STORE_COORDINATES_INVALID)
    if fields['is_active'] and not fields['pickup_enabled'] and not fields['delivery_enabled']:raise ValueError(MSG.STORE_SERVICE_REQUIRED)
    return fields



def instant(value):
    from app.utils.admin_helpers import as_instant
    try:return as_instant(value)
    except ValueError:raise ValueError(MSG.STORE_EDIT_CONFLICT)

def scoped_store(store_id):
    row=get_db().table('stores').select('*').eq('id',uuid(store_id)).single().execute()
    if not row:return None
    if g.user_role!='super_admin' and row['campus_id']!=getattr(g,'campus_id',None):
        from flask import abort
        abort(403,MSG.RESOURCE_ACCESS_DENIED)
    return row


@stores_bp.get('/stores')
@require_role('admin')
@errors
def list_stores():
    value=request.args.get('campus_id')
    if value:uuid(value)
    selected=resolve_scoped_campus_id(value)
    if not selected and g.user_role!='super_admin':raise ValueError(MSG.STORE_CAMPUS_REQUIRED)
    query=get_db().table('stores').select('*').order('name').order('id')
    if selected:query=query.eq('campus_id',selected)
    from app.services.feature_flags import is_feature_enabled
    return jsonify({'stores':query.execute() or [],'ordering_enabled':is_feature_enabled('multi_store_ordering',selected) if selected else None})


@stores_bp.post('/stores')
@require_role('admin')
@errors
def create_store():
    data=body({'request_id','campus_id','name','slug','address','instructions','lat','lon','is_active','pickup_enabled','delivery_enabled'})
    result=get_db().rpc('hg_save_store',{'p_actor':g.user_id,'p_id':uuid(data.get('request_id')),'p_campus':campus(data.get('campus_id')),'p_data':normalized(data),'p_expected':None})
    return jsonify(result),201


@stores_bp.patch('/stores/<store_id>')
@require_role('admin')
@errors
def update_store(store_id):
    data=body({'expected_updated_at','name','slug','address','instructions','lat','lon','is_active','pickup_enabled','delivery_enabled'})
    row=scoped_store(store_id)
    if not row:return jsonify({'error':MSG.STORE_NOT_FOUND}),404
    expected=instant(data.get('expected_updated_at'))
    return jsonify(get_db().rpc('hg_save_store',{'p_actor':g.user_id,'p_id':row['id'],'p_campus':row['campus_id'],'p_data':normalized(data),'p_expected':expected}))


@stores_bp.get('/stores/<store_id>/staff')
@require_role('admin')
@errors
def store_staff(store_id):
    row=scoped_store(store_id)
    if not row:return jsonify({'error':MSG.STORE_NOT_FOUND}),404
    db=get_db()
    assigned=db.rpc('hg_store_staff',{'p_actor':g.user_id,'p_store':row['id']}) or []
    eligible=db.table('profiles').select('id,full_name,nickname,email,role').eq('campus_id',row['campus_id']).eq('is_active',True).in_('role',['kitchen','rider']).order('full_name').limit(200).execute() or []
    return jsonify({'store':row,'assigned':assigned,'eligible':eligible})


@stores_bp.patch('/stores/<store_id>/staff')
@require_role('admin')
@errors
def set_store_staff(store_id):
    data=body({'user_ids','expected_updated_at'})
    row=scoped_store(store_id)
    if not row:return jsonify({'error':MSG.STORE_NOT_FOUND}),404
    ids=data.get('user_ids')
    if not isinstance(ids,list) or len(ids)>100 or len(set(uuid(value) for value in ids))!=len(ids):raise ValueError(MSG.STORE_STAFF_INVALID)
    return jsonify(get_db().rpc('hg_set_store_staff',{'p_actor':g.user_id,'p_store':row['id'],'p_users':ids,'p_expected':instant(data.get('expected_updated_at'))}))


@stores_bp.get('/universities')
@require_role('admin')
@errors
def universities():
    return jsonify({'universities':get_db().table('universities').select('*').order('name').execute() or []})


@stores_bp.post('/universities')
@require_role('super_admin')
@errors
def create_university():
    data=body({'request_id','name','slug','is_active'})
    return jsonify(get_db().rpc('hg_save_university',{'p_actor':g.user_id,'p_id':uuid(data.get('request_id')),'p_data':normalized(data,True),'p_expected':None})),201


@stores_bp.patch('/universities/<university_id>')
@require_role('super_admin')
@errors
def update_university(university_id):
    data=body({'expected_updated_at','name','slug','is_active'})
    return jsonify(get_db().rpc('hg_save_university',{'p_actor':g.user_id,'p_id':uuid(university_id),'p_data':normalized(data,True),'p_expected':instant(data.get('expected_updated_at'))}))


@stores_bp.patch('/campuses/<campus_id>/university')
@require_role('super_admin')
@errors
def link_campus(campus_id):
    data=body({'university_id','expected_updated_at'})
    return jsonify(get_db().rpc('hg_link_university_campus',{'p_actor':g.user_id,'p_campus':uuid(campus_id),'p_university':uuid(data['university_id']) if data.get('university_id') else None,'p_expected':instant(data.get('expected_updated_at'))}))


@stores_bp.get('/store-analytics')
@require_role('admin')
@errors
def store_analytics():
    selected=resolve_scoped_campus_id(request.args.get('campus_id'))
    if selected:uuid(selected)
    if not selected and g.user_role!='super_admin':raise ValueError(MSG.STORE_CAMPUS_REQUIRED)
    store=request.args.get('store_id')
    from datetime import datetime,timedelta,timezone
    end=datetime.now(timezone.utc)
    start=end-timedelta(days=30)
    first=instant(request.args['start']) if request.args.get('start') else start.isoformat()
    last=instant(request.args['end']) if request.args.get('end') else end.isoformat()
    if datetime.fromisoformat(first)>=datetime.fromisoformat(last) or datetime.fromisoformat(last)-datetime.fromisoformat(first)>timedelta(days=366):raise ValueError(MSG.STORE_REPORT_RANGE)
    return jsonify(get_db().rpc('hg_store_analytics',{'p_actor':g.user_id,'p_campus':selected,'p_store':uuid(store) if store else None,'p_start':first,'p_end':last}))


@stores_bp.get('/work-stores')
@require_role('kitchen','rider','admin')
@errors
def work_stores():
    selected=campus(request.args.get('campus_id'))
    return jsonify({'stores':get_db().rpc('hg_actor_stores',{'p_actor':g.user_id,'p_campus':selected}) or []})
