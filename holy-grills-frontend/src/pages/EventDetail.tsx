import { useState, useEffect } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import { ChevronLeft, Calendar, MapPin, Flame, Users, Ticket, Check, Camera, Info, Loader2, Download, ChevronRight } from 'lucide-react';
import { liveApi } from '@/lib/liveApi';
import { useHolyGrill } from '@/lib/HolyGrillContext';
import { formatDateTime, formatNaira } from '@/lib/hgUtils';
import { toast } from '@/components/ui/use-toast';
import EventDetailSkeleton from '@/components/skeletons/EventDetailSkeleton';
import TicketQrImage from '@/components/events/TicketQrImage';
import EventCheckInScanner from '@/components/EventCheckInScanner';
import RegisterModal from '@/components/events/RegisterModal';
import { msg } from '@/lib/messages';

export default function EventDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { user, refreshHp, hpBalance, wallet, isAuthenticated } = useHolyGrill();
  const [event, setEvent] = useState(null);
  const eventId = event?.id || id;
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(false);
  const [retry, setRetry] = useState(0);
  const [tiers, setTiers] = useState([]);
  const [tiersLoading, setTiersLoading] = useState(true);
  const [tiersError, setTiersError] = useState(false);
  const [selectedTier] = useState(null);
  const [showRegister, setShowRegister] = useState(false);
  const [ticket, setTicket] = useState(null);
  const [ticketLookup, setTicketLookup] = useState('ready');
  const [scanning, setScanning] = useState(false);
  const [showScanner, setShowScanner] = useState(false);
  const [checkinResult, setCheckinResult] = useState(null);
  const [checkinError, setCheckinError] = useState(null);
  const [paystackProcessing, setPaystackProcessing] = useState(false);

  const unwrap = (res) => res?.data || res;

  useEffect(() => {
    let cancelled = false;
    setLoading(true); setLoadError(false); setEvent(null); setTicket(null); setTiers([]); setTiersLoading(true); setTiersError(false); setTicketLookup(isAuthenticated ? 'loading' : 'ready');
    liveApi.events.get(id).then(result => {
      if (cancelled) return;
      const detail = unwrap(result); setEvent(detail); setLoading(false);
      liveApi.events.getTiers(detail.id).then(rows => { if (!cancelled) setTiers(rows); }).catch(() => { if (!cancelled) setTiersError(true); }).finally(()=>{if(!cancelled)setTiersLoading(false);});
      if (isAuthenticated) liveApi.events.myTickets().then(mine => {
        if (cancelled) return;
        const all = [...(mine?.upcoming || []), ...(mine?.past || []), ...(mine?.checked_in || []), ...(mine?.tickets || [])];
        const owned = all.find(t => t.event_id === detail.id);
        if (owned && ['paid','not_required'].includes(owned.payment_status)) { setTicket({...owned,ticket_id:owned.ticket_id||owned.id}); setEvent(previous=>previous?.id===detail.id?{...previous,checked_in:!!owned.checked_in}:previous); }
        setTicketLookup('ready');
      }).catch(() => { if (!cancelled) setTicketLookup('error'); });
    }).catch(() => { if (!cancelled) { setLoadError(true); setLoading(false); } });
    const emailProof = new URLSearchParams(window.location.hash.slice(1));
    const emailTicket = emailProof.get('ticket'); const accessToken = emailProof.get('access');
    if (emailTicket && accessToken) liveApi.events.ticketQr(id, emailTicket, undefined, accessToken).then(result => {
      if (!cancelled) setTicket({...result, access_token:accessToken});
    }).catch(error => { if (!cancelled) toast({title:msg('FE_EVENT_TICKET_OPEN_FAILED', 'Your ticket could not be opened'), description:error.message, variant:'destructive'}); });
    return () => { cancelled = true; };
  }, [id, isAuthenticated, retry]);

  // Card payments are webhook-driven (spec §11.6). After Paystack redirects back with a
  // `reference` query param we ask the backend to verify that reference with Paystack
  // (verify-on-return), then poll my-tickets. The webhook stays the primary path; the
  // verify call is the fallback that stops a charged customer being stranded when a
  // delivery fails — previously the ticket stayed `pending`, which also kept the
  // registrant off the host's list even though the seat had been counted.
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const reference = params.get('reference') || params.get('ref');
    const guestEmail = isAuthenticated ? null : sessionStorage.getItem('hg_event_guest_email');
    if (!reference || !event?.id || (!isAuthenticated && !guestEmail)) return;
    setPaystackProcessing(true);
    let cancelled = false;
    const confirmAndClean = (found) => {
      if (cancelled) return;
      setTicket({ ticket_id: found?.ticket_id || found?.id, status: found?.status || 'confirmed', qr_code: found?.qr_token, tier_name: found?.tier_name, guest_email: found?.guest_email || guestEmail, payment_status: found?.payment_status });
      setPaystackProcessing(false);
      if (['refund_pending', 'refunded'].includes(found?.payment_status)) {
        toast({ title: msg('FE_EVENT_REFUND_RECORDED', 'Ticket refund recorded'), description: msg('FE_EVENT_REFUND_RETURN_HELP', 'This payment did not issue an entry ticket. Check the event update for refund details.') });
      } else toast({ title: msg('FE_EVENT_DETAIL_PAYMENT_CONFIRMED', '✅ Payment confirmed!'), description: msg('FE_EVENT_DETAIL_YOUR_TICKET_IS_READY', 'Your ticket is ready.') });
      sessionStorage.removeItem('hg_event_guest_email');
      window.history.replaceState({}, '', window.location.pathname);
    };
    const poll = async (attempt) => {
      try {
        // Idempotent: if the webhook already confirmed the ticket this returns paid.
        const verified = await liveApi.events.verifyTicket(eventId, guestEmail ? { reference, guest_email: guestEmail } : { reference });
        if (['refund_pending', 'refunded'].includes(verified?.payment_status)) {
          confirmAndClean({ ...verified, status: 'cancelled' });
          const latest = unwrap(await liveApi.events.get(id));
          if (!cancelled) setEvent(latest);
          return;
        }
        if (verified?.payment_status === 'paid') {
          if (isAuthenticated) {
            const mine = await liveApi.events.myTickets();
            const all = [...(mine?.upcoming || []), ...(mine?.past || []), ...(mine?.checked_in || []), ...(mine?.tickets || [])];
            confirmAndClean(all.find((t) => t.event_id === eventId) || { ticket_id: verified.ticket_id });
          } else {
            confirmAndClean({ ticket_id: verified.ticket_id });
          }
          return;
        }
        if (isAuthenticated) {
          const mine = await liveApi.events.myTickets();
          const all = [...(mine?.upcoming || []), ...(mine?.past || []), ...(mine?.checked_in || []), ...(mine?.tickets || [])];
          const found = all.find((t) => t.event_id === eventId);
          // A pending reservation is not a paid ticket: my-tickets returns the row as soon
          // as checkout starts, so matching on event_id alone reported "Payment confirmed!"
          // for a registration whose card payment had not (or had failed to) settle.
          const settled = found && ['paid', 'not_required'].includes(found.payment_status);
          if (settled) { confirmAndClean(found); return; }
        }
      } catch { /* keep polling */ }
      if (attempt < 6 && !cancelled) {
        setTimeout(() => poll(attempt + 1), 1500);
      } else if (!cancelled) {
        setPaystackProcessing(false);
        toast({ title: msg('FE_EVENT_DETAIL_PAYMENT_PROCESSING', 'Payment processing'), description: msg('FE_EVENT_DETAIL_YOUR_TICKET_WILL_APPEAR_HERE_ONCE', 'Your ticket will appear here once confirmed.'), variant: 'default' });
        window.history.replaceState({}, '', window.location.pathname);
      }
    };
    poll(0);
    return () => { cancelled = true; };
  }, [event?.id, isAuthenticated]);

  const price = event?.ticket_price ?? (tiers.length ? Number(tiers[0].price_naira) || 0 : 0);
  const hpReward = event?.hp_per_attendee ?? event?.hp_reward ?? 0;
  const isFree = tiers.length ? tiers.some(t => Number(t.price_naira_full ?? t.price_naira ?? 0) === 0) : !event?.is_paid;
  const effPrice = selectedTier ? (selectedTier.price_naira ?? 0) : price;

  const handleScannedToken = async (qrToken) => {
    setShowScanner(false);
    setScanning(true);
    try {
      const result = unwrap(await liveApi.events.checkin(eventId, { qr_token: qrToken, ...(ticket?.ticket_id ? { ticket_id: ticket.ticket_id } : {}) }));
      const hpAdded = result?.hp_added_to_active ?? result?.hp_added_to_pending ?? result?.hp_earned ?? result?.pending_hp ?? result?.hp_awarded ?? 0;
      setCheckinResult({ ...result, hp_added_to_active: hpAdded });
      await refreshHp();
      setEvent({ ...unwrap(await liveApi.events.get(id)), checked_in: true });
    } catch (e) {
      setCheckinError(e.message);
    }
    setScanning(false);
  };

  if (loading) return <EventDetailSkeleton />;
  if (loadError) return <div role="alert" className="mx-auto max-w-md rounded-3xl border border-border bg-card p-8 text-center space-y-4"><p>{msg('FE_EVENT_LOAD_FAILED', 'The event could not be loaded. Check your connection and try again.')}</p><button type="button" onClick={()=>setRetry(value=>value+1)} className="min-h-12 rounded-full bg-primary px-6 py-3 font-bold text-white">{msg('FE_PLATFORM_RETRY', 'Retry')}</button></div>;
  if (!event) return (
    <div className="text-center py-16">
      <Calendar className="w-10 h-10 text-muted-foreground/40 mx-auto mb-3" />
      <p className="text-sm font-semibold text-foreground">Event not found</p>
      <button onClick={() => navigate('/events')} className="mt-3 text-sm text-primary font-bold">Back to events</button>
    </div>
  );

  return (
    <div className="space-y-5 animate-fade-in max-w-2xl mx-auto pb-4">
      <button onClick={() => navigate('/events')} className="flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground transition-colors">
        <ChevronLeft className="w-4 h-4" /> Back to events
      </button>

      <div className="relative rounded-3xl overflow-hidden aspect-[16/10] bg-secondary shadow-card">
        {event.image_url ? (
          <img src={event.image_url} alt={event.title} className="w-full h-full object-cover" />
        ) : (
          <div className="w-full h-full flex items-center justify-center">
            <Calendar className="w-12 h-12 text-muted-foreground/30" />
          </div>
        )}
        <div className="absolute inset-0 bg-gradient-to-t from-foreground/80 via-foreground/30 to-transparent" />
        <div className="absolute bottom-3 left-4 right-4">
          {event.is_featured && (
            <span className="inline-block px-2 py-1 rounded-full bg-gradient-cta text-white text-[10px] font-bold mb-2">⭐ Featured</span>
          )}
          {isFree && (
            <span className="inline-block px-2 py-1 rounded-full bg-success text-white text-[10px] font-bold mb-2 ml-1">FREE</span>
          )}
          <h1 className="font-heading font-extrabold text-2xl text-white leading-tight">{event.title}</h1>
        </div>
      </div>

      {/* Meta pills — date + location, wrap cleanly, no empty slots */}
      <div className="flex flex-wrap gap-2">
        <span className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-card border border-border text-xs font-semibold text-foreground shadow-card">
          <Calendar className="w-3.5 h-3.5 text-primary shrink-0" /> {formatDateTime(event.starts_at)}
        </span>
        {event.location && (
          <span className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-card border border-border text-xs font-semibold text-foreground shadow-card max-w-full">
            <MapPin className="w-3.5 h-3.5 text-primary shrink-0" /> <span className="truncate">{event.location}</span>
          </span>
        )}
      </div>

      {/* Dynamic stat chips — each only renders when it has a value, so the
          row never leaves an L-shaped gap when an event has no price / HP / capacity */}
      <div className="flex flex-wrap gap-2">
        {hpReward > 0 && (
          <span className="inline-flex items-center gap-1 px-3 py-1.5 rounded-full bg-gradient-to-br from-primary/10 to-accent/20 border border-primary/20 text-xs font-bold text-primary">
            <Flame className="w-3.5 h-3.5" /> +{hpReward} HP at the door
          </span>
        )}
        {(event.capacity || event.max_attendees) && (
          <span className="inline-flex items-center gap-1 px-3 py-1.5 rounded-full bg-card border border-border text-xs font-bold text-foreground shadow-card">
            <Users className="w-3.5 h-3.5 text-muted-foreground" /> {event.checkin_count ?? 0}/{event.capacity || event.max_attendees} checked in
          </span>
        )}
        <span className="inline-flex items-center gap-1 px-3 py-1.5 rounded-full bg-card border border-border text-xs font-bold text-foreground shadow-card">
          <Ticket className="w-3.5 h-3.5 text-muted-foreground" /> {isFree ? 'Free entry' : formatNaira(effPrice)}
        </span>
      </div>

      {event.metadata?.lifecycle_status === 'rescheduled' && <div className="rounded-2xl border border-primary/20 bg-secondary p-4 text-sm"><p className="font-bold">{msg('FE_EVENT_RESCHEDULED', 'Event rescheduled')}</p><p>{event.metadata.change_reason}</p><p className="mt-1 text-xs">{msg('FE_EVENT_TICKET_STILL_VALID', 'Your existing ticket remains valid for the date and venue shown above.')}</p></div>}
      {event.description && (
        <div className="rounded-2xl bg-card border border-border p-4 shadow-card">
          <h3 className="font-bold text-sm text-foreground mb-2">About this event</h3>
          <p className="text-sm text-muted-foreground leading-relaxed whitespace-pre-wrap break-words">{event.description}</p>
        </div>
      )}

      {event.metadata?.lifecycle_status !== 'cancelled' && <div className="rounded-2xl bg-secondary/50 border border-border p-4 flex gap-3">
        <Info className="w-4 h-4 text-primary mt-0.5 shrink-0" />
        <div className="text-xs text-foreground leading-relaxed">
          {!isAuthenticated ? msg('FE_EVENT_GUEST_ENTRY_HELP', 'Show your ticket QR to the organizer, or scan the venue QR to record your attendance.') : isFree
            ? "Free to attend. Register so we know you're coming, then scan the Holy Grill QR at the entrance to claim your HP."
            : "After registering, your ticket is your payment proof. At the event, scan the Holy Grill QR code at the entrance to check in and earn your HP."}
        </div>
      </div>}

      {!ticket && ticketLookup==='error' && <div role="alert" className="rounded-2xl border border-border bg-card p-5 text-center space-y-3"><p>{msg('FE_EVENT_OWNED_TICKETS_FAILED','Your existing tickets could not be checked. Retry before starting another registration.')}</p><button className="min-h-11 rounded-full bg-primary px-5 py-2 font-bold text-white" onClick={()=>setRetry(v=>v+1)}>{msg('FE_PLATFORM_RETRY','Retry')}</button></div>}
      {tiersError && <div role="alert" className="rounded-2xl border border-border bg-card p-5 text-center space-y-3"><p>{msg('FE_EVENT_TIERS_FAILED','Ticket options could not be loaded. Please retry before registering.')}</p><button className="min-h-11 rounded-full bg-primary px-5 py-2 font-bold text-white" onClick={()=>setRetry(v=>v+1)}>{msg('FE_PLATFORM_RETRY','Retry')}</button></div>}
      {tiers.some(t=>Number(t.price_naira_full??t.price_naira??0)===0) && tiers.some(t=>Number(t.price_naira_full??t.price_naira??0)>0) && <p className="rounded-xl bg-secondary p-4 text-sm">{msg('FE_EVENT_SUPPORT_HELP','Admission is free. Choose a free ticket, or select an optional paid support tier when you register.')}</p>}
      {tiers.length > 0 && event.metadata?.lifecycle_status !== 'cancelled' && (
        <div className="rounded-2xl bg-card border border-border p-4 shadow-card">
          <h3 className="font-bold text-sm text-foreground mb-3">Ticket Tiers</h3>
          <div className="space-y-2">
            {tiers.map((t) => {
              const sold = t.sold_count ?? t.quantity_sold ?? 0;
              const cap = t.capacity ?? t.quantity_available ?? null;
              const avail = cap != null ? Math.max(0, cap - sold) : null;
              return (
                <Link key={t.id} to={`/events/tiers/${t.id}`} className="flex items-center justify-between p-3 rounded-xl bg-secondary/60 hover:bg-secondary transition-colors">
                  <div className="min-w-0">
                    <div className="font-semibold text-sm text-foreground truncate">{t.name}</div>
                    <div className="text-[11px] text-muted-foreground">{formatNaira(t.price_naira ?? 0)}{t.price_hp ? ` · ${t.price_hp} HP` : ''}{avail != null ? ` · ${avail} left` : ''}</div>
                  </div>
                  <ChevronRight className="w-4 h-4 text-muted-foreground shrink-0" />
                </Link>
              );
            })}
          </div>
        </div>
      )}

      {checkinResult && (
        <div className="rounded-2xl bg-success/10 border border-success/20 p-4 text-center animate-count-up">
          <div className="text-4xl mb-2">✅</div>
          <h3 className="font-heading font-bold text-lg text-success">{checkinResult.replayed ? msg('FE_EVENT_CHECKIN_REPLAY', 'Your check-in is already confirmed') : 'Check-in Successful!'}</h3>
          {checkinResult.is_guest ? <p className="mt-2 text-sm">{msg('FE_EVENT_ATTENDANCE_RECORDED', 'Your attendance has been recorded.')}</p> : <div className="flex items-center justify-center gap-1 mt-2">
            <Flame className="w-5 h-5 text-primary" />
            <span className="font-bold text-primary text-sm">{checkinResult.replayed ? msg('FE_EVENT_HP_RECEIPT', '{amount} HP recorded for this check-in', { amount: checkinResult.hp_added_to_active }) : msg('FE_EVENT_ACTIVE_HP', '+{amount} HP added to your active balance', { amount: checkinResult.hp_added_to_active })}</span>
          </div>}
        </div>
      )}

      {checkinError && (
        <div className="rounded-2xl bg-destructive/10 border border-destructive/20 p-4 text-center">
          <div className="text-2xl mb-2">❌</div>
          <p className="font-bold text-destructive text-sm">{checkinError}</p>
        </div>
      )}

      {/* ===== ACTION AREA ===== */}
      {paystackProcessing && (
        <div className="rounded-2xl bg-accent/10 border border-accent/20 p-4 flex items-center gap-3">
          <Loader2 className="w-5 h-5 text-primary animate-spin shrink-0" />
          <div>
            <div className="font-bold text-foreground text-sm">Confirming your payment…</div>
            <div className="text-xs text-muted-foreground">We're verifying your Paystack payment. Your ticket will appear here shortly.</div>
          </div>
        </div>
      )}

      {event.metadata?.lifecycle_status === 'cancelled' ? <div className="space-y-3 rounded-2xl border border-destructive/20 bg-destructive/5 p-5"><h3 className="font-heading font-bold text-destructive">{msg('FE_EVENT_CANCELLED', 'Event cancelled')}</h3><p className="text-sm">{event.metadata.change_reason}</p><p className="text-xs leading-relaxed">{msg('FE_EVENT_PUBLIC_CANCEL_POLICY', 'Unused paid tickets receive a refund of the ticket amount paid; separately charged payment-provider fees are excluded. Account purchases return to the Holy Grills wallet with spent HP restored; guest credits wait for a verified account linked to the ticket email. Checked-in tickets are excluded. Contact support with your ticket ID if you need help.')}</p><Link to="/contact" className="inline-flex rounded-full bg-secondary px-4 py-2 text-sm font-bold">{msg('FE_EVENT_CONTACT', 'Contact support')}</Link></div> : ['refund_pending', 'refunded'].includes(ticket?.payment_status) ? <div className="rounded-2xl border border-border bg-card p-4"><p className="font-bold">{msg('FE_EVENT_REFUND_RECORDED', 'Ticket refund recorded')}</p><p className="mt-2 text-sm text-muted-foreground">{msg('FE_EVENT_REFUND_RETURN_HELP', 'This payment did not issue an entry ticket. Check the event update for refund details.')}</p>{!isAuthenticated && <div className="mt-3 space-y-3"><p className="text-sm">{msg('FE_EVENT_REFUND_LINK_ACCOUNT','Create and verify an account with your ticket email. Contact support to confirm your refund status.')}</p><Link to="/signup" state={{from:window.location.pathname}} className="inline-flex rounded-full bg-primary px-5 py-2 text-sm font-bold text-white">{msg('FE_EVENT_CREATE_ACCOUNT','Create an account')}</Link></div>}</div> : event.checked_in ? (
        <div className="rounded-2xl bg-success/10 border border-success/20 p-4 flex items-center gap-3">
          <Check className="w-6 h-6 text-success shrink-0" />
          <div>
            <div className="font-bold text-success text-sm">You've checked in! 🎉</div>
            <div className="text-xs text-success">{ticket?.hp_claim_status==='review_required'?msg('FE_EVENT_HP_REVIEW_WAIT','Your attendance HP is awaiting support review.'):msg('FE_EVENT_ATTENDANCE_RECORDED', 'Your attendance has been recorded.')}</div>
          </div>
        </div>
      ) : ticket ? (
        <div className="rounded-2xl bg-card border-2 border-primary/20 p-5 space-y-4 shadow-card">
          <div className="text-center">
            <div className="inline-flex items-center gap-1 px-3 py-1 rounded-full bg-success/15 text-success text-xs font-semibold">
              <Check className="w-3.5 h-3.5" /> Ticket Confirmed
            </div>
            {ticket?.tier_name && (
              <div className="inline-flex items-center gap-1 px-3 py-1 rounded-full bg-accent/15 text-primary text-xs font-semibold ml-2">
                <Ticket className="w-3.5 h-3.5" /> {ticket.tier_name}
              </div>
            )}
            <p className="text-xs text-muted-foreground mt-2">{isAuthenticated ? <>Your entry is confirmed. At the event, scan the Holy Grill QR code at the entrance to check in and earn {hpReward} HP.</> : msg('FE_EVENT_GUEST_ENTRY_HELP', 'Show your ticket QR to the organizer, or scan the venue QR to record your attendance.')}</p>
          </div>
          {!isAuthenticated && <div className="rounded-xl bg-secondary p-4 text-center space-y-3"><p className="text-sm">{msg('FE_EVENT_SIGNUP_REWARD', 'Create an account with your ticket email to earn HP when you attend.')}</p><Link to="/signup" state={{from:`/events/${id}`}} className="inline-flex rounded-full bg-primary px-5 py-2 text-sm font-bold text-white">{msg('FE_EVENT_CREATE_ACCOUNT', 'Create an account')}</Link></div>}
          <div className="rounded-2xl border-2 border-dashed border-primary/30 p-4 text-center bg-primary/5">
            <TicketQrImage eventId={eventId} ticketId={ticket.ticket_id} guestEmail={ticket.guest_email} accessToken={ticket.access_token} />
            <div className="text-[10px] text-muted-foreground uppercase tracking-wide">Ticket ID</div>
            <div className="font-mono font-bold text-sm text-foreground break-all">{ticket.ticket_id}</div>
            {ticket.qr_code && <div className="font-mono text-[10px] text-muted-foreground mt-1 break-all">{ticket.qr_code}</div>}
            <p className="text-[10px] text-muted-foreground mt-1">Show this at the entrance</p>
          </div>
          <button
            onClick={async () => {
              try {
                // Guest tickets require guest_email for ownership verification (spec §11.10).
                const url = await liveApi.events.downloadTicketPdf(eventId, ticket.ticket_id || ticket.id, ticket.guest_email, ticket.access_token);
                const a = document.createElement('a');
                a.href = url;
                a.download = `holy-grills-ticket-${(ticket.ticket_id || '').slice(0, 8)}.pdf`;
                a.click();
                setTimeout(() => URL.revokeObjectURL(url), 10000);
              } catch (e) {
                toast({ title: msg('FE_EVENT_DETAIL_DOWNLOAD_FAILED', 'Download failed'), description: e.message, variant: 'destructive' });
              }
            }}
            className="w-full py-2.5 rounded-2xl border border-border text-foreground text-xs font-bold flex items-center justify-center gap-2 active:scale-95 transition"
          >
            <Download className="w-4 h-4" /> Download Ticket PDF
          </button>
          <button onClick={() => setShowScanner(true)} disabled={scanning} className="w-full py-3.5 rounded-2xl bg-gradient-cta text-white font-bold text-sm flex items-center justify-center gap-2 disabled:opacity-50 transition-all active:scale-[0.98]">
            {scanning ? <><Loader2 className="w-4 h-4 animate-spin" /> Scanning…</> : <><Camera className="w-4 h-4" /> Scan QR Code to Check In</>}
          </button>
        </div>
      ) : (
        <button
          onClick={() => setShowRegister(true)}
          disabled={tiersLoading || tiersError || ticketLookup!=='ready'}
          className="w-full py-4 rounded-2xl bg-gradient-cta text-white font-bold text-sm shadow-glow transition-all active:scale-[0.98] disabled:opacity-50"
        >
          {ticketLookup==='loading' ? msg('FE_EVENT_OWNED_TICKETS_LOADING','Checking your tickets…') : tiersLoading ? msg('FE_EVENT_OPTIONS_LOADING', 'Loading ticket options…') : tiers.length > 0 ? 'Get Your Ticket' : `I'm In`}
        </button>
      )}

      {showRegister && event.metadata?.lifecycle_status !== 'cancelled' && (
        <RegisterModal
          event={event}
          tiers={tiers}
          user={user}
          wallet={wallet}
          hpBalance={hpBalance}
          isAuthenticated={isAuthenticated}
          onClose={() => setShowRegister(false)}
          onSuccess={async (t) => {
            setTicket({ ...t, guest_email: t.guest_email || null });
            setShowRegister(false);
            await refreshHp();
            setEvent(unwrap(await liveApi.events.get(id)));
          }}
        />
      )}

      {showScanner && event.metadata?.lifecycle_status !== 'cancelled' && (
        <EventCheckInScanner eventId={eventId} onScan={handleScannedToken} onClose={() => setShowScanner(false)} />
      )}
    </div>
  );
}
