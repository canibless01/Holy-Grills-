import React, { useState } from 'react';
import { AlertTriangle, RefreshCw } from 'lucide-react';

/**
 * Per-section error boundary for the Admin panel.
 *
 * Catches render errors inside an admin section and shows an inline error
 * card with a retry button — instead of letting the error bubble up to the
 * root ErrorBoundary (which shows a full-page reload prompt and, if a 401
 * cleared the token during the crash, redirects to login on reload).
 *
 * Key behaviours:
 *  - NEVER redirects to login on its own.
 *  - Shows the error message so the admin knows *why* it failed.
 *  - "Try again" resets component state so the section re-mounts cleanly.
 */
export default class SectionErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null, attempt: 0 };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }

  componentDidCatch(error, info) {
    // Log for debugging — does NOT propagate to the root ErrorBoundary.
    console.error('[SectionErrorBoundary]', this.props.sectionName || 'section', error, info);
  }

  handleRetry = () => {
    this.setState((s) => ({ hasError: false, error: null, attempt: s.attempt + 1 }));
  };

  render() {
    if (this.state.hasError) {
      const msg = this.state.error?.message || 'Something went wrong loading this section.';
      const isAuth = /401|unauthor|session expired|log in/i.test(msg);
      return (
        <div className="flex flex-col items-center justify-center py-16 px-4 text-center">
          <div className="w-14 h-14 rounded-2xl bg-red-50 flex items-center justify-center mb-4">
            <AlertTriangle className="w-7 h-7 text-red-500" />
          </div>
          <h3 className="font-heading font-extrabold text-base text-foreground mb-1">
            {isAuth ? 'Session expired' : 'Couldn\'t load this section'}
          </h3>
          <p className="text-sm text-muted-foreground max-w-sm mb-4">
            {isAuth
              ? 'Your session may have expired. Try reloading the page — if you\'re sent to login, sign back in and return here.'
              : msg}
          </p>
          <button
            onClick={this.handleRetry}
            className="flex items-center gap-1.5 px-4 py-2 rounded-full bg-gradient-cta text-white text-sm font-bold shadow-glow"
          >
            <RefreshCw className="w-3.5 h-3.5" /> Try again
          </button>
        </div>
      );
    }

    // Re-mount children on retry (attempt change forces fresh mount)
    return <div key={this.state.attempt}>{this.props.children}</div>;
  }
}