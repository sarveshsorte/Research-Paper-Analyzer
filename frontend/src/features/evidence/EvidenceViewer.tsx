import { Suspense, lazy, useEffect, useState } from 'react';
import { useChunk, useDocument, useDocumentFile } from '@/api/hooks';
import { Button } from '@/components/Button';
import { CloseIcon } from '@/components/icons';
import { PdfPagePlaceholder } from '@/components/PdfPagePlaceholder';
import { useElementWidth } from '@/lib/useElementWidth';
import type { QuoteMatch } from './textMatch';
import type { EvidenceTarget } from './useEvidenceViewer';

const PdfPage = lazy(() => import('./PdfPage'));

/** US Letter height / width, to reserve the page's space while it renders. */
const PAGE_RATIO = 792 / 612;

export interface PaperMeta {
  title: string;
  authors?: string;
  year?: number;
}

interface EvidenceViewerProps {
  target: EvidenceTarget;
  meta?: PaperMeta;
  titleId: string;
  onClose: () => void;
  onPageChange: (page: number) => void;
}

const STATUS: Record<QuoteMatch['kind'], string> = {
  exact: '✓ quote found on page',
  approximate: '≈ approximate match',
  none: 'Quote not found on this page',
};

/**
 * The dark Evidence viewer (Ask artboard): paper, the cited PDF page with the sentence
 * highlighted, page navigation and whether the quote was found. Used inline on Ask and as a
 * drawer elsewhere (EvidenceDrawer).
 */
export function EvidenceViewer({
  target,
  meta,
  titleId,
  onClose,
  onPageChange,
}: EvidenceViewerProps) {
  const detail = useDocument(target.doc);
  const chunk = useChunk(target.chunk);
  const file = useDocumentFile(target.doc);
  const [pageCount, setPageCount] = useState<number>();
  const [match, setMatch] = useState<{ key: string; kind: QuoteMatch['kind'] } | null>(null);
  const [pdfFailed, setPdfFailed] = useState(false);
  const { ref, width } = useElementWidth<HTMLDivElement>();

  useEffect(() => {
    setPdfFailed(false);
  }, [target.doc, target.page]);

  const pages = pageCount ?? detail.data?.pages;
  const citedPage = chunk.data?.page ?? target.page;
  const onCitedPage = target.page === citedPage;
  // Prefer the short snippet from the evidence result; fall back to full chunk text.
  const quote = onCitedPage
    ? (target.quote || (chunk.data?.text ? chunk.data.text.slice(0, 200) : undefined))
    : undefined;
  const matchKey = `${target.doc}:${target.page}:${target.chunk ?? ''}`;
  const matchKind = match?.key === matchKey ? match.kind : undefined;

  let status = '';
  if (target.chunk && !onCitedPage) status = `Cited passage is on p. ${citedPage}`;
  else if (target.chunk && matchKind) status = STATUS[matchKind];
  else if (target.chunk && file.data && !pdfFailed) status = 'Finding the quote…';

  const metaLine = [
    meta?.authors,
    meta?.year,
    chunk.data?.section,
    target.chunk && `chunk ${target.chunk}`,
  ]
    .filter(Boolean)
    .join(' · ');

  const placeholder = (
    <PdfPagePlaceholder
      page={target.page}
      runningHead={chunk.data?.section?.replace(/^§/, '').toUpperCase()}
      highlight={quote}
    />
  );

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between gap-3">
        <h2
          id={titleId}
          className="font-mono text-[13px] font-semibold uppercase tracking-[0.6px] text-marker"
        >
          Evidence viewer{target.n ? ` · [${target.n}]` : ''}
        </h2>
        <button
          type="button"
          aria-label="Close evidence viewer"
          onClick={onClose}
          className="flex h-9 w-9 shrink-0 items-center justify-center border border-muted text-on-ink hover:border-on-ink"
        >
          <CloseIcon size={16} />
        </button>
      </div>

      <div className="flex flex-col gap-1">
        <p className="text-[17px] font-bold">{meta?.title ?? target.doc}</p>
        {metaLine && <p className="font-mono text-[12px] text-muted-on-ink">{metaLine}</p>}
      </div>

      <div ref={ref} className="evidence-pdf">
        {file.data && !pdfFailed && width > 0 ? (
          <div
            className="bg-sheet shadow-page"
            style={{ minHeight: Math.round(width * PAGE_RATIO) }}
          >
            <Suspense fallback={placeholder}>
              <PdfPage
                data={file.data}
                pageNumber={target.page}
                width={width}
                quote={quote}
                onMatch={(kind) => setMatch({ key: matchKey, kind })}
                onPageCount={setPageCount}
                onError={() => setPdfFailed(true)}
              />
            </Suspense>
          </div>
        ) : (
          placeholder
        )}
        {(file.isError || pdfFailed) && (
          <p className="mt-3 font-mono text-[12px] text-muted-on-ink">
            Could not load the PDF; showing the cited passage only.
          </p>
        )}
      </div>

      <div className="flex flex-wrap items-center justify-between gap-3 font-mono text-[12px]">
        <div className="flex gap-1.5">
          <Button
            variant="ghost-on-ink"
            aria-label={`Previous page p.${target.page - 1}`}
            disabled={target.page <= 1}
            onClick={() => onPageChange(target.page - 1)}
          >
            ← p.{Math.max(1, target.page - 1)}
          </Button>
          <span
            aria-live="polite"
            className="inline-flex items-center border border-marker px-2.5 text-marker"
          >
            <span className="sr-only">Page </span>p. {target.page}
            {pages ? ` / ${pages}` : ''}
          </span>
          <Button
            variant="ghost-on-ink"
            aria-label={`Next page p.${target.page + 1}`}
            disabled={pages !== undefined && target.page >= pages}
            onClick={() => onPageChange(target.page + 1)}
          >
            p.{target.page + 1} →
          </Button>
        </div>
        {status && <span className="text-muted-on-ink">{status}</span>}
      </div>
    </div>
  );
}
