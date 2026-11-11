import { useResumeEffect } from '@/hooks/useResumeEffect';
import { useCampus } from '@/lib/campusContext';
import HeroCarousel from '@/components/HeroCarousel';
import StorefrontSlider from '@/components/storefront/StorefrontSlider';
import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Search, X, Gift, Users, ChevronRight } from 'lucide-react';
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
import { ROUTE_META } from '@/seo/routeMeta';
import MascotStandee from '@/components/mascot/MascotStandee';
import { msg } from '@/lib/messages';


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
  const { campusId } = useCampus();
  const { addToCart, isAuthenticated: isAuthed } = useHolyGrill();
  const { play } = useSound();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [catalogue, setCatalogue] = useState([]);
  const [catalogueCampus, setCatalogueCampus] = useState<string | null>(null);
  const [remoteSearch, setRemoteSearch] = useState<{ campus: string; query: string; items: any[] } | null>(null);
  const [searching, setSearching] = useState(false);
  const [searchError, setSearchError] = useState(false);
  const [refreshError, setRefreshError] = useState(false);
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
  useResumeEffect(() => {
    if (!campusId) return;
    mockApi.menu.getCategories({ campus_id: campusId }).then(setCategories).catch(() => {});
    if (isAuthed) {
      mockApi.rewards.getFreeSideCredits().then((res) => {
        const count = res?.count ?? res?.credits ?? (Array.isArray(res) ? res.length : 0);
        setFreeSideCredits(Number(count) || 0);
      }).catch(() => {});
    }
  }, [isAuthed, campusId]);

  // Category filters use the catalogue already in memory. Fetch on campus
  // changes, explicit retries and genuine browser returns only.
  useResumeEffect((background) => {
    if (!campusId) return;
    let alive = true;
    const load = async () => {
      if (!background && catalogueCampus !== campusId) setLoading(true);
      if (!background) setError(null);
      try {
        const params: Record<string, string> = { campus_id: campusId };
        params.available_only = 'true';
        const result = await mockApi.menu.getItems(params);
        const sortedItems = (result.items || []).slice().sort((a, b) => {
          const priceDiff = (Number(a.price) || 0) - (Number(b.price) || 0);
          if (priceDiff !== 0) return priceDiff;
          return (a.name || '').localeCompare(b.name || '');
        });
        if (alive) { setCatalogue(sortedItems); setCatalogueCampus(campusId); setError(null); setRefreshError(false); }
      } catch (e) {
        if (alive && catalogueCampus === campusId) setRefreshError(true);
        else if (alive && !background) setError(msg('FE_MENU_FAILED_TO_FETCH_MENU_ITEMS', 'Failed to fetch menu items.'));
      }
      if (alive) setLoading(false);
    };
    load();
    return () => { alive = false; };
  }, [retryNonce, campusId]);

  // Known matches render immediately; remote search still discovers secret
  // items and revalidates availability without blanking the catalogue.
  useEffect(() => {
    if (!campusId || !search) { setSearching(false); setRemoteSearch(null); setSearchError(false); return; }
    let current = true;
    setSearching(true); setSearchError(false);
    mockApi.menu.getItems({ campus_id: campusId, available_only: 'true', q: search })
      .then(result => { if (current) setRemoteSearch({ campus: campusId, query: search, items: result.items || [] }); })
      .catch(() => { if (current) setSearchError(true); })
      .finally(() => { if (current) setSearching(false); });
    return () => { current = false; };
  }, [campusId, search, retryNonce]);

  const query = searchInput.trim().toLocaleLowerCase();
  const currentCatalogue = catalogueCampus === campusId ? catalogue : [];
  const sourceItems = remoteSearch?.campus === campusId && remoteSearch.query.toLocaleLowerCase() === query
    ? remoteSearch.items : currentCatalogue;
  const items = sourceItems.filter(item =>
    (!activeCategory || item.menu_categories?.slug === activeCategory || categories.find(category => category.slug === activeCategory)?.id === item.category_id)
    && (!query || (item.name || '').toLocaleLowerCase().includes(query)))
    .slice().sort((a, b) => (Number(a.price) || 0) - (Number(b.price) || 0) || (a.name || '').localeCompare(b.name || ''));
  const catalogueLoading = loading || (!!campusId && catalogueCampus !== campusId && !error);

  // Quick add — if the item needs required modifiers, send to detail page
  const handleAdd = async (item) => {
    try {
      const [detail, addons] = await Promise.all([mockApi.menu.getItem(item.id, { campus_id: campusId }, 15000), mockApi.menu.getAddons(item.id, { campus_id: campusId }, 15000)]);
      const hasRequired =
        (detail.variation_groups || []).some((vg) => vg.is_required) ||
        (addons.addon_groups || []).some((ag) => ag.is_required);
      if (!hasRequired) {
        play('cart_add');
        await addToCart({ menu_item_id: item.id, quantity: 1 });
        toast({ title: msg('FE_MENU_ADDED_TO_YOUR_CART', 'Added to your cart'), description: msg('FE_MENU_NAME_IS_READY_TO_CHECKOUT', '{name} is ready to checkout.', { name: item.name }) });
      } else {
        navigate(`/menu/${item.id}`);
      }
    } catch (e) {
      toast({ title: msg('FE_MENU_COULD_NOT_ADD_ITEM', 'Could not add item'), description: e.message || 'Please try again.', variant: 'destructive' });
    }
  };

  return (
    <div className="space-y-3 animate-fade-in">
      <SEO {...ROUTE_META['/menu']} />

      {/* Header */}
      <div>
        <span className="hg-eyebrow">Today's menu</span>
        <h1 className="font-heading font-bold text-xl text-foreground mt-0.5 flex items-center gap-1.5">Fresh Off the Grill 🔥</h1>
        <p className="text-sm text-muted-foreground mt-1">Order for your table.</p>
      </div>

      <HeroCarousel placement="menu" />
      <StorefrontSlider sectionType="promo" variant="banner" placement="menu" />

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

      {(refreshError || searchError) && <p role="status" className="text-xs text-muted-foreground">Some menu updates are unavailable. Showing matching loaded items. <button className="font-bold text-primary" onClick={() => setRetryNonce(n => n + 1)}>Retry updates</button></p>}

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
          className={`flex-shrink-0 px-4 py-2 rounded-full text-xs font-semibold transition-all ${!activeCategory ? 'bg-primary text-primary-foreground' : 'bg-card text-muted-foreground border border-border hover:border-primary/30'}`}
        >
          All Items
        </button>
        {categories.map((cat) => (
          <button
            key={cat.id}
            onClick={() => setActiveCategory(cat.slug)}
            className={`flex-shrink-0 px-4 py-2 rounded-full text-xs font-semibold transition-all ${activeCategory === cat.slug ? 'bg-primary text-primary-foreground' : 'bg-card text-muted-foreground border border-border hover:border-primary/30'}`}
          >
            {cat.name}
          </button>
        ))}
      </div>

      {/* Item count + clear filter */}
      {!catalogueLoading && !error && items.length > 0 && (
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
      {catalogueLoading ? (
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
            {searchError ? 'Search could not be completed. Please retry.' : searching || searchInput.trim() !== search ? 'Searching the grill…' : search ? `No items match "${search}"` : 'No items available right now'}
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
          {items.map((item, index) => (
            <MenuGridCard key={item.id} item={item} onAdd={handleAdd} priority={index < 2} />
          ))}
        </motion.div>
      )}
    </div>
  );
}
