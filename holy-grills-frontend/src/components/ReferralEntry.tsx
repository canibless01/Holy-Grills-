import { Navigate, useLocation, useParams } from 'react-router-dom';
import { isAuthenticated } from '@/lib/apiClient';
import Home from '@/pages/Home';

/** Old shared links remain usable; new links go directly to /register. */
export default function ReferralEntry() {
  const location = useLocation();
  const { code } = useParams();
  const params = new URLSearchParams(location.search);
  const ref = code || params.get('ref') || params.get('referral');
  if (ref && (code || !isAuthenticated())) {
    params.set('ref', ref);
    return <Navigate replace to={`/register?${params.toString()}`} />;
  }
  return <Home />;
}
