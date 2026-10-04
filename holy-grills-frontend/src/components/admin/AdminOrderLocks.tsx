import React, { useState, useEffect } from 'react';
import { Lock } from 'lucide-react';
import { liveApi as mockApi } from '@/lib/liveApi';
import { formatDateTime } from '@/lib/hgUtils';
import LoadingSpinner from '@/components/LoadingSpinner';
import { Pill } from './AdminShared';

const STATUS_TONES = { active: 'green', used: 'blue', expired: 'red', cancelled: 'cocoa', redeemed: 'blue' };

// GET /order-locks/admin/all — returns every order lock across all users joined
// with the profile (full_name, email, phone). Read-only admin view; locks are
// created/cancelled by students. Filters mirror the backend's status + date params.
export default function AdminOrderLocks() {
  const [locks, setLocks] = useState([]);
  const [loading, setLoading] = useState(true);
  const [status, setStatus] = useState('');
  const [date, setDate] = useState('');

  const load = async () => {
    setLoading(true);
    try {
      const params: Record<string, unknown> = {};
      if (status) params.status = status;
      if (date) params.date = date;
      setLocks(await mockApi.admin.getOrderLocks(params));
    } catch { setLocks([]); }
    setLoading(false);
  };
  useEffect(() => { load(); }, [status, date]);

  if (loading) return <LoadingSpinner label="Loading order locks..." />;

  return (
    <div className="space-y-4">
      <div className="rounded-xl bg-muted border border-border p-3 text-xs text-muted-foreground flex items-center gap-2">
        <Lock className="w-4 h-4 text-primary shrink-0" /> Order locks let students hold a discount for a future order. Locks auto-expire; this view shows every lock across all users.
      </div>
      <div className="flex flex-col sm:flex-row gap-3">
        <select value={status} onChange={(e) => setStatus(e.target.value)} className="px-4 py-2.5 rounded-xl border border-border text-sm font-semibold text-foreground focus:outline-none focus:border-primary/60">
          <option value="">All Statuses</option>
          <option value="active">Active</option>
          <option value="used">Used</option>
          <option value="expired">Expired</option>
          <option value="cancelled">Cancelled</option>
          <option value="redeemed">Redeemed</option>
        </select>
        <input type="date" value={date} onChange={(e) => setDate(e.target.value)} className="px-4 py-2.5 rounded-xl border border-border text-sm font-semibold text-foreground focus:outline-none focus:border-primary/60" />
      </div>
      {locks.length === 0 ? (
        <div className="text-center py-12 text-muted-foreground"><Lock className="w-8 h-8 mx-auto mb-2 text-muted-foreground" /> No order locks found</div>
      ) : (
        <div className="space-y-2">
          {locks.map((l) => {
            const profile = l.profiles || l.user || {};
            const name = l.full_name || profile.full_name || l.user_name || '—';
            const email = l.email || profile.email || '';
            const phone = l.phone || profile.phone || '';
            const contact = [email, phone].filter(Boolean).join(' · ') || '—';
            return (
              <div key={l.id} className="rounded-2xl bg-white border border-border p-3 flex items-center gap-3">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="font-bold text-sm text-foreground">{name}</span>
                    <Pill tone={STATUS_TONES[l.status] || 'cocoa'}>{l.status || 'active'}</Pill>
                    {l.discount_pct != null && l.reward_type !== 'hp' && <Pill tone="flame">{l.discount_pct}% off</Pill>}
                    {l.reward_type === 'hp' && l.reward_hp_amount != null && <Pill tone="flame">{l.reward_hp_amount} HP</Pill>}
                  </div>
                  <div className="text-xs text-muted-foreground truncate">{contact}</div>
                  <div className="text-[11px] text-muted-foreground">Created {formatDateTime(l.created_at)}{l.expires_at ? ` · expires ${formatDateTime(l.expires_at)}` : ''}</div>
                </div>
                {l.order_id && <span className="text-[11px] font-mono text-muted-foreground shrink-0">#{String(l.order_id).slice(0, 8).toUpperCase()}</span>}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}