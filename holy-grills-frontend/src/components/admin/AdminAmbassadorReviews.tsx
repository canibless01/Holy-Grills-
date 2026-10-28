import { useState, useEffect, useCallback } from 'react';
import { Check, X, Gift, Loader2, ChevronDown, ChevronUp } from 'lucide-react';
import { liveApi } from '@/lib/liveApi';
import { useHolyGrill } from '@/lib/HolyGrillContext';
import { Card, Field, TextInput, Modal, Pill } from './AdminShared';
import StaffPanelSkeleton from '@/components/skeletons/StaffPanelSkeleton';
import { toast } from '@/components/ui/use-toast';
import { msg } from '@/lib/messages';

const thisMonth = () => new Date().toISOString().slice(0, 7);

export default function AdminAmbassadorReviews() {
  const { user } = useHolyGrill();
  const isFinancialAdmin = ['admin', 'super_admin'].includes(user?.role);
  const [month, setMonth] = useState(thisMonth());
  const [reviews, setReviews] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [grantFor, setGrantFor] = useState<any | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try { setReviews(await liveApi.ambassadors.listReviews(month)); }
    catch (e) { toast({ title: e.message, variant: 'destructive' }); }
    finally { setLoading(false); }
  }, [month]);
  useEffect(() => { load(); }, [load]);

  const recommend = async (review: any, recommendation: 'recommend' | 'do_not_recommend') => {
    const note = window.prompt(
      recommendation === 'recommend'
        ? 'Recommendation note (optional): why should they receive the monthly benefit?'
        : 'Reason for not recommending (optional):',
      review.recommendation_note || '',
    ) || '';
    try {
      await liveApi.ambassadors.recommend(review.ambassador_id, { month, recommendation, note });
      toast({ title: 'Recommendation saved' });
      load();
    } catch (e) { toast({ title: e.message, variant: 'destructive' }); }
  };

  const decide = async (review: any, decision: 'approved' | 'rejected') => {
    const note = window.prompt(`Decision note for ${decision} (optional):`, review.decision_note || '') || '';
    try {
      await liveApi.ambassadors.decide(review.ambassador_id, { month, decision, note });
      toast({ title: `Marked ${decision}` });
      load();
    } catch (e) { toast({ title: e.message, variant: 'destructive' }); }
  };

  if (loading) return <StaffPanelSkeleton />;

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3 flex-wrap">
        <Field label={msg('FE_ADMIN_AMBASSADOR_MONTH', 'Programme month')}>
          <input type="month" value={month} onChange={(e) => setMonth(e.target.value)}
            className="mt-1 p-2.5 rounded-xl border border-border text-sm" />
        </Field>
        <span className="text-xs text-muted-foreground self-end pb-2">{reviews.length} ambassador{reviews.length === 1 ? '' : 's'}</span>
      </div>

      {reviews.length === 0 && (
        <Card className="p-8 text-center text-sm text-muted-foreground">No active ambassadors for this campus yet.</Card>
      )}

      {reviews.map((r) => (
        <ReviewCard key={`${r.ambassador_id}-${r.month}`} review={r}
          isFinancialAdmin={isFinancialAdmin}
          onRecommend={recommend} onDecide={decide}
          onGrant={() => setGrantFor(r)} onChanged={load} />
      ))}

      {grantFor && (
        <GrantModal review={grantFor} month={month}
          onClose={() => setGrantFor(null)}
          onSaved={() => { setGrantFor(null); load(); }} />
      )}
    </div>
  );
}

