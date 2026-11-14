from flask import Flask
from unittest.mock import MagicMock, patch
from app.services import hp_service


def test_signup_gift_is_flat_campus_scoped_and_replay_safe():
    tables={name:MagicMock() for name in ['system_settings','hp_transactions','profiles']}
    for query in tables.values():
        for method in ('select','eq','is_','single'):
            getattr(query,method).return_value=query
    tables['system_settings'].execute.return_value={'value':50}
    tables['profiles'].execute.return_value={'campus_id':'campus'}
    tables['hp_transactions'].execute.return_value=[]
    db=MagicMock();db.table.side_effect=lambda name:tables[name]
    with Flask(__name__).app_context(),patch.object(hp_service,'get_db',return_value=db),patch.object(hp_service,'award_active_hp',return_value={'awarded':50}) as award:
        assert hp_service.award_signup_bonus('owner')['awarded']==50
        assert award.call_args.kwargs['reference_id']=='owner'
        assert award.call_args.kwargs['apply_multiplier'] is False
        assert award.call_args.kwargs['campus_id']=='campus'
        tables['hp_transactions'].execute.return_value=[{'id':'existing-receipt'}]
        assert hp_service.award_signup_bonus('owner')['awarded']==0
        assert award.call_count==1
