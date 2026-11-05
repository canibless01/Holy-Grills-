import { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import {
  Clock, ScrollText, Play, Server, RefreshCw, Eye, User as UserIcon, HeartPulse,
  ShieldAlert,
} from 'lucide-react';
import { liveApi } from '@/lib/liveApi';
import { useHolyGrill } from '@/lib/HolyGrillContext';
import { timeAgo } from '@/lib/hgUtils';
import { toast } from '@/components/ui/use-toast';
import { Card, Skeleton, EmptyState, Modal, Segmented, Pill, Pagination, BreakdownTiles, body } from './ui/AdminKit';
import { msg } from '@/lib/messages';

// System — Cron & Audit. Cron jobs: GET /admin/cron/status + POST /admin/cron/:job
// (super-admin only server-side). Audit log: GET /admin/audit-log with
// limit/offset pagination; rows are the real admin_audit_logs columns.
export default function AdminSystem() {
  const [tab, setTab] = useState('cron');
  return (
    <div className="space-y-4">
      <Segmented
        options={[
          { id: 'cron', label: 'Cron Jobs', icon: Clock },
          { id: 'audit', label: 'Audit Log', icon: ScrollText },
          { id: 'health', label: 'Health', icon: HeartPulse },
        ]}
        value={tab}
        onChange={setTab}
      />
      {tab === 'cron' ? <CronJobs /> : tab === 'audit' ? <AuditLog /> : <HealthCard />}
    </div>
  );
}

// GET /health (public, no auth) — API status + Supabase/Redis connectivity.
// Fields are guarded: known keys render as status tiles, everything else
// scalar renders generically. Nothing is invented.
function HealthCard() {
  const [health, setHealth] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);

  const load = async () => {
    setLoading(true); setError(null);
    try {
      setHealth(body(await liveApi.health.check()));
    } catch (e) {
      setError(e.message);
      setHealth(null);
    }
    setLoading(false);
  };

  useEffect(() => { load(); }, []);

  if (loading) {
    return (
      <div className="space-y-2.5">
        <Skeleton className="h-20" />
        <div className="grid grid-cols-2 gap-3">{Array.from({ length: 2 }).map((_, i) => <Skeleton key={i} className="h-24" />)}</div>
      </div>
    );
  }

  if (error) {
    return (
      <Card>
        <EmptyState
          icon={HeartPulse}
          title="Health check unavailable"
          body={error}
          action={
            <button onClick={load} className="flex items-center gap-1.5 px-4 py-2 rounded-full bg-primary text-white text-xs font-bold active:scale-95 transition">
              <RefreshCw className="w-3.5 h-3.5" /> Retry
            </button>
          }
        />
      </Card>
    );
  }

  const services = [
    { label: 'API', value: health?.status ?? health?.api ?? null, okValues: ['ok', 'success', 'healthy', 'up', true] },
    { label: 'Supabase (Database)', value: health?.supabase ?? health?.database ?? health?.db ?? null, okValues: [true, 'ok', 'connected', 'healthy', 'success'] },
    { label: 'Redis', value: health?.redis ?? null, okValues: [true, 'ok', 'connected', 'healthy', 'success'] },
  ];
  const extras = { ...health };
  delete extras.status; delete extras.api; delete extras.supabase;
  delete extras.database; delete extras.db; delete extras.redis;

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between gap-2">
        <span className="hg-eyebrow">Live connectivity — GET /health (public)</span>
        <button onClick={load} className="p-2 rounded-xl bg-card border border-border text-muted-foreground hover:text-primary hover:border-primary/40 active:scale-95 transition" title="Re-check">
          <RefreshCw className="w-3.5 h-3.5" />
        </button>
      </div>

      <div className="grid grid-cols-3 gap-3">
        {services.map((s) => {
          const v = s.value;
          const known = v != null;
          const ok = known && s.okValues.includes(typeof v === 'string' ? v.toLowerCase() : v);
          return (
            <Card key={s.label} className="p-4 text-center">
              <div className={`w-9 h-9 rounded-2xl mx-auto mb-2 flex items-center justify-center ${!known ? 'bg-secondary' : ok ? 'bg-success/15' : 'bg-destructive/10'}`}>
                <HeartPulse className={`w-4.5 h-4.5 ${!known ? 'text-muted-foreground' : ok ? 'text-success' : 'text-destructive'}`} />
              </div>
              <div className="font-heading font-extrabold text-sm text-foreground">{known ? (typeof v === 'boolean' ? (v ? 'Healthy' : 'Down') : String(v)) : 'No data'}</div>
              <div className="text-[10px] font-bold text-muted-foreground mt-0.5">{s.label}</div>
            </Card>
          );
        })}
      </div>

      <Card className="p-4">
        <BreakdownTiles data={extras} emptyTitle="No additional health details returned." />
      </Card>
    </div>
  );
}

