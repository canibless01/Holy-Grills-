import { useState, useEffect, useRef } from 'react';
import { Save, Gift } from 'lucide-react';
import { liveApi as mockApi } from '@/lib/liveApi';
import { timeAgo } from '@/lib/hgUtils';
import { useCampus } from '@/lib/campusContext';
import StaffPanelSkeleton from '@/components/skeletons/StaffPanelSkeleton';
import { Field, TextInput, Card, Toggle, Pill } from './AdminShared';
import { useIsSuperAdmin } from './SuperAdminGate';
import { toast } from '@/components/ui/use-toast';
import { msg } from '@/lib/messages';
import AdminGiftCampaign from './AdminGiftCampaign';

export default function AdminOnboarding() {
  const isSuperAdmin = useIsSuperAdmin();
  const { campusId, adminCampusId, campuses } = useCampus();
  const scopeCampus = isSuperAdmin ? adminCampusId : campusId;
  const scopeKey = scopeCampus || 'global';
  const scope = scopeCampus ? { campus_id: scopeCampus } : { scope: 'global' };
  const generation = useRef(0);
  const [settings, setSettings] = useState(null);
  const [inherited, setInherited] = useState(false);
  const [gifts, setGifts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [busy, setBusy] = useState(null);
  const [loadError, setLoadError] = useState(false);

  const load = async () => {
    const requestId = ++generation.current;
    setLoading(true); setLoadError(false);
    try {
      const [s, g] = await Promise.all([
        mockApi.admin.getWelcomeCreditSettings(scope),
        mockApi.admin.getFirstOrderGifts(scopeCampus ? { campus_id: scopeCampus } : {}),
      ]);
      if (requestId !== generation.current) return;
      setSettings(s.config); setInherited(s.inherited === true);
      setGifts(Array.isArray(g) ? g : []);
    } catch { if (requestId === generation.current) setLoadError(true); }
    if (requestId === generation.current) setLoading(false);
  };
  useEffect(() => { load(); return () => { generation.current += 1; }; }, [scopeKey]); // eslint-disable-line react-hooks/exhaustive-deps

  const save = async () => {
    if (saving) return;
    const requestId = generation.current;
    setSaving(true);
    try {
      const res = await mockApi.admin.updateWelcomeCreditSettings({ ...scope, config: {
        enabled: settings.enabled, credits: Number(settings.credits), validity_days: Number(settings.validity_days),
      } });
      if (requestId === generation.current) {
        setSettings(res.config); setInherited(false);
        toast({ title: msg('FE_ONBOARDING_WELCOME_SAVED', 'Welcome credits saved') });
      }
    } catch (error) {
      if (requestId === generation.current) toast({ title: msg('FE_ADMIN_ONBOARDING_FAILED', 'Failed'), description: error.message, variant: 'destructive' });
    } finally { setSaving(false); }
  };
  const updateGift = async (id, status) => {
    const requestId = generation.current;
    setBusy(id);
    try { const res = await mockApi.admin.updateFirstOrderGiftStatus(id, { status }); if (requestId === generation.current) { toast({ title: res?.message || msg('FE_ONBOARDING_GIFT_UPDATED', 'Gift updated') }); await load(); } }
    catch (error) { toast({ title: msg('FE_ADMIN_ONBOARDING_FAILED', 'Failed'), description: error.message, variant: 'destructive' }); }
    setBusy(null);
  };
  if (loadError) return <div className="py-10 text-center space-y-3"><p>{msg('FE_PLATFORM_LOAD_FAILED', "We couldn't load this page. Please try again.")}</p><button onClick={load} className="text-primary font-bold">{msg('FE_PLATFORM_RETRY', 'Retry')}</button></div>;
  if (loading || !settings) return <StaffPanelSkeleton />;
  const credits = Number(settings.credits), days = Number(settings.validity_days);
  const valid = Number.isInteger(credits) && credits >= 1 && credits <= 10 && Number.isInteger(days) && days >= 1 && days <= 365;
  const scopeName = scopeCampus ? campuses.find(c => c.id === scopeCampus)?.name || msg('FE_ONBOARDING_SELECTED_CAMPUS', 'Selected campus') : msg('FE_ONBOARDING_GLOBAL_DEFAULTS', 'Global defaults');
  return <div className="space-y-5">
    <Card>
      <h3 className="font-bold text-sm text-foreground mb-1">{msg('FE_ONBOARDING_WELCOME_TITLE', 'Signup welcome credits')}</h3>
      <p className="text-[11px] text-muted-foreground mb-3">{msg('FE_ONBOARDING_WELCOME_HELP', 'Eligible new accounts receive free-side credits automatically. Pausing stops new grants. Credits already granted keep their saved balance and expiry.')}</p>
      <div className="flex items-center gap-2 mb-3"><Pill tone="cocoa">{scopeName}</Pill>{inherited && <Pill tone="blue">{msg('FE_ONBOARDING_INHERITED', 'Using global defaults')}</Pill>}</div>
      <div className="space-y-3">
        <div className="flex items-center gap-2"><Toggle label={msg('FE_ONBOARDING_WELCOME_ENABLE', 'Enable signup free-side credits')} disabled={saving} checked={settings.enabled === true} onChange={enabled => setSettings({ ...settings, enabled })} /><span className="text-sm font-semibold">{msg('FE_ONBOARDING_WELCOME_ENABLE', 'Enable signup free-side credits')}</span></div>
        <div className="grid grid-cols-2 gap-3">
          <Field label={msg('FE_ONBOARDING_CREDITS', 'Credits per account')} hint={msg('FE_ONBOARDING_CREDITS_HINT', '1–10 free-side credits')}><TextInput type="number" min={1} max={10} step={1} disabled={saving} value={settings.credits} onChange={e => setSettings({ ...settings, credits: e.target.value })} /></Field>
          <Field label={msg('FE_ONBOARDING_VALIDITY', 'Validity in days')} hint={msg('FE_ONBOARDING_VALIDITY_HINT', '1–365 days after grant')}><TextInput type="number" min={1} max={365} step={1} disabled={saving} value={settings.validity_days} onChange={e => setSettings({ ...settings, validity_days: e.target.value })} /></Field>
        </div>
        <button onClick={save} disabled={saving || !valid} className="w-full py-3 rounded-full bg-gradient-cta text-white font-bold text-sm flex items-center justify-center gap-2 disabled:opacity-50"><Save className="w-4 h-4" />{saving ? msg('FE_ONBOARDING_SAVING', 'Saving…') : msg('FE_ONBOARDING_WELCOME_SAVE', 'Save welcome credits')}</button>
      </div>
    </Card>
    <AdminGiftCampaign key={scopeKey} scope={scope} />
    <div>
      <h3 className="font-bold text-sm mb-2 flex items-center gap-2"><Gift className="w-4 h-4 text-primary" />{msg('FE_ONBOARDING_LEGACY_TITLE', 'Earlier first-order gifts')}</h3>
      <p className="text-[11px] text-muted-foreground mb-2">{msg('FE_ONBOARDING_LEGACY_HELP', 'Previously granted physical gifts remain available for fulfillment. New welcome rewards use free-side credits.')}</p>
      {gifts.length === 0 ? <p className="text-xs text-muted-foreground text-center py-6">{msg('FE_ONBOARDING_LEGACY_EMPTY', 'No earlier gifts to fulfill.')}</p> : <div className="space-y-2">{gifts.map(g => <Card key={g.id} className="flex items-center gap-3 !p-3">
        <div className="flex-1"><div className="font-bold text-sm text-foreground">{g.profiles?.full_name || g.user_name || g.user?.full_name || msg('FE_ONBOARDING_USER', 'User')}</div><div className="text-xs text-muted-foreground">{g.gift_item_name || g.item_name || msg('FE_ONBOARDING_GIFT', 'Gift')} · #{(g.orders?.id || g.order_id || '').toString().toUpperCase()} · {timeAgo(g.created_at)}</div></div>
        {g.status === 'pending' ? <div className="flex gap-1"><button onClick={() => updateGift(g.id, 'fulfilled')} disabled={busy === g.id} className="px-3 py-1.5 rounded-full tone-success border border-success/30 text-xs font-bold disabled:opacity-50">{msg('FE_ONBOARDING_FULFILL', 'Fulfill')}</button><button onClick={() => updateGift(g.id, 'cancelled')} disabled={busy === g.id} className="px-3 py-1.5 rounded-full tone-error border border-destructive/30 text-xs font-bold disabled:opacity-50">{msg('FE_ONBOARDING_CANCEL', 'Cancel')}</button></div> : <Pill tone={g.status === 'fulfilled' ? 'green' : 'red'}>{g.status}</Pill>}
      </Card>)}</div>}
    </div>
  </div>;
}
