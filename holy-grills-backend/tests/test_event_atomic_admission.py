"""API contract tests; real transaction evidence lives in the rollback SQL."""
from unittest.mock import MagicMock, patch
import pytest
from flask import Flask
from app.services.event_admission import admit_event_ticket


def test_only_validated_ticket_identity_reaches_rpc_and_settings_stay_server_side():
    app = Flask(__name__)
    app.config['EVENT_CHECKIN_HP'] = 75
    db = MagicMock()
    receipt = {'completed': True, 'checkin_id': 'admission', 'hp_added_to_active': 50, 'replayed': True}
    db.rpc.return_value = receipt
    with app.app_context(), patch('app.services.event_admission.get_db', return_value=db):
        assert admit_event_ticket('event', 'ticket', None, 'door', 'campus') is receipt
    db.rpc.assert_called_once_with('hg_admit_event_ticket', {
        'p_event_id': 'event', 'p_ticket_id': 'ticket', 'p_actor_id': None,
        'p_door_token': 'door', 'p_campus_id': 'campus', 'p_default_hp': 75,
    })


@pytest.mark.parametrize('receipt', [None, [], {}, {'error': 'ledger unavailable'}, {'completed': False}])
def test_failed_atomic_admission_does_not_become_success(receipt):
    db = MagicMock()
    db.rpc.return_value = receipt
    with Flask(__name__).app_context(), patch('app.services.event_admission.get_db', return_value=db):
        with pytest.raises(RuntimeError):
            admit_event_ticket('event', 'ticket', 'actor', 'door', 'campus')
