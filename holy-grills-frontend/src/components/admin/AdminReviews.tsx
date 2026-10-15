import { useState, useEffect, useRef } from 'react';
import { Star, Search, RefreshCw, TrendingUp, ChevronDown, ChevronUp } from 'lucide-react';
import { liveApi } from '@/lib/liveApi';
import { formatDateTime } from '@/lib/hgUtils';
import StaffPanelSkeleton from '@/components/skeletons/StaffPanelSkeleton';
import { toast } from '@/components/ui/use-toast';
import { msg } from '@/lib/messages';

const RATING_TONE = {
  5: 'tone-success',
  4: 'bg-lime-100 text-lime-700',
  3: 'tone-warn',
  2: 'tone-warn',
  1: 'tone-error',
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
  const [offset, setOffset] = useState(0);
  const [total, setTotal] = useState(0);
  const [loadError, setLoadError] = useState(false);
  const latest = useRef(0);
  const limit = 25;

  const load = async () => {
    const intent = ++latest.current;
    setLoading(true);
    setLoadError(false);
    try {
      const params: Record<string, unknown> = { limit, offset };
      if (ratingFilter !== 'all') params.rating = Number(ratingFilter);
      if (flaggedFilter !== 'all') params.is_flagged = flaggedFilter === 'flagged';
      const result = await liveApi.admin.getReviewsPage(params);
      if (intent !== latest.current) return;
      if (offset && offset >= (result.total || 0)) {
        setOffset(result.total ? Math.floor((result.total - 1) / limit) * limit : 0);
        return;
      }
      setReviews(result.reviews || []);
      setTotal(result.total || 0);
    } catch (e) {
      if (intent !== latest.current) return;
      toast({ title: msg('FE_ADMIN_REVIEWS_FAILED_TO_LOAD_REVIEWS', 'Failed to load reviews'), description: e.message, variant: 'destructive' });
      setLoadError(true);
    }
    setLoading(false);
  };
  useEffect(() => { load(); return () => { latest.current++; }; }, [ratingFilter, flaggedFilter, offset]);

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

  if (loading) return <StaffPanelSkeleton />;
  if (loadError) return <div className="py-10 text-center space-y-3"><p>{msg('FE_PLATFORM_LOAD_FAILED', "We couldn't load this page. Please try again.")}</p><button onClick={load} className="text-primary font-bold">{msg('FE_PLATFORM_RETRY', 'Retry')}</button></div>;

  const avgRating = reviews.length ? (reviews.reduce((s, r) => s + (r.rating || 0), 0) / reviews.length).toFixed(1) : '—';

  return (
    <div className="space-y-4">
      {/* Summary + filters */}
      <div className="flex items-center gap-3 flex-wrap">
        <div className="flex items-center gap-2 px-3 py-2 rounded-xl bg-card border border-border">
          <TrendingUp className="w-4 h-4 text-primary" />
          <span className="text-sm font-bold text-foreground">{reviews.length} reviews</span>
          <span className="text-xs text-muted-foreground">· avg {avgRating}★</span>
        </div>
        <div className="relative flex-1 min-w-[180px]">
          <Search className="absolute left-3 top-1/2 w-4 h-4 -translate-y-1/2 text-muted-foreground" />
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder={msg('FE_REVIEWS_SEARCH_PAGE', 'Search this page…')} className="w-full pl-9 pr-3 py-2 rounded-xl border border-border text-sm" />
        </div>
        <select value={ratingFilter} onChange={(e) => { setOffset(0); setRatingFilter(e.target.value); }} className="p-2 rounded-xl border border-border text-sm">
          <option value="all">All ratings</option>
          <option value="5">5 ★</option>
          <option value="4">4 ★</option>
          <option value="3">3 ★</option>
          <option value="2">2 ★</option>
          <option value="1">1 ★</option>
        </select>
        <select value={flaggedFilter} onChange={(e) => { setOffset(0); setFlaggedFilter(e.target.value); }} className="p-2 rounded-xl border border-border text-sm">
          <option value="all">All reviews</option>
          <option value="flagged">🚩 Flagged only</option>
          <option value="unflagged">Unflagged</option>
        </select>
        <button onClick={load} className="p-2 rounded-xl border border-border"><RefreshCw className="w-4 h-4 text-muted-foreground" /></button>
      </div>

      <div className="flex items-center justify-between gap-3 text-sm">
        <span>{msg('FE_REVIEWS_PAGE', 'Showing {start}–{end} of {total} reviews', { start: total ? offset + 1 : 0, end: Math.min(offset + reviews.length, total), total })}</span>
        <div className="flex gap-3"><button disabled={!offset} onClick={() => setOffset(Math.max(0, offset - limit))} className="font-bold disabled:opacity-40">{msg('FE_REVIEWS_PREVIOUS', 'Previous')}</button><button disabled={offset + limit >= total} onClick={() => setOffset(offset + limit)} className="font-bold disabled:opacity-40">{msg('FE_REVIEWS_NEXT', 'Next')}</button></div>
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
              <div key={r.id} className="rounded-2xl bg-card border border-border p-4">
                <button onClick={() => setExpanded(isOpen ? null : r.id)} className="w-full flex items-start justify-between gap-3 text-left">
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="font-bold text-sm text-foreground">{userName}</span>
                      <Stars value={r.rating} />
                      <span className={`text-[10px] font-bold px-2 py-0.5 rounded-full ${RATING_TONE[r.rating] || 'bg-secondary text-muted-foreground'}`}>{r.rating}★</span>
                      {isPromoted && <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-accent/30 text-accent-foreground/80">★ On Homepage</span>}
                      {r.is_flagged && <span className="text-[10px] font-bold px-2 py-0.5 rounded-full tone-error">🚩 Flagged</span>}
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
