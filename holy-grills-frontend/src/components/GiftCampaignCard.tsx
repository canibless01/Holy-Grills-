import { useEffect, useState } from 'react';
import { liveApi } from '@/lib/liveApi';
import { msg } from '@/lib/messages';
import { toast } from '@/components/ui/use-toast';

export default function GiftCampaignCard({ onClaimed }) {
  const [data, setData] = useState(null), [busy, setBusy] = useState(false), [error, setError] = useState(false);
  const refreshBalances = async () => { try { await onClaimed?.(); } catch { /* Saved gifts survive a balance-read outage. */ } };
  const load = async () => { try { const value = await liveApi.rewards.getGiftCampaign(); setData(value); setError(false); } catch { setError(true); } };
  useEffect(() => {
    let alive = true;
    liveApi.rewards.getGiftCampaign().then(value => { if (alive) { setData(value); if (value.history?.length) void refreshBalances(); } }).catch(() => { if (alive) setError(true); });
    return () => { alive = false; };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps
  const claim = async () => {
    if (busy) return;
    setBusy(true);
    try {
      const result = await liveApi.rewards.claimGiftCampaign({ campaign_id: data.campaign.id });
      if (!result.granted && !result.idempotent) {
        toast({ title: msg('FE_GIFT_NOT_ELIGIBLE', 'This campaign is not currently available for your account.') });
      } else {
        toast({ title: msg('FE_GIFT_CLAIMED', 'Your gifts are ready') });
        await refreshBalances();
      }
      await load();
    } catch (exception) { toast({ title: msg('FE_GIFT_CLAIM_FAILED', 'Could not claim gifts'), description: exception.message, variant: 'destructive' }); }
    finally { setBusy(false); }
  };
  if (error) return <button onClick={load} className="text-xs font-bold text-primary">{msg('FE_GIFT_RETRY', 'Retry gift campaigns')}</button>;
  if (!data?.campaign && !data?.history?.length) return null;
  const claimed = data.history?.find(row => row.result_snapshot?.campaign_id === data.campaign?.id);
  const campaign = claimed ? { ...data.campaign, name: claimed.prize_name, benefits: claimed.result_snapshot.benefits } : data.campaign;
  return <section className="rounded-2xl border border-border bg-card p-4 space-y-3">
    {campaign && <><h3 className="text-sm font-bold">{campaign.name}</h3><div className="flex flex-wrap gap-2">{campaign.benefits.map(benefit => <span key={benefit.kind} className="rounded-xl bg-secondary px-2 py-1 text-xs">{benefit.label}</span>)}</div>
      <button disabled={busy || !!claimed} onClick={claim} className="rounded-full bg-primary px-4 py-2 text-xs font-bold text-white disabled:opacity-50">{claimed ? msg('FE_GIFT_ALREADY_CLAIMED', 'Claimed') : busy ? msg('FE_ONBOARDING_SAVING', 'Saving…') : msg('FE_GIFT_CLAIM', 'Claim gifts')}</button>
    </>}
    {!!data.history?.length && <details className="text-xs text-muted-foreground"><summary className="cursor-pointer font-semibold">{msg('FE_GIFT_HISTORY', 'Claimed gift campaigns')}</summary><div className="mt-2 space-y-2">{data.history.map(row => <p key={row.id}><strong>{row.prize_name}</strong><br />{(row.result_snapshot?.benefits || []).map(benefit => benefit.label).join(' · ')}{row.result_snapshot?.expires_at && (row.result_snapshot?.benefits || []).some(benefit => benefit.kind !== 'hp') && <><br />{msg('FE_GIFT_EXPIRES', 'Order benefits valid until {date}', { date: new Date(row.result_snapshot.expires_at).toLocaleDateString('en-NG', { timeZone: 'Africa/Lagos' }) })}</>}</p>)}</div></details>}
  </section>;
}
