import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import { CheckCheck, Settings, ArrowLeft } from 'lucide-react';
import { useHolyGrill } from '@/lib/HolyGrillContext';
import NotificationItem from '@/components/notifications/NotificationItem';
import NotificationsSkeleton from '@/components/skeletons/NotificationsSkeleton';
import MascotStandee from '@/components/mascot/MascotStandee';

export default function Notifications() {
  const navigate = useNavigate();
  const { notifications, unreadCount, markNotificationRead, markAllNotificationsRead, refreshNotifications } = useHolyGrill();
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    refreshNotifications().then(() => setLoading(false));
  }, [refreshNotifications]);

  const handleClick = async (notif) => {
    const isRead = !!(notif.read_at || notif.is_read);
    if (!isRead) await markNotificationRead(notif.id);
    const target = notif.action_url || (notif.metadata && notif.metadata.action_url);
    if (target && target.startsWith('/')) navigate(target);
  };

  return (
    <div className="space-y-4 animate-fade-in max-w-xl mx-auto">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <button
            onClick={() => navigate(-1)}
            className="p-2 -ml-2 rounded-full hover:bg-secondary active:scale-95 transition"
            aria-label="Back"
          >
            <ArrowLeft className="w-5 h-5 text-foreground" />
          </button>
          <div className="flex items-center gap-2">
            <h1 className="font-heading font-extrabold text-2xl text-foreground">Notifications</h1>
            {unreadCount > 0 && (
              <span className="min-w-5 h-5 px-1.5 rounded-full bg-primary text-white text-[10px] font-extrabold flex items-center justify-center">
                {unreadCount}
              </span>
            )}
          </div>
        </div>
        <div className="flex gap-1.5">
          {unreadCount > 0 && (
            <button
              onClick={markAllNotificationsRead}
              className="flex items-center gap-1.5 px-3 py-2 rounded-full bg-gradient-cta text-white text-xs font-bold active:scale-95 transition"
            >
              <CheckCheck className="w-3.5 h-3.5" /> Mark all
            </button>
          )}
          <button
            onClick={() => navigate('/notification-preferences')}
            className="p-2 rounded-full bg-card border border-border active:scale-95 transition"
            aria-label="Notification settings"
          >
            <Settings className="w-4 h-4 text-muted-foreground" />
          </button>
        </div>
      </div>

      {loading ? (
        <NotificationsSkeleton />
      ) : notifications.length === 0 ? (
        <motion.div
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          className="rounded-2xl border border-dashed border-border p-8 text-center"
        >
          <MascotStandee mascot="peace" className="w-28 h-28 mx-auto mb-1" alt="No notifications" />
          <p className="font-bold text-foreground">All caught up.</p>
          <p className="text-[11px] text-muted-foreground mt-0.5">
            New notifications will show up here in real time.
          </p>
        </motion.div>
      ) : (
        <div className="space-y-2">
          {notifications.map((notif) => (
            <NotificationItem key={notif.id} notif={notif} onClick={handleClick} />
          ))}
        </div>
      )}
    </div>
  );
}