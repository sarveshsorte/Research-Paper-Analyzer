import { Fragment, useState, type MouseEvent } from 'react';
import { startCompare, useCachedJob } from '@/api/hooks';
import type { CompareResult, Document } from '@/api/types';
import { Button, ButtonLink } from '@/components/Button';
import { Checkbox } from '@/components/Checkbox';
import { EmptyState } from '@/components/EmptyState';
import { ErrorBanner } from '@/components/ErrorBanner';
import { JobProgress } from '@/components/JobProgress';
import { Mark } from '@/components/Mark';
import { PageContainer } from '@/components/PageContainer';
import { Skeleton } from '@/components/Skeleton';
import { EvidenceDrawer } from '@/features/evidence/EvidenceDrawer';
import { useEvidenceViewer } from '@/features/evidence/useEvidenceViewer';
import { useScope } from '@/features/library/useScope';
import { useDocumentTitle } from '@/lib/useDocumentTitle';
import { cellWhere, downloadText, rowDiffers, toCsv } from './compareTable';

function Summary({ differing }: { differing: string[] }) {
  if (differing.length === 0) return <>They agree on every attribute. </>;
  const marks = differing.map((name) => <Mark key={name}>{name.toLowerCase()}</Mark>);
  return (
    <>
      They differ on{' '}
      {marks.map((mark, i) => (
        <Fragment key={differing[i]}>
          {i > 0 && (i === marks.length - 1 ? ' and ' : ', ')}
          {mark}
        </Fragment>
      ))}
      .{' '}
    </>
  );
}

/** /compare?docs=… (artboard "04 · Compare"). */
export function ComparePage() {
  useDocumentTitle('Compare');
  const scope = useScope();
  const viewer = useEvidenceViewer();
  const [highlight, setHighlight] = useState(true);
  const docs: Document[] = scope.ready;
  const ids = docs.map((doc) => doc.document_id);
  const enabled = ids.length >= 2;
  const job = useCachedJob<CompareResult>(
    ['compare', ids.join(',')],
    () => startCompare({ document_ids: ids }),
    enabled,
  );
  const rows = job.result ?? [];
  const differing = rows.filter((row) => rowDiffers(row, ids)).map((row) => row.attribute);
  const papers = Object.fromEntries(
    docs.map((doc) => [
      doc.document_id,
      { title: doc.title, authors: doc.authors, year: doc.year },
    ]),
  );

  if (!scope.isLoading && !scope.error && !enabled) {
    return (
      <PageContainer>
        <h1 className="font-display text-claim font-extrabold md:text-h1">Compare</h1>
        <EmptyState
          title="Select at least two ready papers"
          description="Compare lines papers up attribute by attribute: method, model, benchmark, metric and results. Every cell links to its page."
          action={<ButtonLink to="/library">Go to Library</ButtonLink>}
        />
      </PageContainer>
    );
  }

  const exportCsv = () => downloadText('claimlens-compare.csv', toCsv(rows, docs));

  return (
    <PageContainer>
      <div className="flex flex-wrap items-end gap-4">
        <div className="flex min-w-0 flex-[1_1_520px] flex-col gap-2">
          <div className="flex items-center gap-3">
            <p className="font-mono text-label uppercase text-muted">
              {ids.length} papers{job.result ? ` · ${rows.length} attributes` : ''}
            </p>
            <ButtonLink
              variant="secondary"
              to={`/library?sel=${ids.join(',')}`}
              className="text-[11px] font-mono py-0.5 px-2.5 h-auto min-h-0"
            >
              Change papers
            </ButtonLink>
          </div>
          <h1 className="font-display text-claim font-extrabold md:text-h1">Compare</h1>
          <p className="text-[16px] text-ink-2">
            {job.result ? <Summary differing={differing} /> : 'Reading the papers side by side. '}
            Every cell links to the sentence it came from.
          </p>
        </div>
        <Checkbox
          boxed
          label="Highlight differences"
          checked={highlight}
          onChange={(event) => setHighlight(event.target.checked)}
        />
        <Button variant="secondary" onClick={exportCsv} disabled={!job.result}>
          Export CSV
        </Button>
      </div>

      {scope.error ? (
        <ErrorBanner
          title="Could not load your papers"
          message={scope.error.message}
          onRetry={() => void scope.refetch()}
        />
      ) : job.status === 'error' ? (
        <ErrorBanner
          title="The comparison stopped"
          code={job.error?.code}
          message={job.error?.message ?? 'Something went wrong.'}
          onRetry={job.restart}
        />
      ) : !job.result ? (
        scope.isLoading ? (
          <Skeleton height={320} />
        ) : (
          <JobProgress label={`Comparing ${ids.length} papers…`} steps={job.steps} />
        )
      ) : (
        // relative: visually hidden (absolute) text in cells must scroll with the table, not
        // widen the page.
        <section
          aria-label="Comparison"
          className="relative overflow-x-auto border-1.5 border-ink bg-sheet"
        >
          <table className="w-full min-w-[900px] border-collapse text-[15px]">
            <thead>
              <tr className="text-left align-bottom">
                <th
                  scope="col"
                  className="w-[230px] border-b-1.5 border-ink px-5 py-[18px] font-mono text-[12px] font-medium uppercase tracking-[0.6px] text-muted"
                >
                  Attribute
                </th>
                {docs.map((doc, index) => (
                  <th
                    key={doc.document_id}
                    scope="col"
                    className="border-b-1.5 border-l border-ink border-l-rule px-5 py-[18px]"
                  >
                    <div className="font-mono text-[12px] text-support">[{index + 1}]</div>
                    <div className="text-[16px] font-bold">{doc.title}</div>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => {
                const differs = rowDiffers(row, ids);
                return (
                  <tr key={row.attribute} className="border-t border-rule align-top">
                    <th
                      scope="row"
                      className="px-5 py-4 text-left font-mono text-[12px] font-semibold uppercase tracking-[0.6px]"
                    >
                      {row.attribute}
                      {highlight && differs && (
                        <span className="mt-1.5 block w-max bg-marker px-1.5 py-px text-[11px]">
                          differs
                        </span>
                      )}
                    </th>
                    {docs.map((doc) => {
                      const cell = row.values[doc.document_id];
                      return (
                        <td key={doc.document_id} className="border-l border-rule px-5 py-4">
                          {cell ? (
                            <>
                              <div>{cell.value}</div>
                              <button
                                type="button"
                                className="font-mono text-[12px] text-muted underline hover:text-support"
                                onClick={(event: MouseEvent<HTMLButtonElement>) =>
                                  viewer.open(
                                    {
                                      doc: doc.document_id,
                                      page: cell.page ?? 1,
                                      chunk: cell.chunk_id,
                                      quote: cell.quote,
                                    },
                                    event.currentTarget,
                                  )
                                }
                              >
                                {cellWhere(cell) || 'Open page'}
                                <span className="sr-only">, open in {doc.title}</span>
                              </button>
                            </>
                          ) : (
                            <span className="text-muted">Not reported</span>
                          )}
                        </td>
                      );
                    })}
                  </tr>
                );
              })}
            </tbody>
          </table>
        </section>
      )}

      <EvidenceDrawer papers={papers} />
    </PageContainer>
  );
}
