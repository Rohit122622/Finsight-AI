# ──────────────────────────────────────────────────────────────
# FinSentry AI — Frontend Dockerfile (multi-stage)
# ──────────────────────────────────────────────────────────────
# Stage 1: Build — installs deps and produces static assets
# Stage 2: Serve  — Nginx serves the built SPA
# ──────────────────────────────────────────────────────────────

# ── Stage 1: Build ───────────────────────────────────────────
FROM node:22-alpine AS build

WORKDIR /app

COPY frontend/package*.json ./

RUN npm ci --ignore-scripts

COPY frontend/ .

RUN npm run build


# ── Stage 2: Nginx Serve ─────────────────────────────────────
FROM nginx:1.27-alpine AS production

LABEL maintainer="FinSentry AI Team"
LABEL description="FinSentry AI Frontend"
LABEL version="1.0.0"

# Remove default Nginx content
RUN rm -rf /usr/share/nginx/html/*

# Copy built assets
COPY --from=build /app/dist /usr/share/nginx/html

# Copy Nginx config
COPY docker/nginx/frontend.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD wget -q --spider http://localhost:80/ || exit 1

CMD ["nginx", "-g", "daemon off;"]