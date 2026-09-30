import uuid
import logging

import requests
from flask import Flask, request
from flask_cors import CORS
from flasgger import Swagger
from werkzeug.exceptions import HTTPException
from werkzeug.middleware.proxy_fix import ProxyFix

from app.config import Config
from app.db import SupabaseError
from app.messages import MSG
from app.utils.logger import get_logger
from app.routes.health import health_bp
from app.routes.auth import auth_bp, users_bp
from app.routes.menu import menu_bp
from app.routes.orders import orders_bp
from app.routes.hp import hp_bp
from app.routes.wallet import wallet_bp
from app.routes.rewards import rewards_bp
from app.routes.marketplace import marketplace_bp
from app.routes.events import events_bp
from app.routes.referrals import referrals_bp
from app.routes.notifications import notifications_bp, push_bp
from app.routes.admin import admin_bp
from app.routes.kitchen import kitchen_bp, units_bp, stock_bp
from app.routes.riders import riders_bp
from app.routes.leaderboard import leaderboard_bp
from app.routes.challenges import challenges_bp
from app.routes.webhooks import webhooks_bp
from app.routes.storefront import storefront_bp
from app.routes.analytics import analytics_bp
from app.routes.cart import cart_bp
from app.routes.saved_for_later import saved_bp
from app.routes.order_locks import order_locks_bp
from app.routes.admin_gifts import admin_gifts_bp
from app.routes.delivery import delivery_bp
from app.routes.graduation import graduation_bp
from app.routes.campuses import campuses_bp
from app.routes.departments import departments_bp, admin_departments_bp
from app.routes.academic_levels import academic_levels_bp, admin_academic_levels_bp
from app.routes.academic_calendar import academic_calendar_bp, admin_academic_calendar_bp
from app.routes.free_sides import free_sides_bp
from app.routes.exclusive_spin import exclusive_spin_bp
from app.routes.admin_feature_flags import admin_flags_bp
from app.routes.uploads import uploads_bp
from app.routes.squads import squads_bp
from app.routes.admin_economics import admin_economics_bp

# SQLSTATE codes raised by Postgres/PostgREST that mean "the caller sent something wrong", not "the server is broken":
# 22P02 bad text representation (e.g. malformed UUID), 22007/22008 bad date/time, 22003 number out of range,
# 22001 value too long, 23502 not-null, 23503 foreign key, 23514 check constraint.
_CLIENT_ERROR_CODES = {"22P02", "22007", "22008", "22003", "22001", "23502", "23503", "23514"}


