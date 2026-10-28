import { Navigate, Outlet, useLocation } from 'react-router-dom';
import { useSession } from './session';

/** Route guard: without a session, start at /welcome, which leads to /login. */
export function RequireSession() {
  const session = useSession();
  const location = useLocation();
  if (!session) return <Navigate to="/welcome" replace state={{ from: location }} />;
  return <Outlet />;
}
