import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
export default defineConfig({
  plugins: [react()],
  base: "/web/",
  build: { outDir: "../jobpilot/dashboard/web", emptyOutDir: true },
  server: { proxy: { "/api": "http://127.0.0.1:5000" } },
});
