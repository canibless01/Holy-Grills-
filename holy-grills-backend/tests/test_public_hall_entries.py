from app.routes.leaderboard import _public_hall_entry


def test_explicit_fixtures_are_not_public_honours():
    assert not _public_hall_entry({'full_name': '[TEST] userf'})
    assert not _public_hall_entry({'name': ' [AUDIT PROVIDER] student'})
    assert _public_hall_entry({'full_name': 'Testimony F.'})
    assert _public_hall_entry({'full_name': 'Faith'})
