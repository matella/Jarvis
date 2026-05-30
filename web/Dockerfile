# Jarvis console image — build the Vite SPA, then serve it with nginx (which also reverse-proxies
# the gateway, so the browser only ever hits this one origin).
FROM node:20-alpine AS build
WORKDIR /app
ENV PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build   # tsc -b && vite build → /app/dist

FROM nginx:alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
