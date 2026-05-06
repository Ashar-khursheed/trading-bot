"""
╔══════════════════════════════════════════════════════════════╗
║       ADVANCED TECHNICAL ANALYSIS ENGINE                    ║
║       Multi-Timeframe + Support/Resistance + Trend          ║
║       Much deeper than basic candlestick patterns           ║
╚══════════════════════════════════════════════════════════════╝
"""

import numpy as np
import datetime
import logging
import requests
from typing import Optional

import smart_config as cfg

log = logging.getLogger("SmartAgent")


# ══════════════════════════════════════════════════════════════
#   CORE INDICATORS
# ══════════════════════════════════════════════════════════════

def calc_rsi(closes: list, period: int = 14) -> float:
    closes = np.array(closes[-period-1:], dtype=float)
    deltas = np.diff(closes)
    gains = np.where(deltas > 0, deltas, 0)
    losses = np.where(deltas < 0, -deltas, 0)
    avg_gain = np.mean(gains[:period])
    avg_loss = np.mean(losses[:period])
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return round(100 - (100 / (1 + rs)), 2)


def calc_ema(closes: list, period: int) -> float:
    closes = np.array(closes, dtype=float)
    k = 2 / (period + 1)
    ema = closes[0]
    for price in closes[1:]:
        ema = price * k + ema * (1 - k)
    return round(ema, 8)


def calc_ema_series(closes: list, period: int) -> list:
    """Return full EMA series for divergence/crossover detection."""
    closes = np.array(closes, dtype=float)
    k = 2 / (period + 1)
    ema_series = [closes[0]]
    for price in closes[1:]:
        ema_series.append(price * k + ema_series[-1] * (1 - k))
    return ema_series


def calc_macd(closes: list):
    ema12 = calc_ema(closes, 12)
    ema26 = calc_ema(closes, 26)
    macd_line = ema12 - ema26
    macd_series = []
    for i in range(9, len(closes)):
        e12 = calc_ema(closes[:i], 12)
        e26 = calc_ema(closes[:i], 26)
        macd_series.append(e12 - e26)
    signal = calc_ema(macd_series, 9) if len(macd_series) >= 9 else macd_line
    histogram = macd_line - signal
    return round(macd_line, 8), round(signal, 8), round(histogram, 8)


def calc_macd_series(closes: list) -> tuple:
    """Return MACD histogram series for divergence detection."""
    macd_series = []
    signal_series = []
    for i in range(26, len(closes)):
        e12 = calc_ema(closes[:i+1], 12)
        e26 = calc_ema(closes[:i+1], 26)
        macd_series.append(e12 - e26)
    if len(macd_series) >= 9:
        for j in range(9, len(macd_series)):
            signal_series.append(calc_ema(macd_series[:j+1], 9))
    hist = []
    offset = len(macd_series) - len(signal_series)
    for i in range(len(signal_series)):
        hist.append(macd_series[i + offset] - signal_series[i])
    return macd_series, signal_series, hist


def calc_bollinger_bands(closes: list, period: int = 20):
    closes = np.array(closes[-period:], dtype=float)
    sma = np.mean(closes)
    std = np.std(closes)
    return round(sma + 2*std, 8), round(sma, 8), round(sma - 2*std, 8)


def calc_atr(highs, lows, closes, period: int = 14) -> float:
    trs = []
    for i in range(1, len(closes)):
        tr = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i-1]),
            abs(lows[i] - closes[i-1])
        )
        trs.append(tr)
    return round(np.mean(trs[-period:]), 8)


def calc_volume_signal(volumes: list) -> str:
    avg_vol = np.mean(volumes[-20:-1])
    curr_vol = volumes[-1]
    ratio = curr_vol / avg_vol if avg_vol > 0 else 1
    if ratio > 2.0:   return "VERY_HIGH"
    elif ratio > 1.3:  return "HIGH"
    elif ratio > 0.8:  return "NORMAL"
    else:              return "LOW"


def calc_volume_trend(volumes: list, period: int = 10) -> str:
    """Is volume increasing or decreasing over recent candles?"""
    if len(volumes) < period * 2:
        return "UNKNOWN"
    recent = np.mean(volumes[-period:])
    prior = np.mean(volumes[-period*2:-period])
    if prior == 0:
        return "UNKNOWN"
    ratio = recent / prior
    if ratio > 1.3:   return "INCREASING"
    elif ratio < 0.7:  return "DECREASING"
    else:              return "STABLE"


