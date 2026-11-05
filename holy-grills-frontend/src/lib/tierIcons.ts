import { useCampus } from './campusContext';
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
const cachePromises = new Map<string, Promise<Record<string, string>>>();
const listeners = new Set<() => void>();

export function loadTierIcons(scope = 'global') {
  if (!cachePromises.has(scope)) {
    const promise = liveApi.storefront.getSections({ section_type: 'tier_icon' })
      .then((list) => {
        const map = {};
        (Array.isArray(list) ? list : []).forEach((s) => {
          if (s.is_active === false) return;
          const slug = s.content?.tier_slug || s.content?.slug || s.slug || s.subtitle || String(s.key || '').replace(/^tier[_-]icon[_-]/, '');
          const url = s.image_url || s.content?.image_url;
          if (slug && url) map[String(slug).toLowerCase()] = url;
        });
        return map;
      })
      .catch(() => { cachePromises.delete(scope); return {}; });
    cachePromises.set(scope, promise);
  }
  return cachePromises.get(scope);
}

// Called by the admin after saving a tier icon so the rest of the app picks up
// the new artwork without a full reload.
export function clearTierIconsCache() {
  cachePromises.clear();
  listeners.forEach((listener) => listener());
}

export function useTierIcons() {
  const { campusId, adminCampusId } = useCampus();
  const scope = `${campusId || 'global'}:${adminCampusId || 'global'}`;
  const [icons, setIcons] = useState({});
  const [revision, setRevision] = useState(0);
  useEffect(() => { const refresh = () => setRevision((value) => value + 1); listeners.add(refresh); return () => { listeners.delete(refresh); }; }, []);
  useEffect(() => {
    let live = true;
    setIcons({});
    loadTierIcons(scope).then((m) => { if (live) setIcons(m || {}); });
    return () => { live = false; };
  }, [scope, revision]);
  return icons;
}