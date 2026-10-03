"""
Auth service — register, login, refresh, current user, profile update, logout, verification / reset e-mails.
"""
import uuid
import re
from datetime import datetime, timezone, date
from app.utils.tz import today_wat
from app.utils.logger import get_logger
from app.utils.reference_data import resolve_level, resolve_department
from flask import current_app
from app.db import get_db, get_user_client, SupabaseError
from app.services.notification_service import send_notification
from app.services import hp_service
from app.messages import MSG, resolve_msg

logger = get_logger(__name__)


def _redirect_url(path_key: str, default_path: str):
    """Absolute link target for Supabase emails, built from FRONTEND_URL. None when FRONTEND_URL is unset."""
    base = (current_app.config.get("FRONTEND_URL") or "").rstrip("/")
    if not base:
        return None
    return base + current_app.config.get(path_key, default_path)


def register(email: str, password: str, full_name: str, phone: str = None, date_of_birth: str = None, referred_by_code: str = None, department: str = None, academic_level: str = None, campus_id: str = None, nickname: str = None) -> dict:
    """
    Create a Supabase Auth user and profile.
    Returns Supabase auth session (access_token, refresh_token, user).
    """
    db = get_db()
    config = current_app.config

    # B3: squad_roster / squad_members / pending_squad_hp store lowercase, stripped emails (text columns).
    email = email.strip().lower()

    # Phone validation
    if phone:
        phone_pattern = config.get("PHONE_REGEX_PATTERN", r"^\+234[0-9]{10}$")
        if not re.match(phone_pattern, phone):
            raise ValueError(MSG.PHONE_FORMAT_INVALID)

    # DOB validation — user must meet minimum age
    if date_of_birth:
        try:
            dob = date.fromisoformat(str(date_of_birth)[:10])
            today = today_wat()
            age = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
            minimum_age = config.get("MINIMUM_AGE", 16)
            if age < minimum_age:
                raise ValueError(resolve_msg(MSG.REGISTER_MIN_AGE, minimum_age=minimum_age))
        except ValueError as e:
            if "must be at least" in str(e):
                raise
            raise ValueError(MSG.DOB_FORMAT_INVALID)

    if nickname:
        nickname = nickname.strip()
        if not re.match(r"^[A-Za-z0-9_ ]{2,20}$", nickname):
            raise ValueError(MSG.NICKNAME_INVALID)

    # B1 + B15: resolve department / academic level ONCE, and BEFORE the auth account exists,
    # so a bad value can never leave a half-registered account behind.
    # [D19 B-17] departments / academic_levels are per campus (campus_id NULL = shared by all): resolve them for
    # THIS student's campus so two campuses that use the same department name do not get each other's id/faculty.
    dept_name = department.strip() if department else None
    dept_id = dept_faculty = None
    if dept_name:
        try:
            dept_row = resolve_department(db, dept_name, campus_id)
        except SupabaseError as e:
            logger.error("register: department lookup failed for %r: %s", dept_name, e)
            raise ValueError(MSG.REGISTER_FAILED_RETRY)
        if not dept_row:
            raise ValueError(resolve_msg(MSG.DEPARTMENT_INVALID, department=dept_name))
        dept_name = dept_row.get("name") or dept_name      # store the canonical spelling
        dept_id = dept_row["id"]
        dept_faculty = dept_row.get("faculty")
    level_value = None
    if academic_level:
        try:
            level_row = resolve_level(db, str(academic_level).strip(), campus_id)
        except SupabaseError as e:
            logger.error("register: academic level lookup failed for %r: %s", academic_level, e)
            raise ValueError(MSG.REGISTER_FAILED_RETRY)
        if not level_row:
            raise ValueError(resolve_msg(MSG.ACADEMIC_LEVEL_INVALID, level=academic_level))
        level_value = level_row["value"]

    existing = db.table("profiles").select("id").eq("email", email).execute()
    if existing and len(existing) > 0:
        raise ValueError(MSG.REGISTER_EMAIL_AMBIGUOUS)

    try:
        auth_result = db.auth_sign_up(
            email=email,
            password=password,
            user_metadata={"full_name": full_name},
            redirect_to=_redirect_url("AUTH_VERIFY_REDIRECT_PATH", "/login"),   # helper + env paths: see B-14
        )
    except SupabaseError as e:
        details = getattr(e, "details", None) or {}
        # error_msg is for MATCHING only (lowercased blob of everything the provider said) -- it is never shown.
        error_msg = " ".join(str(x) for x in (e, details.get("msg"), details.get("message"), details.get("error_code")) if x).lower()
        if any(k in error_msg for k in ("user already registered", "user_already_exists", "email_exists", "duplicate")):
            raise ValueError(MSG.REGISTER_EMAIL_AMBIGUOUS)
        # What the user sees: GoTrue's own human-readable text (`msg` / `error_description`, e.g. "Password should be at
        # least 6 characters."), and only for a 4xx -- a rejection of what they submitted. This used to show the lowercased
        # matching blob (provider error codes, "supabase error", and for a 5xx whatever the database said).
        provider_text = str(details.get("msg") or details.get("error_description") or "").strip()
        status = getattr(e, "status_code", 500) or 500
        logger.warning("register: signup rejected by provider (status %s, code %s): %s",
                       status, details.get("error_code"), provider_text or e)
        if 400 <= status < 500 and provider_text:
            raise ValueError(resolve_msg(MSG.REGISTER_FAILED_REASON, reason=provider_text))
        raise ValueError(MSG.REGISTER_FAILED_RETRY)

    user_id = auth_result.get("user", {}).get("id") or auth_result.get("id")
    if not user_id:
        raise ValueError(MSG.REGISTER_NO_USER_ID)

    referral_code = _generate_referral_code(full_name)
    referred_by_user_id = None
    referrer_campus_id = None

    if referred_by_code:
        try:
            referrers = (
                db.table("profiles")
                .select("id,campus_id")
                .eq("referral_code", referred_by_code.upper())
                .execute()
            )
            if referrers and len(referrers) > 0:
                referred_by_user_id = referrers[0]["id"]
                referrer_campus_id = referrers[0].get("campus_id")
        except Exception as e:
            logger.error("register: referrer lookup failed for code %s: %s", referred_by_code, e)

    profile_data = {
        "id": user_id,
        "email": email,
        "full_name": full_name,
        "phone": phone,
        "date_of_birth": date_of_birth,
        "role": "student",
        "referral_code": referral_code,
        "referred_by": referred_by_user_id,
        "is_active": True,
        "email_notifications": True,
        "push_enabled": False,
        "hp_balance": 0,
        "wallet_balance": 0,
        "preferences": {},
        "campus_id": campus_id,
    }
    if nickname:
        profile_data["nickname"] = nickname
    if dept_name:
        profile_data["department"] = dept_name
        if dept_id:
            profile_data["department_id"] = dept_id
            profile_data["faculty"] = dept_faculty
    if level_value:
        profile_data["academic_level"] = level_value

    try:
        existing_profile = db.table("profiles").select("id").eq("id", user_id).execute()
        if not (existing_profile and len(existing_profile) > 0):
            db.table("profiles").insert(profile_data)
        else:
            # Profile created by Supabase trigger — patch referral/personal fields
            patch = {
                "full_name": full_name,
                "referral_code": referral_code,
            }
            if campus_id:
                patch["campus_id"] = campus_id
            if referred_by_user_id:
                patch["referred_by"] = referred_by_user_id
            if phone:
                patch["phone"] = phone
            if date_of_birth:
                patch["date_of_birth"] = date_of_birth
            if nickname:
                patch["nickname"] = nickname
            if dept_name:
                patch["department"] = dept_name
                if dept_id:
                    patch["department_id"] = dept_id
                    patch["faculty"] = dept_faculty
            if level_value:
                patch["academic_level"] = level_value
            try:
                db.table("profiles").eq("id", user_id).update(patch)
            except SupabaseError as e:
                # B5: never swallow silently — a lost patch means no campus / phone / DOB / referral link.
                logger.error("register: profile patch failed for user %s: %s", user_id, e)
    except SupabaseError:
        raise ValueError(MSG.REGISTER_FAILED_RETRY)

    if referred_by_user_id:
        try:
            db.table("referrals").insert({
                "referrer_id": referred_by_user_id,
                "referred_user_id": user_id,
                "hp_awarded": 0,
                "campus_id": campus_id,  # B7: analytics filter referrals by campus_id
            })
        except SupabaseError as e:
            logger.error("register: referral row insert failed for user %s (referrer %s): %s", user_id, referred_by_user_id, e)

        # Notify referrer that someone signed up with their code
        try:
            send_notification(
                user_id=referred_by_user_id,
                notif_type="referral_signup",
                template_data={},
                campus_id=referrer_campus_id,
            )
        except Exception as e:
            logger.error("register: referral signup notification failed for referrer %s: %s", referred_by_user_id, e)

    try:
        hp_service.award_signup_bonus(user_id)
    except Exception as e:
        logger.error("register: award_signup_bonus failed for user %s: %s", user_id, e)

    try:
        newly_linked_orders = (
            db.table("orders")
            .select("id,user_id,status,subtotal,is_squad_order,squad_id,campus_id")
            .eq("user_id", user_id)
            .eq("status", "delivered")
            .is_("hp_credited_at", "null")
            .execute()
        ) or []
        if newly_linked_orders:
            from app.services.order_service import _handle_delivery_rewards
            for o in newly_linked_orders:
                try:
                    _handle_delivery_rewards(o)
                except Exception as e:
                    logger.warning("register: retroactive HP credit failed for order %s: %s", o["id"], e)
    except Exception as e:
        logger.warning("register: retroactive guest-order HP backfill failed for %s: %s", email, e)

    try:
        db.table("squad_roster").eq("email", email).update({"user_id": user_id}).execute()
        pending = db.table("pending_squad_hp").select("id,order_id,hp_amount,campus_id").eq("email", email).eq("status", "pending").execute() or []
        if pending:
            from app.services.hp_service import award_active_hp
            for p in pending:
                try:
                    award_active_hp(
                        user_id=user_id, amount=p["hp_amount"], source_type="squad_split_claimed",
                        # B8: a reference makes the award idempotent (unique index + RPC replay check
                        # both require reference_type AND reference_id to be non-null).
                        reference_type="squad_split_claimed", reference_id=p["order_id"],
                        notes=f"Squad HP claimed from order {p['order_id'][:8]}",
                        apply_multiplier=False,
                        campus_id=p.get("campus_id") or campus_id,
                    )
                    db.table("pending_squad_hp").eq("id", p["id"]).update({"status": "claimed"}).execute()
                    send_notification(user_id=user_id, notif_type="squad_hp_share", template_data={"hp": p["hp_amount"]}, campus_id=p.get("campus_id") or campus_id)
                except Exception as e:
                    logger.error("register: squad HP claim failed for user %s, pending row %s: %s", user_id, p.get("id"), e)
        db.table("squad_members").eq("email", email).update({"user_id": user_id, "is_registered": True}).execute()
    except Exception as e:
        logger.warning("register: squad backfill failed for %s: %s", email, e)

    return auth_result


