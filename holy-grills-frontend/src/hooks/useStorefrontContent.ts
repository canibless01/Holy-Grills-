import { useQuery } from '@tanstack/react-query';
import { apiClient, getPublicCampusScope } from '@/lib/apiClient';
import { queryClientInstance } from '@/lib/query-client';
import { useCampus } from '@/lib/campusContext';
import { useResumeEffect } from '@/hooks/useResumeEffect';

type Resource = 'sections' | 'banners' | 'early-supporters';

// Published content only. One request per resource/campus serves every Home
// section. Keep the last successful response across Menu → Home navigation;
// a failed revalidation must not turn published content into an empty page.
export function useStorefrontContent(resource: Resource) {
  // Subscribe to campus/auth scope changes, but key by the actual public-read
  // header, including an administrator's selected campus. Capture that header
  // for retries so a late response can never populate another campus's cache.
  useCampus();
  const scope = getPublicCampusScope();
  const query = useQuery({
    queryKey: ['published-storefront', scope, resource],
    queryFn: async () => {
      const response = await apiClient.get(`/storefront/${resource}`, undefined,
        { 'X-Campus-ID': scope || '' }, { timeoutMs: 20000 });
      const rows = Array.isArray(response) ? response :
        response?.[resource === 'early-supporters' ? 'early_supporters' : resource] ?? response?.sections;
      if (!Array.isArray(rows)) throw new Error('Invalid storefront response');
      return rows;
    },
    staleTime: 30000,
    // SSR must not schedule a cleanup timer that keeps prerender alive.
    gcTime: typeof window === 'undefined' ? Infinity : 30 * 60 * 1000,
    retry: (failures, error: { status?: number }) => failures < 2 &&
      (error.status === 0 || error.status === 408 || error.status === 429 || (error.status ?? 0) >= 500),
    retryDelay: attempt => Math.min(750 * 2 ** attempt, 3000),
    refetchOnWindowFocus: true,
    refetchOnReconnect: true,
  }, queryClientInstance);

  useResumeEffect(background => {
    if (background) void query.refetch({ cancelRefetch: false });
  }, [scope, resource]);
  return query;
}
