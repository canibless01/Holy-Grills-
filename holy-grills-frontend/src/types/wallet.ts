/**
 * Wallet contract — /api/wallet/* (wallet.py).
 * Withdrawal has been removed platform-wide (API_FIELD_REFERENCE.md).
 */
import type { IsoDateTime, MutationResult, Naira, Uuid } from './common';
import type { VirtualAccount } from './auth';

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
