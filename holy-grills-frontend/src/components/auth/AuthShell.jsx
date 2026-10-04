import React from 'react';
import { Link } from 'react-router-dom';
import { Flame } from 'lucide-react';
import BrandLogo from '@/components/BrandLogo';

// Domain 1 — unified auth shell. Every auth surface (Login, Register,
// Forgot/Reset Password, OAuth Consent) renders through this so the whole
// identity flow feels like one screen, one era. Warm ambient background,
// shared brand lockup, centered content. Owns the full viewport (auth routes
// sit outside the app Layout) for an immersive, focused experience.
export default function AuthShell({ children, footer }) {
  return (
    <div className="relative min-h-screen flex flex-col items-center justify-center px-5 py-10 overflow-hidden bg-beige-soft">
      {/* Ambient brand glows — soft, alive, never muddy */}
      <div className="pointer-events-none absolute -top-28 -left-24 w-72 h-72 rounded-full bg-primary/20 blur-3xl" />
      <div className="pointer-events-none absolute -bottom-32 -right-16 w-80 h-80 rounded-full bg-accent/25 blur-3xl" />
      <div className="pointer-events-none absolute inset-0 bg-gradient-to-b from-transparent via-transparent to-white/40" />

      <div className="relative w-full max-w-sm flex flex-col items-center animate-fade-in">
        {/* Brand lockup */}
        <Link to="/" className="flex items-center justify-center mb-7 group">
          <BrandLogo size="auth" className="transition-transform group-hover:scale-105 group-active:scale-95" />
        </Link>

        {children}

        {footer && (
          <div className="mt-6 text-center text-xs text-muted-foreground">{footer}</div>
        )}
      </div>
    </div>
  );
}