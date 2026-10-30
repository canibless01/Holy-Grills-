/**
 * Order-lock contract — /api/order-locks (order_locks.py).
 * A lock reserves a future order date and its discount.
 */
import type { IsoDate, MutationResult, Uuid } from './common';

/** lock_status enum. */
export type OrderLockStatus = 'active' | 'cancelled' | 'used';

export interface OrderLock {
  id: Uuid;
  user_id?: Uuid;
  locked_date: IsoDate;
  discount_pct: number;
  status: OrderLockStatus;
  reschedule_count?: number;
  created_at?: string;
  [key: string]: unknown;
}

/** POST /api/order-locks request body. */
export interface CreateOrderLockPayload {
  locked_date: IsoDate;
  discount_pct?: number;
  [key: string]: unknown;
}

/** PATCH /api/order-locks/:id/reschedule request body. */
export interface RescheduleOrderLockPayload {
  locked_date: IsoDate;
}

/** GET /api/order-locks → { locks, count }. */
export interface OrderLocksResponse {
  locks: OrderLock[];
  count?: number;
}

/** POST /api/order-locks → { message, lock }. */
export interface OrderLockResponse extends MutationResult {
  lock: OrderLock;
}
