import { confirmAction } from '@/lib/confirmAction';
import { useState, useEffect, useRef } from 'react';
import { localStore } from '@/lib/storage';
import { Plus, Pencil, Trash2, Save, Zap, Clock, Gift, Check, Search } from 'lucide-react';
import { liveApi as mockApi } from '@/lib/liveApi';
import { useHolyGrill } from '@/lib/HolyGrillContext';
import { useCampus } from '@/lib/campusContext';
import LoadingSpinner from '@/components/LoadingSpinner';
import { toast } from '@/components/ui/use-toast';
import { Card, Field, TextInput, Pill, SectionHeader, Modal } from './AdminShared';
import { useIsSuperAdmin, SuperAdminBadge } from './SuperAdminGate';
import { msg, useMessages } from '@/lib/messages';
import { displayName, displayInitial } from '@/lib/displayName';

// DB-backed prize pool (GET/POST/PATCH/DELETE /admin/exclusive-spin-pool).
// Every prize carries a campus scope: campus_id = null is GLOBAL — editing it
// changes the odds for every campus, so the UI must flag it loudly.
export default function AdminExclusiveSpin() {
  useMessages();
  const { user } = useHolyGrill();
  const isSuperAdmin = useIsSuperAdmin();
  const { campuses } = useCampus();
  const campusName = (id) => campuses.find((c) => c.id === id)?.name || 'This campus';
  const [template, setTemplate] = useState([]);
  const [prizes, setPrizes] = useState([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(null);
  const [validityDays, setValidityDays] = useState<string | number>(30);
  const [editItem, setEditItem] = useState(null);
  const [adding, setAdding] = useState(false);
  const [savingValidity, setSavingValidity] = useState(false);
  const [busy, setBusy] = useState(null);
  // Grant panel — POST /admin/exclusive-spin-grant; the student is picked through
  // GET /auth/users/search (campus-scoped, rate-limited) instead of a raw user list.
  const [grantUser, setGrantUser] = useState(null);
  const [grantQuery, setGrantQuery] = useState('');
  const [grantResults, setGrantResults] = useState([]);
  const [searching, setSearching] = useState(false);
  const [grantSpins, setGrantSpins] = useState<string | number>(1);
  const [grantReason, setGrantReason] = useState('');
  const [granting, setGranting] = useState(false);
  const grantingRef = useRef(false);

  useEffect(() => { load(); }, []);

  const load = async () => {
    setLoading(true);
    setLoadError(null);
    try {
      const [configuration, prizeRows] = await Promise.all([
        mockApi.admin.getExclusiveSpinConfiguration(),
        mockApi.admin.getExclusiveSpinPrizes({ status: 'pending' }),
      ]);
      setTemplate(configuration.prizes);
      setPrizes(prizeRows);
      setValidityDays(configuration.credit_validity_days);
    } catch (e) { setLoadError(e.message || msg('FE_ADMIN_SPIN_LOAD_FAILED', 'Spin configuration could not be loaded. Please retry.')); }
    setLoading(false);
  };

  const searchStudents = async () => {
    const q = grantQuery.trim();
    if (!q) { setGrantResults([]); return; }
    setSearching(true);
    try {
      const rows = await mockApi.users.search({ q });
      setGrantResults(rows);
      if (rows.length === 0) toast({ title: msg('FE_ADMIN_EXCLUSIVE_SPIN_NO_STUDENTS_MATCHED', 'No students matched'), description: msg('FE_ADMIN_EXCLUSIVE_SPIN_TRY_A_FULL_NAME_NICKNAME_OR_EMAIL', 'Try a full name, nickname or email.') });
    } catch (e) {
      toast({ title: msg('FE_ADMIN_EXCLUSIVE_SPIN_SEARCH_FAILED', 'Search failed'), description: e.message, variant: 'destructive' });
    }
    setSearching(false);
  };

  const grantSpinsToUser = async () => {
    if (!grantUser) { toast({ title: msg('FE_ADMIN_EXCLUSIVE_SPIN_PICK_A_STUDENT_FIRST', 'Pick a student first'), variant: 'destructive' }); return; }
    const spins = Number(grantSpins);
    if (!(Number.isInteger(spins) && spins >= 1 && spins <= 10)) { toast({ title: msg('FE_ADMIN_EXCLUSIVE_SPIN_SPINS_MUST_BE_1_10', 'Spins must be 1-10'), variant: 'destructive' }); return; }
    if (grantingRef.current) return;
    grantingRef.current = true;
    setGranting(true);
    try {
      const payload = { user_id: grantUser.id, spins, reason: grantReason.trim() || undefined };
      const key = `hg_exclusive_spin_grant:${user?.id}`;
      const fingerprint = JSON.stringify(payload);
      let pending;
      try { pending = JSON.parse(localStore.getItem(key) || 'null'); } catch { pending = null; }
      if (!pending || pending.fingerprint !== fingerprint) { pending = { fingerprint, intent_key: crypto.randomUUID() }; localStore.setItem(key, JSON.stringify(pending)); }
      const res = await mockApi.admin.grantExclusiveSpinCredits({ ...payload, intent_key: pending.intent_key });
      localStore.removeItem(key);
      const grantedName = displayName(grantUser);
      toast({
        title: msg('FE_ADMIN_EXCLUSIVE_SPIN_SPINS_GRANTED', '✅ Spins granted'),
        description: [
          spins === 1
            ? msg('FE_ADMIN_EXCLUSIVE_SPIN_ONE_SPIN_FOR_NAME', '1 exclusive spin for {name}.', { name: grantedName })
            : msg('FE_ADMIN_EXCLUSIVE_SPIN_SPINS_FOR_NAME', '{count} exclusive spins for {name}.', { count: spins, name: grantedName }),
          res?.expires_at ? msg('FE_ADMIN_EXCLUSIVE_SPIN_CREDIT_EXPIRES_ON', 'Expires {date}.', { date: new Date(res.expires_at).toLocaleDateString() }) : '',
        ].filter(Boolean).join(' '),
      });
      setGrantUser(null);
      setGrantQuery('');
      setGrantResults([]);
      setGrantSpins(1);
      setGrantReason('');
    } catch (e) {
      toast({ title: msg('FE_ADMIN_EXCLUSIVE_SPIN_GRANT_FAILED', 'Grant failed'), description: e.message, variant: 'destructive' });
    }
    grantingRef.current = false;
    setGranting(false);
  };

  const totalWeight = template.reduce((sum, t) => sum + (t.weight || 0), 0);

  const saveItem = async (item) => {
    setBusy('item');
    try {
      const body = { name: item.name, weight: Number(item.weight), campus_id: item.campus_id || null, is_active: item.is_active, reward_config: item.reward_config };
      if (item.id && !item.id.startsWith('new_')) {
        await mockApi.admin.updateExclusiveSpinTemplateItem(item.id, body);
      } else {
        await mockApi.admin.createExclusiveSpinTemplateItem(body);
      }
      toast({ title: msg('FE_ADMIN_EXCLUSIVE_SPIN_PRIZE_SAVED', '✅ Prize saved'), description: msg('FE_ADMIN_EXCLUSIVE_SPIN_NAME_UPDATED_IN_THE_EXCLUSIVE_SPIN', '"{name}" updated in the exclusive spin template.', { name: item.name }) });
      setEditItem(null); setAdding(false);
      await load();
    } catch (e) {
      toast({ title: msg('FE_ADMIN_EXCLUSIVE_SPIN_FAILED_TO_SAVE_PRIZE', 'Failed to save prize'), description: e.message, variant: 'destructive' });
    }
    setBusy(null);
  };

  const deleteItem = async (id, name) => {
    if (!(await confirmAction({ title: msg('FE_ADMIN_SPIN_DEACTIVATE_CONFIRM', 'Deactivate "{name}" from the spin pool?', { name }), destructive: true }))) return;
    setBusy(id);
    try {
      const res = await mockApi.admin.deleteExclusiveSpinTemplateItem(id);
      toast({ title: res?.message || msg('FE_ADMIN_SPIN_DEACTIVATED', 'Prize deactivated') });
      await load();
    } catch (e) {
      toast({ title: msg('FE_ADMIN_EXCLUSIVE_SPIN_FAILED_TO_DELETE', 'Failed to delete'), description: e.message, variant: 'destructive' });
    }
    setBusy(null);
  };

  const saveValidity = async () => {
    if (!Number.isInteger(Number(validityDays)) || Number(validityDays)<1 || Number(validityDays)>365) { toast({ title: msg('FE_ADMIN_SPIN_INVALID_VALIDITY', 'Choose a whole number from 1 to 365 days.'), variant:'destructive' }); return; }
    setSavingValidity(true);
    try {
      await mockApi.admin.updateExclusiveSpinValidityDays({ value: Number(validityDays) });
      toast({ title: msg('FE_ADMIN_EXCLUSIVE_SPIN_VALIDITY_UPDATED', '✅ Validity updated'), description: msg('FE_ADMIN_SPIN_VALIDITY_SAVED', 'New spin credits expire after {validity_days} days.', { validity_days: validityDays }) });
    } catch (e) {
      toast({ title: msg('FE_ADMIN_EXCLUSIVE_SPIN_FAILED_TO_SAVE', 'Failed to save'), description: e.message, variant: 'destructive' });
    }
    setSavingValidity(false);
  };

  // Mark a physical exclusive-spin prize as fulfilled (PATCH /admin/exclusive-spin-prizes/:id).
  const fulfillPrize = async (id) => {
    setBusy(id);
    try {
      const res = await mockApi.admin.fulfillExclusiveSpinPrize(id);
      toast({ title: res?.message || msg('FE_ADMIN_SPIN_FULFILLED', 'Prize fulfilled') });
      await load();
    } catch (e) {
      toast({ title: msg('FE_ADMIN_EXCLUSIVE_SPIN_FULFILLMENT_FAILED', 'Fulfillment failed'), description: e.message, variant: 'destructive' });
    }
    setBusy(null);
  };

  if (loading) return <LoadingSpinner label={msg('FE_ADMIN_SPIN_LOADING', 'Loading exclusive spin...')} />;
  if (loadError) return <Card><p role="alert" className="text-sm text-destructive">{loadError}</p><button onClick={load}>{msg('FE_ADMIN_SPIN_RETRY', 'Retry')}</button></Card>;

  return (
    <div className="space-y-5">
      <div>
        <SectionHeader
          title={msg('FE_ADMIN_SPIN_EXCLUSIVE_SPIN_PRIZES', "Exclusive Spin Prizes")}
          action={<button onClick={() => setAdding(true)} className="flex items-center gap-1 px-3 py-2 rounded-full bg-primary text-white text-xs font-bold"><Plus className="w-4 h-4" /> {msg('FE_ADMIN_SPIN_ADD_TITLE', 'Add Prize')}</button>}
        />
        <p className="text-xs text-muted-foreground mb-1">{msg('FE_ADMIN_SPIN_POOL_HELP', 'Configure the spin prizes, their reward categories and relative odds. Credits come from leaderboard finishes, tier perks or admin grants.')}</p>
        <div className="rounded-xl tone-warn border border-warn/40 p-2.5 text-[11px] text-warn mb-3">
          {msg('FE_ADMIN_SPIN_SCOPE_HELP', 'Campus prizes replace the global pool for that campus. Global prizes are managed by super admins.')}
        </div>

        {template.length === 0 ? (
          <Card><p className="text-xs text-muted-foreground text-center py-4">{msg('FE_ADMIN_SPIN_NO_PRIZES_CONFIGURED_YET_ADD_PRIZES_TO_BUILD_THE_SPIN_WHEEL', "No prizes configured yet. Add prizes to build the spin wheel.")}</p></Card>
        ) : (
          <div className="space-y-2">
            {template.map((t) => (
              <Card key={t.id}>
                <div className="flex items-center gap-3">
                  <Zap className="w-5 h-5 text-primary shrink-0" />
                  <div className="flex-1">
                    <div className="font-bold text-sm text-foreground">{t.name || t.label}</div>
                    <div className="text-xs text-muted-foreground">{msg('FE_ADMIN_SPIN_WEIGHT_VALUE', 'Weight: {weight}', { weight:t.weight })}</div>
                    <div className="mt-1">
                      {t.campus_id == null
                        ? <Pill tone="flame">{msg('FE_ADMIN_SPIN_GLOBAL_ALL_CAMPUSES', "🌐 Global — all campuses")}</Pill>
                        : <Pill tone="outline">{campusName(t.campus_id)}</Pill>}
                    </div>
                  </div>
                  <button aria-label={msg('FE_ADMIN_SPIN_EDIT_NAME', 'Edit {name}', { name: t.name })} disabled={!isSuperAdmin && t.campus_id !== user?.campus_id} onClick={() => setEditItem(t)} className="p-2 rounded-lg hover:bg-muted"><Pencil className="w-4 h-4 text-muted-foreground" /></button>
                  <button aria-label={msg('FE_ADMIN_SPIN_DEACTIVATE_NAME', 'Deactivate {name}', { name: t.name })} onClick={() => deleteItem(t.id, t.name || t.label)} disabled={busy === t.id || (!isSuperAdmin && t.campus_id !== user?.campus_id)} className="p-2 rounded-lg hover:tone-error"><Trash2 className="w-4 h-4 text-destructive" /></button>
                </div>
              </Card>
            ))}
          </div>
        )}
        {totalWeight > 0 && totalWeight !== 100 && (
          <div className="mt-2 rounded-xl tone-warn border border-warn/40 p-2 text-xs text-warn">
            {msg('FE_ADMIN_SPIN_WEIGHT_TOTAL', 'Total weight: {weight}. Probabilities are normalized within each campus pool.', { weight:totalWeight })}
          </div>
        )}
      </div>

      <div className="grid sm:grid-cols-2 gap-4">
        <Card>
          <SectionHeader title={msg('FE_ADMIN_SPIN_VALIDITY_TITLE', 'Credit validity')} action={<Pill tone="amber"><Clock className="w-3 h-3 inline" /> days</Pill>} />
          <p className="text-xs text-muted-foreground mb-3">{msg('FE_ADMIN_SPIN_VALIDITY_HELP', 'How long newly granted spin credits remain usable. Already won prizes retain their saved fulfilment status.')}</p>
          {isSuperAdmin ? (
            <div className="flex items-end gap-2">
              <Field label={msg('FE_ADMIN_SPIN_VALIDITY_DAYS', "Validity (days)")}><TextInput type="number" value={validityDays} onChange={(e) => setValidityDays(e.target.value)} className="w-28" /></Field>
              <button onClick={saveValidity} disabled={savingValidity} className="flex items-center gap-1.5 px-4 py-2.5 rounded-full bg-gradient-cta text-white text-xs font-bold disabled:opacity-50">
                <Save className="w-3.5 h-3.5" /> {savingValidity ? '...' : msg('FE_ADMIN_SPIN_SAVE', 'Save')}
              </button>
            </div>
          ) : (
            <div className="flex items-center gap-2">
              <span className="font-bold text-sm text-foreground">{validityDays} days</span>
              <SuperAdminBadge />
            </div>
          )}
        </Card>
      </div>

      <Card>
        <SectionHeader title={msg('FE_ADMIN_SPIN_GRANT_SPIN_CREDITS', "Grant Spin Credits")} action={<Pill tone="blue"><Zap className="w-3 h-3 inline" /> admin</Pill>} />
        <p className="text-xs text-muted-foreground mb-3">{msg('FE_ADMIN_SPIN_GRANT_HELP', 'Grant 1–10 spin credits to a customer within your campus scope.')}</p>
        {grantUser ? (
          <div className="space-y-3">
            <div className="flex items-center gap-2 rounded-xl bg-accent/15 border border-border p-3">
              <Zap className="w-4 h-4 text-accent-foreground" />
              <div className="flex-1 min-w-0">
                <div className="font-bold text-sm text-foreground truncate">{displayName(grantUser)}</div>
                <div className="text-[11px] text-muted-foreground truncate">{grantUser.email || grantUser.nickname || '—'}</div>
              </div>
              <button onClick={() => setGrantUser(null)} className="text-xs font-bold text-muted-foreground hover:text-foreground">{msg('FE_ADMIN_SPIN_CHANGE', "Change")}</button>
            </div>
            <div className="flex items-end gap-3">
              <Field label={msg('FE_ADMIN_SPIN_SPINS_1_10', "Spins (1-10)")}><TextInput type="number" min={1} max={10} value={grantSpins} onChange={(e) => setGrantSpins(e.target.value)} className="w-28" /></Field>
              <div className="flex-1"><Field label={msg('FE_ADMIN_SPIN_REASON_OPTIONAL', "Reason (optional)")}><TextInput value={grantReason} onChange={(e) => setGrantReason(e.target.value)} placeholder={msg('FE_ADMIN_SPIN_E_G_CONTEST_PRIZE', "e.g. contest prize")} /></Field></div>
              <button onClick={grantSpinsToUser} disabled={granting} className="flex items-center gap-1.5 px-4 py-2.5 rounded-full bg-gradient-cta text-white text-xs font-bold disabled:opacity-50">
                <Zap className="w-3.5 h-3.5" /> {granting ? msg('FE_ADMIN_SPIN_GRANTING', 'Granting...') : msg('FE_ADMIN_SPIN_GRANT', 'Grant spins')}
              </button>
            </div>
          </div>
        ) : (
          <div className="space-y-3">
            <div className="flex gap-2">
              <input value={grantQuery} onChange={(e) => setGrantQuery(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && searchStudents()} placeholder={msg('FE_ADMIN_SPIN_SEARCH_BY_NAME_NICKNAME_OR_EMAIL', "Search by name, nickname or email")} className="flex-1 p-2.5 rounded-xl border border-border text-sm" />
              <button onClick={searchStudents} disabled={searching} className="flex items-center gap-1 px-4 py-2 rounded-xl bg-secondary text-foreground text-sm font-bold disabled:opacity-50"><Search className="w-4 h-4" /> {searching ? msg('FE_ADMIN_SPIN_SEARCHING', 'Searching...') : msg('FE_ADMIN_SPIN_SEARCH', 'Search')}</button>
            </div>
            {grantResults.length > 0 && (
              <div className="space-y-1">
                {grantResults.map((u) => (
                  <button key={u.id} onClick={() => setGrantUser(u)} className="w-full flex items-center gap-2 rounded-xl border border-border p-2.5 text-left hover:bg-muted">
                    <div className="w-8 h-8 rounded-full bg-primary/10 text-primary flex items-center justify-center font-bold text-xs">{displayInitial(u, 'S')}</div>
                    <div className="flex-1 min-w-0">
                      <div className="font-bold text-sm text-foreground truncate">{displayName(u)}</div>
                      <div className="text-[11px] text-muted-foreground truncate">{u.email || u.nickname || '—'}</div>
                    </div>
                    <span className="text-[11px] font-bold text-primary">{msg('FE_ADMIN_SPIN_SELECT', "Select")}</span>
                  </button>
                ))}
              </div>
            )}
          </div>
        )}
      </Card>

      <div>
        <SectionHeader title={msg('FE_ADMIN_SPIN_PRIZE_FULFILMENT', "Prize Fulfilment")} action={<Pill tone="amber">{prizes.length} pending</Pill>} />
        <p className="text-xs text-muted-foreground mb-2">{msg('FE_ADMIN_SPIN_PENDING_HELP', 'Physical prizes owed to customers on the selected campus.')}</p>
        {prizes.length === 0 ? (
          <Card><p className="text-xs text-muted-foreground text-center py-4">{msg('FE_ADMIN_SPIN_NO_PENDING_PHYSICAL_PRIZES_ALL_CAUGHT_UP', "No pending physical prizes. All caught up! 🎉")}</p></Card>
        ) : (
          <div className="space-y-2">
            {prizes.map((p) => (
              <Card key={p.id} className="flex items-center gap-3 !p-3">
                <Gift className="w-5 h-5 text-primary shrink-0" />
                <div className="flex-1 min-w-0">
                  <div className="font-bold text-sm text-foreground">{p.full_name || 'User'}</div>
                  <div className="text-xs text-muted-foreground">Won: <span className="font-bold text-primary">{p.prize_name || p.prize || '—'}</span>{p.phone ? ` · ${p.phone}` : ''}{p.created_at ? ` · ${new Date(p.created_at).toLocaleDateString()}` : ''}</div>
                </div>
                <button aria-label={msg('FE_ADMIN_SPIN_FULFILL_NAME', 'Fulfil {name}', { name:p.prize_name })} onClick={() => fulfillPrize(p.id)} disabled={busy === p.id} className="flex items-center gap-1 px-3 py-1.5 rounded-full bg-success text-white text-xs font-bold disabled:opacity-50">
                  <Check className="w-3.5 h-3.5" /> {busy === p.id ? '...' : msg('FE_ADMIN_SPIN_FULFILL', 'Fulfill')}
                </button>
              </Card>
            ))}
          </div>
        )}
      </div>

      {(editItem || adding) && (
        <PrizeModal item={editItem} campuses={campuses} isSuperAdmin={isSuperAdmin} ownCampus={user?.campus_id} onClose={() => { setEditItem(null); setAdding(false); }} onSave={saveItem} busy={busy === 'item'} />
      )}
    </div>
  );
}

function PrizeModal({ item, campuses = [], isSuperAdmin, ownCampus, onClose, onSave, busy }) {
  useMessages();
  const [form, setForm] = useState(item ? { ...item, reward_config: item.reward_config || { kind: 'physical' } } : { name: '', weight: 10, campus_id: isSuperAdmin ? null : ownCampus, is_active: true, reward_config: { kind: 'physical' } });
  const kind = form.reward_config.kind;
  const fields = { hp: 'amount', free_delivery: 'cap', hp_multiplier: 'multiplier' };
  const field = fields[kind];
  return (
    <Modal open onClose={onClose} title={item ? msg('FE_ADMIN_SPIN_EDIT_TITLE', 'Edit Prize') : msg('FE_ADMIN_SPIN_ADD_TITLE', 'Add Prize')}>
      <div className="space-y-3">
        <Field label={msg('FE_ADMIN_SPIN_PRIZE_NAME', "Prize Name")}><TextInput value={form.name || form.label || ''} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder={msg('FE_ADMIN_SPIN_E_G_FREE_SAUSAGE_2_HP_JACKPOT_750', "e.g. Free Sausage ×2, HP Jackpot +750")} /></Field>
        <Field label={msg('FE_ADMIN_SPIN_WEIGHT', 'Relative weight')} hint={msg('FE_ADMIN_SPIN_WEIGHT_HELP', 'Higher weight means a larger share of the active campus pool.')}><TextInput type="number" value={form.weight} onChange={(e) => setForm({ ...form, weight: e.target.value })} /></Field>
        <Field label={msg('FE_ADMIN_SPIN_CAMPUS_SCOPE', "Campus Scope")} hint={msg('FE_ADMIN_SPIN_CAMPUS_HELP', 'Campus scope is fixed after creation. Global prizes are the fallback where no campus prizes are active.')}>
          <select aria-label={msg('FE_ADMIN_SPIN_CAMPUS_SCOPE', 'Campus Scope')} disabled={!!item || !isSuperAdmin} value={form.campus_id || ''} onChange={(e) => setForm({ ...form, campus_id: e.target.value || null })} className="w-full mt-1 p-2.5 rounded-xl border border-border text-sm bg-card">
            {isSuperAdmin && <option value="">{msg('FE_ADMIN_SPIN_GLOBAL_ALL_CAMPUSES', "🌐 Global (all campuses)")}</option>}
            {campuses.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
          </select>
        </Field>
        <Field label={msg('FE_ADMIN_SPIN_KIND', 'Reward category')}>
          <select value={kind} onChange={(e) => { const k=e.target.value; const f=fields[k]; setForm({ ...form, reward_config: f ? { kind:k, [f]:k==='hp_multiplier'?2:100 } : { kind:k } }); }} className="w-full p-2.5 rounded-xl border border-border bg-card text-sm">
            <option value="physical">{msg('FE_ADMIN_SPIN_PHYSICAL', 'Physical prize — campus fulfilment')}</option>
            <option value="hp">{msg('FE_ADMIN_SPIN_HP', 'HP — credited immediately')}</option>
            <option value="free_delivery">{msg('FE_ADMIN_SPIN_DELIVERY', 'Delivery fee credit — next order')}</option>
            <option value="hp_multiplier">{msg('FE_ADMIN_SPIN_MULTIPLIER', 'Food HP multiplier — next delivery')}</option>
          </select>
        </Field>
        {field && <Field label={kind==='hp' ? msg('FE_ADMIN_SPIN_HP_AMOUNT', 'HP amount') : kind==='free_delivery' ? msg('FE_ADMIN_SPIN_DELIVERY_CAP', 'Delivery fee cap (₦)') : msg('FE_ADMIN_SPIN_MULTIPLIER_VALUE', 'HP multiplier')}>
          <TextInput type="number" step={kind==='hp'?1:0.01} min={kind==='hp_multiplier'?1.01:1} value={form.reward_config[field] ?? ''} onChange={(e) => setForm({ ...form, reward_config:{ ...form.reward_config, [field]:Number(e.target.value) } })} />
        </Field>}
        <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={form.is_active} onChange={(e) => setForm({ ...form,is_active:e.target.checked })} />{msg('FE_ADMIN_SPIN_ACTIVE', 'Available in the spin pool')}</label>
        <p className="text-xs text-muted-foreground">{msg('FE_ADMIN_SPIN_SNAPSHOT_HELP', 'Category and value determine fulfilment. Renaming or editing a prize does not change rewards already won.')}</p>
        <button onClick={() => onSave({ ...form, name: form.name || form.label })} disabled={busy || !form.name} className="w-full py-3 rounded-full bg-gradient-cta text-white font-bold text-sm disabled:opacity-50">{busy ? msg('FE_ADMIN_SPIN_SAVING', 'Saving...') : msg('FE_ADMIN_SPIN_SAVE_PRIZE', 'Save Prize')}</button>
      </div>
    </Modal>
  );
}
