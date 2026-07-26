# Multi-stage Dockerfile: chọn target qua docker compose
# - `dev`  : chạy `next dev` với hot-reload (docker-compose.yml)
# - `prod` : build production rồi chạy `next start` (docker-compose.prod.yml)

# ---------- Base: cài dependencies chung ----------
FROM node:18-alpine AS base

WORKDIR /app

# Copy package configs
COPY package.json ./

# Install dependencies (ignoring scripts/engines to speed up)
# Lưu ý: chưa có package-lock.json nên dùng `npm install` thay vì `npm ci`
RUN npm install --legacy-peer-deps

# ---------- Dev target: giữ nguyên hành vi cũ ----------
FROM base AS dev

# Copy code
COPY . .

EXPOSE 3000

ENV PORT=3000
ENV HOSTNAME="0.0.0.0"

# Default command for development
CMD ["npm", "run", "dev"]

# ---------- Prod target: next build + next start ----------
FROM base AS prod

# Copy code
COPY . .

# NEXT_PUBLIC_* phải có mặt LÚC BUILD để Next.js nhúng vào bundle client
ARG NEXT_PUBLIC_API_URL
ARG NEXT_PUBLIC_API_KEY
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL
ENV NEXT_PUBLIC_API_KEY=$NEXT_PUBLIC_API_KEY

RUN npm run build

EXPOSE 3000

ENV NODE_ENV=production
ENV PORT=3000
ENV HOSTNAME="0.0.0.0"

CMD ["npm", "run", "start"]
