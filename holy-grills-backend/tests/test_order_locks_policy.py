import unittest
from datetime import date, timedelta, datetime, timezone

WAT_OFFSET = timedelta(hours=1)

def today_wat() -> date:
    return (datetime.now(timezone.utc) + WAT_OFFSET).date()

def validate_lock_date(locked_date: date):
    today = today_wat()
    tomorrow = today + timedelta(days=1)
    max_date = today + timedelta(days=7)
    if locked_date < tomorrow:
        return False
    if locked_date > max_date:
        return False
    return True


class TestOrderLockPolicy(unittest.TestCase):
    def test_same_day_disallowed(self):
        today = today_wat()
        self.assertFalse(validate_lock_date(today))

    def test_yesterday_disallowed(self):
        today = today_wat()
        yesterday = today - timedelta(days=1)
        self.assertFalse(validate_lock_date(yesterday))

    def test_tomorrow_allowed(self):
        today = today_wat()
        tomorrow = today + timedelta(days=1)
        self.assertTrue(validate_lock_date(tomorrow))

    def test_day_plus_7_allowed(self):
        today = today_wat()
        day7 = today + timedelta(days=7)
        self.assertTrue(validate_lock_date(day7))

    def test_day_plus_8_disallowed(self):
        today = today_wat()
        day8 = today + timedelta(days=8)
        self.assertFalse(validate_lock_date(day8))

    def test_future_far_disallowed(self):
        today = today_wat()
        far = today + timedelta(days=30)
        self.assertFalse(validate_lock_date(far))

    def test_boundaries_inclusive(self):
        today = today_wat()
        for i in range(1, 8):
            d = today + timedelta(days=i)
            self.assertTrue(validate_lock_date(d), f"day+{i} should be allowed")

    def test_reschedule_same_policy(self):
        # Reschedule uses same validation
        today = today_wat()
        self.assertFalse(validate_lock_date(today))
        self.assertTrue(validate_lock_date(today + timedelta(days=3)))


if __name__ == "__main__":
    unittest.main()
