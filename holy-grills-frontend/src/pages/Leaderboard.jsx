import React, { useState, useEffect, useRef } from 'react';
import { Link } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import { Crown, Flame, Users, TrendingUp, ArrowUp, ArrowDown, Minus, Clock, Info, X, Trophy, ChevronRight } from 'lucide-react';
import { liveApi } from '@/lib/liveApi';
import { useHolyGrill } from '@/lib/HolyGrillContext';
import { isFeatureEnabled } from '@/lib/featureConfig';
import LeaderboardSkeleton from '@/components/skeletons/LeaderboardSkeleton';
import SpinWheel from '@/components/SpinWheel';
import LeaderboardPrizeBadge from '@/components/LeaderboardPrizeBadge';
import CountUp from '@/components/CountUp';
import MascotStandee from '@/components/mascot/MascotStandee';
import ModalPortal from '@/components/ModalPortal';
import TierIcon from '@/components/TierIcon';
import { triggerMascotCelebration } from '@/lib/mascots';

const VIEWS = [{ id: 'user', label: 'Solo' }, { id: 'squad', label: 'Squad' }];
const PERIODS = [
  { id: 'weekly', label: 'This Week' },
  { id: 'monthly', label: 'This Month' },
  { id: 'all_time', label: 'All time' },
];

const getWeeklyCountdown = () => {
  const now = new Date();
  const next = new Date(now);
  const day = now.getDay();
  const daysUntil = day === 0 ? 0 : 7 - day;
  next.setDate(now.getDate() + daysUntil);
  next.setHours(23, 59, 59, 0);
  let diff = next - now;
  if (diff < 0) diff = 0;
  const days = Math.floor(diff / (1000 * 60 * 60 * 24));
  const hours = Math.floor((diff % (1000 * 60 * 60 * 24)) / (1000 * 60 * 60));
  return { days, hours };
};

function RankChange({ change }) {
  if (!change || change === 0) return <Minus className="w-3 h-3 text-muted-foreground" />;
  return change > 0 ? (
    <span className="flex items-center gap-0.5 text-emerald-600 text-[10px] font-bold"><ArrowUp className="w-3 h-3" />{change}</span>
  ) : (
    <span className="flex items-center gap-0.5 text-muted-foreground text-[10px] font-bold"><ArrowDown className="w-3 h-3" />{Math.abs(change)}</span>
  );
}

