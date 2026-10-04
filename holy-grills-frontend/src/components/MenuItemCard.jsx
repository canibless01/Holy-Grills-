import React, { useState } from 'react';
import { Link } from 'react-router-dom';
import { motion } from 'framer-motion';
import { Flame, Plus } from 'lucide-react';
import { formatNaira } from '@/lib/hgUtils';
import { useSound } from '@/lib/SoundProvider';
import { fadeUp } from '@/lib/animationPresets';
import RatingStars from '@/components/RatingStars';

/**
 * MenuItemCard — menu item presentation card.
 *
 * variants:
 *   - "compact"     (default): vertical card, image on top — used in the home featured carousel.
 *   - "horizontal": rectangular row card, image left + content right — used on the Menu page,
 *     so the grid reads as scannable horizontal rows (name · HP badge · description · price).
 *
 * The whole card is a Link to the item's detail page (no popup). The Add button
 * overlays via stopPropagation so it can quick-add without leaving the page.
 */
export default function MenuItemCard({ item, onAdd, variant = 'compact' }) {
  const { play } = useSound();
  const [hpPulse, setHpPulse] = useState(false);
  const lowStock = item.daily_remaining <= 10 && !item.is_sold_out;
  const stockLevel = item.daily_remaining <= 2 ? 'critical' : item.daily_remaining <= 5 ? 'low' : 'mid';
  const stockText = stockLevel === 'critical' ? 'text-red-600' : stockLevel === 'low' ? 'text-orange-600' : 'text-amber-600';
  const stockBadge = stockLevel === 'critical' ? 'bg-red-600' : stockLevel === 'low' ? 'bg-orange-500' : 'bg-amber-500';

  const handleAdd = (e) => {
    if (item.is_sold_out) return;
    e?.preventDefault?.();
    e?.stopPropagation?.();
    play('cart_add');
    setHpPulse(true);
    setTimeout(() => setHpPulse(false), 400);
    onAdd?.(item);
  };

  /* Horizontal rectangular row card — designed for grid layout on the Menu page.
   * Shows: image (left), then a vertical column with NAME + HP BADGE row,
   * DESCRIPTION (2-line clamp), and PRICE + Add button row. */
  if (variant === 'horizontal') {
    return (
      <motion.div
        variants={fadeUp}
        initial="hidden"
        animate="show"
        className="group relative bg-card rounded-2xl overflow-hidden border border-border hover:border-primary/40 hover:shadow-card transition-all duration-300 flex"
      >
        <Link to={`/menu/${item.id}`} className="flex w-full">
          <div className="relative w-28 sm:w-32 shrink-0 bg-muted self-stretch overflow-hidden">
            <img
              src={item.image_url}
              alt={item.name}
              loading="lazy"
              decoding="async"
              className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-300"
            />
            {item.is_sold_out && (
              <div className="absolute inset-0 bg-black/55 flex items-center justify-center">
                <span className="text-white text-[10px] font-bold uppercase tracking-wide">Sold Out</span>
              </div>
            )}
          </div>

          <div className="flex-1 p-3 flex flex-col justify-between min-w-0">
            <div>
              <div className="flex items-start justify-between gap-2 mb-1">
                <h3 className="font-heading font-bold text-sm text-foreground leading-tight line-clamp-1">{item.name}</h3>
                {/* HP badge — gold (brand rule: rewards/HP = gold, not gradient) */}
                <div className="flex items-center gap-1 shrink-0">
                  {item.hp_multiplier && item.hp_multiplier !== 1 && (
                    <span className="px-1.5 py-0.5 rounded-md bg-primary text-white text-[9px] font-bold">
                      {item.hp_multiplier === 2 ? '2× HP' : item.hp_multiplier === 0.5 ? '½× HP' : `${item.hp_multiplier}× HP`}
                    </span>
                  )}
                  <span className={`flex items-center gap-0.5 px-1.5 py-0.5 rounded-md bg-accent/20 text-accent-foreground text-[10px] font-bold transition-transform ${hpPulse ? 'animate-hp-pop' : ''}`}>
                    <Flame className="w-3 h-3 text-primary" />+{item.hp_earn_value} HP
                  </span>
                </div>
              </div>
              {item.avg_rating != null && <div className="mb-1"><RatingStars rating={item.avg_rating} count={item.review_count} size="sm" /></div>}
              <p className="text-xs text-muted-foreground line-clamp-2 leading-relaxed">{item.description}</p>
            </div>

            <div className="flex items-center justify-between mt-3">
              <div>
                <span className="font-heading font-bold text-base text-foreground">{formatNaira(item.price)}</span>
                {lowStock && <div className={`text-[10px] font-semibold mt-0.5 ${stockText}`}>Only {item.daily_remaining} left!</div>}
              </div>
              {onAdd && (
                <motion.button
                  type="button"
                  whileTap={{ scale: 0.88 }}
                  whileHover={{ scale: 1.05 }}
                  onClick={handleAdd}
                  disabled={item.is_sold_out}
                  className="flex items-center gap-1 px-3 py-1.5 rounded-lg bg-primary text-white text-xs font-bold hover:bg-primary-hover transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
                >
                  <Plus className="w-3.5 h-3.5" /> Add
                </motion.button>
              )}
            </div>
          </div>
        </Link>
      </motion.div>
    );
  }

  /* Compact vertical card — used in the home AutoScrollCarousel. */
  return (
    <motion.div
      variants={fadeUp}
      initial="hidden"
      animate="show"
      className="group relative bg-card rounded-2xl overflow-hidden border border-border hover:border-primary/40 hover:shadow-card transition-all duration-300 w-full h-full flex flex-col"
    >
      <Link to={`/menu/${item.id}`} className="block h-full flex flex-col">
        <div className="relative aspect-[4/3] overflow-hidden bg-muted">
          <img
            src={item.image_url}
            alt={item.name}
            loading="lazy"
            decoding="async"
            className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-300"
          />
          {item.is_sold_out ? (
            <span className="absolute top-2 right-2 px-2 py-1 rounded-lg bg-foreground/90 text-white text-[10px] font-bold uppercase">Sold Out</span>
          ) : (
            <span className="absolute top-2 right-2 flex items-center gap-1 px-2 py-1 rounded-lg bg-card/95 text-accent-foreground text-[10px] font-bold shadow-sm">
              <Flame className="w-3 h-3 text-primary" />+{item.hp_earn_value} HP
            </span>
          )}
          {item.hp_multiplier && item.hp_multiplier !== 1 && (
            <span className="absolute top-2 left-2 px-1.5 py-0.5 rounded-md bg-primary text-white text-[9px] font-bold">
              {item.hp_multiplier === 2 ? '2× HP' : item.hp_multiplier === 0.5 ? '½× HP' : `${item.hp_multiplier}× HP`}
            </span>
          )}
          {lowStock && (
            <span className={`absolute bottom-2 left-2 px-2 py-1 rounded-lg ${stockBadge} text-white text-[10px] font-bold animate-pulse`}>Only {item.daily_remaining} left!</span>
          )}
        </div>

        <div className="p-3 flex-1 flex flex-col">
          <h3 className="font-heading font-bold text-sm text-foreground leading-tight mb-1 line-clamp-1">{item.name}</h3>
          {item.avg_rating != null && <div className="mb-1"><RatingStars rating={item.avg_rating} count={item.review_count} size="sm" /></div>}
          <p className="text-xs text-muted-foreground line-clamp-2 leading-relaxed mb-2">{item.description}</p>
          <div className="flex items-center justify-between mt-auto">
            <span className="font-heading font-bold text-base text-foreground">{formatNaira(item.price)}</span>
            {onAdd && (
              <motion.button
                type="button"
                whileTap={{ scale: 0.88 }}
                whileHover={{ scale: 1.05 }}
                onClick={handleAdd}
                disabled={item.is_sold_out}
                className="flex items-center gap-1 px-3 py-1.5 rounded-lg bg-primary text-white text-xs font-bold hover:bg-primary-hover transition-colors disabled:opacity-40 disabled:cursor-not-allowed disabled:hover:scale-100"
              >
                <Plus className="w-3.5 h-3.5" /> Add
              </motion.button>
            )}
          </div>
        </div>
      </Link>
    </motion.div>
  );
}