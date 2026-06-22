import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY") or os.environ.get("SESSION_SECRET", "change-me-in-production")
    JWT_SECRET = os.environ.get("JWT_SECRET") or os.environ.get("SUPABASE_JWT_SECRET") or os.environ.get("SECRET_KEY") or os.environ.get("SESSION_SECRET", "change-me-in-production")
    JWT_ALGORITHM = "HS256"
    JWT_ACCESS_TOKEN_EXPIRES = 3600
    JWT_REFRESH_TOKEN_EXPIRES = 2592000

    SUPABASE_URL = os.environ["SUPABASE_URL"]
    SUPABASE_SERVICE_ROLE_KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
    SUPABASE_ANON_KEY = os.environ["SUPABASE_ANON_KEY"]

    CORS_ORIGINS = os.environ.get("CORS_ORIGINS", "*").split(",")

    PAYSTACK_SECRET_KEY = os.environ.get("PAYSTACK_SECRET_KEY", "")
    PAYSTACK_PUBLIC_KEY = os.environ.get("PAYSTACK_PUBLIC_KEY", "")
    PAYSTACK_WEBHOOK_SECRET = os.environ.get("PAYSTACK_WEBHOOK_SECRET", "")

    FLUTTERWAVE_SECRET_KEY = os.environ.get("FLUTTERWAVE_SECRET_KEY", "")
    FLUTTERWAVE_WEBHOOK_SECRET = os.environ.get("FLUTTERWAVE_WEBHOOK_SECRET", "")

    SENDGRID_API_KEY = os.environ.get("SENDGRID_API_KEY", "")
    EMAIL_FROM = os.environ.get("EMAIL_FROM", "noreply@holygrills.ng")
    EMAIL_FROM_NAME = os.environ.get("EMAIL_FROM_NAME", "Holy Grills")

    REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
    CELERY_BROKER_URL = os.environ.get("CELERY_BROKER_URL", REDIS_URL)
    CELERY_RESULT_BACKEND = os.environ.get("CELERY_RESULT_BACKEND", REDIS_URL)

    # HP Economy constants — from Master Brand Document
    HP_LIABILITY_VALUE = 0.185          # ₦0.185 per HP (internal)
    HP_PER_NAIRA_FOOD = 0.1             # 1 HP per ₦10 = 0.1 HP/₦
    HP_UNLOCK_RATE = 100                # 100 HP unlocked per ₦1,000 food spend
    PENDING_CEILING_RATIO = 0.35        # pending pool max = 35% of active balance
    PENDING_FLOOR_HP = 200              # floor for new/low-balance accounts

    # HP Award amounts — from Master Brand Document (final values)
    WELCOME_BONUS_HP = 50               # 50 HP active on first order
    REVIEW_HP = 20                      # 20 HP → PENDING, monthly cap 1×
    REFERRAL_HP = 75                    # 75 HP → PENDING per completed referral (no monthly cap)
    EVENT_CHECKIN_HP = 40               # 40 HP → PENDING, monthly cap 3×
    BIRTHDAY_HP = 150                   # 150 HP → ACTIVE, 30-day window
    WALLET_TOPUP_HP = 50                # 50 HP → ACTIVE on wallet top-up ≥ ₦3,000
    WALLET_TOPUP_MIN = 3000             # Min ₦3,000 to earn wallet top-up HP
    SUBSCRIPTION_HP = 50                # 50 HP → ACTIVE on newsletter sub
    SOCIAL_SHARE_HP = 25                # 25 HP → PENDING per valid social share

    # Tier multipliers (earn bonus on food order HP)
    TIER_MULTIPLIERS = {
        "ember": 1.00,
        "flame": 1.08,
        "blaze": 1.15,
        "holy":  1.25,
    }

    # Tier HP thresholds (rolling 120-day)
    TIER_THRESHOLDS = {
        "ember": 0,
        "flame": 2500,
        "blaze": 7500,
        "holy":  20000,
    }

    # Referral milestone bonuses
    REFERRAL_MILESTONE_5_HP = 150       # +150 HP active at 5 referrals
    REFERRAL_MILESTONE_10_HP = 400      # +400 HP active at 10 referrals

    # Flash redemption
    FLASH_DISCOUNT_PCT = 0.50           # 50% HP discount
    FLASH_MAX_QTY = 5                   # First 5 users only

    # HP Bundle (event hosts)
    HP_BUNDLE_PRICE_PER_HP = 5.0        # ₦5 per HP

    # Expiry
    HP_EXPIRY_INACTIVITY_DAYS = 90
    HP_EXPIRY_BREAKAGE_RATE = 0.25      # 25% breakage on inactive HP
    TIER_GRACE_PERIOD_DAYS = 7

    # Marketplace
    LOW_CODE_INVENTORY_THRESHOLD = 5
    ABANDONED_CART_MINUTES = 60

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
