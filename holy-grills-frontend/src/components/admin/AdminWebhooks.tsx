import { useState, useEffect, useRef } from 'react';
import { motion } from 'framer-motion';
import { Webhook, RefreshCw, Check, X, AlertTriangle, Clock } from 'lucide-react';
import { liveApi } from '@/lib/liveApi';
import { formatDateTime, timeAgo } from '@/lib/hgUtils';
import { toast } from '@/components/ui/use-toast';
import { Card, Skeleton, EmptyState, Pill, BreakdownTiles } from './ui/AdminKit';
import { msg } from '@/lib/messages';
import { useCampus } from '@/lib/campusContext';

// GET /admin/webhook-events — the platform's recent webhook delivery log.
// Each row carries the provider, event, status, HTTP code, and timestamps so
// admins can spot failed integrations without digging into server logs.
//
// The table stores `processed` / `failed` / `processing`. The UI used to expect
// success/delivered/ok, so every healthy delivery rendered as an unknown tone
// and the "Delivered" tile always read 0. Normalise both vocabularies here.
const normalizedStatus = (s) => {
  const v = String(s || '').toLowerCase();
  if (['processed', 'success', 'delivered', 'ok'].includes(v)) return 'success';
  if (['failed', 'error'].includes(v)) return 'failed';
  if (['processing', 'pending', 'retrying', 'queued'].includes(v)) return 'pending';
  return v || 'unknown';
};

const statusTone = (s) => {
  const v = normalizedStatus(s);
  if (v === 'success') return 'green';
  if (v === 'failed') return 'red';
  if (v === 'pending') return 'amber';
  return 'cocoa';
};

