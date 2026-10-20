import { useCampus } from '@/lib/campusContext';
import { msg } from '@/lib/messages';
import { useState, useEffect, useRef } from 'react';
import { motion, AnimatePresence, useReducedMotion } from 'framer-motion';
import { X } from 'lucide-react';
import { useNavigate, useLocation } from 'react-router-dom';
import { getStorefrontSections } from '@/lib/storefrontMockData';
import { openCmsDestination } from '@/lib/safeNavigation';

/**
 * PromoFlyerPopup — a flyer popup shown once per visit/login session on its selected page.
 *
 * The flyer image IS the call-to-action: the entire rectangle is the uploaded
 * image, and tapping anywhere on it navigates to the destination. A small CTA
 * button appears below the image — tapping it goes to the same place. A circular close icon sits
 * beneath the modal, centred.
 *
 * Content (flyer image + cta_text + destination) comes from an admin-uploaded
 * storefront section of section_type='popup'. Data flows through the live API
 * (getStorefrontSections calls liveApi.storefront.getSections first; no fallback content
 * is fabricated when the backend list is empty).
 */
export default function PromoFlyerPopup() {
  const navigate = useNavigate();
  const { pathname } = useLocation();
  const placement = ({ '/': 'home', '/menu': 'menu', '/dashboard': 'dashboard', '/orders': 'orders', '/rewards': 'rewards' } as Record<string, string>)[pathname];
  const reducedMotion = useReducedMotion();
  const closeRef = useRef<HTMLButtonElement>(null);
  const { campusId } = useCampus();
  const [section, setSection] = useState(null);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    setOpen(false);
    setSection(null);
    if (!campusId || !placement) return;
    (async () => {
      try {
        const list = await getStorefrontSections('popup');
        if (cancelled) return;
        const active = list.filter((s) => s.is_active !== false && (s.content?.placement || s.placement || 'home') === placement)
          .sort((a, b) => (a.sort_order ?? 0) - (b.sort_order ?? 0))[0];
        if (!active) return;
        let sessionId = sessionStorage.getItem('hg_login_session') || sessionStorage.getItem('hg_storefront_visit');
        if (!sessionId) {
          sessionId = crypto.randomUUID();
          sessionStorage.setItem('hg_storefront_visit', sessionId);
        }
        const seenKey = `hg_popup_seen_${sessionId}_${campusId}_${active.id}`;
        if (sessionStorage.getItem(seenKey)) return;
        setSection(active);
        timer = setTimeout(() => {
          if (cancelled) return;
          sessionStorage.setItem(seenKey, '1');
          setOpen(true);
        }, 600);
      } catch { /* Unavailable content does not create a popup. */ }
    })();
    return () => { cancelled = true; if (timer) clearTimeout(timer); };
  }, [campusId, placement]);

  useEffect(() => {
    if (!open) return;
    const previous = document.activeElement as HTMLElement | null;
    closeRef.current?.focus();
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setOpen(false);
      if (event.key === 'Tab') {
        const buttons = closeRef.current?.parentElement?.querySelectorAll<HTMLButtonElement>('button');
        if (!buttons?.length) return;
        const first = buttons[0]; const last = buttons[buttons.length - 1];
        if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
        else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
      }
    };
    document.addEventListener('keydown', onKey);
    return () => { document.removeEventListener('keydown', onKey); previous?.focus(); };
  }, [open]);

  const dismiss = () => setOpen(false);

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
          role="dialog" aria-modal="true" aria-label={section.title || msg('FE_STOREFRONT_PROMO', 'Promo')}
          initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
          className="fixed inset-0 z-[60] hg-scrim flex flex-col items-center justify-center p-4"
          onClick={dismiss}
        >
          <motion.div
            initial={{ scale: 0.9, y: 24, opacity: 0 }}
            animate={{ scale: 1, y: 0, opacity: 1 }}
            exit={{ scale: 0.92, opacity: 0 }}
            transition={reducedMotion ? { duration: 0 } : { type: 'spring', stiffness: 220, damping: 24 }}
            className="relative w-full max-w-[min(90vw,440px)]"
            onClick={(e) => e.stopPropagation()}
          >
            {/* The flyer — the whole rectangle is the image, and it IS the CTA. */}
            <button
              onClick={go}
              aria-label={section.title || msg('FE_STOREFRONT_PROMO', 'Promo')}
              className="relative flex w-full justify-center bg-transparent focus-visible:outline focus-visible:outline-2 focus-visible:outline-white active:scale-[0.98] transition-transform"
            >
              {(section.content?.image_url || section.image_url) ? (
                <img
                  src={section.content?.image_url || section.image_url}
                  alt={section.title || msg('FE_STOREFRONT_PROMO', 'Promo')}
                  className="w-auto max-w-full max-h-[70dvh] object-contain"
                />
              ) : (
                <div className="w-full p-8 text-center" style={{ aspectRatio: '4 / 5' }}>
                  <h3 className="font-heading font-extrabold text-lg text-foreground">{section.title}</h3>
                  {(section.content?.subtitle || section.subtitle) && <p className="text-xs text-muted-foreground mt-2">{section.content?.subtitle || section.subtitle}</p>}
                </div>
              )}

            </button>

            {/* Optional CTA below the artwork, sharing its destination. */}
            {(section.content?.cta_text || section.cta_text) && (
              <button
                onClick={go}
                className="block mx-auto mt-3 px-7 py-3 rounded-full bg-gradient-cta text-white font-bold text-sm shadow-glow whitespace-nowrap active:scale-95 transition"
              >
                {section.content?.cta_text || section.cta_text}
              </button>
            )}
          </motion.div>

          {/* Close icon — circular, centred beneath the modal */}
          <button
            ref={closeRef}
            onClick={dismiss}
            aria-label={msg('FE_STOREFRONT_CLOSE_POPUP', 'Close promotion')}
            className="mt-8 w-10 h-10 rounded-full border-2 border-white/40 text-white flex items-center justify-center hover:bg-white/10 transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </motion.div>
      )}
    </AnimatePresence>
  );
}