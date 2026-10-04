import React, { useState } from 'react';
import { Link } from 'react-router-dom';
import { motion } from 'framer-motion';
import { Flame, Plus, Heart } from 'lucide-react';
import { formatNaira } from '@/lib/hgUtils';
import { useSound } from '@/lib/SoundProvider';
import { useHolyGrill } from '@/lib/HolyGrillContext';
import { toast } from '@/components/ui/use-toast';
import { fadeUp } from '@/lib/animationPresets';
import RatingStars from '@/components/RatingStars';

/**
 * MenuListCard — sleek horizontal row card for the Menu page grid.
 * Image left, content right. Whole card links to the detail page;
 * Add and Save buttons overlay via stopPropagation.
 *
 * Save/heart uses the HolyGrillContext saved-items API (toggleSavedItem /
 * isSavedItem). Guests get a "sign in to save" toast instead of a silent no-op.
 */
export default function MenuListCard({ item, onAdd }) {
  const { play } = useSound();
  const { isSavedItem, toggleSavedItem, isAuthenticated: isAuthed } = useHolyGrill();
  const [hpPulse, setHpPulse] = useState(false);
  const saved = isSavedItem(item.id);

  const lowStock = item.daily_remaining != null && item.daily_remaining <= 10 && !item.is_sold_out;
  const stockLevel = item.daily_remaining <= 2 ? 'critical' : item.daily_remaining <= 5 ? 'low' : 'mid';
  const stockText = stockLevel === 'critical' ? 'text-red-600' : stockLevel === 'low' ? 'text-orange-600' : 'text-amber-600';

  const handleAdd = (e) => {
    if (item.is_sold_out) return;
    e?.preventDefault?.();
    e?.stopPropagation?.();
    play('cart_add');
    setHpPulse(true);
    setTimeout(() => setHpPulse(false), 400);
    onAdd?.(item);
  };

  const handleSave = async (e) => {
    e?.preventDefault?.();
    e?.stopPropagation?.();
    if (!isAuthed) {
      toast({ title: 'Sign in to save items', description: 'Saved items sync to your account.' });
      return;
    }
    const nowSaved = await toggleSavedItem(item);
    toast({
      title: nowSaved ? '❤️ Saved to favourites' : 'Removed from favourites',
      description: nowSaved ? `${item.name} is in your saved list.` : `${item.name} was taken off your list.`,
    });
  };

  return (
    <motion.div
      variants={fadeUp}
      initial="hidden"
      animate="show"
      className="group relative bg-card rounded-2xl overflow-hidden border border-border hover:border-primary/40 hover:shadow-card transition-all duration-300 flex"
    >
      <Link to={`/menu/${item.id}`} className="flex w-full">
        {/* Image */}
        <div className="relative w-24 sm:w-28 shrink-0 bg-muted self-stretch overflow-hidden">
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
          {item.is_featured && !item.is_sold_out && (
            <span className="absolute top-1.5 left-1.5 px-1.5 py-0.5 rounded-md bg-accent text-accent-foreground text-[9px] font-bold">★</span>
          )}
        </div>

        {/* Content */}
        <div className="flex-1 p-3 flex flex-col justify-between min-w-0">
          <div>
            <div className="flex items-start justify-between gap-1.5 mb-0.5">
              <h3 className="font-heading font-bold text-sm text-foreground leading-tight line-clamp-1">{item.name}</h3>
              <button
                onClick={handleSave}
                aria-label={saved ? 'Remove from favourites' : 'Save to favourites'}
                className="shrink-0 -mr-1 -mt-1 w-7 h-7 rounded-full flex items-center justify-center hover:bg-muted transition-colors"
              >
                <Heart className={`w-4 h-4 transition-all ${saved ? 'fill-primary text-primary scale-110' : 'text-muted-foreground'}`} />
              </button>
            </div>
            {item.avg_rating != null && (
              <div className="mb-0.5"><RatingStars rating={item.avg_rating} count={item.review_count} size="sm" /></div>
            )}
            <p className="text-xs text-muted-foreground line-clamp-2 leading-relaxed">{item.description}</p>
          </div>

          <div className="flex items-center justify-between mt-2.5">
            <div className="flex flex-col">
              <span className="font-heading font-bold text-base text-foreground leading-none">{formatNaira(item.price)}</span>
              <div className="flex items-center gap-1 mt-1">
                <span className={`flex items-center gap-0.5 px-1.5 py-0.5 rounded-md bg-accent/20 text-accent-foreground text-[10px] font-bold transition-transform ${hpPulse ? 'scale-110' : ''}`}>
                  <Flame className="w-3 h-3 text-primary" />+{item.hp_earn_value} HP
                </span>
                {item.hp_multiplier && item.hp_multiplier !== 1 && (
                  <span className="px-1.5 py-0.5 rounded-md bg-primary text-white text-[9px] font-bold">
                    {item.hp_multiplier === 2 ? '2×' : item.hp_multiplier === 0.5 ? '½×' : `${item.hp_multiplier}×`}
                  </span>
                )}
                {lowStock && <span className={`text-[10px] font-semibold ${stockText}`}>Only {item.daily_remaining} left</span>}
              </div>
            </div>
            {onAdd && (
              <motion.button
                type="button"
                whileTap={{ scale: 0.88 }}
                whileHover={{ scale: 1.05 }}
                onClick={handleAdd}
                disabled={item.is_sold_out}
                aria-label={`Add ${item.name} to cart`}
                className="flex items-center gap-1 px-3 py-2 rounded-xl bg-gradient-cta text-white text-xs font-bold shadow-glow hover:opacity-90 transition-opacity disabled:opacity-40 disabled:cursor-not-allowed disabled:hover:scale-100"
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