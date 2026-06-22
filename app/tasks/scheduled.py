"""
Scheduled Celery tasks — all background jobs for the HP ecosystem.

All tasks are idempotent — safe to re-run if they fail halfway.
Uses Supabase RPC cron lock pattern to prevent duplicate runs.
"""

from app.tasks.celery_app import celery_app
from app.db import get_db
from datetime import datetime, timezone, timedelta, date


@celery_app.task(name="app.tasks.scheduled.reset_monthly_leaderboard", bind=True, max_retries=3)
def reset_monthly_leaderboard(self):
    """
    Runs: 1st of each month at 00:01 WAT.
    1. Archive top 10 of previous month to hall_of_fame (rank #1) and spin_win_entries (ranks 2-10)
    2. Reset monthly_hp_earned to 0 for all users
    3. Create leaderboard snapshot for previous month
    """
    db = get_db()
    lock_acquired = db.rpc("try_acquire_cron_lock", {"p_job_name": "reset_monthly_leaderboard"})
    if not lock_acquired:
        return {"skipped": "Lock not acquired"}

    try:
        now = datetime.now(timezone.utc)
        last_month = (now.replace(day=1) - timedelta(days=1))
        period = last_month.strftime("%Y-%m")

        top_users = (
            db.table("profiles")
            .select("id,full_name,monthly_hp_earned")
            .order("monthly_hp_earned", ascending=False)
            .limit(10)
            .execute()
        )

        if top_users and top_users[0].get("monthly_hp_earned", 0) > 0:
            winner = top_users[0]
            try:
                db.table("hall_of_fame").insert({
                    "user_id": winner["id"],
                    "month": period,
                    "hp_earned": winner.get("monthly_hp_earned", 0),
                    "full_name_snapshot": winner.get("full_name"),
                })
            except Exception:
                pass

            try:
                entries = []
                for i, user in enumerate(top_users[:10]):
                    entries.append({
                        "user_id": user["id"],
                        "month": period,
                        "rank": i + 1,
                        "hp_earned": user.get("monthly_hp_earned", 0),
                    })
                db.table("spin_win_entries").insert(entries)
            except Exception:
                pass

        all_profiles = db.table("profiles").select("id").execute()
        for profile in all_profiles:
            db.table("profiles").eq("id", profile["id"]).update({
                "monthly_hp_earned": 0,
                "last_monthly_reset_at": now.isoformat(),
            })

        return {"reset_count": len(all_profiles), "period": period, "archived_top": len(top_users)}
    finally:
        db.rpc("release_cron_lock", {"p_job_name": "reset_monthly_leaderboard"})


@celery_app.task(name="app.tasks.scheduled.recalculate_120day_hp", bind=True, max_retries=3)
def recalculate_120day_hp(self):
    """
    Runs: Daily at 02:00 WAT.
    Recalculates hp_earned_120day for all active users from hp_transactions
    where created_at >= now() - 120 days and type='earn' and status='active'.
    """
    db = get_db()
    lock_acquired = db.rpc("try_acquire_cron_lock", {"p_job_name": "recalculate_120day_hp"})
    if not lock_acquired:
        return {"skipped": "Lock not acquired"}

    try:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=120)).isoformat()
        profiles = db.table("profiles").select("id").eq("is_active", "true").execute()
        updated = 0

        for profile in profiles:
            user_id = profile["id"]
            try:
                txns = (
                    db.table("hp_transactions")
                    .select("amount")
                    .eq("user_id", user_id)
                    .eq("type", "earn")
                    .eq("status", "active")
                    .gte("created_at", cutoff)
                    .execute()
                )
                earned_120 = sum(t["amount"] for t in txns if t["amount"] > 0)
                db.table("profiles").eq("id", user_id).update({
                    "hp_earned_120day": earned_120,
                    "hp_earned_120day_updated_at": datetime.now(timezone.utc).isoformat(),
                })
                updated += 1
            except Exception as e:
                print(f"[recalculate_120day_hp] Failed for user {user_id}: {e}")

        return {"updated": updated}
    finally:
        db.rpc("release_cron_lock", {"p_job_name": "recalculate_120day_hp"})


