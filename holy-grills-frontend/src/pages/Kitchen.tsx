import { useState } from 'react';
import { Navigate } from 'react-router-dom';
import { Calendar, Package, Zap, Check, ChefHat } from 'lucide-react';
import { useKitchenData } from '@/hooks/useKitchenData';
import { formatDateTime } from '@/lib/hgUtils';
import LoadingSpinner from '@/components/LoadingSpinner';
import KitchenHeader from '@/components/kitchen/KitchenHeader';
import KitchenOrderCard from '@/components/kitchen/KitchenOrderCard';
import KitchenSettings from '@/components/kitchen/KitchenSettings';

const TABS = [
  { id: 'queue', label: 'Live Queue' },
  { id: 'scheduled', label: 'Scheduled' },
  { id: 'batch', label: 'Prep List' },
  { id: 'settings', label: 'Settings' },
];

const COLUMN_ACCENTS = {
  received: { dot: 'bg-amber-500', badge: 'bg-amber-100 text-amber-700', label: 'New Orders' },
  preparing: { dot: 'bg-blue-500', badge: 'bg-blue-100 text-blue-700', label: 'In Preparation' },
  ready: { dot: 'bg-emerald-500', badge: 'bg-emerald-100 text-emerald-700', label: 'Ready for Pickup' },
};

