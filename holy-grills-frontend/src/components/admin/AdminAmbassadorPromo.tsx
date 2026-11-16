import { useState, useEffect, useCallback, useRef } from 'react';
import { Megaphone, ChevronDown, Copy, Check, Download, Share2, Loader2, Send } from 'lucide-react';
import { liveApi } from '@/lib/liveApi';
import { Card, Field, Modal, Pill } from './AdminShared';
import ImageUploader from './ImageUploader';
import StaffPanelSkeleton from '@/components/skeletons/StaffPanelSkeleton';
import { toast } from '@/components/ui/use-toast';
import { msg } from '@/lib/messages';
import { openWhatsApp } from '@/lib/whatsappShare';

const LINK_TOKENS = [/{{link}}/g, /{link}/g, /{{LINK}}/g];
const personalize = (caption: string, link: string) =>
  LINK_TOKENS.reduce((out, token) => out.replace(token, link), caption || '');
const trackingLink = (code?: string | null) => (code ? `${window.location.origin}/?ref=${code}` : '');

/** WhatsApp deep links carry text; graphic saving is a separate action. */
function shareToWhatsApp(_imageUrl: string | null, caption: string, _downloadName: string) {
  // Open synchronously in the tap, before clipboard/network awaits, so mobile
  // browsers preserve user activation and do not turn this into an image tab.
  openWhatsApp(caption);
  return Promise.resolve({ opened: true });
}

export default function AdminAmbassadorPromo() {
  const [messages, setMessages] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(false);
  const [openId, setOpenId] = useState<string | null>(null);
  const [createOpen, setCreateOpen] = useState(false);
  const month = new Date().toISOString().slice(0, 7);

  const load = useCallback(async () => {
    setLoading(true); setLoadError(false);
    try { setMessages(await liveApi.ambassadors.listPromos(month)); }
    catch (e) { setLoadError(true); toast({ title: e.message, variant: 'destructive' }); }
    finally { setLoading(false); }
  }, [month]);
  useEffect(() => { load(); }, [load]);

  if (loading) return <StaffPanelSkeleton />;

  return (
    <div className="space-y-4">
      {loadError && <p role="alert" className="text-sm text-destructive">{msg('FE_AMBASSADOR_WORKSPACE_READ_FAILED', 'Programme data could not be loaded.')}{' '}
        <button onClick={() => { void load(); }} className="underline">{msg('FE_LOOKUP_RETRY', 'Retry')}</button>
      </p>}
      <div className="flex justify-between items-center">
        <p className="text-xs text-muted-foreground">{messages.length} message{messages.length === 1 ? '' : 's'} · {month}</p>
        <button onClick={() => setCreateOpen(true)}
          className="flex items-center gap-1 px-3 py-2 rounded-full bg-primary text-white text-xs font-bold">
          <Megaphone className="w-4 h-4" />{msg('FE_ADMIN_AMBASSADOR_PROMO_NEW', 'New promotional message')}
        </button>
      </div>

      {!loadError && messages.length === 0 && (
        <Card className="p-8 text-center text-sm text-muted-foreground">
          {msg('FE_ADMIN_AMBASSADOR_PROMO_NEW', 'New promotional message')} — upload one graphic, write one caption with {'{{link}}'}, and every selected ambassador gets their own link.
        </Card>
      )}

      {messages.map((m) => (
        <PromoMessageRow key={m.id} message={m} open={openId === m.id}
          onToggle={() => setOpenId((id) => (id === m.id ? null : m.id))}
          />
      ))}

      {createOpen && <CreatePromoModal onClose={() => setCreateOpen(false)} onSaved={() => { setCreateOpen(false); load(); }} />}
    </div>
  );
}

