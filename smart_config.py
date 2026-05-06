"""
╔══════════════════════════════════════════════════════════════╗
║           SMART HALAL TRADING AGENT — CONFIG                ║
║           Long-Only | Multi-Timeframe | Self-Learning       ║
╚══════════════════════════════════════════════════════════════╝

HALAL COMPLIANCE:
- LONG ONLY — no short selling, no margin, no leverage
- No interest-based instruments
- Only spot market buying
- Halal-compliant crypto projects only
"""

# ─── API Keys (shared with existing config) ───────────────────
from config import BINANCE_API_KEY, BINANCE_API_SECRET, OPENAI_API_KEY, ELEVENLABS_API_KEY

# ─── Mode ─────────────────────────────────────────────────────
PAPER_TRADING    = True    # True = simulate | False = real money
ENABLE_AUTO_SELL = True    # auto close on SL/TP hit

# ─── Budget & Risk — PRO QUANT RULES ──────────────────────────
TOTAL_BUDGET_USDT    = 50       # starting capital
MAX_PER_TRADE_PCT    = 20.0     # 20% of $50 = $10 (Binance Minimum Notional)
MAX_OPEN_TRADES      = 4        # max 4 positions to stay within $50
RESERVE_USDT         = 5        # small safety buffer
MAX_DAILY_LOSS_PCT   = 10.0     # stop after 10% loss ($5)
DRAWDOWN_LIMIT_PCT   = 15.0     # Pause bot at 15% drawdown

# ─── Trade Parameters ─────────────────────────────────────────
MIN_RR_RATIO         = 2.0      # Minimum 1:2 Risk/Reward
ATR_SL_MULTIPLIER    = 2.5      # 2.5x ATR for stop loss (pros use 2-3x)
STOP_LOSS_PCT        = 4.0      # Default SL if ATR not available
TAKE_PROFIT_PCT      = 8.0      # Default TP if SR not available
TRAILING_STOP_PCT    = 3.0      # Trailing stop %
BREAKEVEN_TRIGGER    = 5.0      # move SL to entry after 5% profit (3% was too tight)
MIN_SL_DISTANCE_PCT  = 3.0      # NEVER place SL closer than 3% — crypto noise kills tight stops

# ─── Professional Risk Filters ────────────────────────────────
MAX_DAILY_TRADES     = 3        # max new entries per day — quality > quantity
LOSS_COOLDOWN_HOURS  = 4        # hours to wait before re-entering a symbol after loss
MAX_CONSECUTIVE_LOSSES = 3      # pause trading after N consecutive losses
LOSS_STREAK_SIZE_REDUCE = 0.5   # cut position size by 50% after 2+ losses
MIN_ATR_PCT          = 0.3      # skip dead markets (too low volatility)
MAX_ATR_PCT          = 7.0      # skip extremely volatile conditions

# ─── Partial Take Profit (Scale Out) ──────────────────────────
PARTIAL_TP_ENABLED   = True     # take partial profits
PARTIAL_TP_PCT       = 0.50     # close 50% at first target
PARTIAL_TP1_RR       = 1.5      # first TP at 1.5R
FULL_TP_RR           = 3.0      # full TP at 3R (let winners run)

# ─── Stepped Trailing Stop ────────────────────────────────────
# As profit grows, trail gets tighter to lock in more gains
TRAIL_STEP_1_PCT     = 3.0      # 0-5% profit: trail at 3%
TRAIL_STEP_2_PCT     = 2.0      # 5-10% profit: trail at 2%
TRAIL_STEP_3_PCT     = 1.5      # 10%+ profit: trail at 1.5%

# ─── Signal Thresholds — STRICT ───────────────────────────────
GPT_MIN_CONFIDENCE   = 72       # high bar but realistic for daily trades
MIN_TECHNICAL_SCORE  = 8        # was 12 (too strict, no trades passed). 8 = multi-strategy
MIN_MULTI_TF_AGREE   = 2        # at least 2 timeframes must agree

