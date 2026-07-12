FROM node:22-slim AS build
WORKDIR /app

ARG API_URL=https://api.example.com

COPY package.json package-lock.json ./
RUN npm ci

COPY . .

RUN printf 'export const environment = {\n  apiUrl: "%s",\n  games: "games",\n  rounds: "rounds",\n  players: "players"\n};\n' "$API_URL" > src/environments/environment.ts

RUN npm run build

FROM node:22-slim AS runtime
WORKDIR /app
ENV NODE_ENV=production

COPY package.json package-lock.json ./
RUN npm ci --omit=dev

COPY --from=build /app/dist/sheepshead ./dist/sheepshead

RUN groupadd --system app && useradd --system --gid app app && chown -R app:app /app
USER app

ENV PORT=4000
EXPOSE 4000

CMD ["node", "dist/sheepshead/server/server.mjs"]
