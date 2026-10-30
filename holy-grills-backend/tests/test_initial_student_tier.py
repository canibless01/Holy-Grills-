import unittest
from app.services.tier_service import ensure_initial_student_tier


class Query:
    def __init__(self, db, table): self.db, self.table, self.filters, self.patch = db, table, [], None
    def select(self, *_): return self
    def eq(self, key, value): self.filters.append((key, value)); return self
    def is_(self, key, _): self.filters.append((key, None)); return self
    def order(self, *_, **__): return self
    def update(self, patch): self.patch = patch; return self
    def execute(self):
        rows = self.db.tiers if self.table == 'hp_tiers' else [self.db.profile]
        rows = [row for row in rows if all(str(row.get(key)).lower() == str(value).lower() for key, value in self.filters)]
        if self.patch:
            for row in rows: row.update(self.patch)
            self.db.writes.extend(self.patch.keys() for _ in rows)
        return rows


class DB:
    def __init__(self, profile):
        self.profile, self.writes = dict(profile), []
        self.tiers = [{'id':'ember','min_points':0,'sort_order':0,'is_active':True}, {'id':'flame','min_points':100,'sort_order':1,'is_active':True}]
    def table(self, table): return Query(self, table)


class InitialStudentTierTests(unittest.TestCase):
    def test_missing_student_tier_uses_earned_threshold_without_changing_points(self):
        for score, tier in [(0,'ember'),(150,'flame')]:
            profile={'id':'student','role':'student','current_tier_id':None,'hp_earned_120day':score}
            db=DB(profile); result=ensure_initial_student_tier(profile,db)
            self.assertEqual(result['current_tier_id'],tier)
            self.assertEqual(db.profile['hp_earned_120day'],score)
            self.assertEqual([list(keys) for keys in db.writes],[['current_tier_id']])

    def test_existing_staff_and_inactive_profiles_are_not_reassigned(self):
        for patch in [{'current_tier_id':'holy'},{'role':'kitchen'},{'is_active':False}]:
            profile={'id':'person','role':'student','current_tier_id':None,'hp_earned_120day':0,**patch}
            db=DB(profile);ensure_initial_student_tier(profile,db);self.assertEqual(db.writes,[])

    def test_concurrent_upgrade_is_not_overwritten(self):
        before={'id':'student','role':'student','current_tier_id':None,'hp_earned_120day':0}
        db=DB({**before,'current_tier_id':'holy','hp_earned_120day':10000})
        ensure_initial_student_tier(before,db)
        self.assertEqual(db.profile['current_tier_id'],'holy');self.assertEqual(db.writes,[])
