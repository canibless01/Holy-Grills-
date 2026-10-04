import React, { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import { Heart, ExternalLink } from 'lucide-react';
import { liveApi } from '@/lib/liveApi';

// Public Early Supporters strip — backed by GET /api/storefront/early-supporters.
// Each supporter may carry name / note / photo_url / social_links. We read
// whatever the backend returns and never invent entries; an empty response
// renders nothing so the page stays clean.
export default function EarlySupporters({ compact = false }) {
  const [supporters, setSupporters] = useState(null);

  useEffect(() => {
    let live = true;
    liveApi.storefront.getEarlySupporters()
      .then((list) => { if (live) setSupporters(Array.isArray(list) ? list : []); })
      .catch(() => { if (live) setSupporters([]); });
    return () => { live = false; };
  }, []);

  if (!supporters) {
    // skeleton
    return (
      <div className={compact ? 'flex gap-3 overflow-hidden' : 'grid grid-cols-2 sm:grid-cols-4 gap-3'}>
        {[0, 1, 2, 3].map((i) => (
          <div key={i} className="rounded-2xl bg-card border border-border p-4 animate-pulse">
            <div className="w-12 h-12 rounded-full bg-secondary mx-auto mb-2" />
            <div className="h-3 w-20 rounded bg-secondary mx-auto" />
          </div>
        ))}
      </div>
    );
  }
  if (supporters.length === 0) return null;

  return (
    <div className={compact ? 'flex gap-3 overflow-x-auto scrollbar-hide -mx-1 px-1 pb-1' : 'grid grid-cols-2 sm:grid-cols-4 gap-3'}>
      {supporters.map((s, i) => {
        const content = s.content || {};
        const name = s.name || content.name || s.title || 'Supporter';
        const note = s.note || content.note || s.subtitle || '';
        const photo = s.photo_url || content.photo_url || content.photo || '';
        const social = s.social_links || content.social_links || '';
        const socialUrl = typeof social === 'string' ? social : (social?.url || social?.link || '');
        return (
          <motion.div
            key={s.id || i}
            initial={{ opacity: 0, y: 8 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            transition={{ delay: i * 0.04 }}
            className={`rounded-2xl bg-card border border-border p-4 text-center flex-shrink-0 ${compact ? 'w-40' : ''}`}
          >
            <div className="w-12 h-12 rounded-full mx-auto mb-2 overflow-hidden bg-secondary flex items-center justify-center">
              {photo ? (
                <img src={photo} alt={name} className="w-full h-full object-cover" />
              ) : (
                <Heart className="w-5 h-5 text-accent" />
              )}
            </div>
            <div className="font-bold text-xs text-foreground truncate">{name}</div>
            {note && <div className="text-[10px] text-muted-foreground line-clamp-2 mt-0.5">{note}</div>}
            {socialUrl && (
              <a href={socialUrl} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 mt-1.5 text-[10px] font-bold text-primary hover:underline">
                <ExternalLink className="w-2.5 h-2.5" /> Follow
              </a>
            )}
          </motion.div>
        );
      })}
    </div>
  );
}