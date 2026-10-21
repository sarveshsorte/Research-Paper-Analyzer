import { useEffect, useId, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Button } from '@/components/Button';
import { endSession, useSession } from './session';

/** The account menu shows the active demo or Google session and signs out. */
export function AccountMenu() {
  const [open, setOpen] = useState(false);
  const navigate = useNavigate();
  const rootRef = useRef<HTMLDivElement>(null);
  const buttonRef = useRef<HTMLButtonElement>(null);
  const panelId = useId();
  const session = useSession();
  const isGoogle = session?.mode === 'google';
  const isGithub = session?.mode === 'github';

  useEffect(() => {
    if (!open) return;
    const onPointer = (event: MouseEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false);
    };
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setOpen(false);
        buttonRef.current?.focus();
      }
    };
    document.addEventListener('mousedown', onPointer);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onPointer);
      document.removeEventListener('keydown', onKey);
    };
  }, [open]);

  const signOut = () => {
    endSession();
    navigate('/login', { replace: true });
  };

  return (
    <div ref={rootRef} className="relative">
      <button
        ref={buttonRef}
        type="button"
        aria-label="Account"
        aria-expanded={open}
        aria-controls={panelId}
        onClick={() => setOpen((value) => !value)}
        className="h-9 w-9 border-1.5 border-ink bg-sheet font-mono text-[12px] font-semibold text-ink"
      >
        {isGoogle || isGithub ? (session.user?.name.slice(0, 2).toUpperCase() ?? 'AC') : 'AC'}
      </button>
      {open && (
        <div
          id={panelId}
          className="absolute right-0 top-full z-40 mt-2 flex w-64 flex-col gap-3 border-1.5 border-ink bg-sheet p-4"
        >
          <p className="font-mono text-label uppercase text-muted">
            {isGoogle || isGithub ? session.user?.name : 'Demo session'}
          </p>
          <p className="text-[14px] leading-[1.5] text-ink-2">
            {isGoogle || isGithub
              ? session.user?.email
              : 'No account: your papers and checks stay in this browser tab.'}
          </p>
          <Button variant="secondary" fullWidth onClick={signOut}>
            Sign out
          </Button>
        </div>
      )}
    </div>
  );
}
