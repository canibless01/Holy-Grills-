import { useEffect, useRef, useState } from 'react';
import { Link, Navigate, useSearchParams } from 'react-router-dom';
import { useHolyGrill } from '@/lib/HolyGrillContext';
import { useCampus } from '@/lib/campusContext';
import { isAuthenticated } from '@/lib/apiClient';
import { eventOrganizerApi as api } from '@/lib/eventOrganizerApi';
import { useCmsCreateIntent } from '@/lib/useCmsCreateIntent';
import { msg } from '@/lib/messages';
import { csvCell } from '@/lib/csvCell';
import PanelSwitcher from '@/components/PanelSwitcher';
import BrandLogo from '@/components/BrandLogo';
import InlineNotificationBell from '@/components/InlineNotificationBell';
import AdminCampusSelector from '@/components/admin/AdminCampusSelector';
import AdminUserPicker from '@/components/admin/AdminUserPicker';
import ImageUploader from '@/components/admin/ImageUploader';
import EventCheckInScanner from '@/components/EventCheckInScanner';
import { Modal, Field, TextInput } from '@/components/admin/AdminShared';
import { confirmAction } from '@/lib/confirmAction';

const emptyUsers = [];
const button = 'rounded-full bg-primary text-white px-4 py-2 text-sm font-bold disabled:opacity-50';
const secondary = 'rounded-full bg-secondary text-foreground px-4 py-2 text-sm font-bold disabled:opacity-50';
const card = 'rounded-2xl bg-card border border-border p-4 space-y-3';
const money = (value) => `₦${Number(value || 0).toLocaleString('en-NG', {minimumFractionDigits:2,maximumFractionDigits:2})}`;
const wat = value => value ? new Date(new Date(value).getTime()+3600000).toISOString().slice(0,16) : '';
const blank = {title:'',description:'',location:'',starts_at:'',ends_at:'',capacity:100,image_url:''};
const statusLabel = value => ({draft:msg('FE_ORG_DRAFT','Draft'),submitted:msg('FE_ORG_SUBMITTED','Awaiting review'),approved:msg('FE_ORG_APPROVED','Approved'),changes_requested:msg('FE_ORG_CHANGES','Changes requested'),pending:msg('FE_ORG_PENDING','Pending approval'),paid:msg('FE_ORG_PAID','Paid'),rejected:msg('FE_ORG_REJECTED','Rejected'),cancelled:msg('FE_ORG_CANCELLED','Cancelled')})[value] || value;

export default function EventManager() {
  const {user,isLoading}=useHolyGrill();const {adminCampusId}=useCampus();
  if (!isAuthenticated()) return <Navigate to="/login" replace state={{from:'/event-manager'}} />;
  if (isLoading || !user) return <p role="status" className="p-8">{msg('FE_ORG_LOADING','Loading event workspace…')}</p>;
  if (!['event_organizer','admin','super_admin'].includes(user.role)) return <main className="p-8"><p>{msg('FE_ORG_ACCESS','This workspace is for approved event organizers and administrators.')}</p><Link to="/">{msg('FE_PANEL_STUDENT','View student page')}</Link></main>;
  return <Workspace key={`${user.id}:${adminCampusId || ''}`} admin={user.role!=='event_organizer'} />;
}

