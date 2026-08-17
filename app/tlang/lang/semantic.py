from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional
from .config import TLangConfig
from ..nodes import (
    ChartNode, 
    ProgramNode, 
    ThinkNode, 
    ActionNode
)


# =====================================================================
# SemanticResult — passed CHỈ true khi KHÔNG có vi phạm nào (100%, theo
# quyết định đã chốt: gate 2 yêu cầu pass toàn bộ mới cho phép tính
# outcome, không dùng ngưỡng %). `score` vẫn liên tục (dùng cho nhánh
# fail, R_sem_fail) để reward không quá thưa.
# =====================================================================
@dataclass
class SemanticResult:
    passed: bool
    violations: List[str] = field(default_factory=list)
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

    BUY_SIDE_ACTIONS = {"BUY", "HOLD"}
    SELL_SIDE_ACTIONS = {"SELL", "HOLD"}

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
        if chart is None or think is None:
            return SemanticResult(passed=False, violations=["Thiếu chart/think — không thể kiểm tra semantic"], score=0.0)
        if action is None and self.cfg.mode == "full":
            return SemanticResult(passed=False, violations=["Thiếu action — không thể kiểm tra semantic"], score=0.0)
        if not chart.candles or think.trend is None or think.current_price_bin is None:
            return SemanticResult(
                passed=False,
                violations=["Thiếu trend/current_price/candles — không thể kiểm tra semantic"],
                score=0.0,
            )
        if self.cfg.mode == "full" and action.action_type is None:
            return SemanticResult(passed=False, violations=["Thiếu action_type — không thể kiểm tra semantic"], score=0.0)

        self._check_trend_zone(think, violations)
        if think.zone is not None:
            self._check_zone_direction_vs_price(think, violations)
            self._check_zone_width(think, violations)
            self._check_price_in_zone_geometry(chart, think, violations)
            
        if self.cfg.mode == "full":
            self._check_action_group(think, action, violations)
            self._check_sl_valid(think, action, violations)

        passed = len(violations) == 0
        score = max(0.0, 1.0 - self.VIOLATION_PENALTY * len(violations))
        return SemanticResult(passed=passed, violations=violations, score=score)

    # ------------------------------------------------------------------
    # A. Trend ↔ Zone
    # ------------------------------------------------------------------
    def _check_trend_zone(self, think: ThinkNode, violations: List[str]) -> None:
        trend = think.trend
        zone = think.zone

        if trend == "UP":
            if zone is None:
                violations.append("trend=UP nhưng thiếu zone (bắt buộc phải có zone_support)")
            elif zone.direction != "support":
                violations.append(f"trend=UP nhưng zone lại là {zone.direction} (phải là zone_support)")

        elif trend == "DOWN":
            if zone is None:
                violations.append("trend=DOWN nhưng thiếu zone (bắt buộc phải có zone_resistance)")
            elif zone.direction != "resistance":
                violations.append(f"trend=DOWN nhưng zone lại là {zone.direction} (phải là zone_resistance)")

        elif trend == "RANGE":
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

        if zone.direction == "support":
            if not (zone.lower_bin <= current):
                violations.append(
                    f"zone_support ({zone.lower_bin}:{zone.upper_bin}) nằm hoàn toàn trên current_price "
                    f"({current}) — zone_support phải nằm dưới hoặc chứa giá hiện tại"
                )
        else:  # resistance
            if not (zone.upper_bin >= current):
                violations.append(
                    f"zone_resistance ({zone.lower_bin}:{zone.upper_bin}) nằm hoàn toàn dưới current_price "
                    f"({current}) — zone_resistance phải nằm trên hoặc chứa giá hiện tại"
                )

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
            violations.append(
                f"zone={zone.direction} ({zone.lower_bin}:{zone.upper_bin}) có width={width} bin, "
                f"ngoài phạm vi hợp lệ [{self.cfg.zone_range[0]},{self.cfg.zone_range[1]}]"
            )
            
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
                f"zone={zone.direction} ({zone.lower_bin}:{zone.upper_bin}) không chạm {self.last_n_touch} candles gần nhất, "
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

        if zone.direction == "support":
            valid_actions = self.BUY_SIDE_ACTIONS
        else:  # resistance
            valid_actions = self.SELL_SIDE_ACTIONS

        if action_type not in valid_actions:
            violations.append(
                f"zone={zone.direction} thì action hợp lệ phải thuộc "
                f"{sorted(valid_actions)}, nhận được {action_type}"
            )
            
    def _check_sl_valid(
        self,
        think: ThinkNode,
        action: ActionNode,
        violations: List[str]
    ) -> None:
        
        if action.action_type not in ("BUY", "SELL"):
            return
        
        current = think.current_price_bin
        dist = abs(current - action.sl)
        if not (self.cfg.sl_range[0] <= dist <= self.cfg.sl_range[1]):
            violations.append(
                f"SL={action.sl} ({dist}) nằm ngoài phạm vi hợp lệ [{self.cfg.sl_range[0]},{self.cfg.sl_range[1]}] "
            )
        if action.action_type == "BUY":
            if action.sl >= think.zone.lower_bin:
                violations.append(
                    f"BUY SL={action.sl} phải nằm dưới zone={think.zone.direction} ({think.zone.lower_bin}:{think.zone.upper_bin}) "
                )
        if action.action_type == "SELL":
            if action.sl <= think.zone.upper_bin:
                violations.append(
                    f"SELL SL={action.sl} phải nằm trên zone={think.zone.direction} ({think.zone.lower_bin}:{think.zone.upper_bin}) "
                )