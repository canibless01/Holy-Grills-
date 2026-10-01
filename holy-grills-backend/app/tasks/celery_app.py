from celery import Celery
from celery.schedules import crontab
import os

celery_app = Celery(
    "holy_grills",
    broker=os.environ.get("CELERY_BROKER_URL", "redis://localhost:6379/0"),
    backend=os.environ.get("CELERY_RESULT_BACKEND", "redis://localhost:6379/0"),
    include=["app.tasks.scheduled"],
)

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

# Prevent tasks from running simultaneously if the previous run is still active
celery_app.conf.task_acks_late = True
celery_app.conf.worker_prefetch_multiplier = 1

# Result expiry — keep task results for 1 hour
celery_app.conf.result_expires = 3600
