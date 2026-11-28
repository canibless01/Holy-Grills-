import { useRef, useState } from 'react';
import { liveApi } from '@/lib/liveApi';
import { msg } from '@/lib/messages';
import { toast } from '@/components/ui/use-toast';
import { Field, Modal } from './AdminShared';
import ImageUploader from './ImageUploader';

export function PromoActions({ message, onSaved }: { message: any; onSaved: () => void }) {
  const [mode, setMode] = useState<'edit' | 'delete' | null>(null);
  const [caption, setCaption] = useState(message.caption || '');
  const [image, setImage] = useState(message.image_url || '');
  const [busy, setBusy] = useState(false);
  const lock = useRef(false);
  const save = async () => {
    if (lock.current) return;
    lock.current = true; setBusy(true);
    try {
      if (mode === 'delete') await liveApi.ambassadors.deletePromo(message.id, message.revision);
      else await liveApi.ambassadors.editPromo(message.id, { revision: message.revision, caption, image_url: image || null });
      setMode(null); onSaved();
    } catch (error) { toast({ title: error.message, variant: 'destructive' }); }
    finally { lock.current = false; setBusy(false); }
  };
  return <>
    <div className="flex flex-wrap gap-3 px-4 pb-3 text-xs font-bold">
      <button type="button" onClick={() => { setCaption(message.caption || ''); setImage(message.image_url || ''); setMode('edit'); }} className="underline">{msg('FE_AMBASSADOR_PROMO_EDIT', 'Edit message')}</button>
      <button type="button" onClick={() => setMode('delete')} className="text-destructive underline">{msg('FE_AMBASSADOR_PROMO_DELETE', 'Delete message')}</button>
    </div>
    {mode && <Modal open title={(mode === 'edit' ? msg('FE_AMBASSADOR_PROMO_EDIT', 'Edit message') : msg('FE_AMBASSADOR_PROMO_DELETE', 'Delete message'))} onClose={() => { if (!busy) setMode(null); }}>
      <fieldset disabled={busy} className="space-y-4">
        {mode === 'delete' ? <p>{msg('FE_AMBASSADOR_PROMO_DELETE_CONFIRM', 'Delete this promotional message? It will be hidden from the programme; its activity history is kept.')}</p> : <>
          <Field label={msg('FE_ADMIN_AMBASSADOR_PROMO_CAPTION', "Caption — use {{link}} for the ambassador's tracking link")}><textarea aria-label={msg('FE_ADMIN_AMBASSADOR_PROMO_CAPTION', "Caption — use {{link}} for the ambassador's tracking link")} className="w-full rounded-xl border p-3" rows={5} value={caption} onChange={e => setCaption(e.target.value)} maxLength={10000} /></Field>
          <ImageUploader value={image} onChange={setImage} folder="ambassador-promo" />
        </>}
        <button type="button" onClick={save} disabled={busy || (mode === 'edit' && !caption.trim())} className="rounded-full bg-primary px-5 py-2 font-bold text-white disabled:opacity-50">{(mode === 'delete' ? msg('FE_AMBASSADOR_PROMO_DELETE', 'Delete message') : msg('FE_AMBASSADOR_PROMO_SAVE', 'Save changes'))}</button>
      </fieldset>
    </Modal>}
  </>;
}

export function AmbassadorWhatsAppContact({ id, value, onSaved }: { id: string; value?: string; onSaved: (phone: string | null) => void }) {
  const [phone, setPhone] = useState(value || '');
  const [busy, setBusy] = useState(false);
  const lock = useRef(false);
  const save = async () => {
    if (lock.current) return;
    lock.current = true; setBusy(true);
    try { const result = await liveApi.ambassadors.setWhatsApp(id, phone.trim() || null); setPhone(result.whatsapp_phone || ''); onSaved(result.whatsapp_phone); }
    catch (error) { toast({ title: error.message, variant: 'destructive' }); }
    finally { lock.current = false; setBusy(false); }
  };
  return <div className="space-y-1 border-t pt-2">
    <label className="block text-xs font-bold">{msg('FE_AMBASSADOR_WHATSAPP_CONTACT', 'Ambassador WhatsApp contact')}<input type="tel" value={phone} onChange={e => setPhone(e.target.value)} disabled={busy} className="ml-2 rounded-lg border p-2" /></label>
    <p className="text-xs text-muted-foreground">{msg('FE_AMBASSADOR_WHATSAPP_HELP', 'Use a separate WhatsApp number for ambassador outreach. Leave blank to use the account phone.')}</p>
    <button type="button" disabled={busy} onClick={save} className="text-xs font-bold underline">{msg('FE_AMBASSADOR_WHATSAPP_SAVE', 'Save WhatsApp contact')}</button>
  </div>;
}
