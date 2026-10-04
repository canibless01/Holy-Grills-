import { useState, useEffect } from 'react';
import { Flame, Lock, Gift, Target, X, Check, History, GraduationCap, Sparkles, Crown, Zap, Clock, ChevronRight, Award, Download } from 'lucide-react';
import { Link, useNavigate } from 'react-router-dom';
import { liveApi } from '@/lib/liveApi';
import { useHolyGrill } from '@/lib/HolyGrillContext';
import { getTierProgress, getTierProgressGradient, getTierOverallProgress } from '@/lib/hgUtils';
import TierIcon from '@/components/TierIcon';
import { getStreakRewardHp } from '@/lib/featureConfig';
import { graduationHp, lowCodeInventoryThreshold, freeSideCreditsValidityDays } from '@/lib/appConfig';
import { expiryLabel } from '@/lib/rewardUtils';
import { toast } from '@/components/ui/use-toast';
import RewardsSkeleton from '@/components/skeletons/RewardsSkeleton';
import SpinWheel from '@/components/SpinWheel';
import RewardDeliveryModal from '@/components/RewardDeliveryModal';
import InstallPushBonuses from '@/components/challenges/InstallPushBonuses';
import SocialFollowChallenge from '@/components/challenges/SocialFollowChallenge';
import MascotStandee from '@/components/mascot/MascotStandee';
import { triggerMascotCelebration } from '@/lib/mascots';

const CATEGORY_LABELS = { food: 'Food', discount: 'Wallet', experience: 'Experience' };

const normFlash = (r) => {
  const active = !!(r.is_flash_active ?? r.flash_active ?? r.is_flash ?? r.flash_sale_active ?? r.flash?.active);
  if (!active) return null;
  const f = r.flash || {};
  const hpCost = r.flash_hp_cost ?? r.flash_price ?? f.hp_cost ?? f.price;
  const normalHpCost = r.hp_cost ?? r.normal_hp_cost ?? f.normal_hp_cost;
  return {
    active, hpCost, normalHpCost,
    startsAt: r.flash_window_starts_at ?? r.flash_starts_at ?? f.starts_at ?? f.window_starts_at,
    endsAt: r.flash_window_ends_at ?? r.flash_ends_at ?? f.ends_at ?? f.window_ends_at,
    slotsRemaining: r.flash_slots_remaining ?? r.flash_slots_left ?? f.slots_remaining ?? f.slots_left,
    maxQty: r.flash_max_qty ?? r.flash_slots ?? f.max_qty ?? f.slots,
  };
};

const formatCountdown = (endsAt) => {
  if (!endsAt) return null;
  const ms = new Date(endsAt).getTime() - Date.now();
  if (ms <= 0) return 'Ended';
  const mins = Math.floor(ms / 60000);
  const h = Math.floor(mins / 60);
  const m = mins % 60;
  if (h > 24) return `${Math.ceil(h / 24)}d left`;
  if (h > 0) return `${h}h ${m}m left`;
  return `${m}m left`;
};

// TODO(ts): challenge rows are read with legacy aliases (hp_awarded/hp_award,
// trigger_value/target_count) — consolidate against src/types/challenges.ts
// before narrowing these to Challenge[].
interface ChallengesEnvelope {
  badges?: any[];
  challenges_available?: any[];
  challenges_completed?: any[];
}

