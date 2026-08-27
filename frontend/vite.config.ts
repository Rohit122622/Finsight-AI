
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
            proxy.on("error", (err: any) => {
              if (
                err.code === "ECONNRESET" ||
                err.code === "ECONNABORTED" ||
                err.code === "EPIPE"
              ) {
                return;
              }
              console.error("[Vite Proxy Error]:", err);
            });
            proxy.on("proxyReqWs", (_proxyReq, _req, socket) => {
              socket.on("error", (err: any) => {
                if (
                  err.code === "ECONNRESET" ||
                  err.code === "ECONNABORTED" ||
                  err.code === "EPIPE"
                ) {
                  return;
                }
                console.error("[Vite WS Proxy Socket Error]:", err);
              });
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

