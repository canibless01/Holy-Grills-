import { Navigate, Outlet, useLocation } from 'react-router-dom';
import { isAuthenticated } from '@/lib/apiClient';

// Gates student account routes behind the Holy Grills JWT. Unauthenticated
// users are sent to /login with a return path so they come back after auth.
export default function RequireAuth() {
  const location = useLocation();
  if (!isAuthenticated()) {
    return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  }
  return <Outlet />;
}