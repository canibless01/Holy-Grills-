"""
The database's settings validator (`hg_validate_system_setting`) refuses a bad
value with a sentence meant for whoever is editing it. Postgres reports that as
code P0001, which the app-wide SupabaseError handler can only turn into a generic
400/500 — so the admin screen used to toast "Something went wrong" with no clue
what was wrong with the number.

`_validator_refusal` in app/routes/admin_gifts.py is the bridge: it recognises
the validator's refusal and hands the sentence back, and returns None for
everything else so RLS denials, schema errors and network failures keep going to
the global handler untouched.

These tests pin both halves of that promise.
"""
import os
import unittest

# Importing the app package reads Config, whose class body requires the Supabase
# variables. The suite is run with them set in CI; set placeholders so this file
# also runs standalone without weakening anything (no client is constructed here).
for _key, _value in (
    ("SUPABASE_URL", "http://placeholder.test"),
    ("SUPABASE_SERVICE_ROLE_KEY", "placeholder"),
    ("SUPABASE_ANON_KEY", "placeholder"),
    ("SECRET_KEY", "placeholder"),
):
    os.environ.setdefault(_key, _value)

from app.db import SupabaseError                                    # noqa: E402
from app.messages import MSG                                        # noqa: E402
from app.routes.admin_gifts import _validator_refusal               # noqa: E402


class TestSettingValidatorSurfacing(unittest.TestCase):
    def test_raise_exception_message_is_passed_through(self):
        exc = SupabaseError(
            "flash_discount_pct must be between 0 and 1 (got 5)",
            status_code=400,
            details={"code": "P0001", "message": "flash_discount_pct must be between 0 and 1 (got 5)"},
        )
        self.assertEqual(
            _validator_refusal(exc),
            "flash_discount_pct must be between 0 and 1 (got 5)",
        )

    def test_custom_errcode_recognised_by_function_name(self):
        # A trigger may RAISE ... USING ERRCODE = something other than P0001; the
        # message/hint naming the function is the second signal.
        exc = SupabaseError(
            "hp_unlock_rate_pct must be between 0 and 1 (got 30)",
            status_code=400,
            details={"code": "22023", "message": "hp_unlock_rate_pct must be between 0 and 1 (got 30)",
                     "hint": "raised by hg_validate_system_setting"},
        )
        self.assertIsNotNone(_validator_refusal(exc))

    def test_empty_message_falls_back_to_the_catalog_text(self):
        exc = SupabaseError("", status_code=400, details={"code": "P0001", "message": ""})
        self.assertEqual(_validator_refusal(exc), MSG.SETTING_VALUE_REJECTED)

    def test_other_database_errors_are_not_surfaced(self):
        # RLS denial — must keep flowing to the global handler (403), never echoed.
        rls = SupabaseError("permission denied for table system_settings", status_code=403,
                            details={"code": "42501", "message": "permission denied for table system_settings"})
        self.assertIsNone(_validator_refusal(rls))
        # Schema drift — a missing column is an operator problem, not something to
        # print into an admin's browser.
        schema = SupabaseError("Could not find the 'value' column", status_code=400,
                               details={"code": "PGRST204", "message": "Could not find the 'value' column"})
        self.assertIsNone(_validator_refusal(schema))
        # Not our error class at all.
        self.assertIsNone(_validator_refusal(RuntimeError("boom")))


if __name__ == "__main__":
    unittest.main()
