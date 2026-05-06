"""
╔══════════════════════════════════════════════════════════════╗
║       GPT BRAIN — Deep Analysis + Jarvis Conversation       ║
║       Not just signal confirmation — actual reasoning        ║
╚══════════════════════════════════════════════════════════════╝
"""

import json
import logging
import datetime
from openai import OpenAI

import smart_config as cfg

log = logging.getLogger("SmartAgent")
gpt_client = OpenAI(api_key=cfg.OPENAI_API_KEY)


def gpt_deep_analyze(analysis: dict, learning_summary: str) -> dict:
    """
    Unlike the old agent that just confirmed signals, this one:
    1. Considers multi-timeframe data
    2. Reads past trade performance (learning)
    3. Evaluates support/resistance levels
    4. Sets dynamic SL/TP based on ATR
    5. Only recommends LONG (halal - no shorting)
    """
    symbol = analysis["symbol"]
    price = analysis["price"]
    score = analysis["score"]
    reasons = "\n".join(analysis["reasons"])
    fg = analysis["fear_greed"]
    sr = analysis.get("support_resistance", {})
    trend = analysis.get("trend", {})

    # Build timeframe summary
    tf_summary = ""
    for tf_name, tf_data in analysis.get("tf_results", {}).items():
        tf_summary += f"  {tf_name.upper()}: Score {tf_data['score']:+d}, Signal {tf_data['signal']}, RSI {tf_data['rsi']}, EMA {tf_data['ema_trend']}\n"

    prompt = f"""You are JARVIS — an expert crypto analyst who ONLY recommends LONG trades (halal, no shorting).
Your job is to protect capital first, profit second. Be VERY selective.

═══════════════════════════════════════
COIN: {symbol} | PRICE: ${price}
═══════════════════════════════════════

MULTI-TIMEFRAME ANALYSIS:
{tf_summary}
Combined Score: {score} | Timeframes Agreeing: {analysis.get('tf_agreement', 0)}/3

KEY INDICATORS:
- RSI: {analysis['rsi']}
- MACD Trend: {analysis.get('macd_trend', 'N/A')}
- EMA Trend: {analysis['ema_trend']}
- BB Position: {analysis['bb_position']}
- Volume: {analysis['volume']} (Trend: {analysis.get('volume_trend', 'N/A')})
- ATR Volatility: {analysis['atr_pct']}%

SUPPORT & RESISTANCE:
- Nearest Support: ${sr.get('nearest_support', 'N/A')} (dist: {sr.get('support_distance_pct', 'N/A')}%)
- Nearest Resistance: ${sr.get('nearest_resistance', 'N/A')} (dist: {sr.get('resistance_distance_pct', 'N/A')}%)
- S/R Risk:Reward: {sr.get('risk_reward_sr', 'N/A')}

TREND ANALYSIS:
- Direction: {trend.get('direction', 'N/A')}
- Strength: {trend.get('strength', 'N/A')}  
- EMA Alignment: {trend.get('ema_alignment', 'N/A')}/5
- 5-candle momentum: {trend.get('roc_5', 'N/A')}%
- 20-candle momentum: {trend.get('roc_20', 'N/A')}%

MARKET SENTIMENT:
- Fear & Greed: {fg['value']} ({fg['label']})
- BTC Dominance: {analysis['btc_dom']}%

DETAILED BREAKDOWN:
{reasons}

LEARNING FROM PAST TRADES:
{learning_summary}

═══════════════════════════════════════
STRICT RULES (MUST FOLLOW):
1. ONLY recommend BUY (long) — NEVER short. This is halal trading.
2. Need AT LEAST 2 timeframes agreeing bullish to buy.
3. Set stop_loss based on nearest support level and ATR, NOT a fixed percentage.
4. Set take_profit based on nearest resistance level.
5. If past trades on this coin were mostly losses, be EXTRA cautious.
6. If volume is LOW, prefer HOLD.
7. If trend is DOWN or FLAT, prefer HOLD even if RSI is low.
8. Confidence must reflect how many factors align, not just one indicator.
═══════════════════════════════════════

Respond ONLY in this JSON format:
{{
  "signal": "BUY" or "HOLD",
  "confidence": <integer 1-100>,
  "reasoning": "<detailed reasoning in 2-3 sentences>",
  "entry_price": <current price or slightly below>,
  "stop_loss": <based on support + ATR>,
  "take_profit": <based on resistance>,
  "risk_level": "LOW" or "MEDIUM" or "HIGH",
  "risk_reward_ratio": <number>,
  "key_factors": ["<factor1>", "<factor2>", "<factor3>"],
  "warnings": ["<warning1>", "<warning2>"]
}}"""

    try:
        response = gpt_client.chat.completions.create(
            model=cfg.GPT_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are JARVIS, a professional crypto trading AI. "
                        "You ONLY trade LONG positions (halal). "
                        "You are extremely conservative. Capital preservation > profits. "
                        "NEVER recommend buying in a downtrend. "
                        "NEVER recommend buying with low volume. "
                        "You learn from past mistakes and avoid repeating them. "
                        "Respond ONLY with valid JSON."
                    )
                },
                {"role": "user", "content": prompt}
            ],
            temperature=0.15,
            max_tokens=600,
        )

        raw = response.choices[0].message.content.strip()
        raw = raw.replace("```json", "").replace("```", "").strip()
        result = json.loads(raw)

        required = ["signal", "confidence", "reasoning", "entry_price",
                     "stop_loss", "take_profit", "risk_level"]
        for key in required:
            if key not in result:
                raise ValueError(f"Missing key: {key}")

        # Force LONG only (no SELL signal for opening trades)
        if result["signal"] not in ["BUY", "HOLD"]:
            result["signal"] = "HOLD"

        log.info(f"🤖 JARVIS Decision for {symbol}:")
        log.info(f"   Signal:      {result['signal']} ({result['confidence']}%)")
        log.info(f"   Reasoning:   {result['reasoning']}")
        log.info(f"   Risk:        {result['risk_level']} | R:R = {result.get('risk_reward_ratio', 'N/A')}")
        log.info(f"   Entry: ${result['entry_price']} | SL: ${result['stop_loss']} | TP: ${result['take_profit']}")
        if result.get("warnings"):
            for w in result["warnings"]:
                log.warning(f"   ⚠️ {w}")
        if result.get("key_factors"):
            for f in result["key_factors"]:
                log.info(f"   ✓ {f}")

        return result

    except json.JSONDecodeError as e:
        log.error(f"❌ GPT JSON error for {symbol}: {e}")
        return _fallback(analysis)
    except Exception as e:
        log.error(f"❌ GPT API error for {symbol}: {e}")
        return _fallback(analysis)


