ARG BASE_IMAGE_PREFIX=

# Stage 1: 构建阶段 (Node.js 环境)
FROM ${BASE_IMAGE_PREFIX}node:20-alpine AS builder

WORKDIR /app

ARG VITE_CLOUD_LITE_MODE=false
ENV VITE_CLOUD_LITE_MODE=$VITE_CLOUD_LITE_MODE

# 配置 npm 淘宝镜像加速
RUN npm config set registry https://registry.npmmirror.com

# 单独复制 package.json 以利用缓存
COPY package*.json ./
RUN npm install

# 复制前端源码
COPY . .

# 编译生产环境代码 (输出到 /app/dist)
RUN npm run build

# Stage 2: 运行阶段 (Nginx 环境)
FROM ${BASE_IMAGE_PREFIX}nginx:alpine

# 复制编译好的静态文件到 Nginx 目录
COPY --from=builder /app/dist /usr/share/nginx/html

# 复制带环境变量占位符的 Nginx 模板；官方 entrypoint 会自动 envsubst
COPY deploy/nginx.conf /etc/nginx/templates/default.conf.template

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