_INSECURE_DEFAULT_SECRET = "change-me-in-production"


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    # H-03: refuse to boot outside DEBUG/TESTING (i.e. ProductionConfig) if SECRET_KEY or JWT_SECRET is still the
    # public fallback. Newsletter unsubscribe tokens are signed with SECRET_KEY; running the default in production
    # lets anyone forge one. Checked here, not as a raise inside ProductionConfig's class body, because every
    # config class in config_map is imported unconditionally on every boot, so a class-body check would fire even
    # in development.
    if not app.config.get("DEBUG") and not app.config.get("TESTING"):
        for _key in ("SECRET_KEY", "JWT_SECRET"):
            if not app.config.get(_key) or app.config.get(_key) == _INSECURE_DEFAULT_SECRET:
                raise RuntimeError(
                    _key + " is unset or still the public default ('" + _INSECURE_DEFAULT_SECRET + "'). "
                    "Set a real secret via the SECRET_KEY / JWT_SECRET environment variables before starting in production."
                )

    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

    CORS(
        app,
        origins="*",
        methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Campus-ID", "Accept", "Origin", "X-Requested-With"],
        expose_headers=["Authorization", "Deprecation", "Sunset", "Link"],
        supports_credentials=False,
        max_age=86400,
    )

    @app.before_request
    def handle_options_preflight():
        if request.method == "OPTIONS":
            response = app.make_default_options_response()
            response.status_code = 204
            return response

    swagger_config = {
        "headers": [],
        "specs": [
            {
                "endpoint": "apispec",
                "route": "/api/docs/apispec.json",
                "rule_filter": lambda rule: True,
                "model_filter": lambda tag: True,
            }
        ],
        "static_url_path": "/api/docs/static",
        "swagger_ui": True,
        "specs_route": "/api/docs/",
    }
    import os as _os
    _app_name = _os.environ.get("APP_NAME", "Holy Grills")
    swagger_template = {
        "swagger": "2.0",
        "info": {
            "title": f"{_app_name} API",
            "description": f"Backend API for the {_app_name} platform — HP economy, food ordering, marketplace, events, wallet, and admin operations.",
            "version": "1.0.0",
            "contact": {"email": _os.environ.get("SWAGGER_CONTACT_EMAIL", "dev@example.com")},
        },
        "securityDefinitions": {
            "BearerAuth": {
                "type": "apiKey",
                "in": "header",
                "name": "Authorization",
                "description": "JWT Bearer token. Format: 'Bearer <token>'",
            }
        },
        "security": [{"BearerAuth": []}],
        "basePath": "/api",
        "consumes": ["application/json"],
        "produces": ["application/json"],
    }
    Swagger(app, config=swagger_config, template=swagger_template)

    app.register_blueprint(auth_bp, url_prefix="/api/auth")
    app.register_blueprint(users_bp, url_prefix="/api/users")
    app.register_blueprint(menu_bp, url_prefix="/api/menu")
    app.register_blueprint(orders_bp, url_prefix="/api/orders")
    app.register_blueprint(hp_bp, url_prefix="/api/hp")
    app.register_blueprint(wallet_bp, url_prefix="/api/wallet")
    app.register_blueprint(rewards_bp, url_prefix="/api/rewards")
    app.register_blueprint(marketplace_bp, url_prefix="/api/marketplace")
    app.register_blueprint(events_bp, url_prefix="/api/events")
    app.register_blueprint(referrals_bp, url_prefix="/api/referrals")
    app.register_blueprint(notifications_bp, url_prefix="/api/notifications")
    app.register_blueprint(push_bp, url_prefix="/api/push")
    app.register_blueprint(admin_bp, url_prefix="/api/admin")
    app.register_blueprint(kitchen_bp, url_prefix="/api/kitchen")
    app.register_blueprint(units_bp, url_prefix="/api/measurement-units")
    app.register_blueprint(stock_bp, url_prefix="/api/admin/stock-items")
    app.register_blueprint(riders_bp, url_prefix="/api/riders")
    app.register_blueprint(leaderboard_bp, url_prefix="/api/leaderboard")
    app.register_blueprint(challenges_bp, url_prefix="/api/challenges")
    app.register_blueprint(webhooks_bp, url_prefix="/api/webhooks")
    app.register_blueprint(storefront_bp, url_prefix="/api/storefront")
    app.register_blueprint(analytics_bp, url_prefix="/api/analytics")
    app.register_blueprint(cart_bp, url_prefix="/api/cart")
    app.register_blueprint(saved_bp, url_prefix="/api/saved")
    app.register_blueprint(order_locks_bp, url_prefix="/api/order-locks")
    app.register_blueprint(admin_gifts_bp, url_prefix="/api/admin")
    app.register_blueprint(delivery_bp, url_prefix="/api/delivery")
    app.register_blueprint(graduation_bp, url_prefix="/api/graduation")
    app.register_blueprint(campuses_bp, url_prefix="/api/campuses")
    app.register_blueprint(departments_bp, url_prefix="/api/departments")
    app.register_blueprint(admin_departments_bp, url_prefix="/api/admin")
    app.register_blueprint(academic_levels_bp, url_prefix="/api/academic-levels")
    app.register_blueprint(admin_academic_levels_bp, url_prefix="/api/admin")
    app.register_blueprint(academic_calendar_bp, url_prefix="/api/academic-calendar")
    app.register_blueprint(admin_academic_calendar_bp, url_prefix="/api/admin")
    app.register_blueprint(free_sides_bp, url_prefix="/api/free-sides")
    app.register_blueprint(exclusive_spin_bp, url_prefix="/api/exclusive-spin")
    app.register_blueprint(admin_flags_bp, url_prefix="/api/admin")
    app.register_blueprint(uploads_bp, url_prefix="/api/upload")
    app.register_blueprint(squads_bp, url_prefix="/api/squads")
    app.register_blueprint(admin_economics_bp, url_prefix="/api/admin/economics")
    app.register_blueprint(health_bp, url_prefix="/api")

    _logger = get_logger("holy_grills.app")

    @app.before_request
    def _attach_request_id():
        request.request_id = str(uuid.uuid4())[:8]

    @app.errorhandler(405)
    def method_not_allowed(e):
        rid = getattr(request, "request_id", "-")
        return {"error": "Method not allowed", "message": str(e), "request_id": rid}, 405

    @app.errorhandler(400)
    def bad_request(e):
        rid = getattr(request, "request_id", "-")
        _logger.warning("[%s] 400 Bad Request: %s %s — %s", rid, request.method, request.path, e)
        return {"error": "Bad request", "message": str(e), "request_id": rid}, 400

    @app.errorhandler(401)
    def unauthorized(e):
        rid = getattr(request, "request_id", "-")
        _logger.warning("[%s] 401 Unauthorized: %s %s", rid, request.method, request.path)
        return {"error": "Unauthorized", "message": str(e), "request_id": rid}, 401

    @app.errorhandler(403)
    def forbidden(e):
        rid = getattr(request, "request_id", "-")
        _logger.warning("[%s] 403 Forbidden: %s %s", rid, request.method, request.path)
        return {"error": "Forbidden", "message": str(e), "request_id": rid}, 403

    @app.errorhandler(404)
    def not_found(e):
        rid = getattr(request, "request_id", "-")
        _logger.info("[%s] 404 Not Found: %s %s", rid, request.method, request.path)
        return {"error": "Not found", "message": str(e), "request_id": rid}, 404

    @app.errorhandler(500)
    def internal_error(e):
        rid = getattr(request, "request_id", "-")
        _logger.error("[%s] 500 Internal Server Error: %s %s — %s", rid, request.method, request.path, e)
        return {"error": "Internal server error", "message": "An unexpected error occurred. Please contact support.", "request_id": rid}, 500

    @app.errorhandler(503)
    def service_unavailable(e):
        rid = getattr(request, "request_id", "-")
        _logger.error("[%s] 503 Service Unavailable: %s %s", rid, request.method, request.path)
        return {"error": MSG.SERVICE_UNAVAILABLE, "message": e.description, "request_id": rid}, 503

    @app.errorhandler(Exception)
    def unhandled_exception(e):
        rid = getattr(request, "request_id", "-")
        if isinstance(e, HTTPException):     # 413 / 415 / 429 ... keep their own status code
            return {"error": e.name, "message": e.description, "request_id": rid}, e.code or 500
        _logger.exception("[%s] Unhandled exception on %s %s", rid, request.method, request.path)
        return {"error": MSG.ERR_UNEXPECTED, "request_id": rid}, 500

    # Flask picks the most specific handler, so these win over the generic Exception handler above.
    @app.errorhandler(SupabaseError)
    def supabase_error(e):
        rid = getattr(request, "request_id", "-")
        code = str((e.details or {}).get("code") or "")
        if e.status_code == 401 or code in ("PGRST301", "PGRST302"):
            # token expired / rejected by PostgREST mid-request: stay a 401 so the client refreshes its session
            _logger.warning("[%s] Supabase rejected the session on %s %s (code=%s)", rid, request.method, request.path, code)
            return {"error": MSG.SESSION_INVALID, "request_id": rid}, 401
        if code == "42501" or e.status_code == 403:
            _logger.warning("[%s] Supabase denied access on %s %s (code=%s): %s", rid, request.method, request.path, code, e)
            return {"error": MSG.RESOURCE_ACCESS_DENIED, "request_id": rid}, 403
        if code == "23505":
            _logger.warning("[%s] Supabase duplicate on %s %s: %s", rid, request.method, request.path, e)
            return {"error": MSG.CONFLICT_ALREADY_EXISTS, "request_id": rid}, 409
        # Checked BEFORE the bare 409 status below: PostgREST also answers 409 for a foreign-key violation (23503),
        # which is a bad id sent by the caller (400), not "already exists".
        if code in _CLIENT_ERROR_CODES:
            _logger.warning("[%s] Supabase rejected input on %s %s (code=%s): %s", rid, request.method, request.path, code, e)
            return {"error": MSG.ERR_BAD_REQUEST, "request_id": rid}, 400
        if e.status_code == 409:
            _logger.warning("[%s] Supabase conflict on %s %s (code=%s): %s", rid, request.method, request.path, code, e)
            return {"error": MSG.CONFLICT_ALREADY_EXISTS, "request_id": rid}, 409
        if e.status_code >= 500 or e.status_code == 429:
            _logger.error("[%s] Supabase unavailable on %s %s: %s", rid, request.method, request.path, e)
            return {"error": MSG.SERVICE_UNAVAILABLE, "request_id": rid}, 503
        _logger.exception("[%s] Unexpected Supabase error on %s %s (code=%s)", rid, request.method, request.path, code)
        return {"error": MSG.ERR_UNEXPECTED, "request_id": rid}, 500

    @app.errorhandler(requests.exceptions.RequestException)
    def upstream_unreachable(e):
        # Supabase (and any other outbound HTTP call made through `requests`) timed out or could not connect
        rid = getattr(request, "request_id", "-")
        _logger.error("[%s] Upstream request failed on %s %s: %s", rid, request.method, request.path, e)
        return {"error": MSG.SERVICE_UNAVAILABLE, "request_id": rid}, 503

    return app
