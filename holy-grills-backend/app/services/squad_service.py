import logging
from datetime import datetime, timezone
from app.db import get_db

logger = logging.getLogger(__name__)


def resolve_display_name(user_id: str = None, email: str = None, profile: dict = None) -> str:
    """
    Resolve a single user's display name: nickname -> full_name -> email
    prefix -> "Guest". If the nickname collides with another user's nickname
    on the same campus, appends " (<department>)" to disambiguate.
    Pass an already-fetched profile dict when the caller has one, to avoid
    a redundant query (e.g. inside a loop that already has profile rows).
    Use this everywhere EXCEPT leaderboard/hall-of-fame — see
    resolve_leaderboard_name below for those.
    """
    db = get_db()
    if profile is None:
        q = db.table("profiles").select("id,nickname,full_name,email,department,campus_id")
        if user_id:
            profile = q.eq("id", user_id).single().execute()
        elif email:
            profile = q.eq("email", email).single().execute()
        else:
            return "Guest"
    if not profile:
        return "Guest"

    nickname = (profile.get("nickname") or "").strip()
    if nickname:
        try:
            dupe_q = db.table("profiles").select("id").eq("nickname", nickname).neq("id", profile.get("id"))
            campus_id = profile.get("campus_id")
            if campus_id:
                dupe_q = dupe_q.eq("campus_id", campus_id)
            has_dupe = bool(dupe_q.limit(1).execute())
        except Exception:
            has_dupe = False  # dedup is a nice-to-have; never let it block name resolution
        if has_dupe:
            dept = profile.get("department")
            return f"{nickname} ({dept})" if dept else nickname
        return nickname

    full_name = (profile.get("full_name") or "").strip()
    if full_name:
        return full_name

    email_val = profile.get("email") or ""
    return email_val.split("@")[0] if "@" in email_val else "Guest"


def resolve_leaderboard_name(profile: dict) -> str:
    """
    Like resolve_display_name, but respects leaderboard_show_full_name: if
    the user opted to show their real name there, return full_name (falling
    back to standard nickname-first resolution if full_name is empty).
    Use this ONLY for leaderboard / leaderboard-snapshot / hall-of-fame /
    squad-leaderboard display. Notifications and everything else stay
    nickname-first via resolve_display_name regardless of this preference —
    friendly notifications ("your order is ready") always use nickname for
    familiarity; the leaderboard is the one place the user gets to choose
    which name represents them.
    """
    if profile.get("leaderboard_show_full_name"):
        full_name = (profile.get("full_name") or "").strip()
        if full_name:
            return full_name
    return resolve_display_name(profile=profile)


def resolve_leaderboard_names_batch(profiles: list) -> dict:
    """Batch version of resolve_leaderboard_name for list/leaderboard contexts."""
    opted_out_ids = {
        p["id"] for p in profiles
        if p.get("leaderboard_show_full_name") and (p.get("full_name") or "").strip()
    }
    result = {p["id"]: p["full_name"].strip() for p in profiles if p.get("id") in opted_out_ids}
    remaining = [p for p in profiles if p.get("id") not in opted_out_ids]
    if remaining:
        result.update(resolve_display_names_batch(remaining))
    return result


def resolve_display_names_batch(profiles: list) -> dict:
    """
    Batch version for list contexts — avoids N+1 queries.
    Input: list of profile dicts, each with id,nickname,full_name,email,
    department,campus_id already fetched by the caller.
    Output: {profile_id: display_name}.
    """
    by_campus = {}
    for p in profiles:
        by_campus.setdefault(p.get("campus_id"), []).append(p)

    result = {}
    for _campus_id, group in by_campus.items():
        nickname_counts = {}
        for p in group:
            nn = (p.get("nickname") or "").strip()
            if nn:
                nickname_counts[nn] = nickname_counts.get(nn, 0) + 1
        for p in group:
            nn = (p.get("nickname") or "").strip()
            if nn:
                dept = p.get("department")
                result[p["id"]] = f"{nn} ({dept})" if nickname_counts[nn] > 1 and dept else nn
            else:
                full_name = (p.get("full_name") or "").strip()
                if full_name:
                    result[p["id"]] = full_name
                else:
                    email_val = p.get("email") or ""
                    result[p["id"]] = email_val.split("@")[0] if "@" in email_val else "Guest"
    return result


