# --- Stage 1: build ---------------------------------------------------------
FROM node:20-alpine AS build
WORKDIR /app

COPY package.json package-lock.json* ./
RUN npm install --no-audit --no-fund

COPY . .
RUN npm run build

# --- Stage 2: dev (default) -------------------------------------------------
# Lightweight runtime that re-runs Vite so file changes inside the bind mount
# stream back to the browser. Production deployments should target the `nginx`
# stage below or serve `dist/` from the existing host nginx.
FROM node:20-alpine AS dev
WORKDIR /app
ENV CI=1
COPY package.json package-lock.json* ./
RUN npm install --no-audit --no-fund
COPY . .
EXPOSE 5173
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]

# --- Stage 3: nginx (production) -------------------------------------------
FROM nginx:1.27-alpine AS nginx
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
