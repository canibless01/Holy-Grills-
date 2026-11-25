"""HP period flows are not current balances; pending awards never count as active."""
def period_totals(rows):
    active=[r for r in rows if r.get('status') in (None,'active')]
    earned=sum(int(t.get('amount') or 0) for t in active if t.get('type')=='earn' and t.get('source')!='hp_transfer_received')
    spent=sum(int(t.get('amount') or 0) for t in active if t.get('type')=='spend' and t.get('source')!='hp_transfer_sent')
    return {'hp_earned_active':earned,'hp_spent':spent,
            'hp_expired':sum(int(t.get('amount') or 0) for t in rows if t.get('type')=='expire'),
            'hp_pending':sum(int(t.get('amount') or 0) for t in rows if t.get('type')=='earn' and t.get('status')=='pending'),
            'hp_transfer_received':sum(int(t.get('amount') or 0) for t in active if t.get('source')=='hp_transfer_received'),
            'hp_transfer_sent':sum(int(t.get('amount') or 0) for t in active if t.get('source')=='hp_transfer_sent'),
            'redemption_rate':round(spent/earned*100,1) if earned else 0}
