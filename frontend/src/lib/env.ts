/** Reads a "true"/"false" env flag; unset or empty falls back to the documented default. */
export function parseFlag(value: string | undefined, fallback: boolean): boolean {
  if (value === undefined || value.trim() === '') return fallback;
  return value.trim().toLowerCase() === 'true';
}

// Defaults mirror frontend/.env.example so `npm run dev` works without a .env file.
export const env = {
  apiBaseUrl: import.meta.env.VITE_API_BASE_URL || 'http://localhost:8001/api/v1',
  googleClientId:
    import.meta.env.VITE_GOOGLE_CLIENT_ID ||
    '575187270355-7t4k12piivu4jvabsrrisfine1voipfp.apps.googleusercontent.com',
  githubClientId: import.meta.env.VITE_GITHUB_CLIENT_ID || 'Ov23liz4wXUFCGOKJ6DT',
  // Tests intentionally use the deterministic MSW fixtures; deployed/dev builds use the API.
  useMocks: parseFlag(import.meta.env.VITE_USE_MOCKS, import.meta.env.MODE === 'test'),
  enableClaimMode: parseFlag(import.meta.env.VITE_ENABLE_CLAIM_MODE, true),
  enableFetchByLink: parseFlag(import.meta.env.VITE_ENABLE_FETCH_BY_LINK, true),
} as const;
