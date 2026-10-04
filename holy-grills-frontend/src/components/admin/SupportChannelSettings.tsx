import { useState } from 'react';
import { MessageCircle, Globe2, EyeOff, Plus, ShieldCheck, AlertTriangle } from 'lucide-react';
import { liveApi } from '@/lib/liveApi';
import { useCampus } from '@/lib/campusContext';
import { toast } from '@/components/ui/use-toast';
import { Card, Pill, TextInput, Toggle } from './ui/AdminKit';
import { normalizeWhatsAppNumber } from '@/components/WhatsAppFloatingButton';

/**
 * SUPPORT & WHATSAPP — where these three settings actually come from.
 * ============================================================================
 * The floating "Chat with us" button is rendered for every visitor, so it
 * cannot read /admin/settings (students are not admins). Its only source is
 * the PUBLIC config:
 *
 *   system_settings row (is_public = TRUE)
 *     → GET /api/storefront/config/public
 *     → featureConfig.loadSystemSettings()
 *     → WhatsAppFloatingButton → https://wa.me/<number>
 *
 * which is why a value that is visible on this page can still be ignored:
 *   • is_public = FALSE  → the row never leaves the server, and the button
 *                          quietly falls back to the built-in default. Keys
 *                          created from "New Setting" used to default to
 *                          private, so the number was saved, listed here, and
 *                          never used.
 *   • a per-campus row   → it wins over the global row for visitors of that
 *                          campus only. Seeing "several" WhatsApp rows is
 *                          normal; the scope badge says which is which.
 *
 * This panel makes all three facts visible and editable in one place.
 */

const CHANNEL_KEYS = [
  {
    key: 'whatsapp_support_number',
    label: 'WhatsApp number',
    defaultValue: '2348000000000',
    readBy: 'Floating “Chat with us” button (all pages, every visitor)',
    placeholder: '2348012345678',
    hint: 'International format, digits only: 234… (a leading 0 is converted to 234 automatically).',
  },
  {
    key: 'whatsapp_support_enabled',
    label: 'Show the support button',
    defaultValue: 'true',
    readBy: 'Floating “Chat with us” button — hides it when false',
    placeholder: 'true',
    hint: 'Boolean: true shows the button, false hides it.',
  },
  {
    key: 'whatsapp_support_message',
    label: 'Welcome / default message',
    defaultValue: 'Hello, I need help with my order',
    readBy: 'Prefilled text in the WhatsApp chat (replaced by the order number when the user has an active order)',
    placeholder: 'Hello, I need help with my order',
    hint: 'Plain text. This key is read by the web app only — confirm it is public below.',
  },
];

const parseTyped = (raw, fallback) => {
  const v = String(raw ?? '').trim();
  if (v === '') return fallback;
  if (v === 'true') return true;
  if (v === 'false') return false;
  if (!isNaN(Number(v))) return Number(v);
  return v;
};

