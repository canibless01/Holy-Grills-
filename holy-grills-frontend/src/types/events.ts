/**
 * Events contract — /api/events/* (events.py).
 * Public reads return bare arrays/objects; admin writes return the row.
 */
import type { IsoDate, IsoDateTime, MutationResult, Uuid } from './common';
import type { PaymentMethod } from './orders';

/** catering_status enum. */
export type CateringStatus = 'pending' | 'reviewed' | 'confirmed' | 'rejected';

/** events row. */
export interface Event {
  id: Uuid;
  title: string;
  description?: string | null;
  event_date: IsoDateTime;
  location?: string | null;
  capacity?: number | null;
  hp_reward?: number | null;
  image_url?: string | null;
  assigned_to?: Uuid | null;
  is_active?: boolean;
  registrations?: number;
  [key: string]: unknown;
}

/** GET /api/events/:id/tiers + /tiers/comparison. */
export interface EventTier {
  id: Uuid;
  event_id?: Uuid;
  name: string;
  description?: string | null;
  price: number;
  hp_price?: number | null;
  capacity?: number | null;
  perks?: string[];
  [key: string]: unknown;
}

/** GET /api/events/tiers/:tier_id/detail. */
export interface EventTierDetail extends EventTier {
  event?: Event | null;
  sold?: number;
}

/** POST /api/events/:id/register response. */
export interface EventRegistration extends MutationResult {
  ticket_id?: Uuid;
  event_id?: Uuid;
  registered_at?: IsoDateTime;
  ticket?: { id: Uuid; qr_token?: string } | null;
}

/** POST /api/events/:id/checkin request body. */
export interface EventCheckinPayload {
  qr_token: string;
}

/** POST /api/events/catering-requests request body (public). */
export interface CateringRequestPayload {
  organizer_name: string;
  email: string;
  phone: string;
  event_name: string;
  event_date: IsoDate;
  expected_guests: number;
  budget?: number;
  notes?: string;
}

/** catering_requests row (admin list). */
export interface CateringRequest extends CateringRequestPayload {
  id: Uuid;
  status?: CateringStatus;
  created_at?: IsoDateTime;
  [key: string]: unknown;
}

/** Admin: POST /api/events payload. */
export interface CreateEventPayload {
  title: string;
  event_date: IsoDateTime;
  description?: string;
  location?: string;
  capacity?: number;
  hp_reward?: number;
  image_url?: string;
  assigned_to?: Uuid;
}

export type UpdateEventPayload = Partial<CreateEventPayload>;

/**
 * POST /api/events/:id/register request body (events.py:520+).
 * All fields optional: tier/promo/guest/answers only when the event uses them,
 * payment fields only for paid non-guest registration.
 */
export interface RegisterEventPayload {
  callback_url?: string;
  tier_id?: Uuid;
  promo_code?: string;
  registration_answers?: Record<string, unknown>;
  guest_name?: string;
  guest_email?: string;
  guest_phone?: string;
  payment_method?: PaymentMethod;
  use_hp?: boolean;
  wallet_amount?: number;
  [key: string]: unknown;
}

/** Admin: PATCH /api/events/catering-requests/:id. */
export interface UpdateCateringRequestPayload {
  status?: CateringStatus;
  notes?: string;
  [key: string]: unknown;
}

/** Admin: POST /api/events/:id/image. */
export interface EventImagePayload {
  image_url: string;
}

/** Admin: POST /api/events/:id/send-registrants-to-host. */
export interface SendRegistrantsPayload {
  email?: string;
  [key: string]: unknown;
}

/** GET /api/events/my-tickets. */
export interface MyTicket {
  id: Uuid;
  event_id?: Uuid;
  event?: Event | null;
  tier?: EventTier | null;
  registered_at?: IsoDateTime;
  status?: string;
  [key: string]: unknown;
}
