import { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { ChevronLeft, Flame, Wallet, Store, Package } from 'lucide-react';
import { apiClient } from '@/lib/apiClient';
import { useHolyGrill } from '@/lib/HolyGrillContext';
import { formatNaira } from '@/lib/hgUtils';
import DetailSkeleton from '@/components/skeletons/DetailSkeleton';
import PurchaseModal from '@/components/marketplace/PurchaseModal';

export default function MarketplaceDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { refreshHp, refreshWallet } = useHolyGrill();
  const [listing, setListing] = useState(null);
  const [loading, setLoading] = useState(true);
  const [showPurchase, setShowPurchase] = useState(false);

  useEffect(() => {
    const load = async () => {
      try {
        const result = await apiClient.get(`/marketplace/${id}`);
        setListing(result?.data || result);
      } catch (e) { console.error(e); }
      setLoading(false);
    };
    load();
  }, [id]);

  if (loading) return <DetailSkeleton />;
  if (!listing) return (
    <div className="text-center py-16">
      <Package className="w-10 h-10 text-muted-foreground/40 mx-auto mb-3" />
      <p className="text-sm font-semibold text-foreground">Listing not found</p>
      <button onClick={() => navigate('/marketplace')} className="mt-3 text-sm text-primary font-bold">Back to marketplace</button>
    </div>
  );

  const cashPrice = listing.cash_price || listing.price;
  const hpPrice = listing.hp_price;
  const stock = listing.codes_remaining ?? listing.inventory_count;
  const outOfStock = listing.is_out_of_stock || stock === 0;
  const lowStock = !outOfStock && stock != null && stock <= 5;

  return (
    <div className="space-y-5 animate-fade-in max-w-2xl mx-auto pb-4">
      <button onClick={() => navigate('/marketplace')} className="flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground transition-colors">
        <ChevronLeft className="w-4 h-4" /> Back to marketplace
      </button>

      <div className="relative rounded-3xl overflow-hidden aspect-square bg-secondary shadow-card">
        {listing.image_url ? (
          <img src={listing.image_url} alt={listing.title} className="w-full h-full object-cover" />
        ) : (
          <div className="w-full h-full flex items-center justify-center">
            <Package className="w-12 h-12 text-muted-foreground/30" />
          </div>
        )}
        {outOfStock && (
          <div className="absolute inset-0 bg-black/40 flex items-center justify-center">
            <span className="px-4 py-2 rounded-full bg-card text-destructive text-sm font-bold uppercase tracking-wide">Sold Out</span>
          </div>
        )}
      </div>

      <div>
        <div className="flex items-center gap-1.5 text-xs text-muted-foreground mb-1.5">
          <Store className="w-3.5 h-3.5" /> {listing.vendor_name}
        </div>
        <h1 className="font-heading font-extrabold text-xl text-foreground leading-tight">{listing.title}</h1>
        {listing.description && <p className="text-sm text-muted-foreground mt-2 leading-relaxed">{listing.description}</p>}
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div className="rounded-2xl bg-card border border-border p-4 text-center shadow-card">
          <Wallet className="w-5 h-5 text-success mx-auto mb-1.5" />
          <div className="font-heading font-bold text-lg text-foreground tabular-nums">{formatNaira(cashPrice)}</div>
          <div className="text-[10px] text-muted-foreground uppercase tracking-wide">Cash</div>
        </div>
        {hpPrice != null && (
          <div className="rounded-2xl bg-gradient-gold border border-accent/20 p-4 text-center shadow-card">
            <Flame className="w-5 h-5 text-primary mx-auto mb-1.5" />
            <div className="font-heading font-bold text-lg text-primary tabular-nums">{hpPrice} HP</div>
            <div className="text-[10px] text-muted-foreground uppercase tracking-wide">Holy Points</div>
          </div>
        )}
      </div>

      <div className="flex items-center gap-2 text-xs">
        {outOfStock ? (
          <span className="flex items-center gap-1.5 text-destructive font-semibold">
            <span className="w-2 h-2 rounded-full bg-destructive" /> Out of stock
          </span>
        ) : (
          <span className="flex items-center gap-1.5 text-muted-foreground">
            <span className={`w-2 h-2 rounded-full ${lowStock ? 'bg-amber-500' : 'bg-success'}`} />
            {lowStock ? `Only ${stock} left` : `${stock ?? '—'} available`}
          </span>
        )}
      </div>

      <button
        onClick={() => setShowPurchase(true)}
        disabled={outOfStock}
        className="w-full py-4 rounded-2xl bg-gradient-cta text-white font-bold text-sm shadow-glow transition-all active:scale-[0.98] disabled:opacity-50 disabled:active:scale-100"
      >
        {outOfStock ? 'Out of Stock' : 'Purchase Now'}
      </button>

      {showPurchase && (
        <PurchaseModal
          listing={listing}
          onClose={() => setShowPurchase(false)}
          onSuccess={async () => {
            await refreshHp();
            await refreshWallet();
            setShowPurchase(false);
            navigate('/marketplace');
          }}
        />
      )}
    </div>
  );
}