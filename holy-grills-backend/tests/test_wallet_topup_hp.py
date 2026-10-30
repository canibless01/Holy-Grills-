import unittest
import uuid
from unittest.mock import MagicMock, patch
from flask import Flask
from app.services import wallet_service as service


class WalletTopupHpTests(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.config.update(WALLET_TOPUP_MIN=3000, WALLET_TOPUP_HP=50, STREAK_RECLAIM_MIN_TOPUP=100000)
        self.db = MagicMock()
        self.receipt = str(uuid.uuid4())
        self.db.rpc.return_value = {'transaction_id': self.receipt, 'new_balance': 3000}
        self.db.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = {'id': self.receipt, 'amount': 3000}

    def credit(self, amount, award):
        with self.app.app_context(), patch.object(service, 'get_db', return_value=self.db), patch.object(service, 'setting_or_config', return_value=50), patch.object(service, 'award_active_hp', award):
            return service.credit_wallet('owner', amount, 'HG-WALLET-provider-reference', campus_id='campus')

    def test_qualifying_bonus_uses_uuid_wallet_receipt_not_paystack_string(self):
        award = MagicMock()
        self.credit(3000, award)
        args = award.call_args.kwargs
        self.assertEqual(str(uuid.UUID(args['reference_id'])), self.receipt)
        self.assertEqual(args['amount'], 50)
        self.assertEqual(args['reference_type'], 'wallet_topup')
        self.assertEqual(args['campus_id'], 'campus')
        self.assertFalse(args['apply_multiplier'])

    def test_provider_replay_reuses_the_same_hp_deduplication_receipt(self):
        award = MagicMock()
        self.credit(3000, award); self.credit(3000, award)
        self.assertEqual([call.kwargs['reference_id'] for call in award.call_args_list], [self.receipt, self.receipt])

    def test_below_threshold_and_missing_receipt_do_not_award_undeduplicated_hp(self):
        award = MagicMock()
        self.credit(1000, award)
        self.db.rpc.return_value = {'new_balance': 3000}
        self.credit(3000, award)
        award.assert_not_called()
