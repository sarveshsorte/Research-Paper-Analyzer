// Hand-written API models from docs/FRONTEND_BUILD_PROMPT.md §4. Phase 8 replaces these with
// re-exports from the generated OpenAPI schema.
//
// Fields marked PROPOSED are not in the §4 contract. The design shows them, so the UI uses them
// when present and degrades without them. The mock API sends them.

export type DocStatus = 'processing' | 'ready' | 'failed';

export type ClaimStatus =
  'SUPPORTED' | 'PARTIALLY_SUPPORTED' | 'CONTRADICTED' | 'INSUFFICIENT_EVIDENCE';

export interface Document {
  document_id: string;
  title: string;
  filename: string;
  authors?: string;
  year?: number;
  pages: number;
  chunks?: number;
  status: DocStatus;
  source: 'upload' | 'search' | 'link';
  url?: string;
  /** Indexing progress while processing, 0–100. */
  progress?: number;
  error?: string | null;
  uploaded_at: string;
}

/** GET /documents/{id} */
export interface DocumentDetail {
  document_id: string;
  status: DocStatus;
  pages: number;
  chunks: number;
  sections: string[];
  error: string | null;
}

/** POST /upload → 202 */
export interface UploadAccepted {
  document_id: string;
  filename: string;
  status: 'processing';
}

export interface Chunk {
  chunk_id: string;
  document_id: string;
  page: number;
  section: string;
  text: string;
}

export interface Evidence {
  chunk_id: string;
  document_id: string;
  page: number;
  section?: string;
  quote: string;
  /** PROPOSED: the span of `quote` to mark with the highlighter. */
  highlight?: string;
  /** PROPOSED: why partial evidence only partly supports the claim. */
  note?: string;
}

export interface Claim {
  claim: string;
  status: ClaimStatus;
  confidence: number;
  evidence: Evidence[];
}

/**
 * `answer` contains [n] markers. The UI reads [n] as the n-th paper of the query's
 * document_ids (as the scope chips number them) and opens that paper's evidence.
 */
export interface QueryResult {
  answer: string;
  claims: Claim[];
  /** PROPOSED: phrases in `answer` to mark with the highlighter. */
  highlights?: string[];
}

export interface CompareCell {
  value: string;
  chunk_id: string;
  page?: number;
  /** PROPOSED: section label shown next to the page, e.g. "§2", "Table 3". */
  section?: string;
  /** Short exact quote to highlight on the page */
  quote?: string;
}

export interface CompareRow {
  attribute: string;
  /** Keyed by document_id. */
  values: Record<string, CompareCell>;
}

export interface ContradictionSide {
  text: string;
  chunk_id: string;
  document_id: string;
  page: number;
  /** Exact quote to highlight on the page */
  quote?: string;
  /** PROPOSED: the paper's title, so a conflict reads on its own ("A · <title> · p.7"). */
  title?: string;
}

export interface Contradiction {
  id: string;
  topic: string;
  status: ClaimStatus;
  claim_a: ContradictionSide;
  claim_b: ContradictionSide;
  explanation: string;
  factors?: string[];
}

export interface SourceCount {
  name: string;
  count: number;
}

export interface CheckResult {
  claim: string;
  papers: Document[];
  supports: Evidence[];
  contradicts: Evidence[];
  partial: Evidence[];
  insufficient: Evidence[];
  summary: string;
  verified_quotes: number;
  total_quotes: number;
  /** PROPOSED: the key phrase of `summary` to mark. */
  summary_highlight?: string;
  /** PROPOSED: search hits per source, e.g. Semantic Scholar · 14. */
  sources?: SourceCount[];
}

export type CompareResult = CompareRow[];
export type ContradictionResult = Contradiction[];

export type JobKind = 'query' | 'compare' | 'contradiction' | 'check';

export interface JobStep {
  type: string;
  message: string;
  via?: string;
  /** Seconds since the job started. */
  t?: number;
}

export interface ApiErrorBody {
  code: string;
  message: string;
}

/** GET /jobs/{id} */
export interface Job<T = unknown> {
  job_id: string;
  kind: JobKind;
  status: 'running' | 'done' | 'error';
  result?: T;
  error?: ApiErrorBody;
}

export interface JobAccepted {
  job_id: string;
}

export interface Health {
  status: string;
  version: string;
  mock_ai: boolean;
}

/** Search sources for POST /check. */
export type SearchSource =
  | 'semantic_scholar'
  | 'arxiv'
  | 'tavily'
  | 'vector_dense'
  | 'bm25_sparse'
  | 'uploaded_docs';

export interface CheckRequest {
  claim: string;
  max_papers?: number;
  /** PROPOSED: which search sources to use (Edit sources). */
  sources?: SearchSource[];
}
