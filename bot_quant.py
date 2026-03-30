"""
╔══════════════════════════════════════════════════════════════════════════════╗
║   INSTITUTIONAL MULTI-FACTOR QUANT BOT — LIVE TRADING ENGINE               ║
║                                                                            ║
║   Strategy: TSMOM + Volatility Targeting + Regime Detection                ║
║   Market:   BTC/USDT Futures (Binance)                                     ║
║   Risk:     2% per trade, volatility-targeted sizing, 20% DD kill switch   ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

import os
import time
import math
import logging
import threading
from datetime import datetime, timezone
from collections import deque

import numpy as np
import pandas as pd
from binance.client import Client
from binance.exceptions import BinanceAPIException

from strategy_quant import compute_indicators, StrategyConfig

# ─── LOGGING ─────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("bot_quant.log"),
        logging.StreamHandler()
    ]
)
log = logging.getLogger("QUANT_BOT")


# ─── LIVE CONFIG (extends StrategyConfig) ─────────────────────────────────────
class LiveConfig(StrategyConfig):
    """Live-trading-specific configuration."""

    # Binance API
    API_KEY     = os.getenv("BINANCE_API_KEY", "")
    API_SECRET  = os.getenv("BINANCE_API_SECRET", "")
    TESTNET     = os.getenv("TESTNET", "true").lower() == "true"
    PAPER_TRADE = os.getenv("PAPER_TRADE", "true").lower() == "true"  # Set to false to use real/testnet money

    # Live overrides
    LEVERAGE        = 5              # 5× leverage cap
    EVAL_INTERVAL   = 60             # Check every 60 seconds
    CANDLE_LIMIT    = 500            # Bars to fetch for indicator computation
    DAILY_LIMIT     = 30             # Daily candles for trend bias


# ─── POSITION SIZER ──────────────────────────────────────────────────────────
def calc_position_size(balance, risk_pct, entry, stop, vol_leverage,
                       close_price, symbol_info):
    """
    Dual-constrained position sizing:
    1. Risk-based: (balance × risk_pct) / |entry - stop|
    2. Vol-targeted: (balance × vol_leverage) / close_price
    Uses the smaller of the two.
    """
    stop_distance = abs(entry - stop)
    if stop_distance == 0:
        return 0.0

    qty_risk = (balance * risk_pct) / stop_distance
    qty_vol  = (balance * vol_leverage) / close_price
    raw_qty  = min(qty_risk, qty_vol)

    # Respect Binance LOT_SIZE
    step_size = float(symbol_info.get("stepSize", 0.001))
    precision = int(round(-math.log10(step_size)))
    qty = math.floor(raw_qty / step_size) * step_size
    qty = round(qty, precision)
    return max(qty, float(symbol_info.get("minQty", 0.001)))


# ─── TRADE STATE ──────────────────────────────────────────────────────────────
class TradeState:
    """Thread-safe trade state and daily counters."""

    def __init__(self):
        self._lock          = threading.Lock()
        self.active_trade   = None
        self.signals_today  = 0
        self.last_date      = None
        self.trade_log      = deque(maxlen=500)
        self.peak_balance   = 0.0
        self.circuit_breaker = False
        self.current_month   = ""
        self.monthly_peak    = 0.0
        self.reduction_factor = 1.0
        self.starting_balance = 0.0

    def reset_daily(self, today):
        with self._lock:
            if self.last_date != today:
                self.signals_today = 0
                self.last_date = today
                log.info(f"Daily counter reset for {today}")

    def can_take_signal(self, max_signals):
        with self._lock:
            return (self.signals_today < max_signals
                    and not self.circuit_breaker)

    def open_trade(self, trade):
        with self._lock:
            self.active_trade = trade
            self.signals_today += 1
            self.trade_log.appendleft(trade)
            log.info(f"Trade opened: {trade['direction']} @ ${trade['entry']:.0f}")

    def close_trade(self, result, pnl):
        with self._lock:
            if self.active_trade:
                self.active_trade["result"] = result
                self.active_trade["pnl"] = pnl
                self.active_trade["closed_at"] = datetime.now(timezone.utc).isoformat()
                log.info(f"Trade closed: {result} | PnL: ${pnl:.2f}")
                self.active_trade = None

    def check_drawdown(self, balance, max_dd_pct, month_max_dd_pct):
        with self._lock:
            # 1. Total Drawdown (Hard Circuit Breaker)
            self.peak_balance = max(self.peak_balance, balance)
            if self.peak_balance > 0:
                total_dd = (self.peak_balance - balance) / self.peak_balance
                if total_dd >= max_dd_pct:
                    if not self.circuit_breaker:
                        self.circuit_breaker = True
                        log.warning(f"🚨 TOTAL CIRCUIT BREAKER ACTIVATED — DD: {total_dd*100:.1f}%")
                elif total_dd < max_dd_pct * 0.5:
                    if self.circuit_breaker:
                        self.circuit_breaker = False
                        log.info("Total circuit breaker deactivated — drawdown recovered")

            # 2. Monthly Drawdown (Soft Reduction)
            today = datetime.now(timezone.utc).strftime("%Y-%m")
            if not hasattr(self, 'monthly_peak') or self.current_month != today:
                self.current_month = today
                self.monthly_peak = balance
                log.info(f"Monthly drawdown tracker reset for {today}")
            
            self.monthly_peak = max(self.monthly_peak, balance)
            monthly_dd = (self.monthly_peak - balance) / self.monthly_peak if self.monthly_peak > 0 else 0
            self.reduction_factor = 0.25 if monthly_dd >= month_max_dd_pct else 1.0
            
            if self.reduction_factor < 1.0:
                log.warning(f"⚠️ MONTHLY DRAWDOWN EXCEEDED ({monthly_dd*100:.1f}%) — SIZING REDUCED BY 75%")

    def get_log(self):
        with self._lock:
            return list(self.trade_log)

    def get_stats(self):
        with self._lock:
            log_list = list(self.trade_log)
            closed = [t for t in log_list if t.get("result") in ("WIN", "LOSS")]
            wins = [t for t in closed if t["result"] == "WIN"]
            return {
                "total": len(closed),
                "wins": len(wins),
                "losses": len(closed) - len(wins),
                "win_rate": (len(wins) / len(closed) * 100) if closed else 0,
                "total_pnl": sum(t.get("pnl", 0) for t in closed),
            }


# ─── MAIN BOT CLASS ──────────────────────────────────────────────────────────
class QuantBot:
    def __init__(self, cfg=None):
        self.cfg      = cfg or LiveConfig()
        self.state    = TradeState()
        self.client   = None
        self._running = False
        self._thread  = None
        self.symbol_info = {}
        self._last_fail_time = None  # Cooldown after failed trade attempt

        # Cached regime/signal state for dashboard
        self.last_signal    = 0.0
        self.last_regime    = True
        self.last_vol_lev   = 1.0
        self.last_realized_vol = 0.0
        
        # API request caching to prevent rate-limit drain from dashboard
        self._cached_balance = 0.0
        self._last_balance_time = 0
        self._cached_orders = []
        self._last_orders_time = 0

    # ── Connection ────────────────────────────────────────────────────────────
    def connect(self):
        mode = "TESTNET" if self.cfg.TESTNET else "LIVE"
        log.info(f"Connecting to Binance {mode}...")

        self.client = Client(
            self.cfg.API_KEY, self.cfg.API_SECRET,
            testnet=self.cfg.TESTNET
        )
        self.client.ping()

        # Get symbol info
        info = self.client.futures_exchange_info()
        for sym in info["symbols"]:
            if sym["symbol"] == self.cfg.SYMBOL:
                for f in sym["filters"]:
                    if f["filterType"] == "LOT_SIZE":
                        self.symbol_info = {
                            "stepSize": f["stepSize"],
                            "minQty": f["minQty"]
                        }

        # Set leverage and margin type
        try:
            self.client.futures_change_margin_type(
                symbol=self.cfg.SYMBOL,
                marginType="ISOLATED"
            )
        except Exception:
            pass # Already set

        self.client.futures_change_leverage(
            symbol=self.cfg.SYMBOL,
            leverage=self.cfg.LEVERAGE
        )
        log.info(f"Connected. Leverage={self.cfg.LEVERAGE}×  LOT_SIZE={self.symbol_info}")

    # ── Data ──────────────────────────────────────────────────────────────────
    def fetch_ohlcv(self, limit=500):
        """Fetch OHLCV and compute all strategy indicators."""
        raw = self.client.futures_klines(
            symbol=self.cfg.SYMBOL,
            interval=self.cfg.INTERVAL,
            limit=limit
        )
        df = pd.DataFrame(raw, columns=[
            "ts", "open", "high", "low", "close", "volume",
            "close_ts", "quote_vol", "trades", "taker_base", "taker_quote", "ignore"
        ])
        for col in ["open", "high", "low", "close", "volume"]:
            df[col] = df[col].astype(float)
        df["ts"] = pd.to_datetime(df["ts"], unit="ms", utc=True)
        df.set_index("ts", inplace=True)

        # Compute all indicators
        df = compute_indicators(df, self.cfg)
        return df

    def get_balance(self, force_fetch=False):
        if not self.client:
            return 0.0
            
        now = time.time()
        # Return cached balance if fetched within the last 60 seconds unless forced
        if not force_fetch and (now - self._last_balance_time) < 60:
            return self._cached_balance

        try:
            balances = self.client.futures_account_balance()
            for b in balances:
                if b["asset"] == "USDT":
                    avail = float(b["availableBalance"])
                    self._cached_balance = avail
                    self._last_balance_time = now
                    return avail
            return 0.0
        except Exception as e:
            log.error(f"Error fetching balance: {e}")
            return self._cached_balance

    # ── Order Execution ───────────────────────────────────────────────────────
    def cancel_open_orders(self):
        """Cancel ALL open orders for the symbol to clean up orphaned SL/TP."""
        try:
            open_orders = self.client.futures_get_open_orders(symbol=self.cfg.SYMBOL)
            if open_orders:
                log.info(f"Cancelling {len(open_orders)} orphaned open order(s)...")
                self.client.futures_cancel_all_open_orders(symbol=self.cfg.SYMBOL)
                log.info("All open orders cancelled.")
        except BinanceAPIException as e:
            log.warning(f"Failed to cancel open orders: {e}")

    def get_open_orders(self, force_fetch=False):
        """Fetch all open orders from Binance with caching to avoid rate limits."""
        if not self.client: return []
        
        now = time.time()
        # Cache orders for 60 seconds
        if not force_fetch and (now - self._last_orders_time) < 60:
            return self._cached_orders
            
        try:
            orders = self.client.futures_get_open_orders(symbol=self.cfg.SYMBOL)
            parsed = [{
                "id": o["orderId"],
                "type": o["type"],
                "side": o["side"],
                "price": o.get("stopPrice") or o["price"],
                "time": datetime.fromtimestamp(o["time"]/1000, tz=timezone.utc).isoformat()
            } for o in orders]
            
            self._cached_orders = parsed
            self._last_orders_time = now
            return parsed
        except Exception:
            return self._cached_orders

    def place_order(self, direction, qty, entry, stop, take_profit):
        """
        Executes an institutional entry (Market only, as requested).
        """
        side = "BUY"  if direction == "LONG"  else "SELL"

        log.info(f"Placing {direction} | qty={qty} | Expected Entry=${entry:.0f}")

        # Step 1: Place Entry Order
        try:
            entry_order = self.client.futures_create_order(
                symbol=self.cfg.SYMBOL, side=side, type="MARKET", quantity=qty
            )
        except BinanceAPIException as e:
            log.error(f"Entry order failed: {e}")
            raise  

        entry_id = entry_order.get("orderId", "unknown")

        return {
            "entry_id": entry_id,
            "sl_id": None,
            "tp_id": None,
        }

    # ── Signal Evaluation ─────────────────────────────────────────────────────
    def evaluate(self):
        now = datetime.now(timezone.utc)
        today = now.strftime("%Y-%m-%d")
        self.state.reset_daily(today)

        # Check circuit breaker
        balance = self.get_balance()
        self.state.check_drawdown(balance, self.cfg.MAX_DRAWDOWN_PCT, self.cfg.MONTH_MAX_DD_PCT)

        if not self.state.can_take_signal(self.cfg.MAX_TRADES_PER_DAY):
            return

        # Check cooldown after failed trade (15 minutes)
        if self._last_fail_time:
            elapsed = (now - self._last_fail_time).total_seconds()
            if elapsed < 900:  # 15 minutes
                return
            else:
                self._last_fail_time = None
                log.info("Cooldown expired — resuming signal evaluation")

        # Fetch data and compute indicators
        df = self.fetch_ohlcv(limit=self.cfg.CANDLE_LIMIT)

        # Read latest indicator values (use second-to-last = last closed candle)
        idx = -2
        signal      = df['momentum_signal'].iloc[idx]
        regime_safe = df['regime_safe'].iloc[idx] == 1
        vol_lev     = df['vol_leverage'].iloc[idx]
        atr         = df['atr'].iloc[idx]
        close       = df['close'].iloc[idx]
        trend_sma   = df['trend_sma'].iloc[idx]
        realized_vol = df['realized_vol'].iloc[idx]

        # Cache for dashboard
        self.last_signal = signal
        self.last_regime = regime_safe
        self.last_vol_lev = vol_lev
        self.last_realized_vol = realized_vol

        # Skip NaN
        if any(np.isnan(x) for x in [signal, atr, vol_lev, close]):
            return

        # Determine direction
        direction = None
        if signal > 0.15:
            direction = "LONG"
        elif signal < -0.15:
            direction = "SHORT"
            
        # Reversal Logic: Close existing trade if strategy changes direction
        active = self.state.active_trade
        if active and direction and direction != active["direction"]:
            log.info(f"Strategy changed direction from {active['direction']} to {direction}. Closing existing position.")
            try:
                close_side = "SELL" if active["direction"] == "LONG" else "BUY"
                if not self.cfg.PAPER_TRADE:
                    self.client.futures_create_order(
                        symbol=self.cfg.SYMBOL, side=close_side, type="MARKET", quantity=active["qty"]
                    )
                self.state.close_trade("REVERSAL", 0.0)
            except Exception as e:
                log.error(f"Failed to close reversed trade: {e}")
                return
                
        # If we still have an active trade (because direction is None or same direction), hold position.
        active = self.state.active_trade
        if active:
            return

        if direction is None:
            log.debug(f"No signal (momentum={signal:.3f})")
            return

        # Filter 1: Regime
        if not regime_safe:
            log.info(f"Signal {direction} FILTERED: Regime unsafe (vol ratio too high)")
            return

        # Filter 2: Trend alignment
        if not np.isnan(trend_sma):
            if direction == "LONG" and close < trend_sma:
                log.info(f"Signal LONG FILTERED: Below trend SMA")
                return
            if direction == "SHORT" and close > trend_sma:
                log.info(f"Signal SHORT FILTERED: Above trend SMA")
                return

        # Calculate stops
        stop_distance = atr * self.cfg.STOP_ATR_MULT
        entry = close

        if direction == "LONG":
            stop = entry - stop_distance
            tp   = entry + atr * self.cfg.TP_ATR_MULT
        else:
            stop = entry + stop_distance
            tp   = entry - atr * self.cfg.TP_ATR_MULT

        # Position sizing
        qty = calc_position_size(
            balance, self.cfg.RISK_PER_TRADE,
            entry, stop, vol_lev, close,
            self.symbol_info
        )
        
        # Apply Monthly Reduction Factor
        qty *= self.state.reduction_factor

        if qty <= 0:
            log.warning("Position size = 0 — skipping")
            return

        risk_usd = balance * self.cfg.RISK_PER_TRADE
        log.info(f"{'🧪 PAPER SIGNAL' if self.cfg.PAPER_TRADE else '✅ LIVE SIGNAL'} | {direction} | Momentum={signal:.3f} | "
                 f"VolLev={vol_lev:.2f}× | M_Sizing={self.state.reduction_factor:.2f} | "
                 f"Entry≈${entry:.0f} | SL=${stop:.0f} | TP=${tp:.0f} | Qty={qty} | Risk=${risk_usd:.2f}")

        try:
            if self.cfg.PAPER_TRADE:
                # Bypass API and simulate order placement securely
                order_ids = {"entry_id": f"paper_{int(time.time())}", "sl_id": "paper_sl", "tp_id": "paper_tp"}
                log.info("PAPER TRADE MODE ACTIVE: Ignored live exchange execution.")
            else:
                order_ids = self.place_order(direction, qty, entry, stop, tp)
                
            self.state.open_trade({
                "id": order_ids["entry_id"],
                "direction": direction,
                "entry": entry,
                "stop": stop,
                "take_profit": tp,
                "qty": qty,
                "risk_usd": risk_usd,
                "signal_strength": signal,
                "vol_leverage": vol_lev,
                "balance_at_entry": balance,
                "opened_at": now.isoformat(),
                "result": "OPEN",
                "pnl": 0.0,
                "is_paper": self.cfg.PAPER_TRADE,
                **order_ids
            })
        except BinanceAPIException as e:
            log.error(f"Order failed: {e}")
            # Cooldown: don't retry for 15 minutes after a failure
            self._last_fail_time = datetime.now(timezone.utc)
            log.warning("⏸️ 15-minute cooldown activated after failed trade")

    # ── Position Monitor ──────────────────────────────────────────────────────
    def monitor_positions(self):
        trade = self.state.active_trade
        if not trade:
            return
            
        # 1. LATENCY GUARD: Prevent ghosting trades due to Binance Read-Replica Lag
        opened_at_str = trade.get("opened_at")
        if opened_at_str:
            # Parse handle Python 3.11+ isoformat w/ or w/o Z
            if opened_at_str.endswith("Z"): opened_at_str = opened_at_str[:-1] + "+00:00"
            opened_at = datetime.fromisoformat(opened_at_str)
            
            # If the trade was opened less than 15 seconds ago, the REST API position endpoint 
            # might still return positionAmt = 0.0 because it's accessing a delayed database replica.
            if (datetime.now(timezone.utc) - opened_at).total_seconds() < 15:
                # Safely ignore checking to prevent premature local memory wiping
                return

        try:
            # Paper trade check: don't query the exchange
            if trade.get("is_paper"):
                try:
                    ticker = self.client.futures_mark_price(symbol=self.cfg.SYMBOL)
                    mark_price = float(ticker["markPrice"])
                except:
                    return # Skip if network fails
                    
                direction = trade["direction"]
                sl = trade["stop"]
                tp = trade["take_profit"]
                
                # Check for virtual SL or TP hit
                if (direction == "LONG" and (mark_price <= sl or mark_price >= tp)) or \
                   (direction == "SHORT" and (mark_price >= sl or mark_price <= tp)):
                    pnl = (mark_price - trade["entry"]) * trade["qty"] if direction == "LONG" else (trade["entry"] - mark_price) * trade["qty"]
                    result = "WIN" if pnl > 0 else "LOSS"
                    self.state.close_trade(result, pnl)
                    log.info(f"[PAPER TRADE SIMULATION] Position Virtually Closed.")
                return

            positions = self.client.futures_position_information(symbol=self.cfg.SYMBOL)
            for pos in positions:
                if pos["symbol"] == self.cfg.SYMBOL:
                    amt = float(pos["positionAmt"])
                    if abs(amt) < 0.0001:
                        # Position is genuinely closed
                        entry_price = float(pos.get("entryPrice", trade["entry"]))
                        mark_price  = float(pos.get("markPrice",  trade["entry"]))
                        direction   = trade["direction"]
                        qty         = trade["qty"]
                        pnl = (mark_price - entry_price) * qty if direction == "LONG" \
                            else (entry_price - mark_price) * qty
                        result = "WIN" if pnl > 0 else "LOSS"
                        self.state.close_trade(result, pnl)
        except BinanceAPIException as e:
            log.error(f"Monitor error: {e}")

    # ── Institutional Loop & Sync ─────────────────────────────────────────────
    def sync_state_with_exchange(self):
        """Reconcile internal bot memory with actual Binance state on startup."""
        log.info("Synchronizing state with Binance...")
        try:
            positions = self.client.futures_position_information(symbol=self.cfg.SYMBOL)
            has_pos = False
            for pos in positions:
                if pos["symbol"] == self.cfg.SYMBOL:
                    amt = float(pos["positionAmt"])
                    if abs(amt) > 0.0001:
                        has_pos = True
                        direction = "LONG" if amt > 0 else "SHORT"
                        entry_price = float(pos["entryPrice"])
                        log.info(f"Exchange reports open position: {direction} qty={abs(amt)} at ${entry_price}")
                        
                        if not self.state.active_trade:
                            log.warning("Recovering orphaned position into bot state...")
                            self.state.open_trade({
                                "id": "recovered",
                                "direction": direction,
                                "entry": entry_price,
                                "stop": 0,
                                "take_profit": 0,
                                "qty": abs(amt),
                                "result": "OPEN",
                                "pnl": 0.0,
                                "opened_at": datetime.now(timezone.utc).isoformat()
                            })
            
            if not has_pos and self.state.active_trade:
                log.warning("Bot memory has a position, but exchange says NO. Clearing bot memory.")
                self.state.active_trade = None
                
            open_orders = self.client.futures_get_open_orders(symbol=self.cfg.SYMBOL)
            if not has_pos and open_orders:
                log.warning(f"Found {len(open_orders)} orphaned orders without a position. Cancelling...")
                self.client.futures_cancel_all_open_orders(symbol=self.cfg.SYMBOL)
        except Exception as e:
            log.error(f"Failed to sync state: {e}")

    def _wait_for_next_candle(self):
        """Precision sleeper to wake up EXACTLY when a new candle closes. Eliminates drift."""
        now = datetime.now(timezone.utc)
        
        # Parse INTERVAL to seconds (e.g., '1h' -> 3600)
        interval_str = self.cfg.INTERVAL
        if interval_str.endswith('h'):
            total_seconds = int(interval_str[:-1]) * 3600
        elif interval_str.endswith('m'):
            total_seconds = int(interval_str[:-1]) * 60
        else:
            total_seconds = 3600 # Default to 1h
            
        current_ts = now.timestamp()
        # Find next exact boundary
        next_boundary = ((int(current_ts) // total_seconds) + 1) * total_seconds
        
        # +1.5s buffer ensures Binance has finalised the candle before we fetch
        sleep_time = (next_boundary - current_ts) + 1.5
        
        sleep_mins = sleep_time / 60
        log.info(f"Candle closes in {sleep_mins:.1f} minutes. Sleeping until {datetime.fromtimestamp(next_boundary, tz=timezone.utc).strftime('%H:%M:%S UTC')}...")
        
        end_time = time.time() + sleep_time
        while time.time() < end_time and self._running:
            time.sleep(1) # Sleep in 1s chunks so stop() is responsive

    # ── Main Loop ─────────────────────────────────────────────────────────────
    def _run_loop(self):
        log.info("Institutional engine loop started.")
        self.sync_state_with_exchange()
        
        while self._running:
            try:
                # 1. Check if we have an open position
                if self.state.active_trade:
                    # If heavily exposed, monitor positions quickly instead of waiting for full candle close
                    self.monitor_positions()
                    time.sleep(30) # 30s polling when in active trade
                else:
                    # 2. No position? Precision sleep until the next candle
                    self._wait_for_next_candle()
                    if not self._running:
                        break
                        
                    # 3. Candle closed! Evaluate new signals exactly when data is fresh
                    log.info("Candle closed. Evaluating new signals...")
                    self.evaluate()
                    self.monitor_positions()
                    
            except Exception as e:
                log.error(f"Loop error: {e}", exc_info=True)
                time.sleep(10) # Cooldown on crash
                
        log.info("Quant bot loop stopped.")

    def start(self):
        if self._running:
            log.warning("Bot already running.")
            return
        self.connect()
        # Initialize starting balance for ROI
        if self.state.starting_balance == 0:
            self.state.starting_balance = self.get_balance()
            log.info(f"Starting balance recorded: ${self.state.starting_balance:.2f}")

        self._running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        log.info("Quant bot started.")

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=10)
        log.info("Quant bot stopped.")

    def status(self):
        now = datetime.now(timezone.utc)
        stats = self.state.get_stats()
        
        # Calculate ROI
        balance = self.get_balance()
        start_bal = self.state.starting_balance or balance
        roi_pct = ((balance - start_bal) / start_bal * 100) if start_bal > 0 else 0.0
        
        # Margin used
        margin_used = 0.0
        if self.state.active_trade:
            margin_used = (self.state.active_trade['qty'] * self.state.active_trade['entry']) / self.cfg.LEVERAGE

        return {
            "running":           bool(self._running),
            "timestamp":         now.isoformat(),
            "active_trade":      self.state.active_trade,
            "signals_today":     int(self.state.signals_today),
            "circuit_breaker":   bool(self.state.circuit_breaker),
            "last_signal":       float(round(self.last_signal, 4)),
            "last_regime_safe":  bool(self.last_regime),
            "last_vol_leverage": float(round(self.last_vol_lev, 3)),
            "last_realized_vol": float(round(self.last_realized_vol, 4)),
            "reduction_factor":  self.state.reduction_factor,
            "starting_balance":  round(start_bal, 2),
            "roi_pct":           round(roi_pct, 2),
            "margin_used":       round(margin_used, 2),
            "open_orders":       self.get_open_orders(),
            "stats":             stats,
            "trade_log":         self.state.get_log()[:20],
        }
