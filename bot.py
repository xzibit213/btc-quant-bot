"""
╔══════════════════════════════════════════════════════════════════════════╗
║         BTC BOLLINGER BAND OPTIMISED TRADING BOT — BINANCE FUTURES      ║
║  Strategy: BB (20, 1SD) on 1H | 5 Filters | 1% Risk | 2 Signals/Day    ║
║  Author: Generated for automated deployment                              ║
╚══════════════════════════════════════════════════════════════════════════╝
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

# ─── LOGGING ─────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("bot.log"),
        logging.StreamHandler()
    ]
)
log = logging.getLogger("BB_BOT")

# ─── CONFIGURATION ────────────────────────────────────────────────────────────
class Config:
    # Binance API (set via environment variables — never hard-code keys)
    API_KEY    = os.getenv("BINANCE_API_KEY", "")
    API_SECRET = os.getenv("BINANCE_API_SECRET", "")
    TESTNET    = os.getenv("TESTNET", "true").lower() == "true"

    # Strategy parameters
    SYMBOL         = "BTCUSDT"
    INTERVAL       = Client.KLINE_INTERVAL_1HOUR
    BB_PERIOD      = 20
    BB_STD_DEV     = 1.0          # 1 standard deviation (not the default 2)
    ATR_PERIOD     = 14
    ATR_MULTIPLIER = 2.0          # stop = ATR × 2.0 away from entry
    RISK_PCT       = 0.01         # 1% of account per trade
    MIN_RR         = 2.0          # minimum 2:1 reward-to-risk
    LEVERAGE       = 1            # keep at 1× — bot manages risk via position size
    MAX_SIGNALS_PER_DAY = 2

    # Filter parameters
    MIN_BODY_RATIO     = 0.40     # candle body must be ≥40% of total range
    FUNDING_BUFFER_MIN = 30       # minutes to skip around funding resets
    BB_SQUEEZE_RATIO   = 1.5      # band width < 1.5 × ATR = squeeze = skip

    # Signal windows (UTC hours)
    SIGNAL_1_WINDOW = (8, 11)     # London/NY open overlap (8–11am EST = 13–16 UTC)
    SIGNAL_2_WINDOW = (18, 20)    # NY afternoon (1–3pm EST = 18–20 UTC)

    # Funding reset times (UTC hours)
    FUNDING_TIMES_UTC = [0, 8, 16]


# ─── INDICATORS ───────────────────────────────────────────────────────────────
def compute_bb(closes: pd.Series, period: int = 20, std_dev: float = 1.0):
    """Returns (upper, middle, lower) Bollinger Bands."""
    middle = closes.rolling(period).mean()
    std    = closes.rolling(period).std(ddof=0)
    upper  = middle + std_dev * std
    lower  = middle - std_dev * std
    return upper, middle, lower


def compute_atr(highs: pd.Series, lows: pd.Series, closes: pd.Series, period: int = 14):
    """Returns ATR series."""
    prev_close = closes.shift(1)
    tr = pd.concat([
        highs - lows,
        (highs - prev_close).abs(),
        (lows  - prev_close).abs()
    ], axis=1).max(axis=1)
    return tr.rolling(period).mean()


# ─── FILTER ENGINE ────────────────────────────────────────────────────────────
class FilterEngine:
    """All 5 optimisation filters. Returns (passed: bool, reason: str)."""

    def __init__(self, cfg: Config):
        self.cfg = cfg

    def body_filter(self, open_: float, high: float, low: float, close: float):
        """Filter 1 — candle body must be ≥40% of full range."""
        rng = high - low
        if rng == 0:
            return False, "Zero-range candle"
        body = abs(close - open_)
        ratio = body / rng
        if ratio < self.cfg.MIN_BODY_RATIO:
            return False, f"Body ratio {ratio:.0%} < {self.cfg.MIN_BODY_RATIO:.0%}"
        return True, "OK"

    def funding_filter(self, utc_hour: int, utc_minute: int):
        """Filter 2 — skip ±30 min around funding rate resets."""
        buf = self.cfg.FUNDING_BUFFER_MIN
        now_min = utc_hour * 60 + utc_minute
        for ft in self.cfg.FUNDING_TIMES_UTC:
            ft_min = ft * 60
            if abs(now_min - ft_min) <= buf:
                return False, f"Near funding reset at {ft:02d}:00 UTC"
        return True, "OK"

    def bb_squeeze_filter(self, upper: float, lower: float, atr: float):
        """Filter 3 — skip when BB bands are too tight (squeeze)."""
        if atr == 0:
            return False, "ATR is zero"
        band_width = upper - lower
        if band_width < self.cfg.BB_SQUEEZE_RATIO * atr:
            return False, f"BB squeeze: width {band_width:.0f} < {self.cfg.BB_SQUEEZE_RATIO}×ATR {atr:.0f}"
        return True, "OK"

    def daily_bias_filter(self, direction: str, daily_closes: pd.Series):
        """Filter 4 — trade must align with daily 20 SMA bias."""
        if len(daily_closes) < 20:
            return True, "Insufficient daily data — skip bias check"
        daily_sma = daily_closes.rolling(20).mean().iloc[-1]
        current   = daily_closes.iloc[-1]
        if direction == "LONG"  and current < daily_sma:
            return False, f"Daily bias BEARISH (price {current:.0f} < SMA {daily_sma:.0f})"
        if direction == "SHORT" and current > daily_sma:
            return False, f"Daily bias BULLISH (price {current:.0f} > SMA {daily_sma:.0f})"
        return True, "OK"

    def signal_window_filter(self, signal_num: int, utc_hour: int):
        """Filter 5 — signal must fire within its allowed time window."""
        win = self.cfg.SIGNAL_1_WINDOW if signal_num == 1 else self.cfg.SIGNAL_2_WINDOW
        if not (win[0] <= utc_hour < win[1]):
            return False, f"Outside signal {signal_num} window {win[0]}–{win[1]} UTC"
        return True, "OK"

    def run_all(self, signal_num: int, direction: str,
                open_: float, high: float, low: float, close: float,
                upper: float, lower: float, atr: float,
                daily_closes: pd.Series,
                utc_hour: int, utc_minute: int):
        """Run all filters. Returns (passed, reason)."""
        checks = [
            self.body_filter(open_, high, low, close),
            self.funding_filter(utc_hour, utc_minute),
            self.bb_squeeze_filter(upper, lower, atr),
            self.daily_bias_filter(direction, daily_closes),
            self.signal_window_filter(signal_num, utc_hour),
        ]
        for passed, reason in checks:
            if not passed:
                return False, reason
        return True, "All filters passed"


# ─── POSITION SIZER ──────────────────────────────────────────────────────────
def calc_position_size(balance: float, risk_pct: float,
                       entry: float, stop: float,
                       symbol_info: dict) -> float:
    """
    Returns quantity in BTC rounded to Binance step size.
    position_size = (balance × risk_pct) / abs(entry - stop)
    """
    risk_amount   = balance * risk_pct
    stop_distance = abs(entry - stop)
    if stop_distance == 0:
        return 0.0
    raw_qty = risk_amount / stop_distance

    # Respect Binance LOT_SIZE filter
    step_size = float(symbol_info.get("stepSize", 0.001))
    precision = int(round(-math.log10(step_size)))
    qty = math.floor(raw_qty / step_size) * step_size
    qty = round(qty, precision)
    return max(qty, float(symbol_info.get("minQty", 0.001)))


# ─── SIGNAL DETECTOR ─────────────────────────────────────────────────────────
def detect_signal(df: pd.DataFrame, cfg: Config):
    """
    Examines the LAST CLOSED 1H candle.
    Returns ("LONG" | "SHORT" | None, details_dict)
    """
    if len(df) < cfg.BB_PERIOD + 2:
        return None, {"reason": "Insufficient candle data"}

    # Last CLOSED candle is index -2 (index -1 is the currently forming candle)
    c = df.iloc[-2]
    upper  = df["bb_upper"].iloc[-2]
    middle = df["bb_middle"].iloc[-2]
    lower  = df["bb_lower"].iloc[-2]
    atr    = df["atr"].iloc[-2]

    direction = None
    if c["close"] > upper:
        direction = "LONG"
    elif c["close"] < lower:
        direction = "SHORT"
    else:
        return None, {"reason": "No BB breach on last candle"}

    details = {
        "direction": direction,
        "candle_open":  c["open"],
        "candle_high":  c["high"],
        "candle_low":   c["low"],
        "candle_close": c["close"],
        "bb_upper": upper,
        "bb_middle": middle,
        "bb_lower":  lower,
        "atr": atr,
    }
    return direction, details


# ─── TRADE STATE ──────────────────────────────────────────────────────────────
class TradeState:
    """Thread-safe trade state and daily signal counter."""
    def __init__(self):
        self._lock         = threading.Lock()
        self.active_trade  = None       # dict or None
        self.signals_today = 0
        self.last_date     = None
        self.trade_log     = deque(maxlen=500)

    def reset_daily(self, today: str):
        with self._lock:
            if self.last_date != today:
                self.signals_today = 0
                self.last_date = today
                log.info(f"Daily signal counter reset for {today}")

    def can_take_signal(self, max_signals: int) -> bool:
        with self._lock:
            return self.active_trade is None and self.signals_today < max_signals

    def open_trade(self, trade: dict):
        with self._lock:
            self.active_trade = trade
            self.signals_today += 1
            self.trade_log.appendleft(trade)
            log.info(f"Trade opened: {trade}")

    def close_trade(self, result: str, pnl: float):
        with self._lock:
            if self.active_trade:
                self.active_trade["result"] = result
                self.active_trade["pnl"]    = pnl
                self.active_trade["closed_at"] = datetime.now(timezone.utc).isoformat()
                log.info(f"Trade closed: {result} | PnL: ${pnl:.2f}")
                self.active_trade = None

    def get_log(self):
        with self._lock:
            return list(self.trade_log)


# ─── MAIN BOT CLASS ───────────────────────────────────────────────────────────
class BBBot:
    def __init__(self, cfg: Config = None):
        self.cfg     = cfg or Config()
        self.filters = FilterEngine(self.cfg)
        self.state   = TradeState()
        self.client  = None
        self._running = False
        self._thread  = None
        self.symbol_info = {}

    # ── Connection ────────────────────────────────────────────────────────────
    def connect(self):
        log.info(f"Connecting to Binance {'TESTNET' if self.cfg.TESTNET else 'LIVE'}...")
        self.client = Client(
            self.cfg.API_KEY,
            self.cfg.API_SECRET,
            testnet=self.cfg.TESTNET
        )
        # Verify connection
        self.client.ping()
        info = self.client.futures_exchange_info()
        for sym in info["symbols"]:
            if sym["symbol"] == self.cfg.SYMBOL:
                for f in sym["filters"]:
                    if f["filterType"] == "LOT_SIZE":
                        self.symbol_info = {
                            "stepSize": f["stepSize"],
                            "minQty":   f["minQty"]
                        }
        # Set leverage
        self.client.futures_change_leverage(
            symbol=self.cfg.SYMBOL,
            leverage=self.cfg.LEVERAGE
        )
        log.info(f"Connected. Leverage set to {self.cfg.LEVERAGE}×. "
                 f"LOT_SIZE: {self.symbol_info}")

    # ── Data fetching ─────────────────────────────────────────────────────────
    def fetch_ohlcv(self, interval: str = None, limit: int = 100) -> pd.DataFrame:
        """Fetch OHLCV candles and compute indicators."""
        interval = interval or self.cfg.INTERVAL
        raw = self.client.futures_klines(
            symbol=self.cfg.SYMBOL,
            interval=interval,
            limit=limit
        )
        df = pd.DataFrame(raw, columns=[
            "ts","open","high","low","close","volume",
            "close_ts","quote_vol","trades","taker_base","taker_quote","ignore"
        ])
        for col in ["open","high","low","close","volume"]:
            df[col] = df[col].astype(float)
        df["ts"] = pd.to_datetime(df["ts"], unit="ms", utc=True)
        df.set_index("ts", inplace=True)

        # Indicators
        df["bb_upper"], df["bb_middle"], df["bb_lower"] = compute_bb(
            df["close"], self.cfg.BB_PERIOD, self.cfg.BB_STD_DEV
        )
        df["atr"] = compute_atr(df["high"], df["low"], df["close"], self.cfg.ATR_PERIOD)
        return df

    def fetch_daily_closes(self, limit: int = 30) -> pd.Series:
        """Fetch daily closes for the bias filter."""
        raw = self.client.futures_klines(
            symbol=self.cfg.SYMBOL,
            interval=Client.KLINE_INTERVAL_1DAY,
            limit=limit
        )
        closes = pd.Series([float(r[4]) for r in raw])
        return closes

    def get_balance(self) -> float:
        """Return USDT futures wallet balance."""
        balances = self.client.futures_account_balance()
        for b in balances:
            if b["asset"] == "USDT":
                return float(b["balance"])
        return 0.0

    # ── Order execution ───────────────────────────────────────────────────────
    def place_order(self, direction: str, qty: float,
                    entry: float, stop: float, take_profit: float) -> dict:
        """Place market entry + OCO stop/TP orders."""
        side        = "BUY"  if direction == "LONG"  else "SELL"
        close_side  = "SELL" if direction == "LONG"  else "BUY"
        stop_type   = "STOP_MARKET"
        tp_type     = "TAKE_PROFIT_MARKET"

        log.info(f"Placing {direction} order | qty={qty} | "
                 f"entry≈{entry:.0f} | SL={stop:.0f} | TP={take_profit:.0f}")

        # Market entry
        entry_order = self.client.futures_create_order(
            symbol=self.cfg.SYMBOL,
            side=side,
            type="MARKET",
            quantity=qty
        )

        # Stop loss
        sl_order = self.client.futures_create_order(
            symbol=self.cfg.SYMBOL,
            side=close_side,
            type=stop_type,
            stopPrice=round(stop, 1),
            closePosition=True,
            timeInForce="GTE_GTC"
        )

        # Take profit
        tp_order = self.client.futures_create_order(
            symbol=self.cfg.SYMBOL,
            side=close_side,
            type=tp_type,
            stopPrice=round(take_profit, 1),
            closePosition=True,
            timeInForce="GTE_GTC"
        )

        return {
            "entry_id": entry_order["orderId"],
            "sl_id":    sl_order["orderId"],
            "tp_id":    tp_order["orderId"],
        }

    # ── Signal evaluation loop ────────────────────────────────────────────────
    def evaluate(self):
        """Run one evaluation cycle. Called every minute by the scheduler."""
        now    = datetime.now(timezone.utc)
        today  = now.strftime("%Y-%m-%d")
        self.state.reset_daily(today)

        # Determine which signal slot we're in
        hour   = now.hour
        signal_num = None
        w1, w2 = self.cfg.SIGNAL_1_WINDOW, self.cfg.SIGNAL_2_WINDOW
        if w1[0] <= hour < w1[1]:
            signal_num = 1
        elif w2[0] <= hour < w2[1]:
            signal_num = 2

        if signal_num is None:
            return  # Outside signal windows

        if not self.state.can_take_signal(self.cfg.MAX_SIGNALS_PER_DAY):
            return  # Already at max signals or trade is open

        # Fetch data
        df_1h = self.fetch_ohlcv(limit=100)
        direction, details = detect_signal(df_1h, self.cfg)
        if direction is None:
            log.debug(f"No signal: {details.get('reason')}")
            return

        # Fetch daily closes for bias filter
        daily_closes = self.fetch_daily_closes()

        # Run all filters
        atr    = details["atr"]
        passed, reason = self.filters.run_all(
            signal_num   = signal_num,
            direction    = direction,
            open_        = details["candle_open"],
            high         = details["candle_high"],
            low          = details["candle_low"],
            close        = details["candle_close"],
            upper        = details["bb_upper"],
            lower        = details["bb_lower"],
            atr          = atr,
            daily_closes = daily_closes,
            utc_hour     = hour,
            utc_minute   = now.minute
        )

        if not passed:
            log.info(f"Signal {signal_num} {direction} FILTERED: {reason}")
            return

        # Calculate stops and targets
        entry = details["candle_close"]
        if direction == "LONG":
            stop         = entry - atr * self.cfg.ATR_MULTIPLIER
            take_profit  = entry + atr * self.cfg.ATR_MULTIPLIER * self.cfg.MIN_RR
        else:
            stop         = entry + atr * self.cfg.ATR_MULTIPLIER
            take_profit  = entry - atr * self.cfg.ATR_MULTIPLIER * self.cfg.MIN_RR

        # Position sizing
        balance  = self.get_balance()
        qty      = calc_position_size(balance, self.cfg.RISK_PCT,
                                      entry, stop, self.symbol_info)
        if qty <= 0:
            log.warning("Position size calculated as 0 — skipping trade")
            return

        risk_usd = balance * self.cfg.RISK_PCT
        log.info(f"✅ SIGNAL {signal_num} | {direction} | Entry≈${entry:.0f} | "
                 f"SL=${stop:.0f} | TP=${take_profit:.0f} | "
                 f"Qty={qty} BTC | Risk=${risk_usd:.2f}")

        # Execute
        try:
            order_ids = self.place_order(direction, qty, entry, stop, take_profit)
            self.state.open_trade({
                "id":          order_ids["entry_id"],
                "signal":      signal_num,
                "direction":   direction,
                "entry":       entry,
                "stop":        stop,
                "take_profit": take_profit,
                "qty":         qty,
                "risk_usd":    risk_usd,
                "balance_at_entry": balance,
                "opened_at":   now.isoformat(),
                "result":      "OPEN",
                "pnl":         0.0,
                **order_ids
            })
        except BinanceAPIException as e:
            log.error(f"Order failed: {e}")

    # ── Monitor open positions ────────────────────────────────────────────────
    def monitor_positions(self):
        """Check if active trade has been closed (SL/TP hit)."""
        trade = self.state.active_trade
        if not trade:
            return
        try:
            positions = self.client.futures_position_information(symbol=self.cfg.SYMBOL)
            for pos in positions:
                if pos["symbol"] == self.cfg.SYMBOL:
                    amt = float(pos["positionAmt"])
                    if abs(amt) < 0.0001:
                        # Position is closed
                        entry_price = float(pos.get("entryPrice", trade["entry"]))
                        mark_price  = float(pos.get("markPrice",  trade["entry"]))
                        direction   = trade["direction"]
                        qty         = trade["qty"]
                        if direction == "LONG":
                            pnl = (mark_price - entry_price) * qty
                        else:
                            pnl = (entry_price - mark_price) * qty
                        result = "WIN" if pnl > 0 else "LOSS"
                        self.state.close_trade(result, pnl)
        except BinanceAPIException as e:
            log.error(f"Position monitor error: {e}")

    # ── Main loop ─────────────────────────────────────────────────────────────
    def _run_loop(self):
        log.info("Bot loop started.")
        while self._running:
            try:
                self.evaluate()
                self.monitor_positions()
            except Exception as e:
                log.error(f"Loop error: {e}", exc_info=True)
            time.sleep(60)  # Check every minute
        log.info("Bot loop stopped.")

    def start(self):
        if self._running:
            log.warning("Bot already running.")
            return
        self.connect()
        self._running = True
        self._thread  = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        log.info("Bot started.")

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=10)
        log.info("Bot stopped.")

    def status(self) -> dict:
        now = datetime.now(timezone.utc)
        return {
            "running":       self._running,
            "timestamp":     now.isoformat(),
            "active_trade":  self.state.active_trade,
            "signals_today": self.state.signals_today,
            "trade_log":     self.state.get_log()[:20],
        }
