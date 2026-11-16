/**
 * Wallet contract — /api/wallet/* (wallet.py).
 * Withdrawal has been removed platform-wide (API_FIELD_REFERENCE.md).
 */
import type { IsoDateTime, MutationResult, Naira, Uuid } from './common';
import type { VirtualAccount } from './auth';

export interface AutoFundingAttempt {
  id: string;
  cycle: number;
  reference: string;
  state: 'setup' | 'handed_off' | 'succeeded' | 'failed';
  scheduled_for: string;
  updated_at: string;
}

export interface AutoFundingPlan {
  id: string;
  amount_kobo: number;
  interval_days: number;
  stop_after: number | null;
  end_at: string | null;
  state: 'draft' | 'active' | 'attention' | 'stopped' | 'completed';
  successful_payments: number;
  total_credited_kobo: number;
  next_due_at: string | null;
  card_label?: string | null;
  setup_reference: string;
  checkout_url?: string | null;
  in_flight?: boolean;
  last_issue?: 'setup_unavailable' | 'payment_uncertain' | 'payment_failed' | 'card_not_reusable' | 'account_or_card_changed' | null;
  created_at?: string;
  stopped_at?: string | null;
  attempts?: AutoFundingAttempt[];
}

export interface AutoFundingLimits {
  enabled?: boolean;
  minimum_amount: number;
  maximum_amount: number;
  maximum_interval_days: number;
  fee_payer: 'customer';
  consent_version: string;
}

/** GET /api/wallet. */
export interface Wallet {
  balance: Naira;
  virtual_account?: VirtualAccount | null;
  has_virtual_account?: boolean;
  [key: string]: unknown;
}

/** wallet_transactions row (GET /api/wallet/transactions). */
export interface WalletTransaction {
  id: Uuid;
  amount: number;
  type: string;
  status?: string;
  reference?: string | null;
  description?: string | null;
  created_at?: IsoDateTime;
  [key: string]: unknown;
}

export interface WalletTransactionsParams {
  page?: number;
  per_page?: number;
  [key: string]: unknown;
}

/** POST /api/wallet/fund/card request body. */
export interface FundWalletCardPayload {
  amount: number;
  callback_url?: string;
}

/** POST /api/wallet/fund/card response (Paystack checkout). */
export interface FundWalletCardResult extends MutationResult {
  authorization_url: string;
  access_code?: string;
  reference: string;
}

/** POST /api/wallet/fund/bank response — virtual account for transfers. */
export interface FundWalletBankResult extends MutationResult {
  virtual_account?: VirtualAccount | null;
}
