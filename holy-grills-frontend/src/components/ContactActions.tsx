import { useState } from 'react';
import { Mail, MessageCircle } from 'lucide-react';
import { msg, useMessages } from '@/lib/messages';
import { useContactDetails } from '@/lib/useContactDetails';
import { useHolyGrill } from '@/lib/HolyGrillContext';
import { useCampus } from '@/lib/campusContext';
import SocialLinks from '@/components/SocialLinks';

export default function ContactActions({ expanded = false }: { expanded?: boolean }) {
  useMessages();
  const [open, setOpen] = useState(expanded);
  const contact = useContactDetails();
  const { user, isLoading } = useHolyGrill();
  const { campusId, openGate } = useCampus();
  const needCampus = !isLoading && !user && !campusId;
  return <div className="space-y-3">
    {!expanded && <button type="button" aria-expanded={open} onClick={() => setOpen(!open)} className="inline-flex items-center gap-2 rounded-full px-4 py-2 border border-current text-sm font-bold"><MessageCircle className="w-4 h-4" />{msg('FE_CONTACT_CONTACT_US', 'Contact us')}</button>}
    {open && <div className="flex flex-col gap-3 text-sm" aria-label={msg('FE_CONTACT_OPTIONS', 'Contact options')}>
      {contact.loading ? <p role="status">{msg('FE_CONTACT_LOADING', 'Loading contact details…')}</p> : <>
        {needCampus ? <button type="button" onClick={() => openGate(msg('FE_CONTACT_FIND_CAMPUS_SUPPORT', 'find your campus support'), 'blocking')} className="inline-flex items-center gap-2 font-bold"><MessageCircle className="w-4 h-4" />{msg('FE_CONTACT_WHATSAPP_CHOOSE_CAMPUS', 'Choose campus for WhatsApp support')}</button> : contact.whatsappUrl && <a href={contact.whatsappUrl} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-2 font-bold"><MessageCircle className="w-4 h-4" />{msg('FE_CONTACT_MESSAGE_US_ON_WHATSAPP', 'Message us on WhatsApp')}</a>}
        {contact.email && <a href={`mailto:${contact.email}`} className="inline-flex items-center gap-2"><Mail className="w-4 h-4" />{contact.email}</a>}
        <SocialLinks links={contact.socialLinks} />
        {!needCampus && !contact.whatsappUrl && !contact.email && !Object.keys(contact.socialLinks).length && <p>{msg('FE_CONTACT_CONTACT_DETAILS_ARE_BEING_UPDATED_PLEASE_CHECK_B', 'Contact details are being updated. Please check back shortly.')}</p>}
      </>}
    </div>}
  </div>;
}
