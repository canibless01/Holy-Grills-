from unittest.mock import patch
from app.services import notification_service as service
from app.services.engagement_campaigns import render
from app.utils.notification_brand import push_heading


def test_push_has_identifiable_title_color_icon_and_transparent_status_mark():
    with patch.dict(service.os.environ,{'FRONTEND_URL':'https://holygrills.online'}),patch.object(service,'_get_onesignal_creds',return_value=('app','key')):
        payload=service._prepare_notification_push('owner','Good morning, Kani','A new day','/menu',idempotency_key='original-key')
    assert payload['headings']['en']=='Holy Grills · Good morning, Kani'
    assert payload['contents']['en']=='A new day'
    assert payload['chrome_web_icon']=='https://holygrills.online/icons/icon-192.png'
    assert payload['firefox_icon']==payload['chrome_web_icon']
    assert payload['chrome_web_badge']=='https://holygrills.online/brand/icon-mark.png'
    assert payload['idempotency_key']=='original-key'
    assert payload['include_aliases']=={'external_id':['owner']}
    assert payload['url']=='https://holygrills.online/menu'


def test_existing_brand_is_not_repeated_and_empty_heading_is_identifiable():
    for title in ('Holy Grills · Order ready','Your Holy Grills order is coming today','HOLY GRILLS — welcome'):
        assert push_heading(title)==title
    assert push_heading(None)=='Holy Grills'


def test_personalized_campaign_preview_matches_transport_heading():
    step={'title':'Good morning, {{nickname}}','body':'Order at {{campus}}','action_url':'/menu','push_image':None}
    result=render(step,{'nickname':'Kani'},'FUTA','16:00')
    assert result['title']=='Holy Grills · Good morning, Kani'
    assert push_heading(result['title'])==result['title']
    assert result['body']=='Order at FUTA'
