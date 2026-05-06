from fastapi import FastAPI, HTTPException, BackgroundTasks, Response
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import threading
import json
import os
from typing import List, Optional
import datetime

import smart_config as cfg
from smart_agent import SmartHalalBot
from smart_analysis import get_fear_greed_index, get_btc_dominance

app = FastAPI(title="Smart Halal Trading API")

# Enable CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global bot instance
bot = SmartHalalBot()

class CloseTradeRequest(BaseModel):
    symbol: str

@app.on_event("startup")
async def startup_event():
    # Automatically start the bot on API startup
    bot.start()

@app.get("/status")
def get_status():
    balance = bot.manager.get_usdt_balance()
    return {
        "is_running": bot.is_running,
        "cycle": bot.cycle,
        "daily_pnl": round(bot.manager.daily_pnl, 2),
        "daily_trades": bot.manager.daily_new_trades,
        "max_daily_trades": cfg.MAX_DAILY_TRADES,
        "balance": round(balance, 2),
        "open_trades_count": len(bot.manager.open_trades),
        "consecutive_losses": bot.manager.consecutive_losses,
        "mode": "PAPER" if cfg.PAPER_TRADING else "LIVE",
        "timestamp": datetime.datetime.now().isoformat()
    }

@app.get("/trades/open")
def get_open_trades():
    # Refresh current prices and PnL
    trades = []
    for symbol, t in bot.manager.open_trades.items():
        try:
            curr_price = float(bot.client.get_symbol_ticker(symbol=symbol)["price"])
            pnl = (curr_price - t['entry_price']) * t['quantity']
            pnl_pct = ((curr_price - t['entry_price']) / t['entry_price']) * 100
            trades.append({
                **t,
                "current_price": curr_price,
                "pnl_usdt": round(pnl, 2),
                "pnl_pct": round(pnl_pct, 2)
            })
        except:
            trades.append(t)
    return trades

@app.get("/trades/history")
def get_history(limit: int = 20):
    return bot.manager.history[-limit:]

@app.get("/analysis")
def get_all_analysis():
    # Return sorted by score
    sorted_analysis = sorted(
        bot.latest_analysis.values(), 
        key=lambda x: x['score'], 
        reverse=True
    )
    # Convert numpy types to native python types and return as JSONResponse to avoid FastAPI encoder issues
    json_data = json.loads(json.dumps(sorted_analysis, default=str))
    return JSONResponse(content=json_data)

@app.post("/trades/close")
def close_trade(req: CloseTradeRequest):
    print(f"📥 API: Received manual close request for {req.symbol}")
    success, message = bot.manual_close(req.symbol)
    print(f"📤 API: Manual close result: {success} - {message}")
    if not success:
        raise HTTPException(status_code=400, detail=message)
    return {"message": message}

@app.post("/bot/start")
def start_bot():
    bot.start()
    return {"message": "Bot started"}

@app.post("/bot/stop")
def stop_bot():
    bot.stop()
    return {"message": "Bot stopped"}

@app.get("/market")
def get_market():
    fg = get_fear_greed_index()
    btc_dom = get_btc_dominance()
    return {
        "fear_greed": fg,
        "btc_dominance": btc_dom
    }

@app.get("/logs")
def get_logs(lines: int = 50):
    if not os.path.exists(cfg.LOG_FILE):
        return []
    with open(cfg.LOG_FILE, "r", encoding="utf-8") as f:
        return f.readlines()[-lines:]

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
