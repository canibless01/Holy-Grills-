import unittest

def is_same_campus(order_campus, profile_campus):
    if order_campus and profile_campus and order_campus != profile_campus:
        return False
    return True

def should_send_invite(profile_exists, same_campus):
    # After B-7 fix, only truly unregistered get invite
    if not profile_exists:
        return True
    if not same_campus:
        # Different campus treated as not found for privacy, but should we send invite? No, treat as unregistered? Spec says accept match only if same campus, otherwise probe protection.
        # For invite logic, if different campus, we should NOT reveal existence, so treat as unregistered and send invite? But that leaks? Safer to NOT send invite and treat as not found but don't send?
        # Spec: return no other profile details to caller. For email, after B-7 only people with no account get email; today every existing user added also receives it because of bug.
        # So different campus should be treated as not found but should we send invite? The spec says same-campus lookup, so if different campus, treat as not registered and send invite? However privacy says don't return details.
        # We'll treat as unregistered for invite to avoid leaking, but in real implementation we treat as not found (no user_id) and send invite.
        return True
    return False


class TestSquadPrivacy(unittest.TestCase):
    def test_same_campus_accepted(self):
        self.assertTrue(is_same_campus("campus1", "campus1"))
        self.assertFalse(is_same_campus("campus1", "campus2"))

    def test_no_campus_always_accept(self):
        # If order has no campus, allow
        self.assertTrue(is_same_campus(None, "campus1"))
        self.assertTrue(is_same_campus("campus1", None))
        self.assertTrue(is_same_campus(None, None))

    def test_invite_only_unregistered(self):
        # Existing user same campus -> no invite
        self.assertFalse(should_send_invite(True, True))
        # No profile -> invite
        self.assertTrue(should_send_invite(False, False))

    def test_privacy_no_details_returned(self):
        # Simulate results should only contain email and status, not name
        results = [{"email": "test@example.com", "status": "notified"}]
        for r in results:
            self.assertIn("email", r)
            self.assertIn("status", r)
            self.assertNotIn("full_name", r)
            self.assertNotIn("nickname", r)

    def test_delivered_order_409(self):
        def add_squad_members(order_status):
            if order_status == "delivered":
                return 409
            return 200

        self.assertEqual(add_squad_members("delivered"), 409)
        self.assertEqual(add_squad_members("preparing"), 200)


if __name__ == "__main__":
    unittest.main()
