import { defineConfig, loadEnv, searchForWorkspaceRoot } from "vite";
import react from "@vitejs/plugin-react";
import { readFile } from "node:fs/promises";
import { resolve } from "node:path";

const localHistoryPreview = {
  name: "local-history-preview-data",
  apply: "serve",
  configureServer(server) {
    server.middlewares.use(
      "/__local_issue_history_preview",
      async (req, res, next) => {
        const name = (req.url || "").split("?")[0].replace(/^\//, "");
        if (
          !["metadata.jsonl", "details.jsonl", "reports.jsonl"].includes(name)
        )
          return next();
        try {
          const body = await readFile(
            resolve(process.cwd(), "tmp", "issue-history-preview", name),
          );
          res.writeHead(200, {
            "Content-Type": "application/x-ndjson; charset=utf-8",
            "Cache-Control": "no-store",
          });
          res.end(body);
        } catch {
          res.writeHead(404, { "Content-Type": "text/plain; charset=utf-8" });
          res.end("로컬 추출본이 없습니다.");
        }
      },
    );
  },
};

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  return {
    plugins: [react(), localHistoryPreview],
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
