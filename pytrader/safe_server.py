"""
Qbot Safe Server - DeepSeek AI 全自动操盘版
作者：自由的风
"""
import os
import json
import logging
import datetime
import threading
from typing import Optional, List, Dict, Any

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Qbot AI 全自动操盘系统",
    description="DeepSeek AI × 聚宽JQData × 东方财富 — 全自动A股量化交易",
    version="3.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ===== 聚宽初始化 =====
jq = None
jq_auth = False
try:
    import jqdatasdk as _jq
    jq_user = os.environ.get("JQ_USER", "")
    jq_pass = os.environ.get("JQ_PASS", "")
    if jq_user and jq_pass:
        _jq.auth(jq_user, jq_pass)
        jq = _jq
        jq_auth = True
        logger.info("✅ 聚宽 JQData 认证成功")
except Exception as e:
    logger.warning(f"⚠️ 聚宽初始化: {e}")

# ===== DeepSeek AI 操盘引擎 =====
trader_instance = None
try:
    from strategies.deepseek_ai_trader import get_trader
    trader_instance = get_trader()
    logger.info("✅ DeepSeek AI 操盘引擎初始化成功")
except Exception as e:
    logger.warning(f"⚠️ AI操盘引擎: {e}")

# ===== 请求模型 =====
class WatchlistUpdate(BaseModel):
    stocks: List[str]

class TradeRequest(BaseModel):
    code: str
    action: str  # BUY or SELL
    price: float
    qty: int

class AIConfig(BaseModel):
    max_position_value: Optional[float] = None
    max_single_order: Optional[float] = None
    stop_loss_pct: Optional[float] = None
    take_profit_pct: Optional[float] = None
    interval_minutes: Optional[int] = None


# ===== 基础接口 =====

