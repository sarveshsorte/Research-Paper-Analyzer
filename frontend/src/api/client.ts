import { endSession, readSession } from '@/features/auth/session';
import { env } from '@/lib/env';

export type ApiErrorCode =
  | 'INVALID_REQUEST'
  | 'NOT_FOUND'
  | 'DOCUMENT_NOT_READY'
  | 'FILE_TOO_LARGE'
  | 'UNSUPPORTED_TYPE'
  | 'RATE_LIMITED'
  | 'UPSTREAM_ERROR'
  | 'INTERNAL_ERROR'
  /** Client-side: the request never reached the server. */
  | 'NETWORK_ERROR';

const CODE_BY_STATUS: Record<number, ApiErrorCode> = {
  400: 'INVALID_REQUEST',
  404: 'NOT_FOUND',
  409: 'DOCUMENT_NOT_READY',
  413: 'FILE_TOO_LARGE',
  415: 'UNSUPPORTED_TYPE',
  429: 'RATE_LIMITED',
  502: 'UPSTREAM_ERROR',
};

export class ApiError extends Error {
  readonly code: string;
  readonly status: number;

  constructor(code: string, message: string, status: number) {
    super(message);
    this.name = 'ApiError';
    this.code = code;
    this.status = status;
  }
}

function isErrorBody(value: unknown): value is { error: { code: string; message: string } } {
  if (typeof value !== 'object' || value === null || !('error' in value)) return false;
  const { error } = value;
  return (
    typeof error === 'object' &&
    error !== null &&
    'code' in error &&
    typeof error.code === 'string' &&
    'message' in error &&
    typeof error.message === 'string'
  );
}

/** FastAPI's own errors are `{ detail: "message" }`. */
function detailMessage(value: unknown): string | undefined {
  if (typeof value !== 'object' || value === null || !('detail' in value)) return undefined;
  return typeof value.detail === 'string' ? value.detail : undefined;
}

/** Turns a non-2xx response body into an ApiError, falling back to the HTTP status. */
export function toApiError(status: number, body: unknown): ApiError {
  if (isErrorBody(body)) return new ApiError(body.error.code, body.error.message, status);
  const code = CODE_BY_STATUS[status] ?? 'INTERNAL_ERROR';
  return new ApiError(code, detailMessage(body) ?? `Request failed (${status}).`, status);
}

export function apiUrl(path: string): string {
  return `${env.apiBaseUrl}${path}`;
}

function isAbortError(error: unknown): boolean {
  return (
    (error instanceof DOMException && error.name === 'AbortError') ||
    (typeof error === 'object' && error !== null && 'name' in error && error.name === 'AbortError')
  );
}

function isSignalCompatibilityError(error: unknown): boolean {
  return (
    error instanceof TypeError &&
    error.message.includes('Expected signal') &&
    error.message.includes('AbortSignal')
  );
}

function shouldOmitSignal(): boolean {
  return typeof navigator !== 'undefined' && navigator.userAgent.includes('jsdom');
}

async function fetchWithSignalFallback(
  input: string,
  init: RequestInit,
  signal?: AbortSignal,
): Promise<Response> {
  if (signal?.aborted) throw new DOMException('The operation was aborted.', 'AbortError');
  if (shouldOmitSignal()) return fetch(input, init);
  try {
    return await fetch(input, { ...init, signal });
  } catch (error) {
    if (isAbortError(error)) throw error;
    if (signal?.aborted) throw new DOMException('The operation was aborted.', 'AbortError');
    if (!signal || !isSignalCompatibilityError(error)) throw error;
    return fetch(input, init);
  }
}

async function readBody(response: Response): Promise<unknown> {
  const text = await response.text();
  if (!text) return undefined;
  try {
    return JSON.parse(text) as unknown;
  } catch {
    return text;
  }
}

const bearer = (token: string) => ({ Authorization: `Bearer ${token}` });

/**
 * A Firebase session sends its ID token; the demo sends none. When Firebase no longer has the
 * user (signed out or disabled), the app session ends too.
 */
async function authHeaders(): Promise<Record<string, string>> {
  if (readSession()?.mode !== 'firebase') return {};
  let token: string | null;
  try {
    const { currentIdToken } = await import('@/features/auth/firebase');
    token = await currentIdToken();
  } catch {
    throw new ApiError(
      'NETWORK_ERROR',
      'Could not refresh your sign-in. Check your connection.',
      0,
    );
  }
  if (!token) {
    endSession();
    return {};
  }
  return bearer(token);
}

interface RequestOptions {
  method?: 'GET' | 'POST' | 'DELETE';
  /** JSON-encoded unless it is FormData. */
  body?: unknown;
  signal?: AbortSignal;
  /** A Firebase ID token to send instead of the session's, e.g. while signing in. */
  token?: string;
}

/** fetch wrapper: JSON in and out, typed ApiError for every failure. */
export async function apiFetch<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = 'GET', body, signal, token } = options;
  const isForm = body instanceof FormData;
  const auth = token ? bearer(token) : await authHeaders();
  let response: Response;
  try {
    response = await fetchWithSignalFallback(
      apiUrl(path),
      {
        method,
        headers: {
          ...auth,
          ...(body === undefined || isForm ? {} : { 'Content-Type': 'application/json' }),
        },
        body: body === undefined ? undefined : isForm ? body : JSON.stringify(body),
      },
      signal,
    );
  } catch (error) {
    if (isAbortError(error)) throw error;
    throw new ApiError('NETWORK_ERROR', 'Could not reach the ClaimLens server.', 0);
  }
  const data = await readBody(response);
  if (!response.ok) throw toApiError(response.status, data);
  return data as T;
}

/** Downloads binary data (PDF bytes). */
export async function apiFetchBytes(path: string, signal?: AbortSignal): Promise<Uint8Array> {
  const auth = await authHeaders();
  let response: Response;
  try {
    response = await fetchWithSignalFallback(apiUrl(path), { headers: auth }, signal);
  } catch (error) {
    if (isAbortError(error)) throw error;
    throw new ApiError('NETWORK_ERROR', 'Could not reach the ClaimLens server.', 0);
  }
  if (!response.ok) throw toApiError(response.status, await readBody(response));
  return new Uint8Array(await response.arrayBuffer());
}

/**
 * Multipart upload over XHR, because fetch cannot report upload progress.
 * `onProgress` receives 0–100 for the whole request.
 */
export function apiUpload<T>(
  path: string,
  form: FormData,
  onProgress?: (percent: number) => void,
): Promise<T> {
  return (async () => {
    const auth = await authHeaders();
    return new Promise<T>((resolve, reject) => {
      const xhr = new XMLHttpRequest();
      xhr.open('POST', apiUrl(path));
      for (const [name, value] of Object.entries(auth)) xhr.setRequestHeader(name, value);
      xhr.upload.onprogress = (event) => {
        if (event.lengthComputable) onProgress?.(Math.round((event.loaded / event.total) * 100));
      };
      xhr.onload = () => {
        let data: unknown;
        try {
          data = xhr.responseText ? (JSON.parse(xhr.responseText) as unknown) : undefined;
        } catch {
          data = xhr.responseText;
        }
        if (xhr.status >= 200 && xhr.status < 300) {
          onProgress?.(100);
          resolve(data as T);
        } else {
          reject(toApiError(xhr.status, data));
        }
      };
      xhr.onerror = () =>
        reject(new ApiError('NETWORK_ERROR', 'Could not reach the ClaimLens server.', 0));
      xhr.send(form);
    });
  })();
}
