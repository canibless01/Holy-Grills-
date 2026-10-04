import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'
import { fileURLToPath, URL } from 'node:url'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  resolve: {
    // The `@ -> src` alias used to be injected by the Base44 Vite plugin.
    // Declared explicitly now that the plugin is gone (mirrors tsconfig paths).
    alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) },
  },
  server: {
    // The dev server is proxied through the sandbox preview host (*.e2b.app).
    // Vite's DNS-rebinding guard rejects unknown Host headers, so allow that
    // suffix explicitly. Dev-only — production builds are unaffected.
    allowedHosts: ['.e2b.app'],
  },
});
