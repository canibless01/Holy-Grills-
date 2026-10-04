import React, { useState, useEffect } from 'react';
import { Cookie, X, Check } from 'lucide-react';
import { Link } from 'react-router-dom';
import { getConsent, setConsent } from '@/lib/cookieConsent';

export default function CookieConsent() {
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    // Banner stays away once any dated consent record exists (accept or decline).
    if (!getConsent()) {
      // Small delay so it doesn't clash with page-load animations
      const t = setTimeout(() => setVisible(true), 1500);
      return () => clearTimeout(t);
    }
  }, []);

  const handleAccept = () => {
    setConsent({ analytics: true });
    setVisible(false);
  };

  const handleDecline = () => {
    setConsent({ analytics: false });
    setVisible(false);
  };

  if (!visible) return null;

  return (
    <div className="fixed bottom-0 left-0 right-0 z-50 px-4 pb-4 animate-slide-up pointer-events-none">
      <div className="max-w-2xl mx-auto pointer-events-auto rounded-2xl bg-gradient-dark text-white p-4 shadow-card border border-white/10">
        <div className="flex items-start gap-3">
          <div className="w-10 h-10 rounded-xl bg-white/15 flex items-center justify-center shrink-0">
            <Cookie className="w-5 h-5 text-accent" />
          </div>
          <div className="flex-1 min-w-0">
            <h3 className="font-heading font-bold text-sm text-white mb-1 flex items-center gap-1.5">We use cookies 🔥</h3>
            <p className="text-xs text-white/75 leading-relaxed">
              Essential cookies keep you logged in, remember your cart and deliver order updates — those are always on. Analytics cookies measure how the app is used so we can improve it.{' '}
              <Link to="/terms" className="text-accent font-semibold underline">Terms & Privacy Policy</Link>.
            </p>
            <div className="flex gap-2 mt-3">
              <button onClick={handleAccept} className="flex items-center gap-1.5 px-4 py-2 rounded-full bg-gradient-cta text-white text-xs font-bold shadow-glow">
                <Check className="w-3.5 h-3.5" /> Accept all
              </button>
              <button onClick={handleDecline} className="px-4 py-2 rounded-full bg-white/10 text-white/80 text-xs font-bold border border-white/15 hover:bg-white/15 transition-colors">
                Essential only
              </button>
            </div>
          </div>
          <button onClick={handleDecline} className="p-1.5 rounded-lg hover:bg-white/10 shrink-0 transition-colors" aria-label="Dismiss">
            <X className="w-4 h-4 text-white/60" />
          </button>
        </div>
      </div>
    </div>
  );
}