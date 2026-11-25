import { msg } from './messages';

export const passDate = (value: string) => {
  const date = new Date(value);
  return Number.isFinite(date.getTime()) ? `${date.toLocaleString('en-NG', { timeZone: 'Africa/Lagos', dateStyle: 'medium', timeStyle: 'short' })} WAT` : '—';
};

export const passStatus = (state: string) => {
  switch (state) {
    case 'paid': return msg('FE_PASS_STATUS_PAID', 'Paid');
    case 'credited': return msg('FE_PASS_STATUS_CREDITED', 'In wallet');
    case 'refunded': return msg('FE_PASS_STATUS_REFUNDED', 'Refunded');
    case 'cancelled': return msg('FE_PASS_STATUS_CANCELLED', 'Cancelled');
    case 'failed': return msg('FE_PASS_STATUS_FAILED', 'Payment failed');
    default: return msg('FE_PASS_PENDING', 'Payment awaiting confirmation');
  }
};
