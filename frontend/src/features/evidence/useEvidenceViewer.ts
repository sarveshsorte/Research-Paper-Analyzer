import { useCallback, useMemo } from 'react';
import { useSearchParams } from 'react-router-dom';

export interface EvidenceTarget {
  doc: string;
  page: number;
  chunk?: string;
  /** Citation number shown in the header: "Evidence viewer · [2]". */
  n?: number;
  /** The cited words to highlight. Without it the whole chunk is highlighted. */
  quote?: string;
}

const KEYS = ['doc', 'page', 'chunk', 'cite'] as const;

// The element that opened the viewer, so closing can return focus to it.
let lastTrigger: HTMLElement | null = null;

// Quotes of opened citations by chunk id. The URL keeps only ids, so after a reload the
// viewer falls back to highlighting the chunk.
const quotes = new Map<string, string>();

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

  const target = useMemo<EvidenceTarget | null>(
    () =>
      doc ? { doc, page, chunk, n: cite, quote: chunk ? quotes.get(chunk) : undefined } : null,
    [doc, page, chunk, cite],
  );

  const open = useCallback(
    (next: EvidenceTarget, trigger?: HTMLElement | null) => {
      lastTrigger = trigger ?? (document.activeElement as HTMLElement | null);
      if (next.chunk && next.quote) quotes.set(next.chunk, next.quote);
      setParams((prev) => {
        const updated = new URLSearchParams(prev);
        updated.set('doc', next.doc);
        updated.set('page', String(next.page));
        if (next.chunk) updated.set('chunk', next.chunk);
        else updated.delete('chunk');
        if (next.n) updated.set('cite', String(next.n));
        else updated.delete('cite');
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
