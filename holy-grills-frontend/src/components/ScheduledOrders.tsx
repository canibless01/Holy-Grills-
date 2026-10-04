import React, { useState, useEffect } from 'react';
import { Clock, Calendar, X } from 'lucide-react';
import { mockApi } from '@/lib/mockApi';
import { formatDateTime, formatNaira } from '@/lib/hgUtils';
import { toast } from '@/components/ui/use-toast';

// GET /orders/scheduled → upcoming scheduled orders (is_scheduled=true, status=received).
// Each carries order_items + delivery_windows(label,starts_at,ends_at). Cancel uses
// DELETE /orders/<id>/scheduled (wallet refunded server-side).
export default function ScheduledOrders() {
  const [orders, setOrders] = useState([]);
  const [loading, setLoading] = useState(true);
  const [cancelling, setCancelling] = useState(null);

  const load = async () => {
    try {
      const res = await mockApi.orders.getScheduled();
      setOrders(res?.scheduled_orders || []);
    } catch { setOrders([]); }
    setLoading(false);
  };
  useEffect(() => { load(); }, []);

  const cancel = async (id) => {
    if (!confirm('Cancel this scheduled order? Your slot will be released and any wallet payment refunded.')) return;
    setCancelling(id);
    try {
      await mockApi.orders.cancelScheduled(id);
      toast({ title: 'Scheduled order cancelled' });
      await load();
    } catch (e) { toast({ title: 'Cancel failed', description: e.message, variant: 'destructive' }); }
    setCancelling(null);
  };

  if (loading || !orders.length) return null;

  return (
    <div className="space-y-2">
      <h2 className="text-xs font-bold uppercase tracking-wide text-muted-foreground flex items-center gap-1.5">
        <Calendar className="w-3.5 h-3.5" /> Scheduled Orders ({orders.length})
      </h2>
      {orders.map((o) => {
        const win = Array.isArray(o.delivery_windows) ? o.delivery_windows[0] : o.delivery_windows;
        return (
          <div key={o.id} className="rounded-2xl bg-accent/10 border border-accent/30 p-3 space-y-2">
            <div className="flex items-center justify-between">
              <span className="font-bold text-sm text-foreground">{formatDateTime(o.scheduled_for || o.created_at)}</span>
              <span className="text-[10px] font-bold text-accent-foreground bg-accent/20 px-2 py-0.5 rounded-full">Scheduled</span>
            </div>
            <div className="flex flex-wrap gap-1.5">
              {(o.order_items || []).map((it, i) => (
                <span key={i} className="text-[11px] text-foreground bg-white/60 px-2 py-1 rounded-md">{it.quantity}× {it.name_snapshot}</span>
              ))}
            </div>
            <div className="flex items-center justify-between">
              <span className="text-xs text-muted-foreground flex items-center gap-1">
                <Clock className="w-3 h-3" /> {win?.label || 'Future window'}
              </span>
              <div className="flex items-center gap-2">
                <span className="font-heading font-bold text-sm text-foreground">{formatNaira(o.total_amount)}</span>
                <button onClick={() => cancel(o.id)} disabled={cancelling === o.id} className="px-2.5 py-1 rounded-full bg-destructive/10 text-destructive text-[11px] font-bold border border-destructive/20 disabled:opacity-50 flex items-center gap-1">
                  {cancelling === o.id ? <span className="w-3 h-3 border border-destructive/40 border-t-destructive rounded-full animate-spin" /> : <X className="w-3 h-3" />} Cancel
                </button>
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}