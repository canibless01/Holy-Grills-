import { useState, useEffect } from 'react';
import { Plus, Pencil, Trash2, Check, Zap, Clock, Flame, Ban, EyeOff } from 'lucide-react';
import { liveApi as mockApi } from '@/lib/liveApi';
import { formatNaira } from '@/lib/hgUtils';
import StaffPanelSkeleton from '@/components/skeletons/StaffPanelSkeleton';
import { Modal, Field, TextInput, Pill } from './AdminShared';
import ImageUploader from './ImageUploader';
import AdminScopeBadge, { useAdminWriteScope } from './AdminScopeBadge';
import { toast } from '@/components/ui/use-toast';
import { msg } from '@/lib/messages';

// No flash_* columns here — flash sales live in flash_redemptions, created via
// POST /rewards/admin/flash-sales. The reward editor only owns the reward itself.
const BLANK = {
  name: '',
  reward_type: 'food',
  stock_quantity: 50,
  min_tier_id: null,
  fulfillment_type: 'menu_item',
  image_url: '',
  // Stage 16 — HP Economics inputs. The server computes reward_value, hp_cost
  // and hp_liability from these; the admin never types the HP price.
  food_cost: '',
  packaging_cost: '',
  menu_price: '',
  margin_share_pct: '',
  production_cost: '',
  perceived_value: '',
  ticket_face_value: '',
  max_discount_pct: '',
  available_margin: '',
};

const REWARD_TYPES = [
  { value: 'food', label: 'Food' },
  { value: 'merch', label: 'Merchandise' },
  { value: 'event', label: 'Event' },
];
const ECONOMICS_GROUP = { food: 'food', merch: 'merch' };
const ECONOMICS_FIELDS = {
  food: [
    { key: 'food_cost', label: 'Food cost (₦)' },
    { key: 'packaging_cost', label: 'Packaging cost (₦)' },
    { key: 'menu_price', label: 'Menu price (₦)' },
    { key: 'margin_share_pct', label: 'Margin share (%)' },
  ],
  merch: [
    { key: 'production_cost', label: 'Production cost (₦)' },
    { key: 'packaging_cost', label: 'Packaging cost (₦)' },
    { key: 'perceived_value', label: 'Perceived value (₦)' },
    { key: 'margin_share_pct', label: 'Margin share (%)' },
  ],
  event: [
    { key: 'ticket_face_value', label: 'Ticket face value (₦)' },
    { key: 'max_discount_pct', label: 'Max discount (%)' },
    { key: 'available_margin', label: 'Available margin (₦)' },
  ],
};

const economicsPayload = (item) => {
  const group = ECONOMICS_GROUP[item?.reward_type];
  const body: Record<string, number | string | null> = { reward_type: item.reward_type };
  for (const field of group ? ECONOMICS_FIELDS[group] : []) {
    const value = item[field.key];
    body[field.key] = value === '' || value == null ? null : Number(value);
  }
  return body;
};

// Flash status from the response the backend actually returns. _with_flash_status
// sets is_flash_active + flash_hp_cost / flash_starts_at / flash_ends_at /
// flash_max_qty / flash_slots_remaining when a sale window is open right now.
const flashStatus = (r) => {
  if (!r.is_flash_active) return null;
  const now = Date.now();
  const end = r.flash_ends_at ? new Date(r.flash_ends_at).getTime() : Infinity;
  const slots = r.flash_slots_remaining ?? 0;
  if (now > end || slots <= 0) return 'ended';
  return 'live';
};

// `as const` keeps the tone literals (the Pill tone union rejects a widened
// `string`, which is what the new typing caught here).
const FLASH_BADGE = {
  live: { icon: Flame, label: '🔥 Live', tone: 'flame' },
  ended: { icon: Clock, label: '⏰ Ended', tone: 'cocoa' },
} as const;

