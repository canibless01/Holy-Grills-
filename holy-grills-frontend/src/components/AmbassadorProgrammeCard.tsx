import { useEffect, useState } from 'react';
import { Copy, Check, Globe2, Gift, TrendingUp } from 'lucide-react';
import { liveApi } from '@/lib/liveApi';
import { formatNaira } from '@/lib/hgUtils';
import { msg } from '@/lib/messages';

/**
 * Student-dashboard card for users carrying the Campus Ambassador tag.
 * Renders nothing for everyone else, and only ever shows the signed-in
 * user's own programme data (the endpoint and RLS both enforce ownership).
 */
export default function AmbassadorProgrammeCard() {
  const [data, setData] = useState<any | null>(null);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    let active = true;
    liveApi.ambassadors.myProgramme()
      .then((d) => { if (active && d?.is_ambassador) setData(d); })
      .catch(() => undefined);
    return () => { active = false; };
  }, []);

  if (!data) return null;

  const copy = () => {
    if (!data.tracking_link) return;
    navigator.clipboard.writeText(data.tracking_link);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };

  const month = data.month_activity || {};
  const discounts = data.meal_discounts || [];

  return (
    <div className="rounded-2xl bg-card border border-border p-4 space-y-3">
      <div className="flex items-center justify-between gap-2">
        <h3 className="font-heading font-extrabold text-sm flex items-center gap-1.5">
          <Globe2 className="w-4 h-4 text-primary" />
          {msg('FE_AMBASSADOR_CARD_TITLE', 'Campus Ambassador')}
        </h3>
        <span className="text-[10px] text-muted-foreground">{data.month}</span>
      </div>

      <div className="rounded-xl bg-muted p-2.5 flex items-center gap-2">
        <span className="text-xs text-foreground truncate flex-1">{data.tracking_link}</span>
        <button onClick={copy} className="shrink-0 inline-flex items-center gap-1 text-primary text-xs font-bold">
          {copied ? <Check className="w-3.5 h-3.5" /> : <Copy className="w-3.5 h-3.5" />}
          {copied ? msg('FE_AMBASSADOR_LINK_COPIED', 'Tracking link copied') : msg('FE_AMBASSADOR_COPY_LINK', 'Copy link')}
        </button>
      </div>

      <div className="grid grid-cols-3 gap-2 text-center">
        <MiniStat label={msg('FE_AMBASSADOR_STAT_SIGNUPS', 'Attributed signups')} value={data.lifetime?.total_signups ?? 0} />
        <MiniStat label={msg('FE_AMBASSADOR_STAT_ORDERS', 'Completed referred orders')} value={data.lifetime?.total_orders ?? 0} />
        <MiniStat label={msg('FE_AMBASSADOR_STAT_REFERRAL_HP', 'HP from referrals')} value={data.referral_hp_earned ?? 0} />
      </div>

      <div className="rounded-xl border border-border p-2.5 space-y-1">
        <div className="text-[10px] font-extrabold uppercase tracking-wide text-muted-foreground flex items-center gap-1">
          <TrendingUp className="w-3 h-3" />{msg('FE_AMBASSADOR_MONTH_ACTIVITY', 'This month')}
        </div>
        <div className="grid grid-cols-3 gap-2 text-center text-xs">
          <span><b>{month.signups ?? 0}</b> <span className="text-muted-foreground">{msg('FE_ADMIN_AMBASSADOR_SIGNUPS', 'Signups').toLowerCase()}</span></span>
          <span><b>{month.orders ?? 0}</b> <span className="text-muted-foreground">{msg('FE_ADMIN_AMBASSADOR_ORDERS', 'Referred orders').toLowerCase()}</span></span>
          <span><b>{month.shared_count ?? 0}</b> <span className="text-muted-foreground">shares · {month.completion_rate ?? 0}%</span></span>
        </div>
      </div>

      {Array.isArray(data.milestones) && data.milestones.some((m: any) => m.reached) && (
        <div className="space-y-1">
          <div className="text-[10px] font-extrabold uppercase tracking-wide text-muted-foreground">
            {msg('FE_AMBASSADOR_MILESTONE_PROGRESS', 'Milestone progress')}
          </div>
          {data.milestones.filter((m: any) => m.reached).slice(0, 3).map((m: any) => (
            <div key={m.milestone.id} className="flex justify-between text-xs">
              <span className="truncate">{m.milestone.metric} ≥ {m.milestone.threshold}</span>
              <span className="text-success font-bold shrink-0 ml-2">{m.claim?.status?.replace('_', ' ') || 'reached'}</span>
            </div>
          ))}
        </div>
      )}

      {discounts.length > 0 && (
        <div className="space-y-1.5">
          <div className="text-[10px] font-extrabold uppercase tracking-wide text-muted-foreground flex items-center gap-1">
            <Gift className="w-3 h-3" />{msg('FE_AMBASSADOR_MEAL_DISCOUNTS', 'Your meal discounts')}
          </div>
          {discounts.map((d: any) => (
            <div key={d.id} className="flex items-center justify-between rounded-xl border border-border p-2 text-xs gap-2">
              <div className="min-w-0">
                <div className="font-bold truncate">{d.code} · {formatNaira(d.max_meal_value)}</div>
                <div className="text-[10px] text-muted-foreground">
                  {d.uses_remaining}/{d.uses_total} {msg('FE_ADMIN_AMBASSADOR_GRANT_USES', 'Number of uses').toLowerCase()} ·{' '}
                  {msg('FE_AMBASSADOR_DISCOUNT_EXPIRES', 'Expires')} {String(d.expires_at).slice(0, 10)}
                </div>
              </div>
              <span className={`text-[10px] font-extrabold uppercase shrink-0 ${
                d.status === 'active' ? 'text-success' : d.status === 'expired' ? 'text-muted-foreground' : 'text-primary'}`}>
                {d.status === 'active' ? 'active'
                  : d.status === 'expired' ? msg('FE_AMBASSADOR_DISCOUNT_EXPIRED', 'Expired')
                  : msg('FE_AMBASSADOR_DISCOUNT_REDEEMED', 'Redeemed')}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function MiniStat({ label, value }: { label: string; value: any }) {
  return (
    <div className="rounded-xl bg-muted/60 py-2 px-1">
      <div className="font-heading font-extrabold text-base">{value}</div>
      <div className="text-[9px] uppercase tracking-wide text-muted-foreground font-bold leading-tight">{label}</div>
    </div>
  );
}
