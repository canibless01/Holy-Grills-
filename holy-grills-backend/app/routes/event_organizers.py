"""Owned organizer drafts, attendance and separate manual bank-settlement records."""
import uuid
from flask import Blueprint,request,jsonify,g
from app.db import get_db,SupabaseError
from app.middleware.auth import require_role,resolve_scoped_campus_id,header_campus_id
from app.utils.admin_helpers import as_text,as_int,as_instant,as_number,page_args,db_error_response
from app.utils.campus_scope import as_campus_id
from app.utils.validators import validate_uuid,validate_datetime_order
from app.utils.upload_urls import is_trusted_upload_url
from app.services.event_admission import admit_event_ticket
from app.messages import MSG
from app.utils.logger import get_logger

bp=Blueprint('event_organizers',__name__)
logger=get_logger(__name__)
ROLES=('event_organizer','admin')
ERRORS={
 'HG_EVENT_CHANGE_STALE':('EVENT_CHANGE_STALE',409),
 'HG_EVENT_CHANGE_INVALID':('EVENT_CHANGE_INVALID',400),
 'HG_EVENT_ALREADY_CANCELLED':('EVENT_ALREADY_CANCELLED',409),
 'HG_EVENT_ADMISSION_STARTED':('EVENT_CHANGE_ADMISSION_STARTED',409),
 'HG_EVENT_CHANGE_UNCHANGED':('EVENT_CHANGE_UNCHANGED',400),
 'HG_ORGANIZER_ACCESS':('RESOURCE_ACCESS_DENIED',403),
 'HG_ORGANIZER_NOT_FOUND':('EVENT_NOT_FOUND',404),
 'HG_ORGANIZER_REVIEW_LOCKED':('ORG_REVIEW_LOCKED',409),
 'HG_ORGANIZER_DATES':('ORG_DATES_INVALID',400),
 'HG_ORGANIZER_CONFLICT':('ORG_CONFLICT',409),
 'HG_ORGANIZER_OWNER_INVALID':('ORG_OWNER_INVALID',400),
 'HG_ORGANIZER_OWNER_HAS_TICKETS':('ORG_OWNER_HAS_TICKETS',409),
 'HG_ORGANIZER_TERMS_REQUIRED':('ORG_TERMS_REQUIRED',400),
 'HG_ORGANIZER_PAYOUT_NOT_DUE':('ORG_PAYOUT_NOT_DUE',409),
 'HG_ORGANIZER_NO_BALANCE':('ORG_NO_BALANCE',409),
 'HG_ORGANIZER_BALANCE_CHANGED':('ORG_BALANCE_CHANGED',409),
 'HG_ORGANIZER_BANK_INVALID':('ORG_BANK_INVALID',400),
 'HG_ORGANIZER_REFERENCE_REQUIRED':('ORG_REFERENCE_REQUIRED',400),
 'HG_ORGANIZER_INVALID':('INVALID_INPUT',400),
}

def _failure(exc):
 if 'HG_EVENT_CHANGE_STALE' in str(exc):return jsonify({'error':MSG.EVENT_CHANGE_STALE,'code':'event_changed'}),409
 if 'Events disabled' in str(exc):return jsonify({'error':MSG.EVENT_RELEASE_CLOSED}),403
 if any(text in str(exc) for text in ('Event not available','Ticket not admissible')):return jsonify({'error':MSG.EVENT_TICKET_NOT_ADMISSIBLE}),409
 if any(text in str(exc) for text in ('Ticket financial breakdown invalid','Confirmed card payment receipt required','Guest ticket financial breakdown invalid')):return jsonify({'error':MSG.EVENT_CHANGE_FINANCIAL_REVIEW}),409
 for marker,(key,status) in ERRORS.items():
  if marker in str(exc):return jsonify({'error':getattr(MSG,key)}),status
 return db_error_response(exc,'event_organizer')

def _rpc(name,body):
 if name in ('hg_organizer_event_draft','hg_review_organizer_event','hg_event_payout_action'):
  body={**body,'p_data':{**body.get('p_data',{}),'_notice':{'title':MSG.ORG_NOTICE_TITLE,'body':MSG.ORG_NOTICE_BODY}}}
 return get_db().rpc(name,{**body,'p_actor':g.user_id})

def _object():
 value=request.get_json(silent=True)
 if not isinstance(value,dict):raise ValueError
 return value

def _uuid(value):
 if not isinstance(value,str) or not validate_uuid(value):raise ValueError
 return value