function ReviewCard({ review, isFinancialAdmin, onRecommend, onDecide, onGrant, onChanged }: any) {
  const [open, setOpen] = useState(false);
  const [grants, setGrants] = useState<any[]>([]);
  useEffect(() => {
    if (!open) return;
    liveApi.ambassadors.listGrants(review.ambassador_id).then(setGrants).catch(() => undefined);
  }, [open, review.ambassador_id]);
  const pct = (v: number) => `${v}%`;
  return (
    <Card className="p-4 space-y-3">
      <button onClick={() => setOpen((v) => !v)} className="w-full flex items-center justify-between gap-2 text-left">
        <div>
          <div className="text-sm font-bold flex items-center gap-2">
            {review.ambassador_id.slice(0, 8)}…
            {review.decision === 'approved' && <Pill tone="green">approved</Pill>}
            {review.decision === 'rejected' && <Pill tone="red">rejected</Pill>}
            {review.decision === 'pending' && <Pill tone="outline">pending</Pill>}
          </div>
          <div className="text-[11px] text-muted-foreground">{review.month}</div>
        </div>
        {open ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
      </button>

      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-center">
        <Metric label="Assigned" value={review.assigned_count} />
        <Metric label="Seen" value={review.seen_count} />
        <Metric label="Shared" value={review.shared_count} />
        <Metric label={msg('FE_ADMIN_AMBASSADOR_COMPLETION', 'Sharing completion')} value={pct(review.completion_rate)} />
        <Metric label={msg('FE_ADMIN_AMBASSADOR_SIGNUPS', 'Signups')} value={review.signups_count} />
        <Metric label={msg('FE_ADMIN_AMBASSADOR_ORDERS', 'Referred orders')} value={review.orders_count} />
        <Metric label={msg('FE_ADMIN_AMBASSADOR_TARGET', 'Share target')} value={pct(review.share_target_progress ?? 0)} />
        <Metric label="Weekly target" value={`${review.weekly_share_target ?? 4}/wk`} />
      </div>

      {Array.isArray(review.milestones) && review.milestones.length > 0 && (
        <div className="space-y-1">
          <div className="text-[10px] font-extrabold uppercase tracking-wide text-muted-foreground">
            {msg('FE_AMBASSADOR_MILESTONE_PROGRESS', 'Milestone progress')}
          </div>
          {review.milestones.map((mp: any) => (
            <div key={mp.milestone.id} className="flex items-center justify-between text-xs gap-2">
              <span className="truncate">{mp.milestone.metric} ≥ {mp.milestone.threshold}</span>
              <span className={mp.reached ? 'text-success font-bold' : 'text-muted-foreground'}>
                {mp.metric_value}/{mp.milestone.threshold}
                {mp.claim?.status && <em className="ml-1 not-italic">· {mp.claim.status.replace('_', ' ')}</em>}
              </span>
            </div>
          ))}
        </div>
      )}

      <div className="flex items-center gap-2 flex-wrap">
        <button onClick={() => onRecommend(review, 'recommend')}
          className="flex items-center gap-1 px-3 py-1.5 rounded-full border border-success/40 text-success text-[11px] font-bold">
          <Check className="w-3.5 h-3.5" />{msg('FE_ADMIN_AMBASSADOR_RECOMMEND', 'Recommend benefit')}
        </button>
        <button onClick={() => onRecommend(review, 'do_not_recommend')}
          className="flex items-center gap-1 px-3 py-1.5 rounded-full border border-border text-muted-foreground text-[11px] font-bold">
          <X className="w-3.5 h-3.5" />{msg('FE_ADMIN_AMBASSADOR_DO_NOT_RECOMMEND', 'Do not recommend')}
        </button>
        {isFinancialAdmin && (
          <>
            <button onClick={() => onDecide(review, 'approved')}
              className="flex items-center gap-1 px-3 py-1.5 rounded-full bg-success text-white text-[11px] font-bold">
              <Check className="w-3.5 h-3.5" />{msg('FE_ADMIN_AMBASSADOR_APPROVE', 'Approve & grant reward')}
            </button>
            <button onClick={() => onDecide(review, 'rejected')}
              className="px-3 py-1.5 rounded-full border border-destructive/40 text-destructive text-[11px] font-bold">
              {msg('FE_ADMIN_AMBASSADOR_REJECT', 'Reject')}
            </button>
            <button onClick={onGrant}
              className="flex items-center gap-1 ml-auto px-3 py-1.5 rounded-full bg-primary text-white text-[11px] font-bold">
              <Gift className="w-3.5 h-3.5" />Issue reward
            </button>
          </>
        )}
      </div>

      {open && (
        <div className="border-t border-border pt-3 space-y-2">
          {review.recommendation !== 'none' && (
            <div className="text-[11px]">
              <span className="font-bold">Recommendation: </span>
              <Pill tone={review.recommendation === 'recommend' ? 'green' : 'red'}>{review.recommendation.replace('_', ' ')}</Pill>
              {review.recommendation_note && <span className="text-muted-foreground italic"> “{review.recommendation_note}”</span>}
            </div>
          )}
          {review.decision_note && (
            <div className="text-[11px]"><span className="font-bold">Decision note: </span><span className="text-muted-foreground">{review.decision_note}</span></div>
          )}
          <div className="text-[10px] font-extrabold uppercase tracking-wide text-muted-foreground">Grants</div>
          {grants.length === 0 ? <div className="text-[11px] text-muted-foreground">No grants issued for this programme yet.</div> : grants.map((g) => (
            <div key={g.id} className="text-[11px] flex justify-between gap-2">
              <span className="font-bold">{g.reward_category.replace('_', ' ')} · {g.amount}</span>
              <span className="text-muted-foreground">{g.month} · {g.status}{g.expires_at ? ` · exp ${String(g.expires_at).slice(0, 10)}` : ''}</span>
            </div>
          ))}
          <button onClick={onChanged} className="text-[10px] text-primary underline">refresh</button>
        </div>
      )}
    </Card>
  );
}

function Metric({ label, value }: { label: string; value: any }) {
  return (
    <div className="rounded-xl bg-muted/60 py-2">
      <div className="font-heading font-extrabold text-sm">{value}</div>
      <div className="text-[9px] uppercase tracking-wide text-muted-foreground font-bold">{label}</div>
    </div>
  );
}

const GRANT_TYPES = [
  { value: 'hp', label: msg('FE_ADMIN_AMBASSADOR_GRANT_HP', 'Holy Points (HP)') },
  { value: 'free_side', label: msg('FE_ADMIN_AMBASSADOR_GRANT_FREE_SIDE', 'Free side credits') },
  { value: 'meal_discount', label: msg('FE_ADMIN_AMBASSADOR_GRANT_MEAL', 'Meal discount') },
];

function GrantModal({ review, month, onClose, onSaved }: { review: any; month: string; onClose: () => void; onSaved: () => void }) {
  const [form, setForm] = useState({
    reward_type: 'meal_discount', amount: 3000, validity_days: 14, uses_count: 1,
    reason: '', override_duplicate: false,
  });
  const [busy, setBusy] = useState(false);
  const set = (k: string, v: any) => setForm((f) => ({ ...f, [k]: v }));

  const submit = async () => {
    setBusy(true);
    try {
      await liveApi.ambassadors.createGrant({
        ambassador_id: review.ambassador_id,
        reward_type: form.reward_type,
        amount: Number(form.amount),
        validity_days: Number(form.validity_days) || undefined,
        uses_count: Number(form.uses_count) || 1,
        reason: form.reason,
        month,
        override_duplicate: form.override_duplicate,
      });
      toast({ title: 'Reward issued' });
      onSaved();
    } catch (e) {
      if (e.status === 409) {
        toast({ title: e.message, variant: 'destructive' });
        set('override_duplicate', true); // surface the override for an explicit re-submit
      } else {
        toast({ title: e.message, variant: 'destructive' });
      }
    } finally { setBusy(false); };
  };

  return (
    <Modal open onClose={onClose} title={msg('FE_ADMIN_AMBASSADOR_GRANT_TITLE', 'Issue programme reward')}>
      <div className="space-y-3">
        <Field label={msg('FE_ADMIN_AMBASSADOR_GRANT_TYPE', 'Reward type')}>
          <select value={form.reward_type} onChange={(e) => set('reward_type', e.target.value)}
            className="w-full mt-1 p-2.5 rounded-xl border border-border text-sm">
            {GRANT_TYPES.map((t) => <option key={t.value} value={t.value}>{t.label}</option>)}
          </select>
        </Field>
        <div className="grid grid-cols-2 gap-3">
          <Field label={form.reward_type === 'meal_discount'
            ? msg('FE_ADMIN_AMBASSADOR_MEAL_MAX_VALUE', 'Maximum meal value (₦)')
            : msg('FE_ADMIN_AMBASSADOR_GRANT_AMOUNT', 'Amount / quantity')}>
            <TextInput type="number" min={1} value={form.amount} onChange={(e) => set('amount', e.target.value)} />
          </Field>
          <Field label={msg('FE_ADMIN_AMBASSADOR_GRANT_VALIDITY', 'Validity (days)')}>
            <TextInput type="number" min={1} value={form.validity_days} onChange={(e) => set('validity_days', e.target.value)} />
          </Field>
        </div>
        {form.reward_type === 'meal_discount' && (
          <Field label={msg('FE_ADMIN_AMBASSADOR_GRANT_USES', 'Number of uses')}>
            <TextInput type="number" min={1} value={form.uses_count} onChange={(e) => set('uses_count', e.target.value)} />
          </Field>
        )}
        <Field label={msg('FE_ADMIN_AMBASSADOR_GRANT_REASON', 'Reason')}>
          <textarea rows={2} value={form.reason} onChange={(e) => set('reason', e.target.value)}
            className="w-full mt-1 p-2.5 rounded-xl border border-border text-sm"
            placeholder={`Ambassador programme benefit — ${month}`} />
        </Field>
        <label className="flex items-center gap-2 text-[11px] font-bold text-warn">
          <input type="checkbox" checked={form.override_duplicate} onChange={(e) => set('override_duplicate', e.target.checked)} />
          {msg('FE_ADMIN_AMBASSADOR_GRANT_OVERRIDE', 'I authorise an additional grant this month')}
        </label>
        <button disabled={busy || !form.reason.trim() || Number(form.amount) <= 0} onClick={submit}
          className="w-full py-3 rounded-full bg-gradient-cta text-white font-bold text-sm disabled:opacity-50">
          {busy ? <Loader2 className="w-4 h-4 animate-spin mx-auto" /> : 'Issue reward'}
        </button>
      </div>
    </Modal>
  );
}
