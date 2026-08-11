"""
Milestone Service — unified engine for badges and challenges.

One `milestones` table drives both:
  - Badges (time_window IS NULL): lifetime, one-time awards.
  - Challenges (time_window IN ('weekly','monthly')): recurring, real-data verified.

trigger_type values and their verification logic:
  LIFETIME BADGES:
    first_order         — delivered orders >= 1
    first_review        — reviews >= 1
    first_referral      — completed referrals >= 1
    first_event         — event check-ins >= 1
    first_squad         — squad orders >= 1
    first_hp_gift_sent  — hp_transfers sent >= 1
    graduation          — graduation_claimed = true
    birthday            — birthday HP transaction exists
    social_follow       — self-declared (one-time, → pending)
    hp_earned_total     — total active HP earned >= trigger_value
    membership_months   — account age in months >= trigger_value

  RECURRING CHALLENGES:
    referral_count      — completed referrals in period >= trigger_value
    order_count         — delivered orders in period >= trigger_value
    review_count        — reviews in period >= trigger_value
    event_checkins      — event check-ins in period >= trigger_value
    squad_orders        — squad orders in period >= trigger_value
    order_streak_weeks  — order_streaks.streak_weeks >= trigger_value (auto-checked)
    login_streak_cycles — consecutive login weeks >= trigger_value (auto-checked)

  ADMIN-COMPUTED:
    department_leader   — admin-only trigger (not self-completable)
    faculty_leader      — admin-only trigger (not self-completable)
"""

from datetime import datetime, timezone, timedelta
from app.db import get_db
from app.utils.logger import get_logger

logger = get_logger(__name__)

# trigger_types that users CANNOT self-complete (admin-triggered or auto-triggered only)
ADMIN_ONLY_TRIGGERS = {"department_leader", "faculty_leader"}

# trigger_types that are self-declared (no server-side verification, one-time only)
SELF_DECLARED_TRIGGERS = {"social_follow"}


def get_user_milestones(user_id: str) -> dict:
    """
    Return all milestones split into earned badges, available challenges,
    and pending (in-progress) challenges.
    """
    db = get_db()
    now = datetime.now(timezone.utc)
    period_weekly  = _period_key("weekly", now.date())
    period_monthly = _period_key("monthly", now.date())

    all_milestones = (
        db.table("milestones")
        .select("*")
        .eq("is_active", "true")
        .not_.in_("trigger_type", list(ADMIN_ONLY_TRIGGERS))
        .execute()
    ) or []

    earned_rows = (
        db.table("user_milestones")
        .select("milestone_id,period_key,completed_at,hp_awarded")
        .eq("user_id", user_id)
        .execute()
    ) or []

    # Build lookup of what the user has completed
    earned_lifetime = {r["milestone_id"] for r in earned_rows if r.get("period_key") is None}
    earned_weekly   = {r["milestone_id"] for r in earned_rows if r.get("period_key") == period_weekly}
    earned_monthly  = {r["milestone_id"] for r in earned_rows if r.get("period_key") == period_monthly}

    badges_earned = []
    challenges_available = []
    challenges_completed = []

    for m in all_milestones:
        mid = m["id"]
        tw  = m.get("time_window")

        if tw is None:
            # Badge
            m["earned"] = mid in earned_lifetime
            if m["earned"]:
                completion = next((r for r in earned_rows if r["milestone_id"] == mid and r.get("period_key") is None), {})
                m["earned_at"] = completion.get("completed_at")
            badges_earned.append(m)
        else:
            # Challenge
            current_set = earned_weekly if tw == "weekly" else earned_monthly
            m["completed_this_period"] = mid in current_set
            if m["completed_this_period"]:
                challenges_completed.append(m)
            else:
                challenges_available.append(m)

    return {
        "badges": badges_earned,
        "challenges_available": challenges_available,
        "challenges_completed": challenges_completed,
    }


