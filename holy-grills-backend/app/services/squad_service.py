import logging
from datetime import datetime, timezone
from app.db import get_db
from app.utils.settings import get_validated_setting

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
        logger.warning("squad_share_plan: failed to read squad_members for order %s: %s", order_id, e)
        members = []

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
        seen_emails.add(email_key)
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
    """
    True split + owner bonus implementation (B-8).

    - total_hp is the full order HP (100%)
    - Split equally between owner and members on that order (registered + unregistered)
    - Owner takes rounding remainder
    - Registered members: active HP at once, tagged squad_split, no multiplier
    - Unregistered: pending_squad_hp row for share, skip if (order,email) already has a row
    - Owner bonus: squad_hp_bonus_pct% of order HP, tagged squad_bonus, only when at least one other
      registered member exists. pct from settings, default 30, 0 = split only.
    - No multiplier: every squad payment uses award_active_hp(..., apply_multiplier=False)
    - Re-entry protection: rely on orders.squad_hp_distributed, unique reference index, and pending-row check
    """
    if total_hp <= 0:
        return
    db = get_db()

    try:
        # Use shared helper for consistent share calculation
        plan = squad_share_plan(order_id, total_hp, organizer_id, campus_id=campus_id)
        share = plan["share"]
        registered = plan["registered"]
        unregistered = plan["unregistered"]

        # Idempotency: check if squad HP already distributed for this order via hp_transactions
        # We check for any squad_split for this order to avoid replay; bonus is checked separately
        try:
            existing_split = (
                db.table("hp_transactions")
                .select("id")
                .eq("reference_type", "squad_split")
                .eq("reference_id", order_id)
                .limit(1)
                .execute()
            )
            has_existing_splits = bool(existing_split)
        except Exception as e:
            logger.warning("distribute_squad_hp: idempotency check failed for order %s: %s", order_id, e)
            has_existing_splits = False

        from app.services.hp_service import award_active_hp

        # Determine bonus pct
        try:
            pct = get_validated_setting(db, "squad_hp_bonus_pct", default=30, minimum=0, maximum=100, campus_id=campus_id)
            pct = int(pct)
        except Exception as e:
            logger.warning("distribute_squad_hp: failed to read squad_hp_bonus_pct for order %s, using 30: %s", order_id, e)
            pct = 30

        # Registered members (not owner): squad_split
        if not has_existing_splits:
            for m in registered:
                uid = m.get("user_id")
                if not uid or str(uid) == str(organizer_id):
                    continue
                try:
                    award_active_hp(
                        user_id=uid,
                        amount=share,
                        source_type="squad_split",
                        reference_type="squad_split",
                        reference_id=order_id,
                        notes=f"Squad split — {share} HP from order {order_id[:8]}",
                        apply_multiplier=False,
                        campus_id=campus_id,
                    )
                except Exception as e:
                    logger.warning("distribute_squad_hp: squad_split award failed for user %s order %s: %s", uid, order_id, e)

            # Unregistered: pending_squad_hp
            for m in unregistered:
                email = (m.get("email") or "").strip().lower()
                if not email:
                    continue
                try:
                    # Skip if (order,email) already has a pending row
                    existing_pending = (
                        db.table("pending_squad_hp")
                        .select("id")
                        .eq("order_id", order_id)
                        .eq("email", email)
                        .limit(1)
                        .execute()
                    )
                    if existing_pending:
                        continue
                    db.table("pending_squad_hp").insert({
                        "email": email,
                        "order_id": order_id,
                        "hp_amount": share,
                        "campus_id": campus_id,
                        "status": "pending",
                    }).execute()
                except Exception as e:
                    logger.warning("distribute_squad_hp: pending_squad_hp insert failed for %s order %s: %s", m.get("email"), order_id, e)

        # Owner bonus: only if at least one other registered member exists
        has_other_registered = len(registered) > 0
        if has_other_registered and pct > 0:
            # Check if bonus already paid
            try:
                bonus_exists = (
                    db.table("hp_transactions")
                    .select("id")
                    .eq("user_id", organizer_id)
                    .eq("reference_type", "squad_bonus")
                    .eq("reference_id", order_id)
                    .limit(1)
                    .execute()
                )
                if bonus_exists:
                    bonus_exists = True
                else:
                    bonus_exists = False
            except Exception:
                bonus_exists = False

            if not bonus_exists:
                bonus_amount = (total_hp * pct) // 100
                if bonus_amount > 0:
                    try:
                        award_active_hp(
                            user_id=organizer_id,
                            amount=bonus_amount,
                            source_type="squad_bonus",
                            reference_type="squad_bonus",
                            reference_id=order_id,
                            notes=f"Squad bonus {pct}% — {bonus_amount} HP from order {order_id[:8]}",
                            apply_multiplier=False,
                            campus_id=campus_id,
                        )
                    except Exception as e:
                        logger.warning("distribute_squad_hp: squad_bonus award failed for owner %s order %s: %s", organizer_id, order_id, e)

        # Update each member's hp_share with their share
        try:
            all_members = plan.get("all_raw_members") or []
            for m in all_members:
                # Only update distinct members that are part of the share plan
                email_key = (m.get("email") or "").strip().lower()
                if not email_key:
                    continue
                # Check if this email is in distinct list
                if email_key not in { (x.get("email") or "").strip().lower() for x in plan.get("all_members", []) }:
                    continue
                try:
                    db.table("squad_members").eq("id", m["id"]).update({"hp_share": share}).execute()
                except Exception as exc:
                    logger.warning("distribute_squad_hp: could not record hp_share for member %s: %s", m.get("id"), exc)
        except Exception as e:
            logger.warning("distribute_squad_hp: hp_share update failed for order %s: %s", order_id, e)

    except Exception as e:
        logger.error("distribute_squad_hp failed for order %s: %s", order_id, e)


