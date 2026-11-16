/** Ledger amounts may be positive for both directions; type is authoritative. */
export function transactionIsCredit(tx: Record<string, any>, kind: 'cash' | 'hp'): boolean {
  const amount = Number(tx.amount ?? tx.hp_amount ?? tx.points ?? 0);
  if (amount < 0) return false;
  const type = String(tx.type || '').toLowerCase();
  if (['debit', 'spend', 'redeem', 'redemption', 'expire', 'expired', 'transfer_out', 'withdrawal', 'order_payment'].includes(type)) return false;
  if (['credit', 'earn', 'refund', 'transfer_in', 'topup', 'bank_transfer'].includes(type)) return true;
  const source = String(tx.source || tx.reference_type || '').toLowerCase();
  if (/(?:^|_)(?:received|recipient|incoming|in)$/.test(source)) return true;
  if (/(?:^|_)(?:sent|outgoing|out)$/.test(source)) return false;
  if (['order', 'order_payment', 'marketplace_purchase', 'redemption', 'redeem', 'spend', 'expire', 'expired', 'hp_decay', 'hp_decay_applied', 'withdrawal'].includes(source)) return false;
  // A generic transfer does not establish direction; signed legacy amounts do.
  return kind === 'hp' ? amount >= 0 : amount > 0;
}
