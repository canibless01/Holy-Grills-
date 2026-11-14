import ModalPortal from './ModalPortal';

/**
 * ModalBackdrop — the single, consistent overlay for every custom popup.
 *
 *  · Portalled to <body> so a transformed ancestor (Framer Motion) can never
 *    clip `position: fixed` — the backdrop always covers the full screen.
 *  · One shared look everywhere: the .hg-scrim veil (warm brand-black +
 *    one blur step) — same colour, same opacity on every page and every panel,
 *    no light bleeding through the edges.
 *
 * Usage — wrap the popup's panel:
 *   <ModalBackdrop onClose={close}>
 *     <div className="bg-card rounded-2xl p-6 ..." onClick={(e) => e.stopPropagation()}>
 *       …
 *     </div>
 *   </ModalBackdrop>
 */
export default function ModalBackdrop({ children, onClose, align = 'items-end sm:items-center' }) {
  return (
    <ModalPortal>
      <div
        className={`fixed inset-0 z-50 hg-scrim flex ${align} justify-center p-4`}
        onClick={onClose}
      >
        {children}
      </div>
    </ModalPortal>
  );
}