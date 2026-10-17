import { defineConfig } from "vite";

// Vite's built-in esbuild transform is sufficient for this small TSX shell;
// avoiding a plugin keeps the offline/local build dependency surface minimal.
export default defineConfig({
  server: { port: 5173, proxy: { "/api": "http://127.0.0.1:8000" } },
});
