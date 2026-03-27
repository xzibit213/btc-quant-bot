
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
from dotenv import load_dotenv

from strategy_quant import compute_indicators, StrategyConfig

# Load environment variables
load_dotenv()

# --- LOGGING ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("bot_quant.log"),
        logging.StreamHandler()
    ]
)
log = logging.getLogger("QUANT_BOT")

# --- LIVE CONFIG ---
class LiveConfig(StrategyConfig):
    API_KEY     = os.getenv("BINANCE_API_KEY", "")
    API_SECRET  = os.getenv("BINANCE_API_SECRET", "")
    TESTNET     = os.getenv("TESTNET", "true").lower() == "true"
    EVAL_INTERVAL = 60
    CANDLE_LIMIT  = 500

class TradeState:
    def __init__(self):
        self._lock = threading.Lock()
        self.active_trade = None
        self.signals_today = 0
        self.last_date = None
        self.trade_log = deque(maxlen=500)
        self.starting_balance = 0.0

    def open_trade(self, trade):
        with self._lock:
            self.active_trade = trade
            self.signals_today += 1
            self.trade_log.appendleft(trade)
            log.info(f"Trade opened: {trade['direction']} | Margin=10% | Leverage=5x")

    def close_trade(self, result, pnl):
        with self._lock:
            if self.active_trade:
                self.active_trade["result"] = result
                self.active_trade["pnl"] = pnl
                self.active_trade["closed_at"] = datetime.now(timezone.utc).isoformat()
                log.info(f"Trade closed: {result} | PnL: ${pnl:.2f}")
                self.active_trade = None

