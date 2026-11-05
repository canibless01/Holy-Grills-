import { useEffect, useState } from 'react';
import { liveApi } from '@/lib/liveApi';
import { useHolyGrill } from '@/lib/HolyGrillContext';
import { useCampus } from '@/lib/campusContext';
import { msg } from '@/lib/messages';
import { toast } from '@/components/ui/use-toast';

export default function GraduationClaimButton({ onClaimed }: { onClaimed: () => Promise<unknown> }) {
  const { user } = useHolyGrill();
  const { campus } = useCampus();
  const [eligible, setEligible] = useState(false);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    let active = true;
    setEligible(false);
    if (user?.id && campus?.id) liveApi.graduation.eligibility()
      .then(result => { if (active) setEligible(result?.eligible === true && !result.claimed); })
      .catch(() => { /* Eligibility must be confirmed before showing a claim. */ });
    return () => { active = false; };
  }, [user?.id, campus?.id]);
  if (!eligible) return null;
  const claim = async () => {
    if (busy) return;
    setBusy(true);
    try {
      await liveApi.graduation.claim({});
      setEligible(false);
      toast({ title: msg('FE_REWARDS_GRADUATION_HP_CLAIMED', '🎓 Graduation HP claimed!'), description: msg('FE_GRAD_CLAIM_RECORDED', 'Your graduation reward has been recorded.') });
      try { await onClaimed(); } catch { /* A balance read cannot undo the saved reward. */ }
    } catch (error) {
      toast({ title: msg('FE_REWARDS_CLAIM_FAILED', 'Claim failed'), description: error.message, variant: 'destructive' });
    } finally { setBusy(false); }
  };
  return <button type="button" disabled={busy} onClick={claim} className="text-xs font-semibold text-primary underline underline-offset-4 disabled:opacity-50">
    {busy ? msg('FE_GRAD_CLAIM_SAVING', 'Claiming…') : msg('FE_GRAD_CLAIM_ACTION', 'Claim your graduation HP')}
  </button>;
}
