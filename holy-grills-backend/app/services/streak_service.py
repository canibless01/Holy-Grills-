"""
Streak Service — login/check-in streak and order streak tracking.

LOGIN / CHECK-IN STREAK (rebuilt):
  Week = Monday–Sunday (ISO week).
  Daily check-in = records attendance, 0 HP.
  Up to 2 missed days reclaimable via food order OR wallet top-up ≥₦1,000
  on the missed day itself.
  Week fails if more than 2 unremedied misses.
  Week completion pays HP from login_streak_rewards table (no hardcoding):
    Week 1 → 25 HP Pending, Week 2 → 40, Week 3 → 60, Week 4+ → 80.
  Fraud-flagged check-ins silently excluded.

ORDER STREAK (new, independent):
  ≥1 delivered food order per calendar week (Mon–Sun).
  Resets to 0 on missed week.
  HP rewards from order_streak_rewards table (admin-configurable).
  HP destination: Active.

MONTHLY PENDING CAP:
  check_monthly_cap / update_monthly_tracker — used by any route awarding
  free-activity pending HP (challenges, reviews, social, etc.).
  Cap reads from system_settings key 'monthly_pending_cap' (default 1000).
"""

import uuid
from datetime import datetime, timezone, date, timedelta
from app.db import get_db, get_user_client
from app.utils.tz import today_wat
from app.utils.logger import get_logger

logger = get_logger(__name__)


# ── Helpers ────────────────────────────────────────────────────────────────────

def _get_setting(db, key: str, default: str) -> str:
    try:
        row = db.table("system_settings").select("value").eq("key", key).is_("campus_id", "null").single().execute()
        return row.get("value", default) if row else default
    except Exception:
        return default


def _monday_of_week(d: date) -> date:
    """Return the Monday of the ISO week containing d."""
    return d - timedelta(days=d.weekday())


def _week_key(d: date) -> str:
    """ISO week string 'YYYY-WW'."""
    iso = d.isocalendar()
    return f"{iso[0]:04d}-{iso[1]:02d}"


# ── Monthly cap helpers ────────────────────────────────────────────────────────

def check_monthly_cap(user_id: str, hp_to_add: int) -> dict:
    """
    Check headroom under the monthly free-activity HP cap.
    Returns {"allowed": bool, "remaining": int, "capped_amount": int}
    where capped_amount is the HP to actually award (may be < hp_to_add).

    Does NOT update the tracker — call update_monthly_tracker() after awarding.
    Cap key: 'monthly_pending_cap' in system_settings (default 1000).
    """
    db = get_db()
    cap = int(_get_setting(db, "monthly_pending_cap", "1000"))
    month = datetime.now(timezone.utc).strftime("%Y-%m")

    try:
        row = (
            db.table("monthly_hp_tracker")
            .select("total_earned")
            .eq("user_id", user_id)
            .eq("month", month)
            .single()
            .execute()
        )
        earned_so_far = int(row.get("total_earned", 0)) if row else 0
    except Exception:
        earned_so_far = 0

    remaining = max(0, cap - earned_so_far)
    if remaining <= 0:
        return {"allowed": False, "remaining": 0, "capped_amount": 0, "cap": cap}

    capped_amount = min(hp_to_add, remaining)
    return {"allowed": True, "remaining": remaining, "capped_amount": capped_amount, "cap": cap}


def update_monthly_tracker(user_id: str, hp_awarded: int) -> None:
    """Record awarded HP against the monthly cap tracker."""
    if hp_awarded <= 0:
        return
    db = get_db()
    month = datetime.now(timezone.utc).strftime("%Y-%m")
    now = datetime.now(timezone.utc).isoformat()
    try:
        existing = (
            db.table("monthly_hp_tracker")
            .select("id,total_earned")
            .eq("user_id", user_id)
            .eq("month", month)
            .single()
            .execute()
        )
        if existing:
            db.table("monthly_hp_tracker").eq("id", existing["id"]).update({
                "total_earned": int(existing.get("total_earned", 0)) + hp_awarded,
                "updated_at": now,
            })
        else:
            db.table("monthly_hp_tracker").insert({
                "user_id": user_id,
                "month": month,
                "total_earned": hp_awarded,
                "updated_at": now,
            })
    except Exception as e:
        logger.warning("update_monthly_tracker: failed for %s: %s", user_id, e)


# ── LOGIN / CHECK-IN STREAK ────────────────────────────────────────────────────

