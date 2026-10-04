import unittest

def calc_analytics(transactions):
    earned = sum(t["amount"] for t in transactions if t.get("type") == "earn" and t.get("source") != "hp_transfer_received")
    spent = sum(t["amount"] for t in transactions if t.get("type") == "spend" and t.get("source") != "hp_transfer_sent")
    transfer_received = sum(t["amount"] for t in transactions if t.get("source") == "hp_transfer_received")
    transfer_sent = sum(t["amount"] for t in transactions if t.get("source") == "hp_transfer_sent")
    return earned, spent, transfer_received, transfer_sent


class TestAnalyticsSeparation(unittest.TestCase):
    def test_exclude_transfers(self):
        txns = [
            {"amount": 100, "type": "earn", "source": "food_order"},
            {"amount": 50, "type": "earn", "source": "hp_transfer_received"},
            {"amount": 30, "type": "spend", "source": "reward_redemption"},
            {"amount": 20, "type": "spend", "source": "hp_transfer_sent"},
        ]
        earned, spent, recv, sent = calc_analytics(txns)
        self.assertEqual(earned, 100)
        self.assertEqual(spent, 30)
        self.assertEqual(recv, 50)
        self.assertEqual(sent, 20)

    def test_economics_includes_squad(self):
        issued_sources = ("food_order", "order_earn", "unlock", "tier_monthly_hp", "squad_split", "squad_split_claimed", "squad_bonus")
        txns = [
            {"amount": 100, "type": "earn", "source": "food_order"},
            {"amount": 50, "type": "earn", "source": "squad_split"},
            {"amount": 30, "type": "earn", "source": "squad_bonus"},
            {"amount": 20, "type": "earn", "source": "squad_split_claimed"},
        ]
        issued = sum(t["amount"] for t in txns if t.get("type") == "earn" and t.get("source") in issued_sources)
        self.assertEqual(issued, 200)

    def test_pending_squad_report_stuck(self):
        # Simulate stuck detection: pending row whose email now belongs to profile
        pending = [
            {"email": "a@example.com", "status": "pending"},
            {"email": "b@example.com", "status": "pending"},
        ]
        existing_profiles = {"a@example.com"}
        stuck = [p for p in pending if p["email"] in existing_profiles]
        self.assertEqual(len(stuck), 1)
        self.assertEqual(stuck[0]["email"], "a@example.com")


if __name__ == "__main__":
    unittest.main()
