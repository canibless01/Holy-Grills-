/**
 * Notifications & push contract — /api/notifications/*, /api/push/subscribe
 * (notifications.py).
 */
import type { IsoDateTime, MutationResult, Uuid } from './common';

/** notification_channel enum. */
export type NotificationChannel = 'push' | 'in_app' | 'email';

/** notifications row. */
export interface AppNotification {
  id: Uuid;
  type: string;
  channel?: NotificationChannel;
  title: string;
  body: string;
  is_read: boolean;
  action_url?: string | null;
  metadata?: {
    reference_id?: Uuid;
    reference_type?: string;
    /** 'high' = time-sensitive (only set for order_delivery_attempted). */
    urgency?: 'high' | null;
    [key: string]: unknown;
  } | null;
  created_at?: IsoDateTime;
  [key: string]: unknown;
}

/** GET /api/notifications query parameters. */
export interface NotificationsParams {
  unread_only?: boolean;
  page?: number;
  per_page?: number;
  [key: string]: unknown;
}

/** GET /api/notifications — bare array or { notifications, unread_count }. */
export interface NotificationsResponse {
  notifications: AppNotification[];
  unread_count?: number;
  count?: number;
}

/** User notification preferences (GET/PATCH /api/notifications/preferences). */
export interface NotificationPreferences {
  push_enabled?: boolean;
  email_notifications?: boolean;
  order_updates?: boolean;
  promotions?: boolean;
  [key: string]: unknown;
}

export type UpdateNotificationPreferencesPayload = Partial<NotificationPreferences>;

/** POST /api/push/subscribe + DELETE /api/push/subscribe. */
export interface PushSubscribePayload {
  token?: string;
  endpoint?: string;
  keys?: { p256dh?: string; auth?: string };
  platform?: 'ios' | 'android' | 'web';
  user_agent?: string;
  [key: string]: unknown;
}

/** POST /api/notifications/blast request body (admin). */
export interface NotificationBlastPayload {
  title: string;
  body: string;
  channels: string[];
  /** Segment filters — `all` means no filtering. */
  target_segment?: Record<string, unknown>;
  /** Legacy alias kept for backward compatibility (AdminNotifications). */
  segment?: Record<string, unknown>;
  email_provider?: string;
  notify_new_matches_only?: boolean;
  /** When omitted the blast sends immediately. */
  send_at?: string;
  [key: string]: unknown;
}

export type NotificationMutation = MutationResult;
