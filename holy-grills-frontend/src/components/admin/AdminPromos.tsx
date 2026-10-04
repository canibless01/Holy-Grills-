import { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import { Plus, Pencil, BarChart3, Power, Tag, AlertCircle, Infinity as InfinityIcon } from 'lucide-react';
import { liveApi } from '@/lib/liveApi';
import { formatNaira, timeAgo } from '@/lib/hgUtils';
import { toast } from '@/components/ui/use-toast';
import { Card, Skeleton, EmptyState, Modal, Field, TextInput, Pill, BreakdownTiles, body } from './ui/AdminKit';
import { msg } from '@/lib/messages';

const num = (v) => (v == null || isNaN(Number(v)) ? 0 : Number(v));

// Promo Codes — Domain 16. GET/POST /admin/promo-codes · PATCH /:id ·
// GET /:id/uses. Cards render the real promo_codes columns (used_count,
// min_order_amount, starts_at/ends_at, max_uses[_per_user]); usage rows show
// the real promo_code_uses columns (user_id, order_id, discount_amount,
// created_at). Server validation errors ("discount_value must not exceed 100
// for a percentage discount", "is_active must be a boolean") surface as toasts.
export default function AdminPromos() {
  const [promos, setPromos] = useState(null);
  const [showCreate, setShowCreate] = useState(false);
  const [editing, setEditing] = useState(null);
  const [usesFor, setUsesFor] = useState(null);
  const [busy, setBusy] = useState(null);

  const load = async () => {
    try {
      setPromos(await liveApi.admin.getPromoCodes());
    } catch (e) {
      toast({ title: msg('FE_ADMIN_PROMOS_COULDN_T_LOAD_PROMO_CODES', "Couldn't load promo codes"), description: e.message, variant: 'destructive' });
      setPromos([]);
    }
  };

  useEffect(() => { load(); }, []);

  // PATCH is_active directly — no extra list fetch to discover the current state.
  const toggle = async (p) => {
    setBusy(p.id);
    try {
      await liveApi.admin.updatePromoCode(p.id, { is_active: !p.is_active });
      toast({ title: p.is_active ? 'Promo deactivated' : 'Promo activated', description: p.code });
      await load();
    } catch (e) {
      toast({ title: msg('FE_ADMIN_PROMOS_TOGGLE_FAILED', 'Toggle failed'), description: e.message, variant: 'destructive' });
    }
    setBusy(null);
  };

  if (promos == null) {
    return (
      <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-3">
        {Array.from({ length: 6 }).map((_, i) => <Skeleton key={i} className="h-44" />)}
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div className="flex items-center gap-2 text-sm font-bold text-foreground">
          <Tag className="w-4 h-4 text-primary" /> {promos.length} code{promos.length === 1 ? '' : 's'}
        </div>
        <button onClick={() => setShowCreate(true)} className="flex items-center gap-1.5 px-4 py-2.5 rounded-full bg-gradient-cta text-white text-sm font-bold shadow-glow active:scale-95 transition">
          <Plus className="w-4 h-4" /> Create Promo Code
        </button>
      </div>

      {promos.length === 0 ? (
        <Card>
          <EmptyState
            icon={Tag}
            title="No promo codes yet"
            body="Create your first code to start running discounts and campaigns."
            action={
              <button onClick={() => setShowCreate(true)} className="flex items-center gap-1.5 px-4 py-2 rounded-full bg-primary text-white text-xs font-bold active:scale-95 transition">
                <Plus className="w-3.5 h-3.5" /> Create the first code
              </button>
            }
          />
        </Card>
      ) : (
        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-3">
          {promos.map((p, i) => {
            const used = num(p.used_count);
            const max = p.max_uses == null ? null : num(p.max_uses);
            const pctUsed = max ? Math.min(100, (used / max) * 100) : null;
            const ended = p.ends_at && new Date(p.ends_at) < new Date();
            const active = p.is_active && !ended;
            return (
              <motion.div key={p.id} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: Math.min(i * 0.03, 0.2), duration: 0.25 }}>
                <Card className="p-4 space-y-3 h-full">
                  <div className="flex items-center justify-between gap-2">
                    <span className="font-mono font-extrabold text-sm text-foreground bg-secondary px-2 py-1 rounded-lg truncate">{p.code || '—'}</span>
                    {active
                      ? <Pill tone="green"><span className="w-1.5 h-1.5 rounded-full bg-success" /> ACTIVE</Pill>
                      : ended
                        ? <Pill tone="amber">ENDED</Pill>
                        : <Pill tone="red">INACTIVE</Pill>}
                  </div>

                  <div className="font-heading font-extrabold text-lg text-primary">
                    {p.discount_type === 'percentage' ? `${num(p.discount_value)}% off` : `${formatNaira(p.discount_value)} off`}
                    {p.scope && p.scope !== 'cart' && <Pill tone="outline" className="ml-2">{p.scope}</Pill>}
                  </div>

                  {p.description && <div className="text-[11px] text-muted-foreground line-clamp-2">{p.description}</div>}

                  <div className="text-[11px] text-muted-foreground space-y-0.5 font-semibold">
                    <div>Min order: <span className="text-foreground font-bold">{formatNaira(p.min_order_amount)}</span></div>
                    {p.max_uses_per_user != null && <div>Max per user: <span className="text-foreground font-bold">{num(p.max_uses_per_user)}</span></div>}
                    <div>
                      {p.starts_at && <span>from {new Date(p.starts_at).toLocaleDateString()} </span>}
                      {p.ends_at && <span>· ends {new Date(p.ends_at).toLocaleDateString()}</span>}
                      {!p.starts_at && !p.ends_at && <span>No time window</span>}
                    </div>
                  </div>

                  <div>
                    <div className="flex items-center justify-between text-[11px] font-bold mb-1">
                      <span className="text-muted-foreground">Used</span>
                      <span className="text-foreground">{used}{max != null ? ` / ${max}` : ''}</span>
                    </div>
                    {max != null ? (
                      <div className="w-full h-1.5 rounded-full bg-secondary overflow-hidden">
                        <div className={`h-full rounded-full ${pctUsed >= 100 ? 'bg-destructive' : 'bg-gradient-cta'}`} style={{ width: `${pctUsed}%` }} />
                      </div>
                    ) : (
                      <div className="flex items-center gap-1 text-[10px] font-extrabold text-muted-foreground">
                        <InfinityIcon className="w-3 h-3" /> unlimited uses
                      </div>
                    )}
                  </div>

                  <div className="flex gap-1.5 pt-1">
                    <button onClick={() => setEditing(p)} className="flex items-center justify-center gap-1 flex-1 px-2 py-2 rounded-xl bg-secondary text-secondary-foreground text-xs font-bold hover:bg-primary/10 hover:text-primary active:scale-95 transition">
                      <Pencil className="w-3 h-3" /> Edit
                    </button>
                    <button onClick={() => setUsesFor(p)} className="flex items-center justify-center gap-1 flex-1 px-2 py-2 rounded-xl bg-primary/10 text-primary text-xs font-bold hover:bg-primary/20 active:scale-95 transition">
                      <BarChart3 className="w-3 h-3" /> Uses
                    </button>
                    <button
                      onClick={() => toggle(p)}
                      disabled={busy === p.id}
                      title={p.is_active ? 'Deactivate' : 'Activate'}
                      className={`px-3 py-2 rounded-xl text-xs font-bold flex items-center justify-center active:scale-95 transition disabled:opacity-50 ${p.is_active ? 'bg-destructive/10 text-destructive hover:bg-destructive/20' : 'bg-success/10 text-success hover:bg-success/20'}`}
                    >
                      {busy === p.id
                        ? <span className="w-3.5 h-3.5 border-2 border-current border-t-transparent rounded-full animate-spin" />
                        : <Power className="w-3.5 h-3.5" />}
                    </button>
                  </div>
                </Card>
              </motion.div>
            );
          })}
        </div>
      )}

      {showCreate && <PromoModal onClose={() => setShowCreate(false)} onSaved={load} />}
      {editing && <PromoModal promo={editing} onClose={() => setEditing(null)} onSaved={load} />}
      {usesFor && <UsesModal promo={usesFor} onClose={() => setUsesFor(null)} />}
    </div>
  );
}

