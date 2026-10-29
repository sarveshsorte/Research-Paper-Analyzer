import { HttpResponse, http } from 'msw';
import { describe, expect, it } from 'vitest';
import { server } from '@/mocks/node';
import { ApiError, apiFetch, apiUrl, toApiError } from './client';

describe('toApiError', () => {
  it('reads the { error: { code, message } } shape', () => {
    const error = toApiError(409, {
      error: { code: 'DOCUMENT_NOT_READY', message: 'Still indexing.' },
    });
    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({
      code: 'DOCUMENT_NOT_READY',
      message: 'Still indexing.',
      status: 409,
    });
  });

  it('falls back to a code from the HTTP status', () => {
    expect(toApiError(413, 'Payload Too Large')).toMatchObject({
      code: 'FILE_TOO_LARGE',
      status: 413,
    });
    expect(toApiError(503, undefined)).toMatchObject({ code: 'INTERNAL_ERROR', status: 503 });
  });
});

describe('apiFetch', () => {
  it('returns JSON on success', async () => {
    const health = await apiFetch<{ status: string }>('/health');
    expect(health.status).toBe('ok');
  });

  it('throws a typed ApiError for error responses', async () => {
    await expect(apiFetch('/documents/NOPE')).rejects.toMatchObject({
      name: 'ApiError',
      code: 'NOT_FOUND',
      status: 404,
    });
  });

  it('reports a network failure as NETWORK_ERROR', async () => {
    server.use(http.get(apiUrl('/health'), () => HttpResponse.error()));
    await expect(apiFetch('/health')).rejects.toMatchObject({ code: 'NETWORK_ERROR' });
  });

  it('passes an abort through untouched', async () => {
    const controller = new AbortController();
    controller.abort();
    await expect(apiFetch('/health', { signal: controller.signal })).rejects.toMatchObject({
      name: 'AbortError',
    });
  });
});
