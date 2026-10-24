import { useRef, useState, type FormEvent } from 'react';
import { useLocation, useNavigate, type Location } from 'react-router-dom';
import type { User } from 'firebase/auth';
import { ApiError, apiFetch } from '@/api/client';
import { Button } from '@/components/Button';
import { Logo } from '@/components/Logo';
import { TextInput } from '@/components/TextInput';
import { useDocumentTitle } from '@/lib/useDocumentTitle';
import { ExampleCheck } from './ExampleCheck';
import type * as FirebaseAuth from './firebase';
import { startDemoSession, startFirebaseSession, type SessionUser } from './session';

const WRONG_PASSWORD = 'That email and password don’t match an account.';
const CANCELLED = 'Sign-in was cancelled.';

/** Inline messages for Firebase error codes. */
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
  const code = typeof error === 'object' && error !== null && 'code' in error ? error.code : null;
  return (
    (typeof code === 'string' ? SIGN_IN_ERRORS[code] : undefined) ??
    'Sign-in failed. Try again, or use the live demo.'
  );
}

function field(form: HTMLFormElement | null, name: string): string {
  const value = form ? new FormData(form).get(name) : null;
  return typeof value === 'string' ? value.trim() : '';
}

/** /login (artboard "00 · Sign in"). Accounts use Firebase Authentication; the demo needs none. */
export function LoginPage() {
  useDocumentTitle('Sign in');
  const navigate = useNavigate();
  const location = useLocation();
  const formRef = useRef<HTMLFormElement>(null);
  const [notice, setNotice] = useState('');
  const [busy, setBusy] = useState(false);
  const [creating, setCreating] = useState(false);

  const from = (location.state as { from?: Location } | null)?.from;
  const goOn = () => navigate(from ? `${from.pathname}${from.search}` : '/', { replace: true });

  const startDemo = () => {
    startDemoSession();
    goOn();
  };

  /** Signs in with Firebase, then has the API confirm the ID token before the session starts. */
  const signIn = async (attempt: (firebase: typeof FirebaseAuth) => Promise<User>) => {
    setBusy(true);
    setNotice('');
    let firebase: typeof FirebaseAuth | undefined;
    try {
      firebase = await import('./firebase');
      const account = await attempt(firebase);
      const { user } = await apiFetch<{ user: SessionUser }>('/auth/me', {
        token: await account.getIdToken(),
      });
      startFirebaseSession(user);
      goOn();
    } catch (error) {
      // No app session, so no Firebase sign-in either.
      void firebase?.signOutOfFirebase().catch(() => undefined);
      setNotice(signInErrorMessage(error));
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
    void signIn((firebase) =>
      creating
        ? firebase.createAccount(email, password)
        : firebase.signInWithEmail(email, password),
    );
  };

  const resetPassword = async () => {
    const email = field(formRef.current, 'email');
    if (!email) {
      setNotice('Enter your email above, then choose “Forgot?” again.');
      return;
    }
    try {
      const firebase = await import('./firebase');
      await firebase.sendPasswordReset(email);
      setNotice(`If ${email} has an account, a reset link is on its way.`);
    } catch (error) {
      setNotice(signInErrorMessage(error));
    }
  };

  const toggleCreating = () => {
    setCreating((value) => !value);
    setNotice('');
  };

  return (
    <main className="flex min-h-screen flex-wrap bg-paper font-sans text-ink">
      {/* Below 900px the panel is hidden and the form takes the screen. Flex bases are the
          artboard's content-box 620px / 460px plus each side's padding. */}
      <section
        aria-label="About ClaimLens"
        className="graph-paper-ink hidden min-w-0 flex-[1_1_732px] flex-col gap-10 px-14 py-10 text-on-ink min-[900px]:flex"
      >
        <Logo onInk to="/welcome" />
        <div className="flex max-w-[620px] flex-grow flex-col justify-center gap-7">
          <h1 className="font-display text-[64px] font-extrabold leading-[0.98] tracking-[-2px]">
            Don’t trust the claim.
            <br />
            <span className="bg-marker px-2 text-ink">Read the evidence.</span>
          </h1>
          <p className="max-w-[500px] text-[18px] leading-[1.55] text-muted-on-ink-2">
            Paste any research claim. ClaimLens finds the papers, reads them, and shows exactly who
            agrees, who disagrees, and on which page.
          </p>
          <ExampleCheck />
        </div>
        <p className="flex flex-wrap gap-x-5 gap-y-2 font-mono text-[12px] text-muted-on-ink">
          <span>NVIDIA Nemotron 3</span>
          <span>Nebius Token Factory</span>
          <span>Semantic Scholar · arXiv · Tavily</span>
        </p>
      </section>

      <section
        aria-labelledby="signin-h"
        className="flex min-w-0 flex-[1_1_524px] items-center justify-center px-4 py-10 md:px-8"
      >
        <div className="flex w-full max-w-[420px] flex-col gap-6">
          <div className="flex flex-col gap-6 min-[900px]:hidden">
            <Logo to="/welcome" />
            <h1 className="sr-only">ClaimLens: don’t trust the claim, read the evidence.</h1>
          </div>
          <div className="flex flex-col gap-2">
            <p className="font-mono text-label uppercase text-muted">
              {creating ? 'Create account' : 'Sign in'}
            </p>
            <h2 id="signin-h" className="font-display text-[34px] font-bold tracking-[-0.8px]">
              Open your evidence desk
            </h2>
          </div>

          <Button variant="marker-cta" fullWidth onClick={startDemo}>
            Try the live demo — no account
            <span aria-hidden="true">→</span>
          </Button>

          <div className="flex items-center gap-3 font-mono text-[12px] text-muted">
            <span aria-hidden="true" className="h-px flex-1 bg-rule-dashed" />
            or sign in
            <span aria-hidden="true" className="h-px flex-1 bg-rule-dashed" />
          </div>

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
                  <button type="button" className="underline" onClick={() => void resetPassword()}>
                    Forgot?
                  </button>
                )
              }
            />
            <Button type="submit" variant="primary-sheet" size="lg" fullWidth disabled={busy}>
              {creating ? 'Create account' : 'Sign in'}
            </Button>
          </form>

          <div className="grid grid-cols-2 gap-2.5">
            <Button
              variant="secondary"
              size="field"
              disabled={busy}
              onClick={() => void signIn((firebase) => firebase.signInWithProvider('github'))}
            >
              Continue with GitHub
            </Button>
            <Button
              variant="secondary"
              size="field"
              disabled={busy}
              onClick={() => void signIn((firebase) => firebase.signInWithProvider('google'))}
            >
              Continue with Google
            </Button>
          </div>

          <p
            role="status"
            className={notice ? 'border-l-2 border-marker pl-3 text-[14px]' : 'sr-only'}
          >
            {notice}
          </p>

          <p className="text-[14px] text-muted">
            {creating ? 'Have an account?' : 'New here?'}{' '}
            <button
              type="button"
              className="font-semibold text-ink underline"
              onClick={toggleCreating}
            >
              {creating ? 'Sign in' : 'Create an account'}
            </button>{' '}
            · Your uploads stay private to you.
          </p>
        </div>
      </section>
    </main>
  );
}
