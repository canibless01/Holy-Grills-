"""Storefront contracts: public publication windows, saved slots and safe retries."""
import copy
import os
import unittest
from unittest.mock import patch
from flask import Flask, g
for name in ('SUPABASE_URL', 'SUPABASE_ANON_KEY', 'SUPABASE_SERVICE_ROLE_KEY', 'JWT_SECRET', 'SECRET_KEY'):
    os.environ.setdefault(name, 'https://example.supabase.co' if name == 'SUPABASE_URL' else 'test')
from app.routes import storefront, uploads
from app.db import SupabaseError
from app.utils.upload_urls import is_cms_image_url

IMAGE = 'https://res.cloudinary.com/test-cloud/image/upload/v1/banners/main.png'
SECOND = IMAGE.replace('main.png', 'second.png')
THIRD = IMAGE.replace('main.png', 'third.png')

class Query:
    def __init__(self, db):
        self.db, self.filters, self.one = db, {}, False
    def select(self, *_): return self
    def eq(self, key, value): self.filters[key] = value; return self
    def order(self, *_, **__): return self
    def limit(self, *_): return self
    def is_(self, key, value): return self.eq(key, None if value == 'null' else value)
    def single(self): self.one = True; return self
    def execute(self):
        rows = [copy.deepcopy(row) for row in self.db.rows if all(row.get(k) == (True if v == 'true' else v) for k, v in self.filters.items())]
        return (rows[0] if rows else None) if self.one else rows
    def insert(self, payload):
        if any(row.get('id') == payload.get('id') for row in self.db.rows):
            raise SupabaseError('duplicate', 409, {'code':'23505'})
        self.db.rows.append(copy.deepcopy(payload))
        return [copy.deepcopy(payload)]
    def update(self, update):
        if self.db.conflict:
            raise SupabaseError('duplicate', 409, {'code':'23505'})
        if self.db.race:
            self.db.race = False
            self.db.rows[0]['images'].append(THIRD)
            self.db.rows[0]['updated_at'] = 'concurrent-edit'
            return []
        changed = []
        for row in self.db.rows:
            if all(row.get(k) == v for k, v in self.filters.items()):
                row.update(update); changed.append(copy.deepcopy(row))
        return changed

class Database:
    def __init__(self, rows): self.rows, self.race, self.conflict = rows, False, False
    def table(self, _): return Query(self)

