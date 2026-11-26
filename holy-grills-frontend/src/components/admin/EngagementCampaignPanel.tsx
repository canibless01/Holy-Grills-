import { useRef, useState } from 'react';
import { apiClient } from '@/lib/apiClient';
import { msg } from '@/lib/messages';
import { toast } from '@/components/ui/use-toast';
import ImageUploader from './ImageUploader';
import { useCampus } from '@/lib/campusContext';

type Step = { day: number; slot: string; title: string; body: string; action_url: string; push_image?: string | null };
type Campaign = { id: string; revision: number; name: string; start_date: string; morning_time: string; afternoon_time: string; is_active: boolean; steps: Step[] };
const input = 'mt-1 w-full rounded-xl border border-border bg-background p-2 text-sm';

export default function EngagementCampaignPanel() {
  const { adminCampusId } = useCampus();
  return <CampaignEditor key={adminCampusId || 'all'} />;
}

function CampaignEditor() {
  const [open, setOpen] = useState(false);
  const [campaign, setCampaign] = useState<Campaign | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [saved, setSaved] = useState<boolean | null>(null);
  const [day, setDay] = useState(1);
  const [slot, setSlot] = useState('morning');
  const [nickname, setNickname] = useState('Blessing');
  const [preview, setPreview] = useState<{ title: string; body: string; action_url: string } | null>(null);
  const lock = useRef(false);
  const run = async (action: () => Promise<void>) => {
    if (lock.current) return;
    lock.current = true; setBusy(true); setError('');
    try { await action(); }
    catch (e) { setError(e.message); }
    finally { lock.current = false; setBusy(false); }
  };
  const load = () => run(async () => {
    const result: { campaign: Campaign } = await apiClient.get('/engagement-campaign');
    setCampaign(result.campaign); setSaved(result.campaign.is_active); setPreview(null);
  });
  const change = (values: Partial<Campaign>) => { setCampaign(c => c ? { ...c, ...values } : c); setPreview(null); };
  const step = campaign?.steps.find(s => s.day === day && s.slot === slot);
  const changeStep = (values: Partial<Step>) => {
    if (campaign) change({ steps: campaign.steps.map(s => s.day === day && s.slot === slot ? { ...s, ...values } : s) });
  };
  const save = () => run(async () => {
    const result: { campaign: Campaign } = await apiClient.patch('/engagement-campaign', campaign);
    setCampaign(result.campaign); setSaved(result.campaign.is_active);
    toast({ title: msg('FE_CYCLE_SAVED', 'Campaign saved. Changes apply to future unsent slots.') });
  });
  return <section className="rounded-2xl border border-border bg-card p-4 space-y-3">
    <h2 className="font-bold">{msg('FE_CYCLE_TITLE', '14-day community push campaign')}</h2>
    <button type="button" aria-expanded={open} onClick={() => { setOpen(!open); if (!open && !campaign) void load(); }} className="text-primary underline text-sm">{msg('FE_CYCLE_OPEN', 'Edit repeating campaign')}</button>
    {open && <>
      <p className="text-xs text-muted-foreground">{msg('FE_CYCLE_HELP', 'Two slots on a repeating 14-day calendar, in WAT. Sends run only while campus ordering is open and capacity remains. Missed slots are skipped. Pausing or editing cancels unsent messages from the previous version.')}</p>
      {error && <p role="alert" className="rounded-xl bg-destructive/10 p-3 text-sm text-destructive">{error}</p>}
      {busy && !campaign && <p role="status">{msg('FE_CYCLE_LOADING', 'Loading campaign…')}</p>}
      <button type="button" disabled={busy} onClick={load} className="underline text-sm disabled:opacity-50">{msg('FE_CYCLE_RELOAD', 'Reload campaign')}</button>
      {campaign && <fieldset disabled={busy} className="min-w-0 space-y-3">
        <p className="text-xs">{msg('FE_CYCLE_STATUS', 'Saved status')}: {saved ? msg('FE_CYCLE_ACTIVE', 'Active') : msg('FE_CYCLE_DRAFT', 'Paused')}</p>
        <label className="block text-sm">{msg('FE_CYCLE_NAME', 'Campaign name')}<input className={input} maxLength={100} value={campaign.name} onChange={e => change({ name: e.target.value })} /></label>
        <div className="grid gap-3 sm:grid-cols-3">
          <label className="text-sm">{msg('FE_CYCLE_START', 'Cycle starts')}<input type="date" className={input} value={campaign.start_date} onChange={e => change({ start_date: e.target.value })} /></label>
          <label className="text-sm">{msg('FE_CYCLE_MORNING', 'Morning time (WAT)')}<input type="time" max="11:59" className={input} value={campaign.morning_time.slice(0, 5)} onChange={e => change({ morning_time: e.target.value })} /></label>
          <label className="text-sm">{msg('FE_CYCLE_AFTERNOON', 'Afternoon time (WAT)')}<input type="time" min="12:00" className={input} value={campaign.afternoon_time.slice(0, 5)} onChange={e => change({ afternoon_time: e.target.value })} /></label>
        </div>
        <label className="flex items-center gap-3 rounded-xl bg-primary/5 p-3 text-sm"><input type="checkbox" checked={campaign.is_active} onChange={e => change({ is_active: e.target.checked })} />{msg('FE_CYCLE_ENABLED', 'Enable recurring sends to opted-in students')}</label>
        <div className="grid grid-cols-2 gap-3">
          <label className="text-sm">{msg('FE_CYCLE_DAY', 'Cycle day')}<select aria-label={msg('FE_CYCLE_DAY', 'Cycle day')} className={input} value={day} onChange={e => { setDay(Number(e.target.value)); setPreview(null); }}>{Array.from({ length: 14 }, (_, i) => <option key={i + 1} value={i + 1}>{i + 1}</option>)}</select></label>
          <label className="text-sm">{msg('FE_CYCLE_SLOT', 'Time slot')}<select aria-label={msg('FE_CYCLE_SLOT', 'Time slot')} className={input} value={slot} onChange={e => { setSlot(e.target.value); setPreview(null); }}><option value="morning">{msg('FE_CYCLE_MORNING', 'Morning time (WAT)')}</option><option value="afternoon">{msg('FE_CYCLE_AFTERNOON', 'Afternoon time (WAT)')}</option></select></label>
        </div>
        {step && <div className="rounded-xl bg-muted/50 p-3 space-y-3">
          <label className="block text-sm">{msg('FE_CYCLE_HEADLINE', 'Push title')}<input className={input} maxLength={100} value={step.title} onChange={e => changeStep({ title: e.target.value })} /></label>
          <label className="block text-sm">{msg('FE_CYCLE_BODY', 'Push message')}<textarea aria-label={msg('FE_CYCLE_BODY', 'Push message')} className={input} rows={3} maxLength={500} value={step.body} onChange={e => changeStep({ body: e.target.value })} /></label>
          <p className="text-xs text-muted-foreground">{msg('FE_CYCLE_TOKENS', 'Personalize with {{nickname}}, {{name}}, {{campus}} or {{order_cutoff}}. Nickname falls back to their first name, then “friend”.')}</p>
          <label className="block text-sm">{msg('FE_CYCLE_LINK', 'Destination')}<select aria-label={msg('FE_CYCLE_LINK', 'Destination')} className={input} value={step.action_url} onChange={e => changeStep({ action_url: e.target.value })}>{['/menu', '/dashboard', '/rewards', '/wallet', '/events', '/orders', '/leaderboard'].map(path => <option key={path} value={path}>{path}</option>)}</select></label>
          <ImageUploader label={msg('FE_CYCLE_IMAGE', 'Optional Cloudinary image')} value={step.push_image || ''} onChange={value => changeStep({ push_image: value || null })} folder="engagement-campaign" />
        </div>}
        <div className="flex flex-wrap items-end gap-3">
          <label className="text-sm">{msg('FE_CYCLE_PREVIEW_NAME', 'Preview nickname')}<input className={input} maxLength={40} value={nickname} onChange={e => { setNickname(e.target.value); setPreview(null); }} /></label>
          <button type="button" onClick={() => run(async () => { setPreview(await apiClient.post('/engagement-campaign/preview', { campaign, day, slot, nickname })); })} className="rounded-full border px-4 py-2 text-sm">{msg('FE_CYCLE_PREVIEW', 'Preview only')}</button>
          <button type="button" onClick={save} className="rounded-full bg-primary px-4 py-2 text-sm font-bold text-primary-foreground">{msg('FE_CYCLE_SAVE', 'Save campaign')}</button>
        </div>
        {preview && <div role="status" className="rounded-xl border p-3 text-sm"><strong>{preview.title}</strong><p>{preview.body}</p><p className="text-xs text-muted-foreground">{preview.action_url}</p></div>}
      </fieldset>}
    </>}
  </section>;
}
