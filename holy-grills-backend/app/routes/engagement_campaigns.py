"""Read/edit/preview only. Actual delivery belongs to the existing scheduled task."""
from flask import Blueprint, request, jsonify, g
from app.db import get_db
from app.middleware.auth import require_role, resolve_scoped_campus_id
from app.messages import MSG
from app.services import engagement_campaigns as service

engagement_campaigns_bp = Blueprint('engagement_campaigns', __name__)


@engagement_campaigns_bp.route('', methods=['GET', 'PATCH'])
@require_role('admin')
def config():
    scope = resolve_scoped_campus_id()
    if not scope:
        return jsonify({'error': MSG.ENGAGEMENT_CAMPAIGN_SCOPE}), 400
    values = None
    if request.method == 'PATCH':
        try:
            values = service.validate(request.get_json(silent=True))
        except ValueError as exc:
            return jsonify({'error': str(exc)}), 400
    result = get_db().rpc('hg_engagement_campaign_config', {'p_actor': g.user_id, 'p_scope': scope, 'p_values': values})
    if not isinstance(result, dict):
        return jsonify({'error': MSG.SERVICE_UNAVAILABLE}), 503
    if result.get('error'):
        code = result['error']
        return jsonify({'error': MSG.RESOURCE_ACCESS_DENIED if code == 'forbidden' else MSG.ENGAGEMENT_CAMPAIGN_STALE if code == 'stale' else MSG.ENGAGEMENT_CAMPAIGN_INVALID}), 403 if code == 'forbidden' else 409 if code == 'stale' else 400
    if result.get('campaign') is None:
        result['campaign'] = service.defaults()
    return jsonify(result), 200


@engagement_campaigns_bp.route('/preview', methods=['POST'])
@require_role('admin')
def preview():
    scope = resolve_scoped_campus_id()
    if not scope:
        return jsonify({'error': MSG.ENGAGEMENT_CAMPAIGN_SCOPE}), 400
    # Verify current actor and campus again; no provider call or notification write.
    access = get_db().rpc('hg_engagement_campaign_config', {'p_actor': g.user_id, 'p_scope': scope, 'p_values': None})
    if not isinstance(access, dict) or access.get('error'):
        return jsonify({'error': MSG.RESOURCE_ACCESS_DENIED}), 403
    body = request.get_json(silent=True) or {}
    try:
        values = service.validate(body.get('campaign'))
        day = body.get('day'); slot = body.get('slot')
        step = next(s for s in values['steps'] if s['day'] == day and s['slot'] == slot)
        campus = get_db().table('campuses').select('name').eq('id', scope).single().execute()
        return jsonify(service.render(step, {'nickname': body.get('nickname')}, campus['name'], '{{order_cutoff}}')), 200
    except (ValueError, TypeError, StopIteration):
        return jsonify({'error': MSG.ENGAGEMENT_CAMPAIGN_INVALID}), 400