def calc_vwap(closes: list, volumes: list) -> list:
    """Calculate Volume Weighted Average Price (VWAP) series."""
    closes = np.array(closes, dtype=float)
    volumes = np.array(volumes, dtype=float)
    tp = closes # Typical price, using close for simplicity or (H+L+C)/3 if available
    vwap = np.cumsum(tp * volumes) / np.cumsum(volumes)
    return vwap.tolist()


def calc_adx(highs: list, lows: list, closes: list, period: int = 14) -> dict:
    """Calculate Average Directional Index (ADX) to measure trend strength."""
    if len(closes) < period * 2:
        return {"adx": 0, "pdi": 0, "mdi": 0}

    highs = np.array(highs, dtype=float)
    lows = np.array(lows, dtype=float)
    closes = np.array(closes, dtype=float)

    up_move = highs[1:] - highs[:-1]
    down_move = lows[:-1] - lows[1:]

    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0)

    tr = np.array([max(highs[i] - lows[i], abs(highs[i] - closes[i-1]), abs(lows[i] - closes[i-1])) for i in range(1, len(closes))])

    def smooth(data, p):
        res = [np.mean(data[:p])]
        for val in data[p:]:
            res.append((res[-1] * (p - 1) + val) / p)
        return np.array(res)

    tr_s = smooth(tr, period)
    pdm_s = smooth(plus_dm, period)
    mdm_s = smooth(minus_dm, period)

    # Align lengths
    min_len = min(len(tr_s), len(pdm_s), len(mdm_s))
    tr_s = tr_s[-min_len:]
    pdm_s = pdm_s[-min_len:]
    mdm_s = mdm_s[-min_len:]

    pdi = 100 * pdm_s / tr_s
    mdi = 100 * mdm_s / tr_s

    dx = 100 * np.abs(pdi - mdi) / (pdi + mdi)
    adx = smooth(dx, period)

    return {
        "adx": round(adx[-1], 2),
        "pdi": round(pdi[-1], 2),
        "mdi": round(mdi[-1], 2)
    }


def calc_ichimoku(highs: list, lows: list) -> dict:
    """Calculate Ichimoku Cloud components."""
    highs = np.array(highs, dtype=float)
    lows = np.array(lows, dtype=float)

    def donchian(h, l, p):
        res = []
        for i in range(p, len(h) + 1):
            res.append((np.max(h[i-p:i]) + np.min(l[i-p:i])) / 2)
        return np.array(res)

    tenkan = donchian(highs, lows, 9)
    kijun = donchian(highs, lows, 26)

    # Senkou Span A
    span_a = (tenkan[17:] + kijun[:len(tenkan)-17]) / 2 # Offset to match lengths
    # Senkou Span B
    span_b = donchian(highs, lows, 52)

    return {
        "tenkan": tenkan[-1],
        "kijun": kijun[-1],
        "span_a": span_a[-1] if len(span_a) > 0 else 0,
        "span_b": span_b[-1] if len(span_b) > 0 else 0,
        "chikou": highs[-26] if len(highs) > 26 else highs[0]
    }


def detect_bullish_engulfing(opens: list, closes: list) -> bool:
    """Detect bullish engulfing candle pattern."""
    if len(closes) < 2:
        return False
    # Prev candle was bearish
    prev_bearish = closes[-2] < opens[-2]
    # Current candle is bullish
    curr_bullish = closes[-1] > opens[-1]
    # Body engulfs previous body
    engulfs = (opens[-1] <= closes[-2]) and (closes[-1] >= opens[-2])

    return prev_bearish and curr_bullish and engulfs


# ══════════════════════════════════════════════════════════════
#   ADVANCED ANALYSIS
# ══════════════════════════════════════════════════════════════

