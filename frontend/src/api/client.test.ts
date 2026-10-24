import { HttpResponse, http } from 'msw';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { currentIdToken } from '@/features/auth/firebase';
import { readSession, startDemoSession, startFirebaseSession } from '@/features/auth/session';
import { MOCK_USER } from '@/mocks/handlers';
import { server } from '@/mocks/node';
import { ApiError, apiFetch, apiUrl, toApiError } from './client';

vi.mock('@/features/auth/firebase', () => ({ currentIdToken: vi.fn() }));

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

  it('keeps the message from a FastAPI { detail } body', () => {
    expect(toApiError(503, { detail: 'Firebase sign-in is not configured.' })).toMatchObject({
      code: 'INTERNAL_ERROR',
      message: 'Firebase sign-in is not configured.',
      status: 503,
    });
  });
});

describe('auth headers', () => {
  let authorization: string | null;

  beforeEach(() => {
    vi.mocked(currentIdToken).mockReset();
    authorization = null;
    server.use(
      http.get(apiUrl('/health'), ({ request }) => {
        authorization = request.headers.get('Authorization');
        return HttpResponse.json({ status: 'ok' });
      }),
    );
  });

  it('sends the ID token of a Firebase session', async () => {
    vi.mocked(currentIdToken).mockResolvedValue('id-token');
    startFirebaseSession(MOCK_USER);

    await apiFetch('/health');

    expect(authorization).toBe('Bearer id-token');
  });

  it('sends none for the demo', async () => {
    startDemoSession();

    await apiFetch('/health');

    expect(authorization).toBeNull();
    expect(currentIdToken).not.toHaveBeenCalled();
  });

  it('ends the app session once Firebase has signed out', async () => {
    vi.mocked(currentIdToken).mockResolvedValue(null);
    startFirebaseSession(MOCK_USER);

    await apiFetch('/health');

    expect(authorization).toBeNull();
    expect(readSession()).toBeNull();
  });

  it('reports a failed token refresh as NETWORK_ERROR', async () => {
    vi.mocked(currentIdToken).mockRejectedValue(new Error('auth/network-request-failed'));
    startFirebaseSession(MOCK_USER);

    await expect(apiFetch('/health')).rejects.toMatchObject({ code: 'NETWORK_ERROR' });
    expect(readSession()).toEqual({ mode: 'firebase', user: MOCK_USER });
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
