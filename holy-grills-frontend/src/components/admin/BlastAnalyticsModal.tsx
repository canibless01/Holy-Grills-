import { X, Eye, MousePointer, TrendingUp, Clock, Link } from 'lucide-react';
import { apiClient } from '@/lib/apiClient';
import { useState, useEffect } from 'react';
import LoadingSpinner from '@/components/LoadingSpinner';

interface BlastAnalyticsModalProps {
  open: boolean;
  onClose: () => void;
  blastId: string;
  blastTitle: string;
}

interface AnalyticsData {
  blast_id: string;
  recipient_count: number;
  open_count: number;
  click_count: number;
  open_rate: number;
  click_rate: number;
  click_to_open_rate: number;
  last_opened_at: string | null;
  link_clicks: Record<string, { url: string; label: string; count: number }>;
  recent_opens: Array<{ timestamp: string; ip: string; user_agent: string }>;
  recent_clicks: Array<{ timestamp: string; url: string; label: string; ip: string; user_agent: string }>;
}

export default function BlastAnalyticsModal({ open, onClose, blastId, blastTitle }: BlastAnalyticsModalProps) {
  const [analytics, setAnalytics] = useState<AnalyticsData | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (open && blastId) {
      loadAnalytics();
    }
  }, [open, blastId]);

  const loadAnalytics = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await apiClient.get(`/notifications/blasts/${blastId}/analytics`);
      setAnalytics(data);
    } catch (e) {
      setError(e.message || 'Failed to load analytics');
    }
    setLoading(false);
  };

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50 backdrop-blur-sm">
      <div className="relative w-full max-w-4xl max-h-[90vh] overflow-hidden bg-card rounded-2xl border border-border shadow-2xl">
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-border">
          <div>
            <h2 className="font-bold text-lg text-foreground">Email Analytics</h2>
            <p className="text-sm text-muted-foreground">{blastTitle}</p>
          </div>
          <button
            onClick={onClose}
            className="p-2 rounded-lg hover:bg-secondary transition"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Content */}
        <div className="overflow-y-auto max-h-[calc(90vh-80px)] p-6">
          {loading ? (
            <div className="flex items-center justify-center py-12">
              <LoadingSpinner />
            </div>
          ) : error ? (
            <div className="text-center py-12">
              <p className="text-destructive">{error}</p>
              <button
                onClick={loadAnalytics}
                className="mt-4 px-4 py-2 rounded-lg bg-primary text-white text-sm font-medium hover:bg-primary/90"
              >
                Retry
              </button>
            </div>
          ) : analytics ? (
            <div className="space-y-6">
              {/* Summary Stats */}
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <div className="p-4 rounded-xl bg-secondary border border-border">
                  <div className="flex items-center gap-2 mb-2">
                    <TrendingUp className="w-5 h-5 text-primary" />
                    <span className="text-sm font-medium text-foreground">Sent</span>
                  </div>
                  <div className="text-2xl font-bold text-foreground">{analytics.recipient_count}</div>
                  <div className="text-xs text-muted-foreground">recipients</div>
                </div>

                <div className="p-4 rounded-xl bg-secondary border border-border">
                  <div className="flex items-center gap-2 mb-2">
                    <Eye className="w-5 h-5 text-primary" />
                    <span className="text-sm font-medium text-foreground">Opens</span>
                  </div>
                  <div className="text-2xl font-bold text-foreground">{analytics.open_count}</div>
                  <div className="text-xs text-muted-foreground">
                    {analytics.open_rate}% open rate
                  </div>
                </div>

                <div className="p-4 rounded-xl bg-secondary border border-border">
                  <div className="flex items-center gap-2 mb-2">
                    <MousePointer className="w-5 h-5 text-primary" />
                    <span className="text-sm font-medium text-foreground">Clicks</span>
                  </div>
                  <div className="text-2xl font-bold text-foreground">{analytics.click_count}</div>
                  <div className="text-xs text-muted-foreground">
                    {analytics.click_rate}% click rate
                  </div>
                </div>
              </div>

              {/* Click-to-Open Rate */}
              <div className="p-4 rounded-xl bg-primary/10 border border-primary/20">
                <div className="flex items-center justify-between">
                  <div>
                    <div className="text-sm font-medium text-foreground">Click-to-Open Rate</div>
                    <div className="text-xs text-muted-foreground">Percentage of opens that resulted in clicks</div>
                  </div>
                  <div className="text-3xl font-bold text-primary">{analytics.click_to_open_rate}%</div>
                </div>
              </div>

              {/* Link Clicks Breakdown */}
              {Object.keys(analytics.link_clicks).length > 0 && (
                <div>
                  <h3 className="font-semibold text-foreground mb-3 flex items-center gap-2">
                    <Link className="w-4 h-4" />
                    Link Performance
                  </h3>
                  <div className="space-y-2">
                    {Object.values(analytics.link_clicks).map((link, idx) => (
                      <div key={idx} className="flex items-center justify-between p-3 rounded-lg bg-secondary border border-border">
                        <div className="flex-1 min-w-0">
                          <div className="text-sm font-medium text-foreground truncate">
                            {link.label || 'Unnamed Link'}
                          </div>
                          <div className="text-xs text-muted-foreground truncate">
                            {link.url}
                          </div>
                        </div>
                        <div className="text-right ml-4">
                          <div className="text-lg font-bold text-foreground">{link.count}</div>
                          <div className="text-xs text-muted-foreground">clicks</div>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Recent Activity */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {/* Recent Opens */}
                <div>
                  <h3 className="font-semibold text-foreground mb-3 flex items-center gap-2">
                    <Eye className="w-4 h-4" />
                    Recent Opens
                  </h3>
                  {analytics.recent_opens.length > 0 ? (
                    <div className="space-y-2 max-h-64 overflow-y-auto">
                      {analytics.recent_opens.map((open, idx) => (
                        <div key={idx} className="p-2 rounded-lg bg-secondary border border-border text-xs">
                          <div className="flex items-center gap-2 text-muted-foreground">
                            <Clock className="w-3 h-3" />
                            {new Date(open.timestamp).toLocaleString()}
                          </div>
                          <div className="text-foreground mt-1 truncate">
                            {open.user_agent.substring(0, 50)}...
                          </div>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <div className="text-sm text-muted-foreground text-center py-4">
                      No opens yet
                    </div>
                  )}
                </div>

                {/* Recent Clicks */}
                <div>
                  <h3 className="font-semibold text-foreground mb-3 flex items-center gap-2">
                    <MousePointer className="w-4 h-4" />
                    Recent Clicks
                  </h3>
                  {analytics.recent_clicks.length > 0 ? (
                    <div className="space-y-2 max-h-64 overflow-y-auto">
                      {analytics.recent_clicks.map((click, idx) => (
                        <div key={idx} className="p-2 rounded-lg bg-secondary border border-border text-xs">
                          <div className="flex items-center gap-2 text-muted-foreground">
                            <Clock className="w-3 h-3" />
                            {new Date(click.timestamp).toLocaleString()}
                          </div>
                          <div className="text-foreground mt-1 truncate">
                            {click.label || 'Link'}
                          </div>
                          <div className="text-muted-foreground truncate">
                            {click.url.substring(0, 40)}...
                          </div>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <div className="text-sm text-muted-foreground text-center py-4">
                      No clicks yet
                    </div>
                  )}
                </div>
              </div>

              {/* Last Opened */}
              {analytics.last_opened_at && (
                <div className="text-sm text-muted-foreground text-center">
                  Last opened: {new Date(analytics.last_opened_at).toLocaleString()}
                </div>
              )}
            </div>
          ) : null}
        </div>
      </div>
    </div>
  );
}
