import '@testing-library/jest-dom/vitest';
import { cleanup } from '@testing-library/react';
import { transferableAbortController } from 'node:util';
import { afterAll, afterEach, beforeAll, beforeEach } from 'vitest';
import { resetDb } from '@/mocks/db';
import { server } from '@/mocks/node';
import { mockSettings } from '@/mocks/settings';

if (navigator.userAgent.includes('jsdom')) {
  class CompatibleAbortController extends AbortController {
    constructor() {
      super();
      return transferableAbortController();
    }
  }

  globalThis.AbortController = CompatibleAbortController;
}

// The mock API answers every request in tests, instantly.
beforeAll(() => {
  mockSettings.latency = 'none';
  server.listen({ onUnhandledRequest: 'error' });
});

beforeEach(() => {
  resetDb();
  mockSettings.failJobs = false;
  sessionStorage.clear();
});

afterEach(() => {
  cleanup();
  server.resetHandlers();
});

afterAll(() => server.close());
