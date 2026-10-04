import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Search, X, Clock, AlertTriangle, Gift, Users, ChevronRight } from 'lucide-react';
import { Link } from 'react-router-dom';
import { motion } from 'framer-motion';
import { mockApi } from '@/lib/mockApi';
import { useHolyGrill } from '@/lib/HolyGrillContext';
import { useSound } from '@/lib/SoundProvider';
import { toast } from '@/components/ui/use-toast';
import MenuGridCard from '@/components/MenuGridCard';
import KitchenStatusBox from '@/components/KitchenStatusBox';
import { staggerContainer } from '@/lib/animationPresets';
import SEO from '@/components/SEO';
import MascotStandee from '@/components/mascot/MascotStandee';


function MenuSkeleton() {
  return (
    <div className="grid grid-cols-2 lg:grid-cols-3 gap-2.5 max-w-5xl mx-auto">
      {Array.from({ length: 6 }).map((_, i) => (
        <div key={i} className="bg-card rounded-2xl border border-border overflow-hidden">
          <div className="aspect-[4/3] bg-muted animate-pulse" />
          <div className="p-2.5 sm:p-3 space-y-2">
            <div className="h-3.5 w-2/3 bg-muted rounded animate-pulse" />
            <div className="h-3 w-1/2 bg-muted rounded animate-pulse" />
          </div>
        </div>
      ))}
    </div>
  );
}

