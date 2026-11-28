"""Opt-in page measurement; aggregate reports remain staff/campus scoped."""
from flask import Blueprint,request,jsonify,g
from app.db import get_db
from app.messages import MSG
from app.middleware.auth import optional_auth,require_role
from app.middleware.rate_limit import rate_limit
from app.services import engagement_reporting
engagement_bp=Blueprint('engagement',__name__)

@engagement_bp.route('/page-view',methods=['POST'])
@optional_auth
@rate_limit(120,60)
def page_view():
    result=engagement_reporting.record_page(get_db(),request.get_json(silent=True),getattr(g,'user_id',None))
    if not isinstance(result,dict):
        return jsonify({'error':MSG.SERVICE_UNAVAILABLE}),503
    if result.get('error'):
        forbidden=isinstance(result,dict) and result.get('error')=='forbidden'
        return jsonify({'error':MSG.RESOURCE_ACCESS_DENIED if forbidden else MSG.ENGAGEMENT_EVENT_INVALID}),403 if forbidden else 400
    return jsonify(result),200

@engagement_bp.route('/report',methods=['GET'])
@require_role('admin')
def engagement_report():
    from app.routes.analytics import _date_range,_scoped_campus
    try:
        _,_,start,end=_date_range(30);scope=_scoped_campus()
    except ValueError:return jsonify({'error':MSG.ANALYTICS_INVALID_DATE}),400
    result=engagement_reporting.report(get_db(),g.user_id,scope,start,end)
    if not isinstance(result,dict):
        return jsonify({'error':MSG.SERVICE_UNAVAILABLE}),503
    if result.get('error'):
        denied=isinstance(result,dict) and result.get('error')=='forbidden'
        return jsonify({'error':MSG.RESOURCE_ACCESS_DENIED if denied else MSG.ANALYTICS_INVALID_DATE}),403 if denied else 400
    return jsonify(result),200
