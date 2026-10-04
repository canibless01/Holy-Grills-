import { Link } from 'react-router-dom';
import { Bike, Power, ExternalLink, LogOut, Volume2, VolumeX } from 'lucide-react';
import { useSound } from '@/lib/SoundProvider';
import InlineNotificationBell from '@/components/InlineNotificationBell';

// Sticky rider header with duty toggle (Online/Offline). The toggle captures
// real GPS when going online (PATCH /riders/availability with location_lat/lng).
// Sound toggle lets the rider mute/unmute dispatch alerts.
export default function RiderHeader({ online, onToggleOnline, onSignOut, busy = false }) {
  const { soundOn, toggleSound } = useSound();

  return (
    <header className="sticky top-0 z-30 bg-white/90 backdrop-blur-md border-b border-border">
      <div className="max-w-2xl mx-auto px-4 sm:px-6 h-14 flex items-center justify-between gap-2">
        <div className="flex items-center gap-2.5 min-w-0">
          <div className={`w-8 h-8 rounded-xl flex items-center justify-center shrink-0 transition-all ${online ? 'bg-gradient-cta shadow-glow' : 'bg-secondary'}`}>
            <Bike className="w-5 h-5 text-white" />
          </div>
          <div className="min-w-0">
            <h1 className="font-heading font-extrabold text-base sm:text-lg text-foreground leading-none">Rider</h1>
            <div className="flex items-center gap-1.5 mt-1">
              <span className={`w-2 h-2 rounded-full ${online ? 'bg-emerald-500' : 'bg-muted-foreground'} relative flex`}>
                {online && <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-500 opacity-60" />}
              </span>
              <span className="text-[11px] font-bold text-muted-foreground">{online ? 'On duty' : 'Off duty'}</span>
            </div>
          </div>
        </div>

        <div className="flex items-center gap-1.5 sm:gap-2 shrink-0">
          <InlineNotificationBell />
          <button
            onClick={toggleSound}
            className="w-8 h-8 rounded-full bg-card border border-border flex items-center justify-center text-muted-foreground hover:text-primary transition-colors"
            aria-label="Toggle sound"
          >
            {soundOn ? <Volume2 className="w-4 h-4" /> : <VolumeX className="w-4 h-4" />}
          </button>
          <Link
            to="/"
            className="hidden sm:flex items-center gap-1.5 px-3 py-2 rounded-full bg-card border border-border text-xs font-bold text-foreground hover:text-primary transition-colors"
          >
            View Site <ExternalLink className="w-3.5 h-3.5" />
          </Link>
          <button
            onClick={onSignOut}
            className="flex items-center gap-1.5 px-3 py-2 rounded-full bg-red-50 border border-red-200 text-xs font-bold text-red-600 hover:bg-red-100 transition-colors"
          >
            <LogOut className="w-3.5 h-3.5" /> <span className="hidden sm:inline">Sign out</span>
          </button>
          <button
            onClick={onToggleOnline}
            disabled={busy}
            className={`flex items-center gap-1.5 px-3.5 py-2 rounded-full text-xs font-bold transition-all disabled:opacity-70 ${
              online
                ? 'bg-emerald-500 text-white shadow-glow active:scale-95'
                : 'bg-gradient-cta text-white shadow-glow active:scale-95'
            }`}
          >
            {busy
              ? <span className="w-3.5 h-3.5 border-2 border-white/40 border-t-white rounded-full animate-spin" />
              : <Power className="w-3.5 h-3.5" />}
            {busy ? 'Locating…' : online ? 'Online' : 'Go Online'}
          </button>
        </div>
      </div>
    </header>
  );
}