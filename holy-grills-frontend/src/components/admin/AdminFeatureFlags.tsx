import { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import { Plus, Info, Clock, AlertCircle } from 'lucide-react';
import { liveApi } from '@/lib/liveApi';
import { toast } from '@/components/ui/use-toast';
import { Card, Skeleton, EmptyState, Modal, Field, TextInput, Pill, Toggle } from './ui/AdminKit';

// Flag metadata — admin guidance only. On/off values come from the backend's
// feature_flags table (is_active column), never from this map.
const FLAG_META = {
  leaderboard_prizes: { label: 'Leaderboard Prizes', flipWhen: 'After first month of data', impact: 'Shows/hides prize indicators on the leaderboard' },
  free_side_credits: { label: 'Free Side Credits', flipWhen: 'After first month of data', impact: 'Shows/hides free side UI in rewards' },
  exclusive_spin: { label: 'Exclusive Spin', flipWhen: 'After first month of data', impact: 'Shows/hides exclusive spin wheel for top earners' },
  hall_of_fame: { label: 'Hall of Fame', flipWhen: 'After 3 months of data', impact: 'Shows/hides the Hall of Fame page' },
  badge_system: { label: 'Badge System', flipWhen: '200+ active users', impact: 'Shows/hides badges on profiles and challenges' },
  spin_and_win: { label: 'Spin & Win', flipWhen: '200+ active users', impact: 'Shows/hides the daily spin wheel' },
  marketplace_general: { label: 'Marketplace', flipWhen: '500+ active users', impact: 'Shows/hides the marketplace' },
  hp_transfer: { label: 'HP Transfer', flipWhen: 'Phase 3', impact: 'Shows/hides HP transfer between users' },
  squad_order_enabled: { label: 'Squad Orders', flipWhen: 'Once live-verified', impact: 'Backend flag for squad ordering' },
  whatsapp_support_enabled: { label: 'WhatsApp Support', flipWhen: 'When support number is staffed', impact: 'Toggles the support button in the app' },
};

// Feature Flags — Domain 16. GET /admin/feature-flags (campus_id query) ·
// POST (create, defaults OFF, "Feature flag already exists" error) ·
// PATCH /:flag_name (upsert). The campus selector uses the real campus list
// from context — Global sends no campus_id.
export default function AdminFeatureFlags() {
  const [flags, setFlags] = useState(null);
  const [busy, setBusy] = useState(null);
  const [createOpen, setCreateOpen] = useState(false);
  const [draft, setDraft] = useState({ feature_name: '', is_active: false, description: '' });
  const [creating, setCreating] = useState(false);

  // Feature flags are GLOBAL by backend design — campus_id is always written NULL
  // and ignored on read, so there is no campus scope selector here.

  const load = async () => {
    try {
      setFlags(await liveApi.admin.getFeatureFlags());
    } catch (e) {
      toast({ title: "Couldn't load feature flags", description: e.message, variant: 'destructive' });
      setFlags([]);
    }
  };

  useEffect(() => { load(); }, []);

  const toggle = async (name, current) => {
    setBusy(name);
    try {
      // PATCH /:flag_name is a server-side upsert. The backend owns the confirmation
      // wording (MSG.FEATURE_FLAG_UPDATED) — surface res.message verbatim.
      const res = await liveApi.admin.toggleFeatureFlag(name, { is_active: !current });
      toast({ title: res?.message || `${FLAG_META[name]?.label || name} ${!current ? 'enabled' : 'disabled'}` });
      await load();
    } catch (e) {
      toast({ title: 'Failed to update flag', description: e.message, variant: 'destructive' });
    }
    setBusy(null);
  };

  const createFlag = async () => {
    const name = draft.feature_name.trim();
    if (!/^[a-z][a-z0-9_]{2,}$/.test(name)) {
      toast({ title: 'Invalid flag name', description: 'Use lowercase letters, numbers and underscores (min 3 chars).', variant: 'destructive' });
      return;
    }
    setCreating(true);
    try {
      const res = await liveApi.admin.createFeatureFlag({ feature_name: name, is_active: !!draft.is_active, description: draft.description.trim() || null });
      toast({ title: res?.message || 'Feature flag created' });
      setCreateOpen(false);
      setDraft({ feature_name: '', is_active: false, description: '' });
      await load();
    } catch (e) {
      // Server rejects duplicates with "Feature flag already exists" — shown verbatim.
      toast({ title: 'Failed to create flag', description: e.message, variant: 'destructive' });
    }
    setCreating(false);
  };

  return (
    <div className="space-y-4">
      {/* Two-mechanism note — backend DB flags vs the app's built-in client toggles */}
      <div className="rounded-2xl bg-accent/20 border border-accent/40 p-3.5 flex items-start gap-2.5">
        <Info className="w-4 h-4 text-accent-foreground shrink-0 mt-0.5" />
        <p className="text-[11px] text-foreground/80 leading-relaxed">
          These database flags are the backend's mechanism — backend routes read them server-side. The app also ships a few
          built-in UI toggles that gate screens client-side; flipping a flag here does not automatically change those built-ins.
        </p>
      </div>

      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div className="flex items-center gap-2 text-sm font-bold text-foreground">
          {flags ? `${flags.length} flag${flags.length === 1 ? '' : 's'}` : 'Loading…'}
        </div>
        <button onClick={() => setCreateOpen(true)} className="flex items-center gap-1.5 px-4 py-2.5 rounded-full bg-gradient-cta text-white text-sm font-bold shadow-glow active:scale-95 transition">
          <Plus className="w-4 h-4" /> Create Flag
        </button>
      </div>

      {flags == null ? (
        <div className="grid sm:grid-cols-2 gap-3">
          {Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-28" />)}
        </div>
      ) : flags.length === 0 ? (
        <Card>
          <EmptyState
            icon={AlertCircle}
            title="No feature flags yet"
            body="Create the first flag — new flags default OFF so you can verify before going live."
            action={
              <button onClick={() => setCreateOpen(true)} className="flex items-center gap-1.5 px-4 py-2 rounded-full bg-primary text-white text-xs font-bold active:scale-95 transition">
                <Plus className="w-3.5 h-3.5" /> Create the first flag
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
                    <Toggle checked={isActive} onChange={() => toggle(name, isActive)} disabled={busy === name} />
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 mb-1 flex-wrap">
                        <span className="font-bold text-sm text-foreground">{meta.label}</span>
                        <span className="font-mono text-[10px] text-muted-foreground truncate">{name}</span>
                        {isActive ? <Pill tone="green"><span className="w-1.5 h-1.5 rounded-full bg-success" /> Active</Pill> : <Pill tone="outline">Off</Pill>}
                      </div>
                      <div className="text-[11px] text-muted-foreground space-y-0.5">
                        <div>📌 Flip when: <span className="text-foreground font-semibold">{meta.flipWhen}</span></div>
                        {meta.impact && <div>👁 {meta.impact}</div>}
                        {f.description && !FLAG_META[name] && <div>📝 {f.description}</div>}
                        {f.updated_at && (
                          <div className="flex items-center gap-1"><Clock className="w-3 h-3" /> Updated {new Date(f.updated_at).toLocaleString()}</div>
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

      <Modal open={createOpen} onClose={() => setCreateOpen(false)} title="Create Feature Flag">
        <div className="space-y-3">
          <p className="text-xs text-muted-foreground">
            Adds a toggle the backend can read. New flags default OFF so you can verify before going live.
          </p>
          <Field label="Flag name (lowercase, numbers, underscores)">
            <TextInput value={draft.feature_name} onChange={(e) => setDraft({ ...draft, feature_name: e.target.value.toLowerCase().replace(/[^a-z0-9_]/g, '') })} placeholder="new_checkout_flow" />
          </Field>
          <Field label="What it controls">
            <TextInput value={draft.description} onChange={(e) => setDraft({ ...draft, description: e.target.value })} placeholder="Shows the new checkout flow to students" />
          </Field>
          <div className="flex items-center gap-2.5">
            <Toggle checked={draft.is_active} onChange={(v) => setDraft({ ...draft, is_active: v })} />
            <span className="text-xs font-bold text-foreground">Enable immediately (default OFF)</span>
          </div>
          <button onClick={createFlag} disabled={creating || !draft.feature_name.trim()} className="w-full py-3 rounded-full bg-gradient-cta text-white font-bold text-sm active:scale-95 transition disabled:opacity-50">
            {creating ? 'Creating…' : 'Create Flag'}
          </button>
        </div>
      </Modal>
    </div>
  );
}