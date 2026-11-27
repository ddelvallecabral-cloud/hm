import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// En desarrollo, /api se redirige al backend Django.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    host: true,
    // /api, /admin y /static se sirven desde Django: misma URL para la sesión y el CSRF.
    proxy: Object.fromEntries(
      ["/api", "/api-auth", "/admin", "/static"].map((p) => [p, process.env.VITE_PROXY_TARGET || "http://localhost:8000"]),
    ),
  },
});
