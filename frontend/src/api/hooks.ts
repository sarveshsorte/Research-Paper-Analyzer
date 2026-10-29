import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useCallback, useState } from 'react';
import { ApiError, apiFetch, apiFetchBytes, apiUpload } from './client';
import { useJobStream, type JobStreamState } from './sse';
import type {
  CheckRequest,
  Chunk,
  Document,
  DocumentDetail,
  JobAccepted,
  UploadAccepted,
} from './types';

const POLL_WHILE_PROCESSING_MS = 2000;

export const queryKeys = {
  documents: ['documents'] as const,
  document: (id: string) => ['documents', id] as const,
  documentFile: (id: string) => ['documents', id, 'file'] as const,
  chunk: (id: string) => ['chunks', id] as const,
};

/** GET /documents — polls every 2s while any paper is still processing. */
export function useDocuments() {
  return useQuery({
    queryKey: queryKeys.documents,
    queryFn: ({ signal }) => apiFetch<Document[]>('/documents', { signal }),
    refetchInterval: (query) =>
      query.state.data?.some((doc) => doc.status === 'processing')
        ? POLL_WHILE_PROCESSING_MS
        : false,
  });
}

/** GET /documents/{id} — polls every 2s while processing. */
export function useDocument(id: string | undefined) {
  return useQuery({
    queryKey: queryKeys.document(id ?? ''),
    queryFn: ({ signal }) => apiFetch<DocumentDetail>(`/documents/${id}`, { signal }),
    enabled: Boolean(id),
    refetchInterval: (query) =>
      query.state.data?.status === 'processing' ? POLL_WHILE_PROCESSING_MS : false,
  });
}

/** GET /documents/{id}/file as bytes, cached for the session. */
export function useDocumentFile(id: string | undefined) {
  return useQuery({
    queryKey: queryKeys.documentFile(id ?? ''),
    queryFn: ({ signal }) => apiFetchBytes(`/documents/${id}/file`, signal),
    enabled: Boolean(id),
    staleTime: Infinity,
  });
}

/** GET /chunks/{chunk_id} */
export function useChunk(id: string | undefined) {
  return useQuery({
    queryKey: queryKeys.chunk(id ?? ''),
    queryFn: ({ signal }) => apiFetch<Chunk>(`/chunks/${id}`, { signal }),
    enabled: Boolean(id),
    staleTime: Infinity,
  });
}

export interface UploadItem {
  name: string;
  progress: number;
  status: 'uploading' | 'done' | 'error';
  error?: string;
}

/**
 * Uploads each PDF in its own POST /upload request so every file reports its own progress.
 * The documents list is refreshed when all requests settle.
 */
export function useUpload() {
  const queryClient = useQueryClient();
  const [items, setItems] = useState<UploadItem[]>([]);

  const patch = (index: number, change: Partial<UploadItem>) =>
    setItems((current) => current.map((item, i) => (i === index ? { ...item, ...change } : item)));

  const upload = useCallback(
    async (files: File[]) => {
      setItems(files.map((file) => ({ name: file.name, progress: 0, status: 'uploading' })));
      await Promise.allSettled(
        files.map(async (file, index) => {
          const form = new FormData();
          form.append('files', file);
          try {
            await apiUpload<UploadAccepted[]>('/upload', form, (progress) =>
              patch(index, { progress }),
            );
            patch(index, { progress: 100, status: 'done' });
          } catch (error) {
            patch(index, {
              status: 'error',
              error: error instanceof ApiError ? error.message : 'Upload failed.',
            });
          }
        }),
      );
      await queryClient.invalidateQueries({ queryKey: queryKeys.documents });
      // Invalidate any cached compare/contradiction jobs so they re-run with the new paper
      await queryClient.invalidateQueries({ queryKey: ['job-start'] });
    },
    [queryClient],
  );

  const clear = useCallback(() => setItems([]), []);
  return { upload, items, clear, isUploading: items.some((item) => item.status === 'uploading') };
}

export function useDeleteDocument() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => apiFetch<void>(`/documents/${id}`, { method: 'DELETE' }),
    onSettled: () => queryClient.invalidateQueries({ queryKey: queryKeys.documents }),
  });
}

/** POST /documents/fetch (proposed in the contract; behind VITE_ENABLE_FETCH_BY_LINK). */
export function useFetchByLink() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (url: string) =>
      apiFetch<Document>('/documents/fetch', { method: 'POST', body: { url } }),
    onSettled: () => queryClient.invalidateQueries({ queryKey: queryKeys.documents }),
  });
}

/** PROPOSED: POST /documents/{id}/retry — re-index a failed paper with OCR. */
export function useRetryDocument() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => apiFetch<Document>(`/documents/${id}/retry`, { method: 'POST' }),
    onSettled: () => queryClient.invalidateQueries({ queryKey: queryKeys.documents }),
  });
}

export const startQuery = (body: { question: string; document_ids: string[] }) =>
  apiFetch<JobAccepted>('/query', { method: 'POST', body });

export const startCheck = (body: CheckRequest) =>
  apiFetch<JobAccepted>('/check', { method: 'POST', body });

export const startCompare = (body: { document_ids: string[]; attributes?: string[] }) =>
  apiFetch<JobAccepted>('/compare', { method: 'POST', body });

export const startContradiction = (body: { document_ids: string[]; topic?: string }) =>
  apiFetch<JobAccepted>('/contradiction', { method: 'POST', body });

export function useStartQuery() {
  return useMutation({ mutationFn: startQuery });
}

export function useStartCheck() {
  return useMutation({ mutationFn: startCheck });
}

export function useStartCompare() {
  return useMutation({ mutationFn: startCompare });
}

export function useStartContradiction() {
  return useMutation({ mutationFn: startContradiction });
}

/**
 * Starts a job once per `key` (e.g. a document set) and follows it. The job id is cached, and
 * so is the finished result (see useJobStream), so switching tabs never re-runs the job.
 * `restart()` starts a fresh job for the same key.
 *
 * The job result is kept for 5 minutes. Since the key always includes the document IDs,
 * uploading a new paper changes the key and automatically triggers a fresh job.
 */
export function useCachedJob<T>(
  key: readonly unknown[],
  start: () => Promise<JobAccepted>,
  enabled = true,
): JobStreamState<T> & { jobId?: string; restart: () => void } {
  const job = useQuery({
    queryKey: ['job-start', ...key],
    queryFn: start,
    enabled,
    staleTime: 0,
    gcTime: 5 * 60 * 1000,
    retry: false,
  });
  const jobId = job.isFetching ? undefined : job.data?.job_id;
  const stream = useJobStream<T>(jobId);
  const { refetch } = job;
  const restart = useCallback(() => void refetch(), [refetch]);

  if (!enabled) return { status: 'idle', steps: [], restart };
  if (job.isFetching) return { status: 'running', steps: [], restart };
  if (job.error) {
    const error =
      job.error instanceof ApiError
        ? job.error
        : new ApiError('INTERNAL_ERROR', 'Could not start the job.', 0);
    return { status: 'error', steps: [], error, restart };
  }
  return { ...stream, jobId, restart };
}
