import { useState, useEffect } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { motion } from 'framer-motion';
import { Minus, Plus, Trash2, Flame, AlertTriangle, ChevronRight, Heart, Wallet as WalletIcon } from 'lucide-react';
import { mockApi } from '@/lib/mockApi';
import { useHolyGrill } from '@/lib/HolyGrillContext';
import { useSound } from '@/lib/SoundProvider';
import { formatNaira } from '@/lib/hgUtils';
import { toast } from '@/components/ui/use-toast';
import { msg } from '@/lib/messages';
import OrderSuggestionCard from '@/components/OrderSuggestionCard';
import { fadeUp, staggerContainer } from '@/lib/animationPresets';
import MascotStandee from '@/components/mascot/MascotStandee';
import Skeleton from '@/components/Skeleton';

function CartSkeleton() {
  return (
    <div className="space-y-3">
      {Array.from({ length: 3 }).map((_, i) => (
        <div key={i} className="flex gap-3 rounded-2xl bg-card border border-border p-3">
          <Skeleton className="w-16 h-16 rounded-xl shrink-0" />
          <div className="flex-1 space-y-2">
            <Skeleton className="h-4 w-2/3" />
            <Skeleton className="h-3 w-full" />
            <Skeleton className="h-8 w-32 rounded-lg" />
          </div>
        </div>
      ))}
    </div>
  );
}

