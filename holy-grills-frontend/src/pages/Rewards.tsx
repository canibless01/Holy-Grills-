import { nextChallengeSteps } from '@/lib/challengeProgression';
import GraduationClaimButton from '@/components/GraduationClaimButton';
import GiftCampaignCard from '@/components/GiftCampaignCard';
import { formatNaira } from '@/lib/hgUtils';
import { useState, useEffect } from 'react';
import { Flame, Lock, Gift, Target, X, Check, History, Sparkles, Crown, Zap, Clock, ChevronRight, Award, Download } from 'lucide-react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { liveApi } from '@/lib/liveApi';
import { useHolyGrill } from '@/lib/HolyGrillContext';
import { getTierProgress, getTierProgressGradient, getTierOverallProgress, setTiers } from '@/lib/hgUtils';
import TierIcon from '@/components/TierIcon';
import { getStreakRewardHp, isFeatureEnabled, useFeatureFlags } from '@/lib/featureConfig';
import { freeSideCreditsValidityDays } from '@/lib/appConfig';
import { expiryLabel } from '@/lib/rewardUtils';
import { toast } from '@/components/ui/use-toast';
import RewardsSkeleton from '@/components/skeletons/RewardsSkeleton';
import SpinWheel from '@/components/SpinWheel';
import RewardDeliveryModal from '@/components/RewardDeliveryModal';
import ModalPortal from '@/components/ModalPortal';
import InstallPushBonuses from '@/components/challenges/InstallPushBonuses';
import SocialFollowChallenge from '@/components/challenges/SocialFollowChallenge';
import MascotStandee from '@/components/mascot/MascotStandee';
import { haptic } from '@/lib/haptic';
import { triggerMascotCelebration } from '@/lib/mascots';
import type { MyChallengesEnvelope } from '@/types/challenges';
import { msg, useMessages } from '@/lib/messages';
import { localStore } from '@/lib/storage';
import { useCampus } from '@/lib/campusContext';
import { useResumeEffect } from '@/hooks/useResumeEffect';

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

// Rows are read through the legacy aliases the endpoint still emits; the
// envelope itself is the endpoint's documented shape (types/challenges.ts).