export default function Rewards() {
  const { hpBalance, refreshHp, streak, user } = useHolyGrill();
  const navigate = useNavigate();
  const [tab, setTab] = useState('redeem');
  const [rewards, setRewards] = useState([]);
  const [redemptions, setRedemptions] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selectedReward, setSelectedReward] = useState(null);
  const [redeeming, setRedeeming] = useState(false);
  // GET /challenges/my returns an envelope ({ badges, challenges_available,
  // challenges_completed }) — the page reads it with `?.`, so null is a safe
  // initial value and matches the pre-API render.
  const [challenges, setChallenges] = useState<ChallengesEnvelope | null>(null);
  const [spinHistory, setSpinHistory] = useState([]);
  const [unlockHistory, setUnlockHistory] = useState([]);
  const [completing, setCompleting] = useState(null);
  const [gradClaimed, setGradClaimed] = useState(false);
  const [claimingGrad, setClaimingGrad] = useState(false);
  const [freeSideCredits, setFreeSideCredits] = useState({ count: 0, expires_at: null });
  const [exclusiveStatus, setExclusiveStatus] = useState(null);
  const [flashRedeeming, setFlashRedeeming] = useState(null);
  const [showSpinModal, setShowSpinModal] = useState(false);
  const [hasSpun, setHasSpun] = useState(false);
  const [deliveryRedemption, setDeliveryRedemption] = useState(null);
  const [hpTiers, setHpTiers] = useState([]);

  useEffect(() => {
    liveApi.hp.getTiers().then((t) => setHpTiers(Array.isArray(t) ? t : []))
      .catch(() => { /* empty tiers — backend unavailable */ });
    const load = async () => {
      try {
        const [r, myChallenges, fsc, exStatus] = await Promise.all([
          liveApi.rewards.list(),
          liveApi.challenges.my().catch(() => ({ badges: [], challenges_available: [], challenges_completed: [] })),
          liveApi.rewards.getFreeSideCredits().catch(() => ({ count: 0, expires_at: null })),
          liveApi.hp.getExclusiveSpinStatus().catch(() => null),
        ]);
        setRewards(r);
        setChallenges(myChallenges);
        setFreeSideCredits(fsc);
        setExclusiveStatus(exStatus);
      } catch (e) { console.error(e); }
      setLoading(false);
    };
    load();
  }, []);

  // Graduation "already claimed" comes from the profile (graduation_claimed),
  // not a status probe — the backend exposes no /graduation/status route.
  useEffect(() => {
    if (user?.profile?.graduation_claimed) setGradClaimed(true);
  }, [user]);

  const loadRedemptions = async () => {
    try {
      const r = await liveApi.rewards.getRedemptions();
      setRedemptions(Array.isArray(r) ? r : (r?.redemptions || []));
    } catch (e) { /* ignore */ }
  };

  const loadHistory = async () => {
    try {
      // /hp/spin/history is not a backend route — only unlock history exists.
      const unlocks = await liveApi.hp.getUnlockHistory({ limit: 20 }).catch(() => []);
      setSpinHistory([]);
      setUnlockHistory(unlocks);
    } catch (e) { /* ignore */ }
  };

  useEffect(() => {
    if (tab === 'history') loadHistory();
    if (tab === 'redeemed') loadRedemptions();
  }, [tab]);

  const handleFlashRedeem = async (reward) => {
    setFlashRedeeming(reward.id);
    try {
      await liveApi.hp.flashRedeem(reward.id);
      await refreshHp();
      toast({ title: '⚡ Flash reward redeemed!', description: `${reward.name} unlocked at flash price.` });
      const r = await liveApi.rewards.list();
      setRewards(r);
    } catch (e) {
      toast({ title: 'Flash redemption failed', description: e.message, variant: 'destructive' });
    }
    setFlashRedeeming(null);
  };

  const handleGraduationClaim = async () => {
    setClaimingGrad(true);
    try {
      const res = await liveApi.graduation.claim({});
      await refreshHp();
      toast({ title: '🎓 Graduation HP claimed!', description: `${res?.hp_awarded ?? graduationHp()} HP awarded at level ${res?.academic_level ?? ''}.`.trim() });
      setGradClaimed(true);
    } catch (e) {
      toast({ title: 'Claim failed', description: e.message, variant: 'destructive' });
    }
    setClaimingGrad(false);
  };

  const handleCompleteChallenge = async (ch) => {
    setCompleting(ch.id);
    try {
      await liveApi.challenges.complete(ch.id);
      await refreshHp();
      const myChallenges = await liveApi.challenges.my().catch(() => ({ badges: [], challenges_available: [], challenges_completed: [] }));
      setChallenges(myChallenges);
      toast({ title: '🎉 Challenge complete!', description: 'Bonus HP added.' });
    } catch (e) {
      toast({ title: 'Could not complete', description: e.message, variant: 'destructive' });
    }
    setCompleting(null);
  };

  // Social-follow milestone claims through its own endpoint; this just refreshes
  // state after a successful claim (the API call lives in SocialFollowChallenge).
  const handleSocialFollowClaimed = async () => {
    await refreshHp();
    const myChallenges = await liveApi.challenges.my().catch(() => ({ badges: [], challenges_available: [], challenges_completed: [] }));
    setChallenges(myChallenges);
  };

  const handleRedeem = async () => {
    setRedeeming(true);
    try {
      await liveApi.rewards.redeem(selectedReward.id);
      await refreshHp();
      toast({ title: '🎉 Reward redeemed!', description: `${selectedReward.name} is on its way.` });
      setSelectedReward(null);
    } catch (e) {
      toast({ title: 'Redemption failed', description: e.message, variant: 'destructive' });
    }
    setRedeeming(false);
  };

  if (loading) return <RewardsSkeleton />;

  const hpActive = hpBalance?.active || 0;
  const hpPending = hpBalance?.pending || 0;
  const tierInfo = hpBalance ? getTierProgress(hpBalance.hp_earned_120day) : null;
  const spinCount = exclusiveStatus?.total_spins ?? exclusiveStatus?.spins_available ?? 0;
  // Same bar language as the dashboard: continuous fill + the tier gradient.
  const tierGradient = getTierProgressGradient(hpBalance?.hp_earned_120day ?? 0);
  const tierOverall = getTierOverallProgress(hpBalance?.hp_earned_120day ?? 0);

  const tabs = [
    { id: 'dashboard', label: 'My Rewards', icon: Sparkles },
    { id: 'redeem', label: 'Redeem', icon: Gift },
    { id: 'challenges', label: 'Challenges', icon: Target },
    { id: 'redeemed', label: 'Redeemed', icon: Download },
    { id: 'history', label: 'History', icon: History },
  ];

  return (
    <div className="space-y-5 animate-fade-in">
      {/* Page header */}
      <div>
        <span className="hg-eyebrow">Holy Points</span>
        <h1 className="font-heading font-bold text-xl text-foreground mt-0.5 flex items-center gap-1.5">Rewards 🔥</h1>
        <p className="text-sm text-muted-foreground mt-1">Free sides, spins and drops.</p>
      </div>

      {/* HP balance bar */}
      <Link to="/hp-education" className="flex items-center gap-3 rounded-2xl bg-foreground p-4 text-white active:scale-[0.99] transition-transform">
        <div className="w-10 h-10 rounded-xl bg-gradient-cta flex items-center justify-center shrink-0">
          <Flame className="w-5 h-5 text-white" />
        </div>
        <div className="flex-1 min-w-0">
          <div className="text-[10px] font-bold uppercase tracking-wide text-white/60">Holy Points</div>
          <div className="flex items-baseline gap-2">
            <span className="font-heading font-extrabold text-2xl text-white tabular-nums">{hpActive}</span>
            {hpPending > 0 && <span className="text-xs font-bold text-accent/80">+{hpPending} pending</span>}
          </div>
        </div>
        <ChevronRight className="w-4 h-4 text-white/60 shrink-0" />
      </Link>

      {/* Tier progress card with liquid-fill bar */}
      {tierInfo && (
        <div className="rounded-2xl bg-white border border-border p-4 shadow-card">
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-2">
              <TierIcon slug={tierInfo.current.slug || tierInfo.current.id} tier={tierInfo.current} className="w-7 h-7 text-2xl" />
              <div>
                <div className="font-heading font-bold text-sm text-foreground">{tierInfo.current.name} Tier</div>
                <div className="text-[11px] text-muted-foreground">{Number(tierInfo.current.earn_multiplier).toFixed(2)}× earn rate</div>
              </div>
            </div>
            {tierInfo.next && (
              <div className="text-right">
                <div className="text-[10px] text-muted-foreground uppercase font-bold tracking-wide">Next: {tierInfo.next.name}</div>
                <div className="text-xs font-bold text-primary tabular-nums">{tierInfo.remaining} HP to go</div>
              </div>
            )}
          </div>
          {tierInfo.next ? (
            <div className="relative h-3 rounded-full bg-secondary overflow-hidden">
              <div
                className="absolute inset-y-0 left-0 rounded-full transition-all duration-700 ease-out"
                style={{ width: `${tierOverall.progress}%`, background: tierGradient }}
              />
              <div className="absolute inset-0 rounded-full bg-gradient-to-r from-transparent via-white/30 to-transparent animate-pulse" style={{ width: `${tierOverall.progress}%` }} />
            </div>
          ) : (
            <div className="flex items-center gap-2 text-xs font-bold text-accent-foreground">
              <Crown className="w-4 h-4" /> Highest tier reached. You're a legend!
            </div>
          )}
        </div>
      )}

      {/* Streak progress callout */}
      {(() => {
        const cycleDays = streak?.cycle_days ?? 7;
        const currentStreak = streak?.current_streak ?? streak?.days ?? streak?.count ?? 0;
        const cycleRewardHp = getStreakRewardHp(currentStreak);
        const daysIntoCycle = currentStreak % cycleDays;
        const daysToGo = cycleDays - daysIntoCycle;
        if (daysToGo <= 0 || daysToGo === cycleDays) return null;
        return (
          <div className="rounded-2xl bg-primary/5 border border-primary/20 p-3 flex items-center gap-3">
            <div className="w-9 h-9 rounded-full bg-gradient-cta flex items-center justify-center shrink-0">
              <Flame className="w-4 h-4 text-white" />
            </div>
            <div className="flex-1 text-xs text-foreground">
              <span className="font-bold text-primary">{daysToGo} day{daysToGo !== 1 ? 's' : ''} to go</span>
              <span className="text-muted-foreground"> for your {cycleRewardHp} HP streak reward.</span>
            </div>
            <Link to="/streak" className="text-xs font-bold text-primary shrink-0">View</Link>
          </div>
        );
      })()}

      {/* Graduation claim — backend is source of truth for eligibility */}
      {user && (
        <div className="rounded-2xl bg-gradient-dark p-5 text-white relative overflow-hidden">
          <div className="absolute -right-4 -top-4 text-6xl opacity-15">🎓</div>
          <div className="relative">
            <div className="flex items-center gap-2 mb-1">
              <GraduationCap className="w-5 h-5 text-white/60" />
              <span className="text-xs font-bold uppercase tracking-wide text-white/60">Graduation Reward</span>
            </div>
            {gradClaimed ? (
              <p className="text-sm font-semibold text-white/90">✓ You've already claimed your graduation HP. Check back after admin approval!</p>
            ) : (
              <>
                <h3 className="font-heading font-bold text-lg text-white mb-1">Claim your graduation HP! 🎓</h3>
                <p className="text-xs text-white/80 mb-3">Eligible graduates receive up to {graduationHp()} HP. Eligibility is verified when you claim.</p>
                <button onClick={handleGraduationClaim} disabled={claimingGrad} className="px-5 py-2.5 rounded-full bg-white text-primary font-bold text-sm shadow-md disabled:opacity-60 flex items-center gap-2">
                  {claimingGrad ? <><div className="w-3.5 h-3.5 border-2 border-primary/30 border-t-primary rounded-full animate-spin" /> Claiming…</> : <>Claim {graduationHp()} HP</>}
                </button>
              </>
            )}
          </div>
        </div>
      )}

      {/* Tab switcher */}
      <div className="flex gap-1 p-1 rounded-full bg-secondary overflow-x-auto scrollbar-hide">
        {tabs.map((t) => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            className={`shrink-0 flex items-center justify-center gap-1.5 px-3 py-2 rounded-full text-xs font-bold transition-all ${
              tab === t.id ? 'bg-white text-primary shadow-sm' : 'text-muted-foreground'
            }`}
          >
            <t.icon className="w-3.5 h-3.5" />
            {t.label}
          </button>
        ))}
      </div>

      {/* Dashboard tab */}
      {tab === 'dashboard' && (
        <div className="space-y-3">
          <div className="rounded-2xl bg-white border border-border p-4 shadow-card">
            <div className="flex items-center gap-2 mb-1">
              <Gift className="w-4 h-4 text-primary" />
              <h3 className="font-bold text-sm text-foreground">Free Sides on Us</h3>
            </div>
            <div className="flex items-center justify-between">
              <div>
                <div className="font-heading font-extrabold text-2xl text-primary tabular-nums">{freeSideCredits?.count ?? 0}</div>
                <div className="text-xs text-muted-foreground">Available · {freeSideCredits?.expires_at ? expiryLabel(freeSideCredits.expires_at) : `${freeSideCreditsValidityDays()} day expiry`}</div>
              </div>
              <span className="text-2xl">🏆</span>
            </div>
            <p className="text-[11px] text-muted-foreground mt-2">Use one at checkout.</p>
          </div>

          {/* Exclusive Spin — with actual spin button */}
          <div className={`rounded-2xl border p-4 shadow-card ${spinCount > 0 && !hasSpun ? 'bg-gradient-gold border-primary/30' : 'bg-white border-border'}`}>
            <div className="flex items-center gap-3">
              <div className={`w-10 h-10 rounded-full flex items-center justify-center text-xl shrink-0 ${spinCount > 0 && !hasSpun ? 'bg-primary' : 'bg-secondary'}`}>
                🎡
              </div>
              <div className="flex-1">
                {spinCount > 0 && !hasSpun ? (
                  <>
                    <div className="font-heading font-bold text-sm text-foreground">Spin available! 🎉</div>
                    <div className="text-xs text-muted-foreground">You have {spinCount} spin{spinCount !== 1 ? 's' : ''}. Spin to win bonus HP or free items.</div>
                  </>
                ) : hasSpun ? (
                  <>
                    <div className="font-heading font-bold text-sm text-foreground">Spin Used</div>
                    <div className="text-xs text-muted-foreground">Keep climbing the ranks.</div>
                  </>
                ) : (
                  <>
                    <div className="font-heading font-bold text-sm text-muted-foreground">No spins right now</div>
                    <div className="text-xs text-muted-foreground">Climb the leaderboard.</div>
                  </>
                )}
              </div>
              <button
                onClick={() => spinCount > 0 && !hasSpun && setShowSpinModal(true)}
                disabled={spinCount === 0 || hasSpun}
                className={`px-4 py-2 rounded-full text-xs font-bold transition-all shrink-0 ${
                  spinCount > 0 && !hasSpun
                    ? 'bg-gradient-cta text-white active:scale-95'
                    : 'bg-secondary text-muted-foreground cursor-not-allowed'
                }`}
              >
                {hasSpun ? 'Used' : spinCount > 0 ? `Spin (${spinCount})` : 'Spin'}
              </button>
            </div>
          </div>

          <Link to="/hall-of-fame" className="block rounded-2xl bg-accent/10 border border-accent/20 p-4 active:scale-[0.99] transition-transform shadow-card">
            <div className="flex items-center gap-3">
              <Crown className="w-5 h-5 text-accent shrink-0" />
              <div className="flex-1">
                <div className="font-bold text-sm text-foreground">Hall of Fame</div>
                <div className="text-xs text-muted-foreground">Stay on top, month after month.</div>
              </div>
              <ChevronRight className="w-4 h-4 text-muted-foreground" />
            </div>
          </Link>
        </div>
      )}

      {/* Redeem tab */}
      {tab === 'redeem' && (
        <div className="space-y-3">
          <h3 className="font-heading font-bold text-sm text-foreground">It counts everywhere.</h3>
          {rewards.length === 0 && (
            <div className="text-center py-12 rounded-2xl border-2 border-dashed border-border">
              <MascotStandee mascot="worried" className="w-28 h-28 mx-auto mb-2" alt="No rewards available" />
              <p className="text-sm text-muted-foreground">Nothing here yet.</p>
            </div>
          )}
          {[...rewards].sort((a, b) => (normFlash(b) ? 1 : 0) - (normFlash(a) ? 1 : 0)).map((reward) => {
            const flash = normFlash(reward);
            const tierList = hpTiers;
            const tierIndex = tierList.findIndex((t) => t.id === reward.min_tier_id);
            const currentTierIndex = tierInfo ? tierList.findIndex((t) => t.id === tierInfo.current.id || t.slug === tierInfo.current.slug) : 0;
            const tierLocked = currentTierIndex < tierIndex;
            const lowStock = reward.stock_quantity <= lowCodeInventoryThreshold();
            const locked = !flash && (tierLocked || lowStock);
            const effectiveHpCost = flash?.hpCost ?? reward.hp_cost;
            const canAfford = hpActive >= effectiveHpCost;
            const category = CATEGORY_LABELS[reward.reward_type] || reward.reward_type;
            const countdown = flash ? formatCountdown(flash.endsAt) : null;
            const slotsLeft = flash?.slotsRemaining;

            return (
              <div key={reward.id} className={`rounded-2xl bg-white border p-3 flex gap-3 shadow-card ${flash ? 'border-primary/30' : 'border-border'}`}>
                {reward.image_url ? (
                  <img src={reward.image_url} alt={reward.name} className="w-16 h-16 rounded-xl object-cover shrink-0" />
                ) : (
                  <div className="w-16 h-16 rounded-xl bg-secondary flex items-center justify-center text-2xl shrink-0">🎁</div>
                )}
                <div className="flex-1 min-w-0">
                  <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0">
                      {flash && (
                        <div className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded-full bg-primary text-white text-[9px] font-bold uppercase tracking-wide mb-1">
                          <Zap className="w-2.5 h-2.5" /> Flash
                        </div>
                      )}
                      <h3 className="font-bold text-sm text-foreground truncate">{reward.name}</h3>
                    </div>
                    <div className="flex items-center gap-1 shrink-0">
                      {flash?.normalHpCost && flash.normalHpCost > effectiveHpCost && (
                        <span className="text-xs font-medium text-muted-foreground line-through tabular-nums">{flash.normalHpCost}</span>
                      )}
                      <span className="flex items-center gap-1 text-sm font-bold text-primary">
                        <Flame className="w-3.5 h-3.5" />
                        {effectiveHpCost}
                      </span>
                    </div>
                  </div>
                  <p className="text-xs text-muted-foreground mt-0.5 capitalize">{reward.reward_type} reward</p>

                  {flash && (
                    <div className="flex items-center gap-2 mt-1.5">
                      {countdown && (
                        <span className="inline-flex items-center gap-1 text-[10px] font-bold text-primary bg-primary/5 px-1.5 py-0.5 rounded-full">
                          <Clock className="w-2.5 h-2.5" /> {countdown}
                        </span>
                      )}
                      {slotsLeft != null && (
                        <span className="text-[10px] font-bold text-muted-foreground bg-secondary px-1.5 py-0.5 rounded-full">{slotsLeft} left</span>
                      )}
                    </div>
                  )}

                  <div className="flex items-center justify-between mt-2">
                    <span className="text-[10px] font-semibold text-muted-foreground bg-secondary px-2 py-0.5 rounded-full">{category}</span>
                    {locked ? (
                      <div className="flex items-center gap-1 text-xs font-bold text-muted-foreground">
                        <Lock className="w-3.5 h-3.5" />
                        {tierLocked ? `${tierList[tierIndex]?.name || 'Higher'} tier` : 'Low stock'}
                      </div>
                    ) : flash ? (
                      <button
                        onClick={() => handleFlashRedeem(reward)}
                        disabled={!canAfford || flashRedeeming === reward.id}
                        className={`px-4 py-1.5 rounded-full text-xs font-bold transition-all flex items-center gap-1 ${canAfford ? 'bg-gradient-cta text-white active:scale-95' : 'bg-secondary text-muted-foreground cursor-not-allowed'}`}
                      >
                        {flashRedeeming === reward.id ? <><div className="w-3 h-3 border-2 border-white/40 border-t-white rounded-full animate-spin" /> Redeeming…</> : canAfford ? <><Zap className="w-3 h-3" /> Flash Redeem</> : `Need ${effectiveHpCost - hpActive} HP`}
                      </button>
                    ) : (
                      <button
                        onClick={() => setSelectedReward(reward)}
                        disabled={!canAfford}
                        className={`px-4 py-1.5 rounded-full text-xs font-bold transition-all ${canAfford ? 'bg-primary text-white active:scale-95' : 'bg-secondary text-muted-foreground cursor-not-allowed'}`}
                      >
                        {canAfford ? 'Redeem' : `Need ${effectiveHpCost - hpActive} HP`}
                      </button>
                    )}
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Challenges tab */}
      {tab === 'challenges' && (
        <div className="space-y-3">
          <h3 className="font-heading font-bold text-sm text-foreground">Small missions. Real prizes.</h3>
          {/* App install + push bonuses — permanent home under Challenges */}
          <InstallPushBonuses />

          {(() => {
            const available = challenges?.challenges_available || [];
            const completed = challenges?.challenges_completed || [];
            const badges = challenges?.badges || [];
            const all = [...available, ...completed];
            if (all.length === 0 && badges.length === 0) {
              return <div className="text-center py-12 rounded-2xl border-2 border-dashed border-border"><p className="text-sm text-muted-foreground">Nothing here yet.</p></div>;
            }
            return (
              <>
                {badges.length > 0 && (
                  <div className="rounded-2xl bg-accent/10 border border-accent/20 p-3 mb-2">
                    <div className="flex items-center gap-2 mb-2"><Award className="w-4 h-4 text-accent" /><span className="text-xs font-bold text-foreground">Badges Earned</span></div>
                    <div className="flex flex-wrap gap-2">
                      {badges.map((b, i) => (
                        <span key={i} className="text-xs font-bold px-2.5 py-1 rounded-full bg-white border border-accent/20 text-accent-foreground flex items-center gap-1">
                          {b.icon_won || '🏅'} {b.title || b.name}
                        </span>
                      ))}
                    </div>
                  </div>
                )}
                {all.map((ch) => {
                  const isCompleted = completed.some((c) => c.id === ch.id);
                  const progress = ch.progress || ch.current_progress || 0;
                  const target = ch.trigger_value || ch.target || ch.target_count || 1;
                  const pct = Math.min(100, (progress / target) * 100);
                  const isSocial = !isCompleted && (ch.trigger_type === 'social_follow' || (`${ch.title || ch.name || ''} ${ch.slug || ''}`.toLowerCase().includes('social') && `${ch.title || ch.name || ''} ${ch.slug || ''}`.toLowerCase().includes('follow')));
                  return (
                    <div key={ch.id} className="rounded-2xl bg-white border border-border p-4 shadow-card">
                      <div className="flex items-center justify-between mb-2">
                        <div className="flex items-center gap-2">
                          <Target className="w-4 h-4 text-primary" />
                          <h3 className="font-bold text-sm text-foreground">{ch.title || ch.name}</h3>
                        </div>
                        <span className="flex items-center gap-1 text-xs font-bold text-primary">
                          <Flame className="w-3 h-3" />+{ch.hp_awarded || ch.hp_award || 0}
                        </span>
                      </div>
                      <p className="text-xs text-muted-foreground mb-2">{ch.description || ch.requirement}</p>
                      <div className="flex items-center gap-2">
                        <div className="flex-1 h-2 rounded-full bg-secondary">
                          <div className="h-full rounded-full bg-primary transition-all duration-500" style={{ width: `${pct}%` }} />
                        </div>
                        <span className="text-xs font-bold text-foreground tabular-nums">{progress}/{target}</span>
                      </div>
                      <div className="flex items-center justify-between mt-2">
                        {ch.expires_at && <p className="text-[10px] text-muted-foreground">Expires: {new Date(ch.expires_at).toLocaleDateString()}</p>}
                        {isCompleted ? (
                          <span className="ml-auto text-[10px] font-bold text-emerald-600">✓ Completed</span>
                        ) : isSocial ? (
                          <></>
                        ) : (
                          <button onClick={() => handleCompleteChallenge(ch)} disabled={completing === ch.id} className="ml-auto px-3 py-1 rounded-full bg-primary text-white text-[10px] font-bold disabled:opacity-50">
                            {completing === ch.id ? '…' : 'Claim'}
                          </button>
                        )}
                      </div>
                      {!isCompleted && isSocial && (
                        <SocialFollowChallenge challenge={ch} onClaimed={handleSocialFollowClaimed} />
                      )}
                    </div>
                  );
                })}
              </>
            );
          })()}
        </div>
      )}

      {/* Redeemed tab */}
      {tab === 'redeemed' && (
        <div className="space-y-2">
          {redemptions.length === 0 ? (
            <div className="text-center py-12 rounded-2xl border-2 border-dashed border-border">
              <Download className="w-9 h-9 text-muted-foreground/40 mx-auto mb-2" />
              <p className="text-sm text-muted-foreground">Nothing redeemed yet.</p>
            </div>
          ) : redemptions.map((r) => (
            <div key={r.id} className="flex items-center gap-3 p-3.5 rounded-2xl bg-white border border-border shadow-card">
              <div className={`w-10 h-10 rounded-xl flex items-center justify-center shrink-0 ${r.status === 'fulfilled' ? 'bg-emerald-100' : (r.status === 'cancelled' || r.status === 'rejected') ? 'bg-red-100' : 'bg-amber-100'}`}>
                {r.status === 'fulfilled' ? <Check className="w-5 h-5 text-emerald-600" /> : (r.status === 'cancelled' || r.status === 'rejected') ? <X className="w-5 h-5 text-red-500" /> : <Clock className="w-5 h-5 text-amber-500" />}
              </div>
              <div className="flex-1 min-w-0">
                <div className="font-semibold text-sm text-foreground truncate">{r.reward?.name || r.reward_name || 'Reward'}</div>
                <div className="text-xs text-muted-foreground capitalize">{r.status} · {r.hp_cost_snapshot || 0} HP</div>
                <div className="text-[10px] text-muted-foreground">{new Date(r.created_at).toLocaleString()}</div>
              </div>
              <div className="flex flex-col items-end gap-1 shrink-0">
                <div className="flex items-center gap-1 text-xs font-bold text-primary">
                  <Flame className="w-3.5 h-3.5" /> {r.hp_cost_snapshot || 0}
                </div>
                {r.status === 'fulfilled' && !r.attached_order_id && (
                  <button onClick={() => setDeliveryRedemption(r)} className="px-3 py-1.5 rounded-full bg-gradient-cta text-white text-[11px] font-bold active:scale-95 transition">Choose delivery</button>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* History tab */}
      {tab === 'history' && (
        <div className="space-y-4">
          <h3 className="font-heading font-bold text-sm text-foreground">Your HP story</h3>
          <div>
            <h3 className="font-bold text-sm text-foreground mb-2 flex items-center gap-1.5"><History className="w-4 h-4 text-primary" /> Spin History</h3>
            {spinHistory.length === 0 ? (
              <p className="text-xs text-muted-foreground">Nothing here yet.</p>
            ) : (
              <div className="space-y-2">
                {spinHistory.map((s) => (
                  <div key={s.id} className="flex items-center justify-between p-3 rounded-xl bg-white border border-border shadow-card">
                    <div>
                      <div className="text-sm font-semibold text-foreground">+{s.hp_won || 0} HP</div>
                      <div className="text-[10px] text-muted-foreground">{s.free_spin ? 'Free spin' : `Cost ${s.spin_cost_hp || 0} HP`} · {new Date(s.created_at || s.spun_at).toLocaleString()}</div>
                    </div>
                    <span className="text-lg">🎡</span>
                  </div>
                ))}
              </div>
            )}
          </div>
          <div>
            <h3 className="font-bold text-sm text-foreground mb-2 flex items-center gap-1.5"><Award className="w-4 h-4 text-accent" /> Unlock History</h3>
            {unlockHistory.length === 0 ? (
              <p className="text-xs text-muted-foreground">Nothing here yet.</p>
            ) : (
              <div className="space-y-2">
                {unlockHistory.map((u) => (
                  <div key={u.id} className="flex items-center justify-between p-3 rounded-xl bg-white border border-border shadow-card">
                    <div>
                      <div className="text-sm font-semibold text-foreground">{u.reward_name || u.name || 'Reward unlocked'}</div>
                      <div className="text-[10px] text-muted-foreground">{new Date(u.created_at || u.unlocked_at).toLocaleString()}</div>
                    </div>
                    <span className="text-lg">🎁</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}

      {/* Redeem confirmation modal */}
      {selectedReward && (
        <div className="fixed inset-0 z-50 bg-black/60 backdrop-blur-md flex items-center justify-center p-4" onClick={() => setSelectedReward(null)}>
          <div className="bg-white rounded-3xl p-6 w-full max-w-sm animate-slide-up" onClick={(e) => e.stopPropagation()}>
            <div className="flex justify-between items-start mb-4">
              <h3 className="font-heading font-bold text-lg text-foreground">Confirm Redemption</h3>
              <button onClick={() => setSelectedReward(null)}><X className="w-5 h-5 text-muted-foreground" /></button>
            </div>
            <div className="text-center py-2">
              {selectedReward.image_url ? (
                <img src={selectedReward.image_url} alt="" className="w-24 h-24 rounded-2xl object-cover mx-auto mb-3" />
              ) : (
                <div className="w-24 h-24 rounded-2xl bg-secondary flex items-center justify-center text-4xl mx-auto mb-3">🎁</div>
              )}
              <h4 className="font-bold text-foreground text-lg">{selectedReward.name}</h4>
              <p className="text-xs text-muted-foreground capitalize mt-0.5">{selectedReward.reward_type} · {selectedReward.stock_quantity} in stock</p>
              <div className="flex items-center justify-center gap-1 mt-2">
                <Flame className="w-4 h-4 text-primary" />
                <span className="font-bold text-primary tabular-nums">{selectedReward.hp_cost} HP</span>
              </div>
              <p className="text-xs text-muted-foreground mt-3">Your redemption will be processed and you'll be notified when it's ready for pickup.</p>
            </div>
            <button onClick={handleRedeem} disabled={redeeming} className="w-full py-3 rounded-full bg-primary text-white font-bold disabled:opacity-50">
              {redeeming ? 'Redeeming…' : `Redeem for ${selectedReward.hp_cost} HP`}
            </button>
          </div>
        </div>
      )}

      {/* Spin wheel modal */}
      <SpinWheel
        open={showSpinModal}
        prizes={exclusiveStatus?.prizes}
        onClose={() => setShowSpinModal(false)}
        onResult={() => { setHasSpun(true); refreshHp(); triggerMascotCelebration('cheering'); liveApi.hp.getExclusiveSpinStatus().then(setExclusiveStatus).catch(() => {}); }}
        canSpin={spinCount > 0 && !hasSpun}
      />

      <RewardDeliveryModal
        redemption={deliveryRedemption}
        open={!!deliveryRedemption}
        onClose={() => setDeliveryRedemption(null)}
        onDelivered={(res) => { loadRedemptions(); if (res?.next_step === 'checkout') navigate('/checkout'); }}
      />
    </div>
  );
}