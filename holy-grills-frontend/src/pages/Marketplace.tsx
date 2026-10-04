import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Search, X, Plus, Ticket } from 'lucide-react';
import { liveApi } from '@/lib/liveApi';
import { useHolyGrill } from '@/lib/HolyGrillContext';
import { toast } from '@/components/ui/use-toast';
import MarketplaceSkeleton from '@/components/skeletons/MarketplaceSkeleton';
import SEO from '@/components/SEO';
import { metaForPath } from '@/seo/routeMeta';
import MarketplaceCard from '@/components/marketplace/MarketplaceCard';
/** Head data for /marketplace — the same object the pre-render writes. */
const META = metaForPath('/marketplace');
import SellItemModal from '@/components/marketplace/SellItemModal';
import MarketplacePurchasesPanel from '@/components/marketplace/MarketplacePurchasesPanel';
import MascotStandee from '@/components/mascot/MascotStandee';

const FILTERS = [
  { id: 'all', label: 'All' },
  { id: 'voucher', label: 'Vouchers' },
  { id: 'event_ticket', label: 'Tickets' },
  { id: 'goodie', label: 'Goodies' },
  { id: 'service', label: 'Services' },
];

const unwrapList = (res) => {
  if (Array.isArray(res)) return res;
  if (res?.data && Array.isArray(res.data)) return res.data;
  if (res?.listings && Array.isArray(res.listings)) return res.listings;
  return [];
};

export default function Marketplace() {
  const navigate = useNavigate();
  const { isAuthenticated } = useHolyGrill();
  const [loading, setLoading] = useState(true);
  const [listings, setListings] = useState([]);
  const [search, setSearch] = useState('');
  const [filter, setFilter] = useState('all');
  const [showSell, setShowSell] = useState(false);
  const [showPurchases, setShowPurchases] = useState(false);
  const [purchases, setPurchases] = useState([]);
  const [loadingPurchases, setLoadingPurchases] = useState(false);

  useEffect(() => {
    const load = async () => {
      try {
        const result = await liveApi.marketplace.list();
        setListings(unwrapList(result));
      } catch (e) { console.error(e); }
      setLoading(false);
    };
    load();
  }, []);

  const loadPurchases = async () => {
    if (!isAuthenticated) { toast({ title: 'Sign in to view purchases', description: 'Your purchase history is tied to your account.' }); return; }
    setShowPurchases(true);
    setLoadingPurchases(true);
    try {
      setPurchases(await liveApi.marketplace.myPurchases());
    } catch (e) {
      setPurchases([]);
      toast({ title: 'Could not load purchases', description: e.message, variant: 'destructive' });
    }
    setLoadingPurchases(false);
  };

  const filtered = listings.filter((l) => {
    if (filter !== 'all' && l.listing_type !== filter) return false;
    if (search && !l.title.toLowerCase().includes(search.toLowerCase())) return false;
    return true;
  });

  if (loading) return <MarketplaceSkeleton />;

  return (
    <div className="space-y-5 animate-fade-in max-w-2xl mx-auto">
      <SEO title={META.title} description={META.description} path={META.path} />

      <div className="flex items-center justify-between">
        <div>
          <span className="hg-eyebrow">Campus finds</span>
          <h1 className="font-heading font-extrabold text-2xl text-foreground mt-0.5">Marketplace 🛍️</h1>
          <p className="text-sm text-muted-foreground mt-0.5">Buy with HP and cash.</p>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={loadPurchases} className="flex items-center gap-1 px-3 py-2 rounded-full bg-card border border-border text-foreground text-xs font-bold transition-all active:scale-95">
            <Ticket className="w-3.5 h-3.5" /> My Purchases
          </button>
          <button onClick={() => setShowSell(true)} className="flex items-center gap-1 px-3 py-2 rounded-full bg-gradient-cta text-white text-xs font-bold transition-all active:scale-95">
            <Plus className="w-3.5 h-3.5" /> Sell
          </button>
        </div>
      </div>

      {showPurchases && (
        <MarketplacePurchasesPanel purchases={purchases} loading={loadingPurchases} onRefresh={loadPurchases} />
      )}

      <div className="relative">
        <Search className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
        <input
          type="text"
          placeholder="Search marketplace…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="w-full pl-11 pr-10 py-3.5 rounded-2xl bg-card border border-border text-sm focus:outline-none focus:border-primary/40 focus:ring-2 focus:ring-primary/20 transition-all"
        />
        {search && <button onClick={() => setSearch('')} className="absolute right-3.5 top-1/2 -translate-y-1/2"><X className="w-4 h-4 text-muted-foreground" /></button>}
      </div>

      <div className="flex gap-2 overflow-x-auto scrollbar-hide -mx-1 px-1">
        {FILTERS.map((f) => (
          <button
            key={f.id}
            onClick={() => setFilter(f.id)}
            className={`px-4 py-2 rounded-full text-xs font-bold whitespace-nowrap transition-all ${filter === f.id ? 'bg-gradient-cta text-white shadow-glow' : 'bg-card text-foreground border border-border hover:border-primary/20'}`}
          >
            {f.label}
          </button>
        ))}
      </div>

      {filtered.length === 0 ? (
        <div className="text-center py-12">
          <MascotStandee mascot="thinking" className="w-28 h-28 mx-auto mb-3" alt="No marketplace listings" />
          <p className="text-sm font-semibold text-foreground">{search ? 'Nothing yet.' : 'Opening soon.'}</p>
        </div>
      ) : (
        <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
          {filtered.map((listing) => (
            <MarketplaceCard key={listing.id} listing={listing} onClick={() => navigate(`/marketplace/${listing.id}`)} />
          ))}
        </div>
      )}

      <SellItemModal open={showSell} onClose={() => setShowSell(false)} />
    </div>
  );
}