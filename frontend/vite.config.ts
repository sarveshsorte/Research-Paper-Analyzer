import { createReadStream, existsSync, readFileSync, readdirSync } from 'node:fs';
import { join } from 'node:path';
import { fileURLToPath, URL } from 'node:url';
import react from '@vitejs/plugin-react';
import type { Plugin } from 'vite';
import { defineConfig } from 'vitest/config';

/**
 * Serves pdf.js's standard font data at /standard_fonts/ (dev) and copies it into the build.
 * The evidence viewer passes this as `standardFontDataUrl`, so PDFs that do not embed their
 * fonts render with the right metrics and without console warnings.
 */
function pdfjsStandardFonts(): Plugin {
  const dir = fileURLToPath(new URL('./node_modules/pdfjs-dist/standard_fonts/', import.meta.url));
  return {
    name: 'claimlens:pdfjs-standard-fonts',
    configureServer(server) {
      server.middlewares.use('/standard_fonts', (req, res, next) => {
        const name = decodeURIComponent((req.url ?? '').split('?')[0] ?? '').replace(/^\/+/, '');
        const file = join(dir, name);
        if (!name || !file.startsWith(dir) || !existsSync(file)) {
          next();
          return;
        }
        res.setHeader('Content-Type', 'application/octet-stream');
        createReadStream(file).pipe(res);
      });
    },
    generateBundle() {
      for (const name of readdirSync(dir)) {
        this.emitFile({
          type: 'asset',
          fileName: `standard_fonts/${name}`,
          source: readFileSync(join(dir, name)),
        });
      }
    },
  };
}

export default defineConfig({
  plugins: [react(), pdfjsStandardFonts()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  server: {
    port: 5173,
  },
  // Pre-bundle the lazily imported viewer and mock worker at startup. Otherwise Vite discovers
  // them on first use and reloads the page, losing in-memory state (e.g. the Ask history).
  optimizeDeps: {
    include: ['react-pdf', 'msw/browser'],
  },
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
    include: ['src/**/*.test.{ts,tsx}'],
    css: false,
  },
});
