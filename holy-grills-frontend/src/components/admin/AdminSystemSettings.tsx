import { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import { Save, Plus, SlidersHorizontal, AlertCircle, MessageCircle } from 'lucide-react';
import { liveApi } from '@/lib/liveApi';
import { toast } from '@/components/ui/use-toast';
import { Card, Skeleton, EmptyState, Modal, Field, TextInput, Toggle, Pill } from './ui/AdminKit';
import EmailDeliverySettings from './EmailDeliverySettings';
import { useCampus } from '@/lib/campusContext';
import { useIsSuperAdmin, SuperAdminBadge } from './SuperAdminGate';
import { msg } from '@/lib/messages';

// Documented settings from the backend reference (system_settings table) —
// used only to enrich rows with default + purpose when the backend row has no
// description, and to hint server-side constraints.
// `_pct` reads the same in every key but does not mean the same thing: two of
// these are FRACTIONS (0–1) and the rest are real percentages (0–100). The
// ranges below are the ones `hg_validate_system_setting` enforces in the
// database — a value outside them is refused when you hit Save, and the refusal
// message is what the toast shows. Label them, or someone types 50 into
// `flash_discount_pct` meaning 50% and gets a rejection they cannot explain.
const UNITS: Record<string, string> = {
  flash_discount_pct: 'fraction 0–1 · 0.5 = 50% off',
  hp_unlock_rate_pct: 'fraction 0–1 · 0.3 = 30% unlocked now',
  squad_delivery_discount_pct: 'percent 0–100 · 100 = fee waived fully',
  squad_order_discount_pct: 'percent 0–100',
  squad_hp_bonus_pct: 'percent 0–100',
  order_lock_default_discount_pct: 'percent 0–100',
  order_lock_max_discount_pct: 'percent 0–100',
};

const KNOWN_SETTINGS = {
  hp_multiplier: { default: 1, purpose: 'Active loyalty points earn multiplier', hint: 'Must be 0.5, 1.0, or 2.0 — any other value is rejected. Setting it above 1.0 immediately notifies all active users.' },
  flash_discount_pct: { default: 0.5, purpose: 'Discount applied to flash redemptions', hint: 'FRACTION, not a percent: 0.5 = half price, 1 = free. Anything above 1 is refused by the database.' },
  hp_unlock_rate_pct: { default: 0.3, purpose: 'Share of earned HP unlocked immediately', hint: 'FRACTION, not a percent: 0.3 = 30% unlocks now, the rest stays pending. Anything above 1 is refused by the database.' },
  squad_delivery_discount_pct: { default: 100, purpose: 'Share of the delivery fee waived on squad orders', hint: 'Percent 0–100: 100 waives the whole delivery fee.' },
  squad_order_discount_pct: { default: 10, purpose: 'Discount on the squad-order subtotal', hint: 'Percent 0–100: 10 = 10% off the subtotal.' },
  squad_hp_bonus_pct: { default: 10, purpose: 'Extra HP awarded on a squad order', hint: 'Percent 0–100.' },
  order_lock_default_discount_pct: { default: 10, purpose: 'Default goodwill discount on an order lock', hint: 'Percent 0–100 here; the order-lock route itself honours only 1–50 and falls back to the default outside that.' },
  order_lock_max_discount_pct: { default: 50, purpose: 'Highest discount an order lock may offer', hint: 'Percent 0–100. No backend reader today — the order-lock cap is the route default (1–50).' },
  daily_checkin_hp: { default: 0, purpose: 'Daily check-in attendance — no HP is paid per day; the weekly completion reward is what pays HP', hint: 'Daily check-in itself awards 0 HP' },
  free_side_options: { default: 'Coleslaw, Extra Sauce, Soft Drink', purpose: 'Side credit choices', hint: 'Comma-separated list' },
  first_order_gift_enabled: { default: true, purpose: 'Welcome gift toggle' },
  monthly_pending_cap: { default: 1000, purpose: 'Monthly cap on pending HP unlock' },
  graduation_min_level: { default: 400, purpose: 'Minimum academic level for graduation eligibility' },
  whatsapp_support_number: { default: '2348000000000', purpose: 'Support contact number' },
  whatsapp_support_enabled: { default: true, purpose: 'Toggle support button in app' },
  whatsapp_support_message: { default: 'Hello, I need help with my order', purpose: 'Prefilled text in the support chat' },
};

// Parse an edit-string back into the jsonb value shape: arrays for known
// list keys, booleans, numbers, or the raw string.
const parseValue = (key, raw) => {
  if (KNOWN_SETTINGS[key]?.default != null && typeof KNOWN_SETTINGS[key].default !== 'string' && !Array.isArray(KNOWN_SETTINGS[key].default)) {
    if (typeof KNOWN_SETTINGS[key].default === 'boolean') return raw === 'true';
    const n = Number(raw);
    if (!isNaN(n)) return n;
  }
  if (raw.includes(',')) return raw.split(',').map((s) => s.trim()).filter(Boolean);
  if (raw === 'true') return true;
  if (raw === 'false') return false;
  if (raw !== '' && !isNaN(Number(raw))) return Number(raw);
  return raw;
};

const displayValue = (v) => Array.isArray(v) ? v.join(', ') : typeof v === 'object' ? JSON.stringify(v) : String(v);

// One key can exist once globally AND once per campus, and GET /admin/settings
// returns every row — so `key` alone does not identify a row. Using it as the
// React key duplicated keys, and `editKey === s.key` opened the editor on every
// campus copy at once.
const rowId = (s) => `${s.key}:${s.campus_id ?? 'global'}`;

// Write permission mirrors app/routes/admin_gifts.py
// require_settings_write_permission(): a global row (campus_id NULL) is
// super-admin-only; a campus row can also be written by that campus's own
// admin. PATCH must carry the row's campus_id or a campus admin is refused
// with 403 — and without it the backend updates the GLOBAL row instead.
const canEditRow = (s, isSuperAdmin) => Boolean(s.campus_id) || isSuperAdmin;

// What a signed-out visitor actually receives, computed with the same rules as
// GET /api/storefront/config/public: only is_public rows, and with no campus
// selected only the global (campus_id NULL) rows — campus row beats global row
// when there is a campus. A key that resolves to nothing here is exactly the
// key whose value the app silently replaces with its built-in default, which is
// why the floating support button can open 2348000000000 while the table shows
// a perfectly good number.
const resolvePublicValue = (rows, key, campusId) => {
  const candidates = (rows || []).filter(
    (r) => r.key === key && r.is_public !== false && (r.value !== null && r.value !== undefined),
  );
  const scoped = campusId
    ? candidates.filter((r) => r.campus_id === campusId || r.campus_id == null)
    : candidates.filter((r) => r.campus_id == null);
  if (!scoped.length) return { value: null, row: null, reason: 'not-public-or-wrong-campus' };
  const campusRow = scoped.find((r) => r.campus_id === campusId);
  const winner = campusRow || scoped.find((r) => r.campus_id == null) || scoped[0];
  return { value: winner.value, row: winner, reason: campusRow ? 'campus' : 'global' };
};



// System Settings — Domain 17. GET /admin/settings · POST /admin/settings
// (create key) · PATCH /admin/settings/:key. Server-side constraint errors
// (e.g. "hp_multiplier must be 0.5, 1.0, or 2.0") surface as toasts.
export default function AdminSystemSettings() {
  const [settings, setSettings] = useState(null);
  const [editKey, setEditKey] = useState(null);
  const [editValue, setEditValue] = useState('');
  const [busy, setBusy] = useState(null);
  const [createOpen, setCreateOpen] = useState(false);
  const [draft, setDraft] = useState({ key: '', value: '', description: '' });
  const [creating, setCreating] = useState(false);
  // Campus names for the scope badge: the same key can exist once globally and
  // once per campus, and the list shows every row, so "which one is live?" was
  // unanswerable from here.
  const { campuses, adminCampusId } = useCampus();
  const isSuperAdmin = useIsSuperAdmin();

  const load = async () => {
    try {
      setSettings(await liveApi.admin.getSystemSettings());
    } catch (e) {
      toast({ title: msg('FE_ADMIN_SYSTEM_SETTINGS_COULDN_T_LOAD_SETTINGS', "Couldn't load settings"), description: e.message, variant: 'destructive' });
      setSettings([]);
    }
  };

  useEffect(() => { load(); }, []);

  const save = async (s, rawValue = null) => {
    const key = s.key;
    const value = parseValue(key, rawValue != null ? String(rawValue) : editValue);
    const id = rowId(s);
    setBusy(id);
    try {
      // The row's campus_id is what tells the backend which row to write and
      // whether this admin may write it at all.
      await liveApi.admin.updateSystemSetting(key, { value, ...(s.campus_id ? { campus_id: s.campus_id } : {}) });
      toast({ title: msg('FE_ADMIN_SYSTEM_SETTINGS_SETTING_UPDATED', 'Setting updated'), description: msg('FE_ADMIN_SYSTEM_SETTINGS_KEY_SAVED', '{key} saved.', { key: key }) });
      setEditKey(null);
      await load();
    } catch (e) {
      toast({ title: msg('FE_ADMIN_SYSTEM_SETTINGS_FAILED_TO_SAVE', 'Failed to save'), description: e.message, variant: 'destructive' });
    }
    setBusy(null);
  };

  const toggleBool = async (s, current) => {
    const key = s.key;
    setBusy(rowId(s));
    try {
      await liveApi.admin.updateSystemSetting(key, { value: !current, ...(s.campus_id ? { campus_id: s.campus_id } : {}) });
      toast({
        title: current
          ? msg('FE_ADMIN_SYSTEM_SETTINGS_SETTING_DISABLED', '{key} disabled', { key })
          : msg('FE_ADMIN_SYSTEM_SETTINGS_SETTING_ENABLED', '{key} enabled', { key }),
      });
      await load();
    } catch (e) {
      toast({ title: msg('FE_ADMIN_SYSTEM_SETTINGS_FAILED_TO_UPDATE', 'Failed to update'), description: e.message, variant: 'destructive' });
    }
    setBusy(null);
  };

  // POST /admin/settings — create a new settings key.
  const createSetting = async () => {
    const key = draft.key.trim();
    if (!/^[a-z][a-z0-9_]*$/.test(key)) {
      toast({ title: msg('FE_ADMIN_SYSTEM_SETTINGS_INVALID_KEY', 'Invalid key'), description: msg('FE_ADMIN_SYSTEM_SETTINGS_USE_LOWERCASE_LETTERS_NUMBERS_AND', 'Use lowercase letters, numbers and underscores.'), variant: 'destructive' });
      return;
    }
    setCreating(true);
    try {
      await liveApi.admin.createSystemSetting({
        key,
        value: parseValue(key, draft.value.trim()),
        description: draft.description.trim() || null,
        // A private row is invisible to GET /storefront/config/public, which is
        // the only settings source a signed-out visitor has — so a new key
        // created private would show here and never reach the app it is meant
        // to configure. Default to public; the badge on each row flips it.
        is_public: true,
      });
      toast({ title: msg('FE_ADMIN_SYSTEM_SETTINGS_SETTING_CREATED', 'Setting created'), description: key });
      setCreateOpen(false);
      setDraft({ key: '', value: '', description: '' });
      await load();
    } catch (e) {
      toast({ title: msg('FE_ADMIN_SYSTEM_SETTINGS_FAILED_TO_CREATE_SETTING', 'Failed to create setting'), description: e.message, variant: 'destructive' });
    }
    setCreating(false);
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div className="flex items-center gap-2 text-sm font-bold text-foreground">
          <SlidersHorizontal className="w-4 h-4 text-primary" /> {settings ? `${settings.length} setting${settings.length === 1 ? '' : 's'}` : 'Loading…'}
        </div>
        <button onClick={() => setCreateOpen(true)} className="flex items-center gap-1.5 px-4 py-2.5 rounded-full bg-gradient-cta text-white text-sm font-bold shadow-glow active:scale-95 transition">
          <Plus className="w-4 h-4" /> New Setting
        </button>
      </div>


      {/* Support button — the setting people notice first when it is wrong.
          Shows what a visitor will actually receive, not just what the table
          holds, because a private or wrong-campus row silently falls back to the
          built-in default and the button opens WhatsApp's generic invite page. */}
      {settings != null && (() => {
        const viewerCampus = adminCampusId || null;
        const num = resolvePublicValue(settings, 'whatsapp_support_number', viewerCampus);
        const enabled = resolvePublicValue(settings, 'whatsapp_support_enabled', viewerCampus);
        const digits = String(num.value ?? '').replace(/\D/g, '');
        return (
          <Card className={`p-4 ${digits ? '' : 'border-amber-400/60 bg-amber-50/60'}`}>
            <div className="flex items-start gap-2">
              <MessageCircle className={`w-4 h-4 shrink-0 mt-0.5 ${digits ? 'text-primary' : 'text-amber-600'}`} />
              <div className="min-w-0 w-full">
                <p className="text-sm font-bold text-foreground">Floating support button</p>
                {digits ? (
                  <p className="text-[11px] text-muted-foreground mt-1 break-words">
                    Opens <a href={`https://wa.me/${digits}`} target="_blank" rel="noopener noreferrer"
                      className="font-mono font-bold text-primary hover:underline">wa.me/{digits}</a>
                    {' '}· from the <strong>{num.reason === 'campus' ? 'campus' : 'global'}</strong> row
                    {enabled.value === false ? ' · currently hidden (whatsapp_support_enabled is false)' : ''}
                  </p>
                ) : (
                  <p className="text-[11px] text-amber-800 mt-1 break-words">
                    No public <span className="font-mono">whatsapp_support_number</span> reaches this campus, so the
                    app falls back to the built-in default <strong>2348000000000</strong> — which is why the button
                    opens WhatsApp's generic invite page. A row only reaches visitors when it is{' '}
                    <strong>Public</strong> and either global or scoped to this campus.
                  </p>
                )}
              </div>
            </div>
          </Card>
        );
      })()}

      {settings != null && <EmailDeliverySettings settings={settings} onSaved={load} />}

      {settings == null ? (
        <div className="space-y-2.5">{Array.from({ length: 5 }).map((_, i) => <Skeleton key={i} className="h-20" />)}</div>
      ) : settings.length === 0 ? (
        <Card>
          <EmptyState
            icon={AlertCircle}
            title="No system settings yet"
            body="Create the first settings key — defaults like hp_multiplier are consumed by the backend the moment they exist."
            action={
              <button onClick={() => setCreateOpen(true)} className="flex items-center gap-1.5 px-4 py-2 rounded-full bg-primary text-white text-xs font-bold active:scale-95 transition">
                <Plus className="w-3.5 h-3.5" /> Create a setting
              </button>
            }
          />
        </Card>
      ) : (
        <div className="space-y-2.5">
          {settings.map((s, i) => {
            const isBool = typeof s.value === 'boolean';
            const known = KNOWN_SETTINGS[s.key];
            const desc = s.description || known?.purpose;
            const id = rowId(s);
            const editable = canEditRow(s, isSuperAdmin);
            return (
              <motion.div key={id} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: Math.min(i * 0.03, 0.2) }}>
                <Card className="p-4">
                  <div className="flex items-center justify-between gap-2 mb-1 min-w-0">
                    <span className="font-mono font-bold text-xs text-foreground truncate min-w-0 flex-1">{s.key}</span>
                    <span className="flex items-center gap-1 shrink-0">
                      <Pill tone={s.campus_id ? 'blue' : 'cocoa'}>{s.campus_id ? (campuses.find((c) => c.id === s.campus_id)?.name || 'campus') : 'global'}</Pill>
                      {s.campus_id && adminCampusId === s.campus_id && <Pill tone="green">viewing</Pill>}
                      {s.is_public === false && <Pill tone="red">private</Pill>}
                    </span>
                    {!editable ? (
                      // Global rows are super-admin-only by backend policy; say
                      // so instead of offering a Save that answers 403.
                      <SuperAdminBadge />
                    ) : isBool ? (
                      <Toggle checked={s.value} onChange={() => toggleBool(s, s.value)} disabled={busy === id} />
                    ) : editKey === id ? (
                      <div className="flex gap-1.5 shrink-0">
                        <button onClick={() => save(s)} disabled={busy === id} className="px-3 py-1.5 rounded-lg bg-primary text-white text-xs font-bold active:scale-95 transition disabled:opacity-50 flex items-center gap-1">
                          <Save className="w-3 h-3" /> Save
                        </button>
                        <button onClick={() => setEditKey(null)} className="px-3 py-1.5 rounded-lg bg-secondary text-muted-foreground text-xs font-bold active:scale-95 transition">Cancel</button>
                      </div>
                    ) : (
                      <button
                        onClick={() => { setEditKey(id); setEditValue(displayValue(s.value)); }}
                        className="px-3 py-1.5 rounded-lg bg-secondary text-secondary-foreground text-xs font-bold active:scale-95 transition hover:bg-primary/10 hover:text-primary shrink-0"
                      >
                        Edit
                      </button>
                    )}
                  </div>
                  {desc && <div className="text-[11px] text-muted-foreground mb-2 break-words">{desc}{known && s.value !== known.default && ` · documented default: ${displayValue(known.default)}`}</div>}
                  {isBool ? (
                    <div className="font-bold text-sm text-foreground">{s.value ? 'Enabled' : 'Disabled'}</div>
                  ) : editKey === id ? (
                    <div>
                      {known?.hint && <p className="text-[11px] font-bold text-accent-foreground mb-1">⚠ {known.hint}</p>}
                      {s.key === 'hp_multiplier' ? (
                        // Backend hard-validates this setting: exactly 0.5, 1.0 or 2.0.
                        // Fixed choices only — never a free number.
                        <div className="flex gap-1.5 flex-wrap">
                          {[0.5, 1.0, 2.0].map((m) => (
                            <button
                              key={m}
                              onClick={() => save(s, String(m))}
                              disabled={busy === id}
                              className={`px-3.5 py-1.5 rounded-lg text-xs font-bold active:scale-95 transition disabled:opacity-50 ${Number(s.value) === m ? 'bg-primary text-white' : 'bg-secondary text-secondary-foreground hover:bg-primary/10 hover:text-primary'}`}
                            >
                              {m}×
                            </button>
                          ))}
                          <button onClick={() => setEditKey(null)} className="px-3 py-1.5 rounded-lg bg-secondary text-muted-foreground text-xs font-bold active:scale-95 transition">Cancel</button>
                        </div>
                      ) : (
                        <>
                          <input
                            value={editValue}
                            onChange={(e) => setEditValue(e.target.value)}
                            autoFocus
                            className={`w-full p-2.5 rounded-xl border text-sm font-bold text-foreground focus:outline-none focus:ring-2 focus:ring-primary/40 ${known?.hint ? 'border-accent/60 bg-accent/10' : 'border-primary/40 bg-card'}`}
                          />
                          {UNITS[s.key] && (
                            <p className="text-[11px] text-muted-foreground mt-1">Value format — {UNITS[s.key]}</p>
                          )}
                        </>
                      )}
                    </div>
                  ) : (
                    <div className="flex items-baseline gap-2 flex-wrap min-w-0">
                      <span className="font-bold text-sm text-foreground break-words min-w-0">{displayValue(s.value)}</span>
                      {UNITS[s.key] && (
                        <span className="text-[10px] font-bold tracking-wide px-2 py-0.5 rounded-full bg-secondary text-muted-foreground">
                          {UNITS[s.key]}
                        </span>
                      )}
                    </div>
                  )}
                </Card>
              </motion.div>
            );
          })}
        </div>
      )}

      <Modal open={createOpen} onClose={() => setCreateOpen(false)} title="New Setting">
        <div className="space-y-3">
          <Field label="Key (lowercase, numbers, underscores)">
            <TextInput value={draft.key} onChange={(e) => setDraft({ ...draft, key: e.target.value.toLowerCase().replace(/[^a-z0-9_]/g, '') })} placeholder="new_setting_key" />
          </Field>
          <Field label="Value" hint="Booleans: true/false · numbers parse automatically · commas create a list">
            <TextInput value={draft.value} onChange={(e) => setDraft({ ...draft, value: e.target.value })} placeholder="true" />
          </Field>
          <Field label="Description (optional)">
            <TextInput value={draft.description} onChange={(e) => setDraft({ ...draft, description: e.target.value })} placeholder="What this setting controls" />
          </Field>
          <button onClick={createSetting} disabled={creating || !draft.key.trim()} className="w-full py-3 rounded-full bg-gradient-cta text-white font-bold text-sm active:scale-95 transition disabled:opacity-50">
            {creating ? 'Creating…' : 'Create Setting'}
          </button>
        </div>
      </Modal>
    </div>
  );
}