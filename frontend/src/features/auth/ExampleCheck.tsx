import { VerdictMeter } from '@/components/VerdictMeter';

/** A static example result, tilted like a card on a desk (sign-in & welcome views). */
export function ExampleCheck() {
  return (
    <figure
      aria-label="Example check"
      className="flex max-w-[567px] -rotate-[1.2deg] flex-col gap-3.5 border-1.5 border-sheet bg-sheet px-[22px] py-5 text-ink shadow-sm"
    >
      <div className="flex justify-between font-mono text-[11px] uppercase tracking-[0.6px] text-muted">
        <span>Check #0042</span>
        <span>6 papers · 21s</span>
      </div>
      <p className="font-display text-[22px] font-bold leading-[1.2]">
        “LoRA matches full fine-tuning on math and coding.”
      </p>
      <VerdictMeter supports={3} partial={1} contradicts={2} size="sm" />
      <div className="flex items-center justify-between">
        <span className="font-mono text-[12px] text-muted">
          3 support · 1 partial · 2 contradict
        </span>
        <span className="-rotate-[4deg] border-2 border-contra px-2 py-0.5 font-mono text-[12px] font-semibold uppercase tracking-[1px] text-contra">
          Contested
        </span>
      </div>
    </figure>
  );
}
