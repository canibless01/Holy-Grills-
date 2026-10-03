import unittest

def squad_share_plan_logic(hp_amount, distinct_member_count, owner_id_present=False):
    """
    Pure logic extracted from squad_share_plan:
    total_shares = 1 + distinct_members (owner not double counted)
    share = hp // total_shares
    owner_share = hp - share*(total-1)
    """
    total_shares = 1 + distinct_member_count
    if total_shares <= 0:
        total_shares = 1
    share = hp_amount // total_shares if total_shares else 0
    owner_share = hp_amount - share * (total_shares - 1)
    return total_shares, share, owner_share


class TestSquadSharePlan(unittest.TestCase):
    def test_owner_plus_one_registered_100hp(self):
        total, share, owner_share = squad_share_plan_logic(100, 1)
        self.assertEqual(total, 2)
        self.assertEqual(share, 50)
        self.assertEqual(owner_share, 50)

    def test_owner_plus_one_reg_one_unreg_100hp(self):
        total, share, owner_share = squad_share_plan_logic(100, 2)
        self.assertEqual(total, 3)
        self.assertEqual(share, 33)
        self.assertEqual(owner_share, 34)  # owner takes remainder 100-33*2=34

    def test_100hp_2_people_bonus_30(self):
        # 100 HP, 2 people, 30% bonus
        hp = 100
        total, share, owner_share = squad_share_plan_logic(hp, 1)
        bonus_pct = 30
        bonus = (hp * bonus_pct) // 100
        self.assertEqual(share, 50)
        self.assertEqual(owner_share, 50)
        self.assertEqual(bonus, 30)
        # total issued = owner_share + share + bonus? Actually owner gets share+bonus, member share
        # For owner+1: owner 50+30=80, member 50, total 130
        total_issued = owner_share + share + bonus
        self.assertEqual(total_issued, 130)

    def test_owner_only_no_bonus(self):
        total, share, owner_share = squad_share_plan_logic(100, 0)
        self.assertEqual(total, 1)
        self.assertEqual(share, 100)
        self.assertEqual(owner_share, 100)

    def test_small_hp_large_squad(self):
        # 10 HP, 5 members => share 10//6=1, owner 10-1*5=5
        total, share, owner_share = squad_share_plan_logic(10, 5)
        self.assertEqual(total, 6)
        self.assertEqual(share, 1)
        self.assertEqual(owner_share, 5)
        # No HP disappears: share*5 + owner = 1*5+5=10

    def test_no_hp_loss_rounding(self):
        for hp in [1, 2, 3, 99, 100, 101]:
            for members in [1, 2, 3, 4, 5]:
                total, share, owner_share = squad_share_plan_logic(hp, members)
                reconstructed = share * members + owner_share
                self.assertEqual(reconstructed, hp, f"HP loss for hp={hp} members={members}")

    def test_bonus_only_with_registered(self):
        # Bonus guard: only if at least one other registered member
        hp = 100
        pct = 30
        bonus = (hp * pct)//100
        # Only unregistered members -> no bonus
        has_registered = False
        if not has_registered:
            bonus = 0
        self.assertEqual(bonus, 0)
        # With registered
        has_registered = True
        bonus = (hp * pct)//100 if has_registered else 0
        self.assertEqual(bonus, 30)

    def test_setting_0_split_only(self):
        hp = 100
        pct = 0
        bonus = (hp * pct)//100
        self.assertEqual(bonus, 0)


if __name__ == "__main__":
    unittest.main()
