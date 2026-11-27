/** Presentation hint only: no permissions, network lookup or stored fingerprint. */
export function mobilePlatform(device?: { userAgent?: string; platform?: string; maxTouchPoints?: number }): 'android' | 'ios' | 'other' {
  const value = device || (typeof navigator === 'undefined' ? {} : navigator);
  if (/android/i.test(value.userAgent || '')) return 'android';
  if (/iphone|ipad|ipod/i.test(value.userAgent || '') || (/Macintosh/i.test(value.userAgent || '') && (value.maxTouchPoints || 0) > 1)) return 'ios';
  return 'other';
}
