# Jarvis console image — build the Vite SPA, then serve it with nginx (which also reverse-proxies
# the gateway, so the browser only ever hits this one origin).
# node 22 (alpine/musl): Vite 8 needs Node >=20.19; the lockfile carries linux-x64-musl optional deps.
FROM node:22-alpine AS build
WORKDIR /app
ENV PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1
COPY package.json package-lock.json ./
# `npm install`, not `npm ci`: Vite 8 (Rolldown) + Tailwind 4 (lightningcss) pull optional-of-
# optional native deps (@napi-rs/wasm-runtime → @emnapi/*) that npm's strict `ci` reify mishandles
# across platforms (alpine/musl here) — a known npm bug. The image has no pre-existing node_modules,
# so install resolves the locked versions cleanly without the cross-platform ci failure.
RUN npm install --no-audit --no-fund
COPY . .
RUN npm run build   # tsc -b && vite build → /app/dist

FROM nginx:alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
