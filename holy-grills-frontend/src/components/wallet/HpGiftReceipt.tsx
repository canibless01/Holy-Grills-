import { useEffect, useState } from 'react';
import { apiClient } from '@/lib/apiClient';
import { Modal } from '@/components/admin/ui/AdminKit';
import { GiftContact } from './GiftOptions';
import { msg } from '@/lib/messages';

export default function HpGiftReceipt({ id, onClose }) {
  const [receipt, setReceipt] = useState<any>(null);
  const [error, setError] = useState('');
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    let active = true; setError('');
    apiClient.get(`/hp/transfers/${encodeURIComponent(id)}`).then(data => { if (active) setReceipt(data.transfer); })
      .catch(failure => { if (active) setError(failure.message); });
    return () => { active = false; };
  }, [id, retry]);
  return <Modal open title={msg('FE_GIFT_HP_RECEIPT', 'Your HP gift')} onClose={onClose}><div className="space-y-4">
    {error ? <><p role="alert" className="text-sm text-destructive">{error}</p><button onClick={() => setRetry(value => value + 1)} className="font-bold text-primary">{msg('FE_GIFT_RETRY', 'Retry')}</button></> : !receipt ? <p role="status">{msg('FE_GIFT_LOADING_RECEIPT', 'Opening your gift…')}</p> : <>
      <p className="text-3xl font-extrabold">{receipt.amount} HP</p><p>{receipt.direction === 'received' ? msg('FE_GIFT_FROM', 'From {name}', { name: receipt.sender_name || 'Anonymous' }) : msg('FE_GIFT_TO', 'To {name}', { name: receipt.recipient_name })}</p>
      {receipt.note && <p className="whitespace-pre-wrap rounded-xl bg-background p-3 text-sm">{receipt.note}</p>}<GiftContact contact={receipt.shared_contact} />
      <p className="break-all text-xs text-muted-foreground">{receipt.id}</p>
    </>}
  </div></Modal>;
}