def login(email: str, password: str) -> dict:
    db = get_db()
    result = db.auth_sign_in(email, password)
    if "error" in result:
        raise ValueError(result.get("error_description", "Login failed"))
    return result


def refresh_token(refresh_token: str) -> dict:
    db = get_db()
    try:
        result = db.auth_refresh(refresh_token)
    except SupabaseError as e:
        if (getattr(e, "status_code", 500) or 500) >= 500:
            raise            # provider-side failure, not the caller's token: let the app's SupabaseError handler answer it
        logger.info("refresh_token: refresh rejected by provider (status %s)", getattr(e, "status_code", None))
        raise ValueError(MSG.SESSION_INVALID)
    if "error" in result:
        raise ValueError(result.get("error_description", "Token refresh failed"))
    return result


def get_current_user(access_token: str) -> dict:
    db = get_user_client()

    auth_user = db.auth_get_user(access_token)
    user_id = auth_user.get("id")

    if not user_id:
        raise ValueError("Could not retrieve user")

    profile = (
        db.table("profiles")
        .select("*")
        .eq("id", user_id)
        .single()
        .execute()
    )

    wallet = (
        db.table("wallets")
        .select("balance,currency")
        .eq("user_id", user_id)
        .single()
        .execute()
    )

    _profile = profile or {}
    for _internal in ("is_fraud_flagged", "jwt_version", "deactivation_reason", "deactivated_by"):
        _profile.pop(_internal, None)        # [B-06] internal columns are never sent to the client
    return {
        "id": user_id,
        "email": auth_user.get("email"),
        # Top-level aliases so mobile clients don't need to dig into profile{}
        "full_name": _profile.get("full_name"),
        "role": _profile.get("role"),
        "referral_code": _profile.get("referral_code"),
        "profile": profile,
        "wallet": {
            "balance": float(wallet.get("balance", 0)) if wallet else 0.0,
            "currency": wallet.get("currency", "NGN") if wallet else "NGN",
        },
        "tier": _get_tier(user_id),
    }


