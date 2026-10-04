import { useState, useEffect } from 'react';
import { Plus, Pencil, Trash2, Save, Zap, Clock, Coins, Gift, Check } from 'lucide-react';
import { liveApi as mockApi } from '@/lib/liveApi';
import { useCampus } from '@/lib/campusContext';
import LoadingSpinner from '@/components/LoadingSpinner';
import { toast } from '@/components/ui/use-toast';
import { Card, Field, TextInput, Pill, SectionHeader, Modal } from './AdminShared';
import { useIsSuperAdmin, SuperAdminBadge } from './SuperAdminGate';

// DB-backed prize pool (GET/POST/PATCH/DELETE /admin/exclusive-spin-pool).
// Every prize carries a campus scope: campus_id = null is GLOBAL — editing it
// changes the odds for every campus, so the UI must flag it loudly.
export default function AdminExclusiveSpin() {
  const isSuperAdmin = useIsSuperAdmin();
  const { campuses } = useCampus();
  const campusName = (id) => campuses.find((c) => c.id === id)?.name || 'This campus';
  const [template, setTemplate] = useState([]);
  const [history, setHistory] = useState([]);
  const [prizes, setPrizes] = useState([]);
  const [loading, setLoading] = useState(true);
  const [extraCost, setExtraCost] = useState<string | number>(0);
  const [validityDays, setValidityDays] = useState<string | number>(30);
  const [editItem, setEditItem] = useState(null);
  const [adding, setAdding] = useState(false);
  const [savingCost, setSavingCost] = useState(false);
  const [savingValidity, setSavingValidity] = useState(false);
  const [busy, setBusy] = useState(null);

  useEffect(() => { load(); }, []);

  const load = async () => {
    setLoading(true);
    try {
      const [tmpl, hist, settings, prizeRows] = await Promise.all([
        mockApi.admin.getExclusiveSpinTemplate().catch(() => []),
        mockApi.admin.getExclusiveSpinHistoryAdmin().catch(() => []),
        mockApi.admin.getSystemSettings().catch(() => []),
        mockApi.admin.getExclusiveSpinPrizes({ status: 'pending' }).catch(() => []),
      ]);
      setTemplate(tmpl);
      setHistory(hist);
      setPrizes(prizeRows);
      const costSetting = settings.find(s => s.key === 'exclusive_spin_extra_cost');
      const valSetting = settings.find(s => s.key === 'exclusive_spin_validity_days');
      setExtraCost(costSetting?.value || 0);
      setValidityDays(valSetting?.value || 30);
    } catch { /* empty state */ }
    setLoading(false);
  };

  const totalWeight = template.reduce((sum, t) => sum + (t.weight || 0), 0);

  const saveItem = async (item) => {
    setBusy('item');
    try {
      const body = { name: item.name, weight: Number(item.weight), campus_id: item.campus_id || null };
      if (item.id && !item.id.startsWith('new_')) {
        await mockApi.admin.updateExclusiveSpinTemplateItem(item.id, body);
      } else {
        await mockApi.admin.createExclusiveSpinTemplateItem(body);
      }
      toast({ title: '✅ Prize saved', description: `"${item.name}" updated in the exclusive spin template.` });
      setEditItem(null); setAdding(false);
      await load();
    } catch (e) {
      toast({ title: 'Failed to save prize', description: e.message, variant: 'destructive' });
    }
    setBusy(null);
  };

  const deleteItem = async (id, name) => {
    if (!confirm(`Delete "${name}" from the spin template?`)) return;
    setBusy(id);
    try {
      const res = await mockApi.admin.deleteExclusiveSpinTemplateItem(id);
      toast({ title: res?.message || 'Prize deactivated' });
      await load();
    } catch (e) {
      toast({ title: 'Failed to delete', description: e.message, variant: 'destructive' });
    }
    setBusy(null);
  };

  const saveExtraCost = async () => {
    setSavingCost(true);
    try {
      await mockApi.admin.updateExclusiveSpinExtraCost({ value: Number(extraCost) });
      toast({ title: '✅ Extra spin cost updated', description: `Extra spins now cost ${extraCost} HP.` });
    } catch (e) {
      toast({ title: 'Failed to save', description: e.message, variant: 'destructive' });
    }
    setSavingCost(false);
  };

  const saveValidity = async () => {
    setSavingValidity(true);
    try {
      await mockApi.admin.updateExclusiveSpinValidityDays({ value: Number(validityDays) });
      toast({ title: '✅ Validity updated', description: `Exclusive spin rewards now expire after ${validityDays} days.` });
    } catch (e) {
      toast({ title: 'Failed to save', description: e.message, variant: 'destructive' });
    }
    setSavingValidity(false);
  };

  // Mark a physical exclusive-spin prize as fulfilled (PATCH /admin/exclusive-spin-prizes/:id).
  const fulfillPrize = async (id) => {
    setBusy(id);
    try {
      const res = await mockApi.admin.fulfillExclusiveSpinPrize(id);
      toast({ title: res?.message || 'Prize fulfilled' });
      await load();
    } catch (e) {
      toast({ title: 'Fulfillment failed', description: e.message, variant: 'destructive' });
    }
    setBusy(null);
  };

  if (loading) return <LoadingSpinner label="Loading exclusive spin..." />;

  return (
    <div className="space-y-5">
      <div>
        <SectionHeader
          title="Exclusive Spin Prizes"
          action={<button onClick={() => setAdding(true)} className="flex items-center gap-1 px-3 py-2 rounded-full bg-primary text-white text-xs font-bold"><Plus className="w-4 h-4" /> Add Prize</button>}
        />
        <p className="text-xs text-muted-foreground mb-1">Prizes that appear on the exclusive spin wheel for top leaderboard earners. Weights determine probability — total should add up to 100.</p>
        <div className="rounded-xl bg-amber-50 border border-amber-200 p-2.5 text-[11px] text-amber-800 mb-3">
          ⚠️ Prizes are either <b>Global</b> (campus-wide — they apply to every campus) or scoped to a single campus. Editing a Global prize changes the odds for <i>all</i> campuses.
        </div>

        {template.length === 0 ? (
          <Card><p className="text-xs text-muted-foreground text-center py-4">No prizes configured yet. Add prizes to build the spin wheel.</p></Card>
        ) : (
          <div className="space-y-2">
            {template.map((t) => (
              <Card key={t.id}>
                <div className="flex items-center gap-3">
                  <Zap className="w-5 h-5 text-primary shrink-0" />
                  <div className="flex-1">
                    <div className="font-bold text-sm text-foreground">{t.name || t.label}</div>
                    <div className="text-xs text-muted-foreground">Weight: {t.weight}% {totalWeight > 0 && `(${((t.weight / totalWeight) * 100).toFixed(1)}% chance)`}</div>
                    <div className="mt-1">
                      {t.campus_id == null
                        ? <Pill tone="flame">🌐 Global — all campuses</Pill>
                        : <Pill tone="outline">{campusName(t.campus_id)}</Pill>}
                    </div>
                  </div>
                  <button onClick={() => setEditItem(t)} className="p-2 rounded-lg hover:bg-muted"><Pencil className="w-4 h-4 text-muted-foreground" /></button>
                  <button onClick={() => deleteItem(t.id, t.name || t.label)} disabled={busy === t.id} className="p-2 rounded-lg hover:bg-red-50"><Trash2 className="w-4 h-4 text-red-500" /></button>
                </div>
              </Card>
            ))}
          </div>
        )}
        {totalWeight > 0 && totalWeight !== 100 && (
          <div className="mt-2 rounded-xl bg-amber-50 border border-amber-200 p-2 text-xs text-amber-700">
            ⚠️ Total weight is {totalWeight} (should be 100). Probabilities will be normalized automatically.
          </div>
        )}
      </div>

      <div className="grid sm:grid-cols-2 gap-4">
        <Card>
          <SectionHeader title="Extra Spin Cost" action={<Pill tone="flame"><Coins className="w-3 h-3 inline" /> HP</Pill>} />
          <p className="text-xs text-muted-foreground mb-3">System setting <code>exclusive_spin_extra_cost</code>. Spins themselves are never sold — students only earn them from leaderboard prizes.</p>
          {isSuperAdmin ? (
            <div className="flex items-end gap-2">
              <Field label="Cost (HP)"><TextInput type="number" value={extraCost} onChange={(e) => setExtraCost(e.target.value)} className="w-28" /></Field>
              <button onClick={saveExtraCost} disabled={savingCost} className="flex items-center gap-1.5 px-4 py-2.5 rounded-full bg-gradient-cta text-white text-xs font-bold disabled:opacity-50">
                <Save className="w-3.5 h-3.5" /> {savingCost ? '...' : 'Save'}
              </button>
            </div>
          ) : (
            <div className="flex items-center gap-2">
              <span className="font-bold text-sm text-foreground">{extraCost} HP</span>
              <SuperAdminBadge />
            </div>
          )}
        </Card>

        <Card>
          <SectionHeader title="Reward Validity" action={<Pill tone="amber"><Clock className="w-3 h-3 inline" /> days</Pill>} />
          <p className="text-xs text-muted-foreground mb-3">How long exclusive spin rewards remain valid before expiry.</p>
          {isSuperAdmin ? (
            <div className="flex items-end gap-2">
              <Field label="Validity (days)"><TextInput type="number" value={validityDays} onChange={(e) => setValidityDays(e.target.value)} className="w-28" /></Field>
              <button onClick={saveValidity} disabled={savingValidity} className="flex items-center gap-1.5 px-4 py-2.5 rounded-full bg-gradient-cta text-white text-xs font-bold disabled:opacity-50">
                <Save className="w-3.5 h-3.5" /> {savingValidity ? '...' : 'Save'}
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

      <div>
        <SectionHeader title="Spin History" action={<Pill tone="cocoa">{history.length} spins</Pill>} />
        {history.length === 0 ? (
          <Card><p className="text-xs text-muted-foreground text-center py-4">No spins yet.</p></Card>
        ) : (
          <div className="space-y-2">
            {history.slice(0, 20).map((h) => (
              <div key={h.id} className="rounded-xl bg-white border border-border p-3 flex items-center gap-3">
                <div className="w-8 h-8 rounded-full bg-gradient-cta text-white flex items-center justify-center text-xs font-bold">{(h.user_name || 'U').charAt(0)}</div>
                <div className="flex-1">
                  <div className="font-semibold text-sm text-foreground">{h.user_name || 'User'}</div>
                  <div className="text-xs text-muted-foreground">Won: <span className="font-bold text-primary">{h.prize_name || h.prize || '—'}</span></div>
                </div>
                {h.spun_at && <span className="text-[10px] text-muted-foreground">{new Date(h.spun_at).toLocaleDateString()}</span>}
              </div>
            ))}
          </div>
        )}
      </div>

      <div>
        <SectionHeader title="Prize Fulfilment" action={<Pill tone="amber">{prizes.length} pending</Pill>} />
        <p className="text-xs text-muted-foreground mb-2">Physical exclusive-spin prizes awaiting fulfilment · GET /admin/exclusive-spin-prizes, PATCH /:id.</p>
        {prizes.length === 0 ? (
          <Card><p className="text-xs text-muted-foreground text-center py-4">No pending physical prizes. All caught up! 🎉</p></Card>
        ) : (
          <div className="space-y-2">
            {prizes.map((p) => (
              <Card key={p.id} className="flex items-center gap-3 !p-3">
                <Gift className="w-5 h-5 text-primary shrink-0" />
                <div className="flex-1 min-w-0">
                  <div className="font-bold text-sm text-foreground">{p.full_name || 'User'}</div>
                  <div className="text-xs text-muted-foreground">Won: <span className="font-bold text-primary">{p.prize_name || p.prize || '—'}</span>{p.phone ? ` · ${p.phone}` : ''}{p.created_at ? ` · ${new Date(p.created_at).toLocaleDateString()}` : ''}</div>
                </div>
                <button onClick={() => fulfillPrize(p.id)} disabled={busy === p.id} className="flex items-center gap-1 px-3 py-1.5 rounded-full bg-green-600 text-white text-xs font-bold disabled:opacity-50">
                  <Check className="w-3.5 h-3.5" /> {busy === p.id ? '...' : 'Fulfill'}
                </button>
              </Card>
            ))}
          </div>
        )}
      </div>

      {(editItem || adding) && (
        <PrizeModal item={editItem} campuses={campuses} onClose={() => { setEditItem(null); setAdding(false); }} onSave={saveItem} busy={busy === 'item'} />
      )}
    </div>
  );
}

function PrizeModal({ item, campuses = [], onClose, onSave, busy }) {
  const [form, setForm] = useState(item ? { campus_id: item.campus_id ?? null, ...item } : { name: '', weight: 10, campus_id: null });
  return (
    <Modal open onClose={onClose} title={item ? 'Edit Prize' : 'Add Prize'}>
      <div className="space-y-3">
        <Field label="Prize Name"><TextInput value={form.name || form.label || ''} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="e.g. Free Sausage ×2, HP Jackpot +750" /></Field>
        <Field label="Weight (%)" hint="Higher weight = more likely to land on this prize. Total should add up to 100."><TextInput type="number" value={form.weight} onChange={(e) => setForm({ ...form, weight: e.target.value })} /></Field>
        <Field label="Campus Scope" hint="Global prizes apply to every campus — changing them affects the odds everywhere.">
          <select value={form.campus_id || ''} onChange={(e) => setForm({ ...form, campus_id: e.target.value || null })} className="w-full mt-1 p-2.5 rounded-xl border border-border text-sm bg-card">
            <option value="">🌐 Global (all campuses)</option>
            {campuses.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
          </select>
        </Field>
        <button onClick={() => onSave({ ...form, name: form.name || form.label })} disabled={busy || !form.name} className="w-full py-3 rounded-full bg-gradient-cta text-white font-bold text-sm disabled:opacity-50">{busy ? 'Saving...' : 'Save Prize'}</button>
      </div>
    </Modal>
  );
}