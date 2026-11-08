"""Authenticated controls for privately stored automatic wallet funding."""
from uuid import UUID
from flask import Blueprint, request, jsonify, g, current_app
from app.middleware.auth import require_auth
from app.middleware.rate_limit import rate_limit
from app.services import auto_funding as service

auto_funding_bp = Blueprint("auto_funding", __name__)


@auto_funding_bp.route("", methods=["GET", "POST"])
@require_auth
@rate_limit(max_requests=30, window_seconds=60)
def plans():
    try:
        if request.method == "GET":
            rows = service.rpc("list", user_id=g.user_id) or []
            return jsonify({"plans": [service.public_plan(row) for row in rows], "limits": service.limits()})
        body = request.get_json(silent=True)
        if not isinstance(body, dict):
            return jsonify({"error": "Invalid funding request."}), 400
        return jsonify({"plan": service.create_plan(g.user_id, body)})
    except service.FundingError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception:
        current_app.logger.warning("Automatic funding request could not be completed.")
        return jsonify({"error": "Funding request unavailable. Check your existing plan before trying again."}), 503


@auto_funding_bp.route("/<plan_id>/<action>", methods=["POST"])
@require_auth
@rate_limit(max_requests=30, window_seconds=60)
def manage(plan_id, action):
    try:
        plan_id = str(UUID(plan_id))
        if action == "stop":
            return jsonify({"plan": service.public_plan(service.rpc("stop", user_id=g.user_id, plan_id=plan_id))})
        if action == "verify":
            body = request.get_json(silent=True) or {}
            reference = body.get("reference")
            if not isinstance(reference, str) or not 1 <= len(reference) <= 120:
                raise service.FundingError("Choose the payment for this funding plan.")
            return jsonify(service.verify_setup(g.user_id, plan_id, reference))
        return jsonify({"error": "Funding action not found."}), 404
    except (service.FundingError, ValueError) as exc:
        return jsonify({"error": str(exc) if isinstance(exc, service.FundingError) else "Invalid funding plan."}), 400
    except Exception:
        current_app.logger.warning("Automatic funding action unavailable: %s", action)
        return jsonify({"error": "This action could not be confirmed. Refresh the plan before trying again."}), 503
