import { useState, useEffect } from 'react';
import { Star, Search, RefreshCw, TrendingUp, ChevronDown, ChevronUp } from 'lucide-react';
import { liveApi } from '@/lib/liveApi';
import { formatDateTime } from '@/lib/hgUtils';
import LoadingSpinner from '@/components/LoadingSpinner';
import { toast } from '@/components/ui/use-toast';

const RATING_TONE = {
  5: 'bg-green-100 text-green-700',
  4: 'bg-lime-100 text-lime-700',
  3: 'bg-amber-100 text-amber-700',
  2: 'bg-orange-100 text-orange-700',
  1: 'bg-red-100 text-red-700',
};

function Stars({ value }) {
  return (
    <div className="flex items-center gap-0.5">
      {[1, 2, 3, 4, 5].map((n) => (
        <Star key={n} className={`w-3.5 h-3.5 ${n <= (value || 0) ? 'fill-accent text-accent' : 'text-muted-foreground'}`} />
      ))}
    </div>
  );
}

/**
 * AdminReviews — lists all order reviews with overall + sub-ratings (kitchen,
 * rider), filterable by star rating. Admins can promote a review to a homepage
 * testimonial via the storefront sections API.
 *
 * Backend: GET /admin/reviews, POST /admin/reviews/:id/promote
 */
