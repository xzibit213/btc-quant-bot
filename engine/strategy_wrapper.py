import pandas as pd
import numpy as np
import sys
import os

# Add parent directory to path to import strategy_quant
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from strategy_quant import compute_indicators, StrategyConfig

class BtcQuantStrategy:
    def __init__(self):
        self.cfg = StrategyConfig()
        
    def populate_indicators(self, df):
        # We need to compute range for the dashboard heartbeats
        df['range'] = df['high'] - df['low']
        return compute_indicators(df, self.cfg)

    def populate_signals(self, df, min_range=0.0):
        df['enter_long'] = 0
        df['enter_short'] = 0
        df['sl_price'] = 0.0
        df['tp_price'] = 0.0
        
        # Conditions for long
        long_cond = (df['momentum_signal'] > 0.15) & \
                    (df['regime_safe'] == 1) & \
                    ((df['trend_sma'].isna()) | (df['close'] >= df['trend_sma']))
                    
        # Conditions for short
        short_cond = (df['momentum_signal'] < -0.15) & \
                     (df['regime_safe'] == 1) & \
                     ((df['trend_sma'].isna()) | (df['close'] <= df['trend_sma']))
                     
        df.loc[long_cond, 'enter_long'] = 1
        df.loc[short_cond, 'enter_short'] = 1
        
        # SL and TP calculation
        stop_dist = df['atr'] * self.cfg.STOP_ATR_MULT
        tp_dist = df['atr'] * self.cfg.TP_ATR_MULT
        
        df.loc[df['enter_long'] == 1, 'sl_price'] = df['close'] - stop_dist
        df.loc[df['enter_long'] == 1, 'tp_price'] = df['close'] + tp_dist
        
        df.loc[df['enter_short'] == 1, 'sl_price'] = df['close'] + stop_dist
        df.loc[df['enter_short'] == 1, 'tp_price'] = df['close'] - tp_dist
        
        return df