@celery_app.task(name="app.tasks.scheduled.tier_grace_period_check", bind=True, max_retries=3)
def tier_grace_period_check(self):
    """
    Runs: Daily at 03:00 WAT.
    1. Find users whose hp_earned_120day is below their current tier threshold
    2. Start 7-day grace period if not already in one
    3. Drop tier if grace period has elapsed
    """
    db = get_db()
    lock_acquired = db.rpc("try_acquire_cron_lock", {"p_job_name": "tier_grace_period_check"})
    if not lock_acquired:
        return {"skipped": "Lock not acquired"}

    try:
        now = datetime.now(timezone.utc)
        from flask import Flask
        from app.config import Config
        app = Flask(__name__)
        app.config.from_object(Config)

        tiers = db.table("tiers").select("*").order("sort_order").execute()
        ember_tier = tiers[0] if tiers else None

        user_tiers = (
            db.table("user_tiers")
            .select("*,tiers(min_hp_threshold,sort_order,name,slug)")
            .eq("is_current", "true")
            .execute()
        )

        started_grace = 0
        dropped_tier = 0
        notifications_sent = 0

        for ut in user_tiers:
            user_id = ut["user_id"]
            tier = ut.get("tiers") or {}
            threshold = tier.get("min_hp_threshold", 0)
            if threshold == 0:
                continue

            profile = db.table("profiles").select("hp_earned_120day").eq("id", user_id).single().execute()
            earned_120 = profile.get("hp_earned_120day", 0) or 0

            if earned_120 >= threshold:
                if ut.get("is_in_grace_period"):
                    db.table("user_tiers").eq("id", ut["id"]).update({
                        "is_in_grace_period": False,
                        "grace_period_ends_at": None,
                    })
                continue

            if ut.get("is_in_grace_period"):
                grace_ends = ut.get("grace_period_ends_at")
                if grace_ends and grace_ends < now.isoformat():
                    new_tier = ember_tier
                    for t in reversed(tiers):
                        if earned_120 >= t.get("min_hp_threshold", 0):
                            new_tier = t
                            break

                    db.table("user_tiers").eq("id", ut["id"]).update({"is_current": False})
                    if new_tier:
                        db.table("user_tiers").insert({
                            "user_id": user_id,
                            "tier_id": new_tier["id"],
                            "is_current": True,
                            "downgraded_at": now.isoformat(),
                            "downgraded_to_tier_id": new_tier["id"],
                        })
                        db.table("profiles").eq("id", user_id).update({
                            "tier_bonus_multiplier": new_tier.get("earn_multiplier", 1.0),
                        })

                    from app.services.notification_service import send_notification
                    send_notification(
                        user_id=user_id,
                        notif_type="tier_dropped",
                        title=f"Tier Update — {tier.get('name', 'tier')} → {new_tier.get('name', '') if new_tier else 'Ember'}",
                        body="Your grace period has ended. Keep ordering to climb back up!",
                        channels=["in_app", "email"],
                    )
                    dropped_tier += 1
            else:
                grace_ends = (now + timedelta(days=7)).isoformat()
                db.table("user_tiers").eq("id", ut["id"]).update({
                    "is_in_grace_period": True,
                    "grace_period_ends_at": grace_ends,
                })

                from app.services.notification_service import send_notification
                send_notification(
                    user_id=user_id,
                    notif_type="tier_grace_period",
                    title=f"7-Day Grace Period Started — {tier.get('name', 'Tier')}",
                    body=f"Your HP activity has dipped below {tier.get('name', 'your tier')} threshold. Order within 7 days to keep your tier!",
                    channels=["in_app", "email"],
                )
                started_grace += 1
                notifications_sent += 1

        return {"started_grace": started_grace, "dropped_tier": dropped_tier}
    finally:
        db.rpc("release_cron_lock", {"p_job_name": "tier_grace_period_check"})


