import { useState, useEffect, useCallback } from 'react';
import { Plus, Trash2, Search, Copy, Check, Users, Trophy, Loader2 } from 'lucide-react';
import { liveApi } from '@/lib/liveApi';
import { useHolyGrill } from '@/lib/HolyGrillContext';
import { Card, Field, TextInput, Modal, Pill } from './AdminShared';
import StaffPanelSkeleton from '@/components/skeletons/StaffPanelSkeleton';
import { toast } from '@/components/ui/use-toast';
import { msg } from '@/lib/messages';

const METRICS = [
  { value: 'orders', label: 'Completed referred orders' },
  { value: 'signups', label: 'Attributed signups' },
  { value: 'shares', label: 'Confirmed promo shares' },
];
const REWARD_TYPES = [
  { value: 'hp', label: msg('FE_ADMIN_AMBASSADOR_GRANT_HP', 'Holy Points (HP)') },
  { value: 'free_side', label: msg('FE_ADMIN_AMBASSADOR_GRANT_FREE_SIDE', 'Free side credits') },
  { value: 'meal_discount', label: msg('FE_ADMIN_AMBASSADOR_GRANT_MEAL', 'Meal discount') },
];

export default function AdminAmbassadors() {
  const { user } = useHolyGrill();
  const isFinancialAdmin = ['admin', 'super_admin'].includes(user?.role);
  const [tab, setTab] = useState('ambassadors');
  const [rows, setRows] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [tagOpen, setTagOpen] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setRows(await liveApi.ambassadors.listStaff());
    } catch (e) {
      toast({ title: e.message, variant: 'destructive' });
    } finally {
      setLoading(false);
    }
  }, []);
  useEffect(() => { load(); }, [load]);

  const untag = async (ambassadorId: string, name: string) => {
    if (!window.confirm(msg('FE_ADMIN_AMBASSADOR_UNTAG_CONFIRM', 'Remove the Campus Ambassador tag? Historical attribution records are retained.'))) return;
    try {
      await liveApi.ambassadors.untag(ambassadorId);
      toast({ title: `${name} removed from the programme` });
      load();
    } catch (e) {
      toast({ title: e.message, variant: 'destructive' });
    }
  };

  if (loading) return <StaffPanelSkeleton />;

  return (
    <div className="space-y-4">
      <div className="flex gap-1 p-1 rounded-full bg-secondary w-fit">
        {[{ id: 'ambassadors', label: msg('FE_ADMIN_AMBASSADORS_TITLE', 'Campus Ambassadors'), icon: Users },
          { id: 'milestones', label: msg('FE_ADMIN_AMBASSADOR_MILESTONES', 'Performance milestones'), icon: Trophy }].map((t) => (
          <button key={t.id} onClick={() => setTab(t.id)}
            className={`flex items-center gap-1.5 px-4 py-2 rounded-full text-xs font-bold ${tab === t.id ? 'bg-card text-primary shadow-sm' : 'text-muted-foreground'}`}>
            <t.icon className="w-3.5 h-3.5" />{t.label}
          </button>
        ))}
      </div>

      {tab === 'ambassadors' ? (
        <Card className="p-4 space-y-3">
          <div className="flex justify-between items-center flex-wrap gap-2">
            <p className="text-xs text-muted-foreground">{rows.length} active ambassador{rows.length === 1 ? '' : 's'}</p>
            {isFinancialAdmin && (
              <button onClick={() => setTagOpen(true)} className="flex items-center gap-1 px-3 py-2 rounded-full bg-primary text-white text-xs font-bold">
                <Plus className="w-4 h-4" />{msg('FE_ADMIN_AMBASSADOR_TAG', 'Add Ambassador tag')}
              </button>
            )}
          </div>
          {rows.length === 0 ? (
            <p className="text-sm text-muted-foreground py-8 text-center">{msg('FE_ADMIN_AMBASSADOR_NONE', 'No ambassadors yet. Tag a student from User Management or search above.')}</p>
          ) : rows.map((r) => (
            <AmbassadorRow key={r.ambassador.profile_id} row={r} canUntag={isFinancialAdmin} onUntag={untag} />
          ))}
        </Card>
      ) : (
        <MilestonesTab readOnly={!isFinancialAdmin} />
      )}

      {tagOpen && <TagAmbassadorModal onClose={() => setTagOpen(false)} onTagged={load} />}
    </div>
  );
}

