import { act, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { EntryAnimation, replayEntryAnimation } from './EntryAnimation';

describe('EntryAnimation', () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('renders the entry splash screen with brand and progress indicators', () => {
    render(<EntryAnimation />);

    expect(screen.getByRole('status')).toBeInTheDocument();
    expect(screen.getByText('Claim')).toBeInTheDocument();
    expect(screen.getByText('Lens')).toBeInTheDocument();
    expect(screen.getByText(/Scientific Paper & Claim Verification/i)).toBeInTheDocument();
    expect(screen.getByText(/INITIALIZING/i)).toBeInTheDocument();
  });

  it('progresses through initialization stages over time and exits', () => {
    const onComplete = vi.fn();
    render(<EntryAnimation onComplete={onComplete} />);

    // Step 0 -> Step 1 (at 320ms)
    act(() => {
      vi.advanceTimersByTime(350);
    });
    expect(screen.getByText(/LOADING HYBRID RETRIEVAL/i)).toBeInTheDocument();

    // Step 2 (at 720ms)
    act(() => {
      vi.advanceTimersByTime(400);
    });
    expect(screen.getByText(/CONNECTING NVIDIA NEMOTRON/i)).toBeInTheDocument();

    // Step 3 (at 1120ms)
    act(() => {
      vi.advanceTimersByTime(400);
    });
    expect(screen.getByText(/CLAIMLENS SYSTEM ONLINE/i)).toBeInTheDocument();

    // Dismissal and unmount (after 1600ms + 450ms)
    act(() => {
      vi.advanceTimersByTime(900);
    });
    expect(onComplete).toHaveBeenCalled();
    expect(screen.queryByRole('status')).not.toBeInTheDocument();
  });

  it('dismisses immediately when clicking the skip button', () => {
    const onComplete = vi.fn();
    render(<EntryAnimation onComplete={onComplete} />);

    const skipButton = screen.getByRole('button', { name: /skip/i });
    fireEvent.click(skipButton);

    act(() => {
      vi.advanceTimersByTime(500);
    });
    expect(onComplete).toHaveBeenCalled();
    expect(screen.queryByRole('status')).not.toBeInTheDocument();
  });

  it('dismisses when pressing Escape', () => {
    const onComplete = vi.fn();
    render(<EntryAnimation onComplete={onComplete} />);

    fireEvent.keyDown(window, { key: 'Escape' });

    act(() => {
      vi.advanceTimersByTime(500);
    });
    expect(onComplete).toHaveBeenCalled();
    expect(screen.queryByRole('status')).not.toBeInTheDocument();
  });

  it('re-renders when replayEntryAnimation is called', () => {
    const { unmount } = render(<EntryAnimation autoPlay={false} />);
    expect(screen.queryByRole('status')).not.toBeInTheDocument();

    act(() => {
      replayEntryAnimation();
    });

    expect(screen.getByRole('status')).toBeInTheDocument();
    unmount();
  });
});
