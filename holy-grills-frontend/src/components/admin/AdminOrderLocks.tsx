import { useState, useEffect } from 'react';
import { Lock } from 'lucide-react';
import { liveApi as mockApi } from '@/lib/liveApi';
import { formatDateTime } from '@/lib/hgUtils';
import StaffPanelSkeleton from '@/components/skeletons/StaffPanelSkeleton';
import { msg, useMessages } from '@/lib/messages';
import { Pill } from './AdminShared';

const STATUS_TONES = { active: 'green', used: 'blue', expired: 'red', cancelled: 'cocoa', redeemed: 'blue' };

// GET /order-locks/admin/all — returns every order lock across all users joined
// with the profile (full_name, email, phone). Read-only admin view; locks are
// created/cancelled by students. Filters mirror the backend's status + date params.
export default function AdminOrderLocks() {
  useMessages();
  const [locks, setLocks] = useState([]);
  const [loading, setLoading] = useState(true);
  const [status, setStatus] = useState('');
  const [date, setDate] = useState('');
  const [error, setError] = useState<string | null>(null);

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const params: Record<string, unknown> = {};
      if (status) params.status = status;
      if (date) params.date = date;
      setLocks(await mockApi.admin.getOrderLocks(params));
    } catch (e) { setError(e.message || msg('FE_ADMIN_LOCKS_LOAD_FAILED', 'Order locks could not be loaded. Please retry.')); }
    setLoading(false);
  };
  useEffect(() => { load(); }, [status, date]);

  if (loading) return <StaffPanelSkeleton />;

  return (
    <div className="space-y-4">
      <div className="rounded-xl bg-muted border border-border p-3 text-xs text-muted-foreground flex items-center gap-2">
        <Lock className="w-4 h-4 text-primary shrink-0" /> {msg('FE_ADMIN_LOCKS_SCOPE', 'View customer locks for the selected campus. Each lock reserves a discount or HP reward for an order placed on its locked date.')}
      </div>
      <div className="flex flex-col sm:flex-row gap-3">
        <select aria-label={msg('FE_ADMIN_LOCKS_STATUS', 'Lock status')} value={status} onChange={(e) => setStatus(e.target.value)} className="px-4 py-2.5 rounded-xl border border-border text-sm font-semibold text-foreground focus:outline-none focus:border-primary/60">
          <option value="">All Statuses</option>
          <option value="active">Active</option>
          <option value="used">Used</option>
          <option value="expired">Expired</option>
          <option value="cancelled">Cancelled</option>
        </select>
        <input aria-label={msg('FE_ADMIN_LOCKS_DATE', 'Locked date')} type="date" value={date} onChange={(e) => setDate(e.target.value)} className="px-4 py-2.5 rounded-xl border border-border text-sm font-semibold text-foreground focus:outline-none focus:border-primary/60" />
      </div>
      {error ? <div role="alert" className="rounded-xl border border-destructive/30 p-4 text-sm text-destructive">{error} <button className="font-bold underline" onClick={load}>{msg('FE_ADMIN_LOCKS_RETRY', 'Retry')}</button></div> : locks.length === 0 ? (
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
              <div key={l.id} className="rounded-2xl bg-card border border-border p-3 flex items-center gap-3">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="font-bold text-sm text-foreground">{name}</span>
                    <Pill tone={STATUS_TONES[l.status] || 'cocoa'}>{l.status || 'active'}</Pill>
                    {l.discount_pct != null && l.reward_type !== 'hp' && <Pill tone="flame">{l.discount_pct}% off</Pill>}
                    {l.reward_type === 'hp' && l.reward_hp_amount != null && <Pill tone="flame">{l.reward_hp_amount} HP</Pill>}
                  </div>
                  <div className="text-xs text-muted-foreground truncate">{contact}</div>
                  <div className="text-xs font-semibold text-foreground">{msg('FE_ADMIN_LOCKS_TARGET_DATE', 'Locked for {date}', { date: l.locked_date || '—' })}</div>
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