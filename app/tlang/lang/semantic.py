from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional
from enum import Enum

from .config import TLangConfig
from ..nodes import (
    ChartNode, 
    ProgramNode, 
    ThinkNode, 
    ActionNode,
    TrendType,
    ZoneDirection,
    ActionType
)

class ViolationType(Enum):
    MISS_CHART_BLOCK = "Thiếu chart — không thể kiểm tra semantic"
    MISS_THINK_BLOCK = "Thiếu think — không thể kiểm tra semantic"
    MISS_ACTION_BLOCK = "Trong mode full, phải có action block"
    MISS_CANDLES = "Chart block thiếu candles"
    MISS_TREND = "Think block thiếu trend"
    MISS_CURRENT_PRICE = "Think block thiếu current_price"
    MISS_ACTION_TYPE = "Action block thiếu action_type"
    UP_TREND_MISS_ZONE = "Trend=UP nhưng thiếu zone"
    UP_TREND_WRONG_ZONE = "Trend=UP nhưng zone là resistance"
    DOWN_TREND_MISS_ZONE = "Trend=DOWN nhưng thiếu zone"
    DOWN_TREND_WRONG_ZONE = "Trend=DOWN nhưng zone là support"
    ZONE_SUPPORT_ABOVE_CURRENT_PRICE = "Support zone nằm trên current_price"
    ZONE_RESISTANCE_BELOW_CURRENT_PRICE = "Resistance zone nằm dưới current_price"
    ZONE_RANGE_VIOLATION = "Zone range nhỏ hoặc lớn hơn configured range"
    ACTION_VIOLATION_VS_ZONE = "Action type xung đột với zone direction"
    ACTION_SL_OUT_OF_RANGE = "SL out of range"
    ACTION_SL_VIOLATION_ZONE = "SL vi phạm zone"
# =====================================================================
# SemanticResult — passed CHỈ true khi KHÔNG có vi phạm nào (100%, theo
# quyết định đã chốt: gate 2 yêu cầu pass toàn bộ mới cho phép tính
# outcome, không dùng ngưỡng %). `score` vẫn liên tục (dùng cho nhánh
# fail, R_sem_fail) để reward không quá thưa.
# =====================================================================
@dataclass
class SemanticResult:
    passed: bool
    violations: List[ViolationType] = field(default_factory=list)
    score: float = 1.0


