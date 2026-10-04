import { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import { Flame, ChevronLeft, Plus, Minus, Check, AlertCircle, ShoppingCart, Heart, Star } from 'lucide-react';
import { mockApi } from '@/lib/mockApi';
import { useHolyGrill } from '@/lib/HolyGrillContext';
import { useSound } from '@/lib/SoundProvider';
import { formatNaira } from '@/lib/hgUtils';
import RatingStars from '@/components/RatingStars';
import { toast } from '@/components/ui/use-toast';
import { fadeUp } from '@/lib/animationPresets';
import SEO from '@/components/SEO';
import { menuItemJsonLd } from '@/lib/seoJsonLd';
import MascotStandee from '@/components/mascot/MascotStandee';
import { msg } from '@/lib/messages';

export default function ItemDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { addToCart, toggleSavedItem, isSavedItem, isAuthenticated: isAuthed } = useHolyGrill();
  const { play } = useSound();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [item, setItem] = useState(null);
  const [addonGroups, setAddonGroups] = useState([]);
  const [quantity, setQuantity] = useState(1);
  const [selections, setSelections] = useState({});
  const [notes, setNotes] = useState('');
  const [adding, setAdding] = useState(false);
  const [saved, setSaved] = useState(false);
  const [retryCount, setRetryCount] = useState(0);

  useEffect(() => {
    const load = async () => {
      setLoading(true);
      setError(null);
      try {
        const detail = await mockApi.menu.getItem(id);
        setItem(detail);
        // Addons are optional — a failure here must NOT block the item page
        // from rendering (this was the cause of the persistent "retry" screen).
        const addons = await mockApi.menu.getAddons(id).catch(() => ({ addon_groups: [] }));
        setAddonGroups(addons.addon_groups || []);
        const init = {};
        (detail.variation_groups || []).forEach((vg) => { init[vg.id] = []; });
        addons.addon_groups?.forEach((ag) => { init[ag.id] = []; });
        setSelections(init);
        setSaved(isSavedItem(detail.id));
      } catch (e) {
        setError(msg('FE_ITEM_DETAIL_FAILED_TO_LOAD_ITEM_DETAILS', 'Failed to load item details.'));
      }
      setLoading(false);
    };
    load();
  }, [id, retryCount]); // eslint-disable-line react-hooks/exhaustive-deps

  const toggleVariation = (groupId, optionId, maxSelections) => {
    setSelections((prev) => {
      const current = prev[groupId] || [];
      if (maxSelections === 1) return { ...prev, [groupId]: [optionId] };
      if (current.includes(optionId)) return { ...prev, [groupId]: current.filter((x) => x !== optionId) };
      if (current.length < maxSelections) return { ...prev, [groupId]: [...current, optionId] };
      return prev;
    });
  };

  const toggleAddon = (groupId, addonId, maxSelect) => {
    setSelections((prev) => {
      const current = prev[groupId] || [];
      if (current.includes(addonId)) return { ...prev, [groupId]: current.filter((x) => x !== addonId) };
      if (current.length < maxSelect) return { ...prev, [groupId]: [...current, addonId] };
      return prev;
    });
  };

  const calculatePrice = () => {
    if (!item) return 0;
    let price = item.price;
    (item.variation_groups || []).forEach((vg) => {
      (selections[vg.id] || []).forEach((optId) => {
        const opt = (vg.options || []).find((o) => o.id === optId);
        if (opt) price += opt.price_delta;
      });
    });
    addonGroups.forEach((ag) => {
      (selections[ag.id] || []).forEach((addonId) => {
        const ad = (ag.addons || []).find((a) => a.id === addonId);
        if (ad) price += ad.price;
      });
    });
    return price * quantity;
  };

  const validateSelections = () => {
    if (!item) return [];
    const errs = [];
    (item.variation_groups || []).forEach((vg) => {
      if (vg.is_required && (selections[vg.id] || []).length < vg.min_selections) errs.push(`"${vg.name}" requires ${vg.min_selections} selection(s)`);
    });
    addonGroups.forEach((ag) => {
      if (ag.is_required && (selections[ag.id] || []).length < ag.min_select) errs.push(`"${ag.name}" requires ${ag.min_select} selection(s)`);
    });
    return errs;
  };

  const handleAddToCart = async () => {
    const errors = validateSelections();
    if (errors.length > 0) return;
    setAdding(true);
    try {
      const selected_variations = [];
      (item.variation_groups || []).forEach((vg) => {
        (selections[vg.id] || []).forEach((optId) => selected_variations.push({ variation_group_id: vg.id, option_id: optId }));
      });
      const selected_addons = [];
      addonGroups.forEach((ag) => {
        (selections[ag.id] || []).forEach((addonId) => selected_addons.push({ addon_id: addonId, quantity: 1 }));
      });
      play('cart_add');
      await addToCart({ menu_item_id: item.id, quantity, notes, selected_variations, selected_addons });
      toast({ title: msg('FE_ITEM_DETAIL_ADDED_TO_YOUR_CART', '🔥 Added to your cart'), description: `${quantity}× ${item.name} is in your cart.` });
    } catch (e) {
      toast({ title: msg('FE_ITEM_DETAIL_COULD_NOT_ADD_TO_CART', 'Could not add to cart'), description: e.message || 'Please try again.', variant: 'destructive' });
    }
    setAdding(false);
  };

  // Checkout now — adds the configured item to the cart and jumps straight to
  // the checkout page, skipping the cart page entirely to reduce friction.
  const handleCheckoutNow = async () => {
    const errors = validateSelections();
    if (errors.length > 0) return;
    setAdding(true);
    try {
      const selected_variations = [];
      (item.variation_groups || []).forEach((vg) => {
        (selections[vg.id] || []).forEach((optId) => selected_variations.push({ variation_group_id: vg.id, option_id: optId }));
      });
      const selected_addons = [];
      addonGroups.forEach((ag) => {
        (selections[ag.id] || []).forEach((addonId) => selected_addons.push({ addon_id: addonId, quantity: 1 }));
      });
      play('cart_add');
      await addToCart({ menu_item_id: item.id, quantity, notes, selected_variations, selected_addons });
      navigate('/checkout');
    } catch (e) {
      toast({ title: msg('FE_ITEM_DETAIL_COULD_NOT_ADD_TO_CART', 'Could not add to cart'), description: e.message || 'Please try again.', variant: 'destructive' });
    }
    setAdding(false);
  };

  const handleSaveToggle = async () => {
    if (!isAuthed) {
      toast({ title: msg('FE_ITEM_DETAIL_SIGN_IN_TO_SAVE_ITEMS', 'Sign in to save items'), description: msg('FE_ITEM_DETAIL_SAVED_ITEMS_SYNC_TO_YOUR_ACCOUNT', 'Saved items sync to your account.') });
      return;
    }
    const nowSaved = await toggleSavedItem(item);
    setSaved(nowSaved);
    toast({
      title: nowSaved ? '❤️ Saved to favourites' : 'Removed from favourites',
      description: nowSaved ? `${item.name} is in your saved list.` : `${item.name} was taken off your list.`,
    });
  };

  if (loading) {
    return (
      <div className="space-y-5 animate-fade-in pb-8">
        <div className="h-5 w-28 bg-muted rounded animate-pulse" />
        <div className="rounded-2xl aspect-[4/3] bg-muted animate-pulse" />
        <div className="space-y-2">
          <div className="h-6 w-2/3 bg-muted rounded animate-pulse" />
          <div className="h-4 w-full bg-muted rounded animate-pulse" />
          <div className="h-4 w-1/2 bg-muted rounded animate-pulse" />
        </div>
        <div className="h-32 bg-muted rounded-2xl animate-pulse" />
        <div className="h-32 bg-muted rounded-2xl animate-pulse" />
        <div className="h-14 bg-muted rounded-2xl animate-pulse" />
      </div>
    );
  }

  if (error || !item) {
    return (
      <div className="text-center py-16 space-y-4">
        <MascotStandee mascot="worried" className="w-32 h-32 mx-auto" alt="Item not found" />
        <p className="text-sm text-muted-foreground">{error || 'Item not found'}</p>
        <div className="flex items-center justify-center gap-2">
          <button onClick={() => setRetryCount((c) => c + 1)} className="px-4 py-2 rounded-xl bg-primary text-white text-xs font-bold hover:bg-primary-hover transition-colors">Try again</button>
          <button onClick={() => navigate('/menu')} className="px-4 py-2 rounded-xl bg-muted border border-border text-foreground text-xs font-bold">Back to menu</button>
        </div>
      </div>
    );
  }

  const errors = validateSelections();
  const totalPrice = calculatePrice();
  const lowStock = item.daily_remaining != null && item.daily_remaining <= 10 && !item.is_sold_out;
  const stockLevel = item.daily_remaining == null ? 'mid' : item.daily_remaining <= 2 ? 'critical' : item.daily_remaining <= 5 ? 'low' : 'mid';
  const stockBadgeBg = stockLevel === 'critical' ? 'bg-red-600' : stockLevel === 'low' ? 'bg-orange-500' : 'bg-amber-500';

  return (
    <div className="animate-fade-in pb-8">
      <SEO
        title={item.name}
        description={item.description || `${item.name}, flame grilled and delivered across FUTA.`}
        image={item.image_url}
        path={`/menu/${item.id}`}
        jsonLd={menuItemJsonLd(item)}
      />

      {/* Full-bleed hero image */}
      <motion.div
        className="relative -mx-4 sm:-mx-6 lg:-mx-8 -mt-6 h-[42vh] sm:h-[48vh] overflow-hidden bg-muted shadow-card"
      >
        <img src={item.image_url} alt={item.name} className="w-full h-full object-cover" />
        {/* Gradient overlay for badge legibility + fade into content */}
        <div className="absolute inset-0 bg-gradient-to-t from-background/30 via-transparent to-black/15" />

        {/* Back button */}
        <button
          onClick={() => navigate('/menu')}
          aria-label="Back to menu"
          className="absolute top-3 left-3 w-9 h-9 rounded-full glass border border-white/30 flex items-center justify-center text-foreground hover:scale-105 transition-transform"
        >
          <ChevronLeft className="w-5 h-5" />
        </button>

        {/* HP badge */}
        <div className="absolute top-3 right-3 flex items-center gap-1 px-3 py-1.5 rounded-xl bg-card/95 text-accent-foreground text-xs font-bold shadow-card backdrop-blur">
          <Flame className="w-3.5 h-3.5 text-primary" />+{item.hp_earn_value} HP
        </div>

        {/* Multiplier badge */}
        {item.hp_multiplier && item.hp_multiplier !== 1 && (
          <div className="absolute top-14 right-3 px-2 py-1 rounded-lg bg-gradient-cta text-white text-[10px] font-bold shadow-glow">
            {item.hp_multiplier === 2 ? '2× HP' : item.hp_multiplier === 0.5 ? '½× HP' : `${item.hp_multiplier}× HP`}
          </div>
        )}

        {/* Featured indicator — star icon at top, never covered by the content panel */}
        {item.is_featured && (
          <div className="absolute top-3 left-14 w-9 h-9 rounded-full glass border border-white/30 flex items-center justify-center shadow-card" title="Featured">
            <Star className="w-4 h-4 text-accent fill-accent" />
          </div>
        )}

        {/* Sold out overlay */}
        {item.is_sold_out && (
          <div className="absolute inset-0 bg-black/50 flex items-center justify-center">
            <span className="px-4 py-2 rounded-xl bg-foreground text-white font-bold text-sm">Sold Out</span>
          </div>
        )}

        {/* Low stock badge */}
        {lowStock && (
          <div className={`absolute bottom-3 left-3 px-3 py-1.5 rounded-xl ${stockBadgeBg} text-white text-xs font-bold animate-pulse`}>
            Only {item.daily_remaining} left today!
          </div>
        )}
      </motion.div>

      {/* Overlapping content panel */}
      <div className="relative -mt-6 rounded-t-3xl bg-background max-w-2xl mx-auto px-4 sm:px-6 lg:px-8 pt-5 space-y-5">

      {/* Info */}
      <motion.div variants={fadeUp} initial="hidden" animate="show">
        <div className="flex items-start justify-between gap-3">
          <h1 className="font-heading font-bold text-xl text-foreground leading-tight">{item.name}</h1>
          <button
            onClick={handleSaveToggle}
            aria-label={saved ? 'Remove from favourites' : 'Save to favourites'}
            className={`shrink-0 w-10 h-10 rounded-xl flex items-center justify-center transition-all ${saved ? 'bg-primary/10 text-primary' : 'bg-card border border-border text-muted-foreground hover:border-primary/30'}`}
          >
            <Heart className={`w-5 h-5 ${saved ? 'fill-primary' : ''}`} />
          </button>
        </div>
        {item.avg_rating != null && (
          <div className="mt-1.5"><RatingStars rating={item.avg_rating} count={item.review_count} size="md" /></div>
        )}
        <p className="hg-body mt-2 leading-relaxed">{item.description}</p>
        <div className="flex items-center flex-wrap gap-x-4 gap-y-1 mt-3">
          <span className="font-heading font-bold text-xl text-foreground">{formatNaira(item.price)}</span>
          {item.daily_limit != null && (
            <span className="hg-caption">Daily limit: {item.daily_limit} · {item.daily_remaining ?? '—'} remaining</span>
          )}
        </div>
      </motion.div>

      {/* Variation Groups */}
      {(item.variation_groups || []).map((vg) => (
        <motion.div key={vg.id} variants={fadeUp} initial="hidden" animate="show" className="hg-card space-y-3">
          <div className="flex items-center justify-between">
            <h3 className="hg-section-title">{vg.name}</h3>
            <span className={`text-[10px] font-semibold uppercase px-2 py-0.5 rounded-lg ${vg.is_required ? 'bg-primary/15 text-primary' : 'bg-muted text-muted-foreground'}`}>
              {vg.is_required ? 'Required' : 'Optional'}
            </span>
          </div>
          <p className="hg-caption">
            {vg.min_selections === vg.max_selections ? `Choose exactly ${vg.min_selections}` : `Choose ${vg.min_selections}–${vg.max_selections}`}
          </p>
          <div className="space-y-2">
            {(vg.options || []).map((opt) => {
              const selected = (selections[vg.id] || []).includes(opt.id);
              const isRadio = vg.max_selections === 1;
              return (
                <button
                  key={opt.id}
                  onClick={() => toggleVariation(vg.id, opt.id, vg.max_selections)}
                  disabled={item.is_sold_out}
                  className={`w-full flex items-center justify-between p-3 rounded-xl border transition-all ${selected ? 'border-primary bg-primary/5' : 'border-border hover:border-primary/30 hover:bg-muted/50'} disabled:opacity-50 disabled:cursor-not-allowed`}
                >
                  <div className="flex items-center gap-3">
                    <div className={`w-5 h-5 ${isRadio ? 'rounded-full' : 'rounded'} border-2 flex items-center justify-center transition-all ${selected ? 'border-primary bg-primary' : 'border-border'}`}>
                      {selected && <Check className="w-3 h-3 text-white" />}
                    </div>
                    <span className="text-sm font-medium text-foreground">{opt.name}</span>
                  </div>
                  {opt.price_delta > 0 && <span className="text-xs font-bold text-muted-foreground">+{formatNaira(opt.price_delta)}</span>}
                </button>
              );
            })}
          </div>
        </motion.div>
      ))}

      {/* Addon Groups */}
      {addonGroups.map((ag) => (
        <motion.div key={ag.id} variants={fadeUp} initial="hidden" animate="show" className="hg-card space-y-3">
          <div className="flex items-center justify-between">
            <h3 className="hg-section-title">{ag.name}</h3>
            <span className={`text-[10px] font-semibold uppercase px-2 py-0.5 rounded-lg ${ag.is_required ? 'bg-primary/15 text-primary' : 'bg-muted text-muted-foreground'}`}>
              {ag.is_required ? 'Required' : 'Optional'}
            </span>
          </div>
          <p className="hg-caption">
            {ag.min_select === ag.max_select ? `Choose exactly ${ag.min_select}` : `Choose up to ${ag.max_select}`}
          </p>
          <div className="space-y-2">
            {(ag.addons || []).map((ad) => {
              const selected = (selections[ag.id] || []).includes(ad.id);
              return (
                <button
                  key={ad.id}
                  onClick={() => toggleAddon(ag.id, ad.id, ag.max_select)}
                  disabled={item.is_sold_out}
                  className={`w-full flex items-center justify-between p-3 rounded-xl border transition-all ${selected ? 'border-primary bg-primary/5' : 'border-border hover:border-primary/30 hover:bg-muted/50'} disabled:opacity-50 disabled:cursor-not-allowed`}
                >
                  <div className="flex items-center gap-3">
                    <div className={`w-5 h-5 rounded border-2 flex items-center justify-center transition-all ${selected ? 'border-primary bg-primary' : 'border-border'}`}>
                      {selected && <Check className="w-3 h-3 text-white" />}
                    </div>
                    <span className="text-sm font-medium text-foreground">{ad.name}</span>
                  </div>
                  {ad.price > 0 && <span className="text-xs font-bold text-muted-foreground">+{formatNaira(ad.price)}</span>}
                </button>
              );
            })}
          </div>
        </motion.div>
      ))}

      {/* Special Instructions */}
      <motion.div variants={fadeUp} initial="hidden" animate="show" className="hg-card space-y-2">
        <h3 className="hg-section-title">Special Instructions</h3>
        <textarea
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          placeholder="e.g., No onions, extra crispy..."
          disabled={item.is_sold_out}
          className="w-full p-3 rounded-xl border border-border bg-card text-sm resize-none focus:outline-none focus:border-primary focus:ring-2 focus:ring-primary/20 transition-all disabled:opacity-50"
          rows={2}
        />
      </motion.div>

      {/* Action bar */}
      <motion.div variants={fadeUp} initial="hidden" animate="show" className="hg-card space-y-3">
        {/* Checkout — primary, full-width, the one that pops */}
        <motion.button
          whileTap={{ scale: 0.97 }}
          onClick={handleCheckoutNow}
          disabled={item.is_sold_out || errors.length > 0 || adding}
          className="w-full flex items-center justify-center gap-2 py-3.5 rounded-xl bg-gradient-cta text-white font-bold text-sm shadow-glow hover:opacity-90 transition-opacity disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {adding ? (
            <span className="flex items-center gap-2">
              <span className="w-4 h-4 border-2 border-white/40 border-t-white rounded-full animate-spin" />
              Adding...
            </span>
          ) : (
            <>Checkout · {formatNaira(totalPrice)}</>
          )}
        </motion.button>

        <div className="flex items-center gap-2 sm:gap-3">
          {/* Quantity stepper */}
          <div className="flex items-center gap-1 bg-muted rounded-xl p-1 shrink-0">
            <button
              onClick={() => setQuantity(Math.max(1, quantity - 1))}
              disabled={quantity <= 1 || item.is_sold_out}
              className="w-9 h-9 rounded-lg bg-card border border-border flex items-center justify-center hover:border-primary/30 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
              aria-label="Decrease quantity"
            >
              <Minus className="w-4 h-4 text-foreground" />
            </button>
            <span className="font-heading font-bold text-foreground w-7 text-center select-none">{quantity}</span>
            <button
              onClick={() => setQuantity(quantity + 1)}
              disabled={item.is_sold_out}
              className="w-9 h-9 rounded-lg bg-card border border-border flex items-center justify-center hover:border-primary/30 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
              aria-label="Increase quantity"
            >
              <Plus className="w-4 h-4 text-foreground" />
            </button>
          </div>

          {/* Add to Cart — secondary, less obvious */}
          <motion.button
            whileTap={{ scale: 0.97 }}
            onClick={handleAddToCart}
            disabled={item.is_sold_out || errors.length > 0 || adding}
            className="flex-1 flex items-center justify-center gap-2 py-3.5 rounded-xl bg-card border border-border text-foreground font-bold text-sm hover:border-primary/40 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <ShoppingCart className="w-4 h-4" />
            Add to Cart
          </motion.button>
        </div>
        {errors.length > 0 && (
          <div className="flex items-center gap-1.5 text-xs text-destructive font-medium">
            <AlertCircle className="w-3.5 h-3.5 shrink-0" />
            {errors[0]}
          </div>
        )}
      </motion.div>

      </div>
    </div>
  );
}