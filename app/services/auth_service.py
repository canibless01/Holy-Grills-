"""
Auth Service — wraps Supabase Auth for email/password and Google OAuth.
Profile is created automatically via Supabase trigger on auth.users insert.
"""

import uuid
from datetime import datetime, timezone
from app.db import get_db, SupabaseError
from app.services.notification_service import send_notification


def register(email: str, password: str, full_name: str, phone: str = None, date_of_birth: str = None, referred_by_code: str = None) -> dict:
    """
    Create a Supabase Auth user and profile.
    Returns Supabase auth session (access_token, refresh_token, user).
    """
    db = get_db()

    # ✅ STEP 1: Check if user already exists in profiles
    existing = db.table("profiles").select("id").eq("email", email).execute()
    if existing and len(existing) > 0:
        raise ValueError("Account already registered. Please login instead.")

    # ✅ STEP 2: Check if user exists in auth (orphan cleanup)
    try:
        # Try to find user in auth
        auth_users = db.table("auth.users").select("id").eq("email", email).execute()
        if auth_users and len(auth_users) > 0:
            # User exists in auth but not in profiles — raise clear error
            raise ValueError("Account exists but is incomplete. Please contact support.")
    except Exception:
        # Table might not be accessible — skip this check
        pass

    # ✅ STEP 3: Create Auth user
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

    # ✅ STEP 4: Generate referral code
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

    # ✅ STEP 5: Create profile
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
    }

    try:
        db.table("profiles").insert(profile_data)
    except SupabaseError as e:
        # Profile creation failed — Auth user is orphaned
        # Log for admin to handle
        print(f"⚠️ ORPHANED USER CREATED: {user_id} - {email} - Error: {e}")
        raise ValueError("Registration failed. Please try again.")

    # ✅ STEP 6: Create wallet
    try:
        db.table("wallets").insert({
            "user_id": user_id,
            "balance": 0,
            "currency": "NGN",
        })
    except SupabaseError as e:
        # Wallet may already exist — log and continue
        print(f"⚠️ Wallet creation warning: {e}")

    # ✅ STEP 7: Create referral record
    if referred_by_user_id:
        try:
            db.table("referrals").insert({
                "referrer_id": referred_by_user_id,
                "referred_user_id": user_id,
                "hp_awarded": 0,
            })
        except SupabaseError as e:
            # Referral may already exist — log and continue
            print(f"⚠️ Referral creation warning: {e}")

    return auth_result

def login(email: str, password: str) -> dict:
    db = get_db()
    result = db.auth_sign_in(email, password)
    if "error" in result:
        raise ValueError(result.get("error_description", "Login failed"))
    return result


def refresh_token(refresh_token: str) -> dict:
    db = get_db()
    result = db.auth_refresh(refresh_token)
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
        .select("balance,virtual_account_number,virtual_account_bank")
        .eq("user_id", user_id)
        .single()
        .execute()
    )
    tier_info = _get_tier(user_id)

    return {
        "id": user_id,
        "email": auth_user.get("email"),
        "profile": profile,
        "wallet_balance": float(wallet.get("balance", 0)) if wallet else 0.0,
        "virtual_account": {
            "number": wallet.get("virtual_account_number") if wallet else None,
            "bank": wallet.get("virtual_account_bank") if wallet else None,
        },
        "tier": tier_info,
    }


def update_profile(user_id: str, data: dict) -> dict:
    db = get_db()
    allowed = {"full_name", "phone", "date_of_birth", "push_enabled", "push_subscription", "email_notifications"}
    update_data = {k: v for k, v in data.items() if k in allowed}
    if not update_data:
        raise ValueError("No valid fields to update")

    update_data["updated_at"] = datetime.now(timezone.utc).isoformat()
    updated = db.table("profiles").eq("id", user_id).update(update_data)
    return updated[0] if isinstance(updated, list) else updated


def logout(access_token: str) -> None:
    get_db().auth_sign_out(access_token)


def reset_password_request(email: str) -> dict:
    db = get_db()
    db.auth_reset_password(email)
    return {"message": "Password reset email sent if account exists"}


def _generate_referral_code(full_name: str) -> str:
    prefix = "".join(c for c in full_name.upper() if c.isalpha())[:3].ljust(3, "X")
    suffix = str(uuid.uuid4())[:5].upper()
    return f"{prefix}{suffix}"


def _get_tier(user_id: str) -> dict | None:
    db = get_db()
    try:
        user_tier = (
            db.table("user_tiers")
            .select("tier_id,is_current,is_in_grace_period,grace_period_ends_at")
            .eq("user_id", user_id)
            .eq("is_current", "true")
            .single()
            .execute()
        )
        if not user_tier:
            return None
        tier = db.table("tiers").select("*").eq("id", user_tier["tier_id"]).single().execute()
        return {**tier, "is_in_grace_period": user_tier.get("is_in_grace_period", False)}
    except Exception:
        return None
