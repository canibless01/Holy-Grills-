"""Recipient-bound, signed first-party email ticket access; never a public QR service."""
import hashlib
import os
from flask import current_app, has_app_context
from itsdangerous import URLSafeTimedSerializer, BadData

SALT='holy-grills-event-ticket-email-v1'

def _serializer():
    secret=(current_app.config.get('SECRET_KEY') if has_app_context() else None) or os.environ.get('SECRET_KEY')
    if not secret: raise ValueError('Ticket signing key unavailable')
    return URLSafeTimedSerializer(secret, salt=SALT)

def _recipient(email):
    return hashlib.sha256(str(email or '').strip().lower().encode()).hexdigest()

def issue_ticket_access(event_id, ticket_id, email):
    if not email: raise ValueError('Ticket recipient unavailable')
    return _serializer().dumps({'event':str(event_id),'ticket':str(ticket_id),'recipient':_recipient(email)})

def valid_ticket_access(token, ticket, db):
    if not isinstance(token,str) or not token or len(token)>2048:return False
    try:
        signed=_serializer().loads(token,max_age=366*24*3600)
        if not isinstance(signed,dict) or signed.get('event')!=str(ticket.get('event_id')) or signed.get('ticket')!=str(ticket.get('id')):return False
        email=ticket.get('guest_email')
        if ticket.get('user_id'):
            profile=db.table('profiles').select('email').eq('id',ticket['user_id']).single().execute() or {}
            email=profile.get('email')
        return bool(email) and signed.get('recipient')==_recipient(email)
    except (BadData,ValueError,TypeError):
        return False
