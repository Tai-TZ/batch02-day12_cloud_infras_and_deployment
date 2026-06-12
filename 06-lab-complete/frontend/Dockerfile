# Arionear RAG — Frontend (TanStack Start + Nitro node-server)
FROM node:20-slim AS builder

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .

# Baked at build time (Vite)
ARG VITE_RAG_API_URL
ARG VITE_AGENT_API_KEY
ENV VITE_RAG_API_URL=$VITE_RAG_API_URL
ENV VITE_AGENT_API_KEY=$VITE_AGENT_API_KEY

RUN npm run build


FROM node:20-slim AS runtime

WORKDIR /app

COPY --from=builder /app/.output ./.output

ENV NODE_ENV=production

EXPOSE 3000

CMD ["/bin/sh", "-c", "node .output/server/index.mjs"]
