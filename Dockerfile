FROM python:3.10-slim

# 安装系统依赖（含 git + TA-Lib 编译依赖）
RUN apt-get update && apt-get install -y \
    git wget build-essential curl \
    && rm -rf /var/lib/apt/lists/*

# 编译安装 TA-Lib C 库
RUN wget -q http://prdownloads.sourceforge.net/ta-lib/ta-lib-0.4.0-src.tar.gz \
    && tar -xzf ta-lib-0.4.0-src.tar.gz \
    && cd ta-lib && ./configure --prefix=/usr && make && make install \
    && cd .. && rm -rf ta-lib ta-lib-0.4.0-src.tar.gz

WORKDIR /app
COPY . .

# 安装核心依赖
RUN pip install --no-cache-dir fastapi uvicorn easyquotation jqdatasdk

# 尝试安装 TA-Lib Python 包
RUN pip install --no-cache-dir TA-Lib || true

# 尝试安装项目其他依赖（忽略失败项）
RUN grep -v "^git+" pytrader/requirements.txt > /tmp/req_clean.txt && \
    pip install --no-cache-dir -r /tmp/req_clean.txt || true

# 聚宽账号环境变量（可在 Zeabur 控制台覆盖）
ENV JQ_USER=15800715202
ENV JQ_PASS=Aa112233
ENV PORT=8080

EXPOSE 8080

CMD ["python", "pytrader/safe_server.py"]
