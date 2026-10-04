import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Bell } from 'lucide-react';
import { liveApi } from '@/lib/liveApi';

/**
 * NotificationBell — tapping the bell opens the full /notifications page,
 * exactly like the student panel. Works for every role (student, kitchen,
 * rider, admin): they all read the same unified /notifications endpoint.
 * Polls the unread count so the badge stays live.
 */
export default function NotificationBell() {
  const navigate = useNavigate();
  const [unread, setUnread] = useState(0);

  useEffect(() => {
    const load = async () => {
      try {
        const res = await liveApi.notifications.list({ limit: 30 });
        const list = Array.isArray(res) ? res : (res?.notifications || res?.items || res?.data || []);
        const flagged = list.filter((n) => !(n.read_at || n.is_read)).length;
        // The backend returns a global unread count (all unread, not just this page).
        setUnread(res?.unread_count ?? res?.unread ?? flagged);
      } catch { /* not signed in — badge simply stays at 0 */ }
    };
    load();
    const timer = setInterval(load, 60000);
    return () => clearInterval(timer);
  }, []);

  return (
    <button
      type="button"
      onClick={() => navigate('/notifications')}
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
  );
}