def process_login_streak(user_id: str, campus_id: str = None) -> dict:
    """
    Call on every successful authenticated login.
    Marks today as checked-in in the week_state JSONB.
    Evaluates completed/failed weeks when the week turns over.
    Fraud-flagged users: silently excluded.

    Returns:
      {"action": "started"|"same_day"|"checked_in"|"new_week_started",
       "hp_awarded": int,
       "streak_week": int,   # current cycle week number (1,2,3,4+)
       "week_start": str,
       "week_progress": {...}}
    """
    db = get_db()
    now = datetime.now(timezone.utc)
    today = today_wat()

    # Check fraud flag
    profile = (
        db.table("profiles")
        .select("is_fraud_flagged,is_active")
        .eq("id", user_id)
        .single()
        .execute()
    )
    if (profile or {}).get("is_fraud_flagged") or (profile or {}).get("is_active") is False:
        return {"action": "excluded", "hp_awarded": 0, "streak_week": 0}

    # Load or create streak record
    try:
        streak = (
            db.table("login_streaks")
            .select("*")
            .eq("user_id", user_id)
            .single()
            .execute()
        )
    except Exception:
        streak = None

    if not streak:
        # Bootstrap
        week_start = _monday_of_week(today)
        day_offset = str((today - week_start).days)
        if campus_id is None:
            from flask import has_app_context, g
            if has_app_context():
                campus_id = getattr(g, 'campus_id', None)
        record = {
            "user_id": user_id,
            "streak_count": 1,
            "last_login_date": today.isoformat(),
            "last_updated": now.isoformat(),
            "current_week_start": week_start.isoformat(),
            "week_state": {day_offset: "checked"},
            "cycle_week_number": 1,
            "consecutive_weeks": 0,
            "campus_id": campus_id,
        }
        try:
            db.table("login_streaks").insert(record)
        except Exception as ie:
            err_str = str(ie)
            if "23505" in err_str or "duplicate" in err_str.lower() or "unique" in err_str.lower():
                # Lost the race to a concurrent request for this same user -- the row now exists for
                # real. Re-fetch and process today's check-in against it instead of reporting failure.
                try:
                    existing = (
                        db.table("login_streaks").select("*").eq("user_id", user_id).single().execute()
                    )
                except Exception:
                    existing = None
                if existing:
                    return _process_login_streak_checkin(db, user_id, existing, now, today, campus_id)
            logger.warning("process_login_streak: insert failed for %s: %s", user_id, ie)
            return {"action": "failed", "hp_awarded": 0, "streak_week": 1}
        _touch_last_activity(db, user_id, now)
        return {
            "action": "started",
            "hp_awarded": 0,
            "streak_week": 1,
            "week_start": week_start.isoformat(),
            "week_progress": _build_week_progress({day_offset: "checked"}, week_start, today),
        }

    _deliver_login_week_notice(db, user_id, streak.get("last_week_receipt"))
    return _process_login_streak_checkin(db, user_id, streak, now, today, campus_id)


def _process_login_streak_checkin(db, user_id: str, streak: dict, now: datetime, today: date, campus_id: str = None) -> dict:
    """The 'streak row already exists' half of process_login_streak -- factored out so the
    insert-lost-the-race recovery path above can reuse it on the row the winner just created."""
    # Parse stored week state
    stored_week_start_str = streak.get("current_week_start")
    try:
        stored_week_start = date.fromisoformat(str(stored_week_start_str)[:10]) if stored_week_start_str else None
    except Exception:
        stored_week_start = None

    current_week_start = _monday_of_week(today)
    week_state = streak.get("week_state") or {}
    cycle_week = int(streak.get("cycle_week_number") or 1)
    consecutive_weeks = int(streak.get("consecutive_weeks") or 0)
    hp_awarded = 0

    # Same week — just mark today if not already marked
    if stored_week_start and stored_week_start == current_week_start:
        day_offset = str((today - current_week_start).days)
        if day_offset in week_state:
            # Already checked in today
            _touch_last_activity(db, user_id, now)
            return {
                "action": "same_day",
                "hp_awarded": 0,
                "streak_week": cycle_week,
                "week_start": current_week_start.isoformat(),
                "week_progress": _build_week_progress(week_state, current_week_start, today),
            }
        try:
            result = db.rpc("hg_mark_current_login_checkin", {"p_user_id": user_id})
            if not isinstance(result, dict) or not result.get("success"):
                raise RuntimeError("Check-in state changed; retry attendance")
            saved = result["streak"]
        except Exception as ue:
            logger.warning("process_login_streak: atomic same-week check-in failed for %s: %s", user_id, ue)
            return {"action": "failed", "hp_awarded": 0, "streak_week": cycle_week}
        _touch_last_activity(db, user_id, now)
        return {
            "action": result["action"], "hp_awarded": 0,
            "streak_week": int(saved.get("cycle_week_number") or 1),
            "week_start": saved["current_week_start"],
            "week_progress": _build_week_progress(saved.get("week_state") or {}, current_week_start, today),
        }

    # The ledger, monthly tracker and week advancement are one database commit.
    try:
        result = db.rpc("hg_rollover_login_week", {"p_user_id": user_id})
        if not isinstance(result, dict) or not result.get("success") or not isinstance(result.get("streak"), dict):
            raise RuntimeError("Weekly check-in recovery remains pending")
        saved = result["streak"]
    except Exception as exc:
        logger.warning("Weekly check-in payout not advanced for %s: %s", user_id, exc)
        return {"action": "failed", "hp_awarded": 0, "streak_week": cycle_week}
    _deliver_login_week_notice(db, user_id, result.get("receipt"))
    _touch_last_activity(db, user_id, now)
    saved_start = date.fromisoformat(saved["current_week_start"])
    return {
        "action": "same_day" if result.get("replayed") else "new_week_started",
        "previous_week_completed": bool((result.get("receipt") or {}).get("previous_week_completed")),
        "hp_awarded": int(result.get("hp_awarded") or 0),
        "streak_week": int(saved.get("cycle_week_number") or 1),
        "week_start": saved["current_week_start"],
        "week_progress": _build_week_progress(saved.get("week_state") or {}, saved_start,
                                               date.fromisoformat(result.get("today") or today.isoformat())),
    }


