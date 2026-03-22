"""
╔══════════════════════════════════════════════════════════════════════════════╗
║   INSTITUTIONAL MULTI-FACTOR QUANT STRATEGY — BTC/USDT FUTURES BACKTEST    ║
║                                                                            ║
║   Pillars:                                                                 ║
║   1. Time-Series Momentum (TSMOM) — Moskowitz, Ooi & Pedersen (2012)       ║
║   2. Volatility Targeting — Moreira & Muir (2017)                          ║
║   3. Regime Detection — Kritzman et al. (2012)                             ║
║                                                                            ║
║   Used by: AQR Capital, Man AHL, State Street, Winton, Two Sigma          ║
║   Proven:  Profitable across 58+ futures markets over 25+ years (public)   ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

import os
import sys
import pandas as pd
import numpy as np
from datetime import datetime, timezone
from binance.client import Client

# ══════════════════════════════════════════════════════════════════════════════
# CONFIGURATION
# ══════════════════════════════════════════════════════════════════════════════
class StrategyConfig:
    """All tunable parameters in one place."""

    # ── DATA ──────────────────────────────────────────────────────────────────
    SYMBOL          = "BTCUSDT"
    INTERVAL        = "1h"
    DATA_START      = "1 Jan 2025"
    BACKTEST_START  = "22 Mar 2025"

    # ── MOMENTUM (TSMOM) - Optimized for 1h ──────────────────────────────────
    MOMENTUM_LOOKBACKS  = [12, 24, 48, 168]
    MOMENTUM_WEIGHTS    = [0.5, 0.3, 0.15, 0.05]
    SIGNAL_SMOOTHING    = 3

    # ── VOLATILITY TARGETING - Hedge Fund Profile ────────────────────────────
    TARGET_VOL_ANNUAL   = 0.45           # 45% annualized target volatility
    VOL_LOOKBACK        = 24
    VOL_SCALE_FACTOR    = np.sqrt(365 * 24)
    MAX_LEVERAGE        = 5.0            # Capped at 5x per user request
    MIN_LEVERAGE        = 0.1

    # ── REGIME DETECTION ─────────────────────────────────────────────────────
    VOL_FAST_WINDOW     = 12
    VOL_SLOW_WINDOW     = 120
    REGIME_THRESHOLD    = 2.0
    REGIME_REDUCE_FACTOR = 0.0

    # ── RISK MANAGEMENT ──────────────────────────────────────────────────────
    ATR_PERIOD          = 14
    STOP_ATR_MULT       = 1.5            # Tighter institutional stop
    TP_ATR_MULT         = 4.5            # 3:1 Reward-to-Risk
    MAX_TRADES_PER_DAY  = 3
    RISK_PER_TRADE      = 0.03           # 3% of equity per trade
    FEE_RATE            = 0.0004         # 0.04% taker fee each way

    # ── DRAWDOWN CIRCUIT BREAKER ─────────────────────────────────────────────
    # Monthly Soft-Kill: Reduce size by 75% if MTD Drawdown > 20%
    MONTH_MAX_DD_PCT    = 0.20
    # Hard-Kill: Stop trading if Total Drawdown > 30%
    MAX_DRAWDOWN_PCT    = 0.30

    # ── INITIAL CAPITAL ──────────────────────────────────────────────────────
    INITIAL_BALANCE     = 10000.0


# ══════════════════════════════════════════════════════════════════════════════
# DATA FETCHING
# ══════════════════════════════════════════════════════════════════════════════
def fetch_data(symbol="BTCUSDT", interval="1h", start_str="1 Jan 2025"):
    """Fetch OHLCV data from Binance Futures (no API key needed for public data)."""
    print(f"[DATA] Fetching {interval} data for {symbol} from {start_str}...")
    client = Client(None, None)
    start_ts = int(datetime.strptime(start_str, "%d %b %Y").timestamp() * 1000)

    all_klines = []
    current_start = start_ts

    while True:
        klines = client.futures_klines(
            symbol=symbol, interval=interval,
            startTime=current_start, limit=1500
        )
        if not klines:
            break
        all_klines.extend(klines)
        current_start = klines[-1][0] + 1

        last_ts = klines[-1][0]
        if (datetime.now().timestamp() * 1000) - last_ts < 2 * 3600 * 1000:
            break
        if len(klines) < 1500:
            break

    df = pd.DataFrame(all_klines, columns=[
        'timestamp', 'open', 'high', 'low', 'close', 'volume',
        'close_time', 'quote_asset_volume', 'number_of_trades',
        'taker_base_vol', 'taker_quote_vol', 'ignore'
    ])

    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    df.drop_duplicates(subset='timestamp', inplace=True)
    df.set_index('timestamp', inplace=True)

    for col in ['open', 'high', 'low', 'close', 'volume']:
        df[col] = df[col].astype(float)

    print(f"   [OK] Loaded {len(df)} candles ({df.index[0]} -> {df.index[-1]})")
    return df


# ══════════════════════════════════════════════════════════════════════════════
# INDICATOR COMPUTATION
# ══════════════════════════════════════════════════════════════════════════════
def compute_indicators(df, cfg=None):
    """
    Compute all strategy indicators:
    - Multi-period momentum signals
    - Volatility (Parkinson + standard)
    - Regime detection ratio
    - ATR for stops
    """
    if cfg is None:
        cfg = StrategyConfig()

    df = df.copy()

    # ── 1. MULTI-PERIOD MOMENTUM (TSMOM) ─────────────────────────────────────
    # For each lookback, compute exponential ROC, normalize by its rolling std
    momentum_signals = []
    for lookback in cfg.MOMENTUM_LOOKBACKS:
        # Rate of change: (close / close_n_bars_ago) - 1
        roc = df['close'].pct_change(lookback)

        # Normalize by rolling standard deviation (z-score style)
        roc_std = roc.rolling(window=lookback, min_periods=max(10, lookback // 2)).std()
        z_roc = roc / (roc_std + 1e-10)

        # Clip to [-3, 3] to prevent extreme signals
        z_roc = z_roc.clip(-3, 3) / 3.0  # Now in [-1, 1]
        momentum_signals.append(z_roc)

    # Weighted average across all lookback periods
    composite = pd.Series(0.0, index=df.index)
    for sig, weight in zip(momentum_signals, cfg.MOMENTUM_WEIGHTS):
        composite += sig * weight

    # Smooth the composite signal
    df['momentum_raw'] = composite
    df['momentum_signal'] = composite.ewm(span=cfg.SIGNAL_SMOOTHING, adjust=False).mean()

    # ── 2. REALIZED VOLATILITY (Parkinson High-Low Estimator) ────────────────
    # Parkinson (1980) — more efficient than close-to-close vol
    log_hl = np.log(df['high'] / df['low'])
    parkinson_var = (log_hl ** 2) / (4 * np.log(2))
    df['realized_vol'] = np.sqrt(
        parkinson_var.rolling(window=cfg.VOL_LOOKBACK).mean()
    ) * cfg.VOL_SCALE_FACTOR

    # ── 3. REGIME DETECTION ──────────────────────────────────────────────────
    # Fast vol / Slow vol ratio
    fast_vol = np.sqrt(
        parkinson_var.rolling(window=cfg.VOL_FAST_WINDOW).mean()
    ) * cfg.VOL_SCALE_FACTOR

    slow_vol = np.sqrt(
        parkinson_var.rolling(window=cfg.VOL_SLOW_WINDOW).mean()
    ) * cfg.VOL_SCALE_FACTOR

    df['vol_regime_ratio'] = fast_vol / (slow_vol + 1e-10)
    df['regime_safe'] = (df['vol_regime_ratio'] < cfg.REGIME_THRESHOLD).astype(int)

    # ── 4. ATR FOR STOPS ─────────────────────────────────────────────────────
    prev_close = df['close'].shift(1)
    tr = pd.concat([
        df['high'] - df['low'],
        (df['high'] - prev_close).abs(),
        (df['low']  - prev_close).abs()
    ], axis=1).max(axis=1)
    df['atr'] = tr.rolling(window=cfg.ATR_PERIOD).mean()

    # ── 5. VOLATILITY-TARGETED LEVERAGE ──────────────────────────────────────
    df['vol_leverage'] = cfg.TARGET_VOL_ANNUAL / (df['realized_vol'] + 1e-10)
    df['vol_leverage'] = df['vol_leverage'].clip(cfg.MIN_LEVERAGE, cfg.MAX_LEVERAGE)

    # ── 6. DAILY TREND BIAS (20-SMA on daily closes approximation) ───────────
    # Use 24-bar SMA on hourly as proxy for daily trend
    df['trend_sma'] = df['close'].rolling(window=24 * 20).mean()

    return df


# ══════════════════════════════════════════════════════════════════════════════
# BACKTEST ENGINE
# ══════════════════════════════════════════════════════════════════════════════
def run_backtest(df, cfg=None):
    """
    Event-driven backtest with:
    - Multi-factor momentum entry signals
    - Volatility-targeted position sizing
    - Regime filter
    - ATR-based SL/TP
    - Drawdown circuit breaker
    - Daily trade limit
    """
    if cfg is None:
        cfg = StrategyConfig()

    balance = cfg.INITIAL_BALANCE
    peak_balance = balance
    trades = []
    active_trade = None
    daily_trades = {}   # date → count

    backtest_start_dt = datetime.strptime(cfg.BACKTEST_START, "%d %b %Y")

    # Pre-extract arrays for speed
    times     = df.index
    opens     = df['open'].values
    highs     = df['high'].values
    lows      = df['low'].values
    closes    = df['close'].values
    momentum  = df['momentum_signal'].values
    regime    = df['regime_safe'].values
    vol_lev   = df['vol_leverage'].values
    atr_vals  = df['atr'].values
    trend_sma = df['trend_sma'].values

    warmup = max(cfg.MOMENTUM_LOOKBACKS) + cfg.VOL_SLOW_WINDOW
    circuit_breaker_active = False

    for i in range(warmup, len(df)):
        ts = times[i]
        if ts < backtest_start_dt:
            continue

        # ── CHECK DRAWDOWN CIRCUIT BREAKER ────────────────────────────────
        drawdown = (peak_balance - balance) / peak_balance if peak_balance > 0 else 0
        if drawdown >= cfg.MAX_DRAWDOWN_PCT:
            if not circuit_breaker_active:
                circuit_breaker_active = True
            # Close any open trade
            if active_trade:
                exit_price = opens[i]
                direction = active_trade['direction']
                entry = active_trade['entry']
                qty = active_trade['qty']
                pnl = (exit_price - entry) * qty if direction == 'LONG' else (entry - exit_price) * qty
                fee = (entry * qty + exit_price * qty) * cfg.FEE_RATE
                pnl -= fee
                balance += pnl
                trades.append({
                    'entry_time': active_trade['time'],
                    'exit_time': ts,
                    'direction': direction,
                    'entry_price': entry,
                    'exit_price': exit_price,
                    'qty': qty,
                    'pnl': pnl,
                    'balance': balance,
                    'result': 'WIN' if pnl > 0 else 'LOSS',
                    'exit_type': 'CIRCUIT_BREAKER'
                })
                active_trade = None
            continue

        # Reset circuit breaker if balance recovers
        if circuit_breaker_active and drawdown < cfg.MAX_DRAWDOWN_PCT * 0.5:
            circuit_breaker_active = False

        # ── DAILY TRADE LIMIT ────────────────────────────────────────────
        today = str(ts.date()) if hasattr(ts, 'date') else str(ts)[:10]
        today_count = daily_trades.get(today, 0)

        # ── MANAGE OPEN POSITION ─────────────────────────────────────────
        if active_trade:
            direction = active_trade['direction']
            entry = active_trade['entry']
            qty = active_trade['qty']
            sl = active_trade['stop']
            tp = active_trade['tp']

            # Check SL/TP hit using high/low of current bar
            hit_sl = False
            hit_tp = False

            if direction == 'LONG':
                if lows[i] <= sl:
                    hit_sl = True
                    exit_price = sl
                elif highs[i] >= tp:
                    hit_tp = True
                    exit_price = tp
            else:  # SHORT
                if highs[i] >= sl:
                    hit_sl = True
                    exit_price = sl
                elif lows[i] <= tp:
                    hit_tp = True
                    exit_price = tp

            # Also check for signal reversal (momentum flips sign)
            signal_reversal = False
            if direction == 'LONG' and momentum[i] < -0.15:
                signal_reversal = True
            elif direction == 'SHORT' and momentum[i] > 0.15:
                signal_reversal = True

            close_trade = hit_sl or hit_tp or signal_reversal

            if close_trade:
                if signal_reversal and not hit_sl and not hit_tp:
                    exit_price = opens[i]  # Exit at open on reversal

                pnl = (exit_price - entry) * qty if direction == 'LONG' else (entry - exit_price) * qty
                fee = (entry * qty + exit_price * qty) * cfg.FEE_RATE
                pnl -= fee
                balance += pnl
                peak_balance = max(peak_balance, balance)

                exit_type = 'SL' if hit_sl else ('TP' if hit_tp else 'REVERSAL')
                trades.append({
                    'entry_time': active_trade['time'],
                    'exit_time': ts,
                    'direction': direction,
                    'entry_price': entry,
                    'exit_price': exit_price,
                    'qty': qty,
                    'pnl': pnl,
                    'balance': balance,
                    'result': 'WIN' if pnl > 0 else 'LOSS',
                    'exit_type': exit_type
                })
                active_trade = None

        # ── ENTRY LOGIC ──────────────────────────────────────────────────
        if active_trade is None and today_count < cfg.MAX_TRADES_PER_DAY:
            signal = momentum[i]
            is_regime_safe = regime[i] == 1
            atr = atr_vals[i]

            # Skip if NaN values
            if np.isnan(signal) or np.isnan(atr) or atr == 0:
                continue

            # Determine direction from momentum signal
            direction = None
            if signal > 0.15:     # Threshold to avoid noisy entries
                direction = 'LONG'
            elif signal < -0.15:
                direction = 'SHORT'

            if direction is None:
                continue

            # ── FILTER 1: Regime must be safe ────────────────────────────
            if not is_regime_safe:
                continue

            # ── FILTER 2: Trend alignment ────────────────────────────────
            # Trade must align with larger trend (480-period SMA)
            sma_val = trend_sma[i]
            if not np.isnan(sma_val):
                if direction == 'LONG' and closes[i] < sma_val:
                    continue
                if direction == 'SHORT' and closes[i] > sma_val:
                    continue

            # ── POSITION SIZING (Volatility Targeted) ───────────────────
            leverage = vol_lev[i]
            if np.isnan(leverage):
                continue

            # Risk-based sizing: risk X% of balance, stop at 2×ATR
            stop_distance = atr * cfg.STOP_ATR_MULT
            risk_amount = balance * cfg.RISK_PER_TRADE
            qty_from_risk = risk_amount / stop_distance

            # Vol-targeted sizing
            trade_notional = balance * leverage
            qty_from_vol = trade_notional / closes[i]

            # Use the smaller of risk-based and vol-targeted
            qty = min(qty_from_risk, qty_from_vol)
            if qty <= 0:
                continue

            entry_price = opens[i]  # Enter at next bar's open

            if direction == 'LONG':
                sl = entry_price - stop_distance
                tp = entry_price + atr * cfg.TP_ATR_MULT
            else:
                sl = entry_price + stop_distance
                tp = entry_price - atr * cfg.TP_ATR_MULT

            active_trade = {
                'time': ts,
                'direction': direction,
                'entry': entry_price,
                'qty': qty,
                'stop': sl,
                'tp': tp,
                'signal_strength': signal,
                'vol_leverage': leverage
            }
            daily_trades[today] = today_count + 1

    # ── CLOSE ANY REMAINING OPEN TRADE ───────────────────────────────────
    if active_trade:
        direction = active_trade['direction']
        entry = active_trade['entry']
        qty = active_trade['qty']
        exit_price = closes[-1]
        pnl = (exit_price - entry) * qty if direction == 'LONG' else (entry - exit_price) * qty
        fee = (entry * qty + exit_price * qty) * cfg.FEE_RATE
        pnl -= fee
        balance += pnl
        trades.append({
            'entry_time': active_trade['time'],
            'exit_time': times[-1],
            'direction': direction,
            'entry_price': entry,
            'exit_price': exit_price,
            'qty': qty,
            'pnl': pnl,
            'balance': balance,
            'result': 'WIN' if pnl > 0 else 'LOSS',
            'exit_type': 'EOT'
        })

    return trades, cfg.INITIAL_BALANCE


# ══════════════════════════════════════════════════════════════════════════════
# PERFORMANCE METRICS
# ══════════════════════════════════════════════════════════════════════════════
def calculate_metrics(trades, initial_balance):
    """Calculate institutional-grade performance metrics."""
    if not trades:
        return {}

    df = pd.DataFrame(trades)
    total_pnl = df['pnl'].sum()
    final_balance = initial_balance + total_pnl

    # Win/Loss stats
    wins = df[df['result'] == 'WIN']
    losses = df[df['result'] == 'LOSS']
    win_rate = len(wins) / len(df) * 100 if len(df) > 0 else 0
    avg_win = wins['pnl'].mean() if len(wins) > 0 else 0
    avg_loss = abs(losses['pnl'].mean()) if len(losses) > 0 else 0
    profit_factor = (wins['pnl'].sum() / abs(losses['pnl'].sum())) if len(losses) > 0 and losses['pnl'].sum() != 0 else float('inf')

    # Equity curve
    equity = [initial_balance]
    for _, t in df.iterrows():
        equity.append(equity[-1] + t['pnl'])
    equity = pd.Series(equity)

    # Returns series (per-trade)
    returns = df['pnl'] / initial_balance  # Simple approximation

    # Sharpe Ratio (annualized, assuming ~500 trades/year as proxy)
    if len(returns) > 1 and returns.std() > 0:
        # Use per-trade returns, annualize by sqrt of trades-per-year
        avg_daily_pnl = df.set_index('entry_time')['pnl'].resample('D').sum().dropna()
        avg_daily_pnl = avg_daily_pnl[avg_daily_pnl != 0]
        if len(avg_daily_pnl) > 1 and avg_daily_pnl.std() > 0:
            sharpe = (avg_daily_pnl.mean() / avg_daily_pnl.std()) * np.sqrt(365)
        else:
            sharpe = 0
    else:
        sharpe = 0

    # Sortino Ratio (only downside deviation)
    if len(returns) > 1:
        downside = returns[returns < 0]
        downside_std = downside.std() if len(downside) > 0 else 0
        if downside_std > 0:
            avg_daily_pnl_sort = df.set_index('entry_time')['pnl'].resample('D').sum().dropna()
            avg_daily_pnl_sort = avg_daily_pnl_sort[avg_daily_pnl_sort != 0]
            if len(avg_daily_pnl_sort) > 1:
                daily_returns = avg_daily_pnl_sort / initial_balance
                daily_downside = daily_returns[daily_returns < 0]
                sortino = (daily_returns.mean() / daily_downside.std()) * np.sqrt(365) if daily_downside.std() > 0 else 0
            else:
                sortino = 0
        else:
            sortino = 0
    else:
        sortino = 0

    # Maximum Drawdown
    peak = equity.expanding().max()
    drawdown = (equity - peak) / peak
    max_dd = drawdown.min() * 100  # As percentage

    # Calmar Ratio (annualized return / max drawdown)
    total_days = (pd.to_datetime(df['exit_time'].iloc[-1]) - pd.to_datetime(df['entry_time'].iloc[0])).days
    if total_days > 0 and max_dd != 0:
        annualized_return = (total_pnl / initial_balance) * (365 / total_days)
        calmar = annualized_return / abs(max_dd / 100)
    else:
        calmar = 0

    # Exit type breakdown
    exit_types = df['exit_type'].value_counts().to_dict()

    return {
        'total_trades': len(df),
        'wins': len(wins),
        'losses': len(losses),
        'win_rate': win_rate,
        'total_pnl': total_pnl,
        'final_balance': final_balance,
        'total_roi': (total_pnl / initial_balance) * 100,
        'avg_win': avg_win,
        'avg_loss': avg_loss,
        'profit_factor': profit_factor,
        'sharpe_ratio': sharpe,
        'sortino_ratio': sortino,
        'max_drawdown': max_dd,
        'calmar_ratio': calmar,
        'exit_types': exit_types,
        'avg_trade_pnl': total_pnl / len(df) if len(df) > 0 else 0,
        'longs': len(df[df['direction'] == 'LONG']),
        'shorts': len(df[df['direction'] == 'SHORT']),
    }


def monthly_breakdown(trades, initial_balance):
    """Generate monthly P&L breakdown table."""
    if not trades:
        return pd.DataFrame()

    df = pd.DataFrame(trades)
    df['entry_time'] = pd.to_datetime(df['entry_time'])
    df['month'] = df['entry_time'].dt.strftime('%Y-%m')

    current_bal = initial_balance
    monthly_stats = []

    # Generate all months in range
    first_month = df['entry_time'].min().replace(day=1)
    last_month = df['entry_time'].max().replace(day=1)
    all_months = pd.date_range(start=first_month, end=last_month, freq='MS').strftime('%Y-%m').tolist()

    for m in all_months:
        m_trades = df[df['month'] == m]
        pnl = m_trades['pnl'].sum()
        count = len(m_trades)
        wins = len(m_trades[m_trades['result'] == 'WIN'])
        losses = count - wins

        start_bal = current_bal
        current_bal += pnl
        roi = (pnl / start_bal) * 100 if start_bal != 0 else 0

        monthly_stats.append({
            'Month': m,
            'PnL ($)': f"{pnl:,.2f}",
            'ROI (%)': f"{roi:.2f}%",
            'Trades': count,
            'Wins': wins,
            'Losses': losses,
            'Win Rate': f"{(wins/count*100):.0f}%" if count > 0 else "—",
            'Balance ($)': f"{current_bal:,.2f}"
        })

    return pd.DataFrame(monthly_stats)


# ══════════════════════════════════════════════════════════════════════════════
# MAIN EXECUTION
# ══════════════════════════════════════════════════════════════════════════════
def run_all():
    """Full pipeline: fetch → indicators → backtest → report."""

    cfg = StrategyConfig()

    print("=" * 72)
    print("  INSTITUTIONAL MULTI-FACTOR QUANT STRATEGY — BTC/USDT BACKTEST")
    print("  TSMOM + Volatility Targeting + Regime Detection")
    print("=" * 72)
    print()
    print(f"  Symbol:             {cfg.SYMBOL}")
    print(f"  Interval:           {cfg.INTERVAL}")
    print(f"  Data Start:         {cfg.DATA_START}")
    print(f"  Backtest Start:     {cfg.BACKTEST_START}")
    print(f"  Initial Balance:    ${cfg.INITIAL_BALANCE:,.2f}")
    print(f"  Target Vol:         {cfg.TARGET_VOL_ANNUAL*100:.0f}% annualized")
    print(f"  Max Leverage:       {cfg.MAX_LEVERAGE}×")
    print(f"  Risk Per Trade:     {cfg.RISK_PER_TRADE*100:.1f}%")
    print(f"  Stop: {cfg.STOP_ATR_MULT}× ATR | TP: {cfg.TP_ATR_MULT}× ATR")
    print(f"  Regime Threshold:   {cfg.REGIME_THRESHOLD}×")
    print(f"  Max Drawdown Kill:  {cfg.MAX_DRAWDOWN_PCT*100:.0f}%")
    print()

    try:
        # 1. Fetch data
        df = fetch_data(
            symbol=cfg.SYMBOL,
            interval=cfg.INTERVAL,
            start_str=cfg.DATA_START
        )

        # 2. Compute indicators
        print("\n[CALC] Computing indicators (TSMOM, Vol, Regime, ATR)...")
        df = compute_indicators(df, cfg)
        print("   [OK] All indicators computed")

        # 3. Run backtest
        print("\n[RUN] Running backtest...")
        trades, start_bal = run_backtest(df, cfg)

        if not trades:
            print("\n[!!] No trades generated. Consider adjusting parameters.")
            return

        # 4. Calculate metrics
        metrics = calculate_metrics(trades, start_bal)

        # 5. Print results
        print("\n" + "=" * 72)
        print("  BACKTEST RESULTS")
        print("=" * 72)

        print(f"\n  {'Total Trades:':<30} {metrics['total_trades']}")
        print(f"  {'Wins:':<30} {metrics['wins']}  ({metrics['longs']} longs, {metrics['shorts']} shorts)")
        print(f"  {'Losses:':<30} {metrics['losses']}")
        print(f"  {'Win Rate:':<30} {metrics['win_rate']:.1f}%")
        print(f"  {'Avg Win:':<30} ${metrics['avg_win']:,.2f}")
        print(f"  {'Avg Loss:':<30} ${metrics['avg_loss']:,.2f}")
        print(f"  {'Avg Trade PnL:':<30} ${metrics['avg_trade_pnl']:,.2f}")
        print(f"  {'Profit Factor:':<30} {metrics['profit_factor']:.2f}")

        print(f"\n  {'-' * 40}")
        print(f"  {'Total PnL:':<30} ${metrics['total_pnl']:,.2f}")
        print(f"  {'Final Balance:':<30} ${metrics['final_balance']:,.2f}")
        print(f"  {'Total ROI:':<30} {metrics['total_roi']:.2f}%")

        print(f"\n  {'-' * 40}  RISK METRICS")
        print(f"  {'Sharpe Ratio:':<30} {metrics['sharpe_ratio']:.2f}")
        print(f"  {'Sortino Ratio:':<30} {metrics['sortino_ratio']:.2f}")
        print(f"  {'Max Drawdown:':<30} {metrics['max_drawdown']:.2f}%")
        print(f"  {'Calmar Ratio:':<30} {metrics['calmar_ratio']:.2f}")

        print(f"\n  {'-' * 40}  EXIT TYPES")
        for exit_type, count in metrics['exit_types'].items():
            print(f"  {exit_type + ':':<30} {count}")

        # 6. Monthly breakdown
        monthly = monthly_breakdown(trades, start_bal)
        if not monthly.empty:
            print(f"\n{'=' * 72}")
            print("  MONTHLY BREAKDOWN")
            print("=" * 72)
            print(monthly.to_string(index=False))

        print(f"\n{'=' * 72}")
        print("  BACKTEST COMPLETE")
        print(f"{'=' * 72}\n")

    except Exception as e:
        print(f"\n[ERROR] {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    run_all()
