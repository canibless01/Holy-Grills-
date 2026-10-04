import { useState, useEffect } from 'react';
import { Save, Gift } from 'lucide-react';
import { liveApi as mockApi } from '@/lib/liveApi';
import { timeAgo } from '@/lib/hgUtils';
import LoadingSpinner from '@/components/LoadingSpinner';
import { Field, TextInput, Card, Toggle, Pill } from './AdminShared';
import { useIsSuperAdmin, SuperAdminNotice } from './SuperAdminGate';
import { toast } from '@/components/ui/use-toast';
import { msg } from '@/lib/messages';

export default function AdminOnboarding() {
  const isSuperAdmin = useIsSuperAdmin();
  const [settings, setSettings] = useState(null);
  const [gifts, setGifts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [busy, setBusy] = useState(null);

  const load = async () => {
    setLoading(true);
    try {
      const [s, g] = await Promise.all([mockApi.admin.getGiftSettings(), mockApi.admin.getFirstOrderGifts()]);
      setSettings(s || {});
      setGifts(Array.isArray(g) ? g : []);
    } catch { setSettings({}); setGifts([]); }
    setLoading(false);
  };
  useEffect(() => { load(); }, []);

  const saveSetting = async (key, value) => {
    setSaving(true);
    try {
      await mockApi.admin.updateGiftSetting(key, { value: String(value) });
      setSettings((cur) => ({ ...cur, [key]: value }));
      toast({ title: msg('FE_ADMIN_ONBOARDING_GIFT_SETTING_SAVED', 'Gift setting saved'), description: key });
    } catch (e) { toast({ title: msg('FE_ADMIN_ONBOARDING_FAILED', 'Failed'), description: e.message, variant: 'destructive' }); }
    setSaving(false);
  };

  const updateGift = async (id, status) => {
    setBusy(id);
    try { const res = await mockApi.admin.updateFirstOrderGiftStatus(id, { status }); toast({ title: res?.message || 'Gift updated' }); await load(); }
    catch (e) { toast({ title: msg('FE_ADMIN_ONBOARDING_FAILED', 'Failed'), description: e.message, variant: 'destructive' }); }
    setBusy(null);
  };

  if (loading || !settings) return <LoadingSpinner label="Loading gift settings..." />;

  const isTrue = (v) => v === true || String(v) === 'true';
  const enabled = isTrue(settings.first_order_gift_enabled);
  const endDate = settings.launch_window_end_date || '';
  const itemName = settings.first_order_gift_item_name || '';

  return (
    <div className="space-y-5">
      <Card>
        <h3 className="font-bold text-sm text-foreground mb-1">First-Order Gift Settings</h3>
        <p className="text-[11px] text-muted-foreground mb-3">The welcome gift is fully configurable here (not hardcoded). It auto-awards when a user's first order reaches <b>delivered</b>, only if enabled and on/before the launch end date.</p>
        {isSuperAdmin ? (
          <div className="space-y-3">
            <div className="flex items-center gap-2">
              <Toggle checked={enabled} onChange={(v) => setSettings({ ...settings, first_order_gift_enabled: v })} />
              <span className="text-sm text-foreground font-semibold">Enable first-order gift</span>
              <button onClick={() => saveSetting('first_order_gift_enabled', enabled ? 'false' : 'true')} disabled={saving} className="ml-auto px-3 py-1.5 rounded-full bg-gradient-cta text-white text-xs font-bold disabled:opacity-50"><Save className="w-3.5 h-3.5 inline mr-1" />Save toggle</button>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <Field label="Launch window end date" hint="Gift only awarded on or before this date">
                <input type="date" value={endDate ? String(endDate).slice(0, 10) : ''} onChange={(e) => setSettings({ ...settings, launch_window_end_date: e.target.value })} className="w-full mt-1 p-2.5 rounded-xl border border-border text-sm" />
              </Field>
              <Field label="Gift item name" hint="What shows on the receipt as the gift">
                <TextInput value={itemName} onChange={(e) => setSettings({ ...settings, first_order_gift_item_name: e.target.value })} placeholder="e.g. Hot Dog" />
              </Field>
            </div>
            <button onClick={() => { saveSetting('launch_window_end_date', settings.launch_window_end_date || ''); saveSetting('first_order_gift_item_name', settings.first_order_gift_item_name || ''); }} disabled={saving} className="w-full py-3 rounded-full bg-gradient-cta text-white font-bold text-sm flex items-center justify-center gap-2 disabled:opacity-50"><Save className="w-4 h-4" /> Save Gift Settings</button>
          </div>
        ) : (
          // Gift settings are system settings — writes are super-admin-only
          // (regular admins get 403), so render the current config read-only.
          <div className="space-y-2.5">
            <SuperAdminNotice>First-order gift settings are managed by a <b>super admin</b>. Current configuration:</SuperAdminNotice>
            <div className="flex flex-wrap gap-1.5 text-xs font-bold">
              <span className={`px-2.5 py-1 rounded-full ${enabled ? 'bg-success/15 text-success' : 'bg-destructive/10 text-destructive'}`}>{enabled ? 'Gift enabled' : 'Gift disabled'}</span>
              {endDate && <span className="px-2.5 py-1 rounded-full bg-secondary text-foreground">Ends {String(endDate).slice(0, 10)}</span>}
              {itemName && <span className="px-2.5 py-1 rounded-full bg-secondary text-foreground">Gift item: {itemName}</span>}
            </div>
          </div>
        )}
        <div className="mt-3 rounded-xl bg-muted p-2 text-[11px] text-muted-foreground">Note: the signup bonus HP is set in environment variables and is not admin-editable here.</div>
      </Card>

      <div>
        <h3 className="font-bold text-sm text-foreground mb-2 flex items-center gap-2"><Gift className="w-4 h-4 text-primary" /> First-Order Gifts</h3>
        <p className="text-[11px] text-muted-foreground mb-2">Gifted orders awaiting fulfillment (spec: GET /admin/gifts/first-order-gifts, PATCH /admin/gifts/first-order-gifts/:id).</p>
        {gifts.length === 0 ? <p className="text-xs text-muted-foreground text-center py-6">No first-order gifts yet.</p> : (
        <div className="space-y-2">
          {gifts.map((g) => (
            <Card key={g.id} className="flex items-center gap-3 !p-3">
              <div className="flex-1">
                <div className="font-bold text-sm text-foreground">{g.profiles?.full_name || g.user_name || g.user?.full_name || 'User'}</div>
                <div className="text-xs text-muted-foreground">{g.gift_item_name || g.item_name || 'Gift'} · order #{(g.orders?.id || g.order_id || '').toString().toUpperCase()} · {timeAgo(g.created_at)}</div>
              </div>
              {g.status === 'pending' ? (
                <div className="flex gap-1">
                  <button onClick={() => updateGift(g.id, 'fulfilled')} disabled={busy === g.id} className="px-3 py-1.5 rounded-full bg-green-50 text-green-600 border border-green-200 text-xs font-bold disabled:opacity-50">Fulfill</button>
                  <button onClick={() => updateGift(g.id, 'cancelled')} disabled={busy === g.id} className="px-3 py-1.5 rounded-full bg-red-50 text-red-600 border border-red-200 text-xs font-bold disabled:opacity-50">Cancel</button>
                </div>
              ) : <Pill tone={g.status === 'fulfilled' ? 'green' : g.status === 'claimed' || g.status === 'redeemed' ? 'blue' : 'red'}>{g.status}</Pill>}
            </Card>
          ))}
        </div>
        )}
      </div>
    </div>
  );
}