export default function AdminWebhooks() {
  const { adminCampusId } = useCampus();
  const readVersion = useRef(0);
  const writeLock = useRef(false);
  const scopeVersion = useRef(0);
  const [error, setError] = useState('');
  const [offset, setOffset] = useState(0);
  const pageSize = 50;
  const [events, setEvents] = useState(null);
  const [expanded, setExpanded] = useState(null);
  const [refreshing, setRefreshing] = useState(false);
  const [filters, setFilters] = useState({ provider: '', status: '', from_date: '', to_date: '' });
  const [retrying, setRetrying] = useState(null);

  const load = async () => {
    const version = ++readVersion.current;
    setRefreshing(true); setError('');
    try {
      const params: Record<string, unknown> = { limit: pageSize, offset, ...(adminCampusId ? {campus_id: adminCampusId} : {}) };
      if (filters.provider) params.provider = filters.provider;
      if (filters.status) params.status = filters.status;
      if (filters.from_date) params.from_date = filters.from_date;
      if (filters.to_date) params.to_date = filters.to_date;
      const list = await liveApi.admin.getWebhookEvents(params);
      const arr = (Array.isArray(list) ? list : []).sort((a, b) => new Date(b.created_at || b.received_at || 0).getTime() - new Date(a.created_at || a.received_at || 0).getTime());
      if (version === readVersion.current) setEvents(arr);
    } catch (e) {
      if (version === readVersion.current) { setError(e.message || msg('FE_ADMIN_WEBHOOKS_COULDN_T_LOAD_WEBHOOK_EVENTS', "Couldn't load webhook events")); setEvents(null); }
    } finally { if (version === readVersion.current) setRefreshing(false); }
  };

  useEffect(() => { scopeVersion.current++; setOffset(0); setExpanded(null); }, [adminCampusId]);
  useEffect(() => { setExpanded(null); setEvents(null); void load(); return () => { readVersion.current++; }; }, [filters.provider, filters.status, filters.from_date, filters.to_date, adminCampusId, offset]);
  const changeFilters = (next) => { setOffset(0); setFilters(next); };

  // Replays one failed delivery from the payload the backend stored. Safe to repeat:
  // every handler is idempotent, and this is the only repair available once the
  // provider has stopped retrying (Paystack gives up after a few days).
  const retryEvent = async (e) => {
    if (writeLock.current) return;
    writeLock.current = true;
    const scope = scopeVersion.current;
    setRetrying(e.id);
    try {
      await liveApi.admin.retryWebhookEvent(e.id);
      if (scope !== scopeVersion.current) return;
      toast({ title: msg('FE_ADMIN_WEBHOOKS_RETRIED', 'Delivery reprocessed'), description: e.reference || e.event_type || '' });
      await load();
    } catch (err) {
      if (scope !== scopeVersion.current) return;
      toast({ title: msg('FE_ADMIN_WEBHOOKS_RETRY_FAILED', "Retry failed"), description: err.message, variant: 'destructive' });
    } finally { writeLock.current = false; setRetrying(null); }
  };

  const successCount = (events || []).filter((e) => normalizedStatus(e.status) === 'success').length;
  const failedCount = (events || []).filter((e) => normalizedStatus(e.status) === 'failed').length;

  return (
    <div className="space-y-4">
      {error && <div role="alert" className="text-sm text-destructive"><p>{error}</p><button onClick={load} className="font-bold">{msg('FE_PLATFORM_RETRY', 'Retry')}</button></div>}
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div className="flex items-center gap-2 text-sm font-bold text-foreground">
          <Webhook className="w-4 h-4 text-primary" /> {events ? msg('FE_WEBHOOK_PAGE_COUNT', '{count} deliveries on this page', {count: events.length}) : refreshing ? msg('FE_WEBHOOK_LOADING', 'Loading deliveries…') : '—'}
        </div>
        <button onClick={load} disabled={refreshing} className="flex items-center gap-1.5 px-4 py-2.5 rounded-full bg-secondary text-foreground text-sm font-bold active:scale-95 transition disabled:opacity-50">
          <RefreshCw className={`w-4 h-4 ${refreshing ? 'animate-spin' : ''}`} /> Refresh
        </button>
      </div>

      <div className="flex items-center justify-between text-xs font-bold">
        <button disabled={offset === 0 || refreshing} onClick={() => setOffset(value => Math.max(0, value - pageSize))}>{msg('FE_WEBHOOK_PREVIOUS', 'Previous deliveries')}</button>
        <span>{msg('FE_WEBHOOK_PAGE', 'Page {page}', {page: offset / pageSize + 1})}</span>
        <button disabled={refreshing || !events || events.length < pageSize} onClick={() => setOffset(value => value + pageSize)}>{msg('FE_WEBHOOK_NEXT', 'Next deliveries')}</button>
      </div>
      <Card className="p-3 flex flex-col sm:flex-row sm:items-center gap-2.5">
        <input
          value={filters.provider}
          onChange={(e) => changeFilters({ ...filters, provider: e.target.value })}
          placeholder="Provider (e.g. paystack)"
          className="px-3 py-2 rounded-xl border border-border text-sm flex-1 min-w-[120px]"
        />
        <select
          value={filters.status}
          onChange={(e) => changeFilters({ ...filters, status: e.target.value })}
          className="px-3 py-2 rounded-xl border border-border text-sm"
        >
          <option value="">All statuses</option>
          <option value="success">Success</option>
          <option value="failed">Failed</option>
          <option value="pending">Pending</option>
        </select>
        <div className="flex items-center gap-1.5">
          <input type="date" value={filters.from_date} onChange={(e) => changeFilters({ ...filters, from_date: e.target.value })} className="px-2 py-2 rounded-xl border border-border text-sm" />
          <span className="text-xs text-muted-foreground">→</span>
          <input type="date" value={filters.to_date} onChange={(e) => changeFilters({ ...filters, to_date: e.target.value })} className="px-2 py-2 rounded-xl border border-border text-sm" />
        </div>
      </Card>

      {events != null && events.length > 0 && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2.5">
          <Card className="p-3 text-center"><div className="font-heading font-extrabold text-lg text-foreground">{events.length}</div><div className="text-[10px] font-bold uppercase text-muted-foreground">Total</div></Card>
          <Card className="p-3 text-center"><div className="font-heading font-extrabold text-lg text-success">{successCount}</div><div className="text-[10px] font-bold uppercase text-muted-foreground">Delivered</div></Card>
          <Card className="p-3 text-center"><div className="font-heading font-extrabold text-lg text-destructive">{failedCount}</div><div className="text-[10px] font-bold uppercase text-muted-foreground">Failed</div></Card>
          <Card className="p-3 text-center"><div className="font-heading font-extrabold text-lg text-foreground">{events.length - successCount - failedCount}</div><div className="text-[10px] font-bold uppercase text-muted-foreground">Other</div></Card>
        </div>
      )}

      {events == null && !error ? (
        <div className="space-y-2.5">{Array.from({ length: 5 }).map((_, i) => <Skeleton key={i} className="h-16" />)}</div>
      ) : error ? null : events.length === 0 ? (
        <Card>
          <EmptyState
            icon={Webhook}
            title={msg('FE_WEBHOOK_EMPTY', 'No webhook events recorded')}
            body={msg('FE_WEBHOOK_EMPTY_BODY', 'Incoming payment-provider events appear here with their processing status.')}
          />
        </Card>
      ) : (
        <div className="space-y-2">
          {events.map((e, i) => {
            const isOpen = expanded === (e.id || i);
            const ok = normalizedStatus(e.status) === 'success';
            const failed = normalizedStatus(e.status) === 'failed';
            const ts = e.created_at || e.received_at || e.sent_at;
            return (
              <motion.div key={e.id || i} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: Math.min(i * 0.02, 0.15) }}>
                <Card className="overflow-hidden">
                  <button onClick={() => setExpanded(isOpen ? null : (e.id || i))} className="w-full p-3.5 flex items-center gap-3 text-left">
                    <div className={`w-9 h-9 rounded-xl flex items-center justify-center shrink-0 ${ok ? 'bg-success/15' : failed ? 'bg-destructive/10' : 'bg-secondary'}`}>
                      {ok ? <Check className="w-4.5 h-4.5 text-success" /> : failed ? <X className="w-4.5 h-4.5 text-destructive" /> : <AlertTriangle className="w-4.5 h-4.5 text-accent-foreground" />}
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="font-bold text-sm text-foreground truncate">{e.provider || e.source || 'Webhook'}</span>
                        <span className="text-[11px] text-muted-foreground font-mono truncate">{e.event_type || e.event || e.topic || ''}</span>
                      </div>
                      <div className="text-[11px] text-muted-foreground flex items-center gap-1.5 mt-0.5">
                        <Clock className="w-3 h-3" /> {ts ? `${formatDateTime(ts)} · ${timeAgo(ts)}` : '—'}
                        {e.http_status != null && <span className="font-mono">· HTTP {e.http_status}</span>}
                      </div>
                    </div>
                    <Pill tone={statusTone(e.status)}>{normalizedStatus(e.status)}</Pill>
                  </button>
                  {isOpen && (
                    <div className="px-3.5 pb-3.5 pt-1 border-t border-border space-y-2 animate-fade-in">
                      {e.url && <div className="text-[11px] text-muted-foreground"><span className="font-bold">URL:</span> <span className="font-mono break-all">{e.url}</span></div>}
                      {e.endpoint && <div className="text-[11px] text-muted-foreground"><span className="font-bold">Endpoint:</span> <span className="font-mono break-all">{e.endpoint}</span></div>}
                      {e.attempts != null && <div className="text-[11px] text-muted-foreground"><span className="font-bold">Attempts:</span> {e.attempts}</div>}
                      {e.reference && <div className="text-[11px] text-muted-foreground"><span className="font-bold">Reference:</span> <span className="font-mono break-all">{e.reference}</span></div>}
                      {(e.error || e.error_message) && <div className="text-[11px] text-destructive font-semibold break-all">⚠ {e.error || e.error_message}</div>}
                      {e.payload_redacted && <div className="text-[11px] text-muted-foreground">Payload hidden — this delivery has no campus and may belong to another campus.</div>}
                      {failed && e.id && (
                        <button
                          onClick={() => retryEvent(e)}
                          disabled={retrying !== null}
                          className="flex items-center gap-1.5 px-3 py-2 rounded-full bg-primary text-primary-foreground text-xs font-bold active:scale-95 transition disabled:opacity-50"
                        >
                          <RefreshCw className={`w-3.5 h-3.5 ${retrying === e.id ? 'animate-spin' : ''}`} /> Retry delivery
                        </button>
                      )}
                      {e.response_body && <pre className="text-[10px] text-muted-foreground bg-secondary rounded-lg p-2 overflow-x-auto max-h-40 whitespace-pre-wrap">{typeof e.response_body === 'string' ? e.response_body : JSON.stringify(e.response_body, null, 2)}</pre>}
                      {e.payload && <pre className="text-[10px] text-muted-foreground bg-secondary rounded-lg p-2 overflow-x-auto max-h-40 whitespace-pre-wrap">{typeof e.payload === 'string' ? e.payload : JSON.stringify(e.payload, null, 2)}</pre>}
                      <BreakdownTiles data={e.metadata || e.headers || {}} emptyTitle="" />
                    </div>
                  )}
                </Card>
              </motion.div>
            );
          })}
        </div>
      )}
    </div>
  );
}