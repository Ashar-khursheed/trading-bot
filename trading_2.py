#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════╗
║       BINANCE AI TRADING AGENT — GPT POWERED  v3            ║
║       Technical Analysis + GPT-4 Final Decision             ║
║       Fixes: crash recovery, open trade persistence,        ║
║              qty precision, desktop alerts, perf tracking,  ║
║              real-time 30s monitoring between cycles        ║
╚══════════════════════════════════════════════════════════════╝
"""

import time
import json
import logging
import datetime
import requests
import numpy as np
import winsound          # Windows beep alerts
import sys
import io
from typing import Optional
from openai import OpenAI
from binance.client import Client
from binance.exceptions import BinanceAPIException
import config

# ─── Fix Windows console encoding (shows emojis properly) ────
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# ─── Logging Setup ────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(message)s',
    handlers=[
        logging.FileHandler(config.LOG_FILE, encoding='utf-8'),
        logging.StreamHandler(stream=open(
            sys.stdout.fileno(), mode='w', encoding='utf-8', closefd=False
        ))
    ]
)
log = logging.getLogger("TradingAgent")

# ─── OpenAI Client ────────────────────────────────────────────
gpt_client = OpenAI(api_key=config.OPENAI_API_KEY)


# ══════════════════════════════════════════════════════════════
#   DESKTOP ALERT SYSTEM
#   Since you are always at your seat — sound + popup
# ══════════════════════════════════════════════════════════════

def alert_sound(alert_type: str):
    """
    Play a Windows beep sound based on alert type.
    No third-party library needed.
    """
    try:
        if alert_type == "BUY":
            # 3 ascending beeps = BUY signal
            winsound.Beep(800,  200)
            winsound.Beep(1000, 200)
            winsound.Beep(1200, 400)
        elif alert_type == "SELL":
            # 3 descending beeps = SELL / close trade
            winsound.Beep(1200, 200)
            winsound.Beep(1000, 200)
            winsound.Beep(800,  400)
        elif alert_type == "PROFIT":
            # Happy tune = take profit hit
            winsound.Beep(1000, 150)
            winsound.Beep(1200, 150)
            winsound.Beep(1500, 400)
        elif alert_type == "LOSS":
            # Low beep = stop loss hit
            winsound.Beep(500, 600)
        elif alert_type == "WARNING":
            # Single warning beep
            winsound.Beep(600, 500)
        elif alert_type == "STARTUP":
            # Startup chime
            winsound.Beep(600,  150)
            winsound.Beep(800,  150)
            winsound.Beep(1000, 150)
            winsound.Beep(1200, 300)
    except Exception:
        pass  # If sound fails, continue silently


def desktop_notify(title: str, message: str):
    """
    Windows 10/11 toast notification using PowerShell.
    No extra libraries needed.
    """
    try:
        import subprocess
        # Escape single quotes in message
        title   = title.replace("'", "")
        message = message.replace("'", "")
        ps_script = f"""
Add-Type -AssemblyName System.Windows.Forms
$notify = New-Object System.Windows.Forms.NotifyIcon
$notify.Icon = [System.Drawing.SystemIcons]::Information
$notify.Visible = $true
$notify.ShowBalloonTip(8000, '{title}', '{message}', [System.Windows.Forms.ToolTipIcon]::None)
Start-Sleep -Seconds 9
$notify.Dispose()
"""
        subprocess.Popen(
            ["powershell", "-WindowStyle", "Hidden", "-Command", ps_script],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
    except Exception:
        pass  # Notification failed silently — log already covers it


def notify_buy(symbol: str, price: float, usdt: float, confidence: int, reasoning: str):
    msg = f"{symbol} @ ${price:.4f} | ${usdt} USDT | GPT {confidence}% | {reasoning}"
    log.info(f"🔔 ALERT BUY: {msg}")
    alert_sound("BUY")
    desktop_notify(f"BUY SIGNAL — {symbol}", msg)


def notify_close(symbol: str, price: float, pnl: float, reason: str):
    alert_type = "PROFIT" if pnl > 0 else "LOSS"
    emoji      = "💰" if pnl > 0 else "💸"
    msg        = f"{symbol} @ ${price:.4f} | PnL: ${pnl:.2f} | {reason}"
    log.info(f"🔔 ALERT CLOSE: {msg}")
    alert_sound(alert_type)
    desktop_notify(f"{emoji} TRADE CLOSED — {symbol}", msg)


def notify_warning(message: str):
    log.warning(f"🔔 WARNING: {message}")
    alert_sound("WARNING")
    desktop_notify("⚠️ Bot Warning", message)


# ══════════════════════════════════════════════════════════════
#   GPT ANALYSIS ENGINE
# ══════════════════════════════════════════════════════════════

def gpt_analyze(analysis: dict) -> dict:
    symbol  = analysis["symbol"]
    price   = analysis["price"]
    score   = analysis["score"]
    reasons = "\n".join(analysis["reasons"])
    fg      = analysis["fear_greed"]

    prompt = f"""You are an expert crypto trading analyst. Based on the technical analysis below, give a final trading decision.

