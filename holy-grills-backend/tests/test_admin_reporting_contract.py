"""Actual reporting handlers: boundary dates, scope, and CSV output; no live data."""
import csv
import io
from unittest.mock import MagicMock, patch
import pytest
from flask import Flask, g
from app.routes import analytics, admin_economics

A='11111111-1111-4111-8111-111111111111'
B='22222222-2222-4222-8222-222222222222'
app=Flask(__name__)

@pytest.mark.parametrize('dates',[('2026-11-06','2026-11-05'),('2026-02-30','2026-03-01'),('2026-11-05','9999-12-31'),('0001-01-01','0001-01-01')])
def test_invalid_windows_are_rejected_by_both_reporting_families(dates):
    with pytest.raises(ValueError):analytics._wat_window(*dates)
    with app.test_request_context('/?start_date='+dates[0]+'&end_date='+dates[1]),pytest.raises(ValueError):admin_economics._econ_window()

def test_both_windows_use_inclusive_wat_days_and_exclusive_utc_end():
    expected=('2026-11-04T23:00:00+00:00','2026-11-05T23:00:00+00:00')
    assert analytics._wat_window('2026-11-05','2026-11-05')==expected
    with app.test_request_context('/?start_date=2026-11-05&end_date=2026-11-05'):assert admin_economics._econ_window()==expected

@pytest.mark.parametrize('role,campus,expected',[('admin',B,A),('super_admin',B,B),('super_admin','',None)])
def test_economics_forwards_scoped_campus_and_dates(role,campus,expected):
    with app.test_request_context('/?start_date=2026-11-05&end_date=2026-11-05&campus_id='+campus),patch.object(admin_economics,'get_user_client') as db,patch.object(admin_economics.economics_dashboard_service,'get_economics_overview',return_value={'food_revenue':123}) as service:
        g.user_role=role;g.campus_id=A
        response,status=admin_economics.economics_overview.__wrapped__()
        assert status==200 and response.json['food_revenue']==123
        assert service.call_args.args[1:]==('2026-11-04T23:00:00+00:00','2026-11-05T23:00:00+00:00',expected)
        db.assert_called_once_with(paginate=True)

def test_bad_export_limit_never_queries_any_table():
    with app.test_request_context('/?type=orders&limit=bad'),patch.object(analytics,'get_user_client') as client:
        _,status=analytics.export_csv.__wrapped__()
        assert status==400;client.return_value.table.assert_not_called()

def test_csv_export_applies_scope_bounds_limit_and_formula_protection():
    db=MagicMock();q=db.table.return_value
    for name in ('select','gte','lt','eq','order'):getattr(q,name).return_value=q
    q.execute.return_value=[{'id':'first','guest_phone':'=HYPERLINK("evil")','total_amount':100},{'id':'second','total_amount':200}]
    with app.test_request_context('/?type=orders&from_date=2026-11-05&to_date=2026-11-05&limit=1&campus_id='+B),patch.object(analytics,'get_user_client',return_value=db):
        g.user_role='admin';g.campus_id=A
        response=analytics.export_csv.__wrapped__()
        rows=list(csv.DictReader(io.StringIO(response.get_data(as_text=True))))
        assert len(rows)==1 and rows[0]['id']=='first' and rows[0]['guest_phone'].startswith("'=")
        q.eq.assert_called_once_with('campus_id',A)
        q.gte.assert_called_once_with('created_at','2026-11-04T23:00:00+00:00')
        q.lt.assert_called_once_with('created_at','2026-11-05T23:00:00+00:00')
