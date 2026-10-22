import { useSyncExternalStore } from 'react';

/** The signed-in account, as confirmed by GET /auth/me. */
export interface SessionUser {
  id: string;
  name: string;
  email: string | null;
  picture: string | null;
  /** The Firebase sign-in provider: "google.com", "github.com" or "password". */
  provider: string;
}

/** A demo session needs no account; a Firebase session's ID token comes from the Firebase SDK. */
export type Session = { mode: 'demo' } | { mode: 'firebase'; user: SessionUser };

const STORAGE_KEY = 'claimlens:session';
const CHANGE_EVENT = 'claimlens:session-change';

function readRaw(): string | null {
  try {
    return sessionStorage.getItem(STORAGE_KEY);
  } catch {
    return null;
  }
}

function isSessionUser(value: unknown): value is SessionUser {
  if (typeof value !== 'object' || value === null) return false;
  const user = value as Partial<Record<keyof SessionUser, unknown>>;
  return (
    typeof user.id === 'string' &&
    typeof user.name === 'string' &&
    typeof user.provider === 'string'
  );
}

export function readSession(): Session | null {
  const raw = readRaw();
  if (!raw) return null;
  try {
    const parsed = JSON.parse(raw) as { mode?: unknown; user?: unknown };
    if (parsed.mode === 'demo') return { mode: 'demo' };
    if (parsed.mode === 'firebase' && isSessionUser(parsed.user)) {
      return { mode: 'firebase', user: parsed.user };
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
export const startFirebaseSession = (user: SessionUser) => write({ mode: 'firebase', user });
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
