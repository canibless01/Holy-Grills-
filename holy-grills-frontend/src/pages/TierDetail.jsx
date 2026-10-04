import React, { useState, useEffect } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import { motion } from 'framer-motion';
import { ChevronLeft, Calendar, MapPin, Ticket, Users, Package, Flame, ArrowRight } from 'lucide-react';
import { liveApi } from '@/lib/liveApi';
import { formatNaira, formatDateTime } from '@/lib/hgUtils';
import DetailSkeleton from '@/components/skeletons/DetailSkeleton';

// GET /events/tiers/<tier_id>/detail — full tier + nested event. A clean,
// interactive tier card: hero price, availability progress, and a clear
// register CTA. Price boxes adapt to the data (cash-only, HP-only, or both)
// so there's never an L-shaped gap.
export default function TierDetail() {
  const { tierId } = useParams();
  const navigate = useNavigate();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    (async () => {
      try {
        setData(await liveApi.events.getTierDetail(tierId));
      } catch (e) {
        setError(e.message || 'Tier not found');
      }
      setLoading(false);
    })();
  }, [tierId]);

  if (loading) return <DetailSkeleton />;

  const tier = data?.tier || data;
  const event = data?.event || tier?.event || null;

  if (error || !tier) {
    return (
      <div className="text-center py-16 space-y-4 animate-fade-in max-w-md mx-auto">
        <Package className="w-10 h-10 text-muted-foreground/40 mx-auto mb-3" />
        <p className="text-sm font-semibold text-foreground">{error || 'Tier not found'}</p>
        <button onClick={() => navigate(event ? `/events/${event.id}` : '/events')} className="px-4 py-2 rounded-xl bg-primary text-white text-xs font-bold">Back</button>
      </div>
    );
  }

  const sold = tier.sold_count ?? tier.quantity_sold ?? 0;
  const cap = tier.capacity ?? tier.quantity_available ?? null;
  const avail = cap != null ? Math.max(0, cap - sold) : null;
  const cashPrice = tier.price_naira ?? tier.price_wallet ?? tier.price ?? 0;
  const hpPrice = tier.price_hp ?? 0;
  const hasCash = cashPrice > 0;
  const hasHp = hpPrice > 0;
  const soldPct = cap != null && cap > 0 ? Math.min(100, Math.round((sold / cap) * 100)) : null;
  const soldOut = avail != null && avail === 0;

  return (
    <div className="space-y-5 animate-fade-in max-w-md mx-auto pb-4">
      <button onClick={() => navigate(event ? `/events/${event.id}` : '/events')} className="flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground transition-colors">
        <ChevronLeft className="w-4 h-4" /> Back to event
      </button>

      {/* Hero image */}
      <div className="relative rounded-3xl overflow-hidden aspect-[16/10] bg-secondary shadow-card">
        {tier.image_url ? (
          <img src={tier.image_url} alt={tier.name} className="w-full h-full object-cover" />
        ) : (
          <div className="w-full h-full flex items-center justify-center bg-gradient-soft">
            <Ticket className="w-12 h-12 text-primary/30" />
          </div>
        )}
        <div className="absolute inset-0 bg-gradient-to-t from-foreground/70 via-transparent to-transparent" />
        <div className="absolute bottom-3 left-4 right-4">
          <h1 className="font-heading font-extrabold text-xl text-white leading-tight drop-shadow">{tier.name}</h1>
        </div>
        {soldOut && (
          <span className="absolute top-3 right-3 px-3 py-1 rounded-full bg-destructive text-white text-[10px] font-bold shadow">SOLD OUT</span>
        )}
      </div>

      {tier.description && (
        <p className="text-sm text-muted-foreground leading-relaxed -mt-1">{tier.description}</p>
      )}

      {/* Price card — adapts to what's available. Single price = full-width
          hero; both prices = two equal halves. No L-shaped gaps. */}
      <motion.div
        whileTap={{ scale: 0.99 }}
        className={`rounded-2xl border p-5 shadow-card ${hasHp ? 'bg-accent/10 border-primary/20' : 'bg-card border-border'}`}
      >
        <div className={hasHp && hasCash ? 'grid grid-cols-2 gap-4' : 'text-center'}>
          {hasCash && (
            <div className={hasHp ? 'border-r border-border/60 pr-4' : ''}>
              <div className="text-[10px] text-muted-foreground uppercase tracking-wide font-bold mb-1">Cash</div>
              <div className="font-heading font-extrabold text-2xl text-foreground tabular-nums">{formatNaira(cashPrice)}</div>
            </div>
          )}
          {hasHp && (
            <div className={hasCash ? 'pl-4' : ''}>
              <div className="text-[10px] text-muted-foreground uppercase tracking-wide font-bold mb-1 flex items-center gap-1 justify-center"><Flame className="w-3 h-3 text-primary" /> Holy Points</div>
              <div className="font-heading font-extrabold text-2xl text-primary tabular-nums">{hpPrice} HP</div>
            </div>
          )}
          {!hasCash && !hasHp && (
            <div className="font-heading font-extrabold text-2xl text-success">Free</div>
          )}
        </div>
      </motion.div>

      {/* Availability — progress bar makes it feel interactive + informative */}
      {cap != null && (
        <div className="rounded-2xl bg-card border border-border p-4 shadow-card space-y-2">
          <div className="flex items-center justify-between text-xs">
            <span className="font-semibold text-foreground flex items-center gap-1.5"><Users className="w-3.5 h-3.5 text-muted-foreground" /> {sold} sold</span>
            <span className={`font-bold ${soldOut ? 'text-destructive' : 'text-success'}`}>{avail != null ? `${avail} left` : ''}</span>
          </div>
          <div className="h-2 rounded-full bg-secondary overflow-hidden">
            <motion.div
              initial={{ width: 0 }}
              animate={{ width: `${soldPct}%` }}
              transition={{ duration: 0.6, ease: 'easeOut' }}
              className={`h-full rounded-full ${soldOut ? 'bg-destructive' : soldPct > 80 ? 'bg-gradient-cta' : 'bg-success'}`}
            />
          </div>
        </div>
      )}

      {/* Associated event */}
      {event && (
        <Link to={`/events/${event.id}`} className="block rounded-2xl bg-card border border-border p-4 shadow-card hover:border-primary/40 hover:shadow-glow transition-all group">
          <div className="text-[10px] text-muted-foreground uppercase tracking-wide mb-1">Part of</div>
          <div className="font-bold text-sm text-foreground">{event.title}</div>
          <div className="flex items-center gap-1.5 mt-1 text-xs text-muted-foreground"><Calendar className="w-3 h-3" /> {formatDateTime(event.starts_at)}</div>
          {event.location && <div className="flex items-center gap-1.5 text-xs text-muted-foreground"><MapPin className="w-3 h-3" /> {event.location}</div>}
        </Link>
      )}

      {/* Register CTA */}
      {event && (
        <button
          onClick={() => navigate(`/events/${event.id}`)}
          disabled={soldOut}
          className="w-full py-4 rounded-2xl bg-gradient-cta text-white font-bold text-sm shadow-glow transition-all active:scale-[0.98] disabled:opacity-50 flex items-center justify-center gap-2"
        >
          {soldOut ? 'Sold out — join the waitlist' : <>Register for this event <ArrowRight className="w-4 h-4" /></>}
        </button>
      )}
    </div>
  );
}