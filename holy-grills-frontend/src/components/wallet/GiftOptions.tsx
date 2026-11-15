import { msg } from '@/lib/messages';
import { safeCallHref } from '@/lib/safeNavigation';

export function GiftOptions({ anonymous, shareContact, onAnonymous, onShareContact, disabled = false }) {
  return <fieldset disabled={disabled} className="space-y-2 rounded-xl border border-border p-3 text-sm">
    <legend className="px-1 font-bold">{msg('FE_GIFT_VISIBILITY', 'How your gift shows up')}</legend>
    <label className="flex items-start gap-2"><input type="checkbox" checked={anonymous} onChange={event => { onAnonymous(event.target.checked); if (event.target.checked) onShareContact(false); }} className="mt-1 accent-primary" /><span>{msg('FE_GIFT_ANONYMOUS', 'Send anonymously')}<span className="block text-xs text-muted-foreground">{msg('FE_GIFT_ANONYMOUS_HELP', 'Your name stays private. Your message is still visible.')}</span></span></label>
    <label className="flex items-start gap-2"><input type="checkbox" checked={shareContact} disabled={anonymous || disabled} onChange={event => onShareContact(event.target.checked)} className="mt-1 accent-primary" /><span>{msg('FE_GIFT_SHARE_PHONE', 'Share my registered phone number with the recipient')}<span className="block text-xs text-muted-foreground">{msg('FE_GIFT_SHARE_PHONE_HELP', 'So they can reach out and say thank you. This is optional.')}</span></span></label>
  </fieldset>;
}

export function GiftContact({ contact }) {
  const phone = contact?.phone;
  const href = typeof phone === 'string' ? safeCallHref(`tel:${phone}`) : null;
  return href ? <div className="rounded-xl bg-primary/5 p-3 text-sm"><p>{msg('FE_GIFT_CONTACT_SHARED', 'They shared their number so you can say thank you.')}</p><a href={href} className="mt-2 inline-block font-bold text-primary underline">{msg('FE_GIFT_CALL_THANKS', 'Call to say thank you')} · {phone}</a></div> : null;
}
