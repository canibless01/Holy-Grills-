from uuid import UUID
from flask import Blueprint, jsonify, request, g
from app.db import get_db
from app.middleware.auth import require_auth, resolve_scoped_campus_id
from app.messages import MSG
from app.services.team_workspace import ERRORS, decorate

team_workspace_bp = Blueprint('team_workspace', __name__)
ACTIONS = frozenset({'member','responsibility','settings','week','save','submit','review','targets','log','rule'})


def response(result):
    if not isinstance(result, dict):
        return jsonify({'error': MSG.SERVICE_UNAVAILABLE}), 503
    if result.get('error'):
        status, key = ERRORS.get(result['error'], (400, 'TEAM_INVALID'))
        return jsonify({'error': getattr(MSG, key), 'code': result['error']}), status
    return jsonify(decorate(result)), 200


@team_workspace_bp.route('', methods=['GET'])
@require_auth
def snapshot():
    return response(get_db().rpc('hg_team_workspace', {'p_actor':g.user_id,'p_scope':resolve_scoped_campus_id(),
        'p_action':'snapshot','p_data':{'week':request.args.get('week')}}))


@team_workspace_bp.route('/access', methods=['GET'])
@require_auth
def access():
    return response(get_db().rpc('hg_team_workspace', {'p_actor':g.user_id,'p_scope':resolve_scoped_campus_id(),'p_action':'access'}))


@team_workspace_bp.route('/<action>', methods=['POST'])
@require_auth
def mutate(action):
    body = request.get_json(silent=True)
    if action not in ACTIONS or not isinstance(body, dict):
        return jsonify({'error':MSG.TEAM_INVALID}), 400
    try:
        request_id = str(UUID(str(body.get('request_id'))))
    except (ValueError,TypeError):
        return jsonify({'error':MSG.TEAM_REQUEST_REQUIRED}), 400
    values = {k:v for k,v in body.items() if k != 'request_id'}
    return response(get_db().rpc('hg_team_workspace', {'p_actor':g.user_id,'p_scope':resolve_scoped_campus_id(),
        'p_action':action,'p_data':values,'p_request':request_id}))
