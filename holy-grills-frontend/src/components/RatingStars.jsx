import React from 'react';
import { Star } from 'lucide-react';

/**
 * RatingStars — read-only star rating rendered from the backend's avg_rating
 * (and optional review_count). No local computation — the backend already
 * returns the global average across all users, so every student sees the same
 * rating. Half-stars are shown via width-clipped gold overlays on grey bases.
 *
 *   <RatingStars rating={item.avg_rating} count={item.review_count} />
 */
export default function RatingStars({ rating = 0, count, size = 'sm', showCount = true }) {
  const r = Number(rating) || 0;
  const dims = size === 'lg' ? 'w-4 h-4' : size === 'md' ? 'w-3.5 h-3.5' : 'w-3 h-3';
  const fontClass = size === 'lg' ? 'text-xs' : 'text-[10px]';
  if (r <= 0 && count == null) return null;

  return (
    <div className="flex items-center gap-1">
      <div className="flex items-center">
        {[1, 2, 3, 4, 5].map((n) => {
          const ratio = Math.max(0, Math.min(1, r - (n - 1)));
          return (
            <span key={n} className="relative inline-block">
              <Star className={`${dims} text-muted`} />
              <span
                className="absolute inset-0 overflow-hidden leading-none"
                style={{ width: `${ratio * 100}%` }}
              >
                <Star className={`${dims} text-accent fill-accent`} />
              </span>
            </span>
          );
        })}
      </div>
      {showCount && (
        <span className={`${fontClass} font-semibold text-muted-foreground`}>
          {r > 0 && <>{r.toFixed(1)} </>}
          {count != null && <span className="font-normal">({count} review{count === 1 ? '' : 's'})</span>}
        </span>
      )}
    </div>
  );
}