import { useEffect, useState } from 'react';
import { liveApi } from './liveApi';

/**
 * Tier icons — backend-driven.
 *
 * The brand tier marks are uploaded once in the admin panel as storefront
 * sections of type `tier_icon` (one per tier slug: ember / flame / blaze /
 * holy) and this module resolves them for every tier mark on the site. When no
 * artwork has been uploaded for a tier yet, callers fall back to the tier's
 * emoji so nothing ever renders blank.
 *
 * The fetch is shared across the whole app (single promise, cached for the
 * session) so a page with many tier marks only makes one request.
 */
let cachePromise = null;

export function loadTierIcons() {
  if (!cachePromise) {
    cachePromise = liveApi.storefront.getSections({ section_type: 'tier_icon' })
      .then((list) => {
        const map = {};
        (Array.isArray(list) ? list : []).forEach((s) => {
          if (s.is_active === false) return;
          const slug = s.content?.tier_slug || s.content?.slug || s.slug || s.subtitle;
          const url = s.image_url || s.content?.image_url;
          if (slug && url) map[String(slug).toLowerCase()] = url;
        });
        return map;
      })
      .catch(() => ({}));
  }
  return cachePromise;
}

// Called by the admin after saving a tier icon so the rest of the app picks up
// the new artwork without a full reload.
export function clearTierIconsCache() {
  cachePromise = null;
}

export function useTierIcons() {
  const [icons, setIcons] = useState({});
  useEffect(() => {
    let live = true;
    loadTierIcons().then((m) => { if (live) setIcons(m || {}); });
    return () => { live = false; };
  }, []);
  return icons;
}