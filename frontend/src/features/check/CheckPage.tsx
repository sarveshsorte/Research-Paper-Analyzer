import { useQueryClient } from '@tanstack/react-query';
import { useEffect, useMemo, useState, type KeyboardEvent } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { useStartCheck } from '@/api/hooks';
import { ApiError } from '@/api/client';
import { jobKey, useJobStream, type JobStreamState } from '@/api/sse';
import type { CheckResult, Evidence } from '@/api/types';
import { Button } from '@/components/Button';
import { Card } from '@/components/Card';
import { EmptyState } from '@/components/EmptyState';
import { ErrorBanner } from '@/components/ErrorBanner';
import { PageContainer } from '@/components/PageContainer';
import { TextArea } from '@/components/TextArea';
import { VerdictBand } from '@/components/VerdictBand';
import { EvidenceDrawer } from '@/features/evidence/EvidenceDrawer';
import { useEvidenceViewer } from '@/features/evidence/useEvidenceViewer';
import { sourceLabel } from '@/features/library/format';
import { cn } from '@/lib/cn';
import { useDocumentTitle } from '@/lib/useDocumentTitle';
import { DEFAULT_SOURCE_SETTINGS, EditSources } from './EditSources';
import { EvidenceColumns, EvidenceColumnsSkeleton } from './EvidenceColumns';
import { addRecentCheck, completeRecentCheck, useRecentChecks } from './recentChecks';
import { TraceRail } from './TraceRail';
import { verdictCounts, verdictLabel } from './verdict';

/** The claim on the Claim check artboard; pre-filled so the demo is one click away. */
export const DEMO_CLAIM = '“LoRA matches full fine-tuning on math and coding benchmarks.”';

const checkNumber = (jobId: string) => `#${jobId.replace(/^job_/, '')}`;

function sourceChips(result: CheckResult): string[] {
  if (result.sources?.length) return result.sources.map((s) => `${s.name} · ${s.count}`);
  const counts = new Map<string, number>();
  for (const paper of result.papers) {
    const label = sourceLabel(paper);
    counts.set(label, (counts.get(label) ?? 0) + 1);
  }
  return [...counts].map(([name, count]) => `${name} · ${count}`);
}

