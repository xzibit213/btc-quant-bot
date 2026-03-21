"""
Flask web server — trading dashboard + REST API
Run with: gunicorn app:app  (or  python app.py  for dev)
"""

import os
import json
from datetime import datetime, timezone
from flask import Flask, jsonify, render_template_string, request, abort
from bot import BBBot, Config

app = Flask(__name__)

# Initialise bot (single instance)
cfg = Config()
bot = BBBot(cfg)

# ─── DASHBOARD HTML ──────────────────────────────────────────────────────────
DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>BTC BB Bot — Live Dashboard</title>
<style>
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
  :root {
    --bg: #0f1117; --surface: #1a1d26; --surface2: #22263a;
    --border: rgba(255,255,255,0.08); --text: #e2e8f0; --muted: #64748b;
    --green: #22c55e; --red: #ef4444; --amber: #f59e0b; --blue: #3b82f6;
    --purple: #a855f7;
  }
  body { background: var(--bg); color: var(--text); font-family: 'Inter', system-ui, sans-serif; min-height: 100vh; }
  .topbar { background: var(--surface); border-bottom: 1px solid var(--border); padding: 14px 24px; display: flex; align-items: center; justify-content: space-between; }
  .brand { font-size: 16px; font-weight: 600; color: var(--text); display: flex; align-items: center; gap: 8px; }
  .brand-dot { width: 10px; height: 10px; border-radius: 50%; background: var(--green); animation: pulse 2s infinite; }
  @keyframes pulse { 0%,100%{opacity:1} 50%{opacity:0.4} }
  .status-pill { font-size: 11px; padding: 4px 10px; border-radius: 99px; font-weight: 500; }
  .status-running { background: rgba(34,197,94,0.15); color: var(--green); }
  .status-stopped { background: rgba(239,68,68,0.15); color: var(--red); }
  .container { max-width: 1200px; margin: 0 auto; padding: 24px; }
  .grid { display: grid; gap: 16px; }
  .grid-4 { grid-template-columns: repeat(4, 1fr); }
  .grid-2 { grid-template-columns: 1fr 1fr; }
  @media(max-width:768px) { .grid-4,.grid-2 { grid-template-columns: 1fr 1fr; } }
  @media(max-width:480px) { .grid-4,.grid-2 { grid-template-columns: 1fr; } }
  .card { background: var(--surface); border: 1px solid var(--border); border-radius: 12px; padding: 16px; }
  .card-title { font-size: 11px; color: var(--muted); text-transform: uppercase; letter-spacing: .06em; margin-bottom: 6px; }
  .card-value { font-size: 22px; font-weight: 600; }
  .card-sub { font-size: 11px; color: var(--muted); margin-top: 3px; }
  .green { color: var(--green); } .red { color: var(--red); } .amber { color: var(--amber); } .blue { color: var(--blue); }
  h3 { font-size: 14px; font-weight: 600; margin-bottom: 12px; color: var(--text); }
  .trade-card { background: var(--surface2); border: 1px solid var(--border); border-radius: 10px; padding: 14px 16px; margin-bottom: 10px; }
  .trade-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
  .trade-dir { font-size: 12px; font-weight: 600; padding: 3px 8px; border-radius: 6px; }
  .long-badge  { background: rgba(34,197,94,0.15); color: var(--green); }
  .short-badge { background: rgba(239,68,68,0.15); color: var(--red); }
  .trade-result { font-size: 11px; padding: 2px 8px; border-radius: 99px; font-weight: 500; }
  .res-win  { background: rgba(34,197,94,0.15);  color: var(--green); }
  .res-loss { background: rgba(239,68,68,0.15);  color: var(--red); }
  .res-open { background: rgba(59,130,246,0.15); color: var(--blue); }
  .trade-grid { display: grid; grid-template-columns: repeat(3,1fr); gap: 6px; }
  .trade-field { font-size: 11px; color: var(--muted); }
  .trade-field span { display: block; font-size: 12px; color: var(--text); font-weight: 500; margin-top: 1px; }
  .active-trade-card { background: var(--surface); border: 1px solid rgba(59,130,246,0.4); border-radius: 12px; padding: 16px; position: relative; overflow: hidden; }
  .active-trade-card::before { content:''; position:absolute; top:0; left:0; right:0; height:2px; background:linear-gradient(90deg,var(--blue),var(--purple)); }
  .no-trade { text-align: center; padding: 32px; color: var(--muted); font-size: 13px; }
  .btn { padding: 8px 20px; border-radius: 8px; font-size: 13px; font-weight: 500; border: none; cursor: pointer; transition: opacity .15s; }
  .btn:hover { opacity: 0.85; }
  .btn-start { background: var(--green); color: #000; }
  .btn-stop  { background: var(--red);   color: #fff; }
  .btn-group { display: flex; gap: 8px; }
  .log-container { background: var(--surface2); border-radius: 8px; padding: 12px; font-family: 'Courier New', monospace; font-size: 11px; color: #94a3b8; max-height: 240px; overflow-y: auto; }
  .log-entry { padding: 2px 0; border-bottom: 1px solid rgba(255,255,255,0.03); }
  .rule-list { list-style: none; }
  .rule-list li { display: flex; gap: 8px; padding: 7px 0; border-bottom: 1px solid var(--border); font-size: 12px; color: var(--muted); align-items: flex-start; }
  .rule-list li:last-child { border-bottom: none; }
  .rule-dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; margin-top: 3px; }
  .section-header { display: flex; justify-content: space-between; align-items: center; margin: 24px 0 12px; }
  .timestamp { font-size: 11px; color: var(--muted); }
  .filter-tag { display: inline-block; font-size: 10px; padding: 2px 6px; border-radius: 4px; margin: 2px; }
</style>
</head>
<body>
<div class="topbar">
  <div class="brand">
    <div class="brand-dot" id="statusDot"></div>
    BTC BB Optimised Bot
  </div>
  <div style="display:flex;align-items:center;gap:12px">
    <span class="timestamp" id="clock"></span>
    <span class="status-pill" id="statusPill">Loading…</span>
    <div class="btn-group">
      <button class="btn btn-start" onclick="startBot()">▶ Start</button>
      <button class="btn btn-stop"  onclick="stopBot()">■ Stop</button>
    </div>
  </div>
</div>

<div class="container">
  <!-- Stat cards -->
  <div class="grid grid-4" style="margin-bottom:20px">
    <div class="card">
      <div class="card-title">Balance (USDT)</div>
      <div class="card-value green" id="balance">—</div>
      <div class="card-sub">Futures wallet</div>
    </div>
    <div class="card">
      <div class="card-title">Signals today</div>
      <div class="card-value blue" id="signalsToday">—</div>
      <div class="card-sub">Max 2 per day</div>
    </div>
    <div class="card">
      <div class="card-title">Total trades (log)</div>
      <div class="card-value" id="totalTrades">—</div>
      <div class="card-sub">Since bot started</div>
    </div>
    <div class="card">
      <div class="card-title">Win rate</div>
      <div class="card-value green" id="winRate">—</div>
      <div class="card-sub">Last 20 trades</div>
    </div>
  </div>

  <div class="grid grid-2">
    <!-- Active trade -->
    <div>
      <div class="section-header">
        <h3>Active trade</h3>
        <span class="timestamp" id="lastUpdate"></span>
      </div>
      <div id="activeTrade"><div class="active-trade-card"><div class="no-trade">No active trade — waiting for signal</div></div></div>
    </div>

    <!-- Strategy filters -->
    <div>
      <h3 style="margin-top:0;margin-bottom:12px">Active filters</h3>
      <div class="card">
        <ul class="rule-list">
          <li><div class="rule-dot" style="background:#3b82f6"></div><div>BB (20, 1SD) on 1H chart — close outside band = signal</div></li>
          <li><div class="rule-dot" style="background:#22c55e"></div><div>Body ≥40% of candle range — rejects wick-spike false entries</div></li>
          <li><div class="rule-dot" style="background:#f59e0b"></div><div>Funding rate filter — skip ±30 min around 00:00 / 08:00 / 16:00 UTC</div></li>
          <li><div class="rule-dot" style="background:#a855f7"></div><div>Daily bias gate — only trade in direction of daily 20 SMA trend</div></li>
          <li><div class="rule-dot" style="background:#ef4444"></div><div>BB squeeze skip — band width < 1.5× ATR = no trade</div></li>
          <li><div class="rule-dot" style="background:#06b6d4"></div><div>Signal windows — S1: 13–16 UTC | S2: 18–20 UTC</div></li>
        </ul>
      </div>
    </div>
  </div>

  <!-- Trade log -->
  <div class="section-header" style="margin-top:24px">
    <h3>Recent trade log</h3>
    <span class="timestamp">Last 20 trades</span>
  </div>
  <div id="tradeLog"></div>

  <!-- Live bot log -->
  <div class="section-header">
    <h3>Live bot log</h3>
    <button class="btn" style="background:var(--surface2);color:var(--text);font-size:11px;padding:4px 12px" onclick="fetchLog()">Refresh</button>
  </div>
  <div class="log-container" id="botLog">Loading…</div>
</div>

<script>
function clock() {
  const now = new Date();
  document.getElementById('clock').textContent = now.toUTCString().replace('GMT','UTC');
}
clock(); setInterval(clock, 1000);

async function fetchStatus() {
  try {
    const r = await fetch('/api/status');
    const d = await r.json();
    updateDashboard(d);
  } catch(e) { console.error(e); }
}

function updateDashboard(d) {
  const running = d.running;
  document.getElementById('statusPill').textContent = running ? 'Running' : 'Stopped';
  document.getElementById('statusPill').className = 'status-pill ' + (running ? 'status-running' : 'status-stopped');
  document.getElementById('statusDot').style.background = running ? 'var(--green)' : 'var(--red)';
  document.getElementById('signalsToday').textContent = d.signals_today ?? '—';
  document.getElementById('lastUpdate').textContent = 'Updated ' + new Date().toLocaleTimeString();

  // Active trade
  const at = d.active_trade;
  const atDiv = document.getElementById('activeTrade');
  if (at) {
    const dirClass = at.direction === 'LONG' ? 'long-badge' : 'short-badge';
    const pnlSign = at.pnl >= 0 ? '+' : '';
    atDiv.innerHTML = `<div class="active-trade-card">
      <div class="trade-header">
        <span class="trade-dir ${dirClass}">${at.direction}</span>
        <span class="trade-result res-open">OPEN</span>
      </div>
      <div class="trade-grid">
        <div class="trade-field">Entry<span>$${Number(at.entry).toLocaleString()}</span></div>
        <div class="trade-field">Stop loss<span class="red">$${Number(at.stop).toLocaleString()}</span></div>
        <div class="trade-field">Take profit<span class="green">$${Number(at.take_profit).toLocaleString()}</span></div>
        <div class="trade-field">Quantity<span>${at.qty} BTC</span></div>
        <div class="trade-field">Risk<span>$${Number(at.risk_usd).toFixed(2)}</span></div>
        <div class="trade-field">Signal<span>S${at.signal}</span></div>
      </div>
      <div style="font-size:11px;color:var(--muted);margin-top:8px">Opened: ${at.opened_at?.slice(0,19).replace('T',' ')} UTC</div>
    </div>`;
  } else {
    atDiv.innerHTML = '<div class="active-trade-card"><div class="no-trade">No active trade — bot scanning for signal</div></div>';
  }

  // Trade log
  const log = d.trade_log || [];
  document.getElementById('totalTrades').textContent = log.length;
  const wins = log.filter(t => t.result === 'WIN').length;
  const closed = log.filter(t => t.result === 'WIN' || t.result === 'LOSS').length;
  document.getElementById('winRate').textContent = closed > 0 ? (wins/closed*100).toFixed(0)+'%' : '—';

  const logDiv = document.getElementById('tradeLog');
  if (log.length === 0) {
    logDiv.innerHTML = '<div class="card" style="text-align:center;color:var(--muted);padding:24px">No trades yet</div>';
  } else {
    logDiv.innerHTML = log.slice(0,20).map(t => {
      const dirClass = t.direction === 'LONG' ? 'long-badge' : 'short-badge';
      const resClass = t.result === 'WIN' ? 'res-win' : t.result === 'LOSS' ? 'res-loss' : 'res-open';
      const pnlColor = t.pnl >= 0 ? 'green' : 'red';
      const pnlSign  = t.pnl >= 0 ? '+' : '';
      return `<div class="trade-card">
        <div class="trade-header">
          <div style="display:flex;gap:8px;align-items:center">
            <span class="trade-dir ${dirClass}">${t.direction}</span>
            <span style="font-size:11px;color:var(--muted)">${t.opened_at?.slice(0,10) || ''}</span>
          </div>
          <div style="display:flex;gap:6px;align-items:center">
            <span class="${pnlColor}" style="font-size:13px;font-weight:600">${pnlSign}$${Math.abs(t.pnl||0).toFixed(2)}</span>
            <span class="trade-result ${resClass}">${t.result}</span>
          </div>
        </div>
        <div class="trade-grid">
          <div class="trade-field">Entry<span>$${Number(t.entry||0).toLocaleString()}</span></div>
          <div class="trade-field">SL<span>$${Number(t.stop||0).toLocaleString()}</span></div>
          <div class="trade-field">TP<span>$${Number(t.take_profit||0).toLocaleString()}</span></div>
        </div>
      </div>`;
    }).join('');
  }
}

async function fetchBalance() {
  try {
    const r = await fetch('/api/balance');
    const d = await r.json();
    document.getElementById('balance').textContent = '$' + Number(d.balance).toLocaleString(undefined, {minimumFractionDigits:2, maximumFractionDigits:2});
  } catch(e) {}
}

async function fetchLog() {
  try {
    const r = await fetch('/api/log');
    const d = await r.json();
    const lines = d.lines || [];
    const logDiv = document.getElementById('botLog');
    logDiv.innerHTML = lines.map(l => `<div class="log-entry">${l}</div>`).join('') || 'No logs yet.';
    logDiv.scrollTop = logDiv.scrollHeight;
  } catch(e) {}
}

async function startBot() {
  await fetch('/api/start', {method:'POST'});
  setTimeout(fetchStatus, 500);
}
async function stopBot() {
  await fetch('/api/stop', {method:'POST'});
  setTimeout(fetchStatus, 500);
}

// Poll every 15 seconds
fetchStatus(); fetchBalance(); fetchLog();
setInterval(fetchStatus, 15000);
setInterval(fetchBalance, 30000);
setInterval(fetchLog, 30000);
</script>
</body>
</html>
"""

# ─── ROUTES ───────────────────────────────────────────────────────────────────
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
        with open("bot.log", "r") as f:
            lines = f.readlines()[-100:]
        return jsonify({"lines": [l.strip() for l in lines]})
    except FileNotFoundError:
        return jsonify({"lines": []})

@app.route("/api/config")
def api_config():
    """Return non-sensitive config for the dashboard."""
    return jsonify({
        "symbol":           cfg.SYMBOL,
        "interval":         cfg.INTERVAL,
        "bb_period":        cfg.BB_PERIOD,
        "bb_std_dev":       cfg.BB_STD_DEV,
        "risk_pct":         cfg.RISK_PCT,
        "leverage":         cfg.LEVERAGE,
        "max_signals_day":  cfg.MAX_SIGNALS_PER_DAY,
        "testnet":          cfg.TESTNET,
    })

if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