export default function Cart() {
  const navigate = useNavigate();
  const { cart, wallet, refreshCart, updateCartItem, removeFromCart, clearCart, savedItems, moveSavedToCart, removeSavedItem: removeSaved, refreshSavedItems, isAuthenticated: isAuthed } = useHolyGrill();
  const { play } = useSound();
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState('cart');

  useEffect(() => {
    refreshCart().then(() => setLoading(false));
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // E3: promo codes and squad orders live in Checkout (it owns the promo input
  // and the squad selector). The state removed here could no longer be set, so
  // promoDiscount/squadDiscount were always 0 and `total` was always `subtotal`.
  const subtotal = cart?.subtotal || 0;

  const handleQty = async (itemId, currentQty, delta) => {
    const newQty = currentQty + delta;
    if (newQty <= 0) { play('cart_remove'); await removeFromCart(itemId); }
    else { play('cart_add'); await updateCartItem(itemId, { quantity: newQty }); }
  };

  const handleRemove = (itemId) => { play('cart_remove'); removeFromCart(itemId); };

  const [savingId, setSavingId] = useState(null);
  const handleSaveForLater = async (ci) => {
    if (!isAuthed) { toast({ title: msg('FE_CART_SIGNIN_TO_SAVE_TITLE', 'Sign in to save items'), description: msg('FE_CART_SIGNIN_TO_SAVE_BODY', 'Saved items sync to your account.') }); return; }
    setSavingId(ci.id);
    try {
      await mockApi.saved.fromCart(ci.id);
      await refreshSavedItems();
      await refreshCart();
      toast({ title: msg('FE_CART_SAVED_TITLE', '❤️ Saved to your favourites'), description: msg('FE_CART_SAVED_BODY', '{item} moved to Saved Items.', { item: ci.menu_items.name }) });
    } catch (e) {
      toast({ title: msg('FE_CART_SAVE_FAILED_TITLE', 'Could not save item'), description: e.message, variant: 'destructive' });
    }
    setSavingId(null);
  };

  const handleMoveToCart = async (saved) => {
    play('cart_add');
    await moveSavedToCart(saved);
    if (savedItems.length === 1) setTab('cart');
    toast({ title: msg('FE_CART_MOVED_BACK_TITLE', 'Moved to cart'), description: msg('FE_CART_MOVED_BACK_BODY', '{item} is back in your cart.', { item: (saved.menu_items || saved).name || 'Item' }) });
  };

  const handleRemoveSaved = (saved) => { removeSaved(saved.id); };

  // Checkout still reads `subtotal` as a fallback when the cart object has not
  // loaded yet (Checkout.tsx), so that stays part of the navigation contract.
  const handleCheckout = () => navigate('/checkout', { state: { subtotal } });

  if (loading) {
    return (
      <div className="space-y-4 animate-fade-in">
        <div className="h-8 w-32 bg-muted rounded animate-pulse" />
        <CartSkeleton />
      </div>
    );
  }

  const empty = !cart || cart.items.length === 0;
  const savedCount = savedItems.length;

  if (empty && savedCount === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-20 text-center animate-fade-in space-y-5">
        <MascotStandee mascot="worried" className="w-32 h-32" alt="Your cart is empty" />
        <div className="space-y-1.5">
          <h2 className="font-heading font-extrabold text-xl text-foreground">My Holy Order ❤️‍🔥</h2>
          <p className="text-sm text-muted-foreground max-w-xs mx-auto">Nothing here yet.</p>
        </div>
        <button onClick={() => navigate('/menu')} className="px-7 py-3 rounded-full bg-gradient-cta text-white font-bold text-sm shadow-glow active:scale-95 transition">Browse Menu →</button>
      </div>
    );
  }

  return (
    <div className="space-y-4 animate-fade-in pb-4">
      <OrderSuggestionCard />

      {/* Tabs + Wallet */}
      <div className="flex items-center justify-between gap-2">
        <div className="flex gap-2">
          <button onClick={() => setTab('cart')} className={`px-4 py-2 rounded-xl text-xs font-semibold transition-all ${tab === 'cart' ? 'bg-gradient-cta text-white shadow-glow' : 'bg-card text-muted-foreground border border-border'}`}>
            My Cart {cart?.item_count > 0 && `(${cart.item_count})`}
          </button>
          <button onClick={() => setTab('saved')} className={`flex items-center gap-1 px-4 py-2 rounded-xl text-xs font-semibold transition-all ${tab === 'saved' ? 'bg-gradient-cta text-white shadow-glow' : 'bg-card text-muted-foreground border border-border'}`}>
            <Heart className={`w-3.5 h-3.5 ${tab === 'saved' ? 'fill-white' : ''}`} />
            Saved {savedCount > 0 && `(${savedCount})`}
          </button>
        </div>
        <Link to="/wallet" className="flex items-center gap-2.5 rounded-2xl bg-card border border-border px-3 py-2 shadow-card hover:shadow-glow transition-shadow">
          <div className="w-8 h-8 rounded-xl bg-primary/10 flex items-center justify-center shrink-0">
            <WalletIcon className="w-4 h-4 text-primary" />
          </div>
          <div className="leading-tight">
            <div className="text-[10px] text-muted-foreground font-medium">Wallet</div>
            <div className="text-sm font-bold text-foreground">{formatNaira(wallet?.balance || 0)}</div>
          </div>
        </Link>
      </div>

      {tab === 'cart' ? (
        empty ? (
          <div className="text-center py-12 space-y-3">
            <p className="text-sm text-muted-foreground">Your cart is empty.</p>
            {savedCount > 0 && <button onClick={() => setTab('saved')} className="text-xs font-bold text-primary">View Saved Items →</button>}
          </div>
        ) : (
          <>
            {/* Header */}
            <div className="flex items-center justify-between">
              <div>
                <h1 className="font-heading font-bold text-xl text-foreground">Your Cart</h1>
                <p className="text-sm text-muted-foreground">{cart.item_count} item{cart.item_count !== 1 ? 's' : ''}</p>
              </div>
              <button onClick={clearCart} className="text-xs font-semibold text-destructive hover:text-destructive flex items-center gap-1 transition-colors">
                <Trash2 className="w-3.5 h-3.5" /> Clear all
              </button>
            </div>

            {cart.has_unavailable_items && (
              <div className="flex items-center gap-2 p-3 rounded-xl bg-amber-50 border border-amber-200">
                <AlertTriangle className="w-5 h-5 text-amber-600 shrink-0" />
                <div className="text-xs text-amber-800">An item sold out. Remove it.</div>
              </div>
            )}

            {/* HP Preview */}
            <motion.div
              initial={{ opacity: 0, y: -8 }}
              animate={{ opacity: 1, y: 0 }}
              className="flex items-center gap-2.5 p-3.5 rounded-2xl bg-gradient-cta text-white shadow-glow"
            >
              <Flame className="w-5 h-5 text-white shrink-0 animate-flame-flicker" />
              <div className="flex-1">
                <span className="font-bold text-sm">You'll earn {cart.hp_earn_preview} HP</span>
                <span className="text-xs text-white/80"> on this order</span>
              </div>
            </motion.div>

            {/* Items */}
            <motion.div variants={staggerContainer(0.04)} initial="hidden" animate="show" className="space-y-3">
              {cart.items.map((ci) => (
                <motion.div key={ci.id} variants={fadeUp} className={`rounded-2xl bg-card border p-3 shadow-card ${ci.is_unavailable ? 'border-destructive/30 opacity-60' : 'border-border'}`}>
                  <div className="flex gap-3">
                    {ci.menu_items?.image_url ? (
                      <img src={ci.menu_items.image_url} alt={ci.menu_items.name} className="w-16 h-16 rounded-xl object-cover shrink-0" />
                    ) : (
                      <div className="w-16 h-16 rounded-xl bg-primary/10 flex items-center justify-center shrink-0">
                        <Flame className="w-6 h-6 text-primary/40" />
                      </div>
                    )}
                    <div className="flex-1 min-w-0">
                      <h3 className="font-bold text-sm text-foreground">{ci.menu_items?.name}</h3>
                      {ci.notes && <p className="text-xs text-muted-foreground mt-0.5">📝 {ci.notes}</p>}
                      {ci.is_unavailable && <p className="text-xs text-destructive mt-0.5">⚠️ No longer available</p>}
                      <div className="flex items-center justify-between mt-2">
                        <div className="flex items-center gap-1 bg-muted rounded-lg p-1">
                          <button onClick={() => handleQty(ci.id, ci.quantity, -1)} className="w-7 h-7 rounded-lg bg-card border border-border flex items-center justify-center hover:border-primary/30 transition-colors"><Minus className="w-3.5 h-3.5 text-muted-foreground" /></button>
                          <span className="font-bold text-foreground w-5 text-center text-sm">{ci.quantity}</span>
                          <button onClick={() => handleQty(ci.id, ci.quantity, 1)} disabled={ci.is_unavailable} className="w-7 h-7 rounded-lg bg-card border border-border flex items-center justify-center disabled:opacity-40 hover:border-primary/30 transition-colors"><Plus className="w-3.5 h-3.5 text-muted-foreground" /></button>
                        </div>
                        <div className="flex items-center gap-3">
                          <button onClick={() => handleSaveForLater(ci)} disabled={savingId === ci.id} className="text-muted-foreground hover:text-primary transition-colors" title="Save for later"><Heart className="w-4 h-4" /></button>
                          <button onClick={() => handleRemove(ci.id)} className="text-destructive hover:text-destructive transition-colors"><Trash2 className="w-4 h-4" /></button>
                        </div>
                      </div>
                    </div>
                    <div className="text-right shrink-0">
                      <div className="font-heading font-bold text-foreground">{formatNaira((ci.menu_items?.price || 0) * ci.quantity)}</div>
                      <div className="flex items-center gap-1 mt-1 justify-end">
                        <Flame className="w-3 h-3 text-primary" />
                        <span className="text-xs font-semibold text-primary">
                          +{Math.round((ci.menu_items?.hp_earn_value || 0) * (ci.menu_items?.hp_multiplier || 1) * ci.quantity)}
                          {ci.menu_items?.hp_multiplier && ci.menu_items.hp_multiplier !== 1 && (
                            <span className="text-[9px] ml-0.5">({ci.menu_items.hp_multiplier}×)</span>
                          )}
                        </span>
                      </div>
                    </div>
                  </div>
                </motion.div>
              ))}
            </motion.div>

            {/* Summary */}
            <div className="hg-card space-y-2">
              <div className="flex items-center justify-between text-sm"><span className="text-muted-foreground">Subtotal</span><span className="font-semibold text-foreground">{formatNaira(subtotal)}</span></div>
              <div className="border-t border-border pt-2 flex items-center justify-between"><span className="font-semibold text-foreground">Total</span><span className="font-heading font-bold text-lg text-foreground">{formatNaira(subtotal)}</span></div>
            </div>

            <motion.button whileTap={{ scale: 0.97 }} onClick={handleCheckout} disabled={cart.has_unavailable_items} className="w-full flex items-center justify-center gap-2 py-4 rounded-xl bg-gradient-cta text-white font-bold shadow-glow disabled:opacity-50">
              Checkout · {formatNaira(subtotal)} <ChevronRight className="w-4 h-4" />
            </motion.button>
          </>
        )
      ) : (
        /* Saved items tab */
        <div className="space-y-3">
          <h1 className="font-heading font-bold text-xl text-foreground flex items-center gap-2">
            <Heart className="w-5 h-5 text-primary fill-primary" /> Saved Items
          </h1>
          {savedCount === 0 ? (
            <div className="text-center py-12 space-y-3">
              <Heart className="w-10 h-10 text-muted mx-auto mb-2" />
              <p className="text-sm text-muted-foreground">Nothing saved yet.</p>
            </div>
          ) : (
            savedItems.map((s) => {
              const mi = s.menu_items || {};
              const name = mi.name || s.name || 'Saved item';
              const price = mi.price ?? s.price ?? 0;
              return (
              <div key={s.id} className="rounded-2xl bg-card border border-border p-3 flex items-center gap-3 shadow-card">
                {mi.image_url ? (
                  <img src={mi.image_url} alt={name} className="w-12 h-12 rounded-xl object-cover shrink-0" />
                ) : (
                  <div className="w-12 h-12 rounded-xl bg-primary/10 flex items-center justify-center shrink-0"><Heart className="w-5 h-5 text-primary/40" /></div>
                )}
                <div className="flex-1 min-w-0">
                  <h3 className="font-bold text-sm text-foreground truncate">{name}</h3>
                  <p className="text-xs text-muted-foreground">{s.quantity || 1}× · {formatNaira(price * (s.quantity || 1))}</p>
                </div>
                <button onClick={() => handleMoveToCart(s)} className="px-3 py-2 rounded-xl bg-primary text-white text-xs font-bold hover:bg-primary-hover transition-colors">Move to cart</button>
                <button onClick={() => handleRemoveSaved(s)} className="text-destructive hover:text-destructive transition-colors"><Trash2 className="w-4 h-4" /></button>
              </div>
              );
            })
          )}
        </div>
      )}

    </div>
  );
}