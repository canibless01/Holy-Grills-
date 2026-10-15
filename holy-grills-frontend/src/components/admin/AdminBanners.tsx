import { confirmAction } from '@/lib/confirmAction';
import { bannerSlides, bannerSlidePayload, blankBannerSlide } from '@/lib/bannerSlides';
import { useCampus } from '@/lib/campusContext';
import { useCmsCreateIntent } from '@/lib/useCmsCreateIntent';
import { useIsSuperAdmin } from './SuperAdminGate';
import { useState, useEffect, useCallback, useRef } from 'react';
import { Save, Plus, Trash2 } from 'lucide-react';
import { liveApi } from '@/lib/liveApi';
import { Field, TextInput, Card, Toggle, Pill, Modal } from './AdminShared';
import ImageUploader from './ImageUploader';
import LoadingSpinner from '@/components/LoadingSpinner';
import { toast } from '@/components/ui/use-toast';
import { msg, useMessages } from '@/lib/messages';

const slideLabel = (field) => ({
  eyebrow: msg('FE_ADMIN_BANNERS_EYEBROW_TEXT', 'Eyebrow text'),
  title: msg('FE_CMS_SLIDE_TITLE', 'Slide title'), subtitle: msg('FE_CMS_SLIDE_SUBTITLE', 'Slide subtitle'),
  cta_text: msg('FE_CMS_SLIDE_CTA', 'CTA text'), cta_url: msg('FE_CMS_SLIDE_DESTINATION', 'CTA URL'),
})[field];

const localDateInput = (value) => {
  if (!value) return '';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? '' : new Date(date.getTime() - date.getTimezoneOffset() * 60000).toISOString().slice(0, 16);
};
const dateValue = (value) => value ? new Date(value).toISOString() : null;