function Workspace({admin}) {
  const {logout}=useHolyGrill();const {adminCampusId}=useCampus();const [params,setParams]=useSearchParams();
  const [events,setEvents]=useState([]);const [offset,setOffset]=useState(0);const [hasMore,setHasMore]=useState(false);const [loading,setLoading]=useState(true);const [error,setError]=useState('');const [revision,setRevision]=useState(0);const [editor,setEditor]=useState<any>(null);
  const selected=params.get('event') || events[0]?.id;const version=useRef(0);
  useEffect(()=>{const current=++version.current;setLoading(true);setError('');api.list({limit:25,offset,...(admin && adminCampusId ? {campus_id:adminCampusId}:{})}).then(result=>{if(current===version.current){setEvents(result.events||[]);setHasMore(!!result.has_more);}}).catch(e=>{if(current===version.current)setError(e.message);}).finally(()=>{if(current===version.current)setLoading(false);});return()=>{version.current++;};},[offset,revision,admin,adminCampusId]);
  const refresh=()=>setRevision(value=>value+1);
  return <main className="min-h-screen bg-background text-foreground pb-12">
    <header className="sticky top-0 z-30 bg-card border-b border-border p-3 flex items-center gap-3 flex-wrap">
      <BrandLogo size="admin" /><h1 className="font-heading font-extrabold flex-1">{msg('FE_ORG_TITLE','Event workspace')}</h1>
      {admin && <><AdminCampusSelector /><Link className={secondary} to="/admin?section=events">{msg('FE_ORG_ADMIN','Event administration')}</Link></>}
      <InlineNotificationBell /><PanelSwitcher className={secondary} labelClassName="text-xs" />
      <button className={secondary} onClick={()=>void logout()}>{msg('FE_ORG_SIGN_OUT','Sign out')}</button>
    </header>
    <div className="max-w-7xl mx-auto p-4 grid lg:grid-cols-[280px_1fr] gap-5">
      <aside className="space-y-3">
        <button className={`${button} w-full`} onClick={()=>setEditor({...blank})}>{msg('FE_ORG_CREATE','Create event draft')}</button>
        {error && <div role="alert" className={card}><p>{error}</p><button onClick={refresh}>{msg('FE_PLATFORM_RETRY','Retry')}</button></div>}
        {loading ? <p role="status">{msg('FE_ORG_LOADING','Loading event workspace…')}</p> : !error && events.length===0 ? <p>{msg('FE_ORG_EMPTY','No events in this workspace yet.')}</p> : events.map(event=><button key={event.id} onClick={()=>setParams({event:event.id})} className={`${card} text-left w-full ${selected===event.id?'border-primary ring-1 ring-primary':''}`}><strong className="block">{event.title}</strong><span className="text-xs text-muted-foreground">{statusLabel(event.review_status)} · {event.is_published?msg('FE_ORG_LIVE','Published'):msg('FE_ORG_HIDDEN','Not published')}</span></button>)}
        <div className="flex gap-3 justify-between"><button className={secondary} disabled={offset===0 || loading} onClick={()=>setOffset(value=>Math.max(0,value-25))}>{msg('FE_ORG_PREVIOUS','Previous')}</button><button className={secondary} disabled={!hasMore || loading} onClick={()=>setOffset(value=>value+25)}>{msg('FE_ORG_NEXT','Next')}</button></div>
      </aside>
      <section>{selected && <EventAccount key={selected} id={selected} admin={admin} externalRevision={revision} onEdit={event=>setEditor({...event,starts_at:wat(event.starts_at),ends_at:wat(event.ends_at)})} onChange={refresh} />}</section>
    </div>
    {editor && <DraftEditor initial={editor} onClose={()=>setEditor(null)} onSaved={event=>{setEditor(null);setParams({event:event.id});refresh();}} />}
  </main>;
}