@app.get("/", response_class=HTMLResponse)
async def root():
    status = "🟢 运行中" if (trader_instance and trader_instance.running) else "🔴 待启动"
    jq_status = "✅ 已连接" if jq_auth else "❌ 未连接"
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <title>Qbot AI 全自动操盘系统</title>
        <meta http-equiv="refresh" content="10">
        <style>
            body {{ font-family: -apple-system, sans-serif; background: #0a0a1a; color: #e0e0e0; padding: 30px; }}
            h1 {{ color: #00d4aa; }} h2 {{ color: #7eb3ff; border-bottom: 1px solid #333; padding-bottom:8px; }}
            .card {{ background: #1a1a2e; border: 1px solid #333; border-radius: 12px; padding: 20px; margin: 16px 0; }}
            .green {{ color: #00d4aa; }} .red {{ color: #ff4d4f; }} .yellow {{ color: #ffd700; }}
            .btn {{ background: #00d4aa; color: #000; padding: 8px 20px; border: none; border-radius: 6px; cursor: pointer; margin: 4px; font-weight: bold; }}
            .btn-red {{ background: #ff4d4f; color: #fff; }}
            table {{ width:100%; border-collapse:collapse; }} td,th {{ padding:10px; border-bottom:1px solid #333; text-align:left; }}
            th {{ color: #7eb3ff; }}
        </style>
    </head>
    <body>
        <h1>🤖 Qbot AI 全自动操盘系统</h1>
        <div class="card">
            <h2>系统状态</h2>
            <p>AI操盘引擎：<strong>{status}</strong></p>
            <p>聚宽JQData：<strong>{jq_status}</strong></p>
            <p>东方财富账号：<strong>{'✅ 已配置（实盘模式）' if (trader_instance and trader_instance.trader) else '⚠️ 未配置（模拟模式）'}</strong></p>
            <p>监控股票数：<strong>{len(trader_instance.watchlist) if trader_instance else 0} 只</strong></p>
            <p>当前持仓：<strong>{len(trader_instance.positions) if trader_instance else 0} 只</strong></p>
            <p>今日交易次数：<strong>{len(trader_instance.trade_log) if trader_instance else 0} 次</strong></p>
        </div>
        <div class="card">
            <h2>快捷操作</h2>
            <button class="btn" onclick="fetch('/api/ai/start',{{method:'POST'}}).then(()=>location.reload())">🚀 启动自动操盘</button>
            <button class="btn btn-red" onclick="fetch('/api/ai/stop',{{method:'POST'}}).then(()=>location.reload())">⏹ 停止操盘</button>
            <button class="btn" onclick="fetch('/api/ai/analyze',{{method:'POST'}}).then(r=>r.json()).then(d=>alert(JSON.stringify(d,null,2)))">📊 立即分析</button>
            <button class="btn" onclick="window.location='/docs'">📖 API文档</button>
        </div>
        <div class="card">
            <h2>最近交易记录</h2>
            <table>
                <tr><th>时间</th><th>股票</th><th>操作</th><th>结果</th><th>说明</th></tr>
                {''.join([f"<tr><td>{t.get('timestamp','')[:19]}</td><td>{t.get('code')}</td><td><span class='{'green' if t.get('action')=='BUY' else 'red'}'>{t.get('action')}</span></td><td>{'✅' if t.get('success') else '⚪'}</td><td>{t.get('message','')}</td></tr>" for t in (trader_instance.trade_log[-10:] if trader_instance else [])]) or '<tr><td colspan="5" style="text-align:center">暂无交易记录</td></tr>'}
            </table>
        </div>
        <p style="color:#666; font-size:12px">🔄 每10秒自动刷新 | 开发者：自由的风</p>
    </body>
    </html>
    """

@app.get("/api/health")
async def health():
    return {
        "status": "ok",
        "time": datetime.datetime.now().isoformat(),
        "jq_connected": jq_auth,
        "ai_trader_ready": trader_instance is not None,
        "ai_trader_running": trader_instance.running if trader_instance else False,
        "real_trade_mode": trader_instance.trader is not None if trader_instance else False,
    }


# ===== AI 操盘控制接口 =====

@app.post("/api/ai/start")
async def start_ai_trader():
    """启动 DeepSeek AI 全自动操盘"""
    if not trader_instance:
        raise HTTPException(503, "AI操盘引擎未初始化")
    trader_instance.start()
    return {"success": True, "message": "🚀 DeepSeek AI 全自动操盘已启动！"}

@app.post("/api/ai/stop")
async def stop_ai_trader():
    """停止 AI 自动操盘"""
    if not trader_instance:
        raise HTTPException(503, "AI操盘引擎未初始化")
    trader_instance.stop()
    return {"success": True, "message": "⏹️ AI操盘已停止"}

@app.post("/api/ai/analyze")
async def trigger_analysis():
    """立即触发一轮AI分析（不等待定时）"""
    if not trader_instance:
        raise HTTPException(503, "AI操盘引擎未初始化")
    def run():
        trader_instance.run_once()
    t = threading.Thread(target=run, daemon=True)
    t.start()
    return {"success": True, "message": "📊 AI分析已触发，请稍后查看 /api/ai/status 或首页"}

@app.get("/api/ai/status")
async def get_ai_status():
    """获取AI操盘完整状态"""
    if not trader_instance:
        raise HTTPException(503, "AI操盘引擎未初始化")
    return trader_instance.get_status()

@app.get("/api/ai/analysis")
async def get_last_analysis():
    """获取最近一次AI分析结果"""
    if not trader_instance:
        raise HTTPException(503, "AI操盘引擎未初始化")
    return trader_instance.last_analysis

@app.get("/api/ai/positions")
async def get_positions():
    """获取当前持仓"""
    if not trader_instance:
        raise HTTPException(503, "AI操盘引擎未初始化")
    return trader_instance.positions

@app.get("/api/ai/trades")
async def get_trade_log(limit: int = 50):
    """获取交易记录"""
    if not trader_instance:
        raise HTTPException(503, "AI操盘引擎未初始化")
    return trader_instance.trade_log[-limit:]


# ===== 自选股管理 =====

@app.get("/api/watchlist")
async def get_watchlist():
    if not trader_instance:
        return {"watchlist": []}
    return {"watchlist": trader_instance.watchlist}

@app.post("/api/watchlist")
async def update_watchlist(body: WatchlistUpdate):
    """更新监控股票池"""
    if not trader_instance:
        raise HTTPException(503, "AI操盘引擎未初始化")
    trader_instance.watchlist = body.stocks
    return {"success": True, "watchlist": trader_instance.watchlist}

@app.post("/api/watchlist/add/{code}")
async def add_stock(code: str):
    if not trader_instance:
        raise HTTPException(503, "AI操盘引擎未初始化")
    if code not in trader_instance.watchlist:
        trader_instance.watchlist.append(code)
    return {"watchlist": trader_instance.watchlist}

@app.delete("/api/watchlist/{code}")
async def remove_stock(code: str):
    if not trader_instance:
        raise HTTPException(503, "AI操盘引擎未初始化")
    trader_instance.watchlist = [s for s in trader_instance.watchlist if s != code]
    return {"watchlist": trader_instance.watchlist}


# ===== 行情查询 =====

@app.get("/api/quote/{code}")
async def get_quote(code: str):
    """获取股票实时行情"""
    if not trader_instance:
        raise HTTPException(503, "AI操盘引擎未初始化")
    data = trader_instance.get_market_data(code)
    if not data:
        raise HTTPException(404, f"无法获取 {code} 的行情数据")
    return data

@app.get("/api/quote/{code}/analyze")
async def analyze_single(code: str):
    """对单只股票进行AI分析"""
    if not trader_instance:
        raise HTTPException(503, "AI操盘引擎未初始化")
    data = trader_instance.get_market_data(code)
    if not data:
        raise HTTPException(404, "无法获取行情数据")
    decision = trader_instance.analyze_with_deepseek(data)
    return {"market_data": data, "ai_decision": decision}


# ===== 手动下单 =====

@app.post("/api/trade/manual")
async def manual_trade(req: TradeRequest):
    """手动触发买卖（AI执行）"""
    if not trader_instance:
        raise HTTPException(503, "AI操盘引擎未初始化")
    decision = {
        "action": req.action.upper(),
        "code": req.code,
        "price": req.price,
        "confidence": 100,
        "reason": "手动触发",
    }
    result = trader_instance.execute_trade(decision)
    return result


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)
