FROM node:24-slim AS deps

ENV PNPM_HOME=/pnpm
ENV PATH="${PNPM_HOME}:${PATH}"

WORKDIR /app

RUN corepack enable

COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
COPY apps/frontend/package.json apps/frontend/package.json

RUN pnpm install --filter @cognizinterview/frontend --frozen-lockfile

FROM deps AS builder

ARG NEXT_PUBLIC_API_BASE_URL
ARG NEXT_PUBLIC_DEMO_API_KEY
ENV NEXT_PUBLIC_API_BASE_URL=${NEXT_PUBLIC_API_BASE_URL}
ENV NEXT_PUBLIC_DEMO_API_KEY=${NEXT_PUBLIC_DEMO_API_KEY}

COPY apps/frontend apps/frontend

RUN pnpm --dir apps/frontend exec next build --webpack

FROM node:24-slim AS runner

ENV NODE_ENV=production
ENV PNPM_HOME=/pnpm
ENV PATH="${PNPM_HOME}:${PATH}"

WORKDIR /app

RUN corepack enable

COPY --from=builder /app/package.json /app/pnpm-lock.yaml /app/pnpm-workspace.yaml ./
COPY --from=builder /app/node_modules ./node_modules
COPY --from=builder /app/apps/frontend ./apps/frontend

CMD ["pnpm", "--dir", "apps/frontend", "start"]
