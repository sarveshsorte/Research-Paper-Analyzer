import { useEffect, useId, type MouseEvent } from 'react';
import { useJobStream } from '@/api/sse';
import type { QueryResult } from '@/api/types';
import { Card } from '@/components/Card';
import { CitationChip } from '@/components/CitationChip';
import { ErrorBanner } from '@/components/ErrorBanner';
import { Mark } from '@/components/Mark';
import { SectionLabel } from '@/components/SectionLabel';
import { Skeleton } from '@/components/Skeleton';
import { StatusTag } from '@/components/StatusTag';
import type { EvidenceTarget } from '@/features/evidence/useEvidenceViewer';
import { citedNumbers, evidenceFor, parseAnswer } from './answer';

export interface AskEntry {
  jobId: string;
  question: string;
  askedAt: string;
}

interface AnswerBlockProps {
  entry: AskEntry;
  /** Paper ids in scope order: [n] cites scope[n - 1]. */
  scope: string[];
  first: boolean;
  onOpen: (target: EvidenceTarget, trigger: HTMLElement) => void;
  onSettled: (jobId: string) => void;
  onRetry: (question: string) => void;
}

const time = (iso: string) =>
  new Date(iso).toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' });

/** One question and its answer card (artboard "03 · Ask"). */
export function AnswerBlock({ entry, scope, first, onOpen, onSettled, onRetry }: AnswerBlockProps) {
  const headingId = useId();
  const stream = useJobStream<QueryResult>(entry.jobId);
  const { status, result, steps } = stream;

  useEffect(() => {
    if (status === 'done' || status === 'error') onSettled(entry.jobId);
  }, [status, entry.jobId, onSettled]);

  const parts = result ? parseAnswer(result.answer, result.highlights) : [];
  const grounded = citedNumbers(parts).length;
  const Heading = first ? 'h1' : 'h2';

  // The artboard sizes the answer card content-box: 760px + padding + border = 815px.
  return (
    <article aria-labelledby={headingId} className="flex max-w-[815px] flex-col gap-6">
      <div className="flex max-w-[760px] flex-col gap-1.5">
        <p className="font-mono text-label uppercase text-muted">Q · {time(entry.askedAt)}</p>
        <Heading
          id={headingId}
          className="font-display text-[26px] font-bold leading-[1.15] tracking-[-0.6px] md:text-[32px]"
        >
          {entry.question}
        </Heading>
      </div>

      {status === 'error' ? (
        <ErrorBanner
          title="No answer"
          code={stream.error?.code}
          message={stream.error?.message ?? 'The question could not be answered.'}
          onRetry={() => onRetry(entry.question)}
          retryLabel="Ask again"
        />
      ) : (
        <Card
          padding="none"
          className="flex flex-col gap-[18px] px-5 py-5 md:px-[26px] md:py-6"
          aria-busy={!result || undefined}
        >
          {!result ? (
            <>
              <SectionLabel>Answering…</SectionLabel>
              <ol
                aria-live="polite"
                className="flex flex-col gap-1.5 font-mono text-[12px] text-muted"
              >
                {steps.map((step, index) => (
                  <li key={`${index}-${step.message}`} className="flex items-center gap-2">
                    <span aria-hidden="true" className="h-1.5 w-1.5 shrink-0 bg-ink" />
                    {step.message}
                  </li>
                ))}
                <li className="flex items-center gap-2">
                  <span
                    aria-hidden="true"
                    className="h-1.5 w-1.5 shrink-0 bg-marker motion-safe:animate-pulse"
                  />
                  Working…
                </li>
              </ol>
              <div aria-hidden="true" className="flex flex-col gap-2">
                <Skeleton height={17} />
                <Skeleton width="92%" height={17} />
                <Skeleton width="60%" height={17} />
              </div>
            </>
          ) : (
            <>
              <SectionLabel>
                Answer · grounded in {grounded} paper{grounded === 1 ? '' : 's'}
              </SectionLabel>
              <p className="text-[17px] leading-[1.65]">
                {parts.map((part, index) => {
                  if (part.kind === 'text') return part.text;
                  if (part.kind === 'mark') return <Mark key={index}>{part.text}</Mark>;
                  const doc = scope[part.n - 1];
                  const evidence = evidenceFor(result, doc);
                  return (
                    <CitationChip
                      key={index}
                      n={part.n}
                      page={evidence?.page}
                      tone={evidence ? 'support' : 'neutral'}
                      onClick={(event: MouseEvent<HTMLButtonElement>) => {
                        if (!doc) return;
                        onOpen(
                          {
                            doc,
                            page: evidence?.page ?? 1,
                            chunk: evidence?.chunk_id,
                            n: part.n,
                            quote: evidence?.quote,
                          },
                          event.currentTarget,
                        );
                      }}
                    />
                  );
                })}
              </p>
              {result.claims.length > 0 && (
                <div className="flex flex-col gap-2.5 border-t border-dashed border-rule-dashed pt-3.5">
                  <SectionLabel>Claims in this answer</SectionLabel>
                  <ul className="flex flex-col gap-2.5">
                    {result.claims.map((claim) => (
                      <li key={claim.claim} className="flex flex-wrap items-center gap-2.5">
                        <StatusTag status={claim.status} />
                        <span className="text-[15px]">{claim.claim}</span>
                        <span className="font-mono text-[12px] text-muted">
                          <span className="sr-only">Confidence </span>
                          {claim.status === 'INSUFFICIENT_EVIDENCE'
                            ? '—'
                            : claim.confidence.toFixed(2)}
                        </span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </>
          )}
        </Card>
      )}
    </article>
  );
}