def check_and_award_milestone(user_id: str, milestone_id: str) -> dict:
    """
    Main entry point for user-initiated challenge completion attempts.
    Verifies against real data tables, awards HP if criteria met.
    Raises ValueError if not eligible.
    """
    db = get_db()
    now = datetime.now(timezone.utc)

    milestone = (
        db.table("milestones")
        .select("*")
        .eq("id", milestone_id)
        .eq("is_active", "true")
        .single()
        .execute()
    )
    if not milestone:
        raise ValueError("Milestone not found or inactive")

    trigger_type  = milestone.get("trigger_type", "")
    trigger_value = int(milestone.get("trigger_value") or 1)
    time_window   = milestone.get("time_window")  # None | 'weekly' | 'monthly'
    hp_awarded    = int(milestone.get("hp_awarded") or 0)

    # Admin-only triggers cannot be self-completed
    if trigger_type in ADMIN_ONLY_TRIGGERS:
        raise ValueError("This milestone is awarded by admins only")

    # Determine period key for dedup
    period_key = _period_key(time_window, now.date()) if time_window else None

    # Check if already completed (for this period / lifetime)
    already = _is_already_completed(db, user_id, milestone_id, period_key)
    if already:
        return {"message": "Already completed", "already_completed": True}

    # Verify the user actually meets the trigger criteria
    if trigger_type not in SELF_DECLARED_TRIGGERS:
        progress = _compute_trigger_progress(db, user_id, trigger_type, trigger_value, time_window, now)
        if progress < trigger_value:
            raise ValueError(
                f"Not yet eligible: need {trigger_value}, have {progress} for '{trigger_type}'"
            )

    # Award HP (pending for social/self-declared; active for auto-verified challenges)
    hp_destination = "pending" if trigger_type in SELF_DECLARED_TRIGGERS else "active"
    actual_hp = _award_milestone_hp(
        db, user_id, milestone_id, milestone.get("title", ""), hp_awarded, hp_destination
    )

    # Record completion
    try:
        db.table("user_milestones").insert({
            "user_id": user_id,
            "milestone_id": milestone_id,
            "hp_awarded": actual_hp,
            "period_key": period_key,
        })
    except Exception as e:
        logger.warning("check_and_award_milestone: user_milestones insert failed: %s", e)

    # Fire notify_milestone_achieved shared hook
    try:
        notify_milestone_achieved(user_id, milestone_id)
    except Exception as e:
        logger.warning("check_and_award_milestone: notify failed: %s", e)

    return {
        "milestone": milestone,
        "hp_awarded": actual_hp,
        "hp_destination": hp_destination,
        "period_key": period_key,
        "already_completed": False,
    }


def check_milestone_trigger(user_id: str, trigger_type: str, current_value: int) -> None:
    """
    Auto-called by the system when a trigger metric changes (e.g. order delivered,
    referral completed, order streak updated). Checks all active milestones with
    this trigger_type and awards any newly reached thresholds.

    Designed to be called fire-and-forget; all errors are swallowed.
    """
    try:
        db = get_db()
        now = datetime.now(timezone.utc)

        milestones = (
            db.table("milestones")
            .select("id,trigger_value,hp_awarded,time_window,title")
            .eq("trigger_type", trigger_type)
            .eq("is_active", "true")
            .lte("trigger_value", current_value)
            .execute()
        ) or []

        for m in milestones:
            mid = m["id"]
            tw  = m.get("time_window")
            period_key = _period_key(tw, now.date()) if tw else None

            if _is_already_completed(db, user_id, mid, period_key):
                continue

            hp = int(m.get("hp_awarded") or 0)
            actual_hp = _award_milestone_hp(db, user_id, mid, m.get("title", ""), hp, "active")

            try:
                db.table("user_milestones").insert({
                    "user_id": user_id,
                    "milestone_id": mid,
                    "hp_awarded": actual_hp,
                    "period_key": period_key,
                })
            except Exception:
                pass

            try:
                notify_milestone_achieved(user_id, mid)
            except Exception:
                pass

    except Exception as e:
        logger.warning("check_milestone_trigger: error for user %s trigger %s: %s", user_id, trigger_type, e)


