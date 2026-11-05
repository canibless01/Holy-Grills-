"""Artwork sections must save without synthetic overlay copy."""
from tests.test_storefront_publication_and_media import StorefrontContractTests, Database, IMAGE, lambda_fn
from app.routes import storefront

class ArtworkSectionTests(StorefrontContractTests):
    def test_popup_and_design_cards_accept_image_without_title(self):
        for kind, content in [('popup', {}), ('whats_inside', {'display_mode':'image'}), ('how_its_made', {'display_mode':'image'})]:
            with self.subTest(kind=kind):
                response,status=self.call(storefront.create_section,Database([]),data={'key':'local-artwork','section_type':kind,'image_url':IMAGE,'content':content})
                self.assertEqual(status,201)
                self.assertEqual(response.json['title'],'')
                self.assertEqual(response.json['content']['image_url'],IMAGE)
    def test_missing_artwork_and_text_card_without_title_are_rejected(self):
        for body in [{'section_type':'popup'}, {'section_type':'whats_inside','content':{'display_mode':'image'}}, {'section_type':'how_its_made','image_url':IMAGE}]:
            with self.subTest(body=body):
                response,status=self.call(storefront.create_section,Database([]),data=dict(body,key='local-invalid'))
                self.assertEqual(status,400)

    def test_popup_page_and_cta_are_independent_and_retained_after_edit(self):
        for placement in ('home', 'menu', 'dashboard', 'orders', 'rewards'):
            with self.subTest(placement=placement):
                db = Database([])
                response, status = self.call(storefront.create_section, db, data={
                    'key': 'local-popup', 'section_type': 'popup', 'image_url': IMAGE,
                    'placement': placement, 'cta_url': '/faq',
                    'content': {'display_mode': 'image', 'custom_metadata': 'retained'},
                })
                self.assertEqual(status, 201)
                db.rows[0]['id'] = 'local-popup'
                response, status = self.call(lambda_fn(storefront.update_section, 'local-popup'), db,
                    data={'image_url': IMAGE, 'placement': placement, 'cta_url': '/menu', 'title': ''})
                self.assertEqual(status, 200)
                saved = response.json['content']
                self.assertEqual(saved['placement'], placement)
                self.assertEqual(saved['cta_url'], '/menu')
                self.assertEqual(saved['cta_link'], '/menu')
                self.assertEqual(saved['image_url'], IMAGE)
                self.assertEqual(saved['display_mode'], 'image')
                self.assertEqual(saved['custom_metadata'], 'retained')

    def test_process_cards_keep_independent_copy_and_destinations(self):
        db = Database([])
        for index, destination in enumerate(('/faq', '/menu')):
            response, status = self.call(storefront.create_section, db, data={
                'request_id': f'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa{index}',
                'key': f'local-process-{index}', 'section_type': 'how_its_made',
                'title': f'Step {index}', 'image_url': IMAGE, 'subtitle': f'Copy {index}',
                'cta_text': f'Explore {index}', 'cta_url': destination,
                'sort_order': index, 'content': {'eyebrow': f'Stage {index}'},
            })
            self.assertEqual(status, 201)
        self.assertEqual([row['content']['cta_url'] for row in db.rows], ['/faq', '/menu'])
        self.assertEqual([row['content']['subtitle'] for row in db.rows], ['Copy 0', 'Copy 1'])
        self.assertEqual([row['content']['eyebrow'] for row in db.rows], ['Stage 0', 'Stage 1'])
