# ── 构建阶段: Vite 打包 ──
FROM node:20-alpine AS build
WORKDIR /app
# 清华镜像加速 (NAS/国内网络), 失败也不致命可删掉这两行
RUN npm config set registry https://registry.npmmirror.com
COPY package.json package-lock.json* ./
RUN npm ci --no-audit --no-fund || npm install --no-audit --no-fund
COPY . .
RUN npm run build

# ── 运行阶段: Nginx 托管静态产物 + 反代 /api ──
FROM nginx:1.27-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
