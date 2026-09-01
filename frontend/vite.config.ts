
import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";


export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  const backendTarget =
    env.VITE_BACKEND_URL || env.BACKEND_URL || "http://127.0.0.1:8001";

  return {
    plugins: [tailwindcss(), react()],
    css: {
      postcss: {},
    },
    server: {
      port: 5173,
      proxy: {
        "/api": {
          target: backendTarget,
          changeOrigin: true,
          ws: true,
          configure: (proxy) => {
            const HARMLESS_CODES = new Set([
              "ECONNRESET",
              "ECONNABORTED",
              "EPIPE",
              "ECONNREFUSED",
            ]);

            const suppressSocketErrors = (s: any) => {
              if (!s || typeof s.emit !== "function" || s.__finsentry_suppressed) return;
              s.__finsentry_suppressed = true;
              const origEmit = s.emit.bind(s);
              s.emit = function (event: any, ...args: any[]) {
                if (event === "error") {
                  const err = args[0] as any;
                  if (err && HARMLESS_CODES.has(err?.code)) {
                    return false;
                  }
                }
                return origEmit(event, ...args);
              };
            };

            // Intercept harmless errors emitted directly on WS sockets and requests
            proxy.on("proxyReqWs", (proxyReq: any, req: any, socket: any) => {
              suppressSocketErrors(socket);
              suppressSocketErrors(proxyReq);
              suppressSocketErrors(req?.socket);
            });

            (proxy as any).on("proxySocket", (proxySocket: any) => {
              suppressSocketErrors(proxySocket);
            });

            // Suppress harmless disconnects on the proxy instance itself while logging genuine errors
            const originalEmit = proxy.emit.bind(proxy);
            (proxy as any).emit = function (event: any, ...args: any[]) {
              if (event === "error") {
                const err = args[0] as any;
                if (err && HARMLESS_CODES.has(err?.code)) {
                  return false;
                }
              }
              return (originalEmit as any)(event, ...args);
            };

            proxy.on("error", (err: any) => {
              if (err && HARMLESS_CODES.has(err?.code)) {
                return;
              }
              console.error("[Vite Proxy Error]:", err);
            });
          },
        },
      },
    },
    test: {
      environment: "node",
      globals: true,
    },
  };
});

