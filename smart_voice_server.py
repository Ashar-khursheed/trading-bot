"""
╔══════════════════════════════════════════════════════════════╗
║       JARVIS INTELLIGENCE SERVER — LIVE CONNECT              ║
║       Now with Real-Time Market Analysis Capability          ║
╚══════════════════════════════════════════════════════════════╝
"""

import json
import logging
import datetime
from flask import Flask, request, jsonify, send_file, Response
from flask_cors import CORS
from openai import OpenAI
from binance.client import Client

import smart_config as cfg
import smart_analysis as analysis_engine

# ─── Setup ──────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO)
log = logging.getLogger("JarvisBrain")

app = Flask(__name__)
CORS(app)

gpt_client = OpenAI(api_key=cfg.OPENAI_API_KEY)
binance_client = Client(cfg.BINANCE_API_KEY, cfg.BINANCE_API_SECRET)

# ─── System Prompt ───────────────────────────────────────────
SYSTEM_PROMPT = (
    "You are JARVIS, a highly advanced halal trading AI. "
    "You have access to live Binance market data. "
    "\n\n"
    "STYLE GUIDE:\n"
    "- Use a professional Urdu-English mix (Pakistani style).\n"
    "- Address the user as 'Sir' with respect.\n"
    "- Don't be robotic. Be decisive. If a coin looks good, say it. If it looks bad, warn him.\n"
    "- Since you trade LONG-ONLY (Halal), never suggest shorting.\n"
    "- You are smart. If you don't have data, tell the user you are fetching it.\n"
)

# ─── LIVE DATA ENGINE ────────────────────────────────────────

def get_live_coin_data(symbol):
    """Deep analysis of a specific coin for Jarvis to talk about."""
    if not symbol.endswith("USDT"): symbol += "USDT"
    try:
        # Get data for 3 timeframes
        tf_klines = {}
        for tf_name, tf_cfg in cfg.TIMEFRAMES.items():
            klines = binance_client.get_klines(symbol=symbol, interval=tf_cfg["interval"], limit=60)
            tf_klines[tf_name] = klines
            
        fg = analysis_engine.get_fear_greed_index()
        btc_dom = analysis_engine.get_btc_dominance()
        
        # Run our smart analysis engine
        report = analysis_engine.analyze_multi_tf(symbol, tf_klines, fg, btc_dom)
        return report
    except Exception as e:
        log.error(f"Failed to fetch live data for {symbol}: {e}")
        return None

# ─── API ENDPOINTS ───────────────────────────────────────────

@app.route("/")
def index(): return send_file("jarvis_ui.html")

@app.route("/api/chat", methods=["POST"])
def chat():
    data = request.json
    user_msg = data.get("message", "").lower()
    
    # 1. Detect if user is asking about a specific coin
    # Simple logic: check if any watchlist coin or "bitcoin/btc/eth" is mentioned
    target_coin = None
    if "bitcoin" in user_msg or "btc" in user_msg: target_coin = "BTCUSDT"
    elif "ethereum" in user_msg or "eth" in user_msg: target_coin = "ETHUSDT"
    elif "solana" in user_msg or "sol" in user_msg: target_coin = "SOLUSDT"
    
    live_context = ""
    if target_coin:
        log.info(f"🔍 Jarvis fetching live data for {target_coin}")
        analysis = get_live_coin_data(target_coin)
        if analysis:
            live_context = (
                f"\n[LIVE MARKET DATA FOR {target_coin}]\n"
                f"Price: ${analysis['price']}\n"
                f"Technical Score: {analysis['score']}/10\n"
                f"Signal: {analysis['signal']}\n"
                f"Trend: {analysis['trend']['direction']} (Strength: {analysis['trend']['strength']}/100)\n"
                f"RSI: {analysis['rsi']}\n"
                f"Support: ${analysis['support_resistance']['support']}\n"
                f"Resistance: ${analysis['support_resistance']['resistance']}\n"
                f"Fear/Greed: {analysis['fear_greed']['value']} ({analysis['fear_greed']['label']})\n"
            )
    
    # 2. Load Portfolio Context
    try:
        with open(cfg.OPEN_TRADES_FILE, "r") as f:
            open_trades = json.load(f)
    except: open_trades = {}
    
    portfolio_context = f"\n[PORTFOLIO]\nOpen Trades: {len(open_trades)}\n"

    # 3. Call GPT with full intelligence
    try:
        response = gpt_client.chat.completions.create(
            model=cfg.GPT_JARVIS_MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"User asked: {user_msg}\n{live_context}\n{portfolio_context}"}
            ],
            temperature=0.7,
            max_tokens=400
        )
        reply = response.choices[0].message.content.strip()
        
        return jsonify({
            "reply": reply,
            "context": {"total_pnl": 0, "open_trades": len(open_trades), "win_rate": 0, "mode": "PAPER"}
        })
    except Exception as e:
        return jsonify({"reply": "Sir, server disconnect ho gaya hai, ek second rukiye."})

@app.route("/api/tts", methods=["POST"])
def tts():
    text = request.json.get("text", "")
    try:
        # Forcing high-quality ONYX voice
        response = gpt_client.audio.speech.create(
            model="tts-1", voice="onyx", input=text
        )
        return Response(response.content, mimetype="audio/mpeg")
    except: return jsonify({"error": "Voice failed"}), 500

@app.route("/api/status", methods=["GET"])
def status():
    # Placeholder for status polling
    return jsonify({"mode": "PAPER", "open_trades": 0, "total_pnl": 0, "win_rate": 0})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5050, debug=False)
