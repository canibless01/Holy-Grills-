"""Every outgoing email must pass through the counted router.

The daily counter is only trustworthy if *nothing* bypasses it. This file holds the
two invariants that make that true, plus a burst simulation of the case that
motivated the counter: a hundred-odd guest registrations in one afternoon.

Invariant 1 — one transport layer:
    `app/utils/email.py:_email_attempt` is the only code that talks to Resend or to
    OneSignal's email endpoint, and `send_email_routed` is its only caller. So every
    send in the app (orders, guest orders, marketplace, event QR/confirmations,
    newsletters, campaigns, admin mail, catering) is counted exactly once.

Invariant 2 — no side door:
    No other module posts to api.resend.com, so a future feature cannot quietly send
    a hundred uncounted emails and leave the counter short.
"""
import ast
import os
import pathlib
import unittest
from unittest.mock import MagicMock, patch

from app.services import email_usage
from app.utils import email

APP_DIR = pathlib.Path(__file__).resolve().parents[1] / "app"

# Modules allowed to reach a mail provider's HTTP API directly, with the reason.
_ALLOWED_PROVIDER_CALLS = {
    # The single transport funnel for BOTH providers.
    ("utils/email.py", "_email_attempt"),
    # OneSignal email *subscription* bookkeeping, not sending.
    ("services/onesignal_email.py", "_ensure_user"),
    ("services/onesignal_email.py", "ensure_email_subscription"),
}


def _python_files():
    for path in sorted(APP_DIR.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        yield path.relative_to(APP_DIR).as_posix(), path


def _enclosing_functions(tree):
    """Map every Call node to the name of the function that contains it."""
    owners = {}
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for child in ast.walk(node):
                if isinstance(child, ast.Call):
                    owners.setdefault(child, node.name)
    return owners


class TransportFunnelTests(unittest.TestCase):
    def test_only_the_router_calls_the_transport_layer(self):
        callers = []
        for rel, path in _python_files():
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Call):
                    name = getattr(node.func, "id", None) or getattr(node.func, "attr", None)
                    if name == "_email_attempt":
                        callers.append(rel)
        self.assertEqual(callers, ["utils/email.py"],
                         f"email transport reached from {callers} — those sends are uncounted")

    def test_the_transport_is_reachable_only_through_the_router(self):
        source = (APP_DIR / "utils" / "email.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        callers = {}
        for node, owner in _enclosing_functions(tree).items():
            name = getattr(node.func, "id", None) or getattr(node.func, "attr", None)
            callers.setdefault(name, set()).add(owner)
        # _email_attempt is wrapped by _attempt_and_settle (which keeps or gives back
        # the reserved slot), and _attempt_and_settle is used only by the router.
        self.assertEqual(callers["_email_attempt"], {"_attempt_and_settle"})
        self.assertEqual(callers["_attempt_and_settle"], {"send_email_routed"})

    def test_no_module_outside_the_funnel_posts_to_resend(self):
        offenders = []
        for rel, path in _python_files():
            text = path.read_text(encoding="utf-8")
            if "api.resend.com" in text or "RESEND_BASE" in text:
                if rel != "utils/email.py":
                    offenders.append(rel)
        self.assertEqual(offenders, [], f"{offenders} can send email without being counted")


class EntryPointTests(unittest.TestCase):
    """The real callers all land in the counted router."""

    def test_guest_order_and_event_confirmations_use_the_router(self):
        from app.utils import email as email_utils
        with patch.object(email_utils, "send_email_routed", return_value=True) as routed:
            email_utils.send_email_raw("guest@example.invalid", "Guest", "Confirmed", "<p>ok</p>")
        routed.assert_called_once()
        # No explicit provider: the router resolves the configured default (OneSignal
        # when it is set up, else Resend), so the caller cannot pin a transport.
        self.assertIsNone(routed.call_args.kwargs["provider"])

    def test_notification_dispatch_uses_the_router(self):
        from app.services import notification_service as notifications
        with patch.object(email, "get_user_email_and_name", return_value=("a@example.invalid", "A")), \
             patch.object(notifications, "get_email_provider", return_value="resend"), \
             patch.object(email, "send_email_routed", return_value=True) as routed, \
             patch.object(notifications, "_record_delivery"):
            notifications._dispatch_email_async("u1", "Subject", "Body", "notif-1")
        routed.assert_called_once()

    def test_every_counted_send_reserves_exactly_one_slot(self):
        with patch.object(email, "_email_attempt", return_value=(True, False, False)), \
             patch.object(email_usage, "reserve", return_value=1) as reserve:
            email.send_email_routed("a@example.invalid", "A", "S", "<p>b</p>")
        reserve.assert_called_once_with("resend")


class BurstTests(unittest.TestCase):
    """The scenario the counter exists for: more mail than the free plan allows."""

    def test_a_hundred_and_fifty_sends_switch_provider_at_the_limit(self):
        counts = {"resend": 0, "onesignal": 0}

        def reserve(provider):
            counts[provider] += 1
            return counts[provider]

        def release(provider):
            # Mirrors hg_release_email_send: an over-limit claim is handed straight back.
            counts[provider] = max(0, counts[provider] - 1)

        delivered = []

        def attempt(provider, *args, **kwargs):
            delivered.append(provider)
            receipt = kwargs.get("receipt")
            if isinstance(receipt, dict):
                receipt.update({"state": "accepted"})
            return True, False, False

        with patch.dict(os.environ, {"EMAIL_DAILY_LIMIT_RESEND": "100", "EMAIL_DAILY_LIMIT_ONESIGNAL": "0"}), \
             patch.object(email_usage, "reserve", side_effect=reserve), \
             patch.object(email_usage, "release", side_effect=release) as release_mock, \
             patch.object(email, "_email_attempt", side_effect=attempt):
            for n in range(150):
                email.send_email_routed(f"guest{n}@example.invalid", "Guest",
                                        "Your event QR code", "<p>qr</p>", provider="resend")

        self.assertEqual(len(delivered), 150)                       # nothing was dropped
        self.assertEqual(delivered.count("resend"), 100)            # exactly the free allowance
        self.assertEqual(delivered.count("onesignal"), 50)          # the rest went out anyway
        self.assertEqual(counts, {"resend": 100, "onesignal": 50})  # and it is all recorded
        # Only the over-limit claims were handed back; every kept claim became a send.
        self.assertEqual(release_mock.call_count, 50)

    def test_a_rejected_send_gives_its_slot_back(self):
        with patch.object(email_usage, "reserve", return_value=7), \
             patch.object(email_usage, "release") as release, \
             patch.object(email, "_email_attempt", return_value=(False, True, False)):
            email.send_email_routed("a@example.invalid", "A", "S", "<p>b</p>")
        # Both attempts refused for quota, so both claims are handed back: nothing
        # was sent and neither provider should look used up.
        self.assertEqual([c.args[0] for c in release.call_args_list], ["resend", "onesignal"])


if __name__ == "__main__":
    unittest.main()