def update_profile(user_id: str, data: dict) -> dict:
    db = get_user_client()
    config = current_app.config
    allowed = {"full_name", "phone", "date_of_birth", "nickname", "leaderboard_show_full_name",
               "push_enabled", "email_notifications", "department", "academic_level"}
    update_data = {k: v for k, v in data.items() if k in allowed}
    if not update_data:
        raise ValueError(MSG.NO_VALID_FIELDS_TO_UPDATE)

    for k in ("full_name", "phone", "date_of_birth", "nickname", "department", "academic_level"):
        if k in update_data and update_data[k] is not None and not isinstance(update_data[k], str):
            raise ValueError(MSG.AUTH_FIELD_INVALID.format(field=k))
    for k in ("push_enabled", "email_notifications", "leaderboard_show_full_name"):
        if k in update_data and not isinstance(update_data[k], bool):
            raise ValueError(MSG.AUTH_FIELD_INVALID.format(field=k))
    if "full_name" in update_data and not (update_data["full_name"] or "").strip():
        raise ValueError(MSG.AUTH_FIELD_REQUIRED.format(field="full_name"))

    if "nickname" in update_data:
        nickname = (update_data["nickname"] or "").strip()
        if nickname == "":
            update_data["nickname"] = None
        elif not re.match(r"^[A-Za-z0-9_ ]{2,20}$", nickname):
            raise ValueError(MSG.NICKNAME_INVALID)
        else:
            update_data["nickname"] = nickname

    if update_data.get("phone"):
        if not re.match(config.get("PHONE_REGEX_PATTERN", r"^\+234[0-9]{10}$"), update_data["phone"]):
            raise ValueError(MSG.PHONE_FORMAT_INVALID)

    if update_data.get("date_of_birth"):
        try:
            dob = date.fromisoformat(str(update_data["date_of_birth"])[:10])
        except ValueError:
            raise ValueError(MSG.DOB_FORMAT_INVALID)
        today = today_wat()
        age = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
        minimum_age = config.get("MINIMUM_AGE", 16)
        if age < minimum_age:
            raise ValueError(resolve_msg(MSG.REGISTER_MIN_AGE, minimum_age=minimum_age))

    # [D19 B-17] resolve level / department for the student's own campus (campus_id NULL rows are shared by all).
    # A value that is UNCHANGED is not re-validated, so a student whose level or department was later deactivated
    # can still save their other profile fields.
    if "academic_level" in update_data or "department" in update_data:
        current = db.table("profiles").select("campus_id,academic_level,department").eq("id", user_id).single().execute() or {}
        campus_id = current.get("campus_id")

        if "academic_level" in update_data:
            new_level = (update_data["academic_level"] or "").strip() or None
            if new_level and new_level != current.get("academic_level"):
                level_row = resolve_level(db, new_level, campus_id)
                if not level_row:
                    raise ValueError(resolve_msg(MSG.ACADEMIC_LEVEL_INVALID, level=new_level))
                new_level = level_row["value"]
            update_data["academic_level"] = new_level

        if "department" in update_data:                  # dropdown-fed: a NEW unknown value is rejected
            dept_name = (update_data["department"] or "").strip()
            if dept_name:
                dept_row = resolve_department(db, dept_name, campus_id)
                if dept_row:
                    update_data.update({"department": dept_row.get("name") or dept_name,
                                        "department_id": dept_row["id"], "faculty": dept_row.get("faculty")})
                elif dept_name != (current.get("department") or ""):
                    raise ValueError(MSG.DEPARTMENT_INVALID)
                else:
                    update_data["department"] = dept_name   # re-saving the current (now hidden) department: leave derived columns alone
            else:                                        # clearing the department clears the derived columns too
                update_data.update({"department": None, "department_id": None, "faculty": None})

    update_data["updated_at"] = datetime.now(timezone.utc).isoformat()
    updated = db.table("profiles").eq("id", user_id).update(update_data).execute()
    if not updated:
        raise ValueError(MSG.AUTH_USER_NOT_FOUND)         # 0 rows changed (RLS / deactivated) — was an IndexError
    return updated[0] if isinstance(updated, list) else updated


