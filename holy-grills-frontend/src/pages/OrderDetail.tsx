import React, { useState, useEffect } from 'react';
import { useParams, useNavigate, useLocation } from 'react-router-dom';
import { motion } from 'framer-motion';
import { ChevronLeft, MapPin, Clock, CreditCard, Flame, Star, RefreshCw, Share2, X, Check, Package, Bike, Phone, User, Gift, Mail } from 'lucide-react';
import { mockApi } from '@/lib/mockApi';
import { liveApi } from '@/lib/liveApi';
import { useHolyGrill } from '@/lib/HolyGrillContext';
import { useSound } from '@/lib/SoundProvider';
import { formatNaira, formatDateTime, ORDER_STATUS_LABELS, ORDER_STATUS_COLORS, ORDER_STATUS_FLOW, getOrderCustomer } from '@/lib/hgUtils';
import { reviewHp } from '@/lib/appConfig';
import ShareSheet from '@/components/ShareSheet';
import SquadMembersPanel from '@/components/SquadMembersPanel';
import MascotStandee from '@/components/mascot/MascotStandee';
import ImageUploader from '@/components/admin/ImageUploader';
import ModalPortal from '@/components/ModalPortal';
import { toast } from '@/components/ui/use-toast';
import APP_CONFIG from '@/config/app.config';

// Google review handoff — deep-links into the Business Profile review form when
// a Place ID is configured, otherwise falls back to a Google search for the brand.
const googleReviewUrl = () => {
  const placeId = APP_CONFIG.google?.placeId;
  return placeId
    ? `https://search.google.com/local/writereview?placeid=${encodeURIComponent(placeId)}`
    : `https://www.google.com/search?q=${encodeURIComponent(`${APP_CONFIG.name} reviews`)}`;
};

