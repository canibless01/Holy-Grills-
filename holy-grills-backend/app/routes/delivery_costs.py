"""Private delivery-cost bookkeeping, separate from rider payouts and retail prices."""
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from flask import Blueprint, g, jsonify, request
from app.db import get_db, SupabaseError
from app.middleware.auth import require_role, resolve_scoped_campus_id
from app.utils.tz import today_wat
from app.utils.validators import validate_uuid

delivery_costs_bp = Blueprint('delivery_costs', __name__)


def _money(value):
    if isinstance(value, bool) or value is None:
        raise ValueError('Enter a valid amount with at most two decimal places')
    try:
        amount = Decimal(str(value))
        if not amount.is_finite() or amount < 0 or amount > Decimal('999999999999.99') or amount != amount.quantize(Decimal('0.01')):
            raise ValueError('Enter a valid amount with at most two decimal places')
        return str(amount)
    except (InvalidOperation, TypeError):
        raise ValueError('Enter a valid amount with at most two decimal places')


def _campus():
    campus = resolve_scoped_campus_id(request.args.get('campus_id') or None)
    if campus and not validate_uuid(campus):
        raise ValueError('Choose a valid campus')
    return campus


def _day(raw):
    try:
        parsed = date.fromisoformat(raw)
        if parsed.isoformat() != raw or parsed > today_wat():
            raise ValueError()
        return raw
    except (ValueError, TypeError):
        raise ValueError('Choose a valid date, today or earlier')


def _rpc(name, **params):
    try:
        return jsonify(get_db().rpc(name, {'p_actor': g.user_id, 'p_campus': _campus(), **params}))
    except ValueError as exc:
        return jsonify(error=str(exc)), 400
    except SupabaseError as exc:
        code = str(exc.details.get('code', ''))
        if code == '42501':
            return jsonify(error='Delivery cost access denied'), 403
        if code in ('40001', '40P01'):
            return jsonify(error=str(exc)), 409
        if code in ('22023', '22P02', '22007', '22008', '23503', '23514'):
            return jsonify(error=str(exc)), 400
        raise


@delivery_costs_bp.get('')
@require_role('admin')
def list_costs():
    try:
        day = _day(request.args.get('date', today_wat().isoformat()))
    except ValueError as exc:
        return jsonify(error=str(exc)), 400
    return _rpc('hg_delivery_costs', p_action='list', p_data={'date': day})


@delivery_costs_bp.get('/history/<entry_id>')
@require_role('admin')
def history(entry_id):
    if not validate_uuid(entry_id):
        return jsonify(error='Invalid cost entry'), 400
    return _rpc('hg_delivery_costs', p_action='history', p_data={'entry_id': entry_id})


@delivery_costs_bp.post('')
@require_role('admin')
def save_cost():
    data = request.get_json(silent=True)
    try:
        if not isinstance(data, dict):
            raise ValueError('Enter cost details')
        for key in ('request_id', 'entry_id'):
            if not isinstance(data.get(key), str) or not validate_uuid(data[key]):
                raise ValueError('Invalid cost request')
        version = data.get('version')
        if isinstance(version, bool) or not isinstance(version, int) or version < 0:
            raise ValueError('Invalid cost version')
        ids = data.get('order_ids')
        if not isinstance(ids, list) or not 1 <= len(ids) <= 200 or any(not isinstance(i, str) or not validate_uuid(i) for i in ids) or len(set(ids)) != len(ids):
            raise ValueError('Select 1 to 200 different orders')
        if data.get('kind') not in ('order', 'trip') or (data['kind'] == 'order' and len(ids) != 1):
            raise ValueError('Invalid cost type')
        if not isinstance(data.get('note', ''), str) or len(data.get('note', '')) > 500:
            raise ValueError('Keep the note within 500 characters')
        payload = {key: data[key] for key in ('request_id', 'entry_id', 'version', 'kind', 'order_ids')}
        payload.update(date=_day(data.get('date')), total_cost=_money(data.get('total_cost')), note=data.get('note', '').strip())
    except ValueError as exc:
        return jsonify(error=str(exc)), 400
    return _rpc('hg_delivery_costs', p_action='save', p_data=payload)


@delivery_costs_bp.get('/report')
@require_role('admin')
def report():
    try:
        start = _day(request.args.get('from_date', (today_wat()-timedelta(days=29)).isoformat()))
        end = _day(request.args.get('to_date', today_wat().isoformat()))
        if start > end or (date.fromisoformat(end)-date.fromisoformat(start)).days > 366:
            raise ValueError('Choose a range of up to 367 days')
    except ValueError as exc:
        return jsonify(error=str(exc)), 400
    return _rpc('hg_delivery_pool_report', p_from=start, p_to=end, p_export=request.args.get('export') == '1')


@delivery_costs_bp.route('/budget', methods=['GET', 'PATCH'])
@require_role('admin')
def budget():
    params = {}
    if request.method == 'PATCH':
        data = request.get_json(silent=True)
        try:
            if not isinstance(data, dict) or isinstance(data.get('version'), bool) or not isinstance(data.get('version'), int) or data['version'] < 0:
                raise ValueError('Invalid budget version')
            params = {'p_floor': _money(data.get('floor')), 'p_version': data['version']}
        except ValueError as exc:
            return jsonify(error=str(exc)), 400
    return _rpc('hg_delivery_pool_budget', **params)
