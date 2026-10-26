import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { ExternalLink, LogOut, Volume2, VolumeX } from 'lucide-react';
import { Switch } from '@/components/ui/switch';
import BrandLogo from '@/components/BrandLogo';
import { clearTokens } from '@/lib/apiClient';
import { useSound } from '@/lib/SoundProvider';
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent,
  AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import InlineNotificationBell from '@/components/InlineNotificationBell';
import PanelSwitcher from '@/components/PanelSwitcher';
import { msg } from '@/lib/messages';

// Sticky kitchen header with open/closed toggle (PATCH /kitchen/settings),
// sound toggle, and navigation. The toggle maps to is_accepting_orders —
// closing requires a confirmation dialog per the kitchen spec.
export default function KitchenHeader({ accepting, open, onToggleAccepting, deliveryWindow = null }) {
  const navigate = useNavigate();
  const { soundOn, toggleSound } = useSound();
  const [showConfirm, setShowConfirm] = useState(false);

  const handleSwitch = (checked) => {
    if (!checked) {
      setShowConfirm(true);
    } else {
      onToggleAccepting(true);
    }
  };

  const confirmClose = () => {
    setShowConfirm(false);
    onToggleAccepting(false);
  };

  const dotColor = open && accepting ? 'bg-success' : accepting ? 'bg-warn' : 'bg-destructive';
  const deliveryStart = deliveryWindow?.delivery_starts_at;
  const deliveryEnd = deliveryWindow?.delivery_ends_at;
  const deliveryLabel = deliveryStart && deliveryEnd ? msg('FE_KITCHEN_DELIVERY_HOURS', 'Delivery {start}–{end}', { start: deliveryStart, end: deliveryEnd }) : msg('FE_KITCHEN_DELIVERY_UNCONFIGURED', 'Delivery time not configured');
  const statusLabel = open && accepting ? 'Open' : accepting ? 'Paused — no window' : 'Closed';

  return (
    <>
      <header className="sticky top-0 z-30 w-full bg-white/90 backdrop-blur-md border-b border-border">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 h-14 flex items-center justify-between gap-3">
          <div className="flex items-center gap-2.5 min-w-0">
            <BrandLogo size="admin" className="shrink-0" />
            <div className="min-w-0">
              <h1 className="font-heading font-extrabold text-base sm:text-lg text-foreground leading-none truncate">Kitchen</h1>
              <div className="flex items-center gap-1.5 mt-1">
                <span className={`w-2 h-2 rounded-full ${dotColor} relative flex`}>
                  {open && accepting && (
                    <span className={`animate-ping absolute inline-flex h-full w-full rounded-full ${dotColor} opacity-60`} />
                  )}
                </span>
                <span className="text-[11px] font-bold text-muted-foreground">{statusLabel}</span>
              </div>
              <div className="text-[10px] text-muted-foreground truncate">{deliveryLabel}</div>
            </div>
          </div>

          <div className="flex items-center gap-1.5 sm:gap-2.5 shrink-0">
            <InlineNotificationBell />
            <div className="flex items-center gap-2 px-2.5 py-1.5 rounded-full bg-secondary">
              <Switch
                checked={open && accepting}
                onCheckedChange={handleSwitch}
                className="data-[state=checked]:bg-success data-[state=unchecked]:bg-destructive/40"
              />
              <span className="hidden sm:inline text-[11px] font-bold text-foreground">{open && accepting ? 'Open' : 'Closed'}</span>
            </div>
            <button
              onClick={toggleSound}
              className="w-8 h-8 rounded-full bg-card border border-border flex items-center justify-center text-muted-foreground hover:text-primary transition-colors"
              aria-label="Toggle sound"
            >
              {soundOn ? <Volume2 className="w-4 h-4" /> : <VolumeX className="w-4 h-4" />}
            </button>
            {/* One-icon panel switcher: admin → back to /admin; kitchen
                staff → student page (also their mobile way back, since the
                View Site pill starts at sm). */}
            <PanelSwitcher className="w-8 h-8 rounded-full bg-card border border-border flex items-center justify-center text-muted-foreground hover:text-primary transition-colors" />
            <Link
              to="/"
              className="hidden sm:flex items-center gap-1.5 px-3 py-2 rounded-full bg-card border border-border text-xs font-bold text-foreground hover:text-primary transition-colors"
            >
              View Site <ExternalLink className="w-3.5 h-3.5" />
            </Link>
            <button
              onClick={() => { clearTokens(); navigate('/'); }}
              className="flex items-center gap-1.5 px-3 py-2 rounded-full tone-error border border-destructive/30 text-xs font-bold text-destructive hover:bg-destructive/15 transition-colors"
            >
              <LogOut className="w-3.5 h-3.5" /> <span className="hidden sm:inline">Sign out</span>
            </button>
          </div>
        </div>
      </header>

      <AlertDialog open={showConfirm} onOpenChange={setShowConfirm}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Close the kitchen?</AlertDialogTitle>
            <AlertDialogDescription>
              Users won't be able to checkout while the kitchen is closed. You can reopen at any time.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={confirmClose}
              className="bg-destructive text-white hover:bg-destructive"
            >
              Yes, close kitchen
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}