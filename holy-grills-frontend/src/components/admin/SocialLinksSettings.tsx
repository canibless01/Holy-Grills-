import { useEffect, useState } from 'react';
import { liveApi } from '@/lib/liveApi';
import { msg } from '@/lib/messages';
import { SOCIAL_PLATFORMS, safeSocialLinks } from '@/lib/socialLinks';
import { toast } from '@/components/ui/use-toast';
import { Card } from './AdminShared';
import { SuperAdminBadge } from './SuperAdminGate';

const KEY = 'global_social_links';

export default function SocialLinksSettings({ settings, onSaved, canEdit }) {
  const row = settings.find(s => s.key === KEY && !s.campus_id);
  const [draft, setDraft] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  useEffect(() => { setDraft(row?.value || {}); }, [row]);
  const save = async () => {
    setBusy(true);
    try {
      const trimmed = Object.fromEntries(Object.entries(draft).map(([key, value]) => [key, value.trim()]).filter(([, value]) => value));
      const valid = safeSocialLinks(trimmed);
      if (Object.keys(trimmed).length !== Object.keys(valid).length) throw new Error(msg('FE_SOCIAL_LINKS_INVALID', 'Enter HTTPS social-profile links for the matching platform, or leave the field empty.'));
      const body = { value: valid, is_public: true };
      if (row) await liveApi.admin.updateSystemSetting(KEY, body);
      else await liveApi.admin.createSystemSetting({ key: KEY, ...body });
      const fresh = await liveApi.admin.getSystemSettings();
      const saved = fresh.find(s => s.key === KEY && !s.campus_id);
      if (!saved || saved.is_public === false || SOCIAL_PLATFORMS.some(p => (saved.value?.[p.key] || '') !== (valid[p.key] || ''))) {
        throw new Error(msg('FE_SOCIAL_LINKS_READBACK_FAILED', 'The saved social links could not be confirmed. Reload and try again.'));
      }
      await onSaved();
      toast({ title: msg('FE_SOCIAL_LINKS_SAVED', 'Social links saved') });
    } catch (error) {
      toast({ title: msg('FE_SOCIAL_LINKS_FAILED', 'Could not save social links'), description: error.message, variant: 'destructive' });
    } finally { setBusy(false); }
  };
  return <Card className="p-4 space-y-4">
    <div className="flex items-center gap-3"><h3 className="text-sm font-bold">{msg('FE_SOCIAL_LINKS_TITLE', 'Social links')}</h3>{!canEdit && <SuperAdminBadge />}</div>
    <p className="text-xs text-muted-foreground">{msg('FE_SOCIAL_LINKS_HELP', 'Global links shown in the footer and Contact us. Leave a platform empty to hide it.')}</p>
    <div className="grid gap-3 sm:grid-cols-2">{SOCIAL_PLATFORMS.map(platform => <label key={platform.key} className="text-xs font-bold space-y-1">
      <span>{msg(platform.labelKey, platform.label)}</span>
      <input type="url" value={draft[platform.key] || ''} onChange={event => setDraft({ ...draft, [platform.key]: event.target.value })} disabled={!canEdit || busy} placeholder={`https://${platform.hosts[0]}/…`} className="block w-full rounded-xl border border-border bg-background px-3 py-2 text-sm font-normal" />
    </label>)}</div>
    {canEdit && <button type="button" disabled={busy} onClick={save} className="rounded-full bg-primary px-4 py-2 text-sm font-bold text-primary-foreground disabled:opacity-50">{busy ? msg('FE_SOCIAL_LINKS_SAVING', 'Saving…') : msg('FE_SOCIAL_LINKS_SAVE', 'Save social links')}</button>}
  </Card>;
}
