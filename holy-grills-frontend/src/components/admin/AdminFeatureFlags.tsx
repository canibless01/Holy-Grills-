import { useState, useEffect, useRef } from 'react';
import { motion } from 'framer-motion';
import { Plus, Info, Clock, AlertCircle } from 'lucide-react';
import { liveApi } from '@/lib/liveApi';
import { toast } from '@/components/ui/use-toast';
import { Card, Skeleton, EmptyState, Modal, Field, TextInput, Pill, Toggle } from './ui/AdminKit';
import { msg, useMessages } from '@/lib/messages';
import { useHolyGrill } from '@/lib/HolyGrillContext';
import { useCampus } from '@/lib/campusContext';
import { loadFeatureFlags } from '@/lib/featureConfig';

// Flag metadata — admin guidance only. On/off values come from the backend's
// feature_flags table (is_active column), never from this map.
const flagMetadata = () => ({
  events: { label: msg('FE_EVENT_FLAG_LABEL', 'Events'), flipWhen: msg('FE_EVENT_FLAG_WHEN', 'When event admission and rewards are ready'), impact: msg('FE_EVENT_FLAG_IMPACT', 'Shows Coming Soon and blocks new event registrations while disabled') },
  hp_multiplier: { label: msg('FE_ADMIN_FLAG_HP_MULTIPLIER_LABEL', 'HP multiplier events'), flipWhen: msg('FE_ADMIN_FLAG_HP_MULTIPLIER_FLIPWHEN', 'When the launch team is ready'), impact: msg('FE_ADMIN_FLAG_HP_MULTIPLIER_IMPACT', 'Enables timed event multipliers; per-item multipliers remain independent') },
  flash_redemptions: { label: msg('FE_ADMIN_FLAG_FLASH_REDEMPTIONS_LABEL', 'Flash reward events'), flipWhen: msg('FE_ADMIN_FLAG_FLASH_REDEMPTIONS_FLIPWHEN', 'When reward fulfilment is ready'), impact: msg('FE_ADMIN_FLAG_FLASH_REDEMPTIONS_IMPACT', 'Enables flash reward availability and flash redemption') },
  leaderboard_prizes: { label: msg('FE_ADMIN_FLAG_LEADERBOARD_PRIZES_LABEL', 'Leaderboard Prizes'), flipWhen: msg('FE_ADMIN_FLAG_LEADERBOARD_PRIZES_FLIPWHEN', 'After first month of data'), impact: msg('FE_ADMIN_FLAG_LEADERBOARD_PRIZES_IMPACT', 'Shows/hides prize indicators on the leaderboard') },
  free_side_credits: { label: msg('FE_ADMIN_FLAG_FREE_SIDE_CREDITS_LABEL', 'Free Side Credits'), flipWhen: msg('FE_ADMIN_FLAG_LEADERBOARD_PRIZES_FLIPWHEN', 'After first month of data'), impact: msg('FE_ADMIN_FLAG_FREE_SIDE_CREDITS_IMPACT', 'Shows/hides free side UI in rewards') },
  exclusive_spin: { label: msg('FE_ADMIN_FLAG_EXCLUSIVE_SPIN_LABEL', 'Exclusive Spin'), flipWhen: msg('FE_ADMIN_FLAG_LEADERBOARD_PRIZES_FLIPWHEN', 'After first month of data'), impact: msg('FE_ADMIN_FLAG_EXCLUSIVE_SPIN_IMPACT', 'Shows/hides exclusive spin wheel for top earners') },
  hall_of_fame: { label: msg('FE_ADMIN_FLAG_HALL_OF_FAME_LABEL', 'Hall of Fame'), flipWhen: msg('FE_ADMIN_FLAG_HALL_OF_FAME_FLIPWHEN', 'After 3 months of data'), impact: msg('FE_ADMIN_FLAG_HALL_OF_FAME_IMPACT', 'Shows/hides the Hall of Fame page') },
  badge_system: { label: msg('FE_ADMIN_FLAG_BADGE_SYSTEM_LABEL', 'Badge System'), flipWhen: msg('FE_ADMIN_FLAG_BADGE_SYSTEM_FLIPWHEN', '200+ active users'), impact: msg('FE_ADMIN_FLAG_BADGE_SYSTEM_IMPACT', 'Shows/hides badges on profiles and challenges') },
  spin_and_win: { label: msg('FE_ADMIN_FLAG_SPIN_AND_WIN_LABEL', 'Spin & Win'), flipWhen: msg('FE_ADMIN_FLAG_BADGE_SYSTEM_FLIPWHEN', '200+ active users'), impact: msg('FE_ADMIN_FLAG_SPIN_AND_WIN_IMPACT', 'Shows/hides the daily spin wheel') },
  marketplace_general: { label: msg('FE_ADMIN_FLAG_MARKETPLACE_GENERAL_LABEL', 'Marketplace'), flipWhen: msg('FE_ADMIN_FLAG_MARKETPLACE_GENERAL_FLIPWHEN', '500+ active users'), impact: msg('FE_ADMIN_FLAG_MARKETPLACE_GENERAL_IMPACT', 'Shows/hides the marketplace') },
  hp_transfer: { label: msg('FE_ADMIN_FLAG_HP_TRANSFER_LABEL', 'HP Transfer'), flipWhen: msg('FE_ADMIN_FLAG_HP_TRANSFER_FLIPWHEN', 'Phase 3'), impact: msg('FE_ADMIN_FLAG_HP_TRANSFER_IMPACT', 'Shows/hides HP transfer between users') },
  squad_orders: { label: msg('FE_ADMIN_FLAG_SQUAD_ORDERS_LABEL', 'Squad Orders'), flipWhen: msg('FE_ADMIN_FLAG_SQUAD_ORDERS_FLIPWHEN', 'Once live-verified'), impact: msg('FE_ADMIN_FLAG_SQUAD_ORDERS_IMPACT', 'Backend flag for squad ordering') },
});

