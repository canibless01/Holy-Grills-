import React, { useState } from 'react';
import { Navigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import { Bike, Check, Clock, Package } from 'lucide-react';
import { useRiderData } from '@/hooks/useRiderData';
import { formatNaira, formatDateTime, timeAgo, ORDER_STATUS_LABELS } from '@/lib/hgUtils';
import LoadingSpinner from '@/components/LoadingSpinner';
import RiderHeader from '@/components/rider/RiderHeader';
import RiderOrderCard from '@/components/rider/RiderOrderCard';

const PERIODS = [
  { id: 'today', label: 'Today' },
  { id: 'week', label: 'Week' },
  { id: 'month', label: 'Month' },
  { id: 'all', label: 'All Time' },
];

const TABS = [
  { id: 'batch', label: 'Delivery Batch' },
  { id: 'earnings', label: 'Earnings' },
  { id: 'history', label: 'History' },
];

export default function Rider() {
  const [tab, setTab] = useState('batch');
  const {
    authed, loading, error, batch, earnings, stats, history, online, period,
    actionLoading, calling, toggling, changePeriod, handleAction, handleCall, navigateTo, toggleOnline, handleSignOut,
  } = useRiderData();

  if (!authed) return <Navigate to="/login" state={{ from: '/rider' }} replace />;
  if (loading) return <LoadingSpinner label="Loading rider dashboard…" fullScreen />;

  const orderCount = batch?.orders?.length || 0;
  const periodLabel = period === 'all' ? 'All-Time' : period === 'today' ? "Today's" : `This ${period === 'week' ? 'Week' : 'Month'}'s`;

  return (
    <div className="min-h-screen bg-background flex flex-col">
      <RiderHeader online={online} onToggleOnline={toggleOnline} onSignOut={handleSignOut} busy={toggling} />

      <div className="max-w-2xl w-full mx-auto px-4 sm:px-6 py-4 space-y-4 flex-1 animate-fade-in">
        {/* Error state */}
        {error && (
          <div className="rounded-2xl bg-red-50 border border-red-200 p-4 flex items-center justify-between gap-3">
            <span className="text-sm text-red-600 font-medium">{error}</span>
            <button
              onClick={() => window.location.reload()}
              className="px-3 py-1.5 rounded-xl bg-red-600 text-white text-xs font-bold"
            >
              Retry
            </button>
          </div>
        )}

        {/* Earnings hero */}
        {earnings && (
          <motion.div
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.3 }}
            className="rounded-2xl bg-gradient-cta p-5 text-white relative overflow-hidden shadow-glow"
          >
            <div className="absolute -right-4 -top-4 opacity-15">
              <Bike className="w-24 h-24" />
            </div>
            <div className="relative">
              <div className="text-[10px] text-white/80 uppercase font-bold tracking-wider">
                {periodLabel} Earnings
              </div>
              <div className="font-heading font-extrabold text-3xl mt-1 tabular-nums">{formatNaira(earnings?.total_earnings ?? 0)}</div>
              <div className="text-xs text-white/80 mt-1">{earnings?.completed_batches ?? 0} batches completed{earnings?.outstanding ? ` · ${formatNaira(earnings.outstanding)} unpaid` : ''}</div>
            </div>
          </motion.div>
        )}

        {/* Stats bar */}
        {stats && (
          <div className="grid grid-cols-4 gap-2">
            <StatCard value={stats?.total_batches ?? 0} label="Batches" color="text-foreground" />
            <StatCard value={`${Math.round(stats?.completion_rate ?? 0)}%`} label="Completion" color="text-accent-foreground" />
            <StatCard value={stats?.total_orders_delivered ?? 0} label="Delivered" color="text-primary" />
            <StatCard value={stats?.zones_served?.length ?? 0} label="Zones" color="text-accent-foreground" />
          </div>
        )}

        {/* Tabs */}
        <div className="flex gap-1 p-1 rounded-full bg-secondary sticky top-14 z-20">
          {TABS.map((t) => (
            <button
              key={t.id}
              onClick={() => setTab(t.id)}
              className={`flex-1 py-2 rounded-full text-xs font-bold transition-all ${tab === t.id ? 'bg-white text-primary shadow-sm' : 'text-muted-foreground'}`}
            >
              {t.label}
            </button>
          ))}
        </div>

        {/* Batch */}
        {tab === 'batch' && batch && (
          <div className="space-y-3">
            <div className="rounded-2xl bg-white border border-border p-3.5 shadow-card">
              <div className="flex items-center justify-between">
                <div>
                  <div className="text-[10px] text-muted-foreground font-semibold uppercase tracking-wider">Batch #{(batch.batch.id || '').slice(0, 8).toUpperCase() || '—'}</div>
                  <div className="font-heading font-bold text-sm text-foreground mt-0.5">Zone: {batch.batch.zone || '—'}</div>
                </div>
                <span className="text-[10px] font-bold px-2.5 py-1 rounded-lg bg-primary/10 text-primary capitalize">{batch.batch.status || 'active'}</span>
              </div>
              {batch.batch.delivery_window?.label && (
                <div className="text-xs text-muted-foreground mt-2 flex items-center gap-1">
                  <Clock className="w-3 h-3" /> {batch.batch.delivery_window.label}
                </div>
              )}
            </div>

            <div className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground px-1">Delivery Route (sorted by distance)</div>
            {(batch?.orders || []).map((order) => (
              <RiderOrderCard
                key={order.id}
                order={order}
                onAction={handleAction}
                onCall={handleCall}
                onNavigate={navigateTo}
                actionLoading={actionLoading}
                calling={calling}
              />
            ))}
            {orderCount === 0 && (
              <div className="text-center py-12 rounded-2xl border-2 border-dashed border-border">
                <Bike className="w-10 h-10 text-muted-foreground/40 mx-auto mb-2" />
                <p className="text-sm text-muted-foreground font-medium">No active deliveries in your batch.</p>
                <p className="text-xs text-muted-foreground mt-1">New orders will appear here automatically.</p>
              </div>
            )}
          </div>
        )}

        {/* Earnings */}
        {tab === 'earnings' && earnings && (
          <div className="space-y-3">
            <div className="flex gap-1 p-1 rounded-full bg-secondary">
              {PERIODS.map((p) => (
                <button
                  key={p.id}
                  onClick={() => changePeriod(p.id)}
                  className={`flex-1 py-2 rounded-full text-xs font-bold transition-all ${period === p.id ? 'bg-white text-primary shadow-sm' : 'text-muted-foreground'}`}
                >
                  {p.label}
                </button>
              ))}
            </div>
            {(earnings?.unpriced_batches > 0) && (
              <div className="rounded-xl bg-amber-50 border border-amber-200 px-3 py-2 text-[11px] text-amber-700 font-medium">
                {earnings.unpriced_batches} batch(es) awaiting pay-rate set by admin.
              </div>
            )}
            <div className="space-y-2">
              {(earnings?.batches || []).map((b) => {
                const paid = !!b.rider_paid_at;
                return (
                  <div key={b.id} className="flex items-center gap-3 p-3.5 rounded-2xl bg-white border border-border shadow-card">
                    <div className={`w-10 h-10 rounded-xl flex items-center justify-center shrink-0 ${paid ? 'bg-emerald-100' : 'bg-accent/20'}`}>
                      <Check className={`w-5 h-5 ${paid ? 'text-emerald-600' : 'text-accent-foreground'}`} />
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="font-semibold text-sm text-foreground truncate">{b.zone || `Batch #${(b.id || '').slice(0, 8)}`}</div>
                      <div className="text-xs text-muted-foreground">{b.order_count ?? 0} order(s) · {timeAgo(b.delivered_at)}</div>
                    </div>
                    <div className="text-right shrink-0">
                      <div className="font-heading font-bold text-sm text-foreground tabular-nums">{formatNaira(b.rider_pay_total ?? b.batch_pay ?? 0)}</div>
                      <div className={`text-[9px] font-bold uppercase ${paid ? 'text-emerald-600' : 'text-amber-600'}`}>{paid ? 'Paid' : 'Unpaid'}</div>
                    </div>
                  </div>
                );
              })}
              {(earnings?.batches || []).length === 0 && (
                <div className="text-center py-12 rounded-2xl border-2 border-dashed border-border">
                  <Package className="w-9 h-9 text-muted-foreground/40 mx-auto mb-2" />
                  <p className="text-sm text-muted-foreground">No earnings recorded for this period.</p>
                </div>
              )}
            </div>
          </div>
        )}

        {/* History — batch-level rows { id, zone, status, created_at, order_count } */}
        {tab === 'history' && (
          <div className="space-y-2">
            {(history || []).map((d) => {
              const done = d.status === 'completed' || d.status === 'delivered';
              return (
                <div key={d.id} className="flex items-center gap-3 p-3.5 rounded-2xl bg-white border border-border shadow-card">
                  <div className={`w-10 h-10 rounded-xl flex items-center justify-center shrink-0 ${done ? 'bg-emerald-100' : 'bg-amber-100'}`}>
                    {done ? <Check className="w-5 h-5 text-emerald-600" /> : <Clock className="w-5 h-5 text-amber-500" />}
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="font-semibold text-sm text-foreground truncate">{d.zone || `Batch #${(d.id || '').slice(0, 8)}`}</span>
                      <span className="text-[9px] font-bold px-1.5 py-0.5 rounded-md capitalize bg-secondary text-muted-foreground">
                        {ORDER_STATUS_LABELS[d.status] || d.status}
                      </span>
                    </div>
                    <div className="text-xs text-muted-foreground truncate">{d.order_count ?? (d.orders || []).length ?? 0} order(s) in batch</div>
                    <div className="text-[11px] text-muted-foreground">{formatDateTime(d.created_at)}</div>
                  </div>
                  <div className="text-right shrink-0">
                    <div className="font-heading font-bold text-sm text-foreground tabular-nums">{d.order_count ?? (d.orders || []).length ?? 0}</div>
                    <div className="text-[9px] text-muted-foreground font-semibold uppercase">orders</div>
                  </div>
                </div>
              );
            })}
            {history.length === 0 && (
              <div className="text-center py-12 rounded-2xl border-2 border-dashed border-border">
                <Clock className="w-10 h-10 text-muted-foreground/40 mx-auto mb-2" />
                <p className="text-sm text-muted-foreground">No completed batches yet</p>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

function StatCard({ value, label, color }) {
  return (
    <div className="rounded-2xl bg-white border border-border p-2.5 text-center shadow-card">
      <div className={`font-heading font-extrabold text-base tabular-nums ${color}`}>{value}</div>
      <div className="text-[9px] text-muted-foreground font-semibold uppercase tracking-wide mt-0.5">{label}</div>
    </div>
  );
}