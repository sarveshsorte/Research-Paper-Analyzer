import { Navigate, Outlet, useLocation } from 'react-router-dom';
import { useSession } from './session';

/**
 * Route guard: without a session, start at the intro (/welcome), which leads to /login; the page
 * asked for rides along in router state so the demo returns there.
 */
export function RequireSession() {
  const session = useSession();
  const location = useLocation();
  if (!session) return <Navigate to="/welcome" replace state={{ from: location }} />;
  return <Outlet />;
}
