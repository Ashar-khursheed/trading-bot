import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { 
  Activity, 
  TrendingUp, 
  TrendingDown, 
  Wallet, 
  History, 
  Play, 
  Square, 
  ExternalLink,
  ShieldCheck,
  AlertTriangle,
  Zap,
  Info,
  DollarSign,
  ChevronRight
} from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000';

function App() {
  const [activeTab, setActiveTab] = useState('dashboard');
  const [status, setStatus] = useState(null);
  const [openTrades, setOpenTrades] = useState([]);
  const [history, setHistory] = useState([]);
  const [analysis, setAnalysis] = useState([]);
  const [market, setMarket] = useState(null);
  const [logs, setLogs] = useState([]);
  const [loading, setLoading] = useState(true);

  const fetchData = async () => {
    try {
      const [statusRes, tradesRes, historyRes, marketRes, logsRes, analysisRes] = await Promise.all([
        axios.get(`${API_BASE}/status`),
        axios.get(`${API_BASE}/trades/open`),
        axios.get(`${API_BASE}/trades/history`),
        axios.get(`${API_BASE}/market`),
        axios.get(`${API_BASE}/logs`),
        axios.get(`${API_BASE}/analysis`)
      ]);
      setStatus(statusRes.data);
      setOpenTrades(tradesRes.data);
      setHistory(historyRes.data);
      setMarket(marketRes.data);
      setLogs(logsRes.data);
      setAnalysis(analysisRes.data);
      setLoading(false);
    } catch (err) {
      console.error("API error:", err);
    }
  };

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 5000);
    return () => clearInterval(interval);
  }, []);

  const handleCloseTrade = async (symbol) => {
    console.log(`Manual request: Close trade for ${symbol}...`);
    if (!window.confirm(`Are you sure you want to close the trade for ${symbol}?`)) return;
    
    try {
      const response = await axios.post(`${API_BASE}/trades/close`, { symbol });
      console.log("Trade closed successfully:", response.data);
      fetchData();
    } catch (err) {
      console.error("Trade close error:", err);
      const msg = err.response?.data?.detail || err.message || "Failed to close trade";
      alert(`Error: ${msg}`);
    }
  };

  const handleToggleBot = async () => {
    const endpoint = status?.is_running ? '/bot/stop' : '/bot/start';
    try {
      await axios.post(`${API_BASE}${endpoint}`);
      fetchData();
    } catch (err) {
      alert("Failed to toggle bot");
    }
  };

  if (loading && !status) return (
    <div className="h-screen w-screen flex items-center justify-center bg-background">
      <div className="animate-spin rounded-full h-12 w-12 border-t-2 border-accent"></div>
    </div>
  );

  return (
    <div className="min-h-screen p-4 md:p-8 max-w-7xl mx-auto space-y-8">
      {/* Header */}
      <header className="flex flex-col md:flex-row md:items-center justify-between gap-4 glass-panel p-6">
        <div>
          <h1 className="text-3xl font-bold gradient-text">Smart Halal Bot</h1>
          <p className="text-slate-400 mt-1 flex items-center gap-2">
            <Activity size={16} className={status?.is_running ? "text-success animate-pulse" : "text-slate-500"} />
            {status?.is_running ? "Bot is currently monitoring markets" : "Bot is paused"}
          </p>
        </div>
        <div className="flex items-center gap-2 bg-white/5 p-1 rounded-xl">
          <button 
            onClick={() => setActiveTab('dashboard')}
            className={`px-4 py-2 rounded-lg text-sm font-medium transition-all ${activeTab === 'dashboard' ? 'bg-accent text-white shadow-lg' : 'text-slate-400 hover:text-slate-200'}`}
          >
            Dashboard
          </button>
          <button 
            onClick={() => setActiveTab('scanner')}
            className={`px-4 py-2 rounded-lg text-sm font-medium transition-all ${activeTab === 'scanner' ? 'bg-accent text-white shadow-lg' : 'text-slate-400 hover:text-slate-200'}`}
          >
            Market Scanner
          </button>
        </div>
        <div className="flex items-center gap-4">
          <button 
            onClick={handleToggleBot}
            className={`px-6 py-2 rounded-xl font-semibold flex items-center gap-2 transition-all ${
              status?.is_running 
                ? "bg-danger/20 text-danger hover:bg-danger/30" 
                : "bg-success/20 text-success hover:bg-success/30"
            }`}
          >
            {status?.is_running ? <><Square size={18} /> Stop Bot</> : <><Play size={18} /> Start Bot</>}
          </button>
        </div>
      </header>

      {activeTab === 'dashboard' ? (
        <>
          {/* Stats Grid */}
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
            <StatCard 
              title="Total Balance" 
              value={`$${status?.balance}`} 
              icon={<Wallet className="text-accent" />} 
              subtitle={`${status?.mode} Trading`}
            />
            <StatCard 
              title="Daily PnL" 
              value={`$${status?.daily_pnl}`} 
              icon={status?.daily_pnl >= 0 ? <TrendingUp className="text-success" /> : <TrendingDown className="text-danger" />} 
              subtitle={`${status?.daily_trades}/${status?.max_daily_trades} Trades today`}
              trend={status?.daily_pnl >= 0 ? 'up' : 'down'}
            />
            <StatCard 
              title="Fear & Greed" 
              value={market?.fear_greed?.value} 
              icon={<Zap className="text-warning" />} 
              subtitle={market?.fear_greed?.label}
            />
            <StatCard 
              title="Loss Streak" 
              value={status?.consecutive_losses} 
              icon={<ShieldCheck className="text-emerald-400" />} 
              subtitle={status?.consecutive_losses > 0 ? "Caution advised" : "Safely operating"}
            />
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
            {/* Open Trades */}
            <div className="lg:col-span-2 space-y-6">
              <div className="flex items-center justify-between">
                <h2 className="text-xl font-semibold flex items-center gap-2">
                  <Zap className="text-accent" size={20} /> Active Positions
                </h2>
                <span className="bg-accent/10 text-accent px-3 py-1 rounded-full text-sm">
                  {openTrades.length} Active
                </span>
              </div>

              <div className="space-y-4">
                <AnimatePresence>
                  {openTrades.length > 0 ? (
                    openTrades.map((trade) => (
                      <TradeCard key={trade.symbol} trade={trade} onClose={() => handleCloseTrade(trade.symbol)} />
                    ))
                  ) : (
                    <div className="glass-panel p-12 text-center text-slate-500">
                      <p>No active trades at the moment.</p>
                    </div>
                  )}
                </AnimatePresence>
              </div>
            </div>

            {/* Sidebar */}
            <div className="space-y-8">
              {/* Market Health */}
              <div className="glass-panel p-6 space-y-4">
                <h3 className="text-lg font-semibold flex items-center gap-2">
                  <Activity size={18} className="text-accent" /> Market Health
                </h3>
                <div className="space-y-3">
                  <HealthItem label="BTC Dominance" value={`${market?.btc_dominance}%`} color="text-accent" />
                  <HealthItem label="Bot Cycle" value={`#${status?.cycle}`} color="text-slate-400" />
                  <div className="pt-4 border-t border-white/5">
                    <p className="text-xs text-slate-500 uppercase tracking-wider mb-2">Live Logs</p>
                    <div className="bg-black/50 rounded-lg p-3 h-48 overflow-y-auto text-[10px] font-mono text-slate-400 space-y-1">
                      {logs.map((log, i) => (
                        <div key={i} className="whitespace-nowrap opacity-70 hover:opacity-100">{log}</div>
                      ))}
                    </div>
                  </div>
                </div>
              </div>

              {/* Trade History */}
              <div className="glass-panel p-6 space-y-4">
                <h3 className="text-lg font-semibold flex items-center gap-2">
                  <History size={18} className="text-accent" /> Recent History
                </h3>
                <div className="space-y-4">
                  {history.slice().reverse().map((h, i) => (
                    <div key={i} className="flex items-center justify-between text-sm border-b border-white/5 pb-2">
                      <div>
                        <p className="font-medium">{h.symbol}</p>
                        <p className="text-[10px] text-slate-500">{new Date(h.closed_at).toLocaleTimeString()}</p>
                      </div>
                      <div className={h.pnl_usdt >= 0 ? "text-success" : "text-danger"}>
                        ${h.pnl_usdt > 0 ? '+' : ''}{h.pnl_usdt}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>
        </>
      ) : (
        <div className="space-y-6">
          <div className="flex items-center justify-between">
            <h2 className="text-xl font-semibold flex items-center gap-2">
              <Activity className="text-accent" size={20} /> Market Scanner
            </h2>
            <p className="text-slate-400 text-sm italic">Analysis updates every 20 minutes</p>
          </div>
          
          <div className="glass-panel overflow-hidden">
            <table className="w-full text-left border-collapse">
              <thead>
                <tr className="bg-white/5 text-slate-400 text-xs uppercase tracking-widest font-bold">
                  <th className="px-6 py-4">Symbol</th>
                  <th className="px-6 py-4">Price</th>
                  <th className="px-6 py-4">Score</th>
                  <th className="px-6 py-4">Signal</th>
                  <th className="px-6 py-4">Trend</th>
                  <th className="px-6 py-4">RSI</th>
                  <th className="px-6 py-4">Volatility</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-white/5">
                {analysis.length > 0 ? (
                  analysis.map((item) => (
                    <tr key={item.symbol} className="hover:bg-white/[0.02] transition-colors text-sm">
                      <td className="px-6 py-4 font-bold text-slate-200">{item.symbol}</td>
                      <td className="px-6 py-4 font-mono text-slate-400">${item.price.toFixed(4)}</td>
                      <td className="px-6 py-4">
                        <span className={`px-2 py-1 rounded-md ${item.score > 0 ? 'bg-success/10 text-success' : 'bg-danger/10 text-danger'}`}>
                          {item.score > 0 ? '+' : ''}{item.score}
                        </span>
                      </td>
                      <td className="px-6 py-4">
                        <span className={`px-2 py-1 rounded-full text-[10px] font-bold uppercase tracking-wider ${
                          item.signal.includes('BUY') ? 'bg-success/20 text-success border border-success/20' : 
                          item.signal.includes('SELL') ? 'bg-danger/20 text-danger border border-danger/20' : 
                          'bg-slate-800 text-slate-400'
                        }`}>
                          {item.signal}
                        </span>
                      </td>
                      <td className="px-6 py-4">
                        <div className="flex items-center gap-2">
                          {item.trend?.direction === 'UP' || item.trend?.direction === 'STRONG_UP' ? <TrendingUp size={14} className="text-success" /> : <TrendingDown size={14} className="text-danger" />}
                          <span className="text-xs uppercase">{item.trend?.direction}</span>
                        </div>
                      </td>
                      <td className="px-6 py-4 font-mono">{item.rsi}</td>
                      <td className="px-6 py-4 font-mono">{item.atr_pct}%</td>
                    </tr>
                  ))
                ) : (
                  <tr>
                    <td colSpan="7" className="px-6 py-12 text-center text-slate-500">
                      Scanning market... Please wait for the first cycle to complete.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}

function StatCard({ title, value, icon, subtitle, trend }) {
  return (
    <motion.div 
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      className="glass-panel p-6 space-y-2 hover:border-accent/20 transition-colors cursor-default"
    >
      <div className="flex justify-between items-start">
        <div className="p-2 bg-white/5 rounded-lg">{icon}</div>
        {trend && (
          <span className={`text-xs px-2 py-1 rounded-md ${trend === 'up' ? 'bg-success/10 text-success' : 'bg-danger/10 text-danger'}`}>
            {trend === 'up' ? '+1.2%' : '-0.5%'}
          </span>
        )}
      </div>
      <div className="pt-2">
        <p className="text-slate-400 text-sm font-medium">{title}</p>
        <p className="text-2xl font-bold text-slate-100">{value}</p>
        <p className="text-xs text-slate-500 mt-1">{subtitle}</p>
      </div>
    </motion.div>
  );
}

function TradeCard({ trade, onClose }) {
  return (
    <motion.div 
      layout
      initial={{ opacity: 0, x: -20 }}
      animate={{ opacity: 1, x: 0 }}
      exit={{ opacity: 0, scale: 0.95 }}
      className="glass-panel p-5 relative overflow-hidden group"
    >
      <div className="flex flex-col md:flex-row justify-between gap-6 relative z-10">
        <div className="space-y-1">
          <div className="flex items-center gap-2">
            <h3 className="text-xl font-bold">{trade.symbol}</h3>
            <span className="bg-success/10 text-success text-[10px] px-2 py-0.5 rounded uppercase font-bold tracking-wider">LONG</span>
          </div>
          <p className="text-xs text-slate-400 flex items-center gap-1">
            <Info size={12} /> Entry: ${trade.entry_price.toFixed(4)}
          </p>
        </div>

        <div className="grid grid-cols-2 md:grid-cols-3 gap-8 flex-1">
          <div>
            <p className="text-[10px] text-slate-500 uppercase font-bold tracking-widest">Current Price</p>
            <p className="text-lg font-semibold">${trade.current_price?.toFixed(4)}</p>
          </div>
          <div>
            <p className="text-[10px] text-slate-500 uppercase font-bold tracking-widest">Profit/Loss</p>
            <p className={`text-lg font-bold ${trade.pnl_usdt >= 0 ? 'text-success' : 'text-danger'}`}>
              ${trade.pnl_usdt >= 0 ? '+' : ''}{trade.pnl_usdt} ({trade.pnl_pct}%)
            </p>
          </div>
          <div className="hidden md:block">
            <p className="text-[10px] text-slate-500 uppercase font-bold tracking-widest">Confidence</p>
            <div className="flex items-center gap-2 mt-1">
              <div className="w-full bg-white/5 h-1.5 rounded-full overflow-hidden">
                <div 
                  className="bg-accent h-full rounded-full" 
                  style={{ width: `${trade.gpt_confidence}%` }}
                />
              </div>
              <span className="text-xs font-mono">{trade.gpt_confidence}%</span>
            </div>
          </div>
        </div>

        <div className="flex items-center gap-3">
          <button 
            onClick={onClose}
            className="flex-1 md:flex-none px-4 py-2 bg-success/20 text-success hover:bg-success/30 rounded-xl text-sm font-semibold transition-all border border-success/10"
          >
            Book Profit
          </button>
          <button 
            onClick={onClose}
            className="flex-1 md:flex-none px-4 py-2 bg-danger/20 text-danger hover:bg-danger/30 rounded-xl text-sm font-semibold transition-all border border-danger/10"
          >
            Stop Trade
          </button>
        </div>
      </div>
      
      {/* Progress indicators for SL/TP */}
      <div className="mt-4 pt-4 border-t border-white/5 flex items-center justify-between text-[10px] font-mono text-slate-500">
        <span className="text-danger flex items-center gap-1">
          <TrendingDown size={10} /> SL: ${trade.stop_loss.toFixed(4)}
        </span>
        <div className="flex-1 mx-4 bg-white/5 h-1 rounded-full relative">
          <div 
            className="absolute h-1.5 w-1.5 bg-white rounded-full -top-0.5 shadow-[0_0_8px_rgba(255,255,255,0.5)] transition-all duration-1000"
            style={{ left: `${Math.min(Math.max(((trade.current_price - trade.stop_loss) / (trade.take_profit - trade.stop_loss)) * 100, 0), 100)}%` }}
          />
        </div>
        <span className="text-success flex items-center gap-1">
          TP: ${trade.take_profit.toFixed(4)} <TrendingUp size={10} />
        </span>
      </div>

      {/* Decorative background element */}
      <div className={`absolute top-0 right-0 w-32 h-32 blur-[80px] -mr-16 -mt-16 opacity-20 pointer-events-none transition-colors duration-1000 ${trade.pnl_usdt >= 0 ? 'bg-success' : 'bg-danger'}`} />
    </motion.div>
  );
}

function HealthItem({ label, value, color }) {
  return (
    <div className="flex justify-between items-center text-sm">
      <span className="text-slate-500">{label}</span>
      <span className={`font-semibold ${color}`}>{value}</span>
    </div>
  );
}

export default App;
