"""
Class này được xây dựng để phục vụ cho 2 mục đích:
- Xây dựng dataset:
    - Nhận input window + futures window + anchor_atr -> output window:
    Xây dựng prompt, future bins để build và verify entry, zone ...
    LƯU Ý: futures window luôn nhận anchor open của input window, anchor_atr của nến đầu tiên của input window.
    Để đảm bảo cùng hệ tọa độ
- Dùng để chạy trên môi trường thật:
    - Chỉ nhận và input window -> output window: Xây dựng prompt
    - Model dự đoán output
    - Decode thành giá thật cho các trường zone, sl, tp, ...
"""
import re
import numpy as np
import pandas as pd
from typing import List, Tuple
from .nodes import CandleNode

_TOKEN_RE = re.compile(r"([OHLC])_(\d+)")

class ChartCodec:
    def __init__(self, scale: float, n_bins: int):
        self.scale = scale
        self.n_bins = n_bins
        
    def _quantize_price(self, price: np.ndarray | float, anchor_open: float, anchor_atr: float, clip: bool = True):
        if anchor_atr <= 0 or np.isnan(anchor_atr):
            raise ValueError("anchor_atr phải > 0")
        
        # 1. Normalize theo Anchor Open và ATR
        norm = (price - anchor_open) / (self.scale * anchor_atr)
        
        # 2. Chỉ clip khi được yêu cầu (cho Input Window)
        if clip:
            norm = np.clip(norm, -1.0, 1.0)
            
        # 3. Chuyển sang Bin Index (Có thể nhận giá trị âm hoặc > n_bins - 1 nếu clip=False)
        bin_idx = np.round((norm + 1.0) / 2.0 * (self.n_bins - 1)).astype(int)
        return bin_idx
    
    def dequantize_bin(self, bin_idx, anchor_open, anchor_atr) -> float:
        norm = (bin_idx / (self.n_bins - 1)) * 2.0 - 1.0
        price = anchor_open + norm * self.scale * anchor_atr
        return price
    
    def _encode_input(self, input_window: np.ndarray, anchor_atr: float) -> Tuple[List[CandleNode], float]:
        # 1. Xác định window hi,lo
        max_high = np.max(input_window[:, 1]) # High
        min_low = np.min(input_window[:, 2]) # Low
        
        # 2. Xác định tâm đối xúng của window
        anchor_open = (max_high + min_low) / 2.0
        
        # 3. Quantize o, h, l, c
        candles = []
        for o, h, l, c in input_window:
            o = self._quantize_price(o, anchor_open, anchor_atr, clip=True)
            h = self._quantize_price(h, anchor_open, anchor_atr, clip=True)
            l = self._quantize_price(l, anchor_open, anchor_atr, clip=True)
            c = self._quantize_price(c, anchor_open, anchor_atr, clip=True)
            candles.append(CandleNode(open=o, high=h, low=l, close=c))
            
        return candles, anchor_open
    
    def _encode_future(self, future_window: np.ndarray, anchor_open: float, anchor_atr: float) -> List[CandleNode]:
        candles = []
        for o, h, l, c in future_window:
            o = self._quantize_price(o, anchor_open, anchor_atr, clip=False)
            h = self._quantize_price(h, anchor_open, anchor_atr, clip=False)
            l = self._quantize_price(l, anchor_open, anchor_atr, clip=False)
            c = self._quantize_price(c, anchor_open, anchor_atr, clip=False)
            candles.append(CandleNode(open=o, high=h, low=l, close=c))
            
        return candles
    
    def encode_window(self, window_df: pd.DataFrame, anchor_atr) -> Tuple[List[CandleNode], float]:
        max_high = window_df['High'].max()
        min_low = window_df['Low'].min()
        
        # 2. Xác định tâm đối xứng của window
        anchor_open = (max_high + min_low) / 2.0
        
        candles = []
        for _, row in window_df.iterrows():
            o = self.quantize_price(row['Open'], anchor_open, anchor_atr)
            h = self.quantize_price(row['High'], anchor_open, anchor_atr)
            l = self.quantize_price(row['Low'], anchor_open, anchor_atr)
            c = self.quantize_price(row['Close'], anchor_open, anchor_atr)
            candles.append(CandleNode(o, h, l, c))
            
        return candles, anchor_open
    
    def encode_window_with_anchor(self, window_df: pd.DataFrame, anchor_open, anchor_atr) -> List[CandleNode]:
        candles = []
        for _, row in window_df.iterrows():
            o = self.quantize_price(row['Open'], anchor_open, anchor_atr)
            h = self.quantize_price(row['High'], anchor_open, anchor_atr)
            l = self.quantize_price(row['Low'], anchor_open, anchor_atr)
            c = self.quantize_price(row['Close'], anchor_open, anchor_atr)
            candles.append(CandleNode(o, h, l, c))
            
        return candles
    
    def decode_window(self, text: str, anchor_open, anchor_atr) -> str:
        buckets = {"O": [], "H": [], "L": [], "C": []}
        for letter, num in _TOKEN_RE.findall(text):
            buckets[letter].append(int(num))
        
        n_candles = len(buckets["O"])
        if not all(len(buckets[k]) == n_candles for k in "HLC"):
            raise ValueError(
                f"Số token O/H/L/C không khớp nhau: "
                f"O={len(buckets['O'])} H={len(buckets['H'])} "
                f"L={len(buckets['L'])} C={len(buckets['C'])} "
                f"— text có thể bị model sinh lỗi/thiếu token."
            )
        
        rows = []
        for i in range(n_candles):
            rows.append({
                "Open":  self.dequantize_bin(buckets["O"][i], anchor_open, anchor_atr),
                "High":  self.dequantize_bin(buckets["H"][i], anchor_open, anchor_atr),
                "Low":   self.dequantize_bin(buckets["L"][i], anchor_open, anchor_atr),
                "Close": self.dequantize_bin(buckets["C"][i], anchor_open, anchor_atr),
            })
        
        return " ".join([f"O_{row['Open']} H_{row['High']} L_{row['Low']} C_{row['Close']}" for row in rows])
    
