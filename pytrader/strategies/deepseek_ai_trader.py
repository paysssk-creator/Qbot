"""
DeepSeek AI 全自动操盘策略
作者：自由的风
功能：JQData行情数据 → DeepSeek AI分析 → 东方财富自动买卖
"""

import os
import json
import time
import logging
import threading
import datetime
import requests
from typing import Optional, Dict, List, Any

logger = logging.getLogger(__name__)

# ========== 配置 ==========
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "sk-ffed64a047264e0596426877144d1572")
DEEPSEEK_API_URL = "https://api.deepseek.com/v1/chat/completions"
DEEPSEEK_MODEL = "deepseek-chat"

# 交易参数
MAX_POSITION_VALUE = float(os.environ.get("MAX_POSITION_VALUE", "50000"))   # 单股最大持仓金额
MAX_SINGLE_ORDER = float(os.environ.get("MAX_SINGLE_ORDER", "10000"))        # 单次最大下单金额
STOP_LOSS_PCT = float(os.environ.get("STOP_LOSS_PCT", "0.05"))               # 止损5%
TAKE_PROFIT_PCT = float(os.environ.get("TAKE_PROFIT_PCT", "0.10"))           # 止盈10%
TRADE_INTERVAL_MINUTES = int(os.environ.get("TRADE_INTERVAL_MINUTES", "30")) # 每30分钟分析一次

# 监控股票池（可通过API动态修改）
DEFAULT_WATCHLIST = [
    "000001.XSHE",  # 平安银行
    "600519.XSHG",  # 贵州茅台
    "000858.XSHE",  # 五粮液
    "300750.XSHE",  # 宁德时代
    "601318.XSHG",  # 中国平安
]


