import { useState, useEffect } from 'react';
import { Save, Plus, Pencil, Trash2, Gift, Clock, Search, Zap } from 'lucide-react';
import { liveApi as mockApi } from '@/lib/liveApi';
import LoadingSpinner from '@/components/LoadingSpinner';
import { toast } from '@/components/ui/use-toast';
import { Card, Field, TextInput, Pill, SectionHeader, Modal, Toggle } from './AdminShared';
import ImageUploader from './ImageUploader';
import { useIsSuperAdmin, SuperAdminBadge } from './SuperAdminGate';
import { msg } from '@/lib/messages';

// Free side credits (free_sides.py).
//   • The sides students can pick live in the free_side_items TABLE — the public
//     GET /free-sides reads it directly — so they are curated here with
//     /free-sides/admin/items (POST/PATCH/DELETE). The old system_settings
//     `free_side_options` blob this page used to edit is dead config: nothing
//     reads it, so writing it changed nothing for students.
//   • Credits are granted with POST /free-sides/admin/credits, picking the student
//     through GET /auth/users/search (campus-scoped, rate-limited).
export default function AdminFreeCredits() {
  const isSuperAdmin = useIsSuperAdmin();
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [validityDays, setValidityDays] = useState<string | number>(60);
  const [savingValidity, setSavingValidity] = useState(false);
  const [editItem, setEditItem] = useState(null);
  const [busy, setBusy] = useState(null);
  // Grant panel state
  const [grantUser, setGrantUser] = useState(null);
  const [grantQuery, setGrantQuery] = useState('');
  const [grantResults, setGrantResults] = useState([]);
  const [searching, setSearching] = useState(false);
  const [grantCount, setGrantCount] = useState<string | number>(1);
  const [grantReason, setGrantReason] = useState('');
  const [granting, setGranting] = useState(false);

  useEffect(() => { load(); }, []);

  const load = async () => {
    setLoading(true);
    try {
      const [sideItems, settings] = await Promise.all([
        mockApi.admin.getFreeSideItemsAdmin().catch(() => []),
        mockApi.admin.getSystemSettings().catch(() => []),
      ]);
      setItems(sideItems);
      const valSetting = settings.find((s) => s.key === 'free_side_credits_validity_days');
      setValidityDays(valSetting?.value || 60);
    } catch { /* empty state */ }
    setLoading(false);
  };

  const saveItem = async () => {
    if (!editItem?.name?.trim()) { toast({ title: msg('FE_ADMIN_FREE_CREDITS_NAME_IS_REQUIRED', 'Name is required'), variant: 'destructive' }); return; }
    setBusy('item');
    try {
      const body = { name: editItem.name.trim(), image_url: editItem.image_url || null, is_active: editItem.is_active !== false };
      if (editItem.id) await mockApi.admin.updateFreeSideItem(editItem.id, body);
      else await mockApi.admin.createFreeSideItem(body);
      toast({ title: editItem.id ? '✅ Side updated' : '✅ Side added', description: msg('FE_ADMIN_FREE_CREDITS_STUDENTS_CAN_PICK_IT_AT_CHECKOUT_WITH_A', 'Students can pick it at checkout with a free side credit.') });
      setEditItem(null);
      await load();
    } catch (e) {
      toast({ title: msg('FE_ADMIN_FREE_CREDITS_FAILED_TO_SAVE', 'Failed to save'), description: e.message, variant: 'destructive' });
    }
    setBusy(null);
  };

  const toggleItem = async (item) => {
    setBusy(item.id);
    try {
      await mockApi.admin.updateFreeSideItem(item.id, { is_active: !(item.is_active !== false) });
      await load();
    } catch (e) {
      toast({ title: msg('FE_ADMIN_FREE_CREDITS_FAILED_TO_UPDATE', 'Failed to update'), description: e.message, variant: 'destructive' });
    }
    setBusy(null);
  };

  const removeItem = async (item) => {
    if (!confirm(`Deactivate "${item.name}"? It stops showing to students; past orders keep it.`)) return;
    setBusy(item.id);
    try {
      await mockApi.admin.deleteFreeSideItem(item.id);
      toast({ title: msg('FE_ADMIN_FREE_CREDITS_SIDE_DEACTIVATED', 'Side deactivated') });
      await load();
    } catch (e) {
      toast({ title: msg('FE_ADMIN_FREE_CREDITS_FAILED_TO_DEACTIVATE', 'Failed to deactivate'), description: e.message, variant: 'destructive' });
    }
    setBusy(null);
  };

  const saveValidity = async () => {
    setSavingValidity(true);
    try {
      await mockApi.admin.updateFreeSideValidityDays({ value: Number(validityDays) });
      toast({ title: msg('FE_ADMIN_FREE_CREDITS_VALIDITY_UPDATED', '✅ Validity updated'), description: `Free side credits now expire after ${validityDays} days.` });
    } catch (e) {
      toast({ title: msg('FE_ADMIN_FREE_CREDITS_FAILED_TO_SAVE', 'Failed to save'), description: e.message, variant: 'destructive' });
    }
    setSavingValidity(false);
  };

  const searchStudents = async () => {
    const q = grantQuery.trim();
    if (!q) { setGrantResults([]); return; }
    setSearching(true);
    try {
      const rows = await mockApi.users.search({ q });
      setGrantResults(rows);
      if (rows.length === 0) toast({ title: msg('FE_ADMIN_FREE_CREDITS_NO_STUDENTS_MATCHED', 'No students matched'), description: msg('FE_ADMIN_FREE_CREDITS_TRY_A_FULL_NAME_NICKNAME_OR_EMAIL', 'Try a full name, nickname or email.') });
    } catch (e) {
      toast({ title: msg('FE_ADMIN_FREE_CREDITS_SEARCH_FAILED', 'Search failed'), description: e.message, variant: 'destructive' });
    }
    setSearching(false);
  };

  const grantCredits = async () => {
    if (!grantUser) { toast({ title: msg('FE_ADMIN_FREE_CREDITS_PICK_A_STUDENT_FIRST', 'Pick a student first'), variant: 'destructive' }); return; }
    const credits = Number(grantCount);
    if (!(credits >= 1 && credits <= 20)) { toast({ title: msg('FE_ADMIN_FREE_CREDITS_CREDITS_MUST_BE_1_20', 'Credits must be 1-20'), variant: 'destructive' }); return; }
    setGranting(true);
    try {
      const res = await mockApi.admin.grantFreeSideCredits({ user_id: grantUser.id, credits, reason: grantReason.trim() || undefined });
      toast({ title: msg('FE_ADMIN_FREE_CREDITS_CREDITS_GRANTED', '✅ Credits granted'), description: `${credits} free side credit${credits > 1 ? 's' : ''} for ${grantUser.full_name}.${res?.expires_at ? ` Expires ${new Date(res.expires_at).toLocaleDateString()}.` : ''}` });
      setGrantUser(null);
      setGrantQuery('');
      setGrantResults([]);
      setGrantCount(1);
      setGrantReason('');
    } catch (e) {
      toast({ title: msg('FE_ADMIN_FREE_CREDITS_GRANT_FAILED', 'Grant failed'), description: e.message, variant: 'destructive' });
    }
    setGranting(false);
  };

  if (loading) return <LoadingSpinner label="Loading free credits..." />;

  const activeItems = items.filter((i) => i.is_active !== false);

  return (
    <div className="space-y-5">
      <div>
        <SectionHeader title="Free Side Credits" action={<Pill tone="flame"><Gift className="w-3 h-3 inline" /> {activeItems.length} sides live</Pill>} />
        <p className="text-xs text-muted-foreground mb-3">Students earn free side credits (monthly leaderboard top 3 get 5 / 3 / 1) and spend one at checkout to take a side for ₦0. The list below is what they choose from.</p>
        {items.length === 0 ? (
          <Card><p className="text-xs text-muted-foreground text-center py-4">No sides configured yet — students cannot redeem a credit until at least one is active.</p></Card>
        ) : (
          <div className="space-y-2">
            {items.map((it) => (
              <Card key={it.id} className="flex items-center gap-3 !p-3">
                {it.image_url ? (
                  <img src={it.image_url} alt={it.name} loading="lazy" decoding="async" className="w-10 h-10 rounded-lg object-cover" />
                ) : (
                  <div className="w-10 h-10 rounded-lg bg-accent/20 flex items-center justify-center"><Gift className="w-4 h-4 text-accent-foreground" /></div>
                )}
                <div className="flex-1 min-w-0">
                  <div className="font-bold text-sm text-foreground truncate">{it.name}</div>
                  <div className="text-[11px] text-muted-foreground">{it.is_active !== false ? 'Available at checkout' : 'Inactive — hidden from students'}{it.campus_id ? ' · campus-scoped' : ' · all campuses'}</div>
                </div>
                {isSuperAdmin && (
                  <>
                    <Toggle checked={it.is_active !== false} onChange={() => toggleItem(it)} disabled={busy === it.id} />
                    <button onClick={() => setEditItem({ id: it.id, name: it.name, image_url: it.image_url || '', is_active: it.is_active !== false })} className="p-2 rounded-lg hover:bg-muted"><Pencil className="w-4 h-4 text-muted-foreground" /></button>
                    <button onClick={() => removeItem(it)} disabled={busy === it.id} className="p-2 rounded-lg hover:bg-red-50 disabled:opacity-50"><Trash2 className="w-4 h-4 text-red-500" /></button>
                  </>
                )}
              </Card>
            ))}
            {!isSuperAdmin && <SuperAdminBadge />}
          </div>
        )}
        {isSuperAdmin && (
          <button onClick={() => setEditItem({ name: '', image_url: '', is_active: true })} className="flex items-center gap-1 mt-3 px-4 py-2 rounded-full bg-gradient-cta text-white text-xs font-bold"><Plus className="w-3.5 h-3.5" /> Add side</button>
        )}
      </div>

      <Card>
        <SectionHeader title="Grant Credits" action={<Pill tone="blue">admin</Pill>} />
        <p className="text-xs text-muted-foreground mb-3">Give a student free side credits directly (1-20 per grant). Students are searched on your campus only.</p>
        {grantUser ? (
          <div className="space-y-3">
            <div className="flex items-center gap-2 rounded-xl bg-accent/15 border border-border p-3">
              <Gift className="w-4 h-4 text-accent-foreground" />
              <div className="flex-1 min-w-0">
                <div className="font-bold text-sm text-foreground truncate">{grantUser.full_name}</div>
                <div className="text-[11px] text-muted-foreground truncate">{grantUser.email || grantUser.nickname || '—'}</div>
              </div>
              <button onClick={() => setGrantUser(null)} className="text-xs font-bold text-muted-foreground hover:text-foreground">Change</button>
            </div>
            <div className="flex items-end gap-3">
              <Field label="Credits (1-20)"><TextInput type="number" min={1} max={20} value={grantCount} onChange={(e) => setGrantCount(e.target.value)} className="w-28" /></Field>
              <div className="flex-1"><Field label="Reason (optional)"><TextInput value={grantReason} onChange={(e) => setGrantReason(e.target.value)} placeholder="e.g. support goodwill" /></Field></div>
              <button onClick={grantCredits} disabled={granting} className="flex items-center gap-1.5 px-4 py-2.5 rounded-full bg-gradient-cta text-white text-xs font-bold disabled:opacity-50">
                <Zap className="w-3.5 h-3.5" /> {granting ? 'Granting...' : 'Grant credits'}
              </button>
            </div>
          </div>
        ) : (
          <div className="space-y-3">
            <div className="flex gap-2">
              <input value={grantQuery} onChange={(e) => setGrantQuery(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && searchStudents()} placeholder="Search by name, nickname or email" className="flex-1 p-2.5 rounded-xl border border-border text-sm" />
              <button onClick={searchStudents} disabled={searching} className="flex items-center gap-1 px-4 py-2 rounded-xl bg-secondary text-foreground text-sm font-bold disabled:opacity-50"><Search className="w-4 h-4" /> {searching ? 'Searching...' : 'Search'}</button>
            </div>
            {grantResults.length > 0 && (
              <div className="space-y-1">
                {grantResults.map((u) => (
                  <button key={u.id} onClick={() => setGrantUser(u)} className="w-full flex items-center gap-2 rounded-xl border border-border p-2.5 text-left hover:bg-muted">
                    <div className="w-8 h-8 rounded-full bg-primary/10 text-primary flex items-center justify-center font-bold text-xs">{(u.full_name || 'S').charAt(0)}</div>
                    <div className="flex-1 min-w-0">
                      <div className="font-bold text-sm text-foreground truncate">{u.full_name}</div>
                      <div className="text-[11px] text-muted-foreground truncate">{u.email || u.nickname || '—'}</div>
                    </div>
                    <span className="text-[11px] font-bold text-primary">Select</span>
                  </button>
                ))}
              </div>
            )}
          </div>
        )}
      </Card>

      <Card>
        <SectionHeader title="Credit Validity Period" action={<Pill tone="amber"><Clock className="w-3 h-3 inline" /> days</Pill>} />
        <p className="text-xs text-muted-foreground mb-3">How long free side credits remain valid before they expire. Default is 60 days. Used by manual grants and by the monthly leaderboard awards.</p>
        {isSuperAdmin ? (
          <div className="flex items-end gap-3">
            <Field label="Validity (days)">
              <TextInput type="number" value={validityDays} onChange={(e) => setValidityDays(e.target.value)} className="w-32" />
            </Field>
            <button onClick={saveValidity} disabled={savingValidity} className="flex items-center gap-1.5 px-4 py-2.5 rounded-full bg-gradient-cta text-white text-xs font-bold disabled:opacity-50">
              <Save className="w-3.5 h-3.5" /> {savingValidity ? 'Saving...' : 'Save Validity'}
            </button>
          </div>
        ) : (
          // Stored in system settings — super-admin-only write.
          <div className="flex items-center gap-2">
            <span className="font-bold text-sm text-foreground">{validityDays} days</span>
            <SuperAdminBadge />
          </div>
        )}
      </Card>

      <Modal open={!!editItem} onClose={() => setEditItem(null)} title={editItem?.id ? 'Edit free side' : 'Add free side'}>
        {editItem && (
          <div className="space-y-3">
            <Field label="Name"><TextInput value={editItem.name} onChange={(e) => setEditItem({ ...editItem, name: e.target.value })} placeholder="e.g. Coleslaw" /></Field>
            <Field label="Image (optional)"><ImageUploader value={editItem.image_url} onChange={(url) => setEditItem({ ...editItem, image_url: url })} folder="free_side_items" /></Field>
            {editItem.id && (
              <div className="flex items-center justify-between rounded-xl border border-border p-3">
                <span className="text-sm text-foreground">Available to students</span>
                <Toggle checked={editItem.is_active !== false} onChange={(next) => setEditItem({ ...editItem, is_active: next })} />
              </div>
            )}
            <div className="flex justify-end gap-2">
              <button onClick={() => setEditItem(null)} className="px-4 py-2 rounded-full bg-secondary text-foreground text-xs font-bold">Cancel</button>
              <button onClick={saveItem} disabled={busy === 'item'} className="flex items-center gap-1.5 px-4 py-2 rounded-full bg-gradient-cta text-white text-xs font-bold disabled:opacity-50">
                <Save className="w-3.5 h-3.5" /> {busy === 'item' ? 'Saving...' : 'Save side'}
              </button>
            </div>
          </div>
        )}
      </Modal>
    </div>
  );
}
