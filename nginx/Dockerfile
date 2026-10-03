# syntax=docker/dockerfile:1
# =============================================================================
# ReelMind nginx — 前端静态资源烘入镜像（多阶段构建）
# 自 v9.26.1010 起 web/dist 不再依赖宿主机 ./web/dist 挂载，
# 部署不再需要手动 npm run build。
# 注意：构建上下文必须是仓库根目录（context: .），见 docker-compose.yml 与
# .github/workflows/publish-images.yml。
# =============================================================================
# ── Stage 1: build frontend ─────────────────────────────────────────────────
FROM node:20-alpine AS web-build
WORKDIR /build
COPY web/package.json web/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY web/ .
RUN npm run build

# ── Stage 2: nginx runtime ──────────────────────────────────────────────────
FROM nginx:alpine
COPY nginx/nginx.conf /etc/nginx/nginx.conf
COPY --from=web-build /build/dist /web/dist
EXPOSE 2588
