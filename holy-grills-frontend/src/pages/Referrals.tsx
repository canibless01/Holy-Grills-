import { useState, useEffect, useCallback } from 'react';
import { ArrowLeft } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { useHolyGrill } from '@/lib/HolyGrillContext';
import { liveApi } from '@/lib/liveApi';
import { referralHp } from '@/lib/appConfig';
import { toast } from '@/components/ui/use-toast';
import ReferralCodeCard from '@/components/referrals/ReferralCodeCard';
import ReferralStats from '@/components/referrals/ReferralStats';
import ReferralMilestones from '@/components/referrals/ReferralMilestones';
import ReferredFriends from '@/components/referrals/ReferredFriends';
import ShareSheet from '@/components/ShareSheet';
import ReferralsSkeleton from '@/components/skeletons/ReferralsSkeleton';
import { msg } from '@/lib/messages';

// Defensive read of the referral stats response — the backend shapes for
// /referrals/stats aren't pinned in the spec, so we accept whatever keys it
// returns and fall back to the auth-me profile for code/count/hp. We never
// invent values; missing fields surface as honest zeros / empty states.
const readStats = (raw, user) => {
  const s = raw && raw.data ? raw.data : raw || {};
  const profile = user || {};
  const code =
    s.referral_code || s.code || profile.referral_code || (profile.profile && profile.profile.referral_code) || '';
  const link =
    s.referral_link || s.link ||
    (code ? `${window.location.origin}/r/${code}` : '');
  return {
    referral_code: code,
    referral_link: link,
    total_invited: s.total_invited ?? s.total_referrals ?? s.referral_count ?? s.invited ??
      profile.referral_count ?? (profile.profile && profile.profile.referral_count) ?? profile.referrals_count ?? 0,
    active_friends: s.active_friends ?? s.completed_referrals ?? s.completed ?? s.active ?? 0,
    total_hp_earned: s.total_hp_earned ?? s.hp_earned ??
      profile.referral_hp_earned ?? (profile.profile && profile.profile.referral_hp_earned) ?? 0,
  };
};

export default function Referrals() {
  const navigate = useNavigate();
  const { user, isLoading } = useHolyGrill();
  const [stats, setStats] = useState(null);
  const [friends, setFriends] = useState([]);
  const [loading, setLoading] = useState(true);
  const [copied, setCopied] = useState(false);
  const [showShare, setShowShare] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [statsRes, histRes] = await Promise.allSettled([
        liveApi.referrals.getStats(),
        liveApi.referrals.getHistory(),
      ]);
      if (statsRes.status === 'fulfilled') setStats(readStats(statsRes.value, user));
      if (histRes.status === 'fulfilled') setFriends(Array.isArray(histRes.value) ? histRes.value : []);
    } catch (e) { /* surface nothing — honest empty state */ }
    setLoading(false);
  }, [user]);

  useEffect(() => { if (!isLoading) load(); }, [isLoading, load]);

  const code = stats?.referral_code || '';
  const link = stats?.referral_link || '';
  const referredCount = stats?.total_invited ?? 0;

  const handleCopy = async () => {
    if (!link) return;
    try {
      await navigator.clipboard?.writeText(link);
      setCopied(true);
      toast({ title: msg('FE_REFERRALS_REFERRAL_LINK_COPIED', 'Referral link copied!') });
      setTimeout(() => setCopied(false), 2000);
    } catch {
      toast({ title: msg('FE_REFERRALS_FAILED_TO_COPY_REFERRAL_LINK', 'Failed to copy referral link.'), variant: 'destructive' });
    }
  };

  if (isLoading) return <ReferralsSkeleton />;

  return (
    <div className="space-y-5 animate-fade-in max-w-xl mx-auto">
      <div className="flex items-center gap-2">
        <button
          onClick={() => navigate('/dashboard')}
          className="p-2 -ml-2 rounded-full hover:bg-secondary active:scale-95 transition"
          aria-label="Back to dashboard"
        >
          <ArrowLeft className="w-5 h-5 text-foreground" />
        </button>
        <h1 className="font-heading font-extrabold text-2xl text-foreground">Referrals 🔥</h1>
      </div>

      <ReferralCodeCard
        code={code}
        link={link}
        copied={copied}
        onCopy={handleCopy}
        onShare={() => code && setShowShare(true)}
        loading={loading && !code}
      />

      <ReferralStats stats={stats || {}} loading={loading} />

      <ReferralMilestones referredCount={referredCount} />

      <ReferredFriends friends={friends} loading={loading} />

      <ShareSheet
        open={showShare}
        onClose={() => setShowShare(false)}
        type="referral"
        templateKey="referral_share"
        payload={{
          headline: 'Join Holy Grill',
          value: code,
          caption: `Use my code ${code} and I earn ${referralHp()} HP when you place your first order! 🔥`,
          link,
        }}
      />
    </div>
  );
}