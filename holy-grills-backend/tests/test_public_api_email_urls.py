from unittest.mock import patch
from flask import Flask
from app.utils.email import public_api_base, _wrap_url_with_tracking
from app.services.newsletter_service import unsubscribe_links


def test_migrated_backend_origin_and_api_url_produce_same_email_routes():
    app = Flask(__name__); app.config['FRONTEND_URL'] = 'https://holygrills.online'
    for configured in ('https://api.example.com', 'https://api.example.com/api/'):
        with patch.dict('os.environ', {'API_PUBLIC_URL': configured}), app.app_context():
            assert public_api_base() == 'https://api.example.com/api'
            assert _wrap_url_with_tracking('https://holygrills.online/menu', 'campaign', 'menu').startswith('https://api.example.com/api/notifications/tracking/click?')
            page, api = unsubscribe_links('private-token')
            assert page.startswith('https://holygrills.online/newsletter/unsubscribe?')
            assert api.startswith('https://api.example.com/api/storefront/newsletter/unsubscribe?')
