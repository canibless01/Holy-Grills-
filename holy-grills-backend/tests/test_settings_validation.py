import unittest

def validate_squad_bonus_pct(value):
    try:
        iv = int(str(value))
        if iv < 0 or iv > 100:
            return False
        return True
    except (TypeError, ValueError):
        return False

def validate_hp_multiplier(value):
    try:
        if float(str(value)) not in (0.5, 1.0, 2.0):
            return False
        return True
    except (TypeError, ValueError):
        return False


class TestSettingsValidation(unittest.TestCase):
    def test_squad_bonus_valid(self):
        self.assertTrue(validate_squad_bonus_pct(0))
        self.assertTrue(validate_squad_bonus_pct(30))
        self.assertTrue(validate_squad_bonus_pct(100))
        self.assertTrue(validate_squad_bonus_pct("30"))

    def test_squad_bonus_invalid(self):
        self.assertFalse(validate_squad_bonus_pct(-1))
        self.assertFalse(validate_squad_bonus_pct(101))
        self.assertFalse(validate_squad_bonus_pct("abc"))
        self.assertFalse(validate_squad_bonus_pct(None))

    def test_hp_multiplier(self):
        self.assertTrue(validate_hp_multiplier(0.5))
        self.assertTrue(validate_hp_multiplier(1.0))
        self.assertTrue(validate_hp_multiplier(2.0))
        self.assertFalse(validate_hp_multiplier(1.5))
        self.assertFalse(validate_hp_multiplier("invalid"))


if __name__ == "__main__":
    unittest.main()
