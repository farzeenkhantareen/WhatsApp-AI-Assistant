FROM node:20-alpine AS builder

WORKDIR /app

RUN apk add --no-cache openssl libc6-compat

COPY package.json package-lock.json* ./
COPY prisma ./prisma

RUN npm install

COPY tsconfig.json ./
COPY src ./src

RUN npx prisma generate
RUN npm run build

FROM node:20-alpine AS runner

WORKDIR /app

ENV NODE_ENV=production

RUN apk add --no-cache openssl libc6-compat

COPY package.json package-lock.json* ./
COPY prisma ./prisma

RUN npm install --omit=dev && npx prisma generate

COPY --from=builder /app/dist ./dist

RUN mkdir -p /app/auth_info /app/media

EXPOSE 3000

HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
  CMD wget -qO- http://127.0.0.1:3000/health || exit 1

CMD ["sh", "-c", "npx prisma migrate deploy && node dist/index.js"]