function CopyLink({ link }: { link: string }) {
  const [copied, setCopied] = useState(false);
  if (!link) return <span className="text-xs text-muted-foreground">—</span>;
  return (
    <button
      onClick={() => { navigator.clipboard.writeText(link); setCopied(true); setTimeout(() => setCopied(false), 1500); }}
      className="inline-flex items-center gap-1 text-xs text-primary font-bold hover:underline">
      {copied ? <Check className="w-3.5 h-3.5" /> : <Copy className="w-3.5 h-3.5" />}
      {copied ? msg('FE_AMBASSADOR_LINK_COPIED', 'Tracking link copied') : msg('FE_AMBASSADOR_COPY_LINK', 'Copy link')}
    </button>
  );
}

function AmbassadorRow({ row, canUntag, onUntag }: { row: any; canUntag: boolean; onUntag: (id: string, name: string) => void }) {
  const name = row.profile?.full_name || row.profile?.nickname || 'Ambassador';
  const m = row.month || {};
  return (
    <div className="rounded-2xl border border-border p-3 flex items-center gap-3 flex-wrap">
      <div className="flex-1 min-w-[200px]">
        <div className="font-bold text-sm text-foreground flex items-center gap-2">
          {name}
          <Pill tone="amber">Campus Ambassador</Pill>
        </div>
        <div className="text-xs text-muted-foreground mt-0.5">
          {row.profile?.phone || '—'} · {msg('FE_ADMIN_AMBASSADOR_MONTH', 'Programme month')} {row.ambassador && m.signups !== undefined ? '' : ''}
        </div>
        <div className="mt-1"><CopyLink link={row.tracking_link} /></div>
      </div>
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-center">
        <Stat label={msg('FE_ADMIN_AMBASSADOR_SIGNUPS', 'Signups')} value={row.lifetime?.total_signups ?? 0} sub={`${m.signups ?? 0} ${msg('FE_AMBASSADOR_MONTH_ACTIVITY', 'this month').toLowerCase()}`} />
        <Stat label={msg('FE_ADMIN_AMBASSADOR_ORDERS', 'Referred orders')} value={row.lifetime?.total_orders ?? 0} sub={`${m.orders ?? 0} ${msg('FE_AMBASSADOR_MONTH_ACTIVITY', 'this month').toLowerCase()}`} />
        <Stat label={msg('FE_ADMIN_AMBASSADOR_COMPLETION', 'Sharing completion')} value={`${m.completion_rate ?? 0}%`} sub={`${m.shared_count ?? 0}/${m.assigned_count ?? 0}`} />
        <Stat label={msg('FE_ADMIN_AMBASSADOR_TARGET', 'Share target')} value={`${m.share_target_progress ?? 0}%`} sub={`${m.monthly_share_target ?? 0}/mo`} />
      </div>
      {canUntag && (
        <button onClick={() => onUntag(row.ambassador.profile_id, name)} title={msg('FE_ADMIN_AMBASSADOR_UNTAG', 'Remove Ambassador tag')}
          className="p-2 rounded-lg hover:bg-destructive/10">
          <Trash2 className="w-4 h-4 text-destructive" />
        </button>
      )}
    </div>
  );
}

function Stat({ label, value, sub }: { label: string; value: any; sub?: string }) {
  return (
    <div className="min-w-[86px]">
      <div className="text-[10px] uppercase tracking-wide text-muted-foreground font-bold">{label}</div>
      <div className="font-heading font-extrabold text-sm text-foreground">{value}</div>
      {sub && <div className="text-[10px] text-muted-foreground">{sub}</div>}
    </div>
  );
}