export default function AdminBanners({ placement = 'home' }) {
  useMessages();
  const createIntent = useCmsCreateIntent();
  const isSuperAdmin = useIsSuperAdmin();
  const { campusId, adminCampusId, campuses } = useCampus();
  const loadGeneration = useRef(0);
  const [banners, setBanners] = useState([]);
  const [busy, setBusy] = useState(null);
  const [addOpen, setAddOpen] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const [loadError, setLoadError] = useState(false);
  const [draft, setDraft] = useState<{ title: string; eyebrow: string; subtitle: string; cta_text: string; cta_url: string; placement: string; sort_order: number | string; image_url: string; starts_at: string; ends_at: string }>({ title: '', eyebrow: '', subtitle: '', cta_text: '', cta_url: '', placement, sort_order: 0, image_url: '', starts_at: '', ends_at: '' });

  const load = useCallback(async () => {
    const current = ++loadGeneration.current;
    try {
      const all = await liveApi.admin.getBanners();
      const arr = (Array.isArray(all) ? all : [])
        .filter((b) => (b.placement || 'home') === placement)
        .map((b) => ({ ...b, slides: bannerSlides(b) }));
      arr.sort((a, b) => (a.sort_order ?? 0) - (b.sort_order ?? 0));
      if (current !== loadGeneration.current) return;
      setBanners(arr);
      setLoadError(false);
    } catch {
      if (current !== loadGeneration.current) return;
      setLoadError(true);
    }
    setLoaded(true);
  }, [placement, campusId, adminCampusId]);

  useEffect(() => { setLoaded(false); load(); return () => { loadGeneration.current++; }; }, [load]);

  const upd = (id, patch) => setBanners((arr) => arr.map((b) => (b.id === id ? { ...b, ...patch } : b)));

  const save = async (b) => {
    if (b.slides.some((s) => !s.image_url || !s.title.trim() || (!!s.cta_text !== !!s.cta_url))) {
      toast({ title: msg('FE_CMS_SLIDE_REQUIRED', 'Each slide needs an image and title. Set both CTA text and destination, or leave both empty.'), variant: 'destructive' }); return;
    }
    setBusy(b.id);
    try {
      await liveApi.admin.updateBanner(b.id, {
        ...bannerSlidePayload(b.slides, b.metadata || {}), expected_updated_at: b.updated_at,
        is_active: b.is_active, sort_order: Number(b.sort_order) || 0,
        starts_at: b.starts_at || null, ends_at: b.ends_at || null,
      });
      toast({ title: msg('FE_ADMIN_BANNERS_BANNER_SAVED', '✅ Banner saved') });
    } catch (e) {
      setBusy(null);
      toast({ title: msg('FE_ADMIN_BANNERS_SAVE_FAILED', 'Save failed'), description: e.message, variant: 'destructive' });
      return;
    }
    setBusy(null);
    await load();
  };

  const toggleActive = async (b, v) => {
    setBusy(`act-${b.id}`);
    try { await liveApi.admin.updateBanner(b.id, { is_active: v }); await load(); }
    catch (e) { toast({ title: msg('FE_ADMIN_BANNERS_FAILED', 'Failed'), description: e.message, variant: 'destructive' }); }
    setBusy(null);
  };

  const del = async (id) => {
    if (!(await confirmAction({ title: msg('FE_CMS_DELETE_CAROUSEL', 'Delete this carousel from the live site?'), destructive: true }))) return;
    try { await liveApi.admin.deleteBanner(id); toast({ title: msg('FE_ADMIN_BANNERS_DELETED', '✅ Deleted') }); await load(); }
    catch (e) { toast({ title: msg('FE_ADMIN_BANNERS_DELETE_FAILED', 'Delete failed'), description: e.message, variant: 'destructive' }); }
  };

  const move = async (b, dir) => {
    const scoped = banners.filter((x) => x.campus_id === b.campus_id);
    const i = scoped.findIndex((x) => x.id === b.id);
    const j = i + dir;
    if (j < 0 || j >= scoped.length) return;
    const other = scoped[j];
    setBusy(`mv-${b.id}`);
    try {
      await Promise.all([
        liveApi.admin.updateBanner(b.id, { sort_order: other.sort_order ?? j }),
        liveApi.admin.updateBanner(other.id, { sort_order: b.sort_order ?? i }),
      ]);
      await load();
    } catch (e) { toast({ title: msg('FE_ADMIN_BANNERS_REORDER_FAILED', 'Reorder failed'), description: e.message, variant: 'destructive' }); }
    setBusy(null);
  };

  const editSlide = (b, index, patch) => upd(b.id, { slides: b.slides.map((s, i) => i === index ? { ...s, ...patch } : s) });
  const moveSlide = (b, index, dir) => {
    const next = [...b.slides]; const target = index + dir;
    if (target < 0 || target >= next.length) return;
    [next[index], next[target]] = [next[target], next[index]];
    upd(b.id, { slides: next });
  };

  const blankDraft = () => ({ title: '', eyebrow: '', subtitle: '', cta_text: '', cta_url: '', placement, sort_order: 0, image_url: '', starts_at: '', ends_at: '' });

  const create = async () => {
    // POST /storefront/banners requires BOTH `title` and `image_url` as
    // non-empty strings. The create form used to send neither (title was
    // dropped when blank, image_url was never sent at all), so creating a
    // banner failed with "title is required" / "image_url is required" and the
    // only way through was to know to type a title.
    if (!draft.title.trim()) {
      toast({ title: msg('FE_ADMIN_BANNERS_TITLE_REQUIRED', 'Title is required'), description: msg('FE_ADMIN_BANNERS_GIVE_THE_BANNER_A_TITLE_SO_YOU_CAN', 'Give the banner a title so you can tell it apart in this list.'), variant: 'destructive' });
      return;
    }
    if (!draft.image_url.trim()) {
      toast({ title: msg('FE_ADMIN_BANNERS_IMAGE_REQUIRED', 'An image is required'), description: msg('FE_ADMIN_BANNERS_UPLOAD_THE_MAIN_IMAGE_OR_PASTE_AN_IMAGE', 'Upload the main image or paste an image URL before creating.'), variant: 'destructive' });
      return;
    }
    if (!!draft.cta_text !== !!draft.cta_url) { toast({ title: msg('FE_CMS_CTA_PAIR', 'Set both CTA text and destination, or leave both empty.'), variant: 'destructive' }); return; }
    setBusy('create');
    try {
      await liveApi.admin.createBanner(createIntent.body({
        placement, ...bannerSlidePayload([{ ...blankBannerSlide(), ...draft, title: draft.title.trim() }]),
        // Mirror the first slide to legacy columns for older consumers.
        starts_at: dateValue(draft.starts_at), ends_at: dateValue(draft.ends_at),
        sort_order: Number(draft.sort_order) || 0, is_active: true,
      }));
      createIntent.clear();
      setAddOpen(false);
      setDraft(blankDraft());
      await load();
      toast({ title: msg('FE_ADMIN_BANNERS_BANNER_CREATED_ADD_CAROUSEL_IMAGES_BELOW', '✅ Banner created — add slides below') });
    } catch (e) {
      toast({ title: msg('FE_ADMIN_BANNERS_FAILED', 'Failed'), description: e.message, variant: 'destructive' });
    }
    setBusy(null);
  };

  if (!loaded) return <LoadingSpinner label={msg('FE_CMS_BANNER_LOADING_BANNERS', 'Loading banners...')} />;
  if (loadError) return <Card>
    <p role="alert" className="text-sm text-destructive">{msg('FE_ADMIN_STOREFRONT_LOAD_ERROR', 'Storefront content could not be loaded. Retry before making changes.')}</p>
    <button onClick={load} className="mt-3 px-4 py-2 rounded-full bg-primary text-white text-xs font-bold">{msg('FE_ADMIN_STOREFRONT_RETRY', 'Retry')}</button>
  </Card>;

  return (
    <div className="space-y-3">
      <div className="flex justify-between items-center">
        <p className="text-[11px] text-muted-foreground">
          {msg('FE_CMS_CAROUSEL_PLACEMENT', '{placement} carousels — swipeable on the live site.', { placement })}
        </p>
        <button onClick={() => setAddOpen(true)} className="flex items-center gap-1 px-3 py-2 rounded-full bg-primary text-white text-xs font-bold">
          <Plus className="w-4 h-4" /> {msg('FE_CMS_ADD_BANNER', 'Add banner')}
        </button>
      </div>

      {banners.length === 0 ? (
        <Card><p className="text-xs text-muted-foreground text-center py-6">{msg('FE_CMS_NO_BANNERS', 'No {placement} banners yet. Add a banner to create a carousel.', { placement })}</p></Card>
      ) : banners.map((b) => {
        const images = b.slides;
        return (
          <Card key={b.id}>
            {!isSuperAdmin && !b.campus_id && <p className="text-xs text-muted-foreground mb-2">{msg('FE_ADMIN_STOREFRONT_GLOBAL_READ_ONLY', 'Global content is managed by super admins.')}</p>}
            <fieldset disabled={!isSuperAdmin && !b.campus_id}>
            <div className="flex items-center gap-2 mb-3">
              <Pill tone="flame">{(placement || 'banner').toUpperCase()}</Pill>
              <span className="text-[10px] text-muted-foreground">{b.campus_id ? (campuses.find((campus) => campus.id === b.campus_id)?.name || msg('FE_ADMIN_STOREFRONT_CAMPUS_CONTENT', 'Campus content')) : msg('FE_ADMIN_STOREFRONT_GLOBAL_CONTENT', 'Global content')}</span>
              <span className="text-[10px] text-muted-foreground">{msg('FE_CMS_SLIDE_COUNT', '{count} slides', { count: images.length })}</span>
              {(b.is_active === false) && <Pill tone="red">{msg('FE_CMS_INACTIVE', 'Inactive')}</Pill>}
              <div className="ml-auto flex items-center gap-1.5">
                <button type="button" onClick={() => move(b, -1)} className="px-2 py-1 rounded-lg hover:bg-muted text-muted-foreground text-xs">↑</button>
                <button type="button" onClick={() => move(b, 1)} className="px-2 py-1 rounded-lg hover:bg-muted text-muted-foreground text-xs">↓</button>
                <Toggle checked={!!(b.is_active ?? true)} onChange={(v) => toggleActive(b, v)} disabled={busy === `act-${b.id}`} />
              </div>
            </div>

            <p className="text-xs text-muted-foreground mb-3">{msg('FE_CMS_SLIDE_HELP', 'Each slide has its own image, eyebrow, text and action. Save the carousel to publish your changes.')}</p>
            <div className="space-y-4">
              {b.slides.map((slide, index) => <section key={index} aria-label={msg('FE_CMS_SLIDE_NUMBER', 'Slide {number}', { number: index + 1 })} className="rounded-xl border border-border p-3 space-y-2">
                <div className="flex items-center gap-2">
                  <h3 className="font-bold text-sm flex-1">{msg('FE_CMS_SLIDE_NUMBER', 'Slide {number}', { number: index + 1 })}</h3>
                  <button onClick={() => moveSlide(b, index, -1)} disabled={index === 0} aria-label={msg('FE_CMS_MOVE_SLIDE_UP', 'Move slide up')} className="p-2 disabled:opacity-30">↑</button>
                  <button onClick={() => moveSlide(b, index, 1)} disabled={index === b.slides.length - 1} aria-label={msg('FE_CMS_MOVE_SLIDE_DOWN', 'Move slide down')} className="p-2 disabled:opacity-30">↓</button>
                  <button onClick={() => upd(b.id, { slides: b.slides.filter((_, i) => i !== index) })} aria-label={msg('FE_CMS_REMOVE_SLIDE', 'Remove slide')} className="p-2 text-destructive"><Trash2 className="w-4 h-4" /></button>
                </div>
                <ImageUploader value={slide.image_url} onChange={(url) => editSlide(b, index, { image_url: url })} folder={`banners/${placement}`} label={msg('FE_CMS_SLIDE_IMAGE', 'Slide image')} />
                <details><summary className="text-xs text-muted-foreground cursor-pointer">{msg('FE_CMS_MOBILE_CROP', 'Optional crop for phones')}</summary>
                  <ImageUploader value={slide.mobile_image_url} onChange={(url) => editSlide(b, index, { mobile_image_url: url })} folder={`banners/${placement}`} label={msg('FE_CMS_MOBILE_CROP', 'Optional crop for phones')} />
                </details>
                {(['eyebrow', 'title', 'subtitle', 'cta_text', 'cta_url'] as const).map((field) => <Field key={field} label={slideLabel(field)}><TextInput value={slide[field]} onChange={(e) => editSlide(b, index, { [field]: e.target.value })} /></Field>)}
              </section>)}
              <button onClick={() => upd(b.id, { slides: [...b.slides, blankBannerSlide()] })} className="flex items-center gap-1 px-3 py-2 rounded-full border border-primary text-primary text-xs font-bold"><Plus className="w-4 h-4" />{msg('FE_CMS_ADD_SLIDE', 'Add slide')}</button>
            </div>

            <div className="grid grid-cols-2 gap-2 mt-3">
              <Field label={msg('FE_ADMIN_BANNERS_STARTS_AT', 'Starts at')}><TextInput type="datetime-local" value={localDateInput(b.starts_at)} onChange={(e) => upd(b.id, { starts_at: dateValue(e.target.value) })} /></Field>
              <Field label={msg('FE_ADMIN_BANNERS_ENDS_AT', 'Ends at')}><TextInput type="datetime-local" value={localDateInput(b.ends_at)} onChange={(e) => upd(b.id, { ends_at: dateValue(e.target.value) })} /></Field>
            </div>

            <div className="flex items-center gap-2 mt-3">
              <button onClick={() => save(b)} disabled={busy === b.id} className="flex items-center gap-1 px-3 py-2 rounded-full bg-primary text-white text-xs font-bold disabled:opacity-50">
                <Save className="w-3.5 h-3.5" /> {msg('FE_CMS_SAVE', 'Save')}
              </button>
              <button aria-label={msg('FE_CMS_DELETE_CAROUSEL', 'Delete this carousel from the live site?')} onClick={() => del(b.id)} className="p-2 rounded-lg hover:bg-red-50">
                <Trash2 className="w-4 h-4 text-red-500" />
              </button>
            </div>
            </fieldset>
          </Card>
        );
      })}

      <Modal open={addOpen} onClose={() => setAddOpen(false)} title={msg('FE_CMS_ADD_PLACEMENT_BANNER', 'Add {placement} banner', { placement })}>
        <div className="space-y-3">
          <Field label={msg('FE_CMS_BANNER_OVERLAY_TITLE_REQUIRED', 'Overlay title (required)')}><TextInput value={draft.title} onChange={(e) => setDraft({ ...draft, title: e.target.value })} placeholder={msg('FE_CMS_BANNER_FLAME_GRILLED_CAMPUS_FRESH', 'Flame-Grilled, Campus-Fresh')} /></Field>
          <Field label={msg('FE_CMS_BANNER_MAIN_IMAGE_REQUIRED', 'Main image (required)')}>
            <ImageUploader value={draft.image_url} onChange={(url) => setDraft({ ...draft, image_url: url })} folder={`banners/${placement}`} label={msg('FE_CMS_BANNER_MAIN_IMAGE', 'main image')} />
          </Field>
          {<Field label={msg('FE_ADMIN_BANNERS_EYEBROW_TEXT', "Eyebrow text")}><TextInput value={draft.eyebrow} onChange={(e) => setDraft({ ...draft, eyebrow: e.target.value })} placeholder={msg('FE_ADMIN_BANNERS_FRESH_FROM_YOUR_CAMPUS_GRILL', "Fresh from your campus grill")} maxLength={240} /></Field>}
          <Field label={msg('FE_CMS_BANNER_OVERLAY_SUBTITLE', 'Overlay subtitle')}><TextInput value={draft.subtitle} onChange={(e) => setDraft({ ...draft, subtitle: e.target.value })} placeholder={msg('FE_CMS_BANNER_ORDER_FRESH_MEALS_IN_MINUTES', 'Order fresh meals in minutes')} /></Field>
          <div className="grid grid-cols-2 gap-3">
            <Field label={msg('FE_CMS_BANNER_CTA_TEXT', 'CTA text')}><TextInput value={draft.cta_text} onChange={(e) => setDraft({ ...draft, cta_text: e.target.value })} placeholder={msg('FE_CMS_BANNER_ORDER_NOW', 'Order now')} /></Field>
            <Field label={msg('FE_CMS_BANNER_CTA_URL', 'CTA URL')}><TextInput value={draft.cta_url} onChange={(e) => setDraft({ ...draft, cta_url: e.target.value })} placeholder={msg('FE_CMS_BANNER_MENU', '/menu')} /></Field>
          </div>
          <div className="grid grid-cols-2 gap-2">
            <Field label={msg('FE_ADMIN_BANNERS_STARTS_AT', 'Starts at')}><TextInput type="datetime-local" value={draft.starts_at} onChange={(e) => setDraft({ ...draft, starts_at: e.target.value })} /></Field>
            <Field label={msg('FE_ADMIN_BANNERS_ENDS_AT', 'Ends at')}><TextInput type="datetime-local" value={draft.ends_at} onChange={(e) => setDraft({ ...draft, ends_at: e.target.value })} /></Field>
          </div>
          <Field label={msg('FE_CMS_BANNER_SORT_ORDER', 'Sort order')}><TextInput type="number" value={draft.sort_order} onChange={(e) => setDraft({ ...draft, sort_order: e.target.value })} /></Field>
          <button onClick={create} disabled={busy === 'create'} className="w-full py-3 rounded-full bg-gradient-cta text-white font-bold text-sm disabled:opacity-50">
            {busy === 'create' ? msg('FE_CMS_CREATING_BANNER', 'Creating...') : msg('FE_CMS_CREATE_BANNER', 'Create banner')}
          </button>
        </div>
      </Modal>
    </div>
  );
}
