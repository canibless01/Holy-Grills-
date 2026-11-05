import { useCmsCreateIntent } from '@/lib/useCmsCreateIntent';
import StaffPanelSkeleton from '@/components/skeletons/StaffPanelSkeleton';
import { useCampus } from '@/lib/campusContext';
import { useIsSuperAdmin } from './SuperAdminGate';
import AdminScopeBadge, { useAdminWriteScope } from './AdminScopeBadge';
import { confirmAction } from '@/lib/confirmAction';
import { useState, useEffect, useRef } from 'react';
import { Save, Award } from 'lucide-react';
import { liveApi } from '@/lib/liveApi';
import { Card, Pill, Toggle } from './AdminShared';
import ImageUploader from './ImageUploader';
import { toast } from '@/components/ui/use-toast';
import { clearTierIconsCache } from '@/lib/tierIcons';
import { msg } from '@/lib/messages';

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
  const createIntent = useCmsCreateIntent();
  const { campusId, adminCampusId, campuses } = useCampus();
  const isSuperAdmin = useIsSuperAdmin();
  const writeScope = useAdminWriteScope();
  const targetScope = isSuperAdmin ? (adminCampusId || null) : campusId;
  const [loadError, setLoadError] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const [rows, setRows] = useState({});
  // Unfiltered tier rows across every scope — powers the global-save warning
  // when a campus already has its own icon for the same tier.
  const [allRows, setAllRows] = useState([]);
  const loadGeneration = useRef(0);
  const [busy, setBusy] = useState(null);

  const load = async () => {
    const current = ++loadGeneration.current;
    try {
      const list = await liveApi.admin.getStorefrontSections({ section_type: 'tier_icon' });
      const map = {};
      (Array.isArray(list) ? list : []).forEach((s) => {
        const slug = s.content?.tier_slug || s.content?.slug || s.slug || s.subtitle || String(s.key || '').replace(/^tier[_-]icon[_-]/, '');
        if (!slug || (s.campus_id !== null && s.campus_id !== targetScope)) return;
        const key = String(slug).toLowerCase();
        if (!map[key] || s.campus_id === targetScope) {
          map[key] = s.campus_id === targetScope ? s : { ...s, id: undefined };
        }
      });
      if (current !== loadGeneration.current) return;
      setAllRows(Array.isArray(list) ? list : []);
      setRows(map);
      setLoadError(false);
    } catch { if (current !== loadGeneration.current) return; setLoadError(true); }
    setLoaded(true);
  };
  useEffect(() => { setRows({}); setLoaded(false); load(); return () => { loadGeneration.current++; }; }, [targetScope]);

  const setRow = (slug, patch) => setRows((r) => ({ ...r, [slug]: { ...(r[slug] || {}), ...patch } }));

  const save = async (slot) => {
    const row = rows[slot.slug] || {};
    const url = row.image_url || row.content?.image_url || '';
    if (!url) { toast({ title: msg('FE_ADMIN_TIER_ICONS_UPLOAD_AN_IMAGE_FIRST', 'Upload an image first'), variant: 'destructive' }); return; }
    // Creating a global icon while one or more campuses already override this
    // tier: those campuses keep their own artwork, so make that explicit.
    if (!row.id && writeScope.isGlobal) {
      const overrides = allRows.filter((s) => {
        const slug = String(s.content?.tier_slug || s.content?.slug || String(s.key || '').replace(/^tier[_-]icon[_-]/, '')).toLowerCase();
        return slug === slot.slug && s.campus_id;
      });
      if (overrides.length) {
        const names = [...new Set(overrides.map((s) => campuses.find((c) => c.id === s.campus_id)?.name).filter(Boolean))];
        const proceed = await confirmAction({
          title: msg('FE_ADMIN_SCOPE_GLOBAL_OVERRIDE_TITLE', 'Campus-specific version exists'),
          body: msg(
            'FE_ADMIN_SCOPE_TIER_GLOBAL_OVERRIDE_BODY',
            '{names} already has its own {tier} icon and keeps showing it. This global icon only applies where no campus icon exists. Save globally anyway?',
            { names: names.join(', ') || msg('FE_ADMIN_SCOPE_ANOTHER_CAMPUS', 'Another campus'), tier: slot.name },
          ),
          confirmLabel: msg('FE_ADMIN_SCOPE_SAVE_GLOBAL_ANYWAY', 'Save global anyway'),
        });
        if (!proceed) return;
      }
    }
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
      else await liveApi.admin.createStorefrontSection(createIntent.body({ ...body, key: `tier_icon_${slot.slug}` }));
      createIntent.clear();
      clearTierIconsCache();
      toast({ title: msg('FE_ADMIN_TIER_ICONS_NAME_ICON_SAVED', '✅ {name} icon saved', { name: slot.name }), description: msg('FE_ADMIN_TIER_ICONS_LIVE_EVERYWHERE_A_TIER_IS_SHOWN', 'Live everywhere a tier is shown.') });
      await load();
    } catch (e) { toast({ title: msg('FE_ADMIN_TIER_ICONS_SAVE_FAILED', 'Save failed'), description: e.message, variant: 'destructive' }); }
    setBusy(null);
  };

  if (!loaded) return <StaffPanelSkeleton />;
  if (loadError) return <Card>
    <p role="alert" className="text-sm text-destructive">{msg('FE_ADMIN_STOREFRONT_LOAD_ERROR', 'Storefront content could not be loaded. Retry before making changes.')}</p>
    <button onClick={load} className="mt-3 px-4 py-2 rounded-full bg-primary text-white text-xs font-bold">{msg('FE_ADMIN_STOREFRONT_RETRY', 'Retry')}</button>
  </Card>;

  return (
    <div className="space-y-3">
      <AdminScopeBadge />
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
                <span className="w-12 h-12 shrink-0 rounded-xl bg-muted p-1 inline-flex items-center justify-center"><img src={url} alt={slot.name} loading="lazy" decoding="async" className="w-full h-full object-contain" /></span>
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