export default function AdminReviews() {
  const [reviews, setReviews] = useState([]);
  const [loading, setLoading] = useState(true);
  const [ratingFilter, setRatingFilter] = useState('all');
  const [flaggedFilter, setFlaggedFilter] = useState('all');
  const [q, setQ] = useState('');
  const [expanded, setExpanded] = useState(null);

  const load = async () => {
    setLoading(true);
    try {
      const params: Record<string, unknown> = {};
      if (ratingFilter !== 'all') params.rating = Number(ratingFilter);
      if (flaggedFilter !== 'all') params.is_flagged = flaggedFilter === 'flagged';
      setReviews(await liveApi.admin.getReviews(params));
    } catch (e) {
      toast({ title: 'Failed to load reviews', description: e.message, variant: 'destructive' });
      setReviews([]);
    }
    setLoading(false);
  };
  useEffect(() => { load(); }, [ratingFilter, flaggedFilter]);

  const filtered = reviews.filter((r) => {
    const text = (r.review_text || r.comment || '').toLowerCase();
    const userName = (r.profiles?.full_name || r.user?.name || r.user_name || '').toLowerCase();
    const okQ = !q || text.includes(q.toLowerCase()) || userName.includes(q.toLowerCase());
    return okQ;
  });

  // F5 GAP (reported): this panel used to POST /admin/reviews/<id>/promote to push a
  // review onto the homepage. No such route exists in any method (admin.py serves
  // GET /admin/reviews only) and the button 404'd. Homepage testimonials are
  // storefront sections, so promotion needs a backend route before it can come back.

  if (loading) return <LoadingSpinner label="Loading reviews..." />;

  const avgRating = reviews.length ? (reviews.reduce((s, r) => s + (r.rating || 0), 0) / reviews.length).toFixed(1) : '—';

  return (
    <div className="space-y-4">
      {/* Summary + filters */}
      <div className="flex items-center gap-3 flex-wrap">
        <div className="flex items-center gap-2 px-3 py-2 rounded-xl bg-white border border-border">
          <TrendingUp className="w-4 h-4 text-primary" />
          <span className="text-sm font-bold text-foreground">{reviews.length} reviews</span>
          <span className="text-xs text-muted-foreground">· avg {avgRating}★</span>
        </div>
        <div className="relative flex-1 min-w-[180px]">
          <Search className="absolute left-3 top-1/2 w-4 h-4 -translate-y-1/2 text-muted-foreground" />
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search reviews..." className="w-full pl-9 pr-3 py-2 rounded-xl border border-border text-sm" />
        </div>
        <select value={ratingFilter} onChange={(e) => setRatingFilter(e.target.value)} className="p-2 rounded-xl border border-border text-sm">
          <option value="all">All ratings</option>
          <option value="5">5 ★</option>
          <option value="4">4 ★</option>
          <option value="3">3 ★</option>
          <option value="2">2 ★</option>
          <option value="1">1 ★</option>
        </select>
        <select value={flaggedFilter} onChange={(e) => setFlaggedFilter(e.target.value)} className="p-2 rounded-xl border border-border text-sm">
          <option value="all">All reviews</option>
          <option value="flagged">🚩 Flagged only</option>
          <option value="unflagged">Unflagged</option>
        </select>
        <button onClick={load} className="p-2 rounded-xl border border-border"><RefreshCw className="w-4 h-4 text-muted-foreground" /></button>
      </div>

      {filtered.length === 0 ? (
        <div className="text-center py-10 text-muted-foreground">
          <Star className="w-10 h-10 mx-auto mb-2 text-muted-foreground" />
          No reviews found.
        </div>
      ) : (
        <div className="space-y-2">
          {filtered.map((r) => {
            const isOpen = expanded === r.id;
            const userName = r.profiles?.full_name || r.user?.name || r.user_name || 'Student';
            const isPromoted = r.is_promoted || r.promoted;
            return (
              <div key={r.id} className="rounded-2xl bg-white border border-border p-4">
                <button onClick={() => setExpanded(isOpen ? null : r.id)} className="w-full flex items-start justify-between gap-3 text-left">
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="font-bold text-sm text-foreground">{userName}</span>
                      <Stars value={r.rating} />
                      <span className={`text-[10px] font-bold px-2 py-0.5 rounded-full ${RATING_TONE[r.rating] || 'bg-secondary text-muted-foreground'}`}>{r.rating}★</span>
                      {isPromoted && <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-accent/30 text-accent-foreground/80">★ On Homepage</span>}
                      {r.is_flagged && <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-red-100 text-red-700">🚩 Flagged</span>}
                    </div>
                    <p className="text-xs text-muted-foreground mt-0.5">{formatDateTime(r.created_at || r.created_date)}</p>
                    {r.order_id && <p className="text-[11px] text-muted-foreground">Order #{r.order_id?.slice?.(-6) || r.order_id}</p>}
                  </div>
                  {isOpen ? <ChevronUp className="w-4 h-4 text-muted-foreground shrink-0" /> : <ChevronDown className="w-4 h-4 text-muted-foreground shrink-0" />}
                </button>

                {isOpen && (
                  <div className="mt-3 space-y-3 border-t border-border pt-3">
                    {r.review_text || r.comment ? (
                      <p className="text-sm text-foreground">{r.review_text || r.comment}</p>
                    ) : (
                      <p className="text-xs text-muted-foreground italic">No written review.</p>
                    )}

                    {/* Sub-ratings */}
                    {(r.kitchen_rating || r.rider_rating || r.food_rating || r.delivery_rating) && (
                      <div className="grid grid-cols-2 gap-3">
                        {r.kitchen_rating && (
                          <div className="flex items-center gap-2">
                            <span className="text-xs text-muted-foreground">Kitchen</span>
                            <Stars value={r.kitchen_rating} />
                          </div>
                        )}
                        {r.rider_rating && (
                          <div className="flex items-center gap-2">
                            <span className="text-xs text-muted-foreground">Rider</span>
                            <Stars value={r.rider_rating} />
                          </div>
                        )}
                        {r.food_rating && (
                          <div className="flex items-center gap-2">
                            <span className="text-xs text-muted-foreground">Food</span>
                            <Stars value={r.food_rating} />
                          </div>
                        )}
                        {r.delivery_rating && (
                          <div className="flex items-center gap-2">
                            <span className="text-xs text-muted-foreground">Delivery</span>
                            <Stars value={r.delivery_rating} />
                          </div>
                        )}
                      </div>
                    )}

                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}