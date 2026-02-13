# 使用官方轻量级 Python 镜像
FROM python:3.9-slim

# 设置工作目录
WORKDIR /app

# 1. 单独复制 requirements.txt 以利用 Docker 缓存
COPY backend/requirements.txt /app/requirements.txt

# 2. 安装依赖 (使用清华源加速)
RUN pip install --no-cache-dir -r /app/requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

# 3. 复制后端代码
COPY backend /app/backend

# 4. 设置环境变量，确保 Python 能找到 backend 包
ENV PYTHONPATH=/app

# 暴露端口
EXPOSE 8000

# 启动命令
CMD ["uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
