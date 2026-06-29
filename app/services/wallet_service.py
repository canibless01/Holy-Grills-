"""
Wallet Service — manages the closed-loop ₦ wallet.
No withdrawals. Fund via Paystack bank transfer or card.
"""

from datetime import datetime, timezone
from app.db import get_db, SupabaseError
from app.services.hp_service import award_active_hp
from flask import current_app


def get_wallet(user_id: str) -> dict:
    db = get_db()
    return (
        db.table("wallets")
        .select("user_id,balance,currency,created_at,updated_at")
        .eq("user_id", user_id)
        .single()
        .execute()
    )


def credit_wallet(user_id: str, amount: float, payment_reference: str, reference_id: str = None, reference_type: str = "topup", notes: str = "", provider_response: dict = None) -> dict:
    """
    Credit ₦ to wallet (e.g., after Paystack webhook confirms payment).
    Awards HP if top-up meets minimum threshold.
    """
    db = get_db()
    config = current_app.config

    wallet = get_wallet(user_id)
    if not wallet:
        raise ValueError("Wallet not found for user")

    new_balance = float(wallet.get("balance", 0)) + amount

    db.table("wallets").eq("user_id", user_id).update({
        "balance": new_balance,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    })

    txn = db.table("wallet_transactions").insert({
        "user_id": user_id,
        "type": "credit",
        "amount": amount,
        "balance_after": new_balance,
        "reason": notes or f"Wallet credit ({reference_type})",
        "reference_type": reference_type,
        "reference_id": reference_id or None,
        "provider": "paystack",
        "provider_reference": payment_reference,
        "metadata": provider_response or {},
    })

    if amount >= config.get("WALLET_TOPUP_MIN", 3000) and reference_type in ("topup", "bank_transfer"):
        try:
            award_active_hp(
                user_id=user_id,
                amount=config.get("WALLET_TOPUP_HP", 50),
                txn_type="earn_admin_grant",
                reference_id=payment_reference,
                reference_type="wallet_topup",
                notes=f"HP bonus for wallet top-up of ₦{amount:.0f}",
            )
        except Exception:
            pass

    return txn[0] if isinstance(txn, list) else txn


def debit_wallet(user_id: str, amount: float, reference_id: str, reference_type: str, notes: str = "") -> dict:
    """
    Deduct ₦ from wallet. Raises if insufficient balance.
    """
    db = get_db()
    wallet = get_wallet(user_id)
    if not wallet:
        raise ValueError("Wallet not found for user")

    balance = float(wallet.get("balance", 0))
    if balance < amount:
        raise ValueError(f"Insufficient wallet balance: have ₦{balance:.2f}, need ₦{amount:.2f}")

    new_balance = balance - amount

    db.table("wallets").eq("user_id", user_id).update({
        "balance": new_balance,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    })

    txn = db.table("wallet_transactions").insert({
        "user_id": user_id,
        "type": "debit",
        "amount": amount,
        "balance_after": new_balance,
        "reason": notes or f"Wallet debit ({reference_type})",
        "reference_type": reference_type,
        "reference_id": reference_id,
        "metadata": {},
    })

    return txn[0] if isinstance(txn, list) else txn


def get_wallet_transactions(user_id: str, limit: int = 50, offset: int = 0) -> list:
    db = get_db()
    return (
        db.table("wallet_transactions")
        .select("*")
        .eq("user_id", user_id)
        .order("created_at", ascending=False)
        .limit(limit)
        .offset(offset)
        .execute()
    )