def get_pending_squad_hp_report(campus_id: str = None):
    """
    Admin report for unclaimed squad HP (A9).
    Returns pending rows with age, stuck detection.
    A campus admin sees their campus, super_admin sees all.
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
        }
    except Exception as e:
        logger.error("get_pending_squad_hp_report failed: %s", e)
        return {"pending": [], "count": 0, "stuck_count": 0, "error": str(e), "campus_id": campus_id}


def sweep_pending_squad_hp(campus_id: str = None):
    """
    Daily sweep that pays any pending_squad_hp row whose email now matches an existing account.
    Same claim logic as sign-up claim in auth_service.register.
    """
    db = get_db()
    claimed = 0
    try:
        q = db.table("pending_squad_hp").select("id,email,order_id,hp_amount,campus_id").eq("status", "pending")
        if campus_id:
            q = q.eq("campus_id", campus_id)
        pending_rows = q.execute() or []

        from app.services.hp_service import award_active_hp
        from app.services.notification_service import send_notification

        for p in pending_rows:
            email = (p.get("email") or "").strip().lower()
            if not email:
                continue
            try:
                prof = db.table("profiles").select("id,campus_id").eq("email", email).single().execute()
                if not prof or not prof.get("id"):
                    continue
                user_id = prof["id"]
                # Claim as squad_split_claimed
                award_active_hp(
                    user_id=user_id,
                    amount=p["hp_amount"],
                    source_type="squad_split_claimed",
                    reference_type="squad_split_claimed",
                    reference_id=p["order_id"],
                    notes=f"Squad HP claimed from order {p['order_id'][:8]} (sweep)",
                    apply_multiplier=False,
                    campus_id=p.get("campus_id") or prof.get("campus_id"),
                )
                db.table("pending_squad_hp").eq("id", p["id"]).update({"status": "claimed"}).execute()
                try:
                    send_notification(
                        user_id=user_id,
                        notif_type="squad_hp_share",
                        template_data={"hp": p["hp_amount"]},
                        campus_id=p.get("campus_id") or prof.get("campus_id"),
                    )
                except Exception:
                    pass
                claimed += 1
            except Exception as e:
                logger.warning("sweep_pending_squad_hp: claim failed for %s row %s: %s", email, p.get("id"), e)

    except Exception as e:
        logger.error("sweep_pending_squad_hp failed: %s", e)

    return {"claimed": claimed, "campus_id": campus_id}


def claim_pending_for_user(email: str, user_id: str, campus_id: str = None):
    """
    Claim pending squad HP for a specific email/user (used in backfill and register flow).
    """
    db = get_db()
    try:
        pending = db.table("pending_squad_hp").select("id,order_id,hp_amount,campus_id").eq("email", email.strip().lower()).eq("status", "pending").execute() or []
        if not pending:
            return {"claimed": 0}
        from app.services.hp_service import award_active_hp
        from app.services.notification_service import send_notification
        claimed = 0
        for p in pending:
            try:
                award_active_hp(
                    user_id=user_id,
                    amount=p["hp_amount"],
                    source_type="squad_split_claimed",
                    reference_type="squad_split_claimed",
                    reference_id=p["order_id"],
                    notes=f"Squad HP claimed from order {p['order_id'][:8]}",
                    apply_multiplier=False,
                    campus_id=p.get("campus_id") or campus_id,
                )
                db.table("pending_squad_hp").eq("id", p["id"]).update({"status": "claimed"}).execute()
                try:
                    send_notification(
                        user_id=user_id,
                        notif_type="squad_hp_share",
                        template_data={"hp": p["hp_amount"]},
                        campus_id=p.get("campus_id") or campus_id,
                    )
                except Exception:
                    pass
                claimed += 1
            except Exception as e:
                logger.error("claim_pending_for_user: failed for %s row %s: %s", user_id, p.get("id"), e)
        return {"claimed": claimed}
    except Exception as e:
        logger.error("claim_pending_for_user failed for %s: %s", email, e)
        return {"claimed": 0, "error": str(e)}
