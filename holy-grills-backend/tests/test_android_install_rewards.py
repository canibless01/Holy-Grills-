"""Android shares the existing lifetime receipts, with authenticated ownership."""
from unittest.mock import MagicMock, patch
from flask import Flask
import pytest
from app.routes import challenges
from app.middleware import auth
from app.services.push_registration import has_registered_push
from app.services import milestone_service as ms


class Db:
    def __init__(self, rows): self.rows = rows; self.filters = []
    def table(self, name): self.name = name; self.filters = []; return self
    def select(self, *_): return self
    def eq(self, key, value): self.filters.append((key, [value])); return self
    def in_(self, key, values): self.filters.append((key, values)); return self
    def limit(self, *_): return self
    def execute(self):
        if self.name == 'milestones': return [{'id': 'shared-push-milestone'}]
        return [r for r in self.rows if all(r.get(k) in values for k, values in self.filters)][:1]


@pytest.mark.parametrize('platform', ['web', 'android'])
def test_owned_supported_subscription_is_eligible(platform):
    db = Db([{'id': 'sub', 'user_id': 'student', 'platform': platform}])
    assert has_registered_push(db, 'student')
    assert ('user_id', ['student']) in db.filters


@pytest.mark.parametrize('rows', [[], [{'id': 'other', 'user_id': 'other-campus-user', 'platform': 'android'}], [{'id': 'unknown', 'user_id': 'student', 'platform': 'unknown'}]])
def test_another_user_or_unrecognised_subscription_cannot_unlock_bonus(rows):
    assert not has_registered_push(Db(rows), 'student')


@pytest.mark.parametrize('replayed', [False, True])
def test_authenticated_native_claim_uses_same_milestone_and_ignores_supplied_user(replayed):
    app = Flask(__name__); app.register_blueprint(challenges.challenges_bp, url_prefix='/challenges')
    admin_db = MagicMock(); admin_db.auth_get_user.return_value = {'id': 'student'}
    admin_db.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = {'id': 'student', 'role': 'student', 'campus_id': 'campus-a', 'is_active': True}
    db = Db([{'id': 'android-sub', 'user_id': 'student', 'platform': 'android'}])
    with patch.object(auth, 'get_db', return_value=admin_db), patch.object(challenges, 'get_user_client', return_value=db), patch.object(ms, 'check_and_award_milestone', return_value={'already_completed': replayed}) as award:
        response = app.test_client().post('/challenges/push-registered', headers={'Authorization': 'Bearer bounded-fixture-token'}, json={'user_id': 'other-campus-user'})
    assert response.status_code == 200
    assert response.json['already_completed'] is replayed
    award.assert_called_once_with('student', 'shared-push-milestone')


def test_native_reward_claim_still_requires_login():
    app = Flask(__name__); app.register_blueprint(challenges.challenges_bp, url_prefix='/challenges')
    with patch.object(challenges, 'get_user_client') as db:
        response = app.test_client().post('/challenges/push-registered')
    assert response.status_code == 401
    db.assert_not_called()


@pytest.mark.parametrize('eligible', [False, True])
def test_generic_milestone_completion_cannot_bypass_native_subscription_gate(eligible):
    user_db = MagicMock(); milestone = {'id': 'shared', 'trigger_type': 'push_subscribe', 'hp_awarded': 25}
    user_db.table.return_value.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value = milestone
    with Flask(__name__).app_context(), patch.object(ms, 'get_user_client', return_value=user_db), patch.object(ms, 'get_db', return_value=user_db), patch.object(ms, '_is_already_completed', return_value=False), patch('app.services.push_registration.has_registered_push', return_value=eligible) as gate, patch('app.utils.settings.get_validated_setting', return_value=25), patch.object(ms, '_get_user_campus_id', return_value='campus-a'), patch.object(ms, '_complete_active_milestone', return_value={'completed': True}) as award:
        if eligible:
            assert ms.check_and_award_milestone('student', 'shared')['completed']
            award.assert_called_once_with(user_db, 'student', milestone, 25, None, campus_id='campus-a')
        else:
            with pytest.raises(ValueError): ms.check_and_award_milestone('student', 'shared')
            award.assert_not_called()
        gate.assert_called_once_with(user_db, 'student')
