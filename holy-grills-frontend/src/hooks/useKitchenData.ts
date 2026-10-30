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

  const refreshing = useRef(false);
  const lastDetails = useRef(0);
  const mounted = useRef(true);
  const [dataWarning, setDataWarning] = useState('');

  const refreshQueue = async (initial = false) => {
    if (refreshing.current) return;
    refreshing.current = true;
    const generation = scheduleGeneration.current;
    try {
      const detailReads = initial || Date.now() - lastDetails.current > 30000;
      const details = detailReads ? Promise.allSettled([
        liveApi.kitchen.getMetrics(campusId),
        liveApi.kitchen.getScheduled({ date: scheduledDate, ...(campusId ? { campus_id: campusId } : {}) }),
        liveApi.kitchen.getWindows(campusId), liveApi.menu.getKitchenCapacity(campusId),
        liveApi.kitchen.getSettings(campusId), liveApi.orders.getDeliveryWindowStatus(campusId),
      ]) : null;
      const q = await liveApi.kitchen.getQueue(campusId ? { campus_id: campusId } : {});
      if (!mounted.current) return;
      applyQueue(q); setError(null); setLoading(false);
      if (details) {
        const results = await details;
        if (!mounted.current) return;
        const [m, scheduledResult, w, cap, stg, status] = results;
        if (m.status === 'fulfilled') setMetrics(m.value);
        if (scheduledResult.status === 'fulfilled' && generation === scheduleGeneration.current) setScheduled(scheduledResult.value);
        if (w.status === 'fulfilled') {
          setWindows(w.value);
          if (initial) {
            const first = w.value.find(item => item.status === 'open')?.id || w.value[0]?.id;
            setSelectedWindow(first);
            if (first) liveApi.kitchen.getBatchSummary(first, campusId).then(value => { if (mounted.current) setBatchSummary(value); }).catch(() => { if (mounted.current) setDataWarning('Preparation totals could not load. Retry updates before using the prep list.'); });
          }
        }
        if (cap.status === 'fulfilled') setCapacity(cap.value);
        if (stg.status === 'fulfilled') setSettings(stg.value);
        if (status.status === 'fulfilled') setWindowStatus(status.value);
        const labels = ['today’s totals', 'scheduled orders', 'delivery windows', 'capacity', 'settings', 'ordering hours'];
        const missing = results.flatMap((result, index) => result.status === 'rejected' ? [labels[index]] : []);
        setDataWarning(missing.length ? `Some details could not load: ${missing.join(', ')}. The live order queue is available.` : '');
        lastDetails.current = Date.now();
      }
    } catch {
      if (mounted.current) setError(msg('FE_KITCHEN_QUEUE_STALE', 'Kitchen updates are unavailable. The displayed orders may be out of date. Retry before preparing or handing over orders.'));
    } finally {
      refreshing.current = false;
      if (mounted.current) setLoading(false);
    }
  };

  useEffect(() => {
    mounted.current = true;
    if (!authed) { setLoading(false); return; }
    void refreshQueue(true);
    return () => { mounted.current = false; };
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
  const open = windowStatus?.is_open ?? null;
  const prepTarget = null;

  return {
    authed, loading, error, dataWarning, refreshQueue,
    queue, scheduled, scheduledDate, scheduledLoading, selectScheduledDate, windows, selectedWindow, batchSummary, metrics, settings, capacity, windowStatus,
    open, prepTarget, flashingIds, actionLoading, batchBusy, batchResult,
    selectWindow, handleStatusUpdate, handleMarkUnavailable,
    handleMarkAvailable, handleBatchAdvance, clearBatchResult,
  };
}
