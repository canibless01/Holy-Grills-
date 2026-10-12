import { msg, useMessages } from '@/lib/messages';
import { Mail, Phone, MapPin, MessageCircle } from 'lucide-react';
import { useContactDetails } from '@/lib/useContactDetails';
import { useCampus } from '@/lib/campusContext';
import { useHolyGrill } from '@/lib/HolyGrillContext';

export default function Contact() {
  useMessages();
  const contact = useContactDetails();
  const { campus, openGate } = useCampus();
  const { user } = useHolyGrill();
  return (
    <section className="max-w-xl mx-auto py-8 space-y-6">
      <div>
        <span className="hg-eyebrow">{msg('FE_CONTACT_HERE_TO_HELP', "Here to help")}</span>
        <h1 className="font-heading font-extrabold text-3xl mt-2">{msg('FE_CONTACT_CONTACT_US', "Contact us")}</h1>
        <p className="text-muted-foreground mt-2">{campus ? msg('FE_CONTACT_CAMPUS_SUPPORT', '{campus} support', { campus: campus.name }) : msg('FE_CONTACT_GLOBAL_SUPPORT', 'Holy Grills support')}</p>
      </div>
      {!user && <button onClick={() => openGate(msg('FE_CONTACT_FIND_CAMPUS_SUPPORT', 'find your campus support'), 'blocking')} className="text-sm font-bold text-primary underline">{campus ? msg('FE_CONTACT_CHANGE_CAMPUS', 'Change campus') : msg('FE_CONTACT_CHOOSE_CAMPUS', 'Choose your campus')}</button>}
      <div className="rounded-2xl border border-border bg-card p-6 space-y-5">
        {contact.whatsappUrl && <a href={contact.whatsappUrl} target="_blank" rel="noopener noreferrer" className="flex items-center gap-3 text-primary font-bold"><MessageCircle className="w-5 h-5" /> {msg('FE_CONTACT_MESSAGE_US_ON_WHATSAPP', "Message us on WhatsApp")}</a>}
        {contact.email && <a href={`mailto:${contact.email}`} className="flex items-center gap-3"><Mail className="w-5 h-5 text-primary" /> {contact.email}</a>}
        {contact.phone && <a href={`tel:${contact.phone.replace(/[^+\d]/g, '')}`} className="flex items-center gap-3"><Phone className="w-5 h-5 text-primary" /> {contact.phone}</a>}
        {contact.address && <p className="flex items-start gap-3"><MapPin className="w-5 h-5 text-primary shrink-0" /> {contact.address}</p>}
        {!contact.whatsappUrl && !contact.email && !contact.phone && <p className="text-muted-foreground">{msg('FE_CONTACT_CONTACT_DETAILS_ARE_BEING_UPDATED_PLEASE_CHECK_B', "Contact details are being updated. Please check back shortly.")}</p>}
        {contact.social && <p className="text-sm text-muted-foreground">{contact.social}</p>}
      </div>
    </section>
  );
}
