import { useEffect, useState } from 'react';
import { apiClient } from '@/lib/apiClient';
import { msg } from '@/lib/messages';

export default function BirthdayGiftPanel({ code, cashEnabled, hpEnabled, onCash, onHp }) {
  const [recipient, setRecipient] = useState<any>(null);
  const [error, setError] = useState('');
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    let active = true; setRecipient(null); setError('');
    apiClient.get('/hp/birthday-recipient', { code }).then(data => { if (active) setRecipient(data.recipient); })
      .catch(failure => { if (active) setError(failure.message); });
    return () => { active = false; };
  }, [code, retry]);
  return <section className="rounded-2xl border border-primary/25 bg-primary/5 p-5">
    <h2 className="font-heading text-lg font-bold">{msg('FE_GIFT_BIRTHDAY_HEADING', 'A little birthday love')}</h2>
    {error ? <><p role="alert" className="mt-2 text-sm">{error}</p><button type="button" onClick={() => setRetry(value => value + 1)} className="mt-2 font-bold text-primary">{msg('FE_GIFT_RETRY', 'Retry')}</button></> : !recipient ? <p role="status" className="mt-2 text-sm">{msg('FE_GIFT_LOADING_FRIEND', 'Finding your campus friend…')}</p> : <>
      <p className="mt-2 text-sm">{msg('FE_GIFT_BIRTHDAY_PERSON', 'It’s {name}’s birthday. Send a little wallet money or Holy Points, with a message from you.', { name: recipient.name })}</p>
      <div className="mt-4 grid grid-cols-2 gap-3"><button type="button" disabled={!cashEnabled} onClick={() => onCash(recipient)} className="rounded-xl bg-gradient-cta p-3 text-sm font-bold text-white disabled:opacity-50">{msg('FE_GIFT_SEND_CASH', 'Send wallet money')}</button><button type="button" disabled={!hpEnabled} onClick={() => onHp(recipient)} className="rounded-xl border border-primary p-3 text-sm font-bold text-primary disabled:opacity-50">{msg('FE_GIFT_SEND_HP', 'Send HP')}</button></div>
      {!hpEnabled && <p className="mt-2 text-xs text-muted-foreground">{msg('FE_GIFT_HP_LOCKED', 'HP gifts follow your account’s transfer eligibility. You can still choose wallet money when it is available.')}</p>}
    </>}
  </section>;
}
