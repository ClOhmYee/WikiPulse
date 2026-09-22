import { defineConfig, loadEnv, searchForWorkspaceRoot } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  return {
    plugins: [react()],
    optimizeDeps: {
      // Pulse Map is lazy-loaded. Pre-bundle its graph dependencies before the
      // first route change so Vite does not invalidate their versioned URLs
      // while the module is being requested from the Docker dev server.
      noDiscovery: true,
      include: [
        "@react-three/fiber",
        "d3-force",
        "lucide-react",
        "react",
        "react-dom",
        "react-dom/client",
        "react/jsx-dev-runtime",
        "react/jsx-runtime",
        "three",
      ],
    },
    server: {
      proxy: {
        "/api/v1": {
          target: env.VITE_API_PROXY_TARGET || "http://127.0.0.1:8080",
          changeOrigin: true,
        },
      },
      fs: {
        allow: [searchForWorkspaceRoot(process.cwd())],
      },
    },
  };
});