export default function Menu() {
  const navigate = useNavigate();
  const { addToCart, isAuthenticated: isAuthed } = useHolyGrill();
  const { play } = useSound();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [items, setItems] = useState([]);
  const [kitchenCapacity, setKitchenCapacity] = useState(null);
  const [windowStatus, setWindowStatus] = useState(null);
  const [categories, setCategories] = useState([]);
  const [activeCategory, setActiveCategory] = useState(null);
  const [searchInput, setSearchInput] = useState('');
  const [search, setSearch] = useState('');
  const [freeSideCredits, setFreeSideCredits] = useState(0);
  const [retryNonce, setRetryNonce] = useState(0);

  // Debounce search input → search query
  useEffect(() => {
    const t = setTimeout(() => setSearch(searchInput.trim()), 300);
    return () => clearTimeout(t);
  }, [searchInput]);

  // Load static metadata on mount
  useEffect(() => {
    mockApi.menu.getCategories().then(setCategories).catch(() => {});
    mockApi.orders.getDeliveryWindowStatus().then(setWindowStatus).catch(() => {});
    mockApi.menu.getKitchenCapacity().then(setKitchenCapacity).catch(() => {});
    if (isAuthed) {
      mockApi.rewards.getFreeSideCredits().then((res) => {
        const count = res?.count ?? res?.credits ?? (Array.isArray(res) ? res.length : 0);
        setFreeSideCredits(Number(count) || 0);
      }).catch(() => {});
    }
  }, [isAuthed]);

  // Load items on filter/search change
  useEffect(() => {
    const load = async () => {
      setLoading(true);
      setError(null);
      try {
        const params = {};
        if (activeCategory) params.category = activeCategory;
        if (search) params.q = search;
        params.available_only = 'false';
        const result = await mockApi.menu.getItems(params);
        setItems(result.items || []);
      } catch (e) {
        setError('Failed to fetch menu items.');
      }
      setLoading(false);
    };
    load();
  }, [activeCategory, search, retryNonce]);

  // Quick add — if the item needs required modifiers, send to detail page
  const handleAdd = async (item) => {
    try {
      const detail = await mockApi.menu.getItem(item.id);
      const addons = await mockApi.menu.getAddons(item.id);
      const hasRequired =
        (detail.variation_groups || []).some((vg) => vg.is_required) ||
        (addons.addon_groups || []).some((ag) => ag.is_required);
      if (!hasRequired) {
        play('cart_add');
        await addToCart({ menu_item_id: item.id, quantity: 1 });
        toast({ title: 'Added to your cart', description: `${item.name} is ready to checkout.` });
      } else {
        navigate(`/menu/${item.id}`);
      }
    } catch (e) {
      toast({ title: 'Could not add item', description: e.message || 'Please try again.', variant: 'destructive' });
    }
  };

  const open = windowStatus?.is_open;
  const atCapacity = kitchenCapacity?.is_at_capacity ?? kitchenCapacity?.at_capacity ?? false;

  return (
    <div className="space-y-3 animate-fade-in">
      <SEO
        title="Today's Menu"
        description="Browse the full Holy Grills menu, flame grilled chicken, wings, kebabs and crispy sides, delivered hot across FUTA."
        path="/menu"
      />

      {/* Header */}
      <div>
        <span className="hg-eyebrow">Today's menu</span>
        <h1 className="font-heading font-bold text-xl text-foreground mt-0.5 flex items-center gap-1.5">Fresh Off the Grill 🔥</h1>
        <p className="text-sm text-muted-foreground mt-1">Order for your table.</p>
      </div>

      {/* Kitchen status — compact one-line radar so menu items stay near the top */}
      <KitchenStatusBox compact />

      {/* Free side credits banner */}
      {freeSideCredits > 0 && (
        <motion.div
          initial={{ opacity: 0, y: -8 }}
          animate={{ opacity: 1, y: 0 }}
          className="flex items-center gap-2 px-3 py-2.5 rounded-xl bg-gradient-gold text-accent-foreground text-xs font-bold shadow-card"
        >
          <Gift className="w-4 h-4 shrink-0" />
          <span>You have {freeSideCredits} free side credit{freeSideCredits !== 1 ? 's' : ''}. Claim one at checkout.</span>
        </motion.div>
      )}

      {/* Search */}
      <div className="relative">
        <Search className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
        <input
          type="text"
          placeholder="Search the grill..."
          value={searchInput}
          onChange={(e) => setSearchInput(e.target.value)}
          className="w-full pl-11 pr-10 py-3 rounded-xl bg-card border border-border text-sm focus:outline-none focus:border-primary focus:ring-2 focus:ring-primary/20 transition-all"
        />
        {searchInput && (
          <button onClick={() => setSearchInput('')} className="absolute right-3.5 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground transition-colors" aria-label="Clear search">
            <X className="w-4 h-4" />
          </button>
        )}
      </div>

      {/* Squad shortcut */}
      {isAuthed && (
        <Link to="/squads" className="flex items-center gap-2.5 px-3.5 py-2 rounded-xl bg-card border border-border hover:border-primary/40 transition-colors">
          <Users className="w-4 h-4 text-primary shrink-0" />
          <span className="text-xs font-bold text-foreground">Manage your squads</span>
          <span className="text-[10px] font-medium text-muted-foreground hidden sm:inline">tag orders · split HP</span>
          <ChevronRight className="w-3.5 h-3.5 text-muted-foreground ml-auto shrink-0" />
        </Link>
      )}

      {/* Category pills */}
      <div className="flex gap-2 overflow-x-auto scrollbar-hide -mx-4 px-4 pb-1">
        <button
          onClick={() => setActiveCategory(null)}
          className={`flex-shrink-0 px-4 py-2 rounded-full text-xs font-semibold transition-all ${!activeCategory ? 'bg-gradient-cta text-white shadow-glow' : 'bg-card text-muted-foreground border border-border hover:border-primary/30'}`}
        >
          All Items
        </button>
        {categories.map((cat) => (
          <button
            key={cat.id}
            onClick={() => setActiveCategory(cat.slug)}
            className={`flex-shrink-0 px-4 py-2 rounded-full text-xs font-semibold transition-all ${activeCategory === cat.slug ? 'bg-gradient-cta text-white shadow-glow' : 'bg-card text-muted-foreground border border-border hover:border-primary/30'}`}
          >
            {cat.name}
          </button>
        ))}
      </div>

      {/* Item count + clear filter */}
      {!loading && !error && items.length > 0 && (
        <div className="flex items-center justify-between">
          <p className="text-xs text-muted-foreground font-medium">{items.length} item{items.length !== 1 ? 's' : ''}{activeCategory && ' · filtered'}</p>
          {(activeCategory || search) && (
            <button
              onClick={() => { setActiveCategory(null); setSearchInput(''); }}
              className="text-xs font-semibold text-primary hover:text-primary-hover transition-colors"
            >
              Clear all
            </button>
          )}
        </div>
      )}

      {/* Items grid */}
      {loading ? (
        <MenuSkeleton />
      ) : error ? (
        <div className="text-center py-12 space-y-3">
          <MascotStandee mascot="worried" className="w-28 h-28 mx-auto" alt="Couldn't load the menu" />
          <p className="text-sm text-muted-foreground">{error}</p>
          <button onClick={() => { setLoading(true); setRetryNonce((n) => n + 1); }} className="px-4 py-2 rounded-xl bg-primary text-white text-xs font-bold hover:bg-primary-hover active:scale-95 transition">Retry</button>
        </div>
      ) : items.length === 0 ? (
        <div className="text-center py-12 space-y-3">
          <MascotStandee mascot="worried" className="w-28 h-28 mx-auto" alt="No menu items found" />
          <p className="text-sm text-muted-foreground">
            {search ? `No items match "${search}"` : 'No items available right now'}
          </p>
          {(search || activeCategory) && (
            <button
              onClick={() => { setSearchInput(''); setActiveCategory(null); }}
              className="px-4 py-2 rounded-xl bg-primary text-white text-xs font-bold hover:bg-primary-hover transition-colors"
            >
              Browse all items
            </button>
          )}
        </div>
      ) : (
        <motion.div
          variants={staggerContainer(0.04)}
          initial="hidden"
          animate="show"
          className="grid grid-cols-2 lg:grid-cols-3 gap-2.5 max-w-5xl mx-auto"
        >
          {items.map((item) => (
            <MenuGridCard key={item.id} item={item} onAdd={handleAdd} />
          ))}
        </motion.div>
      )}
    </div>
  );
}