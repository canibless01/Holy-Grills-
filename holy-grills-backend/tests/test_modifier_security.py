"""Exercise actual checkout resolvers against invalid ownership and selection data."""
import unittest
from app.services.order_service import _resolve_item_variations, _resolve_item_addons

class Query:
    def __init__(self, db, name): self.db,self.name=db,name
    def select(self,*args): return self
    def eq(self,*args): return self
    def in_(self,*args): return self
    def execute(self):
        if self.name in self.db.fail: raise RuntimeError('database unavailable')
        return self.db.rows.get(self.name, [])
class Db:
    def __init__(self,rows=None,fail=()): self.rows=rows or {};self.fail=fail
    def table(self,name): return Query(self,name)

ITEM={'id':'meal','name':'Meal'}
OPTION={'id':'opt','name':'Beef','variation_group_id':'vg','price_delta':200,'is_available':True}
GROUP={'id':'vg','name':'Protein','is_required':True,'min_selections':0,'max_selections':1}
ADDON={'id':'side','name':'Slaw','group_id':'ag','price':100,'is_available':True,'is_archived':False}
AG={'id':'ag','name':'Sides','is_required':True,'min_select':0,'max_select':3}
class ModifierSecurityTests(unittest.TestCase):
    def test_required_lookup_outage_does_not_admit_bare_item(self):
        with self.assertRaisesRegex(ValueError,'could not be verified'):
            _resolve_item_variations(Db(fail=['menu_item_variation_groups']),ITEM,[])
    def test_option_from_other_item_rejected_even_when_item_has_no_groups(self):
        with self.assertRaisesRegex(ValueError,'does not belong'):
            _resolve_item_variations(Db({'menu_item_variation_options':[OPTION]}),ITEM,[{'option_id':'opt'}])
    def test_required_zero_minimum_still_requires_choice(self):
        with self.assertRaisesRegex(ValueError,'Selection required'):
            _resolve_item_variations(Db({'menu_item_variation_groups':[GROUP]}),ITEM,[])
    def test_duplicate_option_rejected(self):
        with self.assertRaisesRegex(ValueError,'selected twice'):
            _resolve_item_variations(Db(),ITEM,[{'option_id':'opt'},{'option_id':'opt'}])
    def test_required_addon_zero_minimum_still_requires_choice(self):
        with self.assertRaises(ValueError):
            _resolve_item_addons(Db({'menu_addon_groups':[AG]}),ITEM,[])
    def test_addon_quantity_cannot_be_zero_fractional_or_infinite(self):
        db=Db({'menu_addon_groups':[AG],'menu_addons':[ADDON]})
        for quantity in [0,-1,1.5,True,float('inf'),'bad']:
            with self.subTest(quantity=quantity),self.assertRaisesRegex(ValueError,'whole number'):
                _resolve_item_addons(db,ITEM,[{'addon_id':'side','quantity':quantity}])
    def test_valid_choice_uses_database_price_not_client_price(self):
        db=Db({'menu_item_variation_groups':[GROUP],'menu_item_variation_options':[OPTION]})
        amount,resolved=_resolve_item_variations(db,ITEM,[{'option_id':'opt','price_delta':0}])
        self.assertEqual(float(amount),200);self.assertEqual(resolved[0]['price_delta'],200)
