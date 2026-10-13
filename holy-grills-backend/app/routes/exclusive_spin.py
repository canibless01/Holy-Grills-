from datetime import datetime, timezone
from flask import Blueprint, jsonify, g, request
from app.middleware.auth import require_auth
from app.db import get_db, get_user_client
from app.messages import MSG, resolve_msg
from app.services.feature_flags import is_feature_enabled
from app.utils.admin_helpers import as_uuid
from app.utils.logger import get_logger

logger = get_logger(__name__)
exclusive_spin_bp = Blueprint('exclusive_spin', __name__)
SPIN_GRANT_SOURCES = ['leaderboard_prize', 'tier_grant', 'admin_grant']


def _available_spins(db, user_id):
    q = (db.table('exclusive_spins').select('id,spin_count,source,month,expires_at')
         .eq('user_id', user_id).in_('source', SPIN_GRANT_SOURCES)
         .gt('spin_count', 0).gte('expires_at', datetime.now(timezone.utc).isoformat()))
    campus_id = getattr(g, 'campus_id', None)
    if not campus_id:
        return []
    return q.eq('campus_id', campus_id).order('expires_at').execute() or []


def _spin_prizes():
    """The configured campus pool, otherwise global. Unreadable data is an error."""
    db = get_db()
    fields = 'id,name,weight,reward_config,campus_id'
    campus_id = getattr(g, 'campus_id', None)
    if campus_id:
        rows = (db.table('exclusive_spin_prizes').select(fields)
                .eq('is_active', True).eq('campus_id', campus_id).gt('weight', 0).order('id').execute())
        if rows:
            return rows
    return (db.table('exclusive_spin_prizes').select(fields).eq('is_active', True)
            .is_('campus_id', 'null').gt('weight', 0).order('id').execute()) or []


@exclusive_spin_bp.route('', methods=['GET'])
@require_auth
def my_spins():
    if not is_feature_enabled('exclusive_spin'):
        return jsonify({'error': resolve_msg(MSG.FEATURE_NOT_AVAILABLE, feature='Exclusive spin')}), 403
    try:
        db = get_user_client()
        spins = _available_spins(db, g.user_id)
        prizes = _spin_prizes()
        history = (db.table('exclusive_spin_fulfillments').select('*')
                   .eq('user_id', g.user_id).order('created_at', ascending=False).limit(100).execute()) or []
        return jsonify({'total_spins': sum(s.get('spin_count', 0) for s in spins),
                        'spins': spins, 'prizes': prizes, 'history': history}), 200
    except Exception:
        logger.exception('my_spins: configured prizes/credits unavailable')
        return jsonify({'error': MSG.SPIN_SERVICE_UNAVAILABLE}), 503


@exclusive_spin_bp.route('/spin', methods=['POST'])
@require_auth
def do_spin():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({'error': MSG.SPIN_INTENT_REQUIRED}), 400
    try:
        intent = as_uuid(data.get('intent_key'))
    except ValueError:
        intent = None
    if not intent:
        return jsonify({'error': MSG.SPIN_INTENT_REQUIRED}), 400
    try:
        # A committed receipt can be recovered even after its release gate is off.
        result = get_db().rpc('hg_spin_exclusive_atomic', {
            'p_user_id': g.user_id, 'p_intent_key': intent,
        })
    except Exception:
        logger.exception('do_spin: transaction failed; credit and award rolled back')
        return jsonify({'error': MSG.SPIN_SERVICE_UNAVAILABLE}), 503
    if not isinstance(result, dict):
        return jsonify({'error': MSG.SPIN_SERVICE_UNAVAILABLE}), 503
    error = result.get('error')
    if error:
        errors = {
            'invalid_intent': (MSG.SPIN_INTENT_REQUIRED, 400),
            'user_inactive': (MSG.UPDATE_NOT_PERMITTED, 403),
            'campus_required': (MSG.CAMPUS_REQUIRED, 400),
            'feature_disabled': (resolve_msg(MSG.FEATURE_NOT_AVAILABLE, feature='Exclusive spin'), 403),
            'no_credits': (MSG.SPIN_NO_CREDITS, 400),
            'pool_unavailable': (MSG.SPIN_POOL_UNAVAILABLE, 409),
        }
        message, status = errors.get(error, (MSG.SPIN_SERVICE_UNAVAILABLE, 503))
        return jsonify({'error': message}), status
    if not result.get('idempotent'):
        try:
            from app.services.notification_service import send_notification
            send_notification(user_id=g.user_id, notif_type='exclusive_spin_won',
                              template_data={'prize': result['prize']}, campus_id=getattr(g, 'campus_id', None))
        except Exception:
            logger.exception('do_spin: result saved but notification failed')
    return jsonify({**result, 'message': resolve_msg(MSG.SPIN_SUCCESS, prize=result['prize'])}), 200
