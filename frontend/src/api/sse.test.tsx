import { act, renderHook, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { createJob } from '@/mocks/db';
import { QueryWrapper, createTestQueryClient } from '@/test/render';
import { jobKey, useJobStream } from './sse';

/** Minimal EventSource stand-in that tests drive by hand. */
class FakeEventSource {
  static instances: FakeEventSource[] = [];
  readonly url: string;
  closed = false;
  private listeners = new Map<string, ((event: Event) => void)[]>();

  constructor(url: string) {
    this.url = url;
    FakeEventSource.instances.push(this);
  }

  addEventListener(type: string, listener: (event: Event) => void) {
    this.listeners.set(type, [...(this.listeners.get(type) ?? []), listener]);
  }

  close() {
    this.closed = true;
  }

  emit(type: string, data?: unknown) {
    const event =
      data === undefined ? new Event(type) : new MessageEvent(type, { data: JSON.stringify(data) });
    for (const listener of this.listeners.get(type) ?? []) listener(event);
  }
}

function setup(jobId: string | null) {
  const client = createTestQueryClient();
  const hook = renderHook(({ id }) => useJobStream<{ ok: boolean }>(id, { pollInterval: 10 }), {
    initialProps: { id: jobId },
    wrapper: ({ children }) => <QueryWrapper client={client}>{children}</QueryWrapper>,
  });
  return { ...hook, client };
}

afterEach(() => {
  vi.unstubAllGlobals();
  FakeEventSource.instances = [];
});

describe('useJobStream over SSE', () => {
  it('collects steps, then finishes with the result', () => {
    vi.stubGlobal('EventSource', FakeEventSource);
    const { result, client } = setup('job_1');
    const source = FakeEventSource.instances[0];
    expect(source?.url).toBe('http://localhost:8000/api/v1/jobs/job_1/stream');
    expect(result.current.status).toBe('running');

    act(() => source?.emit('step', { type: 'searching', message: 'Searched arXiv', t: 2.4 }));
    expect(result.current.steps).toEqual([
      { type: 'searching', message: 'Searched arXiv', t: 2.4 },
    ]);

    act(() => source?.emit('done', { result: { ok: true } }));
    expect(result.current).toMatchObject({ status: 'done', result: { ok: true } });
    expect(source?.closed).toBe(true);
    expect(client.getQueryData(jobKey('job_1'))).toMatchObject({ status: 'done' });
  });

  it('reports a server-sent error and keeps the steps so far', () => {
    vi.stubGlobal('EventSource', FakeEventSource);
    const { result } = setup('job_2');
    const source = FakeEventSource.instances[0];

    act(() => source?.emit('step', { type: 'searching', message: 'Rewrote the claim' }));
    act(() =>
      source?.emit('error', {
        error: { code: 'UPSTREAM_ERROR', message: 'Semantic Scholar is down' },
      }),
    );

    expect(result.current.status).toBe('error');
    expect(result.current.error).toMatchObject({
      code: 'UPSTREAM_ERROR',
      message: 'Semantic Scholar is down',
    });
    expect(result.current.steps).toHaveLength(1);
    expect(source?.closed).toBe(true);
  });

  it('closes the stream on unmount', () => {
    vi.stubGlobal('EventSource', FakeEventSource);
    const { unmount } = setup('job_3');
    unmount();
    expect(FakeEventSource.instances[0]?.closed).toBe(true);
  });

  it('reuses a finished job from the cache instead of streaming again', () => {
    vi.stubGlobal('EventSource', FakeEventSource);
    const client = createTestQueryClient();
    client.setQueryData(jobKey('job_4'), { status: 'done', steps: [], result: { ok: true } });
    const { result } = renderHook(() => useJobStream<{ ok: boolean }>('job_4'), {
      wrapper: ({ children }) => <QueryWrapper client={client}>{children}</QueryWrapper>,
    });
    expect(result.current.status).toBe('done');
    expect(FakeEventSource.instances).toHaveLength(0);
  });
});

describe('useJobStream fallback', () => {
  it('polls GET /jobs/{id} when the stream connection fails', async () => {
    vi.stubGlobal('EventSource', FakeEventSource);
    const job = createJob('compare', [], [{ attribute: 'Method', values: {} }]);
    const { result } = setup(job.id);

    act(() => FakeEventSource.instances[0]?.emit('error'));

    await waitFor(() => expect(result.current.status).toBe('done'));
    expect(result.current.result).toEqual([{ attribute: 'Method', values: {} }]);
  });

  it('polls when EventSource is unavailable', async () => {
    const job = createJob('query', [], { answer: 'Yes [1].', claims: [] });
    const { result } = setup(job.id);
    await waitFor(() => expect(result.current.status).toBe('done'));
  });

  it('stays idle without a job id', () => {
    const { result } = setup(null);
    expect(result.current).toEqual({ status: 'idle', steps: [] });
  });
});
