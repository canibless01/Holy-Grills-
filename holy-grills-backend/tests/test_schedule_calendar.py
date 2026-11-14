from datetime import datetime,timedelta,timezone
from unittest.mock import patch,MagicMock
from flask import Flask
from app.routes import orders

CAMPUS='11111111-1111-4111-8111-111111111111'
def test_calendar_carries_capacity_and_closed_states_for_fourteen_dates():
    today=(datetime.now(timezone.utc)+timedelta(hours=1)).date()
    def state(db,campus,for_date=None):
        date=for_date or today
        return {'date':date.isoformat(),'is_open':False,'reason':'full','any_capacity_remaining':False,
            'windows':[{'id':'window','is_full':date==today,'is_closed':False,'remaining':0 if date==today else 3,
                        'opens_at':'00:00:00','closes_at':'23:59:59'}]}
    with Flask(__name__).test_request_context('/delivery-windows/status?calendar=true'), \
         patch.object(orders,'get_user_client',return_value=MagicMock()),patch.object(orders,'get_db',return_value=MagicMock()), \
         patch('app.routes.events._get_campus_id',return_value=CAMPUS), \
         patch('app.services.order_service.get_ordering_window_status',side_effect=state), \
         patch('app.services.order_service.find_next_available_ordering_slot',return_value={'date':(today+timedelta(days=1)).isoformat(),'opens_at':'00:00:00'}):
        response,status=orders.delivery_windows_status.__wrapped__()
        calendar=response.json['calendar']
        assert status==200 and len(calendar)==14
        assert calendar[0]['any_capacity_remaining'] is False
        assert calendar[0]['windows'][0]['is_full'] is True
        assert calendar[1]['remaining']==3 and calendar[1]['windows'][0]['date']==(today+timedelta(days=1)).isoformat()
