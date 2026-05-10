"""
╔══════════════════════════════════════════════════════════════════════════════╗
║   QUANT STRATEGY DASHBOARD — Premium Dark UI                               ║
║   Flask web server for the multi-factor quant bot                          ║
║   Run: python app_quant.py                                                 ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

import os
from datetime import datetime, timezone
from flask import Flask, jsonify, render_template_string, abort
from bot_quant import QuantBot, LiveConfig

app = Flask(__name__)

cfg = LiveConfig()
bot = QuantBot(cfg)

# ─── DASHBOARD HTML ──────────────────────────────────────────────────────────
DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Quantum Hedge Fund — Live Terminal</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
  :root {
    --bg: #050608; --surface: #0d0f14; --surface2: #14171f;
    --surface3: #1c212b; --border: rgba(255,255,255,0.08);
    --text: #f0f4f8; --text2: #94a3b8; --muted: #475569;
    --green: #10b981; --green-bg: rgba(16,185,129,0.15);
    --red: #f43f5e; --red-bg: rgba(244,63,94,0.15);
    --blue: #3b82f6; --blue-bg: rgba(59,130,246,0.15);
    --purple: #8b5cf6; --purple-bg: rgba(139,92,246,0.15);
    --amber: #f59e0b; --amber-bg: rgba(245,158,11,0.15);
    --cyan: #06b6d4; --cyan-bg: rgba(6,182,212,0.15);
    --glow: 0 0 20px rgba(16,185,129,0.2);
    --gradient-1: linear-gradient(135deg, #4f46e5 0%, #7c3aed 100%);
  }
  body {
    background: var(--bg); color: var(--text);
    font-family: 'Inter', sans-serif; min-height: 100vh;
  }

  /* ── TOPBAR ──────────────────────────────── */
  .topbar {
    background: rgba(13,15,20,0.8); border-bottom: 1px solid var(--border);
    padding: 10px 24px; display: flex; align-items: center;
    justify-content: space-between; position: sticky; top: 0; z-index: 100;
    backdrop-filter: blur(20px);
  }
  .brand {
    font-size: 16px; font-weight: 800; color: #fff;
    display: flex; align-items: center; gap: 12px; letter-spacing: -0.03em;
  }
  .brand-icon {
    width: 34px; height: 34px; border-radius: 9px;
    background: var(--gradient-1); display: flex; align-items: center;
    justify-content: center; font-size: 18px; box-shadow: 0 4px 15px rgba(124,58,237,0.3);
  }
  .status-pill {
    font-size: 10px; padding: 4px 12px; border-radius: 99px; font-weight: 700;
    letter-spacing: 0.05em; text-transform: uppercase;
  }
  .status-running { background: var(--green-bg); color: var(--green); box-shadow: var(--glow); }
  .status-stopped { background: var(--red-bg); color: var(--red); }

  /* ── BUTTONS ─────────────────────────────── */
  .btn {
    padding: 8px 16px; border-radius: 8px; font-size: 12px;
    font-weight: 600; border: 1px solid rgba(255,255,255,0.1); cursor: pointer;
    transition: all .2s; background: var(--surface2); color: #fff;
  }
  .btn:hover { background: var(--surface3); border-color: rgba(255,255,255,0.2); }
  .btn-start { background: var(--green); color: #000; border: none; }
  .btn-stop { background: var(--red); color: #fff; border: none; }

  /* ── GRID SYSTEM ─────────────────────────── */
  .container { max-width: 1400px; margin: 0 auto; padding: 20px; }
  .grid { display: grid; gap: 16px; }
  .grid-stats { grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); }
  .grid-main { grid-template-columns: 2fr 1fr; }
  .grid-2 { grid-template-columns: 1fr 1fr; display: grid; gap: 16px; }
  
  @media (max-width: 900px) {
      .grid-main { grid-template-columns: 1fr; }
      .grid-2 { grid-template-columns: 1fr; }
  }
  
  /* ── CARDS ───────────────────────────────── */
  .card {
    background: var(--surface); border: 1px solid var(--border);
    border-radius: 12px; padding: 16px; transition: transform 0.2s;
  }
  .card-title {
    font-size: 10px; color: var(--muted); text-transform: uppercase;
    font-weight: 700; letter-spacing: 0.1em; margin-bottom: 8px;
  }
  .card-value { font-size: 22px; font-weight: 800; font-family: 'JetBrains Mono', monospace; }
  .card-sub { font-size: 11px; color: var(--muted); margin-top: 2px; }

  /* ── SPECIFIC UI ─────────────────────────── */
  .sizing-badge {
      display: inline-block; padding: 2px 8px; border-radius: 4px;
      font-size: 10px; font-weight: 700; margin-left: 8px;
  }
  .sizing-full { background: var(--green-bg); color: var(--green); }
  .sizing-reduced { background: var(--amber-bg); color: var(--amber); }

  .order-table { width: 100%; border-collapse: collapse; margin-top: 10px; }
  .order-table th { text-align: left; font-size: 10px; color: var(--muted); padding: 8px; border-bottom: 1px solid var(--border); }
  .order-table td { padding: 8px; font-size: 12px; border-bottom: 1px solid var(--border); font-family: 'JetBrains Mono', monospace; }

  .trade-field { display: flex; flex-direction: column; font-size: 10px; color: var(--muted); font-weight: 700; background: rgba(0,0,0,0.2); padding: 12px; border-radius: 6px; }
  .trade-field span { font-size: 16px; font-weight: 800; margin-top: 4px; font-family: 'JetBrains Mono', monospace; color: #fff; }
  .trade-field span.green { color: var(--green); }
  .trade-field span.red { color: var(--red); }

  /* ── LOGS ────────────────────────────────── */
  .terminal {
    background: #000; border-radius: 8px; padding: 12px;
    height: 300px; overflow-y: auto; font-family: 'JetBrains Mono', monospace;
    font-size: 11px; line-height: 1.6; border: 1px solid var(--border);
  }
  .log-entry { margin-bottom: 2px; color: #a0aec0; }
  .log-entry.info { color: #fff; }
  .log-entry.warn { color: var(--amber); }
  .log-entry.error { color: var(--red); }
</style>
</head>
<body>

<div class="topbar">
  <div class="brand">
    <div class="brand-icon">Q</div>
    <div>QUANTUM TERMINAL <span style="font-size:10px; color:var(--muted); font-weight:400">V2.0.1</span></div>
  </div>
  <div style="display:flex; gap:16px; align-items:center">
    <span class="status-pill" id="statusPill">...</span>
    <div style="display:flex; gap:8px">
      <button class="btn btn-start" onclick="startBot()">RESUME BOT</button>
      <button class="btn btn-stop" onclick="stopBot()">HALT BOT</button>
    </div>
  </div>
</div>

<div class="container">
  
  <!-- ROW 1: CORE METRICS -->
  <div class="grid grid-stats" style="margin-bottom:16px">
    <div class="card">
      <div class="card-title">REAL-TIME BALANCE</div>
      <div class="card-value green" id="balance">$0.00</div>
      <div class="card-sub">Start: <span id="startBalance">$0.00</span></div>
    </div>
    <div class="card">
      <div class="card-title">ALGO PERFORMANCE</div>
      <div class="card-value" id="roiPct">0.00%</div>
      <div class="card-sub" id="tradeCount">0 Completed Trades</div>
    </div>
    <div class="card">
        <div class="card-title">NET PnL (USDT)</div>
        <div class="card-value" id="totalPnl">$0.00</div>
        <div class="card-sub">Win Rate: <span id="winRate">0%</span></div>
      </div>
    <div class="card">
      <div class="card-title">MARGIN UTILIZATION</div>
      <div class="card-value purple" id="marginUsed">$0.00</div>
      <div class="card-sub">Max Leverage: 5x</div>
    </div>
    <div class="card">
        <div class="card-title">MTD SIZING SCALE</div>
        <div id="sizingContainer">
            <span class="card-value" id="sizingVal">100%</span>
            <span class="sizing-badge sizing-full" id="sizingBadge">OPTIMAL</span>
        </div>
        <div class="card-sub">Reduces at 20% Drawdown</div>
      </div>
  </div>

  <!-- ROW 2: LIVE EXECUTION -->
  <div class="grid grid-main" style="margin-bottom:16px">
    <div class="card">
      <div class="card-title">🔥 LIVE EXECUTION ENGINE</div>
      <div id="activeTrade">
        <div style="text-align:center; padding:60px; color:var(--muted); font-size:13px">NO ACTIVE ORDERS — SCANNING MARKET</div>
      </div>
      
      <div style="margin-top:24px">
        <div class="card-title">SYSTEM OPEN ORDERS (SL/TP)</div>
        <table class="order-table">
            <thead>
                <tr><th>TYPE</th><th>SIDE</th><th>TRIGGER PRICE</th><th>TIME (UTC)</th></tr>
            </thead>
            <tbody id="openOrders">
                <tr><td colspan="4" style="text-align:center; color:var(--muted)">No pending orders</td></tr>
            </tbody>
        </table>
      </div>
    </div>

    <div class="grid" style="gap:16px">
        <div class="card">
            <div class="card-title">MOMENTUM Z-SCORE</div>
            <div style="display:flex; justify-content:space-between; align-items:center">
                <div class="card-value" id="momentumVal">0.0000</div>
                <div id="momentumBadge" style="font-size:10px; font-weight:700">NEUTRAL</div>
            </div>
            <div style="height:6px; background:var(--surface3); border-radius:3px; margin-top:10px; overflow:hidden; position:relative">
                <div id="momentumBarPos" style="position:absolute; left:50%; height:100%; background:var(--green); width:0%"></div>
                <div id="momentumBarNeg" style="position:absolute; right:50%; height:100%; background:var(--red); width:0%"></div>
            </div>
        </div>
        <div class="card">
            <div class="card-title">MARKET REGIME</div>
            <div id="regimeBox" style="display:flex; align-items:center; gap:12px; padding:8px; border-radius:8px; background:var(--green-bg)">
                <div id="regimeDot" style="width:10px; height:10px; border-radius:50%; background:var(--green)"></div>
                <div>
                    <div style="font-weight:700; font-size:12px" id="regimeLabel">SAFE</div>
                    <div style="font-size:10px; color:var(--muted)" id="volRatio">Vol Ratio: 1.0</div>
                </div>
            </div>
        </div>
        <div class="card">
            <div class="card-title">CIRCUIT BREAKERS</div>
            <div style="display:flex; justify-content:space-between; align-items:center">
                <span style="font-size:12px">Total Protection (30%):</span>
                <span id="hardBreaker" style="color:var(--green); font-weight:700">ONLINE</span>
            </div>
        </div>
    </div>
  </div>

  <!-- ROW 3: HISTORY & LOGS -->
  <div class="grid grid-2">
    <div>
      <div class="card-title">📋 RECENT DECISIONS</div>
      <div id="tradeLog"></div>
    </div>
    <div>
      <div class="card-title">⚡ REAL-TIME KERNEL LOGS</div>
      <div class="terminal" id="botLog">Initializing terminal...</div>
    </div>
  </div>

</div>

<script>
async function refresh() {
  const r = await fetch('/api/status');
  const d = await r.json();
  
  // Status
  const pill = document.getElementById('statusPill');
  pill.textContent = d.running ? 'TRADING ACTIVE' : 'SYSTEM HALTED';
  pill.className = 'status-pill ' + (d.running ? 'status-running' : 'status-stopped');

  // Balances & ROI
  document.getElementById('balance').textContent = '$' + d.margin_used + ' / $' + (d.stats.total_pnl + d.starting_balance).toFixed(2);
  document.getElementById('roiPct').textContent = (d.roi_pct >= 0 ? '+' : '') + d.roi_pct + '%';
  document.getElementById('roiPct').className = 'card-value ' + (d.roi_pct >= 0 ? 'green' : 'red');
  document.getElementById('startBalance').textContent = '$' + d.starting_balance;
  document.getElementById('marginUsed').textContent = '$' + d.margin_used;
  
  // Sizing
  const sf = d.reduction_factor || 1.0;
  document.getElementById('sizingVal').textContent = (sf * 100).toFixed(0) + '%';
  document.getElementById('sizingBadge').textContent = sf < 1.0 ? 'REDUCED' : 'OPTIMAL';
  document.getElementById('sizingBadge').className = 'sizing-badge ' + (sf < 1.0 ? 'sizing-reduced' : 'sizing-full');

  // Stats
  document.getElementById('totalPnl').textContent = (d.stats.total_pnl >= 0 ? '+$' : '-$') + Math.abs(d.stats.total_pnl).toFixed(2);
  document.getElementById('totalPnl').className = 'card-value ' + (d.stats.total_pnl >= 0 ? 'green' : 'red');
  document.getElementById('winRate').textContent = d.stats.win_rate.toFixed(1) + '%';
  document.getElementById('tradeCount').textContent = d.stats.total + ' Completed Trades';

  // Momentum
  const sig = d.last_signal || 0;
  document.getElementById('momentumVal').textContent = sig.toFixed(4);
  document.getElementById('momentumBadge').textContent = sig > 0.2 ? 'STRONG BUY' : sig < -0.2 ? 'STRONG SELL' : 'NEUTRAL';
  document.getElementById('momentumBadge').style.color = sig > 0.2 ? 'var(--green)' : sig < -0.2 ? 'var(--red)' : 'var(--muted)';
  document.getElementById('momentumBarPos').style.width = sig > 0 ? (sig * 50) + '%' : '0%';
  document.getElementById('momentumBarNeg').style.width = sig < 0 ? (Math.abs(sig) * 50) + '%' : '0%';

  // Regime
  const safe = d.last_regime_safe;
  document.getElementById('regimeBox').style.background = safe ? 'var(--green-bg)' : 'var(--red-bg)';
  document.getElementById('regimeDot').style.background = safe ? 'var(--green)' : 'var(--red)';
  document.getElementById('regimeLabel').textContent = safe ? 'SAFE' : 'DANGER';
  document.getElementById('regimeLabel').style.color = safe ? 'var(--green)' : 'var(--red)';
  document.getElementById('volRatio').textContent = 'Volatility Ratio: ' + d.last_vol_leverage.toFixed(2);

  // Active Trade
  const at = d.active_trade;
  const atDiv = document.getElementById('activeTrade');
  if (at) {
    atDiv.innerHTML = `
      <div style="display:flex; justify-content:space-between; background:var(--surface2); padding:16px; border-radius:8px; border:1px solid var(--blue)">
        <div>
           <div style="font-size:10px; color:var(--muted)">SYMBOL</div>
           <div style="font-weight:800; font-size:18px">BTC/USDT <span style="color:${at.direction=='LONG'?'var(--green)':'var(--red)'}">${at.direction}</span></div>
        </div>
        <div style="text-align:right">
           <div style="font-size:10px; color:var(--muted)">POSITION SIZE</div>
           <div style="font-weight:800; font-size:18px">${at.qty} BTC</div>
        </div>
      </div>
      <div style="display:grid; grid-template-columns: repeat(3,1fr); gap:12px; margin-top:16px">
         <div class="trade-field">ENTRY<span>$${Number(at.entry).toLocaleString()}</span></div>
         <div class="trade-field">STOP LOSS<span class="red">$${Number(at.stop).toLocaleString()}</span></div>
         <div class="trade-field">TAKE PROFIT<span class="green">$${Number(at.take_profit).toLocaleString()}</span></div>
      </div>
    `;
  } else {
    atDiv.innerHTML = `<div style="text-align:center; padding:60px; color:var(--muted); font-size:13px">NO ACTIVE ORDERS — SCANNING MARKET</div>`;
  }

  // Open Orders
  const oo = d.open_orders || [];
  const ooBody = document.getElementById('openOrders');
  if (oo.length > 0) {
      ooBody.innerHTML = oo.map(o => `
        <tr>
            <td><span class="sizing-badge sizing-reduced">${o.type}</span></td>
            <td style="color:${o.side=='BUY'?'var(--green)':'var(--red)'}">${o.side}</td>
            <td>$${Number(o.price).toLocaleString()}</td>
            <td style="color:var(--muted)">${o.time.slice(11,19)}</td>
        </tr>
      `).join('');
  } else {
      ooBody.innerHTML = `<tr><td colspan="4" style="text-align:center; color:var(--muted)">No pending orders</td></tr>`;
  }

  // Trade Log
  const trades = d.trade_log || [];
  document.getElementById('tradeLog').innerHTML = trades.map(t => {
      const pc = (t.pnl||0)>=0?'var(--green)':'var(--red)';
      return `
        <div style="display:flex; justify-content:space-between; padding:10px 0; border-bottom:1px solid var(--border)">
            <div style="font-size:12px">
                <span style="font-weight:700; color:${t.direction=='LONG'?'var(--green)':'var(--red)'}">${t.direction}</span>
                <span style="color:var(--muted); margin-left:8px">${t.exit_time?.substring(5,16).replace('T',' ')}</span>
            </div>
            <div style="font-weight:800; font-family:'JetBrains Mono'; color:${pc}">${(t.pnl>=0?'+':'-')}$${Math.abs(t.pnl).toFixed(2)}</div>
        </div>
      `;
  }).join('') || '<div style="padding:20px; color:var(--muted); text-align:center">No history available</div>';
}

async function fetchLog() {
  const r = await fetch('/api/log');
  const d = await r.json();
  const logDiv = document.getElementById('botLog');
  logDiv.innerHTML = d.lines.map(l => {
      let type = 'info';
      if (l.includes('WARNING')) type = 'warn';
      if (l.includes('ERROR') || l.includes('🚨')) type = 'error';
      return `<div class="log-entry ${type}">${l}</div>`;
  }).join('');
  logDiv.scrollTop = logDiv.scrollHeight;
}

async function startBot() { 
    try {
        const res = await fetch('/api/start',{method:'POST'}); 
        if (!res.ok) {
            const text = await res.text();
            alert('Error starting bot: ' + text);
        }
    } catch (e) {
        alert('Network error starting bot.');
    }
    setTimeout(refresh, 1000); 
}
async function stopBot() { 
    await fetch('/api/stop',{method:'POST'}); 
    setTimeout(refresh, 1000); 
}

refresh(); fetchLog();
setInterval(refresh, 5000);
setInterval(fetchLog, 10000);
</script>
</body>
</html>
"""


