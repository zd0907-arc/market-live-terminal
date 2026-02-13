# Stage 1: 构建阶段 (Node.js 环境)
FROM node:20-alpine AS builder

WORKDIR /app

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
FROM nginx:alpine

# 复制编译好的静态文件到 Nginx 目录
COPY --from=builder /app/dist /usr/share/nginx/html

# 复制自定义 Nginx 配置 (注意：构建上下文需要是项目根目录)
COPY deploy/nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
