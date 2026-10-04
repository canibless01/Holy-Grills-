import { useState, useEffect, useCallback } from 'react';
import { Save, Plus, Trash2, Image as ImageIcon, X } from 'lucide-react';
import { liveApi } from '@/lib/liveApi';
import { Field, TextInput, Card, Toggle, Pill, Modal } from './AdminShared';
import ImageUploader from './ImageUploader';
import LoadingSpinner from '@/components/LoadingSpinner';
import { toast } from '@/components/ui/use-toast';

// Dedicated carousel-banner manager (POST/PATCH/DELETE /storefront/banners,
// POST /storefront/banners/:id/image). Each banner holds an `images` array —
// the swipeable carousel shown on the homepage. This is separate from the
// sections-based hero/promo CMS: banners are multi-image carousels, sections
// are single-image blocks.
//
// `placement` filters which banners this instance manages:
//   'hero'   → homepage hero carousel
//   'home'   → homepage mid-page banners
//   'menu'   → menu page banners
//   'checkout' → checkout banners
export default function AdminBanners({ placement = 'home' }) {
  const [banners, setBanners] = useState([]);
  const [busy, setBusy] = useState(null);
  const [addOpen, setAddOpen] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const [draft, setDraft] = useState<{ title: string; subtitle: string; cta_text: string; cta_url: string; placement: string; sort_order: number | string }>({ title: '', subtitle: '', cta_text: '', cta_url: '', placement, sort_order: 0 });

  const load = useCallback(async () => {
    try {
      const all = await liveApi.admin.getBanners();
      const arr = (Array.isArray(all) ? all : []).filter((b) => (b.placement || 'home') === placement);
      arr.sort((a, b) => (a.sort_order ?? 0) - (b.sort_order ?? 0));
      setBanners(arr);
    } catch {
      setBanners([]);
    }
    setLoaded(true);
  }, [placement]);

  useEffect(() => { load(); }, [load]);

  const upd = (id, patch) => setBanners((arr) => arr.map((b) => (b.id === id ? { ...b, ...patch } : b)));

  const save = async (b) => {
    setBusy(b.id);
    try {
      await liveApi.admin.updateBanner(b.id, {
        title: b.title, subtitle: b.subtitle, cta_text: b.cta_text,
        cta_url: b.cta_url, is_active: b.is_active, sort_order: Number(b.sort_order) || 0,
      });
      toast({ title: '✅ Banner saved' });
    } catch (e) {
      toast({ title: 'Save failed', description: e.message, variant: 'destructive' });
    }
    setBusy(null);
    await load();
  };

  const toggleActive = async (b, v) => {
    setBusy(`act-${b.id}`);
    try { await liveApi.admin.updateBanner(b.id, { is_active: v }); await load(); }
    catch (e) { toast({ title: 'Failed', description: e.message, variant: 'destructive' }); }
    setBusy(null);
  };

  const del = async (id) => {
    if (!confirm('Delete this banner? Its carousel will be removed from the live site.')) return;
    try { await liveApi.admin.deleteBanner(id); toast({ title: '✅ Deleted' }); await load(); }
    catch (e) { toast({ title: 'Delete failed', description: e.message, variant: 'destructive' }); }
  };

  const move = async (b, dir) => {
    const i = banners.findIndex((x) => x.id === b.id);
    const j = i + dir;
    if (j < 0 || j >= banners.length) return;
    const other = banners[j];
    setBusy(`mv-${b.id}`);
    try {
      await Promise.all([
        liveApi.admin.updateBanner(b.id, { sort_order: other.sort_order ?? j }),
        liveApi.admin.updateBanner(other.id, { sort_order: b.sort_order ?? i }),
      ]);
      await load();
    } catch (e) { toast({ title: 'Reorder failed', description: e.message, variant: 'destructive' }); }
    setBusy(null);
  };

  // Add an image to this banner's carousel via the dedicated image endpoint.
  const addImage = async (b, url) => {
    if (!url) return;
    setBusy(`img-${b.id}`);
    try {
      await liveApi.admin.updateBannerImage(b.id, { image_url: url });
      toast({ title: '✅ Image added to carousel' });
      await load();
    } catch (e) {
      toast({ title: 'Image add failed', description: e.message, variant: 'destructive' });
    }
    setBusy(null);
  };

  // Remove a single image from the carousel — PATCH the full images array
  // minus the removed index (no dedicated delete-image endpoint).
  const removeImage = async (b, idx) => {
    const images = Array.isArray(b.images) ? b.images : [];
    const next = images.filter((_, i) => i !== idx);
    setBusy(`rmimg-${b.id}`);
    try {
      await liveApi.admin.updateBanner(b.id, { images: next });
      toast({ title: '✅ Image removed' });
      await load();
    } catch (e) {
      toast({ title: 'Remove failed', description: e.message, variant: 'destructive' });
    }
    setBusy(null);
  };

  const create = async () => {
    setBusy('create');
    try {
      await liveApi.admin.createBanner({
        placement, title: draft.title || undefined, subtitle: draft.subtitle || undefined,
        cta_text: draft.cta_text || undefined, cta_url: draft.cta_url || undefined,
        sort_order: Number(draft.sort_order) || 0, is_active: true, images: [],
      });
      setAddOpen(false);
      setDraft({ title: '', subtitle: '', cta_text: '', cta_url: '', placement, sort_order: 0 });
      await load();
      toast({ title: '✅ Banner created — add carousel images below' });
    } catch (e) {
      toast({ title: 'Failed', description: e.message, variant: 'destructive' });
    }
    setBusy(null);
  };

  if (!loaded) return <LoadingSpinner label="Loading banners..." />;

  return (
    <div className="space-y-3">
      <div className="flex justify-between items-center">
        <p className="text-[11px] text-muted-foreground">
          {placement === 'hero' ? 'Homepage hero' : placement === 'home' ? 'Homepage mid-page' : placement === 'menu' ? 'Menu page' : 'Checkout'} carousels — swipeable on the live site.
        </p>
        <button onClick={() => setAddOpen(true)} className="flex items-center gap-1 px-3 py-2 rounded-full bg-primary text-white text-xs font-bold">
          <Plus className="w-4 h-4" /> Add banner
        </button>
      </div>

      {banners.length === 0 ? (
        <Card><p className="text-xs text-muted-foreground text-center py-6">No {placement} banners yet. Click "Add banner" to create a carousel.</p></Card>
      ) : banners.map((b) => {
        const images = Array.isArray(b.images) ? b.images : [];
        return (
          <Card key={b.id}>
            <div className="flex items-center gap-2 mb-3">
              <Pill tone="flame">{(placement || 'banner').toUpperCase()}</Pill>
              <span className="text-[10px] text-muted-foreground">{images.length} image{images.length !== 1 ? 's' : ''}</span>
              <div className="ml-auto flex items-center gap-1.5">
                <button type="button" onClick={() => move(b, -1)} className="px-2 py-1 rounded-lg hover:bg-muted text-muted-foreground text-xs">↑</button>
                <button type="button" onClick={() => move(b, 1)} className="px-2 py-1 rounded-lg hover:bg-muted text-muted-foreground text-xs">↓</button>
                <Toggle checked={!!(b.is_active ?? true)} onChange={(v) => toggleActive(b, v)} disabled={busy === `act-${b.id}`} />
              </div>
            </div>

            {/* Carousel image thumbnails — swipeable preview */}
            {images.length > 0 && (
              <div className="flex gap-2 overflow-x-auto scrollbar-hide pb-2 mb-3">
                {images.map((img, idx) => (
                  <div key={idx} className="relative shrink-0 w-28 h-20 rounded-xl overflow-hidden border border-border group">
                    <img src={typeof img === 'string' ? img : img.url} alt={`Slide ${idx + 1}`} className="w-full h-full object-cover" />
                    <button
                      onClick={() => removeImage(b, idx)}
                      disabled={busy === `rmimg-${b.id}`}
                      className="absolute top-1 right-1 w-5 h-5 rounded-full bg-black/60 text-white flex items-center justify-center opacity-0 group-hover:opacity-100 transition disabled:opacity-30"
                      title="Remove image"
                    >
                      <X className="w-3 h-3" />
                    </button>
                    <span className="absolute bottom-1 left-1 text-[9px] font-bold text-white bg-black/50 px-1.5 rounded">{idx + 1}</span>
                  </div>
                ))}
              </div>
            )}

            {/* Add image to carousel */}
            <div className="mb-3">
              <p className="text-[10px] font-bold text-muted-foreground uppercase tracking-wide mb-1.5 flex items-center gap-1">
                <ImageIcon className="w-3 h-3" /> Add image to carousel
              </p>
              <ImageUploader
                value=""
                onChange={(url) => addImage(b, url)}
                folder={`banners/${placement}`}
                label="carousel image"
              />
            </div>

            {/* Text + CTA */}
            <input value={b.title || ''} onChange={(e) => upd(b.id, { title: e.target.value })} className="w-full mb-2 p-2 rounded-lg border border-border text-sm font-bold" placeholder="Overlay title" />
            <input value={b.subtitle || ''} onChange={(e) => upd(b.id, { subtitle: e.target.value })} className="w-full mb-2 p-2 rounded-lg border border-border text-sm" placeholder="Overlay subtitle" />
            <div className="grid grid-cols-2 gap-2">
              <input value={b.cta_text || ''} onChange={(e) => upd(b.id, { cta_text: e.target.value })} className="p-2 rounded-lg border border-border text-sm" placeholder="CTA text" />
              <input value={b.cta_url || ''} onChange={(e) => upd(b.id, { cta_url: e.target.value })} className="p-2 rounded-lg border border-border text-sm" placeholder="CTA URL" />
            </div>

            <div className="flex items-center gap-2 mt-3">
              <button onClick={() => save(b)} disabled={busy === b.id} className="flex items-center gap-1 px-3 py-2 rounded-full bg-primary text-white text-xs font-bold disabled:opacity-50">
                <Save className="w-3.5 h-3.5" /> Save
              </button>
              <button onClick={() => del(b.id)} className="p-2 rounded-lg hover:bg-red-50">
                <Trash2 className="w-4 h-4 text-red-500" />
              </button>
            </div>
          </Card>
        );
      })}

      <Modal open={addOpen} onClose={() => setAddOpen(false)} title={`Add ${placement === 'hero' ? 'hero' : placement} banner`}>
        <div className="space-y-3">
          <div className="rounded-xl bg-muted p-3 text-xs text-muted-foreground">
            Create the banner, then add carousel images to it. Each image becomes a swipeable slide on the live site.
          </div>
          <Field label="Overlay title"><TextInput value={draft.title} onChange={(e) => setDraft({ ...draft, title: e.target.value })} placeholder="Flame-Grilled, Campus-Fresh" /></Field>
          <Field label="Overlay subtitle"><TextInput value={draft.subtitle} onChange={(e) => setDraft({ ...draft, subtitle: e.target.value })} placeholder="Order fresh meals in minutes" /></Field>
          <div className="grid grid-cols-2 gap-3">
            <Field label="CTA text"><TextInput value={draft.cta_text} onChange={(e) => setDraft({ ...draft, cta_text: e.target.value })} placeholder="Order now" /></Field>
            <Field label="CTA URL"><TextInput value={draft.cta_url} onChange={(e) => setDraft({ ...draft, cta_url: e.target.value })} placeholder="/menu" /></Field>
          </div>
          <Field label="Sort order"><TextInput type="number" value={draft.sort_order} onChange={(e) => setDraft({ ...draft, sort_order: e.target.value })} /></Field>
          <button onClick={create} disabled={busy === 'create'} className="w-full py-3 rounded-full bg-gradient-cta text-white font-bold text-sm disabled:opacity-50">
            {busy === 'create' ? 'Creating...' : 'Create banner'}
          </button>
        </div>
      </Modal>
    </div>
  );
}