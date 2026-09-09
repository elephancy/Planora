FROM node:22-slim AS build

WORKDIR /app/web

COPY web/package.json web/package-lock.json* ./
RUN npm ci

COPY web /app/web
ARG VITE_PLANORA_API_URL=/api
ENV VITE_PLANORA_API_URL=${VITE_PLANORA_API_URL}
RUN npm run build

FROM caddy:2.9-alpine

RUN addgroup -S -g 10001 planora-web \
    && adduser -S -D -H -u 10001 -G planora-web planora-web \
    && mkdir -p /config /data /srv \
    && chown -R 10001:10001 /config /data /srv
COPY --chown=10001:10001 deploy/Caddyfile /etc/caddy/Caddyfile
COPY --chown=10001:10001 --from=build /app/web/dist /srv
USER 10001:10001
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD wget --quiet --spider http://127.0.0.1/ || exit 1
