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
    wallet = (
        db.table("wallets")
        .select("*")
        .eq("user_id", user_id)
        .single()
        .execute()
    )
    return wallet


def credit_wallet(user_id: str, amount: float, payment_reference: str, reference_id: str = None, reference_type: str = "topup", notes: str = "", provider_response: dict = None) -> dict:
    """
    Credit ₦ to wallet (e.g., after Paystack webhook confirms payment).
    Awards HP if top-up meets minimum threshold.
    """
    db = get_db()
    config = current_app.config

    result = db.rpc("credit_wallet_atomic", {
        "p_user_id": user_id,
        "p_amount": amount,
        "p_payment_reference": payment_reference,
        "p_reference_id": reference_id,
        "p_reference_type": reference_type,
        "p_notes": notes,
    })

    if amount >= config["WALLET_TOPUP_MIN"] and reference_type == "topup":
        award_active_hp(
            user_id=user_id,
            amount=config["WALLET_TOPUP_HP"],
            txn_type="earn",
            reference_id=payment_reference,
            reference_type="wallet_topup",
            notes=f"HP bonus for wallet top-up of ₦{amount:.0f}",
        )

    return result


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

    result = db.rpc("debit_wallet_atomic", {
        "p_user_id": user_id,
        "p_amount": amount,
        "p_reference_id": reference_id,
        "p_reference_type": reference_type,
        "p_notes": notes,
    })
    return result


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
