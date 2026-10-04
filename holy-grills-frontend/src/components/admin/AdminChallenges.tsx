import { useState, useEffect } from 'react';
import { Plus, Trash2, Pencil, Gift } from 'lucide-react';
import { liveApi as mockApi } from '@/lib/liveApi';
import LoadingSpinner from '@/components/LoadingSpinner';
import { toast } from '@/components/ui/use-toast';
import { Field, TextInput, Card, Pill, Toggle, Modal } from './AdminShared';
import { msg } from '@/lib/messages';

// Trigger types map 1:1 to the backend's milestone verification logic.
const TRIGGER_TYPES = [
  'first_order', 'first_review', 'first_referral', 'first_event', 'first_squad',
  'first_hp_gift_sent', 'graduation', 'birthday', 'social_follow', 'membership_months',
  'hp_earned_total', 'referral_count', 'order_count', 'review_count', 'event_checkins',
  'squad_orders', 'order_streak_weeks', 'login_streak_cycles',
];

const TRIGGER_LABELS = {
  first_order: 'First Order', first_review: 'First Review', first_referral: 'First Referral',
  first_event: 'First Event', first_squad: 'First Squad Order', first_hp_gift_sent: 'First HP Gift Sent',
  graduation: 'Graduation', birthday: 'Birthday', social_follow: 'Social Follow',
  membership_months: 'Membership Months', hp_earned_total: 'HP Earned (Total)',
  referral_count: 'Referral Count', order_count: 'Order Count', review_count: 'Review Count',
  event_checkins: 'Event Check-ins', squad_orders: 'Squad Orders',
  order_streak_weeks: 'Order Streak (Weeks)', login_streak_cycles: 'Login Streak Cycles',
};

const WINDOWS = [
  { value: '', label: 'Permanent' },
  { value: 'weekly', label: 'Weekly' },
  { value: 'monthly', label: 'Monthly' },
];

export default function AdminChallenges() {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [editItem, setEditItem] = useState(null);
  const [creating, setCreating] = useState(false);
  const [busy, setBusy] = useState(null);

  useEffect(() => { load(); }, []);

  const load = async () => {
    setLoading(true);
    try { setItems(await mockApi.admin.getChallengesAdmin()); }
    catch { setItems([]); }
    setLoading(false);
  };

  const toggleActive = async (id, current, title) => {
    setBusy(id);
    try {
      await mockApi.admin.updateChallenge(id, { is_active: !current });
      toast({ title: `${!current ? '✅ Activated' : '⏸ Deactivated'}`, description: `"${title}" is now ${!current ? 'live' : 'paused'}.` });
      await load();
    } catch (e) { toast({ title: msg('FE_ADMIN_CHALLENGES_FAILED', 'Failed'), description: e.message, variant: 'destructive' }); }
    setBusy(null);
  };

  const remove = async (id, title) => {
    if (!confirm(`Delete "${title}"?`)) return;
    setBusy(id);
    try {
      await mockApi.admin.deleteChallenge(id);
      toast({ title: msg('FE_ADMIN_CHALLENGES_MILESTONE_DELETED', 'Milestone deleted'), description: `"${title}" removed.` });
      await load();
    } catch (e) { toast({ title: msg('FE_ADMIN_CHALLENGES_FAILED', 'Failed'), description: e.message, variant: 'destructive' }); }
    setBusy(null);
  };

  const grant = async (id, title) => {
    const uid = prompt(`Grant "${title}" to which user ID?`);
    if (!uid) return;
    setBusy(id);
    try {
      await mockApi.admin.grantChallenge(id, { user_id: uid.trim() });
      toast({ title: msg('FE_ADMIN_CHALLENGES_MILESTONE_GRANTED', '✅ Milestone granted'), description: `"${title}" manually granted.` });
      await load();
    } catch (e) { toast({ title: msg('FE_ADMIN_CHALLENGES_FAILED', 'Failed'), description: e.message, variant: 'destructive' }); }
    setBusy(null);
  };

  if (loading) return <LoadingSpinner label="Loading milestones..." />;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <p className="text-xs text-muted-foreground">Time-boxed challenges and permanent milestones. Trigger types drive automatic completion; grants are manual.</p>
        <button onClick={() => setCreating(true)} className="flex items-center gap-1.5 px-4 py-2 rounded-full bg-gradient-cta text-white text-sm font-bold shadow-md"><Plus className="w-4 h-4" /> New Milestone</button>
      </div>

      <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-3">
        {items.map((c) => (
          <Card key={c.id}>
            <div className="flex items-center justify-between mb-2">
              <Pill tone="flame">Challenge</Pill>
              <Toggle checked={c.is_active} onChange={() => toggleActive(c.id, c.is_active, c.title)} disabled={busy === c.id} />
            </div>
            <div className="font-bold text-sm text-foreground">{c.title}</div>
            <div className="text-xs text-muted-foreground mt-0.5 mb-2 line-clamp-2">{c.description}</div>
            <div className="flex flex-wrap gap-1 mb-2">
              <Pill tone="cocoa">{TRIGGER_LABELS[c.trigger_type] || c.trigger_type.replace(/_/g, ' ')}</Pill>
              <Pill tone="cocoa">≥ {c.trigger_value}</Pill>
              <Pill tone="green">{c.hp_awarded} HP</Pill>
              {c.time_window ? <Pill tone="blue">{c.time_window}</Pill> : <Pill tone="amber">permanent</Pill>}
            </div>
            <div className="flex items-center justify-between text-[11px] text-muted-foreground">
              <span>{c.completions} completed</span>
              <div className="flex gap-1">
                <button onClick={() => setEditItem(c)} className="p-1.5 rounded-lg hover:bg-secondary"><Pencil className="w-3.5 h-3.5 text-muted-foreground" /></button>
                <button onClick={() => grant(c.id, c.title)} disabled={busy === c.id} className="p-1.5 rounded-lg hover:bg-primary/10"><Gift className="w-3.5 h-3.5 text-primary" /></button>
                <button onClick={() => remove(c.id, c.title)} disabled={busy === c.id} className="p-1.5 rounded-lg hover:bg-red-50"><Trash2 className="w-3.5 h-3.5 text-red-500" /></button>
              </div>
            </div>
          </Card>
        ))}
      </div>

      {(creating || editItem) && (
        <ChallengeModal item={editItem} onClose={() => { setCreating(false); setEditItem(null); }} onSaved={load} />
      )}
    </div>
  );
}

