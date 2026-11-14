import { motion } from 'framer-motion';
import { Flame, Check, Lock } from 'lucide-react';

// The 6 live production referral-milestone tiers (confirmed in Supabase via
// milestones rows, trigger_type='referral_count'). No student-facing endpoint
// exposes them, so they are kept as the documented live constants. The
// 75-referral tier awards less HP than the 50-referral tier by design.
export const MILESTONES = [
  { count: 5, hp: 150 },
  { count: 10, hp: 400 },
  { count: 20, hp: 750 },
  { count: 30, hp: 1200 },
  { count: 50, hp: 2500 },
  { count: 75, hp: 1500 },
];

// Progress toward the next unreached tier, rendered as a slim bar above the list.
function NextTierProgress({ referredCount }) {
  const next = MILESTONES.find((m) => referredCount < m.count);
  if (!next) {
    return (
      <div className="rounded-2xl bg-gradient-gold border border-accent/30 p-4 text-center">
        <div className="font-heading font-extrabold text-brand-brown text-sm">All tiers unlocked 👑</div>
        <div className="text-[11px] text-brand-brown/70 mt-0.5">You've conquered every referral milestone.</div>
      </div>
    );
  }
  const prev = [...MILESTONES].reverse().find((m) => m.count <= referredCount);
  const base = prev ? prev.count : 0;
  const span = next.count - base;
  const done = referredCount - base;
  const pct = Math.min(100, Math.max(4, (done / span) * 100));
  return (
    <div className="rounded-2xl bg-card border border-border p-4">
      <div className="flex items-center justify-between mb-2">
        <div className="text-xs font-bold text-foreground">Next tier</div>
        <div className="text-[11px] font-bold text-primary">{next.count} referrals</div>
      </div>
      <div className="h-2.5 rounded-full bg-secondary overflow-hidden">
        <motion.div
          initial={{ width: 0 }}
          animate={{ width: `${pct}%` }}
          transition={{ type: 'spring', stiffness: 120, damping: 20 }}
          className="h-full rounded-full bg-gradient-cta"
        />
      </div>
      <div className="flex items-center justify-between mt-1.5">
        <span className="text-[11px] text-muted-foreground">{referredCount} so far</span>
        <span className="text-[11px] font-bold text-accent-foreground flex items-center gap-1">
          <Flame className="w-3 h-3 text-primary" /> +{next.hp} HP
        </span>
      </div>
    </div>
  );
}

export default function ReferralMilestones({ referredCount = 0 }) {
  return (
    <section className="space-y-3">
      <div className="flex items-center justify-between">
        <h2 className="font-heading font-extrabold text-base text-foreground">Milestone rewards</h2>
        <span className="text-[11px] text-muted-foreground">{referredCount} referred</span>
      </div>

      <NextTierProgress referredCount={referredCount} />

      <div className="space-y-2">
        {MILESTONES.map((m, i) => {
          const reached = referredCount >= m.count;
          return (
            <motion.div
              key={m.count}
              initial={{ opacity: 0, x: -8 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ delay: i * 0.04 }}
              className={`flex items-center gap-3 p-3 rounded-2xl border ${
                reached ? 'bg-success/10 border-success/25' : 'bg-card border-border'
              }`}
            >
              <div
                className={`w-9 h-9 rounded-xl flex items-center justify-center flex-shrink-0 ${
                  reached ? 'bg-success text-white' : 'bg-secondary text-muted-foreground'
                }`}
              >
                {reached ? <Check className="w-5 h-5" /> : <Lock className="w-4 h-4" />}
              </div>
              <div className="flex-1 min-w-0">
                <div className="font-bold text-sm text-foreground">{m.count} friends referred</div>
                <div className="text-[11px] text-muted-foreground">
                  {reached ? 'Unlocked' : `Earn ${m.hp} HP bonus`}
                </div>
              </div>
              <span
                className={`flex items-center gap-1 text-xs font-extrabold px-2.5 py-1 rounded-full ${
                  reached ? 'text-success bg-success/10' : 'text-muted-foreground bg-secondary'
                }`}
              >
                <Flame className="w-3 h-3" /> {m.hp}
              </span>
            </motion.div>
          );
        })}
      </div>
    </section>
  );
}