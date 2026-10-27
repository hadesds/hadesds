/// <reference types="vitest" />
import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, ".", "");
  return {
    plugins: [react()],
    server: {
      host: "127.0.0.1",
      port: 5173,
      proxy: { "/api": env.VITE_API_PROXY || "http://127.0.0.1:8080" },
    },
    build: { outDir: "dist", sourcemap: false },
    test: { environment: "jsdom", globals: true, setupFiles: ["./src/setupTests.ts"] },
  };
});