def _draft(data):
 if set(data)-{'request_id','title','description','location','starts_at','ends_at','capacity','image_url'}:raise ValueError
 clean={key:as_text(data.get(key),200 if key=='title' else 500) for key in ('title','location')}
 if data.get('description') is not None and not isinstance(data['description'],str):raise ValueError
 clean['description']=(data.get('description') or '').strip()[:5000]
 clean['starts_at']=as_instant(data.get('starts_at'));clean['ends_at']=as_instant(data.get('ends_at'))
 if not validate_datetime_order(clean['starts_at'],clean['ends_at'])[0]:raise ValueError
 clean['capacity']=as_int(data.get('capacity'),1,1000000)
 clean['image_url']=data.get('image_url') or None
 if clean['image_url'] and not is_trusted_upload_url(clean['image_url']):raise ValueError
 return clean

def _notice(event,kind,receipt=None):
 """Only wake already committed pushes; the durable worker recovers a lost wake."""
 import threading
 from flask import current_app
 from app.services.notification_outbox import dispatch_notification
 try:
  rows=get_db().table('notifications').select('id').eq('metadata->>organizer_event_id',event['id']).eq('channel','push').order('created_at',ascending=False).limit(50).execute() or []
  app=current_app._get_current_object()
  def wake():
   with app.app_context():
    for row in rows:dispatch_notification(row['id'])
  if rows:threading.Thread(target=wake,daemon=True).start()
 except Exception:logger.warning('Organizer push wake deferred for %s',event['id'])

@bp.route('/events',methods=['GET'])
@require_role(*ROLES)
def list_owned_events():
 try:
  limit,offset=page_args();selected=as_campus_id(request.args.get('campus_id'))
 except ValueError:return jsonify({'error':MSG.INVALID_INPUT}),400
 q=get_db().table('events').select('*')
 if g.user_role=='event_organizer':q=q.eq('organizer_id',g.user_id)
 else:
  campus=resolve_scoped_campus_id(selected)
  if campus:q=q.eq('campus_id',campus)
 rows=q.order('created_at',ascending=False).order('id',ascending=False).limit(limit+1).offset(offset).execute() or []
 return jsonify({'events':rows[:limit],'has_more':len(rows)>limit}),200

@bp.route('/events',methods=['POST'])
@require_role(*ROLES)
def create_draft():
 try:
  data=_object();event_id=_uuid(data.get('request_id'));body=_draft(data)
  if g.user_role=='super_admin':body['campus_id']=header_campus_id()
  result=_rpc('hg_organizer_event_draft',{'p_event':event_id,'p_action':'create','p_data':body})
  return jsonify(result),201
 except ValueError:return jsonify({'error':MSG.ORG_DRAFT_INVALID}),400
 except SupabaseError as exc:return _failure(exc)

@bp.route('/events/<event_id>',methods=['PATCH'])
@require_role(*ROLES)
def edit_draft(event_id):
 try:
  result=_rpc('hg_organizer_event_draft',{'p_event':_uuid(event_id),'p_action':'edit','p_data':_draft(_object())})
  return jsonify(result),200
 except ValueError:return jsonify({'error':MSG.ORG_DRAFT_INVALID}),400
 except SupabaseError as exc:return _failure(exc)

@bp.route('/events/<event_id>/submit',methods=['POST'])
@require_role(*ROLES)
def submit_draft(event_id):
 try:
  result=_rpc('hg_organizer_event_draft',{'p_event':_uuid(event_id),'p_action':'submit','p_data':{}})
  _notice(result,'event_review_submitted');return jsonify(result),200
 except ValueError:return jsonify({'error':MSG.INVALID_INPUT}),400
 except SupabaseError as exc:return _failure(exc)

@bp.route('/events/<event_id>',methods=['GET'])
@require_role(*ROLES)
def event_account(event_id):
 try:return jsonify(_rpc('hg_organizer_event_balance',{'p_event':_uuid(event_id)})),200
 except ValueError:return jsonify({'error':MSG.INVALID_INPUT}),400
 except SupabaseError as exc:return _failure(exc)

