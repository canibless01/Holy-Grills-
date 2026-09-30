import logging
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


def distribute_squad_hp(order_id: str, total_hp: int, organizer_id: str, campus_id: str = None):
    """
    Split HP evenly among registered squad members + organizer (active HP,
    matching existing behavior for registered members — confirmed by reading
    the original _distribute_squad_hp, which already used award_active_hp).
    Unregistered members get a pending_squad_hp row instead of being skipped,
    claimed at registration by auth_service.register's backfill.
    """
    if total_hp <= 0:
        return
    db = get_db()
    try:
        members = (
            db.table("squad_members")
            .select("id,user_id,email,is_registered")
            .eq("order_id", order_id)
            .execute()
        ) or []
        if not members:
            return

        registered = [m for m in members if m.get("is_registered") and m.get("user_id")]
        unregistered = [m for m in members if not m.get("is_registered")]
        registered_ids = [m["user_id"] for m in registered]
        if organizer_id not in registered_ids:
            registered_ids.insert(0, organizer_id)

        total_shares = len(registered_ids) + len(unregistered)
        if total_shares == 0:
            return
        # BUG (fixed): max(1, ...) forced at least 1 HP per member even when total_hp < total_shares
        # (a modest order split across a large squad), so the squad could be paid MORE than the order
        # actually earned. A floor of 0 means some/all members legitimately get 0 for a too-small order —
        # award_active_hp / the pending_squad_hp insert below both no-op cleanly on 0, so that's safe.
        share = total_hp // total_shares

        # Idempotency guard: award_active_hp below is now called WITH reference_type, so the database's own
        # unique index (user_id, reference_type, reference_id) protects each registered member from being
        # paid twice for this order. That index does not cover pending_squad_hp (unregistered members) or
        # the squad_members.hp_share write below, so this upfront check (keyed on the organizer, who is
        # always in registered_ids) skips the whole function on a re-entrant call — a retried webhook, a
        # retried route — instead of relying on the per-row index alone.
        try:
            already = (
                db.table("hp_transactions")
                .select("id")
                .eq("user_id", organizer_id)
                .eq("reference_type", "squad_bonus")
                .eq("reference_id", order_id)
                .limit(1)
                .execute()
            )
            if already:
                return
        except Exception as e:
            logger.warning("distribute_squad_hp: idempotency check failed for order %s: %s", order_id, e)

        from app.services.hp_service import award_active_hp
        for uid in registered_ids:
            try:
                award_active_hp(
                    user_id=uid, amount=share, source_type="squad_bonus",
                    reference_type="squad_bonus", reference_id=order_id,
                    notes=f"Squad HP split — {share} HP from order {order_id[:8]}",
                )
            except Exception as e:
                logger.warning("distribute_squad_hp: award failed for user %s order %s: %s", uid, order_id, e)

        for m in unregistered:
            try:
                db.table("pending_squad_hp").insert({
                    "email": m["email"], "order_id": order_id,
                    "hp_amount": share, "campus_id": campus_id, "status": "pending",
                })
            except Exception as e:
                logger.warning("distribute_squad_hp: pending_squad_hp insert failed for %s order %s: %s", m.get("email"), order_id, e)

        for m in members:
            if m.get("user_id") in registered_ids or m in unregistered:
                try:
                    db.table("squad_members").eq("id", m["id"]).update({"hp_share": share})
                except Exception:
                    pass
    except Exception as e:
        logger.error("distribute_squad_hp failed for order %s: %s", order_id, e)
