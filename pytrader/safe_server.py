"""
Safe server for Zeabur deployment - handles missing credentials gracefully
Developer: 自由的风 | GBT AI System
"""
import os
import json
import mimetypes
import sys
from pathlib import Path

# ── 自动创建必要配置文件 ─────────────────────────────────────
def ensure_config_files():
    config_dir = Path(__file__).parent
    em_file = config_dir / "eastmoney.json"
    if not em_file.exists():
        em_file.write_text(json.dumps({
            "user": os.environ.get("EASTMONEY_USER", ""),
            "password": os.environ.get("EASTMONEY_PASS", "")
        }, ensure_ascii=False, indent=2))
    ac_file = config_dir / "account.json"
    if not ac_file.exists():
        ac_file.write_text(json.dumps({
            "user": os.environ.get("EASTMONEY_USER", ""),
            "password": os.environ.get("EASTMONEY_PASS", "")
        }, ensure_ascii=False, indent=2))

ensure_config_files()

# ── 聚宽行情初始化 ─────────────────────────────────────────
jq_user = os.environ.get("JQ_USER", "15800715202")
jq_pass = os.environ.get("JQ_PASS", "Aa112233")

quotation = None
try:
    import jqdatasdk
    jqdatasdk.auth(jq_user, jq_pass)
    print(f"✅ 聚宽行情连接成功！账号：{jq_user}")
    quotation = jqdatasdk
except Exception as e:
    print(f"⚠️ 聚宽行情连接失败（{e}），使用备用行情源")

# ── 备用行情（腾讯免费） ──────────────────────────────────
online_quotation = None
try:
    import easyquotation
    online_quotation = easyquotation.use("qq")
    print("✅ 备用行情（腾讯）已就绪")
except Exception as e:
    print(f"⚠️ 备用行情初始化失败：{e}")

# ── 东财交易引擎（可选） ───────────────────────────────────
trader = None
try:
    import easyquant
    from easyquant.log_handler.default_handler import DefaultLogHandler
    broker = "eastmoney"
    need_data = str(Path(__file__).parent / "eastmoney.json")
    log_handler = DefaultLogHandler(name="GBT", log_type="file", filepath="logs.log")
    engine = easyquant.MainEngine(
        broker, need_data, quotation="online", bar_type="1m",
        log_handler=log_handler,
    )
    trader = engine.user
    print("✅ 东财交易引擎已就绪")
except Exception as e:
    print(f"⚠️ 东财交易引擎未连接（{e}）")

# ── FastAPI 应用 ───────────────────────────────────────────
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
import uvicorn

app = FastAPI(title="GBT Qbot AI量化交易", version="2.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True,
                   allow_methods=["*"], allow_headers=["*"])

@app.get("/api/health")
def health():
    return {
        "status": "running",
        "system": "GBT AI量化交易系统",
        "developer": "自由的风",
        "jqdata": "connected" if quotation else "disconnected",
        "trader": "connected" if trader else "disconnected",
        "quotation": "connected" if online_quotation else "disconnected",
    }

@app.get("/api/quote/{code}")
def get_quote(code: str):
    """获取股票实时行情"""
    if online_quotation:
        try:
            data = online_quotation.real([code])
            return {"code": code, "data": data}
        except Exception as e:
            raise HTTPException(500, str(e))
    raise HTTPException(503, "行情服务未就绪")

@app.get("/api/jq/stock/{code}")
def get_jq_stock(code: str):
    """聚宽数据查询"""
    if not quotation:
        raise HTTPException(503, "聚宽行情未连接，请检查 JQ_USER / JQ_PASS 环境变量")
    try:
        from datetime import date
        df = quotation.get_price(code, start_date=str(date.today()), end_date=str(date.today()), frequency="daily")
        return {"code": code, "data": df.to_dict() if df is not None else {}}
    except Exception as e:
        raise HTTPException(500, str(e))

@app.get("/", response_class=HTMLResponse)
def index():
    return """<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>GBT AI量化交易</title>
<style>
body{font-family:sans-serif;background:#0a0a1a;color:#00ff88;
     display:flex;align-items:center;justify-content:center;min-height:100vh;margin:0}
.card{background:#111;border:1px solid #00ff8844;border-radius:16px;padding:40px;
      max-width:500px;text-align:center}
h1{font-size:2em;margin-bottom:8px}p{color:#aaa}
.badge{display:inline-block;padding:4px 12px;border-radius:20px;font-size:12px;margin:4px}
.ok{background:#00ff8822;border:1px solid #00ff88}
a{color:#00aaff}
</style></head>
<body><div class="card">
<h1>🤖 GBT AI量化交易</h1>
<p>开发者：自由的风</p>
<p>系统状态：<span class="badge ok">✅ 运行中</span></p>
<p><a href="/api/health">📊 系统健康检查</a> | <a href="/docs">📖 API文档</a></p>
<p style="font-size:12px;color:#555">Powered by GBT AI System</p>
</div></body></html>"""

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)
