import React, { useState, useEffect } from 'react';
import { Save, Plus, Trash2, Image, Mail, Flame, Tag, Quote, Share2, Heart, Sparkles, Clock, Pencil, Utensils, Award, BookOpen } from 'lucide-react';
import { liveApi as mockApi } from '@/lib/liveApi';
import { formatDate } from '@/lib/hgUtils';
import LoadingSpinner from '@/components/LoadingSpinner';
import { Field, TextInput, Card, Toggle, Pill, Modal } from './AdminShared';
import ImageUploader from './ImageUploader';
import AdminOperatingHours from './AdminOperatingHours';
import AdminBanners from './AdminBanners';
import AdminTierIcons from './AdminTierIcons';
import { toast } from '@/components/ui/use-toast';

// The storefront CMS is split into clear groups so admins always know which
// surface they're editing. Two APIs back it:
//   /storefront/banners  → multi-image swipeable carousels (hero + banners tabs)
//   /storefront/sections → single-image text blocks (promos, testimonials, share)
const TAB_GROUPS = [
  {
    label: 'Carousels',
    tabs: [
      { id: 'hero', label: 'Hero', icon: Flame, kind: 'banners_api', placement: 'hero', desc: 'Homepage hero carousel — swipeable images with overlay text + CTA.' },
      { id: 'home_banners', label: 'Banners', icon: Image, kind: 'banners_api', placement: 'home', desc: 'Homepage mid-page carousel banners — swipeable multi-image.' },
    ],
  },
  {
    label: 'CMS Sections',
    tabs: [
      { id: 'promo', label: 'Promos', icon: Tag, kind: 'section', desc: 'Promo blocks — single image + text + CTA.' },
      { id: 'testimonial', label: 'Testimonials', icon: Quote, kind: 'section', desc: 'Student reviews shown on the homepage.' },
      { id: 'share_template', label: 'Share Templates', icon: Share2, kind: 'section', desc: 'Base images students overlay their name + HP on.' },
      { id: 'whats_inside', label: "What's Inside", icon: Sparkles, kind: 'section', desc: 'Logged-out feature slider — portrait cards with overlaid text.' },
      { id: 'how_its_made', label: "How It's Made", icon: Flame, kind: 'section', desc: 'Process-stage slider — each slide is a step from raw to door.' },
      { id: 'catering', label: 'Catering', icon: Utensils, kind: 'section', desc: 'Catering card — single image + text + CTA on the homepage.' },
      { id: 'our_story', label: 'Our Story', icon: BookOpen, kind: 'section', desc: 'Our Story page — hero image + title + caption.' },
      { id: 'popup', label: 'Popup Flyer', icon: Sparkles, kind: 'section', desc: 'Flyer popup shown once per visit on the homepage — image + CTA button to a page. Re-shows after re-login.' },
      { id: 'tier_icon', label: 'Tier Icons', icon: Award, kind: 'tier_icons', desc: 'One image per membership tier — used everywhere a tier is shown.' },
    ],
  },
  {
    label: 'Community',
    tabs: [
      { id: 'early_supporter', label: 'Early Supporters', icon: Heart, kind: 'supporters' },
      { id: 'newsletter', label: 'Newsletter', icon: Mail, kind: 'newsletter' },
    ],
  },
  {
    label: 'Operations',
    tabs: [
      { id: 'hours', label: 'Hours', icon: Clock, kind: 'hours' },
    ],
  },
];

const ALL_TABS = TAB_GROUPS.flatMap((g) => g.tabs);
const SECTION_TAB_IDS = ['promo', 'testimonial', 'share_template', 'whats_inside', 'how_its_made', 'catering', 'our_story', 'popup'];
// Slider section types — each slide is an image + overlaid title + line +
// destination + optional badge, rendered by StorefrontSlider.
const SLIDER_TAB_IDS = ['whats_inside', 'how_its_made'];

// Share-card slots — each share surface has its own uploaded base image, on the
// same share_template API but under its own `key`, so one upload point feeds
// different places in the app.
const SHARE_SLOTS = [
  { key: 'order_share', label: 'Order confirmation' },
  { key: 'hall_of_fame_share', label: 'Hall of Fame' },
  { key: 'referral_share', label: 'Referral invite' },
  { key: 'share_template', label: 'General / default' },
];