export default function SupportChannelSettings({ settings = [], onChanged }) {
  const { campuses, adminCampusId } = useCampus();
  const [busy, setBusy] = useState(null);
  const [drafts, setDrafts] = useState({});

  const campusName = (id) => campuses.find((c) => c.id === id)?.name || 'a campus';

  // Rows for one key, global first. A campus row overrides the global row for
  // visitors of that campus (backend: campus row → global row → env var).
  const rowsFor = (key) =>
    (Array.isArray(settings) ? settings : [])
      .filter((s) => s && s.key === key)
      .sort((a, b) => Number(Boolean(a.campus_id)) - Number(Boolean(b.campus_id)));

  const writePatch = async (key, patch, row) => {
    setBusy(key + (row?.campus_id || 'global'));
    try {
      await liveApi.admin.updateSystemSetting(key, { ...patch, ...(row?.campus_id ? { campus_id: row.campus_id } : {}) });
      toast({ title: 'Setting updated', description: key });
      await onChanged?.();
    } catch (e) {
      toast({ title: 'Failed to save', description: e.message, variant: 'destructive' });
    }
    setBusy(null);
  };

  const createMissing = async (spec) => {
    setBusy(`create-${spec.key}`);
    try {
      await liveApi.admin.createSystemSetting({
        key: spec.key,
        value: parseTyped(spec.defaultValue, spec.defaultValue),
        description: spec.readBy,
        // Students are not admins: the floating button can only read this key
        // through the public config, so it is created public on purpose.
        is_public: true,
      });
      toast({ title: 'Setting created', description: `${spec.key} (public)` });
      await onChanged?.();
    } catch (e) {
      toast({ title: 'Failed to create', description: e.message, variant: 'destructive' });
    }
    setBusy(null);
  };

  const saveDraft = async (spec, row) => {
    const raw = drafts[`${spec.key}:${row?.campus_id || 'global'}`];
    if (raw === undefined || String(raw).trim() === '') return;
    const value = spec.key === 'whatsapp_support_number' ? normalizeWhatsAppNumber(raw) : parseTyped(raw, raw);
    await writePatch(spec.key, { value }, row);
    setDrafts((d) => ({ ...d, [`${spec.key}:${row?.campus_id || 'global'}`]: undefined }));
  };

  return (
    <Card className="p-4">
      <div className="flex items-start gap-2 mb-1">
        <div className="w-7 h-7 rounded-lg bg-green-500/15 flex items-center justify-center shrink-0">
          <MessageCircle className="w-3.5 h-3.5 text-green-600" />
        </div>
        <div className="min-w-0">
          <h3 className="font-heading font-extrabold text-sm text-foreground">Support &amp; WhatsApp</h3>
          <p className="text-[11px] text-muted-foreground">
            Read by the floating chat button through <span className="font-mono">GET /storefront/config/public</span>, which
            serves <b>only rows marked public</b>. A private row is saved here but never reaches the button — it falls back
            to the built-in default.
          </p>
        </div>
      </div>

      <div className="space-y-3 mt-3">
        {CHANNEL_KEYS.map((spec) => {
          const rows = rowsFor(spec.key);
          return (
            <div key={spec.key} className="rounded-xl border border-border p-3">
              <div className="flex items-center justify-between gap-2 mb-1.5">
                <span className="font-mono font-bold text-xs text-foreground min-w-0 break-all">{spec.key}</span>
                {rows.length === 0 ? (
                  <button
                    onClick={() => createMissing(spec)}
                    disabled={busy === `create-${spec.key}`}
                    className="shrink-0 flex items-center gap-1 px-2.5 py-1.5 rounded-lg bg-primary text-white text-[11px] font-bold active:scale-95 transition disabled:opacity-50"
                  >
                    <Plus className="w-3 h-3" /> {busy === `create-${spec.key}` ? 'Creating…' : 'Create (public)'}
                  </button>
                ) : (
                  <Pill tone="outline">{rows.length} row{rows.length === 1 ? '' : 's'}</Pill>
                )}
              </div>
              <p className="text-[11px] text-muted-foreground mb-2">{spec.readBy}</p>

              {rows.length === 0 && (
                <div className="flex items-start gap-1.5 text-[11px] text-amber-700">
                  <AlertTriangle className="w-3.5 h-3.5 shrink-0 mt-0.5" />
                  <span>No row with this key — the web app is using its built-in default ({String(spec.defaultValue)}).</span>
                </div>
              )}

              {rows.map((row) => {
                const idKey = `${spec.key}:${row.campus_id || 'global'}`;
                const isPublic = row.is_public !== false;
                const isBool = typeof row.value === 'boolean';
                const draftVal = drafts[idKey] ?? (isBool ? String(row.value) : String(row.value ?? ''));
                const busyKey = spec.key + (row.campus_id || 'global');
                return (
                  <div key={idKey} className="rounded-lg bg-secondary/50 border border-border p-2.5 mb-2 last:mb-0">
                    <div className="flex items-center gap-1.5 flex-wrap mb-1.5">
                      <Pill tone={row.campus_id ? 'blue' : 'cocoa'}>
                        {row.campus_id ? <Globe2 className="w-3 h-3" /> : null}
                        {row.campus_id ? campusName(row.campus_id) : 'All campuses (global)'}
                      </Pill>
                      {row.campus_id && adminCampusId === row.campus_id && <Pill tone="green">viewing now</Pill>}
                      <button
                        onClick={() => writePatch(spec.key, { is_public: !isPublic }, row)}
                        disabled={busy === busyKey}
                        title={isPublic ? 'Served to students — click to make private' : 'Not served to students — click to make public'}
                        className="ml-auto shrink-0"
                      >
                        <Pill tone={isPublic ? 'green' : 'red'}>
                          {isPublic ? <ShieldCheck className="w-3 h-3" /> : <EyeOff className="w-3 h-3" />}
                          {isPublic ? 'Public' : 'Private'}
                        </Pill>
                      </button>
                    </div>

                    {isBool ? (
                      <div className="flex items-center justify-between gap-2">
                        <span className="text-xs font-bold text-foreground">{row.value ? 'Enabled' : 'Disabled'}</span>
                        <Toggle
                          checked={!!row.value}
                          onChange={(v) => writePatch(spec.key, { value: v }, row)}
                          disabled={busy === busyKey}
                        />
                      </div>
                    ) : (
                      <div className="flex gap-1.5 items-center">
                        <TextInput
                          value={draftVal}
                          onChange={(e) => setDrafts((d) => ({ ...d, [idKey]: e.target.value }))}
                          placeholder={spec.placeholder}
                          className="min-w-0 flex-1"
                        />
                        <button
                          onClick={() => saveDraft(spec, row)}
                          disabled={busy === busyKey || String(draftVal) === String(row.value ?? '')}
                          className="shrink-0 px-3 py-2 rounded-xl bg-primary text-white text-xs font-bold active:scale-95 transition disabled:opacity-50"
                        >
                          Save
                        </button>
                      </div>
                    )}
                    {spec.key === 'whatsapp_support_number' && (
                      <p className="text-[10px] text-muted-foreground mt-1 break-words">
                        Opens <span className="font-mono">https://wa.me/{normalizeWhatsAppNumber(row.value) || '—'}</span>
                      </p>
                    )}
                    <p className="text-[10px] text-muted-foreground mt-1">{spec.hint}</p>
                  </div>
                );
              })}
            </div>
          );
        })}
      </div>
    </Card>
  );
}