export default function OrderDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const location = useLocation();
  const { refreshUser, user } = useHolyGrill();
  const { play } = useSound();
  const claimToken = new URLSearchParams(location.search).get('claim_token');
  const [order, setOrder] = useState(null);
  const [loading, setLoading] = useState(true);
  const [showReview, setShowReview] = useState(false);
  const [review, setReview] = useState({ rating: 5, kitchen_rating: 4, rider_rating: 5, comment: '' });
  const [reviewSubmitted, setReviewSubmitted] = useState(false);
  const [showShare, setShowShare] = useState(false);
  const [reviewImages, setReviewImages] = useState([]);
  const [googlePrompt, setGooglePrompt] = useState(false);
  const [callLink, setCallLink] = useState(null);
  const [callingRider, setCallingRider] = useState(false);
  const [showResend, setShowResend] = useState(false);
  const [resendEmail, setResendEmail] = useState('');
  const [resending, setResending] = useState(false);
  const [resendMsg, setResendMsg] = useState(null);

  // Guest tracking — load the claim token from localStorage first when the
  // guest returns without ?claim_token= in the URL (new device, cleared
  // storage, lost link). Once the guest signs up, access is by auth token
  // and the claim_token is no longer needed.
  const resolveClaimToken = () => {
    if (claimToken) return claimToken;
    if (user) return null; // authenticated — access is by token, not claim_token
    try {
      const guestOrders = JSON.parse(localStorage.getItem('hg_guest_orders') || '[]');
      const match = guestOrders.find((g) => g.id === id);
      return match?.claim_token || null;
    } catch { return null; }
  };

  useEffect(() => {
    let first = true;
    const load = async () => {
      try {
        const token = resolveClaimToken();
        const o = await mockApi.orders.get(id, token ? { claim_token: token } : {});
        setOrder(o);
        // Pre-fill the resend email with the guest's email on file — only on the
        // first load, so polling never overwrites what the guest has typed.
        if (first) setResendEmail(o?.guest_email || o?.email || o?.customer_email || '');
      } catch (e) { console.error(e); }
      first = false;
      setLoading(false);
    };
    load();
    // Keep the timeline fresh while the order is still moving.
    const timer = setInterval(load, 30000);
    return () => clearInterval(timer);
  }, [id, claimToken]); // eslint-disable-line react-hooks/exhaustive-deps

  // Resend tracking email — explicit only (rate-limited 5 min / 3 max per order
  // server-side). guest_email is checked against the order's email on file, so
  // the value the guest confirms here is used, not a stale cached one.
  const handleResend = async () => {
    if (!resendEmail.trim() || !/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(resendEmail)) { setResendMsg({ ok: false, text: 'Enter a valid email.' }); return; }
    setResending(true);
    setResendMsg(null);
    try {
      const res = await liveApi.orders.resendTracking(id, { guest_email: resendEmail.trim() });
      setResendMsg({ ok: true, text: res?.message || 'Tracking email sent. Check your inbox.' });
    } catch (e) {
      setResendMsg({ ok: false, text: e.message || 'Could not resend. Try again in a few minutes.' });
    }
    setResending(false);
  };

  const handleCancel = async () => {
    const isScheduled = order.status === 'scheduled' || order.is_scheduled || !!order.scheduled_for;
    const msg = isScheduled ? 'Cancel this scheduled order? Your slot will be released.' : 'Cancel this order? You will be refunded.';
    if (!confirm(msg)) return;
    try {
      if (isScheduled) await mockApi.orders.cancelScheduled(id);
      else await mockApi.orders.cancel(id, { reason: 'Changed my mind' });
      await refreshUser();
      const o = await mockApi.orders.get(id, resolveClaimToken() ? { claim_token: resolveClaimToken() } : {});
      setOrder(o);
    } catch (e) { alert(e.message); }
  };

  const handleReorder = async () => {
    try {
      const result = await mockApi.orders.reorder(id);
      const items = result?.items || result?.order_items || result?.cart_items || [];
      for (const item of items) {
        if (item.is_available !== false) {
          await mockApi.cart.add({ menu_item_id: item.menu_item_id, quantity: item.quantity || 1 });
        }
      }
      navigate('/cart');
    } catch (e) { console.error(e); }
  };

  // Guest order linking — manual claim for the one case the automatic email-match
  // trigger can't cover: the guest registered with a different email than checkout.
  const handleClaim = async () => {
    const token = resolveClaimToken();
    if (!token) return;
    try {
      await mockApi.orders.claim(id, { claim_token: token });
      await refreshUser();
      toast({ title: '✅ Order linked to your account', description: 'You can now track it from your orders.' });
      const o = await mockApi.orders.get(id, resolveClaimToken() ? { claim_token: resolveClaimToken() } : {});
      setOrder(o);
    } catch (e) { alert(e.message); }
  };

  const handleReview = async () => {
    try {
      const result = await mockApi.orders.review(id, review);
      if (reviewImages.length) {
        try { await mockApi.orders.addReviewImages(id, { image_urls: reviewImages }); } catch { /* non-fatal */ }
      }
      await refreshUser();
      play('review_submitted');
      // Response shape: { review: { rating, kitchen_rating, rider_rating, ... }, hp_awarded }
      const submittedRating = result?.review?.rating ?? review.rating;
      setGooglePrompt(Number(submittedRating) >= 4);
      setReviewSubmitted(true);
      setShowReview(false);
      setReviewImages([]);
    } catch (e) {
      // Surface the failure — a silent catch made the review button feel dead.
      toast({ title: 'Review failed', description: e.message || 'Please try again in a moment.', variant: 'destructive' });
    }
  };

  // Call rider — fetch a secure tel: link from GET /orders/<id>/call-rider
  // instead of trusting an embedded field on the order object.
  const handleCallRider = async () => {
    if (callLink) { window.location.href = callLink; return; }
    setCallingRider(true);
    try {
      const res = await liveApi.orders.callRider(id);
      const link = res?.rider?.call_link || res?.call_link || res?.call_url || '';
      if (link) { setCallLink(link); window.location.href = link; }
      else toast({ title: 'Call unavailable', description: 'No rider call link right now.', variant: 'destructive' });
    } catch (e) { toast({ title: 'Call failed', description: e.message, variant: 'destructive' }); }
    setCallingRider(false);
  };

  if (loading) {
    return (
      <div className="space-y-4 animate-fade-in pb-4">
        <div className="h-5 w-28 bg-muted rounded animate-pulse" />
        <div className="h-32 bg-muted rounded-2xl animate-pulse" />
        <div className="h-40 bg-muted rounded-2xl animate-pulse" />
        <div className="h-48 bg-muted rounded-2xl animate-pulse" />
      </div>
    );
  }

  if (!order) {
    return (
      <div className="text-center py-16 space-y-4">
        <MascotStandee mascot="worried" className="w-32 h-32 mx-auto" alt="Order not found" />
        <p className="text-sm text-muted-foreground">Order not found</p>
        <button onClick={() => navigate('/orders')} className="px-4 py-2 rounded-xl bg-primary text-white text-xs font-bold">Back to orders</button>
      </div>
    );
  }

  const statusIndex = ORDER_STATUS_FLOW.indexOf(order.status);
  const etaMin = order.delivery_batch ? ({ preparing: 25, ready: 15, assigned: 18, out_for_delivery: 12 }[order.status] || 0) : 0;
  const isScheduled = order.status === 'scheduled' || order.is_scheduled || !!order.scheduled_for;
  const canCancel = order.status === 'received' || isScheduled;
  const canReview = order.status === 'delivered' && !reviewSubmitted;
  const canReorder = ['delivered', 'cancelled'].includes(order.status);

  return (
    <div className="space-y-4 animate-fade-in pb-4 max-w-2xl mx-auto">
      <button onClick={() => navigate('/orders')} className="flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground transition-colors">
        <ChevronLeft className="w-4 h-4" /> Back to orders
      </button>

      {/* Status Card */}
      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        className="rounded-2xl bg-gradient-dark p-5 text-white shadow-card"
      >
        <div className="flex items-center justify-between mb-3">
          <span className={`px-3 py-1 rounded-full text-xs font-bold ${ORDER_STATUS_COLORS[order.status] || 'bg-muted text-foreground'}`}>
            {ORDER_STATUS_LABELS[order.status] || order.status}
          </span>
          <span className="text-xs text-white/70 font-mono">#{(order.order_number || order.id || '').toUpperCase()}</span>
        </div>

        {/* Progress Timeline */}
        {order.status !== 'cancelled' && order.status !== 'refunded' && (
          <div className="flex items-center gap-0.5 mt-4">
            {ORDER_STATUS_FLOW.map((step, i) => (
              <React.Fragment key={step}>
                <div className="flex flex-col items-center">
                  <div className={`w-7 h-7 rounded-full flex items-center justify-center text-[10px] font-bold ${i <= statusIndex ? 'bg-gradient-cta text-white' : 'bg-white/15 text-white/50'}`}>
                    {i < statusIndex ? <Check className="w-3.5 h-3.5 text-white" /> : i + 1}
                  </div>
                  <span className="text-[8px] mt-1 font-semibold whitespace-nowrap text-white/70">{ORDER_STATUS_LABELS[step].split(' ')[0]}</span>
                </div>
                {i < ORDER_STATUS_FLOW.length - 1 && (
                  <div className={`flex-1 h-0.5 rounded-full ${i < statusIndex ? 'bg-primary' : 'bg-white/15'}`} />
                )}
              </React.Fragment>
            ))}
          </div>
        )}
      </motion.div>

      {/* Items */}
      <div className="rounded-2xl bg-card border border-border p-4 shadow-card">
        <h3 className="font-bold text-sm text-foreground mb-3">Items Ordered</h3>
        <div className="space-y-2">
          {(order.order_items || []).map((item, i) => (
            <div key={i} className="flex items-center justify-between text-sm">
              <div className="min-w-0">
                <span className="font-medium text-foreground">{item.quantity}× {item.name_snapshot}</span>
                {order.notes && <p className="text-xs text-muted-foreground mt-0.5">📝 {order.notes}</p>}
              </div>
              <span className="font-semibold text-foreground shrink-0 ml-2">{formatNaira(item.line_total)}</span>
            </div>
          ))}
        </div>
        <div className="border-t border-border mt-3 pt-3 space-y-1">
          {order.discount_amount > 0 && (
            <div className="flex justify-between text-xs text-success">
              <span>Discount</span><span>-{formatNaira(order.discount_amount)}</span>
            </div>
          )}
          <div className="flex justify-between font-bold">
            <span className="text-foreground">Total</span>
            <span className="text-foreground">{formatNaira(order.total_amount)}</span>
          </div>
        </div>
      </div>

      {/* Squad members — order-scoped management (the squad roster is untouched) */}
      {order.is_squad_order && (
        <SquadMembersPanel orderId={order.id} delivered={order.status === 'delivered'} />
      )}

      {/* Order Details */}
      <div className="rounded-2xl bg-card border border-border p-4 space-y-3 shadow-card">
        <div className="flex items-center gap-3 text-sm">
          <Clock className="w-4 h-4 text-muted-foreground shrink-0" />
          <div><div className="text-xs text-muted-foreground">{isScheduled ? 'Scheduled for' : 'Placed'}</div><div className="font-semibold text-foreground">{formatDateTime(isScheduled ? (order.scheduled_for || order.scheduled_date || order.created_at) : order.created_at)}</div></div>
        </div>
        {(() => { const c = getOrderCustomer(order); return (c.name || c.phone) ? (
          <div className="flex items-center gap-3 text-sm">
            <User className="w-4 h-4 text-muted-foreground shrink-0" />
            <div><div className="text-xs text-muted-foreground">Ordered by</div><div className="font-semibold text-foreground">{c.display}{c.phone ? ` · ${c.phone}` : ''}</div></div>
          </div>
        ) : null; })()}
        {order.delivered_at && (
          <div className="flex items-center gap-3 text-sm">
            <Check className="w-4 h-4 text-success shrink-0" />
            <div><div className="text-xs text-muted-foreground">Delivered</div><div className="font-semibold text-foreground">{formatDateTime(order.delivered_at)}</div></div>
          </div>
        )}
        <div className="flex items-center gap-3 text-sm">
          <MapPin className="w-4 h-4 text-muted-foreground shrink-0" />
          <div><div className="text-xs text-muted-foreground">Delivery to</div><div className="font-semibold text-foreground">{order.delivery_address?.line1 || '—'}</div></div>
        </div>
        <div className="flex items-center gap-3 text-sm">
          <Package className="w-4 h-4 text-muted-foreground shrink-0" />
          <div><div className="text-xs text-muted-foreground">Window</div><div className="font-semibold text-foreground">{order.delivery_window?.label || '—'}</div></div>
        </div>
        <div className="flex items-center gap-3 text-sm">
          <CreditCard className="w-4 h-4 text-muted-foreground shrink-0" />
          <div>
            <div className="text-xs text-muted-foreground">Payment ({order.payment_status})</div>
            <div className="font-semibold text-foreground">
              {order.wallet_amount_used > 0 && `Wallet: ${formatNaira(order.wallet_amount_used)}`}
              {order.wallet_amount_used > 0 && order.card_amount_used > 0 && ' + '}
              {order.card_amount_used > 0 && `Card: ${formatNaira(order.card_amount_used)}`}
            </div>
          </div>
        </div>
        {order.hp_earned > 0 && (
          <div className="flex items-center gap-3 text-sm">
            <Flame className="w-4 h-4 text-primary shrink-0" />
            <div><div className="text-xs text-muted-foreground">HP Earned</div><div className="font-semibold text-primary">+{order.hp_earned} HP</div></div>
          </div>
        )}
        {order.hp_redeemed > 0 && (
          <div className="flex items-center gap-3 text-sm">
            <Flame className="w-4 h-4 text-muted-foreground shrink-0" />
            <div><div className="text-xs text-muted-foreground">HP Redeemed</div><div className="font-semibold text-foreground">-{order.hp_redeemed} HP</div></div>
          </div>
        )}
      </div>

      {/* Rider Info */}
      {order.delivery_batch && (
        <div className="rounded-2xl bg-card border border-border p-4 space-y-3 shadow-card">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-full bg-secondary flex items-center justify-center">
              <Bike className="w-5 h-5 text-muted-foreground" />
            </div>
            <div>
              <div className="text-xs text-muted-foreground">Rider</div>
              <div className="font-semibold text-sm text-foreground">{order.assigned_rider?.name || `Rider #${order.delivery_batch.rider_id}`}</div>
            </div>
            <span className="ml-auto text-xs font-bold text-muted-foreground capitalize">{order.delivery_batch.status}</span>
          </div>
          {etaMin > 0 && (
            <div className="flex items-center gap-2 p-3 rounded-xl bg-primary/5 border border-primary/20">
              <Clock className="w-4 h-4 text-primary" />
              <div className="text-sm font-bold text-primary">Arriving in ~{etaMin} min</div>
            </div>
          )}
          <button onClick={handleCallRider} disabled={callingRider} className="flex items-center justify-center gap-2 w-full py-3 rounded-xl bg-success text-white text-sm font-bold hover:opacity-90 transition-opacity disabled:opacity-60">
            <Phone className="w-4 h-4" /> {callingRider ? 'Connecting…' : 'Call Rider'}
          </button>
        </div>
      )}

      {/* Guest claim prompt — an account links the order and unlocks its HP. */}
      {!user && resolveClaimToken() && !order.user_id && (
        <div className="rounded-2xl bg-gradient-cta p-4 text-white shadow-glow flex items-center gap-3">
          <Gift className="w-8 h-8 shrink-0" />
          <div className="flex-1 min-w-0">
            <div className="font-bold text-sm">Create an account to claim this order</div>
            <div className="text-xs text-white/80 mt-0.5">Link it to your profile and earn HP on it.</div>
          </div>
          <button
            onClick={() => navigate('/register')}
            className="shrink-0 px-3.5 py-2 rounded-full bg-white text-primary text-xs font-bold active:scale-95 transition-transform"
          >
            Sign up
          </button>
        </div>
      )}

      {/* Actions */}
      <div className="flex flex-wrap gap-2">
        {/* Guest tracking resend — explicit only, never automatic. */}
        {!user && (
          <button
            onClick={() => setShowResend(true)}
            className="flex-1 py-3 rounded-xl bg-card border border-border text-foreground font-bold text-sm flex items-center justify-center gap-1.5 hover:border-primary/30 transition-colors"
          >
            <Mail className="w-4 h-4" /> Resend tracking email
          </button>
        )}
        {canCancel && (
          <button onClick={handleCancel} className="flex-1 py-3 rounded-xl bg-destructive/10 border border-destructive/20 text-destructive font-bold text-sm hover:bg-destructive/20 transition-colors">
            {isScheduled ? 'Cancel Scheduled Order' : 'Cancel Order'}
          </button>
        )}
        {canReorder && (
          <button onClick={handleReorder} className="flex-1 py-3 rounded-xl bg-card border border-border text-foreground font-bold text-sm flex items-center justify-center gap-1.5 hover:border-primary/30 transition-colors">
            <RefreshCw className="w-4 h-4" /> Reorder
          </button>
        )}
        <button onClick={() => setShowShare(true)} className="flex-1 py-3 rounded-xl bg-card border border-border text-foreground font-bold text-sm flex items-center justify-center gap-1.5 hover:border-primary/30 transition-colors">
          <Share2 className="w-4 h-4" /> Share
        </button>
        {user && !order.user_id && resolveClaimToken() && (
          <button onClick={handleClaim} className="flex-1 py-3 rounded-xl bg-gradient-cta text-white font-bold text-sm shadow-glow">
            Link to my account
          </button>
        )}
        {canReview && (
          <motion.button whileTap={{ scale: 0.97 }} onClick={() => setShowReview(true)} className="flex-1 py-3 rounded-xl bg-gradient-cta text-white font-bold text-sm flex items-center justify-center gap-1.5 shadow-glow">
            <Star className="w-4 h-4" /> Review
          </motion.button>
        )}
      </div>

      {reviewSubmitted && (
        <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} className="rounded-2xl bg-success/10 border border-success/20 p-4 flex items-center gap-2">
          <Check className="w-5 h-5 text-success shrink-0" />
          <div>
            <div className="font-bold text-sm text-success">Review submitted!</div>
            <div className="text-xs text-success">You earned {reviewHp()} HP (pending)</div>
          </div>
        </motion.div>
      )}

      {/* Google handoff — only for happy customers (4★ and up) */}
      {reviewSubmitted && googlePrompt && (
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          className="rounded-2xl bg-gradient-cta p-5 text-white shadow-glow"
        >
          <div className="flex items-center gap-1.5 mb-1">
            <Star className="w-3.5 h-3.5 fill-white text-white" />
            <span className="text-[10px] font-extrabold uppercase tracking-wider">Loved it?</span>
          </div>
          <h3 className="font-heading font-extrabold text-lg">Tell Google too!</h3>
          <p className="text-xs text-white/85 mt-1 mb-4">
            A quick Google review helps more students find the grill.
          </p>
          <a
            href={googleReviewUrl()}
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center justify-center gap-2 w-full py-3 rounded-full bg-white text-foreground font-bold text-sm active:scale-95 transition"
          >
            <Star className="w-4 h-4 fill-accent text-accent" /> Leave a Google review
          </a>
        </motion.div>
      )}

      {/* Review Modal */}
      {showReview && (
        <ModalPortal>
        <div className="fixed inset-0 z-50 bg-black/60 backdrop-blur-md flex items-end sm:items-center justify-center p-4" onClick={() => setShowReview(false)}>
          <div className="bg-card rounded-3xl p-6 w-full max-w-md animate-slide-up" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between mb-4">
              <h3 className="font-heading font-bold text-lg text-foreground">Rate Your Order</h3>
              <button onClick={() => setShowReview(false)}><X className="w-5 h-5 text-muted-foreground" /></button>
            </div>
            <div className="space-y-4">
              <div>
                <label className="text-xs font-bold text-muted-foreground uppercase tracking-wide">Overall Rating</label>
                <div className="flex gap-1 mt-2">
                  {[1, 2, 3, 4, 5].map((s) => (
                    <button key={s} onClick={() => setReview({ ...review, rating: s })}>
                      <Star className={`w-8 h-8 transition-transform ${s <= review.rating ? 'fill-accent text-accent scale-110' : 'text-muted-foreground'}`} />
                    </button>
                  ))}
                </div>
              </div>
              <div>
                <label className="text-xs font-bold text-muted-foreground uppercase tracking-wide">Kitchen Rating</label>
                <div className="flex gap-1 mt-2">
                  {[1, 2, 3, 4, 5].map((s) => (
                    <button key={s} onClick={() => setReview({ ...review, kitchen_rating: s })}>
                      <Star className={`w-6 h-6 ${s <= review.kitchen_rating ? 'fill-accent text-accent' : 'text-muted-foreground'}`} />
                    </button>
                  ))}
                </div>
              </div>
              <div>
                <label className="text-xs font-bold text-muted-foreground uppercase tracking-wide">Rider Rating</label>
                <div className="flex gap-1 mt-2">
                  {[1, 2, 3, 4, 5].map((s) => (
                    <button key={s} onClick={() => setReview({ ...review, rider_rating: s })}>
                      <Star className={`w-6 h-6 ${s <= review.rider_rating ? 'fill-accent text-accent' : 'text-muted-foreground'}`} />
                    </button>
                  ))}
                </div>
              </div>
              <textarea
                value={review.comment}
                onChange={(e) => setReview({ ...review, comment: e.target.value })}
                placeholder="Tell us about your experience..."
                className="w-full p-3 rounded-xl border border-border text-sm resize-none focus:outline-none focus:border-primary focus:ring-2 focus:ring-primary/20 transition-all"
                rows={3}
              />
              <div>
                <label className="text-xs font-bold text-muted-foreground uppercase tracking-wide">Add photos (optional)</label>
                {reviewImages.length > 0 && (
                  <div className="flex flex-wrap gap-2 mt-2">
                    {reviewImages.map((url, i) => (
                      <div key={i} className="relative w-20 h-20 rounded-xl overflow-hidden border border-border">
                        <img src={url} alt="" loading="lazy" decoding="async" className="w-full h-full object-cover" />
                        <button type="button" onClick={() => setReviewImages((prev) => prev.filter((_, idx) => idx !== i))} className="absolute top-1 right-1 w-5 h-5 rounded-full bg-black/60 text-white flex items-center justify-center"><X className="w-3 h-3" /></button>
                      </div>
                    ))}
                  </div>
                )}
                {reviewImages.length < 3 && (
                  <div className="mt-2">
                    <ImageUploader value="" onChange={(url) => { if (url) setReviewImages((prev) => [...prev, url]); }} folder="reviews" label="a photo" />
                  </div>
                )}
              </div>
              <button onClick={handleReview} className="w-full py-3.5 rounded-xl bg-gradient-cta text-white font-bold shadow-glow">
                Submit Review (+{reviewHp()} HP)
              </button>
            </div>
          </div>
        </div>
        </ModalPortal>
      )}

      {/* Guest resend-tracking modal — explicit request only, never automatic */}
      {showResend && (
        <div className="fixed inset-0 z-50 bg-black/60 backdrop-blur-md flex items-end sm:items-center justify-center p-4" onClick={() => !resending && setShowResend(false)}>
          <div className="bg-card rounded-3xl p-6 w-full max-w-sm animate-slide-up" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between mb-3">
              <h3 className="font-heading font-bold text-lg text-foreground flex items-center gap-2"><Mail className="w-5 h-5 text-primary" /> Resend tracking email</h3>
              <button onClick={() => setShowResend(false)} disabled={resending}><X className="w-5 h-5 text-muted-foreground" /></button>
            </div>
            <p className="text-xs text-muted-foreground mb-3 leading-relaxed">
              Lost the email or on a new device? We'll resend your tracking link. Use the email you ordered with:
              it must match the order on file. (Rate-limited: 3 sends per order, 5 min cooldown.)
            </p>
            <input
              type="email"
              value={resendEmail}
              onChange={(e) => setResendEmail(e.target.value)}
              placeholder="Your order email"
              className="w-full p-3 rounded-xl border border-border text-sm focus:outline-none focus:ring-2 focus:ring-primary/40 focus:border-primary/40 transition mb-3"
            />
            {resendMsg && (
              <div className={`mb-3 p-2.5 rounded-xl text-xs font-semibold ${resendMsg.ok ? 'bg-success/10 text-success border border-success/20' : 'bg-destructive/10 text-destructive border border-destructive/20'}`}>
                {resendMsg.text}
              </div>
            )}
            <button
              onClick={handleResend}
              disabled={resending}
              className="w-full py-3 rounded-xl bg-gradient-cta text-white font-bold text-sm disabled:opacity-50 active:scale-[0.98] transition flex items-center justify-center gap-2"
            >
              {resending ? <><span className="w-4 h-4 border-2 border-white/40 border-t-white rounded-full animate-spin" /> Sending…</> : <><Mail className="w-4 h-4" /> Send tracking email</>}
            </button>
          </div>
        </div>
      )}

      <ShareSheet
        open={showShare}
        onClose={() => setShowShare(false)}
        type="order"
        payload={{
          orderId: order.id,
          headline: 'My Holy Grills order',
          value: formatNaira(order.total_amount || 0),
          caption: 'Just got my grill on 🔥',
          link: `${window.location.origin}/orders/${order.id}`,
        }}
      />
    </div>
  );
}