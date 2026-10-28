import { useEffect, useRef, useState, type FormEvent } from 'react';
import { useNavigate, type Location } from 'react-router-dom';
import type { User } from 'firebase/auth';
import { apiFetch, ApiError } from '@/api/client';
import { Button } from '@/components/Button';
import { TextInput } from '@/components/TextInput';
import type * as FirebaseAuth from './firebase';
import { startDemoSession, startFirebaseSession, type SessionUser } from './session';

interface SignInModalProps {
  /** Forwarded destination to land on after a session starts. */
  from?: Location;
  onClose: () => void;
}

const WRONG_PASSWORD = 'That email and password don’t match an account.';
const CANCELLED = 'Sign-in was cancelled.';

const SIGN_IN_ERRORS: Record<string, string> = {
  'claimlens/firebase-not-configured': 'Accounts aren’t set up here yet — use the live demo.',
  'auth/invalid-credential': WRONG_PASSWORD,
  'auth/invalid-login-credentials': WRONG_PASSWORD,
  'auth/wrong-password': WRONG_PASSWORD,
  'auth/user-not-found': WRONG_PASSWORD,
  'auth/invalid-email': 'Enter a valid email address.',
  'auth/email-already-in-use': 'An account with that email already exists. Sign in instead.',
  'auth/weak-password': 'Choose a password of at least 6 characters.',
  'auth/popup-closed-by-user': CANCELLED,
  'auth/cancelled-popup-request': CANCELLED,
  'auth/popup-blocked': 'Your browser blocked the sign-in window. Allow pop-ups and try again.',
  'auth/account-exists-with-different-credential':
    'That email already signs in another way. Use the method you used before.',
  'auth/operation-not-allowed': 'That sign-in method isn’t turned on for ClaimLens.',
  'auth/unauthorized-domain': 'This site isn’t allowed to sign in with Firebase yet.',
  'auth/user-disabled': 'This account has been disabled.',
  'auth/too-many-requests': 'Too many attempts. Wait a moment and try again.',
  'auth/network-request-failed': 'Could not reach Firebase. Check your connection.',
};

function signInErrorMessage(error: unknown): string {
  if (error instanceof ApiError) return error.message;
  const code = typeof error === 'object' && error !== null && 'code' in error ? (error as { code: unknown }).code : null;
  return (
    (typeof code === 'string' ? SIGN_IN_ERRORS[code] : undefined) ??
    'Sign-in failed. Try again, or use the live demo.'
  );
}

function field(form: HTMLFormElement | null, name: string): string {
  const value = form ? new FormData(form).get(name) : null;
  return typeof value === 'string' ? value.trim() : '';
}

/**
 * Modal/drawer that pops up over the Welcome page when "Sign in to ClaimLens" is clicked.
 * Clicking outside the panel or pressing Escape dismisses it.
 */