export default function Leaderboard() {
  const { hpBalance, user } = useHolyGrill();
  const [view, setView] = useState('user');
  const [period, setPeriod] = useState('monthly');
  const [rankings, setRankings] = useState([]);
  const [myRank, setMyRank] = useState(null);
  const [squadRankings, setSquadRankings] = useState([]);
  const [hallOfFame, setHallOfFame] = useState([]);
  const [loading, setLoading] = useState(true);
  const [countdown, setCountdown] = useState(getWeeklyCountdown());
  const [showSpinModal, setShowSpinModal] = useState(false);
  const [hasSpun, setHasSpun] = useState(false);
  const [showPrizesModal, setShowPrizesModal] = useState(false);
  const [error, setError] = useState(null);
  const [hpTiers, setHpTiers] = useState([]);

  useEffect(() => {
    liveApi.hp.getTiers().then((t) => setHpTiers(Array.isArray(t) ? t : []))
      .catch(() => { /* keep empty — icon falls back to 🔥 */ });
    const t = setInterval(() => setCountdown(getWeeklyCountdown()), 60000);
    return () => clearInterval(t);
  }, []);

  useEffect(() => {
    const load = async () => {
      setLoading(true);
      setError(null);
      const [lb, my, squad, hof] = await Promise.allSettled([
        liveApi.leaderboard.get({ period_type: period }),
        liveApi.leaderboard.getMyRank({ period_type: period }),
        liveApi.leaderboard.getSquad({ period_type: period }),
        liveApi.leaderboard.getHallOfFame(),
      ]);
      const lbRes = lb.status === 'fulfilled' ? lb.value : null;
      setRankings(lbRes?.rankings || (Array.isArray(lbRes) ? lbRes : []));
      setMyRank(my.status === 'fulfilled' ? (my.value?.rank_entry || my.value) : null);
      const sqRes = squad.status === 'fulfilled' ? squad.value : null;
      setSquadRankings(sqRes?.rankings || (Array.isArray(sqRes) ? sqRes : []));
      const hofRes = hof.status === 'fulfilled' ? hof.value : null;
      setHallOfFame(hofRes?.inductees || hofRes?.monthly_winners || (Array.isArray(hofRes) ? hofRes : []));
      if (lb.status === 'rejected' && my.status === 'rejected') setError('Something slipped. Try again.');
      setLoading(false);
    };
    load();
  }, [period]);

  // Tier marks are backend-driven — TierIcon resolves the admin-uploaded art
  // for a tier slug, falling back to the tier's emoji.
  const findTier = (tierSlug) =>
    hpTiers.find((t) => t.slug === tierSlug || t.id === tierSlug) || null;

  const prevRankRef = useRef(null);
  useEffect(() => {
    if (myRank && prevRankRef.current != null && myRank.rank < prevRankRef.current) {
      triggerMascotCelebration('hips');
    }
    if (myRank) prevRankRef.current = myRank.rank;
  }, [myRank]);

  if (loading) return <LeaderboardSkeleton />;

  const ahead = myRank ? rankings.find((r) => r.rank === myRank.rank - 1) : null;
  const diff = ahead && myRank ? ahead.hp_total - myRank.hp_total : 0;
  const spinEarned = myRank && myRank.rank <= 10;

  return (
    <div className="space-y-5 animate-fade-in">
      <div className="flex items-start justify-between gap-3">
        <div>
          <span className="hg-eyebrow">Who is showing up</span>
          <h1 className="font-heading font-bold text-xl text-foreground mt-0.5 flex items-center gap-1.5">Leaderboard 🏆</h1>
          <p className="text-sm text-muted-foreground mt-1">Top spots win real rewards.</p>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          {period === 'weekly' && (
            <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-primary/5 border border-primary/20">
              <Clock className="w-3.5 h-3.5 text-primary" />
              <span className="text-[10px] font-bold text-primary">Resets in {countdown.days}d {countdown.hours}h</span>
            </div>
          )}
          <button onClick={() => setShowPrizesModal(true)} className="flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-secondary text-foreground text-[10px] font-bold">
            <Info className="w-3.5 h-3.5" /> Prizes
          </button>
        </div>
      </div>

      {error && (
        <div className="rounded-2xl bg-red-50 border border-red-200 p-4 flex items-center justify-between gap-3">
          <span className="text-sm text-red-600 font-medium">{error}</span>
          <button onClick={() => setPeriod(period)} className="px-3 py-1.5 rounded-xl bg-red-600 text-white text-xs font-bold">Retry</button>
        </div>
      )}

      {/* Pinned user rank */}
      {myRank && (
        <div className="sticky top-16 z-20 rounded-2xl bg-gradient-dark p-3 text-white shadow-glow">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <div className="w-9 h-9 rounded-full bg-gradient-cta flex items-center justify-center font-bold text-sm">#{<CountUp value={myRank.rank} />}</div>
              <div>
                <div className="text-xs font-semibold">{user?.full_name?.split(' ')[0] || 'You'}</div>
                <div className="text-[10px] text-white/60 tabular-nums"><CountUp value={myRank.hp_total} /> HP this {period === 'weekly' ? 'week' : period === 'monthly' ? 'month' : 'season'}</div>
              </div>
            </div>
            <div className="text-right">
              <TierIcon slug={hpBalance?.tier?.slug} tier={findTier(hpBalance?.tier?.slug)} className="w-6 h-6 text-lg ml-auto" />
              {diff > 0 && <div className="text-[10px] text-white/60">{diff} HP to #{myRank.rank - 1}</div>}
            </div>
          </div>
        </div>
      )}

      {/* User/Squad toggle */}
      <div className="relative flex bg-secondary rounded-full p-1 w-full">
        {VIEWS.map((v) => (
          <button key={v.id} onClick={() => setView(v.id)} className={`flex-1 py-2 rounded-full text-xs font-bold transition-all ${view === v.id ? 'bg-gradient-cta text-white shadow-glow' : 'text-foreground'}`}>
            {v.label}
          </button>
        ))}
      </div>

      {view !== 'squad' && (
        <div className="grid grid-cols-3 gap-2">
          {PERIODS.map((p) => (
            <button key={p.id} onClick={() => setPeriod(p.id)} className={`px-4 py-2 rounded-xl text-xs font-semibold transition-all ${period === p.id ? 'bg-primary text-white' : 'bg-white text-foreground border border-border'}`}>
              {p.label}
            </button>
          ))}
        </div>
      )}

      <AnimatePresence mode="wait">
        <motion.div key={view + period} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -8 }} transition={{ duration: 0.2 }}>
          {view === 'user' && (
            <>
              {hallOfFame.length > 0 && (
                <Link to="/hall-of-fame" className="block mb-4 group">
                  <div className="relative rounded-2xl bg-accent/10 border border-accent/30 p-4 overflow-hidden shadow-glow transition-transform group-hover:scale-[1.01]">
                    <Crown className="absolute -right-3 -top-3 w-16 h-16 text-accent/20" />
                    <div className="relative flex items-center gap-3">
                      <div className="w-12 h-12 rounded-full bg-accent flex items-center justify-center shrink-0 ring-2 ring-accent/40 shadow-md">
                        <Crown className="w-6 h-6 text-white" />
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="text-[10px] font-extrabold uppercase tracking-wider text-amber-600">Hall of Fame</div>
                        <div className="font-heading font-extrabold text-base text-foreground truncate">
                          {hallOfFame[0].winner?.full_name || hallOfFame[0].full_name}
                        </div>
                        <div className="text-xs text-muted-foreground">
                          Month after month at the top.
                        </div>
                      </div>
                      <ChevronRight className="w-5 h-5 text-amber-600 shrink-0" />
                    </div>
                  </div>
                </Link>
              )}

              {rankings.length >= 3 && (
                <div className="flex items-end justify-center gap-2 py-4 mb-4">
                  <PodiumBar rank={rankings[1]} place={2} height={96} delay={0.15} />
                  <PodiumBar rank={rankings[0]} place={1} height={128} delay={0} />
                  <PodiumBar rank={rankings[2]} place={3} height={80} delay={0.3} />
                </div>
              )}

              {/* Spin card */}
              <div className={`rounded-2xl border p-4 mb-4 shadow-card ${spinEarned && !hasSpun ? 'bg-accent/15 border-accent/30' : 'bg-white border-border'}`}>
                <div className="flex items-center gap-3">
                  <div className={`w-10 h-10 rounded-full flex items-center justify-center text-xl shrink-0 ${spinEarned && !hasSpun ? 'bg-primary' : 'bg-secondary'}`}>🎡</div>
                  <div className="flex-1">
                    {spinEarned && !hasSpun ? (
                      <><div className="font-heading font-bold text-sm text-foreground">Free Spin Earned! 🎉</div><div className="text-xs text-muted-foreground">Spin to win bonus HP.</div></>
                    ) : spinEarned && hasSpun ? (
                      <><div className="font-heading font-bold text-sm text-foreground">Spin Used</div><div className="text-xs text-muted-foreground">Come back next month for another shot.</div></>
                    ) : (
                      <><div className="font-heading font-bold text-sm text-muted-foreground">Spin Locked</div><div className="text-xs text-muted-foreground">Climb the ranks.</div></>
                    )}
                  </div>
                  <button onClick={() => spinEarned && !hasSpun && setShowSpinModal(true)} disabled={!spinEarned || hasSpun} className={`px-4 py-2 rounded-full text-xs font-bold transition-all shrink-0 ${spinEarned && !hasSpun ? 'bg-gradient-cta text-white active:scale-95' : 'bg-secondary text-muted-foreground cursor-not-allowed'}`}>
                    {hasSpun ? 'Used' : 'Spin'}
                  </button>
                </div>
              </div>

              <div className="space-y-2">
                {rankings.length === 0 && (
                  <div className="text-center py-12 rounded-2xl border-2 border-dashed border-border">
                    <MascotStandee mascot="thinking" className="w-28 h-28 mx-auto mb-2" alt="Leaderboard resetting" />
                    <p className="text-sm text-muted-foreground">No rankings yet.</p>
                  </div>
                )}
                {rankings.map((entry, i) => (
                  <motion.div
                    key={entry.user_id || i}
                    initial={{ opacity: 0, x: -10 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{ delay: i * 0.04, duration: 0.3 }}
                    className={`flex items-center gap-3 p-3 rounded-2xl border shadow-card ${entry.is_current_user ? 'bg-primary/5 border-primary/30 ring-2 ring-primary/40' : 'bg-white border-border'}`}
                  >
                    <div className={`w-8 h-8 rounded-full flex items-center justify-center font-semibold text-xs tabular-nums ${entry.rank <= 3 ? 'bg-gradient-cta text-white' : 'bg-secondary text-foreground'}`}>{entry.rank}</div>
                    {isFeatureEnabled('leaderboard_prizes', true) && (
                      <LeaderboardPrizeBadge rank={entry.rank} />
                    )}
                    <TierIcon slug={entry.tier} tier={findTier(entry.tier)} className="w-5 h-5 text-sm shrink-0" />
                    <div className="flex-1 min-w-0">
                      <div className={`font-semibold text-sm truncate ${entry.is_current_user ? 'text-primary' : 'text-foreground'}`}>{entry.full_name}{entry.is_current_user && ' (You)'}</div>
                    </div>
                    <RankChange change={entry.rank_change} />
                    <div className="flex items-center gap-1 shrink-0">
                      <Flame className="w-3.5 h-3.5 text-primary" />
                      <span className="font-semibold text-foreground tabular-nums">{entry.hp_total}</span>
                    </div>
                  </motion.div>
                ))}
              </div>
            </>
          )}

          {view === 'squad' && (
            <>
              <div className="flex items-center gap-2 text-xs text-muted-foreground mb-3">
                <Users className="w-4 h-4 text-primary" />
                Your people. One board.
              </div>
              {squadRankings.length === 0 ? (
                <div className="text-center py-12">
                  <MascotStandee mascot="peace" className="w-28 h-28 mx-auto mb-2" alt="No squad rankings yet" />
                  <p className="text-sm font-semibold text-foreground">No squad rankings yet.</p>
                  <Link to="/squads" className="inline-block mt-4 px-5 py-2.5 rounded-full bg-gradient-cta text-white text-xs font-bold">Manage your squads</Link>
                </div>
              ) : (
                <div className="space-y-2">
                  {squadRankings.map((squad, i) => (
                    <motion.div
                      key={squad.rank || i}
                      initial={{ opacity: 0, x: -10 }}
                      animate={{ opacity: 1, x: 0 }}
                      transition={{ delay: i * 0.04, duration: 0.3 }}
                      className="flex items-center gap-3 p-3 rounded-2xl bg-white border border-border shadow-card"
                    >
                      <div className={`w-8 h-8 rounded-full flex items-center justify-center font-semibold text-xs tabular-nums ${squad.rank <= 3 ? 'bg-gradient-cta text-white' : 'bg-secondary text-foreground'}`}>{squad.rank}</div>
                      <div className="flex-1 min-w-0">
                        <div className="font-semibold text-sm text-foreground truncate">{squad.squad_name}</div>
                        <div className="text-[11px] text-muted-foreground truncate">
                          {squad.organizer_name
                            ? `Organized by ${squad.organizer_name}`
                            : `${squad.squad_size ?? squad.member_count ?? '—'} members · ${squad.squad_order_count ?? 0} orders`}
                        </div>
                      </div>
                      <div className="flex items-center gap-1 shrink-0">
                        <Flame className="w-3.5 h-3.5 text-primary" />
                        <span className="font-semibold text-foreground tabular-nums">{squad.hp_total ?? squad.total_hp}</span>
                      </div>
                    </motion.div>
                  ))}
                </div>
              )}
            </>
          )}
        </motion.div>
      </AnimatePresence>

      <SpinWheel open={showSpinModal} onClose={() => setShowSpinModal(false)} onResult={() => setHasSpun(true)} canSpin={spinEarned && !hasSpun} />

      {/* How Prizes Work modal — portalled to <body> so its dimmed backdrop
          covers the whole viewport. Inside the animated page wrapper, `fixed`
          was clipped to that wrapper, letting page light leak through above
          and below the sheet. */}
      {showPrizesModal && (
        <ModalPortal>
        <div className="fixed inset-0 z-50 bg-black/60 backdrop-blur-md flex items-center justify-center p-4" onClick={() => setShowPrizesModal(false)}>
          <div className="bg-white rounded-3xl p-6 w-full max-w-sm animate-slide-up" onClick={(e) => e.stopPropagation()}>
            <div className="flex justify-between items-start mb-4">
              <h3 className="font-heading font-bold text-lg text-foreground">How Prizes Work 🏆</h3>
              <button onClick={() => setShowPrizesModal(false)}><X className="w-5 h-5 text-muted-foreground" /></button>
            </div>
            <div className="space-y-3 text-sm">
              <div className="flex gap-3">
                <span className="text-2xl shrink-0">🥇</span>
                <div>
                  <div className="font-bold text-foreground">Rank #1</div>
                  <p className="text-xs text-muted-foreground">Recognised and rewarded.</p>
                </div>
              </div>
              <div className="flex gap-3">
                <span className="text-2xl shrink-0">⭐</span>
                <div>
                  <div className="font-bold text-foreground">Top ranks</div>
                  <p className="text-xs text-muted-foreground">Free sides and a spin.</p>
                </div>
              </div>
              <div className="flex gap-3">
                <span className="text-2xl shrink-0">📅</span>
                <div>
                  <div className="font-bold text-foreground">Monthly Reset</div>
                  <p className="text-xs text-muted-foreground">A fresh start every month.</p>
                </div>
              </div>
              <div className="flex gap-3">
                <span className="text-2xl shrink-0">🏅</span>
                <div>
                  <div className="font-bold text-foreground">Hall of Fame</div>
                  <p className="text-xs text-muted-foreground">Stay on top, month after month.</p>
                </div>
              </div>
            </div>
            <button onClick={() => setShowPrizesModal(false)} className="w-full mt-4 py-3 rounded-full bg-primary text-white font-bold text-sm">Got it</button>
          </div>
        </div>
        </ModalPortal>
      )}
    </div>
  );
}

function PodiumBar({ rank, place, height, delay }) {
  const colors = ['bg-accent', 'bg-muted-foreground/40', 'bg-accent/70'];
  return (
    <div className="flex flex-col items-center" style={{ order: place === 1 ? 1 : place === 2 ? 0 : 2 }}>
      <div className="text-xs font-semibold text-foreground text-center max-w-[80px] truncate">{rank.full_name}</div>
      <div className="flex items-center gap-0.5 text-xs text-primary font-semibold mb-1 tabular-nums"><Flame className="w-3 h-3" />{rank.hp_total}</div>
      <motion.div
        initial={{ height: 0, opacity: 0 }}
        animate={{ height, opacity: 1 }}
        transition={{ delay, duration: 0.6, ease: [0.34, 1.56, 0.64, 1] }}
        className={`w-16 rounded-t-xl ${colors[place - 1]} flex items-start justify-center pt-2 overflow-hidden`}
      >
        <span className="text-white font-bold text-lg">#{place}</span>
      </motion.div>
    </div>
  );
}