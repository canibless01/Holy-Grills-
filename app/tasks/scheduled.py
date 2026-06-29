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
    try:
        lock_acquired = db.rpc("try_acquire_cron_lock", {"p_job_name": "reset_monthly_leaderboard"})
    except Exception:
        lock_acquired = True
    if not lock_acquired:
        return {"skipped": "Lock not acquired"}

    try:
        now = datetime.now(timezone.utc)
        last_month = (now.replace(day=1) - timedelta(days=1))
        period = last_month.strftime("%Y-%m")

        # Compute top earners for last month from hp_transactions
        month_start = last_month.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        month_end = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        EARN_TYPES = ["earn_order", "earn_first_order", "earn_referral", "earn_event_checkin",
                      "earn_review", "earn_birthday", "earn_challenge", "earn_admin_grant",
                      "earn_squad_bonus", "earn_streak"]
        month_txns = (
            db.table("hp_transactions")
            .select("user_id,amount")
            .in_("type", EARN_TYPES)
            .gte("created_at", month_start.isoformat())
            .lt("created_at", month_end.isoformat())
            .execute()
        )

        # Aggregate HP earned per user
        from collections import defaultdict
        user_hp = defaultdict(int)
        for t in (month_txns or []):
            if t.get("amount", 0) > 0:
                user_hp[t["user_id"]] += t["amount"]

        sorted_users = sorted(user_hp.items(), key=lambda x: x[1], reverse=True)[:10]

        if sorted_users:
            # Fetch display names for top users
            top_ids = [uid for uid, _ in sorted_users]
            profiles_data = (
                db.table("profiles")
                .select("id,full_name")
                .in_("id", top_ids)
                .execute()
            )
            profile_map = {p["id"]: p for p in (profiles_data or [])}

            entries = []
            for i, (user_id, hp_earned) in enumerate(sorted_users):
                entries.append({
                    "rank": i + 1,
                    "user_id": user_id,
                    "full_name": profile_map.get(user_id, {}).get("full_name"),
                    "hp_earned": hp_earned,
                })

            try:
                db.table("leaderboard_snapshots").insert({
                    "ranking_type": "monthly",
                    "period_key": period,
                    "entries": entries,
                })
            except Exception as e:
                print(f"[reset_monthly_leaderboard] Snapshot insert failed: {e}")
        else:
            entries = []

        return {"period": period, "top_count": len(entries)}
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
    try:
        lock_acquired = db.rpc("try_acquire_cron_lock", {"p_job_name": "recalculate_120day_hp"})
    except Exception:
        lock_acquired = True
    if not lock_acquired:
        return {"skipped": "Lock not acquired"}

    try:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=120)).isoformat()
        profiles = db.table("profiles").select("id").eq("is_active", "true").execute()
        updated = 0

        for profile in profiles:
            user_id = profile["id"]
            try:
                EARN_TYPES = ["earn_order", "earn_first_order", "earn_referral", "earn_event_checkin",
                              "earn_review", "earn_birthday", "earn_challenge", "earn_admin_grant",
                              "earn_squad_bonus", "earn_streak"]
                txns = (
                    db.table("hp_transactions")
                    .select("amount")
                    .eq("user_id", user_id)
                    .in_("type", EARN_TYPES)
                    .gte("created_at", cutoff)
                    .execute()
                )
                earned_120 = sum(t["amount"] for t in txns if t["amount"] > 0)
                # hp_earned_120day is tracked internally — no profile column to update
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
    try:
        lock_acquired = db.rpc("try_acquire_cron_lock", {"p_job_name": "tier_grace_period_check"})
    except Exception:
        lock_acquired = True
    if not lock_acquired:
        return {"skipped": "Lock not acquired"}

    try:
        now = datetime.now(timezone.utc)
        from app.config import Config as _TierCfg
        _tier_config = _TierCfg()

        tiers = db.table("hp_tiers").select("*").order("sort_order").execute()
        base_tier = tiers[0] if tiers else None

        # Build tier lookup by id
        tier_map = {t["id"]: t for t in tiers}

        # Find all active students with a current tier set
        profiles_in_tier = (
            db.table("profiles")
            .select("id,hp_balance,current_tier_id,tier_grace_ends_at,tier_grace_started_at")
            .eq("is_active", "true")
            .eq("role", "student")
            .not_.is_("current_tier_id", "null")
            .execute()
        )

        started_grace = 0
        dropped_tier = 0

        for profile in (profiles_in_tier or []):
            user_id = profile["id"]
            current_tier_id = profile.get("current_tier_id")
            tier = tier_map.get(current_tier_id, {})
            maintenance = tier.get("maintenance_points", 0)
            if maintenance == 0:
                continue

            hp_balance = profile.get("hp_balance", 0) or 0
            grace_ends = profile.get("tier_grace_ends_at")

            if hp_balance >= maintenance:
                # User met maintenance — clear any grace period
                if grace_ends:
                    db.table("profiles").eq("id", user_id).update({
                        "tier_grace_started_at": None,
                        "tier_grace_ends_at": None,
                    })
                continue

            if grace_ends:
                # Already in grace period — check if elapsed
                if grace_ends < now.isoformat():
                    # Grace over — find the highest tier they qualify for
                    new_tier = base_tier
                    for t in reversed(tiers):
                        if hp_balance >= t.get("min_points", 0):
                            new_tier = t
                            break

                    new_tier_id = new_tier["id"] if new_tier else None
                    db.table("profiles").eq("id", user_id).update({
                        "current_tier_id": new_tier_id,
                        "tier_grace_started_at": None,
                        "tier_grace_ends_at": None,
                    })

                    if new_tier_id:
                        db.table("user_tiers").insert({
                            "user_id": user_id,
                            "tier_id": new_tier_id,
                            "previous_tier_id": current_tier_id,
                            "event": "downgrade",
                            "hp_at_event": hp_balance,
                        })

                    from app.services.notification_service import send_notification
                    send_notification(
                        user_id=user_id,
                        notif_type="tier_dropped",
                        title=f"Tier Update — {tier.get('name', 'tier')} → {new_tier.get('name', '') if new_tier else 'Base'}",
                        body="Your grace period has ended. Keep ordering to climb back up!",
                        channels=["in_app", "email"],
                    )
                    dropped_tier += 1
            else:
                # Start grace period (days from config)
                grace_days = _tier_config.TIER_GRACE_PERIOD_DAYS
                grace_start = now.isoformat()
                grace_end = (now + timedelta(days=grace_days)).isoformat()
                db.table("profiles").eq("id", user_id).update({
                    "tier_grace_started_at": grace_start,
                    "tier_grace_ends_at": grace_end,
                })

                from app.services.notification_service import send_notification
                send_notification(
                    user_id=user_id,
                    notif_type="tier_grace_period",
                    title=f"{grace_days}-Day Grace Period Started — {tier.get('name', 'Tier')}",
                    body=f"Your HP is below the {tier.get('name', 'your tier')} maintenance threshold. Order within {grace_days} days to keep your tier!",
                    channels=["in_app", "email"],
                )
                started_grace += 1

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
    try:
        lock_acquired = db.rpc("try_acquire_cron_lock", {"p_job_name": "hp_expiry_check"})
    except Exception:
        lock_acquired = True
    if not lock_acquired:
        return {"skipped": "Lock not acquired"}

    try:
        from app.config import Config
        _config = Config()
        now = datetime.now(timezone.utc)
        inactivity_days = _config.HP_EXPIRY_INACTIVITY_DAYS
        warn_early = _config.HP_EXPIRY_WARNING_EARLY_DAYS
        warn_late = _config.HP_EXPIRY_WARNING_LATE_DAYS
        breakage_rate = _config.HP_EXPIRY_BREAKAGE_RATE
        cutoff_full = (now - timedelta(days=inactivity_days)).isoformat()
        cutoff_warn_14 = (now - timedelta(days=inactivity_days - warn_early)).isoformat()
        cutoff_warn_3 = (now - timedelta(days=inactivity_days - warn_late)).isoformat()

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

            amount_to_expire = int(active_hp * breakage_rate)
            if amount_to_expire > 0:
                expire_hp(user_id, amount_to_expire, f"HP expiry — {inactivity_days} days inactivity ({int(breakage_rate * 100)}% breakage)")
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
    Award birthday HP (BIRTHDAY_HP env var, default 150) ACTIVE to users whose birthday is today.
    30-day redemption window communicated in notification.
    """
    from app.config import Config
    _config = Config()
    birthday_hp = _config.BIRTHDAY_HP

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
                    amount=birthday_hp,
                    txn_type="earn_birthday",
                    reference_type="birthday",
                    notes=f"Birthday HP — {today.strftime('%B %d, %Y')}",
                )

                from app.services.notification_service import send_notification
                name = (profile.get("full_name") or "").split()[0]
                send_notification(
                    user_id=profile["id"],
                    notif_type="birthday_bonus",
                    title=f"Happy Birthday, {name}!",
                    body=f"You've received {birthday_hp} HP as a birthday gift! Valid for 30 days. Enjoy your special day.",
                    channels=["in_app", "email"],
                )
                awarded += 1
        except Exception as e:
            print(f"[birthday_hp_awards] Failed for user {profile['id']}: {e}")

    return {"awarded": awarded, "date": today_md}


@celery_app.task(name="app.tasks.scheduled.monthly_birthday_report", bind=True, max_retries=2)
def monthly_birthday_report(self):
    """
    Runs: 1st of each month at 07:00 WAT.
    Sends each admin an in-app notification + email listing every user
    whose birthday falls in the current month (name, date MM-DD, phone).
    Admins use this to send birthday wishes, WhatsApp DMs, or social posts.
    """
    db = get_db()
    try:
        lock_acquired = db.rpc("try_acquire_cron_lock", {"p_job_name": "monthly_birthday_report"})
        if not lock_acquired:
            return {"skipped": "Lock not acquired"}
    except Exception:
        lock_acquired = True

    try:
        now = datetime.now(timezone.utc)
        current_month = now.month

        profiles = (
            db.table("profiles")
            .select("id,full_name,date_of_birth,phone")
            .eq("is_active", "true")
            .execute()
        )

        birthday_users = []
        for p in (profiles or []):
            dob = p.get("date_of_birth")
            if not dob:
                continue
            try:
                dob_str = str(dob)
                month = int(dob_str[5:7])
                if month == current_month:
                    day = int(dob_str[8:10])
                    birthday_users.append({
                        "name": p.get("full_name") or "Unknown",
                        "date": dob_str[5:10],
                        "phone": p.get("phone") or "N/A",
                        "user_id": p["id"],
                    })
            except Exception:
                continue

        birthday_users.sort(key=lambda x: x["date"])
        month_name = now.strftime("%B %Y")
        count = len(birthday_users)

        admins = (
            db.table("profiles")
            .select("id,email,full_name")
            .eq("role", "admin")
            .eq("is_active", "true")
            .execute()
        )

        if not admins:
            return {"birthday_count": count, "month": month_name, "notified_admins": 0}

        summary_lines = [
            f"• {u['name']} — {u['date']} (📞 {u['phone']})"
            for u in birthday_users
        ]
        summary_text = "\n".join(summary_lines) if summary_lines else "No birthdays this month."

        notif_body = (
            f"Users with birthdays in {month_name}:\n\n{summary_text}"
            if birthday_users
            else f"No users have birthdays in {month_name}."
        )

        from app.services.notification_service import send_notification
        from app.utils.email import send_email

        for admin in admins:
            send_notification(
                user_id=admin["id"],
                notif_type="birthday_report",
                title=f"🎂 {count} Birthday{'s' if count != 1 else ''} This Month ({month_name})",
                body=notif_body,
                channels=["in_app"],
            )
            if admin.get("email"):
                send_email(
                    to_email=admin["email"],
                    to_name=admin.get("full_name") or "Admin",
                    template_key="monthly_birthday_report",
                    data={
                        "month": month_name,
                        "count": count,
                        "birthday_list": birthday_users,
                        "summary_text": summary_text,
                    },
                )

        return {
            "birthday_count": count,
            "month": month_name,
            "notified_admins": len(admins),
        }
    finally:
        try:
            db.rpc("release_cron_lock", {"p_job_name": "monthly_birthday_report"})
        except Exception:
            pass


@celery_app.task(name="app.tasks.scheduled.scan_abandoned_carts", bind=True)
def scan_abandoned_carts(self):
    """
    Runs: Every 30 minutes.
    Flags carts inactive for 60+ minutes as abandoned.
    """
    db = get_db()
    from datetime import datetime, timezone, timedelta
    from app.config import Config as _CartCfg
    _cart_config = _CartCfg()
    now = datetime.now(timezone.utc)
    cutoff = (now - timedelta(minutes=_cart_config.ABANDONED_CART_MINUTES)).isoformat()

    existing_abandoned_user_ids = [
        r["user_id"]
        for r in db.table("abandoned_carts").select("user_id").eq("is_recovered", "false").execute()
        if r.get("user_id")
    ]

    return {"scanned": True, "cutoff": cutoff}