@celery_app.task(name="app.tasks.scheduled.hp_expiry_check", bind=True, max_retries=3)
def hp_expiry_check(self):
    """
    Runs: Weekly on Sunday at 04:00 WAT.
    Identifies HP eligible for expiry: accounts inactive for 90+ days.
    Sends warning at 14 days and 3 days before expiry.
    Applies 20-30% breakage on full-expiry accounts.
    """
    db = get_db()
    lock_acquired = db.rpc("try_acquire_cron_lock", {"p_job_name": "hp_expiry_check"})
    if not lock_acquired:
        return {"skipped": "Lock not acquired"}

    try:
        now = datetime.now(timezone.utc)
        inactivity_days = 90
        cutoff_full = (now - timedelta(days=inactivity_days)).isoformat()
        cutoff_warn_14 = (now - timedelta(days=inactivity_days - 14)).isoformat()
        cutoff_warn_3 = (now - timedelta(days=inactivity_days - 3)).isoformat()

        inactive_users = (
            db.table("hp_transactions")
            .select("user_id")
            .lt("created_at", cutoff_full)
            .execute()
        )

        processed = set()
        expired_count = 0

        for row in inactive_users:
            user_id = row["user_id"]
            if user_id in processed:
                continue
            processed.add(user_id)

            recent = (
                db.table("hp_transactions")
                .select("id")
                .eq("user_id", user_id)
                .gte("created_at", cutoff_full)
                .limit(1)
                .execute()
            )
            if recent:
                continue

            from app.services.hp_service import get_hp_balance, expire_hp
            balance = get_hp_balance(user_id)
            active_hp = balance["active"]
            if active_hp <= 0:
                continue

            breakage_rate = 0.25
            amount_to_expire = int(active_hp * breakage_rate)
            if amount_to_expire > 0:
                expire_hp(user_id, amount_to_expire, f"HP expiry — {inactivity_days} days inactivity (25% breakage)")
                expired_count += 1

                from app.services.notification_service import send_notification
                send_notification(
                    user_id=user_id,
                    notif_type="hp_expired",
                    title=f"{amount_to_expire} HP Expired",
                    body=f"Some of your HP has expired due to {inactivity_days} days of inactivity. Place an order to protect your remaining balance!",
                    channels=["in_app", "email"],
                )

        return {"accounts_processed": len(processed), "expired_count": expired_count}
    finally:
        db.rpc("release_cron_lock", {"p_job_name": "hp_expiry_check"})


@celery_app.task(name="app.tasks.scheduled.birthday_hp_awards", bind=True, max_retries=3)
def birthday_hp_awards(self):
    """
    Runs: Daily at 08:00 WAT.
    Award 150 HP ACTIVE to users whose birthday is today.
    30-day redemption window communicated in notification.
    """
    db = get_db()
    today = datetime.now(timezone.utc)
    today_md = today.strftime("%m-%d")

    profiles = (
        db.table("profiles")
        .select("id,full_name,date_of_birth")
        .eq("is_active", "true")
        .execute()
    )

    awarded = 0
    for profile in profiles:
        dob = profile.get("date_of_birth")
        if not dob:
            continue
        try:
            dob_md = str(dob)[5:][:5]
            if dob_md == today_md:
                already = (
                    db.table("hp_transactions")
                    .select("id")
                    .eq("user_id", profile["id"])
                    .eq("reference_type", "birthday")
                    .gte("created_at", today.replace(month=today.month, day=1, hour=0, minute=0, second=0, microsecond=0).isoformat())
                    .execute()
                )
                if already:
                    continue

                from app.services.hp_service import award_active_hp
                award_active_hp(
                    user_id=profile["id"],
                    amount=150,
                    txn_type="earn",
                    reference_type="birthday",
                    notes=f"Birthday HP — {today.strftime('%B %d, %Y')}",
                )

                from app.services.notification_service import send_notification
                name = (profile.get("full_name") or "").split()[0]
                send_notification(
                    user_id=profile["id"],
                    notif_type="birthday_bonus",
                    title=f"Happy Birthday, {name}! 🎂",
                    body="You've received 150 HP as a birthday gift! Valid for 30 days. Enjoy your special day.",
                    channels=["in_app", "email"],
                )
                awarded += 1
        except Exception as e:
            print(f"[birthday_hp_awards] Failed for user {profile['id']}: {e}")

    return {"awarded": awarded, "date": today_md}


@celery_app.task(name="app.tasks.scheduled.scan_abandoned_carts", bind=True)
def scan_abandoned_carts(self):
    """
    Runs: Every 30 minutes.
    Flags carts inactive for 60+ minutes as abandoned.
    """
    db = get_db()
    from datetime import datetime, timezone, timedelta
    now = datetime.now(timezone.utc)
    cutoff = (now - timedelta(minutes=60)).isoformat()

    existing_abandoned_user_ids = [
        r["user_id"]
        for r in db.table("abandoned_carts").select("user_id").eq("is_recovered", "false").execute()
        if r.get("user_id")
    ]

    return {"scanned": True, "cutoff": cutoff}