def _deliver_login_week_notice(db, user_id, receipt):
    if not receipt or receipt.get("notified"):
        return
    try:
        from app.services.notification_service import send_notification
        completed = bool(receipt["previous_week_completed"])
        data = {"missed_days": receipt["missed_days"], "week_start": receipt["week_start"]}
        if completed:
            data.update(week=receipt["cycle_week"], hp=receipt["hp_awarded"], capped=bool(receipt.get("capped")))
        send_notification(user_id=user_id,
                          notif_type="checkin_streak_week" if completed else "streak_cycle_failed",
                          template_data=data, reference_id=receipt["reference_id"],
                          reference_type="login_week", strict=True)
        db.rpc("hg_ack_login_week_notice", {"p_user_id": user_id, "p_reference_id": receipt["reference_id"]})
    except Exception:
        logger.warning("Weekly check-in credited; notice remains recoverable for %s", user_id, exc_info=True)


def try_reclaim_checkin(user_id: str, reclaim_type: str = "order", reference_id: str = None) -> dict:
    """Reclaim the activity's actual WAT day from a validated persisted receipt.

    A replay never claims a different day. Current-week attendance is merged by
    the database; no stale Python week-state snapshot is written back.
    """
    try:
        uuid.UUID(str(reference_id))
    except (TypeError, ValueError, AttributeError):
        return {"reclaimed": False, "day_offset": None, "reason": "missing_receipt"}
    try:
        from flask import current_app
        result = get_db().rpc("hg_reclaim_login_checkin", {
            "p_user_id": user_id, "p_source_type": reclaim_type,
            "p_source_id": str(reference_id),
            "p_min_topup": current_app.config.get("STREAK_RECLAIM_MIN_TOPUP", 1000),
        })
        if not isinstance(result, dict) or "reclaimed" not in result or result.get("error"):
            raise RuntimeError("Check-in reclamation remains pending")
        if (result.get("reclaimed") or result.get("already_reclaimed")) and result.get("reference_id"):
            from app.services.notification_outbox import start_reference_dispatch
            start_reference_dispatch("checkin_reclaimed", result["reference_id"])
        return result
    except Exception as exc:
        logger.warning("try_reclaim_checkin: recovery failed for %s: %s", user_id, exc)
        return {"reclaimed": False, "day_offset": None, "reason": "recovery_pending"}


def _build_week_progress(week_state: dict, week_start: date, today: date) -> dict:
    """Build a human-readable progress dict for the current week."""
    days = {}
    day_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    for i in range(7):
        d = week_start + timedelta(days=i)
        key = str(i)
        if key in week_state:
            status = week_state[key]  # 'checked' or 'reclaimed'
        elif d < today:
            status = "missed"
        elif d == today:
            status = "today"
        else:
            status = "upcoming"
        days[day_names[i]] = status
    return {"week_start": week_start.isoformat(), "days": days}


def order_streak_rewards(db, campus_id=None):
    """Effective configured milestones: a campus row overrides the same global week."""
    rows = db.table("order_streak_rewards").select("weeks,hp_awarded,is_active,campus_id").execute() or []
    effective = {}
    for row in sorted(rows, key=lambda r: r.get("campus_id") is not None):
        if row.get("campus_id") not in (None, campus_id):
            continue
        effective[int(row["weeks"])] = row
    return [{"weeks": week, "hp_awarded": int(row.get("hp_awarded") or 0)}
            for week, row in sorted(effective.items()) if row.get("is_active") and int(row.get("hp_awarded") or 0) > 0]