function CronJobs() {
  const { user } = useHolyGrill();
  const isSuperAdmin = user?.role === 'super_admin';
  const [jobs, setJobs] = useState(null);
  const [busy, setBusy] = useState(null);
  const [refreshing, setRefreshing] = useState(false);

  const load = async () => {
    setRefreshing(true);
    try {
      setJobs(await liveApi.admin.getCronStatus());
    } catch (e) {
      toast({ title: msg('FE_ADMIN_SYSTEM_COULDN_T_LOAD_CRON_STATUS', "Couldn't load cron status"), description: e.message, variant: 'destructive' });
      setJobs([]);
    }
    setRefreshing(false);
  };

  useEffect(() => { load(); }, []);

  const run = async (job) => {
    setBusy(job);
    try {
      const res = await liveApi.admin.triggerCron(job);
      // Backend returns { job, status: 'started', triggered_by, note } — the
      // job runs async in a thread, so we surface the backend's own note/status
      // rather than claiming it "ran successfully".
      toast({ title: res?.note || 'Cron job triggered', description: res?.status ? `Status: ${res.status}` : job });
      await load();
    } catch (e) {
      // The only hard super_admin wall in the backend lives here (POST /admin/cron/:job).
      toast({ title: msg('FE_ADMIN_SYSTEM_CRON_TRIGGER_FAILED', 'Cron trigger failed'), description: e.message, variant: 'destructive' });
    }
    setBusy(null);
  };

  if (jobs == null) {
    return (
      <div className="space-y-2.5">
        {Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-16" />)}
      </div>
    );
  }

  return (
    <div className="space-y-2.5">
      <div className="flex items-center gap-2 flex-wrap">
        <div className="flex-1 min-w-[240px] rounded-xl bg-secondary/60 border border-border px-3 py-2.5 text-xs text-muted-foreground flex items-center gap-1.5">
          <Server className="w-3.5 h-3.5 shrink-0" /> Scheduled jobs run automatically. Trigger manually for testing/operations.
        </div>
        <button onClick={load} disabled={refreshing} className="p-2 rounded-xl bg-card border border-border text-muted-foreground hover:text-primary hover:border-primary/40 active:scale-95 transition disabled:opacity-50" title="Refresh">
          <RefreshCw className={`w-3.5 h-3.5 ${refreshing ? 'animate-spin' : ''}`} />
        </button>
      </div>

      {!isSuperAdmin && (
        <div className="flex items-start gap-2 rounded-2xl bg-accent/10 border border-accent/25 p-3 text-[11px] text-foreground/80">
          <ShieldAlert className="w-4 h-4 text-accent shrink-0 mt-0.5" />
          <div>Only a <b>super admin</b> can trigger cron jobs. You can still view job status, the audit log, and health.</div>
        </div>
      )}

      {jobs.map((j, i) => {
        const ok = j.status === 'ok' || j.status === 'success';
        const never = j.status === 'never_run' || !j.status;
        return (
          <motion.div key={j.job || i} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: Math.min(i * 0.03, 0.2) }}>
            <Card className="p-3.5 flex items-center gap-3 hover:border-primary/30 transition-colors">
              <div className={`w-2.5 h-2.5 rounded-full shrink-0 ${ok ? 'bg-success' : never ? 'bg-border' : 'bg-destructive'} ${ok ? 'animate-pulse' : ''}`} />
              <div className="flex-1 min-w-0">
                <div className="font-mono font-bold text-sm text-foreground truncate">{j.job}</div>
                {j.desc && <div className="text-[10px] text-muted-foreground truncate">{j.desc}</div>}
                <div className="text-[11px] text-muted-foreground font-semibold">
                  Last run: {j.last_triggered ? timeAgo(j.last_triggered) : 'Never'} · {j.cadence || '—'}
                </div>
              </div>
              <Pill tone={ok ? 'green' : never ? 'outline' : 'red'} className="hidden sm:inline-flex">{never ? 'never run' : j.status}</Pill>
              <button
                onClick={() => run(j.job)}
                disabled={busy === j.job || !isSuperAdmin}
                title={!isSuperAdmin ? 'Only a super admin can trigger cron jobs' : 'Run job'}
                className="flex items-center gap-1.5 px-3.5 py-2 rounded-full bg-foreground text-white text-xs font-bold active:scale-95 transition disabled:opacity-50 shrink-0"
              >
                {busy === j.job
                  ? <span className="w-3 h-3 border-2 border-white/40 border-t-white rounded-full animate-spin" />
                  : <Play className="w-3 h-3" />}
                Run
              </button>
            </Card>
          </motion.div>
        );
      })}
      {jobs.length === 0 && (
        <Card>
          <EmptyState icon={Server} title="No cron status available" body="Scheduled jobs appear here once the backend reports them." />
        </Card>
      )}
    </div>
  );
}

