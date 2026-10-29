import { useEffect, useState, useCallback } from 'react';
import { cn } from '@/lib/cn';

export const REPLAY_EVENT = 'claimlens:replay-intro';

export function replayEntryAnimation() {
  window.dispatchEvent(new CustomEvent(REPLAY_EVENT));
}

interface EntryAnimationProps {
  /** Optional callback fired when animation sequence finishes. */
  onComplete?: () => void;
  /** Force the animation to run even if already played in this session. Default is true for initial load. */
  autoPlay?: boolean;
}

const STEPS = [
  'INITIALIZING SCIENTIFIC REASONING ENGINE…',
  'LOADING HYBRID RETRIEVAL & VECTOR PIPELINE…',
  'CONNECTING NVIDIA NEMOTRON-3.5 RERANKER…',
  'CLAIMLENS SYSTEM ONLINE · READY',
];

/**
 * Entry splash animation for ClaimLens.
 * Plays when the user starts the application, featuring a brutalist viewfinder,
 * animated logo reveal, diagnostic telemetry, and an ultra-smooth exit transition.
 */
export function EntryAnimation({ onComplete, autoPlay = true }: EntryAnimationProps) {
  const [mounted, setMounted] = useState(autoPlay);
  const [exiting, setExiting] = useState(false);
  const [stepIndex, setStepIndex] = useState(0);
  const [progress, setProgress] = useState(15);

  const dismiss = useCallback(() => {
    setExiting(true);
    const timeout = setTimeout(() => {
      setMounted(false);
      onComplete?.();
    }, 450);
    return () => clearTimeout(timeout);
  }, [onComplete]);

  // Main animation timeline
  useEffect(() => {
    if (!mounted || exiting) return;

    // Timeline stages
    const t1 = setTimeout(() => {
      setStepIndex(1);
      setProgress(48);
    }, 320);

    const t2 = setTimeout(() => {
      setStepIndex(2);
      setProgress(82);
    }, 720);

    const t3 = setTimeout(() => {
      setStepIndex(3);
      setProgress(100);
    }, 1120);

    const t4 = setTimeout(() => {
      dismiss();
    }, 1600);

    return () => {
      clearTimeout(t1);
      clearTimeout(t2);
      clearTimeout(t3);
      clearTimeout(t4);
    };
  }, [mounted, exiting, dismiss]);

  // Keyboard shortcut listener to skip
  useEffect(() => {
    if (!mounted) return;
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape' || e.key === ' ' || e.key === 'Enter') {
        e.preventDefault();
        dismiss();
      }
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [mounted, dismiss]);

  // Replay intro event listener
  useEffect(() => {
    const handleReplay = () => {
      setMounted(true);
      setExiting(false);
      setStepIndex(0);
      setProgress(15);
    };
    window.addEventListener(REPLAY_EVENT, handleReplay);
    return () => window.removeEventListener(REPLAY_EVENT, handleReplay);
  }, []);

  if (!mounted) return null;

  return (
    <div
      role="status"
      aria-live="polite"
      aria-label="ClaimLens Engine Initialization"
      onClick={dismiss}
      className={cn(
        'fixed inset-0 z-[99999] flex flex-col items-center justify-center select-none overflow-hidden cursor-pointer',
        'bg-[#121412] graph-paper-ink text-[#e9ece4]',
        'transition-all duration-400 ease-out',
        exiting ? 'opacity-0 scale-[1.03] pointer-events-none' : 'opacity-100 scale-100',
      )}
    >
      {/* Corner Technical Identifiers */}
      <div className="absolute top-6 left-6 hidden sm:flex items-center gap-2 font-mono text-[11px] uppercase tracking-wider text-muted-on-ink pointer-events-none">
        <span className="inline-block w-1.5 h-1.5 bg-marker animate-pulse-dot" />
        <span>SYS // CLAIMLENS ENGINE</span>
      </div>

      <div className="absolute top-6 right-6 hidden sm:flex items-center gap-2 font-mono text-[11px] text-muted-on-ink tracking-wider pointer-events-none">
        <span>NVIDIA NEMOTRON · v0.1.0</span>
      </div>

      <div className="absolute bottom-6 left-6 hidden sm:flex items-center gap-2 font-mono text-[11px] text-muted-on-ink tracking-wider pointer-events-none">
        <span>HYBRID RETRIEVAL · EVIDENCE VERIFIER</span>
      </div>

      <div className="absolute bottom-6 right-6 flex items-center gap-2 pointer-events-auto">
        <button
          type="button"
          onClick={(e) => {
            e.stopPropagation();
            dismiss();
          }}
          className="font-mono text-[11px] uppercase tracking-wider text-muted-on-ink hover:text-marker hover:border-marker border border-rule-on-ink bg-[#181c17] px-3 py-1.5 transition-colors"
        >
          SKIP [ESC] ↵
        </button>
      </div>

      {/* Central Viewfinder Frame */}
      <div
        className={cn(
          'relative w-[90vw] max-w-[440px] border border-[#2e332d] bg-[#181c17]/95 p-7 sm:p-9 shadow-2xl backdrop-blur-md',
          'animate-bracket-in',
        )}
      >
        {/* Viewfinder Target Brackets (in highlighter yellow) */}
        <div className="absolute -top-1.5 -left-1.5 w-4 h-4 border-t-2 border-l-2 border-marker pointer-events-none" />
        <div className="absolute -top-1.5 -right-1.5 w-4 h-4 border-t-2 border-r-2 border-marker pointer-events-none" />
        <div className="absolute -bottom-1.5 -left-1.5 w-4 h-4 border-b-2 border-l-2 border-marker pointer-events-none" />
        <div className="absolute -bottom-1.5 -right-1.5 w-4 h-4 border-b-2 border-r-2 border-marker pointer-events-none" />

        {/* Dynamic Sweeping Scanline */}
        <div className="absolute inset-x-0 top-0 h-[2px] bg-gradient-to-r from-transparent via-marker to-transparent opacity-80 animate-scan-beam pointer-events-none" />

        {/* Logo and Brand Mark */}
        <div className="flex flex-col items-center text-center">
          <div className="relative mb-4 flex items-center justify-center">
            {/* Animated Logo Icon */}
            <svg
              width="48"
              height="48"
              viewBox="0 0 26 26"
              fill="none"
              aria-hidden="true"
              className="transform transition-transform duration-500 hover:scale-105"
            >
              <rect
                x="1"
                y="1"
                width="24"
                height="24"
                strokeWidth="1.5"
                className="stroke-on-ink"
              />
              <rect
                x="5"
                y="10"
                width="16"
                height="6"
                className="fill-marker transition-all duration-300"
              />
              <path d="M5 13h16" strokeWidth="1.5" className="stroke-ink" />
            </svg>
          </div>

          <h1 className="font-display text-[34px] sm:text-[40px] font-extrabold tracking-[-1px] text-on-ink leading-none">
            Claim<span className="bg-marker text-ink px-1.5 ml-0.5">Lens</span>
          </h1>

          <p className="mt-2 font-mono text-[11px] uppercase tracking-[1.4px] text-muted-on-ink">
            Scientific Paper & Claim Verification
          </p>
        </div>

        {/* Telemetry Progress Indicator */}
        <div className="mt-7 flex flex-col gap-2.5">
          {/* Diagnostic Step Readout */}
          <div className="flex items-center justify-between font-mono text-[11px] text-[#b9beb4]">
            <span className="truncate pr-2">{STEPS[stepIndex]}</span>
            <span className="font-semibold text-marker">{progress}%</span>
          </div>

          {/* Smooth Progress Bar */}
          <div className="h-[3px] w-full bg-[#2e332d] overflow-hidden">
            <div
              className="h-full bg-marker transition-all duration-300 ease-out"
              style={{ width: `${progress}%` }}
            />
          </div>

          {/* System Status Indicators */}
          <div className="mt-1 flex items-center justify-between font-mono text-[10px] text-muted-on-ink">
            <div className="flex items-center gap-1.5">
              <span
                className={cn(
                  'h-1.5 w-1.5 rounded-full transition-colors duration-300',
                  stepIndex === 3 ? 'bg-[#22c55e] animate-pulse-dot' : 'bg-marker',
                )}
              />
              <span className={stepIndex === 3 ? 'text-[#22c55e] font-semibold' : ''}>
                {stepIndex === 3 ? 'STATUS: ALL ENGINES OPERATIONAL' : 'STATUS: CALIBRATING PIPELINE'}
              </span>
            </div>
            <span className="hidden sm:inline">PARALLEL RERANK</span>
          </div>
        </div>
      </div>

      {/* Subtle bottom prompt */}
      <p className="mt-8 font-mono text-[11px] text-muted-on-ink/80 hover:text-on-ink transition-colors">
        Click anywhere to continue
      </p>
    </div>
  );
}
