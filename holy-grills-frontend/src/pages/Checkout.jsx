import React, { useState, useEffect, useRef } from 'react';
import { useNavigate, useLocation, Link } from 'react-router-dom';
import { motion } from 'framer-motion';
import { ChevronLeft, ChevronDown, MapPin, CreditCard, Wallet, Split, Check, AlertCircle, AlertTriangle, Tag, User, Plus, Clock, Flame } from 'lucide-react';
import { mockApi } from '@/lib/mockApi';
import { useHolyGrill } from '@/lib/HolyGrillContext';
import { formatNaira } from '@/lib/hgUtils';
import { squadOrderDiscountEnabled, squadOrderDiscountPct, squadDeliveryDiscountEnabled, squadDeliveryDiscountPct, squadOrderMinItems, squadOrderMaxItems, squadOrdersEnabled } from '@/lib/appConfig';
import { toast } from '@/components/ui/use-toast';
import FreeSideCreditModal from '@/components/FreeSideCreditModal';
import SquadOrderButton from '@/components/checkout/SquadOrderButton';
import OffCampusMap from '@/components/OffCampusMap';
import FlameMark from '@/components/FlameMark';
import DeliveryZonesInfo from '@/components/DeliveryZonesInfo';
import { useSound } from '@/lib/SoundProvider';
import Skeleton from '@/components/Skeleton';

