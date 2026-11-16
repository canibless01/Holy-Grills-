import React from 'react';
import { RefreshCw } from 'lucide-react';
import FlameMark from '@/components/FlameMark';

/**
 * ErrorBoundary — catches render-time crashes so a broken component
 * shows a friendly reload prompt instead of a permanent blank screen.
 */
type ErrorBoundaryProps = { children: React.ReactNode };
type ErrorBoundaryState = { hasError: boolean; error: Error | null };

export default class ErrorBoundary extends React.Component<ErrorBoundaryProps, ErrorBoundaryState> {
  constructor(props: ErrorBoundaryProps) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, info: React.ErrorInfo) {
    console.error('ErrorBoundary caught:', error, info);
  }

  handleReload = () => {
    this.setState({ hasError: false, error: null });
    window.location.href = window.location.pathname;
  };

  render() {
    if (this.state.hasError) {
      return (
        <div className="min-h-screen bg-muted flex flex-col items-center justify-center px-6 text-center">
          <div className="w-16 h-16 rounded-2xl bg-gradient-cta flex items-center justify-center shadow-xl mb-4">
            <FlameMark className="w-8 h-8" />
          </div>
          <h1 className="font-heading font-bold text-xl text-foreground mb-1">Something went wrong</h1>
          <p className="text-sm text-muted-foreground mb-6 max-w-xs">
            The grill hit a snag loading this page. A quick reload usually fixes it.
          </p>
          <button
            onClick={this.handleReload}
            className="inline-flex items-center gap-2 px-5 py-2.5 rounded-full bg-gradient-cta text-white font-bold text-sm shadow-md"
          >
            <RefreshCw className="w-4 h-4" /> Reload
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}