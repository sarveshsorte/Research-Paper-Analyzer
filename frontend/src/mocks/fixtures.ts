// Job results for the mock API, built from the design artboards (fictional content).

import type {
  CheckResult,
  CompareRow,
  Contradiction,
  ContradictionSide,
  Document,
  Evidence,
  JobKind,
  JobStep,
  QueryResult,
  SearchSource,
} from '@/api/types';
import { CHUNKS, PAPERS, findChunk, findPaper } from './papers';

function evidence(chunkId: string, extra: Partial<Evidence> = {}): Evidence {
  const c = findChunk(chunkId);
  if (!c) throw new Error(`Unknown mock chunk ${chunkId}`);
  return {
    chunk_id: c.chunk_id,
    document_id: c.document_id,
    page: c.page,
    section: c.section || undefined,
    quote: c.text,
    ...extra,
  };
}

function asDocument(documentId: string, uploadedAt: string): Document {
  const paper = findPaper(documentId);
  if (!paper) throw new Error(`Unknown mock paper ${documentId}`);
  const { sections, ...doc } = paper;
  return { ...doc, status: 'ready', uploaded_at: uploadedAt };
}

// ---------------------------------------------------------------------------------------------
// Check (artboard "01 · Claim check")

export const SOURCE_COUNTS: Record<SearchSource, { name: string; count: number }> = {
  semantic_scholar: { name: 'Semantic Scholar', count: 14 },
  arxiv: { name: 'arXiv', count: 9 },
  tavily: { name: 'Tavily', count: 6 },
  vector_dense: { name: 'Semantic Embeddings', count: 14 },
  bm25_sparse: { name: 'Keyword Match', count: 9 },
  uploaded_docs: { name: 'Uploaded PDFs', count: 6 },
};

export function checkResult(claim: string, sources: SearchSource[], now: string): CheckResult {
  return {
    claim,
    papers: ['DOC001', 'DOC002', 'DOC003', 'DOC004', 'DOC005', 'DOC006'].map((id) =>
      asDocument(id, now),
    ),
    supports: [
      evidence('DOC001_CH051', { highlight: 'recovers 98–100% of full fine-tuning accuracy' }),
      evidence('DOC002_CH058', { highlight: 'match 16-bit full fine-tuning' }),
      evidence('DOC003_CH040', { highlight: 'closes the remaining gap' }),
    ],
    contradicts: [
      evidence('DOC004_CH031', { highlight: 'substantially underperforms full fine-tuning' }),
      evidence('DOC005_CH066', { highlight: 'falls 9 points short' }),
    ],
    partial: [
      evidence('DOC006_CH077', {
        note: 'Matches full fine-tuning on code only at rank 256 and above; the claim omits this condition.',
      }),
    ],
    insufficient: [evidence('DOC002_CH070')],
    summary:
      'The literature splits on which benchmarks count. Papers that test on instruction-following agree; papers that test on code and math generation report a gap.',
    summary_highlight: 'which benchmarks count',
    verified_quotes: 31,
    total_quotes: 31,
    sources: sources.map((source) => SOURCE_COUNTS[source]),
  };
}

export function checkSteps(sources: SearchSource[]): JobStep[] {
  const search: Record<SearchSource, JobStep> = {
    semantic_scholar: {
      type: 'searching',
      message: 'Searched Semantic Scholar — 14 results',
      via: 'graph/v1/paper/search',
      t: 1.8,
    },
    arxiv: {
      type: 'searching',
      message: 'Searched arXiv — 9 preprints',
      via: 'export.arxiv.org',
      t: 2.4,
    },
    tavily: {
      type: 'searching',
      message: 'Searched the web — 6 sources',
      via: 'tavily /search',
      t: 3.1,
    },
    vector_dense: {
      type: 'searching',
      message: 'Searched indexed library — 14 results (dense)',
      via: 'qdrant vector search',
      t: 1.8,
    },
    bm25_sparse: {
      type: 'searching',
      message: 'Searched indexed library — 9 results (BM25)',
      via: 'sqlite bm25',
      t: 2.4,
    },
    uploaded_docs: {
      type: 'searching',
      message: 'Scanned 6 full uploaded PDFs',
      via: 'full-text scan',
      t: 3.1,
    },
  };
  return [
    {
      type: 'searching',
      message: 'Rewrote the claim into 4 search queries',
      via: 'nemotron-3-nano',
      t: 0,
    },
    ...sources.map((source) => search[source]),
    {
      type: 'processing',
      message: 'Downloaded 6 open-access PDFs',
      via: 'deduped by arXiv id',
      t: 6.9,
    },
    {
      type: 'processing',
      message: 'Parsed and indexed 1,104 chunks',
      via: 'hybrid: dense + BM25',
      t: 12.2,
    },
    {
      type: 'reasoning',
      message: 'Judged 31 claim–evidence pairs',
      via: 'nemotron-3-ultra',
      t: 19.5,
    },
    {
      type: 'validating',
      message: 'Verified every quote on its page',
      via: 'deterministic check',
      t: 21,
    },
  ];
}

