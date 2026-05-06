"""
╔══════════════════════════════════════════════════════════════╗
║       SELF-LEARNING ENGINE — Learns from every trade        ║
║       Remembers what worked, avoids what failed             ║
╚══════════════════════════════════════════════════════════════╝
"""

import json
import logging
import datetime
import numpy as np
from typing import Optional

import smart_config as cfg

log = logging.getLogger("SmartAgent")


class LearningEngine:
    """
    Stores every trade outcome with full context (indicators, market state).
    Before each new trade, it checks: "Have I seen this pattern before? Did it win or lose?"
    Builds rules over time from accumulated experience.
    """

    def __init__(self):
        self.lessons = self._load()
        self.rules = self._derive_rules()
        log.info(f"🧠 Learning Engine loaded: {len(self.lessons)} lessons, {len(self.rules)} rules")

    # ── Persistence ───────────────────────────────────────────

    def _load(self) -> list:
        try:
            with open(cfg.LEARNING_DB_FILE, "r") as f:
                return json.load(f)
        except Exception:
            return []

    def _save(self):
        # Keep only the last N entries
        self.lessons = self.lessons[-cfg.MAX_LEARNING_ENTRIES:]
        with open(cfg.LEARNING_DB_FILE, "w") as f:
            json.dump(self.lessons, f, indent=2)

    # ── Record a completed trade ─────────────────────────────

    def record_trade(self, trade: dict, exit_price: float, reason: str):
        """Record the full context of a trade for future learning."""
        entry = trade["entry_price"]
        pnl_pct = ((exit_price - entry) / entry) * 100

        lesson = {
            "symbol":          trade["symbol"],
            "entry_price":     entry,
            "exit_price":      exit_price,
            "pnl_pct":         round(pnl_pct, 2),
            "won":             pnl_pct > 0,
            "close_reason":    reason,
            "timestamp":       datetime.datetime.now().isoformat(),
            # Context snapshot at entry time
            "rsi_at_entry":    trade.get("rsi_at_entry"),
            "macd_trend":      trade.get("macd_trend"),
            "ema_trend":       trade.get("ema_trend"),
            "volume_signal":   trade.get("volume_signal"),
            "bb_position":     trade.get("bb_position"),
            "fear_greed":      trade.get("fear_greed_at_entry"),
            "btc_dominance":   trade.get("btc_dom_at_entry"),
            "atr_pct":         trade.get("atr_pct_at_entry"),
            "tf_agreement":    trade.get("tf_agreement", 0),
            "support_dist":    trade.get("support_distance_pct"),
            "resistance_dist": trade.get("resistance_distance_pct"),
            "trend_strength":  trade.get("trend_strength"),
            "hour_of_day":     trade.get("hour_of_day"),
            "gpt_confidence":  trade.get("gpt_confidence"),
            "technical_score": trade.get("signal_score"),
        }

        self.lessons.append(lesson)
        self._save()
        self.rules = self._derive_rules()

        status = "✅ WIN" if lesson["won"] else "❌ LOSS"
        log.info(f"🧠 Lesson recorded: {trade['symbol']} {status} ({pnl_pct:+.2f}%)")

    # ── Derive rules from patterns ───────────────────────────

    def _derive_rules(self) -> list:
        """Analyze all lessons to find patterns that predict wins/losses."""
        if len(self.lessons) < cfg.PATTERN_MIN_SAMPLES:
            return []

        rules = []

        # Rule 1: RSI ranges that tend to lose
        rsi_lessons = [l for l in self.lessons if l.get("rsi_at_entry") is not None]
        if len(rsi_lessons) >= cfg.PATTERN_MIN_SAMPLES:
            # Check RSI 45-55 (neutral zone) loss rate
            neutral_rsi = [l for l in rsi_lessons if 45 <= (l["rsi_at_entry"] or 50) <= 55]
            if len(neutral_rsi) >= cfg.PATTERN_MIN_SAMPLES:
                loss_rate = sum(1 for l in neutral_rsi if not l["won"]) / len(neutral_rsi)
                if loss_rate > 0.6:
                    rules.append({
                        "type": "AVOID_RSI_NEUTRAL",
                        "desc": f"RSI 45-55 has {loss_rate*100:.0f}% loss rate ({len(neutral_rsi)} trades)",
                        "condition": "rsi_neutral",
                        "loss_rate": loss_rate,
                        "samples": len(neutral_rsi),
                    })

        # Rule 2: Low volume entries tend to lose
        vol_lessons = [l for l in self.lessons if l.get("volume_signal") is not None]
        if len(vol_lessons) >= cfg.PATTERN_MIN_SAMPLES:
            low_vol = [l for l in vol_lessons if l["volume_signal"] == "LOW"]
            if len(low_vol) >= cfg.PATTERN_MIN_SAMPLES:
                loss_rate = sum(1 for l in low_vol if not l["won"]) / len(low_vol)
                if loss_rate > 0.6:
                    rules.append({
                        "type": "AVOID_LOW_VOLUME",
                        "desc": f"Low volume entries have {loss_rate*100:.0f}% loss rate",
                        "condition": "low_volume",
                        "loss_rate": loss_rate,
                        "samples": len(low_vol),
                    })

        # Rule 3: Timeframe disagreement
        tf_lessons = [l for l in self.lessons if l.get("tf_agreement") is not None]
        if len(tf_lessons) >= cfg.PATTERN_MIN_SAMPLES:
            low_agree = [l for l in tf_lessons if (l["tf_agreement"] or 0) < 2]
            if len(low_agree) >= cfg.PATTERN_MIN_SAMPLES:
                loss_rate = sum(1 for l in low_agree if not l["won"]) / len(low_agree)
                if loss_rate > 0.5:
                    rules.append({
                        "type": "REQUIRE_TF_AGREEMENT",
                        "desc": f"Trades without 2+ TF agreement have {loss_rate*100:.0f}% loss rate",
                        "condition": "low_tf_agreement",
                        "loss_rate": loss_rate,
                        "samples": len(low_agree),
                    })

        # Rule 4: Per-coin performance
        symbols = set(l["symbol"] for l in self.lessons)
        for sym in symbols:
            sym_lessons = [l for l in self.lessons if l["symbol"] == sym]
            if len(sym_lessons) >= cfg.PATTERN_MIN_SAMPLES:
                loss_rate = sum(1 for l in sym_lessons if not l["won"]) / len(sym_lessons)
                if loss_rate > 0.7:
                    rules.append({
                        "type": "AVOID_COIN",
                        "desc": f"{sym} has {loss_rate*100:.0f}% loss rate over {len(sym_lessons)} trades",
                        "condition": f"coin_{sym}",
                        "symbol": sym,
                        "loss_rate": loss_rate,
                        "samples": len(sym_lessons),
                    })

        # Rule 5: High ATR (volatility) entries
        atr_lessons = [l for l in self.lessons if l.get("atr_pct") is not None]
        if len(atr_lessons) >= cfg.PATTERN_MIN_SAMPLES:
            high_atr = [l for l in atr_lessons if (l["atr_pct"] or 0) > 4]
            if len(high_atr) >= cfg.PATTERN_MIN_SAMPLES:
                loss_rate = sum(1 for l in high_atr if not l["won"]) / len(high_atr)
                if loss_rate > 0.6:
                    rules.append({
                        "type": "AVOID_HIGH_VOLATILITY",
                        "desc": f"High ATR entries have {loss_rate*100:.0f}% loss rate",
                        "condition": "high_atr",
                        "loss_rate": loss_rate,
                        "samples": len(high_atr),
                    })

        # Rule 6: Time-of-day patterns
        time_lessons = [l for l in self.lessons if l.get("hour_of_day") is not None]
        if len(time_lessons) >= cfg.PATTERN_MIN_SAMPLES:
            for hour_range_name, hours in [("late_night", range(0, 5)), ("afternoon", range(12, 16))]:
                hr_trades = [l for l in time_lessons if l["hour_of_day"] in hours]
                if len(hr_trades) >= cfg.PATTERN_MIN_SAMPLES:
                    loss_rate = sum(1 for l in hr_trades if not l["won"]) / len(hr_trades)
                    if loss_rate > 0.65:
                        rules.append({
                            "type": "AVOID_TIME",
                            "desc": f"Trades during {hour_range_name} have {loss_rate*100:.0f}% loss rate",
                            "condition": f"time_{hour_range_name}",
                            "loss_rate": loss_rate,
                            "samples": len(hr_trades),
                        })

        if rules:
            log.info(f"🧠 Derived {len(rules)} learning rules:")
            for r in rules:
                log.info(f"   📌 {r['desc']}")

        return rules

    # ── Check if a trade should be blocked by learned rules ──

    def should_block_trade(self, analysis: dict) -> tuple:
        """
        Returns (should_block: bool, reasons: list[str])
        Check all learned rules against the current analysis.
        """
        if not self.rules:
            return False, []

        blocks = []

        for rule in self.rules:
            if rule["type"] == "AVOID_RSI_NEUTRAL":
                rsi = analysis.get("rsi", 50)
                if 45 <= rsi <= 55:
                    blocks.append(f"🧠 LEARNED: {rule['desc']}")

            elif rule["type"] == "AVOID_LOW_VOLUME":
                if analysis.get("volume") == "LOW":
                    blocks.append(f"🧠 LEARNED: {rule['desc']}")

            elif rule["type"] == "REQUIRE_TF_AGREEMENT":
                if analysis.get("tf_agreement", 0) < 2:
                    blocks.append(f"🧠 LEARNED: {rule['desc']}")

            elif rule["type"] == "AVOID_COIN":
                if analysis.get("symbol") == rule.get("symbol"):
                    blocks.append(f"🧠 LEARNED: {rule['desc']}")

            elif rule["type"] == "AVOID_HIGH_VOLATILITY":
                if analysis.get("atr_pct", 0) > 4:
                    blocks.append(f"🧠 LEARNED: {rule['desc']}")

            elif rule["type"] == "AVOID_TIME":
                hour = datetime.datetime.now().hour
                if "late_night" in rule["condition"] and hour in range(0, 5):
                    blocks.append(f"🧠 LEARNED: {rule['desc']}")
                elif "afternoon" in rule["condition"] and hour in range(12, 16):
                    blocks.append(f"🧠 LEARNED: {rule['desc']}")

        return len(blocks) > 0, blocks

    # ── Get learning context for GPT prompt ──────────────────

    def get_learning_summary(self, symbol: str = None) -> str:
        """Generate a text summary of past performance for GPT to consider."""
        if not self.lessons:
            return "No prior trade data — first-time trading."

        total = len(self.lessons)
        wins = sum(1 for l in self.lessons if l["won"])
        losses = total - wins
        avg_pnl = np.mean([l["pnl_pct"] for l in self.lessons])

        summary = f"PAST PERFORMANCE ({total} trades): {wins}W/{losses}L, Avg PnL: {avg_pnl:+.2f}%\n"

        # Add symbol-specific history
        if symbol:
            sym_lessons = [l for l in self.lessons if l["symbol"] == symbol]
            if sym_lessons:
                sym_wins = sum(1 for l in sym_lessons if l["won"])
                sym_avg = np.mean([l["pnl_pct"] for l in sym_lessons])
                summary += f"THIS COIN ({symbol}): {sym_wins}W/{len(sym_lessons)-sym_wins}L, Avg: {sym_avg:+.2f}%\n"

                # Show last 3 trades on this coin
                recent = sym_lessons[-3:]
                for t in recent:
                    status = "WIN" if t["won"] else "LOSS"
                    summary += f"  - {status}: {t['pnl_pct']:+.2f}% | RSI={t.get('rsi_at_entry','?')} | Reason: {t['close_reason']}\n"

        # Add active rules
        if self.rules:
            summary += "LEARNED RULES:\n"
            for r in self.rules:
                summary += f"  ⚠️ {r['desc']}\n"

        return summary