class StorefrontContractTests(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.config.update(CLOUDINARY_CLOUD_NAME='test-cloud', CLOUDINARY_API_KEY='test-key', CLOUDINARY_API_SECRET='test-secret')
    def call(self, fn, db, path='/', data=None, role='admin', campus='a'):
        with self.app.test_request_context(path, json=data):
            g.user_role, g.campus_id, g.user_id = role, campus, 'actor'
            with patch.object(storefront, 'get_user_client', return_value=db), patch.object(storefront, '_get_campus_id', return_value=campus):
                return fn.__wrapped__()
    def test_type_filter_and_super_admin_all_scope(self):
        rows=[{'id':'a','section_type':'our_story','is_active':True,'campus_id':'a'}, {'id':'b','section_type':'testimonial','is_active':True,'campus_id':'b'}]
        response,status=self.call(storefront.list_sections, Database(rows), '/?section_type=our_story')
        self.assertEqual([r['id'] for r in response.json], ['a'])
        response,status=self.call(storefront.list_sections, Database(rows), '/?include_inactive=1', role='super_admin', campus=None)
        self.assertEqual(len(response.json), 2)
    def test_share_slot_key_is_saved_and_duplicate_is_conflict(self):
        db=Database([{'id':'s','section_type':'share_template','content':{},'key':'general'}])
        response,status=self.call(lambda_fn(storefront.update_section,'s'),db,data={'key':'order_share'})
        self.assertEqual((status,response.json['key']), (200,'order_share'))
        db.conflict=True
        response,status=self.call(lambda_fn(storefront.update_section,'s'),db,data={'key':'occupied'})
        self.assertEqual(status,409)
    def test_public_banner_dates_apply_even_to_admin(self):
        db=Database([{'id':'future','is_active':True,'starts_at':'2099-01-01T00:00:00Z','campus_id':'a'}, {'id':'expired','is_active':True,'ends_at':'2000-01-01T00:00:00Z','campus_id':'a'}, {'id':'current','is_active':True,'campus_id':'a'}])
        response,status=self.call(storefront.list_banners,db)
        self.assertEqual([r['id'] for r in response.json],['current'])
        response,status=self.call(storefront.list_banners,db,'/?include_inactive=1')
        self.assertEqual(len(response.json),3)
    def test_append_retries_preserve_concurrent_slide_and_deduplicate(self):
        db=Database([{'id':'b','campus_id':'a','image_url':IMAGE,'images':[IMAGE],'updated_at':'original'}]);db.race=True
        response,status=self.call(lambda_fn(storefront.update_banner_image,'b'),db,data={'image_url':SECOND})
        self.assertEqual((status,db.rows[0]['images']),(200,[IMAGE,THIRD,SECOND]))
        response,status=self.call(lambda_fn(storefront.update_banner_image,'b'),db,data={'image_url':SECOND})
        self.assertEqual(len(db.rows[0]['images']),3)
        self.assertEqual(db.rows[0]['image_url'],IMAGE)
    def test_campus_admin_cannot_append_to_global_banner(self):
        db=Database([{'id':'b','campus_id':None,'image_url':IMAGE,'images':[IMAGE],'updated_at':'original'}])
        response,status=self.call(lambda_fn(storefront.update_banner_image,'b'),db,data={'image_url':SECOND})
        self.assertEqual(status,403);self.assertEqual(db.rows[0]['images'],[IMAGE])
    def test_main_image_replacement_reaches_rendered_carousel(self):
        db=Database([{'id':'b','campus_id':'a','image_url':IMAGE,'images':[IMAGE,SECOND],'updated_at':'original'}])
        response,status=self.call(lambda_fn(storefront.update_banner,'b'),db,data={'image_url':THIRD})
        self.assertEqual((status,response.json['images']), (200,[THIRD,SECOND]))
    def test_invalid_ratings_and_fractional_sort_are_rejected(self):
        with self.app.test_request_context():
            for value in (True,0,6,1.5,'not-a-rating'):
                with self.subTest(value=value):
                    self.assertEqual(storefront._section_validation({'rating':value},'testimonial')[1],400)
            with self.assertRaises(ValueError):storefront._parse_int(1.5)
    def test_create_response_loss_recovers_original_row_and_conflicts_fail(self):
        db=Database([])
        with self.app.test_request_context():
            g.user_id='actor'
            intent={'request_id':'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'}
            body={'title':'Banner','campus_id':'a','image_url':IMAGE}
            response,status=storefront._insert_cms(db,'banners',body,intent)
            self.assertEqual(status,201)
            response,status=storefront._insert_cms(db,'banners',body,intent)
            self.assertEqual(status,200);self.assertEqual(len(db.rows),1)
            response,status=storefront._insert_cms(db,'banners',dict(body,title='Changed'),intent)
            self.assertEqual(status,409);self.assertEqual(db.rows[0]['title'],'Banner')
    def test_stale_slide_editor_is_rejected_and_last_removal_stays_empty(self):
        db=Database([{'id':'b','campus_id':'a','image_url':IMAGE,'images':[IMAGE],'updated_at':'new'}])
        response,status=self.call(lambda_fn(storefront.update_banner,'b'),db,data={'images':[], 'expected_updated_at':'old'})
        self.assertEqual(status,409);self.assertEqual(db.rows[0]['images'],[IMAGE])
        response,status=self.call(lambda_fn(storefront.update_banner,'b'),db,data={'images':[], 'expected_updated_at':'new'})
        self.assertEqual((status,response.json['images'],response.json['image_url']),(200,[],''))
    def test_banner_window_rejects_reversed_and_unzoned_dates(self):
        with self.app.test_request_context():
            self.assertEqual(storefront._banner_window_error({'starts_at':'2099-01-02T00:00:00Z','ends_at':'2099-01-01T00:00:00Z'})[1],400)
            self.assertEqual(storefront._banner_fields({'starts_at':'2099-01-01T00:00:00'})[1][1],400)
            self.assertIsNone(storefront._banner_window_error({'starts_at':'2099-01-01T00:00:00Z','ends_at':'2099-01-02T00:00:00Z'}))
    def test_campus_section_overrides_global_only_for_public_read(self):
        db=Database([{'id':'global','key':'tier_icon_ember','section_type':'tier_icon','is_active':True,'campus_id':None}, {'id':'local','key':'tier_icon_ember','section_type':'tier_icon','is_active':True,'campus_id':'a'}])
        response,status=self.call(storefront.list_sections,db)
        self.assertEqual([row['id'] for row in response.json],['local'])
        response,status=self.call(storefront.list_sections,db,'/?include_inactive=1')
        self.assertEqual(len(response.json),2)
    def test_cloudinary_url_validation_does_not_throw_on_invalid_input(self):
        with self.app.test_request_context():
            self.assertTrue(is_cms_image_url(IMAGE))
            for url in ('https://[invalid','https://res.cloudinary.com/other/image/upload/a.png',IMAGE.replace('/upload/','/fetch/'),IMAGE.replace('/banners/','/../other/'),IMAGE.replace('res.cloudinary.com','user@res.cloudinary.com')):
                with self.subTest(url=url):self.assertFalse(is_cms_image_url(url))
    def test_admin_unsubscribe_is_scoped_and_replays_without_restamping(self):
        db=Database([{'id':'n','email':'audit@example.invalid','campus_id':'a','unsubscribed_at':None}])
        response,status=self.call(storefront.admin_newsletter_unsubscribe,db,data={'email':'audit@example.invalid'})
        self.assertEqual(status,200);stamp=db.rows[0]['unsubscribed_at'];self.assertTrue(stamp)
        response,status=self.call(storefront.admin_newsletter_unsubscribe,db,data={'email':'audit@example.invalid'})
        self.assertEqual(status,200);self.assertEqual(db.rows[0]['unsubscribed_at'],stamp)
        response,status=self.call(storefront.admin_newsletter_unsubscribe,db,data={'email':'audit@example.invalid'},campus='b')
        self.assertEqual(status,404)
    def test_newsletter_unsubscribe_headers_are_in_email_payload(self):
        from app.utils.email import send_email_raw
        mail_headers={'List-Unsubscribe':'<https://example.test/unsubscribe>', 'List-Unsubscribe-Post':'List-Unsubscribe=One-Click'}
        with patch('app.utils.email._resend_api_key',return_value='test-key'),patch('app.utils.email.requests.post') as post:
            post.return_value.status_code=200
            self.assertTrue(send_email_raw('audit@example.invalid','Audit','Subject','<p>Body</p>',headers=mail_headers))
            sent=post.call_args.kwargs
            self.assertEqual(sent['json']['headers'],mail_headers)
            self.assertNotIn('List-Unsubscribe',sent['headers'])
    def test_independent_slide_copy_is_saved_with_legacy_columns(self):
        slides=[{'image_url':IMAGE,'title':'First','eyebrow':'One','subtitle':'Copy 1','cta_text':'Read','cta_url':'/faq'},
                {'image_url':SECOND,'title':'Second','eyebrow':'Two','subtitle':'Copy 2','cta_text':'Menu','cta_url':'/menu'}]
        db=Database([{'id':'b','metadata':{},'image_url':IMAGE,'images':[IMAGE],'updated_at':'v1'}])
        response,status=self.call(lambda_fn(storefront.update_banner,'b'),db,data={'metadata':{'slides':slides},'expected_updated_at':'v1'})
        self.assertEqual(status,200)
        self.assertEqual(response.json['images'],[IMAGE,SECOND])
        self.assertEqual(response.json['action_url'],'/faq')
        self.assertEqual(response.json['metadata']['slides'][1]['cta_url'],'/menu')
        response,status=self.call(lambda_fn(storefront.update_banner,'b'),db,data={'metadata':{'slides':slides},'expected_updated_at':'v1'})
        self.assertEqual(status,409)
    def test_slide_payload_rejects_unsafe_media_and_unpaired_actions(self):
        invalid=[{'title':'Good','image_url':IMAGE,'cta_text':'Missing destination'},
                 {'title':'Good','image_url':IMAGE,'cta_text':'Bad','cta_url':'javascript:alert(1)'},
                 {'title':'Good','image_url':'https://example.test/image.png'},
                 {'title':{},'image_url':IMAGE}]
        for row in invalid:
            response,status=self.call(lambda_fn(storefront.update_banner,'b'),Database([]),data={'metadata':{'slides':[row]}})
            self.assertEqual(status,400)
    def test_legacy_image_append_preserves_configured_slide_copy(self):
        first={'image_url':IMAGE,'title':'First','eyebrow':'One','cta_text':'Read','cta_url':'/faq'}
        db=Database([{'id':'b','campus_id':'a','metadata':{'slides':[first]},'image_url':IMAGE,'images':[IMAGE],'title':'First','updated_at':'v1'}])
        response,status=self.call(lambda_fn(storefront.update_banner_image,'b'),db,data={'image_url':SECOND})
        self.assertEqual(status,200)
        self.assertEqual(db.rows[0]['metadata']['slides'][0],first)
        self.assertEqual(db.rows[0]['metadata']['slides'][1]['image_url'],SECOND)

    def test_contact_email_stays_global_and_whatsapp_requires_own_campus(self):
        rows=[{'key':'support_email','value':'global@example.invalid','campus_id':None,'is_public':True},
              {'key':'support_email','value':'campus@example.invalid','campus_id':'a','is_public':True},
              {'key':'whatsapp_support_number','value':'2348010000011','campus_id':'a','is_public':True},
              {'key':'whatsapp_support_number','value':'2348010000099','campus_id':None,'is_public':True}]
        with patch.object(storefront, 'get_db', return_value=Database([])):
            response,status=self.call(storefront.get_public_config,Database(rows),campus='a')
            self.assertEqual(status,200)
            self.assertEqual(response.json['global_support_email'],'global@example.invalid')
            self.assertEqual(response.json['whatsapp_support_number'],'2348010000011')
            response,status=self.call(storefront.get_public_config,Database(rows),campus='b')
            self.assertEqual(response.json['whatsapp_support_number'],'')
            self.assertEqual(response.json['global_support_email'],'global@example.invalid')

    def test_legacy_copy_edit_keeps_other_slide_configuration(self):
        slides=[{'image_url':IMAGE,'title':'First','eyebrow':'One'}, {'image_url':SECOND,'title':'Second','eyebrow':'Two'}]
        db=Database([{'id':'b','metadata':{'slides':slides},'image_url':IMAGE,'images':[IMAGE,SECOND],'updated_at':'v1'}])
        response,status=self.call(lambda_fn(storefront.update_banner,'b'),db,data={'title':'Revised','eyebrow':'New eyebrow'})
        self.assertEqual(status,200)
        self.assertEqual(response.json['metadata']['slides'][0]['title'],'Revised')
        self.assertEqual(response.json['metadata']['slides'][0]['eyebrow'],'New eyebrow')
        self.assertEqual(response.json['metadata']['slides'][1],slides[1])

    def test_signature_rejects_non_objects_and_unsafe_folders(self):
        for data in ([],{'folder':{}},{'folder':'banners&timestamp=0'}):
            with self.subTest(data=data),self.app.test_request_context(json=data):
                g.user_role,g.user_id='admin','actor'
                response,status=uploads.upload_signature.__wrapped__()
                self.assertEqual(status,400)
        with self.app.test_request_context(json={'folder':'banners'}):
            g.user_role,g.user_id='student','actor'
            response,status=uploads.upload_signature.__wrapped__()
            self.assertEqual((status,response.json['folder']), (200,'profile_photos/actor'))

def lambda_fn(fn, argument):
    class Bound:
        @staticmethod
        def __wrapped__(): return fn.__wrapped__(argument)
    return Bound