function DraftEditor({initial,onClose,onSaved}) {
  const [form,setForm]=useState(initial);const [busy,setBusy]=useState(false);const [error,setError]=useState('');const lock=useRef(false);const intent=useCmsCreateIntent();
  const save=async(event)=>{event.preventDefault();if(lock.current)return;lock.current=true;setBusy(true);setError('');
    const body={title:form.title,description:form.description||'',location:form.location,starts_at:form.starts_at,ends_at:form.ends_at,capacity:Number(form.capacity),image_url:form.image_url||''};
    try{const result=initial.id?await api.edit(initial.id,body):await api.create(intent.body(body));intent.clear();onSaved(result);}catch(e){setError(e.message);}finally{lock.current=false;setBusy(false);}};
  return <Modal open title={msg('FE_ORG_DRAFT_EDITOR','Event draft')} onClose={()=>{if(!busy)onClose();}}><form onSubmit={save} className="space-y-3"><fieldset disabled={busy} className="space-y-3">
    <p className="text-sm text-muted-foreground">{msg('FE_ORG_REVIEW_HELP','Submit your event for review. Holy Grills finalizes ticket prices, organizer amounts and HP rewards before publication.')}</p>
    <Field label={msg('FE_ORG_EVENT_TITLE','Event title')}><TextInput required maxLength={200} value={form.title} onChange={e=>setForm({...form,title:e.target.value})}/></Field>
    <Field label={msg('FE_ORG_DESCRIPTION','Description')}><textarea maxLength={5000} value={form.description||''} onChange={e=>setForm({...form,description:e.target.value})} className="w-full rounded-xl border border-border p-3"/></Field>
    <Field label={msg('FE_ORG_LOCATION','Venue / location')}><TextInput required maxLength={500} value={form.location} onChange={e=>setForm({...form,location:e.target.value})}/></Field>
    <div className="grid sm:grid-cols-2 gap-3"><Field label={msg('FE_EVENT_START_WAT','Starts (WAT)')}><TextInput required type="datetime-local" value={form.starts_at} onChange={e=>setForm({...form,starts_at:e.target.value})}/></Field><Field label={msg('FE_EVENT_END_WAT','Ends (WAT)')}><TextInput required type="datetime-local" value={form.ends_at} onChange={e=>setForm({...form,ends_at:e.target.value})}/></Field></div>
    <Field label={msg('FE_ORG_CAPACITY','Capacity')}><TextInput required min={1} max={1000000} type="number" value={form.capacity} onChange={e=>setForm({...form,capacity:e.target.value})}/></Field>
    <ImageUploader value={form.image_url||''} onChange={url=>setForm({...form,image_url:url})} folder="events" />
    {error && <p role="alert" className="text-destructive">{error}</p>}<button className={button} type="submit">{busy?msg('FE_ORG_SAVING','Saving…'):msg('FE_ORG_SAVE_DRAFT','Save draft')}</button>
  </fieldset></form></Modal>;
}

