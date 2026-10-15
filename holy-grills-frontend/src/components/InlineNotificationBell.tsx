import { useState, useEffect, useRef, useCallback } from 'react';
import { createPortal } from 'react-dom';
import { useNavigate, useLocation } from 'react-router-dom';
import { Bell, X, Check, CheckCheck } from 'lucide-react';
import { liveApi } from '@/lib/liveApi';
import { toast } from '@/components/ui/use-toast';
import { msg } from '@/lib/messages';

/**
 * InlineNotificationBell — opens a dropdown panel of notifications in-place,
 * so admin/kitchen/rider panels never navigate away to the student /notifications
 * page. Polls the unread count, lists recent notifications, and supports
 * mark-one / mark-all read — all without leaving the current panel.
 *
 * Two things this component gets right on a phone:
 *
 *   • The panel is PORTALLED to <body> and positioned from the bell's rect, so a
 *     narrow panel header with `overflow-hidden` (or any transformed ancestor)
 *     can no longer clip it — the "cut off on mobile" bug in the rider and
 *     kitchen headers. Below `sm` it spans the viewport with 8px gutters; above
 *     it is the 320px dropdown anchored to the bell.
 *
 *   • A notification that carries `action_url` (the backend sets one for order,
 *     wallet, HP, rider, kitchen and squad types — and for pushes) actually goes
 *     there. Rows without a destination still just mark themselves read.
 */
export default function InlineNotificationBell() {
  const [open, setOpen] = useState(false);
  const [notifications, setNotifications] = useState([]);
  const [unread, setUnread] = useState(0);
  const [busy, setBusy] = useState(false);
  const [anchor, setAnchor] = useState<{ top: number; left?: number; right?: number; width?: number }>({ top: 0 });
  const wrapRef = useRef(null);
  const panelRef = useRef(null);
  const navigate = useNavigate();
  const { pathname } = useLocation();

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

  /** Keep the portalled panel glued to the bell (and on-screen) while open. */
  const place = useCallback(() => {
    const el = wrapRef.current;
    if (!el) return;
    const rect = el.getBoundingClientRect();
    if (window.innerWidth < 640) {
      setAnchor({ top: rect.bottom + 8, left: 8, right: 8 });
    } else {
      setAnchor({ top: rect.bottom + 8, right: Math.max(8, window.innerWidth - rect.right), width: 320 });
    }
  }, []);

  useEffect(() => {
    if (!open) return;
    place();
    window.addEventListener('resize', place);
    window.addEventListener('scroll', place, true);
    return () => {
      window.removeEventListener('resize', place);
      window.removeEventListener('scroll', place, true);
    };
  }, [open, place]);

  useEffect(() => {
    if (!open) return;
    const onDown = (e) => {
      if (wrapRef.current?.contains(e.target)) return;
      if (panelRef.current?.contains(e.target)) return;
      setOpen(false);
    };
    const onKey = (e) => { if (e.key === 'Escape') setOpen(false); };
    document.addEventListener('mousedown', onDown);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onDown);
      document.removeEventListener('keydown', onKey);
    };
  }, [open]);

  // A panel is never left hanging over the next screen.
  useEffect(() => { setOpen(false); }, [pathname]);

  const markRead = async (id) => {
    try {
      await liveApi.notifications.markRead(id);
      setNotifications((prev) => prev.map((n) => (n.id === id ? { ...n, read_at: new Date().toISOString(), is_read: true } : n)));
      setUnread((u) => Math.max(0, u - 1));
    } catch (e) { toast({ title: msg('FE_INLINE_NOTIFICATION_BELL_COULD_NOT_MARK_NOTIFICATION', 'Could not mark notification'), variant: 'destructive' }); }
  };

  const markAllRead = async () => {
    if (busy || unread === 0) return;
    setBusy(true);
    try {
      await liveApi.notifications.markAllRead();
      setNotifications((prev) => prev.map((n) => ({ ...n, read_at: n.read_at || new Date().toISOString(), is_read: true })));
      setUnread(0);
      toast({ title: msg('FE_INLINE_NOTIFICATION_BELL_ALL_CAUGHT_UP', 'All caught up ✅') });
    } catch (e) { toast({ title: msg('FE_INLINE_NOTIFICATION_BELL_COULD_NOT_MARK_ALL_READ', 'Could not mark all read'), variant: 'destructive' }); }
    setBusy(false);
  };

  /** Mark read, then follow the notification's own destination when it has one. */
  const openNotification = (n) => {
    const isRead = !!(n.read_at || n.is_read);
    if (!isRead) markRead(n.id);
    const target = n.action_url || n.metadata?.action_url || n.data?.action_url;
    if (typeof target === 'string' && target.startsWith('/')) {
      setOpen(false);
      navigate(target);
    }
  };

  const panel = open && typeof document !== 'undefined' ? createPortal(
    <div
      ref={panelRef}
      style={anchor}
      className="fixed z-[300] max-h-[75vh] flex flex-col bg-card rounded-2xl border border-border shadow-card animate-fade-in"
    >
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
            const target = n.action_url || n.metadata?.action_url || n.data?.action_url;
            const goesSomewhere = typeof target === 'string' && target.startsWith('/');
            return (
              <button
                key={n.id}
                onClick={() => openNotification(n)}
                className={`w-full text-left px-4 py-3 border-b border-border last:border-0 hover:bg-secondary/50 transition-colors ${isRead ? '' : 'bg-primary/5'}`}
              >
                <div className="flex items-start gap-2.5">
                  {!isRead && <span className="w-2 h-2 rounded-full bg-primary shrink-0 mt-1.5" />}
                  <div className="flex-1 min-w-0">
                    <div className="text-sm font-semibold text-foreground">{n.title || 'Notification'}</div>
                    {n.body && <div className="text-xs text-muted-foreground mt-0.5 line-clamp-2">{n.body}</div>}
                    <div className="text-[10px] text-muted-foreground mt-1 flex items-center gap-1.5">
                      <span>{n.created_at ? new Date(n.created_at).toLocaleString() : ''}</span>
                      {goesSomewhere && <span className="font-bold text-primary">Open ›</span>}
                    </div>
                  </div>
                  {!isRead && <Check className="w-3.5 h-3.5 text-primary/60 shrink-0 mt-1" />}
                </div>
              </button>
            );
          })
        )}
      </div>
    </div>,
    document.body,
  ) : null;

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
      {panel}
    </div>
  );
}
