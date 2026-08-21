import matplotlib.pyplot as plt
import mplfinance as mpf
import pandas as pd
from typing import List, Optional

from .nodes import ProgramNode, CandleNode

def plot_program(program: ProgramNode, future_candles: Optional[List[CandleNode]] = None):
    # 1. Gom toàn bộ nến (input + future)
    input_candles = program.chart.candles
    if future_candles is None:
        candles = input_candles
    else:
        candles = input_candles + future_candles
    
    df = pd.DataFrame({
        "Open": [c.open for c in candles],
        "High": [c.high for c in candles],
        "Low":  [c.low for c in candles],
        "Close": [c.close for c in candles],
    })
    df.index = pd.date_range(start="2026-01-01", periods=len(df), freq="1min")
    
    # 2. Định nghĩa Style
    mc = mpf.make_marketcolors(
        up='#26a69a', down='#ef5350',
        edge='inherit', wick='inherit', volume='in'
    )
    style = mpf.make_mpf_style(marketcolors=mc, gridstyle="--", y_on_right=False)

    # 3. Plot nến (Cần set returnfig=True để lấy axlist)
    fig, axlist = mpf.plot(
        df,
        type='candle',
        style=style,
        title=f"Program Execution Viz | Action: {getattr(program.action, 'action_type', 'HOLD')}",
        ylabel="Quantized Bin / Price",
        figratio=(12, 7),
        returnfig=True
    )
    ax = axlist[0]

    # 4. Đường dọc phân cách giữa Input Window và Future Window
    split_idx = len(input_candles) - 0.5
    ax.axvline(x=split_idx, color="orange", linestyle="--", linewidth=1.5, label="Prediction Point")

    # 5. Vẽ Zone (Tô màu vùng giá giữa lower_bin và upper_bin)
    if program.think is not None and program.think.zone is not None:
        zone = program.think.zone
        ax.axhspan(
            ymin=zone.lower_bin, 
            ymax=zone.upper_bin, 
            color="blue", 
            alpha=0.15, 
            label=f"Zone ({zone.direction}) [{zone.lower_bin} - {zone.upper_bin}]"
        )
        # Bờ cõi của Zone
        ax.axhline(zone.lower_bin, color="blue", linestyle=":", linewidth=1, alpha=0.6)
        ax.axhline(zone.upper_bin, color="blue", linestyle=":", linewidth=1, alpha=0.6)

    # 6. Vẽ các mức Trade Execution (Entry, SL, TP)
    if program.action is not None:
        act = program.action
        
        # Entry
        ax.axhline(program.chart.current_price, color="gray", linestyle="--", linewidth=1.5, label=f"Entry ({program.chart.current_price})")
            
        # Stop Loss
        ax.axhline(act.sl, color="red", linestyle="-", linewidth=2, label=f"SL ({act.sl})")
        
        tp_price = act.rr * (program.chart.current_price - act.sl) + program.chart.current_price
        if act.action_type == "SELL":
            tp_price = program.chart.current_price - act.rr * (act.sl - program.chart.current_price)
        
        ax.axhline(tp_price, color="green", linestyle="-", linewidth=2, label=f"TP ({tp_price})")

    # 7. Hiển thị Chú thích (Legend)
    ax.legend(loc="upper left", frameon=True, framealpha=0.8)
    
    mpf.show()
    
def plot_zones(input_candles: List[CandleNode], future_candles: List[CandleNode], zones: List[ZoneNode]):
    current_price = input_candles[-1].close
    # 1. Gom toàn bộ nến (input + future)
    if future_candles is None:
        candles = input_candles
    else:
        candles = input_candles + future_candles

    df = pd.DataFrame({
        "Open": [c.open for c in candles],
        "High": [c.high for c in candles],
        "Low":  [c.low for c in candles],
        "Close": [c.close for c in candles],
    })
    df.index = pd.date_range(start="2026-01-01", periods=len(df), freq="1min")

    # 2. Định nghĩa Style
    mc = mpf.make_marketcolors(
        up='#26a69a', down='#ef5350',
        edge='inherit', wick='inherit', volume='in'
    )
    style = mpf.make_mpf_style(marketcolors=mc, gridstyle="--", y_on_right=False)

    # 3. Plot nến (Cần set returnfig=True để lấy axlist)
    fig, axlist = mpf.plot(
        df,
        type='candle',
        style=style,
        title=f"Program Execution Viz | Action: {getattr(program.action, 'action_type', 'HOLD')}",
        ylabel="Quantized Bin / Price",
        figratio=(12, 7),
        returnfig=True
    )
    ax = axlist[0]

    # 4. Đường dọc phân cách giữa Input Window và Future Window
    split_idx = len(input_candles) - 0.5
    ax.axvline(x=split_idx, color="orange", linestyle="--", linewidth=1.5, label="Prediction Point")

    # 5. Vẽ Zone (Tô màu vùng giá giữa lower_bin và upper_bin)
    for zone in zones:
        ax.axhspan(
            ymin=zone.lower_bin,
            ymax=zone.upper_bin,
            color="blue",
            alpha=0.15,
            label=f"Zone ({zone.direction}) [{zone.lower_bin} - {zone.upper_bin}]"
        )
        # Bờ cõi của Zone
        ax.axhline(zone.lower_bin, color="blue", linestyle=":", linewidth=1, alpha=0.6)
        ax.axhline(zone.upper_bin, color="blue", linestyle=":", linewidth=1, alpha=0.6)

    # 7. Hiển thị Chú thích (Legend)
    ax.legend(loc="upper left", frameon=True, framealpha=0.8)

    mpf.show()