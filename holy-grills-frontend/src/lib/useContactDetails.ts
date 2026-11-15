import { useQuery } from '@tanstack/react-query';
import { msg } from '@/lib/messages';
import { useHolyGrill } from '@/lib/HolyGrillContext';
import { useCampus } from '@/lib/campusContext';
import { apiClient, getPublicCampusScope } from '@/lib/apiClient';
import { queryClientInstance } from '@/lib/query-client';
import { useResumeEffect } from '@/hooks/useResumeEffect';
import { normalizeWhatsAppNumber, safeText } from '@/lib/valueText';
import { safeSocialLinks } from '@/lib/socialLinks';

export function useContactDetails() {
  const { isLoading } = useHolyGrill();
  useCampus();
  const scope = getPublicCampusScope();
  const query = useQuery<Record<string, any>, Error & { status?: number }>({
    queryKey: ['public-contact-details', scope],
    enabled: !isLoading,
    queryFn: async () => {
      const data = await apiClient.get('/storefront/config/public', undefined,
        { 'X-Campus-ID': scope || '' }, { timeoutMs: 20000 });
      if (!data || typeof data !== 'object' || Array.isArray(data)) throw new Error('Invalid contact response');
      return data;
    },
    staleTime: 30000,
    gcTime: typeof window === 'undefined' ? Infinity : 30 * 60 * 1000,
    retry: (failures, error: { status?: number }) => failures < 1 &&
      (error.status === 0 || error.status === 408 || error.status === 429 || (error.status ?? 0) >= 500),
    refetchOnWindowFocus: true,
    refetchOnReconnect: true,
  }, queryClientInstance);
  useResumeEffect(background => {
    if (background && !isLoading) void query.refetch({ cancelRefetch: false });
  }, [scope, isLoading]);
  const config = query.data || {};
  const whatsapp = normalizeWhatsAppNumber(config.whatsapp_support_number);
  const message = safeText(config.whatsapp_support_message) || msg('FE_CONTACT_DEFAULT_WHATSAPP_MESSAGE', 'Hello, I need help with my order');
  return {
    loading: isLoading || query.isPending,
    error: query.isError,
    retry: () => { void query.refetch({ cancelRefetch: false }); },
    socialLinks: safeSocialLinks(config.global_social_links),
    email: safeText(config.global_support_email), phone: safeText(config.support_phone),
    address: safeText(config.support_address), social: safeText(config.support_social), whatsapp,
    whatsappUrl: whatsapp ? `https://wa.me/${whatsapp}?text=${encodeURIComponent(message)}` : '',
  };
}