def find_support_resistance(highs: list, lows: list, closes: list, n: int = 5) -> dict:
    """
    Find key support/resistance levels using swing highs/lows.
    Much more useful than just candlestick patterns.
    """
    highs = np.array(highs, dtype=float)
    lows = np.array(lows, dtype=float)
    current = closes[-1]

    # Find swing highs (local maxima)
    swing_highs = []
    for i in range(n, len(highs) - n):
        if all(highs[i] >= highs[i-j] for j in range(1, n+1)) and \
           all(highs[i] >= highs[i+j] for j in range(1, min(n+1, len(highs)-i))):
            swing_highs.append(highs[i])

    # Find swing lows (local minima)
    swing_lows = []
    for i in range(n, len(lows) - n):
        if all(lows[i] <= lows[i-j] for j in range(1, n+1)) and \
           all(lows[i] <= lows[i+j] for j in range(1, min(n+1, len(lows)-i))):
            swing_lows.append(lows[i])

    # Nearest support = highest swing low below current price
    supports = sorted([s for s in swing_lows if s < current], reverse=True)
    # Nearest resistance = lowest swing high above current price
    resistances = sorted([r for r in swing_highs if r > current])

    nearest_support = supports[0] if supports else current * 0.95
    nearest_resistance = resistances[0] if resistances else current * 1.10

    support_dist_pct = ((current - nearest_support) / current) * 100
    resistance_dist_pct = ((nearest_resistance - current) / current) * 100

    return {
        "nearest_support": round(nearest_support, 8),
        "nearest_resistance": round(nearest_resistance, 8),
        "support_distance_pct": round(support_dist_pct, 2),
        "resistance_distance_pct": round(resistance_dist_pct, 2),
        "support_count": len(supports[:3]),
        "resistance_count": len(resistances[:3]),
        "risk_reward_sr": round(resistance_dist_pct / max(support_dist_pct, 0.1), 2),
    }


def calc_trend_strength(closes: list) -> dict:
    """
    Measure trend strength using ADX-like calculation and price structure.
    """
    if len(closes) < 30:
        return {"strength": "UNKNOWN", "score": 0, "direction": "FLAT"}

    # 1. Price vs multiple EMAs
    ema9 = calc_ema(closes, 9)
    ema21 = calc_ema(closes, 21)
    ema50 = calc_ema(closes, 50)
    current = closes[-1]

    # Count aligned EMAs
    bullish_count = sum([
        current > ema9,
        current > ema21,
        current > ema50,
        ema9 > ema21,
        ema21 > ema50,
    ])

    # 2. Higher highs / higher lows count (last 20 candles)
    recent = closes[-20:]
    hh_count = sum(1 for i in range(1, len(recent)) if recent[i] > recent[i-1])
    hl_pct = hh_count / max(len(recent) - 1, 1)

    # 3. Price momentum (rate of change)
    roc_5 = ((closes[-1] - closes[-6]) / closes[-6]) * 100 if len(closes) >= 6 else 0
    roc_20 = ((closes[-1] - closes[-21]) / closes[-21]) * 100 if len(closes) >= 21 else 0

    # Composite score
    if bullish_count >= 4:
        direction = "STRONG_UP"
        score = bullish_count + (2 if roc_5 > 1 else 0) + (2 if roc_20 > 3 else 0)
    elif bullish_count >= 3:
        direction = "UP"
        score = bullish_count + (1 if roc_5 > 0 else 0)
    elif bullish_count <= 1:
        direction = "STRONG_DOWN"
        score = -bullish_count - (2 if roc_5 < -1 else 0)
    elif bullish_count <= 2:
        direction = "DOWN"
        score = -1
    else:
        direction = "FLAT"
        score = 0

    if abs(score) >= 6:
        strength = "VERY_STRONG"
    elif abs(score) >= 4:
        strength = "STRONG"
    elif abs(score) >= 2:
        strength = "MODERATE"
    else:
        strength = "WEAK"

    return {
        "strength": strength,
        "score": score,
        "direction": direction,
        "ema_alignment": bullish_count,
        "roc_5": round(roc_5, 2),
        "roc_20": round(roc_20, 2),
        "higher_close_pct": round(hl_pct * 100, 1),
    }


