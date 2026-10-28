import { useEffect, useRef, useState, type FormEvent } from 'react';
import { useNavigate, type Location } from 'react-router-dom';
import { Button } from '@/components/Button';
import { TextInput } from '@/components/TextInput';
import { signIn, startDemoSession } from './session';

interface SignInModalProps {
  /** Forwarded destination to land on after a demo session starts. */
  from?: Location;
  onClose: () => void;
}

/**
 * Modal/drawer that pops up over the Welcome page when "Sign in to ClaimLens" is clicked.
 * Clicking outside the panel or pressing Escape dismisses it.
 */
export function SignInModal({ from, onClose }: SignInModalProps) {
  const navigate = useNavigate();
  const [notice, setNotice] = useState('');
  const panelRef = useRef<HTMLDivElement>(null);
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

  const startDemo = () => {
    startDemoSession();
    navigate(from ? `${from.pathname}${from.search}` : '/', { replace: true });
  };

  const comingSoon = async () => setNotice((await signIn()).message);
  const onSubmit = (event: FormEvent) => {
    event.preventDefault();
    void comingSoon();
  };

  const handleBackdropClick = (e: React.MouseEvent) => {
    if (!panelRef.current?.contains(e.target as Node)) onClose();
  };

  return (
    /* Backdrop */
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

        <div className="flex flex-col gap-6 px-8 py-8 pt-12">
          {/* Header */}
          <div className="flex flex-col gap-1.5">
            <p className="font-mono text-label uppercase tracking-[0.6px] text-muted">ClaimLens</p>
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
            or sign in with email
            <span aria-hidden="true" className="h-px flex-1 bg-rule-dashed" />
          </div>

          {/* Email / password form */}
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
                <button type="button" className="underline text-muted" onClick={() => void comingSoon()}>
                  Forgot?
                </button>
              }
            />
            <Button type="submit" variant="primary-sheet" size="lg" fullWidth>
              Sign in
            </Button>
          </form>

          {/* OAuth buttons */}
          <div className="grid grid-cols-2 gap-2.5">
            <Button variant="secondary" size="field" onClick={() => void comingSoon()}>
              GitHub
            </Button>
            <Button variant="secondary" size="field" onClick={() => void comingSoon()}>
              Google
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
            New here?{' '}
            <button
              type="button"
              className="font-semibold text-ink underline"
              onClick={() => void comingSoon()}
            >
              Create an account
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