function PromoModal({
  promo,
  onClose,
  onSaved,
}: {
  // TODO(ts): admin promo rows are untyped on the backend; the modal reads the
  // row defensively field-by-field, so a loose record is the honest shape here.
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  promo?: Record<string, any> | null;
  onClose?: () => void;
  onSaved?: () => void | Promise<void>;
}) {
  const [form, setForm] = useState(promo ? {
    code: promo.code || '',
    description: promo.description || '',
    discount_type: promo.discount_type || 'percentage',
    discount_value: promo.discount_value ?? '',
    min_order_amount: promo.min_order_amount ?? 0,
    max_uses: promo.max_uses ?? '',
    max_uses_per_user: promo.max_uses_per_user ?? '',
    starts_at: promo.starts_at ? String(promo.starts_at).slice(0, 10) : '',
    ends_at: promo.ends_at ? String(promo.ends_at).slice(0, 10) : '',
    scope: promo.scope || 'cart',
    applicable_item_ids: Array.isArray(promo.applicable_item_ids) ? promo.applicable_item_ids.join(', ') : (promo.applicable_item_ids || ''),
  } : {
    code: '', description: '', discount_type: 'percentage', discount_value: 10,
    min_order_amount: 0, max_uses: '', max_uses_per_user: '', starts_at: '', ends_at: '',
    scope: 'cart', applicable_item_ids: '',
  });
  const [submitting, setSubmitting] = useState(false);

  const submit = async () => {
    const dv = Number(form.discount_value);
    if (!form.code.trim()) { toast({ title: msg('FE_ADMIN_PROMOS_CODE_REQUIRED', 'Code required'), variant: 'destructive' }); return; }
    if (isNaN(dv) || dv <= 0) { toast({ title: msg('FE_ADMIN_PROMOS_INVALID_DISCOUNT', 'Invalid discount'), description: msg('FE_ADMIN_PROMOS_DISCOUNT_VALUE_MUST_BE_GREATER_THAN_0', 'Discount value must be greater than 0.'), variant: 'destructive' }); return; }
    // NOTE: the >100 percentage cap and the min-order sign are enforced by the
    // backend (admin.py update_promo / create_promo) and surface verbatim via
    // e.message below — no duplicated client wording to drift.
    if (Number(form.min_order_amount) < 0) { toast({ title: msg('FE_ADMIN_PROMOS_INVALID_MIN_ORDER', 'Invalid min order'), description: msg('FE_ADMIN_PROMOS_MINIMUM_ORDER_AMOUNT_CANNOT_BE_NEGATIVE', 'Minimum order amount cannot be negative.'), variant: 'destructive' }); return; }
    setSubmitting(true);
    try {
      // scope & applicable IDs — the backend already accepts this full contract
      // (scope, applicable_item_ids, applicable_category_ids). Only send the
      // ID arrays when the scope actually targets them, so 'cart' stays clean.
      const splitIds = (v) => (v ? String(v).split(/[\s,]+/).map((s) => s.trim()).filter(Boolean) : null);
      const payload = {
        code: form.code.trim().toUpperCase(),
        description: form.description.trim() || null,
        discount_type: form.discount_type,
        discount_value: dv,
        min_order_amount: Number(form.min_order_amount) || 0,
        max_uses: form.max_uses === '' ? null : Number(form.max_uses),
        max_uses_per_user: form.max_uses_per_user === '' ? null : Number(form.max_uses_per_user),
        starts_at: form.starts_at ? new Date(form.starts_at).toISOString() : null,
        ends_at: form.ends_at ? new Date(form.ends_at).toISOString() : null,
        scope: form.scope,
        ...(form.scope === 'item' ? { applicable_item_ids: splitIds(form.applicable_item_ids) || [] } : {}),
      };
      if (promo) { await liveApi.admin.updatePromoCode(promo.id, payload); toast({ title: msg('FE_ADMIN_PROMOS_PROMO_UPDATED', 'Promo updated'), description: payload.code }); }
      else { await liveApi.admin.createPromoCode(payload); toast({ title: msg('FE_ADMIN_PROMOS_PROMO_CREATED', 'Promo created'), description: payload.code }); }
      onClose(); onSaved();
    } catch (e) {
      // Backend rejects >100 percentage discounts and non-boolean is_active —
      // the message lands here verbatim.
      toast({ title: msg('FE_ADMIN_PROMOS_FAILED_TO_SAVE', 'Failed to save'), description: e.message, variant: 'destructive' });
    }
    setSubmitting(false);
  };

  return (
    <Modal open onClose={onClose} title={promo ? `Edit — ${promo.code}` : 'Create Promo Code'}>
      <div className="space-y-3">
        <Field label="Code"><TextInput value={form.code} onChange={(e) => setForm({ ...form, code: e.target.value.toUpperCase() })} placeholder="SAVE10" /></Field>
        <Field label="Description (optional)"><TextInput value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} placeholder="Launch week discount" /></Field>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Type">
            <select value={form.discount_type} onChange={(e) => setForm({ ...form, discount_type: e.target.value })} className="w-full mt-1 px-3 py-2.5 rounded-xl border border-border bg-card text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-primary/40">
              <option value="percentage">Percentage %</option>
              <option value="flat">Flat ₦</option>
            </select>
          </Field>
          <Field label="Value" hint={form.discount_type === 'percentage' ? 'Max 100' : 'Naira amount'}>
            <TextInput type="number" value={form.discount_value} onChange={(e) => setForm({ ...form, discount_value: e.target.value })} />
          </Field>
        </div>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Min Order ₦"><TextInput type="number" value={form.min_order_amount} onChange={(e) => setForm({ ...form, min_order_amount: e.target.value })} /></Field>
          <Field label="Max Uses (blank = ∞)"><TextInput type="number" value={form.max_uses} onChange={(e) => setForm({ ...form, max_uses: e.target.value })} /></Field>
        </div>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Max Uses / User (blank = ∞)"><TextInput type="number" value={form.max_uses_per_user} onChange={(e) => setForm({ ...form, max_uses_per_user: e.target.value })} /></Field>
          <Field label="Starts At"><TextInput type="date" value={form.starts_at} onChange={(e) => setForm({ ...form, starts_at: e.target.value })} /></Field>
        </div>
        <Field label="Ends At"><TextInput type="date" value={form.ends_at} onChange={(e) => setForm({ ...form, ends_at: e.target.value })} /></Field>
        <Field label="Scope" hint="cart = whole order · items = specific menu items · categories = whole categories">
          <select value={form.scope} onChange={(e) => setForm({ ...form, scope: e.target.value })} className="w-full mt-1 px-3 py-2.5 rounded-xl border border-border bg-card text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-primary/40">
            <option value="cart">Cart — whole order</option>
            <option value="item">Specific items</option>
          </select>
        </Field>
        {form.scope === 'item' && (
          <Field label="Applicable item IDs" hint="Comma-separated menu item IDs the code applies to">
            <TextInput value={form.applicable_item_ids} onChange={(e) => setForm({ ...form, applicable_item_ids: e.target.value })} placeholder="uuid1, uuid2, uuid3" />
          </Field>
        )}
        <button onClick={submit} disabled={submitting || !form.code.trim()} className="w-full py-3 rounded-full bg-gradient-cta text-white font-bold active:scale-95 transition disabled:opacity-50">
          {submitting ? 'Saving…' : (promo ? 'Save Changes' : 'Create Promo')}
        </button>
      </div>
    </Modal>
  );
}

