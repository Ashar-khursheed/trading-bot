"""
╔══════════════════════════════════════════════════════════════╗
║       SMART HALAL TRADING AGENT — MAIN ENGINE               ║
║       Long-Only | Multi-TF | Self-Learning | Jarvis Chat    ║
║                                                              ║
║       🕌 Halal Compliant: LONG only, no leverage, spot only  ║
╚══════════════════════════════════════════════════════════════╝

WHAT MAKES THIS SMARTER:
1. Multi-timeframe analysis (15m + 1h + 4h must agree)
2. Support/Resistance-based SL/TP (not fixed %)
3. Self-learning from every trade (pattern recognition)
4. Strict entry criteria (no weak-signal trades)
5. Trend strength validation (don't buy in downtrends)
6. Jarvis conversational interface
7. Breakeven trailing stops
"""

import time
import json
import logging
import datetime
import sys
import io
import threading
import numpy as np
import winsound
from typing import Optional
from binance.client import Client
from binance.exceptions import BinanceAPIException

import smart_config as cfg
from smart_analysis import (
    analyze_multi_tf, get_fear_greed_index, get_btc_dominance
)
from smart_gpt import gpt_deep_analyze, gpt_market_overview, JarvisChat
from smart_learning import LearningEngine

# ─── Fix Windows console encoding ────────────────────────────
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# ─── Logging ─────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(message)s',
    handlers=[
        logging.FileHandler(cfg.LOG_FILE, encoding='utf-8'),
        logging.StreamHandler(stream=open(
            sys.stdout.fileno(), mode='w', encoding='utf-8', closefd=False
        ))
    ]
)
log = logging.getLogger("SmartAgent")


# ══════════════════════════════════════════════════════════════
#   ALERT SYSTEM
# ══════════════════════════════════════════════════════════════

def alert_sound(alert_type: str):
    try:
        sounds = {
            "BUY":     [(800,200),(1000,200),(1200,400)],
            "PROFIT":  [(1000,150),(1200,150),(1500,400)],
            "LOSS":    [(500,600)],
            "WARNING": [(600,500)],
            "STARTUP": [(600,150),(800,150),(1000,150),(1200,300)],
            "JARVIS":  [(1000,100),(1200,100)],
        }
        for freq, dur in sounds.get(alert_type, []):
            winsound.Beep(freq, dur)
    except Exception:
        pass