// The backend requires a unique `key` on every storefront section (create AND
// update) — the "key is required" / not-persisting failures came from bodies
// sent without one. Sections created here get a slug of their title.
const slugify = (str) => (str || '').toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '');
const keyFor = (s) => s.key || s.content?.key || (s.section_type === 'share_template'
  ? 'share_template'
  : (slugify(s.title) || `${s.section_type}-${String(s.id).slice(0, 8)}`));

// Real sample content the admin can seed into the live backend (POST /storefront/sections)
// so each segment has data to view and edit — not mock, persisted via the API.
const SAMPLE_SECTIONS = [
  { section_type: 'promo', title: 'Squad Feast — Save Together', subtitle: 'Order with your squad and unlock group discounts on platters.', image_url: 'https://images.unsplash.com/photo-1504674900247-0877df9cc836?w=1200&q=80', cta_text: 'Start a squad', cta_url: '/events', placement: 'home', sort_order: 0 },
  { section_type: 'testimonial', content: { name: 'Omoayena A.', review: 'It was wonderful 😭 I was even so full and it came right to my hostel. The HP rewards keep me coming back!', rating: 5 } },
  { section_type: 'share_template', title: 'Share Template', content: { base_image_url: 'https://images.unsplash.com/photo-1513104890-87103ece8d46?w=1200&q=80', caption_template: 'I just earned {hp} Holy Points at Holy Grills 🔥' } },
  { section_type: 'popup', title: 'Welcome to Holy Grills 🔥', subtitle: 'Your first order comes with a free Holy Fries.', image_url: 'https://images.unsplash.com/photo-1567620832903-9fc6debc209f?w=1200&q=80', cta_text: 'Order now', cta_url: '/menu', placement: 'home', sort_order: 0 },
];

const blankSection = (type) => ({ section_type: type, title: '', subtitle: '', image_url: '', cta_text: '', cta_url: '', placement: 'home', sort_order: 0, testimonial_name: '', testimonial_review: '', testimonial_rating: 5, caption_template: '', badge: '', share_key: 'share_template' });

