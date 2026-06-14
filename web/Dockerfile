FROM node:20-alpine AS build
WORKDIR /app
COPY package.json package-lock.json* /app/
RUN npm ci --no-audit --no-fund
COPY . /app
ARG VITE_API_BASE_URL=http://localhost:17821
ARG VITE_API_TOKEN=
ENV VITE_API_BASE_URL=${VITE_API_BASE_URL} \
    VITE_API_TOKEN=${VITE_API_TOKEN}
RUN npm run build

FROM nginx:1.27-alpine
COPY --from=build /app/dist /usr/share/nginx/html
# SPA fallback：/jobs/:id 直接刷新会落到这里，由 try_files 转到 index.html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