def squad_share_plan(order_id: str, hp_amount: int, owner_id: str, campus_id: str = None):
    """
    Shared helper used by both _handle_delivery_rewards and distribute_squad_hp so they always agree.
    Reads the order's squad_members with service client and after B-7 lookup returns:
      - total_shares = 1 + number of distinct members (owner's own row, if present, not counted twice)
      - share = hp_amount // total_shares
      - owner_share = hp_amount - share * (total_shares - 1) (owner takes rounding remainder)
      - registered and unregistered member lists

    B-7 robustness: for each "unregistered" row, look up email with get_db() and if profile exists,
    treat as registered and update the row (user_id, is_registered=true).
    """
    db = get_db()
    if hp_amount <= 0:
        return {
            "total_shares": 1,
            "share": 0,
            "owner_share": 0,
            "registered": [],
            "unregistered": [],
            "all_members": [],
        }

    try:
        members = (
            db.table("squad_members")
            .select("id,user_id,email,is_registered,campus_id")
            .eq("order_id", order_id)
            .execute()
        ) or []
    except Exception as e:
        logger.warning('squad_share_plan: member read failed for %s', order_id, exc_info=True)
        raise RuntimeError('squad_member_plan_unavailable') from e

    if not members:
        return {
            "total_shares": 1,
            "share": hp_amount,
            "owner_share": hp_amount,
            "registered": [],
            "unregistered": [],
            "all_members": [],
        }

    # B-7 robustness: fix rows stored wrongly (is_registered=false but email belongs to existing profile)
    fixed_members = []
    for m in members:
        if not m.get("is_registered") and m.get("email"):
            try:
                prof = db.table("profiles").select("id,campus_id").eq("email", m["email"].strip().lower()).single().execute()
                if prof and prof.get("id"):
                    # Same-campus check if both have campus
                    order_campus = campus_id
                    if not order_campus:
                        try:
                            order_row = db.table("orders").select("campus_id").eq("id", order_id).single().execute()
                            order_campus = (order_row or {}).get("campus_id")
                        except Exception:
                            order_campus = None
                    if order_campus and prof.get("campus_id") and prof.get("campus_id") != order_campus:
                        # Different campus — keep as unregistered for privacy
                        fixed_members.append(m)
                        continue
                    # Update row to registered
                    try:
                        db.table("squad_members").eq("id", m["id"]).update({
                            "user_id": prof["id"],
                            "is_registered": True,
                        }).execute()
                        m = {**m, "user_id": prof["id"], "is_registered": True}
                    except Exception as exc:
                        logger.warning("squad_share_plan: failed to fix member row %s: %s", m.get("id"), exc)
            except Exception as exc:
                logger.warning("squad_share_plan: profile lookup failed for %s: %s", m.get("email"), exc)
        fixed_members.append(m)

    members = fixed_members

    # Deduplicate by email lowercased, keep first, but ensure owner not double counted
    seen_emails = set()
    seen_users = set()
    distinct_members = []
    for m in members:
        email_key = (m.get("email") or "").strip().lower()
        if not email_key:
            continue
        if email_key in seen_emails:
            continue
        # If member is the owner (same user_id as owner_id), don't count as separate share
        if m.get("user_id") and owner_id and str(m["user_id"]) == str(owner_id):
            continue
        if m.get('user_id') and str(m['user_id']) in seen_users:
            continue
        seen_emails.add(email_key)
        if m.get('user_id'):
            seen_users.add(str(m['user_id']))
        distinct_members.append(m)

    total_shares = 1 + len(distinct_members)  # owner + distinct others
    if total_shares <= 0:
        total_shares = 1

    share = hp_amount // total_shares if total_shares else 0
    owner_share = hp_amount - share * (total_shares - 1)  # owner takes remainder

    registered = [m for m in distinct_members if m.get("is_registered") and m.get("user_id")]
    unregistered = [m for m in distinct_members if not m.get("is_registered")]

    return {
        "total_shares": total_shares,
        "share": share,
        "owner_share": owner_share,
        "registered": registered,
        "unregistered": unregistered,
        "all_members": distinct_members,
        "all_raw_members": members,
    }


def distribute_squad_hp(order_id: str, total_hp: int, organizer_id: str, campus_id: str = None):
    """Compatibility entry: all financial delivery steps share one durable receipt."""
    from app.services.delivery_reward_recovery import complete_delivery_financial_rewards
    order = get_db().table('orders').select('*').eq('id', order_id).single().execute()
    if not order or order.get('user_id') != organizer_id or int(order.get('hp_earned') or 0) != int(total_hp):
        raise ValueError('delivery_reward_order_mismatch')
    return complete_delivery_financial_rewards(order)


