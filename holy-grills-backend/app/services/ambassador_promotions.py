"""Scoped promo lifecycle and contact overrides; no commerce or reward mutation."""
import re
from urllib.parse import urlparse
from app.messages import MSG
from app.services import ambassador_service as programme


def image_url(value):
    if value in (None, ''):
        return None
    if not isinstance(value, str):
        raise programme.AmbassadorError(MSG.AMBASSADOR_PROMO_IMAGE_INVALID)
    parsed = urlparse(value)
    if (parsed.scheme != 'https' or parsed.netloc != 'res.cloudinary.com'
            or any(c.isspace() for c in value) or '/image/upload/' not in parsed.path):
        raise programme.AmbassadorError(MSG.AMBASSADOR_PROMO_IMAGE_INVALID)
    return value


def result_or_error(result):
    errors = {
        'promo_forbidden': (MSG.RESOURCE_ACCESS_DENIED, 403),
        'promo_not_found': (MSG.RESOURCE_NOT_FOUND, 404),
        'promo_deleted': (MSG.AMBASSADOR_PROMO_DELETED, 409),
        'promo_stale': (MSG.AMBASSADOR_PROMO_STALE, 409),
        'promo_invalid': (MSG.AMBASSADOR_PROMO_INVALID, 400),
    }
    if isinstance(result, dict) and result.get('error'):
        message, status = errors.get(result['error'], (MSG.SERVICE_UNAVAILABLE, 503))
        raise programme.AmbassadorError(message, status=status)
    if not isinstance(result, dict) or not result:
        raise programme.AmbassadorError(MSG.SERVICE_UNAVAILABLE, status=503)
    return result


def manage(db, actor_id, message_id, scope, revision, action, values=None):
    if not isinstance(revision, int) or isinstance(revision, bool) or revision < 1:
        raise programme.AmbassadorError(MSG.AMBASSADOR_PROMO_STALE, status=409)
    current = db.table('ambassador_promo_messages').select('id,campus_id').eq('id', message_id).single().execute()
    if not current:
        raise programme.AmbassadorError(MSG.RESOURCE_NOT_FOUND, status=404)
    if scope is not None and current.get('campus_id') != scope:
        raise programme.AmbassadorError(MSG.RESOURCE_ACCESS_DENIED, status=403)
    patch = {}
    if action == 'edit':
        if not isinstance(values, dict) or not set(values) <= {'caption', 'image_url', 'revision'}:
            raise programme.AmbassadorError(MSG.AMBASSADOR_PROMO_INVALID)
        if 'caption' in values:
            caption = values['caption']
            if not isinstance(caption, str) or not caption.strip() or len(caption) > 10000 or not any(t in caption for t in programme.LINK_PLACEHOLDERS):
                raise programme.AmbassadorError(MSG.AMBASSADOR_PROMO_LINK_PLACEHOLDER_REQUIRED)
            patch['caption'] = caption.strip()
        if 'image_url' in values:
            patch['image_url'] = image_url(values['image_url'])
        if not patch:
            raise programme.AmbassadorError(MSG.AMBASSADOR_PROMO_INVALID)
    result = result_or_error(db.rpc('hg_manage_ambassador_promo', {
        'p_actor': actor_id, 'p_id': message_id, 'p_revision': revision,
        'p_action': action, 'p_values': patch,
    }))
    programme._invalidate_metric_reads()
    return result


def contact(db, actor_id, ambassador_id, scope, value):
    target = db.table('ambassadors').select('profile_id,campus_id').eq('profile_id', ambassador_id).eq('status', 'active').single().execute()
    if not target:
        raise programme.AmbassadorError(MSG.AMBASSADOR_NOT_FOUND, status=404)
    if scope is not None and target.get('campus_id') != scope:
        raise programme.AmbassadorError(MSG.RESOURCE_ACCESS_DENIED, status=403)
    if value in (None, ''):
        phone = None
    elif isinstance(value, str):
        phone = re.sub(r'[ ()-]', '', value)
        if phone.startswith('0') and len(phone) == 11:
            phone = '+234' + phone[1:]
        elif phone.startswith('234'):
            phone = '+' + phone
        if not re.fullmatch(r'\+[1-9]\d{7,14}', phone):
            raise programme.AmbassadorError(MSG.AMBASSADOR_WHATSAPP_INVALID)
    else:
        raise programme.AmbassadorError(MSG.AMBASSADOR_WHATSAPP_INVALID)
    return result_or_error(db.rpc('hg_set_ambassador_whatsapp', {
        'p_actor': actor_id, 'p_ambassador': ambassador_id, 'p_phone': phone,
    }))
