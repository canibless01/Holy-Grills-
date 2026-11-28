import { useRef, useState } from 'react';
import { Mail } from 'lucide-react';
import { apiClient } from '@/lib/apiClient';
import { msg } from '@/lib/messages';

export default function TicketResendButton({eventId,ticketId,guestEmail,accessToken}:{eventId:string;ticketId:string;guestEmail?:string;accessToken?:string}) {
  const [busy,setBusy]=useState(false);
  const [notice,setNotice]=useState('');
  const [error,setError]=useState('');
  const intent=useRef<string>();
  const lock=useRef(false);
  const resend=async()=>{
    if(lock.current)return;
    lock.current=true;setBusy(true);setError('');setNotice('');
    intent.current ||= crypto.randomUUID();
    try {
      await apiClient.post(`/events/${eventId}/tickets/${ticketId}/resend`,{request_id:intent.current,...(guestEmail?{guest_email:guestEmail}:{}),...(accessToken?{access_token:accessToken}:{})});
      setNotice(msg('FE_EVENT_TICKET_RESEND_QUEUED','Ticket email requested. Check your inbox and spam folder.'));intent.current=undefined;
    } catch(e) {setError(e.message);} finally {lock.current=false;setBusy(false);}
  };
  return <div className="space-y-2"><button type="button" disabled={busy||!!notice} onClick={resend} className="inline-flex min-h-10 items-center justify-center gap-2 rounded-full border border-border px-4 py-2 text-xs font-bold disabled:opacity-50"><Mail className="h-4 w-4"/>{busy?msg('FE_EVENT_TICKET_RESEND_BUSY','Requesting ticket email…'):msg('FE_EVENT_TICKET_RESEND','Resend ticket email')}</button>{notice&&<p role="status" className="text-xs text-muted-foreground">{notice}</p>}{error&&<p role="alert" className="text-xs text-destructive">{error}</p>}</div>;
}
