"""Group purchases use individual attendee tickets and one purchaser-owned payment."""
import hashlib
import json
from datetime import datetime, timezone
from flask import current_app, g
from itsdangerous import URLSafeTimedSerializer, BadData
from app.db import get_db
from app.messages import MSG
from app.utils.event_questions import validate_answers
from app.utils.event_ticket_access import issue_ticket_access
from app.utils.validators import validate_email, validate_phone, validate_uuid


class GroupAnswersError(ValueError):
    def __init__(self,message,fields):
        super().__init__(message)
        self.fields=fields


def clean_contact(value):
    if not isinstance(value, dict):raise ValueError(MSG.EVENT_GROUP_CONTACT_INVALID)
    result={key:str(value.get(key) or '').strip() if isinstance(value.get(key),str) else '' for key in ('name','email','phone')}
    result['email']=result['email'].lower()
    if not result['name'] or len(result['name'])>200 or len(result['email'])>254 or not validate_email(result['email']) or not validate_phone(result['phone'],pattern=r'^(\+?234|0)[789]\d{9}$'):
        raise ValueError(MSG.EVENT_GROUP_CONTACT_INVALID)
    return result


def clean_attendees(rows, fields, booking_contact=None):
    if not isinstance(rows,list) or not 1<=len(rows)<=10:
        raise ValueError(MSG.EVENT_GROUP_SIZE_INVALID)
    result=[]
    emails=set()
    for index,row in enumerate(rows,1):
        try:
            # Email identifies the recipient. The purchaser remains the booking
            # contact; never invent a friend's name or claim their phone number.
            value=row
            if booking_contact is not None and isinstance(row,dict):
                value={**row,'name':row.get('name') or row.get('email'),'phone':row.get('phone') or booking_contact['phone']}
                if str(row.get('email') or '').strip().lower()==booking_contact['email']:
                    value['name']=row.get('name') or booking_contact['name']
            contact=clean_contact(value)
            if contact['email'] in emails:
                raise ValueError(MSG.EVENT_GROUP_DUPLICATE)
            emails.add(contact['email'])
            tier=row.get('tier_id')
            if tier is not None and not validate_uuid(tier):
                raise ValueError(MSG.EVENT_TIER_REQUIRED)
            try:
                answers=validate_answers(fields,row.get('answers',{}))
            except (ValueError,KeyError,TypeError) as exc:
                raise GroupAnswersError(MSG.EVENT_GROUP_ATTENDEE_INVALID.format(number=index,detail=str(exc)),fields) from exc
            result.append({**contact,'tier_id':tier,'answers':answers})
        except GroupAnswersError:
            raise
        except (ValueError,KeyError,TypeError) as exc:
            raise ValueError(MSG.EVENT_GROUP_ATTENDEE_INVALID.format(number=index,detail=str(exc))) from exc
    return result


def serializer():return URLSafeTimedSerializer(current_app.config['SECRET_KEY'],salt='hg-event-group-buyer-v1')
def access_token(group):return serializer().dumps({'group':group['id'],'buyer':hashlib.sha256(group['buyer_email'].lower().encode()).hexdigest()})
def may_read(group,token=None):
    actor=getattr(g,'user_id',None)
    if actor and str(group.get('buyer_user_id'))==str(actor):return True
    if actor:
        owned=get_db().rpc('hg_event_groups_for_buyer',{'p_event':group['event_id'],'p_actor':actor}) or []
        if any(str(row['id'])==str(group['id']) for row in owned):return True
        if str((read(group['id']) or {}).get('buyer_user_id'))==str(actor):return True
    if not isinstance(token,str) or len(token)>2048:return False
    try:
        signed=serializer().loads(token,max_age=366*24*3600)
        return signed=={'group':group['id'],'buyer':hashlib.sha256(group['buyer_email'].lower().encode()).hexdigest()}
    except (BadData,ValueError,TypeError):return False


def snapshot(group):
    tickets=[]
    for row in group.get('tickets') or []:
        settled=row.get('status') in ('confirmed','checked_in') and row.get('payment_status') in ('paid','not_required')
        tickets.append({'id':row['id'],'name':row.get('guest_name'),'email':row.get('guest_email'),'tier_name':row.get('tier_name'),
            'status':'checked_in' if row.get('checked_in') else row.get('status'),'payment_status':row.get('payment_status'),'price':float(row.get('price_naira') or 0)-float(row.get('discount_amount') or 0),
            **({'access_token':issue_ticket_access(row['event_id'],row['id'],row['guest_email'])} if settled else {})})
    return {'id':group['id'],'event_id':group['event_id'],'payment_status':group['payment_status'],
        'total':group['total'],'wallet_amount':group['wallet_amount'],'card_amount':group['card_amount'],'expires_at':group.get('expires_at'),
        'tickets':tickets,'access_token':access_token(group)}


def read(group_id):return get_db().rpc('hg_event_group_read',{'p_id':group_id})