export default function Kitchen() {
  const [tab, setTab] = useState('queue');
  const {
    authed, loading, error, queue, scheduled, windows, selectedWindow, batchSummary,
    settings, capacity, metrics, accepting, open, prepTarget, flashingIds, actionLoading,
    batchBusy, batchResult, selectWindow, handleStatusUpdate, handleToggleAccepting,
    handleMarkUnavailable, handleMarkAvailable, handleBatchAdvance, clearBatchResult,
  } = useKitchenData();

  if (!authed) return <Navigate to="/login" state={{ from: '/kitchen' }} replace />;
  if (loading) return <LoadingSpinner label="Loading kitchen…" fullScreen />;

  const received = queue.filter((o) => o.status === 'received');
  const preparing = queue.filter((o) => o.status === 'preparing');
  const ready = queue.filter((o) => o.status === 'ready');

  return (
    <div className="min-h-screen bg-background">
      <KitchenHeader accepting={accepting} open={open} onToggleAccepting={handleToggleAccepting} />

      <div className="max-w-6xl mx-auto px-4 sm:px-6 py-4 space-y-4 animate-fade-in">
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

        {/* Capacity bar */}
        {capacity && (
          <div className="rounded-2xl bg-white border border-border p-3.5 shadow-card flex items-center justify-between gap-3 flex-wrap">
            <div className="flex items-center gap-2">
              <Package className="w-4 h-4 text-primary" />
              <span className="text-sm font-bold text-foreground">Today's Capacity</span>
            </div>
            <div className="text-xs text-muted-foreground flex items-center gap-2">
              <span className="font-bold text-foreground tabular-nums">{capacity.orders_today ?? 0}</span>
              <span>/</span>
              <span className="tabular-nums">{capacity.daily_order_capacity ?? 0}</span>
              <span className={`px-2 py-0.5 rounded-md text-[10px] font-bold ${(capacity.is_at_capacity ?? (capacity.remaining != null && capacity.remaining <= 0)) ? 'bg-red-100 text-red-600' : 'bg-emerald-100 text-emerald-600'}`}>
                {(capacity.is_at_capacity ?? (capacity.remaining != null && capacity.remaining <= 0)) ? 'AT CAPACITY' : `${Math.max(0, (capacity.daily_order_capacity ?? 0) - (capacity.orders_today ?? 0))} LEFT`}
              </span>
            </div>
          </div>
        )}

        {/* Metrics */}
        {metrics && (
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2.5">
            <MetricCard value={metrics?.total_orders ?? 0} label="Total Today" color="text-foreground" />
            <MetricCard value={metrics?.orders_by_status?.preparing || 0} label="Preparing" color="text-blue-500" />
            <MetricCard value={metrics?.orders_by_status?.ready || 0} label="Ready" color="text-emerald-500" />
            <MetricCard value={`${metrics?.avg_prep_time_minutes ?? '—'}m`} label="Avg Prep" color="text-primary" />
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

        {/* Live Queue — 3-column KDS board */}
        {tab === 'queue' && (
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-3 lg:gap-4">
            {['received', 'preparing', 'ready'].map((status) => {
              const orders = status === 'received' ? received : status === 'preparing' ? preparing : ready;
              const accent = COLUMN_ACCENTS[status];
              return (
                <div key={status} className="space-y-2.5">
                  <div className="flex items-center justify-between px-1 sticky top-[3.5rem] z-10 lg:static lg:z-auto">
                    <div className="flex items-center gap-2">
                      <span className={`w-2.5 h-2.5 rounded-full ${accent.dot}`} />
                      <h3 className="text-xs font-extrabold uppercase tracking-wide text-foreground">{accent.label}</h3>
                    </div>
                    <span className={`text-[10px] font-bold px-2 py-0.5 rounded-full ${accent.badge}`}>{orders.length}</span>
                  </div>
                  <div className="space-y-2.5">
                    {orders.map((order) => (
                      <KitchenOrderCard
                        key={order.id}
                        order={order}
                        onStatusUpdate={handleStatusUpdate}
                        onMarkUnavailable={handleMarkUnavailable}
                        onMarkAvailable={handleMarkAvailable}
                        actionLoading={actionLoading}
                        targetMinutes={prepTarget}
                        isNew={flashingIds.has(order.id)}
                      />
                    ))}
                    {orders.length === 0 && (
                      <div className="rounded-2xl border-2 border-dashed border-border py-10 text-center">
                        <ChefHat className="w-6 h-6 text-muted-foreground/40 mx-auto mb-1.5" />
                        <p className="text-xs text-muted-foreground font-medium">No {status === 'received' ? 'new' : status === 'preparing' ? 'cooking' : 'ready'} orders</p>
                      </div>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        )}

        {/* Scheduled */}
        {tab === 'scheduled' && scheduled && (
          <div className="space-y-3">
            <div className="rounded-2xl bg-card border border-border p-3 text-xs text-foreground flex items-center gap-2">
              <Calendar className="w-4 h-4 text-primary" />
              <span><span className="font-bold">{scheduled.count}</span> scheduled order(s) awaiting promotion to the queue</span>
            </div>
            {scheduled.scheduled_orders.map((order) => (
              <div key={order.id} className="rounded-2xl bg-white border border-border p-3.5 shadow-card">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-xs font-bold text-foreground font-mono">#{(order.id || '').slice(0, 8).toUpperCase()}</span>
                  <span className="text-xs text-primary font-semibold">{formatDateTime(order.scheduled_for)}</span>
                </div>
                <div className="space-y-1 mb-2">
                  {(order.order_items || []).map((item, i) => (
                    <div key={i} className="text-sm text-foreground"><span className="font-bold">{item.quantity}×</span> {item.name_snapshot}</div>
                  ))}
                </div>
                <div className="text-xs text-muted-foreground mb-2.5">Window: {order.delivery_windows?.label || '—'}</div>
                <button
                  onClick={() => handleStatusUpdate(order.id, 'preparing')}
                  disabled={actionLoading === order.id}
                  className="w-full py-2.5 rounded-xl bg-primary text-white text-xs font-bold disabled:opacity-50 active:scale-[0.98] transition-all"
                >
                  {actionLoading === order.id ? 'Promoting…' : 'Promote to Preparing'}
                </button>
              </div>
            ))}
            {scheduled.scheduled_orders.length === 0 && (
              <div className="text-center py-12">
                <Calendar className="w-9 h-9 text-muted-foreground/40 mx-auto mb-2" />
                <p className="text-sm text-muted-foreground">No scheduled orders.</p>
              </div>
            )}
          </div>
        )}

        {/* Prep List */}
        {tab === 'batch' && (
          <div className="space-y-3">
            <div className="flex gap-1.5 overflow-x-auto scrollbar-hide pb-1">
              {windows.map((w) => (
                <button
                  key={w.id}
                  onClick={() => selectWindow(w.id)}
                  className={`shrink-0 px-3.5 py-2.5 rounded-2xl border text-left transition-all ${selectedWindow === w.id ? 'bg-primary border-primary text-white shadow-glow' : 'bg-white border-border text-foreground'}`}
                >
                  <div className="text-xs font-bold">{w.label}</div>
                  <div className={`text-[10px] ${selectedWindow === w.id ? 'text-white/80' : 'text-muted-foreground'}`}>
                    {w.order_count ?? 0} orders · <span className="capitalize">{w.status}</span>
                  </div>
                </button>
              ))}
            </div>

            {batchResult && (
              <div className="rounded-2xl bg-white border border-border p-3.5 shadow-card">
                <div className="flex items-center justify-between mb-2.5">
                  <span className="text-xs font-bold text-foreground">{batchResult.label}</span>
                  <button onClick={clearBatchResult} className="text-muted-foreground text-xs font-bold hover:text-muted">✕</button>
                </div>
                <div className="flex gap-2.5">
                  <div className="flex-1 rounded-xl bg-emerald-50 border border-emerald-200 p-2.5 text-center">
                    <div className="text-lg font-heading font-extrabold text-emerald-600 tabular-nums">{batchResult.advanced}</div>
                    <div className="text-[10px] text-emerald-600 font-semibold uppercase tracking-wide">advanced</div>
                  </div>
                  <div className="flex-1 rounded-xl bg-amber-50 border border-amber-200 p-2.5 text-center">
                    <div className="text-lg font-heading font-extrabold text-amber-600 tabular-nums">{batchResult.skipped}</div>
                    <div className="text-[10px] text-amber-600 font-semibold uppercase tracking-wide">skipped</div>
                  </div>
                </div>
                {batchResult.skipped > 0 && Object.keys(batchResult.skippedReasons).length > 0 && (
                  <div className="mt-2.5 flex flex-wrap gap-1.5">
                    {Object.entries(batchResult.skippedReasons).map(([reason, count]) => (
                      <span key={reason} className="text-[10px] font-semibold px-2 py-1 rounded-md bg-amber-100 text-amber-700">{count}× {reason}</span>
                    ))}
                  </div>
                )}
              </div>
            )}

            {batchSummary && batchSummary.total_orders > 0 && (
              <div className="grid grid-cols-2 gap-2.5">
                <button
                  onClick={() => handleBatchAdvance(selectedWindow, { from_status: 'received', notes: 'Started preparing batch' }, 'Received → Preparing')}
                  disabled={batchBusy}
                  className="flex flex-col items-center gap-0.5 py-3 rounded-xl bg-primary text-white text-xs font-bold disabled:opacity-50 active:scale-[0.98] transition-all"
                >
                  <Zap className="w-3.5 h-3.5" />
                  <span>Start Preparing</span>
                  <span className="text-[9px] font-normal text-white/80">received → preparing</span>
                </button>
                <button
                  onClick={() => handleBatchAdvance(selectedWindow, { from_status: 'preparing', notes: 'Marked batch ready' }, 'Preparing → Ready')}
                  disabled={batchBusy}
                  className="flex flex-col items-center gap-0.5 py-3 rounded-xl bg-emerald-600 text-white text-xs font-bold disabled:opacity-50 active:scale-[0.98] transition-all"
                >
                  <Check className="w-3.5 h-3.5" />
                  <span>Mark Ready</span>
                  <span className="text-[9px] font-normal text-white/80">preparing → ready</span>
                </button>
              </div>
            )}

            {batchSummary && (
              <div className="rounded-2xl bg-white border border-border p-4 shadow-card">
                <h3 className="font-bold text-sm text-foreground mb-1">Consolidated Prep List</h3>
                <p className="text-xs text-muted-foreground mb-3">{batchSummary.total_orders} orders in this window</p>
                <div className="space-y-2">
                  {batchSummary.summary.map((item, i) => (
                    <div key={i} className="flex items-center justify-between p-2.5 rounded-xl bg-muted">
                      <span className="text-sm font-medium text-foreground">{item.item_name}</span>
                      <span className="font-bold text-foreground tabular-nums">{item.total_quantity}×</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}

        {/* Settings */}
        {tab === 'settings' && settings && (
          <KitchenSettings settings={settings} capacity={capacity} />
        )}
      </div>
    </div>
  );
}

function MetricCard({ value, label, color }) {
  return (
    <div className="rounded-2xl bg-white border border-border p-3 text-center shadow-card">
      <div className={`font-heading font-extrabold text-xl tabular-nums ${color}`}>{value}</div>
      <div className="text-[10px] text-muted-foreground font-semibold uppercase tracking-wide mt-0.5">{label}</div>
    </div>
  );
}