@bp.route('/events/<event_id>/review',methods=['POST'])
@require_role('admin')
def review_event(event_id):
 try:
  data=_object();action=data.get('action');body={}
  if action=='configure':
   body['organizer_id']=_uuid(data.get('organizer_id'));tiers=data.get('tiers',[])
   if not isinstance(tiers,list) or len(tiers)>100:raise ValueError
   body['tiers']=[{'id':_uuid(tier.get('id')),'organizer_amount':as_number(tier.get('organizer_amount'),0,999999999)} for tier in tiers if isinstance(tier,dict)]
   if len(body['tiers'])!=len(tiers):raise ValueError
  elif action in ('approve','changes_requested'):
   body['notes']=as_text(data['notes'],500) if data.get('notes') else ''
   if action=='changes_requested' and len(body['notes'])<3:raise ValueError
  else:raise ValueError
  result=_rpc('hg_review_organizer_event',{'p_event':_uuid(event_id),'p_action':action,'p_data':body})
  if action!='configure':_notice(result,'event_review_updated')
  return jsonify(result),200
 except (ValueError,AttributeError):return jsonify({'error':MSG.INVALID_INPUT}),400
 except SupabaseError as exc:return _failure(exc)

@bp.route('/events/<event_id>/change',methods=['POST'])
@require_role('admin')
def change_event_operation(event_id):
 try:
  data=_object();action=data.get('action')
  if action not in ('cancel','reschedule') or set(data)-{'request_id','action','reason','starts_at','ends_at','location','expected_updated_at'}:raise ValueError
  body={'reason':as_text(data.get('reason'),500),'expected_updated_at':as_instant(data.get('expected_updated_at'))}
  if len(body['reason'])<10:raise ValueError
  if action=='reschedule':
   body.update(starts_at=as_instant(data.get('starts_at')),ends_at=as_instant(data.get('ends_at')),location=as_text(data.get('location'),500))
   if not validate_datetime_order(body['starts_at'],body['ends_at'])[0]:raise ValueError
  body['_copy']={'event_cancelled_title':MSG.EVENT_CANCELLED_NOTICE_TITLE,'event_cancelled_body':MSG.EVENT_CANCELLED_NOTICE_BODY,'event_rescheduled_title':MSG.EVENT_RESCHEDULED_NOTICE_TITLE,'event_rescheduled_body':MSG.EVENT_RESCHEDULED_NOTICE_BODY}
  request_id=_uuid(data.get('request_id'))
  result=_rpc('hg_change_event_operation',{'p_event':_uuid(event_id),'p_request':request_id,'p_action':action,'p_data':body})
  if not isinstance(result,dict) or result.get('id')!=request_id:return jsonify({'error':MSG.SERVICE_UNAVAILABLE}),503
  # Both scans are bounded and operate only on committed durable rows. A lost
  # wake is recoverable by the existing scheduled dispatch/refund scans.
  _wake_event_operation(event_id)
  return jsonify(result),200
 except ValueError:return jsonify({'error':MSG.EVENT_CHANGE_INVALID}),400
 except SupabaseError as exc:return _failure(exc)


def _wake_event_operation(event_id):
 import threading
 from flask import current_app
 from app.services.notification_outbox import dispatch_notification
 from app.services.event_refunds import process_event_refund
 app=current_app._get_current_object()
 def wake():
  with app.app_context():
   try:
    db=get_db()
    notices=db.table('notification_deliveries').select('id').eq('status','queued').eq('dispatch_payload->notification->metadata->>event_id',event_id).order('created_at').limit(50).execute() or []
    for row in notices:dispatch_notification(row['id'])
    refunds=db.rpc('hg_event_refund_list',{'p_actor_id':actor,'p_event_id':event_id}) or []
    for row in refunds[:20]:process_event_refund(row['id'])
   except Exception:logger.warning('Event operation wake deferred for %s',event_id)
 actor=g.user_id
 threading.Thread(target=wake,daemon=True).start()


@bp.route('/events/<event_id>/attendees',methods=['GET'])
@require_role(*ROLES)
def attendees(event_id):
 try:
  limit,offset=page_args();search=request.args.get('q','').strip()
  if len(search)>160:raise ValueError
  rows=_rpc('hg_organizer_event_attendees',{'p_event':_uuid(event_id),'p_search':search,'p_limit':limit,'p_offset':offset})
  return jsonify({'attendees':rows or []}),200
 except ValueError:return jsonify({'error':MSG.INVALID_INPUT}),400
 except SupabaseError as exc:return _failure(exc)

