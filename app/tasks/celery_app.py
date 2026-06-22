"""
Celery application instance and scheduled task definitions.
Run with: celery -A app.tasks.celery_app worker --beat -l info

Scheduled Jobs:
  1. reset_monthly_leaderboard   — 1st of each month at 00:01
  2. recalculate_120day_hp       — Daily at 02:00
  3. tier_grace_period_check     — Daily at 03:00
  4. pending_unlock_batch        — Runs after each delivery window closes (event-driven)
  5. hp_expiry_check             — Weekly Sunday at 04:00
  6. birthday_hp_awards          — Daily at 08:00
  7. abandoned_cart_scan         — Every 30 minutes
"""

from celery import Celery
from celery.schedules import crontab
import os

celery_app = Celery(
    "holy_grills",
    broker=os.environ.get("CELERY_BROKER_URL", "redis://localhost:6379/0"),
    backend=os.environ.get("CELERY_RESULT_BACKEND", "redis://localhost:6379/0"),
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
    "hp-expiry-check": {
        "task": "app.tasks.scheduled.hp_expiry_check",
        "schedule": crontab(hour=4, minute=0, day_of_week=0),  # Sunday
    },
    "birthday-hp-awards": {
        "task": "app.tasks.scheduled.birthday_hp_awards",
        "schedule": crontab(hour=8, minute=0),
    },
    "abandoned-cart-scan": {
        "task": "app.tasks.scheduled.scan_abandoned_carts",
        "schedule": crontab(minute="*/30"),
    },
}

celery_app.conf.timezone = "Africa/Lagos"
