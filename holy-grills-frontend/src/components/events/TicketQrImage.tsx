import { useEffect, useState } from 'react';
import { liveApi } from '@/lib/liveApi';
import { msg } from '@/lib/messages';

export default function TicketQrImage({ eventId, ticketId, guestEmail }: { eventId: string; ticketId: string; guestEmail?: string }) {
  const [image, setImage] = useState('');
  const [error, setError] = useState('');
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    let active = true;
    setImage(''); setError('');
    liveApi.events.ticketQr(eventId, ticketId, guestEmail).then(result => {
      if (typeof result?.qr_image !== 'string' || !result.qr_image.startsWith('data:image/png;base64,')) throw new Error(msg('FE_EVENT_QR_UNAVAILABLE', 'Your ticket QR could not be loaded. Try again.'));
      if (active) setImage(result.qr_image);
    }).catch(err => { if (active) setError(err.message); });
    return () => { active = false; };
  }, [eventId, ticketId, guestEmail, retry]);
  if (error) return <div role="alert" className="space-y-2 text-xs text-destructive"><p>{error}</p><button type="button" onClick={() => setRetry(value => value + 1)} className="rounded-full border border-border px-4 py-2 font-bold">{msg('FE_EVENT_RETRY_QR', 'Retry ticket QR')}</button></div>;
  if (!image) return <p role="status" className="py-8 text-xs text-muted-foreground">{msg('FE_EVENT_LOADING_QR', 'Loading your ticket QR…')}</p>;
  return <img onError={() => setError(msg('FE_EVENT_QR_UNAVAILABLE', 'Your ticket QR could not be loaded. Try again.'))} src={image} alt={msg('FE_EVENT_CUSTOMER_QR', 'Your event ticket QR code')} className="mx-auto h-48 w-48 rounded-xl bg-white p-2 object-contain" />;
}