// GET /admin/promo-codes/:id/uses — redemption stats + usage history.
// Only the documented promo_code_uses columns are rendered; the total is
// summed from the actual discount_amount values, never estimated.
function UsesModal({ promo, onClose }) {
  const [uses, setUses] = useState(null);

  useEffect(() => {
    (async () => {
      try {
        const raw = body(await liveApi.admin.getPromoCodeUses(promo.id));
        const list = Array.isArray(raw) ? raw : (raw.uses || raw.usage || raw.usage_history || raw.history || raw.redemptions || []);
        const stats = Array.isArray(raw) ? {} : raw;
        setUses({ list, stats });
      } catch (e) {
        toast({ title: msg('FE_ADMIN_PROMOS_COULDN_T_LOAD_USAGE', "Couldn't load usage"), description: e.message, variant: 'destructive' });
        setUses({ list: [], stats: {} });
      }
    })();
  }, [promo.id]);

  const totalDiscount = uses ? uses.list.reduce((s, u) => s + num(u.discount_amount), 0) : 0;

  return (
    <Modal open onClose={onClose} title={`Usage — ${promo.code}`} wide>
      {uses == null ? (
        <div className="space-y-2.5">{Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-14" />)}</div>
      ) : (
        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-2.5">
            <div className="rounded-xl bg-primary/10 border border-primary/20 px-3 py-2.5">
              <div className="text-[10px] font-extrabold uppercase tracking-wide text-muted-foreground">Total Uses</div>
              <div className="font-heading font-extrabold text-lg text-foreground">{uses.stats.total_uses ?? promo.used_count ?? uses.list.length}</div>
            </div>
            <div className="rounded-xl bg-success/15 border border-success/25 px-3 py-2.5">
              <div className="text-[10px] font-extrabold uppercase tracking-wide text-muted-foreground">Total Discount Given</div>
              <div className="font-heading font-extrabold text-lg text-success">{formatNaira(uses.stats.total_discount_given ?? totalDiscount)}</div>
            </div>
          </div>

          {/* Any extra stat fields the endpoint returns (per-user counts etc.) */}
          <BreakdownTiles data={uses.stats} emptyTitle="" formatValue={(v) => (isNaN(Number(v)) ? String(v) : Number(v).toLocaleString())} />

          {uses.list.length === 0 ? (
            <EmptyState icon={AlertCircle} title="No redemptions yet" body="Each redemption appears here with the user, order and discount applied." />
          ) : (
            <div className="space-y-2">
              {uses.list.map((u, i) => (
                <div key={u.id || i} className="rounded-xl bg-secondary/50 border border-border p-3 flex items-center justify-between gap-2">
                  <div className="min-w-0">
                    <div className="text-xs font-bold text-foreground truncate">
                      {u.user_name || (u.user_id ? `User ${String(u.user_id).slice(0, 8)}…` : 'Unknown user')}
                    </div>
                    <div className="text-[11px] text-muted-foreground truncate">
                      {u.order_id ? `Order ${String(u.order_id).slice(0, 8)}… · ` : ''}{u.created_at ? timeAgo(u.created_at) : ''}
                    </div>
                  </div>
                  <span className="text-sm font-extrabold text-destructive shrink-0">−{formatNaira(u.discount_amount)}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </Modal>
  );
}