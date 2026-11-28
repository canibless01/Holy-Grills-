import { Instagram, Facebook, Youtube, Music2 } from 'lucide-react';
import { msg } from '@/lib/messages';
import { SOCIAL_PLATFORMS, safeSocialLinks } from '@/lib/socialLinks';

const ICONS = { instagram: Instagram, facebook: Facebook, youtube: Youtube, tiktok: Music2 };

export default function SocialLinks({ links }: { links: unknown }) {
  const valid = safeSocialLinks(links);
  if (!Object.keys(valid).length) return null;
  return <nav aria-label={msg('FE_SOCIAL_LINKS_LABEL', 'Follow us')} className="flex items-center flex-wrap gap-3">
    {SOCIAL_PLATFORMS.filter(platform => valid[platform.key]).map(platform => {
      const Icon = ICONS[platform.key];
      const label = msg(platform.labelKey, platform.label);
      return <a key={platform.key} href={valid[platform.key]} target="_blank" rel="noopener noreferrer" aria-label={label} title={label}
        className="inline-flex items-center justify-center w-10 h-10 rounded-full border border-current/20 hover:text-accent transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2">
        {Icon ? <Icon className="w-5 h-5" aria-hidden="true" /> : <span aria-hidden="true" className="font-bold text-lg">𝕏</span>}
      </a>;
    })}
  </nav>;
}