def _fallback(analysis: dict) -> dict:
    """Conservative fallback — defaults to HOLD."""
    price = analysis["price"]
    return {
        "signal": "HOLD",
        "confidence": 30,
        "reasoning": "GPT unavailable — defaulting to HOLD for safety",
        "entry_price": price,
        "stop_loss": round(price * (1 - cfg.STOP_LOSS_PCT / 100), 8),
        "take_profit": round(price * (1 + cfg.TAKE_PROFIT_PCT / 100), 8),
        "risk_level": "HIGH",
        "risk_reward_ratio": 0,
        "key_factors": ["FALLBACK"],
        "warnings": ["GPT unavailable"],
    }


def gpt_market_overview(opportunities: list, fear_greed: dict, btc_dom: float,
                         learning_summary: str) -> str:
    """Get market-level overview from GPT before analyzing individual coins."""
    if not opportunities:
        return "No opportunities this cycle."

    coins = "\n".join([
        f"- {o['symbol']}: Score {o['score']}, TF Agreement {o.get('tf_agreement',0)}/3, "
        f"RSI {o['rsi']}, Trend {o.get('trend',{}).get('direction','?')}"
        for o in opportunities[:5]
    ])

    prompt = f"""Quick crypto market analysis (2-3 sentences):

Fear & Greed: {fear_greed['value']} ({fear_greed['label']})
BTC Dominance: {btc_dom}%

Top Signals:
{coins}

Past Performance:
{learning_summary}

Should we be buying right now, or is it better to wait? Be honest and conservative."""

    try:
        response = gpt_client.chat.completions.create(
            model=cfg.GPT_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=200,
        )
        return response.choices[0].message.content.strip()
    except Exception:
        return "Market overview unavailable."


# ══════════════════════════════════════════════════════════════
#   JARVIS CONVERSATIONAL MODE
# ══════════════════════════════════════════════════════════════

class JarvisChat:
    """
    Talk to your trading agent like Jarvis.
    Ask questions, get insights, discuss strategy.
    """

    def __init__(self):
        self.history = [
            {
                "role": "system",
                "content": (
                    "You are JARVIS, a halal crypto trading AI assistant. "
                    "You only trade LONG (no shorting). "
                    "You speak clearly, are honest about risks, and reference the user's "
                    "actual trade history when asked. "
                    "You are friendly but professional. "
                    "When the user asks about market conditions, give actionable insights. "
                    "When asked about past trades, analyze what went wrong and suggest improvements. "
                    "Always remind that crypto is volatile and only trade what you can afford to lose."
                )
            }
        ]

    def chat(self, user_message: str, context: dict = None) -> str:
        """Send a message to Jarvis and get a response."""
        # Add context about current state
        if context:
            context_str = f"\n[CONTEXT: Open trades: {context.get('open_trades', 0)}, "
            context_str += f"Daily PnL: ${context.get('daily_pnl', 0):.2f}, "
            context_str += f"Win rate: {context.get('win_rate', 'N/A')}%, "
            context_str += f"Balance: ${context.get('balance', 0):.2f}]"
            user_message += context_str

        self.history.append({"role": "user", "content": user_message})

        try:
            response = gpt_client.chat.completions.create(
                model=cfg.GPT_JARVIS_MODEL,
                messages=self.history[-10:],  # Keep last 10 messages for context
                temperature=0.4,
                max_tokens=500,
            )
            reply = response.choices[0].message.content.strip()
            self.history.append({"role": "assistant", "content": reply})
            return reply
        except Exception as e:
            return f"Sorry sir, I'm experiencing a connection issue: {e}"