function PromoMessageRow({ message, open, onToggle }: { message: any; open: boolean; onToggle: () => void }) {
  const [assignments, setAssignments] = useState<any[]>([]);
  const [busy, setBusy] = useState(false);
  const [sharingId, setSharingId] = useState<string | null>(null);
  const loaded = useRef(false);
  const statusLock=useRef(false);
  const [assignmentError, setAssignmentError] = useState(false);
  const [assignmentLoading, setAssignmentLoading] = useState(false);
  const [retry, setRetry] = useState(0);

  useEffect(() => {
    if (!open || loaded.current) return;
    let active = true;
    setAssignmentLoading(true); setAssignmentError(false);
    liveApi.ambassadors.promoAssignments(message.id).then(rows => {
      if (active) { setAssignments(rows); loaded.current = true; }
    }).catch(e => {
      if (active) { setAssignmentError(true); toast({ title: e.message, variant: 'destructive' }); }
    }).finally(() => { if (active) setAssignmentLoading(false); });
    return () => { active = false; };
  }, [open, message.id, retry]);

  const setStatus = async (assignmentId: string, status: string) => {
    if(statusLock.current)return;statusLock.current=true;setBusy(true);
    try {
      const updated = await liveApi.ambassadors.setAssignmentStatus(assignmentId, status);
      setAssignments((rows) => rows.map((r) => (r.id === assignmentId ? { ...r, ...updated } : r)));
    } catch (e) {
      toast({ title: e.message, variant: 'destructive' });
    } finally { statusLock.current=false;setBusy(false); }
  };

  const share = async (a: any) => {
    const link = trackingLink(a.profile?.referral_code);
    const caption = personalize(message.caption, link);
    setSharingId(a.id);
    try {
      await shareToWhatsApp(message.image_url, caption, `hg-promo-${message.id.slice(0, 8)}.jpg`);
    } finally { setSharingId(null); }
  };

  const statusPill = (s: string) => {
    const tone = s === 'shared' ? 'green' : s === 'seen' ? 'amber' : 'neutral';
    return <Pill tone={tone as any}>{msg(`FE_ADMIN_AMBASSADOR_STATUS_${s.toUpperCase()}`, s[0].toUpperCase() + s.slice(1))}</Pill>;
  };

  return (
    <Card className="p-0 overflow-hidden">
      <button onClick={onToggle} className="w-full flex items-center gap-3 p-4 text-left">
        {message.image_url
          ? <img src={message.image_url} alt="" className="w-14 h-14 rounded-xl object-cover shrink-0" />
          : <div className="w-14 h-14 rounded-xl bg-muted shrink-0" />}
        <div className="flex-1 min-w-0">
          <div className="text-sm font-bold truncate">{message.caption}</div>
          <div className="text-[11px] text-muted-foreground mt-0.5">{message.target_all ? 'All ambassadors' : 'Selected ambassadors'} · {message.month}</div>
        </div>
        <ChevronDown className={`w-4 h-4 transition-transform ${open ? 'rotate-180' : ''}`} />
      </button>

      {open && (
        <div className="border-t border-border p-3 space-y-2">
          {assignmentLoading && <p role="status">Loading assignments…</p>}
          {assignmentError && <button onClick={() => setRetry(value => value + 1)} className="underline text-destructive">Could not load assignments. Retry</button>}
          {assignments.map((a) => (
            <div key={a.id} className="rounded-xl border border-border p-3 space-y-2">
              <div className="flex items-center justify-between gap-2 flex-wrap">
                <div className="text-sm font-bold">{a.profile?.full_name || a.profile?.nickname || 'Ambassador'}</div>
                {statusPill(a.status)}
              </div>
              <div className="rounded-lg bg-muted p-2 text-[11px] text-muted-foreground max-h-20 overflow-y-auto whitespace-pre-wrap">
                {personalize(message.caption, trackingLink(a.profile?.referral_code))}
              </div>
              <div className="flex items-center gap-2 flex-wrap">
                <button onClick={() => share(a)} disabled={sharingId === a.id}
                  className="flex items-center gap-1 px-3 py-1.5 rounded-full bg-success text-white text-[11px] font-bold disabled:opacity-50">
                  {sharingId === a.id ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Share2 className="w-3.5 h-3.5" />}
                  {msg('FE_ADMIN_AMBASSADOR_PROMO_SHARE', 'Share on WhatsApp')}
                </button>
                {message.image_url && (
                  <a href={message.image_url} download={`hg-promo-${message.id.slice(0, 8)}.jpg`} target="_blank" rel="noopener noreferrer"
                    className="flex items-center gap-1 px-3 py-1.5 rounded-full border border-border text-[11px] font-bold">
                    <Download className="w-3.5 h-3.5" />{msg('FE_ADMIN_AMBASSADOR_PROMO_DOWNLOAD', 'Save graphic')}
                  </a>
                )}
                <CopyCaption caption={personalize(message.caption, trackingLink(a.profile?.referral_code))} />
                <div className="ml-auto flex gap-1">
                  {(['pending', 'seen', 'shared'] as const).map((s) => (
                    <button key={s} disabled={busy} onClick={() => setStatus(a.id, s)}
                      className={`px-2.5 py-1 rounded-full text-[10px] font-bold border ${a.status === s ? 'border-primary text-primary bg-primary/10' : 'border-border text-muted-foreground'}`}>
                      {msg(`FE_ADMIN_AMBASSADOR_STATUS_${s.toUpperCase()}`, s[0].toUpperCase() + s.slice(1))}
                    </button>
                  ))}
                </div>
              </div>
              {a.evidence_note && <div className="text-[10px] italic text-muted-foreground">“{a.evidence_note}”</div>}
            </div>
          ))}
          <p className="text-[10px] text-muted-foreground flex items-center gap-1">
            <Send className="w-3 h-3" /> Statuses are recorded manually from the ambassador's response — the site cannot read WhatsApp activity.
          </p>
        </div>
      )}
    </Card>
  );
}

