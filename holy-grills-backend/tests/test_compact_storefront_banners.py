"""Compact slots keep independent artwork and icon/copy slide contracts."""
import unittest
from app.routes import storefront
from tests import test_storefront_publication_and_media as fixtures
from tests.test_storefront_publication_and_media import Database, IMAGE, SECOND

class CompactBannerTests(unittest.TestCase):
    setUp = fixtures.StorefrontContractTests.setUp
    call = fixtures.StorefrontContractTests.call

    def test_menu_and_checkout_accept_text_without_image_and_independent_artwork(self):
        for placement in ('menu', 'checkout'):
            with self.subTest(placement=placement):
                response, status = self.call(storefront.create_banner, Database([]), data={
                    'placement': placement,
                    'metadata': {'slides': [
                        {'display_mode': 'text', 'title': 'Choose your sides', 'subtitle': 'Freshly made',
                         'cta_text': 'Explore', 'cta_url': '/menu'},
                        {'display_mode': 'image', 'image_url': IMAGE, 'cta_url': '/rewards'},
                    ]}})
                self.assertEqual(status, 201)
                self.assertEqual(response.json['image_url'], '')
                self.assertEqual(response.json['images'], [IMAGE])
                self.assertEqual(response.json['metadata']['slides'][0]['title'], 'Choose your sides')
                self.assertEqual(response.json['metadata']['slides'][1]['title'], '')

    def test_compact_text_requires_title_and_artwork_requires_image(self):
        for slide in ({'display_mode': 'text', 'image_url': IMAGE},
                      {'display_mode': 'image', 'title': 'Not artwork'},
                      {'display_mode': 'other', 'image_url': IMAGE, 'title': 'Invalid'},
                      {'display_mode': {'invalid': True}, 'title': 'Invalid'}):
            with self.subTest(slide=slide):
                _, status = self.call(storefront.create_banner, Database([]), data={
                    'placement': 'checkout', 'metadata': {'slides': [slide]}})
                self.assertEqual(status, 400)

    def test_hero_and_home_require_image_with_overlay_copy(self):
        for placement in ('hero', 'home'):
            for slide in ({'display_mode': 'text', 'title': 'Not a hero', 'image_url': IMAGE},
                          {'display_mode': 'image', 'image_url': IMAGE}):
                with self.subTest(placement=placement, slide=slide):
                    _, status = self.call(storefront.create_banner, Database([]), data={
                        'placement': placement, 'metadata': {'slides': [slide]}})
                    self.assertEqual(status, 400)

    def test_cta_pair_is_required_for_text_not_unlabelled_artwork_link(self):
        for slide in ({'display_mode': 'text', 'title': 'Text', 'cta_url': '/menu'},
                      {'display_mode': 'image', 'image_url': SECOND, 'cta_text': 'Missing destination'}):
            _, status = self.call(storefront.create_banner, Database([]), data={
                'placement': 'menu', 'metadata': {'slides': [slide]}})
            self.assertEqual(status, 400)

    def test_supporter_contact_accepts_web_whatsapp_and_rejects_unsafe_destinations(self):
        self.assertTrue(storefront._supporter_links_valid({'url': 'https://wa.me/2348000000000'}))
        self.assertTrue(storefront._supporter_links_valid({'url': 'https://instagram.com/local'}))
        for links in ({'url': 'javascript:alert(1)'}, {'url': '/not-a-social-page'},
                      {'url': {'invalid': True}}, {'link': 'https://user:pass@example.com'},
                      {'url': 'https://example.com:bad'}):
            with self.subTest(links=links):
                self.assertFalse(storefront._supporter_links_valid(links))