/** / — check a claim against the literature (artboard "01 · Claim check (hero)"). */
export function CheckPage() {
  useDocumentTitle('Check');
  const queryClient = useQueryClient();
  const [params, setParams] = useSearchParams();
  const jobId = params.get('job');
  const recents = useRecentChecks();
  const recent = recents.find((check) => check.jobId === jobId);

  // A finished check from this session reopens from storage instead of re-running.
  useMemo(() => {
    if (!jobId || !recent?.result || queryClient.getQueryData(jobKey(jobId))) return;
    const done: JobStreamState<CheckResult> = {
      status: 'done',
      steps: recent.steps ?? [],
      result: recent.result,
    };
    queryClient.setQueryData(jobKey(jobId), done);
  }, [jobId, recent, queryClient]);

  const stream = useJobStream<CheckResult>(jobId);
  const start = useStartCheck();
  const viewer = useEvidenceViewer();
  const [claim, setClaim] = useState(() => recent?.claim ?? '');
  const [claimError, setClaimError] = useState<string>();
  const [settings, setSettings] = useState(DEFAULT_SOURCE_SETTINGS);

  // Opening another recent check shows its claim.
  const recentClaim = recent?.claim;
  useEffect(() => {
    if (recentClaim) setClaim(recentClaim);
  }, [recentClaim]);

  const { status, result, steps } = stream;
  useEffect(() => {
    if (jobId && status === 'done' && result) completeRecentCheck(jobId, result, steps);
  }, [jobId, status, result, steps]);

  const running = start.isPending || status === 'running';

  const submit = () => {
    const text = claim.trim();
    if (text.length < 3) {
      setClaimError('Enter a claim to check.');
      return;
    }
    if (settings.sources.length === 0) {
      setClaimError('Choose at least one source under Edit sources.');
      return;
    }
    setClaimError(undefined);
    start.mutate(
      { claim: text, max_papers: settings.maxPapers, sources: settings.sources },
      {
        onSuccess: ({ job_id }) => {
          addRecentCheck({ jobId: job_id, claim: text, startedAt: new Date().toISOString() });
          setParams(new URLSearchParams({ job: job_id }));
        },
      },
    );
  };

  const onKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if ((event.metaKey || event.ctrlKey) && event.key === 'Enter') {
      event.preventDefault();
      submit();
    }
  };

  const openEvidence = (e: Evidence, n: number) =>
    viewer.open({ doc: e.document_id, page: e.page, chunk: e.chunk_id, quote: e.quote, n });

  const papers = useMemo(
    () =>
      Object.fromEntries(
        (result?.papers ?? []).map((p) => [
          p.document_id,
          { title: p.title, authors: p.authors, year: p.year },
        ]),
      ),
    [result],
  );

  const startError = start.error instanceof ApiError ? start.error : undefined;

  return (
    <PageContainer>
      <h1 className="sr-only">Check a claim</h1>
      <Card as="section" aria-labelledby="claim-label" className="flex flex-col gap-4">
        <div className="flex flex-wrap items-center gap-3 font-mono text-label uppercase text-muted">
          <span id="claim-label" className="font-semibold text-ink">
            Claim under review
          </span>
          {jobId && (
            <>
              <span aria-hidden="true">·</span>
              <span>Check {checkNumber(jobId)}</span>
            </>
          )}
        </div>
        <div className="flex flex-wrap items-end gap-5">
          <TextArea
            label="Claim"
            hideLabel
            variant="claim"
            rows={2}
            className="min-w-0 flex-[999_1_560px]"
            placeholder="Paste a research claim…"
            value={claim}
            error={claimError}
            onChange={(event) => setClaim(event.target.value)}
            onKeyDown={onKeyDown}
          />
          <div className="flex flex-[1_1_auto] flex-wrap justify-end gap-2">
            <EditSources value={settings} onChange={setSettings} />
            <Button onClick={submit} loading={running}>
              {jobId ? 'Re-check claim →' : 'Check claim →'}
            </Button>
          </div>
        </div>
        {result && (
          <ul aria-label="Sources searched" className="flex flex-wrap gap-2 font-mono text-[12px]">
            {sourceChips(result).map((chip) => (
              <li key={chip} className="border border-rule-dashed px-2 py-1">
                {chip}
              </li>
            ))}
            <li className="bg-ink px-2 py-1 text-sheet">
              {result.papers.length} papers read in full
            </li>
          </ul>
        )}
      </Card>

      {/* Shown once there is another check to switch to. */}
      {recents.some((check) => check.jobId !== jobId) && (
        <nav
          aria-label="Recent checks"
          className="flex flex-wrap items-center gap-2 font-mono text-[12px]"
        >
          <span className="uppercase tracking-[0.6px] text-muted">Recent</span>
          {recents.map((check) => (
            <Link
              key={check.jobId}
              to={`/?job=${check.jobId}`}
              aria-current={check.jobId === jobId ? 'page' : undefined}
              className={cn(
                'max-w-[280px] truncate border px-2 py-1 no-underline',
                check.jobId === jobId
                  ? 'border-ink bg-ink text-marker hover:text-marker'
                  : 'border-rule-dashed bg-sheet text-ink',
              )}
            >
              {checkNumber(check.jobId)} {check.claim}
            </Link>
          ))}
        </nav>
      )}

      {startError && (
        <ErrorBanner
          title="Could not start the check"
          code={startError.code}
          message={startError.message}
          onRetry={submit}
        />
      )}

      {!jobId ? (
        <EmptyState
          title="Check a claim against the literature"
          description="Paste a claim from a paper, a post or a talk. ClaimLens searches your indexed library of uploaded PDFs, reads the relevant passages in full, and shows which papers support, contest, or contradict the claim — with page references for every quote."
        />
      ) : (
        <>
          {status === 'error' ? (
            <ErrorBanner
              title="The check stopped"
              code={stream.error?.code}
              message={stream.error?.message ?? 'Something went wrong.'}
              onRetry={submit}
              retryLabel="Run the check again"
            />
          ) : (
            <VerdictBand
              verdict={result ? verdictLabel(result) : ''}
              summary={result?.summary ?? ''}
              highlight={result?.summary_highlight}
              loading={!result}
              {...(result ? verdictCounts(result) : { supports: 0, partial: 0, contradicts: 0 })}
            />
          )}
          <div className="flex flex-wrap items-start gap-6">
            {result ? (
              <EvidenceColumns result={result} onOpen={openEvidence} />
            ) : (
              status !== 'error' && <EvidenceColumnsSkeleton />
            )}
            <TraceRail steps={steps} status={status} result={result} error={stream.error} />
          </div>
        </>
      )}

      <EvidenceDrawer papers={papers} />
    </PageContainer>
  );
}
