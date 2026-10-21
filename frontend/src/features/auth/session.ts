import { useSyncExternalStore } from 'react';

export interface Session {
  mode: 'demo' | 'google' | 'github';
  accessToken?: string;
  user?: { id: string; email: string; name: string; picture?: string };
}

const STORAGE_KEY = 'claimlens:session';
const CHANGE_EVENT = 'claimlens:session-change';

function readRaw(): string | null {
  try {
    return sessionStorage.getItem(STORAGE_KEY);
  } catch {
    return null;
  }
}

export function readSession(): Session | null {
  const raw = readRaw();
  if (!raw) return null;
  try {
    const parsed = JSON.parse(raw) as Partial<Session>;
    if (parsed.mode === 'demo') return { mode: 'demo' };
    if (
      (parsed.mode === 'google' || parsed.mode === 'github') &&
      typeof parsed.accessToken === 'string' &&
      parsed.user &&
      typeof parsed.user.email === 'string'
    ) {
      return parsed as Session;
    }
    return null;
  } catch {
    return null;
  }
}

function write(value: Session | null) {
  try {
    if (value) sessionStorage.setItem(STORAGE_KEY, JSON.stringify(value));
    else sessionStorage.removeItem(STORAGE_KEY);
  } catch {
    // Storage unavailable: the session lasts until reload.
  }
  window.dispatchEvent(new Event(CHANGE_EVENT));
}

export const startDemoSession = () => write({ mode: 'demo' });
export const startGoogleSession = (session: Omit<Session, 'mode'>) =>
  write({ mode: 'google', ...session });
export const startGithubSession = (session: Omit<Session, 'mode'>) =>
  write({ mode: 'github', ...session });
export const endSession = () => write(null);

function subscribe(onChange: () => void) {
  window.addEventListener(CHANGE_EVENT, onChange);
  window.addEventListener('storage', onChange);
  return () => {
    window.removeEventListener(CHANGE_EVENT, onChange);
    window.removeEventListener('storage', onChange);
  };
}

/** The current session, re-rendering when it starts or ends. */
export function useSession(): Session | null {
  const raw = useSyncExternalStore(subscribe, readRaw, () => null);
  return raw ? readSession() : null;
}
