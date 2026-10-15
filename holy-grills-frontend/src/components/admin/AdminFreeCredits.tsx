import { confirmAction } from '@/lib/confirmAction';
import { localStore } from '@/lib/storage';
import { useHolyGrill } from '@/lib/HolyGrillContext';
import { useState, useEffect, useRef } from 'react';
import { Save, Plus, Pencil, Trash2, Gift, Clock, Search, Zap } from 'lucide-react';
import { liveApi as mockApi } from '@/lib/liveApi';
import LoadingSpinner from '@/components/LoadingSpinner';
import { toast } from '@/components/ui/use-toast';
import { Card, Field, TextInput, Pill, SectionHeader, Modal, Toggle } from './AdminShared';
import ImageUploader from './ImageUploader';
import { useIsSuperAdmin, SuperAdminBadge } from './SuperAdminGate';
import { msg, useMessages } from '@/lib/messages';
import { displayName, displayInitial } from '@/lib/displayName';

// Free side credits (free_sides.py).
//   • The sides students can pick live in the free_side_items TABLE — the public
//     GET /free-sides reads it directly — so they are curated here with
//     /free-sides/admin/items (POST/PATCH/DELETE). The old system_settings
//     `free_side_options` blob this page used to edit is dead config: nothing
//     reads it, so writing it changed nothing for students.
//   • Credits are granted with POST /free-sides/admin/credits, picking the student
//     through GET /auth/users/search (campus-scoped, rate-limited).
export default function AdminFreeCredits() {
  useMessages();
  const { user } = useHolyGrill();
  const grantingRef = useRef(false);
  const [loadError, setLoadError] = useState('');
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
    setLoadError('');
    try {
      const config = await mockApi.admin.getFreeSideConfig();
      setItems(config.items || []);
      setValidityDays(config.validity_days);
    } catch (e) { setLoadError(e.message || msg('FE_ADMIN_FREE_SIDE_LOAD_ERROR', 'Free-side configuration could not be loaded.')); }
    setLoading(false);
  };

  const saveItem = async () => {
    if (!editItem?.name?.trim()) { toast({ title: msg('FE_ADMIN_FREE_CREDITS_NAME_IS_REQUIRED', 'Name is required'), variant: 'destructive' }); return; }
    setBusy('item');
    try {
      const body = { name: editItem.name.trim(), image_url: editItem.image_url || null, is_active: editItem.is_active !== false, intent_key: editItem.intent_key, expected_updated_at: editItem.updated_at };
      if (editItem.id) await mockApi.admin.updateFreeSideItem(editItem.id, body);
      else await mockApi.admin.createFreeSideItem(body);
      toast({ title: editItem.id ? msg('FE_ADMIN_FREE_SIDE_UPDATED', 'Side updated') : msg('FE_ADMIN_FREE_SIDE_ADDED', 'Side added'), description: msg('FE_ADMIN_FREE_CREDITS_STUDENTS_CAN_PICK_IT_AT_CHECKOUT_WITH_A', 'Students can pick it at checkout with a free side credit.') });
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
      await mockApi.admin.updateFreeSideItem(item.id, { is_active: !(item.is_active !== false), expected_updated_at: item.updated_at });
      await load();
    } catch (e) {
      toast({ title: msg('FE_ADMIN_FREE_CREDITS_FAILED_TO_UPDATE', 'Failed to update'), description: e.message, variant: 'destructive' });
    }
    setBusy(null);
  };

  const removeItem = async (item) => {
    if (!(await confirmAction({ title: msg('FE_FREE_SIDE_DEACTIVATE_CONFIRM', 'Deactivate {name}? Past orders keep their saved side.', { name: item.name }), destructive: true }))) return;
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
    if (!Number.isInteger(Number(validityDays)) || Number(validityDays)<1 || Number(validityDays)>365) { toast({ title: msg('FE_FREE_SIDE_VALIDITY_INVALID', 'Choose a whole number from 1 to 365 days.'), variant: 'destructive' }); return; }
    setSavingValidity(true);
    try {
      await mockApi.admin.updateFreeSideValidityDays({ value: Number(validityDays) });
      toast({ title: msg('FE_ADMIN_FREE_CREDITS_VALIDITY_UPDATED', '✅ Validity updated'), description: msg('FE_ADMIN_FREE_CREDITS_FREE_SIDE_CREDITS_NOW_EXPIRE_AFTER', 'Free side credits now expire after {validity_days} days.', { validity_days: validityDays }) });
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
    if (!(Number.isInteger(credits) && credits >= 1 && credits <= 20)) { toast({ title: msg('FE_ADMIN_FREE_CREDITS_CREDITS_MUST_BE_1_20', 'Credits must be 1-20'), variant: 'destructive' }); return; }
    if (grantingRef.current) return;
    grantingRef.current = true;
    setGranting(true);
    try {
      const payload = { user_id: grantUser.id, credits, reason: grantReason.trim() || undefined };
      const key = `hg_free_side_grant:${user?.id}`;
      const fingerprint = JSON.stringify(payload);
      let pending;
      try { pending = JSON.parse(localStore.getItem(key) || 'null'); } catch { pending = null; }
      if (!pending || pending.fingerprint !== fingerprint) { pending = { fingerprint, intent_key: crypto.randomUUID(), validity_days: Number(validityDays) }; localStore.setItem(key, JSON.stringify(pending)); }
      const res = await mockApi.admin.grantFreeSideCredits({ ...payload, intent_key: pending.intent_key, validity_days: pending.validity_days });
      localStore.removeItem(key);
      const grantedName = displayName(grantUser);
      toast({
        title: msg('FE_ADMIN_FREE_CREDITS_CREDITS_GRANTED', '✅ Credits granted'),
        description: [
          credits === 1
            ? msg('FE_ADMIN_FREE_CREDITS_ONE_CREDIT_FOR_NAME', '1 free side credit for {name}.', { name: grantedName })
            : msg('FE_ADMIN_FREE_CREDITS_CREDITS_FOR_NAME', '{count} free side credits for {name}.', { count: credits, name: grantedName }),
          res?.expires_at ? msg('FE_ADMIN_FREE_CREDITS_CREDIT_EXPIRES_ON', 'Expires {date}.', { date: new Date(res.expires_at).toLocaleDateString() }) : '',
        ].filter(Boolean).join(' '),
      });
      setGrantUser(null);
      setGrantQuery('');
      setGrantResults([]);
      setGrantCount(1);
      setGrantReason('');
    } catch (e) {
      toast({ title: msg('FE_ADMIN_FREE_CREDITS_GRANT_FAILED', 'Grant failed'), description: e.message, variant: 'destructive' });
    }
    grantingRef.current = false;
    setGranting(false);
  };

  if (loading) return <LoadingSpinner label={msg('FE_ADMIN_FREE_SIDE_LOADING', 'Loading free credits...')} />;

  if (loadError) return <Card><p role="alert" className="text-sm text-destructive">{loadError}</p><button onClick={load}>{msg('FE_FREE_SIDES_RETRY', 'Retry')}</button></Card>;

  const activeItems = items.filter((i) => i.is_active !== false);

  return (
    <div className="space-y-5">
      <div>
        <SectionHeader title={msg('FE_ADMIN_FREE_SIDE_TITLE', 'Free Side Credits')} action={<Pill tone="flame"><Gift className="w-3 h-3 inline" /> {msg('FE_ADMIN_FREE_SIDE_LIVE_COUNT', '{count} sides live', { count: activeItems.length })}</Pill>} />
        <p className="text-xs text-muted-foreground mb-3">{msg('FE_ADMIN_FREE_SIDE_HELP', 'Students spend an earned free-side credit at checkout to add one of the active sides below for ₦0.')}</p>
        {items.length === 0 ? (
          <Card><p className="text-xs text-muted-foreground text-center py-4">{msg('FE_ADMIN_FREE_SIDE_EMPTY', 'No sides configured yet — students cannot redeem a credit until at least one is active.')}</p></Card>
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
                  <div className="text-[11px] text-muted-foreground">{it.is_active !== false ? msg('FE_ADMIN_FREE_SIDE_ACTIVE', 'Available at checkout') : msg('FE_ADMIN_FREE_SIDE_INACTIVE', 'Inactive — hidden from students')}{it.campus_id ? msg('FE_ADMIN_FREE_SIDE_CAMPUS_SCOPE', ' · campus-scoped') : msg('FE_ADMIN_FREE_SIDE_GLOBAL_SCOPE', ' · all campuses')}</div>
                </div>
                {!isSuperAdmin && !it.campus_id && <SuperAdminBadge />}
                {(isSuperAdmin || it.campus_id) && (
                  <>
                    <Toggle checked={it.is_active !== false} onChange={() => toggleItem(it)} disabled={busy === it.id} />
                    <button aria-label={msg('FE_ADMIN_FREE_SIDE_EDIT', 'Edit {name}', { name: it.name })} onClick={() => setEditItem({ id: it.id, updated_at: it.updated_at, name: it.name, image_url: it.image_url || '', is_active: it.is_active !== false })} className="p-2 rounded-lg hover:bg-muted"><Pencil className="w-4 h-4 text-muted-foreground" /></button>
                    <button aria-label={msg('FE_ADMIN_FREE_SIDE_REMOVE', 'Deactivate {name}', { name: it.name })} onClick={() => removeItem(it)} disabled={busy === it.id} className="p-2 rounded-lg hover:tone-error disabled:opacity-50"><Trash2 className="w-4 h-4 text-destructive" /></button>
                  </>
                )}
              </Card>
            ))}

          </div>
        )}
        {(
          <button onClick={() => setEditItem({ intent_key: crypto.randomUUID(), name: '', image_url: '', is_active: true })} className="flex items-center gap-1 mt-3 px-4 py-2 rounded-full bg-gradient-cta text-white text-xs font-bold"><Plus className="w-3.5 h-3.5" /> {msg('FE_ADMIN_FREE_SIDE_ADD', 'Add side')}</button>
        )}
      </div>

      <Card>
        <SectionHeader title={msg('FE_ADMIN_FREE_SIDE_GRANT_TITLE', 'Grant Credits')} action={<Pill tone="blue">admin</Pill>} />
        <p className="text-xs text-muted-foreground mb-3">{msg('FE_ADMIN_FREE_SIDE_GRANT_HELP', 'Give a student free side credits directly (1-20 per grant). Search results follow your current campus scope.')}</p>
        {grantUser ? (
          <div className="space-y-3">
            <div className="flex items-center gap-2 rounded-xl bg-accent/15 border border-border p-3">
              <Gift className="w-4 h-4 text-accent-foreground" />
              <div className="flex-1 min-w-0">
                <div className="font-bold text-sm text-foreground truncate">{displayName(grantUser)}</div>
                <div className="text-[11px] text-muted-foreground truncate">{grantUser.email || grantUser.nickname || '—'}</div>
              </div>
              <button onClick={() => setGrantUser(null)} className="text-xs font-bold text-muted-foreground hover:text-foreground">{msg('FE_ADMIN_FREE_SIDE_CHANGE_USER', 'Change')}</button>
            </div>
            <div className="flex items-end gap-3">
              <Field label={msg('FE_ADMIN_FREE_SIDE_COUNT', 'Credits (1-20)')}><TextInput type="number" min={1} max={20} value={grantCount} onChange={(e) => setGrantCount(e.target.value)} className="w-28" /></Field>
              <div className="flex-1"><Field label={msg('FE_ADMIN_FREE_SIDE_REASON', 'Reason (optional)')}><TextInput value={grantReason} onChange={(e) => setGrantReason(e.target.value)} placeholder={msg('FE_ADMIN_FREE_SIDE_REASON_EXAMPLE', 'e.g. support goodwill')} /></Field></div>
              <button onClick={grantCredits} disabled={granting} className="flex items-center gap-1.5 px-4 py-2.5 rounded-full bg-gradient-cta text-white text-xs font-bold disabled:opacity-50">
                <Zap className="w-3.5 h-3.5" /> {granting ? msg('FE_ADMIN_FREE_SIDE_GRANTING', 'Granting...') : msg('FE_ADMIN_FREE_SIDE_GRANT', 'Grant credits')}
              </button>
            </div>
          </div>
        ) : (
          <div className="space-y-3">
            <div className="flex gap-2">
              <input value={grantQuery} onChange={(e) => setGrantQuery(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && searchStudents()} placeholder={msg('FE_ADMIN_FREE_SIDE_SEARCH_HINT', 'Search by name, nickname or email')} className="flex-1 p-2.5 rounded-xl border border-border text-sm" />
              <button onClick={searchStudents} disabled={searching} className="flex items-center gap-1 px-4 py-2 rounded-xl bg-secondary text-foreground text-sm font-bold disabled:opacity-50"><Search className="w-4 h-4" /> {searching ? msg('FE_ADMIN_FREE_SIDE_SEARCHING', 'Searching...') : msg('FE_ADMIN_FREE_SIDE_SEARCH', 'Search')}</button>
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
                    <span className="text-[11px] font-bold text-primary">{msg('FE_ADMIN_FREE_SIDE_SELECT_USER', 'Select')}</span>
                  </button>
                ))}
              </div>
            )}
          </div>
        )}
      </Card>

      <Card>
        <SectionHeader title={msg('FE_ADMIN_FREE_SIDE_VALIDITY_TITLE', 'Credit Validity Period')} action={<Pill tone="amber"><Clock className="w-3 h-3 inline" /> days</Pill>} />
        <p className="text-xs text-muted-foreground mb-3">{msg('FE_FREE_SIDE_VALIDITY_HELP', 'Controls expiry for new credit grants. Existing credits keep their original expiry.')}</p>
        {isSuperAdmin ? (
          <div className="flex items-end gap-3">
            <Field label={msg('FE_ADMIN_FREE_SIDE_VALIDITY_DAYS', 'Validity (days)')}>
              <TextInput type="number" value={validityDays} onChange={(e) => setValidityDays(e.target.value)} className="w-32" />
            </Field>
            <button onClick={saveValidity} disabled={savingValidity} className="flex items-center gap-1.5 px-4 py-2.5 rounded-full bg-gradient-cta text-white text-xs font-bold disabled:opacity-50">
              <Save className="w-3.5 h-3.5" /> {savingValidity ? msg('FE_ADMIN_FREE_SIDE_SAVING', 'Saving...') : msg('FE_ADMIN_FREE_SIDE_SAVE_VALIDITY', 'Save Validity')}
            </button>
          </div>
        ) : (
          // Stored in system settings — super-admin-only write.
          <div className="flex items-center gap-2">
            <span className="font-bold text-sm text-foreground">{msg('FE_ADMIN_FREE_SIDE_DAYS_COUNT', '{count} days', { count: validityDays })}</span>
            <SuperAdminBadge />
          </div>
        )}
      </Card>

      <Modal open={!!editItem} onClose={() => setEditItem(null)} title={editItem?.id ? msg('FE_ADMIN_FREE_SIDE_EDIT_TITLE', 'Edit free side') : msg('FE_ADMIN_FREE_SIDE_ADD_TITLE', 'Add free side')}>
        {editItem && (
          <div className="space-y-3">
            <Field label={msg('FE_ADMIN_FREE_SIDE_NAME', 'Name')}><TextInput value={editItem.name} onChange={(e) => setEditItem({ ...editItem, name: e.target.value })} placeholder={msg('FE_ADMIN_FREE_SIDE_NAME_EXAMPLE', 'e.g. Coleslaw')} /></Field>
            <Field label={msg('FE_ADMIN_FREE_SIDE_IMAGE', 'Image (optional)')}><ImageUploader value={editItem.image_url} onChange={(url) => setEditItem({ ...editItem, image_url: url })} folder="free_side_items" /></Field>
            {editItem.id && (
              <div className="flex items-center justify-between rounded-xl border border-border p-3">
                <span className="text-sm text-foreground">{msg('FE_ADMIN_FREE_SIDE_AVAILABLE', 'Available to students')}</span>
                <Toggle checked={editItem.is_active !== false} onChange={(next) => setEditItem({ ...editItem, is_active: next })} />
              </div>
            )}
            <div className="flex justify-end gap-2">
              <button onClick={() => setEditItem(null)} className="px-4 py-2 rounded-full bg-secondary text-foreground text-xs font-bold">{msg('FE_ADMIN_FREE_SIDE_CANCEL', 'Cancel')}</button>
              <button onClick={saveItem} disabled={busy === 'item'} className="flex items-center gap-1.5 px-4 py-2 rounded-full bg-gradient-cta text-white text-xs font-bold disabled:opacity-50">
                <Save className="w-3.5 h-3.5" /> {busy === 'item' ? msg('FE_ADMIN_FREE_SIDE_SAVING', 'Saving...') : msg('FE_ADMIN_FREE_SIDE_SAVE', 'Save side')}
              </button>
            </div>
          </div>
        )}
      </Modal>
    </div>
  );
}
