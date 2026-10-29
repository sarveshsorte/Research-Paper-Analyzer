// Loaded lazily: this module pulls in react-pdf and pdf.js.
import { useCallback, useEffect, useMemo, useState } from 'react';
import { Document, Page, pdfjs } from 'react-pdf';
import type { CustomTextRenderer } from 'react-pdf/dist/shared/types.js';
import workerUrl from 'pdfjs-dist/build/pdf.worker.min.mjs?url';
import 'react-pdf/dist/Page/TextLayer.css';
import { findQuote, renderTextItem, type QuoteMatch } from './textMatch';

pdfjs.GlobalWorkerOptions.workerSrc = workerUrl;

// Stable reference: react-pdf reloads the document when `options` changes identity.
const OPTIONS = { standardFontDataUrl: '/standard_fonts/' };

export interface PdfPageProps {
  data: Uint8Array;
  pageNumber: number;
  width: number;
  /** Text to find and highlight on this page. */
  quote?: string;
  onMatch: (kind: QuoteMatch['kind']) => void;
  onPageCount: (pages: number) => void;
  onError: () => void;
}

/** One PDF page with its text layer, the quote highlighted (marker + 2px ink outline). */
export default function PdfPage({
  data,
  pageNumber,
  width,
  quote,
  onMatch,
  onPageCount,
  onError,
}: PdfPageProps) {
  // pdf.js transfers the buffer to its worker, so hand it a copy and keep the cached bytes.
  const file = useMemo(() => ({ data: data.slice() }), [data]);
  const [match, setMatch] = useState<QuoteMatch | null>(null);

  // Reset highlight whenever the visible page or the target quote changes.
  useEffect(() => {
    setMatch(null);
  }, [pageNumber, quote]);

  const ranges = useMemo(
    () => new Map((match?.ranges ?? []).map((range) => [range.item, range])),
    [match],
  );
  const textRenderer = useCallback<CustomTextRenderer>(
    ({ str, itemIndex }) => renderTextItem(str, ranges.get(itemIndex)),
    [ranges],
  );

  return (
    <Document
      file={file}
      options={OPTIONS}
      loading={null}
      error={null}
      onLoadSuccess={(pdf) => {
        onPageCount(pdf.numPages);
        if (pageNumber > pdf.numPages || pageNumber < 1) {
          onError();
        }
      }}
      onLoadError={onError}
    >
      <Page
        key={pageNumber}
        pageNumber={pageNumber}
        width={width}
        renderAnnotationLayer={false}
        loading={null}
        error={null}
        onLoadError={onError}
        onRenderError={onError}
        customTextRenderer={textRenderer}
        onGetTextSuccess={({ items }) => {
          const next = findQuote(
            items.map((item) => ('str' in item ? item.str : '')),
            quote,
          );
          setMatch(next);
          onMatch(next.kind);
        }}
      />
    </Document>
  );
}