// ---------------------------------------------------------------------------------------------
// Ask (artboard "03 · Ask + Evidence viewer")

const QUANTIZATION_ANSWER: QueryResult = {
  answer:
    'Mostly no. One paper reports that 4-bit adapters match 16-bit full fine-tuning across its benchmark suite [2]. A second finds the same on instruction-following but does not test math [1]. The third does not report quantized results, so it neither supports nor contradicts the point [3].',
  highlights: ['match 16-bit full fine-tuning'],
  claims: [
    {
      claim: '4-bit adapters match 16-bit fine-tuning',
      status: 'SUPPORTED',
      confidence: 0.92,
      evidence: [evidence('DOC002_CH042')],
    },
    {
      claim: 'Holds on instruction-following; math untested',
      status: 'PARTIALLY_SUPPORTED',
      confidence: 0.71,
      evidence: [evidence('DOC001_CH051')],
    },
    {
      claim: 'Effect on code generation',
      status: 'INSUFFICIENT_EVIDENCE',
      confidence: 0,
      evidence: [],
    },
  ],
};

const MODEL_SIZE_ANSWER: QueryResult = {
  answer:
    'The largest models appear in one paper, which adapts base models from 7B up to 65B parameters [2]. The other two stay small: 7B and 13B [1], and a single 7B model [3].',
  highlights: ['from 7B up to 65B parameters'],
  claims: [
    {
      claim: 'The largest base model is 65B',
      status: 'SUPPORTED',
      confidence: 0.95,
      evidence: [evidence('DOC002_CH035')],
    },
    {
      claim: 'The other papers use 13B models or smaller',
      status: 'SUPPORTED',
      confidence: 0.88,
      evidence: [evidence('DOC001_CH027'), evidence('DOC003_CH025')],
    },
  ],
};

export function queryResult(question: string): QueryResult {
  return /largest|model size|parameters|65b/i.test(question)
    ? MODEL_SIZE_ANSWER
    : QUANTIZATION_ANSWER;
}

export const QUERY_STEPS: JobStep[] = [
  {
    type: 'retrieving',
    message: 'Retrieved 24 passages from the selected papers',
    via: 'hybrid: dense + BM25',
    t: 0.6,
  },
  { type: 'reranking', message: 'Reranked to the 8 most relevant', via: 'nv-rerank', t: 1.4 },
  {
    type: 'reasoning',
    message: 'Drafted an answer with 3 claims',
    via: 'nemotron-3-ultra',
    t: 3.9,
  },
  {
    type: 'validating',
    message: 'Verified every quote on its page',
    via: 'deterministic check',
    t: 4.6,
  },
];

// ---------------------------------------------------------------------------------------------
// Compare (artboard "04 · Compare")

const COMPARE_TABLE: { attribute: string; cells: Record<string, [string, string]> }[] = [
  {
    attribute: 'Method',
    cells: {
      DOC001: ['LoRA, rank 16', 'DOC001_CH012'],
      DOC002: ['LoRA on a 4-bit base', 'DOC002_CH018'],
      DOC003: ['Magnitude + direction update', 'DOC003_CH014'],
      DOC004: ['LoRA vs. full fine-tuning', 'DOC004_CH010'],
      DOC006: ['LoRA rank sweep, 8 to 512', 'DOC006_CH015'],
    },
  },
  {
    attribute: 'Base model',
    cells: {
      DOC001: ['7B and 13B', 'DOC001_CH027'],
      DOC002: ['7B to 65B', 'DOC002_CH035'],
      DOC003: ['7B', 'DOC003_CH025'],
      DOC004: ['7B', 'DOC004_CH020'],
      DOC006: ['7B', 'DOC006_CH022'],
    },
  },
  {
    attribute: 'Benchmark',
    cells: {
      DOC001: ['Instruction suite', 'DOC001_CH041'],
      DOC002: ['Eight-task suite', 'DOC002_CH043'],
      DOC003: ['Commonsense suite', 'DOC003_CH033'],
      DOC004: ['Code and math suite', 'DOC004_CH030'],
      DOC006: ['Code suite', 'DOC006_CH030'],
    },
  },
  {
    attribute: 'Metric',
    cells: {
      DOC001: ['Accuracy', 'DOC001_CH042'],
      DOC002: ['Accuracy', 'DOC002_CH044'],
      DOC003: ['Accuracy', 'DOC003_CH034'],
      DOC004: ['Pass@1 and accuracy', 'DOC004_CH029'],
      DOC006: ['Pass@1', 'DOC006_CH031'],
    },
  },
  {
    attribute: 'Headline result',
    cells: {
      DOC001: ['Within 1 point of full FT', 'DOC001_CH053'],
      DOC002: ['Matches 16-bit full FT', 'DOC002_CH058'],
      DOC003: ['+1.1 over LoRA', 'DOC003_CH041'],
      DOC004: ['Trails full FT on code', 'DOC004_CH032'],
      DOC006: ['Matches full FT at rank 256+', 'DOC006_CH077'],
    },
  },
  {
    attribute: 'Code released',
    cells: {
      DOC001: ['Yes', 'DOC001_CH003'],
      DOC002: ['Yes', 'DOC002_CH002'],
      DOC003: ['Yes', 'DOC003_CH004'],
      DOC004: ['Yes', 'DOC004_CH002'],
      DOC006: ['Not yet', 'DOC006_CH005'],
    },
  },
];