def desktop_notify(title: str, message: str):
    try:
        import subprocess
        title = title.replace("'", "")
        message = message.replace("'", "")
        ps = f"""
Add-Type -AssemblyName System.Windows.Forms
$n = New-Object System.Windows.Forms.NotifyIcon
$n.Icon = [System.Drawing.SystemIcons]::Information
$n.Visible = $true
$n.ShowBalloonTip(8000, '{title}', '{message}', [System.Windows.Forms.ToolTipIcon]::None)
Start-Sleep -Seconds 9; $n.Dispose()
"""
        subprocess.Popen(
            ["powershell", "-WindowStyle", "Hidden", "-Command", ps],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
    except Exception:
        pass


# ══════════════════════════════════════════════════════════════
#   TRADE MANAGER — LONG ONLY
# ══════════════════════════════════════════════════════════════

class SmartTradeManager:
    def __init__(self, client: Client, learner: LearningEngine):
        self.client = client
        self.learner = learner
        self.daily_pnl = 0.0
        self.trade_count = 0
        self.daily_new_trades = 0          # NEW: daily trade cap
        self.consecutive_losses = 0        # NEW: loss streak tracker
        self.loss_cooldowns = {}           # NEW: {symbol: datetime} cooldown after loss
        self.open_trades = self._load_open_trades()
        self.history = self._load_history()
        self._precision_cache = {}
        self._init_streak_from_history()

    # ── Persistence ───────────────────────────────────────────

    def _load_history(self) -> list:
        try:
            with open(cfg.TRADE_HISTORY_FILE, "r") as f:
                return json.load(f)
        except Exception:
            return []

    def _save_history(self):
        with open(cfg.TRADE_HISTORY_FILE, "w") as f:
            json.dump(self.history, f, indent=2)

    def _load_open_trades(self) -> dict:
        try:
            with open(cfg.OPEN_TRADES_FILE, "r") as f:
                trades = json.load(f)
                if trades:
                    log.info(f"♻️ Recovered {len(trades)} open trade(s):")
                    for sym, t in trades.items():
                        log.info(f"   {sym}: Entry ${t['entry_price']:.4f}")
                return trades
        except Exception:
            return {}

    def _save_open_trades(self):
        with open(cfg.OPEN_TRADES_FILE, "w") as f:
            json.dump(self.open_trades, f, indent=2)

    # ── Precision ─────────────────────────────────────────────

    def get_quantity_precision(self, symbol: str) -> int:
        if symbol in self._precision_cache:
            return self._precision_cache[symbol]
        try:
            info = self.client.get_symbol_info(symbol)
            step = next(f['stepSize'] for f in info['filters'] if f['filterType'] == 'LOT_SIZE')
            precision = len(step.rstrip('0').split('.')[-1]) if '.' in step else 0
            self._precision_cache[symbol] = precision
            return precision
        except Exception:
            return 5

    def get_min_notional(self, symbol: str) -> float:
        try:
            info = self.client.get_symbol_info(symbol)
            for f in info['filters']:
                if f['filterType'] == 'MIN_NOTIONAL':
                    return float(f['minNotional'])
            return 10.0
        except Exception:
            return 10.0

    # ── Balance ───────────────────────────────────────────────

    def _init_streak_from_history(self):
        """Calculate current consecutive loss streak from trade history."""
        streak = 0
        for t in reversed(self.history):
            if t.get('pnl_usdt', 0) <= 0:
                streak += 1
            else:
                break
        self.consecutive_losses = streak
        if streak > 0:
            log.info(f"⚠️ Current loss streak: {streak} consecutive losses")

    def get_usdt_balance(self) -> float:
        if cfg.PAPER_TRADING:
            used = sum(t["usdt_used"] for t in self.open_trades.values())
            return cfg.TOTAL_BUDGET_USDT - used
        try:
            return float(self.client.get_asset_balance(asset='USDT')['free'])
        except Exception:
            return 0.0

    def can_open_trade(self, symbol: str, analysis: dict = None) -> tuple:
        # Check drawdown limit
        total_pnl = sum(t['pnl_usdt'] for t in self.history)
        drawdown = (total_pnl / cfg.TOTAL_BUDGET_USDT) * 100
        if total_pnl < 0 and abs(drawdown) >= cfg.DRAWDOWN_LIMIT_PCT:
            return False, f"Drawdown limit reached ({abs(drawdown):.1f}%) — PAUSING"

        # Daily loss limit
        daily_loss_pct = (abs(self.daily_pnl) / cfg.TOTAL_BUDGET_USDT) * 100
        if self.daily_pnl < 0 and daily_loss_pct >= cfg.MAX_DAILY_LOSS_PCT:
            return False, f"Daily loss limit ({daily_loss_pct:.1f}%)"

        if len(self.open_trades) >= cfg.MAX_OPEN_TRADES:
            return False, f"Max {cfg.MAX_OPEN_TRADES} open trades"

        # NEW: Daily trade cap
        if self.daily_new_trades >= cfg.MAX_DAILY_TRADES:
            return False, f"Daily trade limit ({cfg.MAX_DAILY_TRADES}) — quality over quantity"

        # NEW: Consecutive loss protection
        if self.consecutive_losses >= cfg.MAX_CONSECUTIVE_LOSSES:
            return False, f"🛑 {self.consecutive_losses} consecutive losses — bot paused until a manual reset or next day"

        # NEW: Per-symbol cooldown after loss
        if symbol in self.loss_cooldowns:
            cooldown_until = self.loss_cooldowns[symbol]
            if datetime.datetime.now() < cooldown_until:
                remaining = (cooldown_until - datetime.datetime.now()).total_seconds() / 60
                return False, f"Cooldown active for {symbol} — {remaining:.0f}min remaining"
            else:
                del self.loss_cooldowns[symbol]

        # NEW: Volatility filter
        if analysis and analysis.get("atr_pct"):
            atr_pct = analysis["atr_pct"]
            if atr_pct > cfg.MAX_ATR_PCT:
                return False, f"ATR {atr_pct:.1f}% > {cfg.MAX_ATR_PCT}% — too volatile, skip"
            if atr_pct < cfg.MIN_ATR_PCT:
                return False, f"ATR {atr_pct:.1f}% < {cfg.MIN_ATR_PCT}% — dead market, skip"

        balance = self.get_usdt_balance()
        trade_amt = cfg.TOTAL_BUDGET_USDT * (cfg.MAX_PER_TRADE_PCT / 100)

        # NEW: Reduce position after loss streak
        if self.consecutive_losses >= 2:
            trade_amt *= cfg.LOSS_STREAK_SIZE_REDUCE
            log.info(f"📉 Position reduced to ${trade_amt:.2f} due to {self.consecutive_losses} consecutive losses")

        if balance < trade_amt + cfg.RESERVE_USDT:
            return False, f"Low balance (${balance:.2f}) for ${trade_amt:.2f} trade"

        return True, "OK"

    # ── Open Trade (LONG ONLY) ───────────────────────────────

    def open_trade(self, analysis: dict, gpt_decision: dict) -> bool:
        symbol = analysis["symbol"]

        if symbol in self.open_trades:
            log.info(f"⏭️ Already in {symbol}")
            return False

        # Strict confidence check
        if gpt_decision["confidence"] < cfg.GPT_MIN_CONFIDENCE:
            log.info(f"⏭️ Confidence {gpt_decision['confidence']}% < {cfg.GPT_MIN_CONFIDENCE}% for {symbol}")
            return False

        if gpt_decision["risk_level"] == "HIGH":
            log.warning(f"⚠️ HIGH risk for {symbol} — skipping")
            return False

        # Check learning engine
        should_block, block_reasons = self.learner.should_block_trade(analysis)
        if should_block:
            log.warning(f"🧠 LEARNING BLOCK for {symbol}:")
            for r in block_reasons:
                log.warning(f"   {r}")
            return False

        # Check technical score minimum
        if analysis["score"] < cfg.MIN_TECHNICAL_SCORE:
            log.info(f"⏭️ Score {analysis['score']} < minimum {cfg.MIN_TECHNICAL_SCORE} for {symbol}")
            return False

        # Check timeframe agreement
        if analysis.get("tf_agreement", 0) < cfg.MIN_MULTI_TF_AGREE:
            log.info(f"⏭️ Only {analysis.get('tf_agreement',0)}/{cfg.MIN_MULTI_TF_AGREE} TFs agree for {symbol}")
            return False

        # Pass analysis to can_open_trade for volatility filter
        can_trade, reason = self.can_open_trade(symbol, analysis)
        if not can_trade:
            log.warning(f"🚫 {reason}")
            return False

        price = analysis["price"]
        # Calculate quantity — reduced after loss streaks
        usdt_amt = cfg.TOTAL_BUDGET_USDT * (cfg.MAX_PER_TRADE_PCT / 100)
        if self.consecutive_losses >= 2:
            usdt_amt *= cfg.LOSS_STREAK_SIZE_REDUCE
            log.info(f"📉 Position reduced to ${usdt_amt:.2f} (loss streak: {self.consecutive_losses})")
        qty = usdt_amt / price

        # ── SMART STOP LOSS (the #1 fix for profitability) ──
        atr = (analysis["atr_pct"] / 100) * price if analysis.get("atr_pct") else price * (cfg.STOP_LOSS_PCT / 100)

        # ATR-based stop loss
        atr_stop = price - (atr * cfg.ATR_SL_MULTIPLIER)
        # Support-based stop loss (just below nearest support)
        sr = analysis.get("support_resistance", {})
        support_stop = sr.get("nearest_support", atr_stop) * 0.998  # 0.2% below support
        # GPT recommended stop
        gpt_stop = gpt_decision.get("stop_loss", atr_stop)

        # Use the WIDEST reasonable stop (most protection from noise)
        stop_loss = min(atr_stop, support_stop, gpt_stop)

        # ★ CRITICAL: Enforce minimum SL distance — this was killing trades
        min_sl = price * (1 - cfg.MIN_SL_DISTANCE_PCT / 100)
        if stop_loss > min_sl:
            log.info(f"   🔧 SL ${stop_loss:.4f} too tight → widened to ${min_sl:.4f} ({cfg.MIN_SL_DISTANCE_PCT}% min)")
            stop_loss = min_sl

        # ── SMART TAKE PROFIT with partial exits ──
        risk = abs(price - stop_loss)
        # TP1 = partial exit at 1.5R, TP2 = full exit at 3R
        take_profit_1 = price + (risk * cfg.PARTIAL_TP1_RR)
        take_profit = gpt_decision.get("take_profit", price + (risk * cfg.FULL_TP_RR))

        # Ensure TP meets minimum R:R
        reward = abs(take_profit - price)
        rr = reward / risk if risk > 0 else 0
        if rr < cfg.MIN_RR_RATIO:
            take_profit = price + (risk * cfg.MIN_RR_RATIO)
            reward = abs(take_profit - price)
            rr = reward / risk

        trade = {
            "symbol": symbol,
            "entry_price": price,
            "quantity": qty,
            "original_quantity": qty,        # NEW: track for partial TP
            "usdt_used": usdt_amt,
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "take_profit_1": take_profit_1,  # NEW: partial TP target
            "partial_tp_hit": False,         # NEW: has partial TP been taken?
            "highest_price": price,
            "breakeven_hit": False,
            "signal_score": analysis["score"],
            "gpt_confidence": gpt_decision["confidence"],
            "gpt_reasoning": gpt_decision["reasoning"],
            "risk_level": gpt_decision["risk_level"],
            "opened_at": datetime.datetime.now().isoformat(),
            "reasons": analysis["reasons"][:10],
            # Learning context
            "rsi_at_entry": analysis.get("rsi"),
            "macd_trend": analysis.get("macd_trend"),
            "ema_trend": analysis.get("ema_trend"),
            "volume_signal": analysis.get("volume"),
            "bb_position": analysis.get("bb_position"),
            "fear_greed_at_entry": analysis.get("fear_greed", {}).get("value"),
            "btc_dom_at_entry": analysis.get("btc_dom"),
            "atr_pct_at_entry": analysis.get("atr_pct"),
            "tf_agreement": analysis.get("tf_agreement", 0),
            "support_distance_pct": analysis.get("support_resistance", {}).get("support_distance_pct"),
            "resistance_distance_pct": analysis.get("support_resistance", {}).get("resistance_distance_pct"),
            "trend_strength": analysis.get("trend", {}).get("strength"),
            "hour_of_day": datetime.datetime.now().hour,
        }

        if not cfg.PAPER_TRADING:
            try:
                self.client.order_market_buy(symbol=symbol, quoteOrderQty=usdt_amt)
                log.info(f"✅ REAL BUY: {symbol} @ ${price:.4f}")
            except BinanceAPIException as e:
                log.error(f"❌ Buy failed: {e}")
                return False
        else:
            log.info(f"📄 PAPER BUY: {symbol} @ ${price:.4f} | ${usdt_amt:.2f}")

        self.open_trades[symbol] = trade
        self._save_open_trades()
        self.trade_count += 1
        self.daily_new_trades += 1

        sl_dist = ((price - stop_loss) / price) * 100
        log.info(f"   SL: ${stop_loss:.4f} ({sl_dist:.1f}% away) | TP1: ${take_profit_1:.4f} | TP2: ${take_profit:.4f} | R:R: {rr:.2f}")
        log.info(f"   🤖 {gpt_decision['reasoning']}")

        alert_sound("BUY")
        desktop_notify(f"🟢 BUY — {symbol}", f"${price:.4f} | Conf: {gpt_decision['confidence']}%")
        return True

    # ── Exit Conditions with Breakeven ───────────────────────

    def check_exit_conditions(self, symbol: str, current_price: float) -> Optional[str]:
        if symbol not in self.open_trades:
            return None
        trade = self.open_trades[symbol]
        entry = trade["entry_price"]
        gain_pct = ((current_price - entry) / entry) * 100

        # Update highest price
        if current_price > trade["highest_price"]:
            trade["highest_price"] = current_price

            # Breakeven: once up 5%, move SL to entry + small buffer
            if gain_pct >= cfg.BREAKEVEN_TRIGGER and not trade.get("breakeven_hit"):
                trade["stop_loss"] = entry * 1.002  # 0.2% above entry
                trade["breakeven_hit"] = True
                self._save_open_trades()
                log.info(f"🛡️ BREAKEVEN activated for {symbol} — SL moved to entry+0.2%")

            # ── STEPPED TRAILING STOP (tighter as profit grows) ──
            if gain_pct >= 10:
                trail_pct = cfg.TRAIL_STEP_3_PCT
            elif gain_pct >= 5:
                trail_pct = cfg.TRAIL_STEP_2_PCT
            else:
                trail_pct = cfg.TRAIL_STEP_1_PCT

            new_trailing = current_price * (1 - trail_pct / 100)
            if new_trailing > trade["stop_loss"]:
                trade["stop_loss"] = new_trailing
                self._save_open_trades()
                log.info(f"📈 Stepped Trail ({trail_pct}%): {symbol} SL → ${new_trailing:.4f} | Profit: {gain_pct:.1f}%")

        # ── PARTIAL TAKE PROFIT ──
        if cfg.PARTIAL_TP_ENABLED and not trade.get("partial_tp_hit"):
            tp1 = trade.get("take_profit_1", trade["take_profit"])
            if current_price >= tp1:
                trade["partial_tp_hit"] = True
                sell_qty = trade["original_quantity"] * cfg.PARTIAL_TP_PCT
                trade["quantity"] -= sell_qty
                # Move SL to entry after partial TP (guaranteed profit on remainder)
                trade["stop_loss"] = entry * 1.005
                trade["breakeven_hit"] = True
                self._save_open_trades()
                partial_pnl = (current_price - entry) * sell_qty
                log.info(f"💰 PARTIAL TP: {symbol} sold {cfg.PARTIAL_TP_PCT*100:.0f}% @ ${current_price:.4f} | Partial PnL: ${partial_pnl:.2f}")
                log.info(f"   Remaining {(1-cfg.PARTIAL_TP_PCT)*100:.0f}% trailing to TP2: ${trade['take_profit']:.4f}")
                if not cfg.PAPER_TRADING:
                    try:
                        precision = self.get_quantity_precision(symbol)
                        self.client.order_market_sell(symbol=symbol, quantity=round(sell_qty, precision))
                    except BinanceAPIException as e:
                        log.error(f"❌ Partial sell failed: {e}")
                return None  # Don't fully close yet

        if current_price >= trade["take_profit"]:
            return "TAKE_PROFIT"
        if current_price <= trade["stop_loss"]:
            return "STOP_LOSS"
        return None

    # ── Close Trade ──────────────────────────────────────────

    def close_trade(self, symbol: str, current_price: float, reason: str):
        if symbol not in self.open_trades:
            return
        trade = self.open_trades[symbol]
        entry = trade["entry_price"]
        qty = trade["quantity"]
        pnl = (current_price - entry) * qty
        pnl_pct = ((current_price - entry) / entry) * 100

        if not cfg.PAPER_TRADING:
            try:
                precision = self.get_quantity_precision(symbol)
                self.client.order_market_sell(symbol=symbol, quantity=round(qty, precision))
            except BinanceAPIException as e:
                log.error(f"❌ Sell failed: {e}")
                return False

        emoji = "💰" if pnl > 0 else "💸"
        log.info(f"{emoji} CLOSED {symbol} | {reason} | PnL: ${pnl:.2f} ({pnl_pct:.2f}%)")
        self.daily_pnl += pnl

        # NEW: Track consecutive losses + set cooldown
        if pnl > 0:
            self.consecutive_losses = 0
        else:
            self.consecutive_losses += 1
            # Set cooldown for this symbol after a loss
            cooldown_until = datetime.datetime.now() + datetime.timedelta(hours=cfg.LOSS_COOLDOWN_HOURS)
            self.loss_cooldowns[symbol] = cooldown_until
            log.warning(f"🕐 Cooldown set for {symbol} until {cooldown_until.strftime('%H:%M')} ({cfg.LOSS_COOLDOWN_HOURS}h)")
            if self.consecutive_losses >= cfg.MAX_CONSECUTIVE_LOSSES:
                log.warning(f"🛑 {self.consecutive_losses} CONSECUTIVE LOSSES — Bot will pause new entries!")

        # Record in learning engine
        self.learner.record_trade(trade, current_price, reason)

        self.history.append({
            **trade,
            "exit_price": current_price,
            "closed_at": datetime.datetime.now().isoformat(),
            "close_reason": reason,
            "pnl_usdt": round(pnl, 4),
            "pnl_pct": round(pnl_pct, 2),
        })
        self._save_history()
        del self.open_trades[symbol]
        self._save_open_trades()
        return True

        alert_type = "PROFIT" if pnl > 0 else "LOSS"
        alert_sound(alert_type)
        desktop_notify(f"{emoji} {symbol} CLOSED", f"PnL: ${pnl:.2f} ({pnl_pct:.2f}%)")

    # ── Status ───────────────────────────────────────────────

    def print_status(self):
        balance = self.get_usdt_balance()
        mode = "📄 PAPER" if cfg.PAPER_TRADING else "💰 LIVE"
        log.info("─" * 60)
        log.info(f"💼 Balance: ${balance:.2f} | Open: {len(self.open_trades)}/{cfg.MAX_OPEN_TRADES} | PnL: ${self.daily_pnl:.2f} | {mode}")
        log.info(f"   📊 Today: {self.daily_new_trades}/{cfg.MAX_DAILY_TRADES} trades | Streak: {'🔴' * self.consecutive_losses or '🟢'} | Cooldowns: {len(self.loss_cooldowns)}")
        for sym, t in self.open_trades.items():
            partial = "💰P1" if t.get('partial_tp_hit') else ""
            be = "🛡️BE" if t.get('breakeven_hit') else ""
            log.info(f"   {sym}: ${t['entry_price']:.4f} | SL ${t['stop_loss']:.4f} | TP ${t['take_profit']:.4f} | {be} {partial}")
        log.info("─" * 60)

    def print_performance(self):
        if not self.history:
            log.info("📊 No completed trades yet.")
            return
        wins = [t for t in self.history if t['pnl_usdt'] > 0]
        losses = [t for t in self.history if t['pnl_usdt'] <= 0]
        total = sum(t['pnl_usdt'] for t in self.history)
        winrate = len(wins) / len(self.history) * 100
        log.info("═" * 60)
        log.info("📊 SMART AGENT PERFORMANCE")
        log.info(f"   Trades: {len(self.history)} | Win Rate: {winrate:.1f}% ({len(wins)}W/{len(losses)}L)")
        log.info(f"   Total PnL: ${total:.2f}")
        if wins:
            log.info(f"   Avg Win: ${np.mean([t['pnl_usdt'] for t in wins]):.2f}")
        if losses:
            log.info(f"   Avg Loss: ${np.mean([t['pnl_usdt'] for t in losses]):.2f}")
        log.info("═" * 60)

    def get_context(self) -> dict:
        """Context dict for Jarvis chat."""
        wins = [t for t in self.history if t['pnl_usdt'] > 0]
        return {
            "open_trades": len(self.open_trades),
            "daily_pnl": self.daily_pnl,
            "win_rate": round(len(wins) / max(len(self.history), 1) * 100, 1),
            "balance": self.get_usdt_balance(),
            "total_trades": len(self.history),
        }


# ══════════════════════════════════════════════════════════════
#   JARVIS CHAT THREAD
# ══════════════════════════════════════════════════════════════

def jarvis_chat_thread(jarvis: JarvisChat, manager: SmartTradeManager):
    """Run Jarvis in a background thread — user can type anytime."""
    log.info("💬 Jarvis chat ready — type in console anytime")
    while True:
        try:
            user_input = input("\n🗣️ You: ").strip()
            if not user_input:
                continue
            if user_input.lower() in ["quit", "exit", "bye"]:
                print("🤖 JARVIS: Goodbye sir. Your trades are being monitored. Stay safe.")
                break
            alert_sound("JARVIS")
            context = manager.get_context()
            reply = jarvis.chat(user_input, context)
            print(f"\n🤖 JARVIS: {reply}\n")
        except EOFError:
            break
        except Exception as e:
            print(f"🤖 JARVIS: Communication error — {e}")


# ══════════════════════════════════════════════════════════════
#   MAIN LOOP
# ══════════════════════════════════════════════════════════════

class SmartHalalBot:
    def __init__(self):
        self.client = Client(cfg.BINANCE_API_KEY, cfg.BINANCE_API_SECRET)
        self.learner = LearningEngine()
        self.manager = SmartTradeManager(self.client, self.learner)
        self.jarvis = JarvisChat()
        self.is_running = False
        self._thread = None
        self.cycle = 0
        self.latest_analysis = {}  # Store latest analysis for all coins

    def start(self):
        if self.is_running:
            return
        self.is_running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        log.info("🚀 Smart Halal Bot started in background thread.")

    def stop(self):
        self.is_running = False
        log.info("🛑 Stop signal sent to Smart Halal Bot.")

    def _run_loop(self):
        self.cycle = 0
        while self.is_running:
            self.cycle += 1
            now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            log.info(f"\n{'═'*60}")
            log.info(f"🔄 CYCLE #{self.cycle} | {now}")
            log.info(f"{'═'*60}")

            try:
                # Midnight reset
                if datetime.datetime.now().hour == 0 and datetime.datetime.now().minute < cfg.ANALYSIS_INTERVAL_MIN:
                    self.manager.daily_pnl = 0.0
                    self.manager.daily_new_trades = 0
                    self.manager.consecutive_losses = 0
                    self.manager.loss_cooldowns.clear()
                    log.info("🌙 Daily reset performed.")
                    self.manager.print_performance()

                # Market sentiment
                fear_greed = get_fear_greed_index()
                btc_dom = get_btc_dominance()

                # Check exits
                if self.manager.open_trades:
                    for symbol in list(self.manager.open_trades.keys()):
                        try:
                            price = float(self.client.get_symbol_ticker(symbol=symbol)["price"])
                            reason = self.manager.check_exit_conditions(symbol, price)
                            if reason and cfg.ENABLE_AUTO_SELL:
                                self.manager.close_trade(symbol, price, reason)
                        except Exception as e:
                            log.error(f"Exit check error {symbol}: {e}")

                # Analysis
                opportunities = []
                for symbol in cfg.WATCHLIST:
                    if not self.is_running: break
                    try:
                        tf_klines = {}
                        for tf_name, tf_cfg in cfg.TIMEFRAMES.items():
                            klines = self.client.get_klines(symbol=symbol, interval=tf_cfg["interval"], limit=tf_cfg["limit"])
                            if len(klines) >= 50: tf_klines[tf_name] = klines
                        
                        if len(tf_klines) < 2: continue
                        
                        analysis = analyze_multi_tf(symbol, tf_klines, fear_greed, btc_dom)
                        self.latest_analysis[symbol] = analysis  # SAVE FOR UI
                        
                        if analysis["signal"] in ["BUY", "STRONG_BUY"]:
                            opportunities.append(analysis)
                        time.sleep(0.1) # Faster than before
                    except Exception as e:
                        log.error(f"Analysis error {symbol}: {e}")

                # Process opportunities
                if opportunities and self.is_running:
                    opportunities.sort(key=lambda x: x["score"], reverse=True)
                    opportunities = opportunities[:2]

                    if self.manager.daily_new_trades < cfg.MAX_DAILY_TRADES and \
                       self.manager.consecutive_losses < cfg.MAX_CONSECUTIVE_LOSSES:
                        
                        learning_summary = self.learner.get_learning_summary()
                        overview = gpt_market_overview(opportunities, fear_greed, btc_dom, learning_summary)
                        log.info(f"\n🌐 JARVIS: {overview}")

                        for opp in opportunities:
                            if not self.is_running: break
                            if opp["symbol"] in self.manager.open_trades: continue
                            
                            can_trade, reason = self.manager.can_open_trade(opp["symbol"], opp)
                            if not can_trade: continue

                            coin_learning = self.learner.get_learning_summary(opp["symbol"])
                            gpt_decision = gpt_deep_analyze(opp, coin_learning)

                            if gpt_decision["signal"] == "BUY":
                                self.manager.open_trade(opp, gpt_decision)
                            time.sleep(1)

                self.manager.print_status()

            except Exception as e:
                log.error(f"💥 Cycle #{self.cycle} error: {e}")
            
            # Wait for next cycle with real-time monitoring
            wait_sec = cfg.ANALYSIS_INTERVAL_MIN * 60
            start_wait = time.time()
            while time.time() - start_wait < wait_sec and self.is_running:
                # Check is_running every second for responsiveness
                for _ in range(int(cfg.MONITOR_INTERVAL_SEC)):
                    if not self.is_running: break
                    time.sleep(1)
                
                if not self.is_running: break
                if self.manager.open_trades and cfg.ENABLE_AUTO_SELL:
                    for symbol in list(self.manager.open_trades.keys()):
                        try:
                            price = float(self.client.get_symbol_ticker(symbol=symbol)["price"])
                            reason = self.manager.check_exit_conditions(symbol, price)
                            if reason:
                                self.manager.close_trade(symbol, price, reason)
                        except: pass

    def manual_close(self, symbol: str):
        """Allow manual profit booking or stopping."""
        if symbol in self.manager.open_trades:
            try:
                price = float(self.client.get_symbol_ticker(symbol=symbol)["price"])
                success = self.manager.close_trade(symbol, price, "MANUAL_CLOSE")
                if success:
                    return True, f"Successfully closed {symbol} at ${price:.4f}"
                else:
                    return False, f"Failed to execute sell order for {symbol}"
            except Exception as e:
                log.error(f"Manual close exception: {e}")
                return False, f"Error: {str(e)}"
        return False, f"Symbol {symbol} not found in open trades"

if __name__ == "__main__":
    bot = SmartHalalBot()
    try:
        bot._run_loop() # Run in main thread if executed directly
    except KeyboardInterrupt:
        log.info("\n🛑 Stopped. Assalamu Alaikum!")
