// The Business Profile review link is sufficient; no Places API request is made.
export function googleReviewUrl({ reviewUrl = '', placeId = '' } = {}): string | null {
  if (reviewUrl.trim()) {
    try {
      const url = new URL(reviewUrl.trim());
      const googleHost = ['g.page', 'g.co', 'google.com', 'www.google.com', 'search.google.com', 'maps.google.com', 'maps.app.goo.gl'].includes(url.hostname);
      if (url.protocol === 'https:' && googleHost && !url.username && !url.password && url.pathname !== '/url') return url.href;
    } catch { /* An invalid direct link can still use the configured Place ID. */ }
  }
  return placeId.trim() ? `https://search.google.com/local/writereview?placeid=${encodeURIComponent(placeId.trim())}` : null;
}