function TagAmbassadorModal({ onClose, onTagged }: { onClose: () => void; onTagged: () => void }) {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<any[]>([]);
  const [busy, setBusy] = useState(false);
  const [searching, setSearching] = useState(false);

  const search = async (term: string) => {
    setQuery(term);
    if (term.trim().length < 2) { setResults([]); return; }
    setSearching(true);
    try {
      setResults((await liveApi.admin.getUsers({ q: term.trim(), limit: 8 })).slice(0, 8));
    } catch {
      setResults([]);
    } finally {
      setSearching(false);
    }
  };

  const tag = async (userId: string) => {
    setBusy(true);
    try {
      await liveApi.ambassadors.tag(userId);
      toast({ title: msg('FE_ADMIN_AMBASSADOR_TAG', 'Add Ambassador tag') + ' ✓' });
      onTagged();
      onClose();
    } catch (e) {
      toast({ title: e.message, variant: 'destructive' });
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal open onClose={onClose} title={msg('FE_ADMIN_AMBASSADOR_TAG', 'Add Ambassador tag')}>
      <div className="space-y-3">
        <Field label={msg('FE_ADMIN_AMBASSADOR_SEARCH_PLACEHOLDER', 'Search a student by name, email or referral code')}>
          <div className="relative">
            <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
            <TextInput value={query} onChange={(e) => search(e.target.value)} placeholder="Name, email or code" className="pl-9" />
          </div>
        </Field>
        {searching && <Loader2 className="w-4 h-4 animate-spin text-primary" />}
        <div className="space-y-2 max-h-72 overflow-y-auto">
          {results.map((u) => (
            <div key={u.id} className="flex items-center justify-between rounded-xl border border-border p-2.5">
              <div className="min-w-0">
                <div className="text-sm font-bold truncate">{u.full_name || u.nickname || u.email}</div>
                <div className="text-[11px] text-muted-foreground truncate">{u.email} · {u.referral_code || '—'}</div>
              </div>
              <button disabled={busy} onClick={() => tag(u.id)}
                className="shrink-0 ml-2 px-3 py-1.5 rounded-full bg-primary text-white text-[11px] font-bold disabled:opacity-50">
                {msg('FE_ADMIN_AMBASSADOR_TAG', 'Add Ambassador tag')}
              </button>
            </div>
          ))}
        </div>
        <p className="text-[11px] text-muted-foreground">{msg('FE_ADMIN_AMBASSADOR_TAG_CONFIRM', 'Add the Campus Ambassador tag to this account? They keep their existing student dashboard.')}</p>
      </div>
    </Modal>
  );
}

function MilestonesTab({ readOnly }: { readOnly: boolean }) {
  const [items, setItems] = useState<any[]>([]);
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(true);
  const load = useCallback(async () => {
    try { setItems(await liveApi.ambassadors.listMilestones()); }
    catch (e) { toast({ title: e.message, variant: 'destructive' }); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { load(); }, [load]);
  if (loading) return <StaffPanelSkeleton />;
  return (
    <Card className="p-4 space-y-3">
      <div className="flex justify-between items-center">
        <p className="text-xs text-muted-foreground">{items.length} configured milestone{items.length === 1 ? '' : 's'}</p>
        {!readOnly && (
          <button onClick={() => setOpen(true)} className="flex items-center gap-1 px-3 py-2 rounded-full bg-primary text-white text-xs font-bold">
            <Plus className="w-4 h-4" />{msg('FE_ADMIN_AMBASSADOR_MILESTONE_NEW', 'New milestone')}
          </button>
        )}
      </div>
      {items.map((m) => (
        <div key={m.id} className="rounded-xl border border-border p-3 flex items-center justify-between gap-2 flex-wrap">
          <div>
            <div className="text-sm font-bold">
              {METRICS.find((x) => x.value === m.metric)?.label || m.metric} ≥ {m.threshold}
              {m.campus_id ? <Pill tone="blue">campus</Pill> : <Pill tone="green">global</Pill>}
              {!m.is_active && <Pill tone="red">inactive</Pill>}
            </div>
            <div className="text-[11px] text-muted-foreground">
              {REWARD_TYPES.find((r) => r.value === m.reward_type)?.label} · {m.reward_amount} · {m.validity_days}d
              {m.auto_issue ? ` · ${msg('FE_ADMIN_AMBASSADOR_AUTO_ISSUE', 'Issue reward automatically when reached')}` : ''}
            </div>
          </div>
        </div>
      ))}
      {open && <MilestoneModal onClose={() => setOpen(false)} onSaved={load} />}
    </Card>
  );
}

function MilestoneModal({ onClose, onSaved }: { onClose: () => void; onSaved: () => void }) {
  const [form, setForm] = useState({
    metric: 'orders', threshold: 3, reward_type: 'meal_discount', reward_amount: 3000,
    reward_uses: 1, validity_days: 14, auto_issue: false, global: true,
  });
  const [busy, setBusy] = useState(false);
  const set = (k: string, v: any) => setForm((f) => ({ ...f, [k]: v }));
  const save = async () => {
    setBusy(true);
    try {
      await liveApi.ambassadors.createMilestone(form);
      toast({ title: msg('FE_ADMIN_AMBASSADOR_MILESTONE_NEW', 'New milestone') + ' ✓' });
      onSaved(); onClose();
    } catch (e) {
      toast({ title: e.message, variant: 'destructive' });
    } finally { setBusy(false); }
  };
  return (
    <Modal open onClose={onClose} title={msg('FE_ADMIN_AMBASSADOR_MILESTONE_NEW', 'New milestone')}>
      <div className="space-y-3">
        <Field label="Metric">
          <select value={form.metric} onChange={(e) => set('metric', e.target.value)} className="w-full mt-1 p-2.5 rounded-xl border border-border text-sm">
            {METRICS.map((m) => <option key={m.value} value={m.value}>{m.label}</option>)}
          </select>
        </Field>
        <Field label="Threshold"><TextInput type="number" min={1} value={form.threshold} onChange={(e) => set('threshold', Number(e.target.value))} /></Field>
        <Field label={msg('FE_ADMIN_AMBASSADOR_GRANT_TYPE', 'Reward type')}>
          <select value={form.reward_type} onChange={(e) => set('reward_type', e.target.value)} className="w-full mt-1 p-2.5 rounded-xl border border-border text-sm">
            {REWARD_TYPES.map((r) => <option key={r.value} value={r.value}>{r.label}</option>)}
          </select>
        </Field>
        <div className="grid grid-cols-2 gap-3">
          <Field label={msg('FE_ADMIN_AMBASSADOR_GRANT_AMOUNT', 'Amount / quantity')}>
            <TextInput type="number" min={1} value={form.reward_amount} onChange={(e) => set('reward_amount', Number(e.target.value))} />
          </Field>
          <Field label={msg('FE_ADMIN_AMBASSADOR_GRANT_USES', 'Number of uses')}>
            <TextInput type="number" min={1} value={form.reward_uses} onChange={(e) => set('reward_uses', Number(e.target.value))} />
          </Field>
        </div>
        <Field label={msg('FE_ADMIN_AMBASSADOR_GRANT_VALIDITY', 'Validity (days)')}>
          <TextInput type="number" min={1} value={form.validity_days} onChange={(e) => set('validity_days', Number(e.target.value))} />
        </Field>
        <label className="flex items-center gap-2 text-xs font-bold">
          <input type="checkbox" checked={form.global} onChange={(e) => set('global', e.target.checked)} /> Global (all campuses)
        </label>
        <label className="flex items-center gap-2 text-xs font-bold">
          <input type="checkbox" checked={form.auto_issue} onChange={(e) => set('auto_issue', e.target.checked)} />
          {msg('FE_ADMIN_AMBASSADOR_AUTO_ISSUE', 'Issue reward automatically when reached')}
        </label>
        <button disabled={busy} onClick={save} className="w-full py-3 rounded-full bg-gradient-cta text-white font-bold text-sm disabled:opacity-50">
          {busy ? 'Saving…' : 'Save milestone'}
        </button>
      </div>
    </Modal>
  );
}
