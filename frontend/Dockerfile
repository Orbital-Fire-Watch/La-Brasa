# build the app, then serve the static files with Caddy
FROM node:26-alpine AS build
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
# The image always talks to the real backend (Caddy proxies /api), whatever .env.local says
ARG VITE_API_MODE=live
ENV VITE_API_MODE=$VITE_API_MODE
RUN npm run build

FROM caddy:2-alpine
COPY Caddyfile /etc/caddy/Caddyfile
COPY --from=build /app/dist /srv
