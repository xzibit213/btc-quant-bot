import pandas as pd
from datetime import datetime, timedelta
from strategy_quant import StrategyConfig, fetch_data, compute_indicators, monthly_breakdown, calculate_metrics
from backtest_1y_5x import QuantumHedgeFundConfig, run_backtest_hedgefund

class Last10DaysConfig(QuantumHedgeFundConfig):
    pass

def main():
    cfg = Last10DaysConfig()
    
    # Calculate exact dates
    now = datetime.now()
    backtest_start_dt = now - timedelta(days=10)
    data_start_dt = backtest_start_dt - timedelta(days=15) # 15 days padding for warmup
    
    cfg.DATA_START = data_start_dt.strftime("%d %b %Y")
    cfg.BACKTEST_START = backtest_start_dt.strftime("%d %b %Y")
    
    df = fetch_data(cfg.SYMBOL, cfg.INTERVAL, cfg.DATA_START)
    df = compute_indicators(df, cfg)
    
    print(f"\n[OK] DATA LOADED: {len(df)} candles")
    print(f"[RUN] RUNNING 10-DAY BACKTEST FOR: {cfg.BACKTEST_START} TO CURRENT")
    
    trades, start_bal = run_backtest_hedgefund(df, cfg)
    
    if trades:
        metrics = calculate_metrics(trades, start_bal)
        
        print("\n" + "="*70)
        print("      HEDGE FUND QUANT STRATEGY - LAST 10 DAYS RECAP")
        print("="*70)
        
        tdf = pd.DataFrame(trades)
        print("\n=== TRADE HISTORY ===")
        for _, t in tdf.iterrows():
            print(f"[{t['entry_time']}] {t['direction']} | PnL: ${t['pnl']:.2f} ({t['result']}) | Bal: ${t['balance']:.2f}")

        print("\n" + "="*70)
        print("      STRATEGY ANALYTICS (PRO GRADE)")
        print("="*70)
        print(f"Total Trade Count:  {metrics['total_trades']}")
        print(f"Win Rate:           {metrics['win_rate']:.1f}%")
        print(f"Profit Factor:      {metrics['profit_factor']:.2f}")
        print(f"Sharpe Ratio:       {metrics['sharpe_ratio']:.2f}")
        print(f"Sortino Ratio:      {metrics['sortino_ratio']:.2f}")
        print("-" * 40)
        print(f"Starting Capital:   ${start_bal:,.2f}")
        print(f"Final Balance:      ${metrics['final_balance']:,.2f}")
        print(f"Total Net PnL:      ${metrics['total_pnl']:,.2f}")
        print(f"TOTAL ROI:          {metrics['total_roi']:,.2f}%")
        print(f"MAX DRAWDOWN:       {metrics['max_drawdown']:.2f}%")
        print("="*70)
    else:
        print("\nNo signals found in the last 10 days.")

if __name__ == "__main__":
    main()