def plot_encode(candles: List[CandleNode]) -> None:
    import matplotlib.pyplot as plt
    import pandas as pd
    import mplfinance as mpf

    # 1. Tạo DataFrame
    df = pd.DataFrame({
        "Open": [c.open for c in candles],
        "High": [c.high for c in candles],
        "Low":  [c.low for c in candles],
        "Close": [c.close for c in candles],
    })
    
    # mplfinance yêu cầu Index dạng Datetime, nếu chỉ có index số thì tạo dummy date
    df.index = pd.date_range(start="2026-01-01", periods=len(df), freq="1min")

    # 2. Định nghĩa style (màu nến xanh/đỏ chuẩn trading)
    mc = mpf.make_marketcolors(
        up='green', down='red',
        edge='inherit',
        wick='inherit',
        volume='in'
    )
    s = mpf.make_mpf_style(marketcolors=mc, gridstyle="--", y_on_right=False)

    # 3. Vẽ Candlestick Chart
    fig, axlist = mpf.plot(
        df,
        type='candle',             # Kiểu nến Nhật (hoặc 'ohlc' cho dạng gạch ngang)
        style=s,
        title="Encoded Window Chart",
        ylabel="Quantized Price / Bin",
        figratio=(10, 6),
        returnfig=True
    )
    mid_index = len(df) / 2.0 - 0.5  # Vị trí chính giữa 2 nến trung tâm
    axlist[0].axvline(x=mid_index, color='orange', linestyle='--', linewidth=1.5, label='Center')
    
    mpf.show()
    