@bp.route('/events/<event_id>/attendees/export',methods=['GET'])
@require_role(*ROLES)
def export_attendees(event_id):
 try:
  event_id=_uuid(event_id);rows=[]
  for offset in range(0,10500,500):
   batch=_rpc('hg_organizer_event_attendees',{'p_event':event_id,'p_search':'','p_limit':500,'p_offset':offset}) or []
   rows.extend(batch)
   if len(rows)>10000:return jsonify({'error':MSG.ORG_EXPORT_LIMIT}),413
   if len(batch)<500:break
  return jsonify({'attendees':rows}),200
 except ValueError:return jsonify({'error':MSG.INVALID_INPUT}),400
 except SupabaseError as exc:return _failure(exc)

@bp.route('/events/<event_id>/checkin',methods=['POST'])
@require_role(*ROLES)
def organizer_checkin(event_id):
 try:
  event_id=_uuid(event_id);account=_rpc('hg_organizer_event_balance',{'p_event':event_id})
  data=_object();token=data.get('qr_token') or data.get('ticket_id')
  if isinstance(token,str) and token.startswith('hg-event:'):
   parts=token.split(':')
   if len(parts)!=3 or parts[1]!=event_id:raise ValueError
   token=parts[2]
  ticket=_uuid(token)
  result=admit_event_ticket(event_id,ticket,g.user_id,None,account['event'].get('campus_id'))
  return jsonify(result),200
 except ValueError:return jsonify({'error':MSG.EVENT_QR_INVALID}),400
 except SupabaseError as exc:return _failure(exc)
 except RuntimeError:return jsonify({'error':MSG.EVENT_CHECKIN_FAILED}),503

@bp.route('/events/<event_id>/payouts',methods=['POST'])
@require_role(*ROLES)
def request_payout(event_id):
 try:
  data=_object();request_id=_uuid(data.get('request_id'));bank={key:as_text(data.get(key),120) for key in ('bank_name','account_name','account_number')}
  if len(bank['account_number'])!=10 or not bank['account_number'].isascii() or not bank['account_number'].isdigit():raise ValueError
  result=_rpc('hg_event_payout_action',{'p_event':_uuid(event_id),'p_request':request_id,'p_action':'request','p_data':bank})
  account=_rpc('hg_organizer_event_balance',{'p_event':event_id});_notice(account['event'],'event_payout_requested',result)
  return jsonify(result),200
 except ValueError:return jsonify({'error':MSG.ORG_BANK_INVALID}),400
 except SupabaseError as exc:return _failure(exc)

@bp.route('/events/<event_id>/payouts/<request_id>',methods=['POST'])
@require_role(*ROLES)
def review_payout(event_id,request_id):
 try:
  data=_object();action=data.get('action')
  if action not in ('approve','paid','reject','cancel'):raise ValueError
  if action!='cancel' and g.user_role not in ('admin','super_admin'):return jsonify({'error':MSG.RESOURCE_ACCESS_DENIED}),403
  clean={'notes':as_text(data['notes'],500) if data.get('notes') else ''}
  if action=='paid':clean['reference']=as_text(data.get('reference'),120)
  result=_rpc('hg_event_payout_action',{'p_event':_uuid(event_id),'p_request':_uuid(request_id),'p_action':action,'p_data':clean})
  account=_rpc('hg_organizer_event_balance',{'p_event':event_id});_notice(account['event'],'event_payout_updated',result)
  return jsonify(result),200
 except ValueError:return jsonify({'error':MSG.INVALID_INPUT}),400
 except SupabaseError as exc:return _failure(exc)

@bp.route('/events/<event_id>/door-qr',methods=['POST'])
@require_role(*ROLES)
def organizer_door_qr(event_id):
 try:
  event_id=_uuid(event_id)
  account=_rpc('hg_organizer_event_balance',{'p_event':event_id})
  if account['event'].get('review_status')!='approved':return jsonify({'error':MSG.ORG_REVIEW_LOCKED}),409
  import base64,io,qrcode
  token=uuid.uuid4().hex;payload=f'hg-event:{event_id}:{token}'
  image=io.BytesIO();qrcode.make(payload).save(image,format='PNG')
  get_db().table('event_door_tokens').upsert({'event_id':event_id,'qr_token':token},on_conflict='event_id').execute()
  return jsonify({'event_id':event_id,'qr_payload':payload,'qr_image':'data:image/png;base64,'+base64.b64encode(image.getvalue()).decode('ascii')}),200
 except ValueError:return jsonify({'error':MSG.INVALID_INPUT}),400
 except SupabaseError as exc:return _failure(exc)
