import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The built site goes straight into the Python app, which serves it.
export default defineConfig({
  plugins: [react()],
  build: { outDir: "../app/static", emptyOutDir: true },
  server: { proxy: { "/api": "http://127.0.0.1:8000" } },
});
