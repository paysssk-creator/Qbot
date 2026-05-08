FROM python:3.9-slim

# 系统依赖（含 git 和编译工具）
RUN apt-get update && apt-get install -y \
    git gcc g++ make wget curl build-essential \
    --no-install-recommends && \
    rm -rf /var/lib/apt/lists/*

# 编译安装 TA-Lib C 库
RUN wget -q http://prdownloads.sourceforge.net/ta-lib/ta-lib-0.4.0-src.tar.gz && \
    tar -xzf ta-lib-0.4.0-src.tar.gz && \
    cd ta-lib && ./configure --prefix=/usr && make && make install && \
    ldconfig && cd .. && rm -rf ta-lib ta-lib-0.4.0-src.tar.gz

WORKDIR /app
COPY . .

# 安装 Python 依赖（精准版，只装 web server 需要的）
RUN pip install --no-cache-dir --upgrade pip setuptools wheel && \
    pip install --no-cache-dir \
        numpy pandas requests logbook arrow xlrd aiofiles \
        fastapi "uvicorn[standard]" starlette python-multipart \
        "python-jose[cryptography]" "passlib[bcrypt]" sqlalchemy && \
    pip install --no-cache-dir TA-Lib && \
    pip install --no-cache-dir easytrader easyquotation || true && \
    pip install --no-cache-dir anyjson aiohttp || true

# 创建必要的初始化文件
RUN cd pytrader && \
    echo '{"user":"","password":""}' > account.json && \
    mkdir -p logs static

WORKDIR /app/pytrader

EXPOSE 8000

# 使用安全启动服务器（不需要真实券商账号也能启动）
CMD ["uvicorn", "safe_server:app", "--host", "0.0.0.0", "--port", "8000"]

LABEL maintainer="paysssk-creator" \
      description="Qbot Web API Server - Safe Startup Mode" \
      version="3.0.0"
