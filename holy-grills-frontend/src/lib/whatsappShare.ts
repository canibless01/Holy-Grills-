export function openWhatsApp(caption: string) {
  // Deliberately text-only. WhatsApp links cannot attach an arbitrary URL as
  // an image file; saving a graphic is a separate explicit user action.
  window.open(`https://wa.me/?text=${encodeURIComponent(caption)}`, '_blank', 'noopener,noreferrer');
}