def admin_grant_milestone(admin_id: str, user_id: str, milestone_id: str) -> dict:
    """Admin manually awards a milestone (used for department_leader, faculty_leader, etc.)."""
    db = get_db()
    now = datetime.now(timezone.utc)
    milestone = db.table("milestones").select("*").eq("id", milestone_id).single().execute()
    if not milestone:
        raise ValueError("Milestone not found")

    tw = milestone.get("time_window")
    period_key = _period_key(tw, now.date()) if tw else None
    hp = int(milestone.get("hp_awarded") or 0)

    already = _is_already_completed(db, user_id, milestone_id, period_key)
    if already:
        return {"message": "Already completed", "already_completed": True}

    actual_hp = _award_milestone_hp(db, user_id, milestone_id, milestone.get("title", ""), hp, "active")

    try:
        db.table("user_milestones").insert({
            "user_id": user_id,
            "milestone_id": milestone_id,
            "hp_awarded": actual_hp,
            "period_key": period_key,
        })
    except Exception as e:
        logger.warning("admin_grant_milestone: insert failed: %s", e)

    try:
        notify_milestone_achieved(user_id, milestone_id)
    except Exception:
        pass

    return {"milestone": milestone, "hp_awarded": actual_hp, "awarded_by": admin_id}


def notify_milestone_achieved(user_id: str, milestone_id: str) -> None:
    """
    Shared notification hook for all milestone/badge awards.
    Always fires push + in_app together. No email for gamification events.
    """
    try:
        from app.services.notification_service import send_notification
        from app.db import get_db as _get_db
        _db = _get_db()
        m = _db.table("milestones").select("title,hp_awarded,time_window").eq("id", milestone_id).single().execute()
        if not m:
            return
        from app.messages import MSG
        is_badge = m.get("time_window") is None
        hp = int(m.get("hp_awarded") or 0)
        _title = MSG.MILESTONE_BADGE_TITLE if is_badge else MSG.MILESTONE_CHALLENGE_TITLE
        _body = m["title"] + (MSG.MILESTONE_HP_SUFFIX.format(hp=hp) if hp else "")
        send_notification(
            user_id=user_id,
            notif_type="milestone_achieved",
            title=_title,
            body=_body,
            reference_id=milestone_id,
            reference_type="milestone",
            channels=["push", "in_app"],
        )
    except Exception as e:
        logger.warning("notify_milestone_achieved: failed for user %s milestone %s: %s", user_id, milestone_id, e)


# ── Internal helpers ───────────────────────────────────────────────────────────

def _period_key(time_window: str | None, today) -> str | None:
    """Generate the dedup period key for a given time_window."""
    if not time_window:
        return None
    if time_window == "weekly":
        iso = today.isocalendar()
        return f"{iso[0]:04d}-W{iso[1]:02d}"
    if time_window == "monthly":
        return today.strftime("%Y-%m")
    return None


def _is_already_completed(db, user_id: str, milestone_id: str, period_key) -> bool:
    try:
        if period_key is None:
            # Lifetime badge: check for any completion without period_key
            rows = (
                db.table("user_milestones")
                .select("id")
                .eq("user_id", user_id)
                .eq("milestone_id", milestone_id)
                .is_("period_key", "null")
                .execute()
            )
        else:
            rows = (
                db.table("user_milestones")
                .select("id")
                .eq("user_id", user_id)
                .eq("milestone_id", milestone_id)
                .eq("period_key", period_key)
                .execute()
            )
        return bool(rows and len(rows) > 0)
    except Exception:
        return False


