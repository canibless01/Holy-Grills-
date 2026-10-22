export const SOCIAL_PLATFORMS = [
  { key: 'instagram', labelKey: 'FE_SOCIAL_LINK_INSTAGRAM', label: 'Instagram', hosts: ['instagram.com', 'www.instagram.com'] },
  { key: 'facebook', labelKey: 'FE_SOCIAL_LINK_FACEBOOK', label: 'Facebook', hosts: ['facebook.com', 'www.facebook.com'] },
  { key: 'x', labelKey: 'FE_SOCIAL_LINK_X', label: 'X', hosts: ['x.com', 'www.x.com', 'twitter.com', 'www.twitter.com'] },
  { key: 'tiktok', labelKey: 'FE_SOCIAL_LINK_TIKTOK', label: 'TikTok', hosts: ['tiktok.com', 'www.tiktok.com'] },
  { key: 'youtube', labelKey: 'FE_SOCIAL_LINK_YOUTUBE', label: 'YouTube', hosts: ['youtube.com', 'www.youtube.com', 'youtu.be'] },
];

export function safeSocialLinks(value: unknown): Record<string, string> {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return {};
  const links: Record<string, string> = {};
  for (const platform of SOCIAL_PLATFORMS) {
    const raw = (value as Record<string, unknown>)[platform.key];
    if (typeof raw !== 'string') continue;
    const url = raw.trim();
    if (url.length > 512 || /\s/.test(url)) continue;
    try {
      const parsed = new URL(url);
      if (parsed.protocol === 'https:' && platform.hosts.includes(parsed.hostname)
          && !parsed.username && !parsed.password && (!parsed.port || parsed.port === '443')) links[platform.key] = url;
    } catch { /* Empty and invalid historical destinations stay hidden. */ }
  }
  return links;
}