def detect_divergence(closes: list, indicator_values: list, lookback: int = 10) -> str:
    """
    Detect bullish/bearish divergence between price and indicator.
    Divergence = price makes new low but indicator doesn't (bullish) or vice versa.
    """
    if len(closes) < lookback or len(indicator_values) < lookback:
        return "NONE"

    price_recent = closes[-lookback:]
    ind_recent = indicator_values[-lookback:]

    price_min_idx = np.argmin(price_recent)
    ind_min_idx = np.argmin(ind_recent)

    # Bullish divergence: price makes lower low, indicator makes higher low
    if price_min_idx > len(price_recent) // 2:  # recent low
        mid = len(price_recent) // 2
        if min(price_recent[mid:]) < min(price_recent[:mid]):
            if min(ind_recent[mid:]) > min(ind_recent[:mid]):
                return "BULLISH"

    # Bearish divergence: price makes higher high, indicator makes lower high
    if np.argmax(price_recent) > len(price_recent) // 2:
        mid = len(price_recent) // 2
        if max(price_recent[mid:]) > max(price_recent[:mid]):
            if max(ind_recent[mid:]) < max(ind_recent[:mid]):
                return "BEARISH"

    return "NONE"


# ══════════════════════════════════════════════════════════════
#   MARKET SENTIMENT
# ══════════════════════════════════════════════════════════════

def get_fear_greed_index() -> dict:
    try:
        r = requests.get("https://api.alternative.me/fng/?limit=1", timeout=5)
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


# ══════════════════════════════════════════════════════════════
#   SINGLE TIMEFRAME ANALYSIS
# ══════════════════════════════════════════════════════════════

