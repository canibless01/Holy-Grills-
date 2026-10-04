import { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { X } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { getStorefrontSections } from '@/lib/storefrontMockData';
import { openCmsDestination } from '@/lib/safeNavigation';

/**
 * PromoFlyerPopup — a flyer popup shown once per login session on the homepage.
 *
 * The flyer image IS the call-to-action: the entire rectangle is the uploaded
 * image, and tapping anywhere on it navigates to the destination. A small CTA
 * button floats as an overlay on top of the image (a separate box, not inside
 * the image) — tapping it goes to the same place. A circular close icon sits
 * beneath the modal, centred.
 *
 * Content (flyer image + cta_text + destination) comes from an admin-uploaded
 * storefront section of section_type='popup'. Data flows through the live API
 * (getStorefrontSections calls liveApi.storefront.getSections first; mock data
 * is only a last-resort fallback when the backend list is empty).
 */
export default function PromoFlyerPopup() {
  const navigate = useNavigate();
  const [section, setSection] = useState(null);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      const list = await getStorefrontSections('popup');
      if (cancelled) return;
      const active = (Array.isArray(list) ? list : [])
        .filter((s) => s.is_active !== false)
        .sort((a, b) => (a.sort_order ?? 0) - (b.sort_order ?? 0))[0];
      if (!active) return;
      const sessionId = sessionStorage.getItem('hg_login_session');
      if (!sessionId) return;
      if (sessionStorage.getItem(`hg_popup_seen_${sessionId}_${active.id}`)) return;
      setSection(active);
      // Brief delay so it lands after the hero, not on top of a blank paint.
      const t = setTimeout(() => setOpen(true), 600);
      return () => clearTimeout(t);
    })();
    return () => { cancelled = true; };
  }, []);

  const dismiss = () => {
    setOpen(false);
    if (section) {
      const sessionId = sessionStorage.getItem('hg_login_session');
      if (sessionId) sessionStorage.setItem(`hg_popup_seen_${sessionId}_${section.id}`, '1');
    }
  };

  const go = () => {
    const dest = section?.content?.cta_url || section?.content?.cta_link || section?.cta_url || section?.content?.destination;
    dismiss();
    if (!dest) return;
    // S8 — the rule this popup used to carry inline now lives in one helper.
    openCmsDestination(dest, navigate);
  };

  return (
    <AnimatePresence>
      {open && section && (
        <motion.div
          initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
          className="fixed inset-0 z-[60] bg-black/80 backdrop-blur-lg flex flex-col items-center justify-center p-4"
          onClick={dismiss}
        >
          <motion.div
            initial={{ scale: 0.9, y: 24, opacity: 0 }}
            animate={{ scale: 1, y: 0, opacity: 1 }}
            exit={{ scale: 0.92, opacity: 0 }}
            transition={{ type: 'spring', stiffness: 220, damping: 24 }}
            className="relative w-full max-w-[300px]"
            onClick={(e) => e.stopPropagation()}
          >
            {/* The flyer — the whole rectangle is the image, and it IS the CTA. */}
            <button
              onClick={go}
              aria-label={section.title || 'Promo'}
              className="block w-full rounded-3xl overflow-hidden bg-card shadow-glow focus:outline-none active:scale-[0.98] transition-transform"
            >
              {(section.content?.image_url || section.image_url) ? (
                <img
                  src={section.content?.image_url || section.image_url}
                  alt={section.title || 'Promo'}
                  className="w-full object-cover"
                  style={{ aspectRatio: '4 / 5' }}
                />
              ) : (
                <div className="w-full p-8 text-center" style={{ aspectRatio: '4 / 5' }}>
                  <h3 className="font-heading font-extrabold text-lg text-foreground">{section.title}</h3>
                  {(section.content?.subtitle || section.subtitle) && <p className="text-xs text-muted-foreground mt-2">{section.content?.subtitle || section.subtitle}</p>}
                </div>
              )}
            </button>

            {/* CTA button — a small overlay box floating on top of the flyer,
                separate from the image. Same destination as the flyer tap. */}
            {(section.content?.cta_text || section.cta_text) && (
              <button
                onClick={go}
                className="absolute left-1/2 -translate-x-1/2 -bottom-5 px-7 py-3 rounded-full bg-gradient-cta text-white font-bold text-sm shadow-glow whitespace-nowrap active:scale-95 transition"
              >
                {section.content?.cta_text || section.cta_text}
              </button>
            )}
          </motion.div>

          {/* Close icon — circular, centred beneath the modal */}
          <button
            onClick={dismiss}
            aria-label="Close"
            className="mt-8 w-10 h-10 rounded-full border-2 border-white/40 text-white flex items-center justify-center hover:bg-white/10 transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </motion.div>
      )}
    </AnimatePresence>
  );
}