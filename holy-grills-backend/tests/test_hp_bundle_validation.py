import unittest

def validate_hp_bundle_purchase(verify_metadata, request_user_id, request_hp_amount, paid_kobo, expected_kobo):
    """
    Simulate stricter validation from B-4.
    Returns (is_valid, error)
    """
    purpose = verify_metadata.get("purpose") or verify_metadata.get("type")
    if purpose != "hp_bundle":
        return False, "Payment reference is not for HP bundle purchase"

    meta_user_id = verify_metadata.get("user_id")
    if meta_user_id and str(meta_user_id) != str(request_user_id):
        return False, "Payment reference does not belong to this user"

    meta_hp = verify_metadata.get("hp_amount")
    if meta_hp is not None:
        try:
            if int(meta_hp) != int(request_hp_amount):
                return False, f"HP amount mismatch: payment was for {meta_hp} HP, requested {request_hp_amount} HP"
        except (TypeError, ValueError):
            return False, "Invalid hp_amount in payment metadata"

    if paid_kobo != expected_kobo:
        return False, f"Payment mismatch: expected {expected_kobo}, got {paid_kobo}"

    return True, None


class TestHPBundleValidation(unittest.TestCase):
    def test_valid_bundle(self):
        meta = {"purpose": "hp_bundle", "user_id": "user123", "hp_amount": 500}
        ok, err = validate_hp_bundle_purchase(meta, "user123", 500, 250000, 250000)
        self.assertTrue(ok)

    def test_wrong_purpose_rejected(self):
        meta = {"purpose": "wallet_topup", "user_id": "user123", "hp_amount": 500}
        ok, err = validate_hp_bundle_purchase(meta, "user123", 500, 250000, 250000)
        self.assertFalse(ok)
        self.assertIn("not for HP bundle", err)

    def test_order_payment_rejected(self):
        meta = {"type": "order_payment", "user_id": "user123", "hp_amount": 500}
        ok, err = validate_hp_bundle_purchase(meta, "user123", 500, 250000, 250000)
        self.assertFalse(ok)

    def test_user_mismatch_rejected(self):
        meta = {"purpose": "hp_bundle", "user_id": "user999", "hp_amount": 500}
        ok, err = validate_hp_bundle_purchase(meta, "user123", 500, 250000, 250000)
        self.assertFalse(ok)
        self.assertIn("does not belong", err)

    def test_hp_amount_mismatch_rejected(self):
        meta = {"purpose": "hp_bundle", "user_id": "user123", "hp_amount": 100}
        ok, err = validate_hp_bundle_purchase(meta, "user123", 500, 250000, 250000)
        self.assertFalse(ok)
        self.assertIn("HP amount mismatch", err)

    def test_exact_kobo_match_required(self):
        meta = {"purpose": "hp_bundle", "user_id": "user123", "hp_amount": 500}
        # Paid less
        ok, _ = validate_hp_bundle_purchase(meta, "user123", 500, 240000, 250000)
        self.assertFalse(ok)
        # Paid more
        ok, _ = validate_hp_bundle_purchase(meta, "user123", 500, 260000, 250000)
        self.assertFalse(ok)
        # Exact
        ok, _ = validate_hp_bundle_purchase(meta, "user123", 500, 250000, 250000)
        self.assertTrue(ok)

    def test_webhook_isolation(self):
        # HP bundle ref must not be credited as wallet or order
        # Simulate webhook routing
        def route_webhook(metadata):
            purpose = metadata.get("purpose")
            ptype = metadata.get("type")
            if purpose == "hp_bundle" or ptype == "hp_bundle":
                return "hp_bundle"
            if ptype == "wallet_topup":
                return "wallet"
            if ptype == "order_payment":
                return "order"
            return "unknown"

        self.assertEqual(route_webhook({"purpose": "hp_bundle", "type": "hp_bundle"}), "hp_bundle")
        self.assertEqual(route_webhook({"type": "wallet_topup"}), "wallet")
        self.assertNotEqual(route_webhook({"purpose": "hp_bundle"}), "wallet")
        self.assertNotEqual(route_webhook({"purpose": "hp_bundle"}), "order")


if __name__ == "__main__":
    unittest.main()