def _plan(event_id,body,contact):
    method=body.get('payment_method','card')
    if method not in ('wallet','card','split') or body.get('use_hp') or body.get('hp_amount'):
        raise ValueError(MSG.EVENT_GROUP_PAYMENT_INVALID)
    key=body.get('idempotency_key')
    if not isinstance(key,str) or not validate_uuid(key):raise ValueError(MSG.EVENT_GROUP_INTENT_INVALID)
    from decimal import Decimal,InvalidOperation
    try:
        wallet=Decimal(str(body.get('wallet_amount',0)))
        if isinstance(body.get('wallet_amount'),bool) or not wallet.is_finite() or wallet<0:raise ValueError()
        wallet=wallet.quantize(Decimal('.01'))
    except (InvalidOperation,ValueError):raise ValueError(MSG.WALLET_AMOUNT_INVALID)
    promo_text=body.get('promo_code') or ''
    if not isinstance(promo_text,str):raise ValueError(MSG.EVENT_REQUEST_INVALID)
    promo_text=promo_text.strip().upper()
    expected=None
    if body.get('expected_subtotal') is not None:
        try:
            expected=Decimal(str(body['expected_subtotal'])).quantize(Decimal('.01'))
            if isinstance(body['expected_subtotal'],bool) or not expected.is_finite() or expected<0:raise ValueError()
        except (InvalidOperation,ValueError):raise ValueError(MSG.EVENT_REQUEST_INVALID)
    actor=getattr(g,'user_id',None)
    if not actor and method!='card':raise ValueError(MSG.EVENT_GROUP_PAYMENT_INVALID)
    raw_rows=body.get('attendees')
    if not isinstance(raw_rows,list) or not 1<=len(raw_rows)<=10:raise ValueError(MSG.EVENT_GROUP_SIZE_INVALID)
    shared='registration_answers' in body
    notes=body.get('booking_notes','')
    if not isinstance(notes,str) or len(notes)>5000 or (shared and not isinstance(body['registration_answers'],dict)):
        raise ValueError(MSG.EVENT_REQUEST_INVALID)
    bound={'attendees':raw_rows,'contact':contact,'method':method,'wallet':str(wallet),'promo':promo_text,'expected':str(expected) if expected is not None else None}
    # Preserve the exact fingerprint of old in-flight requests on deployment.
    if shared:bound.update(registration_answers=body['registration_answers'],booking_notes=notes)
    elif 'booking_notes' in body:raise ValueError(MSG.EVENT_REQUEST_INVALID)
    fingerprint=hashlib.sha256(json.dumps(bound,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    scoped_key=hashlib.sha256(f'{actor or contact["email"]}:{event_id}:{key}'.encode()).hexdigest()
    return {'method':method,'wallet':wallet,'promo_text':promo_text,'actor':actor,'raw_rows':raw_rows,
            'fingerprint':fingerprint,'scoped_key':scoped_key,'expected':expected,'shared':shared,'shared_answers':body.get('registration_answers'),'notes':notes}


def _recover(event_id,contact,plan):
    previous=get_db().rpc('hg_event_group_by_intent',{'p_event':event_id,'p_key':plan['scoped_key']})
    if previous:
        if previous.get('fingerprint')!=plan['fingerprint'] or previous.get('buyer_user_id')!=plan['actor'] or previous.get('buyer_email')!=contact['email']:raise ValueError(MSG.EVENT_GROUP_CONFLICT)
        return previous
    return None


def recover(event_id,body,contact):
    return _recover(event_id,contact,_plan(event_id,body,contact))


def create(event,body,contact,*,lookup=True):
    plan=_plan(event['id'],body,contact)
    if lookup:
        previous=_recover(event['id'],contact,plan)
        if previous:return previous
    fields=event.get('registration_fields') or []
    rows=clean_attendees(plan['raw_rows'],[] if plan['shared'] else fields,booking_contact=contact)
    if plan['shared']:
        try:answers=validate_answers(fields,plan['shared_answers'])
        except (ValueError,KeyError,TypeError) as exc:
            raise GroupAnswersError(str(exc),fields) from exc
        for row in rows:
            row['answers']=answers
            row['registration_context']={'scope':'group','answered_by':contact['name'],'notes':plan['notes'].strip()}
    promo=None
    if plan['promo_text']:
        promo=(get_db().table('promo_codes').select('id').eq('code',plan['promo_text']).eq('is_active',True).single().execute() or {}).get('id')
        if not promo:raise ValueError(MSG.EVENT_GROUP_PROMO_INVALID)
    return get_db().rpc('hg_create_event_group',{'p_event':event['id'],'p_buyer':plan['actor'],
        'p_contact':{**contact,'_wallet_description':MSG.EVENT_GROUP_WALLET_DESCRIPTION,
            **({'_expected_subtotal':str(plan['expected'])} if plan['expected'] is not None else {})},'p_attendees':rows,
        'p_method':plan['method'],'p_wallet':str(plan['wallet']),'p_promo':promo,'p_key':plan['scoped_key'],'p_fingerprint':plan['fingerprint']})


def initialize(group,callback):
    if group['payment_status']!='pending' or not float(group['card_amount']):raise ValueError(MSG.EVENT_GROUP_NOT_PENDING)
    if group.get('expires_at') and datetime.fromisoformat(group['expires_at'].replace('Z','+00:00'))<=datetime.now(timezone.utc):raise ValueError(MSG.EVENT_GROUP_EXPIRED)
    if any(row['status'] in ('cancelled','canceled','expired') for row in group['tickets']):raise ValueError(MSG.EVENT_GROUP_EXPIRED)
    if group.get('authorization_url'):return {'authorization_url':group['authorization_url']}
    if not current_app.config.get('PAYSTACK_SECRET_KEY'):raise ValueError(MSG.EVENT_CARD_UNAVAILABLE)
    from app.services.payment_service import initialize_payment
    # Fixed first-party callback, never a client-controlled return URL.
    base=current_app.config.get('FRONTEND_URL','https://holygrills.online').split(',')[0].strip().rstrip('/')
    result=initialize_payment(email=group['buyer_email'],amount_naira=float(group['card_amount']),reference=group['payment_reference'],
        metadata={'type':'event_group_payment','group_id':group['id'],'event_id':group['event_id'],'expected_amount_kobo':round(float(group['card_amount'])*100)},
        callback_url=f'{base}/events/{group["event_id"]}/group/{group["id"]}')
    from urllib.parse import urlparse
    parsed=urlparse(result.get('authorization_url') or '')
    if parsed.scheme!='https' or parsed.hostname not in ('checkout.paystack.com','paystack.com') or parsed.username or parsed.password:
        raise ValueError(MSG.EVENT_GROUP_PAYMENT_INVALID)
    # Provider URL is verified by the frontend shared allowlist as for single tickets.
    get_db().rpc('hg_event_group_authorization',{'p_id':group['id'],'p_url':result['authorization_url']})
    return {'authorization_url':result['authorization_url']}


def confirm(group,reference,charge,provider='paystack'):
    from app.services.payment_amounts import validate_charge_amount
    meta=charge.get('metadata') or charge.get('meta') or {}
    if isinstance(meta,str):
        try:meta=json.loads(meta)
        except ValueError:meta={}
    if not meta and reference==group['payment_reference']:
        meta={'type':'event_group_payment','group_id':group['id'],'event_id':group['event_id']}
        charge={**charge,'metadata':meta}
    if provider!='paystack' or reference!=group['payment_reference'] or meta.get('type')!='event_group_payment' or str(meta.get('group_id'))!=str(group['id']) or str(meta.get('event_id'))!=str(group['event_id']):raise ValueError(MSG.EVENT_GROUP_PAYMENT_INVALID)
    if charge.get('status')!='success' or charge.get('currency')!='NGN':raise ValueError(MSG.EVENT_GROUP_PAYMENT_INVALID)
    from decimal import Decimal,InvalidOperation
    try:
        paid=Decimal(str(charge.get('amount')))
        if not paid.is_finite() or paid!=paid.to_integral_value() or paid < Decimal(str(group['card_amount']))*100:raise ValueError()
    except (InvalidOperation,ValueError):raise ValueError(MSG.EVENT_GROUP_PAYMENT_INVALID)
    breakdown=validate_charge_amount(charge,float(group['card_amount']),provider,label='Event group')
    result=get_db().rpc('hg_pay_event_group',{'p_id':group['id'],'p_reference':reference,'p_amount':group['card_amount'],
        'p_metadata':{**charge,'_amount_breakdown':breakdown,'_recovery_reason':MSG.EVENT_EXPIRED_PAYMENT_REFUND_REASON}})
    from app.services.notification_outbox import start_ticket_email_dispatch
    start_ticket_email_dispatch(result['id'])
    for ticket in result.get('tickets') or []:
        if ticket['payment_status'] in ('paid','not_required'):start_ticket_email_dispatch(ticket['id'])
    return result


def prepare_receipt(group):
    """Private purchaser recovery link; transport/retry stays in the shared outbox."""
    from urllib.parse import urlencode
    from app.utils.email import _build_html
    from app.services import notification_service as service
    event=get_db().table('events').select('title').eq('id',group['event_id']).single().execute() or {}
    rows=group.get('tickets') or []
    confirmed=sum(row.get('status') in ('confirmed','checked_in') and row.get('payment_status') in ('paid','not_required') for row in rows)
    base=current_app.config.get('FRONTEND_URL','https://holygrills.online').split(',')[0].strip().rstrip('/')
    url=f"{base}/events/{group['event_id']}/group/{group['id']}?{urlencode({'access':access_token(group)})}"
    body=MSG.EVENT_GROUP_EMAIL_BODY.format(event=event.get('title') or '',total=f"{float(group['total']):,.2f}",confirmed=confirmed,count=len(rows))
    return {'to_email':group['buyer_email'],'to_name':group['buyer_name'],'subject':MSG.EVENT_GROUP_EMAIL_SUBJECT,
        'html_body':_build_html(group['buyer_name'],body,cta_buttons=[{'label':MSG.EVENT_GROUP_EMAIL_CTA,'url':url,'primary':True}],skip_thank_you=True),
        'provider':service.get_email_provider(scope='transactional'),'transactional':True}
