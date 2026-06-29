from flask import Flask
from flask_cors import CORS
from flasgger import Swagger

from app.config import Config
from app.routes.auth import auth_bp
from app.routes.menu import menu_bp
from app.routes.orders import orders_bp
from app.routes.hp import hp_bp
from app.routes.wallet import wallet_bp
from app.routes.rewards import rewards_bp
from app.routes.marketplace import marketplace_bp
from app.routes.events import events_bp
from app.routes.referrals import referrals_bp
from app.routes.notifications import notifications_bp
from app.routes.admin import admin_bp
from app.routes.kitchen import kitchen_bp
from app.routes.riders import riders_bp
from app.routes.leaderboard import leaderboard_bp
from app.routes.challenges import challenges_bp
from app.routes.webhooks import webhooks_bp
from app.routes.storefront import storefront_bp
from app.routes.analytics import analytics_bp


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    CORS(app, resources={r"/api/*": {"origins": app.config["CORS_ORIGINS"]}})

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
    swagger_template = {
        "swagger": "2.0",
        "info": {
            "title": "Holy Grills API",
            "description": "Backend API for the Holy Grills Student Participation Engine — HP ecosystem, food ordering, marketplace, events, wallet, and admin operations.",
            "version": "1.0.0",
            "contact": {"email": "dev@holygrills.ng"},
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
    app.register_blueprint(menu_bp, url_prefix="/api/menu")
    app.register_blueprint(orders_bp, url_prefix="/api/orders")
    app.register_blueprint(hp_bp, url_prefix="/api/hp")
    app.register_blueprint(wallet_bp, url_prefix="/api/wallet")
    app.register_blueprint(rewards_bp, url_prefix="/api/rewards")
    app.register_blueprint(marketplace_bp, url_prefix="/api/marketplace")
    app.register_blueprint(events_bp, url_prefix="/api/events")
    app.register_blueprint(referrals_bp, url_prefix="/api/referrals")
    app.register_blueprint(notifications_bp, url_prefix="/api/notifications")
    app.register_blueprint(admin_bp, url_prefix="/api/admin")
    app.register_blueprint(kitchen_bp, url_prefix="/api/kitchen")
    app.register_blueprint(riders_bp, url_prefix="/api/riders")
    app.register_blueprint(leaderboard_bp, url_prefix="/api/leaderboard")
    app.register_blueprint(challenges_bp, url_prefix="/api/challenges")
    app.register_blueprint(webhooks_bp, url_prefix="/api/webhooks")
    app.register_blueprint(storefront_bp, url_prefix="/api/storefront")
    app.register_blueprint(analytics_bp, url_prefix="/api/analytics")

    @app.route("/api/health")
    def health():
        import os, requests as req
        status = {"status": "ok", "api": "Holy Grills", "version": "1.0.0"}
        try:
            url = os.environ.get("SUPABASE_URL", "").rstrip("/")
            key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
            r = req.get(
                f"{url}/rest/v1/profiles?select=id&limit=1",
                headers={"apikey": key, "Authorization": f"Bearer {key}"},
                timeout=5,
            )
            status["supabase"] = "connected" if r.status_code < 400 else f"error:{r.status_code}"
        except Exception as exc:
            status["supabase"] = f"unreachable:{str(exc)[:60]}"
        return status, 200

    @app.errorhandler(400)
    def bad_request(e):
        return {"error": "Bad request", "message": str(e)}, 400

    @app.errorhandler(401)
    def unauthorized(e):
        return {"error": "Unauthorized", "message": str(e)}, 401

    @app.errorhandler(403)
    def forbidden(e):
        return {"error": "Forbidden", "message": str(e)}, 403

    @app.errorhandler(404)
    def not_found(e):
        return {"error": "Not found", "message": str(e)}, 404

    @app.errorhandler(500)
    def internal_error(e):
        return {"error": "Internal server error", "message": str(e)}, 500

    return app
