from unittest.mock import MagicMock, patch
from app.services import gift_service


def test_disabled_legacy_promotion_never_reads_orders_or_writes_a_gift():
    db=MagicMock()
    with patch.object(gift_service,'get_db',return_value=db),patch.object(gift_service,'_get_setting',return_value='false'):
        assert gift_service.maybe_grant_first_order_gift('user','order')=={'granted':False,'reason':'gift_disabled'}
    db.table.assert_not_called()


def test_unavailable_legacy_settings_fail_closed_without_reward_writes():
    db=MagicMock();db.table.return_value.select.side_effect=RuntimeError('controlled settings outage')
    with patch.object(gift_service,'get_db',return_value=db):
        assert gift_service.maybe_grant_first_order_gift('user','order')['reason']=='gift_disabled'
    db.table.assert_called_once_with('system_settings')


def test_expired_legacy_promotion_never_reads_orders_or_writes_a_gift():
    db=MagicMock()
    with patch.object(gift_service,'get_db',return_value=db),patch.object(gift_service,'_get_setting',side_effect=lambda db,key,default:'true' if key=='first_order_gift_enabled' else '2020-01-01'):
        assert gift_service.maybe_grant_first_order_gift('user','order')['reason']=='launch_window_closed'
    db.table.assert_not_called()
