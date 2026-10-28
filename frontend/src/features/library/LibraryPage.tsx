import { useMemo, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useDeleteDocument, useDocuments, useRetryDocument } from '@/api/hooks';
import type { Document } from '@/api/types';
import { Button, ButtonLink } from '@/components/Button';
import { ConfirmDialog } from '@/components/ConfirmDialog';
import { EmptyState } from '@/components/EmptyState';
import { ErrorBanner } from '@/components/ErrorBanner';
import { PageContainer } from '@/components/PageContainer';
import { Skeleton } from '@/components/Skeleton';
import { useDocumentTitle } from '@/lib/useDocumentTitle';
import { DropZone } from './DropZone';
import { parseIds } from './format';
import { PapersTable } from './PapersTable';

/** /library (artboard "02 · Library"). Selection lives in ?sel=DOC001,DOC002. */
export function LibraryPage() {
  useDocumentTitle('Library');
  const documents = useDocuments();
  const retry = useRetryDocument();
  const remove = useDeleteDocument();
  const [params, setParams] = useSearchParams();
  const navigate = useNavigate();
  const [pendingDelete, setPendingDelete] = useState<{ doc: Document; trigger: HTMLElement }>();

  const docs = useMemo(() => documents.data ?? [], [documents.data]);
  const readyIds = docs.filter((doc) => doc.status === 'ready').map((doc) => doc.document_id);
  // No ?sel= means "all ready papers"; once the user changes it, ?sel= holds the exact list.
  const selected = params.has('sel') ? parseIds(params.get('sel')) : readyIds;
  const selectedReady = selected.filter((id) => readyIds.includes(id));
  const canAct = selectedReady.length >= 2;
  const docsQuery = `docs=${selectedReady.join(',')}`;

  const setSelection = (ids: string[]) => {
    try {
      sessionStorage.setItem('claimlens_selected_docs', JSON.stringify(ids));
    } catch {
      // ignore
    }
    setParams(
      (prev) => {
        const next = new URLSearchParams(prev);
        next.set('sel', ids.join(','));
        return next;
      },
      { replace: true },
    );
  };

  const toggle = (id: string, checked: boolean) =>
    setSelection(checked ? [...selectedReady, id] : selectedReady.filter((x) => x !== id));

  const confirmDelete = () => {
    if (!pendingDelete) return;
    const id = pendingDelete.doc.document_id;
    remove.mutate(id, {
      onSuccess: () => {
        if (params.has('sel')) setSelection(selected.filter((x) => x !== id));
      },
      onSettled: () => setPendingDelete(undefined),
    });
  };

  const hint = 'Select two or more ready papers.';

  return (
    <PageContainer>
      <div className="flex flex-wrap items-end gap-4">
        <div className="flex min-w-0 flex-[1_1_480px] flex-col gap-1.5">
          <p className="font-mono text-label uppercase text-muted">Your papers</p>
          <h1 className="font-display text-claim font-extrabold md:text-h1">Library</h1>
        </div>
        <span id="library-actions-hint" className="sr-only">
          {canAct ? '' : hint}
        </span>
        {canAct ? (
          // A <button> in the artboard (unlike the Ask link beside it), so it navigates on click.
          <Button variant="secondary" onClick={() => navigate(`/compare?${docsQuery}`)}>
            Compare {selectedReady.length} selected
          </Button>
        ) : (
          <Button variant="secondary" disabled aria-describedby="library-actions-hint" title={hint}>
            Compare {selectedReady.length} selected
          </Button>
        )}
        {canAct ? (
          <ButtonLink to={`/ask?${docsQuery}`}>
            Ask across {selectedReady.length} papers →
          </ButtonLink>
        ) : (
          <Button disabled aria-describedby="library-actions-hint" title={hint}>
            Ask across {selectedReady.length} papers →
          </Button>
        )}
      </div>

      <DropZone />

      {documents.isLoading ? (
        <div aria-busy="true" className="flex flex-col gap-3 border-1.5 border-ink bg-sheet p-5">
          <span className="sr-only">Loading papers…</span>
          {[0, 1, 2].map((row) => (
            <Skeleton key={row} height={44} />
          ))}
        </div>
      ) : documents.error ? (
        <ErrorBanner
          title="Could not load your papers"
          message={documents.error.message}
          onRetry={() => void documents.refetch()}
        />
      ) : docs.length === 0 ? (
        <EmptyState
          title="No papers yet"
          description="Upload PDFs above. They appear here while they are indexed, and you can ask, compare or find conflicts once two are ready."
        />
      ) : (
        <PapersTable
          documents={docs}
          selected={new Set(selectedReady)}
          onToggle={toggle}
          onRetry={(id) => retry.mutate(id)}
          onDelete={(doc, trigger) => setPendingDelete({ doc, trigger })}
        />
      )}

      {pendingDelete && (
        <ConfirmDialog
          title={`Delete “${pendingDelete.doc.title}”?`}
          message="It leaves your library and any comparison that uses it. This cannot be undone."
          confirmLabel="Delete paper"
          busy={remove.isPending}
          onConfirm={confirmDelete}
          onCancel={() => setPendingDelete(undefined)}
        />
      )}
    </PageContainer>
  );
}
