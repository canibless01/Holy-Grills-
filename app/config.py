import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY") or os.environ.get("SESSION_SECRET", "change-me-in-production")
    JWT_SECRET = os.environ.get("JWT_SECRET") or os.environ.get("SUPABASE_JWT_SECRET") or os.environ.get("SECRET_KEY") or os.environ.get("SESSION_SECRET", "change-me-in-production")
    JWT_ALGORITHM = os.environ.get("JWT_ALGORITHM", "HS256")
    JWT_ACCESS_TOKEN_EXPIRES = int(os.environ.get("JWT_ACCESS_TOKEN_EXPIRES", 3600))
    JWT_REFRESH_TOKEN_EXPIRES = int(os.environ.get("JWT_REFRESH_TOKEN_EXPIRES", 2592000))

    FRONTEND_URL = os.environ.get("FRONTEND_URL", "http://localhost:3000")
    APP_NAME = os.environ.get("APP_NAME", "Holy Grills")
    APP_TAGLINE = os.environ.get("APP_TAGLINE", "Holy Grills FUTA")

    SUPABASE_URL = os.environ["SUPABASE_URL"]
    SUPABASE_SERVICE_ROLE_KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
    SUPABASE_ANON_KEY = os.environ["SUPABASE_ANON_KEY"]

    CORS_ORIGINS = os.environ.get("CORS_ORIGINS", "*").split(",")

    PAYSTACK_SECRET_KEY = os.environ.get("PAYSTACK_SECRET_KEY", "")
    PAYSTACK_PUBLIC_KEY = os.environ.get("PAYSTACK_PUBLIC_KEY", "")
    PAYSTACK_WEBHOOK_SECRET = os.environ.get("PAYSTACK_WEBHOOK_SECRET", "")
    PAYSTACK_PREFERRED_BANK = os.environ.get("PAYSTACK_PREFERRED_BANK", "wema-bank")

    FLUTTERWAVE_SECRET_KEY = os.environ.get("FLUTTERWAVE_SECRET_KEY", "")
    FLUTTERWAVE_WEBHOOK_SECRET = os.environ.get("FLUTTERWAVE_WEBHOOK_SECRET", "")

    # Email — OneSignal
    ONESIGNAL_APP_ID = os.environ.get("ONESIGNAL_APP_ID", "")
    ONESIGNAL_API_KEY = os.environ.get("ONESIGNAL_API_KEY", "")
    EMAIL_FROM = os.environ.get("EMAIL_FROM", "noreply@holygrills.ng")
    EMAIL_FROM_NAME = os.environ.get("EMAIL_FROM_NAME", "Holy Grills")

    REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
    CELERY_BROKER_URL = os.environ.get("CELERY_BROKER_URL", os.environ.get("REDIS_URL", "redis://localhost:6379/0"))
    CELERY_RESULT_BACKEND = os.environ.get("CELERY_RESULT_BACKEND", os.environ.get("REDIS_URL", "redis://localhost:6379/0"))

    # ── HP Economy constants ───────────────────────────────────────────────────
    HP_LIABILITY_VALUE = float(os.environ.get("HP_LIABILITY_VALUE", "0.185"))
    HP_PER_NAIRA_FOOD = float(os.environ.get("HP_PER_NAIRA_FOOD", "0.1"))
    HP_UNLOCK_RATE = int(os.environ.get("HP_UNLOCK_RATE", "100"))
    PENDING_CEILING_RATIO = float(os.environ.get("PENDING_CEILING_RATIO", "0.35"))
    PENDING_FLOOR_HP = int(os.environ.get("PENDING_FLOOR_HP", "200"))

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

    # Tier multipliers (slugs match live hp_tiers table)
    TIER_MULTIPLIERS = {
        "starter":  1.00,
        "ember":    1.00,
        "regular":  1.10,
        "flame":    1.08,
        "champion": 1.25,
        "blaze":    1.15,
        "elite":    1.50,
        "holy":     1.25,
    }

    # Tier HP thresholds (rolling 120-day)
    TIER_THRESHOLDS = {
        "starter":  0,
        "regular":  1000,
        "champion": 5000,
        "elite":    12000,
    }

    # Referral milestones
    REFERRAL_MILESTONE_1_COUNT = int(os.environ.get("REFERRAL_MILESTONE_1_COUNT", "5"))
    REFERRAL_MILESTONE_2_COUNT = int(os.environ.get("REFERRAL_MILESTONE_2_COUNT", "10"))
    REFERRAL_MILESTONE_5_HP = int(os.environ.get("REFERRAL_MILESTONE_5_HP", "150"))
    REFERRAL_MILESTONE_10_HP = int(os.environ.get("REFERRAL_MILESTONE_10_HP", "400"))

    # Flash redemption
    FLASH_DISCOUNT_PCT = float(os.environ.get("FLASH_DISCOUNT_PCT", "0.50"))
    FLASH_MAX_QTY = int(os.environ.get("FLASH_MAX_QTY", "5"))

    # HP Bundle (event hosts)
    HP_BUNDLE_PRICE_PER_HP = float(os.environ.get("HP_BUNDLE_PRICE_PER_HP", "5.0"))
    HP_BUNDLE_MIN_PURCHASE = int(os.environ.get("HP_BUNDLE_MIN_PURCHASE", "100"))

    # HP Expiry
    HP_EXPIRY_INACTIVITY_DAYS = int(os.environ.get("HP_EXPIRY_INACTIVITY_DAYS", "90"))
    HP_EXPIRY_BREAKAGE_RATE = float(os.environ.get("HP_EXPIRY_BREAKAGE_RATE", "0.25"))
    HP_EXPIRY_WARNING_EARLY_DAYS = int(os.environ.get("HP_EXPIRY_WARNING_EARLY_DAYS", "14"))
    HP_EXPIRY_WARNING_LATE_DAYS = int(os.environ.get("HP_EXPIRY_WARNING_LATE_DAYS", "3"))
    TIER_GRACE_PERIOD_DAYS = int(os.environ.get("TIER_GRACE_PERIOD_DAYS", "7"))

    # Event / Challenge caps
    EVENT_CHECKIN_CAP_PER_MONTH = int(os.environ.get("EVENT_CHECKIN_CAP_PER_MONTH", "3"))
    CHALLENGE_MAX_HP_REWARD = int(os.environ.get("CHALLENGE_MAX_HP_REWARD", "100"))

    # Marketplace / Cart
    LOW_CODE_INVENTORY_THRESHOLD = int(os.environ.get("LOW_CODE_INVENTORY_THRESHOLD", "5"))
    ABANDONED_CART_MINUTES = int(os.environ.get("ABANDONED_CART_MINUTES", "60"))
    MARKETPLACE_PURCHASE_HP = int(os.environ.get("MARKETPLACE_PURCHASE_HP", "50"))

    # ── Squad Order ───────────────────────────────────────────────────────────
    # When a single order contains >= SQUAD_ORDER_MIN_ITEMS distinct item lines,
    # it qualifies as a "squad order" and may earn a delivery-fee and/or
    # subtotal discount. Both discounts can be toggled independently.
    SQUAD_ORDER_ENABLED = os.environ.get("SQUAD_ORDER_ENABLED", "true").lower() == "true"
    SQUAD_ORDER_MIN_ITEMS = int(os.environ.get("SQUAD_ORDER_MIN_ITEMS", "3"))
    SQUAD_ORDER_MAX_ITEMS = int(os.environ.get("SQUAD_ORDER_MAX_ITEMS", "20"))
    # Delivery-fee discount: percentage of delivery_fee to waive (0-100)
    SQUAD_DELIVERY_DISCOUNT_ENABLED = os.environ.get("SQUAD_DELIVERY_DISCOUNT_ENABLED", "true").lower() == "true"
    SQUAD_DELIVERY_DISCOUNT_PCT = float(os.environ.get("SQUAD_DELIVERY_DISCOUNT_PCT", "100"))
    # Order-subtotal discount: percentage discount on the subtotal (0-100)
    SQUAD_ORDER_DISCOUNT_ENABLED = os.environ.get("SQUAD_ORDER_DISCOUNT_ENABLED", "false").lower() == "true"
    SQUAD_ORDER_DISCOUNT_PCT = float(os.environ.get("SQUAD_ORDER_DISCOUNT_PCT", "10"))

    # Spin wheel cost
    SPIN_COST_HP = int(os.environ.get("SPIN_COST_HP", "10"))

    # Wallet minimum top-up via card
    WALLET_MIN_CARD_TOPUP = float(os.environ.get("WALLET_MIN_CARD_TOPUP", "100"))

    # Reward fulfilment time communicated in email (hours)
    REWARD_FULFILMENT_HOURS = int(os.environ.get("REWARD_FULFILMENT_HOURS", "24"))

    # ── Rate limits (requests / window_seconds per IP) ─────────────────────────
    RATE_LIMIT_REGISTER_REQUESTS = int(os.environ.get("RATE_LIMIT_REGISTER_REQUESTS", "10"))
    RATE_LIMIT_REGISTER_WINDOW   = int(os.environ.get("RATE_LIMIT_REGISTER_WINDOW",   "3600"))
    RATE_LIMIT_LOGIN_REQUESTS    = int(os.environ.get("RATE_LIMIT_LOGIN_REQUESTS",    "20"))
    RATE_LIMIT_LOGIN_WINDOW      = int(os.environ.get("RATE_LIMIT_LOGIN_WINDOW",      "900"))
    RATE_LIMIT_ORDERS_REQUESTS   = int(os.environ.get("RATE_LIMIT_ORDERS_REQUESTS",   "10"))
    RATE_LIMIT_ORDERS_WINDOW     = int(os.environ.get("RATE_LIMIT_ORDERS_WINDOW",     "300"))
    RATE_LIMIT_RESET_PW_REQUESTS = int(os.environ.get("RATE_LIMIT_RESET_PW_REQUESTS", "5"))
    RATE_LIMIT_RESET_PW_WINDOW   = int(os.environ.get("RATE_LIMIT_RESET_PW_WINDOW",   "3600"))

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
