"""Real identity handlers with controlled Auth/DB; no provider/account deletion."""
import inspect
from unittest.mock import MagicMock,patch
import pytest
from flask import Flask,g
from app.routes import auth
app=Flask(__name__);app.config['CLOUDINARY_CLOUD_NAME']='fixture-cloud'
U='11111111-1111-4111-8111-111111111111';OTHER='22222222-2222-4222-8222-222222222222'
@pytest.mark.parametrize('url,expected',[(None,200),(f'https://res.cloudinary.com/fixture-cloud/image/upload/v1/profile_photos/{U}/photo.png',200),(f'https://res.cloudinary.com/fixture-cloud/image/upload/profile_photos/{OTHER}/photo.png',400),(f'https://res.cloudinary.com/another/image/upload/profile_photos/{U}/photo.png',400),('https://example.invalid/photo.jpg',400),({'url':'wrong'},400)])
def test_photo_binds_current_user_and_configured_cloud(url,expected):
 db=MagicMock();db.table.return_value.eq.return_value.update.return_value=[{'id':U,'photo_url':url}]
 with app.test_request_context('/',method='POST',json={'photo_url':url}),patch.object(auth,'get_user_client',return_value=db):
  g.user_id=U;response,status=inspect.unwrap(auth.update_profile_photo)()
 assert status==expected
 if expected==200:
  db.table.return_value.eq.assert_called_once_with('id',U)
  assert db.table.return_value.eq.return_value.update.call_args.args[0]['photo_url']==url
 else:db.table.assert_not_called()

@pytest.mark.parametrize('case,expected',[('missing_password',400),('unknown',404),('wrong_password',400),('balance',400),('orders',409),('order_race',409),('success',200)])
def test_account_delete_preconditions_prevent_auth_or_data_loss(case,expected):
 db=MagicMock();profile={'email':'fixture@example.invalid','full_name':'Fixture user'}
 db.table.return_value.select.return_value.eq.return_value.single.return_value.execute.side_effect=[None if case=='unknown' else profile,{'balance':500 if case=='balance' else 0}]
 db.table.return_value.select.return_value.eq.return_value.not_.in_.return_value.limit.return_value.execute.return_value=[{'id':'open'}] if case=='orders' else []
 db.rpc.return_value={'success':False,'error':'open_orders'} if case=='order_race' else {'success':True,'anonymized_at':'2026-11-15T10:00:00Z'}
 if case=='wrong_password':db.auth_sign_in.side_effect=RuntimeError('controlled invalid password')
 body={} if case=='missing_password' else {'password':'Fixture-only confirmation'}
 with app.test_request_context('/',method='DELETE',json=body),patch.object(auth,'get_db',return_value=db),patch.object(auth,'_lock_auth_account') as lock,patch.object(auth,'_revoke_all_sessions') as revoke,patch('app.services.notification_templates.render_notification_template',return_value=None):
  g.user_id=U;g.jwt_token='synthetic';response,status=inspect.unwrap(auth.delete_account)()
 assert status==expected
 if case=='success':
  lock.assert_called_once_with(U);revoke.assert_called_once_with(U,'synthetic');assert response.json['anonymized_at']=='2026-11-15T10:00:00Z'
 else:lock.assert_not_called();revoke.assert_not_called()
 if case not in ('order_race','success'):db.rpc.assert_not_called()
