# syntax=docker/dockerfile:1

# --- agent-portal Dockerfile (dono: infra-docker) ---
# Node 20. Multi-stage para produção (build estático do Next.js); o override de dev
# (docker-compose.override.yml) usa `next dev` com bind mount, sem rebuild.

FROM node:20-alpine AS deps
WORKDIR /app
# Instala dependências primeiro (melhor cache de camada).
COPY package.json package-lock.json ./
RUN npm ci

# Build: gera os artefatos do Next.js.
FROM node:20-alpine AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
# Produção: build estático (standalone) para imagem menor.
ENV NEXT_TELEMETRY_DISABLED=1
RUN npm run build

# Runtime: só o runtime do Next.js + node_modules.
FROM node:20-alpine AS runner
WORKDIR /app

ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PYTHONUNBUFFERED=1

# Copia o build standalone (Next.js 14 suporta standalone output).
COPY --from=builder /app/next.config.mjs ./next.config.mjs
COPY --from=builder /app/package.json ./package.json
COPY --from=builder /app/node_modules ./node_modules
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static

# wget leve, nativo do alpine; usado pelo healthcheck do compose.
RUN apk add --no-cache wget

EXPOSE 3000

# Healthcheck nativo da imagem (o compose também define um, mas este é o fallback).
HEALTHCHECK --interval=10s --timeout=5s --retries=10 --start-period=40s \
    CMD wget -q --spider http://localhost:3000/ || exit 1

# Entrypoint: o servidor do Next.js em produção.
# No dev (override), o compose substitui o command por `next dev --0.0.0.0:3000`.
ENTRYPOINT ["node", "server.js"]
