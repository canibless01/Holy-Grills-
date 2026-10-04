import React from 'react';
import { Package, Clock, Zap, Lock, ShieldCheck } from 'lucide-react';

// Read-only visual snapshot of kitchen limits. Kitchen staff can VIEW these
// via /kitchen/settings but cannot change them — capacity, window limits and
// auto-accept are admin-only (PATCH /api/kitchen/settings is admin auth).
export default function KitchenSettings({ settings, capacity }) {
  // Settings is a key/value map of strings from GET /kitchen/settings.
  // Parse values defensively — only render what the backend actually returns.
  const s = settings || {};
  const boolVal = (v) => v === true || v === 'true';
  const accepting = !boolVal(s.is_closed_for_day) && s.is_accepting_orders !== 'false' && s.is_accepting_orders !== false;
  const dailyCap = s.daily_order_capacity != null && s.daily_order_capacity !== '' ? s.daily_order_capacity : null;
  const cards = [
    { icon: Package, label: 'Daily Capacity', value: dailyCap != null ? dailyCap : '∞', tone: 'text-primary' },
    { icon: Zap, label: 'Auto-Accept', value: boolVal(s.auto_accept_orders) ? 'On' : 'Off', tone: 'text-emerald-600' },
    { icon: Clock, label: 'Opens', value: s.ordering_window_open_time || '—', tone: 'text-foreground' },
    { icon: Clock, label: 'Closes', value: s.ordering_window_close_time || '—', tone: 'text-foreground' },
    { icon: Clock, label: 'Prep Target', value: s.avg_prep_target_minutes != null && s.avg_prep_target_minutes !== '' ? `${s.avg_prep_target_minutes}m` : '—', tone: 'text-blue-600' },
  ];
  const usagePct = dailyCap ? Math.min(100, ((capacity?.orders_today ?? 0) / Number(dailyCap)) * 100) : 0;

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2 rounded-2xl bg-card border border-border px-3.5 py-2.5">
        <ShieldCheck className="w-4 h-4 text-muted-foreground shrink-0" />
        <span className="text-xs font-semibold text-foreground">Admin-managed · read-only</span>
        <span className={`ml-auto text-[10px] font-bold px-2 py-0.5 rounded-md ${accepting ? 'bg-emerald-100 text-emerald-600' : 'bg-red-100 text-red-600'}`}>
          {accepting ? 'Open' : 'Paused'}
        </span>
      </div>

      {capacity && (
        <div className="rounded-2xl bg-white border border-border p-4 shadow-card">
          <div className="flex items-center justify-between mb-2.5">
            <span className="text-xs font-bold text-foreground">Today's Usage</span>
            <span className="text-xs font-bold text-foreground tabular-nums">{capacity.orders_today ?? 0} / {dailyCap ?? '∞'}</span>
          </div>
          <div className="h-2.5 rounded-full bg-secondary overflow-hidden">
            <div className="h-full bg-gradient-cta rounded-full transition-all duration-500" style={{ width: `${usagePct}%` }} />
          </div>
        </div>
      )}

      <div className="grid grid-cols-2 sm:grid-cols-3 gap-2.5">
        {cards.map((c) => (
          <div key={c.label} className="rounded-2xl bg-white border border-border p-3 shadow-card relative">
            <Lock className="w-3 h-3 text-muted-foreground/60 absolute top-2.5 right-2.5" />
            <c.icon className={`w-4 h-4 ${c.tone} mb-1.5`} />
            <div className="font-heading font-extrabold text-base text-foreground leading-none">{c.value}</div>
            <div className="text-[10px] text-muted-foreground font-semibold uppercase tracking-wide mt-1">{c.label}</div>
          </div>
        ))}
      </div>
    </div>
  );
}