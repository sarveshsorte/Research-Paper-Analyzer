import { useId, useMemo, useState, type FormEvent } from 'react';
import { startContradiction, useCachedJob } from '@/api/hooks';
import type { ContradictionResult, ContradictionSide } from '@/api/types';
import { Button, ButtonLink } from '@/components/Button';
import { EmptyState } from '@/components/EmptyState';
import { ErrorBanner } from '@/components/ErrorBanner';
import { JobProgress } from '@/components/JobProgress';
import { PageContainer } from '@/components/PageContainer';
import { SegmentedControl } from '@/components/SegmentedControl';
import { Skeleton } from '@/components/Skeleton';
import { EvidenceDrawer } from '@/features/evidence/EvidenceDrawer';
import type { PaperMeta } from '@/features/evidence/EvidenceViewer';
import { useEvidenceViewer } from '@/features/evidence/useEvidenceViewer';
import { useScope } from '@/features/library/useScope';
import { useDocumentTitle } from '@/lib/useDocumentTitle';
import { ConflictCard } from './ConflictCard';

type Filter = 'all' | 'contradicted' | 'partial';

/** /conflicts?docs=… (artboard "05 · Contradictions"). */
export function ConflictsPage() {
  useDocumentTitle('Conflicts');
  const scope = useScope();
  const viewer = useEvidenceViewer();
  const topicId = useId();
  const [filter, setFilter] = useState<Filter>('all');
  const [topic, setTopic] = useState('');
  const [draftTopic, setDraftTopic] = useState('');
  const [narrowing, setNarrowing] = useState(false);

  const docs = scope.ready;
  const ids = docs.map((doc) => doc.document_id);
  const enabled = ids.length >= 2;
  const job = useCachedJob<ContradictionResult>(
    ['contradiction', ids.join(','), topic],
    () => startContradiction({ document_ids: ids, topic: topic || undefined }),
    enabled,
  );
  const conflicts = useMemo(() => job.result ?? [], [job.result]);
  const counts = {
    all: conflicts.length,
    contradicted: conflicts.filter((c) => c.status === 'CONTRADICTED').length,
    partial: conflicts.filter((c) => c.status === 'PARTIALLY_SUPPORTED').length,
  };
  const shown = conflicts.filter(
    (c) =>
      filter === 'all' ||
      (filter === 'contradicted'
        ? c.status === 'CONTRADICTED'
        : c.status === 'PARTIALLY_SUPPORTED'),
  );

  const titles = new Map(docs.map((doc) => [doc.document_id, doc.title]));
  const papers: Record<string, PaperMeta> = Object.fromEntries(
    docs.map((doc) => [
      doc.document_id,
      { title: doc.title, authors: doc.authors, year: doc.year },
    ]),
  );
  // Sides can cite a paper outside the library list (it carries its own title).
  for (const conflict of conflicts) {
    for (const side of [conflict.claim_a, conflict.claim_b]) {
      if (!papers[side.document_id] && side.title) papers[side.document_id] = { title: side.title };
    }
  }

  const openSide = (side: ContradictionSide, trigger: HTMLElement) =>
    viewer.open(
      {
        doc: side.document_id,
        page: side.page,
        chunk: side.chunk_id,
        quote: side.quote || side.text,
      },
      trigger,
    );

  const applyTopic = (event: FormEvent) => {
    event.preventDefault();
    setTopic(draftTopic.trim());
  };

  if (!scope.isLoading && !scope.error && !enabled) {
    return (
      <PageContainer gap="loose">
        <h1 className="font-display text-claim font-extrabold md:text-h1">
          Where the papers disagree
        </h1>
        <EmptyState
          title="Select at least two ready papers"
          description="Conflicts pairs claims across your papers and shows where they disagree, with both quotes and why."
          action={<ButtonLink to="/library">Go to Library</ButtonLink>}
        />
      </PageContainer>
    );
  }

  return (
    <PageContainer gap="loose">
      <div className="flex flex-col gap-4">
        <div className="flex flex-wrap items-end gap-4">
          <div className="flex min-w-0 flex-[1_1_520px] flex-col gap-2">
            <div className="flex items-center gap-3">
              <p className="font-mono text-label uppercase text-muted">
                {ids.length} papers
                {job.result
                  ? ` · ${conflicts.length} conflict${conflicts.length === 1 ? '' : 's'} found`
                  : ''}
                {topic ? ` · topic: ${topic}` : ''}
              </p>
              <ButtonLink
                variant="secondary"
                to={`/library?sel=${ids.join(',')}`}
                className="text-[11px] font-mono py-0.5 px-2.5 h-auto min-h-0"
              >
                Change papers
              </ButtonLink>
            </div>
            <h1 className="font-display text-claim font-extrabold md:text-h1">
              Where the papers disagree
            </h1>
          </div>
          <Button
            variant="secondary"
            aria-expanded={narrowing}
            onClick={() => setNarrowing((v) => !v)}
          >
            Narrow by topic
          </Button>
          <SegmentedControl
            label="Filter"
            value={filter}
            onChange={setFilter}
            options={[
              { value: 'all', label: 'All', count: counts.all },
              { value: 'contradicted', label: 'Contradicted', count: counts.contradicted },
              { value: 'partial', label: 'Partial', count: counts.partial },
            ]}
          />
        </div>
        {narrowing && (
          <form onSubmit={applyTopic} className="flex flex-wrap items-center gap-2">
            <label htmlFor={topicId} className="font-mono text-label uppercase text-muted">
              Topic
            </label>
            <input
              id={topicId}
              value={draftTopic}
              onChange={(event) => setDraftTopic(event.target.value)}
              placeholder="e.g. rank, forgetting, code"
              className="min-h-11 min-w-0 flex-[1_1_260px] border-1.5 border-ink bg-sheet px-3 font-mono text-[13px]"
            />
            <Button type="submit" variant="primary-sheet">
              Re-run
            </Button>
            {topic && (
              <Button
                variant="secondary"
                onClick={() => {
                  setDraftTopic('');
                  setTopic('');
                }}
              >
                Clear
              </Button>
            )}
          </form>
        )}
      </div>

      {scope.error ? (
        <ErrorBanner
          title="Could not load your papers"
          message={scope.error.message}
          onRetry={() => void scope.refetch()}
        />
      ) : job.status === 'error' ? (
        <ErrorBanner
          title="The conflict search stopped"
          code={job.error?.code}
          message={job.error?.message ?? 'Something went wrong.'}
          onRetry={job.restart}
        />
      ) : !job.result ? (
        scope.isLoading ? (
          <Skeleton height={260} />
        ) : (
          <JobProgress
            label={`Looking for disagreements across ${ids.length} papers…`}
            steps={job.steps}
          />
        )
      ) : shown.length === 0 ? (
        <EmptyState
          title={conflicts.length === 0 ? 'No conflicts found' : 'Nothing under this filter'}
          description={
            conflicts.length === 0
              ? 'These papers do not contradict each other on anything the agent could pair up.'
              : 'Choose All to see every conflict.'
          }
        />
      ) : (
        shown.map((conflict) => (
          <ConflictCard key={conflict.id} conflict={conflict} titles={titles} onOpen={openSide} />
        ))
      )}

      <EvidenceDrawer papers={papers} />
    </PageContainer>
  );
}
