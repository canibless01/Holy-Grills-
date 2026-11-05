import { msg, useMessages } from '@/lib/messages';
import { MapPin } from 'lucide-react';
import ContactActions from '@/components/ContactActions';
import { useContactDetails } from '@/lib/useContactDetails';
import { useCampus } from '@/lib/campusContext';

export default function Contact() {
  useMessages();
  const contact = useContactDetails();
  const { campus } = useCampus();
  return (
    <section className="max-w-xl mx-auto py-8 space-y-6">
      <div>
        <span className="hg-eyebrow">{msg('FE_CONTACT_HERE_TO_HELP', "Here to help")}</span>
        <h1 className="font-heading font-extrabold text-3xl mt-2">{msg('FE_CONTACT_CONTACT_US', "Contact us")}</h1>
        <p className="text-muted-foreground mt-2">{campus ? msg('FE_CONTACT_CAMPUS_SUPPORT', '{campus} support', { campus: campus.name }) : msg('FE_CONTACT_GLOBAL_SUPPORT', '{platform} support', { platform: 'Holy Grills' })}</p>
      </div>
      <div className="rounded-2xl border border-border bg-card p-6 space-y-5">
        <ContactActions expanded />
        {contact.address && <p className="flex items-start gap-3"><MapPin className="w-5 h-5 text-primary shrink-0" /> {contact.address}</p>}
      </div>
    </section>
  );
}
