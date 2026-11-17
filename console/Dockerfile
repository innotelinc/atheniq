# The console in a container: Next builds the app, then a slim runtime serves it.
# The store lives on a volume at /app/data, so rebuilding the image never touches
# learners, courses or credentials.
FROM node:22-alpine AS deps
WORKDIR /app
RUN apk add --no-cache libc6-compat
COPY package.json package-lock.json ./
RUN npm ci

FROM node:22-alpine AS build
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
ENV NEXT_TELEMETRY_DISABLED=1
RUN npm run build

FROM node:22-alpine AS run
WORKDIR /app
RUN apk add --no-cache wget
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3100 \
    HOSTNAME=0.0.0.0
COPY --from=build /app ./
EXPOSE 3100
CMD ["npm", "run", "start"]
