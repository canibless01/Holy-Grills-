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
    birthday            — (not implemented: no verification branch, not creatable)
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

  Valid values for a new milestone: VALID_TRIGGER_TYPES below (routes/challenges.py rejects the rest).

  ADMIN-COMPUTED:
    department_leader   — admin-only trigger (not self-completable)
    faculty_leader      — admin-only trigger (not self-completable)
"""
from datetime import datetime, timezone, timedelta
from app.db import get_db, get_user_client
from app.utils.logger import get_logger
from app.utils.tz import today_wat, WAT_OFFSET
from app.messages import MSG, resolve_msg

logger = get_logger(__name__)

# trigger_types that users CANNOT self-complete (admin-triggered or auto-triggered only)
ADMIN_ONLY_TRIGGERS = {"department_leader", "faculty_leader"}

# trigger_types that are self-declared (no server-side verification, one-time only)
SELF_DECLARED_TRIGGERS = {"social_follow"}

# System-verified triggers configured via system_settings (one-time system milestones, time_window IS NULL)
SYSTEM_VERIFIED_TRIGGERS = {
    "pwa_install",
    "push_subscribe",
    "pwa_push_bonus",
}

# trigger_types verified against real data by _compute_trigger_progress (one branch each).
AUTO_VERIFIED_TRIGGERS = {
    "first_order", "order_count",
    "first_review", "review_count",
    "first_referral", "referral_count",
    "first_event", "event_checkins",
    "first_squad", "squad_orders",
    "first_hp_gift_sent",
    "graduation",
    "hp_earned_total",
    "membership_months",
    "order_streak_weeks",
    "login_streak_cycles",
}

# Every trigger_type a milestone can be created with. A value outside this set can never be completed
# (_compute_trigger_progress returns 0 for it), so routes/challenges.py rejects it at creation.
VALID_TRIGGER_TYPES = (
    AUTO_VERIFIED_TRIGGERS | ADMIN_ONLY_TRIGGERS | SELF_DECLARED_TRIGGERS | SYSTEM_VERIFIED_TRIGGERS
)


class MilestoneNotFoundError(LookupError, ValueError):
    """Milestone missing or inactive. Routes answer 404 for it.
    Also a ValueError so any caller that still catches only ValueError keeps working (it answers 400, as before)."""

def get_user_milestones(user_id: str) -> dict:
    """
    Return all milestones split into earned badges, locked badges, available
    challenges, and pending (in-progress) challenges.
    """
    db = get_user_client()
    period_weekly  = _milestone_period_key("weekly", today_wat())
    period_monthly = _milestone_period_key("monthly", today_wat())

    from flask import has_app_context, g
    q = db.table("milestones").select("*").eq("is_active", "true").not_.in_("trigger_type", list(ADMIN_ONLY_TRIGGERS))
    campus_id = getattr(g, 'campus_id', None) if has_app_context() else None
    user_role = getattr(g, 'user_role', None) if has_app_context() else None
    if campus_id:
        q = q.or_(f"campus_id.eq.{campus_id},campus_id.is.null")
    elif user_role != "super_admin":
        q = q.is_("campus_id", "null")
    # else: super_admin has no campus, sees every campus (matches RLS: hg_is_campus_admin is true for super_admin)
    all_milestones = q.execute() or []

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
    badges_locked = []
    challenges_available = []
    challenges_completed = []

    for m in all_milestones:
        mid = m["id"]
        tw  = m.get("time_window")

        if tw is None:
            # Badge or system milestone. `earned` stays on every row (that is the
            # flag clients have always read); the list it lands in is what decides
            # which group it is rendered under.
            m["earned"] = mid in earned_lifetime
            m["is_system"] = m.get("trigger_type") in SYSTEM_VERIFIED_TRIGGERS
            if m["earned"]:
                completion = next((r for r in earned_rows if r["milestone_id"] == mid and r.get("period_key") is None), {})
                m["earned_at"] = completion.get("completed_at")
                m["hp_awarded"] = completion.get("hp_awarded", m.get("hp_awarded", 0))
                badges_earned.append(m)
            else:
                badges_locked.append(m)
        else:
            # Challenge
            current_set = earned_weekly if tw == "weekly" else earned_monthly
            m["completed_this_period"] = mid in current_set
            if m["completed_this_period"]:
                challenges_completed.append(m)
            else:
                challenges_available.append(m)

    # `badges` is the whole set with the `earned` flag, kept for clients that
    # still read it. `badges_earned` / `badges_locked` are the two groups the UI
    # should render — listing `badges` under a "Badges Earned" heading shows
    # every badge the campus defines, earned or not.
    all_badges = badges_earned + badges_locked
    return {
        "badges_earned": badges_earned,
        "badges_locked": badges_locked,
        "badges": all_badges,
        "challenges_available": challenges_available,
        "challenges_completed": challenges_completed,
    }


def check_and_award_milestone(user_id: str, milestone_id: str) -> dict:
    """
    Main entry point for user-initiated challenge completion attempts.
    Verifies against real data tables, awards HP if criteria met.
    Raises MilestoneNotFoundError (a LookupError) if the milestone is missing or inactive.
    Raises ValueError if not eligible.
    """
    db = get_user_client()
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
        raise MilestoneNotFoundError(MSG.MILESTONE_NOT_FOUND)

    trigger_type  = milestone.get("trigger_type", "")
    trigger_value = int(milestone.get("trigger_value") or 1)
    time_window   = milestone.get("time_window")  # None | 'weekly' | 'monthly'
    hp_awarded    = int(milestone.get("hp_awarded") or 0)

    # Admin-only triggers cannot be self-completed
    if trigger_type in ADMIN_ONLY_TRIGGERS:
        raise ValueError(MSG.MILESTONE_ADMIN_ONLY)

    # Determine period key for dedup
    period_key = _milestone_period_key(time_window, today_wat()) if time_window else None

    # Check if already completed (for this period / lifetime)
    already = _is_already_completed(db, user_id, milestone_id, period_key)
    if already:
        return {"message": MSG.MILESTONE_ALREADY_COMPLETED, "already_completed": True}

    db = get_db()

    # Resolve reward amount for system-verified triggers from system_settings
    if trigger_type in SYSTEM_VERIFIED_TRIGGERS:
        from app.utils.settings import get_validated_setting, SettingError
        # Fallback keys only: every system milestone row normally carries its own hp_setting_key.
        # Lowercase, to match the keys that exist in system_settings.
        setting_map = {
            "pwa_install": "pwa_install_hp",
            "push_subscribe": "push_subscribe_hp",
            "pwa_push_bonus": "pwa_push_bonus_hp",
        }
        setting_key = milestone.get("hp_setting_key") or setting_map.get(trigger_type)
        try:
            hp_awarded = int(get_validated_setting(db, setting_key, required=True, minimum=1))
        except SettingError as se:
            # Details (setting key, bounds) go to the log only, never to the user.
            logger.error("check_and_award_milestone: configuration error for %s (%s): %s", trigger_type, setting_key, se)
            raise ValueError(resolve_msg(MSG.MILESTONE_CONFIG_ERROR, trigger_type=trigger_type)) from se
    elif trigger_type not in SELF_DECLARED_TRIGGERS:
        # Verify the user actually meets the trigger criteria for standard triggers
        progress = _compute_trigger_progress(db, user_id, trigger_type, trigger_value, time_window, now)
        if progress < trigger_value:
            raise ValueError(
                resolve_msg(MSG.MILESTONE_NOT_ELIGIBLE, needed=trigger_value, have=progress, trigger_type=trigger_type)
            )

    # Campus of the user who is completing it (this row is what campus admins see through RLS)
    campus_id = _get_user_campus_id(db, user_id)

    # Record completion first to defend against concurrent race conditions before awarding HP.
    # The row's own id anchors the HP transaction, so every period gets its own idempotency slot.
    try:
        um_result = db.table("user_milestones").insert({
            "user_id": user_id,
            "milestone_id": milestone_id,
            "hp_awarded": hp_awarded,
            "period_key": period_key,
            "campus_id": campus_id,
        })
        completion_id = _first_id(um_result)
    except Exception as e:
        err_str = str(e)
        if "23505" in err_str or "duplicate" in err_str.lower() or "unique" in err_str.lower():
            return {"message": MSG.MILESTONE_ALREADY_COMPLETED, "already_completed": True, "hp_awarded": 0}
        logger.warning("check_and_award_milestone: user_milestones insert failed: %s", e)
        if _is_already_completed(db, user_id, milestone_id, period_key):
            return {"message": MSG.MILESTONE_ALREADY_COMPLETED, "already_completed": True, "hp_awarded": 0}
        return {"message": MSG.MILESTONE_CHECK_FAILED, "already_completed": False, "hp_awarded": 0}

    # Award HP (pending for social/self-declared; active for auto-verified challenges and system triggers)
    hp_destination = "pending" if trigger_type in SELF_DECLARED_TRIGGERS else "active"
    actual_hp = _award_milestone_hp(
        db, user_id, milestone_id, milestone.get("title", ""), hp_awarded, hp_destination,
        campus_id=campus_id, completion_id=completion_id,
    )

    # Update recorded actual_hp if capped or modified during HP award
    if actual_hp != hp_awarded:
        _record_actual_hp(db, user_id, milestone_id, period_key, actual_hp, "check_and_award_milestone")

    notify_milestone_achieved(user_id, milestone_id, hp_awarded=actual_hp)

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

        # Campus always comes from the TARGET user's own profile. g.campus_id (when it exists at all)
        # belongs to whoever triggered the check: a referrer, an event organiser, or a background job
        # with no request context.
        campus_id = _get_user_campus_id(db, user_id)

        q = db.table("milestones").select("id,trigger_value,hp_awarded,time_window,title").eq("trigger_type", trigger_type).eq("is_active", "true").lte("trigger_value", current_value)
        if campus_id:
            q = q.or_(f"campus_id.eq.{campus_id},campus_id.is.null")
        else:
            q = q.is_("campus_id", "null")
        milestones = q.execute() or []

        for m in milestones:
            mid = m["id"]
            tw  = m.get("time_window")
            period_key = _milestone_period_key(tw, today_wat()) if tw else None

            if _is_already_completed(db, user_id, mid, period_key):
                continue

            hp = int(m.get("hp_awarded") or 0)

            # Insert completion FIRST to defend against race conditions before awarding HP
            try:
                um_result = db.table("user_milestones").insert({
                    "user_id": user_id,
                    "milestone_id": mid,
                    "hp_awarded": hp,
                    "period_key": period_key,
                    "campus_id": campus_id,
                })
                completion_id = _first_id(um_result)
            except Exception as ie:
                err_str = str(ie)
                if "23505" in err_str or "duplicate" in err_str.lower() or "unique" in err_str.lower():
                    continue
                if _is_already_completed(db, user_id, mid, period_key):
                    continue
                # Not recorded and not a duplicate: award nothing rather than pay HP with no completion row.
                logger.warning("check_milestone_trigger: user_milestones insert failed for user %s milestone %s: %s", user_id, mid, ie)
                continue

            actual_hp = _award_milestone_hp(
                db, user_id, mid, m.get("title", ""), hp, "active",
                campus_id=campus_id, completion_id=completion_id,
            )
            if actual_hp != hp:
                _record_actual_hp(db, user_id, mid, period_key, actual_hp, "check_milestone_trigger")
            notify_milestone_achieved(user_id, mid, hp_awarded=actual_hp)

    except Exception as e:
        logger.warning("check_milestone_trigger: error for user %s trigger %s: %s", user_id, trigger_type, e)


def admin_grant_milestone(admin_id: str, user_id: str, milestone_id: str, target_campus_id: str = None) -> dict:
    """
    Admin manually awards a milestone (used for department_leader, faculty_leader, etc.).
    target_campus_id: the campus of the user receiving it (the route has already checked it against the admin's).
    Falls back to the milestone's own campus when the caller does not supply one.
    """
    db = get_user_client()
    # Read through the admin's own session: RLS limits which milestones this admin can see and grant.
    milestone = db.table("milestones").select("*").eq("id", milestone_id).single().execute()
    if not milestone:
        raise MilestoneNotFoundError(MSG.MILESTONE_NOT_FOUND)

    tw = milestone.get("time_window")
    period_key = _milestone_period_key(tw, today_wat()) if tw else None
    hp = int(milestone.get("hp_awarded") or 0)

    # The recipient's rows are not the admin's own; check with the service client, not the admin's session.
    db = get_db()
    already = _is_already_completed(db, user_id, milestone_id, period_key)
    if already:
        return {"message": MSG.MILESTONE_ALREADY_COMPLETED, "already_completed": True}

    effective_campus_id = target_campus_id if target_campus_id is not None else milestone.get("campus_id")

    # Record completion first to defend against concurrent race conditions before awarding HP
    try:
        um_result = db.table("user_milestones").insert({
            "user_id": user_id,
            "milestone_id": milestone_id,
            "hp_awarded": hp,
            "period_key": period_key,
            "campus_id": effective_campus_id,
            "granted_by_admin_id": admin_id,
        })
        completion_id = _first_id(um_result)
    except Exception as e:
        err_str = str(e)
        if "23505" in err_str or "duplicate" in err_str.lower() or "unique" in err_str.lower():
            return {"message": MSG.MILESTONE_ALREADY_COMPLETED, "already_completed": True, "hp_awarded": 0}
        logger.warning("admin_grant_milestone: user_milestones insert failed: %s", e)
        if _is_already_completed(db, user_id, milestone_id, period_key):
            return {"message": MSG.MILESTONE_ALREADY_COMPLETED, "already_completed": True, "hp_awarded": 0}
        # Not recorded and not a duplicate: do not pay HP with no completion row. The admin needs to see the failure.
        raise RuntimeError(MSG.MILESTONE_CHECK_FAILED) from e

    # issued_by_admin_id also stops the live promo multiplier applying to a manual grant.
    actual_hp = _award_milestone_hp(
        db, user_id, milestone_id, milestone.get("title", ""), hp, "active",
        issued_by_admin_id=admin_id, campus_id=effective_campus_id, completion_id=completion_id,
    )
    if actual_hp != hp:
        _record_actual_hp(db, user_id, milestone_id, period_key, actual_hp, "admin_grant_milestone")

    notify_milestone_achieved(user_id, milestone_id, hp_awarded=actual_hp)

    return {"milestone": milestone, "hp_awarded": actual_hp, "awarded_by": admin_id}


def check_and_award_pwa_push_bonus(user_id: str) -> dict:
    """
    Check if both pwa_install and push_subscribe system milestones are completed by user_id.
    If both are completed and pwa_push_bonus has not been awarded, award pwa_push_bonus.
    Returns status dict.
    """
    db = get_db()
    # Fetch milestones for pwa_install, push_subscribe, pwa_push_bonus
    m_rows = (
        db.table("milestones")
        .select("id,trigger_type")
        .in_("trigger_type", ["pwa_install", "push_subscribe", "pwa_push_bonus"])
        .eq("is_active", "true")
        .execute()
    ) or []

    pwa_m = next((m for m in m_rows if m.get("trigger_type") == "pwa_install"), None)
    push_m = next((m for m in m_rows if m.get("trigger_type") == "push_subscribe"), None)
    bonus_m = next((m for m in m_rows if m.get("trigger_type") == "pwa_push_bonus"), None)

    pwa_done = _is_already_completed(db, user_id, pwa_m["id"], None) if pwa_m else False
    push_done = _is_already_completed(db, user_id, push_m["id"], None) if push_m else False
    bonus_done = _is_already_completed(db, user_id, bonus_m["id"], None) if bonus_m else False

    eligible = pwa_done and push_done
    bonus_result = None

    if eligible and not bonus_done and bonus_m:
        try:
            bonus_result = check_and_award_milestone(user_id, bonus_m["id"])
            if bonus_result.get("already_completed"):
                bonus_done = True
            elif not bonus_result.get("already_completed") and bonus_result.get("hp_awarded", 0) >= 0:
                bonus_done = True
        except Exception as e:
            logger.warning("check_and_award_pwa_push_bonus failed for user %s: %s", user_id, e)

    return {
        "pwa_install": pwa_done,
        "push_subscribe": push_done,
        "bonus_completed": bonus_done,
        "eligible": eligible,
        "bonus_result": bonus_result,
    }


def notify_milestone_achieved(user_id: str, milestone_id: str, hp_awarded: int = None) -> None:
    """
    Shared notification hook for all milestone/badge awards.
    Always fires push + in_app together. No email for gamification events.
    hp_awarded: what was actually credited (after multiplier / cap). Defaults to the milestone's listed HP.
    """
    try:
        from app.services.notification_service import send_notification
        # Service client: this runs for a user other than the caller (referrer, event attendee) or with no
        # request at all, so the caller's session may not be allowed to read this milestone.
        m = get_db().table("milestones").select("title,hp_awarded,time_window").eq("id", milestone_id).single().execute()
        if not m:
            return
        is_badge = m.get("time_window") is None
        hp = int(hp_awarded) if hp_awarded is not None else int(m.get("hp_awarded") or 0)
        _title = MSG.MILESTONE_BADGE_TITLE if is_badge else MSG.MILESTONE_CHALLENGE_TITLE
        # resolve_msg fills {currency}; a plain .format(hp=hp) raises KeyError('currency') and no notification is sent.
        _body = m["title"] + (resolve_msg(MSG.MILESTONE_HP_SUFFIX, hp=hp) if hp else "")
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

def _first_id(insert_result):
    """id of the row an insert returned (the client returns a list of rows), or None."""
    if isinstance(insert_result, list) and insert_result:
        return insert_result[0].get("id")
    if isinstance(insert_result, dict):
        return insert_result.get("id")
    return None


def _get_user_campus_id(db, user_id: str):
    """The user's own campus from their profile (None for no campus). Never the request's campus."""
    try:
        profile = db.table("profiles").select("campus_id").eq("id", user_id).single().execute()
    except Exception as e:
        logger.warning("_get_user_campus_id: profile lookup failed for %s: %s", user_id, e)
        return None
    return (profile or {}).get("campus_id")


def _record_actual_hp(db, user_id: str, milestone_id: str, period_key, actual_hp: int, caller: str) -> None:
    """Correct user_milestones.hp_awarded when what was credited differs from the listed amount."""
    try:
        q = db.table("user_milestones").eq("user_id", user_id).eq("milestone_id", milestone_id)
        if period_key:
            q = q.eq("period_key", period_key)
        else:
            q = q.is_("period_key", "null")
        q.update({"hp_awarded": actual_hp})
    except Exception as e:
        logger.warning("%s: update actual_hp failed: %s", caller, e)


def _milestone_period_key(time_window: str | None, today) -> str | None:
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
            q = db.table("order_reviews").select("id").eq("user_id", user_id)
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
                q = q.gte("created_at", period_start)  # event_checkins has created_at, not checked_in_at
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
    """ISO start of the current period for range queries (boundaries computed in WAT)."""
    if not time_window:
        return None
    now_wat = now + WAT_OFFSET
    if time_window == "weekly":
        monday = now_wat.date() - timedelta(days=now_wat.weekday())
        return f"{monday.isoformat()}T00:00:00+01:00"
    if time_window == "monthly":
        return f"{now_wat.year}-{now_wat.month:02d}-01T00:00:00+01:00"
    return None


def _award_milestone_hp(
    db, user_id: str, milestone_id: str, title: str,
    hp: int, destination: str, issued_by_admin_id: str = None,
    campus_id: str = None, completion_id: str = None,
) -> int:
    """Award HP for a milestone. destination: 'active' | 'pending'.
    completion_id: the user_milestones row's own id for THIS period's completion. It is the HP-transaction
    reference, so each period gets its own idempotency slot instead of colliding on the constant milestone_id
    across every repeat.
    Returns the amount ACTUALLY credited (post-multiplier, post-cap). 0 if nothing was credited."""
    if hp <= 0:
        return 0
    ref_id = completion_id or milestone_id  # fall back only if the insert didn't return an id
    from app.services.hp_service import award_active_hp, earn_pending_hp
    if destination == "pending":
        # earn_pending_hp applies the multiplier and the monthly pending cap itself, and books the tracker.
        try:
            result = earn_pending_hp(
                user_id=user_id, amount=hp, source_type="challenge",
                reference_id=ref_id, notes=f"Milestone: {title} pending",
                campus_id=campus_id,
            )
        except Exception as e:
            logger.warning("_award_milestone_hp (pending): failed for %s: %s", user_id, e)
            return 0
        return int(result.get("added_to_pending", 0) or 0)
    else:
        try:
            result = award_active_hp(
                user_id=user_id, amount=hp, source_type="challenge",
                reference_id=ref_id, reference_type="milestone",
                notes=f"Milestone: {title} active",
                issued_by_admin_id=issued_by_admin_id, campus_id=campus_id,
            )
        except Exception as e:
            logger.warning("_award_milestone_hp (active): failed for %s: %s", user_id, e)
            return 0
        return int(result.get("awarded", 0) or 0)
