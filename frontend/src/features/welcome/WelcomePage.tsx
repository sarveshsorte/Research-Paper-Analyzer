import { useState } from 'react';
import { useNavigate, useLocation, type Location } from 'react-router-dom';
import { Button, buttonClasses } from '@/components/Button';
import { DarkPanel } from '@/components/DarkPanel';
import { EvidenceCard } from '@/components/EvidenceCard';
import { Logo } from '@/components/Logo';
import { SectionLabel } from '@/components/SectionLabel';
import { StatusTag } from '@/components/StatusTag';
import { TraceList } from '@/components/TraceList';
import { ExampleCheck } from '@/features/auth/ExampleCheck';
import { SignInModal } from '@/features/auth/SignInModal';
import { useSession } from '@/features/auth/session';
import { useDocumentTitle } from '@/lib/useDocumentTitle';

const STEPS = [
  {
    n: '01',
    title: 'Search',
    text: 'ClaimLens rewrites your claim into multi-angle queries and searches across arXiv, Semantic Scholar, and open web literature.',
  },
  {
    n: '02',
    title: 'Read & Extract',
    text: 'Downloads full-text PDFs and parses exact passages, tables, and sections, ensuring claims are never judged out of context.',
  },
  {
    n: '03',
    title: 'Judge & Verify',
    text: 'NVIDIA Nemotron 3 weighs each claim–evidence pair, and each cited sentence is mapped directly to its exact page in the PDF.',
  },
];

const MODES = [
  {
    n: '01',
    title: 'Check',
    text: 'Paste any scientific claim and receive a verifiable verdict (Supported, Contested, Refuted) with cited evidence.',
  },
  {
    n: '02',
    title: 'Library',
    text: 'Upload PDFs or fetch papers directly via arXiv / DOI links into your private workspace library.',
  },
  {
    n: '03',
    title: 'Ask',
    text: 'Ask open-ended scientific questions across papers, with citations pinned to exact document pages.',
  },
  {
    n: '04',
    title: 'Compare',
    text: 'Compare papers side-by-side across methodology, architecture, datasets, benchmarks, and key metrics.',
  },
  {
    n: '05',
    title: 'Conflicts',
    text: 'Detect contradictions between papers automatically, displaying opposing author quotes side-by-side.',
  },
];

const TRACE = [
  { t: 0, message: 'Rewrote claim into 4 multi-angle queries', via: 'nemotron-3-nano' },
  { t: 1.8, message: 'Searched Semantic Scholar & arXiv', via: 'vector & hybrid retrieval' },
  { t: 6.9, message: 'Parsed full text & extracted passages', via: 'PyMuPDF page chunks' },
  { t: 21, message: 'Verified quote on page 8 with Nemotron reranker', via: 'deterministic check' },
];

/**
 * /welcome: Welcome introduction page before signing in.
 * "Sign in to ClaimLens" opens a modal popup rather than navigating away.
 */
