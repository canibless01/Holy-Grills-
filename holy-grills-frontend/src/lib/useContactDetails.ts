import { msg } from '@/lib/messages';
import { useHolyGrill } from '@/lib/HolyGrillContext';
import { normalizeWhatsAppNumber } from '@/lib/valueText';

export function useContactDetails() {
  const { getStringSetting } = useHolyGrill();
  const whatsapp = normalizeWhatsAppNumber(getStringSetting('whatsapp_support_number', ''));
  const message = getStringSetting('whatsapp_support_message', msg('FE_CONTACT_DEFAULT_WHATSAPP_MESSAGE', 'Hello, I need help with my order'));
  return {
    email: getStringSetting('support_email', ''),
    phone: getStringSetting('support_phone', ''),
    address: getStringSetting('support_address', ''),
    social: getStringSetting('support_social', ''),
    whatsapp,
    whatsappUrl: whatsapp ? `https://wa.me/${whatsapp}?text=${encodeURIComponent(message)}` : '',
  };
}