class DeepSeekAITrader:
    """DeepSeek AI 全自动操盘引擎"""

    def __init__(self):
        self.running = False
        self.trade_thread = None
        self.watchlist = list(DEFAULT_WATCHLIST)
        self.positions = {}       # 当前持仓 {code: {cost, qty, value}}
        self.trade_log = []       # 交易记录
        self.last_analysis = {}   # 最近一次AI分析结果
        self.trader = None        # easytrader 东方财富实例
        self.jq_auth = False      # 聚宽认证状态
        self._init_jq()
        self._init_trader()

    def _init_jq(self):
        """初始化聚宽数据"""
        try:
            import jqdatasdk as jq
            jq_user = os.environ.get("JQ_USER", "")
            jq_pass = os.environ.get("JQ_PASS", "")
            if jq_user and jq_pass:
                jq.auth(jq_user, jq_pass)
                self.jq_auth = True
                self.jq = jq
                logger.info("✅ 聚宽 JQData 认证成功")
        except Exception as e:
            logger.warning(f"⚠️ 聚宽初始化失败: {e}")
            self.jq = None

    def _init_trader(self):
        """初始化东方财富交易接口"""
        try:
            account_file = os.path.join(os.path.dirname(__file__), "../eastmoney.json")
            if os.path.exists(account_file):
                with open(account_file) as f:
                    account = json.load(f)
                if account.get("user") and account.get("password"):
                    from easytrader import use
                    self.trader = use("eastmoney")
                    self.trader.prepare(user=account["user"], password=account["password"])
                    logger.info("✅ 东方财富交易接口初始化成功")
                else:
                    logger.warning("⚠️ 东方财富账号未配置，使用模拟交易模式")
            else:
                logger.warning("⚠️ eastmoney.json 不存在，使用模拟交易模式")
        except Exception as e:
            logger.warning(f"⚠️ 东方财富初始化失败: {e}，使用模拟交易模式")
            self.trader = None

    # ========== 数据获取 ==========

    def get_market_data(self, code: str) -> Dict:
        """获取股票行情数据"""
        try:
            if self.jq and self.jq_auth:
                return self._get_jq_data(code)
            else:
                return self._get_fallback_data(code)
        except Exception as e:
            logger.error(f"获取行情数据失败 {code}: {e}")
            return {}

    def _get_jq_data(self, code: str) -> Dict:
        """从聚宽获取完整数据"""
        jq = self.jq
        # 获取最近30天K线
        end = datetime.datetime.now()
        start = end - datetime.timedelta(days=60)
        df = jq.get_price(code, start_date=start, end_date=end,
                          frequency="daily", fields=["open", "close", "high", "low", "volume", "money"])
        if df is None or df.empty:
            return {}

        # 最新价
        current = jq.get_price(code, count=1, frequency="minute")
        current_price = float(current["close"].iloc[-1]) if current is not None and not current.empty else float(df["close"].iloc[-1])

        # 基本面
        fundamentals = {}
        try:
            q = jq.query(jq.valuation).filter(jq.valuation.code == code)
            fund_df = jq.get_fundamentals(q)
            if not fund_df.empty:
                fundamentals = {
                    "pe_ratio": float(fund_df["pe_ratio"].iloc[0]) if "pe_ratio" in fund_df else None,
                    "pb_ratio": float(fund_df["pb_ratio"].iloc[0]) if "pb_ratio" in fund_df else None,
                    "market_cap": float(fund_df["market_cap"].iloc[0]) if "market_cap" in fund_df else None,
                }
        except Exception:
            pass

        # 计算技术指标
        closes = df["close"].tolist()
        ma5 = sum(closes[-5:]) / 5 if len(closes) >= 5 else current_price
        ma20 = sum(closes[-20:]) / 20 if len(closes) >= 20 else current_price
        ma60 = sum(closes[-60:]) / 60 if len(closes) >= 60 else current_price

        # 涨跌幅
        prev_close = closes[-2] if len(closes) >= 2 else current_price
        change_pct = (current_price - prev_close) / prev_close * 100

        # 成交量
        volumes = df["volume"].tolist()
        avg_vol_5 = sum(volumes[-5:]) / 5 if len(volumes) >= 5 else 0
        latest_vol = volumes[-1] if volumes else 0
        vol_ratio = latest_vol / avg_vol_5 if avg_vol_5 > 0 else 1

        return {
            "code": code,
            "name": jq.get_security_info(code).display_name if self.jq_auth else code,
            "current_price": current_price,
            "change_pct": round(change_pct, 2),
            "ma5": round(ma5, 2),
            "ma20": round(ma20, 2),
            "ma60": round(ma60, 2),
            "volume_ratio": round(vol_ratio, 2),
            "recent_closes": closes[-10:],
            "fundamentals": fundamentals,
            "timestamp": datetime.datetime.now().isoformat(),
        }

    def _get_fallback_data(self, code: str) -> Dict:
        """聚宽不可用时用新浪行情接口"""
        try:
            sina_code = code.replace(".XSHE", "sz").replace(".XSHG", "sh").lower()
            r = requests.get(f"http://hq.sinajs.cn/list={sina_code}", timeout=5,
                             headers={"Referer": "http://finance.sina.com.cn"})
            parts = r.text.split('"')[1].split(",")
            if len(parts) > 10:
                current = float(parts[3])
                prev = float(parts[2])
                change_pct = (current - prev) / prev * 100 if prev > 0 else 0
                return {
                    "code": code,
                    "name": parts[0],
                    "current_price": current,
                    "change_pct": round(change_pct, 2),
                    "ma5": current, "ma20": current, "ma60": current,
                    "volume_ratio": 1.0,
                    "recent_closes": [current],
                    "fundamentals": {},
                    "timestamp": datetime.datetime.now().isoformat(),
                }
        except Exception as e:
            logger.error(f"新浪行情获取失败: {e}")
        return {}

    # ========== DeepSeek AI 分析 ==========

    def analyze_with_deepseek(self, market_data: Dict) -> Dict:
        """调用 DeepSeek AI 分析股票并给出操盘决策"""
        if not market_data:
            return {"action": "HOLD", "reason": "无数据", "confidence": 0}

        prompt = f"""你是一位专业的量化交易AI分析师。请根据以下A股数据给出精准的操盘建议。

## 股票信息
- 代码：{market_data.get('code')}
- 名称：{market_data.get('name')}
- 当前价格：{market_data.get('current_price')} 元
- 今日涨跌幅：{market_data.get('change_pct')}%
- 5日均线：{market_data.get('ma5')}
- 20日均线：{market_data.get('ma20')}
- 60日均线：{market_data.get('ma60')}
- 量比：{market_data.get('volume_ratio')}（>1.5放量，<0.5缩量）
- 近10日收盘价：{market_data.get('recent_closes')}
- 基本面：{json.dumps(market_data.get('fundamentals', {}), ensure_ascii=False)}

## 止损止盈规则
- 止损：-5%
- 止盈：+10%

## 要求
请严格按照以下JSON格式返回，不要有任何其他文字：
{{
  "action": "BUY" | "SELL" | "HOLD",
  "position_pct": 0-100,
  "target_price": 目标价格(数字),
  "stop_loss": 止损价格(数字),
  "confidence": 0-100,
  "reason": "简短的中文分析理由（50字以内）",
  "key_signals": ["信号1", "信号2"]
}}

action说明：BUY=买入，SELL=卖出，HOLD=观望
position_pct：建议仓位占可用资金百分比（BUY时有效）
confidence：AI信心分数（低于60分不建议操作）"""

        try:
            resp = requests.post(
                DEEPSEEK_API_URL,
                headers={
                    "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": DEEPSEEK_MODEL,
                    "messages": [
                        {"role": "system", "content": "你是专业的A股量化交易AI，只返回JSON格式的操盘决策。"},
                        {"role": "user", "content": prompt}
                    ],
                    "temperature": 0.3,
                    "max_tokens": 500,
                },
                timeout=30,
            )
            content = resp.json()["choices"][0]["message"]["content"].strip()
            # 提取JSON
            if "```" in content:
                content = content.split("```")[1].replace("json", "").strip()
            result = json.loads(content)
            result["code"] = market_data.get("code")
            result["name"] = market_data.get("name")
            result["price"] = market_data.get("current_price")
            result["analyzed_at"] = datetime.datetime.now().isoformat()
            return result
        except Exception as e:
            logger.error(f"DeepSeek 分析失败: {e}")
            return {
                "action": "HOLD",
                "reason": f"AI分析失败: {str(e)[:50]}",
                "confidence": 0,
                "code": market_data.get("code"),
            }

    # ========== 执行交易 ==========

    def execute_trade(self, decision: Dict, available_cash: float = 100000) -> Dict:
        """根据AI决策执行买卖"""
        action = decision.get("action", "HOLD")
        code = decision.get("code", "")
        price = decision.get("price", 0)
        confidence = decision.get("confidence", 0)

        result = {
            "code": code,
            "action": action,
            "success": False,
            "message": "",
            "timestamp": datetime.datetime.now().isoformat(),
            "simulated": self.trader is None,
        }

        # 信心分数低于60不操作
        if confidence < 60:
            result["message"] = f"信心分数 {confidence} < 60，跳过交易"
            return result

        # 非交易时间不操作
        if not self._is_trading_time():
            result["message"] = "非交易时间（9:30-15:00）"
            return result

        try:
            if action == "BUY":
                position_pct = decision.get("position_pct", 20) / 100
                order_amount = min(available_cash * position_pct, MAX_SINGLE_ORDER)
                qty = int(order_amount / price / 100) * 100  # 整手
                if qty < 100:
                    result["message"] = "资金不足，最小100股"
                    return result

                if self.trader:
                    self.trader.buy(code.replace(".XSHE", "").replace(".XSHG", ""),
                                    price=price, amount=qty)
                    result["success"] = True
                    result["message"] = f"✅ 买入 {qty}股 @{price}"
                else:
                    result["success"] = True
                    result["message"] = f"📝 模拟买入 {qty}股 @{price}（未配置真实账号）"

                # 记录持仓
                self.positions[code] = {
                    "qty": qty, "cost": price,
                    "target": decision.get("target_price", price * 1.1),
                    "stop_loss": decision.get("stop_loss", price * 0.95),
                }

            elif action == "SELL":
                pos = self.positions.get(code, {})
                qty = pos.get("qty", 0)
                if qty == 0:
                    result["message"] = "无持仓，无需卖出"
                    return result

                if self.trader:
                    self.trader.sell(code.replace(".XSHE", "").replace(".XSHG", ""),
                                     price=price, amount=qty)
                    result["success"] = True
                    result["message"] = f"✅ 卖出 {qty}股 @{price}"
                else:
                    result["success"] = True
                    result["message"] = f"📝 模拟卖出 {qty}股 @{price}（未配置真实账号）"

                if code in self.positions:
                    del self.positions[code]

        except Exception as e:
            result["message"] = f"交易执行失败: {str(e)}"
            logger.error(f"交易执行异常: {e}")

        # 记录交易日志
        log_entry = {**result, "decision": decision}
        self.trade_log.append(log_entry)
        if len(self.trade_log) > 500:
            self.trade_log = self.trade_log[-500:]

        return result

    def check_stop_loss_take_profit(self):
        """检查止损止盈"""
        results = []
        for code, pos in list(self.positions.items()):
            data = self.get_market_data(code)
            if not data:
                continue
            current = data.get("current_price", 0)
            cost = pos.get("cost", 0)
            if cost == 0:
                continue
            change = (current - cost) / cost

            if change <= -STOP_LOSS_PCT:
                result = self.execute_trade({"action": "SELL", "code": code,
                                             "price": current, "confidence": 100,
                                             "reason": f"触发止损 {change*100:.1f}%"})
                results.append(result)
                logger.warning(f"🛑 止损触发: {code} 亏损 {change*100:.1f}%")
            elif change >= TAKE_PROFIT_PCT:
                result = self.execute_trade({"action": "SELL", "code": code,
                                             "price": current, "confidence": 100,
                                             "reason": f"触发止盈 {change*100:.1f}%"})
                results.append(result)
                logger.info(f"🎯 止盈触发: {code} 盈利 {change*100:.1f}%")
        return results

    # ========== 自动化主循环 ==========

    def _is_trading_time(self) -> bool:
        """判断是否为A股交易时间"""
        now = datetime.datetime.now()
        if now.weekday() >= 5:  # 周末
            return False
        t = now.time()
        morning = datetime.time(9, 30) <= t <= datetime.time(11, 30)
        afternoon = datetime.time(13, 0) <= t <= datetime.time(15, 0)
        return morning or afternoon

    def run_once(self) -> List[Dict]:
        """执行一轮分析和交易"""
        logger.info(f"🔄 开始AI分析轮次 ({datetime.datetime.now().strftime('%H:%M:%S')})")
        results = []

        # 先检查止损止盈
        sl_results = self.check_stop_loss_take_profit()
        results.extend(sl_results)

        # 分析每只股票
        for code in self.watchlist:
            try:
                data = self.get_market_data(code)
                if not data:
                    continue
                decision = self.analyze_with_deepseek(data)
                self.last_analysis[code] = decision
                logger.info(f"📊 {code} → {decision.get('action')} (信心:{decision.get('confidence')}%) {decision.get('reason')}")

                if decision.get("action") in ("BUY", "SELL"):
                    trade_result = self.execute_trade(decision)
                    results.append(trade_result)
                    logger.info(f"💹 {trade_result.get('message')}")

                time.sleep(2)  # 避免API限速
            except Exception as e:
                logger.error(f"分析 {code} 失败: {e}")

        return results

    def start(self):
        """启动自动交易"""
        if self.running:
            return
        self.running = True
        self.trade_thread = threading.Thread(target=self._loop, daemon=True)
        self.trade_thread.start()
        logger.info(f"🚀 DeepSeek AI 全自动操盘已启动（每{TRADE_INTERVAL_MINUTES}分钟分析一次）")

    def stop(self):
        """停止自动交易"""
        self.running = False
        logger.info("⏹️ DeepSeek AI 操盘已停止")

    def _loop(self):
        """主循环"""
        while self.running:
            try:
                if self._is_trading_time():
                    self.run_once()
                else:
                    logger.debug("非交易时间，等待...")
            except Exception as e:
                logger.error(f"主循环异常: {e}")
            time.sleep(TRADE_INTERVAL_MINUTES * 60)

    def get_status(self) -> Dict:
        """获取当前状态"""
        return {
            "running": self.running,
            "jq_connected": self.jq_auth,
            "real_trade": self.trader is not None,
            "watchlist": self.watchlist,
            "positions": self.positions,
            "last_analysis": self.last_analysis,
            "trade_count": len(self.trade_log),
            "recent_trades": self.trade_log[-10:],
        }


# 全局单例
_trader_instance: Optional[DeepSeekAITrader] = None


def get_trader() -> DeepSeekAITrader:
    global _trader_instance
    if _trader_instance is None:
        _trader_instance = DeepSeekAITrader()
    return _trader_instance
