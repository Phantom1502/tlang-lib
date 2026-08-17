from dataclasses import dataclass
from typing import Tuple

@dataclass(frozen=True)
class TLangConfig:
    expected_candle_count: int
    bin_range: Tuple[int, int]
    digit_pad: int
    mode: str
    zone_range: Tuple[int, int]
    sl_range: Tuple[int, int]
    zone_extend_multiplier: float
    last_n_touch: int