"""Disabled release gates must refuse actions without touching business data."""
import ast
import inspect
import unittest
from pathlib import Path
from unittest.mock import MagicMock,patch
from flask import Flask,g
from app.messages import MSG
from app.routes import hp,exclusive_spin,free_sides,leaderboard

class FeatureGateMessageTests(unittest.TestCase):
    def test_disabled_routes_return_403_before_business_queries(self):
        app=Flask(__name__)
        # Spin mutations check the release flag inside their atomic transaction,
        # after recovering an already committed intent (covered separately).
        cases=[(hp,hp.transfer_hp,()),(hp,hp.flash_redeem,('reward',)),(exclusive_spin,exclusive_spin.my_spins,()),(free_sides,free_sides.my_free_sides,()),(free_sides,free_sides.select_free_side,()),(leaderboard,leaderboard.hall_of_fame,()),(leaderboard,leaderboard.hall_of_fame_inductees,())]
        for module,handler,args in cases:
            db=MagicMock()
            with self.subTest(handler=handler.__name__),app.test_request_context(method='POST',json={}),patch('app.services.feature_flags.is_feature_enabled',return_value=False),patch.object(module,'get_user_client',return_value=db):
                g.user_id='student';g.campus_id='campus'
                # exclusive_spin imports the flag reader once at module load.
                with patch.object(exclusive_spin,'is_feature_enabled',return_value=False):
                    response,status=inspect.unwrap(handler)(*args)
                self.assertEqual(status,403);self.assertIn('not available',response.get_json()['error']);db.table.assert_not_called();db.rpc.assert_not_called()
    def test_all_backend_message_references_exist(self):
        root=Path(__file__).resolve().parents[1]/'app';missing=[]
        for path in root.rglob('*.py'):
            for node in ast.walk(ast.parse(path.read_text())):
                if isinstance(node,ast.Attribute) and isinstance(node.value,ast.Name) and node.value.id=='MSG' and not hasattr(MSG,node.attr):missing.append(str(path.relative_to(root))+':'+str(node.lineno)+' '+node.attr)
        self.assertEqual(missing,[])