export function compareResult(documentIds: string[]): CompareRow[] {
  return COMPARE_TABLE.map(({ attribute, cells }) => ({
    attribute,
    values: Object.fromEntries(
      documentIds.flatMap((id) => {
        const cell = cells[id];
        const c = cell && findChunk(cell[1]);
        if (!cell || !c) return [];
        return [
          [
            id,
            { value: cell[0], chunk_id: c.chunk_id, page: c.page, section: c.section || undefined },
          ],
        ];
      }),
    ),
  }));
}

export const COMPARE_STEPS: JobStep[] = [
  {
    type: 'retrieving',
    message: 'Pulled method, model and result passages',
    via: 'hybrid: dense + BM25',
    t: 0.8,
  },
  { type: 'reranking', message: 'Kept the best passage per attribute', via: 'nv-rerank', t: 1.7 },
  {
    type: 'reasoning',
    message: 'Filled 6 attributes for each paper',
    via: 'nemotron-3-ultra',
    t: 4.2,
  },
  {
    type: 'validating',
    message: 'Checked every cell against its page',
    via: 'deterministic check',
    t: 5.1,
  },
];

// ---------------------------------------------------------------------------------------------
// Conflicts (artboard "05 · Contradictions")

function side(chunkId: string): ContradictionSide & { title?: string } {
  const c = findChunk(chunkId);
  if (!c) throw new Error(`Unknown mock chunk ${chunkId}`);
  return {
    text: c.text,
    chunk_id: c.chunk_id,
    document_id: c.document_id,
    page: c.page,
    title: findPaper(c.document_id)?.title,
  };
}

export function contradictionResult(topic?: string): Contradiction[] {
  const all: Contradiction[] = [
    {
      id: 'C-01',
      topic: 'Does LoRA close the gap with full fine-tuning on code?',
      status: 'CONTRADICTED',
      claim_a: side('DOC001_CH052'),
      claim_b: side('DOC004_CH032'),
      explanation: 'Different benchmarks: A never evaluates code; B evaluates only code and math.',
      factors: ['benchmark', 'task domain'],
    },
    {
      id: 'C-02',
      topic: 'Is a small rank enough?',
      status: 'CONTRADICTED',
      claim_a: side('DOC002_CH063'),
      claim_b: side('DOC006_CH078'),
      explanation:
        'Different model sizes (65B vs 7B) and A adapts every layer while B adapts attention only.',
      factors: ['model size', 'layers adapted'],
    },
    {
      id: 'C-03',
      topic: 'Do adapters forget less of the base model?',
      status: 'PARTIALLY_SUPPORTED',
      claim_a: side('DOC004_CH044'),
      claim_b: side('DOC003_CH061'),
      explanation:
        'B controls for learning rate; A does not. Both may hold under their own settings.',
      factors: ['learning rate', 'setup'],
    },
  ];
  if (!topic?.trim()) return all;
  const words = topic
    .toLowerCase()
    .split(/\W+/)
    .filter((w) => w.length > 2);
  return all.filter((c) =>
    words.some((w) =>
      `${c.topic} ${c.explanation} ${(c.factors ?? []).join(' ')} ${c.claim_a.text} ${c.claim_b.text}`
        .toLowerCase()
        .includes(w),
    ),
  );
}

export const CONTRADICTION_STEPS: JobStep[] = [
  {
    type: 'retrieving',
    message: 'Collected 62 claims from the selected papers',
    via: 'hybrid: dense + BM25',
    t: 0.9,
  },
  { type: 'reranking', message: 'Paired 31 claims on the same topic', via: 'nv-rerank', t: 2.2 },
  { type: 'reasoning', message: 'Judged each pair for agreement', via: 'nemotron-3-ultra', t: 5.6 },
  {
    type: 'validating',
    message: 'Verified every quote on its page',
    via: 'deterministic check',
    t: 6.3,
  },
];

export const STEPS_BY_KIND: Record<Exclude<JobKind, 'check'>, JobStep[]> = {
  query: QUERY_STEPS,
  compare: COMPARE_STEPS,
  contradiction: CONTRADICTION_STEPS,
};

/** Library papers (artboard "02 · Library"); DOC006 is only found by the claim check. */
export const LIBRARY_IDS = ['DOC001', 'DOC002', 'DOC003', 'DOC004', 'DOC005'];

export { CHUNKS, PAPERS };
