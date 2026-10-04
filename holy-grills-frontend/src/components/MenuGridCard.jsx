import React, { useState } from 'react';
import { Link } from 'react-router-dom';
import { motion } from 'framer-motion';
import { Flame, Plus, Heart } from 'lucide-react';
import { formatNaira } from '@/lib/hgUtils';
import { useSound } from '@/lib/SoundProvider';
import { useHolyGrill } from '@/lib/HolyGrillContext';
import { toast } from '@/components/ui/use-toast';
import { fadeUp } from '@/lib/animationPresets';

/**
 * MenuGridCard — compact vertical card for the menu page's two-up grid.
 * Image on top, name/price/HP below. Vertical shape keeps two items visible
 * per row on small screens, so at least two menu items show without
 * scrolling. Add + Save overlay via stopPropagation, like MenuListCard.
 */
export default function MenuGridCard({ item, onAdd }) {
  const { play } = useSound();
  const { isSavedItem, toggleSavedItem, isAuthenticated: isAuthed } = useHolyGrill();
  const [hpPulse, setHpPulse] = useState(false);
  const saved = isSavedItem(item.id);

  const lowStock = item.daily_remaining != null && item.daily_remaining <= 10 && !item.is_sold_out;

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
      className="group relative bg-card rounded-2xl overflow-hidden border border-border hover:border-primary/40 hover:shadow-card transition-all duration-300 flex flex-col"
    >
      <Link to={`/menu/${item.id}`} className="flex flex-col flex-1 min-w-0">
        {/* Image */}
        <div className="relative aspect-[4/3] bg-muted overflow-hidden">
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
        <div className="p-2.5 sm:p-3 flex flex-col flex-1 gap-1 min-w-0">
          <div className="flex items-start justify-between gap-1">
            <h3 className="font-heading font-bold text-[13px] sm:text-sm text-foreground leading-tight line-clamp-1">{item.name}</h3>
            <button
              onClick={handleSave}
              aria-label={saved ? 'Remove from favourites' : 'Save to favourites'}
              className="shrink-0 -mr-1 -mt-1 w-6 h-6 rounded-full flex items-center justify-center hover:bg-muted transition-colors"
            >
              <Heart className={`w-3.5 h-3.5 transition-all ${saved ? 'fill-primary text-primary scale-110' : 'text-muted-foreground'}`} />
            </button>
          </div>
          <p className="text-[11px] text-muted-foreground line-clamp-1 leading-snug hidden sm:block">{item.description}</p>
          <div className="mt-auto flex items-end justify-between gap-1.5">
            <div className="min-w-0">
              <span className="font-heading font-bold text-sm text-foreground leading-none block">{formatNaira(item.price)}</span>
              <span className={`inline-flex items-center gap-0.5 mt-1 px-1.5 py-0.5 rounded-md bg-accent/20 text-accent-foreground text-[10px] font-bold transition-transform ${hpPulse ? 'scale-110' : ''}`}>
                <Flame className="w-2.5 h-2.5 text-primary" />+{item.hp_earn_value} HP
              </span>
            </div>
            {onAdd && (
              <motion.button
                type="button"
                whileTap={{ scale: 0.88 }}
                whileHover={{ scale: 1.05 }}
                onClick={handleAdd}
                disabled={item.is_sold_out}
                aria-label={`Add ${item.name} to cart`}
                className="flex items-center gap-1 px-2.5 py-1.5 rounded-xl bg-gradient-cta text-white text-xs font-bold shadow-glow hover:opacity-90 transition-opacity disabled:opacity-40 disabled:cursor-not-allowed"
              >
                <Plus className="w-3.5 h-3.5" /> Add
              </motion.button>
            )}
          </div>
          {lowStock && <span className="text-[10px] font-semibold text-orange-600">Only {item.daily_remaining} left</span>}
        </div>
      </Link>
    </motion.div>
  );
}