function CopyCaption({ caption }: { caption: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      onClick={async()=>{try{await navigator.clipboard.writeText(caption);setCopied(true);setTimeout(()=>setCopied(false),1500);}catch{toast({title:msg('FE_AMBASSADOR_CLIPBOARD_FAILED','Copy failed. Select and copy the link or caption instead.'),variant:'destructive'});}}}
      className="flex items-center gap-1 px-3 py-1.5 rounded-full border border-border text-[11px] font-bold">
      {copied ? <Check className="w-3.5 h-3.5" /> : <Copy className="w-3.5 h-3.5" />}
      {msg('FE_ADMIN_AMBASSADOR_PROMO_COPY_CAPTION', 'Copy caption')}
    </button>
  );
}

function CreatePromoModal({ onClose, onSaved }: { onClose: () => void; onSaved: () => void }) {
  const [ambassadors, setAmbassadors] = useState<any[]>([]);
  const [form, setForm] = useState({ image_url: '', caption: '', target_all: true, ambassador_ids: [] as string[] });
  const [busy, setBusy] = useState(false);
  const [readError,setReadError]=useState(false);const [readRetry,setReadRetry]=useState(0);
  const intent = useRef<{ signature: string; id: string } | null>(null);
  const busyRef = useRef(false);
  const set = (k: string, v: any) => setForm((f) => ({ ...f, [k]: v }));

  useEffect(() => {
    let active=true;setReadError(false);
    liveApi.ambassadors.listStaff().then(rows=>{if(active)setAmbassadors(rows);}).catch(()=>{if(active)setReadError(true);});
    return()=>{active=false;};
  }, [readRetry]);

  const toggleAmbassador = (id: string) => set('ambassador_ids',
    form.ambassador_ids.includes(id) ? form.ambassador_ids.filter((x) => x !== id) : [...form.ambassador_ids, id]);

  const save = async () => {
    if (busyRef.current) return;
    busyRef.current = true;
    const month = new Date().toISOString().slice(0, 7);
    const signature = JSON.stringify({ month, ...form });
    if (!intent.current || intent.current.signature !== signature) intent.current = { signature, id: crypto.randomUUID() };
    setBusy(true);
    try {
      await liveApi.ambassadors.createPromo({
        request_id: intent.current.id, month,
        image_url: form.image_url || null,
        caption: form.caption,
        target_all: form.target_all,
        ambassador_ids: form.ambassador_ids,
      });
      toast({ title: msg('FE_ADMIN_AMBASSADOR_PROMO_GENERATE', 'Generate personalized messages') + ' ✓' });
      onSaved();
    } catch (e) {
      toast({ title: e.message, variant: 'destructive' });
    } finally { busyRef.current = false; setBusy(false); }
  };

  return (
    <Modal open onClose={()=>{if(!busy)onClose();}} title={msg('FE_ADMIN_AMBASSADOR_PROMO_NEW', 'New promotional message')}>
      <fieldset disabled={busy} className="space-y-3">
        {readError&&<p role="alert" className="text-sm text-destructive">{msg('FE_AMBASSADOR_WORKSPACE_READ_FAILED','Programme data could not be loaded.')} <button onClick={()=>setReadRetry(v=>v+1)} className="underline">{msg('FE_LOOKUP_RETRY','Retry')}</button></p>}
        <Field label={msg('FE_ADMIN_AMBASSADOR_PROMO_IMAGE' , 'Promotional graphic')}>
          <ImageUploader value={form.image_url} onChange={(url) => set('image_url', url)} folder="ambassador-promo" />
        </Field>
        <Field label={msg('FE_ADMIN_AMBASSADOR_PROMO_CAPTION', "Caption — use {{link}} for the ambassador's tracking link")}>
          <textarea value={form.caption} onChange={(e) => set('caption', e.target.value)} rows={4}
            className="w-full mt-1 p-2.5 rounded-xl border border-border text-sm" placeholder={`Hi! Order fresh grill via my link ${'{{link}}'}`} />
        </Field>
        <label className="flex items-center gap-2 text-xs font-bold">
          <input type="checkbox" checked={form.target_all} onChange={(e) => set('target_all', e.target.checked)} />
          {msg('FE_ADMIN_AMBASSADOR_PROMO_TARGET_ALL', 'Send to all ambassadors')}
        </label>
        {!form.target_all && (
          <div className="max-h-48 overflow-y-auto rounded-xl border border-border p-2 space-y-1">
            {ambassadors.map((a) => {
              const id = a.ambassador.profile_id;
              return (
                <label key={id} className="flex items-center gap-2 text-xs p-1.5 rounded-lg hover:bg-muted">
                  <input type="checkbox" checked={form.ambassador_ids.includes(id)} onChange={() => toggleAmbassador(id)} />
                  {a.profile?.full_name || a.profile?.nickname || id}
                </label>
              );
            })}
          </div>
        )}
        <button disabled={busy || readError || !form.caption.trim()} onClick={save}
          className="w-full py-3 rounded-full bg-gradient-cta text-white font-bold text-sm disabled:opacity-50">
          {busy ? <Loader2 className="w-4 h-4 animate-spin mx-auto" /> : msg('FE_ADMIN_AMBASSADOR_PROMO_GENERATE', 'Generate personalized messages')}
        </button>
      </fieldset>
    </Modal>
  );
}
