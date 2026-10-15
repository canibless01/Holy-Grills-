import { useNavigate } from 'react-router-dom';
import { openCmsDestination } from '@/lib/safeNavigation';
import { useCampus } from '@/lib/campusContext';
import { useState, useEffect } from 'react';
import { Utensils, ChevronRight } from 'lucide-react';
import CateringRequestModal from '@/components/events/CateringRequestModal';
import { getStorefrontSections } from '@/lib/storefrontMockData';
import { useHolyGrill } from '@/lib/HolyGrillContext';

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
  const { campusId } = useCampus();
  const navigate = useNavigate();
  const [section, setSection] = useState(null);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setSection(null);
    setLoading(true);
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
  }, [campusId]);

  if (loading || !section) return null;

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
            onClick={() => { const destination = content.cta_url || content.cta_link || section?.cta_url; if (destination) openCmsDestination(destination, navigate); else setShowForm(true); }}
            className="mt-3 w-full py-2.5 rounded-full bg-gradient-cta text-white text-xs font-bold flex items-center justify-center gap-1.5"
          >
            {cta} <ChevronRight className="w-4 h-4" />
          </button>
          {!isAuthenticated && (
            <p className="text-[10px] text-muted-foreground mt-2 text-center">No account needed.</p>
          )}
        </div>
      </div>

      <CateringRequestModal open={showForm} onClose={() => setShowForm(false)} />
    </>
  );
}