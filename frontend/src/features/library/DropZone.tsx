import { useId, useState, type ChangeEvent, type DragEvent, type FormEvent } from 'react';
import { useFetchByLink, useUpload } from '@/api/hooks';
import { ApiError } from '@/api/client';
import { UploadIcon } from '@/components/icons';
import { cn } from '@/lib/cn';
import { env } from '@/lib/env';
import { checkFiles } from './format';

// Both halves draw a left and top dashed border; the wrapper's negative margin hides the outer
// ones, so the divider is right whether the halves sit side by side or stack. Flex bases are the
// artboard's content-box 420px plus padding.
const HALF =
  'flex min-w-0 flex-[1_1_476px] flex-col border-l-1.5 border-t-1.5 border-dashed border-ink p-7';

function UploadHalf() {
  const inputId = useId();
  const { upload, items, isUploading } = useUpload();
  const [errors, setErrors] = useState<string[]>([]);
  const [dragging, setDragging] = useState(false);

  const handleFiles = (files: File[]) => {
    const { accepted, errors: problems } = checkFiles(files);
    setErrors(problems);
    if (accepted.length > 0) void upload(accepted);
  };

  const onChange = (event: ChangeEvent<HTMLInputElement>) => {
    handleFiles([...(event.target.files ?? [])]);
    event.target.value = '';
  };

  const onDrop = (event: DragEvent) => {
    event.preventDefault();
    setDragging(false);
    handleFiles([...event.dataTransfer.files]);
  };

  const done = items.filter((item) => item.status === 'done').length;
  const progressSummary = isUploading
    ? `Uploading ${items.length} PDF${items.length === 1 ? '' : 's'}…`
    : done > 0
      ? `${done} PDF${done === 1 ? '' : 's'} uploaded. Indexing starts now.`
      : '';

  return (
    <div
      className={cn(HALF, 'justify-center gap-3', dragging && 'bg-sheet-2')}
      onDragOver={(event) => {
        event.preventDefault();
        setDragging(true);
      }}
      onDragLeave={() => setDragging(false)}
      onDrop={onDrop}
    >
      <div className="flex items-center gap-[18px]">
        <div
          aria-hidden="true"
          className="box-content flex h-[52px] w-[52px] shrink-0 items-center justify-center border-1.5 border-ink bg-marker text-ink"
        >
          <UploadIcon />
        </div>
        <div className="flex flex-col gap-1">
          <p className="text-[17px] font-bold">
            Drop PDFs here, or{' '}
            <input
              id={inputId}
              type="file"
              accept="application/pdf,.pdf"
              multiple
              className="peer sr-only"
              onChange={onChange}
            />
            <label
              htmlFor={inputId}
              className="cursor-pointer underline hover:text-support peer-focus-visible:shadow-[0_0_0_2px_var(--ink)] peer-focus-visible:outline peer-focus-visible:outline-2 peer-focus-visible:outline-offset-2 peer-focus-visible:outline-marker"
            >
              browse<span className="sr-only"> for PDFs to upload</span>
            </label>
          </p>
          <p className="text-[14px] text-muted">
            Up to 5 files · 25 MB each · scans are read with OCR
          </p>
        </div>
      </div>

      <div role="alert" className="empty:hidden">
        {errors.length > 0 && (
          <ul className="flex flex-col gap-1 font-mono text-[12px] text-contra">
            {errors.map((error) => (
              <li key={error}>{error}</li>
            ))}
          </ul>
        )}
      </div>

      <p aria-live="polite" className="sr-only">
        {progressSummary}
      </p>
      {items.length > 0 && (
        <ul className="flex flex-col gap-2 font-mono text-[12px]">
          {items.map((item) => (
            <li key={item.name} className="flex flex-col gap-1">
              <span className="flex justify-between gap-3">
                <span className="truncate">{item.name}</span>
                <span className={item.status === 'error' ? 'text-contra' : 'text-muted'}>
                  {item.status === 'error'
                    ? item.error
                    : item.status === 'done'
                      ? 'Uploaded'
                      : `${item.progress}%`}
                </span>
              </span>
              {item.status !== 'error' && (
                <span
                  role="progressbar"
                  aria-label={`Uploading ${item.name}`}
                  aria-valuemin={0}
                  aria-valuemax={100}
                  aria-valuenow={item.progress}
                  className="block h-1.5 bg-grid"
                >
                  <span className="block h-1.5 bg-ink" style={{ width: `${item.progress}%` }} />
                </span>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function FetchHalf() {
  const inputId = useId();
  const errorId = useId();
  const [url, setUrl] = useState('');
  const [success, setSuccess] = useState(false);
  const fetchByLink = useFetchByLink();

  const onSubmit = (event: FormEvent) => {
    event.preventDefault();
    if (!url.trim()) return;
    setSuccess(false);
    fetchByLink.mutate(url.trim(), {
      onSuccess: () => {
        setUrl('');
        setSuccess(true);
        setTimeout(() => setSuccess(false), 4000);
      },
    });
  };
  const error = fetchByLink.error instanceof ApiError ? fetchByLink.error.message : undefined;

  return (
    <form className={cn(HALF, 'gap-2')} onSubmit={onSubmit}>
      <label htmlFor={inputId} className="text-[17px] font-bold">
        …or fetch by link
      </label>
      <div className="flex gap-2">
        <input
          id={inputId}
          value={url}
          onChange={(event) => setUrl(event.target.value)}
          placeholder="arXiv abs URL, DOI, Semantic Scholar or direct PDF link"
          aria-invalid={error ? true : undefined}
          aria-describedby={error ? errorId : undefined}
          disabled={fetchByLink.isPending}
          className="box-content min-h-11 min-w-0 flex-1 border-1.5 border-ink bg-sheet px-3 font-mono text-[13px] disabled:opacity-50"
        />
        {/* The artboard leaves this button at the browser's 13.33px font size. */}
        <button
          type="submit"
          aria-busy={fetchByLink.isPending || undefined}
          disabled={fetchByLink.isPending || !url.trim()}
          className="min-h-11 border-1.5 border-ink bg-ink px-4 text-[13.333px] font-semibold text-sheet disabled:opacity-40"
        >
          {fetchByLink.isPending ? 'Fetching…' : 'Fetch'}
        </button>
      </div>
      <p className="font-mono text-[11px] text-muted">
        Supports: arxiv.org/abs/…, arxiv.org/pdf/…, doi.org/…, semanticscholar.org/paper/…, or any
        direct .pdf URL
      </p>
      {error && (
        <p id={errorId} role="alert" className="font-mono text-[12px] text-contra">
          {error}
        </p>
      )}
      {success && (
        <p role="status" className="font-mono text-[12px] text-support">
          ✓ Paper fetched — indexing in background. It will appear in your library shortly.
        </p>
      )}
    </form>
  );
}


/** Upload (drag-and-drop or browse) and, when enabled, fetch-by-link (artboard "02 · Library"). */
export function DropZone() {
  return (
    <div className="overflow-hidden border-1.5 border-dashed border-ink bg-sheet">
      <div className="-ml-[1.5px] -mt-[1.5px] flex flex-wrap">
        <UploadHalf />
        {env.enableFetchByLink && <FetchHalf />}
      </div>
    </div>
  );
}
