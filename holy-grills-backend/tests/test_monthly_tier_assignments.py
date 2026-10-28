"""Controlled monthly grant routing; never executes live rewards or cron."""
import unittest
from unittest.mock import patch
from datetime import date
from flask import Flask
from app.services.tier_service import DEFAULT_TIER_PERKS, resolve_perk
from app.tasks.scheduled import grant_monthly_tier_perks

class Query:
    def __init__(self, db, table):
        self.db, self.table, self.filters, self.one, self.new = db, table, [], False, None
    def select(self, *_): return self
    def eq(self, key, value):
        self.filters.append(lambda row: row.get(key) == value); return self
    def is_(self, key, value):
        self.filters.append(lambda row: row.get(key) is None); return self
    def gte(self, key, value):
        self.filters.append(lambda row: row.get(key, '') >= value); return self
    def single(self): self.one = True; return self
    def insert(self, row): self.new = row; return self
    def execute(self):
        if self.new is not None:
            row = dict(self.new, id=str(len(self.db.rows[self.table])), created_at='2026-10-01T00:05:00Z')
            self.db.rows[self.table].append(row); return [row]
        rows = [r for r in self.db.rows[self.table] if all(f(r) for f in self.filters)]
        return (rows[0] if rows else None) if self.one else rows

class DB:
    def __init__(self):
        self.rows = {
            'profiles': [{'id': s, 'current_tier_id': s, 'campus_id': 'campus', 'is_active': True} for s in DEFAULT_TIER_PERKS],
            'hp_tiers': [{'id': s, 'slug': s} for s in DEFAULT_TIER_PERKS],
            'system_settings': [], 'free_side_credits': [],
        }
    def table(self, name): return Query(self, name)
    def rpc(self, *_): return True

class MonthlyTierAssignments(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__); self.db = DB()
    def run_grants(self, twice=False):
        with self.app.app_context(), patch('app.tasks.scheduled.get_db', return_value=self.db), patch('app.services.tier_service.get_db', return_value=self.db), patch('app.services.hp_service.award_active_hp') as award, patch('app.utils.tz.today_wat', return_value=date(2026, 10, 1)), patch('app.utils.tz.wat_month_start_utc', return_value='2026-10-01'):
            grant_monthly_tier_perks.run.__wrapped__(None)
            if twice: grant_monthly_tier_perks.run.__wrapped__(None)
            return [c.kwargs for c in award.call_args_list]
    def test_each_tier_routes_to_its_assigned_reward_and_replay_key(self):
        calls = self.run_grants(twice=True)
        self.assertEqual([(r['user_id'], r['credits_remaining']) for r in self.db.rows['free_side_credits']], [('blaze', 1), ('holy', 1)])
        self.assertEqual([c['user_id'] for c in calls], ['flame', 'flame'])
        self.assertTrue(all(c['amount'] == 50 and c['apply_multiplier'] is False and c['campus_id'] == 'campus' for c in calls))
        self.assertEqual(calls[0]['reference_id'], calls[1]['reference_id'])
        self.assertEqual(calls[0]['reference_type'], 'tier_grant')
    def test_configured_override_is_used_by_the_grant_path(self):
        self.db.rows['system_settings'] = [{'key': 'tier_perk_flame_monthly_bonus_hp', 'value': '75', 'campus_id': None}]
        self.assertEqual(self.run_grants()[0]['amount'], 75)
    def test_only_holy_has_monthly_delivery_and_no_tier_has_monthly_spins(self):
        with self.app.app_context(), patch('app.services.tier_service.get_db', return_value=self.db):
            self.assertEqual([s for s in DEFAULT_TIER_PERKS if resolve_perk(s, 'monthly_free_delivery')], ['holy'])
            self.assertTrue(all(resolve_perk(s, 'exclusive_spins_monthly') == 0 for s in DEFAULT_TIER_PERKS))
