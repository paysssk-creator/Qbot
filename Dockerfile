FROM python:3.10-slim

# 系统依赖（含 git + TA-Lib 编译）
RUN apt-get update && apt-get install -y \
    git build-essential wget curl \
    && rm -rf /var/lib/apt/lists/*

# 编译安装 TA-Lib C库
RUN wget -q http://prdownloads.sourceforge.net/ta-lib/ta-lib-0.4.0-src.tar.gz && \
    tar -xzf ta-lib-0.4.0-src.tar.gz && \
    cd ta-lib && ./configure --prefix=/usr && make -j4 && make install && \
    cd .. && rm -rf ta-lib ta-lib-0.4.0-src.tar.gz

WORKDIR /app
COPY . .

# Python 依赖
RUN pip install --no-cache-dir \
    fastapi uvicorn[standard] \
    requests python-dotenv \
    jqdatasdk \
    TA-Lib \
    numpy pandas scipy \
    scikit-learn lightgbm \
    ddddocr easytrader \
    || true

# 环境变量
ENV JQ_USER=15800715202
ENV JQ_PASS=Aa112233
ENV DEEPSEEK_API_KEY=sk-ffed64a047264e0596426877144d1572
ENV MAX_POSITION_VALUE=50000
ENV MAX_SINGLE_ORDER=10000
ENV STOP_LOSS_PCT=0.05
ENV TAKE_PROFIT_PCT=0.10
ENV TRADE_INTERVAL_MINUTES=30
ENV PORT=8080

EXPOSE 8080

CMD ["python", "-m", "uvicorn", "pytrader.safe_server:app", "--host", "0.0.0.0", "--port", "8080"]
