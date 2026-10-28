import { useEffect, useId, useRef, useState } from 'react';
import type { SearchSource } from '@/api/types';
import { Button } from '@/components/Button';
import { Checkbox } from '@/components/Checkbox';

export interface SourceSettings {
  sources: SearchSource[];
  maxPapers: number;
}

export const DEFAULT_SOURCE_SETTINGS: SourceSettings = {
  sources: ['vector_dense', 'bm25_sparse', 'uploaded_docs'],
  maxPapers: 6,
};

const SOURCES: { value: SearchSource; label: string }[] = [
  { value: 'vector_dense', label: 'Semantic Embeddings (dense)' },
  { value: 'bm25_sparse', label: 'Keyword Match (BM25)' },
  { value: 'uploaded_docs', label: 'Full Uploaded PDFs' },
];

interface EditSourcesProps {
  value: SourceSettings;
  onChange: (value: SourceSettings) => void;
}

/** "Edit sources" button and popover: which search sources to use and how many papers to read. */
export function EditSources({ value, onChange }: EditSourcesProps) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const buttonRef = useRef<HTMLButtonElement>(null);
  const panelId = useId();
  const maxId = useId();

  useEffect(() => {
    if (!open) return;
    const onPointer = (event: MouseEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false);
    };
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setOpen(false);
        buttonRef.current?.focus();
      }
    };
    document.addEventListener('mousedown', onPointer);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onPointer);
      document.removeEventListener('keydown', onKey);
    };
  }, [open]);

  const toggleSource = (source: SearchSource, checked: boolean) => {
    const sources = checked
      ? SOURCES.map((s) => s.value).filter((s) => s === source || value.sources.includes(s))
      : value.sources.filter((s) => s !== source);
    onChange({ ...value, sources });
  };

  return (
    <div ref={rootRef} className="relative">
      <Button
        ref={buttonRef}
        variant="secondary"
        aria-expanded={open}
        aria-controls={panelId}
        onClick={() => setOpen((v) => !v)}
      >
        Edit sources
      </Button>
      {open && (
        <div
          id={panelId}
          className="absolute right-0 top-full z-30 mt-2 flex w-72 flex-col gap-4 border-1.5 border-ink bg-sheet p-4"
        >
          <fieldset className="flex flex-col gap-2.5">
            <legend className="mb-2.5 font-mono text-label uppercase text-muted">Library Search</legend>
            {SOURCES.map((source) => (
              <Checkbox
                key={source.value}
                label={source.label}
                checked={value.sources.includes(source.value)}
                onChange={(event) => toggleSource(source.value, event.target.checked)}
              />
            ))}
            {value.sources.length === 0 && (
              <p role="alert" className="font-mono text-[12px] text-contra">
                Choose at least one source.
              </p>
            )}
          </fieldset>
          <div className="flex items-center justify-between gap-3">
            <label htmlFor={maxId} className="text-[14px] font-semibold">
              Papers to read in full
            </label>
            <select
              id={maxId}
              value={value.maxPapers}
              onChange={(event) => onChange({ ...value, maxPapers: Number(event.target.value) })}
              className="min-h-11 border-1.5 border-ink bg-sheet px-2 font-mono text-[13px]"
            >
              {[3, 4, 5, 6, 7, 8, 9, 10].map((n) => (
                <option key={n} value={n}>
                  {n}
                </option>
              ))}
            </select>
          </div>
        </div>
      )}
    </div>
  );
}