export default function Rewards() {
  useFeatureFlags();
  useMessages();
  const freeSidesReleased = isFeatureEnabled('free_side_credits');
  const spinReleased = isFeatureEnabled('exclusive_spin');
  const hallReleased = isFeatureEnabled('hall_of_fame');
  const flashReleased = isFeatureEnabled('flash_redemptions');
  const { hpBalance, refreshHp, streak, user } = useHolyGrill();
  const { campusId } = useCampus();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const [tab, setTab] = useState(() => searchParams.get('tab') === 'challenges' ? 'challenges' : 'redeem');
  const [rewards, setRewards] = useState([]);
  const [redemptions, setRedemptions] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selectedReward, setSelectedReward] = useState(null);
  const [redeeming, setRedeeming] = useState(false);
  // GET /challenges/my returns an envelope ({ badges, challenges_available,
  // challenges_completed }) — the page reads it with `?.`, so null is a safe
  // initial value and matches the pre-API render.
  const [challenges, setChallenges] = useState<MyChallengesEnvelope | null>(null);
  const [spinHistory, setSpinHistory] = useState([]);
  const [unlockHistory, setUnlockHistory] = useState([]);
  const [completing, setCompleting] = useState(null);
  const [freeSideCredits, setFreeSideCredits] = useState({ count: 0, expires_at: null });
  const [exclusiveStatus, setExclusiveStatus] = useState(null);
  const [flashRedeeming, setFlashRedeeming] = useState(null);
  const [showSpinModal, setShowSpinModal] = useState(false);
  const [hasSpun, setHasSpun] = useState(false);
  const [deliveryRedemption, setDeliveryRedemption] = useState(null);
  const [hpTiers, setHpTiers] = useState([]);
  const [loadError, setLoadError] = useState(false);
  const [reload, setReload] = useState(0);

  useResumeEffect((background) => {
    let active = true;
    if (!user?.id || !campusId) return;
    if (!background) setLoading(true);
    setLoadError(false);
    liveApi.hp.getTiers().then(t => {
      if (active && Array.isArray(t)) { setTiers(t); setHpTiers(t); }
    }).catch(() => { if (active) setLoadError(true); });
    const load = async () => {
      try {
        const r = await liveApi.rewards.list();
        if (!active) return;
        setRewards(Array.isArray(r) ? r : (r?.rewards || []));
      } catch { if (active) setLoadError(true); }
      if (active) setLoading(false);
    };
    Promise.all([
      liveApi.challenges.my().catch(() => ({ badges: [], challenges_available: [], challenges_completed: [] })),
      liveApi.rewards.getFreeSideCredits().catch(() => ({ count: 0, expires_at: null })),
      liveApi.hp.getExclusiveSpinStatus().catch(() => null),
    ]).then(([myChallenges, fsc, exStatus]) => {
      if (!active) return;
      setChallenges(myChallenges); setFreeSideCredits(fsc); setExclusiveStatus(exStatus);
    });
    load();
    return () => { active = false; };
  }, [user?.id, campusId, reload]);

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
      const res = await liveApi.hp.flashRedeem(reward.id);
      const saved = res?.redemption || res;
      const redemptionId = saved?.redemption_id || saved?.id;
      if (redemptionId) setDeliveryRedemption({ ...saved, id: redemptionId, status: 'fulfilled', reward });
      try { await refreshHp(); } catch { /* the reward was already redeemed */ }
      toast({ title: msg('FE_REWARDS_FLASH_REWARD_REDEEMED', '⚡ Flash reward redeemed!'), description: msg('FE_REWARDS_NAME_UNLOCKED_AT_FLASH_PRICE', '{name} unlocked at flash price.', { name: reward.name }) });
      try { const r = await liveApi.rewards.list(); setRewards(r); } catch { /* do not report a saved redemption as failed */ }
    } catch (e) {
      toast({ title: msg('FE_REWARDS_FLASH_REDEMPTION_FAILED', 'Flash redemption failed'), description: e.message, variant: 'destructive' });
    }
    setFlashRedeeming(null);
  };

  const handleCompleteChallenge = async (ch) => {
    setCompleting(ch.id);
    try {
      await liveApi.challenges.complete(ch.id);
      await refreshHp();
      const myChallenges = await liveApi.challenges.my().catch(() => ({ badges: [], challenges_available: [], challenges_completed: [] }));
      setChallenges(myChallenges);
      toast({ title: msg('FE_REWARDS_CHALLENGE_COMPLETE', '🎉 Challenge complete!'), description: msg('FE_REWARDS_BONUS_HP_ADDED', 'Bonus HP added.') });
    } catch (e) {
      toast({ title: msg('FE_REWARDS_COULD_NOT_COMPLETE', 'Could not complete'), description: e.message, variant: 'destructive' });
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
      const chosen = selectedReward;
      const res = await liveApi.rewards.redeem(chosen.id);
      const saved = res?.redemption || res;
      setSelectedReward(null);
      if (saved?.id && saved.status === 'fulfilled') setDeliveryRedemption({ ...saved, reward: chosen });
      haptic('success');
      toast({ title: msg('FE_REWARDS_REWARD_REDEEMED', '🎉 Reward redeemed!'), description: msg('FE_REWARDS_CHOOSE_DELIVERY', 'Your reward is ready. Choose how to receive it.') });
      try { await refreshHp(); await loadRedemptions(); } catch { /* a read failure does not undo the saved redemption */ }
    } catch (e) {
      haptic('error');
      toast({ title: msg('FE_REWARDS_REDEMPTION_FAILED', 'Redemption failed'), description: e.message, variant: 'destructive' });
    }
    setRedeeming(false);
  };

  if (loading) return <RewardsSkeleton />;

  const hpActive = hpBalance?.active || 0;
  const hpPending = hpBalance?.pending || 0;
  const tierInfo = hpBalance ? getTierProgress(hpBalance.hp_earned_120day) : null;
  const spinCount = exclusiveStatus?.total_spins ?? exclusiveStatus?.spins_available ?? 0;
  const recoverSpin = !!(user?.id && localStore.getItem(`hg_exclusive_spin_intent:${user.id}`));
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
      {loadError && <div role="alert" className="rounded-2xl border border-destructive/30 p-4 text-sm flex items-center justify-between gap-3"><span>Rewards or tier details could not be loaded.</span><button className="font-bold text-primary" onClick={() => setReload(value => value + 1)}>Retry</button></div>}
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
        <div className="rounded-2xl bg-card border border-border p-4 shadow-card">
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

      {/* Tab switcher */}
      <div className="flex gap-1 p-1 rounded-full bg-secondary overflow-x-auto scrollbar-hide">
        {tabs.map((t) => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            className={`shrink-0 flex items-center justify-center gap-1.5 px-3 py-2 rounded-full text-xs font-bold transition-all ${
              tab === t.id ? 'bg-card text-primary shadow-sm' : 'text-muted-foreground'
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
          {freeSidesReleased && <div className="rounded-2xl bg-card border border-border p-4 shadow-card">
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
          </div>}

          {/* Exclusive Spin — with actual spin button */}
          {spinReleased && <div className={`rounded-2xl border p-4 shadow-card ${spinCount > 0 ? 'bg-gradient-gold border-primary/30' : 'bg-card border-border'}`}>
            <div className="flex items-center gap-3">
              <div className={`w-10 h-10 rounded-full flex items-center justify-center text-xl shrink-0 ${spinCount > 0 ? 'bg-primary' : 'bg-secondary'}`}>
                🎡
              </div>
              <div className="flex-1">
                {spinCount > 0 ? (
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
                onClick={() => (spinCount > 0 || recoverSpin) && setShowSpinModal(true)}
                disabled={spinCount === 0 && !recoverSpin}
                className={`px-4 py-2 rounded-full text-xs font-bold transition-all shrink-0 ${
                  spinCount > 0
                    ? 'bg-gradient-cta text-white active:scale-95'
                    : 'bg-secondary text-muted-foreground cursor-not-allowed'
                }`}
              >
                {recoverSpin ? msg('FE_SPIN_RECOVER', 'Recover spin result') : spinCount > 0 ? `Spin (${spinCount})` : hasSpun ? 'Used' : 'Spin'}
              </button>
            </div>
          </div>}

          {spinReleased && exclusiveStatus?.history?.length > 0 && <section className="rounded-2xl border border-border bg-card p-4 shadow-card" aria-label={msg('FE_SPIN_HISTORY_TITLE', 'Exclusive spin prizes')}>
            <h3 className="font-bold text-sm mb-2">{msg('FE_SPIN_HISTORY_TITLE', 'Exclusive spin prizes')}</h3>
            <div className="space-y-2">{exclusiveStatus.history.map((receipt) => <div key={receipt.id} className="rounded-xl bg-secondary/40 p-3 flex items-center justify-between gap-2">
              <div><p className="font-semibold text-sm">{receipt.prize_name}</p><p className="text-xs text-muted-foreground">{new Date(receipt.created_at).toLocaleDateString()}</p></div>
              <span className="text-xs font-semibold">{receipt.result_snapshot?.prize_type==='hp_multiplier' && receipt.status==='pending' && receipt.applied_order_id ? <Link className="underline" to={`/orders/${receipt.applied_order_id}`}>{msg('FE_SPIN_MULTIPLIER_RESERVED', 'HP bonus reserved for order {order}', { order: receipt.applied_order_id.slice(0, 8).toUpperCase() })}</Link> : receipt.result_snapshot?.prize_type==='hp_multiplier' && receipt.status==='pending' ? msg('FE_SPIN_MULTIPLIER_READY', '{multiplier}× food HP saved for a delivered order', { multiplier: receipt.result_snapshot.reward_config?.multiplier }) : receipt.result_snapshot?.prize_type==='hp_multiplier' && receipt.applied_order_id ? msg('FE_SPIN_MULTIPLIER_APPLIED', 'HP bonus applied to order {order}', { order: receipt.applied_order_id.slice(0, 8).toUpperCase() }) : receipt.result_snapshot?.prize_type==='hp_multiplier' && receipt.status==='fulfilled' ? msg('FE_SPIN_MULTIPLIER_LEGACY', 'Legacy HP bonus; usage was not recorded') : receipt.result_snapshot?.prize_type==='free_delivery' && receipt.status==='pending' ? msg('FE_SPIN_DELIVERY_READY', 'Up to {cap} off your next delivery fee', { cap: formatNaira(receipt.result_snapshot.reward_config?.cap || 0) }) : receipt.result_snapshot?.prize_type==='free_delivery' && receipt.applied_order_id ? msg('FE_SPIN_DELIVERY_APPLIED', 'Applied to order {order}', { order: receipt.applied_order_id.slice(0, 8).toUpperCase() }) : receipt.status==='pending' ? msg('FE_SPIN_PENDING', 'Awaiting campus fulfilment') : receipt.status==='fulfilled' ? msg('FE_SPIN_FULFILLED', 'Fulfilled') : msg('FE_SPIN_CANCELLED', 'Cancelled')}</span>
            </div>)}</div>
          </section>}

          <GraduationClaimButton onClaimed={refreshHp} />

          {hallReleased && <Link to="/hall-of-fame" className="block rounded-2xl bg-accent/10 border border-accent/20 p-4 active:scale-[0.99] transition-transform shadow-card">
            <div className="flex items-center gap-3">
              <Crown className="w-5 h-5 text-accent shrink-0" />
              <div className="flex-1">
                <div className="font-bold text-sm text-foreground">Hall of Fame</div>
                <div className="text-xs text-muted-foreground">Stay on top, month after month.</div>
              </div>
              <ChevronRight className="w-4 h-4 text-muted-foreground" />
            </div>
          </Link>}
        </div>
      )}

      {/* Redeem tab */}
      {tab === 'redeem' && (
        <div className="space-y-3">
          <GiftCampaignCard onClaimed={async () => { await refreshHp(); setFreeSideCredits(await liveApi.rewards.getFreeSideCredits()); }} />
          <h3 className="font-heading font-bold text-sm text-foreground">It counts everywhere.</h3>
          {rewards.length === 0 && !loadError && (
            <div className="text-center py-12 rounded-2xl border-2 border-dashed border-border">
              <MascotStandee mascot="worried" className="w-28 h-28 mx-auto mb-2" alt="No rewards available" />
              <p className="text-sm text-muted-foreground">Nothing here yet.</p>
            </div>
          )}
          {[...rewards].sort((a, b) => (flashReleased && normFlash(b) ? 1 : 0) - (flashReleased && normFlash(a) ? 1 : 0)).map((reward) => {
            const flash = flashReleased ? normFlash(reward) : null;
            const tierList = hpTiers;
            const tierIndex = tierList.findIndex((t) => t.id === reward.min_tier_id);
            const currentTierIndex = tierInfo ? tierList.findIndex((t) => t.id === tierInfo.current.id || t.slug === tierInfo.current.slug) : 0;
            const tierLocked = Boolean(reward.min_tier_id) && (tierIndex < 0 || currentTierIndex < tierIndex);
            const outOfStock = reward.stock_quantity != null && Number(reward.stock_quantity) <= 0;
            const locked = !flash && (tierLocked || outOfStock);
            const effectiveHpCost = flash?.hpCost ?? reward.hp_cost;
            const canAfford = hpActive >= effectiveHpCost;
            const category = CATEGORY_LABELS[reward.reward_type] || reward.reward_type;
            const countdown = flash ? formatCountdown(flash.endsAt) : null;
            const slotsLeft = flash?.slotsRemaining;

            return (
              <div key={reward.id} className={`rounded-2xl bg-card border p-3 flex gap-3 shadow-card ${flash ? 'border-primary/30' : 'border-border'}`}>
                {reward.image_url ? (
                  <img src={reward.image_url} alt={reward.name} loading="lazy" decoding="async" className="w-16 h-16 rounded-xl object-cover shrink-0" />
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
                      {Boolean(flash?.normalHpCost) && flash.normalHpCost > effectiveHpCost && (
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
                        {tierLocked ? `${tierList[tierIndex]?.name || reward.hp_tiers?.name || 'Higher'} tier` : 'Out of stock'}
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
            const available = [...(challenges?.milestones_available || []), ...(challenges?.challenges_available || [])];
            const completed = [...(challenges?.milestones_completed || []), ...(challenges?.challenges_completed || [])];
            // Lifetime HP milestones and recurring challenges share progress cards.
            const all = nextChallengeSteps(available, completed);
            if (all.length === 0 && completed.length === 0) {
              return <div className="text-center py-12 rounded-2xl border-2 border-dashed border-border"><p className="text-sm text-muted-foreground">Nothing here yet.</p></div>;
            }
            return (
              <>
                {all.map((ch) => {
                  const isCompleted = completed.some((c) => c.id === ch.id);
                  const progress = ch.progress || ch.current_progress || 0;
                  const target = ch.trigger_value || ch.target || ch.target_count || 1;
                  const pct = Math.min(100, (progress / target) * 100);
                  const isSocial = !isCompleted && (ch.trigger_type === 'social_follow' || (`${ch.title || ch.name || ''} ${ch.slug || ''}`.toLowerCase().includes('social') && `${ch.title || ch.name || ''} ${ch.slug || ''}`.toLowerCase().includes('follow')));
                  return (
                    <div key={ch.id} className="rounded-2xl bg-card border border-border p-4 shadow-card">
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
                          <span className="ml-auto text-[10px] font-bold text-success">✓ Completed</span>
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
                {completed.length > 0 && <details className="rounded-2xl border border-border bg-card p-4"><summary className="cursor-pointer text-xs font-bold text-muted-foreground">{msg('FE_CHALLENGES_COMPLETED_HISTORY', 'Completed ({count})', { count: completed.length })}</summary><div className="space-y-2 mt-3">{completed.map(ch => <div key={ch.id} className="flex items-center justify-between gap-3 text-xs"><span>{ch.title || ch.name}</span><span className="text-success font-bold">{msg('FE_CHALLENGES_CLAIMED_HP', '{hp} HP claimed', { hp: ch.hp_awarded ?? ch.hp_award ?? 0 })}</span></div>)}</div></details>}
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
            <div key={r.id} className="flex items-center gap-3 p-3.5 rounded-2xl bg-card border border-border shadow-card">
              <div className={`w-10 h-10 rounded-xl flex items-center justify-center shrink-0 ${r.status === 'fulfilled' ? 'tone-success' : (r.status === 'cancelled' || r.status === 'rejected') ? 'tone-error' : 'tone-warn'}`}>
                {r.status === 'fulfilled' ? <Check className="w-5 h-5 text-success" /> : (r.status === 'cancelled' || r.status === 'rejected') ? <X className="w-5 h-5 text-destructive" /> : <Clock className="w-5 h-5 text-warn" />}
              </div>
              <div className="flex-1 min-w-0">
                <div className="font-semibold text-sm text-foreground truncate">{r.reward?.name || r.rewards?.name || r.reward_name || msg('FE_REWARDS_REWARD_LABEL', 'Reward')}</div>
                <div className="text-xs text-muted-foreground capitalize">{r.status === 'fulfilled' ? (r.attached_order_id ? msg('FE_REWARDS_ATTACHED_ORDER', 'Added to order') : msg('FE_REWARDS_READY_DELIVERY', 'Ready for delivery')) : r.status} · {r.hp_cost_snapshot || 0} HP</div>
                <div className="text-[10px] text-muted-foreground">{new Date(r.created_at).toLocaleString()}</div>
              </div>
              <div className="flex flex-col items-end gap-1 shrink-0">
                <div className="flex items-center gap-1 text-xs font-bold text-primary">
                  <Flame className="w-3.5 h-3.5" /> {r.hp_cost_snapshot || 0}
                </div>
                {r.attached_order_id && <Link to={'/orders/' + r.attached_order_id} className="text-xs font-semibold text-primary underline">{msg('FE_REWARDS_VIEW_ORDER', 'View order')}</Link>}
                {r.status === 'fulfilled' && !r.attached_order_id && !r.used_at && (
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
                  <div key={s.id} className="flex items-center justify-between p-3 rounded-xl bg-card border border-border shadow-card">
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
                  <div key={u.id} className="flex items-center justify-between p-3 rounded-xl bg-card border border-border shadow-card">
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
        <ModalPortal>
        <div className="fixed inset-0 z-50 hg-scrim flex items-center justify-center p-4" onClick={() => setSelectedReward(null)}>
          <div role="dialog" aria-modal="true" aria-labelledby="redemption-title" className="bg-card rounded-3xl p-6 w-full max-w-sm animate-slide-up" onClick={(e) => e.stopPropagation()}>
            <div className="flex justify-between items-start mb-4">
              <h3 id="redemption-title" className="font-heading font-bold text-lg text-foreground">Confirm Redemption</h3>
              <button onClick={() => setSelectedReward(null)}><X className="w-5 h-5 text-muted-foreground" /></button>
            </div>
            <div className="text-center py-2">
              {selectedReward.image_url ? (
                <img src={selectedReward.image_url} alt="" loading="lazy" decoding="async" className="w-24 h-24 rounded-2xl object-cover mx-auto mb-3" />
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
        </ModalPortal>
      )}

      {/* Spin wheel modal */}
      <SpinWheel
        open={showSpinModal && spinReleased}
        prizes={exclusiveStatus?.prizes}
        onClose={() => setShowSpinModal(false)}
        onResult={(result) => { if (result) setHasSpun(true); refreshHp(); triggerMascotCelebration('cheering'); liveApi.hp.getExclusiveSpinStatus().then(setExclusiveStatus).catch(() => {}); }}
        canSpin={spinCount > 0}
      />

      <RewardDeliveryModal
        redemption={deliveryRedemption}
        open={!!deliveryRedemption}
        onClose={() => setDeliveryRedemption(null)}
        onDelivered={(res) => { loadRedemptions(); if (res?.next_step === 'checkout' && res.reward_redemption_id) navigate('/checkout?reward=' + encodeURIComponent(res.reward_redemption_id)); }}
      />
    </div>
  );
}
