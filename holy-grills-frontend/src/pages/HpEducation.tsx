import React, { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { Flame, Gift, TrendingUp, Calendar, Star, Lock, ChevronRight, HelpCircle, Send } from 'lucide-react';
import { liveApi } from '@/lib/liveApi';
import { useHolyGrill } from '@/lib/HolyGrillContext';
import { isFeatureEnabled } from '@/lib/featureConfig';
import { hpUnlockRatePct, hpPerNairaFood } from '@/lib/appConfig';
import { getTierProgress } from '@/lib/hgUtils';
import HpDisplay from '@/components/HpDisplay';
import HpHistoryLedger from '@/components/HpHistoryLedger';
import HpTransferModal from '@/components/HpTransferModal';
import HpEducationSkeleton from '@/components/skeletons/HpEducationSkeleton';
import TierIcon from '@/components/TierIcon';

const EARN_WAYS = [
  { icon: Flame, title: 'Order food', body: 'Every plate earns HP.', to: '/menu' },
  { icon: TrendingUp, title: 'Login streaks', body: 'Come back. Your bonus grows.', to: '/streak' },
  { icon: Calendar, title: 'Show up at events.', body: 'Check in. Earn HP.', to: '/events' },
  { icon: Star, title: 'Reviews & referrals', body: 'Review or refer. Both earn HP.', to: '/referrals' },
];

export default function HpEducation() {
  const { hpBalance } = useHolyGrill();
  const [showTransfer, setShowTransfer] = useState(false);
  const [backendTiers, setBackendTiers] = useState(null);
  const hpTransferEnabled = isFeatureEnabled('hp_transfer', true);
  const unlockPct = Math.round(hpUnlockRatePct() * 100);
  // Unlock = food_spend × HP_PER_NAIRA_FOOD × unlock_rate_pct.
  // Per ₦1,000: 1000 × 0.1 × 0.30 = 30 HP (not 300 — the earn rate is the multiplier).
  const hpPerThousand = Math.round(1000 * hpPerNairaFood() * hpUnlockRatePct());

  useEffect(() => {
    liveApi.hp.getTiers().then(setBackendTiers).catch(() => setBackendTiers(null));
  }, []);

  if (!hpBalance) return <HpEducationSkeleton />;

  const tierInfo = getTierProgress(hpBalance.hp_earned_120day);
  const tierList = (Array.isArray(backendTiers) ? [...backendTiers] : [])
    .sort((a, b) => (a.sort_order ?? a.min_points ?? 0) - (b.sort_order ?? b.min_points ?? 0))
    .filter((t) => t.is_active !== false);

  const FAQ = [
    { q: 'What is the difference between Active and Pending HP?', a: 'Pending is on its way. It becomes Active once your order is delivered, and Active is what you can spend.' },
    { q: 'Do my Holy Points expire?', a: 'Keep showing up and they stay with you. Go quiet for a long stretch and they slowly fade 😉.' },
    { q: 'How do tiers and multipliers work?', a: 'You climb from Ember to Flame to Blaze to Holy. Each tier makes your points work harder. Stay active to keep your tier.' },
    { q: 'Where do I spend my HP?', a: 'On event tickets, rewards, and challenges with exclusive prizes. The Marketplace joins the list soon.' },
  ];

  return (
    <div className="space-y-5 animate-fade-in">
      <div>
        <span className="hg-eyebrow">How HP work</span>
        <h1 className="font-heading font-bold text-xl text-foreground mt-0.5 flex items-center gap-1.5">Show up. Get rewarded ❤️‍🔥</h1>
        <p className="text-sm text-muted-foreground mt-1">Everything HP does, one page.</p>
      </div>

      <HpDisplay hpBalance={hpBalance} />

      {hpTransferEnabled && (
        <button onClick={() => setShowTransfer(true)} className="w-full rounded-2xl bg-white border border-border p-4 flex items-center gap-3 hover:shadow-card transition-all text-left">
          <div className="w-10 h-10 shrink-0 rounded-full bg-accent/15 flex items-center justify-center">
            <Send className="w-5 h-5 text-primary" />
          </div>
          <div className="flex-1">
            <div className="font-heading font-bold text-sm text-foreground">Send HP to a friend</div>
            <p className="text-xs text-muted-foreground">To a fellow student.</p>
          </div>
          <ChevronRight className="w-4 h-4 text-muted-foreground" />
        </button>
      )}

      <section className="rounded-2xl bg-white border border-border p-4 space-y-2 shadow-card">
        <span className="text-[10px] font-bold uppercase tracking-wider text-primary">The basics</span>
        <h2 className="font-heading font-bold text-lg text-foreground">What are Holy Points?</h2>
        <p className="text-sm text-muted-foreground leading-relaxed">
          Our thank you for showing up. Earn it at the table. Spend it across Holy Grills.
        </p>
      </section>

      <section className="space-y-3">
        <h2 className="font-heading font-bold text-lg text-foreground">How you earn</h2>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          {EARN_WAYS.map((w) => (
            <Link key={w.title} to={w.to} className="rounded-2xl bg-white border border-border p-4 flex gap-3 items-start hover:shadow-card transition-all">
              <div className="w-10 h-10 shrink-0 rounded-full bg-primary/5 flex items-center justify-center">
                <w.icon className="w-5 h-5 text-primary" />
              </div>
              <div className="flex-1">
                <div className="font-heading font-bold text-sm text-foreground">{w.title}</div>
                <p className="text-xs text-muted-foreground mt-1">{w.body}</p>
              </div>
              <ChevronRight className="w-4 h-4 text-muted-foreground self-center" />
            </Link>
          ))}
        </div>
      </section>

      <section className="space-y-3">
        <div className="flex items-center justify-between">
          <h2 className="font-heading font-bold text-lg text-foreground">Tiers &amp; multipliers</h2>
          {tierInfo.next && (
            <span className="text-xs text-muted-foreground font-semibold">{tierInfo.remaining} HP to {tierInfo.next.name}</span>
          )}
        </div>
        <div className="space-y-2.5">
          {tierList.map((tier) => {
            const slug = tier.slug || tier.id;
            const isCurrent = tierInfo.current.id === tier.id || tierInfo.current.slug === slug;
            const isPassed = (hpBalance.hp_earned_120day || 0) >= (tier.min_points || 0);
            const multiplier = tier.earn_multiplier ?? tier.earn_multiplier_snapshot ?? 1;
            return (
              <div
                key={tier.id || slug}
                className={`rounded-2xl bg-white border p-4 flex items-center gap-3 shadow-card transition-all ${isCurrent ? 'border-primary/30 ring-2 ring-primary/20' : 'border-border'}`}
              >
                <TierIcon slug={slug} tier={tier} className="w-8 h-8 text-2xl shrink-0" />
                <div className="flex-1 min-w-0">
                  <div className="font-heading font-bold text-sm text-foreground">{tier.name}</div>
                  <div className="text-xs text-muted-foreground">{(tier.min_points || 0).toLocaleString()} HP earned in 120 days</div>
                </div>
                <div className="text-right shrink-0">
                  <div className="font-heading font-bold text-primary tabular-nums">{Number(multiplier).toFixed(2)}×</div>
                  <div className="text-[10px] text-muted-foreground uppercase tracking-wide">earn rate</div>
                </div>
                {isPassed ? (
                  <Flame className="w-5 h-5 text-primary shrink-0" />
                ) : (
                  <Lock className="w-5 h-5 text-muted-foreground shrink-0" />
                )}
              </div>
            );
          })}
        </div>
      </section>

      <Link to="/rewards" className="rounded-2xl bg-white border border-border p-4 flex items-center gap-3 hover:shadow-card transition-all">
        <div className="w-10 h-10 shrink-0 rounded-full bg-accent/15 flex items-center justify-center">
          <Gift className="w-5 h-5 text-accent" />
        </div>
        <div className="flex-1">
          <div className="font-heading font-bold text-sm text-foreground">Spend your HP</div>
          <p className="text-xs text-muted-foreground">Tickets, rewards, challenges.</p>
        </div>
        <ChevronRight className="w-5 h-5 text-muted-foreground" />
      </Link>

      <HpHistoryLedger />

      <section className="space-y-3">
        <div className="flex items-center gap-2">
          <HelpCircle className="w-5 h-5 text-primary" />
          <h2 className="font-heading font-bold text-lg text-foreground">Questions</h2>
        </div>
        <div className="space-y-2.5">
          {FAQ.map((item, i) => (
            <details key={i} className="group rounded-2xl bg-white border border-border p-4 shadow-card cursor-pointer">
              <summary className="flex items-center justify-between font-heading font-bold text-sm text-foreground list-none">
                {item.q}
                <ChevronRight className="w-4 h-4 text-muted-foreground transition-transform group-open:rotate-90 shrink-0" />
              </summary>
              <p className="text-sm text-muted-foreground mt-2 leading-relaxed">{item.a}</p>
            </details>
          ))}
        </div>
      </section>

      <HpTransferModal open={showTransfer} onClose={() => setShowTransfer(false)} />
    </div>
  );
}