def logout(access_token: str) -> bool:
    return get_user_client().auth_sign_out(access_token)      # local scope (this device only); db.auth_sign_out returns a bool


def resend_verification_email(email: str) -> dict:
    """Always returns the same vague success message (no account discovery); provider errors are logged."""
    db = get_db()
    try:
        db.auth_resend_email(
            email.strip().lower(),
            email_type="signup",
            redirect_to=_redirect_url("AUTH_VERIFY_REDIRECT_PATH", "/login"),
        )
    except Exception as e:
        logger.warning("resend_verification_email: provider error: %s", e)
    return {"message": MSG.AUTH_VERIFY_EMAIL_SENT}


def reset_password_request(email: str) -> dict:
    db = get_db()
    try:
        db.auth_reset_password(
            email.strip().lower(),
            redirect_to=_redirect_url("AUTH_RESET_REDIRECT_PATH", "/reset-password"),
        )
    except Exception as e:
        logger.warning("reset_password_request: provider error: %s", e)
    return {"message": MSG.PASSWORD_RESET_SENT}


def _generate_referral_code(full_name: str) -> str:
    prefix = "".join(c for c in full_name.upper() if c.isalpha())[:3].ljust(3, "X")
    suffix = str(uuid.uuid4())[:5].upper()
    return f"{prefix}{suffix}"


def _get_tier(user_id: str) -> dict | None:
    db = get_user_client()
    try:
        profile_rows = (
            db.table("profiles")
            .select("current_tier_id,tier_grace_ends_at")
            .eq("id", user_id)
            .execute()
        )
        if not profile_rows:
            return None
        profile = profile_rows[0]
        tier_id = profile.get("current_tier_id")
        if not tier_id:
            return None
        tier_rows = db.table("hp_tiers").select("*").eq("id", tier_id).execute()
        tier = tier_rows[0] if tier_rows else None
        if not tier:
            return None
        from datetime import datetime, timezone
        grace_ends = profile.get("tier_grace_ends_at")
        is_in_grace = bool(grace_ends and grace_ends > datetime.now(timezone.utc).isoformat())
        return {**tier, "is_in_grace_period": is_in_grace, "grace_period_ends_at": grace_ends}
    except Exception as e:
        logger.warning("get_current_user: tier lookup failed for %s: %s", user_id, e)     # [B-06] was silent
        return None
