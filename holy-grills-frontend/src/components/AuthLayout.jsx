import React from "react";
import AuthShell from "@/components/auth/AuthShell";

// Domain 1 — refreshed AuthLayout. Preserves the original API (icon, title,
// subtitle, footer, children) so OAuthConsent's logic is untouched, but now
// renders through the shared AuthShell for a uniform look across the whole
// auth flow. Used by ResetPassword and OAuthConsent.
export default function AuthLayout({ icon: Icon, title, subtitle, footer, children }) {
  return (
    <AuthShell footer={footer}>
      <div className="w-full bg-card rounded-2xl border border-border shadow-card p-6">
        <div className="flex flex-col items-center text-center mb-5">
          <div className="w-12 h-12 rounded-2xl bg-gradient-cta flex items-center justify-center shadow-glow mb-3">
            <Icon className="w-6 h-6 text-white" aria-hidden="true" />
          </div>
          <h1 className="font-heading font-bold text-xl text-foreground">{title}</h1>
          {subtitle && <p className="text-xs text-muted-foreground mt-1 max-w-xs leading-relaxed">{subtitle}</p>}
        </div>
        {children}
      </div>
    </AuthShell>
  );
}