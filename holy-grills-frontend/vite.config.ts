import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'
import { fileURLToPath, URL } from 'node:url'

/** VITE_DEV_PROXY_TARGET from the environment, if it is set. */
function devProxyTarget(): string | undefined {
  const env = (globalThis as { process?: { env?: Record<string, string | undefined> } }).process?.env;
  return env?.VITE_DEV_PROXY_TARGET;
}

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
    // D4: a few callers use relative URLs (web-push registration, the MCP consent
    // page); `liveApi` itself uses the absolute API base, so only those could not
    // be exercised locally. Point VITE_DEV_PROXY_TARGET at a backend to pass them
    // through. Unset means no proxy, exactly as before.
    //
    // Read through globalThis because this package has no @types/node, so
    // `process` is not typed here.
    proxy: devProxyTarget()
      ? { '/api': { target: devProxyTarget(), changeOrigin: true } }
      : undefined,
  },
});