def analyze_single_tf(symbol: str, klines: list) -> dict:
    """Analyze a single timeframe and return structured result."""
    closes = [float(k[4]) for k in klines]
    highs = [float(k[2]) for k in klines]
    lows = [float(k[3]) for k in klines]
    volumes = [float(k[5]) for k in klines]
    opens = [float(k[1]) for k in klines]
    current_price = closes[-1]

    score = 0
    reasons = []

    # ─── 1. Basic Indicators ───
    
    # RSI
    rsi = calc_rsi(closes)
    if rsi < 30:
        score += 3; reasons.append(f"✅ RSI Oversold ({rsi})")
    elif rsi < 40:
        score += 1; reasons.append(f"🟡 RSI low ({rsi})")
    elif rsi > 70:
        score -= 3; reasons.append(f"❌ RSI Overbought ({rsi})")
    elif rsi > 65:
        score -= 2; reasons.append(f"🟡 RSI high ({rsi})")

    # MACD
    macd_line, signal_line, histogram = calc_macd(closes)
    if macd_line > signal_line and histogram > 0:
        score += 2; reasons.append("✅ MACD Bullish")
        macd_trend = "BULLISH"
    elif macd_line < signal_line and histogram < 0:
        score -= 2; reasons.append("❌ MACD Bearish")
        macd_trend = "BEARISH"
    else:
        macd_trend = "NEUTRAL"
        reasons.append("➡️ MACD Neutral")

    # Bollinger Bands
    bb_upper, bb_mid, bb_lower = calc_bollinger_bands(closes)
    if current_price < bb_lower:
        score += 2; reasons.append("✅ Below BB Lower")
        bb_pos = "BELOW"
    elif current_price > bb_upper:
        score -= 2; reasons.append("❌ Above BB Upper")
        bb_pos = "ABOVE"
    elif current_price < bb_mid:
        score += 1; reasons.append("🟡 Below BB Mid")
        bb_pos = "LOWER_HALF"
    else:
        bb_pos = "UPPER_HALF"

    # EMA Trends
    ema20 = calc_ema(closes, 20)
    ema50 = calc_ema(closes, 50)
    ema200 = calc_ema(closes, 200)
    if current_price > ema20 > ema50:
        score += 2; reasons.append("✅ Strong uptrend (P>EMA20>EMA50)")
        ema_trend = "STRONG_UP"
    elif current_price < ema20 < ema50:
        score -= 2; reasons.append("❌ Strong downtrend")
        ema_trend = "STRONG_DOWN"
    elif current_price > ema50:
        score += 1; reasons.append("🟡 Above EMA50")
        ema_trend = "MILD_UP"
    else:
        ema_trend = "DOWN"

    # Volume
    vol_signal = calc_volume_signal(volumes)
    vol_trend = calc_volume_trend(volumes)
    if vol_signal in ["HIGH", "VERY_HIGH"] and score > 0:
        score += 1; reasons.append("✅ High volume confirms move")
    elif vol_signal == "LOW":
        score -= 1; reasons.append("⚠️ Low volume — weak signal")

    # ATR
    atr = calc_atr(highs, lows, closes)
    atr_pct = (atr / current_price) * 100

    # Support/Resistance
    sr = find_support_resistance(highs, lows, closes)
    if sr["risk_reward_sr"] >= 2.0:
        score += 1; reasons.append(f"✅ Good R:R at S/R ({sr['risk_reward_sr']:.1f})")
    elif sr["support_distance_pct"] < 1.0:
        score += 1; reasons.append("✅ Near strong support")

    # Trend Strength
    trend = calc_trend_strength(closes)
    if trend["direction"] in ["STRONG_UP", "UP"] and trend["strength"] in ["STRONG", "VERY_STRONG"]:
        score += 2; reasons.append(f"✅ Strong uptrend ({trend['strength']})")
    elif trend["direction"] in ["STRONG_DOWN", "DOWN"]:
        score -= 2; reasons.append(f"❌ Downtrend ({trend['direction']})")

    # ─── 2. Advanced Trading Strategies ───

    # Strategy 1: Trend Following (Momentum)
    # EMA 50/200 crossover + ADX > 25 + Price > VWAP
    adx_data = calc_adx(highs, lows, closes)
    vwap_series = calc_vwap(closes, volumes)
    current_vwap = vwap_series[-1]
    strat_trend = (ema50 > ema200) and (adx_data["adx"] > 25) and (current_price > current_vwap)
    if strat_trend:
        score += 4; reasons.append("🚀 STRAT: Trend Following Active")

    # Strategy 2: Breakout Strategy
    # 20-period high + volume spike (1.5x avg)
    n_period_high = max(highs[-21:-1])
    vol_ratio = volumes[-1] / np.mean(volumes[-20:-1]) if len(volumes) >= 20 else 1
    strat_breakout = (current_price > n_period_high) and (vol_ratio > 1.5)
    if strat_breakout:
        score += 4; reasons.append("💥 STRAT: 20-Period High Breakout")

    # Strategy 3: Mean Reversion (Dip Buying)
    # RSI < 30 + BB Lower Touch + Price < VWAP
    strat_reversion = (rsi < 30) and (current_price <= bb_lower) and (current_price < current_vwap)
    if strat_reversion:
        score += 4; reasons.append("🔄 STRAT: Mean Reversion (Oversold Dip)")

    # Strategy 4: VWAP Strategy
    # Price pulls back to VWAP + Bullish Engulfing
    near_vwap = abs(current_price - current_vwap) / current_vwap < 0.007 # 0.7% range
    engulfing = detect_bullish_engulfing(opens, closes)
    if near_vwap and engulfing:
        score += 4; reasons.append("⚓ STRAT: VWAP Pullback Reversal")

    # Strategy 5: EMA Ribbon + Volume
    # EMAs (8, 13, 21, 34, 55) fanning out upward + Volume increasing
    ema8 = calc_ema(closes, 8)
    ema13 = calc_ema(closes, 13)
    ema21 = calc_ema(closes, 21)
    ema34 = calc_ema(closes, 34)
    ema55 = calc_ema(closes, 55)
    ribbon_fan = (current_price > ema8 > ema13 > ema21 > ema34 > ema55)
    if ribbon_fan and (vol_trend == "INCREASING" or vol_signal in ["HIGH", "VERY_HIGH"]):
        score += 4; reasons.append("🎀 STRAT: EMA Ribbon Bullish Fan")

    # Strategy 6: Ichimoku Cloud Long
    # Price > Cloud, Tenkan > Kijun, Chikou > Price
    ichi = calc_ichimoku(highs, lows)
    ichi_long = (current_price > ichi["span_a"]) and (current_price > ichi["span_b"]) and \
                (ichi["tenkan"] > ichi["kijun"]) and (current_price > ichi["chikou"])
    if ichi_long:
        score += 4; reasons.append("☁️ STRAT: Ichimoku Cloud Bullish")

    # Strategy 7: Higher Highs / Higher Lows (Structure)
    # 70%+ of recent closes are higher + strong uptrend
    if trend["higher_close_pct"] > 70 and trend["direction"] == "STRONG_UP":
        score += 3; reasons.append("🪜 STRAT: Strong H-H/H-L Structure")

    # ─── 3. Final Signal ───
    
    if score >= 12:    signal = "STRONG_BUY"
    elif score >= 6:   signal = "BUY"
    elif score <= -8:  signal = "STRONG_SELL"
    elif score <= -4:  signal = "SELL"
    else:              signal = "HOLD"

    return {
        "symbol": symbol,
        "price": current_price,
        "score": score,
        "signal": signal,
        "rsi": rsi,
        "macd": macd_line,
        "macd_trend": macd_trend,
        "bb_position": bb_pos,
        "ema_trend": ema_trend,
        "volume": vol_signal,
        "volume_trend": vol_trend,
        "atr_pct": round(atr_pct, 2),
        "support_resistance": sr,
        "trend": trend,
        "vwap": round(current_vwap, 8),
        "adx": adx_data["adx"],
        "reasons": reasons,
    }