# ─── ROUTES ───────────────────────────────────────────────────────────────────
@app.route("/health")
def health():
    return jsonify({"status": "ok"})

@app.route("/")
def dashboard():
    return render_template_string(DASHBOARD_HTML)

@app.route("/api/status")
def api_status():
    return jsonify(bot.status())

@app.route("/api/balance")
def api_balance():
    try:
        bal = bot.get_balance() if bot.client else 0.0
        return jsonify({"balance": bal})
    except Exception as e:
        return jsonify({"balance": 0.0, "error": str(e)})

@app.route("/api/start", methods=["POST"])
def api_start():
    if not cfg.API_KEY or not cfg.API_SECRET:
        abort(400, "API keys not configured. Set BINANCE_API_KEY and BINANCE_API_SECRET env vars.")
    bot.start()
    return jsonify({"status": "started"})

@app.route("/api/stop", methods=["POST"])
def api_stop():
    bot.stop()
    return jsonify({"status": "stopped"})

@app.route("/api/log")
def api_log():
    try:
        with open("bot_quant.log", "r") as f:
            lines = f.readlines()[-100:]
        return jsonify({"lines": [l.strip() for l in lines]})
    except FileNotFoundError:
        return jsonify({"lines": []})

@app.route("/api/config")
def api_config():
    return jsonify({
        "symbol":           cfg.SYMBOL,
        "interval":         cfg.INTERVAL,
        "target_vol":       cfg.TARGET_VOL_ANNUAL,
        "risk_per_trade":   cfg.RISK_PER_TRADE,
        "max_leverage":     cfg.MAX_LEVERAGE,
        "regime_threshold": cfg.REGIME_THRESHOLD,
        "stop_atr_mult":    cfg.STOP_ATR_MULT,
        "tp_atr_mult":      cfg.TP_ATR_MULT,
        "max_dd_pct":       cfg.MAX_DRAWDOWN_PCT,
        "testnet":          cfg.TESTNET,
    })


if __name__ == "__main__":
    port = int(os.getenv("PORT", 5001))
    app.run(host="0.0.0.0", port=port, debug=False)
