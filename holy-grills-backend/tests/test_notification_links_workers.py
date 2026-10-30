import ast
import copy
from pathlib import Path
import unittest
import uuid
from unittest.mock import patch, MagicMock
from app.services import notification_service as service
from app.tasks.celery_app import celery_app
from app.routes.admin import _CRON_INTERVAL_MINUTES

class NotificationLinksWorkersTests(unittest.TestCase):
    def test_all_literal_app_notification_types_have_a_destination(self):
        for path in (Path(__file__).parents[1]/'app').rglob('*.py'):
            tree=ast.parse(path.read_text())
            for node in ast.walk(tree):
                if not isinstance(node,ast.Call): continue
                name=node.func.id if isinstance(node.func,ast.Name) else getattr(node.func,'attr','')
                if name!='send_notification': continue
                kind=next((k.value for k in node.keywords if k.arg=='notif_type'),None)
                if kind is None and len(node.args)>1: kind=node.args[1]
                if isinstance(kind,ast.Constant) and isinstance(kind.value,str):
                    self.assertIsNotNone(service.default_action_url(kind.value,{'order_id':'order'}),f'{path.name}: {kind.value}')

    def test_order_and_cart_and_staff_destinations_are_specific(self):
        for kind,expected in [('order_ready','/orders/order'),('gift_rider_assigned','/orders/order'),('abandoned_cart_reminder','/cart'),('order_streak','/streak'),('order_lock_ready','/order-locks'),('gift_campaign_granted','/rewards'),('low_stock_ingredient','/admin?section=store'),('webhook_failure','/admin?section=webhooks')]:
            self.assertEqual(service.default_action_url(kind,{'order_id':'order'}),expected)
        self.assertEqual(service.default_action_url('order_ready'),'/orders')

    def test_os_push_uses_absolute_safe_urls(self):
        with patch.dict(service.os.environ,{'FRONTEND_URL':'https://holygrills.online'}):
            self.assertEqual(service._push_action_url('/cart?reminder=1'),'https://holygrills.online/cart?reminder=1')
            self.assertEqual(service._push_action_url('https://example.com/promo'),'https://example.com/promo')
            for value in ('//evil.invalid','/\\evil.invalid','javascript:alert(1)','https://[invalid','http://evil.invalid','https://u:p@example.com',None):
                self.assertIsNone(service._push_action_url(value))

    def test_transport_retries_reuse_one_uuid_key(self):
        import requests
        seen=[]
        def post(*args,**kwargs):
            seen.append(copy.deepcopy(kwargs['json']))
            if len(seen)==1: raise requests.Timeout('uncertain')
            return MagicMock(status_code=200)
        with patch.object(service,'_get_onesignal_creds',return_value=('app','key')),patch.object(service.http_requests,'post',side_effect=post),patch('app.utils.retry.time.sleep'):
            service._dispatch_push_async('user','Title','Body',None,'receipt')
        self.assertEqual(len(seen),2);self.assertEqual(seen[0]['idempotency_key'],seen[1]['idempotency_key']);self.assertEqual(uuid.UUID(seen[0]['idempotency_key']).version,4)

    def test_browser_push_carries_the_public_brand_icon(self):
        with patch.dict(service.os.environ,{'FRONTEND_URL':'https://holygrills.online'}),patch.object(service,'_get_onesignal_creds',return_value=('app','key')),patch.object(service,'_onesignal_post',return_value=MagicMock(status_code=200)) as post:
            service._dispatch_push_async('user','Title','Body','/orders/full-id','receipt')
        payload=post.call_args.kwargs['payload']
        self.assertEqual(payload['chrome_web_icon'],'https://holygrills.online/icons/icon-192.png')
        self.assertEqual(payload['url'],'https://holygrills.online/orders/full-id')

    def test_worker_schedule_targets_registered_tasks_once(self):
        celery_app.loader.import_default_modules()
        scheduled=[entry['task'] for entry in celery_app.conf.beat_schedule.values()]
        self.assertEqual(len(scheduled),len(set(scheduled)))
        for name in scheduled: self.assertIn(name,celery_app.tasks)
        self.assertIn('app.tasks.scheduled.sweep_pending_squad_hp',scheduled)
        self.assertNotIn('app.tasks.scheduled.send_scheduled_notifications',scheduled)
        self.assertNotIn('send-scheduled-notifications',_CRON_INTERVAL_MINUTES)
        self.assertIn('sweep-pending-squad-hp',_CRON_INTERVAL_MINUTES)
        self.assertEqual(celery_app.conf.timezone,'Africa/Lagos')