function EventAccount({id,admin,externalRevision,onEdit,onChange}) {
  const [account,setAccount]=useState<any>(null);const [error,setError]=useState('');const [loading,setLoading]=useState(true);const [revision,setRevision]=useState(0);const [busy,setBusy]=useState(false);const [message,setMessage]=useState('');const [scanner,setScanner]=useState(false);const [doorQr,setDoorQr]=useState<any>(null);
  const lock=useRef(false);const alive=useRef(true);const version=useRef(0);
  useEffect(()=>{alive.current=true;return()=>{alive.current=false;version.current++;};},[]);
  const reload=()=>setRevision(value=>value+1);
  useEffect(()=>{const current=++version.current;setLoading(true);setError('');api.account(id).then(result=>{if(current===version.current)setAccount(result);}).catch(e=>{if(current===version.current)setError(e.message);}).finally(()=>{if(current===version.current)setLoading(false);});return()=>{version.current++;};},[id,revision,externalRevision]);
  const run=async(task,success?)=>{if(lock.current)return;lock.current=true;setBusy(true);setError('');setMessage('');try{const result=await task();if(alive.current){setMessage(success?success(result):msg('FE_ORG_SAVED','Saved.'));reload();onChange();}}catch(e){if(alive.current)setError(e.message);}finally{lock.current=false;if(alive.current)setBusy(false);}};
  if(loading && !account)return <p role="status">{msg('FE_ORG_LOADING','Loading event workspace…')}</p>;
  if(!account)return <div role="alert" className={card}><p>{error}</p><button onClick={reload}>{msg('FE_PLATFORM_RETRY','Retry')}</button></div>;
  const event=account.event;const canEdit=['draft','changes_requested'].includes(event.review_status);
  const admit=token=>run(()=>api.checkin(id,token),result=>result.replayed?msg('FE_EVENT_ALREADY_ADMITTED','This ticket was already checked in. No additional HP was awarded.'):msg('FE_EVENT_ADMITTED','Check-in recorded. Attendee HP: {hp}.',{hp:result.hp_added_to_active||0}));
  return <div className="space-y-4">
    <div className={card}><div className="flex justify-between items-start gap-3 flex-wrap"><div><h2 className="font-heading font-extrabold text-xl">{event.title}</h2><p className="text-sm text-muted-foreground">{statusLabel(event.review_status)}</p></div><button className={secondary} onClick={reload} disabled={busy}>{msg('FE_ORG_REFRESH','Refresh')}</button></div>
      {event.review_notes && <p className="rounded-xl bg-secondary p-3 text-sm">{event.review_notes}</p>}
      {error && <div role="alert" className="text-destructive"><p>{error}</p><button onClick={reload}>{msg('FE_PLATFORM_RETRY','Retry')}</button></div>}{message && <p role="status">{message}</p>}
      <div className="flex gap-2 flex-wrap">{canEdit && <><button className={secondary} disabled={busy} onClick={()=>onEdit(event)}>{msg('FE_ORG_EDIT_DRAFT','Edit draft')}</button><button className={button} disabled={busy} onClick={()=>void run(()=>api.submit(id))}>{msg('FE_ORG_SUBMIT','Submit for approval')}</button></>}{event.review_status==='approved' && <button className={secondary} disabled={busy || loading} onClick={async()=>{if(await confirmAction({title:msg('FE_EVENT_QR_ROTATE','Generate a new venue QR? Previous venue codes will stop working.'),confirmLabel:msg('FE_EVENT_GENERATE_QR','Generate QR')}))void run(async()=>{const result=await api.doorQr(id);setDoorQr(result);return result;});}}>{msg('FE_ORG_VENUE_QR','Venue QR')}</button>}{event.is_published && <Link className={secondary} to={`/events/${id}`}>{msg('FE_ORG_PUBLIC_PAGE','View event page')}</Link>}</div>
    </div>
    <div className="grid grid-cols-2 xl:grid-cols-4 gap-3">{[[msg('FE_ORG_CONFIRMED','Confirmed tickets'),account.counts?.confirmed||0],[msg('FE_ORG_CHECKED_IN','Checked in'),account.counts?.checked_in||0],[msg('FE_ORG_PENDING_TICKETS','Awaiting payment'),account.counts?.pending||0],[msg('FE_ORG_CANCELLED_TICKETS','Cancelled / refunded'),account.counts?.cancelled||0]].map(([label,value])=><div key={label} className={card}><p className="text-xs text-muted-foreground">{label}</p><strong className="text-2xl font-heading">{value}</strong></div>)}</div>
    <div className={card}><h3 className="font-heading font-extrabold">{msg('FE_ORG_EARNINGS','Organizer settlement')}</h3><p className="text-sm text-muted-foreground">{msg('FE_ORG_EARNINGS_HELP','Your agreed organizer amount is recorded per ticket. Unpaid and refunded tickets do not add to this balance. This is separate from your shopping wallet.')}</p>
      <div className="grid grid-cols-2 xl:grid-cols-4 gap-3">{[[msg('FE_ORG_EARNED','Earned'),account.earned],[msg('FE_ORG_PAID_OUT','Paid out'),account.paid],[msg('FE_ORG_RESERVED','Requested / approved'),account.reserved],[msg('FE_ORG_AVAILABLE','Available to request'),account.available]].map(([label,value])=><div key={label} className="rounded-xl bg-secondary p-3"><p className="text-xs text-muted-foreground">{label}</p><strong>{money(value)}</strong></div>)}</div>
      {admin && <p className="text-sm">{msg('FE_ORG_CASH_COMPARISON', 'Cash on confirmed tickets: {cash}. Cash less organizer earnings, before provider fees: {difference}.', {cash:money(account.counts?.confirmed_cash),difference:money(Number(account.counts?.confirmed_cash||0)-Number(account.earned||0))})}</p>}
      {Number(account.overpaid)>0 && <p role="alert" className="text-destructive">{msg('FE_ORG_OVERPAID','Refunds changed previously paid earnings. Adjustment to review: {amount}.',{amount:money(account.overpaid)})}</p>}
      <div className="space-y-2">{(account.tiers||[]).map(tier=><p key={tier.id} className="flex justify-between gap-3 text-sm"><strong>{tier.name}</strong><span>{tier.organizer_amount==null?msg('FE_ORG_TERMS_PENDING','Organizer amount awaiting finalization'):msg('FE_ORG_UNIT_AMOUNT','{amount} organizer amount per ticket',{amount:money(tier.organizer_amount)})}</span></p>)}</div>
      {!admin && <PayoutForm event={event} available={account.available} busy={busy || loading} run={run} />}
      <div className="space-y-3">{(account.requests||[]).map(row=><PayoutCard key={row.id} row={row} admin={admin} busy={busy || loading} run={run} eventId={id}/>)}</div>
    </div>
    {admin && <ReviewControls account={account} busy={busy || loading} run={run} />}
    <Attendees id={id} revision={revision} busy={busy || loading} onScan={()=>setScanner(true)} onAdmit={ticket=>void admit(`hg-event:${id}:${ticket}`)} />
    {doorQr && <Modal open onClose={()=>setDoorQr(null)} title={msg('FE_ORG_VENUE_QR','Venue QR')}><div className="text-center space-y-3"><img alt={msg('FE_EVENT_VENUE_QR','Venue check-in QR code')} src={doorQr.qr_image} className="w-64 h-64 mx-auto object-contain"/><a href={doorQr.qr_image} download={`event-${id}-venue-qr.png`} className={secondary}>{msg('FE_EVENT_DOWNLOAD_QR','Download venue QR')}</a><p className="text-xs break-all">{doorQr.qr_payload}</p></div></Modal>}
    {scanner && <EventCheckInScanner mode="ticket" eventId={id} onClose={()=>setScanner(false)} onScan={token=>{setScanner(false);void admit(token);}} />}
  </div>;
}

