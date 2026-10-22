"""CMS media regression contracts for artwork banners and retry diagnostics."""
import unittest
from flask import g
from app.routes import storefront
from tests import test_storefront_publication_and_media as fixtures
from tests.test_storefront_publication_and_media import Database, IMAGE, SECOND, lambda_fn

class MediaRepairTests(unittest.TestCase):
    setUp = fixtures.StorefrontContractTests.setUp
    call = fixtures.StorefrontContractTests.call

    def test_menu_accepts_artwork_only_but_hero_still_requires_copy(self):
        for placement, expected in [('menu', 201), ('hero', 400), ('home', 400)]:
            with self.subTest(placement=placement):
                body = {'placement': placement, 'image_url': IMAGE, 'title': '',
                        'metadata': {'slides': [{'image_url': IMAGE, 'title': ''},
                                                {'image_url': SECOND, 'title': ''}]}}
                response, status = self.call(storefront.create_banner, Database([]), data=body)
                self.assertEqual(status, expected)
                if status == 201:
                    self.assertEqual(response.json['images'], [IMAGE, SECOND])
                    self.assertEqual(response.json['title'], '')

    def test_create_cannot_hide_an_empty_carousel_behind_legacy_image(self):
        response, status = self.call(storefront.create_banner, Database([]), data={
            'placement': 'menu', 'image_url': IMAGE, 'metadata': {'slides': []}})
        self.assertEqual(status, 400)

    def test_menu_update_uses_saved_placement_when_not_resent(self):
        row = {'id': 'menu', 'placement': 'menu', 'image_url': IMAGE, 'images': [IMAGE],
               'metadata': {}, 'updated_at': '2026-10-21T09:00:00+00:00'}
        response, status = self.call(lambda_fn(storefront.update_banner, 'menu'), Database([row]),
            data={'expected_updated_at': '2026-10-21T09:00:00Z',
                  'metadata': {'slides': [{'image_url': SECOND, 'title': ''}]}})
        self.assertEqual(status, 200)
        self.assertEqual(response.json['images'], [SECOND])

    def test_timestamp_equivalence_keeps_real_conflicts(self):
        self.assertTrue(storefront._same_timestamp('2026-10-21T09:00:00Z', '2026-10-21T10:00:00+01:00'))
        self.assertFalse(storefront._same_timestamp('2026-10-21T09:00:01Z', '2026-10-21T09:00:00+00:00'))
        self.assertFalse(storefront._same_timestamp('2026-10-21T09:00:00', '2026-10-21T09:00:00Z'))
        self.assertFalse(storefront._same_timestamp('invalid', '2026-10-21T09:00:00Z'))

    def test_other_row_key_collision_is_not_reported_as_changed_replay(self):
        class KeyConflict(Database):
            def table(self, name):
                q = super().table(name)
                def conflict(_):
                    from app.db import SupabaseError
                    raise SupabaseError('duplicate key', 409, {'code': '23505'})
                q.insert = conflict
                return q
        with self.app.test_request_context():
            g.user_id = 'actor'
            response, status = storefront._insert_cms(KeyConflict([]), 'storefront_sections',
                {'title': 'Step', 'key': 'same-step'}, {'request_id': 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'})
        self.assertEqual(status, 409)
        self.assertEqual(response.json['error'], storefront.MSG.STOREFRONT_KEY_EXISTS)