export default function AdminRewards() {
  const writeScope = useAdminWriteScope();
  const [tab, setTab] = useState('rewards');
  const [rewards, setRewards] = useState([]);
  const [redemptions, setRed] = useState([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState('');
  const [modal, setModal] = useState(null);
  const [saveError, setSaveError] = useState(null);
  const [saveConflict, setSaveConflict] = useState(false);
  const [pricePreview, setPricePreview] = useState<any>(null);
  const [previewError, setPreviewError] = useState('');
  const [previewBusy, setPreviewBusy] = useState(false);
  const savedReward = modal?.item.id ? rewards.find(reward => reward.id === modal.item.id) : null;
  const pricingChanged = !!modal && (modal.isNew || JSON.stringify(economicsPayload(modal.item)) !== JSON.stringify(economicsPayload(savedReward || {})));
  const priceKey = modal && pricingChanged && ECONOMICS_GROUP[modal.item.reward_type] ? JSON.stringify(economicsPayload(modal.item)) : '';
  useEffect(() => {
    let active = true;
    setPricePreview(null); setPreviewError(''); setPreviewBusy(!!priceKey && priceKey !== '{}');
    if (!priceKey || priceKey === '{}') return;
    const timer = setTimeout(() => {
      mockApi.admin.previewRewardEconomics(JSON.parse(priceKey)).then(result => { if (active) setPricePreview({ ...result, key: priceKey }); })
        .catch(error => { if (active) setPreviewError(error.message); })
        .finally(() => { if (active) setPreviewBusy(false); });
    }, 300);
    return () => { active = false; clearTimeout(timer); };
  }, [priceKey]);
  const [hpTiers, setHpTiers] = useState([]);
  const [flashModal, setFlashModal] = useState(null);
  const [actionModal, setActionModal] = useState(null);

  const load = async () => {
    setLoadError('');
    try {
      const [items, receipts] = await Promise.all([mockApi.admin.getRewards(), mockApi.admin.getRedemptions()]);
      setRewards(items); setRed(receipts);
    } catch (error) { setLoadError(error.message || msg('FE_REWARD_PRICE_LOAD_FAILED', 'Rewards could not be loaded.')); }
    finally { setLoading(false); }
  };
  useEffect(() => {
    load();
    mockApi.hp.getTiers().then((t) => setHpTiers(Array.isArray(t) ? t : [])).catch(() => setHpTiers([]));
  }, []);

  const tierList = hpTiers;

  const save = async () => {
    setSaveError(null); setSaveConflict(false);
    // hp_cost / reward_value / hp_liability are server-computed read-only
    // outputs — never submitted from the form.
    const item = modal.item;
    const body: Record<string, any> = {
      name: item.name, image_url: item.image_url || null,
      reward_type: item.reward_type, min_tier_id: item.min_tier_id || null,
      stock_quantity: item.stock_quantity === '' || item.stock_quantity == null ? null : Number(item.stock_quantity),
      fulfillment_type: item.fulfillment_type || 'menu_item',
      ...economicsPayload(item),
      ...(!modal.isNew && item.updated_at ? { expected_updated_at: item.updated_at } : {}),
    };
    try {
      if (modal.isNew) await mockApi.admin.createReward(body);
      else await mockApi.admin.updateReward(modal.item.id, body);
      setModal(null);
      await load();
      toast({ title: modal.isNew ? 'Reward created' : 'Reward updated' });
    } catch (e) {
      // Inline — the backend owns the message (e.g. economics validation).
      setSaveError(e.message); setSaveConflict(e.status === 409);
    }
  };
  const remove = async (id) => { await mockApi.admin.deleteReward(id); await load(); };

  if (loading) return <StaffPanelSkeleton />;
  if (loadError) return <div role="alert" className="rounded-2xl border border-border p-4 text-sm">{loadError}<button onClick={load} className="ml-3 text-primary underline">{msg('FE_LOOKUP_RETRY', 'Retry')}</button></div>;

  // Stage 16 — active economics group + live summary for the open editor.
  const econGroup = modal ? ECONOMICS_GROUP[modal.item.reward_type] : null;
  const econFields = econGroup ? ECONOMICS_FIELDS[econGroup] : [];
  const econSummary = pricePreview?.key === priceKey && pricePreview?.complete ? pricePreview : null;
  const shownPrice = econSummary?.hp_cost ?? (pricingChanged && !!econGroup ? null : modal?.item.hp_cost ?? null);

  return (
    <div className="space-y-4">
      <div className="flex gap-1 p-1 rounded-full bg-secondary">
        {[{ id: 'rewards', label: 'Rewards' }, { id: 'redemptions', label: 'Redemptions' }].map((t) => (
          <button key={t.id} onClick={() => setTab(t.id)} className={`flex-1 py-2 rounded-full text-xs font-bold ${tab === t.id ? 'bg-card text-primary shadow-sm' : 'text-muted-foreground'}`}>{t.label}</button>
        ))}
      </div>
      {tab === 'rewards' ? (
        <div className="space-y-2">
          <div className="flex justify-end items-center gap-2">
            <AdminScopeBadge />
            <button onClick={() => setModal({ item: { ...BLANK, min_tier_id: tierList[0]?.id || null }, isNew: true })} className="flex items-center gap-1 px-3 py-2 rounded-full bg-primary text-white text-xs font-bold"><Plus className="w-4 h-4" /> Add Reward</button>
          </div>
          {rewards.map((r) => {
            const fs = flashStatus(r);
            const badge = fs ? FLASH_BADGE[fs] : null;
            return (
              <div key={r.id} className="rounded-2xl bg-card border border-border p-3 flex items-center gap-3">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <div className="font-bold text-sm text-foreground">{r.name}</div>
                    {badge && <Pill tone={badge.tone}>{badge.label}</Pill>}
                  </div>
                  <div className="text-xs text-muted-foreground">
                    {r.is_flash_active && r.flash_hp_cost != null ? (
                      <><span className="line-through text-muted-foreground">{r.hp_cost}</span> <span className="text-primary font-bold">{r.flash_hp_cost}</span> HP · </>
                    ) : `${r.hp_cost} HP · `}
                    {REWARD_TYPES.find(t => t.value === r.reward_type)?.label || r.reward_type} · stock {r.stock_quantity} · {tierList.find((t) => t.id === r.min_tier_id)?.name || 'Ember'} tier
                  </div>
                  {r.is_flash_active && (
                    <div className="text-[10px] text-muted-foreground mt-0.5">
                      Flash: {r.flash_slots_remaining ?? 0}/{r.flash_max_qty ?? 0} slots
                      {r.flash_starts_at && ` · ${new Date(r.flash_starts_at).toLocaleString()}`}
                      {r.flash_ends_at && ` → ${new Date(r.flash_ends_at).toLocaleString()}`}
                    </div>
                  )}
                </div>
                <button onClick={() => setFlashModal(r)} title="Open flash sale" className="p-2 rounded-lg hover:bg-primary/10"><Zap className="w-4 h-4 text-primary" /></button>
                <button onClick={() => setModal({ item: { ...r }, isNew: false })} aria-label={msg('FE_REWARD_EDIT_ACTION', 'Edit reward')} className="p-2 rounded-lg hover:bg-muted"><Pencil className="w-4 h-4 text-muted-foreground" /></button>
                <button onClick={() => remove(r.id)} className="p-2 rounded-lg hover:tone-error"><Trash2 className="w-4 h-4 text-destructive" /></button>
              </div>
            );
          })}
        </div>
      ) : (
        <div className="space-y-2">
          {redemptions.map((r) => {
            const statusTone = r.status === 'fulfilled' ? 'green' : r.status === 'rejected' ? 'red' : 'amber';
            const statusLabel = r.status === 'fulfilled' ? 'Fulfilled' : r.status === 'rejected' ? 'Rejected' : 'Pending';
            const user = r.profiles || {};
            return (
              <div key={r.id} className="rounded-2xl bg-card border border-border p-3 flex items-center gap-3">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <div className="font-bold text-sm text-foreground">{r.rewards?.name}</div>
                    {r.is_flash && <Pill tone="flame"><Zap className="w-2.5 h-2.5 inline" /> Flash</Pill>}
                    <Pill tone={statusTone}>{statusLabel}</Pill>
                  </div>
                  <div className="text-xs text-muted-foreground">
                    {user.full_name || user.email || 'Unknown user'} · {r.hp_cost_snapshot} HP
                    {r.fulfillment_type ? ` · ${r.fulfillment_type === 'menu_item' ? 'Menu item' : 'Simple'}` : ''}
                  </div>
                  {r.admin_notes && <div className="text-[11px] text-muted-foreground mt-0.5 italic">“{r.admin_notes}”</div>}
                </div>
                {r.status === 'pending' && (
                  <button onClick={() => setActionModal(r)} className="flex items-center gap-1 px-3 py-1.5 rounded-full bg-primary text-white text-xs font-bold">Review</button>
                )}
              </div>
            );
          })}
        </div>
      )}
      <Modal open={!!modal} onClose={() => { setModal(null); setSaveError(null); setSaveConflict(false); }} title={modal?.isNew ? 'New Reward' : 'Edit Reward'}>
        {modal && (
          <div className="space-y-3">
            {modal.isNew && <AdminScopeBadge />}
            {modal.isNew && writeScope.isGlobal && (
              <div className="flex gap-2 rounded-xl border border-warn/40 bg-warn/10 p-3 text-[11px] font-semibold text-warn">
                <EyeOff className="w-4 h-4 shrink-0 mt-0.5" />
                <span>{msg('FE_ADMIN_REWARD_GLOBAL_VISIBILITY_NOTE', 'Global rewards are saved with no campus (campus_id NULL). The hg_campus_visible database policy hides campus-less rows from student accounts, so only admins will see this reward. To make it visible to students, pick a campus in the header switcher and create it there instead.')}</span>
              </div>
            )}
            <Field label="Name"><TextInput value={modal.item.name} onChange={(e) => setModal({ item: { ...modal.item, name: e.target.value }, isNew: modal.isNew })} /></Field>
            <div className="grid grid-cols-2 gap-3">
              <Field label="Stock"><TextInput type="number" value={modal.item.stock_quantity ?? ''} onChange={(e) => setModal({ item: { ...modal.item, stock_quantity: e.target.value }, isNew: modal.isNew })} /></Field>
              <Field label="HP price" hint="Server-computed from the economics inputs — read-only">
                <div className="mt-1 p-2.5 rounded-xl border border-border bg-muted text-sm font-bold text-foreground">{previewBusy ? msg('FE_REWARD_PRICE_LOADING', 'Calculating…') : shownPrice == null ? msg('FE_REWARD_PRICE_AFTER_INPUTS', 'Enter cost inputs to preview') : `${shownPrice} HP`}</div>
              </Field>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <Field label="Type"><select value={modal.item.reward_type} onChange={(e) => setModal({ item: { ...modal.item, reward_type: e.target.value }, isNew: modal.isNew })} className="w-full mt-1 p-2.5 rounded-xl border border-border text-sm">{REWARD_TYPES.filter(t => t.value !== 'event' || modal.item.reward_type === 'event').map((t) => <option key={t.value} value={t.value}>{t.label}</option>)}</select></Field>
              <Field label="Min Tier"><select value={modal.item.min_tier_id} onChange={(e) => setModal({ item: { ...modal.item, min_tier_id: e.target.value }, isNew: modal.isNew })} className="w-full mt-1 p-2.5 rounded-xl border border-border text-sm">{tierList.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}</select></Field>
            </div>

            <Field label="Fulfillment type">
              <div className="mt-1 flex gap-2">
                {[
                  { value: 'menu_item', label: 'Menu item' },
                  { value: 'simple', label: 'Simple item' },
                ].map((o) => (
                  <button key={o.value} type="button" onClick={() => setModal({ item: { ...modal.item, fulfillment_type: o.value }, isNew: modal.isNew })} className={`flex-1 px-3 py-2.5 rounded-xl border text-xs font-bold transition ${modal.item.fulfillment_type === o.value ? 'border-primary bg-primary/10 text-primary' : 'border-border bg-card text-muted-foreground'}`}>{o.label}</button>
                ))}
              </div>
            </Field>

            {/* Stage 16 — HP Economics: type-aware cost inputs + live read-only summary */}
            {econGroup && (
              <div className="rounded-2xl border border-border p-3 space-y-3 bg-muted/50">
                <div className="flex items-center gap-2"><Flame className="w-4 h-4 text-primary" /><span className="text-sm font-bold text-foreground">HP Economics ({econGroup})</span></div>
                <div className={`grid gap-3 ${econFields.length === 3 ? 'grid-cols-3' : 'grid-cols-2'}`}>
                  {econFields.map((f) => (
                    <Field key={f.key} label={f.label}><TextInput type="number" value={modal.item[f.key] == null || modal.item[f.key] === '' ? '' : f.key === 'margin_share_pct' ? Number(modal.item[f.key]) * 100 : modal.item[f.key]} onChange={(e) => setModal({ item: { ...modal.item, [f.key]: e.target.value === '' ? '' : f.key === 'margin_share_pct' ? Number(e.target.value) / 100 : e.target.value }, isNew: modal.isNew })} /></Field>
                  ))}
                </div>
                {econSummary && <div className="rounded-xl bg-card border border-border p-3">
                  <div className="grid grid-cols-3 gap-2 text-center">
                    <div>
                      <div className="text-[10px] font-bold uppercase tracking-wide text-muted-foreground">Reward value</div>
                      <div className="font-heading font-extrabold text-sm text-foreground">{formatNaira(econSummary.reward_value)}</div>
                    </div>
                    <div>
                      <div className="text-[10px] font-bold uppercase tracking-wide text-muted-foreground">HP price</div>
                      <div className="font-heading font-extrabold text-sm text-primary">{econSummary.hp_cost} HP</div>
                    </div>
                    <div>
                      <div className="text-[10px] font-bold uppercase tracking-wide text-muted-foreground">{msg('FE_REWARD_PRICE_LIABILITY', 'Liability per reward')}</div>
                      <div className="font-heading font-extrabold text-sm text-foreground">{formatNaira(econSummary.hp_liability)}</div>
                    </div>
                  </div>
                  <p className="text-[10px] text-muted-foreground mt-2 text-center">{msg('FE_REWARD_PRICE_NOTE', 'Calculated by the backend. Saving confirms the final price.')}</p>
                </div>}
                {previewError && <p role="alert" className="text-xs text-destructive">{previewError}</p>}

              </div>
            )}

            <Field label="Image"><ImageUploader value={modal.item.image_url} onChange={(url) => setModal({ item: { ...modal.item, image_url: url }, isNew: modal.isNew })} folder="rewards" /></Field>

            {saveConflict && <button type="button" onClick={() => { setModal(null); setSaveConflict(false); setSaveError(null); void load(); }} className="text-primary underline text-sm font-bold">{msg('FE_REWARD_RELOAD', 'Reload rewards')}</button>}
            {saveError && <p className="text-[11px] font-bold text-destructive text-center">⚠ {saveError}</p>}
            <button onClick={save} disabled={previewBusy || !!previewError || (pricingChanged && !!econGroup && !econSummary)} className="w-full py-3 rounded-full bg-gradient-cta text-white font-bold text-sm disabled:opacity-50 disabled:cursor-not-allowed">{modal.isNew ? 'Create Reward' : 'Save Changes'}</button>
          </div>
        )}
      </Modal>

      {flashModal && <FlashSaleModal reward={flashModal} onClose={() => setFlashModal(null)} onSaved={load} />}
      {actionModal && <RedemptionActionModal redemption={actionModal} onClose={() => setActionModal(null)} onSaved={load} />}
    </div>
  );
}

// Flash sale creator — POST /rewards/admin/flash-sales. The discounted HP price
// is server-computed from the reward's economics + discount_pct, so the admin
// only sets the window, slot limit and discount percentage.
function FlashSaleModal({ reward, onClose, onSaved }) {
  const [form, setForm] = useState<{ window_starts_at: string; window_ends_at: string; quantity_limit: number | string; discount_pct: number | string }>({ window_starts_at: '', window_ends_at: '', quantity_limit: 5, discount_pct: 50 });
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);

  const submit = async () => {
    setError(null);
    if (!form.window_ends_at) { setError(msg('FE_ADMIN_REWARDS_END_TIME_IS_REQUIRED', 'End time is required.')); return; }
    const startsAt = form.window_starts_at ? new Date(form.window_starts_at).toISOString() : null;
    const endsAt = new Date(form.window_ends_at).toISOString();
    if (startsAt && new Date(endsAt) <= new Date(startsAt)) { setError(msg('FE_ADMIN_REWARDS_END_TIME_MUST_BE_AFTER_THE_START_TIME', 'End time must be after the start time.')); return; }
    const qty = Number(form.quantity_limit);
    const disc = Number(form.discount_pct);
    if (!qty || qty < 1) { setError(msg('FE_ADMIN_REWARDS_SLOT_LIMIT_MUST_BE_AT_LEAST_1', 'Slot limit must be at least 1.')); return; }
    if (!disc || disc <= 0 || disc >= 100) { setError(msg('FE_ADMIN_REWARDS_DISCOUNT_MUST_BE_BETWEEN_1_AND_99', 'Discount must be between 1 and 99 percent.')); return; }
    setSubmitting(true);
    try {
      await mockApi.admin.createFlashSale({
        reward_id: reward.id,
        window_starts_at: startsAt,
        window_ends_at: endsAt,
        quantity_limit: qty,
        discount_pct: disc / 100,
      });
      toast({ title: msg('FE_ADMIN_REWARDS_FLASH_SALE_CREATED', '🔥 Flash sale created') });
      onSaved(); onClose();
    } catch (e) {
      setError(e.message);
    }
    setSubmitting(false);
  };

  return (
    <Modal open onClose={onClose} title={`Flash Sale · ${reward.name}`}>
      <div className="space-y-3">
        <div className="rounded-xl bg-muted p-3 text-xs text-muted-foreground">A time-boxed discount: the first {form.quantity_limit || 'N'} redeemers pay a lower HP price. The server computes the flash price from the reward's economics and your discount %.</div>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Starts at (optional)" hint="Defaults to now"><input type="datetime-local" value={form.window_starts_at} onChange={(e) => setForm({ ...form, window_starts_at: e.target.value })} className="w-full mt-1 p-2.5 rounded-xl border border-border text-sm" /></Field>
          <Field label="Ends at"><input type="datetime-local" value={form.window_ends_at} onChange={(e) => setForm({ ...form, window_ends_at: e.target.value })} className="w-full mt-1 p-2.5 rounded-xl border border-border text-sm" /></Field>
        </div>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Max slots"><TextInput type="number" value={form.quantity_limit} onChange={(e) => setForm({ ...form, quantity_limit: e.target.value })} /></Field>
          <Field label="Discount (%)" hint="1–99"><TextInput type="number" value={form.discount_pct} onChange={(e) => setForm({ ...form, discount_pct: e.target.value })} /></Field>
        </div>
        {error && <p className="text-[11px] font-bold text-destructive text-center">⚠ {error}</p>}
        <button onClick={submit} disabled={submitting || !form.window_ends_at} className="w-full py-3 rounded-full bg-gradient-cta text-white font-bold disabled:opacity-50">{submitting ? 'Creating...' : 'Create Flash Sale'}</button>
      </div>
    </Modal>
  );
}

// Fulfil or reject a redemption — PATCH /rewards/admin/redemptions/:id.
// Fulfil accepts an optional actual_cost (logged for the economics dashboard);
// reject triggers an HP refund server-side. Both accept admin_notes.
function RedemptionActionModal({ redemption, onClose, onSaved }) {
  const [mode, setMode] = useState('fulfilled');
  const [adminNotes, setAdminNotes] = useState('');
  const [actualCost, setActualCost] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);

  const submit = async () => {
    setError(null);
    setSubmitting(true);
    try {
      const body: { status: string; admin_notes?: string; actual_cost?: number } = { status: mode, admin_notes: adminNotes || undefined };
      if (mode === 'fulfilled' && actualCost !== '') body.actual_cost = Number(actualCost);
      if (mode === 'fulfilled') await mockApi.admin.fulfillRedemption(redemption.id, body);
      else await mockApi.admin.rejectRedemption(redemption.id, body);
      toast({ title: mode === 'fulfilled' ? '✅ Redemption fulfilled' : 'Redemption rejected' });
      onSaved(); onClose();
    } catch (e) {
      setError(e.message);
    }
    setSubmitting(false);
  };

  const user = redemption.profiles || {};

  return (
    <Modal open onClose={onClose} title="Review Redemption">
      <div className="space-y-3">
        <div className="rounded-xl bg-muted p-3 text-xs">
          <div className="font-bold text-foreground">{redemption.rewards?.name}</div>
          <div className="text-muted-foreground">{user.full_name || user.email || 'Unknown user'} · {redemption.hp_cost_snapshot} HP</div>
        </div>
        <div className="flex gap-2">
          <button type="button" onClick={() => setMode('fulfilled')} className={`flex-1 py-2.5 rounded-xl border text-xs font-bold flex items-center justify-center gap-1.5 ${mode === 'fulfilled' ? 'border-success/30 tone-success' : 'border-border text-muted-foreground'}`}><Check className="w-3.5 h-3.5" /> Fulfil</button>
          <button type="button" onClick={() => setMode('rejected')} className={`flex-1 py-2.5 rounded-xl border text-xs font-bold flex items-center justify-center gap-1.5 ${mode === 'rejected' ? 'border-destructive/30 tone-error' : 'border-border text-muted-foreground'}`}><Ban className="w-3.5 h-3.5" /> Reject</button>
        </div>
        {mode === 'fulfilled' && (
          <Field label="Actual cost (₦)" hint="Optional — logs what this reward cost the business. The server derives it from the reward if left blank.">
            <TextInput type="number" value={actualCost} onChange={(e) => setActualCost(e.target.value)} placeholder="Leave blank to auto-derive" />
          </Field>
        )}
        {mode === 'rejected' && (
          <div className="rounded-xl tone-warn border border-warn/40 p-2.5 text-[11px] text-warn">Rejecting refunds the spent HP to the student automatically.</div>
        )}
        <Field label="Admin notes (optional)"><TextInput value={adminNotes} onChange={(e) => setAdminNotes(e.target.value)} placeholder="Reason / instructions" /></Field>
        {error && <p className="text-[11px] font-bold text-destructive text-center">⚠ {error}</p>}
        <button onClick={submit} disabled={submitting} className="w-full py-3 rounded-full bg-gradient-cta text-white font-bold disabled:opacity-50">{submitting ? 'Saving...' : mode === 'fulfilled' ? 'Confirm Fulfilment' : 'Confirm Rejection'}</button>
      </div>
    </Modal>
  );
}