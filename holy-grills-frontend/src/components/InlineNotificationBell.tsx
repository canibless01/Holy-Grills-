import { useState, useEffect, useRef } from 'react';
import { Bell, X, Check, CheckCheck } from 'lucide-react';
import { liveApi } from '@/lib/liveApi';
import { toast } from '@/components/ui/use-toast';
/**
 * InlineNotificationBell — opens a dropdown panel of notifications in-place,
 * so admin/kitchen/rider panels never navigate away to the student /notifications
 * page. Polls the unread count, lists recent notifications, and supports
 * mark-one / mark-all read — all without leaving the current panel.
 */
export default function InlineNotificationBell() {
  const [open, setOpen] = useState(false);
  const [notifications, setNotifications] = useState([]);
  const [unread, setUnread] = useState(0);
  const [busy, setBusy] = useState(false);
  const wrapRef = useRef(null);

  const load = async () => {
    try {
      const res = await liveApi.notifications.list({ limit: 20 });
      const list = Array.isArray(res) ? res : (res?.notifications || res?.items || res?.data || []);
      setNotifications(list);
      const flagged = list.filter((n) => !(n.read_at || n.is_read)).length;
      setUnread(res?.unread_count ?? res?.unread ?? flagged);
    } catch { /* not signed in */ }
  };

  useEffect(() => {
    load();
    const timer = setInterval(load, 60000);
    return () => clearInterval(timer);
  }, []);

  useEffect(() => {
    const handler = (e) => {
      if (wrapRef.current && !wrapRef.current.contains(e.target)) setOpen(false);
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, []);

  const markRead = async (id) => {
    try {
      await liveApi.notifications.markRead(id);
      setNotifications((prev) => prev.map((n) => (n.id === id ? { ...n, read_at: new Date().toISOString(), is_read: true } : n)));
      setUnread((u) => Math.max(0, u - 1));
    } catch (e) { toast({ title: 'Could not mark notification', variant: 'destructive' }); }
  };

  const markAllRead = async () => {
    if (busy || unread === 0) return;
    setBusy(true);
    try {
      await liveApi.notifications.markAllRead();
      setNotifications((prev) => prev.map((n) => ({ ...n, read_at: n.read_at || new Date().toISOString(), is_read: true })));
      setUnread(0);
      toast({ title: 'All caught up ✅' });
    } catch (e) { toast({ title: 'Could not mark all read', variant: 'destructive' }); }
    setBusy(false);
  };

  return (
    <div className="relative" ref={wrapRef}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-label="Notifications"
        title="Notifications"
        className="relative w-8 h-8 rounded-full bg-card border border-border flex items-center justify-center text-muted-foreground hover:text-primary transition-colors shrink-0"
      >
        <Bell className="w-4 h-4" />
        {unread > 0 && (
          <span className="absolute -top-1 -right-1 min-w-[16px] h-[16px] px-1 rounded-full bg-primary text-white text-[9px] font-bold flex items-center justify-center ring-2 ring-card">
            {unread > 9 ? '9+' : unread}
          </span>
        )}
      </button>

      {open && (
        <div className="absolute right-0 top-full mt-2 w-80 max-w-[calc(100vw-2rem)] max-h-[70vh] flex flex-col bg-card rounded-2xl border border-border shadow-card z-50 animate-fade-in">
          <div className="flex items-center justify-between px-4 py-3 border-b border-border shrink-0">
            <h3 className="font-heading font-bold text-sm text-foreground">Notifications</h3>
            <div className="flex items-center gap-1">
              {unread > 0 && (
                <button
                  onClick={markAllRead}
                  disabled={busy}
                  className="flex items-center gap-1 px-2 py-1 rounded-lg text-[10px] font-bold text-primary hover:bg-primary/10 disabled:opacity-50 transition-colors"
                  title="Mark all as read"
                >
                  <CheckCheck className="w-3.5 h-3.5" /> Mark all read
                </button>
              )}
              <button onClick={() => setOpen(false)} className="p-1 rounded-lg hover:bg-secondary transition-colors">
                <X className="w-4 h-4 text-muted-foreground" />
              </button>
            </div>
          </div>
          <div className="flex-1 overflow-y-auto">
            {notifications.length === 0 ? (
              <div className="p-8 text-center">
                <Bell className="w-7 h-7 text-muted-foreground/40 mx-auto mb-2" />
                <p className="text-xs text-muted-foreground">No notifications yet.</p>
              </div>
            ) : (
              notifications.map((n) => {
                const isRead = !!(n.read_at || n.is_read);
                return (
                  <button
                    key={n.id}
                    onClick={() => { if (!isRead) markRead(n.id); }}
                    className={`w-full text-left px-4 py-3 border-b border-border last:border-0 hover:bg-secondary/50 transition-colors ${isRead ? '' : 'bg-primary/5'}`}
                  >
                    <div className="flex items-start gap-2.5">
                      {!isRead && <span className="w-2 h-2 rounded-full bg-primary shrink-0 mt-1.5" />}
                      <div className="flex-1 min-w-0">
                        <div className="text-sm font-semibold text-foreground">{n.title || 'Notification'}</div>
                        {n.body && <div className="text-xs text-muted-foreground mt-0.5 line-clamp-2">{n.body}</div>}
                        <div className="text-[10px] text-muted-foreground mt-1">
                          {n.created_at ? new Date(n.created_at).toLocaleString() : ''}
                        </div>
                      </div>
                      {!isRead && <Check className="w-3.5 h-3.5 text-primary/60 shrink-0 mt-1" />}
                    </div>
                  </button>
                );
              })
            )}
          </div>
        </div>
      )}
    </div>
  );
}