const PAGE_SIZE = 15;

function AuditLog() {
  const [log, setLog] = useState(null);
  const [page, setPage] = useState(0);
  const [hasMore, setHasMore] = useState(false);
  const [loading, setLoading] = useState(true);
  const [payload, setPayload] = useState(null);

  const load = async () => {
    setLoading(true);
    try {
      const res = await liveApi.admin.getAuditLog({ limit: PAGE_SIZE, offset: page * PAGE_SIZE });
      setLog(res);
      setHasMore(res.length === PAGE_SIZE);
    } catch (e) {
      toast({ title: msg('FE_ADMIN_SYSTEM_COULDN_T_LOAD_THE_AUDIT_LOG', "Couldn't load the audit log"), description: e.message, variant: 'destructive' });
      setLog([]);
    }
    setLoading(false);
  };

  useEffect(() => { load(); }, [page]);

  if (log == null) {
    return <div className="space-y-2.5">{Array.from({ length: 5 }).map((_, i) => <Skeleton key={i} className="h-14" />)}</div>;
  }

  if (log.length === 0) {
    return (
      <Card>
        <EmptyState icon={ScrollText} title="No audit entries" body="Every admin action — settings, roles, orders — lands here with a full before/after trail." />
      </Card>
    );
  }

  return (
    <div className="space-y-2.5">
      {log.map((e, i) => (
        <motion.div key={e.id || i} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: Math.min(i * 0.02, 0.2) }}>
          <Card className="p-3.5 hover:border-primary/30 transition-colors">
            <div className="flex flex-wrap items-center gap-2">
              <span className="font-mono text-xs font-bold text-foreground">{e.action || 'unknown_action'}</span>
              {e.entity_type && <Pill tone="flame">{e.entity_type}</Pill>}
              {e.actor_role && (
                <Pill tone="outline">
                  <UserIcon className="w-2.5 h-2.5" /> {e.actor_role}
                </Pill>
              )}
              <span className="text-[11px] text-muted-foreground font-semibold ml-auto">{e.created_at ? timeAgo(e.created_at) : ''}</span>
            </div>
            <div className="flex items-center gap-3 mt-1.5 flex-wrap text-[11px] text-muted-foreground">
              {e.entity_id && <span className="font-mono truncate max-w-[220px]">{e.entity_id}</span>}
              <button
                onClick={() => setPayload({
                  title: e.action,
                  data: {
                    actor_id: e.actor_id,
                    actor_role: e.actor_role,
                    ip_address: e.ip_address,
                    user_agent: e.user_agent,
                    session_id: e.session_id,
                    before_value: e.before_value,
                    after_value: e.after_value,
                    metadata: e.metadata,
                  },
                })}
                className="font-extrabold text-primary inline-flex items-center gap-1 hover:underline"
              >
                <Eye className="w-3 h-3" /> Payload
              </button>
            </div>
          </Card>
        </motion.div>
      ))}

      {(page > 0 || hasMore) && (
        <Card className="p-3">
          <Pagination page={page} canPrev={page > 0} canNext={hasMore} onPrev={() => setPage((p) => Math.max(0, p - 1))} onNext={() => setPage((p) => p + 1)} busy={loading} />
        </Card>
      )}

      <Modal open={!!payload} onClose={() => setPayload(null)} title={`Payload — ${payload?.title || ''}`} wide>
        <pre className="text-[11px] font-mono bg-secondary/60 rounded-xl p-3 overflow-x-auto max-h-[50vh] text-foreground whitespace-pre-wrap">
          {JSON.stringify(payload?.data ?? {}, null, 2)}
        </pre>
      </Modal>
    </div>
  );
}