# ─── Multi-Timeframe Settings ────────────────────────────────
TIMEFRAMES = {
    "15m": {"interval": "15m", "limit": 100, "weight": 1.0},   # short-term entry timing
    "1h":  {"interval": "1h",  "limit": 100, "weight": 1.5},   # medium-term trend
    "4h":  {"interval": "4h",  "limit": 100, "weight": 2.0},   # primary trend direction
}

# ─── Analysis Cycle ──────────────────────────────────────────
ANALYSIS_INTERVAL_MIN = 20      # run every 20 minutes
MONITOR_INTERVAL_SEC  = 30      # check prices every 30s between cycles

# ─── Files — Separate from old system ────────────────────────
LOG_FILE              = "smart_trading_log.txt"
TRADE_HISTORY_FILE    = "smart_trade_history.json"
OPEN_TRADES_FILE      = "smart_open_trades.json"
LEARNING_DB_FILE      = "smart_learning_db.json"
MARKET_CONTEXT_FILE   = "smart_market_context.json"

# ─── Watchlist — Halal, Utility-Based Projects Only ──────────
# Only coins with real technology and use-case, no meme coins
WATCHLIST = [
    "BTCUSDT",    # Bitcoin — digital gold
    "ETHUSDT",    # Ethereum — smart contracts
    "BNBUSDT",    # BNB — exchange utility
    "SOLUSDT",    # Solana — fast L1
    "ADAUSDT",    # Cardano — research-driven
    "XRPUSDT",    # Ripple — payments
    "DOTUSDT",    # Polkadot — interoperability
    "LINKUSDT",   # Chainlink — oracle network
    "AVAXUSDT",   # Avalanche — DeFi L1
    "NEARUSDT",   # NEAR — sharded L1
    "APTUSDT",    # Aptos — Move VM
    "SUIUSDT",    # Sui — Move VM
    "ALGOUSDT",   # Algorand — green blockchain
    "ATOMUSDT",   # Cosmos — interchain
    "MATICUSDT",  # Polygon — Ethereum L2
    "ARBUSDT",    # Arbitrum — Ethereum L2
    "OPUSDT",     # Optimism — Ethereum L2
    "RENDERUSDT", # Render — GPU computing
    "INJUSDT",    # Injective — DeFi
    "STXUSDT",    # Stacks — Bitcoin L2
    "LTCUSDT",    # Litecoin — Digital silver
    "XLMUSDT",    # Stellar — Payments
    "HBARUSDT",   # Hedera — Enterprise DLT
    "QNTUSDT",    # Quant — Interoperability
    "FETUSDT",    # Fetch.ai — AI
    "AGIXUSDT",   # SingularityNET — AI
    "GRTUSDT",    # The Graph — Indexing
    "EGLDUSDT",   # MultiversX — Sharded L1
    "FILUSDT",    # Filecoin — Storage
    "ARUSDT",     # Arweave — Storage
    "TAOUSDT",    # Bittensor — AI
    "IMXUSDT",    # Immutable X — Gaming L2
    "FTMUSDT",    # Fantom — DAG L1
    "ROSEUSDT",   # Oasis Network — Privacy
    "KASUSDT",    # Kaspa — PoW L1 (if available)
]

# ─── Learning System ─────────────────────────────────────────
MAX_LEARNING_ENTRIES   = 500    # keep last 500 trade lessons
PATTERN_MIN_SAMPLES    = 3      # need 3+ similar trades to form a rule
LOSS_PENALTY_BOOST     = 1.5    # weigh losses more in learning
WIN_REWARD_BOOST       = 1.0    # normal weight for wins

# ─── GPT Model ───────────────────────────────────────────────
GPT_MODEL = "gpt-4o-mini"       # fast + cheap for analysis
GPT_JARVIS_MODEL = "gpt-4o-mini"  # for conversational Jarvis mode

# ─── ElevenLabs Voice Cloning ────────────────────────────────
# ELEVENLABS_API_KEY is imported from config.py
ELEVENLABS_VOICE_ID = ""         # will be set after you record your voice
ELEVENLABS_MODEL = "eleven_multilingual_v2"  # supports Urdu + English
