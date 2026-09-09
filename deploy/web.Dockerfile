FROM node:22-slim AS build

WORKDIR /app/web

COPY web/package.json web/package-lock.json* ./
RUN npm ci

COPY web /app/web
ARG VITE_PLANORA_API_URL=/api
ENV VITE_PLANORA_API_URL=${VITE_PLANORA_API_URL}
RUN npm run build

FROM caddy:2.9-alpine

COPY --chown=caddy:caddy deploy/Caddyfile /etc/caddy/Caddyfile
COPY --chown=caddy:caddy --from=build /app/web/dist /srv
USER caddy
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD wget --quiet --spider http://127.0.0.1/ || exit 1
