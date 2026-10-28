/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_BASE_URL?: string;
  readonly VITE_USE_MOCKS?: string;
  readonly VITE_ENABLE_CLAIM_MODE?: string;
  readonly VITE_ENABLE_FETCH_BY_LINK?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
