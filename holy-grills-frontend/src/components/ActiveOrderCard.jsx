import React, { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { Package } from 'lucide-react';
import { mockApi } from '@/lib/mockApi';
import { useHolyGrill } from '@/lib/HolyGrillContext';
import { ORDER_STATUS_LABELS } from '@/lib/hgUtils';

/**
 * ActiveOrderCard — compact horizontal stat card for the Home quick-stats grid.
 * Shows the status of the user's most recent active order, or a "Start one" CTA.
 * Auth only — guests don't see it.
 */
export default function ActiveOrderCard() {
  const { isAuthenticated } = useHolyGrill();
  const [active, setActive] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!isAuthenticated) { setLoading(false); return; }
    let cancelled = false;
    const load = async () => {
      try {
        const order = await mockApi.orders.getActive();
        if (cancelled) return;
        setActive(order);
      } catch { /* ignore */ }
      if (!cancelled) setLoading(false);
    };
    load();
    return () => { cancelled = true; };
  }, [isAuthenticated]);

  if (!isAuthenticated) return null;

  const value = loading
    ? '—'
    : active
      ? (ORDER_STATUS_LABELS[active.status] || 'Active')
      : 'No order';
  const label = active ? 'Track Order' : 'Start one →';
  const to = active ? '/track-orders' : '/menu';

  return (
    <Link to={to} className="flex flex-col items-start gap-1 rounded-xl bg-card border border-border px-2.5 py-2.5 hover:border-primary/40 active:scale-95 transition">
      <Package className="w-3.5 h-3.5 text-primary" />
      <div className="font-heading font-extrabold text-base text-foreground leading-none truncate w-full">{value}</div>
      <div className="text-[10px] text-muted-foreground font-medium leading-tight truncate w-full">{label}</div>
    </Link>
  );
}