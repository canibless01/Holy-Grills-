import { useEffect, useRef, useState } from 'react';
import { Clock } from 'lucide-react';
import { apiClient } from '@/lib/apiClient';
import { msg } from '@/lib/messages';

export function EventAdmissionOpening({event}:{event:any}) {
  const minutes=event.metadata?.checkin_minutes_before_start;
  if(!Number.isInteger(minutes)||minutes<0||minutes>10080)return null;
  const time=new Date(new Date(event.starts_at).getTime()-minutes*60000);
  if(!Number.isFinite(time.getTime()))return null;
  return <p className="text-xs leading-relaxed text-muted-foreground">{msg('FE_EVENT_ADMISSION_WINDOW_CURRENT','Opens: {time}',{time:time.toLocaleString('en-NG',{timeZone:'Africa/Lagos',dateStyle:'medium',timeStyle:'short'})+' WAT'})}</p>;
}

export default function EventAdmissionWindow({event,onSaved,disabled=false}:{event:any;onSaved:()=>void;disabled?:boolean}) {
  const saved=event.metadata?.checkin_minutes_before_start;
  const [enabled,setEnabled]=useState(saved!=null);
  const [minutes,setMinutes]=useState(String(saved??30));
  const [busy,setBusy]=useState(false);const [error,setError]=useState('');const [notice,setNotice]=useState('');const lock=useRef(false);
  useEffect(()=>{setEnabled(saved!=null);setMinutes(String(saved??30));},[saved]);
  const save=async(e:React.FormEvent)=>{e.preventDefault();if(lock.current)return;lock.current=true;setBusy(true);setError('');setNotice('');try{await apiClient.post(`/events/${event.id}/admission-window`,{minutes:enabled?Number(minutes):null});setNotice(msg('FE_EVENT_ADMISSION_WINDOW_SAVED','Check-in opening time saved.'));onSaved();}catch(err){setError(err.message);}finally{lock.current=false;setBusy(false);}};
  return <section aria-label={msg('FE_EVENT_ADMISSION_WINDOW','Check-in opening time')} className="space-y-3 rounded-2xl border border-border bg-card p-4 sm:p-5"><h3 className="flex items-center gap-2 font-heading font-extrabold"><Clock className="h-5 w-5 text-primary"/>{msg('FE_EVENT_ADMISSION_WINDOW','Check-in opening time')}</h3><p className="text-xs leading-relaxed text-muted-foreground">{msg('FE_EVENT_ADMISSION_WINDOW_HELP','Set when staff and venue QR check-in can begin. The opening time follows event rescheduling. Check-in closes when the event ends.')}</p>{saved!=null?<EventAdmissionOpening event={event}/>:<p className="text-xs text-muted-foreground">{msg('FE_EVENT_ADMISSION_WINDOW_UNRESTRICTED','No opening-time restriction is set.')}</p>}<form onSubmit={save} className="space-y-3"><fieldset disabled={disabled||busy||event.metadata?.lifecycle_status==='cancelled'} className="space-y-3 disabled:opacity-60"><label className="flex items-center gap-2 text-sm font-bold"><input type="checkbox" checked={enabled} onChange={e=>setEnabled(e.target.checked)}/>{msg('FE_EVENT_ADMISSION_WINDOW_ENABLE','Set an opening time')}</label>{enabled&&<label className="block space-y-1 text-xs font-bold">{msg('FE_EVENT_ADMISSION_WINDOW_MINUTES','Minutes before event start')}<input required type="number" min={0} max={10080} step={1} value={minutes} onChange={e=>setMinutes(e.target.value)} className="w-full rounded-xl border border-border bg-background p-3 text-sm"/></label>}<button type="submit" className="min-h-11 w-full rounded-full bg-gradient-cta px-4 py-3 text-sm font-bold text-white sm:w-auto">{busy?msg('FE_ORG_SAVING','Saving…'):msg('FE_EVENT_ADMISSION_WINDOW_SAVE','Save check-in opening time')}</button></fieldset></form>{error&&<p role="alert" className="text-sm text-destructive">{error}</p>}{notice&&<p role="status" className="text-sm text-success">{notice}</p>}</section>;
}
