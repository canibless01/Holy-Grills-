"""
Wallet Service — manages the closed-loop ₦ wallet.
No withdrawals. Fund via Paystack bank transfer or card.
"""

from datetime import datetime, timezone
from app.db import get_db, get_user_client, SupabaseError
from app.services.hp_service import award_active_hp
from flask import current_app


def get_wallet(user_id: str) -> dict:
    db = get_user_client()
    return (
        db.table("wallets")
        .select("user_id,balance,currency,created_at,updated_at")
        .eq("user_id", user_id)
        .single()
        .execute()
    )


def credit_wallet(user_id: str, amount: float, payment_reference: str, reference_id: str = None, reference_type: str = "topup", notes: str = "", provider_response: dict = None, campus_id: str = None) -> dict:
    """
    Credit ₦ to wallet (e.g., after Paystack webhook confirms payment).
    Awards HP if top-up meets minimum threshold. Uses atomic database-level RPC.
    """
    if campus_id is None:
        from flask import has_app_context, g
        if has_app_context():
            campus_id = getattr(g, 'campus_id', None)
    db = get_db()
    config = current_app.config

    res = db.rpc("credit_wallet_atomic", {
        "p_user_id": user_id,
        "p_amount": amount,
        "p_reason": notes or f"Wallet credit ({reference_type})",
        "p_reference_type": reference_type,
        "p_reference_id": reference_id,
        "p_provider": "paystack",
        "p_provider_reference": payment_reference,
        "p_metadata": provider_response or {},
        "p_campus_id": campus_id,
    })

    if isinstance(res, dict) and res.get("error"):
        raise ValueError(res["error"])

    # Fetch transaction row for backward compatibility
    txn_id = res.get("transaction_id") if isinstance(res, dict) else None
    txn = None
    if txn_id:
        try:
            txn = db.table("wallet_transactions").select("*").eq("id", txn_id).single().execute()
        except Exception:
            pass

    if amount >= config.get("WALLET_TOPUP_MIN", 3000) and reference_type in ("topup", "bank_transfer"):
        try:
            award_active_hp(
                user_id=user_id,
                amount=config.get("WALLET_TOPUP_HP", 50),
                txn_type="earn",
                reference_id=payment_reference,
                reference_type="wallet_topup",
                notes=f"HP bonus for wallet top-up of ₦{amount:.0f}",
            )
        except Exception:
            pass

    return txn or {"user_id": user_id, "amount": amount, "balance_after": res.get("new_balance") if isinstance(res, dict) else amount}


def debit_wallet(user_id: str, amount: float, reference_id: str, reference_type: str, notes: str = "", campus_id: str = None) -> dict:
    """
    Deduct ₦ from wallet. Uses atomic database-level RPC.
    """
    if campus_id is None:
        from flask import has_app_context, g
        if has_app_context():
            campus_id = getattr(g, 'campus_id', None)
    db = get_db()
    res = db.rpc("debit_wallet_atomic", {
        "p_user_id": user_id,
        "p_amount": amount,
        "p_reason": notes or f"Wallet debit ({reference_type})",
        "p_reference_type": reference_type,
        "p_reference_id": reference_id,
        "p_metadata": {},
        "p_campus_id": campus_id,
    })

    if isinstance(res, dict) and res.get("error"):
        raise ValueError(res["error"])

    txn_id = res.get("transaction_id") if isinstance(res, dict) else None
    txn = None
    if txn_id:
        try:
            txn = db.table("wallet_transactions").select("*").eq("id", txn_id).single().execute()
        except Exception:
            pass

    return txn or {"user_id": user_id, "amount": amount, "balance_after": res.get("new_balance") if isinstance(res, dict) else 0.0}


def get_wallet_transactions(user_id: str, limit: int = 50, offset: int = 0, reference_type: str = None) -> list:
    db = get_user_client()
    q = db.table("wallet_transactions").select("*").eq("user_id", user_id)
    if reference_type:
        q = q.eq("reference_type", reference_type)
    return q.order("created_at", ascending=False).limit(limit).offset(offset).execute()