export default function AdminStorefront() {
  const [tab, setTab] = useState('hero');
  const [sections, setSections] = useState([]);
  const [supporters, setSupporters] = useState([]);
  const [subscribers, setSubscribers] = useState([]);
  const [busy, setBusy] = useState(null);
  const [seeding, setSeeding] = useState(false);
  const [addOpen, setAddOpen] = useState(false);
  const [supporterName, setSupporterName] = useState('');
  const [supporterPhoto, setSupporterPhoto] = useState('');
  const [supporterNote, setSupporterNote] = useState('');
  const [supporterSocial, setSupporterSocial] = useState('');
  const [supporterOrder, setSupporterOrder] = useState(0);
  const [editSupporter, setEditSupporter] = useState(null); // supporter being edited
  const [newSection, setNewSection] = useState(blankSection('hero'));
  const [loaded, setLoaded] = useState(false);

  const load = async () => {
    try {
      const [b, s, n] = await Promise.all([mockApi.admin.getStorefrontSections(), mockApi.admin.getEarlySupporters(), mockApi.admin.getNewsletterSubscribers()]);
      setSections(Array.isArray(b) ? [...b].sort((a, c) => (a.sort_order ?? 0) - (c.sort_order ?? 0)) : []);
      setSupporters(Array.isArray(s) ? s : []); setSubscribers(Array.isArray(n) ? n : []);
    } catch { setSections([]); }
    setLoaded(true);
  };
  useEffect(() => { load(); }, []);

  const activeTab = ALL_TABS.find((t) => t.id === tab);
  const isSectionType = SECTION_TAB_IDS.includes(tab);
  const isBannersApi = activeTab?.kind === 'banners_api';
  const visible = sections.filter((s) => s.section_type === tab);

  const upd = (id, patch) => setSections((arr) => arr.map((s) => (s.id === id ? { ...s, ...patch } : s)));
  const save = async (s) => {
    setBusy(s.id);
    try {
      // Clean payload: server fields (id, created_at, updated_at…) are
      // stripped and a key is always included — the backend rejects or
      // ignores updates that carry them, which made saves not persist.
      const body = {
        key: keyFor(s),
        section_type: s.section_type,
        title: s.title ?? '',
        subtitle: s.subtitle ?? '',
        image_url: s.image_url ?? '',
        cta_text: s.cta_text ?? '',
        cta_url: s.cta_url ?? '',
        placement: s.placement ?? 'home',
        sort_order: s.sort_order ?? 0,
        is_active: s.is_active ?? true,
        content: s.content ?? {},
      };
      await mockApi.admin.updateStorefrontSection(s.id, body);
      toast({ title: '✅ Section saved' });
    } catch (e) { toast({ title: 'Save failed', description: e.message, variant: 'destructive' }); }
    setBusy(null); await load();
  };
  const move = async (s, dir) => {
    const sameType = sections.filter((x) => x.section_type === s.section_type).sort((a, b) => (a.sort_order ?? 0) - (b.sort_order ?? 0));
    const i = sameType.findIndex((x) => x.id === s.id); const j = i + dir; if (j < 0 || j >= sameType.length) return;
    const other = sameType[j];
    setBusy(`mv-${s.id}`);
    try { await Promise.all([mockApi.admin.updateStorefrontSection(s.id, { key: keyFor(s), sort_order: other.sort_order ?? j }), mockApi.admin.updateStorefrontSection(other.id, { key: keyFor(other), sort_order: s.sort_order ?? i })]); await load(); }
    catch (e) { toast({ title: 'Reorder failed', description: e.message, variant: 'destructive' }); }
    setBusy(null);
  };
  const toggleActive = async (s, v) => { setBusy(`act-${s.id}`); try { await mockApi.admin.updateStorefrontSection(s.id, { key: keyFor(s), is_active: v }); await load(); } catch (e) { toast({ title: 'Failed', description: e.message, variant: 'destructive' }); } setBusy(null); };
  const del = async (id) => { if (!confirm('Delete this storefront section? It will be removed from the live homepage.')) return; try { await mockApi.admin.deleteStorefrontSection(id); toast({ title: '✅ Deleted' }); await load(); } catch (e) { toast({ title: 'Delete failed', description: e.message, variant: 'destructive' }); } };

  const seedSamples = async () => {
    setSeeding(true); let ok = 0;
    for (const sample of SAMPLE_SECTIONS) {
      try {
        const body = { ...sample, is_active: true };
        if (sample.section_type === 'share_template') body.key = 'share_template';
        else body.key = slugify(sample.title || sample.content?.name) || `${sample.section_type}-${Date.now().toString(36)}`;
        if (sample.section_type === 'testimonial') body.title = sample.content.name;
        await mockApi.admin.createStorefrontSection(body); ok++;
      } catch (e) { /* skip duplicates / failures */ }
    }
    toast({ title: `Seeded ${ok} sample section(s)`, description: 'Edit them below to see how each type renders.' });
    setSeeding(false); await load();
  };

  const create = async () => {
    const t = newSection.section_type;
    if (t === 'testimonial') { if (!newSection.testimonial_name || !newSection.testimonial_review) { toast({ title: 'Name and review required', variant: 'destructive' }); return; } }
    else if (t === 'share_template') { if (!newSection.image_url) { toast({ title: 'Base image required', variant: 'destructive' }); return; } }
    else { if (!newSection.title || !newSection.image_url) { toast({ title: 'Title and image required', variant: 'destructive' }); return; } }
    setBusy('create');
    try {
      const body = { section_type: t, placement: newSection.placement || 'home', sort_order: Number(newSection.sort_order) || 0, is_active: true };
      // Key is required by the backend for every section — not just share templates.
      body.key = t === 'share_template'
        ? (newSection.share_key || 'share_template')
        : (slugify(newSection.title || newSection.testimonial_name) || `${t}-${Date.now().toString(36)}`);
      if (t === 'testimonial') { body.title = newSection.testimonial_name; body.content = { name: newSection.testimonial_name, review: newSection.testimonial_review, rating: Number(newSection.testimonial_rating) || 5 }; }
      else if (t === 'share_template') { body.title = newSection.title || 'Share Template'; body.key = newSection.share_key || 'share_template'; body.content = { base_image_url: newSection.image_url, caption_template: newSection.caption_template || '', key: newSection.share_key || 'share_template' }; }
      else { body.title = newSection.title; body.subtitle = newSection.subtitle; body.image_url = newSection.image_url; body.cta_text = newSection.cta_text; body.cta_url = newSection.cta_url; if (SLIDER_TAB_IDS.includes(t) && newSection.badge) body.content = { ...(body.content || {}), badge: newSection.badge }; }
      await mockApi.admin.createStorefrontSection(body);
      setAddOpen(false); setNewSection(blankSection(t)); await load();
    } catch (e) { toast({ title: 'Failed to create', description: e.message, variant: 'destructive' }); }
    setBusy(null);
  };

  // Backend create_early_supporter expects { name, photo_url, social_links, note, sort_order }
  // (NOT full_name). The list returns { id, name, photo_url, social_links, note, sort_order }.
  const addSupporter = async () => {
    if (!supporterName) { toast({ title: 'Name is required', variant: 'destructive' }); return; }
    try {
      await mockApi.admin.addEarlySupporter({ name: supporterName, photo_url: supporterPhoto || undefined, note: supporterNote || undefined, social_links: supporterSocial || undefined, sort_order: Number(supporterOrder) || 0 });
      setSupporterName(''); setSupporterPhoto(''); setSupporterNote(''); setSupporterSocial(''); setSupporterOrder(0);
      setAddOpen(false); await load();
      toast({ title: '✅ Early supporter added' });
    } catch (e) { toast({ title: 'Failed', description: e.message, variant: 'destructive' }); }
  };
  const saveSupporter = async () => {
    if (!editSupporter) return;
    setBusy(`sup-${editSupporter.id}`);
    try {
      const body = { name: editSupporter.name, note: editSupporter.note || undefined, social_links: editSupporter.social_links || undefined, sort_order: Number(editSupporter.sort_order) || 0 };
      if (editSupporter.is_active !== undefined) body.is_active = editSupporter.is_active;
      await mockApi.admin.updateEarlySupporter(editSupporter.id, body);
      if (editSupporter.photo_url && editSupporter.photo_url !== editSupporter._origPhoto) {
        await mockApi.admin.updateEarlySupporterPhoto(editSupporter.id, { photo_url: editSupporter.photo_url });
      }
      setEditSupporter(null);
      toast({ title: '✅ Supporter updated' });
      await load();
    } catch (e) { toast({ title: 'Update failed', description: e.message, variant: 'destructive' }); }
    setBusy(null);
  };
  const removeSupporter = async (id) => { if (!confirm('Remove this early supporter?')) return; await mockApi.admin.removeEarlySupporter(id); await load(); };
  const unsubscribe = async (email) => { setBusy(email); await mockApi.admin.unsubscribeNewsletter({ email }); await load(); setBusy(null); };

  if (!loaded) return <LoadingSpinner label="Loading..." />;

  return (
    <div className="space-y-4">
      {/* Grouped segment chips — each group is a labelled row so the admin
          always knows which surface (carousel / CMS / community / ops) they're on. */}
      <div className="space-y-2">
        {TAB_GROUPS.map((group) => (
          <div key={group.label} className="space-y-1.5">
            <p className="text-[10px] font-extrabold uppercase tracking-wider text-muted-foreground px-1">{group.label}</p>
            <div className="flex gap-2 overflow-x-auto scrollbar-hide pb-1">
              {group.tabs.map((t) => {
                const count = t.id === 'early_supporter' ? supporters.length : t.id === 'newsletter' ? subscribers.length : t.kind === 'banners_api' ? '↗' : sections.filter((s) => s.section_type === t.id).length;
                const Icon = t.icon;
                return (
                  <button key={t.id} onClick={() => setTab(t.id)} className={`flex items-center gap-1.5 px-3.5 py-2 rounded-full text-xs font-bold whitespace-nowrap ${tab === t.id ? 'bg-gradient-cta text-white shadow-glow' : 'bg-white border border-border text-foreground'}`}>
                    <Icon className="w-3.5 h-3.5" /> {t.label} {typeof count === 'number' && <span className={`ml-0.5 text-[10px] ${tab === t.id ? 'text-white/80' : 'text-muted-foreground'}`}>{count}</span>}
                  </button>
                );
              })}
            </div>
          </div>
        ))}
      </div>

      {isBannersApi && (
        <div className="space-y-3">
          {activeTab.desc && <p className="text-[11px] text-muted-foreground">{activeTab.desc}</p>}
          <AdminBanners placement={activeTab.placement} />
        </div>
      )}

      {activeTab?.kind === 'tier_icons' && <AdminTierIcons />}

      {isSectionType && (
        <div className="space-y-3">
          <div className="flex justify-between items-center">
            <p className="text-[11px] text-muted-foreground capitalize">{tab.replace(/_/g, ' ')} sections — render on the live homepage in sort order.</p>
            <div className="flex gap-2">
              {visible.length === 0 && <button onClick={seedSamples} disabled={seeding} className="flex items-center gap-1 px-3 py-2 rounded-full bg-foreground text-white text-xs font-bold disabled:opacity-50"><Sparkles className="w-3.5 h-3.5" /> {seeding ? 'Seeding...' : 'Seed samples'}</button>}
              <button onClick={() => { setNewSection(blankSection(tab)); setAddOpen(true); }} className="flex items-center gap-1 px-3 py-2 rounded-full bg-primary text-white text-xs font-bold"><Plus className="w-4 h-4" /> Add</button>
            </div>
          </div>
          {visible.length === 0 ? (
            <Card><p className="text-xs text-muted-foreground text-center py-6">No {tab.replace(/_/g, ' ')} sections yet. Click "Seed samples" to insert real example sections you can edit, or "Add" to create your own.</p></Card>
          ) : visible.map((s) => (
            <Card key={s.id}>
              <div className="flex items-center gap-2 mb-2">
                <Pill tone="blue">{(s.section_type || 'banner').toUpperCase()}</Pill>
                {s.placement && <span className="text-[10px] text-muted-foreground uppercase tracking-wide">{s.placement}</span>}
                <div className="ml-auto flex items-center gap-1.5">
                  <button type="button" onClick={() => move(s, -1)} className="px-2 py-1 rounded-lg hover:bg-muted text-muted-foreground text-xs" title="Move up">↑</button>
                  <button type="button" onClick={() => move(s, 1)} className="px-2 py-1 rounded-lg hover:bg-muted text-muted-foreground text-xs" title="Move down">↓</button>
                  <Toggle checked={!!(s.is_active ?? s.active)} onChange={(v) => toggleActive(s, v)} disabled={busy === `act-${s.id}`} />
                </div>
              </div>
              {s.section_type === 'testimonial' ? (
                <>
                  <input value={s.title || s.content?.name || ''} onChange={(e) => upd(s.id, { title: e.target.value, content: { ...s.content, name: e.target.value } })} className="w-full mb-2 p-2 rounded-lg border border-border text-sm font-bold" placeholder="Customer name" />
                  <textarea value={s.content?.review || ''} onChange={(e) => upd(s.id, { content: { ...s.content, review: e.target.value } })} rows={2} className="w-full mb-2 p-2 rounded-lg border border-border text-sm" placeholder="Review text" />
                  <div className="flex items-center gap-2"><span className="text-xs text-muted-foreground">Rating</span><input type="number" min={1} max={5} value={s.content?.rating ?? 5} onChange={(e) => upd(s.id, { content: { ...s.content, rating: Number(e.target.value) } })} className="w-16 p-1.5 rounded-lg border border-border text-sm" /></div>
                </>
              ) : s.section_type === 'share_template' ? (
                <>
                  <input value={s.title || ''} onChange={(e) => upd(s.id, { title: e.target.value })} className="w-full mb-2 p-2 rounded-lg border border-border text-sm font-bold" placeholder="Title" />
                  <ImageUploader value={s.content?.base_image_url || s.image_url || ''} onChange={(url) => upd(s.id, { content: { ...s.content, base_image_url: url }, image_url: url })} folder="share_templates" />
                  <textarea value={s.content?.caption_template || ''} onChange={(e) => upd(s.id, { content: { ...s.content, caption_template: e.target.value } })} rows={2} className="w-full mt-2 p-2 rounded-lg border border-border text-sm" placeholder="Caption template — use {hp} for the student's HP" />
                  <select
                    value={s.key || s.content?.key || 'share_template'}
                    onChange={(e) => upd(s.id, { key: e.target.value, content: { ...s.content, key: e.target.value } })}
                    className="w-full mt-2 p-2 rounded-lg border border-border text-sm"
                  >
                    {SHARE_SLOTS.map((slot) => <option key={slot.key} value={slot.key}>{slot.label}</option>)}
                  </select>
                </>
              ) : (
                <>
                  <input value={s.title || ''} onChange={(e) => upd(s.id, { title: e.target.value })} className="w-full mb-2 p-2 rounded-lg border border-border text-sm font-bold" placeholder="Title" />
                  <input value={s.subtitle || ''} onChange={(e) => upd(s.id, { subtitle: e.target.value })} className="w-full mb-2 p-2 rounded-lg border border-border text-sm" placeholder="Subtitle" />
                  <ImageUploader value={s.image_url || ''} onChange={(url) => upd(s.id, { image_url: url })} folder="banners" />
                  {SLIDER_TAB_IDS.includes(s.section_type) && (
                    <input value={s.content?.badge || ''} onChange={(e) => upd(s.id, { content: { ...s.content, badge: e.target.value } })} className="w-full mt-2 p-2 rounded-lg border border-border text-sm" placeholder="Optional badge (e.g. Opening soon)" />
                  )}
                  <div className="grid grid-cols-2 gap-2 mt-2">
                    <input value={s.cta_text || ''} onChange={(e) => upd(s.id, { cta_text: e.target.value })} className="p-2 rounded-lg border border-border text-sm" placeholder="CTA text" />
                    <input value={s.cta_url || ''} onChange={(e) => upd(s.id, { cta_url: e.target.value })} className="p-2 rounded-lg border border-border text-sm" placeholder="CTA URL" />
                  </div>
                </>
              )}
              <div className="flex items-center gap-2 mt-3">
                <button onClick={() => save(s)} disabled={busy === s.id} className="flex items-center gap-1 px-3 py-2 rounded-full bg-primary text-white text-xs font-bold disabled:opacity-50"><Save className="w-3.5 h-3.5" /> Save</button>
                <button onClick={() => del(s.id)} className="p-2 rounded-lg hover:bg-red-50"><Trash2 className="w-4 h-4 text-red-500" /></button>
              </div>
            </Card>
          ))}
        </div>
      )}

      {tab === 'early_supporter' && (
        <div className="space-y-2">
          <div className="flex justify-end"><button onClick={() => { setSupporterName(''); setSupporterPhoto(''); setSupporterNote(''); setSupporterSocial(''); setSupporterOrder(0); setAddOpen(true); }} className="flex items-center gap-1 px-3 py-2 rounded-full bg-primary text-white text-xs font-bold"><Plus className="w-4 h-4" /> Add</button></div>
          {supporters.length === 0 ? <Card><p className="text-xs text-muted-foreground text-center py-6">No early supporters yet.</p></Card> : supporters.map((s) => (
            <Card key={s.id} className="flex items-center gap-3 !p-3">
              {s.photo_url ? (
                <img src={s.photo_url} alt={s.name} className="w-10 h-10 rounded-full object-cover shrink-0" />
              ) : (
                <div className="w-10 h-10 rounded-full bg-primary/10 flex items-center justify-center shrink-0"><Heart className="w-4 h-4 text-primary" /></div>
              )}
              <div className="flex-1 min-w-0">
                <div className="font-bold text-sm text-foreground truncate">{s.name || 'Supporter'}</div>
                <div className="text-xs text-muted-foreground truncate">{s.note || 'No note'}</div>
              </div>
              <span className="text-[10px] text-muted-foreground">#{s.sort_order ?? 0}</span>
              <button onClick={() => setEditSupporter({ ...s, _origPhoto: s.photo_url })} className="p-2 rounded-lg hover:bg-muted"><Pencil className="w-4 h-4 text-muted-foreground" /></button>
              <button onClick={() => removeSupporter(s.id)} className="p-2 rounded-lg hover:bg-red-50"><Trash2 className="w-4 h-4 text-red-500" /></button>
            </Card>
          ))}
        </div>
      )}

      {tab === 'hours' && <AdminOperatingHours />}

      {tab === 'newsletter' && (
        <div className="space-y-2">
          <div className="rounded-xl bg-muted border border-border p-3 text-xs text-muted-foreground flex items-center gap-1.5"><Mail className="w-3.5 h-3.5" /> {subscribers.length} subscribers.</div>
          {subscribers.length === 0 ? <Card><p className="text-xs text-muted-foreground text-center py-6">No newsletter subscribers yet.</p></Card> : subscribers.map((s) => (
            <Card key={s.id} className="flex items-center gap-3 !p-3">
              <div className="w-9 h-9 rounded-full bg-primary/10 text-primary flex items-center justify-center"><Mail className="w-4 h-4" /></div>
              <div className="flex-1 min-w-0"><div className="font-bold text-sm text-foreground truncate">{s.email}</div><div className="text-[11px] text-muted-foreground">{s.full_name || '—'} · via {s.source || '—'} · {formatDate(s.subscribed_at)}</div></div>
              <button onClick={() => unsubscribe(s.email)} disabled={busy === s.email} className="px-3 py-1.5 rounded-full bg-red-50 text-red-600 border border-red-200 text-xs font-bold disabled:opacity-50">Unsubscribe</button>
            </Card>
          ))}
        </div>
      )}

      <Modal open={addOpen && isSectionType} onClose={() => setAddOpen(false)} title={`Create ${tab.replace(/_/g, ' ')} section`}>
        <div className="space-y-3">
          {newSection.section_type === 'testimonial' ? (
            <>
              <Field label="Customer name (required)"><TextInput value={newSection.testimonial_name} onChange={(e) => setNewSection({ ...newSection, testimonial_name: e.target.value })} placeholder="Omoayena A" /></Field>
              <Field label="Review text (required)"><textarea value={newSection.testimonial_review} onChange={(e) => setNewSection({ ...newSection, testimonial_review: e.target.value })} rows={3} className="w-full mt-1 p-2.5 rounded-xl border border-border text-sm" placeholder="It was wonderful 😭..." /></Field>
              <Field label="Rating (1-5)"><TextInput type="number" value={newSection.testimonial_rating} onChange={(e) => setNewSection({ ...newSection, testimonial_rating: e.target.value })} /></Field>
            </>
          ) : newSection.section_type === 'share_template' ? (
            <>
              <div className="rounded-xl bg-muted p-3 text-xs text-muted-foreground">Students' share cards overlay their name and HP on the base image.</div>
              <Field label="Base share image (required)"><ImageUploader value={newSection.image_url} onChange={(url) => setNewSection({ ...newSection, image_url: url })} folder="share_templates" /></Field>
              <Field label="Caption template"><textarea value={newSection.caption_template} onChange={(e) => setNewSection({ ...newSection, caption_template: e.target.value })} rows={2} className="w-full mt-1 p-2.5 rounded-xl border border-border text-sm" placeholder="I just earned {hp} HP at Holy Grills 🔥" /></Field>
              <Field label="Used for">
                <select value={newSection.share_key} onChange={(e) => setNewSection({ ...newSection, share_key: e.target.value })} className="w-full mt-1 p-2.5 rounded-xl border border-border text-sm">
                  {SHARE_SLOTS.map((slot) => <option key={slot.key} value={slot.key}>{slot.label}</option>)}
                </select>
              </Field>
            </>
          ) : (
            <>
              <Field label="Title (required)"><TextInput value={newSection.title} onChange={(e) => setNewSection({ ...newSection, title: e.target.value })} /></Field>
              <Field label="Subtitle"><TextInput value={newSection.subtitle} onChange={(e) => setNewSection({ ...newSection, subtitle: e.target.value })} /></Field>
              <Field label="Image (required)"><ImageUploader value={newSection.image_url} onChange={(url) => setNewSection({ ...newSection, image_url: url })} folder="banners" /></Field>
              {SLIDER_TAB_IDS.includes(newSection.section_type) && (
                <Field label="Optional badge (e.g. Opening soon)"><TextInput value={newSection.badge} onChange={(e) => setNewSection({ ...newSection, badge: e.target.value })} /></Field>
              )}
              <div className="grid grid-cols-2 gap-3">
                <Field label="CTA text"><TextInput value={newSection.cta_text} onChange={(e) => setNewSection({ ...newSection, cta_text: e.target.value })} placeholder="Order now" /></Field>
                <Field label="Destination page"><TextInput value={newSection.cta_url} onChange={(e) => setNewSection({ ...newSection, cta_url: e.target.value })} placeholder="/menu" /></Field>
              </div>
            </>
          )}
          <div className="grid grid-cols-2 gap-3">
            <Field label="Placement"><select value={newSection.placement} onChange={(e) => setNewSection({ ...newSection, placement: e.target.value })} className="w-full mt-1 p-2.5 rounded-xl border border-border text-sm"><option value="home">Home</option><option value="menu">Menu</option><option value="checkout">Checkout</option></select></Field>
            <Field label="Sort order"><TextInput type="number" value={newSection.sort_order} onChange={(e) => setNewSection({ ...newSection, sort_order: e.target.value })} /></Field>
          </div>
          <button onClick={create} disabled={busy === 'create'} className="w-full py-3 rounded-full bg-gradient-cta text-white font-bold text-sm disabled:opacity-50">{busy === 'create' ? 'Creating...' : 'Create Section'}</button>
        </div>
      </Modal>

      <Modal open={addOpen && tab === 'early_supporter'} onClose={() => setAddOpen(false)} title="Add Early Supporter">
        <div className="space-y-3">
          <Field label="Name (required)"><TextInput value={supporterName} onChange={(e) => setSupporterName(e.target.value)} placeholder="Jane Doe" /></Field>
          <Field label="Photo"><ImageUploader value={supporterPhoto} onChange={setSupporterPhoto} folder="early_supporters" label="photo" /></Field>
          <Field label="Note"><textarea value={supporterNote} onChange={(e) => setSupporterNote(e.target.value)} rows={2} className="w-full mt-1 p-2.5 rounded-xl border border-border text-sm" placeholder="A short personal note" /></Field>
          <Field label="Social URL"><TextInput value={supporterSocial} onChange={(e) => setSupporterSocial(e.target.value)} placeholder="https://instagram.com/username" /></Field>
          <Field label="Sort order"><TextInput type="number" value={supporterOrder} onChange={(e) => setSupporterOrder(e.target.value)} /></Field>
          <button onClick={addSupporter} disabled={busy === 'create'} className="w-full py-3 rounded-full bg-gradient-cta text-white font-bold text-sm disabled:opacity-50">Add</button>
        </div>
      </Modal>

      <Modal open={!!editSupporter} onClose={() => setEditSupporter(null)} title="Edit Early Supporter">
        {editSupporter && (
          <div className="space-y-3">
            <Field label="Name"><TextInput value={editSupporter.name || ''} onChange={(e) => setEditSupporter({ ...editSupporter, name: e.target.value })} /></Field>
            <Field label="Photo"><ImageUploader value={editSupporter.photo_url || ''} onChange={(url) => setEditSupporter({ ...editSupporter, photo_url: url })} folder="early_supporters" label="photo" /></Field>
            <Field label="Note"><textarea value={editSupporter.note || ''} onChange={(e) => setEditSupporter({ ...editSupporter, note: e.target.value })} rows={2} className="w-full mt-1 p-2.5 rounded-xl border border-border text-sm" /></Field>
            <Field label="Social URL"><TextInput value={editSupporter.social_links || ''} onChange={(e) => setEditSupporter({ ...editSupporter, social_links: e.target.value })} placeholder="https://instagram.com/username" /></Field>
            <div className="grid grid-cols-2 gap-3">
              <Field label="Sort order"><TextInput type="number" value={editSupporter.sort_order ?? 0} onChange={(e) => setEditSupporter({ ...editSupporter, sort_order: e.target.value })} /></Field>
              <div className="flex items-end gap-2 pb-2">
                <Toggle checked={editSupporter.is_active !== false} onChange={(v) => setEditSupporter({ ...editSupporter, is_active: v })} />
                <span className="text-xs text-muted-foreground">Visible</span>
              </div>
            </div>
            <button onClick={saveSupporter} disabled={busy === `sup-${editSupporter.id}`} className="w-full py-3 rounded-full bg-gradient-cta text-white font-bold text-sm disabled:opacity-50">Save changes</button>
          </div>
        )}
      </Modal>
    </div>
  );
}