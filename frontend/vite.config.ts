import { defineConfig } from "vite";
import { svelte } from "@sveltejs/vite-plugin-svelte";

// Multi-page build: a static landing and about page (~zero JS), plus the Svelte app entry.
// Dev proxies /api to the FastAPI backend on :8000, so the client always talks to same-origin
// /api in both dev and prod.
export default defineConfig({
  plugins: [svelte()],
  build: {
    rollupOptions: {
      input: {
        index: "index.html",
        about: "about.html",
        app: "app.html",
      },
    },
  },
  server: {
    proxy: {
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
      },
    },
  },
});
