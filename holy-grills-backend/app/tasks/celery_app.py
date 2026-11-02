from celery import Celery
from celery.schedules import crontab
import os

_FALLBACK_REDIS_URL = "redis://localhost:6379/0"


def _redis_url() -> str:
    """The broker/result URL, never empty.

    `os.environ.get(key, default)` returns "" when the key exists but is empty, and an
    empty broker URL makes kombu fall back to amqp://guest@localhost:5672 — which is
    why a blank Railway reference surfaces as "Cannot connect to amqp://guest:**@
    127.0.0.1:5672" instead of a Redis error. Chain to REDIS_URL, exactly as
    app/config.py does, so a blank CELERY_BROKER_URL still reaches Redis.
    """
    for name in ("CELERY_BROKER_URL", "REDIS_URL"):
        value = (os.environ.get(name) or "").strip()
        if value:
            return value
    return _FALLBACK_REDIS_URL


celery_app = Celery(
    "holy_grills",
    broker=_redis_url(),
    backend=(os.environ.get("CELERY_RESULT_BACKEND") or "").strip() or _redis_url(),
    include=["app.tasks.scheduled"],
)

# Celery 6.0 stops honouring broker_connection_retry for startup retries and warns
# (CPendingDeprecationWarning) unless this is set explicitly. Retrying on startup is
# what we want: the worker on Railway often starts before Redis is reachable, and a
# refused first connection must not kill the process.
celery_app.conf.broker_connection_retry_on_startup = True

class ContextTask(celery_app.Task):
    def __call__(self, *args, **kwargs):
        from app import create_app
        app = create_app()
        with app.app_context():
            return self.run(*args, **kwargs)

celery_app.Task = ContextTask

celery_app.conf.beat_schedule = {
    "reset-monthly-leaderboard": {
        "task": "app.tasks.scheduled.reset_monthly_leaderboard",
        "schedule": crontab(hour=0, minute=1, day_of_month=1),
    },
    "reset-weekly-leaderboard": {
        "task": "app.tasks.scheduled.reset_weekly_leaderboard",
        "schedule": crontab(hour=0, minute=1, day_of_week="monday"),
    },
    "recalculate-120day-hp": {
        "task": "app.tasks.scheduled.recalculate_120day_hp",
        "schedule": crontab(hour=2, minute=0),
    },
    "tier-grace-period-check": {
        "task": "app.tasks.scheduled.tier_grace_period_check",
        "schedule": crontab(hour=3, minute=0),
    },
    "birthday-hp-awards": {
        "task": "app.tasks.scheduled.birthday_hp_awards",
        "schedule": crontab(hour=8, minute=0),
    },
    "grant-monthly-tier-perks": {
        "task": "app.tasks.scheduled.grant_monthly_tier_perks",
        "schedule": crontab(hour=0, minute=5, day_of_month=1),
    },
    "sweep-pending-squad-hp": {
        "task": "app.tasks.scheduled.sweep_pending_squad_hp",
        "schedule": crontab(hour=5, minute=30),
    },
    "send-newsletter-campaigns": {
        "task": "app.tasks.scheduled.send_newsletter_campaigns",
        "schedule": crontab(minute="*/5"),
    },
    "abandoned-cart-scan": {
        "task": "app.tasks.scheduled.scan_abandoned_carts",
        "schedule": crontab(minute="*/30"),
    },
    "monthly-birthday-report": {
        "task": "app.tasks.scheduled.monthly_birthday_report",
        "schedule": crontab(hour=7, minute=0, day_of_month=1),
    },
    "process-scheduled-orders": {
        "task": "app.tasks.scheduled.process_scheduled_orders",
        "schedule": crontab(minute="*/5"),
    },
    # ── New Feature Tasks ─────────────────────────────────────────────────────
    "win-back-notifications": {
        "task": "app.tasks.scheduled.win_back_notifications",
        "schedule": crontab(hour=10, minute=0),
    },
    "hp-decay-check": {
        "task": "app.tasks.scheduled.hp_decay_check",
        "schedule": crontab(hour=5, minute=0),
    },
    "check-order-locks": {
        "task": "app.tasks.scheduled.check_order_locks",
        "schedule": crontab(hour=9, minute=0),
    },
    "reset-monthly-hp-tracker": {
        "task": "app.tasks.scheduled.reset_monthly_hp_tracker",
        "schedule": crontab(hour=0, minute=5, day_of_month=1),
    },
    # Phase 2 tasks
    "membership-anniversary-awards": {
        "task": "app.tasks.scheduled.membership_anniversary_awards",
        "schedule": crontab(hour=6, minute=0),
    },
    "send-scheduled-blasts": {
        "task": "app.tasks.scheduled.send_scheduled_blasts",
        "schedule": crontab(minute="*/15"),
    },
    # "send-scheduled-notifications" removed from beat_schedule (B-2, tasks/celery_app):
    # it duplicated send-scheduled-blasts on the same */15 cadence, hitting the same
    # notification_blasts rows and double-sending. The task function itself stays in
    # app/tasks/scheduled.py, unscheduled, for a manual one-off trigger if ever needed.
    "check-post-delivery-nudges": {
        "task": "app.tasks.scheduled.check_post_delivery_nudges",
        "schedule": crontab(minute="*/30"),
    },
}

# All times in West Africa Time (UTC+1)
celery_app.conf.timezone = "Africa/Lagos"

# Reserve one task per worker process and acknowledge after execution.
# These settings do not serialize runs; individual job locks provide that guard.
celery_app.conf.task_acks_late = True
celery_app.conf.worker_prefetch_multiplier = 1

# Result expiry — keep task results for 1 hour
celery_app.conf.result_expires = 3600
