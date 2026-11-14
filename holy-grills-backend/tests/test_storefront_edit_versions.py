"""Stale CMS drafts and competing saves cannot overwrite newer stored content."""
import copy
import pytest
from flask import Flask, g
from unittest.mock import patch
from app.routes import storefront as sf
from tests.test_storefront_publication_and_media import Database, Query

STAMP = '2026-11-14T09:00:00+00:00'

@pytest.mark.parametrize('kind', ['section', 'supporter', 'banner'])
@pytest.mark.parametrize('race', [False, True])
def test_stale_draft_or_save_race_preserves_newer_content(kind, race):
    row = {'id': 'item', 'title': 'Newer', 'content': {'name': 'Newer', 'private_custom': 'Keep'},
           'section_type': 'early_supporter' if kind == 'supporter' else 'our_story',
           'placement': 'hero', 'metadata': {}, 'updated_at': STAMP}
    class RacingQuery(Query):
        def update(self, payload):
            if race:
                self.db.rows[0]['updated_at'] = '2026-11-14T09:01:00+00:00'
                self.db.rows[0]['title'] = 'Concurrent'
            return super().update(payload)
    class RacingDB(Database):
        def table(self, name): return RacingQuery(self)
    db = RacingDB([copy.deepcopy(row)])
    fn = {'section': sf.update_section, 'supporter': sf.update_early_supporter, 'banner': sf.update_banner}[kind]
    body = {'name': 'Old draft'} if kind == 'supporter' else {'title': 'Old draft'}
    body['expected_updated_at'] = STAMP if race else '2026-11-14T08:59:00Z'
    with Flask(__name__).test_request_context(json=body), patch.object(sf, 'get_user_client', return_value=db):
        g.user_role = 'admin'; g.campus_id = 'a'; g.user_id = 'actor'
        response, status = fn.__wrapped__('item')
    assert status == 409
    assert db.rows[0]['title'] == ('Concurrent' if race else 'Newer')
    assert db.rows[0]['content']['private_custom'] == 'Keep'


@pytest.mark.parametrize('kind', ['section', 'supporter'])
def test_matching_timestamp_accepts_save_and_keeps_custom_content(kind):
    db = Database([{'id': 'item', 'section_type': 'early_supporter' if kind == 'supporter' else 'our_story',
                    'updated_at': STAMP, 'content': {'private_custom': 'Keep'}}])
    body = {'expected_updated_at': '2026-11-14T09:00:00Z', **({'name': 'Saved'} if kind == 'supporter' else {'subtitle': 'Saved'})}
    fn = sf.update_early_supporter if kind == 'supporter' else sf.update_section
    with Flask(__name__).test_request_context(json=body), patch.object(sf, 'get_user_client', return_value=db):
        response, status = fn.__wrapped__('item')
    assert status == 200
    assert response.json['content']['private_custom'] == 'Keep'
    assert db.rows[0]['updated_at'] != STAMP
