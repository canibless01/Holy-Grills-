"""
Payment Service — Paystack integration for card payments and bank transfer (virtual accounts).
All payment confirmation is webhook-driven. Never trust client-side payment success.
"""

import hashlib
import hmac
import json
import requests as http_requests
from flask import current_app
from app.utils.retry import with_retry
from app.utils.logger import get_logger

import os

logger = get_logger(__name__)
PAYSTACK_BASE = os.environ.get("PAYSTACK_BASE_URL", "https://api.paystack.co")


def _paystack_headers() -> dict:
    return {
        "Authorization": f"Bearer {current_app.config['PAYSTACK_SECRET_KEY']}",
        "Content-Type": "application/json",
    }


@with_retry(max_attempts=3, backoff=0.5)
def _paystack_post(url: str, headers: dict, payload: dict) -> "http_requests.Response":
    return http_requests.post(url, headers=headers, json=payload, timeout=15)


@with_retry(max_attempts=3, backoff=0.5)
def _paystack_get(url: str, headers: dict) -> "http_requests.Response":
    return http_requests.get(url, headers=headers, timeout=15)


def initialize_payment(email: str, amount_naira: float, reference: str, metadata: dict = None, callback_url: str = None) -> dict:
    """
    Initialize a Paystack card payment. Returns authorization_url for redirect.
    amount_naira is in naira — converted to kobo for Paystack.
    """
    payload = {
        "email": email,
        "amount": int(amount_naira * 100),
        "reference": reference,
        "metadata": metadata or {},
    }
    if callback_url:
        payload["callback_url"] = callback_url

    resp = _paystack_post(
        f"{PAYSTACK_BASE}/transaction/initialize",
        headers=_paystack_headers(),
        payload=payload,
    )
    data = resp.json()
    if not data.get("status"):
        raise ValueError(data.get("message", "Paystack initialization failed"))

    return data["data"]


def verify_payment(reference: str) -> dict:
    """
    Verify a Paystack transaction by reference. Returns transaction data.
    """
    resp = _paystack_get(
        f"{PAYSTACK_BASE}/transaction/verify/{reference}",
        headers=_paystack_headers(),
    )
    data = resp.json()
    if not data.get("status"):
        raise ValueError(data.get("message", "Payment verification failed"))
    return data["data"]


def create_virtual_account(user_id: str, email: str, full_name: str, phone: str = None) -> dict:
    """
    Create a dedicated virtual account for a user (Paystack Dedicated NUBAN).
    """
    payload = {
        "email": email,
        "first_name": full_name.split()[0] if full_name else "User",
        "last_name": " ".join(full_name.split()[1:]) if len(full_name.split()) > 1 else "",
        "phone": phone or "",
        "preferred_bank": current_app.config.get("PAYSTACK_PREFERRED_BANK", "wema-bank"),
        "country": "NG",
    }
    customer_resp = _paystack_post(
        f"{PAYSTACK_BASE}/customer",
        headers=_paystack_headers(),
        payload=payload,
    )
    customer_data = customer_resp.json()
    if not customer_data.get("status"):
        raise ValueError(customer_data.get("message", "Failed to create Paystack customer"))

    customer_code = customer_data["data"]["customer_code"]

    dva_resp = _paystack_post(
        f"{PAYSTACK_BASE}/dedicated_account",
        headers=_paystack_headers(),
        payload={
            "customer": customer_code,
            "preferred_bank": current_app.config.get("PAYSTACK_PREFERRED_BANK", "wema-bank"),
        },
    )
    dva_data = dva_resp.json()
    if not dva_data.get("status"):
        raise ValueError(dva_data.get("message", "Failed to create dedicated account"))

    account = dva_data["data"]["dedicated_account"]
    return {
        "account_number": account["account_number"],
        "bank_name": account["bank"]["name"],
        "account_name": account["account_name"],
        "reference": account.get("id"),
    }


def verify_webhook_signature(payload_bytes: bytes, signature: str) -> bool:
    """
    Verify Paystack webhook HMAC-SHA512 signature.
    """
    secret = current_app.config["PAYSTACK_WEBHOOK_SECRET"].encode()
    computed = hmac.new(secret, payload_bytes, hashlib.sha512).hexdigest()
    return hmac.compare_digest(computed, signature)
