/**
 * Holy Grill — useSEO hook
 * ----------------------------------------------------------------------------
 * Dynamically updates document title + meta tags per page/route, and injects
 * JSON-LD structured data:
 *   - the global Restaurant block on EVERY page (from APP_CONFIG.seo.business)
 *   - an optional page-specific block (e.g. MenuItem) via the `jsonLd` prop
 * Every page MUST call this (or render <SEO />) — see BUILDER_RULES.md.
 *
 *   useSEO({ title: 'Menu', description: 'Browse the flame-grilled menu' });
 *
 * Falls back to APP_CONFIG.seo defaults when a field is omitted.
 */
import { useEffect } from 'react';
import APP_CONFIG from '@/config/app.config';
import { absoluteUrl, restaurantJsonLd } from '@/lib/seoJsonLd';

const upsertMeta = (attr, key, content) => {
  if (!content) return;
  let el = document.head.querySelector(`meta[${attr}="${key}"]`);
  if (!el) {
    el = document.createElement('meta');
    el.setAttribute(attr, key);
    document.head.appendChild(el);
  }
  el.setAttribute('content', content);
};

const upsertCanonical = (url) => {
  let link = document.head.querySelector('link[rel="canonical"]');
  if (!link) {
    link = document.createElement('link');
    link.setAttribute('rel', 'canonical');
    document.head.appendChild(link);
  }
  link.setAttribute('href', url);
};

const upsertJsonLd = (id, data) => {
  let el = document.head.querySelector(`script[data-seo-jsonld="${id}"]`);
  if (!data) {
    if (el) el.remove();
    return;
  }
  if (!el) {
    el = document.createElement('script');
    el.type = 'application/ld+json';
    el.setAttribute('data-seo-jsonld', id);
    document.head.appendChild(el);
  }
  el.textContent = JSON.stringify(data);
};

export const useSEO = ({ title, description, image, path, type, jsonLd } = {}) => {
  // Serialised so the effect only re-runs when the data actually changes.
  const jsonLdKey = jsonLd ? JSON.stringify(jsonLd) : '';

  useEffect(() => {
    const fullTitle = title ? `${title} | ${APP_CONFIG.name}` : APP_CONFIG.seo.defaultTitle;
    const desc = description || APP_CONFIG.seo.defaultDescription;
    const img = absoluteUrl(image || APP_CONFIG.seo.defaultImage);
    const url = `${APP_CONFIG.domain}${path || window.location.pathname}`;
    const ogType = type || APP_CONFIG.seo.ogType;

    document.title = fullTitle;

    upsertMeta('name', 'description', desc);
    upsertMeta('name', 'theme-color', APP_CONFIG.themeColor);

    // Open Graph
    upsertMeta('property', 'og:title', fullTitle);
    upsertMeta('property', 'og:description', desc);
    upsertMeta('property', 'og:type', ogType);
    upsertMeta('property', 'og:url', url);
    upsertMeta('property', 'og:site_name', APP_CONFIG.name);
    if (img) upsertMeta('property', 'og:image', img);

    // Twitter
    upsertMeta('name', 'twitter:card', APP_CONFIG.seo.twitterCard);
    upsertMeta('name', 'twitter:title', fullTitle);
    upsertMeta('name', 'twitter:description', desc);
    if (img) upsertMeta('name', 'twitter:image', img);

    upsertCanonical(url);

    // Structured data — global identity on every page, plus optional page block.
    upsertJsonLd('business', restaurantJsonLd());
    upsertJsonLd('page', jsonLd || null);
  }, [title, description, image, path, type, jsonLdKey]);
};

export default useSEO;