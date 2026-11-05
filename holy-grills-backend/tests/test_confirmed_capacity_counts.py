from flask import Flask
from unittest.mock import patch
from app.routes import menu
from app.services import order_service


class Query:
    def __init__(self, table): self.table, self.filters = table, []
    def select(self,*a): return self
    def eq(self,*a): return self
    def or_(self,*a): return self
    def limit(self,*a): return self
    def single(self): return self
    @property
    def not_(self): self.negate=True; return self
    def in_(self,key,values):
        self.filters.append((key,values,getattr(self,'negate',False)));self.negate=False;return self
    def execute(self):
        if self.table=='kitchen_settings':
            return [{'value':'60'}] if not getattr(self,'one',False) else {'value':'60'}
        rows=[{'id':'paid','status':'received','payment_status':'paid'},{'id':'unpaid','status':'received','payment_status':'pending'}]
        for key,values,negate in self.filters:
            rows=[r for r in rows if ((r.get(key) in values) != negate)]
        return rows


class Db:
    def table(self,table): return Query(table)


def test_public_remaining_excludes_unpaid_but_admission_keeps_reservation_guard():
    db=Db()
    assert order_service._daily_capacity_remaining(db,'campus','2026-10-30',paid_only=True)==59
    assert order_service._daily_capacity_remaining(db,'campus','2026-10-30')==58
    assert len(order_service._window_capacity_orders(db,'campus','window','2026-10-30',paid_only=True))==1
