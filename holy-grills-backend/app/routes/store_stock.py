"""Central kitchen inventory with explicit, auditable store allocations."""
from flask import Blueprint, g, jsonify, request
from app.db import get_db, SupabaseError
from app.middleware.auth import require_role, resolve_scoped_campus_id
from app.middleware.rate_limit import rate_limit
from app.messages import MSG
from app.utils.validators import validate_uuid

store_stock_bp = Blueprint('store_stock', __name__)


@store_stock_bp.route('', methods=['GET', 'POST'])
@require_role('admin', 'kitchen')
@rate_limit(max_requests=60, window_seconds=60)
def inventory():
    data = request.args.to_dict() if request.method == 'GET' else request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({'error': MSG.JSON_OBJECT_REQUIRED}), 400
    scope = resolve_scoped_campus_id(data.get('campus_id'))
    store_id = data.get('store_id') or None
    if not scope or not validate_uuid(str(scope)) or (store_id and (not isinstance(store_id, str) or not validate_uuid(store_id))):
        return jsonify({'error': MSG.STORE_CAMPUS_REQUIRED}), 400
    action = data.get('action', 'snapshot')
    if action not in (('snapshot', 'history') if request.method == 'GET' else ('classify', 'transfer', 'usage', 'waste', 'correction')):
        return jsonify({'error': MSG.INVALID_INPUT}), 400
    payload = {key: value for key, value in data.items() if key not in ('campus_id', 'store_id', 'action')}
    allowed = {'item_id'} if action == 'history' else set() if action == 'snapshot' else {'item_id', 'distributable'} if action == 'classify' else {'item_id', 'quantity', 'notes', 'request_id', 'destination_store_id'}
    if set(payload) - allowed:
        return jsonify({'error': MSG.INVALID_INPUT}), 400
    for field in ('item_id', 'request_id', 'destination_store_id'):
        value = payload.get(field)
        if value is not None and (not isinstance(value, str) or not validate_uuid(value)):
            return jsonify({'error': MSG.INVALID_INPUT}), 400
    if request.method == 'POST' and (not payload.get('item_id') or (action != 'classify' and not payload.get('request_id'))):
        return jsonify({'error': MSG.INVALID_INPUT}), 400
    if action == 'classify' and not isinstance(payload.get('distributable'), bool):
        return jsonify({'error': MSG.INVALID_INPUT}), 400
    if request.method == 'POST' and action != 'classify':
        from decimal import Decimal, InvalidOperation
        try:
            quantity = Decimal(str(payload.get('quantity')))
            if isinstance(payload.get('quantity'), bool) or not quantity.is_finite() or quantity == 0 or (action != 'correction' and quantity < 0):
                raise ValueError()
            notes = payload.get('notes')
            if not isinstance(notes, str) or not 1 <= len(notes.strip()) <= 1000:
                raise ValueError()
            payload.update(quantity=str(quantity), notes=notes.strip())
        except (ValueError, InvalidOperation):
            return jsonify({'error': MSG.STORE_STOCK_INVALID}), 400
    try:
        result = get_db().rpc('hg_store_stock', {'p_actor': g.user_id, 'p_campus': scope,
                             'p_store': store_id, 'p_action': action, 'p_data': payload})
        return jsonify(result), 200
    except SupabaseError as exc:
        markers = [('store_stock_denied', MSG.RESOURCE_ACCESS_DENIED, 403),
                   ('store_stock_insufficient', MSG.STORE_STOCK_INSUFFICIENT, 409),
                   ('store_stock_conflict', MSG.STOCK_INTENT_CONFLICT, 409),
                   ('store_stock_allocated', MSG.STORE_STOCK_ALLOCATED, 409),
                   ('store_stock_central_only', MSG.STORE_STOCK_CENTRAL_ONLY, 400),
                   ('store_stock_archived', MSG.STOCK_ARCHIVED_ADJUSTMENT, 409),
                   ('store_stock_not_found', MSG.STOCK_ITEM_NOT_FOUND, 404),
                   ('store_stock_invalid', MSG.STORE_STOCK_INVALID, 400)]
        for marker, message, status in markers:
            if marker in str(exc):
                return jsonify({'error': message}), status
        if str((exc.details or {}).get('code')) in ('22P02', '22003', '23514'):
            return jsonify({'error': MSG.STORE_STOCK_INVALID}), 400
        return jsonify({'error': MSG.SERVICE_UNAVAILABLE}), 503