function PayoutForm({event,available,busy,run}) {
  const [bank,setBank]=useState({bank_name:'',account_name:'',account_number:''});const intent=useCmsCreateIntent();
  const due=event.ends_at && new Date(event.ends_at).getTime()<=Date.now() && event.review_status==='approved';
  const submit=eventForm=>{eventForm.preventDefault();void run(async()=>{const result=await api.requestPayout(event.id,intent.body(bank));intent.clear();return result;});};
  return <form onSubmit={submit} className="space-y-3 border-t border-border pt-3"><p className="text-sm">{msg('FE_ORG_PAYOUT_HELP','Request settlement after the event ends. Holy Grills reviews the amount and records the completed bank transfer.')}</p>
    {due && Number(available)>0 && <><div className="grid sm:grid-cols-3 gap-3">{[['bank_name',msg('FE_ORG_BANK','Bank name')],['account_name',msg('FE_ORG_ACCOUNT_NAME','Account holder name')],['account_number',msg('FE_ORG_ACCOUNT_NUMBER','Account number')]].map(([key,label])=><Field key={key} label={label}><TextInput required maxLength={key==='account_number'?10:120} pattern={key==='account_number'?'[0-9]{10}':undefined} inputMode={key==='account_number'?'numeric':undefined} disabled={busy} value={bank[key]} onChange={e=>setBank({...bank,[key]:e.target.value})}/></Field>)}</div><button className={button} type="submit" disabled={busy}>{msg('FE_ORG_REQUEST_PAYOUT','Request available payout')}</button></>}
  </form>;
}

