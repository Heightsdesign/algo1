# indicators.py
from __future__ import annotations
import numpy as np

def rsi(series: np.ndarray, period: int) -> np.ndarray:
    series = np.asarray(series, dtype=float)
    deltas = np.diff(series, prepend=series[0])
    gain = np.where(deltas > 0, deltas, 0.0)
    loss = np.where(deltas < 0, -deltas, 0.0)

    # Wilder's smoothing
    roll_up = np.zeros_like(series)
    roll_dn = np.zeros_like(series)
    roll_up[period] = gain[1:period+1].mean()
    roll_dn[period] = loss[1:period+1].mean()
    for i in range(period+1, len(series)):
        roll_up[i] = (roll_up[i-1]*(period-1) + gain[i]) / period
        roll_dn[i] = (roll_dn[i-1]*(period-1) + loss[i]) / period

    rs = np.divide(roll_up, roll_dn, out=np.zeros_like(roll_up), where=roll_dn!=0)
    rsi = 100.0 - (100.0 / (1.0 + rs))
    rsi[:period] = np.nan
    return rsi

def compute_streak(closes: np.ndarray) -> np.ndarray:
    # +n if consecutive up bars, -n if consecutive down bars
    streak = np.zeros_like(closes, dtype=float)
    for i in range(1, len(closes)):
        if closes[i] > closes[i-1]:
            streak[i] = streak[i-1] + 1 if streak[i-1] > 0 else 1
        elif closes[i] < closes[i-1]:
            streak[i] = streak[i-1] - 1 if streak[i-1] < 0 else -1
        else:
            streak[i] = 0
    return streak

def percent_rank(values: np.ndarray, lookback: int) -> np.ndarray:
    pr = np.full_like(values, fill_value=np.nan, dtype=float)
    for i in range(lookback, len(values)):
        window = values[i-lookback+1:i+1]
        pr[i] = 100.0 * (window <= values[i]).sum() / lookback
    return pr

def connors_rsi_30m(closes: np.ndarray,
                    rsi_period: int = 3,
                    streak_rsi_period: int = 2,
                    pr_lookback: int = 100) -> np.ndarray:
    closes = np.asarray(closes, dtype=float)
    roc1 = np.zeros_like(closes)
    roc1[1:] = (closes[1:] - closes[:-1]) / closes[:-1] * 100.0

    # components
    rsi_price   = rsi(closes, rsi_period)
    streak_vals = compute_streak(closes)
    rsi_streak  = rsi(streak_vals, streak_rsi_period)
    pr_rank     = percent_rank(roc1, pr_lookback)

    crsi = (rsi_price + rsi_streak + pr_rank) / 3.0
    return crsi