export function WelcomePage() {
  useDocumentTitle('Welcome');
  const location = useLocation();
  const navigate = useNavigate();
  const session = useSession();
  const [modalOpen, setModalOpen] = useState(false);

  // Destination the visitor originally wanted to reach (preserved in router state)
  const from = (location.state as { from?: Location } | null)?.from;

  // If the user already has a session, clicking the CTA goes straight to the app
  const handleCta = () => {
    if (session) {
      navigate(from ? `${from.pathname}${from.search}` : '/', { replace: true });
    } else {
      setModalOpen(true);
    }
  };

  const ctaLabel = session ? 'Open Evidence Desk' : 'Sign in to ClaimLens';

  const getStarted = (
    <Button
      variant="marker-cta"
      className="min-h-14 px-6 text-[16px]"
      onClick={handleCta}
    >
      {ctaLabel}
      <span aria-hidden="true" className="ml-2 font-mono">→</span>
    </Button>
  );

  return (
    <div className="graph-paper flex min-h-screen flex-col bg-paper font-sans text-ink">
      {/* Sign-in modal popup */}
      {modalOpen && (
        <SignInModal from={from} onClose={() => setModalOpen(false)} />
      )}

      <a
        href="#main"
        className="sr-only font-mono text-label uppercase no-underline focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-50 focus:bg-ink focus:px-4 focus:py-3 focus:text-marker"
      >
        Skip to content
      </a>

      {/* Top Header */}
      <header className="flex flex-wrap items-center justify-between gap-x-8 gap-y-3 border-b-1.5 border-ink bg-sheet px-4 py-3.5 md:px-8">
        <Logo to="/welcome" />
        <div className="flex items-center gap-5">
          <p className="hidden items-center gap-2 font-mono text-[12px] text-muted sm:flex">
            <span aria-hidden="true" className="h-2 w-2 rounded-full bg-support motion-safe:animate-pulse" />
            <span>NVIDIA Nemotron 3 · Qdrant Vector Engine</span>
          </p>
          <Button variant="secondary" size="sm" onClick={handleCta}>
            {session ? 'Open App →' : 'Sign in'}
          </Button>
        </div>
      </header>

      {/* Main Content */}
      <main
        id="main"
        tabIndex={-1}
        className="mx-auto flex w-full max-w-layout flex-1 flex-col gap-14 px-4 py-8 md:gap-20 md:p-8 md:pb-16"
      >
        {/* Hero Section */}
        <section aria-labelledby="intro-title" className="flex flex-wrap items-stretch gap-6">
          <div className="flex min-w-0 flex-[1_1_520px] flex-col justify-center gap-6 md:py-6">
            <p className="font-mono text-label uppercase tracking-[0.8px] text-muted">
              Research claims, checked against the literature
            </p>
            <h1
              id="intro-title"
              className="font-display text-[40px] font-extrabold leading-[1.02] tracking-[-1.5px] md:text-[62px] md:leading-[0.98] md:tracking-[-2px]"
            >
              Every claim, traced to{' '}
              <span className="bg-marker px-2 [box-decoration-break:clone]">
                the page it came from.
              </span>
            </h1>
            <p className="max-w-[560px] text-[18px] leading-[1.55] text-ink-2">
              ClaimLens checks research claims against scientific literature in real-time. Paste a claim from
              a paper, article, or talk: an AI agent finds the relevant papers, reads them in full,
              and reveals who agrees, who disagrees, and the exact page of every quote.
            </p>
            <div className="flex flex-wrap items-center gap-3 pt-2">
              {getStarted}
              <a
                href="#how-it-works"
                className={buttonClasses({ variant: 'secondary', size: 'xl' }, undefined, true)}
              >
                See how it works
              </a>
            </div>
            <p className="font-mono text-[12px] text-muted">
              {session ? 'Active session ready.' : 'No setup required: sign in with live demo mode in 1 click.'}
            </p>
          </div>

          <DarkPanel
            grid
            padding="lg"
            className="flex min-w-0 flex-[1_1_480px] flex-col justify-center gap-7 md:px-10 md:py-10"
          >
            <ExampleCheck />
            <div className="flex flex-col gap-3">
              <SectionLabel as="p" size="md" tone="marker" strong>
                Agent Verification Trace
              </SectionLabel>
              <TraceList steps={TRACE} />
            </div>
          </DarkPanel>
        </section>

        {/* How It Works Section */}
        <section
          id="how-it-works"
          aria-labelledby="how-title"
          className="flex scroll-mt-6 flex-col gap-6"
        >
          <div className="flex flex-col gap-1.5">
            <p className="font-mono text-label uppercase text-muted">How it works</p>
            <h2
              id="how-title"
              className="font-display text-[32px] font-extrabold leading-[1.05] tracking-[-1px] md:text-[40px]"
            >
              From a claim to verifiable evidence, step by step
            </h2>
          </div>
          <ol className="grid gap-6 md:grid-cols-3">
            {STEPS.map((step) => (
              <li key={step.n} className="flex flex-col gap-3 border-1.5 border-ink bg-sheet p-6 shadow-sm">
                <span
                  aria-hidden="true"
                  className="self-start bg-ink px-2 py-1 font-mono text-label font-bold text-marker"
                >
                  {step.n}
                </span>
                <h3 className="font-display text-[22px] font-bold tracking-[-0.5px]">
                  {step.title}
                </h3>
                <p className="text-[15px] leading-[1.55] text-ink-2">{step.text}</p>
              </li>
            ))}
          </ol>
        </section>

        {/* Modes Section */}
        <section aria-labelledby="modes-title" className="flex flex-col gap-6">
          <div className="flex flex-col gap-1.5">
            <p className="font-mono text-label uppercase text-muted">Core Capabilities</p>
            <h2
              id="modes-title"
              className="font-display text-[32px] font-extrabold leading-[1.05] tracking-[-1px] md:text-[40px]"
            >
              Five ways to interact with research papers
            </h2>
          </div>
          <ul className="grid grid-cols-[repeat(auto-fit,minmax(220px,1fr))] gap-4">
            {MODES.map((mode) => (
              <li key={mode.n} className="flex flex-col gap-2 border-1.5 border-ink bg-sheet p-5 shadow-sm">
                <h3 className="font-mono text-label font-bold uppercase tracking-[0.5px]">
                  <span aria-hidden="true" className="text-muted">
                    {mode.n}{' '}
                  </span>
                  {mode.title}
                </h3>
                <p className="text-[14px] leading-[1.55] text-ink-2">{mode.text}</p>
              </li>
            ))}
          </ul>
        </section>

        {/* Trust & Provenance Section */}
        <section aria-labelledby="trust-title" className="flex flex-wrap items-center gap-6">
          <div className="flex min-w-0 flex-[1_1_420px] flex-col gap-4">
            <div className="flex flex-col gap-1.5">
              <p className="font-mono text-label uppercase text-muted">Deterministic Provenance</p>
              <h2
                id="trust-title"
                className="font-display text-[32px] font-extrabold leading-[1.05] tracking-[-1px] md:text-[40px]"
              >
                Every quote is verified on its original page
              </h2>
            </div>
            <p className="max-w-[560px] text-[16px] leading-[1.55] text-ink-2">
              An answer is only as reliable as its citations. ClaimLens extracts the exact sentence from
              the paper, highlights the key assertion, and anchors it to the PDF page number so you can verify it directly.
            </p>
            <ul aria-label="Claim statuses" className="flex flex-wrap gap-2.5 pt-2">
              <li>
                <StatusTag status="SUPPORTED" />
              </li>
              <li>
                <StatusTag status="PARTIALLY_SUPPORTED" />
              </li>
              <li>
                <StatusTag status="CONTRADICTED" />
              </li>
              <li>
                <StatusTag status="INSUFFICIENT_EVIDENCE" />
              </li>
            </ul>
          </div>
          <div className="min-w-0 flex-[1_1_420px]">
            <EvidenceCard
              title="Quantized Adapters for Open Models"
              n={2}
              stance="supports"
              quote="Our 4-bit adapters match 16-bit full fine-tuning on every benchmark in Table 3."
              highlight="match 16-bit full fine-tuning"
              page={8}
              section="Table 3"
            />
          </div>
        </section>

        {/* Bottom CTA Banner */}
        <DarkPanel
          as="section"
          grid
          padding="lg"
          aria-labelledby="cta-title"
          className="flex flex-wrap items-center justify-between gap-6 md:px-12 md:py-10"
        >
          <div className="flex max-w-[640px] flex-col gap-3">
            <h2
              id="cta-title"
              className="font-display text-[32px] font-extrabold leading-[1.05] tracking-[-1px] md:text-[40px]"
            >
              Ready to <span className="bg-marker px-2 text-ink">examine the literature?</span>
            </h2>
            <p className="text-[16px] leading-[1.55] text-muted-on-ink-2">
              Sign in to start with the live evidence desk: verify claims, upload PDFs, or ask questions across research papers.
            </p>
          </div>
          {getStarted}
        </DarkPanel>
      </main>

      {/* Footer */}
      <footer className="border-t-1.5 border-ink bg-sheet">
        <div className="mx-auto flex max-w-layout flex-wrap justify-between gap-x-6 gap-y-2 px-4 py-5 font-mono text-[12px] text-muted md:px-8">
          <span>ClaimLens · Research Paper Intelligence</span>
          <span>NVIDIA Nemotron 3 · Qdrant · BM25 Hybrid Retrieval</span>
        </div>
      </footer>
    </div>
  );
}