COIN: {symbol}
CURRENT PRICE: ${price}
TECHNICAL SCORE: {score}/10  (positive = bullish, negative = bearish)
RSI: {analysis['rsi']}
MACD: {analysis['macd']}
BB POSITION: {analysis['bb_position']}
EMA TREND: {analysis['ema_trend']}
VOLUME: {analysis['volume']}
FEAR & GREED INDEX: {fg['value']} ({fg['label']})
BTC DOMINANCE: {analysis['btc_dom']}%
ATR VOLATILITY: {analysis['atr_pct']}%

TECHNICAL INDICATORS BREAKDOWN:
{reasons}

RISK CONFIG:
- Stop Loss: {config.STOP_LOSS_PCT}%
- Take Profit: {config.TAKE_PROFIT_PCT}%
- Max per trade: ${config.MAX_PER_TRADE_USDT}

Respond ONLY in this exact JSON format (no markdown, no extra text):
{{
  "signal": "BUY" or "SELL" or "HOLD",
  "confidence": <integer 1-100>,
  "reasoning": "<one clear sentence, max 20 words>",
  "entry_price": <number>,
  "stop_loss": <number>,
  "take_profit": <number>,
  "risk_level": "LOW" or "MEDIUM" or "HIGH",
  "override_technical": <true or false>,
  "override_reason": "<only if override_technical is true, else empty string>"
}}"""

    try:
        response = gpt_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a professional crypto trading analyst. "
                        "Always respond with valid JSON only. "
                        "No markdown, no explanation outside JSON. "
                        "Be conservative — capital preservation is priority."
                    )
                },
                {"role": "user", "content": prompt}
            ],
            temperature=0.2,
            max_tokens=400,
        )

        raw    = response.choices[0].message.content.strip()
        raw    = raw.replace("```json", "").replace("```", "").strip()
        result = json.loads(raw)

        required = ["signal", "confidence", "reasoning", "entry_price",
                    "stop_loss", "take_profit", "risk_level"]
        for key in required:
            if key not in result:
                raise ValueError(f"Missing key: {key}")

        log.info(f"🤖 GPT Decision for {symbol}:")
        log.info(f"   Signal:     {result['signal']} ({result['confidence']}% confidence)")
        log.info(f"   Reasoning:  {result['reasoning']}")
        log.info(f"   Risk Level: {result['risk_level']}")
        log.info(f"   Entry: ${result['entry_price']} | SL: ${result['stop_loss']} | TP: ${result['take_profit']}")
        if result.get("override_technical"):
            log.warning(f"   ⚠️  GPT OVERRIDING TECHNICAL: {result['override_reason']}")

        return result

    except json.JSONDecodeError as e:
        log.error(f"❌ GPT returned invalid JSON for {symbol}: {e}")
        return _fallback_signal(analysis)
    except Exception as e:
        log.error(f"❌ GPT API error for {symbol}: {e}")
        return _fallback_signal(analysis)


def _fallback_signal(analysis: dict) -> dict:
    score = analysis["score"]
    price = analysis["price"]
    if score >= 4:
        signal = "BUY"
    elif score <= -4:
        signal = "SELL"
    else:
        signal = "HOLD"
    return {
        "signal":             signal,
        "confidence":         min(abs(score) * 10, 70),
        "reasoning":          "Fallback: GPT unavailable, using technical score only",
        "entry_price":        price,
        "stop_loss":          round(price * (1 - config.STOP_LOSS_PCT / 100), 6),
        "take_profit":        round(price * (1 + config.TAKE_PROFIT_PCT / 100), 6),
        "risk_level":         "MEDIUM",
        "override_technical": False,
        "override_reason":    "",
    }


def gpt_market_summary(opportunities: list, fear_greed: dict, btc_dom: float) -> str:
    if not opportunities:
        return "No opportunities found this cycle."

    coins_info = "\n".join([
        f"- {o['symbol']}: Score {o['score']}, RSI {o['rsi']}, Signal {o['signal']}"
        for o in opportunities[:5]
    ])

    prompt = f"""Crypto market quick summary in 2-3 sentences:

Fear & Greed: {fear_greed['value']} ({fear_greed['label']})
BTC Dominance: {btc_dom}%

Top Opportunities:
{coins_info}

Give a brief market overview and whether this is a good time to trade."""

    try:
        response = gpt_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=150,
        )
        return response.choices[0].message.content.strip()
    except Exception:
        return "Market summary unavailable."


# ══════════════════════════════════════════════════════════════
#   TECHNICAL ANALYSIS ENGINE
# ══════════════════════════════════════════════════════════════

def calc_rsi(closes: list, period: int = 14) -> float:
    closes = np.array(closes[-period-1:], dtype=float)
    deltas = np.diff(closes)
    gains  = np.where(deltas > 0, deltas, 0)
    losses = np.where(deltas < 0, -deltas, 0)
    avg_gain = np.mean(gains[:period])
    avg_loss = np.mean(losses[:period])
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return round(100 - (100 / (1 + rs)), 2)

def calc_ema(closes: list, period: int) -> float:
    closes = np.array(closes, dtype=float)
    k      = 2 / (period + 1)
    ema    = closes[0]
    for price in closes[1:]:
        ema = price * k + ema * (1 - k)
    return round(ema, 6)

def calc_macd(closes: list):
    ema12 = calc_ema(closes, 12)
    ema26 = calc_ema(closes, 26)
    macd_line   = ema12 - ema26
    macd_series = []
    for i in range(9, len(closes)):
        e12 = calc_ema(closes[:i], 12)
        e26 = calc_ema(closes[:i], 26)
        macd_series.append(e12 - e26)
    signal = calc_ema(macd_series, 9) if len(macd_series) >= 9 else macd_line
    return round(macd_line, 6), round(signal, 6), round(macd_line - signal, 6)

def calc_bollinger_bands(closes: list, period: int = 20):
    closes = np.array(closes[-period:], dtype=float)
    sma    = np.mean(closes)
    std    = np.std(closes)
    return round(sma + 2*std, 6), round(sma, 6), round(sma - 2*std, 6)

def calc_atr(highs, lows, closes, period: int = 14) -> float:
    trs = []
    for i in range(1, len(closes)):
        tr = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i-1]),
            abs(lows[i]  - closes[i-1])
        )
        trs.append(tr)
    return round(np.mean(trs[-period:]), 6)

def calc_volume_signal(volumes: list) -> str:
    avg_vol  = np.mean(volumes[-20:-1])
    curr_vol = volumes[-1]
    ratio    = curr_vol / avg_vol if avg_vol > 0 else 1
    if ratio > 1.5:   return "HIGH"
    elif ratio > 1.0: return "NORMAL"
    else:             return "LOW"

def get_fear_greed_index() -> dict:
    try:
        r    = requests.get("https://api.alternative.me/fng/?limit=1", timeout=5)
        data = r.json()["data"][0]
        return {"value": int(data["value"]), "label": data["value_classification"]}
    except Exception:
        return {"value": 50, "label": "Neutral"}

def get_btc_dominance() -> float:
    try:
        r = requests.get("https://api.coingecko.com/api/v3/global", timeout=5)
        return round(r.json()["data"]["market_cap_percentage"]["btc"], 2)
    except Exception:
        return 50.0

def analyze_coin(symbol: str, klines: list, fear_greed: dict, btc_dom: float) -> dict:
    closes  = [float(k[4]) for k in klines]
    highs   = [float(k[2]) for k in klines]
    lows    = [float(k[3]) for k in klines]
    volumes = [float(k[5]) for k in klines]
    current_price = closes[-1]
    score   = 0
    reasons = []

    # RSI
    rsi = calc_rsi(closes)
    if rsi < 30:
        score += 3; reasons.append(f"✅ RSI Oversold ({rsi}) — BUY zone")
    elif rsi < 45:
        score += 1; reasons.append(f"🟡 RSI low ({rsi}) — Slight bullish")
    elif rsi > 70:
        score -= 3; reasons.append(f"❌ RSI Overbought ({rsi}) — SELL zone")
    elif rsi > 60:
        score -= 1; reasons.append(f"🟡 RSI high ({rsi}) — Caution")
    else:
        reasons.append(f"➡️  RSI Neutral ({rsi})")

    # MACD
    macd_line, signal_line, histogram = calc_macd(closes)
    if macd_line > signal_line and histogram > 0:
        score += 2; reasons.append("✅ MACD Bullish crossover")
    elif macd_line < signal_line and histogram < 0:
        score -= 2; reasons.append("❌ MACD Bearish crossover")
    else:
        reasons.append("➡️  MACD Neutral")

    # Bollinger Bands
    bb_upper, bb_mid, bb_lower = calc_bollinger_bands(closes)
    if current_price < bb_lower:
        score += 2; reasons.append("✅ Price below BB Lower — Oversold bounce likely")
    elif current_price > bb_upper:
        score -= 2; reasons.append("❌ Price above BB Upper — Overbought")
    elif current_price < bb_mid:
        score += 1; reasons.append("🟡 Price below BB Mid — Slight bullish")

    # EMA Trend
    ema20 = calc_ema(closes, 20)
    ema50 = calc_ema(closes, 50)
    if current_price > ema20 > ema50:
        score += 2; reasons.append("✅ Strong uptrend (Price > EMA20 > EMA50)")
    elif current_price < ema20 < ema50:
        score -= 2; reasons.append("❌ Strong downtrend (Price < EMA20 < EMA50)")
    elif current_price > ema50:
        score += 1; reasons.append("🟡 Above EMA50 — Mild bullish")

    # Volume
    vol_signal = calc_volume_signal(volumes)
    if vol_signal == "HIGH" and score > 0:
        score += 1; reasons.append("✅ High volume confirms bullish move")
    elif vol_signal == "HIGH" and score < 0:
        score -= 1; reasons.append("❌ High volume confirms bearish move")
    elif vol_signal == "LOW":
        score -= 1; reasons.append("⚠️  Low volume — signal not confirmed")

    # Fear & Greed
    fg = fear_greed["value"]
    if fg < 25:
        score += 2; reasons.append(f"✅ Extreme Fear ({fg}) — Historically good buy time")
    elif fg < 40:
        score += 1; reasons.append(f"🟡 Fear ({fg}) — Cautious buy")
    elif fg > 75:
        score -= 2; reasons.append(f"❌ Extreme Greed ({fg}) — Market may be overheated")
    elif fg > 60:
        score -= 1; reasons.append(f"🟡 Greed ({fg}) — Be cautious")

    # BTC Dominance
    if symbol != "BTCUSDT":
        if btc_dom > 60:
            score -= 1; reasons.append(f"⚠️  BTC Dominance high ({btc_dom}%) — Alts weak")
        elif btc_dom < 45:
            score += 1; reasons.append(f"✅ BTC Dom low ({btc_dom}%) — Alt season possible")

    # ATR Volatility
    atr     = calc_atr(highs, lows, closes)
    atr_pct = (atr / current_price) * 100
    if atr_pct > 5:
        score -= 1; reasons.append(f"⚠️  High volatility (ATR {atr_pct:.1f}%) — Risky")

    # Signal
    if score >= 6:    signal = "STRONG_BUY"
    elif score >= 3:  signal = "BUY"
    elif score <= -6: signal = "STRONG_SELL"
    elif score <= -3: signal = "SELL"
    else:             signal = "HOLD"

    return {
        "symbol":      symbol,
        "price":       current_price,
        "score":       score,
        "signal":      signal,
        "rsi":         rsi,
        "macd":        macd_line,
        "bb_position": "BELOW" if current_price < bb_lower else ("ABOVE" if current_price > bb_upper else "INSIDE"),
        "ema_trend":   "UP" if current_price > ema50 else "DOWN",
        "volume":      vol_signal,
        "fear_greed":  fear_greed,
        "btc_dom":     btc_dom,
        "reasons":     reasons,
        "atr_pct":     round(atr_pct, 2),
        "timestamp":   datetime.datetime.now().isoformat(),
    }


# ══════════════════════════════════════════════════════════════
#   TRADE MANAGER
# ══════════════════════════════════════════════════════════════

class TradeManager:
    def __init__(self, client: Client):
        self.client      = client
        self.daily_pnl   = 0.0
        self.trade_count = 0
        self.open_trades = self._load_open_trades()   # FIX: persist across restarts
        self.history     = self._load_history()
        self._symbol_precision_cache = {}

    # ── Persistence ───────────────────────────────────────────

    def _load_history(self) -> list:
        try:
            with open(config.TRADE_HISTORY_FILE, "r") as f:
                return json.load(f)
        except Exception:
            return []

    def _save_history(self):
        with open(config.TRADE_HISTORY_FILE, "w") as f:
            json.dump(self.history, f, indent=2)

    def _load_open_trades(self) -> dict:
        """FIX: Load open trades from disk so bot survives restarts"""
        try:
            with open("open_trades.json", "r") as f:
                trades = json.load(f)
                if trades:
                    log.info(f"♻️  Recovered {len(trades)} open trade(s) from previous session:")
                    for sym in trades:
                        log.info(f"   {sym}: Entry ${trades[sym]['entry_price']:.4f}")
                return trades
        except Exception:
            return {}

    def _save_open_trades(self):
        """FIX: Save open trades to disk after every change"""
        with open("open_trades.json", "w") as f:
            json.dump(self.open_trades, f, indent=2)

    # ── Quantity Precision ────────────────────────────────────

    def get_quantity_precision(self, symbol: str) -> int:
        """FIX: Get correct decimal precision per coin from Binance"""
        if symbol in self._symbol_precision_cache:
            return self._symbol_precision_cache[symbol]
        try:
            info = self.client.get_symbol_info(symbol)
            step = next(
                f['stepSize'] for f in info['filters']
                if f['filterType'] == 'LOT_SIZE'
            )
            if '.' in step:
                precision = len(step.rstrip('0').split('.')[-1])
            else:
                precision = 0
            self._symbol_precision_cache[symbol] = precision
            return precision
        except Exception:
            return 5  # safe fallback

    def get_min_notional(self, symbol: str) -> float:
        """Get minimum order value in USDT"""
        try:
            info = self.client.get_symbol_info(symbol)
            for f in info['filters']:
                if f['filterType'] == 'MIN_NOTIONAL':
                    return float(f['minNotional'])
            return 10.0
        except Exception:
            return 10.0

    # ── Balance ───────────────────────────────────────────────

    def get_usdt_balance(self) -> float:
        if config.PAPER_TRADING:
            used = sum(t["usdt_used"] for t in self.open_trades.values())
            return config.TOTAL_BUDGET_USDT - used
        try:
            balance = self.client.get_asset_balance(asset='USDT')
            return float(balance['free'])
        except Exception as e:
            log.error(f"Balance check failed: {e}")
            return 0.0

    def can_open_trade(self, symbol: str) -> tuple:
        if self.daily_pnl <= -config.MAX_DAILY_LOSS_USDT:
            return False, f"Daily loss limit hit (${abs(self.daily_pnl):.2f})"
        if len(self.open_trades) >= config.MAX_OPEN_TRADES:
            return False, f"Max open trades ({config.MAX_OPEN_TRADES}) reached"
        balance = self.get_usdt_balance()
        if balance < config.MAX_PER_TRADE_USDT + config.RESERVE_USDT:
            return False, f"Insufficient balance (${balance:.2f})"
        # FIX: Check minimum order value
        min_notional = self.get_min_notional(symbol)
        if config.MAX_PER_TRADE_USDT < min_notional:
            return False, f"Trade size ${config.MAX_PER_TRADE_USDT} below Binance minimum ${min_notional}"
        return True, "OK"

    # ── Open Trade ────────────────────────────────────────────

    def open_trade(self, analysis: dict, gpt_decision: dict) -> bool:
        symbol = analysis["symbol"]

        if symbol in self.open_trades:
            log.info(f"⏭️  Already in trade for {symbol}")
            return False

        if gpt_decision["confidence"] < config.GPT_MIN_CONFIDENCE:
            log.info(f"⏭️  GPT confidence too low ({gpt_decision['confidence']}%) for {symbol} — skipping")
            return False

        if gpt_decision["risk_level"] == "HIGH":
            log.warning(f"⚠️  GPT flagged HIGH risk for {symbol} — skipping")
            return False

        can_trade, reason = self.can_open_trade(symbol)
        if not can_trade:
            log.warning(f"🚫 Cannot trade: {reason}")
            notify_warning(reason)
            return False

        price    = analysis["price"]
        usdt_amt = config.MAX_PER_TRADE_USDT
        qty      = usdt_amt / price

        stop_loss   = gpt_decision.get("stop_loss",   price * (1 - config.STOP_LOSS_PCT / 100))
        take_profit = gpt_decision.get("take_profit", price * (1 + config.TAKE_PROFIT_PCT / 100))

        trade = {
            "symbol":         symbol,
            "entry_price":    price,
            "quantity":       qty,
            "usdt_used":      usdt_amt,
            "stop_loss":      stop_loss,
            "take_profit":    take_profit,
            "highest_price":  price,
            "signal_score":   analysis["score"],
            "gpt_confidence": gpt_decision["confidence"],
            "gpt_reasoning":  gpt_decision["reasoning"],
            "risk_level":     gpt_decision["risk_level"],
            "opened_at":      datetime.datetime.now().isoformat(),
            "reasons":        analysis["reasons"],
        }

        if not config.PAPER_TRADING:
            try:
                # FIX: Use correct quantity precision
                precision   = self.get_quantity_precision(symbol)
                qty_rounded = round(qty, precision)
                order       = self.client.order_market_buy(
                    symbol=symbol, quoteOrderQty=usdt_amt
                )
                trade["order_id"]  = order["orderId"]
                trade["quantity"]  = qty_rounded
                log.info(f"✅ REAL BUY: {symbol} @ ${price:.4f}")
            except BinanceAPIException as e:
                log.error(f"❌ Buy order failed: {e}")
                return False
        else:
            log.info(f"📄 PAPER BUY: {symbol} @ ${price:.4f} | ${usdt_amt} | GPT: {gpt_decision['confidence']}% conf")

        self.open_trades[symbol] = trade
        self._save_open_trades()   # FIX: persist immediately
        self.trade_count += 1

        log.info(f"   SL: ${stop_loss:.4f} | TP: ${take_profit:.4f} | Risk: {gpt_decision['risk_level']}")
        log.info(f"   GPT: {gpt_decision['reasoning']}")

        # Alert
        notify_buy(symbol, price, usdt_amt, gpt_decision['confidence'], gpt_decision['reasoning'])
        return True

    # ── Exit Conditions ───────────────────────────────────────

    def check_exit_conditions(self, symbol: str, current_price: float) -> Optional[str]:
        if symbol not in self.open_trades:
            return None
        trade = self.open_trades[symbol]

        # Trailing stop update
        if current_price > trade["highest_price"]:
            trade["highest_price"] = current_price
            new_trailing = current_price * (1 - config.TRAILING_STOP_PCT / 100)
            if new_trailing > trade["stop_loss"]:
                trade["stop_loss"] = new_trailing
                self._save_open_trades()  # FIX: persist updated SL
                log.info(f"📈 Trailing stop updated for {symbol}: ${new_trailing:.4f}")

        if current_price >= trade["take_profit"]: return "TAKE_PROFIT"
        if current_price <= trade["stop_loss"]:   return "STOP_LOSS"
        return None

    # ── Close Trade ───────────────────────────────────────────

    def close_trade(self, symbol: str, current_price: float, reason: str):
        if symbol not in self.open_trades:
            return
        trade   = self.open_trades[symbol]
        entry   = trade["entry_price"]
        qty     = trade["quantity"]
        pnl     = (current_price - entry) * qty
        pnl_pct = ((current_price - entry) / entry) * 100

        if not config.PAPER_TRADING:
            try:
                # FIX: Use correct quantity precision
                precision   = self.get_quantity_precision(symbol)
                qty_rounded = round(qty, precision)
                self.client.order_market_sell(symbol=symbol, quantity=qty_rounded)
            except BinanceAPIException as e:
                log.error(f"❌ Sell failed: {e}")
                return

        emoji = "💰" if pnl > 0 else "💸"
        log.info(f"{emoji} CLOSED {symbol} | {reason} | PnL: ${pnl:.2f} ({pnl_pct:.2f}%)")
        self.daily_pnl += pnl

        self.history.append({
            **trade,
            "exit_price":   current_price,
            "closed_at":    datetime.datetime.now().isoformat(),
            "close_reason": reason,
            "pnl_usdt":     round(pnl, 4),
            "pnl_pct":      round(pnl_pct, 2),
        })
        self._save_history()

        del self.open_trades[symbol]
        self._save_open_trades()  # FIX: persist after removal

        # Alert
        notify_close(symbol, current_price, pnl, reason)

    # ── Status & Performance ──────────────────────────────────

    def print_status(self):
        balance = self.get_usdt_balance()
        log.info("─" * 55)
        mode = "📄 PAPER" if config.PAPER_TRADING else "💰 LIVE"
        log.info(f"💼 Balance: ${balance:.2f} | Open: {len(self.open_trades)}/{config.MAX_OPEN_TRADES} | Day PnL: ${self.daily_pnl:.2f} | Mode: {mode}")
        for sym, t in self.open_trades.items():
            log.info(f"   {sym}: Entry ${t['entry_price']:.4f} | SL ${t['stop_loss']:.4f} | TP ${t['take_profit']:.4f} | GPT {t['gpt_confidence']}%")
        log.info("─" * 55)

    def print_performance(self):
        """FIX: Track and display win/loss statistics"""
        if not self.history:
            log.info("📊 No completed trades yet.")
            return
        wins    = [t for t in self.history if t['pnl_usdt'] > 0]
        losses  = [t for t in self.history if t['pnl_usdt'] <= 0]
        total   = sum(t['pnl_usdt'] for t in self.history)
        winrate = len(wins) / len(self.history) * 100
        avg_win = np.mean([t['pnl_usdt'] for t in wins])   if wins   else 0
        avg_loss= np.mean([t['pnl_usdt'] for t in losses]) if losses else 0
        log.info("═" * 55)
        log.info("📊 PERFORMANCE SUMMARY")
        log.info(f"   Total Trades : {len(self.history)}")
        log.info(f"   Win Rate     : {winrate:.1f}%  ({len(wins)}W / {len(losses)}L)")
        log.info(f"   Total PnL    : ${total:.2f}")
        log.info(f"   Avg Win      : ${avg_win:.2f}")
        log.info(f"   Avg Loss     : ${avg_loss:.2f}")
        if losses and wins:
            rr = abs(avg_win / avg_loss) if avg_loss != 0 else 0
            log.info(f"   Risk/Reward  : {rr:.2f}")
        log.info("═" * 55)


# ══════════════════════════════════════════════════════════════
#   MAIN AGENT LOOP
# ══════════════════════════════════════════════════════════════

def main():
    log.info("╔══════════════════════════════════════════╗")
    log.info("║   BINANCE AI TRADING AGENT — GPT MODE    ║")
    log.info(f"║   Mode: {'PAPER 📄' if config.PAPER_TRADING else 'LIVE 💰 ⚠️ '}                          ║")
    log.info(f"║   Budget: ${config.TOTAL_BUDGET_USDT} USDT                    ║")
    log.info("╚══════════════════════════════════════════╝")

    alert_sound("STARTUP")
    desktop_notify("🤖 Trading Bot Started", f"Mode: {'PAPER' if config.PAPER_TRADING else 'LIVE'} | Budget: ${config.TOTAL_BUDGET_USDT}")

    # Binance connect
    client = Client(config.BINANCE_API_KEY, config.BINANCE_API_SECRET)
    try:
        client.ping()
        log.info("✅ Binance API connected")
    except Exception as e:
        log.error(f"❌ Binance connection failed: {e}")
        return

    # GPT test
    try:
        test = gpt_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": "Reply with: OK"}],
            max_tokens=5
        )
        log.info(f"✅ OpenAI GPT connected ({test.choices[0].message.content.strip()})")
    except Exception as e:
        log.error(f"❌ OpenAI API failed: {e}")
        log.error("Check OPENAI_API_KEY in config.py")
        return

    manager = TradeManager(client)
    cycle   = 0

    # Show performance from previous sessions
    manager.print_performance()

    while True:
        cycle += 1
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log.info(f"\n{'═'*55}")
        log.info(f"🔄 CYCLE #{cycle} | {now}")
        log.info(f"{'═'*55}")

        # FIX: Wrap entire cycle in try/except — bot never dies
        try:

            # Midnight reset
            if datetime.datetime.now().hour == 0 and datetime.datetime.now().minute < config.ANALYSIS_INTERVAL_MIN:
                manager.daily_pnl = 0.0
                log.info("🌙 Daily PnL reset")
                manager.print_performance()   # daily summary at midnight

            # Market sentiment
            log.info("🌍 Fetching sentiment data...")
            fear_greed = get_fear_greed_index()
            btc_dom    = get_btc_dominance()
            log.info(f"   F&G: {fear_greed['value']} ({fear_greed['label']}) | BTC Dom: {btc_dom}%")

            # Check exit conditions
            if manager.open_trades:
                for symbol in list(manager.open_trades.keys()):
                    try:
                        curr_price  = float(client.get_symbol_ticker(symbol=symbol)["price"])
                        exit_reason = manager.check_exit_conditions(symbol, curr_price)
                        if exit_reason and config.ENABLE_AUTO_SELL:
                            manager.close_trade(symbol, curr_price, exit_reason)
                    except Exception as e:
                        log.error(f"Exit check error {symbol}: {e}")

            # Analyze all coins
            log.info(f"\n🔍 Technical analysis — {len(config.WATCHLIST)} coins...")
            opportunities = []

            for symbol in config.WATCHLIST:
                try:
                    klines = client.get_klines(
                        symbol=symbol,
                        interval=config.CANDLE_INTERVAL,
                        limit=config.CANDLE_LIMIT
                    )
                    if len(klines) < 50:
                        continue

                    analysis = analyze_coin(symbol, klines, fear_greed, btc_dom)
                    log.info(
                        f"   {symbol:<14} ${analysis['price']:<12.4f} "
                        f"Score: {analysis['score']:+d}  "
                        f"Signal: {analysis['signal']:<14} RSI: {analysis['rsi']}"
                    )

                    if analysis["signal"] in ["BUY", "STRONG_BUY"]:
                        opportunities.append(analysis)

                except Exception as e:
                    log.error(f"Analysis error {symbol}: {e}")

            # FIX: Cap GPT calls to 3 per cycle max to control cost
            if opportunities:
                opportunities.sort(key=lambda x: x["score"], reverse=True)
                opportunities = opportunities[:3]

                summary = gpt_market_summary(opportunities, fear_greed, btc_dom)
                log.info(f"\n🌐 GPT Market Summary: {summary}")
                log.info(f"\n🤖 GPT analyzing {len(opportunities)} opportunity(ies)...")

                for opp in opportunities:
                    if opp["symbol"] in manager.open_trades:
                        log.info(f"   {opp['symbol']} — already in trade")
                        continue

                    gpt_decision = gpt_analyze(opp)

                    if gpt_decision["signal"] == "BUY":
                        manager.open_trade(opp, gpt_decision)
                    else:
                        log.info(
                            f"   GPT overrides technical for {opp['symbol']}: "
                            f"{gpt_decision['signal']} — {gpt_decision['reasoning']}"
                        )

                    time.sleep(1)
            else:
                log.info("   No BUY signals — skipping GPT calls (saving cost)")

            manager.print_status()

        # FIX: Catch any crash in cycle — log and continue
        except KeyboardInterrupt:
            raise  # let Ctrl+C still work
        except Exception as e:
            log.error(f"💥 Cycle #{cycle} crashed: {e} — recovering in 60s")
            notify_warning(f"Bot cycle crashed: {str(e)[:80]}")
            time.sleep(60)
            continue

        # ── Real-time monitoring during sleep ─────────────────
        # Bot sone ki bajaye har 30 sec mein price check karta hai
        # Taake 15 min ke beech bhi TP/SL pakad sake
        wait_sec   = config.ANALYSIS_INTERVAL_MIN * 60
        start_time = time.time()
        elapsed    = 0
        remaining  = wait_sec

        log.info(f"\n⏳ Next cycle in {config.ANALYSIS_INTERVAL_MIN} min | Monitoring open trades every 30s...")

        while elapsed < wait_sec:
            time.sleep(min(30, remaining))  # 30 sec ya jitna bacha ho
            elapsed   = time.time() - start_time
            remaining = wait_sec - elapsed

            # Open trades hain to price check karo
            if manager.open_trades and config.ENABLE_AUTO_SELL:
                for symbol in list(manager.open_trades.keys()):
                    try:
                        curr_price  = float(client.get_symbol_ticker(symbol=symbol)["price"])
                        exit_reason = manager.check_exit_conditions(symbol, curr_price)

                        if exit_reason:
                            manager.close_trade(symbol, curr_price, exit_reason)
                            log.info(f"⚡ Real-time exit: {symbol} @ ${curr_price:.4f} | {exit_reason}")
                        else:
                            # Live price dikhao taake tum dekh sako
                            trade    = manager.open_trades.get(symbol)
                            if trade:
                                unreal_pnl = (curr_price - trade['entry_price']) * trade['quantity']
                                log.info(
                                    f"   👁️  {symbol} @ ${curr_price:.4f} | "
                                    f"Unrealized PnL: ${unreal_pnl:.2f} | "
                                    f"SL: ${trade['stop_loss']:.4f} | "
                                    f"TP: ${trade['take_profit']:.4f} | "
                                    f"Next scan: {max(0, int(remaining))}s"
                                )
                    except Exception as e:
                        log.error(f"Monitor error {symbol}: {e}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log.info("\n🛑 Agent stopped by user. Goodbye!")
        alert_sound("WARNING")
        desktop_notify("🛑 Bot Stopped", "Trading agent was manually stopped.")