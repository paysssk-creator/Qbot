# Qbot 生产级 Dockerfile - 修复 Git 依赖问题
FROM python:3.9-slim

# 🔧 第一步：安装系统依赖（包括 git）
RUN apt-get update && apt-get install -y \
    git \
    gcc \
    g++ \
    make \
    wget \
    curl \
    build-essential \
    --no-install-recommends && \
    rm -rf /var/lib/apt/lists/*

# 📁 设置工作目录
WORKDIR /app

# 📦 复制 requirements.txt
COPY requirements.txt .

# 🚀 第二步：安装 Python 依赖
# 使用 --no-cache-dir 减少镜像大小
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# 📂 复制项目文件
COPY . .

# 🏃 启动应用（修改为你实际的启动命令）
# 示例：可以是 main.py、qbot_main.py 等
CMD ["python", "main.py"]

# ✨ 标签
LABEL maintainer="paysssk-creator" \
      description="Qbot - AI Quantitative Investment Platform" \
      version="1.0.0"
