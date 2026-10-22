import { useEffect, useRef, useState, type FormEvent } from 'react';
import { useLocation, useNavigate, type Location } from 'react-router-dom';
import { Button } from '@/components/Button';
import { Logo } from '@/components/Logo';
import { TextInput } from '@/components/TextInput';
import { useDocumentTitle } from '@/lib/useDocumentTitle';
import { apiFetch } from '@/api/client';
import { env } from '@/lib/env';
import { ExampleCheck } from './ExampleCheck';
import { startDemoSession, startGithubSession, startGoogleSession } from './session';

declare global {
  interface Window {
    google?: {
      accounts: {
        id: {
          initialize(options: {
            client_id: string;
            callback: (response: { credential: string }) => void;
          }): void;
          renderButton(element: HTMLElement, options: Record<string, string | number>): void;
        };
      };
    };
  }
}

/** /login (artboard "00 · Sign in"). Accounts are stubbed; the demo starts a session. */
export function LoginPage() {
  useDocumentTitle('Sign in');
  const navigate = useNavigate();
  const location = useLocation();
  const [notice, setNotice] = useState('');
  const googleButtonRef = useRef<HTMLDivElement>(null);

  const from = (location.state as { from?: Location } | null)?.from;
  useEffect(() => {
    const params = new URLSearchParams(location.search);
    if (params.get('provider') !== 'github') return;
    const accessToken = params.get('access_token');
    const id = params.get('user_id');
    const email = params.get('email');
    const name = params.get('name');
    if (!accessToken || !id || !email || !name) {
      setNotice('GitHub sign-in response was incomplete.');
      return;
    }
    startGithubSession({
      accessToken,
      user: { id, email, name, picture: params.get('picture') || undefined },
    });
    navigate(from ? `${from.pathname}${from.search}` : '/', { replace: true });
  }, [from, location.search, navigate]);
  const startDemo = () => {
    startDemoSession();
    navigate(from ? `${from.pathname}${from.search}` : '/', { replace: true });
  };
  const comingSoon = async () => setNotice('Use Google sign-in or the live demo.');
  const startGithub = () => {
    window.location.assign(`${env.apiBaseUrl}/auth/github/login`);
  };
  useEffect(() => {
    if (!env.googleClientId || !googleButtonRef.current) return;
    const script = document.createElement('script');
    script.src = 'https://accounts.google.com/gsi/client';
    script.async = true;
    script.onload = () => {
      window.google?.accounts.id.initialize({
        client_id: env.googleClientId,
        callback: async ({ credential }) => {
          try {
            const result = await apiFetch<{
              access_token: string;
              user: { id: string; email: string; name: string; picture?: string };
            }>('/auth/google', { method: 'POST', body: { credential } });
            startGoogleSession({ accessToken: result.access_token, user: result.user });
            navigate(from ? `${from.pathname}${from.search}` : '/', { replace: true });
          } catch (error) {
            setNotice(error instanceof Error ? error.message : 'Google sign-in failed.');
          }
        },
      });
      if (googleButtonRef.current) {
        window.google?.accounts.id.renderButton(googleButtonRef.current, {
          type: 'standard',
          theme: 'outline',
          size: 'large',
          text: 'continue_with',
          width: 220,
        });
      }
    };
    document.head.appendChild(script);
    return () => script.remove();
  }, [from, navigate]);
  const onSubmit = (event: FormEvent) => {
    event.preventDefault();
    void comingSoon();
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
            <p className="font-mono text-label uppercase text-muted">Sign in</p>
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

          <form className="flex flex-col gap-4" onSubmit={onSubmit} noValidate>
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
              autoComplete="current-password"
              labelAction={
                <button type="button" className="underline" onClick={() => void comingSoon()}>
                  Forgot?
                </button>
              }
            />
            <Button type="submit" variant="primary-sheet" size="lg" fullWidth>
              Sign in
            </Button>
          </form>

          <div className="grid grid-cols-2 gap-2.5">
            <Button variant="secondary" size="field" onClick={startGithub}>
              Continue with GitHub
            </Button>
            <div className="relative flex min-h-10 items-center justify-center overflow-hidden">
              <div
                aria-hidden="true"
                className="pointer-events-none absolute inset-0 flex items-center justify-center gap-2.5 border-1.5 border-ink bg-sheet px-3 py-2 text-[15px] font-semibold text-ink"
              >
                Continue with Google
              </div>
              <div
                ref={googleButtonRef}
                aria-label="Continue with Google"
                className="relative z-10 min-h-10 w-full opacity-0"
              />
            </div>
          </div>

          <p
            role="status"
            className={notice ? 'border-l-2 border-marker pl-3 text-[14px]' : 'sr-only'}
          >
            {notice}
          </p>

          <p className="text-[14px] text-muted">
            New here?{' '}
            <button
              type="button"
              className="font-semibold text-ink underline"
              onClick={() => void comingSoon()}
            >
              Create an account
            </button>{' '}
            · Your uploads stay private to you.
          </p>
        </div>
      </section>
    </main>
  );
}
