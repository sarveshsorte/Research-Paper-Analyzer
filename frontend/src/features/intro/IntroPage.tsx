import { useLocation, type Location } from 'react-router-dom';
import { ButtonLink, buttonClasses } from '@/components/Button';
import { DarkPanel } from '@/components/DarkPanel';
import { EvidenceCard } from '@/components/EvidenceCard';
import { Logo } from '@/components/Logo';
import { SectionLabel } from '@/components/SectionLabel';
import { StatusTag } from '@/components/StatusTag';
import { TraceList } from '@/components/TraceList';
import { ExampleCheck } from '@/features/auth/ExampleCheck';
import { useDocumentTitle } from '@/lib/useDocumentTitle';

const STEPS = [
  {
    n: '01',
    title: 'Search',
    text: 'The agent rewrites your claim into search queries and looks across Semantic Scholar, arXiv and the open web.',
  },
  {
    n: '02',
    title: 'Read',
    text: 'It downloads the open-access papers and reads them in full, not just the abstracts, so nothing is judged out of context.',
  },
  {
    n: '03',
    title: 'Judge and verify',
    text: 'NVIDIA Nemotron weighs every claim–evidence pair, and each quote is checked against its page before you see it.',
  },
];

// Same numbering as the app's navigation.
const MODES = [
  {
    n: '01',
    title: 'Check',
    text: 'Paste a claim and get a verdict (supported, refuted or contested) with the evidence on both sides.',
  },
  {
    n: '02',
    title: 'Library',
    text: 'Upload up to five PDFs or fetch papers by link, and choose the ones to work with.',
  },
  {
    n: '03',
    title: 'Ask',
    text: 'Ask questions across your papers. Every answer cites the paper and the page.',
  },
  {
    n: '04',
    title: 'Compare',
    text: 'Line papers up attribute by attribute: method, model, benchmark, metric and results.',
  },
  {
    n: '05',
    title: 'Conflicts',
    text: 'Find where your papers disagree, with both quotes side by side and the reason they differ.',
  },
];

const TRACE = [
  { t: 0, message: 'Rewrote the claim into 4 search queries', via: 'nemotron-3-nano' },
  { t: 1.8, message: 'Searched Semantic Scholar — 14 results', via: 'graph/v1/paper/search' },
  { t: 6.9, message: 'Downloaded 6 open-access PDFs', via: 'deduped by arXiv id' },
  { t: 21, message: 'Verified every quote on its page', via: 'deterministic check' },
];

