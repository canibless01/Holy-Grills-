"""Section-specific inserts and malformed optional fields share one validation contract."""
import unittest
from tests.test_storefront_publication_and_media import StorefrontContractTests, Database, IMAGE, lambda_fn
from app.routes import storefront


class SectionInsertContractTests(unittest.TestCase):
    setUp = StorefrontContractTests.setUp
    call = StorefrontContractTests.call

    def create(self, kind, **fields):
        return self.call(storefront.create_section, Database([]), data={'key': 'local-section', 'section_type': kind, **fields})

    def test_consumer_minimums_do_not_require_unused_title_or_image(self):
        cases = [
            ('testimonial', {'content': {'name': 'Reviewer', 'review': 'Good food', 'rating': 5}}),
            ('share_template', {'content': {'base_image_url': IMAGE}}),
            ('tier_icon', {'content': {'tier_slug': 'ember', 'image_url': IMAGE}}),
            ('popup', {'image_url': IMAGE, 'cta_url': '/menu', 'placement': 'rewards'}),
            ('whats_inside', {'title': 'Community'}),
            ('how_its_made', {'content': {'display_mode': 'image'}, 'image_url': IMAGE}),
            ('our_story', {'subtitle': 'Our campus story'}),
            ('catering', {'title': 'Catering', 'cta_text': 'Request catering'}),
            ('promo', {'image_url': IMAGE}),
        ]
        for kind, fields in cases:
            with self.subTest(kind=kind):
                response, status = self.create(kind, **fields)
                self.assertEqual(status, 201, response.json)

    def test_minimums_refuse_blank_required_review_artwork_and_process_content(self):
        for kind, fields in [
            ('testimonial', {'title': 'Someone', 'content': {'review': ' '}}),
            ('share_template', {'title': 'Share'}),
            ('tier_icon', {'title': 'Ember'}),
            ('popup', {'title': 'Popup'}),
            ('how_its_made', {'title': 'Cooked slowly'}),
            ('whats_inside', {'image_url': IMAGE}),
            ('our_story', {}), ('catering', {}), ('promo', {}),
            ('our_story', {'content': {'body': 'Not read by the story artwork consumer'}}),
            ('promo', {'content': {'description': 'Not read by the promo slider'}}),
        ]:
            with self.subTest(kind=kind):
                self.assertEqual(self.create(kind, **fields)[1], 400)

    def test_optional_fields_are_type_checked_before_insert_or_update(self):
        invalid = [{'subtitle': {'text': 'nested'}}, {'image_url': []}, {'cta_text': True},
                   {'eyebrow': 3}, {'placement': []}, {'display_mode': 'carousel'}, {'config': []}]
        for content in invalid:
            with self.subTest(content=content):
                self.assertEqual(self.create('promo', title='Promo', content=content)[1], 400)
                db = Database([{'id': 's', 'section_type': 'promo', 'content': {}}])
                response, status = self.call(lambda_fn(storefront.update_section, 's'), db, data={'content': content})
                self.assertEqual(status, 400)
                self.assertEqual(db.rows[0]['content'], {})
        response, status = self.call(lambda_fn(storefront.update_section, 's'), Database([{'id': 's', 'content': {}}]), data={'title': ['not text']})
        self.assertEqual(status, 400)

    def test_destination_and_page_validation_match_consumers(self):
        for destination in ('javascript:alert(1)', '//evil.test', '/\\evil.test', 'https://user:pass@example.test', 'https://[invalid', 'https://example.test:wrong', '/menu\nadmin'):
            with self.subTest(destination=destination):
                self.assertEqual(self.create('popup', image_url=IMAGE, cta_url=destination)[1], 400)
        self.assertEqual(self.create('popup', image_url=IMAGE, placement='checkout')[1], 400)
        self.assertEqual(self.create('promo', title='Offer', placement='dashboard')[1], 400)
        self.assertEqual(self.create('popup', image_url=IMAGE, cta_url='https://example.test/menu')[1], 201)

    def test_unrelated_visibility_patch_and_custom_metadata_are_preserved(self):
        db = Database([{'id': 's', 'section_type': 'promo', 'content': {'custom': {'retained': True}}}])
        response, status = self.call(lambda_fn(storefront.update_section, 's'), db, data={'is_active': False})
        self.assertEqual(status, 200)
        self.assertEqual(response.json['content']['custom'], {'retained': True})
        response, status = self.call(lambda_fn(storefront.update_section, 's'), db, data={'content': {'subtitle': 'Edited'}, 'placement': ''})
        self.assertEqual(status, 200)
        self.assertEqual(response.json['content']['custom'], {'retained': True})

    def test_banner_optional_fields_fail_cleanly_and_menu_needs_no_overlay_copy(self):
        with self.app.test_request_context():
            for body in ({'subtitle': {}}, {'cta_url': []}, {'action_label': True}, {'placement': 'dashboard'}, {'cta_url': 'https://user:pass@example.test'}):
                with self.subTest(body=body):
                    self.assertEqual(storefront._banner_fields(body)[1][1], 400)
            fields, error = storefront._banner_fields({'placement': 'menu', 'metadata': {'slides': [{'image_url': IMAGE}]}})
            self.assertIsNone(error)
            self.assertEqual(fields['title'], '')
            self.assertEqual(fields['images'], [IMAGE])
