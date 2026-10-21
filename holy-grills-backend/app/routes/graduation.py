"""Graduation eligibility and lifetime HP claim, scoped to the signed-in user."""
from flask import Blueprint, jsonify, g, current_app
from app.middleware.auth import require_auth
from app.db import get_db
from app.messages import MSG, resolve_msg
from app.utils.logger import get_logger

logger = get_logger(__name__)
graduation_bp = Blueprint("graduation", __name__)
_GRADUATION_HP_DEFAULT = 1000


def _configured_hp():
    value = current_app.config.get("GRADUATION_HP", _GRADUATION_HP_DEFAULT)
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        return 0
    try:
        amount = int(value)
        return amount if 0 < amount <= 2147483647 else 0
    except (ValueError, TypeError):
        return 0


def _claim_error(result):
    code = result.get('error')
    if code == 'profile_not_found':
        return jsonify({'error': MSG.GRADUATION_PROFILE_NOT_FOUND}), 404
    if code == 'already_claimed':
        return jsonify({'error': resolve_msg(MSG.GRADUATION_ALREADY_CLAIMED)}), 400
    messages = {'campus_required': MSG.CAMPUS_REQUIRED,
                'level': MSG.GRADUATION_ELIGIBILITY_REQUIRED,
                'orders': MSG.GRADUATION_ORDERS_REQUIRED,
                'period': MSG.GRADUATION_PERIOD_REQUIRED}
    if code in messages:
        return jsonify({**result, 'error': messages[code]}), 400
    logger.warning('graduation claim unavailable: %s', code)
    return jsonify({'error': MSG.GRADUATION_HP_CLAIM_FAILED}), 503


@graduation_bp.route('/eligibility', methods=['GET'])
@require_auth
def graduation_eligibility():
    """Read eligibility without claiming HP, changing a profile or creating a row."""
    try:
        result = get_db().rpc('hg_graduation_eligibility', {'p_user_id': g.user_id})
        if not isinstance(result, dict) or result.get('error'):
            return _claim_error(result if isinstance(result, dict) else {})
        amount = _configured_hp()
        if not amount and not result.get('claimed'):
            result = {**result, 'eligible': False, 'reason': 'configuration'}
        return jsonify({**result, 'hp_amount': amount}), 200
    except Exception as exc:
        logger.warning('graduation eligibility unavailable: %s', type(exc).__name__)
        return jsonify({'error': MSG.GRADUATION_HP_CLAIM_FAILED}), 503


@graduation_bp.route('/claim', methods=['POST'])
@require_auth
def claim_graduation():
    """Claim once during the campus graduation period after three delivered orders.

    The service RPC rechecks all gates and commits the earning, monthly counter
    and graduation marker together. User-supplied identity, level and HP values
    are never accepted. Historical lifetime receipts repair their marker without
    receiving a second award, even after the calendar/configuration changes.
    """
    try:
        result = get_db().rpc('hg_claim_graduation_atomic', {
            'p_user_id': g.user_id, 'p_hp_amount': _configured_hp(),
        })
    except Exception as exc:
        logger.warning('graduation claim unavailable: %s', type(exc).__name__)
        return jsonify({'error': MSG.GRADUATION_HP_CLAIM_FAILED}), 503
    if not isinstance(result, dict) or result.get('error') or not result.get('success'):
        return _claim_error(result if isinstance(result, dict) else {})
    if result.get('hp_awarded', 0) > 0:
        # HP is already committed. Optional notification/milestone failures must
        # never turn a saved claim into an apparent failure or invite a replay.
        try:
            from app.services.milestone_service import check_milestone_trigger
            check_milestone_trigger(g.user_id, 'graduation', 1)
        except Exception as exc:
            logger.warning('graduation milestone follow-up failed: %s', type(exc).__name__)
        try:
            from app.services.notification_service import send_notification
            send_notification(user_id=g.user_id, notif_type='graduation_hp',
                              template_data={'hp': result['hp_awarded'],
                                             'level': result.get('academic_level')})
        except Exception as exc:
            logger.warning('graduation notification follow-up failed: %s', type(exc).__name__)
    return jsonify({**result, 'message': resolve_msg(MSG.GRADUATION_CLAIMED_OK)}), 200
