"""Email sign-off contract.

Every branded transactional/rich/ticket email must end with the fixed two-line
brand sign-off, in separate paragraphs with a gap between them:

    Made with more than flame ❤️‍🔥,

    Holy Grills Team.

instead of the old "With love, / Holy Grills FUTA" sign-off or a single-line
variant. Newsletters deliberately skip the shared sign-off (their campaign
body carries its own tone), so they remain exempt.
"""
import inspect
import os
import re
import unittest
from unittest.mock import patch

for name in ('SUPABASE_URL', 'SUPABASE_ANON_KEY', 'SUPABASE_SERVICE_ROLE_KEY',
             'JWT_SECRET', 'SECRET_KEY'):
    os.environ.setdefault(
        name, 'https://example.supabase.co' if name == 'SUPABASE_URL' else 'test')

from app import config as config_mod
from app.constants import APP_TAGLINE_DEFAULT
from app.routes import notifications as notifications_routes
from app.services import notification_service, order_service
from app.utils import email as email_mod


SIGNOFF_LINE_1 = "Made with more than flame ❤️‍🔥,"
SIGNOFF_LINE_2 = "Holy Grills Team."
# The two lines must never be rendered as one comma-less/single paragraph line.
SINGLE_LINE = "Made with more than flame ❤️‍🔥, Holy Grills Team."
TAGLINE = "Made with more than flame ❤️‍🔥"


class EmailSignoffTests(unittest.TestCase):
    def assert_branded_signoff(self, html):
        # Both brand lines exist, in separate paragraphs, line 1 first.
        self.assertIn(SIGNOFF_LINE_1, html)
        self.assertIn(SIGNOFF_LINE_2, html)
        self.assertNotIn(SINGLE_LINE, html)
        paragraphs = re.findall(r"<p[^>]*>(.*?)</p>", html, flags=re.S)
        texts = [re.sub(r"\s+", " ", p).strip() for p in paragraphs]
        self.assertIn(SIGNOFF_LINE_1, texts)
        self.assertIn(SIGNOFF_LINE_2, texts)
        self.assertLess(texts.index(SIGNOFF_LINE_1), texts.index(SIGNOFF_LINE_2))
        # Legacy wording is gone everywhere.
        self.assertNotIn('With love,', html)
        self.assertNotIn('Holy Grills FUTA', html)

    def test_standard_builder_uses_the_two_line_signoff_even_with_old_tagline_env(self):
        with patch.dict(os.environ, {'APP_TAGLINE': 'Holy Grills FUTA'}):
            html = email_mod._build_html(
                'Ada', 'Your order is confirmed.', os.environ['APP_TAGLINE'])
        self.assert_branded_signoff(html)

    def test_rich_builder_uses_the_two_line_signoff(self):
        html = email_mod._build_rich_html(
            'Ada', '<p>Big news</p>', [], [], 'Holy Grills FUTA')
        self.assert_branded_signoff(html)

    def test_qr_ticket_email_uses_the_two_line_signoff(self):
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
            'there', 'Campaign body', APP_TAGLINE_DEFAULT,
            skip_greeting=True, skip_signoff=True)
        self.assertNotIn(SIGNOFF_LINE_1, html)
        self.assertNotIn(SIGNOFF_LINE_2, html)
        self.assertNotIn('With love,', html)

    def test_signoff_constants_are_the_single_source(self):
        # All three builders render the shared constants rather than local copies.
        self.assertEqual(email_mod.EMAIL_SIGNOFF_LINE_1, SIGNOFF_LINE_1)
        self.assertEqual(email_mod.EMAIL_SIGNOFF_LINE_2, SIGNOFF_LINE_2)
        source = inspect.getsource(email_mod)
        self.assertEqual(source.count('Made with more than flame'), 1)
        self.assertNotIn('EMAIL_SIGNOFF =', source)  # no legacy single-line constant

    def test_tagline_fallback_is_the_brand_line_everywhere(self):
        import importlib
        self.assertEqual(APP_TAGLINE_DEFAULT, TAGLINE)
        # With APP_TAGLINE unset, Config must resolve to the brand constant.
        saved = os.environ.pop('APP_TAGLINE', None)
        try:
            reloaded = importlib.reload(config_mod)
            self.assertEqual(reloaded.Config.APP_TAGLINE, APP_TAGLINE_DEFAULT)
        finally:
            if saved is not None:
                os.environ['APP_TAGLINE'] = saved
            importlib.reload(config_mod)
        # Every os.environ.get fallback must point at the constant, never a
        # hardcoded legacy string.
        for module in (email_mod, notification_service, order_service,
                       notifications_routes, config_mod):
            source = inspect.getsource(module)
            self.assertNotIn('The Holy Grills Team', source,
                             f'legacy tagline fallback remains in {module.__name__}')
            self.assertNotIn('Holy Grills FUTA', source,
                             f'retired tagline remains in {module.__name__}')


if __name__ == '__main__':
    unittest.main()
