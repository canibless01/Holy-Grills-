import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Gift } from 'lucide-react';
import { apiClient } from '@/lib/apiClient';
import { msg } from '@/lib/messages';

export default function GiftCampaignTeaser({ campusId, authenticated }) {
  const [campaign, setCampaign] = useState(null);
  useEffect(() => {
    let alive = true; setCampaign(null);
    const load = async () => {
      if (!campusId) return;
      try { const response = await apiClient.get('/storefront/gift-campaign'); if (alive) setCampaign(response.campaign); }
      catch { if (alive) setCampaign(null); }
    };
    load(); const timer = setInterval(load, 60000);
    return () => { alive = false; clearInterval(timer); };
  }, [campusId, authenticated]);
  if (!campaign) return null;
  const labels = { signup: msg('FE_GIFT_TEASER_SIGNUP', 'New account gifts'), first_order: msg('FE_GIFT_TEASER_FIRST', 'First-order gifts'), everyone: msg('FE_GIFT_TEASER_CAMPUS', 'Campus gifts') };
  return <section className="flex items-center gap-3 rounded-2xl border border-border bg-card p-4 shadow-card">
    <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-primary/10 text-primary"><Gift className="h-6 w-6" /></div>
    <div className="min-w-0 flex-1"><p className="text-[10px] font-bold uppercase tracking-wide text-primary">{labels[campaign.eligibility]}</p><h3 className="text-sm font-bold">{campaign.name}</h3><p className="text-xs text-muted-foreground">{campaign.benefits.map(benefit => benefit.label).join(' · ')}</p></div>
    <Link to={authenticated ? '/rewards' : '/signup'} className="shrink-0 rounded-full border border-primary px-3 py-2 text-xs font-bold text-primary">{msg('FE_GIFT_SEE_GIFTS', 'See gifts')}</Link>
  </section>;
}
