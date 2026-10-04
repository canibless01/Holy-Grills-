import { useState, useEffect } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import { ChevronLeft, Calendar, MapPin, Flame, Users, Ticket, Check, QrCode, Camera, Info, Loader2, Download, ChevronRight } from 'lucide-react';
import { liveApi } from '@/lib/liveApi';
import { useHolyGrill } from '@/lib/HolyGrillContext';
import { formatDateTime, formatNaira } from '@/lib/hgUtils';
import { toast } from '@/components/ui/use-toast';
import EventDetailSkeleton from '@/components/skeletons/EventDetailSkeleton';
import EventCheckInScanner from '@/components/EventCheckInScanner';
import RegisterModal from '@/components/events/RegisterModal';

export default function EventDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { user, refreshHp, hpBalance, wallet, isAuthenticated } = useHolyGrill();
  const [event, setEvent] = useState(null);
  const [loading, setLoading] = useState(true);
  const [tiers, setTiers] = useState([]);
  const [selectedTier] = useState(null);
  const [showRegister, setShowRegister] = useState(false);
  const [ticket, setTicket] = useState(null);
  const [scanning, setScanning] = useState(false);
  const [showScanner, setShowScanner] = useState(false);
  const [checkinResult, setCheckinResult] = useState(null);
  const [checkinError, setCheckinError] = useState(null);
  const [paystackProcessing, setPaystackProcessing] = useState(false);

  const unwrap = (res) => res?.data || res;

  useEffect(() => {
    const load = async () => {
      try {
        const e = unwrap(await liveApi.events.get(id));
        // get_event returns no per-user ticket/checked-in field. For an authed
        // user, look up their ticket for this event via /events/my-tickets.
        let myTicket = null;
        try {
          if (isAuthenticated) {
            const mine = await liveApi.events.myTickets();
            const all = [...(mine?.upcoming || []), ...(mine?.past || []), ...(mine?.checked_in || []), ...(mine?.tickets || [])];
            myTicket = all.find((t) => t.event_id === id) || null;
          }
        } catch { /* my-tickets unavailable for guests */ }
        setEvent({ ...e, checked_in: !!(myTicket?.checked_in) });
        if (myTicket) setTicket({ ticket_id: myTicket.ticket_id, status: myTicket.status || 'confirmed', qr_code: myTicket.qr_token, tier_name: myTicket.tier_name });
        try { setTiers(await liveApi.events.getTiers(id)); } catch { /* no tiers */ }
      } catch (e) { console.error(e); }
      setLoading(false);
    };
    load();
  }, [id]);

  // Card payments are webhook-driven (spec §11.6). After Paystack redirects
  // back with a `reference` query param, poll my-tickets until the ticket
  // confirms — the webhook may lag the redirect by a few seconds.
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const reference = params.get('reference') || params.get('ref');
    if (!reference || !isAuthenticated) return;
    setPaystackProcessing(true);
    let cancelled = false;
    const poll = async (attempt) => {
      try {
        const mine = await liveApi.events.myTickets();
        const all = [...(mine?.upcoming || []), ...(mine?.past || []), ...(mine?.checked_in || []), ...(mine?.tickets || [])];
        const found = all.find((t) => t.event_id === id);
        if (found) {
          if (cancelled) return;
          setTicket({ ticket_id: found.ticket_id || found.id, status: found.status || 'confirmed', qr_code: found.qr_token, tier_name: found.tier_name, guest_email: found.guest_email });
          setPaystackProcessing(false);
          toast({ title: '✅ Payment confirmed!', description: 'Your ticket is ready.' });
          // Clean the reference from the URL.
          window.history.replaceState({}, '', window.location.pathname);
          return;
        }
      } catch { /* keep polling */ }
      if (attempt < 6 && !cancelled) {
        setTimeout(() => poll(attempt + 1), 1500);
      } else if (!cancelled) {
        setPaystackProcessing(false);
        toast({ title: 'Payment processing', description: 'Your ticket will appear here once confirmed.', variant: 'default' });
        window.history.replaceState({}, '', window.location.pathname);
      }
    };
    poll(0);
    return () => { cancelled = true; };
  }, [id, isAuthenticated]);

  const price = event?.ticket_price ?? 0;
  const hpReward = event?.hp_per_attendee ?? event?.hp_reward ?? 0;
  const isFree = !event?.is_paid || price === 0;
  const effPrice = selectedTier ? (selectedTier.price_naira ?? 0) : price;

  const handleScannedToken = async (qrToken) => {
    setShowScanner(false);
    setScanning(true);
    try {
      const result = unwrap(await liveApi.events.checkin(id, { qr_token: qrToken }));
      const hpAdded = result?.hp_added_to_pending ?? result?.hp_earned ?? result?.pending_hp ?? result?.hp_awarded ?? 0;
      setCheckinResult({ ...result, hp_added_to_pending: hpAdded });
      await refreshHp();
      setEvent({ ...unwrap(await liveApi.events.get(id)), checked_in: true });
    } catch (e) {
      setCheckinError(e.message);
    }
    setScanning(false);
  };

  if (loading) return <EventDetailSkeleton />;
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

      {event.description && (
        <div className="rounded-2xl bg-card border border-border p-4 shadow-card">
          <h3 className="font-bold text-sm text-foreground mb-2">About this event</h3>
          <p className="text-sm text-muted-foreground leading-relaxed">{event.description}</p>
        </div>
      )}

      <div className="rounded-2xl bg-secondary/50 border border-border p-4 flex gap-3">
        <Info className="w-4 h-4 text-primary mt-0.5 shrink-0" />
        <div className="text-xs text-foreground leading-relaxed">
          {isFree
            ? "Free to attend. Register so we know you're coming, then scan the Holy Grill QR at the entrance to claim your HP."
            : "After registering, your ticket is your payment proof. At the event, scan the Holy Grill QR code at the entrance to check in and earn your HP."}
        </div>
      </div>

      {tiers.length > 0 && (
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
          <h3 className="font-heading font-bold text-lg text-success">Check-in Successful!</h3>
          <div className="flex items-center justify-center gap-1 mt-2">
            <Flame className="w-5 h-5 text-primary" />
            <span className="font-bold text-primary text-sm">+{checkinResult.hp_added_to_pending} HP added to pending pool</span>
          </div>
          <p className="text-xs text-success mt-1">HP unlocks once your next order is delivered</p>
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

      {event.checked_in ? (
        <div className="rounded-2xl bg-success/10 border border-success/20 p-4 flex items-center gap-3">
          <Check className="w-6 h-6 text-success shrink-0" />
          <div>
            <div className="font-bold text-success text-sm">You've checked in! 🎉</div>
            <div className="text-xs text-success">{hpReward} HP added to your pending pool</div>
          </div>
        </div>
      ) : isFree ? (
        <div className="rounded-2xl bg-card border-2 border-primary/20 p-5 text-center space-y-3 shadow-card">
          <QrCode className="w-12 h-12 text-muted-foreground mx-auto" />
          <div>
            <div className="font-bold text-foreground text-sm">{ticket ? "You're in. Bring a friend." : 'Ready to check in?'}</div>
            <div className="text-xs text-muted-foreground mt-1">
              {ticket
                ? 'Point your camera at the Holy Grill QR code displayed at the event entrance to claim your HP.'
                : "Register so we know you're coming, then scan the QR at the entrance."}
            </div>
          </div>
          {!ticket ? (
            <>
              <button onClick={() => setShowRegister(true)} className="w-full py-3.5 rounded-2xl bg-gradient-cta text-white font-bold text-sm shadow-glow transition-all active:scale-[0.98]">
                I'm In
              </button>
              <button onClick={() => setShowScanner(true)} disabled={scanning} className="w-full py-3.5 rounded-2xl border-2 border-primary/20 text-foreground font-bold text-sm flex items-center justify-center gap-2 disabled:opacity-50 transition-all active:scale-[0.98]">
                {scanning ? <><Loader2 className="w-4 h-4 animate-spin" /> Scanning…</> : <><Camera className="w-4 h-4" /> Scan QR Code to Check In</>}
              </button>
            </>
          ) : (
            <button onClick={() => setShowScanner(true)} disabled={scanning} className="w-full py-3.5 rounded-2xl bg-gradient-cta text-white font-bold text-sm flex items-center justify-center gap-2 disabled:opacity-50 transition-all active:scale-[0.98]">
              {scanning ? <><Loader2 className="w-4 h-4 animate-spin" /> Scanning…</> : <><Camera className="w-4 h-4" /> Scan QR Code to Check In</>}
            </button>
          )}
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
            <p className="text-xs text-muted-foreground mt-2">Your entry is confirmed. At the event, scan the Holy Grill QR code at the entrance to check in and earn {hpReward} HP.</p>
          </div>
          <div className="rounded-2xl border-2 border-dashed border-primary/30 p-4 text-center bg-primary/5">
            <QrCode className="w-16 h-16 text-foreground mx-auto mb-2" />
            <div className="text-[10px] text-muted-foreground uppercase tracking-wide">Ticket ID</div>
            <div className="font-mono font-bold text-sm text-foreground break-all">{ticket.ticket_id}</div>
            {ticket.qr_code && <div className="font-mono text-[10px] text-muted-foreground mt-1 break-all">{ticket.qr_code}</div>}
            <p className="text-[10px] text-muted-foreground mt-1">Show this at the entrance</p>
          </div>
          <button
            onClick={async () => {
              try {
                // Guest tickets require guest_email for ownership verification (spec §11.10).
                const url = await liveApi.events.downloadTicketPdf(id, ticket.ticket_id || ticket.id, ticket.guest_email);
                const a = document.createElement('a');
                a.href = url;
                a.download = `holy-grills-ticket-${(ticket.ticket_id || '').slice(0, 8)}.pdf`;
                a.click();
                setTimeout(() => URL.revokeObjectURL(url), 10000);
              } catch (e) {
                toast({ title: 'Download failed', description: e.message, variant: 'destructive' });
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
          className="w-full py-4 rounded-2xl bg-gradient-cta text-white font-bold text-sm shadow-glow transition-all active:scale-[0.98]"
        >
          {tiers.length > 0 ? 'Get Your Ticket' : `I'm In`}
        </button>
      )}

      {showRegister && (
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

      {showScanner && (
        <EventCheckInScanner eventId={id} onScan={handleScannedToken} onClose={() => setShowScanner(false)} />
      )}
    </div>
  );
}