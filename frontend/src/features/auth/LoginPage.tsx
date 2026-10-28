import { useState, type FormEvent } from 'react';
import { Link, useLocation, useNavigate, type Location } from 'react-router-dom';
import { Button } from '@/components/Button';
import { Logo } from '@/components/Logo';
import { TextInput } from '@/components/TextInput';
import { useDocumentTitle } from '@/lib/useDocumentTitle';
import { signIn, startDemoSession } from './session';

import { ExampleCheck } from './ExampleCheck';

/** /login (artboard "00 · Sign in"). Accounts are stubbed; the demo starts a session. */
export function LoginPage() {
  useDocumentTitle('Sign in');
  const navigate = useNavigate();
  const location = useLocation();
  const [notice, setNotice] = useState('');

  const from = (location.state as { from?: Location } | null)?.from;
  const startDemo = () => {
    startDemoSession();
    navigate(from ? `${from.pathname}${from.search}` : '/', { replace: true });
  };
  const comingSoon = async () => setNotice((await signIn()).message);
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
            <Link
              to="/welcome"
              className="self-start font-mono text-[12px] uppercase tracking-[0.5px] text-muted no-underline hover:text-ink hover:underline"
            >
              ← Back to Welcome
            </Link>
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
            <Button variant="secondary" size="field" onClick={() => void comingSoon()}>
              Continue with GitHub
            </Button>
            <Button variant="secondary" size="field" onClick={() => void comingSoon()}>
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
