import { useState, useEffect } from 'react';
import { Utensils, ChevronRight, X, Loader2 } from 'lucide-react';
import { liveApi } from '@/lib/liveApi';
import { getStorefrontSections } from '@/lib/storefrontMockData';
import { useHolyGrill } from '@/lib/HolyGrillContext';
import { toast } from '@/components/ui/use-toast';
import { msg } from '@/lib/messages';

/**
 * CateringCard — storefront-driven Catering card on the Home page, visible to
 * guests too. The content (image, title, description, CTA) comes from an admin-
 * uploaded storefront section of section_type='service' (see Confirmed Business
 * Logic · Catering). Renders nothing if no such section is configured.
 *
 * The CTA opens an inline request form that POSTs /events/catering-requests
 * (public submissions allowed).
 */
export default function CateringCard() {
  const { isAuthenticated } = useHolyGrill();
  const [section, setSection] = useState(null);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({ name: '', phone: '', email: '', event_date: '', guests: '', details: '' });
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const sections = await getStorefrontSections('catering');
        if (cancelled) return;
        const s = Array.isArray(sections) ? sections[0] : null;
        setSection(s || null);
      } catch { /* ignore */ }
      if (!cancelled) setLoading(false);
    })();
    return () => { cancelled = true; };
  }, []);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!form.name.trim() || !form.phone.trim()) { toast({ title: msg('FE_CATERING_CARD_NAME_PHONE_REQUIRED', 'Name & phone required'), variant: 'destructive' }); return; }
    setSubmitting(true);
    try {
      await liveApi.events.cateringRequest({
        name: form.name.trim(),
        phone: form.phone.trim(),
        email: form.email.trim() || undefined,
        event_date: form.event_date || undefined,
        guests: form.guests ? Number(form.guests) : undefined,
        details: form.details.trim() || undefined,
      });
      toast({ title: msg('FE_CATERING_CARD_REQUEST_SENT', '🍽️ Request sent'), description: msg('FE_CATERING_CARD_OUR_TEAM_WILL_REACH_OUT_SHORTLY', 'Our team will reach out shortly.') });
      setShowForm(false);
      setForm({ name: '', phone: '', email: '', event_date: '', guests: '', details: '' });
    } catch (err) {
      toast({ title: msg('FE_CATERING_CARD_REQUEST_FAILED', 'Request failed'), description: err.message, variant: 'destructive' });
    }
    setSubmitting(false);
  };

  if (loading) return null;

  const content = section?.content || section?.data || {};
  const image = content.image_url || content.image || section?.image_url;
  const title = content.title || section?.title || 'Your crowd. Our fire.';
  // The CMS form writes subtitle + cta_text; storefront.py merges both into
  // `content`, so those are the keys that actually arrive.
  const description = content.description || content.body || content.subtitle || section?.subtitle || 'Tell us the date.';
  const cta = content.cta_label || content.cta_text || content.cta || section?.cta_text || 'Request catering';

  return (
    <>
      <div id="catering" className="rounded-2xl bg-card border border-border overflow-hidden hover:border-primary/20 hover:shadow-glow transition-all">
        {image && (
          <div className="relative h-32 sm:h-40 bg-secondary overflow-hidden">
            <img src={image} alt={title} loading="lazy" className="w-full h-full object-cover" />
          </div>
        )}
        <div className="p-4">
          {!image && (
            <div className="flex items-center gap-2 mb-2">
              <div className="w-8 h-8 rounded-xl bg-primary/5 flex items-center justify-center"><Utensils className="w-4 h-4 text-primary" /></div>
              <span className="text-[10px] font-bold uppercase tracking-wide text-primary">Catering</span>
            </div>
          )}
          <h3 className="font-heading font-bold text-base text-foreground">{title}</h3>
          <p className="text-xs text-muted-foreground mt-1 leading-relaxed">{description}</p>
          <button
            onClick={() => setShowForm(true)}
            className="mt-3 w-full py-2.5 rounded-full bg-gradient-cta text-white text-xs font-bold flex items-center justify-center gap-1.5"
          >
            {cta} <ChevronRight className="w-4 h-4" />
          </button>
          {!isAuthenticated && (
            <p className="text-[10px] text-muted-foreground mt-2 text-center">No account needed.</p>
          )}
        </div>
      </div>

      {showForm && (
        <div className="fixed inset-0 z-50 bg-black/70 backdrop-blur-lg flex items-end sm:items-center justify-center p-4" onClick={() => !submitting && setShowForm(false)}>
          <form onSubmit={handleSubmit} className="bg-card rounded-2xl p-6 w-full max-w-md space-y-3 animate-slide-up" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between">
              <h3 className="font-heading font-bold text-lg text-foreground flex items-center gap-2"><Utensils className="w-5 h-5 text-primary" /> Catering Request</h3>
              <button type="button" onClick={() => setShowForm(false)}><X className="w-5 h-5 text-muted-foreground" /></button>
            </div>
            <input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="Your name" className="w-full p-3 rounded-xl border border-border text-sm focus:outline-none focus:border-primary/40" />
            <input value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} placeholder="Phone (08012345678)" className="w-full p-3 rounded-xl border border-border text-sm focus:outline-none focus:border-primary/40" />
            <input value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} placeholder="Email (optional)" className="w-full p-3 rounded-xl border border-border text-sm focus:outline-none focus:border-primary/40" />
            <div className="grid grid-cols-2 gap-2">
              <input type="date" value={form.event_date} onChange={(e) => setForm({ ...form, event_date: e.target.value })} className="w-full p-3 rounded-xl border border-border text-sm focus:outline-none focus:border-primary/40" />
              <input type="number" value={form.guests} onChange={(e) => setForm({ ...form, guests: e.target.value })} placeholder="Guests" className="w-full p-3 rounded-xl border border-border text-sm focus:outline-none focus:border-primary/40" />
            </div>
            <textarea value={form.details} onChange={(e) => setForm({ ...form, details: e.target.value })} placeholder="Tell us about your event…" rows={3} className="w-full p-3 rounded-xl border border-border text-sm resize-none focus:outline-none focus:border-primary/40" />
            <button type="submit" disabled={submitting} className="w-full py-3 rounded-full bg-gradient-cta text-white font-bold text-sm flex items-center justify-center gap-2 disabled:opacity-50">
              {submitting ? <><Loader2 className="w-4 h-4 animate-spin" /> Sending…</> : 'Send request'}
            </button>
          </form>
        </div>
      )}
    </>
  );
}