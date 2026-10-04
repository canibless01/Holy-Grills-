import React from 'react';
import { createPortal } from 'react-dom';

/**
 * ModalPortal — renders its children into document.body via a React portal.
 *
 * Why: when a modal's backdrop uses `position: fixed; inset: 0` but an ancestor
 * has a CSS `transform` (e.g. a Framer Motion `motion.div` with initial/animate),
 * `fixed` is constrained to that ancestor instead of the viewport, leaving gaps
 * above/below the backdrop. Portalling to <body> escapes every transformed
 * wrapper so the backdrop always covers the full screen.
 *
 * Usage: wrap the modal's outermost `fixed inset-0` element.
 *   return (
 *     <ModalPortal>
 *       <div className="fixed inset-0 ...">…</div>
 *     </ModalPortal>
 *   );
 */
export default function ModalPortal({ children }) {
  if (typeof document === 'undefined') return children;
  return createPortal(children, document.body);
}