def plot_comparison(
    real_window: np.ndarray, 
    candles: List[CandleNode], 
    codec: ChartCodec, 
    anchor_open: float, 
    anchor_atr: float
) -> None:
    import matplotlib.pyplot as plt
    import pandas as pd
    import mplfinance as mpf
    """
    Trực quan hóa so sánh giữa Giá thực tế và Giá đã Quantize.
    - Top Plot: Biểu đồ nến Giá thật (USD) + Nến Dequantized đè lên để soi sai số.
    - Bottom Plot: Biểu đồ nến dạng Quantized Bin Index.
    """
    # 1. Chuẩn bị DataFrame cho Giá thật
    df_real = pd.DataFrame(real_window, columns=["Open", "High", "Low", "Close"])
    df_real.index = pd.date_range(start="2026-01-01", periods=len(df_real), freq="1min")

    # 2. Chuẩn bị DataFrame cho Quantized Bins
    df_bin = pd.DataFrame({
        "Open": [c.open for c in candles],
        "High": [c.high for c in candles],
        "Low":  [c.low for c in candles],
        "Close": [c.close for c in candles],
    }, index=df_real.index)

    # 3. Chuẩn bị DataFrame cho Giá Dequantized (Decode ngược về USD)
    df_dequant = pd.DataFrame({
        "Open": codec.dequantize_bin(df_bin["Open"].values, anchor_open, anchor_atr),
        "High": codec.dequantize_bin(df_bin["High"].values, anchor_open, anchor_atr),
        "Low": codec.dequantize_bin(df_bin["Low"].values, anchor_open, anchor_atr),
        "Close": codec.dequantize_bin(df_bin["Close"].values, anchor_open, anchor_atr),
    }, index=df_real.index)

    # 4. Khởi tạo Subplots
    fig, (ax_real, ax_bin) = plt.subplots(2, 1, figsize=(14, 10), sharex=True)
    
    # ------------------ SUBPLOT 1: REAL PRICE VS DEQUANTIZED ------------------
    # Vẽ nến Giá thật (Real Price)
    for i in range(len(df_real)):
        color = '#26a69a' if df_real['Close'].iloc[i] >= df_real['Open'].iloc[i] else '#ef5350'
        # Râu nến
        ax_real.vlines(i, df_real['Low'].iloc[i], df_real['High'].iloc[i], color=color, linewidth=1)
        # Thân nến
        body_bottom = min(df_real['Open'].iloc[i], df_real['Close'].iloc[i])
        body_height = abs(df_real['Close'].iloc[i] - df_real['Open'].iloc[i])
        ax_real.bar(i, body_height, bottom=body_bottom, color=color, width=0.5, alpha=0.8)

    # Vẽ đường Close Dequantized đè lên để thấy mức độ làm tròn (Quantization noise)
    ax_real.plot(np.arange(len(df_dequant)), df_dequant['Close'], color='black', linestyle='--', linewidth=1, alpha=0.7, label='Dequantized Close')
    ax_real.axhline(y=anchor_open, color='blue', linestyle=':', label=f'Anchor Open ({anchor_open:.2f})')
    
    ax_real.set_title("Real Price (USD) vs Dequantized Reconstruction", fontsize=12, fontweight='bold')
    ax_real.set_ylabel("Price ($)")
    ax_real.grid(True, linestyle=":", alpha=0.5)
    ax_real.legend(loc="upper left")

    # ------------------ SUBPLOT 2: QUANTIZED BIN INDEX ------------------
    for i in range(len(df_bin)):
        color = '#26a69a' if df_bin['Close'].iloc[i] >= df_bin['Open'].iloc[i] else '#ef5350'
        ax_bin.vlines(i, df_bin['Low'].iloc[i], df_bin['High'].iloc[i], color=color, linewidth=1)
        body_bottom = min(df_bin['Open'].iloc[i], df_bin['Close'].iloc[i])
        body_height = abs(df_bin['Close'].iloc[i] - df_bin['Open'].iloc[i])
        ax_bin.bar(i, body_height, bottom=body_bottom, color=color, width=0.5, alpha=0.8)

    # Đường phân cách Center giữa Input Window và Future Window
    mid_index = len(df_real) / 2.0 - 0.5
    ax_real.axvline(x=mid_index, color='orange', linestyle='--', linewidth=1.5, label='Input/Future Split')
    ax_bin.axvline(x=mid_index, color='orange', linestyle='--', linewidth=1.5, label='Input/Future Split')

    ax_bin.set_title("Quantized Window (Bin Index Space)", fontsize=12, fontweight='bold')
    ax_bin.set_ylabel("Bin Index [0 - N_Bins]")
    ax_bin.set_xlabel("Bar Index")
    ax_bin.grid(True, linestyle=":", alpha=0.5)

    plt.tight_layout()
    plt.show()
    
if __name__ == "__main__":
    import random
    df = pd.read_csv("data/XAUUSD_Daily.csv")
    
    ran_idx = random.randint(0, len(df) - 200)
    df = df.iloc[ran_idx:]
    
    input_df = df.iloc[:100]
    input_window = input_df[["Open", "High", "Low", "Close"]].values
    atr = input_df["ATR_100"].values[0]
    
    future_window = df.iloc[100:200][["Open", "High", "Low", "Close"]].values
    
    codec = ChartCodec(scale=24, n_bins=2048)
    input_candles, anchor_open = codec._encode_input(input_window, atr)
    future_candles = codec._encode_future(future_window, anchor_open, atr)
    
    # 📍 Gộp cả 2 mảng real window
    full_real_window = np.vstack([input_window, future_window])
    full_candles = input_candles + future_candles
    
    # Gọi hàm plot so sánh
    plot_comparison(
        real_window=full_real_window, 
        candles=full_candles, 
        codec=codec, 
        anchor_open=anchor_open, 
        anchor_atr=atr
    )