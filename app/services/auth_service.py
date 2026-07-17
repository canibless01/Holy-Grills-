"""
Auth Service — wraps Supabase Auth for email/password and Google OAuth.
Profile is created automatically via Supabase trigger on auth.users insert.
"""

import uuid
import re
from datetime import datetime, timezone, date
from flask import current_app
from app.db import get_db, SupabaseError
from app.services.notification_service import send_notification
from app.services import hp_service


def register(email: str, password: str, full_name: str, phone: str = None, date_of_birth: str = None, referred_by_code: str = None, department: str = None, academic_level: str = None) -> dict:
    """
    Create a Supabase Auth user and profile.
    Returns Supabase auth session (access_token, refresh_token, user).
    """
    db = get_db()
    config = current_app.config

    # Phone validation
    if phone:
        phone_pattern = config.get("PHONE_REGEX_PATTERN", r"^\+234[0-9]{10}$")
        if not re.match(phone_pattern, phone):
            raise ValueError("Invalid phone number format. Use international format e.g. +2348012345678.")

    # DOB validation — user must meet minimum age
    if date_of_birth:
        try:
            dob = date.fromisoformat(str(date_of_birth)[:10])
            today = date.today()
            age = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
            minimum_age = config.get("MINIMUM_AGE", 16)
            if age < minimum_age:
                raise ValueError(f"You must be at least {minimum_age} years old to register.")
        except ValueError as e:
            if "must be at least" in str(e):
                raise
            raise ValueError("Invalid date of birth. Use YYYY-MM-DD format.")

    existing = db.table("profiles").select("id").eq("email", email).execute()
    if existing and len(existing) > 0:
        raise ValueError("Account already registered. Please login instead.")

    try:
        auth_result = db.auth_sign_up(
            email=email,
            password=password,
            user_metadata={"full_name": full_name},
        )
    except SupabaseError as e:
        error_msg = str(e).lower()
        if "user already registered" in error_msg or "duplicate" in error_msg:
            raise ValueError("Account already exists. Please login.")
        raise ValueError(f"Registration failed: {error_msg}")

    user_id = auth_result.get("user", {}).get("id") or auth_result.get("id")
    if not user_id:
        raise ValueError("Registration failed: no user ID returned")

    referral_code = _generate_referral_code(full_name)
    referred_by_user_id = None

    if referred_by_code:
        try:
            referrers = (
                db.table("profiles")
                .select("id")
                .eq("referral_code", referred_by_code.upper())
                .execute()
            )
            if referrers and len(referrers) > 0:
                referred_by_user_id = referrers[0]["id"]
        except Exception:
            pass

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
    }
    # Populate department / level if provided at sign-up (RUN 9)
    if department:
        profile_data["department"] = department.strip()
    if academic_level:
        profile_data["academic_level"] = str(academic_level).strip()

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
            if referred_by_user_id:
                patch["referred_by"] = referred_by_user_id
            if phone:
                patch["phone"] = phone
            if date_of_birth:
                patch["date_of_birth"] = date_of_birth
            # Always persist department/level on the trigger path too (RUN 9)
            if department:
                patch["department"] = department.strip()
            if academic_level:
                patch["academic_level"] = str(academic_level).strip()
            try:
                db.table("profiles").eq("id", user_id).update(patch)
            except SupabaseError:
                pass
    except SupabaseError:
        raise ValueError("Registration failed. Please try again.")

    try:
        db.table("wallets").insert({
            "user_id": user_id,
            "balance": 0,
            "currency": "NGN",
        })
    except SupabaseError:
        pass

    if referred_by_user_id:
        try:
            db.table("referrals").insert({
                "referrer_id": referred_by_user_id,
                "referred_user_id": user_id,
                "hp_awarded": 0,
            })
        except SupabaseError:
            pass

        # Notify referrer that someone signed up with their code
        try:
            from app.messages import MSG
            send_notification(
                user_id=referred_by_user_id,
                notif_type="referral_signup",
                template_data={},
            )
        except Exception:
            pass

    try:
        hp_service.award_signup_bonus(user_id)
    except Exception:
        pass

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
        raise ValueError(str(e))
    if "error" in result:
        raise ValueError(result.get("error_description", "Token refresh failed"))
    return result


def get_current_user(access_token: str) -> dict:
    db = get_db()

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
    db = get_db()
    # department, academic_level, faculty are live columns on profiles (confirmed against DB).
    # faculty is derived from department mapping but can also be set directly here.
    allowed = {
        "full_name", "phone", "date_of_birth",
        "push_enabled", "push_subscription", "email_notifications",
        "department", "academic_level", "faculty",
    }
    update_data = {k: v for k, v in data.items() if k in allowed}
    if not update_data:
        raise ValueError("No valid fields to update")

    update_data["updated_at"] = datetime.now(timezone.utc).isoformat()
    updated = db.table("profiles").eq("id", user_id).update(update_data)
    return updated[0] if isinstance(updated, list) else updated


def logout(access_token: str) -> None:
    get_db().auth_sign_out(access_token)


def resend_verification_email(email: str) -> dict:
    """
    Ask Supabase to resend the email confirmation link for an unconfirmed address.
    Always returns a vague success message regardless of whether the email exists
    or is already confirmed — prevents email-enumeration attacks.
    """
    db = get_db()
    try:
        db.auth_resend_email(email, email_type="signup")
    except Exception:
        pass
    from app.messages import MSG
    return {"message": MSG.AUTH_VERIFY_EMAIL_SENT}


def reset_password_request(email: str) -> dict:
    db = get_db()
    try:
        db.auth_reset_password(email)
    except Exception:
        pass
    return {"message": "If that email is registered, a password reset link has been sent"}


def _generate_referral_code(full_name: str) -> str:
    prefix = "".join(c for c in full_name.upper() if c.isalpha())[:3].ljust(3, "X")
    suffix = str(uuid.uuid4())[:5].upper()
    return f"{prefix}{suffix}"


def _get_tier(user_id: str) -> dict | None:
    db = get_db()
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
    except Exception:
        return None
