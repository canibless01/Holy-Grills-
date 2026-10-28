"""Email sign-off contract.

Every branded transactional/rich/ticket email must end with the fixed brand
line "Made with more than flame ❤️‍🔥, Holy Grills Team." instead of the old
"With love, / Holy Grills FUTA" two-paragraph sign-off. Newsletters
deliberately skip the shared sign-off (their campaign body carries its own
tone), so they remain exempt.
"""
import os
import unittest
from unittest.mock import patch

for name in ('SUPABASE_URL', 'SUPABASE_ANON_KEY', 'SUPABASE_SERVICE_ROLE_KEY',
             'JWT_SECRET', 'SECRET_KEY'):
    os.environ.setdefault(
        name, 'https://example.supabase.co' if name == 'SUPABASE_URL' else 'test')

from app.utils import email as email_mod


SIGNOFF = "Made with more than flame ❤️‍🔥, Holy Grills Team."


class EmailSignoffTests(unittest.TestCase):
    def assert_branded_signoff(self, html):
        self.assertIn(SIGNOFF, html)
        self.assertNotIn('With love,', html)
        self.assertNotIn('Holy Grills FUTA', html)

    def test_standard_builder_uses_the_new_signoff_even_with_old_tagline_env(self):
        with patch.dict(os.environ, {'APP_TAGLINE': 'Holy Grills FUTA'}):
            html = email_mod._build_html(
                'Ada', 'Your order is confirmed.', os.environ['APP_TAGLINE'])
        self.assert_branded_signoff(html)

    def test_rich_builder_uses_the_new_signoff(self):
        html = email_mod._build_rich_html(
            'Ada', '<p>Big news</p>', [], [], 'Holy Grills FUTA')
        self.assert_branded_signoff(html)

    def test_qr_ticket_email_uses_the_new_signoff(self):
        captured = {}

        def fake_send(to_email, to_name, subject, html_body, headers=None):
            captured['html'] = html_body
            return True

        with patch.object(email_mod, 'send_email_raw', side_effect=fake_send):
            ok = email_mod.send_qr_ticket_email(
                'guest@example.test', 'Guest', 'Grill Night',
                'ticket-1', 'event-1', event_date='2026-11-01',
                event_location='FUTA')
        self.assertTrue(ok)
        self.assert_branded_signoff(captured['html'])

    def test_newsletter_style_skip_signoff_emits_no_brand_signoff(self):
        html = email_mod._build_html(
            'there', 'Campaign body', 'The Holy Grills Team',
            skip_greeting=True, skip_signoff=True)
        self.assertNotIn(SIGNOFF, html)
        self.assertNotIn('With love,', html)

    def test_signoff_constant_is_the_single_source(self):
        # All three builders render the shared constant rather than a local copy.
        self.assertEqual(email_mod.EMAIL_SIGNOFF, SIGNOFF)
        source = open(email_mod.__file__, encoding='utf-8').read()
        self.assertEqual(source.count('Made with more than flame'), 1)


if __name__ == '__main__':
    unittest.main()
