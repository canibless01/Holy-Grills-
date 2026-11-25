"""An optional view filter. Database RLS independently enforces membership."""
from flask import request,g,abort
from app.db import get_db,get_user_client
from app.messages import MSG
from app.utils.validators import validate_uuid
from app.services.store_fulfilment import staff_may_access


def client(db=None):
    body=request.get_json(silent=True)
    store_id=request.args.get('store_id') or (body.get('store_id') if isinstance(body,dict) else None)
    db=db if db is not None else get_user_client()
    if not store_id:return db
    if not isinstance(store_id,str) or not validate_uuid(store_id):abort(400,MSG.INVALID_INPUT)
    store=get_db().table('stores').select('campus_id').eq('id',store_id).single().execute() or {}
    if not store or not staff_may_access(g.user_id,store_id,store['campus_id']):abort(403,MSG.RESOURCE_ACCESS_DENIED)
    class ScopedRead:
        def table(self,name):
            query=db.table(name)
            return query.eq('store_id',store_id) if name in ('orders','delivery_batches') else query
        def __getattr__(self,name):return getattr(db,name)
    return ScopedRead()
