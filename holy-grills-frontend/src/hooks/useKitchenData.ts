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
export function useKitchenData(campusId?: string) {
  const [queue, setQueue] = useState([]);
  const [scheduled, setScheduled] = useState(null);
  const [scheduledDate, setScheduledDate] = useState(new Date(Date.now() + 3600000).toISOString().slice(0, 10));
  const [scheduledLoading, setScheduledLoading] = useState(false);
  const scheduleGeneration = useRef(0);
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
    const generation = scheduleGeneration.current;
    try {
      const [q, m, s, w, cap, stg, status] = await Promise.all([
        liveApi.kitchen.getQueue(campusId ? { campus_id: campusId } : {}),
        liveApi.kitchen.getMetrics(campusId),
        liveApi.kitchen.getScheduled({ date: scheduledDate, ...(campusId ? { campus_id: campusId } : {}) }),
        liveApi.kitchen.getWindows(campusId), liveApi.menu.getKitchenCapacity(campusId),
        liveApi.kitchen.getSettings(campusId), liveApi.orders.getDeliveryWindowStatus(campusId),
      ]);
      applyQueue(q);
      setMetrics(m); setWindows(w); setCapacity(cap); setSettings(stg); setWindowStatus(status);
      if (generation === scheduleGeneration.current) setScheduled(s);
      setError(null);
    } catch { setError(msg('FE_KITCHEN_QUEUE_STALE', 'Kitchen updates are unavailable. The displayed orders may be out of date. Retry before preparing or handing over orders.')); }
  };

  useEffect(() => {
    if (!authed) { setLoading(false); return; }
    let alive = true;
    const init = async () => {
      try {
        const [q, s, w, m, cap, stg, status] = await Promise.all([
          liveApi.kitchen.getQueue(campusId ? { campus_id: campusId } : {}),
          liveApi.kitchen.getScheduled({ date: scheduledDate, ...(campusId ? { campus_id: campusId } : {}) }),
          liveApi.kitchen.getWindows(campusId),
          liveApi.kitchen.getMetrics(campusId),
          liveApi.menu.getKitchenCapacity(campusId),
          liveApi.kitchen.getSettings(campusId),
          liveApi.orders.getDeliveryWindowStatus(campusId),
        ]);
        if (!alive) return;
        applyQueue(q);
        setScheduled(s); setWindows(w); setMetrics(m); setCapacity(cap); setSettings(stg); setWindowStatus(status);
        const firstWin = w.find((x) => x.status === 'open')?.id || w[0]?.id;
        setSelectedWindow(firstWin);
        if (firstWin) {
          const bs = await liveApi.kitchen.getBatchSummary(firstWin, campusId);
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
  }, [authed, campusId]);

  useEffect(() => {
    if (!authed) return;
    const interval = setInterval(refreshQueue, 10000);
    return () => clearInterval(interval);
  }, [authed, scheduledDate, campusId]);

  const selectScheduledDate = async (date) => {
    if (!date) return;
    const generation = ++scheduleGeneration.current;
    setScheduledDate(date); setScheduledLoading(true); setScheduled(null);
    try {
      const value = await liveApi.kitchen.getScheduled({ date, ...(campusId ? { campus_id: campusId } : {}) });
      if (generation === scheduleGeneration.current) setScheduled(value);
    } catch (exception) {
      if (generation === scheduleGeneration.current) setScheduled({ date, scheduled_orders: [], count: 0, error: true });
    } finally { if (generation === scheduleGeneration.current) setScheduledLoading(false); }
  };

  const selectWindow = async (winId) => {
    setSelectedWindow(winId);
    try {
      const bs = await liveApi.kitchen.getBatchSummary(winId, campusId);
      setBatchSummary(bs);
    } catch (e) { console.error(e); }
  };

  const handleStatusUpdate = async (orderId, status) => {
    setActionLoading(orderId);
    try {
      await liveApi.orders.updateStatus(orderId, { status });
      toast({ title: msg('FE_USE_KITCHEN_DATA_MARKED_STATUS', 'Marked {status}', { status: ORDER_STATUS_LABELS[status] }) });
      await refreshQueue();
    } catch (e) {
      toast({ title: msg('FE_USE_KITCHEN_DATA_FAILED_TO_UPDATE_ORDER_STATUS', 'Failed to update order status'), description: e.message, variant: 'destructive' });
    }
    setActionLoading(null);
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

  const handleBatchAdvance = async (winId, body, label) => {
    setBatchBusy(true);
    try {
      const res = await liveApi.kitchen.batchAdvanceStatus(winId, body, campusId);
      const advanced = res?.advanced_count ?? res?.advanced?.length ?? 0;
      const skipped = res?.skipped_count ?? 0;
      const skippedReasons: Record<string, number> = {};
      (res?.skipped || []).forEach((o) => {
        const r = o.reason || (o.from_status ? `past ${o.from_status}` : 'skipped');
        skippedReasons[r] = (skippedReasons[r] || 0) + 1;
      });
      setBatchResult({ advanced, skipped, skippedReasons, label: label || 'Batch advanced' });
      toast({
        title: msg('FE_USE_KITCHEN_DATA_BATCH_ADVANCED', '{label} — {count} moved', {
          label: label || msg('FE_USE_KITCHEN_DATA_ADVANCED', 'Advanced'),
          count: advanced,
        }),
        description: skipped ? msg('FE_USE_KITCHEN_DATA_BATCH_SKIPPED', '{count} skipped', { count: skipped }) : undefined,
      });
      await refreshQueue();
    } catch (e) {
      toast({ title: msg('FE_USE_KITCHEN_DATA_BATCH_UPDATE_FAILED', 'Batch update failed'), description: e.message, variant: 'destructive' });
    }
    setBatchBusy(false);
  };

  const clearBatchResult = () => setBatchResult(null);

  // Ordering-window status is authoritative. Legacy kitchen settings such as
  // is_accepting_orders are not consumed by order admission.
  const open = windowStatus?.is_open === true;
  const prepTarget = null;

  return {
    authed, loading, error,
    queue, scheduled, scheduledDate, scheduledLoading, selectScheduledDate, windows, selectedWindow, batchSummary, metrics, settings, capacity, windowStatus,
    open, prepTarget, flashingIds, actionLoading, batchBusy, batchResult,
    selectWindow, handleStatusUpdate, handleMarkUnavailable,
    handleMarkAvailable, handleBatchAdvance, clearBatchResult,
  };
}