// Global release configuration; campus admins can inspect, super admins can edit.
export default function AdminFeatureFlags() {
  useMessages();
  const FLAG_META = flagMetadata();
  const { user } = useHolyGrill();
  const { campuses } = useCampus();
  const writePending = useRef(false);
  const canEdit = user?.role === 'super_admin';
  const [error, setError] = useState<string | null>(null);
  const [flags, setFlags] = useState(null);
  const [busy, setBusy] = useState(null);
  const [createOpen, setCreateOpen] = useState(false);
  const [draft, setDraft] = useState({ feature_name: '', is_active: false, description: '' });
  const [creating, setCreating] = useState(false);

  // This page edits global rows. Legacy campus overrides are shown read-only.

  const load = async () => {
    setError(null);
    try {
      setFlags(await liveApi.admin.getFeatureFlags());
    } catch (e) {
      toast({ title: msg('FE_ADMIN_FEATURE_FLAGS_COULDN_T_LOAD_FEATURE_FLAGS', "Couldn't load feature flags"), description: e.message, variant: 'destructive' });
      setError(e.message || msg('FE_ADMIN_FEATURE_FLAGS_COULDN_T_LOAD_FEATURE_FLAGS', "Couldn't load feature flags"));
    }
  };

  useEffect(() => { load(); }, []);

  const toggle = async (name, current) => {
    if (!canEdit || writePending.current) return;
    writePending.current = true;
    setBusy(name);
    try {
      // PATCH /:flag_name is a server-side upsert. The backend owns the confirmation
      // wording (MSG.FEATURE_FLAG_UPDATED) — surface res.message verbatim.
      const res = await liveApi.admin.toggleFeatureFlag(name, { is_active: !current });
      toast({ title: res?.message || msg('FE_ADMIN_FLAGS_SAVED', 'Feature flag saved') });
      await load();
      await loadFeatureFlags();
    } catch (e) {
      toast({ title: msg('FE_ADMIN_FEATURE_FLAGS_FAILED_TO_UPDATE_FLAG', 'Failed to update flag'), description: e.message, variant: 'destructive' });
    }
    writePending.current = false; setBusy(null);
  };

  const createFlag = async () => {
    if (!canEdit || writePending.current) return;
    const name = draft.feature_name.trim();
    if (!/^[a-z][a-z0-9_]{2,63}$/.test(name)) {
      toast({ title: msg('FE_ADMIN_FEATURE_FLAGS_INVALID_FLAG_NAME', 'Invalid flag name'), description: msg('FE_ADMIN_FEATURE_FLAGS_USE_LOWERCASE_LETTERS_NUMBERS_AND', 'Use lowercase letters, numbers and underscores (min 3 chars).'), variant: 'destructive' });
      return;
    }
    writePending.current = true; setCreating(true);
    try {
      const res = await liveApi.admin.createFeatureFlag({ feature_name: name, is_active: !!draft.is_active, description: draft.description.trim() || null });
      toast({ title: res?.message || msg('FE_ADMIN_FLAGS_CREATED', 'Feature flag created') });
      setCreateOpen(false);
      setDraft({ feature_name: '', is_active: false, description: '' });
      await load();
      await loadFeatureFlags();
    } catch (e) {
      // Server rejects duplicates with "Feature flag already exists" — shown verbatim.
      toast({ title: msg('FE_ADMIN_FEATURE_FLAGS_FAILED_TO_CREATE_FLAG', 'Failed to create flag'), description: e.message, variant: 'destructive' });
    }
    writePending.current = false; setCreating(false);
  };

  return (
    <div className="space-y-4">
      {/* Two-mechanism note — backend DB flags vs the app's built-in client toggles */}
      <div className="rounded-2xl bg-accent/20 border border-accent/40 p-3.5 flex items-start gap-2.5">
        <Info className="w-4 h-4 text-accent-foreground shrink-0 mt-0.5" />
        <p className="text-[11px] text-foreground/80 leading-relaxed">
          {msg('FE_ADMIN_FLAGS_SCOPE', 'Release switches apply across campuses. Only a super admin can change them.')} {msg('FE_ADMIN_FLAGS_OVERRIDE_HELP', 'Campus overrides shown below take precedence for that campus. Changing the global switch preserves those overrides.')}
        </p>
      </div>

      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div className="flex items-center gap-2 text-sm font-bold text-foreground">
          {flags ? msg('FE_ADMIN_FLAGS_COUNT', '{count} release switches', { count: flags.length }) : msg('FE_ADMIN_FLAGS_LOADING', 'Loading…')}
        </div>
        {canEdit && <button disabled={busy != null || creating} onClick={() => setCreateOpen(true)} className="flex items-center gap-1.5 px-4 py-2.5 rounded-full bg-gradient-cta text-white text-sm font-bold shadow-glow active:scale-95 transition">
          <Plus className="w-4 h-4" /> {msg('FE_ADMIN_FLAGS_CREATE', "Create Flag")}
        </button>}
      </div>

      {error ? <Card className="p-4"><p role="alert" className="text-sm text-destructive">{error}</p><button onClick={load} className="mt-2 font-bold text-primary">{msg('FE_ADMIN_FLAGS_RETRY', 'Retry')}</button></Card> : flags == null ? (
        <div className="grid sm:grid-cols-2 gap-3">
          {Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-28" />)}
        </div>
      ) : flags.length === 0 ? (
        <Card>
          <EmptyState
            icon={AlertCircle}
            title={msg('FE_ADMIN_FLAGS_EMPTY_TITLE', "No feature flags yet")}
            body={msg('FE_ADMIN_FLAGS_EMPTY_BODY', "Create the first flag — new flags default OFF so you can verify before going live.")}
            action={canEdit &&
              <button disabled={busy != null || creating} onClick={() => setCreateOpen(true)} className="flex items-center gap-1.5 px-4 py-2 rounded-full bg-primary text-white text-xs font-bold active:scale-95 transition">
                <Plus className="w-3.5 h-3.5" /> {msg('FE_ADMIN_FLAGS_FIRST', "Create the first flag")}
              </button>
            }
          />
        </Card>
      ) : (
        <div className="grid sm:grid-cols-2 gap-3">
          {flags.map((f, i) => {
            const name = f.feature_name || f.name;
            const meta = FLAG_META[name] || { label: name, flipWhen: '—', impact: f.description || '' };
            const isActive = f.is_active ?? f.enabled ?? false;
            return (
              <motion.div key={name} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: Math.min(i * 0.03, 0.2), duration: 0.25 }}>
                <Card className="p-4">
                  <div className="flex items-start gap-3">
                    <Toggle label={msg('FE_ADMIN_FLAGS_SWITCH_LABEL', '{label} feature flag', { label: meta.label })} checked={isActive} onChange={() => toggle(name, isActive)} disabled={!canEdit || busy != null || creating} />
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 mb-1 flex-wrap">
                        <span className="font-bold text-sm text-foreground">{meta.label}</span>
                        <span className="font-mono text-[10px] text-muted-foreground truncate">{name}</span>
                        {isActive ? <Pill tone="green"><span className="w-1.5 h-1.5 rounded-full bg-success" /> {msg('FE_ADMIN_FLAGS_ACTIVE', 'Active')}</Pill> : <Pill tone="outline">{msg('FE_ADMIN_FLAGS_OFF', 'Off')}</Pill>}
                      </div>
                      <div className="text-[11px] text-muted-foreground space-y-0.5">
                        <div>📌 {msg('FE_ADMIN_FLAGS_FLIP_WHEN', 'Flip when:')} <span className="text-foreground font-semibold">{meta.flipWhen}</span></div>
                        {(f.description || meta.impact) && <div>👁 {f.description || meta.impact}</div>}
                        {f.campus_overrides?.length > 0 && <div className="rounded-lg bg-accent/20 p-2" role="note">
                          <strong>{msg('FE_ADMIN_FLAGS_OVERRIDES', 'Campus overrides')}</strong>
                          {f.campus_overrides.map(override => <div key={override.campus_id}>{campuses.find(campus => campus.id === override.campus_id)?.name || override.campus_id}: {override.is_active ? msg('FE_ADMIN_FLAGS_ACTIVE', 'Active') : msg('FE_ADMIN_FLAGS_OFF', 'Off')}</div>)}
                        </div>}
                        {f.updated_at && (
                          <div className="flex items-center gap-1"><Clock className="w-3 h-3" /> {msg('FE_ADMIN_FLAGS_UPDATED', 'Updated {date}', { date: new Date(f.updated_at).toLocaleString() })}</div>
                        )}
                      </div>
                    </div>
                  </div>
                </Card>
              </motion.div>
            );
          })}
        </div>
      )}

      <Modal open={createOpen} onClose={() => setCreateOpen(false)} title={msg('FE_ADMIN_FLAGS_CREATE_TITLE', "Create Feature Flag")}>
        <div className="space-y-3">
          <p className="text-xs text-muted-foreground">
            {msg('FE_ADMIN_FLAGS_CREATE_HELP', "Adds a toggle the backend can read. New flags default OFF so you can verify before going live.")} {msg('FE_ADMIN_FLAGS_WIRING_HELP', 'A new name has no effect until a feature is connected to it.')}
          </p>
          <Field label={msg('FE_ADMIN_FLAGS_NAME', "Flag name (lowercase, numbers, underscores)")}>
            <TextInput maxLength={64} value={draft.feature_name} onChange={(e) => setDraft({ ...draft, feature_name: e.target.value.toLowerCase().replace(/[^a-z0-9_]/g, '') })} placeholder={msg('FE_ADMIN_FLAGS_NAME_EXAMPLE', "new_checkout_flow")} />
          </Field>
          <Field label={msg('FE_ADMIN_FLAGS_DESCRIPTION', "What it controls")}>
            <TextInput maxLength={500} value={draft.description} onChange={(e) => setDraft({ ...draft, description: e.target.value })} placeholder={msg('FE_ADMIN_FLAGS_DESCRIPTION_EXAMPLE', "Shows the new checkout flow to students")} />
          </Field>
          <div className="flex items-center gap-2.5">
            <Toggle checked={draft.is_active} onChange={(v) => setDraft({ ...draft, is_active: v })} />
            <span className="text-xs font-bold text-foreground">{msg('FE_ADMIN_FLAGS_ENABLE', "Enable immediately (default OFF)")}</span>
          </div>
          <button onClick={createFlag} disabled={!canEdit || busy != null || creating || !draft.feature_name.trim()} className="w-full py-3 rounded-full bg-gradient-cta text-white font-bold text-sm active:scale-95 transition disabled:opacity-50">
            {creating ? msg('FE_ADMIN_FLAGS_CREATING', "Creating…") : msg('FE_ADMIN_FLAGS_CREATE', "Create Flag")}
          </button>
        </div>
      </Modal>
    </div>
  );
}
