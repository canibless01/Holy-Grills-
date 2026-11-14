import { useState, useEffect, useCallback, useRef } from 'react';
import { useCmsCreateIntent } from '@/lib/useCmsCreateIntent';
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
  const [loadError, setLoadError] = useState(false);
  const [tagOpen, setTagOpen] = useState(false);
  const untagLock=useRef(false);const [untagBusy,setUntagBusy]=useState(false);

  const load = useCallback(async () => {
    setLoading(true); setLoadError(false);
    try {
      setRows(await liveApi.ambassadors.listStaff());
    } catch (e) {
      setLoadError(true); toast({ title: e.message, variant: 'destructive' });
    } finally {
      setLoading(false);
    }
  }, []);
  useEffect(() => { load(); }, [load]);

  const untag = async (ambassadorId: string, name: string) => {
    if(untagLock.current)return;
    if (!window.confirm(msg('FE_ADMIN_AMBASSADOR_UNTAG_CONFIRM', 'Remove the Campus Ambassador tag? Historical attribution records are retained.'))) return;
    untagLock.current=true;setUntagBusy(true);
    try {
      await liveApi.ambassadors.untag(ambassadorId);
      toast({ title: `${name} removed from the programme` });
      load();
    } catch (e) {
      toast({ title: e.message, variant: 'destructive' });
    }finally{untagLock.current=false;setUntagBusy(false);}
  };

  if (loading) return <StaffPanelSkeleton />;

  return (
    <div className="space-y-4">
      {loadError && <p role="alert" className="text-sm text-destructive">{msg('FE_AMBASSADOR_WORKSPACE_READ_FAILED', 'Programme data could not be loaded.')}{' '}
        <button onClick={() => { void load(); }} className="underline">{msg('FE_LOOKUP_RETRY', 'Retry')}</button>
      </p>}
      <div className="flex flex-wrap gap-1 p-1 rounded-2xl bg-secondary w-full sm:w-fit">
        {[{ id: 'ambassadors', label: msg('FE_ADMIN_AMBASSADORS_TITLE', 'Campus Ambassadors'), icon: Users },
          { id: 'milestones', label: msg('FE_ADMIN_AMBASSADOR_MILESTONES', 'Performance milestones'), icon: Trophy }].map((t) => (
          <button key={t.id} onClick={() => setTab(t.id)}
            className={`flex min-w-0 flex-1 sm:flex-none items-center justify-center gap-1.5 px-3 py-2 rounded-xl text-xs font-bold ${tab === t.id ? 'bg-card text-primary shadow-sm' : 'text-muted-foreground'}`}>
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
            <AmbassadorRow key={r.ambassador.profile_id} row={r} canUntag={isFinancialAdmin} disabled={untagBusy} onUntag={untag} />
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
      onClick={async()=>{try{await navigator.clipboard.writeText(link);setCopied(true);setTimeout(()=>setCopied(false),1500);}catch{toast({title:msg('FE_AMBASSADOR_CLIPBOARD_FAILED','Copy failed. Select and copy the link or caption instead.'),variant:'destructive'});}}}
      className="inline-flex items-center gap-1 text-xs text-primary font-bold hover:underline">
      {copied ? <Check className="w-3.5 h-3.5" /> : <Copy className="w-3.5 h-3.5" />}
      {copied ? msg('FE_AMBASSADOR_LINK_COPIED', 'Tracking link copied') : msg('FE_AMBASSADOR_COPY_LINK', 'Copy link')}
    </button>
  );
}

function AmbassadorRow({ row, canUntag, onUntag, disabled=false }: { row: any; canUntag: boolean; disabled?:boolean; onUntag: (id: string, name: string) => void }) {
  const name = row.profile?.full_name || row.profile?.nickname || 'Ambassador';
  const m = row.month || {};
  return (
    <div className="rounded-2xl border border-border p-3 grid grid-cols-[minmax(0,1fr)_auto] gap-3 sm:flex sm:items-center sm:flex-wrap">
      <div className="min-w-0 sm:flex-1">
        <div className="font-bold text-sm text-foreground flex flex-wrap items-center gap-2">
          {name}
          <Pill tone="amber">Campus Ambassador</Pill>
        </div>
        <div className="text-xs text-muted-foreground mt-0.5">
          {row.profile?.phone || '—'} · {msg('FE_ADMIN_AMBASSADOR_MONTH', 'Programme month')} {row.ambassador && m.signups !== undefined ? '' : ''}
        </div>
        <div className="mt-1"><CopyLink link={row.tracking_link} /></div>
      </div>
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-center col-span-2 sm:order-none order-last w-full sm:w-auto">
        <Stat label={msg('FE_ADMIN_AMBASSADOR_SIGNUPS', 'Signups')} value={row.lifetime?.total_signups ?? 0} sub={`${m.signups ?? 0} ${msg('FE_AMBASSADOR_MONTH_ACTIVITY', 'this month').toLowerCase()}`} />
        <Stat label={msg('FE_ADMIN_AMBASSADOR_ORDERS', 'Referred orders')} value={row.lifetime?.total_orders ?? 0} sub={`${m.orders ?? 0} ${msg('FE_AMBASSADOR_MONTH_ACTIVITY', 'this month').toLowerCase()}`} />
        <Stat label={msg('FE_ADMIN_AMBASSADOR_COMPLETION', 'Sharing completion')} value={`${m.completion_rate ?? 0}%`} sub={`${m.shared_count ?? 0}/${m.assigned_count ?? 0}`} />
        <Stat label={msg('FE_ADMIN_AMBASSADOR_TARGET', 'Share target')} value={`${m.share_target_progress ?? 0}%`} sub={`${m.monthly_share_target ?? 0}/mo`} />
      </div>
      {canUntag && (
        <button disabled={disabled} onClick={() => onUntag(row.ambassador.profile_id, name)} title={msg('FE_ADMIN_AMBASSADOR_UNTAG', 'Remove Ambassador tag')}
          className="p-2 rounded-lg hover:bg-destructive/10">
          <Trash2 className="w-4 h-4 text-destructive" />
        </button>
      )}
    </div>
  );
}

function Stat({ label, value, sub }: { label: string; value: any; sub?: string }) {
  return (
    <div className="min-w-0 break-words">
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

  const [searchError,setSearchError]=useState(false);const [retry,setRetry]=useState(0);const searchVersion=useRef(0);const tagLock=useRef(false);
  useEffect(()=>{
    const current=++searchVersion.current;setResults([]);setSearchError(false);setSearching(false);
    if(query.trim().length<2)return;
    setSearching(true);
    const timer=setTimeout(()=>{liveApi.admin.getUsers({q:query.trim(),limit:8}).then(rows=>{if(current===searchVersion.current)setResults((rows||[]).filter(row=>row.is_active!==false).slice(0,8));}).catch(()=>{if(current===searchVersion.current)setSearchError(true);}).finally(()=>{if(current===searchVersion.current)setSearching(false);});},250);
    return()=>{clearTimeout(timer);searchVersion.current++;};
  },[query,retry]);

  const tag = async (userId: string) => {
    if(tagLock.current)return;tagLock.current=true;setBusy(true);
    try {
      await liveApi.ambassadors.tag(userId);
      toast({ title: msg('FE_ADMIN_AMBASSADOR_TAG', 'Add Ambassador tag') + ' ✓' });
      onTagged();
      onClose();
    } catch (e) {
      toast({ title: e.message, variant: 'destructive' });
    } finally {
      tagLock.current=false;setBusy(false);
    }
  };

  return (
    <Modal open onClose={()=>{if(!busy)onClose();}} title={msg('FE_ADMIN_AMBASSADOR_TAG', 'Add Ambassador tag')}>
      <div className="space-y-3">
        <Field label={msg('FE_ADMIN_AMBASSADOR_SEARCH_PLACEHOLDER', 'Search a student by name, email or referral code')}>
          <div className="relative">
            <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
            <TextInput value={query} disabled={busy} onChange={(e) => setQuery(e.target.value)} placeholder="Name, email or code" className="pl-9" />
          </div>
        </Field>
        {searchError&&<p role="alert" className="text-sm text-destructive">{msg('FE_AMBASSADOR_WORKSPACE_READ_FAILED','Programme data could not be loaded.')} <button onClick={()=>setRetry(v=>v+1)} className="underline">{msg('FE_LOOKUP_RETRY','Retry')}</button></p>}
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
  const { user } = useHolyGrill();
  const [items, setItems] = useState<any[]>([]);
  const [open, setOpen] = useState(false);
  const [editing,setEditing]=useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(false);
  const load = useCallback(async () => {
    setLoading(true); setLoadError(false);
    try { setItems(await liveApi.ambassadors.listMilestones()); }
    catch (e) { setLoadError(true); toast({ title: e.message, variant: 'destructive' }); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { load(); }, [load]);
  if (loading) return <StaffPanelSkeleton />;
  return (
    <Card className="p-4 space-y-3">
      {loadError && <p role="alert" className="text-sm text-destructive">{msg('FE_AMBASSADOR_WORKSPACE_READ_FAILED', 'Programme data could not be loaded.')}{' '}
        <button onClick={() => { void load(); }} className="underline">{msg('FE_LOOKUP_RETRY', 'Retry')}</button>
      </p>}
      <div className="flex justify-between items-center">
        <p className="text-xs text-muted-foreground">{items.length} configured milestone{items.length === 1 ? '' : 's'}</p>
        {!readOnly && (
          <button disabled={loadError} onClick={() => {setEditing(null);setOpen(true);}} className="flex items-center gap-1 px-3 py-2 rounded-full bg-primary text-white text-xs font-bold">
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
          {!readOnly&&(m.campus_id || user?.role==='super_admin')&&<button type="button" disabled={loadError} onClick={()=>{setEditing(m);setOpen(true);}} className="rounded-full border border-border px-3 py-2 text-xs font-bold">{msg('FE_AMBASSADOR_EDIT_MILESTONE','Edit milestone')}</button>}
        </div>
      ))}
      {open && <MilestoneModal initial={editing} onClose={() => setOpen(false)} onSaved={load} />}
    </Card>
  );
}

function MilestoneModal({ onClose, onSaved,initial }: { onClose: () => void; onSaved: () => void;initial?:any }) {
  const {user}=useHolyGrill();const intent=useCmsCreateIntent();const lock=useRef(false);
  const [form, setForm] = useState({
    metric: 'orders', threshold: 3, reward_type: 'meal_discount', reward_amount: 3000,
    reward_uses: 1, validity_days: 14, auto_issue: false, global: user?.role==='super_admin',is_active:true,...(initial||{}),
  });
  const [busy, setBusy] = useState(false);
  const set = (k: string, v: any) => setForm((f) => ({ ...f, [k]: v }));
  const save = async () => {
    if(lock.current)return;lock.current=true;setBusy(true);
    try {
      const {metric,threshold,reward_type,reward_amount,reward_uses,validity_days,auto_issue,is_active}=form;
      const payload=intent.body({metric,threshold,reward_type,reward_amount,reward_uses,validity_days,auto_issue,is_active,...(initial?{expected_updated_at:initial.updated_at}:{global:form.global})});
      if(initial)await liveApi.ambassadors.updateMilestone(initial.id,payload);else await liveApi.ambassadors.createMilestone(payload);
      intent.clear();
      toast({ title: msg('FE_ADMIN_AMBASSADOR_MILESTONE_NEW', 'New milestone') + ' ✓' });
      onSaved(); onClose();
    } catch (e) {
      toast({ title: e.message, variant: 'destructive' });
    } finally { lock.current=false;setBusy(false); }
  };
  return (
    <Modal open onClose={()=>{if(!busy)onClose();}} title={initial?msg('FE_AMBASSADOR_EDIT_MILESTONE','Edit milestone'):msg('FE_ADMIN_AMBASSADOR_MILESTONE_NEW','New milestone')}>
      <form onSubmit={e=>{e.preventDefault();void save();}}><fieldset disabled={busy} className="space-y-3">
        <Field label="Metric">
          <select value={form.metric} onChange={(e) => set('metric', e.target.value)} className="w-full mt-1 p-2.5 rounded-xl border border-border text-sm">
            {METRICS.map((m) => <option key={m.value} value={m.value}>{m.label}</option>)}
          </select>
        </Field>
        <Field label="Threshold"><TextInput required type="number" min={1} value={form.threshold} onChange={(e) => set('threshold', Number(e.target.value))} /></Field>
        <Field label={msg('FE_ADMIN_AMBASSADOR_GRANT_TYPE', 'Reward type')}>
          <select value={form.reward_type} onChange={(e) => set('reward_type', e.target.value)} className="w-full mt-1 p-2.5 rounded-xl border border-border text-sm">
            {REWARD_TYPES.map((r) => <option key={r.value} value={r.value}>{r.label}</option>)}
          </select>
        </Field>
        <div className="grid grid-cols-2 gap-3">
          <Field label={msg('FE_ADMIN_AMBASSADOR_GRANT_AMOUNT', 'Amount / quantity')}>
            <TextInput required type="number" step={form.reward_type==='meal_discount'?0.01:1} min={form.reward_type==='meal_discount'?0.01:1} max={form.reward_type==='free_side'?20:1000000} value={form.reward_amount} onChange={(e) => set('reward_amount', Number(e.target.value))} />
          </Field>
          <Field label={msg('FE_ADMIN_AMBASSADOR_GRANT_USES', 'Number of uses')}>
            <TextInput required type="number" min={1} max={100} value={form.reward_uses} onChange={(e) => set('reward_uses', Number(e.target.value))} />
          </Field>
        </div>
        <Field label={msg('FE_ADMIN_AMBASSADOR_GRANT_VALIDITY', 'Validity (days)')}>
          <TextInput required type="number" min={1} max={365} value={form.validity_days} onChange={(e) => set('validity_days', Number(e.target.value))} />
        </Field>
        {!initial&&user?.role==='super_admin'&&<label className="flex items-center gap-2 text-xs font-bold">
          <input type="checkbox" checked={form.global} onChange={(e) => set('global', e.target.checked)} /> Global (all campuses)
        </label>}
        <label className="flex items-center gap-2 text-xs font-bold">
          <input type="checkbox" checked={form.auto_issue} onChange={(e) => set('auto_issue', e.target.checked)} />
          {msg('FE_ADMIN_AMBASSADOR_AUTO_ISSUE', 'Issue reward automatically when reached')}
        </label>
        <label className="flex items-center gap-2 text-xs font-bold"><input type="checkbox" checked={form.is_active} onChange={e=>set('is_active',e.target.checked)}/>{msg('FE_AMBASSADOR_MILESTONE_ACTIVE','Milestone active')}</label>
        <button type="submit" disabled={busy} className="w-full py-3 rounded-full bg-gradient-cta text-white font-bold text-sm disabled:opacity-50">
          {busy ? 'Saving…' : 'Save milestone'}
        </button>
      </fieldset></form>
    </Modal>
  );
}
