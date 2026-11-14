"""Global social settings, platform validation and campus-isolation boundaries."""
import unittest
from unittest.mock import patch
from flask import Flask, g
from app.routes import admin_gifts, storefront
from app.utils.social_links import validate_social_links, public_social_links
from tests.test_storefront_publication_and_media import Database


class SocialLinksTests(unittest.TestCase):
    def test_platform_destinations_and_removal(self):
        self.assertEqual(validate_social_links({'instagram': ' https://instagram.com/holygrills ', 'facebook': ''}),
                         {'instagram': 'https://instagram.com/holygrills'})
        self.assertEqual(validate_social_links({}), {})

    def test_untrusted_destinations_and_wrong_shapes_are_rejected(self):
        for value in ({'instagram': 'javascript:alert(1)'}, {'instagram': 'https://instagram.com.evil.test/name'},
                      {'instagram': 'https://evil.test@instagram.com/name'}, {'instagram': 'https://facebook.com/name'},
                      {'instagram': 'https://instagram.com:9999/name'}, {'instagram': 'https://instagram.com/a b'},
                      {'unknown': 'https://instagram.com/name'}, {'instagram': []}, [], None):
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_social_links(value)

    def call(self, fn, rows, *, body=None, role='super_admin', campus='campus', path='/'):
        db = Database(rows)
        with Flask(__name__).test_request_context(path, method='POST', json=body), \
             patch.object(admin_gifts, 'get_user_client', return_value=db), \
             patch.object(storefront, 'get_user_client', return_value=db), \
             patch.object(storefront, 'get_db', return_value=db), \
             patch.object(storefront, '_get_campus_id', return_value=campus):
            g.user_role, g.campus_id, g.user_id = role, campus, 'actor'
            response, status = fn.__wrapped__()
            return response, status, db

    def test_super_admin_can_create_global_setting_without_a_migration(self):
        response, status, db = self.call(admin_gifts.create_setting, [], body={
            'key': 'global_social_links', 'value': {'instagram': 'https://instagram.com/holygrills'}, 'is_public': True})
        self.assertEqual(status, 201)
        self.assertIsNone(db.rows[0]['campus_id'])
        self.assertEqual(db.rows[0]['value']['instagram'], 'https://instagram.com/holygrills')

    def test_campus_admin_cannot_write_global_or_campus_social_links(self):
        for campus in (None, 'campus'):
            response, status, db = self.call(admin_gifts.create_setting, [], role='admin', body={
                'key': 'global_social_links', 'campus_id': campus, 'value': {}})
            self.assertIn(status, (400, 403))
            self.assertEqual(db.rows, [])

    def test_even_super_admin_cannot_create_a_campus_override(self):
        _, status, db = self.call(admin_gifts.create_setting, [], body={
            'key': 'global_social_links', 'campus_id': 'campus', 'value': {}})
        self.assertEqual(status, 400)
        self.assertEqual(db.rows, [])

    def test_actual_public_config_uses_global_links_despite_campus_override(self):
        rows = [
            {'key': 'global_social_links', 'campus_id': None, 'is_public': True, 'value': {'instagram': 'https://instagram.com/global'}},
            {'key': 'global_social_links', 'campus_id': 'campus', 'is_public': True, 'value': {'instagram': 'https://instagram.com/campus'}},
        ]
        for campus in ('campus', None):
            response, status, _ = self.call(storefront.get_public_config, rows, campus=campus)
            self.assertEqual(status, 200)
            self.assertEqual(response.json['global_social_links'], {'instagram': 'https://instagram.com/global'})

    def test_invalid_historical_global_or_campus_only_setting_stays_hidden(self):
        self.assertEqual(public_social_links([{'key': 'global_social_links', 'campus_id': None, 'value': {'instagram': 'http://evil.test'}}]), {})
        self.assertEqual(public_social_links([{'key': 'global_social_links', 'campus_id': 'campus', 'value': {'instagram': 'https://instagram.com/campus'}}]), {})


if __name__ == '__main__':
    unittest.main()
