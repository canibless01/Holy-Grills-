import { useEffect, useState } from 'react';
import { msg } from '@/lib/messages';
import { useHolyGrill } from '@/lib/HolyGrillContext';
import { useCampus } from '@/lib/campusContext';
import { liveApi } from '@/lib/liveApi';
import { normalizeWhatsAppNumber, safeText } from '@/lib/valueText';

export function useContactDetails() {
  const { isLoading } = useHolyGrill();
  const { campusId } = useCampus();
  const [config, setConfig] = useState<Record<string, any>>({});
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    let current = true;
    setConfig({}); setLoading(true);
    if (isLoading) return () => { current = false; };
    liveApi.storefront.getPublicConfig().then((data) => { if (current) setConfig(data || {}); })
      .catch(() => {}).finally(() => { if (current) setLoading(false); });
    return () => { current = false; };
  }, [campusId, isLoading]);
  const whatsapp = normalizeWhatsAppNumber(config.whatsapp_support_number);
  const message = safeText(config.whatsapp_support_message) || msg('FE_CONTACT_DEFAULT_WHATSAPP_MESSAGE', 'Hello, I need help with my order');
  return {
    loading: loading || isLoading,
    email: safeText(config.global_support_email), phone: safeText(config.support_phone),
    address: safeText(config.support_address), social: safeText(config.support_social), whatsapp,
    whatsappUrl: whatsapp ? `https://wa.me/${whatsapp}?text=${encodeURIComponent(message)}` : '',
  };
}