class QuantBot:
    def __init__(self, cfg=None):
        self.cfg = cfg or LiveConfig()
        self.state = TradeState()
        self.client = None
        self._running = False
        self._thread = None
        self.symbol_info = {}
        self.last_signal = 0.0
        self.last_regime = True

    def connect(self):
        mode = "TESTNET" if self.cfg.TESTNET else "LIVE"
        log.info(f"Connecting to Binance {mode}...")
        self.client = Client(self.cfg.API_KEY, self.cfg.API_SECRET, testnet=self.cfg.TESTNET)
        
        # Sync with Binance Server Time (Fixes -1021 error)
        server_time = self.client.get_server_time()
        self.client.timestamp_offset = server_time['serverTime'] - int(time.time() * 1000)
        log.info(f"Synced with server. Offset: {self.client.timestamp_offset}ms")
        
        # Set to ISOLATED and 5x Leverage as requested
        try:
            self.client.futures_change_margin_type(symbol=self.cfg.SYMBOL, marginType="ISOLATED")
        except Exception as e:
            log.info(f"Margin type already ISOLATED or could not set: {e}")
            
        self.client.futures_change_leverage(symbol=self.cfg.SYMBOL, leverage=5)
        
        info = self.client.futures_exchange_info()
        for sym in info["symbols"]:
            if sym["symbol"] == self.cfg.SYMBOL:
                for f in sym["filters"]:
                    if f["filterType"] == "LOT_SIZE":
                        self.symbol_info = {"stepSize": f["stepSize"], "minQty": f["minQty"]}
        log.info(f"Connected. Mode=ISOLATED, Leverage=5x, Symbol={self.cfg.SYMBOL}")

    def get_balance(self):
        try:
            balances = self.client.futures_account_balance()
            for b in balances:
                if b["asset"] == "USDT":
                    return float(b["availableBalance"])
            return 0.0
        except Exception as e:
            log.error(f"Error fetching balance: {e}")
            return 0.0

    def cancel_open_orders(self):
        try:
            self.client.futures_cancel_all_open_orders(symbol=self.cfg.SYMBOL)
            log.info("Cancelled all open orders.")
        except Exception as e:
            log.warning(f"Failed to cancel orders: {e}")

    def place_order(self, direction, qty, entry, stop, tp):
        side = "BUY" if direction == "LONG" else "SELL"
        close_side = "SELL" if direction == "LONG" else "BUY"
        
        self.cancel_open_orders()
        
        log.info(f"Executing MARKET {side} for {qty} BTC...")
        entry_order = self.client.futures_create_order(symbol=self.cfg.SYMBOL, side=side, type="MARKET", quantity=qty)
        
        log.info(f"Placing SL @ ${stop:.1f} and TP @ ${tp:.1f}...")
        sl_order = self.client.futures_create_order(
            symbol=self.cfg.SYMBOL, side=close_side, type="STOP_MARKET", 
            stopPrice=round(stop, 1), closePosition=True, timeInForce="GTE_GTC"
        )
        tp_order = self.client.futures_create_order(
            symbol=self.cfg.SYMBOL, side=close_side, type="TAKE_PROFIT_MARKET", 
            stopPrice=round(tp, 1), closePosition=True, timeInForce="GTE_GTC"
        )
        return {"entry_id": entry_order["orderId"], "sl_id": sl_order["orderId"], "tp_id": tp_order["orderId"]}

    def evaluate(self):
        balance = self.get_balance()
        if balance <= 0: return

        raw = self.client.futures_klines(symbol=self.cfg.SYMBOL, interval=self.cfg.INTERVAL, limit=self.cfg.CANDLE_LIMIT)
        df = pd.DataFrame(raw, columns=["ts", "open", "high", "low", "close", "v", "cts", "qv", "t", "tb", "tq", "i"])
        for c in ["open", "high", "low", "close"]: df[c] = df[c].astype(float)
        df = compute_indicators(df, self.cfg)
        
        idx = -2
        signal = df['momentum_signal'].iloc[idx]
        regime_safe = df['regime_safe'].iloc[idx] == 1
        atr = df['atr'].iloc[idx]
        close = df['close'].iloc[idx]
        trend_sma = df['trend_sma'].iloc[idx]
        
        self.last_signal = signal
        self.last_regime = regime_safe

        direction = "LONG" if signal > 0.15 else ("SHORT" if signal < -0.15 else None)
        if not direction or not regime_safe: return
        
        if direction == "LONG" and close < trend_sma: return
        if direction == "SHORT" and close > trend_sma: return

        # OPTIMIZED POSITION SIZING: 10% Margin @ 5x Leverage
        # Margin = 0.1 * balance
        # Notional = Margin * 5
        pos_notional = (balance * 0.10) * 5
        qty = pos_notional / close
        
        step_size = float(self.symbol_info.get("stepSize", 0.001))
        qty = math.floor(qty / step_size) * step_size
        qty = round(qty, int(round(-math.log10(step_size))))

        # SL and TP logic
        stop_dist = atr * self.cfg.STOP_ATR_MULT
        stop = close - stop_dist if direction == "LONG" else close + stop_dist
        tp   = close + (atr * self.cfg.TP_ATR_MULT) if direction == "LONG" else close - (atr * self.cfg.TP_ATR_MULT)

        if qty > 0 and self.state.active_trade is None:
            ids = self.place_order(direction, qty, close, stop, tp)
            self.state.open_trade({
                "direction": direction, "entry": close, "stop": stop, "tp": tp, "qty": qty, "result": "OPEN", **ids
            })

    def run_manual_trade(self, direction):
        self.connect()
        balance = self.get_balance()
        log.info(f"Manual Test: {direction} | Balance: ${balance:.2f}")
        
        raw = self.client.futures_klines(symbol=self.cfg.SYMBOL, interval=self.cfg.INTERVAL, limit=100)
        close = float(raw[-1][4])
        
        # 10% Margin rule
        qty = (balance * 0.10 * 5) / close
        step_size = float(self.symbol_info.get("stepSize", 0.001))
        qty = math.floor(qty / step_size) * step_size
        qty = round(qty, int(round(-math.log10(step_size))))
        
        # Generic stops for test
        stop = close * 0.98 if direction == "LONG" else close * 1.02
        tp   = close * 1.05 if direction == "LONG" else close * 0.95
        
        self.place_order(direction, qty, close, stop, tp)

    def monitor_positions(self):
        trade = self.state.active_trade
        if not trade: return
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
        except Exception as e:
            log.error(f"Position monitor error: {e}")

    def start(self):
        self.connect()
        self._running = True
        def loop():
            while self._running:
                try: 
                    self.evaluate()
                    self.monitor_positions()
                except Exception as e: log.error(f"Error: {e}")
                time.sleep(60)
        threading.Thread(target=loop, daemon=True).start()

    def status(self):
        return {"running": self._running, "active": self.state.active_trade, "log": list(self.state.trade_log)}
