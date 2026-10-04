import { useState, useEffect } from 'react';
import { Save, Award } from 'lucide-react';
import { liveApi } from '@/lib/liveApi';
import { Card, Pill, Toggle } from './AdminShared';
import ImageUploader from './ImageUploader';
import { toast } from '@/components/ui/use-toast';
import { clearTierIconsCache } from '@/lib/tierIcons';

// One fixed slot per membership tier. Each tier's artwork is its own storefront
// section (section_type 'tier_icon') keyed by content.tier_slug — so uploading
// Ember's mark only ever changes Ember, and every tier mark on the site (HP card,
// dashboard, leaderboard, account menu, HP education) reads from that one place.
const TIER_SLOTS = [
  { slug: 'ember', name: 'Ember', hint: 'Entry tier' },
  { slug: 'flame', name: 'Flame', hint: 'Second tier' },
  { slug: 'blaze', name: 'Blaze', hint: 'Third tier' },
  { slug: 'holy', name: 'Holy', hint: 'Top tier' },
];

export default function AdminTierIcons() {
  const [rows, setRows] = useState({});
  const [busy, setBusy] = useState(null);

  const load = async () => {
    try {
      const list = await liveApi.admin.getStorefrontSections({ section_type: 'tier_icon' });
      const map = {};
      (Array.isArray(list) ? list : []).forEach((s) => {
        const slug = s.content?.tier_slug || s.content?.slug;
        if (slug) map[String(slug).toLowerCase()] = s;
      });
      setRows(map);
    } catch { setRows({}); }
  };
  useEffect(() => { load(); }, []);

  const setRow = (slug, patch) => setRows((r) => ({ ...r, [slug]: { ...(r[slug] || {}), ...patch } }));

  const save = async (slot) => {
    const row = rows[slot.slug] || {};
    const url = row.image_url || row.content?.image_url || '';
    if (!url) { toast({ title: 'Upload an image first', variant: 'destructive' }); return; }
    setBusy(slot.slug);
    try {
      const content = { ...(row.content || {}), tier_slug: slot.slug, image_url: url };
      const body = {
        section_type: 'tier_icon',
        title: `${slot.name} tier icon`,
        image_url: url,
        content,
        is_active: row.is_active !== false,
        sort_order: TIER_SLOTS.findIndex((s) => s.slug === slot.slug),
      };
      if (row.id) await liveApi.admin.updateStorefrontSection(row.id, body);
      else await liveApi.admin.createStorefrontSection({ ...body, key: `tier_icon_${slot.slug}` });
      clearTierIconsCache();
      toast({ title: `✅ ${slot.name} icon saved`, description: 'Live everywhere a tier is shown.' });
      await load();
    } catch (e) { toast({ title: 'Save failed', description: e.message, variant: 'destructive' }); }
    setBusy(null);
  };

  return (
    <div className="space-y-3">
      <p className="text-[11px] text-muted-foreground">
        Each tier has its own image. Upload one per tier — Ember's mark only ever changes Ember.
        Every tier shown across the app (HP card, dashboard, leaderboard, account menu, HP education)
        uses these.
      </p>
      {TIER_SLOTS.map((slot) => {
        const row = rows[slot.slug] || {};
        const url = row.image_url || row.content?.image_url || '';
        return (
          <Card key={slot.slug}>
            <div className="flex items-center gap-2 mb-3">
              <Pill tone="blue">{slot.name.toUpperCase()}</Pill>
              <span className="text-[10px] text-muted-foreground uppercase tracking-wide">{slot.hint}</span>
              <div className="ml-auto flex items-center gap-1.5">
                <Toggle checked={row.is_active !== false} onChange={(v) => setRow(slot.slug, { is_active: v })} />
                <span className="text-[10px] text-muted-foreground">Visible</span>
              </div>
            </div>
            <div className="flex items-center gap-3">
              {url ? (
                <img src={url} alt={slot.name} className="w-12 h-12 object-contain shrink-0 rounded-xl bg-muted p-1" />
              ) : (
                <div className="w-12 h-12 shrink-0 rounded-xl bg-muted flex items-center justify-center"><Award className="w-5 h-5 text-muted-foreground" /></div>
              )}
              <div className="flex-1 min-w-0">
                <ImageUploader
                  value={url}
                  onChange={(u) => setRow(slot.slug, { image_url: u, content: { ...(row.content || {}), tier_slug: slot.slug, image_url: u } })}
                  folder="tier_icons"
                  label={`${slot.name} icon`}
                />
              </div>
            </div>
            <button onClick={() => save(slot)} disabled={busy === slot.slug} className="mt-3 flex items-center gap-1 px-3 py-2 rounded-full bg-primary text-white text-xs font-bold disabled:opacity-50">
              <Save className="w-3.5 h-3.5" /> {busy === slot.slug ? 'Saving…' : 'Save'}
            </button>
          </Card>
        );
      })}
    </div>
  );
}