def _compute_trigger_progress(
    db, user_id: str, trigger_type: str, trigger_value: int,
    time_window: str | None, now: datetime
) -> int:
    """
    Return the user's current count for a given trigger_type.
    For lifetime triggers: all-time count.
    For recurring: count within current period.
    """
    period_start = _period_start(time_window, now) if time_window else None

    try:
        if trigger_type == "first_order" or trigger_type == "order_count":
            q = db.table("orders").select("id").eq("user_id", user_id).eq("status", "delivered")
            if period_start:
                q = q.gte("delivered_at", period_start)
            rows = q.execute()
            return len(rows or [])

        elif trigger_type == "first_review" or trigger_type == "review_count":
            q = db.table("reviews").select("id").eq("user_id", user_id)
            if period_start:
                q = q.gte("created_at", period_start)
            rows = q.execute()
            return len(rows or [])

        elif trigger_type == "first_referral" or trigger_type == "referral_count":
            q = (
                db.table("referrals")
                .select("id")
                .eq("referrer_id", user_id)
                .gt("hp_awarded", 0)
            )
            if period_start:
                q = q.gte("created_at", period_start)
            rows = q.execute()
            return len(rows or [])

        elif trigger_type == "first_event" or trigger_type == "event_checkins":
            tickets = (
                db.table("event_tickets")
                .select("id")
                .eq("user_id", user_id)
                .execute()
            ) or []
            if not tickets:
                return 0
            ticket_ids = [t["id"] for t in tickets]
            q = db.table("event_checkins").select("id").in_("ticket_id", ticket_ids)
            if period_start:
                q = q.gte("checked_in_at", period_start)
            rows = q.execute()
            return len(rows or [])

        elif trigger_type == "first_squad" or trigger_type == "squad_orders":
            q = (
                db.table("orders")
                .select("id")
                .eq("user_id", user_id)
                .eq("is_squad_order", "true")
                .eq("status", "delivered")
            )
            if period_start:
                q = q.gte("delivered_at", period_start)
            rows = q.execute()
            return len(rows or [])

        elif trigger_type == "first_hp_gift_sent":
            rows = (
                db.table("hp_transactions")
                .select("id")
                .eq("user_id", user_id)
                .eq("reference_type", "hp_transfer")
                .eq("source", "hp_transfer")
                .execute()
            )
            return len(rows or [])

        elif trigger_type == "graduation":
            profile = (
                db.table("profiles")
                .select("graduation_claimed")
                .eq("id", user_id)
                .single()
                .execute()
            )
            return 1 if (profile or {}).get("graduation_claimed") else 0

        elif trigger_type == "hp_earned_total":
            profile = (
                db.table("profiles")
                .select("hp_balance,hp_earned_120day")
                .eq("id", user_id)
                .single()
                .execute()
            )
            # Use hp_earned_120day as proxy for total earned in rolling window
            return int((profile or {}).get("hp_earned_120day") or 0)

        elif trigger_type == "membership_months":
            profile = (
                db.table("profiles")
                .select("created_at")
                .eq("id", user_id)
                .single()
                .execute()
            )
            if not profile or not profile.get("created_at"):
                return 0
            created = datetime.fromisoformat(str(profile["created_at"]).replace("Z", "+00:00"))
            months = (now - created).days // 30
            return months

        elif trigger_type == "order_streak_weeks":
            row = db.table("order_streaks").select("streak_weeks").eq("user_id", user_id).single().execute()
            return int((row or {}).get("streak_weeks") or 0)

        elif trigger_type == "login_streak_cycles":
            row = db.table("login_streaks").select("consecutive_weeks").eq("user_id", user_id).single().execute()
            return int((row or {}).get("consecutive_weeks") or 0)

        else:
            return 0

    except Exception as e:
        logger.warning("_compute_trigger_progress: error for %s / %s: %s", user_id, trigger_type, e)
        return 0


def _period_start(time_window: str | None, now: datetime) -> str | None:
    """ISO start of the current period for range queries."""
    if not time_window:
        return None
    if time_window == "weekly":
        monday = now.date() - __import__("datetime").timedelta(days=now.weekday())
        return f"{monday.isoformat()}T00:00:00+00:00"
    if time_window == "monthly":
        return f"{now.year}-{now.month:02d}-01T00:00:00+00:00"
    return None


def _award_milestone_hp(
    db, user_id: str, milestone_id: str, title: str,
    hp: int, destination: str
) -> int:
    """Award HP for a milestone. destination: 'active' | 'pending'."""
    if hp <= 0:
        return 0

    from app.services.hp_service import award_active_hp, earn_pending_hp

    if destination == "pending":
        from app.services.streak_service import check_monthly_cap, update_monthly_tracker
        cap_check = check_monthly_cap(user_id, hp)
        if not cap_check["allowed"]:
            return 0
        actual_hp = cap_check["capped_amount"]
        if actual_hp <= 0:
            return 0
        try:
            earn_pending_hp(
                user_id=user_id,
                amount=actual_hp,
                source_type="challenge",
                reference_id=milestone_id,
                notes=f"Milestone: {title} — {actual_hp} HP pending",
            )
            update_monthly_tracker(user_id, actual_hp)
        except Exception as e:
            logger.warning("_award_milestone_hp (pending): failed for %s: %s", user_id, e)
            return 0
        return actual_hp
    else:
        try:
            award_active_hp(
                user_id=user_id,
                amount=hp,
                source_type="challenge",
                reference_id=milestone_id,
                reference_type="milestone",
                notes=f"Milestone: {title} — {hp} HP active",
            )
        except Exception as e:
            logger.warning("_award_milestone_hp (active): failed for %s: %s", user_id, e)
            return 0
        return hp
