import { useState } from 'react';
import { Mail } from 'lucide-react';
import { liveApi } from '@/lib/liveApi';
import { toast } from '@/components/ui/use-toast';
import { Card } from './AdminShared';
import { SuperAdminBadge } from './SuperAdminGate';
import { msg } from '@/lib/messages';

// Stage 13 — Email delivery. Two independent provider defaults, kept visually
// separate on purpose: one control that looked like it governed both would
// misrepresent what are two separate settings.
const PROVIDERS = [
  { value: 'resend', label: 'Resend' },
  { value: 'onesignal', label: 'OneSignal' },
];

const KEYS = [
  { key: 'email_provider_transactional_default', label: 'Transactional emails', hint: 'Order confirmations, receipts, password resets.' },
  { key: 'email_provider_blast_default', label: 'Blast emails', hint: 'Campaigns, drops, announcements.' },
];

export default function EmailDeliverySettings({ settings, onSaved, canEdit = true }) {
  const [busy, setBusy] = useState(null);

  const getProvider = (key) => {
    const row = (settings || []).find((s) => s.key === key);
    return row?.value?.provider || 'resend';
  };

  const save = async (key, provider) => {
    setBusy(key);
    try {
      // PATCH first; if the key doesn't exist yet, create it (POST).
      try {
        await liveApi.admin.updateSystemSetting(key, { value: { provider } });
      } catch (e) {
        if (e.status && e.status !== 404) throw e;
        await liveApi.admin.createSystemSetting({ key, value: { provider }, description: `Default email provider for this category` });
      }
      toast({ title: msg('FE_EMAIL_DELIVERY_SETTINGS_EMAIL_DELIVERY_UPDATED', 'Email delivery updated'), description: msg('FE_EMAIL_DELIVERY_SETTINGS_KEY_PROVIDER', '{key} → {provider}', { key: key, provider: provider }) });
      onSaved?.();
    } catch (e) {
      toast({ title: msg('FE_EMAIL_DELIVERY_SETTINGS_FAILED_TO_SAVE', 'Failed to save'), description: e.message, variant: 'destructive' });
    }
    setBusy(null);
  };

  return (
    <Card className="p-4">
      <div className="flex items-center gap-2 mb-1"><Mail className="w-4 h-4 text-primary" /><span className="font-bold text-sm text-foreground">Email delivery</span></div>
      <p className="text-[11px] text-muted-foreground mb-3">Two independent defaults — transactional and blast emails can go through different providers.</p>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        {KEYS.map(({ key, label, hint }) => (
          <div key={key}>
            <label className="text-[11px] font-bold uppercase tracking-wide text-muted-foreground">{label}</label>
            {canEdit ? (
              <select
                value={getProvider(key)}
                disabled={busy === key}
                onChange={(e) => save(key, e.target.value)}
                className="w-full mt-1 p-2.5 rounded-xl border border-border text-sm bg-card disabled:opacity-50"
              >
                {PROVIDERS.map((p) => <option key={p.value} value={p.value}>{p.label}</option>)}
              </select>
            ) : (
              // System settings writes are super-admin-only (backend returns 403
              // for regular admins) — show the current provider, not an editor.
              <div className="flex items-center gap-2 mt-1 min-h-[38px]">
                <span className="font-bold text-sm text-foreground">{PROVIDERS.find((p) => p.value === getProvider(key))?.label || getProvider(key)}</span>
                <SuperAdminBadge />
              </div>
            )}
            <p className="text-[10px] text-muted-foreground mt-1">{hint}</p>
          </div>
        ))}
      </div>
    </Card>
  );
}