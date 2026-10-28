import { useEffect, useMemo, useRef } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useDocuments } from '@/api/hooks';
import type { Document } from '@/api/types';
import { parseIds } from './format';

/** At most this many papers go into Ask, Compare or Conflicts when none are chosen. */
const DEFAULT_SCOPE = 2;

/** Only include ready papers (real uploaded DOC- or valid DOC stubs). */
const isRealPaper = (doc: Document) =>
  doc.status === 'ready' && (doc.document_id.startsWith('DOC-') || doc.document_id.startsWith('DOC'));

/**
 * The papers Ask, Compare and Conflicts work on, driven by ?docs=DOC-xxx,DOC-yyy.
 *
 * - On first load, seeds ?docs= with user's selected papers or top 2 papers.
 * - Whenever a new real paper finishes indexing (status flips to "ready"),
 *   it is automatically added to the scope so Ask/Compare/Conflicts pick it up.
 */
export function useScope() {
  const documents = useDocuments();
  const [params, setParams] = useSearchParams();
  const raw = params.get('docs');
  const initialized = useRef(false);
  const knownReadyIds = useRef<Set<string>>(new Set());

  useEffect(() => {
    if (!documents.data) return;

    const readyIds = documents.data
      .filter((doc) => doc.status === 'ready' && isRealPaper(doc))
      .map((doc) => doc.document_id);

    if (readyIds.length === 0) return;

    // First time documents data arrives:
    if (!initialized.current) {
      initialized.current = true;
      readyIds.forEach((id) => knownReadyIds.current.add(id));

      // Seed ?docs= only when empty/null
      if (params.get('docs') === null) {
        let seedIds = readyIds.slice(0, DEFAULT_SCOPE);
        try {
          const saved = sessionStorage.getItem('claimlens_selected_docs');
          if (saved) {
            const parsed = JSON.parse(saved);
            const valid = parsed.filter((id: string) => readyIds.includes(id));
            if (valid.length >= 2) seedIds = valid.slice(0, 4);
          }
        } catch {
          // ignore
        }
        setParams(
          (prev) => {
            const next = new URLSearchParams(prev);
            next.set('docs', seedIds.join(','));
            return next;
          },
          { replace: true },
        );
      }
      return;
    }

    // Subsequent updates (e.g. newly uploaded paper finished indexing):
    const newlyReady = readyIds.filter((id) => !knownReadyIds.current.has(id));
    if (newlyReady.length > 0) {
      newlyReady.forEach((id) => knownReadyIds.current.add(id));
      setParams(
        (prev) => {
          const next = new URLSearchParams(prev);
          const current = parseIds(prev.get('docs'));
          // Add new papers to scope without capping (user can remove from Library)
          const merged = [...new Set([...current, ...newlyReady])];
          next.set('docs', merged.join(','));
          return next;
        },
        { replace: true },
      );
    }
  }, [documents.data, params, setParams]);

  return useMemo(() => {
    const byId = new Map((documents.data ?? []).map((doc) => [doc.document_id, doc]));
    const ids = parseIds(raw);
    const docs = ids.map((id) => byId.get(id)).filter((doc): doc is Document => Boolean(doc));
    const ready = docs.filter((doc) => doc.status === 'ready' && isRealPaper(doc));
    return {
      ids,
      docs,
      ready,
      byId,
      isLoading: documents.isLoading || (raw === null && !documents.error),
      error: documents.error,
      refetch: documents.refetch,
    };
  }, [documents.data, documents.error, documents.isLoading, documents.refetch, raw]);
}
