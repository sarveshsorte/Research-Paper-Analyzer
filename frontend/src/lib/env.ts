/** Reads a "true"/"false" env flag; unset or empty falls back to the documented default. */
export function parseFlag(value: string | undefined, fallback: boolean): boolean {
  if (value === undefined || value.trim() === '') return fallback;
  return value.trim().toLowerCase() === 'true';
}

// Defaults mirror frontend/.env.example so `npm run dev` works without a .env file.
export const env = {
  apiBaseUrl: import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api/v1',
  useMocks: parseFlag(import.meta.env.VITE_USE_MOCKS, true),
  enableClaimMode: parseFlag(import.meta.env.VITE_ENABLE_CLAIM_MODE, true),
  enableFetchByLink: parseFlag(import.meta.env.VITE_ENABLE_FETCH_BY_LINK, true),
} as const;