function ChallengeModal({ item, onClose, onSaved }) {
  const [form, setForm] = useState(item ? { ...item } : { title: '', description: '', trigger_type: 'order_count', trigger_value: 1, hp_awarded: 50, time_window: 'weekly' });
  const [submitting, setSubmitting] = useState(false);

  const submit = async () => {
    setSubmitting(true);
    const body = {
      title: form.title,
      description: form.description,
      trigger_type: form.trigger_type,
      trigger_value: Number(form.trigger_value),
      hp_awarded: Number(form.hp_awarded),
      time_window: form.time_window || null,
      icon_won: form.icon_won || undefined,
      icon_locked: form.icon_locked || undefined,
      social_link: form.social_link || undefined,
      is_active: form.is_active ?? false,
    };
    try {
      if (item) { await mockApi.admin.updateChallenge(item.id, body); toast({ title: msg('FE_ADMIN_CHALLENGES_MILESTONE_UPDATED', '✅ Milestone updated'), description: `"${body.title}" saved.` }); }
      else { await mockApi.admin.createChallenge(body); toast({ title: msg('FE_ADMIN_CHALLENGES_MILESTONE_CREATED', '✅ Milestone created'), description: `"${body.title}" is now live.` }); }
      onClose(); onSaved();
    } catch (e) { toast({ title: msg('FE_ADMIN_CHALLENGES_FAILED', 'Failed'), description: e.message, variant: 'destructive' }); }
    setSubmitting(false);
  };

  return (
    <Modal open onClose={onClose} title={item ? 'Edit Milestone' : 'New Milestone'}>
      <div className="space-y-3">
        <Field label="Title"><TextInput value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} /></Field>
        <Field label="Description"><TextInput value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} /></Field>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Trigger type">
            <select value={form.trigger_type} onChange={(e) => setForm({ ...form, trigger_type: e.target.value, trigger_value: 1 })} className="w-full mt-1 p-2.5 rounded-xl border border-border text-sm">
              {TRIGGER_TYPES.map((t) => <option key={t} value={t}>{TRIGGER_LABELS[t] || t.replace(/_/g, ' ')}</option>)}
            </select>
          </Field>
          <Field label="Trigger value (target count)" hint="The target count to complete the milestone (e.g. 5 for 5 orders).">
            <TextInput type="number" value={form.trigger_value} onChange={(e) => setForm({ ...form, trigger_value: e.target.value })} />
          </Field>
        </div>
        <div className="grid grid-cols-2 gap-3">
          <Field label="HP awarded"><TextInput type="number" value={form.hp_awarded} onChange={(e) => setForm({ ...form, hp_awarded: e.target.value })} /></Field>
          <Field label="Time window">
            <select value={form.time_window || ''} onChange={(e) => setForm({ ...form, time_window: e.target.value || null })} className="w-full mt-1 p-2.5 rounded-xl border border-border text-sm">
              {WINDOWS.map((w) => <option key={w.value} value={w.value}>{w.label}</option>)}
            </select>
          </Field>
        </div>
        <button onClick={submit} disabled={submitting || !form.title} className="w-full py-3 rounded-full bg-gradient-cta text-white font-bold disabled:opacity-50">{submitting ? 'Saving...' : 'Save Milestone'}</button>
      </div>
    </Modal>
  );
}