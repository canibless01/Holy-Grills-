import { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import { Webhook, RefreshCw, Check, X, AlertTriangle, Clock } from 'lucide-react';
import { liveApi } from '@/lib/liveApi';
import { formatDateTime, timeAgo } from '@/lib/hgUtils';
import { toast } from '@/components/ui/use-toast';
import { Card, Skeleton, EmptyState, Pill, BreakdownTiles } from './ui/AdminKit';
import { msg } from '@/lib/messages';

// GET /admin/webhook-events — the platform's recent webhook delivery log.
// Each row carries the provider, event, status, HTTP code, and timestamps so
// admins can spot failed integrations without digging into server logs.
const statusTone = (s) => {
  if (s === 'success' || s === 'delivered' || s === 'ok') return 'green';
  if (s === 'failed' || s === 'error') return 'red';
  if (s === 'pending' || s === 'retrying' || s === 'queued') return 'amber';
  return 'cocoa';
};

export default function AdminWebhooks() {
  const [events, setEvents] = useState(null);
  const [expanded, setExpanded] = useState(null);
  const [refreshing, setRefreshing] = useState(false);
  const [filters, setFilters] = useState({ provider: '', status: '', from_date: '', to_date: '' });

  const load = async () => {
    setRefreshing(true);
    try {
      const params: Record<string, unknown> = {};
      if (filters.provider) params.provider = filters.provider;
      if (filters.status) params.status = filters.status;
      if (filters.from_date) params.from_date = filters.from_date;
      if (filters.to_date) params.to_date = filters.to_date;
      const list = await liveApi.admin.getWebhookEvents(params);
      const arr = (Array.isArray(list) ? list : []).sort((a, b) => new Date(b.created_at || b.received_at || 0).getTime() - new Date(a.created_at || a.received_at || 0).getTime());
      setEvents(arr);
    } catch (e) {
      toast({ title: msg('FE_ADMIN_WEBHOOKS_COULDN_T_LOAD_WEBHOOK_EVENTS', "Couldn't load webhook events"), description: e.message, variant: 'destructive' });
      setEvents([]);
    }
    setRefreshing(false);
  };

  useEffect(() => { load(); }, [filters.provider, filters.status, filters.from_date, filters.to_date]);

  const successCount = (events || []).filter((e) => ['success', 'delivered', 'ok'].includes(e.status)).length;
  const failedCount = (events || []).filter((e) => ['failed', 'error'].includes(e.status)).length;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div className="flex items-center gap-2 text-sm font-bold text-foreground">
          <Webhook className="w-4 h-4 text-primary" /> {events ? `${events.length} event${events.length === 1 ? '' : 's'}` : 'Loading…'}
        </div>
        <button onClick={load} disabled={refreshing} className="flex items-center gap-1.5 px-4 py-2.5 rounded-full bg-secondary text-foreground text-sm font-bold active:scale-95 transition disabled:opacity-50">
          <RefreshCw className={`w-4 h-4 ${refreshing ? 'animate-spin' : ''}`} /> Refresh
        </button>
      </div>

      <Card className="p-3 flex flex-col sm:flex-row sm:items-center gap-2.5">
        <input
          value={filters.provider}
          onChange={(e) => setFilters({ ...filters, provider: e.target.value })}
          placeholder="Provider (e.g. paystack)"
          className="px-3 py-2 rounded-xl border border-border text-sm flex-1 min-w-[120px]"
        />
        <select
          value={filters.status}
          onChange={(e) => setFilters({ ...filters, status: e.target.value })}
          className="px-3 py-2 rounded-xl border border-border text-sm"
        >
          <option value="">All statuses</option>
          <option value="success">Success</option>
          <option value="failed">Failed</option>
          <option value="pending">Pending</option>
        </select>
        <div className="flex items-center gap-1.5">
          <input type="date" value={filters.from_date} onChange={(e) => setFilters({ ...filters, from_date: e.target.value })} className="px-2 py-2 rounded-xl border border-border text-sm" />
          <span className="text-xs text-muted-foreground">→</span>
          <input type="date" value={filters.to_date} onChange={(e) => setFilters({ ...filters, to_date: e.target.value })} className="px-2 py-2 rounded-xl border border-border text-sm" />
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

      {events == null ? (
        <div className="space-y-2.5">{Array.from({ length: 5 }).map((_, i) => <Skeleton key={i} className="h-16" />)}</div>
      ) : events.length === 0 ? (
        <Card>
          <EmptyState
            icon={Webhook}
            title="No webhook events recorded"
            body="Outgoing webhook deliveries appear here as they happen, with status and response details."
          />
        </Card>
      ) : (
        <div className="space-y-2">
          {events.map((e, i) => {
            const isOpen = expanded === (e.id || i);
            const ok = ['success', 'delivered', 'ok'].includes(e.status);
            const ts = e.created_at || e.received_at || e.sent_at;
            return (
              <motion.div key={e.id || i} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: Math.min(i * 0.02, 0.15) }}>
                <Card className="overflow-hidden">
                  <button onClick={() => setExpanded(isOpen ? null : (e.id || i))} className="w-full p-3.5 flex items-center gap-3 text-left">
                    <div className={`w-9 h-9 rounded-xl flex items-center justify-center shrink-0 ${ok ? 'bg-success/15' : ['failed', 'error'].includes(e.status) ? 'bg-destructive/10' : 'bg-secondary'}`}>
                      {ok ? <Check className="w-4.5 h-4.5 text-success" /> : ['failed', 'error'].includes(e.status) ? <X className="w-4.5 h-4.5 text-destructive" /> : <AlertTriangle className="w-4.5 h-4.5 text-accent-foreground" />}
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
                    <Pill tone={statusTone(e.status)}>{e.status || 'unknown'}</Pill>
                  </button>
                  {isOpen && (
                    <div className="px-3.5 pb-3.5 pt-1 border-t border-border space-y-2 animate-fade-in">
                      {e.url && <div className="text-[11px] text-muted-foreground"><span className="font-bold">URL:</span> <span className="font-mono break-all">{e.url}</span></div>}
                      {e.endpoint && <div className="text-[11px] text-muted-foreground"><span className="font-bold">Endpoint:</span> <span className="font-mono break-all">{e.endpoint}</span></div>}
                      {e.attempts != null && <div className="text-[11px] text-muted-foreground"><span className="font-bold">Attempts:</span> {e.attempts}</div>}
                      {e.error_message && <div className="text-[11px] text-destructive font-semibold break-all">⚠ {e.error_message}</div>}
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