def get_order_streak(user_id, campus_id=None, db=None):
    """Read order consistency independently of daily check-ins; never award from a GET."""
    db = db or get_user_client()
    today = today_wat()
    current_week = _week_key(today)
    previous_week = _week_key(today - timedelta(weeks=1))
    row = db.table("order_streaks").select("streak_weeks,longest_streak,last_order_week").eq("user_id", user_id).single().execute() or {}
    weeks = int(row.get("streak_weeks") or 0) if row.get("last_order_week") in (current_week, previous_week) else 0
    milestones = order_streak_rewards(db, campus_id)
    return {
        "streak_weeks": weeks, "longest_streak": int(row.get("longest_streak") or 0),
        "current_week": current_week, "week_start": _monday_of_week(today).isoformat(),
        "counted_this_week": row.get("last_order_week") == current_week,
        "last_order_week": row.get("last_order_week"), "rewards": milestones,
        "next_reward": next((reward for reward in milestones if reward["weeks"] > weeks), None),
        "repeat_after_week": milestones[-1]["weeks"] if milestones else None,
    }


def get_streak(user_id: str, campus_id: str = None) -> dict:
    """Return the user's current login streak info."""
    db = get_user_client()
    today = today_wat()
    try:
        order_summary = get_order_streak(user_id, campus_id, db)
    except Exception:
        logger.warning("Order streak summary unavailable for %s", user_id, exc_info=True)
        order_summary = None
    try:
        row = (
            db.table("login_streaks")
            .select("streak_count,last_login_date,current_week_start,week_state,cycle_week_number,consecutive_weeks,last_updated")
            .eq("user_id", user_id)
            .single()
            .execute()
        )
        if not row:
            return {"streak_count": 0, "last_login_date": None, "cycle_week_number": 1, "order_streak": order_summary}

        # Build week progress if we have week data
        week_progress = None
        week_start_str = row.get("current_week_start")
        if week_start_str:
            try:
                week_start = date.fromisoformat(str(week_start_str)[:10])
                week_state = row.get("week_state") or {}
                week_progress = _build_week_progress(week_state, week_start, today)
            except Exception:
                pass

        return {
            "order_streak": order_summary,
            "streak_count": row.get("streak_count") or 0,
            "last_login_date": row.get("last_login_date"),
            "cycle_week_number": row.get("cycle_week_number") or 1,
            "consecutive_weeks": row.get("consecutive_weeks") or 0,
            "week_progress": week_progress,
            "last_updated": row.get("last_updated"),
        }
    except Exception as e:
        logger.error("get_streak failed for %s: %s", user_id, e)
        raise


def _touch_last_activity(db, user_id: str, now: datetime) -> None:
    """Update profiles.last_activity_at for decay-onset tracking."""
    try:
        db.table("profiles").eq("id", user_id).update({"last_activity_at": now.isoformat()})
    except Exception as exc:
        logger.warning("streak: could not touch last_activity_at for %s — the activity is not recorded: %s",
                        user_id, exc)


# ── ORDER STREAK ───────────────────────────────────────────────────────────────

def process_order_streak(user_id: str, order_id: str, campus_id: str = None) -> dict:
    """
    Called when a food order is delivered.
    If this is the first qualifying order for its delivered ISO week, increments
    the order streak. Awards HP from order_streak_rewards table.

    Returns {"streak_weeks": int, "hp_awarded": int, "new_week": bool}
    """
    # The database owns qualification, delivery week, configured reward snapshot,
    # balance, streak state and replay protection in one transaction.
    from app.messages import MSG
    from app.services.hp_service import _get_hp_multiplier
    result = get_db().rpc("hg_process_order_streak_atomic", {
        "p_order_id": order_id,
        "p_multiplier": _get_hp_multiplier(campus_id),
        "p_notes": MSG.ORDER_STREAK_LEDGER_NOTE,
    })
    if not isinstance(result, dict) or not result.get("success"):
        raise RuntimeError(MSG.ORDER_STREAK_RECOVERY_PENDING)
    awarded_hp = int(result.get("hp_awarded") or 0)
    if awarded_hp > 0:
        from app.services.notification_service import send_notification
        try:
            weeks = int(result["streak_weeks"])
            send_notification(
                user_id=user_id, notif_type="order_streak",
                template_data={"weeks": weeks, "plural": "s" if weeks != 1 else "", "hp": awarded_hp},
                reference_id=result["reference_id"], reference_type="streak",
            )
        except Exception:
            logger.warning("Order streak credited; notification pending for %s", order_id, exc_info=True)
    return result
