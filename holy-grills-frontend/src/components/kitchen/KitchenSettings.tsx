import { Package, ShieldCheck } from 'lucide-react';
import { Link } from 'react-router-dom';
import { msg } from '@/lib/messages';

/** Read the same capacity and window status used by checkout. */
export default function KitchenSettings({ settings, capacity, windowStatus, canManageSettings = false }) {
  const dailyCap = capacity?.daily_order_capacity ?? settings?.daily_order_capacity;
  const hasLimit = dailyCap != null && Number(dailyCap) >= 0;
  const usagePct = hasLimit && Number(dailyCap) > 0 ? Math.min(100, ((capacity?.orders_today ?? 0) / Number(dailyCap)) * 100) : 0;
  return <div className="space-y-3">
    <div className="flex items-center gap-2 rounded-2xl bg-card border border-border px-3.5 py-2.5">
      <ShieldCheck className="w-4 h-4 text-muted-foreground shrink-0" />
      <span className="text-xs font-semibold">{msg('FE_KITCHEN_SETTINGS_READONLY', 'Admin-managed · read-only')}</span>
      <span className="ml-auto text-xs font-bold">{windowStatus?.is_open ? msg('FE_KITCHEN_OPEN', 'Open') : msg('FE_KITCHEN_CLOSED', 'Closed')}</span>
    </div>
    <p className="text-xs text-muted-foreground">{msg('FE_KITCHEN_SCHEDULE_HELP', 'Ordering windows, dated overrides and remaining capacity determine when customers can order. Existing paid orders remain in the preparation queue.')}</p>
    {capacity && <div className="rounded-2xl bg-card border border-border p-4 shadow-card">
      <div className="flex items-center justify-between mb-2.5"><span className="flex items-center gap-2 text-xs font-bold"><Package className="h-4 w-4" />{msg('FE_KITCHEN_USAGE', "Today's usage")}</span><span className="text-xs font-bold tabular-nums">{capacity.orders_today ?? 0} / {hasLimit ? dailyCap : msg('FE_KITCHEN_NO_DAILY_LIMIT', 'No daily limit')}</span></div>
      {hasLimit && <div className="h-2.5 rounded-full bg-secondary overflow-hidden"><div className="h-full bg-gradient-cta" style={{ width: `${usagePct}%` }} /></div>}
    </div>}
    {canManageSettings && <Link to="/admin?section=delivery" className="inline-flex rounded-full bg-primary px-4 py-2 text-sm font-bold text-white">{msg('FE_KITCHEN_MANAGE_SCHEDULE', 'Manage ordering windows')}</Link>}
  </div>;
}
