import { useState, useEffect, useRef } from 'react';

// Summary returned to the kitchen after a prep-list batch advance.
interface KitchenBatchResult {
  advanced: number;
  skipped: number;
  skippedReasons: Record<string, number>;
  label: string;
}
import { liveApi } from '@/lib/liveApi';
import { isAuthenticated } from '@/lib/apiClient';
import { useSound } from '@/lib/SoundProvider';
import { ORDER_STATUS_LABELS } from '@/lib/hgUtils';
import { toast } from '@/components/ui/use-toast';
import { msg } from '@/lib/messages';

/**
 * All data + action logic for the Kitchen (KDS) panel, isolated from its UI.
 * Polls the live order queue, detects newly-arrived orders (sound + flash),
 * and exposes the handlers the KDS board needs.
 */
export function useKitchenData() {
  const [queue, setQueue] = useState([]);
  const [scheduled, setScheduled] = useState(null);
  const [windows, setWindows] = useState([]);
  const [selectedWindow, setSelectedWindow] = useState(null);
  const [batchSummary, setBatchSummary] = useState(null);
  const [metrics, setMetrics] = useState(null);
  const [settings, setSettings] = useState(null);
  const [capacity, setCapacity] = useState(null);
  const [windowStatus, setWindowStatus] = useState(null);
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState(null);
  const [batchBusy, setBatchBusy] = useState(false);
  const [batchResult, setBatchResult] = useState<KitchenBatchResult | null>(null);
  const [flashingIds, setFlashingIds] = useState(new Set());
  const [error, setError] = useState(null);
  const [authed] = useState(isAuthenticated());
  const { play } = useSound();

  const prevOrderIds = useRef(new Set());
  const initialized = useRef(false);

  // Apply a freshly-fetched queue: store it, and on subsequent polls detect
  // brand-new order ids to fire the alert sound + a 6s flash highlight.
  const applyQueue = (q) => {
    setQueue(q);
    const currentIds = new Set(q.map((o) => o.id));
    if (initialized.current) {
      const newIds = [...currentIds].filter((id) => !prevOrderIds.current.has(id));
      if (newIds.length > 0) {
        play('order_placed');
        setFlashingIds((prev) => new Set([...prev, ...newIds]));
        const idSet = new Set(newIds);
        setTimeout(() => {
          setFlashingIds((prev) => {
            const next = new Set(prev);
            idSet.forEach((id) => next.delete(id));
            return next;
          });
        }, 6000);
      }
    }
    prevOrderIds.current = currentIds;
    initialized.current = true;
  };

  const refreshQueue = async () => {
    try {
      const [q, m] = await Promise.all([liveApi.kitchen.getQueue(), liveApi.kitchen.getMetrics()]);
      applyQueue(q);
      setMetrics(m);
    } catch (e) { /* ignore poll errors */ }
  };

  useEffect(() => {
    if (!authed) { setLoading(false); return; }
    let alive = true;
    const init = async () => {
      try {
        const [q, s, w, m, cap, stg, status] = await Promise.all([
          liveApi.kitchen.getQueue(),
          liveApi.kitchen.getScheduled(),
          liveApi.kitchen.getWindows(),
          liveApi.kitchen.getMetrics(),
          liveApi.menu.getKitchenCapacity(),
          liveApi.kitchen.getSettings(),
          liveApi.orders.getDeliveryWindowStatus(),
        ]);
        if (!alive) return;
        applyQueue(q);
        setScheduled(s); setWindows(w); setMetrics(m); setCapacity(cap); setSettings(stg); setWindowStatus(status);
        const firstWin = w.find((x) => x.status === 'open')?.id || w[0]?.id;
        setSelectedWindow(firstWin);
        if (firstWin) {
          const bs = await liveApi.kitchen.getBatchSummary(firstWin);
          if (alive) setBatchSummary(bs);
        }
      } catch (e) {
        console.error(e);
        if (alive) setError(msg('FE_USE_KITCHEN_DATA_COULD_NOT_LOAD_KITCHEN_DATA_CHECK_YOUR', 'Could not load kitchen data. Check your connection and try again.'));
      }
      if (alive) setLoading(false);
    };
    init();
    return () => { alive = false; };
  }, [authed]);

  useEffect(() => {
    if (!authed) return;
    const interval = setInterval(refreshQueue, 10000);
    return () => clearInterval(interval);
  }, [authed]);

  const selectWindow = async (winId) => {
    setSelectedWindow(winId);
    try {
      const bs = await liveApi.kitchen.getBatchSummary(winId);
      setBatchSummary(bs);
    } catch (e) { console.error(e); }
  };

  const handleStatusUpdate = async (orderId, status) => {
    setActionLoading(orderId);
    try {
      await liveApi.orders.updateStatus(orderId, { status });
      toast({ title: `Marked ${ORDER_STATUS_LABELS[status]}` });
      await refreshQueue();
    } catch (e) {
      toast({ title: msg('FE_USE_KITCHEN_DATA_FAILED_TO_UPDATE_ORDER_STATUS', 'Failed to update order status'), description: e.message, variant: 'destructive' });
    }
    setActionLoading(null);
  };

  const handleToggleAccepting = async (newValue) => {
    try {
      // Settings are stored as strings on the backend (str(value) on upsert).
      await liveApi.kitchen.updateSettings({ is_accepting_orders: String(newValue) });
      setSettings((prev) => ({ ...prev, is_accepting_orders: String(newValue) }));
      toast({ title: newValue ? 'Kitchen open — accepting orders' : 'Kitchen paused — orders closed' });
    } catch (e) {
      toast({ title: msg('FE_USE_KITCHEN_DATA_COULD_NOT_UPDATE_KITCHEN_STATE', 'Could not update kitchen state'), description: e.message, variant: 'destructive' });
    }
  };

  const handleMarkUnavailable = async (itemId) => {
    try {
      await liveApi.kitchen.markItemUnavailable(itemId);
      toast({ title: msg('FE_USE_KITCHEN_DATA_ITEM_MARKED_AS_SOLD_OUT', 'Item marked as sold out') });
    } catch (e) {
      toast({ title: msg('FE_USE_KITCHEN_DATA_COULD_NOT_UPDATE_ITEM', 'Could not update item'), description: e.message, variant: 'destructive' });
    }
  };

  const handleMarkAvailable = async (itemId) => {
    try {
      await liveApi.kitchen.markItemAvailable(itemId);
      toast({ title: msg('FE_USE_KITCHEN_DATA_ITEM_BACK_IN_STOCK', 'Item back in stock') });
    } catch (e) {
      toast({ title: msg('FE_USE_KITCHEN_DATA_COULD_NOT_UPDATE_ITEM', 'Could not update item'), description: e.message, variant: 'destructive' });
    }
  };

  const batchIdFor = (winId) => windows.find((w) => w.id === winId)?.batch_id || winId;
  const handleBatchAdvance = async (winId, body, label) => {
    setBatchBusy(true);
    try {
      const res = await liveApi.kitchen.batchAdvanceStatus(batchIdFor(winId), body);
      const advanced = res?.advanced_count ?? res?.advanced?.length ?? 0;
      const skipped = res?.skipped_count ?? 0;
      const skippedReasons: Record<string, number> = {};
      (res?.skipped || []).forEach((o) => {
        const r = o.reason || (o.from_status ? `past ${o.from_status}` : 'skipped');
        skippedReasons[r] = (skippedReasons[r] || 0) + 1;
      });
      setBatchResult({ advanced, skipped, skippedReasons, label: label || 'Batch advanced' });
      toast({ title: `${label || 'Advanced'} — ${advanced} moved`, description: skipped ? `${skipped} skipped` : undefined });
      await refreshQueue();
    } catch (e) {
      toast({ title: msg('FE_USE_KITCHEN_DATA_BATCH_UPDATE_FAILED', 'Batch update failed'), description: e.message, variant: 'destructive' });
    }
    setBatchBusy(false);
  };

  const clearBatchResult = () => setBatchResult(null);

  // Settings arrive as a key/value map of strings from the backend. Booleans are
  // "true"/"false" strings (or absent). Parse defensively — no hardcoded
  // defaults for business rules (the backend is the source of truth).
  const boolVal = (v) => v === true || v === 'true';
  const accepting = !boolVal(settings?.is_closed_for_day) && settings?.is_accepting_orders !== 'false' && settings?.is_accepting_orders !== false;
  const open = !!windowStatus?.is_open;
  const prepTarget = settings?.avg_prep_target_minutes ?? settings?.prep_time_minutes ?? null;

  return {
    authed, loading, error,
    queue, scheduled, windows, selectedWindow, batchSummary, metrics, settings, capacity, windowStatus,
    accepting, open, prepTarget, flashingIds, actionLoading, batchBusy, batchResult,
    selectWindow, handleStatusUpdate, handleToggleAccepting, handleMarkUnavailable,
    handleMarkAvailable, handleBatchAdvance, clearBatchResult,
  };
}