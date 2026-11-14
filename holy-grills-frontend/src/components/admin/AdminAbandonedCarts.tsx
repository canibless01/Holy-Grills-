import { useState, useEffect, useRef } from 'react';
import { ShoppingCart, RefreshCw, Search, Bell } from 'lucide-react';
import { useCampus } from '@/lib/campusContext';
import { liveApi } from '@/lib/liveApi';
import { formatNaira, formatDateTime } from '@/lib/hgUtils';
import StaffPanelSkeleton from '@/components/skeletons/StaffPanelSkeleton';
import { toast } from '@/components/ui/use-toast';
import { msg } from '@/lib/messages';

const STATUS_TONE = {
  pending: 'tone-warn',
  pending_unrecovered: 'tone-warn',
  recovered: 'tone-success',
  exhausted: 'bg-secondary text-foreground',
  cleared: 'bg-secondary text-muted-foreground',
};

/**
 * AdminAbandonedCarts — retention panel for carts left at checkout. Lists
 * every cart the cron job flagged, lets admins search/filter by status, see
 * the snapshot of items, and queue a due member reminder or guest checkout email.
 * Rider/kitchen have no part in this flow — admin + system only.
 *
 * Backend: GET /admin/abandoned-carts, POST /admin/abandoned-carts/:id/nudge.
 */
export default function AdminAbandonedCarts() {
  const { adminCampusId } = useCampus();
  const generation = useRef(0);
  const [carts, setCarts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [statusFilter, setStatusFilter] = useState('all');
  const [q, setQ] = useState('');
  const [busy, setBusy] = useState(null);

  const load = async () => {
    const request = ++generation.current;
    setLoading(true); setError('');
    try { const rows = await liveApi.admin.getAbandonedCarts(); if (request === generation.current) setCarts(rows); } catch (e) { if (request === generation.current) setError(e.message || 'Could not load carts. Please retry.'); }
    if (request === generation.current) setLoading(false);
  };
  useEffect(() => { setCarts([]); load(); return () => { generation.current++; }; }, [adminCampusId]);

  const filtered = carts.filter((c) => {
    const okStatus = statusFilter === 'all' || (c.is_recovered ? 'recovered' : 'pending') === statusFilter;
    const name = [c.profiles?.full_name, c.profiles?.email, c.user?.name, c.user?.email, c.user_name, c.user_email, c.guest_email, c.guest_phone].filter(Boolean).join(' ').toLowerCase();
    const okQ = !q || name.includes(q.toLowerCase());
    return okStatus && okQ;
  });

  const nudge = async (id) => {
    setBusy(id);
    try { await liveApi.admin.nudgeAbandonedCart(id); toast({ title: msg('FE_ADMIN_ABANDONED_CARTS_RECOVERY_NUDGE_SENT', '🔔 Reminder queued') }); await load(); }
    catch (e) { toast({ title: msg('FE_ADMIN_ABANDONED_CARTS_NUDGE_FAILED', 'Nudge failed'), description: e.message, variant: 'destructive' }); }
    setBusy(null);
  };

  if (loading) return <StaffPanelSkeleton />;

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2 flex-wrap">
        <div className="relative flex-1 min-w-[180px]">
          <Search className="absolute left-3 top-1/2 w-4 h-4 -translate-y-1/2 text-muted-foreground" />
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search by name or email" className="w-full pl-9 pr-3 py-2 rounded-xl border border-border text-sm" />
        </div>
        <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)} className="p-2 rounded-xl border border-border text-sm">
          <option value="all">All statuses</option>
          <option value="pending">Pending</option>

          <option value="recovered">Recovered</option>
          <option value="exhausted">Exhausted</option>
          <option value="cleared">Cleared</option>
        </select>
        <button onClick={load} className="p-2 rounded-xl border border-border"><RefreshCw className="w-4 h-4 text-muted-foreground" /></button>
      </div>

      {error && <p role="alert" className="rounded-xl bg-destructive/10 p-3 text-destructive">{error}</p>}
      {!error && filtered.length === 0 ? (
        <div className="text-center py-10 text-muted-foreground">
          <ShoppingCart className="w-10 h-10 mx-auto mb-2 text-muted-foreground" />
          No abandoned carts found.
        </div>
      ) : (
        <div className="space-y-2">
          {filtered.map((c) => {
            const items = c.cart_payload?.items || c.items || c.cart_items || c.snapshot || [];
            const phone = c.profiles?.phone || c.guest_phone;
            const digits = (phone || '').replace(/\D/g, '').replace(/^0(?=\d{10}$)/, '234');
            const userName = c.profiles?.full_name || c.user?.name || c.user_name || 'User';
            return (
              <div key={c.id} className="rounded-2xl bg-card border border-border p-4">
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="font-bold text-sm text-foreground truncate">{userName}</span>
                      <span className={`text-[10px] font-bold px-2 py-0.5 rounded-full capitalize ${STATUS_TONE[c.status] || 'bg-secondary text-muted-foreground'}`}>{c.is_recovered ? 'recovered' : 'pending'}</span>
                    </div>
                    <div className="text-xs text-muted-foreground truncate">{c.profiles?.email || c.guest_email || c.user?.email || c.user_email}</div>
                    <div className="text-xs">{phone && <><a href={`tel:${phone}`}>{phone}</a> · <button onClick={() => navigator.clipboard.writeText(phone).catch(() => toast({ title: 'Copy unavailable; select the phone number.' }))}>Copy</button> · <a href={`https://wa.me/${digits}`} target="_blank" rel="noopener noreferrer">WhatsApp</a></>}</div>
                    <div className="text-[11px] text-muted-foreground">Last active {formatDateTime(c.last_active_at || c.updated_at || c.created_at)}</div>
                  </div>
                  <div className="text-right shrink-0">
                    <div className="font-heading font-bold text-foreground">{c.subtotal != null || c.total != null ? formatNaira(c.subtotal ?? c.total) : 'View checkout details'}</div>
                    <div className="text-[10px] text-muted-foreground">{c.saved_nudges ?? '—'} reminder{c.saved_nudges === 1 ? '' : 's'} saved</div>
                    <div className="text-[10px] text-muted-foreground">Email accepted: {c.email_accepted ?? '—'} · Push accepted: {c.push_accepted ?? '—'}</div>
                    {c.delivery_issues > 0 && <div className="text-[10px] text-destructive">Delivery needs review</div>}
                  </div>
                </div>
                {items.length > 0 && (
                  <div className="mt-2 flex flex-wrap gap-1.5">
                    {items.map((it, i) => (
                      <span key={i} className="text-[11px] px-2 py-0.5 rounded-full bg-muted text-foreground">
                        {it.quantity || 1}× {it.name_snapshot || it.name || it.menu_item_name || 'Item'}
                      </span>
                    ))}
                  </div>
                )}
                {(!c.is_recovered && (c.user_id || c.guest_email)) && (
                  <div className="mt-3 flex gap-2">
                    <button onClick={() => nudge(c.id)} disabled={busy === c.id} className="flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-primary text-white text-xs font-bold disabled:opacity-50">
                      <Bell className="w-3.5 h-3.5" /> {busy === c.id ? 'Queuing…' : 'Queue reminder'}
                    </button>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
