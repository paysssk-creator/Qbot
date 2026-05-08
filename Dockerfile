FROM python:3.9-slim

# 安装系统依赖（包含 git 和编译工具）
RUN apt-get update && apt-get install -y \
    git gcc g++ make wget curl build-essential \
    --no-install-recommends && \
    rm -rf /var/lib/apt/lists/*

# 手动编译安装 TA-Lib（量化必需）
RUN wget -q http://prdownloads.sourceforge.net/ta-lib/ta-lib-0.4.0-src.tar.gz && \
    tar -xzf ta-lib-0.4.0-src.tar.gz && \
    cd ta-lib && ./configure --prefix=/usr && make && make install && \
    cd .. && rm -rf ta-lib ta-lib-0.4.0-src.tar.gz

WORKDIR /app
COPY . .

# 安装 pytrader web 服务器依赖
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir \
    numpy pandas requests logbook anyjson aiohttp \
    easytrader easyquotation arrow \
    aiofiles python-multipart \
    fastapi "uvicorn[standard]" \
    starlette "python-jose[cryptography]" "passlib[bcrypt]" \
    sqlalchemy xlrd TA-Lib ddddocr

WORKDIR /app/pytrader

EXPOSE 8000

CMD ["uvicorn", "web_server:app", "--host", "0.0.0.0", "--port", "8000"]

LABEL maintainer="paysssk-creator" \
      description="Qbot Web API Server" \
      version="2.0.0"
