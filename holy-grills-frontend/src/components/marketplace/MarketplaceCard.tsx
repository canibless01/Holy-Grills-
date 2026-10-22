import { Flame, Package } from 'lucide-react';
import { formatNaira } from '@/lib/hgUtils';
import { lowCodeInventoryThreshold } from '@/lib/appConfig';

export default function MarketplaceCard({ listing, onClick }) {
  const stock = listing.codes_remaining ?? listing.inventory_count;
  const outOfStock = listing.is_out_of_stock || stock === 0;
  const lowStock = !outOfStock && stock != null && stock <= lowCodeInventoryThreshold();
  const hpPrice = listing.hp_price;
  const cashPrice = listing.cash_price || listing.price;

  return (
    <button
      onClick={onClick}
      className="group text-left bg-card rounded-2xl border border-border overflow-hidden hover:border-primary/20 hover:shadow-card transition-all duration-300 active:scale-[0.98]"
    >
      <div className="relative aspect-[4/3] bg-secondary overflow-hidden">
        {listing.image_url ? (
          <img src={listing.image_url} alt={listing.title} loading="lazy" className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-300" />
        ) : (
          <div className="w-full h-full flex items-center justify-center">
            <Package className="w-8 h-8 text-muted-foreground/30" />
          </div>
        )}
        {hpPrice != null && (
          <span className="absolute top-2 right-2 flex items-center gap-0.5 px-2 py-1 rounded-lg bg-card/95 text-primary text-[10px] font-bold shadow-sm backdrop-blur-sm">
            <Flame className="w-3 h-3" />{hpPrice} HP
          </span>
        )}
        {outOfStock ? (
          <div className="absolute inset-0 bg-black/40 flex items-center justify-center">
            <span className="px-3 py-1 rounded-full bg-card text-destructive text-[10px] font-bold uppercase tracking-wide">Sold Out</span>
          </div>
        ) : lowStock ? (
          <span className="absolute bottom-2 left-2 px-2 py-1 rounded-lg bg-accent text-accent-foreground text-[10px] font-bold animate-pulse">{stock} left</span>
        ) : null}
      </div>
      <div className="p-3">
        <h3 className="font-heading font-bold text-sm text-foreground leading-tight line-clamp-1">{listing.title}</h3>
        <p className="text-[10px] text-muted-foreground mt-0.5 truncate">{listing.vendor_name}</p>
        <div className="flex items-center justify-between mt-2">
          <span className="font-heading font-bold text-base text-foreground tabular-nums">{formatNaira(cashPrice)}</span>
          <span className="text-[9px] text-muted-foreground tabular-nums">{outOfStock ? '—' : `${stock ?? '—'} left`}</span>
        </div>
      </div>
    </button>
  );
}