export function SignInModal({ from, onClose }: SignInModalProps) {
  const navigate = useNavigate();
  const [notice, setNotice] = useState('');
  const [busy, setBusy] = useState(false);
  const [creating, setCreating] = useState(false);
  const panelRef = useRef<HTMLDivElement>(null);
  const formRef = useRef<HTMLFormElement>(null);
  const firstFocusRef = useRef<HTMLButtonElement>(null);

  // Trap focus and handle Escape key
  useEffect(() => {
    const prev = document.activeElement as HTMLElement | null;
    firstFocusRef.current?.focus();

    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', onKey);
    document.body.style.overflow = 'hidden';

    return () => {
      document.removeEventListener('keydown', onKey);
      document.body.style.overflow = '';
      prev?.focus();
    };
  }, [onClose]);

  const goOn = () => {
    navigate(from ? `${from.pathname}${from.search}` : '/', { replace: true });
  };

  const startDemo = () => {
    startDemoSession();
    goOn();
  };

  /** Signs in with Firebase, then has the API confirm the ID token before the session starts. */
  const signInWithFb = async (attempt: (firebase: typeof FirebaseAuth) => Promise<User>) => {
    setBusy(true);
    setNotice('');
    let firebase: typeof FirebaseAuth | undefined;
    try {
      firebase = await import('./firebase');
      const account = await attempt(firebase);
      const token = await account.getIdToken();
      const { user } = await apiFetch<{ user: SessionUser }>('/auth/me', { token });
      startFirebaseSession(user);
      goOn();
    } catch (error) {
      void firebase?.signOutOfFirebase().catch(() => undefined);
      const msg = signInErrorMessage(error);
      if (msg) setNotice(msg);
      setBusy(false);
    }
  };

  const onSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const email = field(event.currentTarget, 'email');
    const password = field(event.currentTarget, 'password');
    if (!email || !password) {
      setNotice('Enter your email and password.');
      return;
    }
    void signInWithFb((fb) =>
      creating
        ? fb.createAccount(email, password)
        : fb.signInWithEmail(email, password),
    );
  };

  const resetPassword = async () => {
    const email = field(formRef.current, 'email');
    if (!email) {
      setNotice('Enter your email above, then choose “Forgot?”.');
      return;
    }
    try {
      const firebase = await import('./firebase');
      await firebase.sendPasswordReset(email);
      setNotice(`If ${email} has an account, a reset link is on its way.`);
    } catch (error) {
      const msg = signInErrorMessage(error);
      if (msg) setNotice(msg);
    }
  };

  const toggleCreating = () => {
    setCreating((value) => !value);
    setNotice('');
  };

  const handleBackdropClick = (e: React.MouseEvent) => {
    if (!panelRef.current?.contains(e.target as Node)) onClose();
  };

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="modal-title"
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      onClick={handleBackdropClick}
    >
      {/* Blurred dark overlay */}
      <div className="absolute inset-0 bg-ink/60 backdrop-blur-sm" aria-hidden="true" />

      {/* Panel */}
      <div
        ref={panelRef}
        className="relative z-10 w-full max-w-[440px] bg-paper font-sans text-ink shadow-[8px_8px_0_var(--ink)] border-1.5 border-ink animate-modal-in"
        style={{ animation: 'modalIn 0.22s cubic-bezier(0.22,1,0.36,1) both' }}
      >
        {/* Close button */}
        <button
          type="button"
          aria-label="Close sign-in panel"
          onClick={onClose}
          className="absolute right-4 top-4 flex h-8 w-8 items-center justify-center border-1.5 border-ink bg-sheet font-mono text-[16px] font-bold text-ink hover:bg-ink hover:text-marker transition-colors"
        >
          ×
        </button>

        <div className="flex flex-col gap-6 px-8 py-8 pt-10">
          {/* Header */}
          <div className="flex flex-col gap-1.5">
            <p className="font-mono text-label uppercase tracking-[0.6px] text-muted">
              {creating ? 'Create account' : 'ClaimLens'}
            </p>
            <h2 id="modal-title" className="font-display text-[30px] font-extrabold leading-[1.1] tracking-[-0.8px]">
              Open your evidence desk
            </h2>
            <p className="text-[14px] text-muted leading-[1.5]">
              No account needed — try the live demo instantly.
            </p>
          </div>

          {/* Primary CTA — demo */}
          <Button
            ref={firstFocusRef}
            variant="marker-cta"
            fullWidth
            onClick={startDemo}
            id="demo-btn"
          >
            Try the live demo — no account
            <span aria-hidden="true">→</span>
          </Button>

          {/* Divider */}
          <div className="flex items-center gap-3 font-mono text-[11px] uppercase tracking-[0.5px] text-muted">
            <span aria-hidden="true" className="h-px flex-1 bg-rule-dashed" />
            or {creating ? 'create an account' : 'sign in'}
            <span aria-hidden="true" className="h-px flex-1 bg-rule-dashed" />
          </div>

          {/* Email / password form */}
          <form ref={formRef} className="flex flex-col gap-4" onSubmit={onSubmit} noValidate>
            <TextInput
              label="Email"
              type="email"
              name="email"
              autoComplete="email"
              placeholder="you@university.edu"
            />
            <TextInput
              label="Password"
              type="password"
              name="password"
              autoComplete={creating ? 'new-password' : 'current-password'}
              labelAction={
                creating ? undefined : (
                  <button type="button" className="underline text-muted" onClick={() => void resetPassword()}>
                    Forgot?
                  </button>
                )
              }
            />
            <Button type="submit" variant="primary-sheet" size="lg" fullWidth disabled={busy}>
              {creating ? 'Create account' : 'Sign in'}
            </Button>
          </form>

          {/* OAuth buttons */}
          <div className="grid grid-cols-2 gap-2.5">
            <Button
              variant="secondary"
              size="field"
              disabled={busy}
              onClick={() => void signInWithFb((fb) => fb.signInWithProvider('github'))}
            >
              Continue with GitHub
            </Button>
            <Button
              variant="secondary"
              size="field"
              disabled={busy}
              onClick={() => void signInWithFb((fb) => fb.signInWithProvider('google'))}
            >
              Continue with Google
            </Button>
          </div>

          {/* Notice / status */}
          <p
            role="status"
            className={notice ? 'border-l-2 border-marker pl-3 text-[13px] text-ink-2' : 'sr-only'}
          >
            {notice}
          </p>

          {/* Footer */}
          <p className="text-[13px] text-muted">
            {creating ? 'Have an account?' : 'New here?'}{' '}
            <button
              type="button"
              className="font-semibold text-ink underline"
              onClick={toggleCreating}
            >
              {creating ? 'Sign in' : 'Create an account'}
            </button>
            {' '}· Your uploads stay private to you.
          </p>
        </div>
      </div>

      {/* Keyframe injected inline for portability */}
      <style>{`
        @keyframes modalIn {
          from { opacity: 0; transform: translateY(16px) scale(0.97); }
          to   { opacity: 1; transform: translateY(0)    scale(1);    }
        }
      `}</style>
    </div>
  );
}
