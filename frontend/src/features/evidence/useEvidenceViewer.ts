import { useCallback, useMemo } from 'react';
import { useSearchParams } from 'react-router-dom';

export interface EvidenceTarget {
  doc: string;
  page: number;
  chunk?: string;
  /** Short verbatim quote to highlight on the PDF page (the evidence snippet, not the full chunk). */
  quote?: string;
  /** Citation number shown in the header: "Evidence viewer · [2]". */
  n?: number;
}

const KEYS = ['doc', 'page', 'chunk', 'cite', 'q'] as const;

// The element that opened the viewer, so closing can return focus to it.
let lastTrigger: HTMLElement | null = null;

/**
 * Evidence viewer state, kept in the URL (?doc=DOC002&page=8&chunk=DOC002_CH042&cite=2) so a
 * citation can be shared. Other query params (docs, sel, job) are preserved.
 */
export function useEvidenceViewer() {
  const [params, setParams] = useSearchParams();
  const doc = params.get('doc');
  const page = Number(params.get('page')) || 1;
  const chunk = params.get('chunk') ?? undefined;
  const cite = Number(params.get('cite')) || undefined;
  const quote = params.get('q') ?? undefined;

  const target = useMemo<EvidenceTarget | null>(
    () => (doc ? { doc, page, chunk, quote, n: cite } : null),
    [doc, page, chunk, quote, cite],
  );

  const open = useCallback(
    (next: EvidenceTarget, trigger?: HTMLElement | null) => {
      lastTrigger = trigger ?? (document.activeElement as HTMLElement | null);
      setParams((prev) => {
        const updated = new URLSearchParams(prev);
        updated.set('doc', next.doc);
        updated.set('page', String(next.page));
        if (next.chunk) updated.set('chunk', next.chunk);
        else updated.delete('chunk');
        if (next.n) updated.set('cite', String(next.n));
        else updated.delete('cite');
        if (next.quote) updated.set('q', next.quote);
        else updated.delete('q');
        return updated;
      });
    },
    [setParams],
  );

  const close = useCallback(() => {
    setParams((prev) => {
      const updated = new URLSearchParams(prev);
      for (const key of KEYS) updated.delete(key);
      return updated;
    });
    const trigger = lastTrigger;
    lastTrigger = null;
    // After the viewer unmounts, put focus back on the citation that opened it.
    requestAnimationFrame(() => {
      if (trigger?.isConnected) trigger.focus();
    });
  }, [setParams]);

  const setPage = useCallback(
    (nextPage: number) =>
      setParams(
        (prev) => {
          const updated = new URLSearchParams(prev);
          updated.set('page', String(nextPage));
          return updated;
        },
        { replace: true },
      ),
    [setParams],
  );

  return { target, open, close, setPage };
}
