import React, { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import { Save, Plus, SlidersHorizontal, AlertCircle } from 'lucide-react';
import { liveApi } from '@/lib/liveApi';
import { toast } from '@/components/ui/use-toast';
import { Card, Skeleton, EmptyState, Modal, Field, TextInput, Toggle } from './ui/AdminKit';
import EmailDeliverySettings from './EmailDeliverySettings';

// Documented settings from the backend reference (system_settings table) —
// used only to enrich rows with default + purpose when the backend row has no
// description, and to hint server-side constraints.
const KNOWN_SETTINGS = {
  hp_multiplier: { default: 1, purpose: 'Active loyalty points earn multiplier', hint: 'Must be 0.5, 1.0, or 2.0 — any other value is rejected. Setting it above 1.0 immediately notifies all active users.' },
  daily_checkin_hp: { default: 0, purpose: 'Daily check-in attendance — no HP is paid per day; the weekly completion reward is what pays HP', hint: 'Daily check-in itself awards 0 HP' },
  free_side_options: { default: 'Coleslaw, Extra Sauce, Soft Drink', purpose: 'Side credit choices', hint: 'Comma-separated list' },
  first_order_gift_enabled: { default: true, purpose: 'Welcome gift toggle' },
  monthly_pending_cap: { default: 1000, purpose: 'Monthly cap on pending HP unlock' },
  graduation_min_level: { default: 400, purpose: 'Minimum academic level for graduation eligibility' },
  whatsapp_support_number: { default: '2348000000000', purpose: 'Support contact number' },
  whatsapp_support_enabled: { default: true, purpose: 'Toggle support button in app' },
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

  const load = async () => {
    try {
      setSettings(await liveApi.admin.getSystemSettings());
    } catch (e) {
      toast({ title: "Couldn't load settings", description: e.message, variant: 'destructive' });
      setSettings([]);
    }
  };

  useEffect(() => { load(); }, []);

  const save = async (key, rawValue = null) => {
    const value = parseValue(key, rawValue != null ? String(rawValue) : editValue);
    setBusy(key);
    try {
      await liveApi.admin.updateSystemSetting(key, { value });
      toast({ title: 'Setting updated', description: `${key} saved.` });
      setEditKey(null);
      await load();
    } catch (e) {
      toast({ title: 'Failed to save', description: e.message, variant: 'destructive' });
    }
    setBusy(null);
  };

  const toggleBool = async (key, current) => {
    setBusy(key);
    try {
      await liveApi.admin.updateSystemSetting(key, { value: !current });
      toast({ title: `${key} ${!current ? 'enabled' : 'disabled'}` });
      await load();
    } catch (e) {
      toast({ title: 'Failed to update', description: e.message, variant: 'destructive' });
    }
    setBusy(null);
  };

  // POST /admin/settings — create a new settings key.
  const createSetting = async () => {
    const key = draft.key.trim();
    if (!/^[a-z][a-z0-9_]*$/.test(key)) {
      toast({ title: 'Invalid key', description: 'Use lowercase letters, numbers and underscores.', variant: 'destructive' });
      return;
    }
    setCreating(true);
    try {
      await liveApi.admin.createSystemSetting({
        key,
        value: parseValue(key, draft.value.trim()),
        description: draft.description.trim() || null,
      });
      toast({ title: 'Setting created', description: key });
      setCreateOpen(false);
      setDraft({ key: '', value: '', description: '' });
      await load();
    } catch (e) {
      toast({ title: 'Failed to create setting', description: e.message, variant: 'destructive' });
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
            return (
              <motion.div key={s.key} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: Math.min(i * 0.03, 0.2) }}>
                <Card className="p-4">
                  <div className="flex items-center justify-between gap-3 mb-1">
                    <span className="font-mono font-bold text-xs text-foreground truncate">{s.key}</span>
                    {isBool ? (
                      <Toggle checked={s.value} onChange={() => toggleBool(s.key, s.value)} disabled={busy === s.key} />
                    ) : editKey === s.key ? (
                      <div className="flex gap-1.5 shrink-0">
                        <button onClick={() => save(s.key)} disabled={busy === s.key} className="px-3 py-1.5 rounded-lg bg-primary text-white text-xs font-bold active:scale-95 transition disabled:opacity-50 flex items-center gap-1">
                          <Save className="w-3 h-3" /> Save
                        </button>
                        <button onClick={() => setEditKey(null)} className="px-3 py-1.5 rounded-lg bg-secondary text-muted-foreground text-xs font-bold active:scale-95 transition">Cancel</button>
                      </div>
                    ) : (
                      <button
                        onClick={() => { setEditKey(s.key); setEditValue(displayValue(s.value)); }}
                        className="px-3 py-1.5 rounded-lg bg-secondary text-secondary-foreground text-xs font-bold active:scale-95 transition hover:bg-primary/10 hover:text-primary shrink-0"
                      >
                        Edit
                      </button>
                    )}
                  </div>
                  {desc && <div className="text-[11px] text-muted-foreground mb-2">{desc}{known && s.value !== known.default && ` · documented default: ${displayValue(known.default)}`}</div>}
                  {isBool ? (
                    <div className="font-bold text-sm text-foreground">{s.value ? 'Enabled' : 'Disabled'}</div>
                  ) : editKey === s.key ? (
                    <div>
                      {known?.hint && <p className="text-[11px] font-bold text-accent-foreground mb-1">⚠ {known.hint}</p>}
                      {s.key === 'hp_multiplier' ? (
                        // Backend hard-validates this setting: exactly 0.5, 1.0 or 2.0.
                        // Fixed choices only — never a free number.
                        <div className="flex gap-1.5 flex-wrap">
                          {[0.5, 1.0, 2.0].map((m) => (
                            <button
                              key={m}
                              onClick={() => save(s.key, String(m))}
                              disabled={busy === s.key}
                              className={`px-3.5 py-1.5 rounded-lg text-xs font-bold active:scale-95 transition disabled:opacity-50 ${Number(s.value) === m ? 'bg-primary text-white' : 'bg-secondary text-secondary-foreground hover:bg-primary/10 hover:text-primary'}`}
                            >
                              {m}×
                            </button>
                          ))}
                          <button onClick={() => setEditKey(null)} className="px-3 py-1.5 rounded-lg bg-secondary text-muted-foreground text-xs font-bold active:scale-95 transition">Cancel</button>
                        </div>
                      ) : (
                        <input
                          value={editValue}
                          onChange={(e) => setEditValue(e.target.value)}
                          autoFocus
                          className={`w-full p-2.5 rounded-xl border text-sm font-bold text-foreground focus:outline-none focus:ring-2 focus:ring-primary/40 ${known?.hint ? 'border-accent/60 bg-accent/10' : 'border-primary/40 bg-card'}`}
                        />
                      )}
                    </div>
                  ) : (
                    <div className="font-bold text-sm text-foreground break-words">{displayValue(s.value)}</div>
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