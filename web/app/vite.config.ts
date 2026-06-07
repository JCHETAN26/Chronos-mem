import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    // Dev proxy to the FastAPI backend so the UI can fetch /api/* directly.
    proxy: { "/api": "http://localhost:8000" },
  },
});