def get_pending_squad_hp_report(campus_id: str = None, p_stale_days: int = 14):
    """
    Admin report for unclaimed squad HP (A9).
    Returns pending rows with age, stuck detection.
    A campus admin sees their campus, super_admin sees all.
    Test-2 RPC signature: public.get_pending_squad_hp_report(p_stale_days integer DEFAULT 14) RETURNS jsonb
    This service-client fallback mirrors that contract and filters by campus in Flask.
    """
    db = get_db()
    try:
        q = db.table("pending_squad_hp").select("id,email,order_id,hp_amount,campus_id,status,created_at").eq("status", "pending")
        if campus_id:
            q = q.eq("campus_id", campus_id)
        rows = q.order("created_at", ascending=True).execute() or []

        # Calculate age and stuck detection
        now = datetime.now(timezone.utc)
        enriched = []
        stuck_count = 0
        for r in rows:
            created_at_str = r.get("created_at")
            age_days = None
            try:
                if created_at_str:
                    created_dt = datetime.fromisoformat(str(created_at_str).replace("Z", "+00:00"))
                    age_days = (now - created_dt).days
            except Exception:
                age_days = None

            # Stuck: email now belongs to existing profile but row still pending
            is_stuck = False
            try:
                prof = db.table("profiles").select("id").eq("email", r.get("email", "").strip().lower()).single().execute()
                if prof:
                    is_stuck = True
                    stuck_count += 1
            except Exception:
                pass

            enriched.append({
                **r,
                "age_days": age_days,
                "is_stuck": is_stuck,
            })

        return {
            "pending": enriched,
            "count": len(enriched),
            "stuck_count": stuck_count,
            "campus_id": campus_id,
            "p_stale_days": p_stale_days,
        }
    except Exception as e:
        logger.error("get_pending_squad_hp_report failed: %s", e)
        return {"pending": [], "count": 0, "stuck_count": 0, "error": str(e), "campus_id": campus_id, "p_stale_days": p_stale_days}


def _claim_pending_row(db, pending, user_id):
    result = db.rpc("hg_claim_pending_squad_hp", {"p_pending": pending["id"], "p_user": user_id})
    if not isinstance(result, dict) or not result.get("success"):
        logger.warning("Squad share %s remains pending: %s", pending.get("id"), result)
        return False
    try:
        from app.services.hp_service import recalculate_tier
        recalculate_tier(user_id)
    except Exception:
        logger.warning("Squad share tier refresh deferred", exc_info=True)
    # Dispatch only the already committed receipt. The existing outbox job retries failures.
    try:
        from app.services.notification_outbox import start_reference_dispatch
        start_reference_dispatch("squad_hp_share", result["order_id"])
    except Exception:
        logger.warning("Squad share dispatch wake failed", exc_info=True)
    return True


def sweep_pending_squad_hp(campus_id: str = None):
    """Existing daily recovery; no campus means legacy null-campus rows only."""
    db = get_db()
    claimed = 0
    try:
        q = db.table("pending_squad_hp").select("id,email,campus_id").eq("status", "pending")
        q = q.eq("campus_id", campus_id) if campus_id else q.is_("campus_id", "null")
        for pending in q.execute() or []:
            try:
                if not pending.get("campus_id"):
                    continue  # Ambiguous legacy ownership needs review, never a guessed campus.
                profile = (db.table("profiles").select("id").eq("email", (pending.get("email") or "").strip().lower())
                           .eq("campus_id", pending["campus_id"]).eq("is_active", True).single().execute())
                if profile and profile.get("id") and _claim_pending_row(db, pending, profile["id"]):
                    claimed += 1
            except Exception:
                logger.warning("Squad share recovery failed for row %s", pending.get("id"), exc_info=True)
    except Exception:
        logger.error("Pending squad HP sweep failed", exc_info=True)
    return {"claimed": claimed, "campus_id": campus_id}


def claim_pending_for_user(email: str, user_id: str, campus_id: str = None):
    """Signup/backfill share claims use the same atomic, authoritative DB checks."""
    if not campus_id:
        return {"claimed": 0}
    db = get_db()
    claimed = 0
    try:
        pending = (db.table("pending_squad_hp").select("id").eq("email", email.strip().lower())
                   .eq("campus_id", campus_id).eq("status", "pending").execute()) or []
        for row in pending:
            try:
                claimed += int(_claim_pending_row(db, row, user_id))
            except Exception:
                logger.warning("Squad share claim failed for row %s", row.get("id"), exc_info=True)
        return {"claimed": claimed}
    except Exception as exc:
        logger.error("Squad share lookup failed", exc_info=True)
        return {"claimed": 0, "error": str(exc)}
