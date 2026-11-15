# syntax=docker/dockerfile:1.7
# AthenIQ registrar console - production image.
#
# Three stages: install the lockfile exactly, build the Next.js app, then ship
# only the standalone server. The runtime image carries no toolchain and no
# source, and the process runs unprivileged.

FROM node:22-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci

FROM node:22-alpine AS build
WORKDIR /app
ENV NEXT_TELEMETRY_DISABLED=1
COPY --from=deps /app/node_modules ./node_modules
COPY . .
RUN npm run build

FROM node:22-alpine AS runtime
WORKDIR /app
ENV NODE_ENV=production     NEXT_TELEMETRY_DISABLED=1     HOSTNAME=0.0.0.0
    PORT=3100
RUN addgroup -S console && adduser -S -G console console
RUN mkdir -p /app/data && chown -R console:console /app/data
COPY --from=build --chown=console:console /app/.next/standalone ./
COPY --from=build --chown=console:console /app/.next/static ./.next/static
USER console
EXPOSE 3100
CMD ["node", "server.js"]