function PayoutCard({row,admin,busy,run,eventId}) {
  const [reference,setReference]=useState('');const [notes,setNotes]=useState('');
  const act=action=>run(()=>api.payout(eventId,row.id,{action,reference,notes}));
  return <div className="rounded-xl bg-secondary p-3 space-y-2"><p className="flex justify-between gap-3"><strong>{money(row.amount)}</strong><span>{statusLabel(row.state)}</span></p><p className="text-xs">{row.bank_details?.bank_name} · {admin?row.bank_details?.account_number:`••••${String(row.bank_details?.account_number||'').slice(-4)}`} · {row.bank_details?.account_name}</p>{row.bank_transfer_reference && <p className="text-xs">{msg('FE_ORG_TRANSFER_RECEIPT','Transfer reference: {reference}',{reference:row.bank_transfer_reference})}</p>}{row.admin_notes && <p className="text-sm">{row.admin_notes}</p>}
    {admin && ['pending','approved'].includes(row.state) && <><Field label={msg('FE_ORG_ADMIN_NOTES','Review notes')}><TextInput disabled={busy} value={notes} onChange={e=>setNotes(e.target.value)}/></Field><div className="flex gap-2 flex-wrap">{row.state==='pending' && <button className={button} disabled={busy} onClick={()=>void act('approve')}>{msg('FE_ORG_APPROVE_PAYOUT','Approve payout')}</button>}<button className={secondary} disabled={busy || notes.trim().length<3} onClick={()=>void act('reject')}>{msg('FE_ORG_REJECT_PAYOUT','Reject payout')}</button></div>
      {row.state==='approved' && <><Field label={msg('FE_ORG_BANK_REFERENCE','Completed bank transfer reference')}><TextInput disabled={busy} value={reference} onChange={e=>setReference(e.target.value)}/></Field><button className={button} disabled={busy || reference.trim().length<4} onClick={async()=>{if(await confirmAction({title:msg('FE_ORG_PAID_CONFIRM','Confirm that you have sent this bank transfer. This action records payment; it does not send money.'),confirmLabel:msg('FE_ORG_RECORD_PAID','Record completed transfer')}))void act('paid');}}>{msg('FE_ORG_RECORD_PAID','Record completed transfer')}</button></>}
    </>}{!admin && row.state==='pending' && <button className={secondary} disabled={busy} onClick={()=>void act('cancel')}>{msg('FE_ORG_CANCEL_REQUEST','Cancel payout request')}</button>}
  </div>;
}

function ReviewControls({account,busy,run}) {
  const [owner,setOwner]=useState(account.event.organizer_id||'');const [amounts,setAmounts]=useState<Record<string,string>>(()=>Object.fromEntries((account.tiers||[]).map(tier=>[tier.id,tier.organizer_amount==null?'':String(tier.organizer_amount)])));const [notes,setNotes]=useState('');
  const save=()=>run(()=>api.review(account.event.id,{action:'configure',organizer_id:owner,tiers:(account.tiers||[]).map(tier=>({id:tier.id,organizer_amount:Number(amounts[tier.id])}))}));
  return <div className={card}><h3 className="font-heading font-extrabold">{msg('FE_ORG_FINALIZATION','Admin review and organizer terms')}</h3><p className="text-sm text-muted-foreground">{msg('FE_ORG_FINALIZE_HELP','Use event administration to finalize ticket prices and attendee HP. Set the organizer account and agreed payout below, then approve publication. Existing ticket amounts remain unchanged.')}</p>
    <AdminUserPicker users={emptyUsers} value={owner} onChange={setOwner} campusId={account.event.campus_id||undefined} label={msg('FE_ORG_OWNER','Organizer account')} searchLabel={msg('FE_ORG_FIND_OWNER','Find organizer account')} disabled={busy}/>
    {(account.tiers||[]).map(tier=><Field key={tier.id} label={msg('FE_ORG_SET_UNIT','Organizer amount for {tier}',{tier:tier.name})}><TextInput disabled={busy} required min={0} max={999999999} step="0.01" type="number" value={amounts[tier.id]??''} onChange={e=>setAmounts({...amounts,[tier.id]:e.target.value})}/></Field>)}
    <button className={secondary} disabled={busy || !owner || (account.tiers||[]).some(tier=>!String(amounts[tier.id]??'').trim())} onClick={()=>void save()}>{msg('FE_ORG_SAVE_TERMS','Save organizer terms')}</button>
    <Field label={msg('FE_ORG_REVIEW_NOTES','Event review notes')}><TextInput disabled={busy} value={notes} onChange={e=>setNotes(e.target.value)}/></Field><div className="flex gap-2 flex-wrap"><button className={button} disabled={busy} onClick={()=>void run(()=>api.review(account.event.id,{action:'approve',notes}))}>{msg('FE_ORG_APPROVE_EVENT','Approve and publish')}</button><button className={secondary} disabled={busy || notes.trim().length<3} onClick={()=>void run(()=>api.review(account.event.id,{action:'changes_requested',notes}))}>{msg('FE_ORG_REQUEST_CHANGES','Request event changes')}</button></div>
  </div>;
}

