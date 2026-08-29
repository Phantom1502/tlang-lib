from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Tuple, Literal

from ..nodes import (
    CandleNode,
    ZoneNode,
    ActionType,
    ZoneDirection
)

ZONE_PROBE_SL_BUFFER_BINS = 1

def derive_target(
    entry_bin: int, 
    sl_bin: int, 
    rr: int, 
    action_type: ActionType,
) -> Optional[int]:
    if action_type == ActionType.BUY:
        target = entry_bin + rr * (entry_bin - sl_bin)
    else:
        target = entry_bin - rr * (sl_bin - entry_bin)
    return round(target)

def find_entry_touch(entry_price: int, type: ActionType, candles: List[CandleNode]) -> Optional[int]:
    """Index nến ĐẦU TIÊN có [low,high] giao với [zone.lower_bin,
    zone.upper_bin] — None nếu không nến nào chạm trong toàn bộ `candles`
    (caller đã cắt đúng outcome_horizon trước khi truyền vào)."""
    for i, c in enumerate(candles):
        if type == ActionType.BUY:
            if c.low <= entry_price:
                return i
        else:
            if c.high >= entry_price:
                return i
    return None

def find_best_rr(
    action_type: ActionType, 
    entry_price: int, 
    sl: int, 
    future_candles: List[CandleNode], 
    rr_min: int, 
    rr_max: int
) -> int:
    targets = {rr: derive_target(entry_price, sl, rr, action_type) for rr in range(rr_min, rr_max + 1)}

    best_rr = 0
    for candle in future_candles:
        hit_sl = (candle.low <= sl) if action_type == ActionType.BUY else (candle.high >= sl)
        if hit_sl:
            return best_rr

        next_rr = max(best_rr + 1, rr_min)
        while next_rr <= rr_max:
            target = targets[next_rr]
            hit_target = (candle.high >= target) if action_type == ActionType.BUY else (candle.low <= target)
            if not hit_target:
                break
            best_rr = next_rr
            next_rr += 1

    return best_rr

def find_truly_valid_zones(
    input_candles: List[CandleNode],
    last_n: int,
    future_candles: List[CandleNode],
    mode: Literal[ZoneDirection.support, ZoneDirection.resistance] = ZoneDirection.support,
    swing_window: int = 2,
    zone_width: int = 50,
    max_bin: int = 2047
) -> List[Tuple[int, int, int]]:
    last_n_candles = input_candles[-last_n:]
    candles = last_n_candles + future_candles
    n = len(candles)
    
    valid_input_min = min(c.low for c in input_candles)
    valid_input_max = max(c.high for c in input_candles)
    valid_zone_ranges = [valid_input_min, valid_input_max]
    
    valid_swings = []
    if n <= last_n:
        return valid_swings
    
    is_support = (mode == ZoneDirection.support)
    for i in range(last_n, n):
        # 1. KIỂM TRA ĐIỀU KIỆN SWING HIGH / SWING LOW
        # Đảm bảo đủ số nến swing_window ở hai bên
        left_start = max(0, i - swing_window)
        right_end = min(n - 1, i + swing_window)

        if is_support:
            current_val = candles[i].low
            # Là Swing Low nếu giá Low hiện tại <= tất cả các nến trong cửa sổ xung quanh
            is_swing = all(current_val <= candles[j].low for j in range(left_start, right_end + 1) if j != i)
        else:
            current_val = candles[i].high
            # Là Swing High nếu giá High hiện tại >= tất cả các nến trong cửa sổ xung quanh
            is_swing = all(current_val >= candles[j].high for j in range(left_start, right_end + 1) if j != i)

        if not is_swing:
            continue
        
        if len(valid_swings) == 0:
            valid_swings.append((i, current_val))
        else:
            if is_support:
                min_swing = valid_swings[-1][1]
                if current_val < min_swing:
                    valid_swings.append((i, current_val))
            else:
                max_swing = valid_swings[-1][1]
                if current_val > max_swing:
                    valid_swings.append((i, current_val))

    # group all nearby swings into zones
    valid_zones = []
    for idx, swing in valid_swings:
        if len(valid_zones) == 0:
            valid_zones.append((idx, swing, swing))
        else:
            id, slow, shigh = valid_zones[-1]
            if is_support:
                if shigh - swing <= zone_width:
                    valid_zones[-1] = (id, swing, shigh)
                else:
                    valid_zones.append((idx, swing, swing))
            else:
                if swing - slow <= zone_width:
                    valid_zones[-1] = (id, slow, swing)
                else:
                    valid_zones.append((idx, swing, swing))

    # extend valid_zones to zone_width
    results = []
    for id, slow, shigh in valid_zones:
        if is_support:
            if shigh - slow <= zone_width:
                remain = zone_width - (shigh - slow)
                lower_bin = max(0, slow - remain // 2)
                upper_bin = lower_bin + zone_width
                    
                if upper_bin >= valid_zone_ranges[0]:
                    results.append((id, lower_bin, upper_bin, upper_bin - lower_bin))
        else:
            if shigh - slow <= zone_width:
                remain = zone_width - (shigh - slow)
                upper_bin = min(max_bin, shigh + remain // 2)
                lower_bin = upper_bin - zone_width
                    
                if lower_bin <= valid_zone_ranges[1]:
                    results.append((id, lower_bin, upper_bin, upper_bin - lower_bin))

    return results

def zone_score(
    zone: ZoneNode,
    future_candles: List[CandleNode],
    rr_min: int, 
    rr_max: int,
    max_bin: int,   # = n_bins - 1, giá trị bin hợp lệ tối đa
) -> float:
    touch_idx = None
    if zone.direction == ZoneDirection.support:
        touch_idx = find_entry_touch(zone.upper_bin, ActionType.BUY, future_candles)
    else:
        touch_idx = find_entry_touch(zone.lower_bin, ActionType.SELL, future_candles)
        
    if touch_idx is None:
        return 0.0

    rr = 0
    if zone.direction == ZoneDirection.support:
        sl = max(0, zone.lower_bin - ZONE_PROBE_SL_BUFFER_BINS)
        rr = find_best_rr(ActionType.BUY, zone.upper_bin, sl, future_candles[touch_idx:], rr_min, rr_max)
    else:
        sl = min(max_bin, zone.upper_bin + ZONE_PROBE_SL_BUFFER_BINS)
        rr = find_best_rr(ActionType.SELL, zone.lower_bin, sl, future_candles[touch_idx:], rr_min, rr_max)
    return rr