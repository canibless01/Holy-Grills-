import React from 'react';
import { motion } from 'framer-motion';
import { Users, Flame, UserCheck } from 'lucide-react';
import type { ReferralStats as ReferralStatsData } from '@/types/referrals';

// Three compact stat tiles. Every value comes from the backend stats response
// (or the auth profile as a fallback) — nothing is computed/fabricated.
const TILES = [
  { key: 'invited', label: 'Invited', icon: Users, accent: 'text-primary' },
  { key: 'active', label: 'Active', icon: UserCheck, accent: 'text-success' },
  { key: 'hp', label: 'HP earned', icon: Flame, accent: 'text-accent-foreground' },
];

export default function ReferralStats({
  stats = {} as ReferralStatsData,
  loading,
}: {
  stats?: ReferralStatsData;
  loading?: boolean;
}) {
  const values = {
    invited: stats.total_invited ?? stats.total_referrals ?? stats.referral_count ?? stats.invited ?? 0,
    active: stats.active_friends ?? stats.completed ?? stats.active ?? 0,
    hp: stats.total_hp_earned ?? stats.hp_earned ?? 0,
  };

  return (
    <div className="grid grid-cols-3 gap-2.5">
      {TILES.map((t, i) => {
        const Icon = t.icon;
        return (
          <motion.div
            key={t.key}
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: i * 0.05 }}
            className="rounded-2xl bg-card border border-border p-3 text-center"
          >
            <Icon className={`w-5 h-5 mx-auto mb-1 ${t.accent}`} />
            {loading ? (
              <div className="h-6 w-10 mx-auto rounded bg-secondary animate-pulse" />
            ) : (
              <div className="font-heading font-extrabold text-xl text-foreground leading-none">
                {values[t.key]}
              </div>
            )}
            <div className="text-[10px] text-muted-foreground mt-1">{t.label}</div>
          </motion.div>
        );
      })}
    </div>
  );
}