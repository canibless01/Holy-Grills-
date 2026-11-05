"""Provider allowances are not interchangeable, so the accounting must say which is which.

Resend: 100 per **day**, resets at midnight (Africa/Lagos).
OneSignal: 10,000 per **month**, no rollover.

That asymmetry is the whole reason Resend is tried first and OneSignal absorbs the
overflow: a busy day spends an allowance tomorrow renews, instead of burning a monthly
entitlement that cannot be earned back. These tests pin both the routing preference and
the monthly figures the admin page shows.
"""
import os
import unittest
from unittest.mock import MagicMock, patch

for _name in ("SUPABASE_URL", "SUPABASE_ANON_KEY", "SUPABASE_SERVICE_ROLE_KEY", "JWT_SECRET", "SECRET_KEY"):
    os.environ.setdefault(_name, "https://example.supabase.co" if _name == "SUPABASE_URL" else "test")

from app.services import email_usage


class MonthlyLimitTests(unittest.TestCase):
    def test_defaults_match_the_plans(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("EMAIL_MONTHLY_LIMIT_RESEND", None)
            os.environ.pop("EMAIL_MONTHLY_LIMIT_ONESIGNAL", None)
            self.assertEqual(email_usage.monthly_limit("onesignal"), 10000)
            self.assertEqual(email_usage.monthly_limit("resend"), 0)   # the daily cap binds first

    def test_an_operator_can_raise_it(self):
        with patch.dict(os.environ, {"EMAIL_MONTHLY_LIMIT_ONESIGNAL": "50000"}):
            self.assertEqual(email_usage.monthly_limit("onesignal"), 50000)

    def test_a_junk_value_falls_back_instead_of_breaking(self):
        with patch.dict(os.environ, {"EMAIL_MONTHLY_LIMIT_ONESIGNAL": "lots"}):
            self.assertEqual(email_usage.monthly_limit("onesignal"), 10000)


class MonthToDateTests(unittest.TestCase):
    def _db(self, rows, today_counts=None):
        db = MagicMock()
        db.table.return_value.select.return_value.eq.return_value.gte.return_value.execute.return_value = rows
        db.rpc.return_value = today_counts or {}
        return db

    def test_the_month_total_sums_the_daily_rows(self):
        db = self._db([{"provider": "onesignal", "sent_count": 120, "usage_date": "2026-10-01"},
                       {"provider": "onesignal", "sent_count": 80, "usage_date": "2026-10-02"}])
        with patch.object(email_usage, "get_db", return_value=db):
            self.assertEqual(email_usage.sent_this_month("onesignal"), 200)

    def test_it_asks_only_for_this_month_and_this_provider(self):
        db = self._db([])
        with patch.object(email_usage, "get_db", return_value=db), \
             patch.object(email_usage, "_today", return_value=__import__("datetime").date(2026, 10, 30)):
            email_usage.sent_this_month("onesignal")
        select = db.table.return_value.select.return_value
        select.eq.assert_called_once_with("provider", "onesignal")
        select.eq.return_value.gte.assert_called_once_with("usage_date", "2026-10-01")

    def test_a_missing_table_reports_unknown_rather_than_zero(self):
        db = MagicMock()
        db.table.side_effect = RuntimeError("relation does not exist")
        with patch.object(email_usage, "get_db", return_value=db):
            self.assertIsNone(email_usage.sent_this_month("onesignal"))

    def test_health_shows_both_horizons(self):
        db = self._db([{"provider": "onesignal", "sent_count": 60, "usage_date": "2026-10-01"}],
                      today_counts={"onesignal": 12})
        with patch.object(email_usage, "get_db", return_value=db), \
             patch.object(email_usage, "sent_this_month", return_value=60), \
             patch.object(email_usage, "daily_limit", return_value=0), \
             patch.object(email_usage, "monthly_limit", return_value=10000), \
             patch("app.utils.email._resend_api_key", return_value="key"), \
             patch("app.services.notification_service._get_onesignal_creds",
                   return_value=("app", "key")):
            health = email_usage.health()
        onesignal = {p["provider"]: p for p in health["providers"]}["onesignal"]
        self.assertEqual(onesignal["sent_today"], 12)
        self.assertEqual(onesignal["sent_this_month"], 60)
        self.assertEqual(onesignal["monthly_limit"], 10000)
        self.assertEqual(onesignal["monthly_remaining"], 9940)
        self.assertFalse(onesignal["monthly_exhausted"])

    def test_an_exhausted_month_is_flagged(self):
        with patch.object(email_usage, "get_db", return_value=self._db([])), \
             patch.object(email_usage, "sent_this_month", return_value=10000), \
             patch.object(email_usage, "daily_limit", return_value=0), \
             patch.object(email_usage, "monthly_limit", return_value=10000), \
             patch("app.utils.email._resend_api_key", return_value="key"), \
             patch("app.services.notification_service._get_onesignal_creds",
                   return_value=("app", "key")):
            health = email_usage.health()
        onesignal = {p["provider"]: p for p in health["providers"]}["onesignal"]
        self.assertTrue(onesignal["monthly_exhausted"])
        self.assertEqual(onesignal["monthly_remaining"], 0)


class CapacityTests(unittest.TestCase):
    """The routing order is what makes a month's total capacity ~13,000, not 10,000."""

    def test_resend_absorbs_the_daily_quota_before_onesignal_is_touched(self):
        counts = {"resend": 0, "onesignal": 0}

        def reserve(provider):
            counts[provider] += 1
            return counts[provider]

        def release(provider):
            counts[provider] = max(0, counts[provider] - 1)

        def attempt(provider, *args, **kwargs):
            receipt = kwargs.get("receipt")
            if isinstance(receipt, dict):
                receipt.update({"state": "accepted"})
            return True, False, False

        delivered = []
        with patch.dict(os.environ, {"EMAIL_DAILY_LIMIT_RESEND": "100"}), \
             patch.object(email_usage, "reserve", side_effect=reserve), \
             patch.object(email_usage, "release", side_effect=release), \
             patch("app.utils.email._email_attempt",
                   side_effect=lambda provider, *a, **k: (delivered.append(provider), attempt(provider, *a, **k))[1]):
            from app.utils import email as email_utils
            for n in range(130):
                email_utils.send_email_routed(f"guest{n}@example.invalid", "Guest", "S", "<p>b</p>",
                                              provider="resend")

        self.assertEqual(delivered.count("resend"), 100)   # the renewable allowance, spent first
        self.assertEqual(delivered.count("onesignal"), 30)  # the monthly pool absorbs the rest
        self.assertEqual(len(delivered), 130)               # nothing dropped


if __name__ == "__main__":
    unittest.main()