/** /welcome: what ClaimLens is, before signing in. "Let's get started" opens /login. */
export function IntroPage() {
  useDocumentTitle('Welcome');
  const location = useLocation();
  // Pass on the page the visitor first asked for, so the demo lands them there.
  const from = (location.state as { from?: Location } | null)?.from;
  const loginState = from ? { from } : undefined;

  const getStarted = (
    <ButtonLink variant="marker-cta" to="/login" state={loginState}>
      Let’s get started
      <span aria-hidden="true">→</span>
    </ButtonLink>
  );

  return (
    <div className="graph-paper flex min-h-screen flex-col">
      <a
        href="#main"
        className="sr-only font-mono text-label uppercase no-underline focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-50 focus:bg-ink focus:px-4 focus:py-3 focus:text-marker"
      >
        Skip to content
      </a>
      <header className="flex flex-wrap items-center gap-x-8 gap-y-3 border-b-1.5 border-ink bg-sheet px-4 py-3.5 md:px-8">
        <Logo to="/welcome" />
        <div aria-hidden="true" className="flex-grow" />
        <p className="hidden items-center gap-2 font-mono text-[12px] text-muted md:flex">
          <span aria-hidden="true" className="h-2 w-2 bg-support" />
          <span className="sr-only">Model: </span>
          Nemotron 3 · Token Factory
        </p>
        <ButtonLink variant="secondary" size="sm" to="/login" state={loginState}>
          Sign in
        </ButtonLink>
      </header>

      <main
        id="main"
        tabIndex={-1}
        className="mx-auto flex w-full max-w-layout flex-1 flex-col gap-14 px-4 py-8 md:gap-20 md:p-8 md:pb-16"
      >
        {/* Hero: the product in one sentence, the way in, and an example result. */}
        <section aria-labelledby="intro-title" className="flex flex-wrap items-stretch gap-6">
          <div className="flex min-w-0 flex-[1_1_520px] flex-col justify-center gap-6 md:py-6">
            <p className="font-mono text-label uppercase text-muted">
              Research claims, checked against the literature
            </p>
            <h1
              id="intro-title"
              className="font-display text-[40px] font-extrabold leading-[1.02] tracking-[-1.5px] md:text-[64px] md:leading-[0.98] md:tracking-[-2px]"
            >
              Every claim, traced to{' '}
              <span className="bg-marker px-2 [box-decoration-break:clone]">
                the page it came from.
              </span>
            </h1>
            <p className="max-w-[560px] text-[18px] leading-[1.55] text-ink-2">
              ClaimLens checks research claims against the scientific literature. Paste a claim from
              a paper, a post or a talk: an AI agent finds the relevant papers, reads them in full,
              and shows who agrees, who disagrees, and the exact page of every quote.
            </p>
            <div className="flex flex-wrap items-center gap-3">
              {getStarted}
              <a
                href="#how-it-works"
                className={buttonClasses({ variant: 'secondary', size: 'xl' }, undefined, true)}
              >
                See how it works
              </a>
            </div>
            <p className="font-mono text-[12px] text-muted">
              No account needed: the next screen has a live demo.
            </p>
          </div>

          <DarkPanel
            grid
            padding="lg"
            className="flex min-w-0 flex-[1_1_480px] flex-col justify-center gap-7 md:px-12 md:py-10"
          >
            <ExampleCheck />
            <div className="flex flex-col gap-3">
              <SectionLabel as="p" size="md" tone="marker" strong>
                Agent trace
              </SectionLabel>
              <TraceList steps={TRACE} />
            </div>
          </DarkPanel>
        </section>

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
              From a claim to its evidence, step by step
            </h2>
          </div>
          <ol className="grid gap-6 md:grid-cols-3">
            {STEPS.map((step) => (
              <li key={step.n} className="flex flex-col gap-3 border-1.5 border-ink bg-sheet p-6">
                <span
                  aria-hidden="true"
                  className="self-start bg-ink px-2 py-1 font-mono text-label text-marker"
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

        <section aria-labelledby="modes-title" className="flex flex-col gap-6">
          <div className="flex flex-col gap-1.5">
            <p className="font-mono text-label uppercase text-muted">What you can do</p>
            <h2
              id="modes-title"
              className="font-display text-[32px] font-extrabold leading-[1.05] tracking-[-1px] md:text-[40px]"
            >
              Five ways to work with papers
            </h2>
          </div>
          <ul className="grid grid-cols-[repeat(auto-fit,minmax(220px,1fr))] gap-4">
            {MODES.map((mode) => (
              <li key={mode.n} className="flex flex-col gap-2 border border-ink bg-sheet p-5">
                <h3 className="font-mono text-label font-semibold uppercase">
                  <span aria-hidden="true" className="text-muted">
                    {mode.n}{' '}
                  </span>
                  {mode.title}
                </h3>
                <p className="text-[15px] leading-[1.55] text-ink-2">{mode.text}</p>
              </li>
            ))}
          </ul>
        </section>

        <section aria-labelledby="trust-title" className="flex flex-wrap items-center gap-6">
          <div className="flex min-w-0 flex-[1_1_420px] flex-col gap-4">
            <div className="flex flex-col gap-1.5">
              <p className="font-mono text-label uppercase text-muted">Built for trust</p>
              <h2
                id="trust-title"
                className="font-display text-[32px] font-extrabold leading-[1.05] tracking-[-1px] md:text-[40px]"
              >
                Every quote is checked on its page
              </h2>
            </div>
            <p className="max-w-[560px] text-[16px] leading-[1.55] text-ink-2">
              An answer is only as good as its sources. ClaimLens shows the exact sentence a paper
              says, marks the part that matters, and opens the PDF at that page so you can read it
              yourself. Status never relies on colour alone: each verdict has its own shape and
              word.
            </p>
            <ul aria-label="Claim statuses" className="flex flex-wrap gap-2.5">
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
              Ready to <span className="bg-marker px-2 text-ink">read the evidence?</span>
            </h2>
            <p className="text-[16px] leading-[1.55] text-muted-on-ink-2">
              Start with the live demo: no account and no setup. Check the sample claim or paste
              your own.
            </p>
          </div>
          {getStarted}
        </DarkPanel>
      </main>

      <footer className="border-t-1.5 border-ink bg-sheet">
        <div className="mx-auto flex max-w-layout flex-wrap justify-between gap-x-6 gap-y-2 px-4 py-5 font-mono text-[12px] text-muted md:px-8">
          <span>ClaimLens · Nebius × NVIDIA Global AI Hackathon</span>
          <span>NVIDIA Nemotron 3 · Nebius Token Factory · Semantic Scholar · arXiv · Tavily</span>
        </div>
      </footer>
    </div>
  );
}
