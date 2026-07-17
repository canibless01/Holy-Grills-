"""
Celery application instance and scheduled task definitions.

Production start commands (in Procfile):
  worker: celery -A app.tasks.celery_app.celery_app worker --loglevel=info --concurrency=2
  beat:   celery -A app.tasks.celery_app.celery_app beat --loglevel=info

Scheduled Jobs (all times WAT = UTC+1):
  1. reset_monthly_leaderboard   — 1st of each month at 00:01 WAT
  2. recalculate_120day_hp       — Daily at 02:00 WAT
  3. tier_grace_period_check     — Daily at 03:00 WAT
  4. hp_decay_check              — Daily at 05:00 WAT (120-day onset, 10 %/month decay)
  5. birthday_hp_awards          — Daily at 08:00 WAT
  6. win_back_notifications      — Daily at 10:00 WAT
  7. scan_abandoned_carts        — Every 30 minutes
  8. monthly_birthday_report     — 1st of each month at 07:00 WAT
  9. process_scheduled_orders    — Every 5 minutes
 10. check_order_locks           — Daily at 09:00 WAT
 11. reset_monthly_hp_tracker    — 1st of each month at 00:05 WAT
"""

from celery import Celery
from celery.schedules import crontab
import os

celery_app = Celery(
    "holy_grills",
    broker=os.environ.get("CELERY_BROKER_URL", "redis://localhost:6379/0"),
    backend=os.environ.get("CELERY_RESULT_BACKEND", "redis://localhost:6379/0"),
    include=["app.tasks.scheduled"],
)

celery_app.conf.beat_schedule = {
    "reset-monthly-leaderboard": {
        "task": "app.tasks.scheduled.reset_monthly_leaderboard",
        "schedule": crontab(hour=0, minute=1, day_of_month=1),
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
    "send-scheduled-notifications": {
        "task": "app.tasks.scheduled.send_scheduled_notifications",
        "schedule": crontab(minute="*/15"),
    },
}

# All times in West Africa Time (UTC+1)
celery_app.conf.timezone = "Africa/Lagos"

# Prevent tasks from running simultaneously if the previous run is still active
celery_app.conf.task_acks_late = True
celery_app.conf.worker_prefetch_multiplier = 1

# Result expiry — keep task results for 1 hour
celery_app.conf.result_expires = 3600