function CheckoutSkeleton() {
  return (
    <div className="space-y-4 pb-24">
      <Skeleton className="h-5 w-24" />
      <Skeleton className="h-8 w-40" />
      {Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-32 rounded-2xl" />)}
    </div>
  );
}

export default function Checkout() {
  const navigate = useNavigate();
  const location = useLocation();
  const passed = location.state || {};
  const { cart, wallet, refreshUser, addToCart, isAuthenticated, user, getSetting } = useHolyGrill();
  const { play } = useSound();
  const [loading, setLoading] = useState(true);
  const [placing, setPlacing] = useState(false);
  const [windowStatus, setWindowStatus] = useState(null);
  const [hostels, setHostels] = useState([]);
  const [gates, setGates] = useState([]);
  const [addresses, setAddresses] = useState([]);

  const [deliveryType, setDeliveryType] = useState(null);
  const [hostelId, setHostelId] = useState(null);
  const [gateId, setGateId] = useState(null);
  const [deliveryFee, setDeliveryFee] = useState(0);
  const [deliveryPin, setDeliveryPin] = useState(null);
  const [deliveryAddress, setDeliveryAddress] = useState('');
  const [landmark, setLandmark] = useState('');
  const [feePreview, setFeePreview] = useState(null);
  const [radiusError, setRadiusError] = useState(null);
  const [paymentMethod, setPaymentMethod] = useState('card');
  const [walletAmount, setWalletAmount] = useState(0);
  const [notes, setNotes] = useState('');
  const [guestName, setGuestName] = useState('');
  const [guestPhone, setGuestPhone] = useState('');
  const [guestEmail, setGuestEmail] = useState('');
  const [error, setError] = useState(null);
  const [freeSideCredits, setFreeSideCredits] = useState({ count: 0, expires_at: null });
  const [showFreeSide, setShowFreeSide] = useState(false);
  const [freeSideChoice, setFreeSideChoice] = useState(null);
  const [showGateSelector, setShowGateSelector] = useState(true);
  const [globalAddons, setGlobalAddons] = useState([]);
  const [selectedGlobalAddonIds, setSelectedGlobalAddonIds] = useState([]);
  const [scheduledWindow, setScheduledWindow] = useState(null);
  const [squadSelection, setSquadSelection] = useState(passed.squadId ? { squad_id: passed.squadId, excluded_member_ids: [], extra_members: [] } : null);
  const [reschedule, setReschedule] = useState(null); // { date, payload } — today full, awaiting schedule confirm
  // Promo code is now managed here (moved from the cart page) so the cart stays
  // a pure review of items and checkout owns all order-level adjustments.
  const [promoCode, setPromoCode] = useState('');
  const [promoResult, setPromoResult] = useState(null);
  const [promoError, setPromoError] = useState(null);
  const [validatingPromo, setValidatingPromo] = useState(false);

  useEffect(() => {
    const load = async () => {
      try {
        const [status, h, g, ga] = await Promise.all([
          mockApi.orders.getDeliveryWindowStatus(),
          mockApi.delivery.getHostels(),
          mockApi.delivery.getGates(),
          mockApi.menu.getGlobalAddons().catch(() => []),
        ]);
        setWindowStatus(status);
        setHostels(h || []);
        setGates(g || []);
        setGlobalAddons(Array.isArray(ga) ? ga : (ga?.addons || ga?.global_addons || []));
      } catch (e) { console.error(e); }
      setLoading(false);
    };
    load();
    try { setScheduledWindow(JSON.parse(sessionStorage.getItem('hg_scheduled_window') || 'null')); } catch { /* ignore */ }
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // Addresses + free side credits are auth-scoped. The auth state resolves
  // AFTER mount, so this has to react to it — a mount-only fetch left both
  // stuck at their defaults (free sides always read 0).
  useEffect(() => {
    if (!isAuthenticated) return;
    let live = true;
    (async () => {
      try { const a = await mockApi.addresses.list(); if (live) setAddresses(a || []); } catch { /* ignore */ }
      try { const c = await mockApi.rewards.getFreeSideCredits(); if (live) setFreeSideCredits(c || { count: 0, expires_at: null }); } catch { /* ignore */ }
    })();
    return () => { live = false; };
  }, [isAuthenticated]);

  const subtotal = cart?.subtotal != null ? cart.subtotal : (passed.subtotal || 0);
  const promoDiscount = promoResult?.calculated_discount || 0;
  const squadSubPct = squadSelection?.squad_id && squadOrderDiscountEnabled() ? squadOrderDiscountPct() : 0;
  const squadDelEnabled = squadSelection?.squad_id && squadDeliveryDiscountEnabled();
  const squadDeliveryPct = squadDelEnabled ? squadDeliveryDiscountPct() : 0;
  const squadDiscount = squadSubPct > 0 ? subtotal * (squadSubPct / 100) : 0;
  const squadItemCount = (cart?.items || []).reduce((s, ci) => s + (ci.quantity || 1), 0);
  const squadEligible = squadOrdersEnabled() && squadItemCount >= squadOrderMinItems() && squadItemCount <= squadOrderMaxItems();
  const selectedGlobalAddons = globalAddons.filter((a) => selectedGlobalAddonIds.includes(a.id));
  const globalAddonsTotal = selectedGlobalAddons.reduce((s, a) => s + (Number(a.price) || 0), 0);
  const effectiveDeliveryFee = Math.round(deliveryFee * (1 - squadDeliveryPct / 100));
  const total = Math.max(0, subtotal - promoDiscount - squadDiscount) + effectiveDeliveryFee + globalAddonsTotal;
  // FIX: HP fields live on ci.menu_items, not on the cart item itself.
  const hpPreview = (cart?.items || []).reduce(
    (s, ci) => s + Math.round((Number(ci.menu_items?.hp_earn_value) || 0) * (Number(ci.menu_items?.hp_multiplier) || 1) * (ci.quantity || 1)),
    0
  );

  const effectivePayment = isAuthenticated ? paymentMethod : 'card';

  const calcOnCampusFee = async (id) => {
    if (!id) { setDeliveryFee(0); setFeePreview(null); return; }
    try {
      const res = await mockApi.delivery.calculateFee({ delivery_type: 'on_campus', delivery_location_id: id });
      setDeliveryFee(res.delivery_fee ?? res.fee ?? 0);
    } catch { setDeliveryFee(0); }
    setFeePreview(null);
  };

  const pinRef = useRef(null);
  const gateRef = useRef(null);
  const feeTimer = useRef(null);

  // Off-campus fee: when the pin moves we ask the backend for the nearest gate
  // (no delivery_location_id) and adopt the gate object it returns. A manually
  // chosen gate overrides that for the calc (keepGate) so its fee is used.
  const runFeeCalc = async ({ keepGate = false } = {}) => {
    const ll = pinRef.current;
    if (!ll || ll.lat == null || ll.lng == null) { setDeliveryFee(0); setFeePreview(null); setRadiusError(null); return; }
    const body = { delivery_type: 'off_campus', lat: ll.lat, lon: ll.lng };
    if (keepGate && gateRef.current) body.delivery_location_id = gateRef.current;
    setRadiusError(null);
    try {
      const res = await mockApi.delivery.calculateFee(body);
      const fee = res.delivery_fee ?? res.fee ?? 0;
      setDeliveryFee(fee);
      const returnedGate = res.gate || null;
      if (!keepGate && returnedGate?.id) {
        gateRef.current = returnedGate.id;
        setGateId(returnedGate.id);
      }
      setFeePreview({ fee, km: res.distance_km ?? null, gateName: returnedGate?.name || returnedGate?.id || 'nearest gate' });
    } catch (e) {
      setDeliveryFee(0); setFeePreview(null);
      // Backend rejects pins outside the delivery area — surface its message as-is.
      if (e?.message && /outside|delivery area|radius/i.test(e.message)) setRadiusError(e.message);
    }
  };

  const calcOffCampusFee = (gid, ll, { keepGate = false } = {}) => {
    if (gid !== undefined && gid !== null) gateRef.current = gid;
    if (ll && ll.lat != null) pinRef.current = ll;
    if (feeTimer.current) clearTimeout(feeTimer.current);
    feeTimer.current = setTimeout(() => runFeeCalc({ keepGate }), 350);
  };

  const friendlyPromoError = (msg = '') => {
    if (msg.includes('Promo code has expired')) return 'This promo code has expired.';
    if (msg.includes('not yet active')) return "This code isn't active yet. Check its start date.";
    if (msg.includes('reached its usage limit')) return 'This code has been fully claimed.';
    if (msg.includes('maximum number of times')) return "You've hit the per-user limit for this code.";
    if (msg.includes('Minimum order value')) return msg;
    if (msg.includes('not valid')) return "That code isn't valid for your order.";
    return msg;
  };

  const handleValidatePromo = async () => {
    if (!promoCode) return;
    setValidatingPromo(true);
    setPromoError(null);
    try {
      const result = await mockApi.orders.validatePromo({ code: promoCode, order_subtotal: subtotal });
      setPromoResult(result);
    } catch (e) { setPromoError(friendlyPromoError(e.message)); setPromoResult(null); }
    setValidatingPromo(false);
  };

  const handlePlaceOrder = async () => {
    setError(null);
    // The backend is the source of truth for whether ordering is allowed —
    // never hard-block on the frontend's read of kitchen status. If the
    // kitchen is closed but the user scheduled a window, send it through; if
    // no window was picked, still attempt and surface the backend's own error.
    const scheduled = !windowStatus?.is_open ? scheduledWindow : null;
    if (!deliveryType) { setError('Please choose on-campus or off-campus delivery'); return; }
    if (deliveryType === 'on_campus' && !hostelId) { setError('Please select your hostel'); return; }
    if (deliveryType === 'off_campus') {
      const hasPin = deliveryPin && deliveryPin.lat != null && deliveryPin.lng != null;
      // Block only when there is no pin and no chosen gate. A pin is enough —
      // the backend fills in the nearest gate from the coordinates.
      if (!hasPin && !gateId) { setError('Please select your nearest gate'); return; }
      if (radiusError) { setError(radiusError); return; }
    }
    if (!isAuthenticated) {
      if (!guestName.trim()) { setError('Please enter your name'); return; }
      if (!guestPhone.match(/^(0|\+234)\d{10}$/)) { setError('Phone must be 11 digits (080...) or +234 + 10 digits'); return; }
      if (!guestEmail.trim() || !/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(guestEmail)) { setError('Please enter a valid email'); return; }
    }
    if (effectivePayment === 'split' && isAuthenticated) {
      if (walletAmount <= 0) { setError('Enter a wallet amount for your split payment.'); return; }
      if (walletAmount > (wallet?.balance || 0)) { setError('Wallet amount can\'t exceed your balance.'); return; }
      if (walletAmount > total) { setError('Wallet amount can\'t exceed the order total.'); return; }
    }

    setPlacing(true);
    const payload = {
        items: (cart?.items || []).map((ci) => ({
          menu_item_id: ci.menu_item_id,
          quantity: ci.quantity,
          notes: ci.notes || undefined,
          selected_variations: (ci.selected_variations || []).map((v) => ({ option_id: v.option_id || v.id || v })),
          selected_addons: (ci.selected_addons || []).map((a) => ({ addon_id: a.addon_id || a.id || a, quantity: a.quantity || 1 })),
        })),
        payment_method: effectivePayment,
        order_source: (typeof sessionStorage !== 'undefined' && sessionStorage.getItem('hg_order_source')) || 'website',
        delivery_type: deliveryType,
        promo_code: promoResult?.code,
        ...(squadSelection?.squad_id ? {
          squad_id: squadSelection.squad_id,
          ...(squadSelection.excluded_member_ids?.length ? { excluded_member_ids: squadSelection.excluded_member_ids } : {}),
          ...(squadSelection.extra_members?.length ? { extra_members: squadSelection.extra_members } : {}),
        } : {}),
        notes,
        ...(paymentMethod === 'split' && isAuthenticated ? { wallet_amount: walletAmount } : {}),
        ...(freeSideChoice ? { free_side_credit: true, free_side_choice: freeSideChoice } : {}),
        ...(!isAuthenticated ? { guest_name: guestName, guest_phone: guestPhone, guest_email: guestEmail } : {}),
        ...(deliveryType === 'on_campus'
          ? { delivery_location_id: hostelId }
          : {
            ...(gateId ? { delivery_location_id: gateId } : {}),
            ...(deliveryPin && deliveryPin.lat != null ? { delivery_location_lat: deliveryPin.lat, delivery_location_lon: deliveryPin.lng } : {}),
            delivery_address: deliveryAddress || landmark || 'Off-campus delivery',
          }),
        ...(selectedGlobalAddonIds.length ? { addons: selectedGlobalAddonIds.map((id) => ({ addon_id: id, quantity: 1 })) } : {}),
        ...(scheduled ? { delivery_window_id: scheduled.id, is_scheduled: true } : {}),
      };
    try {
      await submitOrder(payload);
    } catch (e) {
      // "Today's orders are full" — the backend signals ORDERING_WINDOW_AT_CAPACITY
      // with a next_available_date. Offer exactly one reschedule, never a loop.
      const detail = e.detail || {};
      if ((e.message === 'ORDERING_WINDOW_AT_CAPACITY' || detail.error === 'ORDERING_WINDOW_AT_CAPACITY') && detail.next_available_date && !payload.accept_next_available_date) {
        setReschedule({ date: detail.next_available_date, payload });
      } else {
        setError(e.message);
      }
    }
    setPlacing(false);
  };

  // Shared submit — places the order and hands off to the confirmation screen.
  // Throws so the caller can apply its own error handling (capacity reschedule).
  const submitOrder = async (payload) => {
    const result = await mockApi.orders.create(payload);
    const order = result?.order || result;
    play('order_placed');
    if (isAuthenticated) { try { await refreshUser(); } catch { /* ignore */ } }
    if (!isAuthenticated) {
      localStorage.removeItem('hg_guest_cart');
      try {
        const guestOrders = JSON.parse(localStorage.getItem('hg_guest_orders') || '[]');
        guestOrders.unshift({ id: order?.id, claim_token: order?.claim_token, created_at: new Date().toISOString(), total: order?.total_amount || total });
        localStorage.setItem('hg_guest_orders', JSON.stringify(guestOrders.slice(0, 10)));
      } catch { /* ignore */ }
    }
    if (payload.delivery_window_id) { try { sessionStorage.removeItem('hg_scheduled_window'); } catch { /* ignore */ } }
    setReschedule(null);
    navigate(`/order-confirmation/${order?.id || 'pending'}`, {
      state: {
        claim_token: order?.claim_token,
        guest: !isAuthenticated,
        is_scheduled: order?.is_scheduled,
        scheduled_for: order?.scheduled_for,
        delivery_window_start: order?.delivery_window_start,
        delivery_window_end: order?.delivery_window_end,
      },
    });
  };

  // Confirm the "schedule for the next available day" offer — one extra attempt only.
  const handleAcceptReschedule = async () => {
    if (!reschedule) return;
    setError(null);
    setPlacing(true);
    try {
      await submitOrder({ ...reschedule.payload, accept_next_available_date: true });
    } catch (e) {
      setReschedule(null);
      setError(e.message || 'Could not schedule your order. Please try again.');
    }
    setPlacing(false);
  };

  if (loading) return <CheckoutSkeleton />;

  return (
    <div className="space-y-4 animate-fade-in pb-24 max-w-2xl mx-auto">
      <button onClick={() => navigate('/cart')} className="flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground transition-colors">
        <ChevronLeft className="w-4 h-4" /> Back to cart
      </button>
      <div>
        <span className="hg-eyebrow">Almost there</span>
        <h1 className="font-heading font-bold text-xl text-foreground mt-0.5">Checkout</h1>
        <p className="text-sm text-muted-foreground mt-1">One step to the table.</p>
      </div>

      {!isAuthenticated && (
        <div className="flex items-center gap-2 p-3 rounded-xl bg-primary/10 border border-primary/30">
          <User className="w-4 h-4 text-primary shrink-0" />
          <div className="text-xs text-primary">Guest checkout, pay by card. <button onClick={() => navigate('/login')} className="font-bold underline">Sign in</button> to use wallet and earn HP.</div>
        </div>
      )}

      {isAuthenticated && (
        <>
          {/* Free side credit — sits at the top with the squad order entry point */}
          <div className="rounded-2xl bg-primary/10 border border-primary/30 p-3 flex items-center gap-3">
            <span className="text-xl">🏆</span>
            <div className="flex-1 text-xs text-foreground">
              {freeSideCredits.count > 0 ? (
                <>You have <span className="font-bold text-primary">{freeSideCredits.count}</span> free side credit{freeSideCredits.count !== 1 ? 's' : ''}!{freeSideChoice && <span className="text-success font-semibold"> · {freeSideChoice} added at ₦0</span>}</>
              ) : (
                <>No free side credits yet. Earn them through rewards and challenges.</>
              )}
            </div>
            {freeSideCredits.count > 0 && (
              <button onClick={() => setShowFreeSide(true)} className="px-3 py-1.5 rounded-xl bg-gradient-cta text-white text-xs font-bold shrink-0 shadow-glow">
                {freeSideChoice ? 'Change' : 'Use one'}
              </button>
            )}
          </div>
          <SquadOrderButton itemCount={squadItemCount} value={squadSelection} onChange={setSquadSelection} />
        </>
      )}

      {scheduledWindow && !windowStatus?.is_open && (
        <div className="flex items-center gap-2 p-3 rounded-xl bg-accent/20 border border-accent/40">
          <Clock className="w-4 h-4 text-accent-foreground shrink-0" />
          <div className="text-xs text-foreground flex-1">
            Scheduled for <span className="font-bold">{scheduledWindow.label || 'next window'}</span>
            {scheduledWindow.starts_at ? ` · ${new Date(scheduledWindow.starts_at).toLocaleString('en-NG', { dateStyle: 'medium', timeStyle: 'short' })}` : ''}
          </div>
          <button onClick={() => { setScheduledWindow(null); try { sessionStorage.removeItem('hg_scheduled_window'); } catch { /* ignore */ } }} className="text-xs font-bold text-muted-foreground underline">Clear</button>
        </div>
      )}

      {/* Guest details */}
      {!isAuthenticated && (
        <div className="hg-card space-y-2">
          <h3 className="hg-section-title flex items-center gap-2"><User className="w-4 h-4 text-primary" /> Your Details</h3>
          <input value={guestName} onChange={(e) => setGuestName(e.target.value)} placeholder="Full name" className="w-full p-3 rounded-xl border border-border text-sm focus:outline-none focus:border-primary focus:ring-2 focus:ring-primary/20 transition-all" />
          <input value={guestPhone} onChange={(e) => setGuestPhone(e.target.value)} placeholder="08012345678" className="w-full p-3 rounded-xl border border-border text-sm focus:outline-none focus:border-primary focus:ring-2 focus:ring-primary/20 transition-all" />
          <input value={guestEmail} onChange={(e) => setGuestEmail(e.target.value)} placeholder="Email (for order confirmation)" className="w-full p-3 rounded-xl border border-border text-sm focus:outline-none focus:border-primary focus:ring-2 focus:ring-primary/20 transition-all" />
        </div>
      )}

      {/* Saved addresses */}
      {isAuthenticated && (
        <div className="hg-card">
          <div className="flex items-center justify-between mb-3">
            <h3 className="hg-section-title flex items-center gap-2"><MapPin className="w-4 h-4 text-primary" /> Saved Addresses</h3>
            <Link to="/addresses" className="flex items-center gap-1 text-xs font-bold text-primary hover:underline">
              <Plus className="w-3 h-3" /> Edit
            </Link>
          </div>
          {addresses.length > 0 ? (
            <div className="space-y-2">
              {addresses.map((addr) => (
                <button
                  key={addr.id}
                  onClick={() => {
                    const type = addr.type || addr.delivery_type;
                    if (type) setDeliveryType(type);
                    if (type === 'on_campus' && (addr.location_id || addr.hostel_id || addr.delivery_location_id)) {
                      const hid = addr.location_id || addr.hostel_id || addr.delivery_location_id;
                      setHostelId(hid); calcOnCampusFee(hid);
                    }
                    if (type === 'off_campus') {
                      const gid = addr.gate_id || addr.delivery_location_id;
                      if (gid) setGateId(gid);
                      const savedPin = (addr.lat != null && addr.lng != null) ? { lat: addr.lat, lng: addr.lng } : null;
                      if (savedPin) { setDeliveryPin(savedPin); setDeliveryAddress(addr.line1 || addr.description || addr.address || ''); }
                      calcOffCampusFee(gid, savedPin, { keepGate: true });
                    }
                  }}
                  className="w-full flex items-center gap-2 p-3 rounded-xl border border-border text-left hover:border-primary transition-colors bg-card"
                >
                  <MapPin className="w-4 h-4 text-muted-foreground shrink-0" />
                  <div className="flex-1 min-w-0">
                    <div className="text-sm font-semibold text-foreground truncate">{addr.label || addr.name || 'Saved address'}</div>
                    <div className="text-xs text-muted-foreground truncate">{addr.description || addr.address || addr.line1 || ''}</div>
                  </div>
                </button>
              ))}
            </div>
          ) : (
            <Link to="/addresses" className="text-xs text-primary font-semibold hover:underline">+ Add a saved address</Link>
          )}
        </div>
      )}

      {/* Delivery location */}
      <div className="hg-card">
        <h3 className="hg-section-title mb-3 flex items-center gap-2"><MapPin className="w-4 h-4 text-primary" /> Delivery Location</h3>
        <div className="grid grid-cols-2 gap-3">
          <button onClick={() => { setDeliveryType('on_campus'); setHostelId(null); setGateId(null); setDeliveryFee(0); setDeliveryPin(null); setDeliveryAddress(''); setLandmark(''); setFeePreview(null); }} className={`p-3 rounded-xl border text-center transition-all ${deliveryType === 'on_campus' ? 'border-primary bg-primary/10' : 'border-border hover:border-primary/30'}`}>
            <div className="text-xl mb-0.5">🏫</div><div className="text-xs font-semibold text-foreground">On Campus</div>
          </button>
          <button onClick={() => { setDeliveryType('off_campus'); setHostelId(null); setGateId(null); setDeliveryFee(0); setDeliveryAddress(''); setLandmark(''); }} className={`p-3 rounded-xl border text-center transition-all ${deliveryType === 'off_campus' ? 'border-primary bg-primary/10' : 'border-border hover:border-primary/30'}`}>
            <div className="text-xl mb-0.5">🏠</div><div className="text-xs font-semibold text-foreground">Off Campus</div>
          </button>
        </div>

        {deliveryType === 'on_campus' && (
          <div className="mt-3 animate-fade-in">
            <label className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">Select Hostel</label>
            <div className="grid grid-cols-2 gap-2 mt-1.5">
              {hostels.map((h) => (
                <button key={h.id} onClick={() => { setHostelId(h.id); calcOnCampusFee(h.id); }} className={`p-2.5 rounded-xl border text-xs font-semibold transition-all ${hostelId === h.id ? 'border-primary bg-primary/10 text-primary' : 'border-border text-muted-foreground hover:border-primary/30'}`}>
                  {h.name}
                  <div className="text-[10px] font-normal text-muted-foreground">{formatNaira(h.delivery_fee)}</div>
                </button>
              ))}
              {hostels.length === 0 && <p className="text-xs text-muted-foreground col-span-2">No hostels available.</p>}
            </div>
          </div>
        )}

        {deliveryType === 'off_campus' && (
          <div className="mt-3 animate-fade-in space-y-3">
            <label className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">Drop your delivery pin</label>
            <OffCampusMap
              gates={gates}
              pin={deliveryPin}
              onPinChange={(ll) => { setDeliveryPin(ll); calcOffCampusFee(gateId, ll); }}
              selectedGateId={gateId}
              onGateSelect={(g) => { setGateId(g.id); calcOffCampusFee(g.id, deliveryPin, { keepGate: true }); }}
              feePreview={feePreview}
            />

            {radiusError && (
              <div className="flex items-center gap-2 p-3 rounded-xl bg-destructive/10 border border-destructive/30 animate-fade-in">
                <AlertCircle className="w-4 h-4 text-destructive shrink-0" />
                <div className="text-xs text-destructive">{radiusError}</div>
              </div>
            )}

            <div>
              <button type="button" onClick={() => setShowGateSelector((v) => !v)} className="flex items-center gap-2 text-xs font-semibold text-primary">
                <ChevronDown className={`w-3.5 h-3.5 transition-transform ${showGateSelector ? 'rotate-180' : ''}`} />
                {showGateSelector ? 'Hide gate selector' : 'Can\'t see your location? Select closest gate'}
              </button>
              {showGateSelector && (
                <div className="grid grid-cols-2 gap-2 mt-1.5 animate-fade-in">
                  {gates.map((g) => (
                    <button key={g.id} onClick={() => { setGateId(g.id); calcOffCampusFee(g.id, deliveryPin, { keepGate: true }); }} className={`p-2.5 rounded-xl border text-xs font-semibold transition-all ${gateId === g.id ? 'border-primary bg-primary/10 text-primary' : 'border-border text-muted-foreground hover:border-primary/30'}`}>
                      {g.name}
                      <div className="text-[10px] font-normal text-muted-foreground">{formatNaira(g.base_fee)}</div>
                    </button>
                  ))}
                  {gates.length === 0 && <p className="text-xs text-muted-foreground col-span-2">No gates available.</p>}
                </div>
              )}
            </div>

            <div>
              <label className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">Exact address / description</label>
              <input value={deliveryAddress} onChange={(e) => setDeliveryAddress(e.target.value)} placeholder="e.g. Behind the market, near the blue gate" className="w-full mt-1.5 p-3 rounded-xl border border-border text-sm focus:outline-none focus:border-primary focus:ring-2 focus:ring-primary/20 transition-all" />
            </div>

            <div>
              <label className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">Landmark (optional)</label>
              <input value={landmark} onChange={(e) => setLandmark(e.target.value)} placeholder="e.g. Behind the market" className="w-full mt-1.5 p-3 rounded-xl border border-border text-sm focus:outline-none focus:border-primary focus:ring-2 focus:ring-primary/20 transition-all" />
            </div>
          </div>
        )}
        <DeliveryZonesInfo />
      </div>

      {/* Payment method */}
      <div className="hg-card">
        <h3 className="hg-section-title mb-2 flex items-center gap-2"><CreditCard className="w-4 h-4 text-primary" /> Payment Method</h3>
        <div className="space-y-2">
          {[
            { id: 'wallet', label: 'Wallet', icon: Wallet, desc: wallet ? `Balance: ${formatNaira(wallet.balance)}` : '', authOnly: true },
            { id: 'card', label: 'Card', icon: CreditCard, desc: 'Paystack secure payment' },
            { id: 'split', label: 'Split (Wallet + Card)', icon: Split, desc: 'Pay part with wallet, rest with card', authOnly: true },
          ].filter((pm) => !pm.authOnly || isAuthenticated).map((pm) => {
            const Icon = pm.icon;
            return (
              <button key={pm.id} onClick={() => setPaymentMethod(pm.id)} className={`w-full flex items-center gap-3 p-3 rounded-xl border transition-all ${effectivePayment === pm.id ? 'border-primary bg-primary/10' : 'border-border hover:border-primary/30'}`}>
                <Icon className="w-5 h-5 text-muted-foreground" />
                <div className="flex-1 text-left"><div className="text-sm font-semibold text-foreground">{pm.label}</div>{pm.desc && <div className="text-xs text-muted-foreground">{pm.desc}</div>}</div>
                <div className={`w-5 h-5 rounded-full border-2 flex items-center justify-center transition-all ${effectivePayment === pm.id ? 'border-primary bg-primary' : 'border-border'}`}>{effectivePayment === pm.id && <Check className="w-3 h-3 text-white" />}</div>
              </button>
            );
          })}
        </div>
        {effectivePayment === 'split' && (
          <div className="mt-3 animate-slide-up">
            <label className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">Wallet Amount (max {formatNaira(Math.min(wallet?.balance || 0, total))})</label>
            <input type="number" value={walletAmount} onChange={(e) => setWalletAmount(Math.min(wallet?.balance || 0, total, Math.max(0, parseInt(e.target.value) || 0)))} max={Math.min(wallet?.balance || 0, total)} className="w-full mt-1.5 p-3 rounded-xl border border-border text-sm focus:outline-none focus:border-primary focus:ring-2 focus:ring-primary/20 transition-all" />
            <p className="text-xs text-muted-foreground mt-1">Card portion: {formatNaira(Math.max(0, total - walletAmount))}</p>
          </div>
        )}
        {effectivePayment === 'wallet' && wallet && wallet.balance < total && (
          <div className="mt-3 flex items-center gap-2 p-3 rounded-xl bg-destructive/10 border border-destructive/30">
            <AlertCircle className="w-4 h-4 text-destructive shrink-0" />
            <div className="flex-1 text-xs text-destructive">Insufficient balance. Need {formatNaira(total - wallet.balance)} more.</div>
            <button onClick={() => navigate('/wallet')} className="text-xs font-bold text-destructive underline">Fund</button>
          </div>
        )}
      </div>

      {/* Notes */}
      <div className="hg-card">
        <label className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">Order Notes</label>
        <textarea value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="Call before delivery, extra packaging, etc." className="w-full mt-1.5 p-3 rounded-xl border border-border text-sm resize-none focus:outline-none focus:border-primary focus:ring-2 focus:ring-primary/20 transition-all" rows={2} />
      </div>

      {/* Global add-ons — the single, admin-managed add-on system */}
      {globalAddons.length > 0 && (
        <div className="hg-card">
          <h3 className="hg-section-title mb-2 flex items-center gap-2"><Plus className="w-4 h-4 text-primary" /> Add extras to your order</h3>
          <div className="space-y-2">
            {globalAddons.filter((a) => a.is_available !== false).map((a) => {
              const on = selectedGlobalAddonIds.includes(a.id);
              return (
                <button key={a.id} onClick={() => setSelectedGlobalAddonIds((ids) => (on ? ids.filter((x) => x !== a.id) : [...ids, a.id]))} className={`w-full flex items-center justify-between p-2.5 rounded-xl border transition-all ${on ? 'border-primary bg-primary/10' : 'border-border hover:border-primary/30'}`}>
                  <span className="text-sm font-medium text-foreground">{a.name}</span>
                  <span className="text-xs font-bold text-muted-foreground">+{formatNaira(a.price)}</span>
                </button>
              );
            })}
          </div>
        </div>
      )}

      {/* Promo code — moved from the cart page so all order adjustments live here */}
      <div className="hg-card">
        <h3 className="hg-section-title mb-2 flex items-center gap-2"><Tag className="w-4 h-4 text-primary" /> Promo Code</h3>
        <div className="flex gap-2">
          <input type="text" value={promoCode} onChange={(e) => { setPromoCode(e.target.value.toUpperCase()); setPromoResult(null); setPromoError(null); }} placeholder="Try SAVE10 or WELCOME50" className="flex-1 p-3 rounded-xl border border-border text-sm focus:outline-none focus:border-primary focus:ring-2 focus:ring-primary/20 transition-all" />
          <button onClick={handleValidatePromo} disabled={!promoCode || validatingPromo} className="px-4 rounded-xl bg-brand-brown text-white text-xs font-bold disabled:opacity-40 hover:opacity-90 transition-opacity">{validatingPromo ? '...' : 'Apply'}</button>
        </div>
        {promoResult && <div className="mt-2 flex items-center gap-2 text-xs text-success font-semibold"><Check className="w-3.5 h-3.5" /> {promoResult.code} applied. You save {formatNaira(promoResult.calculated_discount)}</div>}
        {promoError && <div className="mt-2 flex items-center gap-2 text-xs text-destructive font-semibold"><AlertTriangle className="w-3.5 h-3.5" /> {promoError}</div>}
      </div>

      {/* Order summary */}
      <div className="rounded-2xl bg-card border border-border p-4 space-y-1.5 text-sm shadow-card">
        <div className="font-heading font-bold text-base text-foreground mb-2">Order Summary</div>
        <div className="flex justify-between"><span className="text-muted-foreground">Subtotal</span><span className="font-semibold text-foreground">{formatNaira(subtotal)}</span></div>
        {promoDiscount > 0 && <div className="flex justify-between text-success"><span>Promo ({promoResult?.code})</span><span>-{formatNaira(promoDiscount)}</span></div>}
        {squadDiscount > 0 && <div className="flex justify-between text-success"><span>Squad ({squadSubPct}%)</span><span>-{formatNaira(squadDiscount)}</span></div>}
        {freeSideChoice && <div className="flex justify-between text-success"><span>🏆 Reward · {freeSideChoice}</span><span>₦0</span></div>}
        <div className="flex justify-between"><span className="text-muted-foreground">Delivery</span><span className="font-semibold">{effectiveDeliveryFee > 0 ? formatNaira(effectiveDeliveryFee) : <span className="text-success">FREE</span>}</span></div>
        {squadDeliveryPct > 0 && deliveryFee > 0 && <div className="flex justify-between text-success"><span>Squad delivery ({squadDeliveryPct}%)</span><span>-{formatNaira(deliveryFee - effectiveDeliveryFee)}</span></div>}
        {globalAddonsTotal > 0 && <div className="flex justify-between"><span className="text-muted-foreground">Extras</span><span className="font-semibold">{formatNaira(globalAddonsTotal)}</span></div>}
        {hpPreview > 0 && <div className="flex justify-between text-accent-foreground"><span className="flex items-center gap-1"><Flame className="w-3.5 h-3.5 text-primary" /> You'll earn</span><span className="font-semibold">+{hpPreview} HP</span></div>}
        <div className="border-t border-border pt-1.5 flex justify-between"><span className="font-semibold text-foreground">Total</span><span className="font-heading font-bold text-lg text-foreground">{formatNaira(total)}</span></div>
      </div>

      {reschedule && (
        <div className="p-3.5 rounded-xl bg-accent/15 border border-accent/40 space-y-2.5">
          <div className="text-sm font-semibold text-foreground">Today's orders are full. Schedule for {reschedule.date} instead?</div>
          <button
            onClick={handleAcceptReschedule}
            disabled={placing}
            className="px-4 py-2.5 rounded-xl bg-gradient-cta text-white text-xs font-bold shadow-glow disabled:opacity-50 active:scale-95 transition"
          >
            Schedule for {reschedule.date}
          </button>
        </div>
      )}

      {error && (
        <div className="flex items-center gap-2 p-3 rounded-xl bg-destructive/10 border border-destructive/30">
          <AlertCircle className="w-4 h-4 text-destructive shrink-0" />
          <span className="text-sm text-destructive">{error}</span>
        </div>
      )}

      <motion.button whileTap={{ scale: 0.97 }} onClick={handlePlaceOrder} disabled={placing} className="w-full py-4 rounded-xl bg-gradient-cta text-white font-bold shadow-glow disabled:opacity-50 transition-opacity">
        {placing ? <span className="flex items-center justify-center gap-2"><span className="w-4 h-4 border-2 border-white/40 border-t-white rounded-full animate-spin" /> Placing order...</span> : `Place Order · ${formatNaira(total)}`}
      </motion.button>

      <FreeSideCreditModal
        open={showFreeSide}
        count={freeSideCredits.count}
        onClose={() => setShowFreeSide(false)}
        onUse={(choice) => {
          setFreeSideChoice(choice);
          setShowFreeSide(false);
          toast({ title: '🏆 Free side added', description: `${choice} added to your order at ₦0. Your credit is used when you place the order.` });
        }}
      />
    </div>
  );
}