class SemanticChecker:
    """
    Kiểm tra bảng 2.2 (A, B, D, E) trên AST đã parse thành công.

    KHÔNG kiểm tra bảng F (field bắt buộc/cấm theo action_type — đã ở
    well-form, thuộc Parser) và KHÔNG kiểm tra mục G (good_price_action
    không có rule nội dung, chủ ý để tránh áp đặt bias chủ quan).

    Nguyên tắc: verifier này = "lật ngược" generator dùng để sinh dữ
    liệu SFT/pretrain — generator đảm bảo đúng các invariant này lúc
    sinh, verifier chỉ cần lật ngược logic đó thành kiểm tra.
    """

    VIOLATION_PENALTY = 0.2       # placeholder — tinh chỉnh sau khi có dữ liệu GRPO thực nghiệm

    BUY_SIDE_ACTIONS = {ActionType.BUY, ActionType.HOLD}
    SELL_SIDE_ACTIONS = {ActionType.SELL, ActionType.HOLD}

    def __init__(
        self,
        cfg: TLangConfig,
    ) -> None:
        self.cfg = cfg

    def check(self, program: ProgramNode) -> SemanticResult:
        chart, think, action = program.chart, program.think, program.action
        violations: List[str] = []

        # Phòng vệ: thiếu thành phần cơ bản để đánh giá — lẽ ra đã bị
        # well-form chặn từ trước (Semantic Checker chỉ nên chạy khi
        # well-form đã pass), nhưng vẫn xử lý an toàn nếu bị gọi độc lập.
        if chart is None:
            return SemanticResult(
                passed=False, 
                violations=[ViolationType.MISS_CHART_BLOCK], 
                score=0.0
            )
        if think is None:
            return SemanticResult(
                passed=False, 
                violations=[ViolationType.MISS_THINK_BLOCK], 
                score=0.0
            )
        if action is None and self.cfg.mode == "full":
            return SemanticResult(
                passed=False, 
                violations=[ViolationType.MISS_ACTION_BLOCK], 
                score=0.0
            )
        
        if not chart.candles:
            return SemanticResult(
                passed=False, 
                violations=[ViolationType.MISS_CANDLES], 
                score=0.0
            )
            
        if think.trend is None:
            return SemanticResult(
                passed=False, 
                violations=[ViolationType.MISS_TREND], 
                score=0.0
            )
            
        if think.current_price_bin is None:
            return SemanticResult(
                passed=False, 
                violations=[ViolationType.MISS_CURRENT_PRICE], 
                score=0.0
            )
            
        
        if self.cfg.mode == "full" and action.action_type is None:
            return SemanticResult(
                passed=False, 
                violations=[ViolationType.MISS_ACTION_TYPE], 
                score=0.0
            )
            
        self._check_trend_zone(think, violations)
        if think.zone is not None:
            self._check_zone_direction_vs_price(think, violations)
            self._check_zone_width(think, violations)
            
            # entry chuyển thành limit, không cần price in zone
            #if self.cfg.mode == "full": # check price in zone
            #    self._check_price_in_zone_geometry(chart, think, violations)
            
        if self.cfg.mode == "full":
            self._check_action_group(think, action, violations)
            self._check_sl_valid(think, action, violations)

        passed = len(violations) == 0
        score = max(0.0, 1.0 - self.VIOLATION_PENALTY * len(violations))
        return SemanticResult(passed=passed, violations=violations, score=score)

    # ------------------------------------------------------------------
    # A. Trend ↔ Zone
    # ------------------------------------------------------------------
    def _check_trend_zone(self, think: ThinkNode, violations: List[ViolationType]) -> None:
        trend = think.trend
        zone = think.zone

        if trend == TrendType.UP:
            if zone is None:
                violations.append(ViolationType.UP_TREND_MISS_ZONE)
            elif zone.direction != ZoneDirection.support:
                violations.append(ViolationType.UP_TREND_WRONG_ZONE)

        elif trend == TrendType.DOWN:
            if zone is None:
                violations.append(ViolationType.DOWN_TREND_MISS_ZONE)
            elif zone.direction != ZoneDirection.resistance:
                violations.append(ViolationType.DOWN_TREND_WRONG_ZONE)

        elif trend == TrendType.RANGE:
            # RANGE: zone tùy chọn, cả 2 hướng đều hợp lệ nếu có — không có vi phạm ở mục A.
            pass

    # ------------------------------------------------------------------
    # B. Hướng của Zone ↔ current_price (bin arithmetic thuần túy)
    # ------------------------------------------------------------------
    def _check_zone_direction_vs_price(self, think: ThinkNode, violations: List[str]) -> None:
        zone = think.zone
        if zone is None:
            return
        current = think.current_price_bin

        if zone.direction == ZoneDirection.support:
            if not (zone.lower_bin <= current):
                violations.append(ViolationType.ZONE_SUPPORT_ABOVE_CURRENT_PRICE)
        else:  # resistance
            if not (zone.upper_bin >= current):
                violations.append(ViolationType.ZONE_RESISTANCE_BELOW_CURRENT_PRICE)

    # ------------------------------------------------------------------
    # B2. Bề rộng Zone — BỔ SUNG (không có trong bảng A/B/D/E gốc của spec
    # mục 2.2, nhưng spec mục 7.1 có nhắc ZONE_WIDTH_MIN_BINS/MAX_BINS như
    # 1 ràng buộc set tay, cùng cấp với SL_MIN_DIST_BINS/MAX_BINS. Trước
    # đây constraint này CHỈ được generator tôn trọng lúc sinh data, không
    # verifier nào kiểm tra lại lúc GRPO — vi phạm nguyên tắc "verifier =
    # lật ngược generator" (mục 4.4). Thêm ở đây để đóng gap này.
    # ------------------------------------------------------------------
    def _check_zone_width(self, think: ThinkNode, violations: List[str]) -> None:
        zone = think.zone
        width = zone.upper_bin - zone.lower_bin
        if not (self.cfg.zone_range[0] <= width <= self.cfg.zone_range[1]):
            violations.append(ViolationType.ZONE_RANGE_VIOLATION)
            
    def _check_price_in_zone_geometry(
        self, chart: ChartNode, think: ThinkNode, violations: List[str]
    ) -> Optional[bool]:
        zone = think.zone
        if zone is None:
            return
        extend_zone_range = (zone.upper_bin - zone.lower_bin) * self.cfg.zone_extend_multiplier
        current = think.current_price_bin
        is_current_price_in_extend_zone = (zone.lower_bin - extend_zone_range <= current <= zone.upper_bin + extend_zone_range)

        last_n_candles = chart.candles[-self.cfg.last_n_touch:]
        is_price_in_zone = any(c.low <= zone.upper_bin and c.high >= zone.lower_bin for c in last_n_candles) and is_current_price_in_extend_zone
        if not is_price_in_zone:
            violations.append(
                f"zone={zone.direction} ({zone.lower_bin}:{zone.upper_bin}) không chạm {self.cfg.last_n_touch} candles gần nhất, "
                f"hoặc current_price ({current}) đã di chuyển quá xa khỏi zone. Không nằm trong phạm vi model cần học."
            )
        return is_price_in_zone
    
    # ------------------------------------------------------------------
    # E. price_in_zone ↔ nhóm action hợp lệ
    # ------------------------------------------------------------------
    def _check_action_group(
        self,
        think: ThinkNode,
        action: ActionNode,
        violations: List[str]
    ) -> None:
        zone = think.zone # đối với action model, luôn luôn phải có zone
        action_type = action.action_type

        if zone.direction == ZoneDirection.support:
            valid_actions = self.BUY_SIDE_ACTIONS
        else:  # resistance
            valid_actions = self.SELL_SIDE_ACTIONS

        if action_type not in valid_actions:
            violations.append(ViolationType.ACTION_VIOLATION_VS_ZONE)
            
    def _check_sl_valid(
        self,
        think: ThinkNode,
        action: ActionNode,
        violations: List[str]
    ) -> None:
        
        if action.action_type not in (ActionType.BUY, ActionType.SELL):
            return
        
        current = think.current_price_bin
        dist = abs(current - action.sl)
        if not (self.cfg.sl_range[0] <= dist <= self.cfg.sl_range[1]):
            violations.append(ViolationType.ACTION_SL_OUT_OF_RANGE)
            
        if action.action_type == ActionType.BUY:
            if action.sl >= think.zone.lower_bin:
                violations.append(ViolationType.ACTION_SL_VIOLATION_ZONE)
        if action.action_type == ActionType.SELL:
            if action.sl <= think.zone.upper_bin:
                violations.append(ViolationType.ACTION_SL_VIOLATION_ZONE)