function Attendees({id,revision,busy,onScan,onAdmit}) {
  const [query,setQuery]=useState('');const [offset,setOffset]=useState(0);const [rows,setRows]=useState([]);const [error,setError]=useState('');const [loading,setLoading]=useState(true);const [retry,setRetry]=useState(0);const version=useRef(0);
  useEffect(()=>{const current=++version.current;setLoading(true);setError('');const timer=setTimeout(()=>{api.attendees(id,{q:query.trim(),limit:50,offset}).then(result=>{if(current===version.current)setRows(result.attendees||[]);}).catch(e=>{if(current===version.current){setRows([]);setError(e.message);}}).finally(()=>{if(current===version.current)setLoading(false);});},250);return()=>{clearTimeout(timer);version.current++;};},[id,query,offset,revision,retry]);
  const exportRows=async()=>{try{const result=await api.export(id);const data=result.attendees||[];if(!data.length)return;const headers=Object.keys(data[0]);const csv=[headers.join(','),...data.map(row=>headers.map(key=>`"${csvCell(row[key])}"`).join(','))].join('\n');const url=URL.createObjectURL(new Blob([csv],{type:'text/csv'}));const anchor=document.createElement('a');anchor.href=url;anchor.download=`event-${id}-attendees.csv`;anchor.click();URL.revokeObjectURL(url);}catch(e){setError(e.message);}};
  return <div className={card}><div className="flex items-center justify-between flex-wrap gap-2"><h3 className="font-heading font-extrabold">{msg('FE_ORG_ATTENDEES','Attendees and check-in')}</h3><div className="flex gap-2"><button className={secondary} disabled={busy} onClick={onScan}>{msg('FE_EVENT_SCAN_ATTENDEE','Scan attendee ticket')}</button><button className={secondary} onClick={()=>void exportRows()}>{msg('FE_ORG_EXPORT','Export attendees')}</button></div></div>
    <input aria-label={msg('FE_EVENT_FIND_ATTENDEE','Find attendee')} placeholder={msg('FE_EVENT_FIND_ATTENDEE_HELP','Name, email, phone or ticket ID')} value={query} onChange={e=>{setOffset(0);setQuery(e.target.value);}} className="rounded-xl border border-border p-3 w-full"/>
    {error && <div role="alert" className="text-destructive"><p>{error}</p><button onClick={()=>setRetry(value=>value+1)}>{msg('FE_PLATFORM_RETRY','Retry')}</button></div>}
    {loading ? <p role="status">{msg('FE_EVENT_LOADING','Loading event details…')}</p> : !error && rows.length===0 ? <p>{msg('FE_ORG_NO_ATTENDEES','No attendees match this search.')}</p> : rows.map(row=><div key={row.ticket_id} className="rounded-xl bg-secondary p-3 flex flex-col sm:flex-row justify-between gap-2"><div className="min-w-0"><strong>{row.full_name||row.email}</strong><p className="text-xs break-words">{row.email} · {row.phone}</p><p className="text-xs break-all">{row.ticket_id}</p><p className="text-xs">{row.tier_name} · {row.payment_status}</p></div>{row.checked_in?<span>{msg('FE_ORG_CHECKED_IN','Checked in')}</span>:row.status==='confirmed' && ['paid','not_required'].includes(row.payment_status) && <button className={button} disabled={busy} onClick={()=>onAdmit(row.ticket_id)}>{msg('FE_EVENT_CHECK_IN_ATTENDEE','Check in attendee')}</button>}</div>)}
    <div className="flex justify-between"><button className={secondary} disabled={offset===0||loading} onClick={()=>setOffset(value=>Math.max(0,value-50))}>{msg('FE_ORG_PREVIOUS','Previous')}</button><button className={secondary} disabled={rows.length<50||loading} onClick={()=>setOffset(value=>value+50)}>{msg('FE_ORG_NEXT','Next')}</button></div>
  </div>;
}
