import { useSyncExternalStore } from 'react';

/** Hackathon auth stub: the only session is the no-account demo. */
export interface Session {
  mode: 'demo';
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
    return parsed.mode === 'demo' ? { mode: 'demo' } : null;
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
export const endSession = () => write(null);

/** Stub for the email/password and GitHub/Google buttons: accounts are not built yet. */
export async function signIn(): Promise<{ ok: false; message: string }> {
  return Promise.resolve({ ok: false, message: 'Accounts are coming soon — use the demo.' });
}

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
