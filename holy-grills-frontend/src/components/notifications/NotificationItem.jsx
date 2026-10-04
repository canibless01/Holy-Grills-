import React from 'react';
import { motion } from 'framer-motion';
import { timeAgo, NOTIFICATION_ICONS } from '@/lib/hgUtils';

// One notification row. `read_at` / `is_read` both checked for read state.
// A tap marks it read (handled by parent) and navigates to action_url if present.
export default function NotificationItem({ notif, onClick }) {
  const isRead = !!(notif.read_at || notif.is_read);
  const icon = NOTIFICATION_ICONS[notif.type] || '🔔';

  return (
    <motion.button
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      onClick={() => onClick(notif)}
      className={`w-full text-left rounded-2xl border p-3.5 transition-all active:scale-[0.99] ${
        isRead
          ? 'bg-card border-border'
          : 'bg-primary/[0.04] border-primary/25'
      }`}
    >
      <div className="flex items-start gap-3">
        <div className={`w-10 h-10 rounded-xl flex items-center justify-center flex-shrink-0 text-lg ${
          isRead ? 'bg-secondary' : 'bg-primary/10'
        }`}>
          {icon}
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center justify-between gap-2">
            <h3 className="font-bold text-sm text-foreground truncate">{notif.title}</h3>
            <span className="text-[10px] text-muted-foreground flex-shrink-0">
              {timeAgo(notif.created_at)}
            </span>
          </div>
          <p className="text-xs text-muted-foreground mt-0.5 line-clamp-2">{notif.body}</p>
        </div>
        {!isRead && (
          <span className="w-2.5 h-2.5 rounded-full bg-primary flex-shrink-0 mt-2 ring-2 ring-primary/20" />
        )}
      </div>
    </motion.button>
  );
}