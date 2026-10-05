import os
import re

from dotenv import load_dotenv

load_dotenv()


# Required before the app can start at all.
#
# These three were read with os.environ[...] inside the class body, which runs at
# IMPORT time. With any of them unset the process died with a bare
# `KeyError: 'SUPABASE_URL'` and no explanation — the service looked like it had
# deployed fine (pip install succeeds) but gunicorn never came up, so the API
# list simply never loaded. Fail loudly and name everything that is missing.
_REQUIRED_ENV = ("SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY", "SUPABASE_ANON_KEY")


def _assert_required_env():
    missing = [name for name in _REQUIRED_ENV if not (os.environ.get(name) or "").strip()]
    if missing:
        raise RuntimeError(
            "Missing required environment variable(s): "
            + ", ".join(missing)
            + ". The backend cannot start without them — set them on the host "
            "(Render → your service → Environment) and restart. "
            "Values come from Supabase → Project Settings → API. See .env.example."
        )


_assert_required_env()


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY") or os.environ.get("SESSION_SECRET", "change-me-in-production")
    JWT_SECRET = os.environ.get("JWT_SECRET") or os.environ.get("SUPABASE_JWT_SECRET") or os.environ.get("SECRET_KEY") or os.environ.get("SESSION_SECRET", "change-me-in-production")
    JWT_ALGORITHM = os.environ.get("JWT_ALGORITHM", "HS256")
    JWT_ACCESS_TOKEN_EXPIRES = int(os.environ.get("JWT_ACCESS_TOKEN_EXPIRES", 3600))
    JWT_REFRESH_TOKEN_EXPIRES = int(os.environ.get("JWT_REFRESH_TOKEN_EXPIRES", 2592000))
    JWT_REFRESH_WINDOW_MINUTES = int(os.environ.get("JWT_REFRESH_WINDOW_MINUTES", 5))

    # Outbound links (password reset, verification) are built from this, so a
    # stale or unset value mails users a link that does not resolve.
    FRONTEND_URL = os.environ.get("FRONTEND_URL", "https://holy-grills.vercel.app")
    AUTH_RESET_REDIRECT_PATH = os.environ.get("AUTH_RESET_REDIRECT_PATH", "/reset-password")
    AUTH_VERIFY_REDIRECT_PATH = os.environ.get("AUTH_VERIFY_REDIRECT_PATH", "/login")
    APP_NAME = os.environ.get("APP_NAME", "Holy Grills")
    APP_TAGLINE = os.environ.get("APP_TAGLINE", "Holy Grills FUTA")
    HP_CURRENCY_NAME = os.environ.get("HP_CURRENCY_NAME", "HP")
    SWAGGER_CONTACT_EMAIL = os.environ.get("SWAGGER_CONTACT_EMAIL", "dev@example.com")

    SUPABASE_URL = os.environ["SUPABASE_URL"]
    SUPABASE_SERVICE_ROLE_KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
    SUPABASE_ANON_KEY = os.environ["SUPABASE_ANON_KEY"]

    raw_origins = os.environ.get("CORS_ORIGINS") or os.environ.get("ALLOWED_ORIGINS", "")
    origins_set = {o.strip() for o in raw_origins.split(",") if o.strip() and o.strip() != "*"}
    frontend_env = os.environ.get("FRONTEND_URL")
    if frontend_env and frontend_env.strip() != "*":
        origins_set.add(frontend_env.strip())
    # Origins are environment-driven, with the known deployments as the default
    # so the API is not left on a wildcard. CORS_ORIGINS / ALLOWED_ORIGINS /
    # FRONTEND_URL (comma-separated) override this list entirely; a "*" in any of
    # them is ignored — pinning the list is the point.
    #
    DEFAULT_CORS_ORIGINS = (
        "https://holy-grills.vercel.app",
        "https://holygrill.app",
        "https://www.holygrill.app",
        # Local dev: vite dev server, vite preview, the static smoke server.
        "http://localhost:5173", "http://127.0.0.1:5173",
        "http://localhost:4173", "http://127.0.0.1:4173",
        "http://localhost:4174", "http://127.0.0.1:4174",
    )

    # The known origins are always allowed; env entries (CORS_ORIGINS /
    # ALLOWED_ORIGINS / FRONTEND_URL) only ADD to them — so a stale or missing
    # FRONTEND_URL can never lock the real frontend out of its own API.
    CORS_ORIGINS = sorted(set(DEFAULT_CORS_ORIGINS) | origins_set)

    # Vercel PREVIEW deployments get a fresh random host per push
    # (holy-grills-<hash>.vercel.app, holy-grills-git-<branch>-<scope>.vercel.app),
    # so a fixed allow-list can never keep up and every branch preview was
    # blocked by CORS — "Failed to fetch" on login, with the API itself fine.
    #
    # flask_cors' try_match() calls pattern.match() for any compiled regex in the
    # origins list, so a pattern covers every preview without opening CORS up.
    # Turn it off with ALLOW_VERCEL_PREVIEWS=false once you no longer need it.
    ALLOW_VERCEL_PREVIEWS = os.environ.get("ALLOW_VERCEL_PREVIEWS", "true").strip().lower() != "false"
    CORS_ORIGIN_PATTERNS = (
        [re.compile(r"^https://holy-grills[a-z0-9-]*\.vercel\.app$")] if ALLOW_VERCEL_PREVIEWS else []
    )

    PAYSTACK_SECRET_KEY = os.environ.get("PAYSTACK_SECRET_KEY", "")
    PAYSTACK_PUBLIC_KEY = os.environ.get("PAYSTACK_PUBLIC_KEY", "")
    # Paystack signs webhooks with the account secret key; there is no separate webhook secret in their dashboard.
    # Falls back to PAYSTACK_SECRET_KEY so any code reading this setting agrees with webhooks.py's own fallback.
    PAYSTACK_WEBHOOK_SECRET = os.environ.get("PAYSTACK_WEBHOOK_SECRET") or os.environ.get("PAYSTACK_SECRET_KEY", "")
    PAYSTACK_PREFERRED_BANK = os.environ.get("PAYSTACK_PREFERRED_BANK", "wema-bank")

    FLUTTERWAVE_SECRET_KEY = os.environ.get("FLUTTERWAVE_SECRET_KEY", "")
    FLUTTERWAVE_WEBHOOK_SECRET = os.environ.get("FLUTTERWAVE_WEBHOOK_SECRET", "")

    # Cloudinary — used by the direct-upload signature endpoint (admins: any folder; everyone else: their own profile_photos/<user_id> folder).
    # The cloud name is the account's public identifier, not a secret. It falls back
    # to the live account so uploads keep working when the env var is absent; a value
    # in the environment still wins.
    CLOUDINARY_CLOUD_NAME = os.environ.get("CLOUDINARY_CLOUD_NAME") or "risvlfhx"
    CLOUDINARY_API_KEY = os.environ.get("CLOUDINARY_API_KEY", "")
    CLOUDINARY_API_SECRET = os.environ.get("CLOUDINARY_API_SECRET", "")

    # Email — Resend (primary); OneSignal kept for push-only
    RESEND_API_KEY = os.environ.get("RESEND_API_KEY", "")
    EMAIL_FROM = os.environ.get("EMAIL_FROM", "noreply@holygrills.ng")
    EMAIL_FROM_NAME = os.environ.get("EMAIL_FROM_NAME", "Holy Grills")

    # Push — OneSignal
    ONESIGNAL_APP_ID = os.environ.get("ONESIGNAL_APP_ID", "")
    ONESIGNAL_API_KEY = os.environ.get("ONESIGNAL_API_KEY", "")

    REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
    CELERY_BROKER_URL = os.environ.get("CELERY_BROKER_URL", os.environ.get("REDIS_URL", "redis://localhost:6379/0"))
    CELERY_RESULT_BACKEND = os.environ.get("CELERY_RESULT_BACKEND", os.environ.get("REDIS_URL", "redis://localhost:6379/0"))

    # ── Registration / validation ──────────────────────────────────────────────
    MINIMUM_AGE = int(os.environ.get("MINIMUM_AGE", "16"))
    PHONE_REGEX_PATTERN = os.environ.get("PHONE_REGEX_PATTERN", r"^\+234\d{10}$")

    # ── Ordering window ────────────────────────────────────────────────────────
    ORDERING_WINDOW_OPEN_TIME  = os.environ.get("ORDERING_WINDOW_OPEN_TIME", "08:00")
    ORDERING_WINDOW_CLOSE_TIME = os.environ.get("ORDERING_WINDOW_CLOSE_TIME", "16:00")
    CALLBACK_WINDOW_MINUTES    = int(os.environ.get("CALLBACK_WINDOW_MINUTES", "30"))

    # ── HP Economy constants ───────────────────────────────────────────────────
    HP_PER_NAIRA_FOOD   = float(os.environ.get("HP_PER_NAIRA_FOOD", "0.1"))
    HP_UNLOCK_RATE_PCT  = float(os.environ.get("HP_UNLOCK_RATE_PCT", "0.30"))

    # HP Award amounts
    SIGNUP_BONUS_HP = int(os.environ.get("SIGNUP_BONUS_HP", "0"))
    WELCOME_BONUS_HP = int(os.environ.get("WELCOME_BONUS_HP", "50"))
    REVIEW_HP = int(os.environ.get("REVIEW_HP", "20"))
    REFERRAL_HP = int(os.environ.get("REFERRAL_HP", "75"))
    EVENT_CHECKIN_HP = int(os.environ.get("EVENT_CHECKIN_HP", "40"))
    BIRTHDAY_HP = int(os.environ.get("BIRTHDAY_HP", "150"))
    WALLET_TOPUP_HP = int(os.environ.get("WALLET_TOPUP_HP", "50"))
    WALLET_TOPUP_MIN = float(os.environ.get("WALLET_TOPUP_MIN", "3000"))
    SUBSCRIPTION_HP = int(os.environ.get("SUBSCRIPTION_HP", "50"))
    SOCIAL_SHARE_HP = int(os.environ.get("SOCIAL_SHARE_HP", "25"))

    try:
        import json as _json
        _env_perks = os.environ.get("TIER_PERKS")
        if _env_perks:
            TIER_PERKS = _json.loads(_env_perks)
        else:
            from app.services.tier_service import DEFAULT_TIER_PERKS
            TIER_PERKS = DEFAULT_TIER_PERKS
    except Exception:
        from app.services.tier_service import DEFAULT_TIER_PERKS
        TIER_PERKS = DEFAULT_TIER_PERKS

    # Flash redemption
    FLASH_DISCOUNT_PCT = float(os.environ.get("FLASH_DISCOUNT_PCT", "0.50"))
    FLASH_MAX_QTY = int(os.environ.get("FLASH_MAX_QTY", "5"))

    # HP Bundle (event hosts)
    HP_BUNDLE_PRICE_PER_HP = float(os.environ.get("HP_BUNDLE_PRICE_PER_HP", "5.0"))
    HP_BUNDLE_MIN_PURCHASE = int(os.environ.get("HP_BUNDLE_MIN_PURCHASE", "100"))

    # HP Bundle tier definitions — configurable without a deploy.
    # Override via HP_BUNDLES env var as a JSON array of {hp, label} objects.
    # Example: '[{"hp":200,"label":"Lite"},{"hp":500,"label":"Pro"}]'
    # Price per HP is still controlled by HP_BUNDLE_PRICE_PER_HP.
    _hp_bundles_default = '[{"hp":100,"label":"Starter"},{"hp":250,"label":"Basic"},{"hp":500,"label":"Standard"},{"hp":1000,"label":"Premium"},{"hp":2500,"label":"Elite"}]'
    try:
        import json as _json
        HP_BUNDLES = _json.loads(os.environ.get("HP_BUNDLES", _hp_bundles_default))
    except Exception:
        HP_BUNDLES = [
            {"hp": 100,  "label": "Starter"},
            {"hp": 250,  "label": "Basic"},
            {"hp": 500,  "label": "Standard"},
            {"hp": 1000, "label": "Premium"},
            {"hp": 2500, "label": "Elite"},
        ]

    # Transaction reference prefixes — override to match your own naming scheme
    WALLET_REF_PREFIX      = os.environ.get("WALLET_REF_PREFIX",      "HG-WALLET-")

    # Paystack sandbox mock: set PAYSTACK_SANDBOX_MOCK_NUBAN=true in development
    # to get a fake virtual account when real NUBAN provisioning isn't available.
    PAYSTACK_SANDBOX_MOCK_NUBAN = os.environ.get("PAYSTACK_SANDBOX_MOCK_NUBAN", "false").lower() == "true"

    TIER_GRACE_PERIOD_DAYS = int(os.environ.get("TIER_GRACE_PERIOD_DAYS", "7"))

    # Marketplace / Cart
    LOW_CODE_INVENTORY_THRESHOLD = int(os.environ.get("LOW_CODE_INVENTORY_THRESHOLD", "5"))
    ABANDONED_CART_MINUTES = int(os.environ.get("ABANDONED_CART_MINUTES", "60"))
    MARKETPLACE_PURCHASE_HP = int(os.environ.get("MARKETPLACE_PURCHASE_HP", "50"))
    MARKETPLACE_DEFAULT_VENDOR_NAME = os.environ.get("MARKETPLACE_DEFAULT_VENDOR_NAME", APP_NAME)

    # ── Squad Order ───────────────────────────────────────────────────────────
    # When a single order contains >= SQUAD_ORDER_MIN_ITEMS distinct item lines,
    # it qualifies as a "squad order" and may earn a delivery-fee and/or
    # subtotal discount. Both discounts can be toggled independently.
    SQUAD_ORDER_ENABLED = os.environ.get("SQUAD_ORDER_ENABLED", "true").lower() == "true"
    SQUAD_ORDER_MIN_ITEMS = int(os.environ.get("SQUAD_ORDER_MIN_ITEMS", "3"))
    SQUAD_ORDER_MAX_ITEMS = int(os.environ.get("SQUAD_ORDER_MAX_ITEMS", "6"))
    SQUAD_MAX_MEMBERS = int(os.environ.get("SQUAD_MAX_MEMBERS", "20"))
    # Delivery-fee discount: percentage of delivery_fee to waive (0-100)
    SQUAD_DELIVERY_DISCOUNT_ENABLED = os.environ.get("SQUAD_DELIVERY_DISCOUNT_ENABLED", "true").lower() == "true"
    SQUAD_DELIVERY_DISCOUNT_PCT = float(os.environ.get("SQUAD_DELIVERY_DISCOUNT_PCT", "100"))
    # Order-subtotal discount: percentage discount on the subtotal (0-100)
    SQUAD_ORDER_DISCOUNT_ENABLED = os.environ.get("SQUAD_ORDER_DISCOUNT_ENABLED", "false").lower() == "true"
    SQUAD_ORDER_DISCOUNT_PCT = float(os.environ.get("SQUAD_ORDER_DISCOUNT_PCT", "10"))

    # Graduation HP bonus (one-time, on first claim after reaching graduation level)
    GRADUATION_HP = int(os.environ.get("GRADUATION_HP", "1000"))

    # HP transfer constraints
    HP_TRANSFER_MIN_AMOUNT  = int(os.environ.get("HP_TRANSFER_MIN_AMOUNT",  "10"))
    HP_TRANSFER_MIN_ORDERS  = int(os.environ.get("HP_TRANSFER_MIN_ORDERS",  "3"))

    # Wallet minimum top-up via card
    WALLET_MIN_CARD_TOPUP = float(os.environ.get("WALLET_MIN_CARD_TOPUP", "100"))

    # ── New Features ──────────────────────────────────────────────────────────
    # Login streak
    LOGIN_STREAK_HP = int(os.environ.get("LOGIN_STREAK_HP", "2"))

    # Monthly free-activity HP cap (challenges, events, reviews, login streak, social shares)
    MONTHLY_HP_CAP = int(os.environ.get("MONTHLY_HP_CAP", "800"))

    # HP decay (replaces old 90-day expiry breakage model)
    HP_DECAY_ONSET_DAYS = int(os.environ.get("HP_DECAY_ONSET_DAYS", "120"))
    HP_DECAY_RATE_MONTHLY = float(os.environ.get("HP_DECAY_RATE_MONTHLY", "0.10"))

    # Win-back notification schedule (days of inactivity)
    WINBACK_DAY1 = int(os.environ.get("WINBACK_DAY1", "70"))
    WINBACK_DAY2 = int(os.environ.get("WINBACK_DAY2", "95"))
    WINBACK_DAY3 = int(os.environ.get("WINBACK_DAY3", "118"))

    # First-order gift (toggled in system_settings table)
    FIRST_ORDER_GIFT_ENABLED = os.environ.get("FIRST_ORDER_GIFT_ENABLED", "true").lower() == "true"

    # Order-confirmation share prompt HP
    SHARE_PROMPT_HP = int(os.environ.get("SHARE_PROMPT_HP", "25"))

    # Squad HP split toggle
    SQUAD_HP_SPLIT_ENABLED = os.environ.get("SQUAD_HP_SPLIT_ENABLED", "true").lower() == "true"

    # Squad referral attribution window (days after being added to a squad)
    SQUAD_REFERRAL_WINDOW_DAYS = int(os.environ.get("SQUAD_REFERRAL_WINDOW_DAYS", "7"))

    # Order lock maximum reschedules
    ORDER_LOCK_MAX_RESCHEDULES = int(os.environ.get("ORDER_LOCK_MAX_RESCHEDULES", "1"))
    ORDER_LOCK_MAX_DISCOUNT_PCT = float(os.environ.get("ORDER_LOCK_MAX_DISCOUNT_PCT", "50"))
    ORDER_LOCK_DEFAULT_DISCOUNT_PCT = float(os.environ.get("ORDER_LOCK_DEFAULT_DISCOUNT_PCT", "10"))

    # Login streak — weekly completion bonuses (HP to Pending pool).
    # These are the defaults if the login_streak_rewards DB table is absent/empty.
    LOGIN_STREAK_WEEK1_HP = int(os.environ.get("LOGIN_STREAK_WEEK1_HP", "25"))
    LOGIN_STREAK_WEEK2_HP = int(os.environ.get("LOGIN_STREAK_WEEK2_HP", "40"))
    LOGIN_STREAK_WEEK3_HP = int(os.environ.get("LOGIN_STREAK_WEEK3_HP", "60"))
    LOGIN_STREAK_WEEK4_HP = int(os.environ.get("LOGIN_STREAK_WEEK4_HP", "80"))

    # Streak tolerance — missed days allowed per 7-day cycle before the cycle breaks
    STREAK_MAX_MISSED_DAYS = int(os.environ.get("STREAK_MAX_MISSED_DAYS", "2"))

    # Minimum wallet top-up (₦) to reclaim a missed streak day
    STREAK_RECLAIM_MIN_TOPUP = float(os.environ.get("STREAK_RECLAIM_MIN_TOPUP", "1000"))

    # Notification throttle defaults (also editable per-admin in system_settings table)
    NOTIFICATION_GAP_MINUTES = int(os.environ.get("NOTIFICATION_GAP_MINUTES", "30"))
    NOTIFICATION_DAILY_CAP = int(os.environ.get("NOTIFICATION_DAILY_CAP", "20"))

    # Leaderboard pagination limits
    LEADERBOARD_DEFAULT_LIMIT = int(os.environ.get("LEADERBOARD_DEFAULT_LIMIT", "10"))
    LEADERBOARD_MAX_LIMIT = int(os.environ.get("LEADERBOARD_MAX_LIMIT", "50"))

    # Request body size limit (Flask MAX_CONTENT_LENGTH)
    MAX_CONTENT_LENGTH = int(os.environ.get("MAX_CONTENT_LENGTH_MB", "10")) * 1024 * 1024

    # Reward fulfilment time communicated in email (hours)
    REWARD_FULFILMENT_HOURS = int(os.environ.get("REWARD_FULFILMENT_HOURS", "24"))

    # ── Free Side Credits ─────────────────────────────────────────────────────
    FREE_SIDE_CREDITS_VALIDITY_DAYS = int(os.environ.get("FREE_SIDE_CREDITS_VALIDITY_DAYS", "60"))

    # ── Exclusive Spin ────────────────────────────────────────────────────────
    # Credits are leaderboard rewards only; there is no HP purchase path.
    EXCLUSIVE_SPIN_VALIDITY_DAYS = int(os.environ.get("EXCLUSIVE_SPIN_VALIDITY_DAYS", "30"))

    # Exclusive spin prize template — configurable without deploy.
    # This is only used when the `exclusive_spin_prizes` DB table is empty; the table itself is the
    # real admin-configurable source of weights (weight column, editable without a deploy). Weights
    # below are a reasonable placeholder distribution, not a spec value — the rewards doc names the
    # 7 outcomes but doesn't give exact weights, so adjust via the DB table rather than here.
    _exc_spin_default = '[{"name":"+300 HP","weight":25},{"name":"+750 HP","weight":8},{"name":"Free Sausage","weight":15},{"name":"Free Gizzard \u00d72","weight":12},{"name":"Free Side of Choice","weight":15},{"name":"Free Chicken Kebab","weight":15},{"name":"Free Delivery","weight":10}]'
    try:
        import json as _json
        EXCLUSIVE_SPIN_TEMPLATE_ITEMS = _json.loads(os.environ.get("EXCLUSIVE_SPIN_TEMPLATE_ITEMS", _exc_spin_default))
    except Exception:
        EXCLUSIVE_SPIN_TEMPLATE_ITEMS = [
            {"name": "+300 HP",              "weight": 25},
            {"name": "+750 HP",              "weight": 8},
            {"name": "Free Sausage",         "weight": 15},
            {"name": "Free Gizzard ×2",      "weight": 12},
            {"name": "Free Side of Choice",  "weight": 15},
            {"name": "Free Chicken Kebab",   "weight": 15},
            {"name": "Free Delivery",        "weight": 10},
        ]

    # Free side options (admin-configurable via system_settings.free_side_options)
    _free_sides_default = '["Fries","Coleslaw","Plantain","Gizzard"]'
    try:
        import json as _json
        FREE_SIDE_OPTIONS = _json.loads(os.environ.get("FREE_SIDE_OPTIONS", _free_sides_default))
    except Exception:
        FREE_SIDE_OPTIONS = ["Fries", "Coleslaw", "Plantain", "Gizzard"]

    # ── Order Streak Rewards (config fallback; DB table is authoritative) ─────
    _order_streak_default = '{"3":100,"6":200,"12":350}'
    try:
        import json as _json
        ORDER_STREAK_REWARDS = _json.loads(os.environ.get("ORDER_STREAK_REWARDS", _order_streak_default))
    except Exception:
        ORDER_STREAK_REWARDS = {"3": 100, "6": 200, "12": 350}

    # ── Membership Rewards (config fallback; DB table is authoritative) ───────
    _membership_default = '{"3":100,"6":200,"12":500,"24":750,"36":1000,"48":1250,"60":1500}'
    try:
        import json as _json
        MEMBERSHIP_REWARDS = _json.loads(os.environ.get("MEMBERSHIP_REWARDS", _membership_default))
    except Exception:
        MEMBERSHIP_REWARDS = {"3": 100, "6": 200, "12": 500, "24": 750, "36": 1000, "48": 1250, "60": 1500}

    # ── Rate limits (requests / window_seconds per IP) ─────────────────────────
    RATE_LIMIT_REGISTER_REQUESTS  = int(os.environ.get("RATE_LIMIT_REGISTER_REQUESTS",  "10"))
    RATE_LIMIT_REGISTER_WINDOW    = int(os.environ.get("RATE_LIMIT_REGISTER_WINDOW",    "3600"))
    RATE_LIMIT_LOGIN_REQUESTS     = int(os.environ.get("RATE_LIMIT_LOGIN_REQUESTS",     "20"))
    RATE_LIMIT_LOGIN_WINDOW       = int(os.environ.get("RATE_LIMIT_LOGIN_WINDOW",       "900"))
    RATE_LIMIT_ORDERS_REQUESTS    = int(os.environ.get("RATE_LIMIT_ORDERS_REQUESTS",    "10"))
    RATE_LIMIT_ORDERS_WINDOW      = int(os.environ.get("RATE_LIMIT_ORDERS_WINDOW",      "300"))
    RATE_LIMIT_RESET_PW_REQUESTS  = int(os.environ.get("RATE_LIMIT_RESET_PW_REQUESTS",  "5"))
    RATE_LIMIT_RESET_PW_WINDOW    = int(os.environ.get("RATE_LIMIT_RESET_PW_WINDOW",    "3600"))
    RATE_LIMIT_REFRESH_REQUESTS   = int(os.environ.get("RATE_LIMIT_REFRESH_REQUESTS",   "30"))
    RATE_LIMIT_REFRESH_WINDOW     = int(os.environ.get("RATE_LIMIT_REFRESH_WINDOW",     "60"))
    RATE_LIMIT_VERIFY_EMAIL_REQUESTS   = int(os.environ.get("RATE_LIMIT_VERIFY_EMAIL_REQUESTS",   "3"))
    RATE_LIMIT_VERIFY_EMAIL_WINDOW     = int(os.environ.get("RATE_LIMIT_VERIFY_EMAIL_WINDOW",     "3600"))
    RATE_LIMIT_DEVICE_TOKEN_REQUESTS   = int(os.environ.get("RATE_LIMIT_DEVICE_TOKEN_REQUESTS",   "20"))
    RATE_LIMIT_DEVICE_TOKEN_WINDOW     = int(os.environ.get("RATE_LIMIT_DEVICE_TOKEN_WINDOW",     "3600"))

    DEBUG = os.environ.get("FLASK_DEBUG", "false").lower() == "true"
    TESTING = False


class DevelopmentConfig(Config):
    DEBUG = True


class ProductionConfig(Config):
    DEBUG = False


config_map = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
    "default": DevelopmentConfig,
}
