import { startTransition, useEffect } from 'react';
import { useLocation, useNavigate, useParams } from 'react-router-dom';
import { isAuthenticated } from '@/lib/apiClient';
import { isHydratingPrerender } from '@/lib/hydrationMode';
import Home from '@/pages/Home';

/** Old shared links remain usable; new links go directly to /register. */
export default function ReferralEntry() {
  const location = useLocation();
  const navigate = useNavigate();
  const { code } = useParams();
  const params = new URLSearchParams(location.search);
  const ref = code || params.get('ref') || params.get('referral');
  const target = ref && (code || !isAuthenticated())
    ? `/register?${new URLSearchParams({ ...Object.fromEntries(params), ref }).toString()}` : null;
  useEffect(() => {
    // Preserve the initial homepage markup; transition the router after mount
    // so a referral redirect does not interrupt its Suspense hydration.
    if (target) startTransition(() => navigate(target, { replace: true }));
  }, [target, navigate]);
  if (target && !isHydratingPrerender()) return null;
  return <Home />;
}
