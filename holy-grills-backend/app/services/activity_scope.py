"""Read-only customer reporting scope; never wrap management or mutation clients."""
from app.db import get_user_client

REPORTING_TABLES = frozenset({
    'orders', 'order_items', 'profiles', 'wallet_transactions', 'hp_transactions',
    'abandoned_carts', 'first_order_gifts', 'marketplace_purchases',
    'redemption_cost_log', 'referrals', 'event_tickets', 'event_checkins',
})

class ReportingClient:
    def __init__(self, client):
        self.client = client

    def table(self, name):
        return self.client.table('reporting_' + name if name in REPORTING_TABLES else name)

    def __getattr__(self, name):
        return getattr(self.client, name)


def get_reporting_client(*args, **kwargs):
    return ReportingClient(get_user_client(*args, **kwargs))
