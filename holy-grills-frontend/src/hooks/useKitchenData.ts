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
  const queueGeneration = useRef(0);
  const [windows, setWindows] = useState([]);
  const [selectedWindow, setSelectedWindow] = useState(null);
  const [batchSummary, setBatchSummary] = useState(null);
  const [batchSummaryLoading, setBatchSummaryLoading] = useState(false);
  const [batchSummaryError, setBatchSummaryError] = useState(false);
  const summaryGeneration = useRef(0);
  const selectedWindowRef = useRef(null);
  const summaryWindowRef = useRef(null);
  const summaryPending = useRef(false);
  const batchWritePending = useRef(false);
  const [itemAvailability, setItemAvailability] = useState({});
  const [availabilityBusy, setAvailabilityBusy] = useState(new Set());
  const availabilityPending = useRef(new Set());
  const availabilityRevision = useRef(0);
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
  const applyQueue = (q, stockRevision = availabilityRevision.current) => {
    setQueue(q);
    setItemAvailability(previous => {
      const next = { ...previous };
      q.forEach(order => (order.order_items || []).forEach(item => {
        if (stockRevision === availabilityRevision.current && item.menu_item_id && !availabilityPending.current.has(item.menu_item_id)) {
          next[item.menu_item_id] = item.campus_is_available !== false;
        }
      }));
      return next;
    });
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

  const loadBatchSummary = async (winId) => {
    const generation = ++summaryGeneration.current;
    summaryPending.current = true;
    setBatchSummaryLoading(true); setBatchSummaryError(false);
    try {
      const value = await liveApi.kitchen.getBatchSummary(winId, campusId);
      if (generation !== summaryGeneration.current || winId !== selectedWindowRef.current) return;
      summaryWindowRef.current = winId;
      setBatchSummary(value);
    } catch {
      if (generation !== summaryGeneration.current) return;
      summaryWindowRef.current = null;
      setBatchSummary(null); setBatchSummaryError(true);
    } finally {
      if (generation === summaryGeneration.current) {
        summaryPending.current = false; setBatchSummaryLoading(false);
      }
    }
  };

  const refreshQueue = async () => {
    const queueRequest = ++queueGeneration.current;
    const stockRevision = availabilityRevision.current;
    const generation = scheduleGeneration.current;
    try {
      const [q, m, s, w, cap, stg, status] = await Promise.all([
        liveApi.kitchen.getQueue(campusId ? { campus_id: campusId } : {}),
        liveApi.kitchen.getMetrics(campusId),
        liveApi.kitchen.getScheduled({ date: scheduledDate, ...(campusId ? { campus_id: campusId } : {}) }),
        liveApi.kitchen.getWindows(campusId), liveApi.menu.getKitchenCapacity(campusId),
        liveApi.kitchen.getSettings(campusId), liveApi.orders.getDeliveryWindowStatus(campusId),
      ]);
      if (queueRequest !== queueGeneration.current) return;
      applyQueue(q, stockRevision);
      setMetrics(m); setWindows(w); setCapacity(cap); setSettings(stg); setWindowStatus(status);
      if (generation === scheduleGeneration.current) setScheduled(s);
      setError(null);
      const winId = w.some(window => window.id === selectedWindowRef.current)
        ? selectedWindowRef.current : w.find(window => window.status === 'open')?.id || w[0]?.id;
      if (winId) {
        if (selectedWindowRef.current !== winId) {
          selectedWindowRef.current = winId; setSelectedWindow(winId);
          summaryWindowRef.current = null; setBatchSummary(null); setBatchResult(null);
        }
        await loadBatchSummary(winId);
      } else {
        ++summaryGeneration.current; selectedWindowRef.current = null; summaryWindowRef.current = null;
        summaryPending.current = false; setSelectedWindow(null); setBatchSummary(null);
        setBatchSummaryLoading(false); setBatchSummaryError(false);
      }
    } catch { if (queueRequest !== queueGeneration.current) return; setError(msg('FE_KITCHEN_QUEUE_STALE', 'Kitchen updates are unavailable. The displayed orders may be out of date. Retry before preparing or handing over orders.')); }
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
        selectedWindowRef.current = firstWin; setSelectedWindow(firstWin);
        if (firstWin) await loadBatchSummary(firstWin);
      } catch (e) {
        console.error(e);
        if (alive) setError(msg('FE_USE_KITCHEN_DATA_COULD_NOT_LOAD_KITCHEN_DATA_CHECK_YOUR', 'Could not load kitchen data. Check your connection and try again.'));
      }
      if (alive) setLoading(false);
    };
    init();
    return () => { alive = false; ++summaryGeneration.current; };
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
    if (!winId || batchWritePending.current) return;
    selectedWindowRef.current = winId; summaryWindowRef.current = null;
    setSelectedWindow(winId); setBatchSummary(null); setBatchResult(null);
    await loadBatchSummary(winId);
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

  const setAvailability = async (itemId, available) => {
    if (availabilityPending.current.has(itemId)) return false;
    availabilityPending.current.add(itemId); setAvailabilityBusy(new Set(availabilityPending.current));
    try {
      if (available) await liveApi.kitchen.markItemAvailable(itemId, campusId);
      else await liveApi.kitchen.markItemUnavailable(itemId, campusId);
      ++availabilityRevision.current;
      setItemAvailability(previous => ({ ...previous, [itemId]: available }));
      toast({ title: available ? msg('FE_USE_KITCHEN_DATA_ITEM_BACK_IN_STOCK', 'Item back in stock') : msg('FE_USE_KITCHEN_DATA_ITEM_MARKED_AS_SOLD_OUT', 'Item marked as sold out') });
      return true;
    } catch (e) {
      toast({ title: msg('FE_USE_KITCHEN_DATA_COULD_NOT_UPDATE_ITEM', 'Could not update item'), description: e.message, variant: 'destructive' });
      return false;
    } finally {
      availabilityPending.current.delete(itemId); setAvailabilityBusy(new Set(availabilityPending.current));
    }
  };
  const handleMarkUnavailable = (itemId) => setAvailability(itemId, false);
  const handleMarkAvailable = (itemId) => setAvailability(itemId, true);

  const handleBatchAdvance = async (winId, body, label) => {
    if (batchWritePending.current || summaryPending.current || !winId ||
        winId !== selectedWindowRef.current || winId !== summaryWindowRef.current) return;
    batchWritePending.current = true; setBatchBusy(true);
    summaryWindowRef.current = null;
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
      await refreshQueue();
    } finally { batchWritePending.current = false; setBatchBusy(false); }
  };

  const clearBatchResult = () => setBatchResult(null);

  // Ordering-window status is authoritative. Legacy kitchen settings such as
  // is_accepting_orders are not consumed by order admission.
  const open = windowStatus?.is_open === true;
  const prepTarget = null;

  return {
    authed, loading, error,
    queue, scheduled, scheduledDate, scheduledLoading, selectScheduledDate, windows, selectedWindow, batchSummary, batchSummaryLoading, batchSummaryError, metrics, settings, capacity, windowStatus,
    open, prepTarget, flashingIds, actionLoading, batchBusy, batchResult, itemAvailability, availabilityBusy,
    selectWindow, handleStatusUpdate, handleMarkUnavailable,
    handleMarkAvailable, handleBatchAdvance, clearBatchResult,
  };
}