# ══════════════════════════════════════════════════════════════
#   MULTI-TIMEFRAME ANALYSIS
# ══════════════════════════════════════════════════════════════

def analyze_multi_tf(symbol: str, tf_klines: dict, fear_greed: dict, btc_dom: float) -> dict:
    """
    Analyze a coin across multiple timeframes.
    Only buy when the majority of timeframes agree on direction.
    """
    tf_results = {}
    weighted_score = 0
    bullish_tfs = 0
    total_reasons = []

    for tf_name, klines in tf_klines.items():
        if len(klines) < 50:
            continue
        weight = cfg.TIMEFRAMES[tf_name]["weight"]
        result = analyze_single_tf(symbol, klines)
        tf_results[tf_name] = result
        weighted_score += result["score"] * weight

        if result["signal"] in ["BUY", "STRONG_BUY"]:
            bullish_tfs += 1

        total_reasons.append(f"[{tf_name.upper()}] Score:{result['score']:+d} Signal:{result['signal']}")
        for r in result["reasons"][:3]:
            total_reasons.append(f"  {tf_name}: {r}")

    # Primary timeframe (4h) data for returns
    primary = tf_results.get("4h", tf_results.get("1h", list(tf_results.values())[0] if tf_results else {}))
    entry_tf = tf_results.get("15m", primary)

    # Fear & Greed adjustment
    fg = fear_greed["value"]
    fg_adj = 0
    if fg < 25:
        fg_adj = 3; total_reasons.append(f"✅ Extreme Fear ({fg}) — Best buy zone")
    elif fg < 35:
        fg_adj = 1; total_reasons.append(f"🟡 Fear ({fg}) — Good for buying")
    elif fg > 75:
        fg_adj = -3; total_reasons.append(f"❌ Extreme Greed ({fg}) — Dangerous")
    elif fg > 60:
        fg_adj = -1; total_reasons.append(f"🟡 Greed ({fg}) — Caution")
    weighted_score += fg_adj

    # BTC Dominance
    if symbol != "BTCUSDT":
        if btc_dom > 60:
            weighted_score -= 1
            total_reasons.append(f"⚠️ BTC Dom high ({btc_dom}%)")
        elif btc_dom < 45:
            weighted_score += 1
            total_reasons.append(f"✅ BTC Dom low ({btc_dom}%)")

    # Final signal based on weighted score AND timeframe agreement
    final_score = round(weighted_score, 1)
    if final_score >= cfg.MIN_TECHNICAL_SCORE and bullish_tfs >= cfg.MIN_MULTI_TF_AGREE:
        final_signal = "STRONG_BUY" if final_score >= 8 else "BUY"
    elif final_score <= -5:
        final_signal = "SELL"
    else:
        final_signal = "HOLD"

    return {
        "symbol": symbol,
        "price": entry_tf.get("price", 0),
        "score": final_score,
        "signal": final_signal,
        "tf_results": tf_results,
        "tf_agreement": bullish_tfs,
        "rsi": entry_tf.get("rsi", 50),
        "macd": entry_tf.get("macd", 0),
        "macd_trend": primary.get("macd_trend", "NEUTRAL"),
        "bb_position": entry_tf.get("bb_position", "INSIDE"),
        "ema_trend": primary.get("ema_trend", "FLAT"),
        "volume": entry_tf.get("volume", "NORMAL"),
        "volume_trend": entry_tf.get("volume_trend", "STABLE"),
        "atr_pct": entry_tf.get("atr_pct", 0),
        "fear_greed": fear_greed,
        "btc_dom": btc_dom,
        "reasons": total_reasons,
        "support_resistance": entry_tf.get("support_resistance", {}),
        "trend": primary.get("trend", {}),
        "timestamp": datetime.datetime.now().isoformat(),
    }
