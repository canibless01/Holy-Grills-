from functools import wraps
from flask import Blueprint, current_app, g, jsonify, request
from app.middleware.auth import require_auth, require_role, resolve_scoped_campus_id
from app.middleware.rate_limit import rate_limit
from app.messages import MSG
from app.services import delivery_pass as service

delivery_pass_bp = Blueprint('delivery_pass', __name__)
admin_delivery_pass_bp = Blueprint('admin_delivery_pass', __name__)


def responses(fn):
    @wraps(fn)
    def handle(*args, **kwargs):
        try:
            return jsonify(fn(*args, **kwargs)), 200
        except service.PassError as exc:
            return jsonify({'error': str(exc)}), exc.status
        except Exception:
            current_app.logger.exception('Delivery pass operation unavailable')
            return jsonify({'error': MSG.SERVICE_UNAVAILABLE}), 503
    return handle


def body(keys):
    data = request.get_json(silent=True)
    if not isinstance(data, dict) or set(data) - set(keys):
        raise service.PassError(MSG.PASS_INVALID)
    return data


@delivery_pass_bp.route('', methods=['GET'])
@require_auth
@responses
def status():
    return service.status(g.user_id)


@delivery_pass_bp.route('/buy', methods=['POST'])
@require_auth
@rate_limit(max_requests=12, window_seconds=60)
@responses
def buy():
    return service.buy(g.user_id, request.get_json(silent=True))


@delivery_pass_bp.route('/receipts/<receipt_id>/<action>', methods=['POST'])
@require_auth
@rate_limit(max_requests=30, window_seconds=60)
@responses
def receipt_action(receipt_id, action):
    receipt_id = service.identifier(receipt_id)
    if action == 'verify':
        return {'receipt': service.verify(g.user_id, receipt_id)}
    if action == 'cancel':
        return {'receipt': service.public_receipt(service.rpc('cancel', g.user_id, receipt_id))}
    raise service.PassError(MSG.PASS_INVALID, 404)


@delivery_pass_bp.route('/renewal', methods=['POST'])
@require_auth
@responses
def renewal():
    data = body({'enabled', 'price', 'consent_version'})
    enabled = data.get('enabled')
    if not isinstance(enabled, bool) or enabled and data.get('consent_version') != service.CONSENT:
        raise service.PassError(MSG.PASS_INVALID)
    value = service.rpc('renewal', g.user_id, data={'enabled': enabled,
        'price_kobo': service.kobo(data.get('price')) if enabled else None,
        'consent_version': service.CONSENT if enabled else None})
    return {'membership': value}


@admin_delivery_pass_bp.route('', methods=['GET', 'PATCH'])
@require_role('admin')
@responses
def configuration():
    data = request.args.to_dict() if request.method == 'GET' else body({'campus_id', 'price', 'is_active', 'expected_updated_at'})
    campus = resolve_scoped_campus_id(data.get('campus_id'))
    if campus is not None:
        campus = service.identifier(campus)
    if request.method == 'GET':
        return service.rpc('report', g.user_id, data={'campus_id': campus})
    if campus is None or not isinstance(data.get('is_active'), bool):
        raise service.PassError(MSG.PASS_INVALID)
    from app.utils.admin_helpers import as_instant
    version = data.get('expected_updated_at')
    if version is not None:
        try: as_instant(version)
        except (ValueError, TypeError): raise service.PassError(MSG.PASS_INVALID) from None
    return {'offer': service.rpc('configure', g.user_id, data={'campus_id': campus,
        'price_kobo': service.kobo(data.get('price')), 'is_active': data['is_active'], 'expected_updated_at': version})}


@admin_delivery_pass_bp.route('/receipts/<receipt_id>/refund', methods=['POST'])
@require_role('admin')
@responses
def refund(receipt_id):
    data = body({'reason', 'acknowledge'})
    reason = data.get('reason')
    if not isinstance(reason, str) or not 1 <= len(reason.strip()) <= 1000 or data.get('acknowledge') is not True:
        raise service.PassError(MSG.PASS_REFUND_REQUIRED)
    return {'receipt': service.public_receipt(service.rpc('refund', g.user_id, service.identifier(receipt_id),
        {'reason': reason.strip(), 'ledger_reason': MSG.PASS_REFUND_REASON}))}
