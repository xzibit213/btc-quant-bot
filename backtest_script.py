import os
import pandas as pd
import numpy as np
from datetime import datetime, timezone
from binance.client import Client

def fetch_data(symbol="BTCUSDT", interval="1h", start_str="1 Mar 2025"):
    print(f"Fetching {interval} data for {symbol} starting from {start_str}...")
    client = Client(None, None)
    start_ts = int(datetime.strptime(start_str, "%d %b %Y").timestamp() * 1000)
    
    all_klines = []
    current_start = start_ts
    
    while True:
        klines = client.futures_klines(
            symbol=symbol,
            interval=interval,
            startTime=current_start,
            limit=1000
        )
        if not klines:
            break
        all_klines.extend(klines)
        current_start = klines[-1][0] + 1
        
        last_ts = klines[-1][0]
        if (datetime.now().timestamp() * 1000) - last_ts < 2 * 3600 * 1000:
            break
        if len(klines) < 1000:
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
        
    return df

def compute_indicators(df):
    df = df.copy()
    
    # EMAs
    df['ema_20'] = df['close'].ewm(span=50, adjust=False).mean()
    df['ema_50'] = df['close'].ewm(span=200, adjust=False).mean()
    
    return df

def run_backtest(df, interval_name="1H"):
    INITIAL_BALANCE = 10000.0
    balance = INITIAL_BALANCE
    
    trades = []
    active_trade = None
    
    backtest_start = datetime(2025, 4, 1)
    if df.index.tz is not None:
        backtest_start = datetime(2025, 4, 1, tzinfo=timezone.utc)
        
    times = df.index
    opens = df['open'].values
    closes = df['close'].values
    ema_20 = df['ema_20'].values
    ema_50 = df['ema_50'].values
    
    df_len = len(df)
    
    for i in range(50, df_len):
        ts = times[i]
        if ts < backtest_start:
            continue
            
        c_open = opens[i]
        
        # Cross logic from previous candle
        prev_ema20 = ema_20[i-1]
        prev_ema50 = ema_50[i-1]
        pprev_ema20 = ema_20[i-2]
        pprev_ema50 = ema_50[i-2]
        
        cross_up = pprev_ema20 <= pprev_ema50 and prev_ema20 > prev_ema50
        cross_dn = pprev_ema20 >= pprev_ema50 and prev_ema20 < prev_ema50
        
        # Exit current trade on opposite cross
        if active_trade:
            direction = active_trade['direction']
            entry = active_trade['entry']
            qty = active_trade['qty']
            
            close_trade = False
            if direction == 'LONG' and cross_dn:
                close_trade = True
            elif direction == 'SHORT' and cross_up:
                close_trade = True
                
            if close_trade:
                exit_price = c_open
                pnl = (exit_price - entry) * qty if direction == 'LONG' else (entry - exit_price) * qty
                fee = (entry * qty * 0.0004) + (exit_price * qty * 0.0004)
                pnl -= fee
                balance += pnl
                trades.append({
                    'entry_time': active_trade['time'],
                    'exit_time': ts,
                    'direction': direction,
                    'pnl': pnl,
                    'balance': balance,
                    'result': 'WIN' if pnl > 0 else 'LOSS',
                    'exit_type': 'CROSS'
                })
                active_trade = None
                
        # Enter new trade
        if not active_trade:
            if cross_up:
                entry_price = c_open
                # Use 99% of balance to compound
                trade_size = balance * 0.99
                qty = trade_size / entry_price
                active_trade = {
                    'time': ts, 'direction': 'LONG', 'entry': entry_price, 'qty': qty
                }
            elif cross_dn:
                entry_price = c_open
                trade_size = balance * 0.99
                qty = trade_size / entry_price
                active_trade = {
                    'time': ts, 'direction': 'SHORT', 'entry': entry_price, 'qty': qty
                }

    # Close any open trade at the end to reflect final balance
    if active_trade:
        direction = active_trade['direction']
        entry = active_trade['entry']
        qty = active_trade['qty']
        exit_price = closes[-1]
        pnl = (exit_price - entry) * qty if direction == 'LONG' else (entry - exit_price) * qty
        fee = (entry * qty * 0.0004) + (exit_price * qty * 0.0004)
        pnl -= fee
        balance += pnl
        trades.append({
            'entry_time': active_trade['time'],
            'exit_time': times[-1],
            'direction': direction,
            'pnl': pnl,
            'balance': balance,
            'result': 'WIN' if pnl > 0 else 'LOSS',
            'exit_type': 'EOT'
        })

    return trades, INITIAL_BALANCE

def summarize_monthly(trades, initial_balance):
    if not trades:
        return pd.DataFrame()
        
    df = pd.DataFrame(trades)
    df['entry_time'] = pd.to_datetime(df['entry_time'])
    df['month'] = df['entry_time'].dt.strftime('%Y-%m')
    
    current_bal = initial_balance
    monthly_stats = []
    
    all_months = pd.date_range(start=datetime(2025, 4, 1), end=datetime(2026, 3, 21), freq='MS').strftime('%Y-%m').tolist()
    
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
            'Balance ($)': f"{current_bal:,.2f}"
        })
        
    return pd.DataFrame(monthly_stats)

def run_all():
    print("==================================================")
    print("STARTING BACKTEST FOR 50/200 EMA CROSSOVER (1H)")
    print("==================================================")
    try:
        df = fetch_data(interval="1h", start_str="1 Mar 2025")
        df = compute_indicators(df)
        
        trades, start_bal = run_backtest(df, interval_name="1H")
        summary = summarize_monthly(trades, start_bal)
        
        if not summary.empty:
            print("\n=== 1H MONTHLY BREAKDOWN ===")
            print(summary.to_string(index=False))
        else:
            print("\nNo trades taken.")
            
        if trades:
            total_pnl = sum(t['pnl'] for t in trades)
            final_bal = start_bal + total_pnl
            win_rate = len([t for t in trades if t['result'] == 'WIN']) / len(trades) * 100
            print(f"\nSTRATEGY SUMMARY:")
            print(f"Total Trades: {len(trades)}")
            print(f"Total PnL: ${total_pnl:,.2f}")
            print(f"Final Balance: ${final_bal:,.2f}")
            print(f"Win Rate: {win_rate:.2f}%")
            print(f"Total ROI: {((total_pnl / start_bal) * 100):.2f}%")
            
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    run_all()
