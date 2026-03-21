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
<title>Quant Strategy — Live Dashboard</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
  :root {
    --bg: #08090d; --surface: #11131a; --surface2: #1a1d28;
    --surface3: #222636; --border: rgba(255,255,255,0.06);
    --text: #e8ecf4; --text2: #a0aec0; --muted: #5a6a85;
    --green: #10b981; --green-bg: rgba(16,185,129,0.12);
    --red: #ef4444; --red-bg: rgba(239,68,68,0.12);
    --blue: #3b82f6; --blue-bg: rgba(59,130,246,0.12);
    --purple: #a78bfa; --purple-bg: rgba(167,139,250,0.12);
    --amber: #f59e0b; --amber-bg: rgba(245,158,11,0.12);
    --cyan: #06b6d4; --cyan-bg: rgba(6,182,212,0.12);
    --gradient-1: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    --gradient-2: linear-gradient(135deg, #10b981 0%, #3b82f6 100%);
  }
  body {
    background: var(--bg); color: var(--text);
    font-family: 'Inter', system-ui, -apple-system, sans-serif;
    min-height: 100vh; line-height: 1.5;
  }

  /* ── TOPBAR ──────────────────────────────── */
  .topbar {
    background: var(--surface); border-bottom: 1px solid var(--border);
    padding: 12px 28px; display: flex; align-items: center;
    justify-content: space-between; position: sticky; top: 0; z-index: 100;
    backdrop-filter: blur(12px);
  }
  .brand {
    font-size: 15px; font-weight: 700; color: var(--text);
    display: flex; align-items: center; gap: 10px; letter-spacing: -0.02em;
  }
  .brand-icon {
    width: 32px; height: 32px; border-radius: 8px;
    background: var(--gradient-1); display: flex; align-items: center;
    justify-content: center; font-size: 16px;
  }
  .brand-sub { font-size: 11px; color: var(--muted); font-weight: 400; }
  .status-pill {
    font-size: 11px; padding: 4px 12px; border-radius: 99px;
    font-weight: 600; letter-spacing: 0.04em; text-transform: uppercase;
  }
  .status-running { background: var(--green-bg); color: var(--green); }
  .status-stopped { background: var(--red-bg); color: var(--red); }
  .topbar-right { display: flex; align-items: center; gap: 12px; }
  .clock { font-family: 'JetBrains Mono', monospace; font-size: 11px; color: var(--muted); }

  /* ── BUTTONS ─────────────────────────────── */
  .btn {
    padding: 7px 18px; border-radius: 8px; font-size: 12px;
    font-weight: 600; border: none; cursor: pointer;
    transition: all .2s; letter-spacing: 0.02em;
  }
  .btn:hover { transform: translateY(-1px); box-shadow: 0 4px 12px rgba(0,0,0,0.3); }
  .btn:active { transform: translateY(0); }
  .btn-start { background: var(--green); color: #000; }
  .btn-stop { background: var(--red); color: #fff; }
  .btn-group { display: flex; gap: 6px; }

  /* ── CONTAINER ───────────────────────────── */
  .container { max-width: 1280px; margin: 0 auto; padding: 24px; }

  /* ── GRID ────────────────────────────────── */
  .grid { display: grid; gap: 16px; }
  .grid-5 { grid-template-columns: repeat(5, 1fr); }
  .grid-3 { grid-template-columns: repeat(3, 1fr); }
  .grid-2 { grid-template-columns: 1fr 1fr; }
  @media(max-width:1024px) { .grid-5 { grid-template-columns: repeat(3, 1fr); } }
  @media(max-width:768px) { .grid-5,.grid-3,.grid-2 { grid-template-columns: 1fr 1fr; } }
  @media(max-width:480px) { .grid-5,.grid-3,.grid-2 { grid-template-columns: 1fr; } }

  /* ── CARDS ───────────────────────────────── */
  .card {
    background: var(--surface); border: 1px solid var(--border);
    border-radius: 14px; padding: 18px; position: relative; overflow: hidden;
  }
  .card::before {
    content: ''; position: absolute; top: 0; left: 0; right: 0;
    height: 1px; background: linear-gradient(90deg, transparent, rgba(255,255,255,0.06), transparent);
  }
  .card-icon {
    width: 36px; height: 36px; border-radius: 10px;
    display: flex; align-items: center; justify-content: center;
    font-size: 16px; margin-bottom: 12px;
  }
  .card-title {
    font-size: 11px; color: var(--muted); text-transform: uppercase;
    letter-spacing: 0.08em; font-weight: 500; margin-bottom: 6px;
  }
  .card-value { font-size: 24px; font-weight: 700; letter-spacing: -0.02em; }
  .card-sub { font-size: 11px; color: var(--muted); margin-top: 4px; }

  /* ── COLORS ──────────────────────────────── */
  .green { color: var(--green); } .red { color: var(--red); }
  .blue { color: var(--blue); } .amber { color: var(--amber); }
  .purple { color: var(--purple); } .cyan { color: var(--cyan); }

  /* ── SECTIONS ────────────────────────────── */
  .section-header {
    display: flex; justify-content: space-between; align-items: center;
    margin: 28px 0 14px; padding-bottom: 8px;
    border-bottom: 1px solid var(--border);
  }
  .section-title {
    font-size: 14px; font-weight: 600; color: var(--text);
    display: flex; align-items: center; gap: 8px;
  }
  .section-badge {
    font-size: 10px; padding: 2px 8px; border-radius: 99px;
    background: var(--surface3); color: var(--text2);
  }

  /* ── SIGNAL PANEL ────────────────────────── */
  .signal-panel {
    background: var(--surface); border: 1px solid var(--border);
    border-radius: 14px; padding: 20px;
  }
  .signal-bar-container {
    height: 8px; background: var(--surface3); border-radius: 99px;
    overflow: hidden; margin: 8px 0; position: relative;
  }
  .signal-bar {
    height: 100%; border-radius: 99px; transition: width .5s ease;
    position: absolute;
  }
  .signal-bar.positive { background: var(--green); right: 50%; }
  .signal-bar.negative { background: var(--red); left: 50%; }
  .signal-center {
    position: absolute; top: -2px; left: 50%; width: 2px; height: 12px;
    background: var(--muted); transform: translateX(-50%); border-radius: 1px;
  }
  .signal-labels {
    display: flex; justify-content: space-between;
    font-size: 10px; color: var(--muted);
  }

  /* ── REGIME INDICATOR ────────────────────── */
  .regime-indicator {
    display: flex; align-items: center; gap: 10px;
    padding: 12px 16px; border-radius: 10px; margin-top: 8px;
  }
  .regime-dot {
    width: 12px; height: 12px; border-radius: 50%;
    animation: pulse 2s infinite;
  }
  @keyframes pulse { 0%,100%{opacity:1} 50%{opacity:0.5} }
  .regime-safe { background: var(--green-bg); }
  .regime-danger { background: var(--red-bg); }

  /* ── TRADE CARDS ─────────────────────────── */
  .active-trade-card {
    background: var(--surface); border: 1px solid rgba(59,130,246,0.3);
    border-radius: 14px; padding: 20px; position: relative; overflow: hidden;
  }
  .active-trade-card::before {
    content: ''; position: absolute; top: 0; left: 0; right: 0;
    height: 2px; background: var(--gradient-2);
  }
  .no-trade {
    text-align: center; padding: 40px; color: var(--muted); font-size: 13px;
  }
  .trade-card {
    background: var(--surface2); border: 1px solid var(--border);
    border-radius: 12px; padding: 14px 18px; margin-bottom: 10px;
    transition: border-color .2s;
  }
  .trade-card:hover { border-color: rgba(255,255,255,0.12); }
  .trade-header {
    display: flex; justify-content: space-between; align-items: center;
    margin-bottom: 10px;
  }
  .trade-dir {
    font-size: 11px; font-weight: 700; padding: 3px 10px;
    border-radius: 6px; letter-spacing: 0.06em;
  }
  .long-badge { background: var(--green-bg); color: var(--green); }
  .short-badge { background: var(--red-bg); color: var(--red); }
  .trade-result {
    font-size: 10px; padding: 2px 10px; border-radius: 99px;
    font-weight: 600; letter-spacing: 0.04em;
  }
  .res-win { background: var(--green-bg); color: var(--green); }
  .res-loss { background: var(--red-bg); color: var(--red); }
  .res-open { background: var(--blue-bg); color: var(--blue); }
  .trade-grid { display: grid; grid-template-columns: repeat(3,1fr); gap: 8px; }
  .trade-field { font-size: 11px; color: var(--muted); }
  .trade-field span {
    display: block; font-size: 13px; color: var(--text);
    font-weight: 600; margin-top: 2px;
    font-family: 'JetBrains Mono', monospace;
  }

  /* ── STRATEGY RULES ──────────────────────── */
  .rule-list { list-style: none; }
  .rule-list li {
    display: flex; gap: 10px; padding: 10px 0;
    border-bottom: 1px solid var(--border);
    font-size: 12px; color: var(--text2); align-items: flex-start;
  }
  .rule-list li:last-child { border-bottom: none; }
  .rule-num {
    width: 22px; height: 22px; border-radius: 6px; flex-shrink: 0;
    display: flex; align-items: center; justify-content: center;
    font-size: 10px; font-weight: 700; color: #fff;
  }

  /* ── LOG ──────────────────────────────────── */
  .log-container {
    background: var(--surface2); border-radius: 10px; padding: 14px;
    font-family: 'JetBrains Mono', monospace; font-size: 11px;
    color: var(--text2); max-height: 260px; overflow-y: auto;
    border: 1px solid var(--border);
  }
  .log-entry {
    padding: 3px 0; border-bottom: 1px solid rgba(255,255,255,0.02);
  }
</style>
</head>
<body>

<div class="topbar">
  <div class="brand">
    <div class="brand-icon">⚡</div>
    <div>
      Quant Strategy Bot
      <div class="brand-sub">TSMOM + Vol Target + Regime</div>
    </div>
  </div>
  <div class="topbar-right">
    <span class="clock" id="clock"></span>
    <span class="status-pill" id="statusPill">Loading…</span>
    <div class="btn-group">
      <button class="btn btn-start" onclick="startBot()">▶ Start</button>
      <button class="btn btn-stop" onclick="stopBot()">■ Stop</button>
    </div>
  </div>
</div>

<div class="container">

  <!-- STAT CARDS -->
  <div class="grid grid-5" style="margin-bottom:20px">
    <div class="card">
      <div class="card-icon" style="background:var(--green-bg)">💰</div>
      <div class="card-title">Balance</div>
      <div class="card-value green" id="balance">—</div>
      <div class="card-sub">USDT Futures</div>
    </div>
    <div class="card">
      <div class="card-icon" style="background:var(--blue-bg)">📊</div>
      <div class="card-title">Signals Today</div>
      <div class="card-value blue" id="signalsToday">—</div>
      <div class="card-sub">Max 2 per day</div>
    </div>
    <div class="card">
      <div class="card-icon" style="background:var(--purple-bg)">📈</div>
      <div class="card-title">Total PnL</div>
      <div class="card-value" id="totalPnl">—</div>
      <div class="card-sub">All closed trades</div>
    </div>
    <div class="card">
      <div class="card-icon" style="background:var(--cyan-bg)">🎯</div>
      <div class="card-title">Win Rate</div>
      <div class="card-value cyan" id="winRate">—</div>
      <div class="card-sub" id="tradeCount">— trades</div>
    </div>
    <div class="card">
      <div class="card-icon" style="background:var(--amber-bg)">🛡️</div>
      <div class="card-title">Circuit Breaker</div>
      <div class="card-value" id="circuitBreaker">—</div>
      <div class="card-sub">20% DD kill switch</div>
    </div>
  </div>

  <!-- SIGNAL + REGIME ROW -->
  <div class="grid grid-3" style="margin-bottom:20px">
    <!-- Momentum Signal -->
    <div class="signal-panel">
      <div class="card-title">Momentum Signal</div>
      <div style="display:flex;justify-content:space-between;align-items:baseline;margin-bottom:4px">
        <div class="card-value" id="momentumVal" style="font-size:20px">—</div>
        <span class="card-sub" id="momentumDir">—</span>
      </div>
      <div class="signal-bar-container">
        <div class="signal-center"></div>
        <div class="signal-bar" id="signalBarPos" style="width:0%"></div>
        <div class="signal-bar" id="signalBarNeg" style="width:0%"></div>
      </div>
      <div class="signal-labels"><span>SHORT −1</span><span>0</span><span>LONG +1</span></div>
    </div>

    <!-- Vol Leverage -->
    <div class="signal-panel">
      <div class="card-title">Vol-Targeted Leverage</div>
      <div class="card-value purple" id="volLev" style="font-size:20px">—</div>
      <div class="card-sub">Target: 15% annual vol</div>
      <div style="margin-top:12px">
        <div class="card-title">Realized Vol (Ann.)</div>
        <div style="font-size:16px;font-weight:600;color:var(--amber)" id="realVol">—</div>
      </div>
    </div>

    <!-- Regime -->
    <div class="signal-panel">
      <div class="card-title">Market Regime</div>
      <div id="regimeIndicator" class="regime-indicator regime-safe">
        <div class="regime-dot" id="regimeDot" style="background:var(--green)"></div>
        <div>
          <div style="font-weight:600;font-size:14px" id="regimeLabel">Safe</div>
          <div style="font-size:11px;color:var(--muted)" id="regimeDesc">
            Volatility within normal range
          </div>
        </div>
      </div>
      <div class="card-sub" style="margin-top:10px">
        Fast/Slow vol ratio &lt; 2.0 = Safe
      </div>
    </div>
  </div>

  <!-- ACTIVE TRADE & STRATEGY -->
  <div class="grid grid-2">
    <div>
      <div class="section-header">
        <div class="section-title">🔥 Active Trade</div>
        <span class="card-sub" id="lastUpdate"></span>
      </div>
      <div id="activeTrade">
        <div class="active-trade-card"><div class="no-trade">
          No active trade — scanning for signals
        </div></div>
      </div>
    </div>

    <div>
      <div class="section-header">
        <div class="section-title">🧠 Strategy Pillars</div>
      </div>
      <div class="card">
        <ul class="rule-list">
          <li>
            <div class="rule-num" style="background:var(--blue)">1</div>
            <div><strong>TSMOM</strong> — Multi-period momentum (21/63/126/252h lookbacks), z-score normalized, weighted composite signal</div>
          </li>
          <li>
            <div class="rule-num" style="background:var(--purple)">2</div>
            <div><strong>Vol Targeting</strong> — Auto-sizes positions to target 15% annualized vol using Parkinson estimator</div>
          </li>
          <li>
            <div class="rule-num" style="background:var(--amber)">3</div>
            <div><strong>Regime Filter</strong> — Fast/slow vol ratio > 2.0 = dangerous regime = no trades</div>
          </li>
          <li>
            <div class="rule-num" style="background:var(--green)">4</div>
            <div><strong>Trend Gate</strong> — Only trade in direction of 480-period SMA trend</div>
          </li>
          <li>
            <div class="rule-num" style="background:var(--red)">5</div>
            <div><strong>Risk Control</strong> — 2% risk per trade, ATR stops (2×SL / 4×TP), 20% DD kill switch</div>
          </li>
        </ul>
      </div>
    </div>
  </div>

  <!-- TRADE LOG -->
  <div class="section-header">
    <div class="section-title">📋 Recent Trades <span class="section-badge">Last 20</span></div>
  </div>
  <div id="tradeLog"></div>

  <!-- BOT LOG -->
  <div class="section-header">
    <div class="section-title">📝 Live Log</div>
    <button class="btn" style="background:var(--surface3);color:var(--text2);font-size:11px;padding:5px 14px" onclick="fetchLog()">Refresh</button>
  </div>
  <div class="log-container" id="botLog">Loading…</div>

</div>

<script>
// ── Clock ────────────────────────────────────────
function clock() {
  const now = new Date();
  document.getElementById('clock').textContent =
    now.toUTCString().replace('GMT','UTC');
}
clock(); setInterval(clock, 1000);

// ── API Calls ────────────────────────────────────
async function fetchStatus() {
  try {
    const r = await fetch('/api/status');
    const d = await r.json();
    updateDashboard(d);
  } catch(e) { console.error(e); }
}

function updateDashboard(d) {
  const running = d.running;

  // Status pill
  const pill = document.getElementById('statusPill');
  pill.textContent = running ? 'Running' : 'Stopped';
  pill.className = 'status-pill ' + (running ? 'status-running' : 'status-stopped');

  // Stats
  document.getElementById('signalsToday').textContent = d.signals_today ?? '—';
  document.getElementById('lastUpdate').textContent = 'Updated ' + new Date().toLocaleTimeString();

  // Circuit breaker
  const cb = document.getElementById('circuitBreaker');
  cb.textContent = d.circuit_breaker ? 'ACTIVE' : 'OFF';
  cb.className = 'card-value ' + (d.circuit_breaker ? 'red' : 'green');

  // Momentum signal
  const sig = d.last_signal || 0;
  document.getElementById('momentumVal').textContent = sig.toFixed(4);
  const dirText = sig > 0.15 ? '▲ LONG' : sig < -0.15 ? '▼ SHORT' : '● NEUTRAL';
  const dirColor = sig > 0.15 ? 'green' : sig < -0.15 ? 'red' : 'muted';
  const dirEl = document.getElementById('momentumDir');
  dirEl.textContent = dirText;
  dirEl.className = 'card-sub ' + dirColor;

  // Signal bar
  const posBar = document.getElementById('signalBarPos');
  const negBar = document.getElementById('signalBarNeg');
  posBar.className = 'signal-bar positive';
  negBar.className = 'signal-bar negative';
  if (sig > 0) {
    posBar.style.width = (sig * 50) + '%';
    negBar.style.width = '0%';
  } else {
    posBar.style.width = '0%';
    negBar.style.width = (Math.abs(sig) * 50) + '%';
  }

  // Vol leverage
  document.getElementById('volLev').textContent = (d.last_vol_leverage || 0).toFixed(2) + '×';
  document.getElementById('realVol').textContent = ((d.last_realized_vol || 0) * 100).toFixed(1) + '%';

  // Regime
  const safe = d.last_regime_safe;
  const ri = document.getElementById('regimeIndicator');
  ri.className = 'regime-indicator ' + (safe ? 'regime-safe' : 'regime-danger');
  document.getElementById('regimeDot').style.background = safe ? 'var(--green)' : 'var(--red)';
  document.getElementById('regimeLabel').textContent = safe ? 'Safe' : 'Danger';
  document.getElementById('regimeLabel').style.color = safe ? 'var(--green)' : 'var(--red)';
  document.getElementById('regimeDesc').textContent = safe
    ? 'Normal volatility — trading enabled'
    : 'Vol spike detected — trading paused';

  // Stats
  const stats = d.stats || {};
  const totalPnl = stats.total_pnl || 0;
  const tpEl = document.getElementById('totalPnl');
  tpEl.textContent = (totalPnl >= 0 ? '+$' : '-$') + Math.abs(totalPnl).toFixed(2);
  tpEl.className = 'card-value ' + (totalPnl >= 0 ? 'green' : 'red');
  document.getElementById('winRate').textContent = stats.total > 0 ? stats.win_rate.toFixed(0) + '%' : '—';
  document.getElementById('tradeCount').textContent = (stats.total || 0) + ' trades';

  // Active trade
  const at = d.active_trade;
  const atDiv = document.getElementById('activeTrade');
  if (at) {
    const dc = at.direction === 'LONG' ? 'long-badge' : 'short-badge';
    atDiv.innerHTML = `<div class="active-trade-card">
      <div class="trade-header">
        <span class="trade-dir ${dc}">${at.direction}</span>
        <span class="trade-result res-open">OPEN</span>
      </div>
      <div class="trade-grid">
        <div class="trade-field">Entry<span>$${Number(at.entry).toLocaleString()}</span></div>
        <div class="trade-field">Stop Loss<span class="red">$${Number(at.stop).toLocaleString()}</span></div>
        <div class="trade-field">Take Profit<span class="green">$${Number(at.take_profit).toLocaleString()}</span></div>
        <div class="trade-field">Quantity<span>${at.qty} BTC</span></div>
        <div class="trade-field">Risk<span>$${Number(at.risk_usd).toFixed(2)}</span></div>
        <div class="trade-field">Signal<span>${Number(at.signal_strength).toFixed(3)}</span></div>
        <div class="trade-field">Vol Lev<span>${Number(at.vol_leverage).toFixed(2)}×</span></div>
      </div>
      <div style="font-size:11px;color:var(--muted);margin-top:10px">
        Opened: ${at.opened_at?.slice(0,19).replace('T',' ')} UTC
      </div>
    </div>`;
  } else {
    atDiv.innerHTML = '<div class="active-trade-card"><div class="no-trade">No active trade — scanning for signals</div></div>';
  }

  // Trade log
  const log = d.trade_log || [];
  const logDiv = document.getElementById('tradeLog');
  if (log.length === 0) {
    logDiv.innerHTML = '<div class="card" style="text-align:center;color:var(--muted);padding:30px">No trades yet</div>';
  } else {
    logDiv.innerHTML = log.slice(0,20).map(t => {
      const dc = t.direction === 'LONG' ? 'long-badge' : 'short-badge';
      const rc = t.result === 'WIN' ? 'res-win' : t.result === 'LOSS' ? 'res-loss' : 'res-open';
      const pc = (t.pnl||0) >= 0 ? 'green' : 'red';
      const ps = (t.pnl||0) >= 0 ? '+' : '';
      return `<div class="trade-card">
        <div class="trade-header">
          <div style="display:flex;gap:8px;align-items:center">
            <span class="trade-dir ${dc}">${t.direction}</span>
            <span style="font-size:11px;color:var(--muted)">${t.opened_at?.slice(0,10)||''}</span>
          </div>
          <div style="display:flex;gap:8px;align-items:center">
            <span class="${pc}" style="font-size:14px;font-weight:700;font-family:'JetBrains Mono',monospace">
              ${ps}$${Math.abs(t.pnl||0).toFixed(2)}
            </span>
            <span class="trade-result ${rc}">${t.result}</span>
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
    document.getElementById('balance').textContent =
      '$' + Number(d.balance).toLocaleString(undefined, {minimumFractionDigits:2, maximumFractionDigits:2});
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

// Poll
fetchStatus(); fetchBalance(); fetchLog();
setInterval(fetchStatus, 10000);
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
