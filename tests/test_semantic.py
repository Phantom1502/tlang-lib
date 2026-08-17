"""
Unit tests cho app/tlang/lang/semantic.py

Chạy: pytest tests/test_semantic.py -v

Lưu ý thiết kế fixture: chart dùng 1 nến "phủ toàn dải" (L=0, H=1023) để
điều kiện "zone chạm nến gần nhất" trong _check_price_in_zone_geometry()
LUÔN đúng, bất kể zone đặt ở đâu trong bin_range. Điều này cần thiết vì
_check_price_in_zone_geometry() có 1 bug (xem TestPriceInZoneGeometry)
khiến nó crash bất cứ khi nào điều kiện "not is_price_in_zone" đúng —
nên các test không nhắm trực tiếp vào bug đó phải né được branch này,
nếu không toàn bộ test khác (width, direction, action-group, SL...) đều
sẽ crash lây dù không liên quan tới lỗi geometry.
"""
from __future__ import annotations

import pytest

from app.tlang.lang.config import TLangConfig
from app.tlang.lang.parser import Parser
from app.tlang.lang.semantic import SemanticChecker


@pytest.fixture
def full_cfg() -> TLangConfig:
    return TLangConfig(
        expected_candle_count=1,
        bin_range=(0, 1023),
        digit_pad=4,
        mode="full",
        zone_range=(1, 20),
        sl_range=(1, 50),
        zone_extend_multiplier=50.0,   # margin rộng để test không tình cờ vấp bug last_n_touch
        last_n_touch=1,
    )


@pytest.fixture
def zone_cfg() -> TLangConfig:
    return TLangConfig(
        expected_candle_count=1,
        bin_range=(0, 1023),
        digit_pad=4,
        mode="zone",
        zone_range=(1, 20),
        sl_range=(1, 50),
        zone_extend_multiplier=50.0,
        last_n_touch=1,
    )


# 1 nến phủ toàn bộ bin_range -> luôn "chạm" mọi zone hợp lệ trong [0,1023],
# và current_price=0500 khớp Close nến (bắt buộc ở mode="zone").
VALID_CHART = """
<chart>
<O_500> <H_1023> <L_0> <C_500>
</chart>
"""

VALID_ACTION = """
<action>
BUY
SL:0460
<RR_3>
</action>
"""


def build_ast(cfg: TLangConfig, think_body: str, chart: str = VALID_CHART, action: str = VALID_ACTION):
    text = chart + think_body
    if cfg.mode == "full":
        text += action
    result = Parser.from_text(cfg, text).parse()
    assert result.is_well_formed(), f"fixture text should be well-formed, got errors: {result.errors}"
    return result.ast


def check(cfg: TLangConfig, ast):
    return SemanticChecker(cfg).check(ast)


# ======================================================================
# Chương trình hợp lệ end-to-end
# ======================================================================
def test_valid_full_program_passes(full_cfg):
    # zone_support (480:490) width=10, nằm dưới current_price (500);
    # SL=460 (dist=40, < lower_bin=480) -> mọi ràng buộc đều thoả.
    think = """
    <think>
    <trend>UP</trend>
    <current_price>0500</current_price>
    <zone_support>0480:0490</zone_support>
    </think>
    """
    ast = build_ast(full_cfg, think)
    result = check(full_cfg, ast)
    assert result.passed
    assert result.violations == []
    assert result.score == 1.0


def test_valid_zone_program_passes(zone_cfg):
    think = """
    <think>
    <trend>UP</trend>
    <current_price>0500</current_price>
    <zone_support>0480:0490</zone_support>
    </think>
    """
    ast = build_ast(zone_cfg, think)
    result = check(zone_cfg, ast)
    assert result.passed
    assert result.violations == []


# ======================================================================
# Guards: thiếu thành phần cơ bản
# ======================================================================
class TestGuards:
    def test_missing_action_in_full_mode_fails_safely(self, full_cfg):
        think = """
        <think>
        <trend>RANGE</trend>
        <current_price>0500</current_price>
        </think>
        """
        text = VALID_CHART + think  # không có action_block
        result = Parser.from_text(full_cfg, text).parse()
        sem = check(full_cfg, result.ast)
        assert sem.passed is False
        assert sem.score == 0.0

    def test_missing_trend_fails_safely(self, zone_cfg):
        think = """
        <think>
        <current_price>0500</current_price>
        <zone_support>0480:0490</zone_support>
        </think>
        """
        text = VALID_CHART + think
        result = Parser.from_text(zone_cfg, text).parse()
        sem = check(zone_cfg, result.ast)
        assert sem.passed is False
        assert sem.score == 0.0


# ======================================================================
# Bảng A: Trend <-> Zone
# ======================================================================
class TestTrendZoneTable:
    def test_up_without_zone_is_violation(self, zone_cfg):
        think = """
        <think>
        <trend>UP</trend>
        <current_price>0500</current_price>
        </think>
        """
        ast = build_ast(zone_cfg, think)
        result = check(zone_cfg, ast)
        assert not result.passed
        assert any("trend=UP nhưng thiếu zone" in v for v in result.violations)

    def test_up_with_resistance_is_violation(self, zone_cfg):
        think = """
        <think>
        <trend>UP</trend>
        <current_price>0500</current_price>
        <zone_resistance>0510:0520</zone_resistance>
        </think>
        """
        ast = build_ast(zone_cfg, think)
        result = check(zone_cfg, ast)
        assert not result.passed
        assert any("trend=UP nhưng zone lại là resistance" in v for v in result.violations)

    def test_down_without_zone_is_violation(self, zone_cfg):
        think = """
        <think>
        <trend>DOWN</trend>
        <current_price>0500</current_price>
        </think>
        """
        ast = build_ast(zone_cfg, think)
        result = check(zone_cfg, ast)
        assert not result.passed
        assert any("trend=DOWN nhưng thiếu zone" in v for v in result.violations)

    def test_down_with_support_is_violation(self, zone_cfg):
        think = """
        <think>
        <trend>DOWN</trend>
        <current_price>0500</current_price>
        <zone_support>0480:0490</zone_support>
        </think>
        """
        ast = build_ast(zone_cfg, think)
        result = check(zone_cfg, ast)
        assert not result.passed
        assert any("trend=DOWN nhưng zone lại là support" in v for v in result.violations)

    def test_down_with_resistance_is_ok(self, zone_cfg):
        think = """
        <think>
        <trend>DOWN</trend>
        <current_price>0500</current_price>
        <zone_resistance>0510:0520</zone_resistance>
        </think>
        """
        ast = build_ast(zone_cfg, think)
        result = check(zone_cfg, ast)
        assert result.passed

    def test_range_without_zone_is_ok(self, zone_cfg):
        think = """
        <think>
        <trend>RANGE</trend>
        <current_price>0500</current_price>
        </think>
        """
        ast = build_ast(zone_cfg, think)
        result = check(zone_cfg, ast)
        assert result.passed

    def test_range_with_either_zone_direction_is_ok(self, zone_cfg):
        for zone_tag, body in [
            ("zone_support", "0480:0490"),
            ("zone_resistance", "0510:0520"),
        ]:
            think = f"""
            <think>
            <trend>RANGE</trend>
            <current_price>0500</current_price>
            <{zone_tag}>{body}</{zone_tag}>
            </think>
            """
            ast = build_ast(zone_cfg, think)
            result = check(zone_cfg, ast)
            assert result.passed, result.violations


# ======================================================================
# Bảng B: hướng zone <-> current_price
# ======================================================================
class TestZoneDirectionVsPrice:
    def test_support_entirely_above_price_is_violation(self, zone_cfg):
        # zone_support (600:610) nằm hoàn toàn TRÊN current_price (500).
        # width=10 -> extend=10*50=500 nên vẫn "gần" đủ để né bug geometry.
        think = """
        <think>
        <trend>UP</trend>
        <current_price>0500</current_price>
        <zone_support>0600:0610</zone_support>
        </think>
        """
        ast = build_ast(zone_cfg, think)
        result = check(zone_cfg, ast)
        assert not result.passed
        assert any("nằm hoàn toàn trên current_price" in v for v in result.violations)

    def test_resistance_entirely_below_price_is_violation(self, zone_cfg):
        # zone_resistance (10:20) nằm hoàn toàn DƯỚI current_price (500).
        think = """
        <think>
        <trend>DOWN</trend>
        <current_price>0500</current_price>
        <zone_resistance>0010:0020</zone_resistance>
        </think>
        """
        ast = build_ast(zone_cfg, think)
        result = check(zone_cfg, ast)
        assert not result.passed
        assert any("nằm hoàn toàn dưới current_price" in v for v in result.violations)

    def test_support_boundary_equal_to_price_is_ok(self, zone_cfg):
        # lower_bin == current_price -> "<=" nên hợp lệ (boundary inclusive)
        think = """
        <think>
        <trend>UP</trend>
        <current_price>0500</current_price>
        <zone_support>0500:0510</zone_support>
        </think>
        """
        ast = build_ast(zone_cfg, think)
        result = check(zone_cfg, ast)
        direction_violations = [v for v in result.violations if "nằm hoàn toàn trên current_price" in v]
        assert direction_violations == []


# ======================================================================
# Zone width (spec 7.1)
# ======================================================================
class TestZoneWidth:
    def test_width_within_range_is_ok(self, zone_cfg):
        # zone_range=(1,20) -> width=10 hợp lệ
        think = """
        <think>
        <trend>UP</trend>
        <current_price>0500</current_price>
        <zone_support>0480:0490</zone_support>
        </think>
        """
        ast = build_ast(zone_cfg, think)
        result = check(zone_cfg, ast)
        width_violations = [v for v in result.violations if "width=" in v]
        assert width_violations == []

    def test_width_too_large_is_violation(self, zone_cfg):
        # zone_range=(1,20) -> width=220 vượt max (nhưng extend theo đó cũng
        # rất lớn nên geometry vẫn không vướng bug).
        think = """
        <think>
        <trend>UP</trend>
        <current_price>0500</current_price>
        <zone_support>0700:0920</zone_support>
        </think>
        """
        ast = build_ast(zone_cfg, think)
        result = check(zone_cfg, ast)
        assert any("width=220" in v for v in result.violations)

    def test_width_too_small_is_violation(self, zone_cfg):
        # zone_range=(1,20) -> width=0 dưới min. Đặt đúng tại current_price
        # (500:500) để extend=0 vẫn chứa current_price (boundary inclusive),
        # né được bug geometry trong khi vẫn trigger đúng lỗi width.
        think = """
        <think>
        <trend>UP</trend>
        <current_price>0500</current_price>
        <zone_support>0500:0500</zone_support>
        </think>
        """
        ast = build_ast(zone_cfg, think)
        result = check(zone_cfg, ast)
        assert any("width=0" in v for v in result.violations)


# ======================================================================
# price_in_zone geometry
# ======================================================================
class TestPriceInZoneGeometry:
    def test_zone_touching_recent_candles_and_price_nearby_is_ok(self, zone_cfg):
        think = """
        <think>
        <trend>UP</trend>
        <current_price>0500</current_price>
        <zone_support>0480:0490</zone_support>
        </think>
        """
        ast = build_ast(zone_cfg, think)
        result = check(zone_cfg, ast)
        geometry_violations = [v for v in result.violations if "không chạm" in v or "di chuyển quá xa" in v]
        assert geometry_violations == []

    @pytest.mark.xfail(
        reason=(
            "BUG: SemanticChecker._check_price_in_zone_geometry() build message bằng "
            "`self.last_n_touch` nhưng attribute thực tế là `self.cfg.last_n_touch` "
            "(SemanticChecker không lưu last_n_touch riêng, chỉ có self.cfg) -> "
            "AttributeError bất cứ khi nào is_price_in_zone == False, tức là BẤT KỲ "
            "completion nào có current_price lệch quá xa khỏi zone (trường hợp rất "
            "thường gặp trong output của model khi GRPO mới bắt đầu train) sẽ làm "
            "sập toàn bộ reward pipeline thay vì trả về violation bình thường. "
            "Sửa: đổi `self.last_n_touch` thành `self.cfg.last_n_touch`."
        ),
        strict=True,
    )
    def test_zone_far_from_price_should_report_violation_not_crash(self, zone_cfg):
        # current_price=0 rất xa zone_support (600:610) ngay cả sau khi extend
        # -> is_price_in_zone phải là False và lẽ ra chỉ nên append 1 violation
        # string, KHÔNG được crash.
        think = """
        <think>
        <trend>UP</trend>
        <current_price>0000</current_price>
        <zone_support>0600:0610</zone_support>
        </think>
        """
        ast = build_ast(zone_cfg, think)
        result = check(zone_cfg, ast)
        assert not result.passed


# ======================================================================
# Bảng E: zone <-> action group hợp lệ (chỉ mode="full")
# ======================================================================
class TestActionGroup:
    def test_support_zone_allows_buy(self, full_cfg):
        think = """
        <think>
        <trend>UP</trend>
        <current_price>0500</current_price>
        <zone_support>0480:0490</zone_support>
        </think>
        """
        ast = build_ast(full_cfg, think, action=VALID_ACTION)  # BUY, SL:0460
        result = check(full_cfg, ast)
        assert result.passed

    def test_support_zone_allows_hold(self, full_cfg):
        think = """
        <think>
        <trend>UP</trend>
        <current_price>0500</current_price>
        <zone_support>0480:0490</zone_support>
        </think>
        """
        action = """
        <action>
        HOLD
        </action>
        """
        ast = build_ast(full_cfg, think, action=action)
        result = check(full_cfg, ast)
        assert result.passed

    def test_support_zone_rejects_sell(self, full_cfg):
        think = """
        <think>
        <trend>UP</trend>
        <current_price>0500</current_price>
        <zone_support>0480:0490</zone_support>
        </think>
        """
        action = """
        <action>
        SELL
        SL:0520
        <RR_3>
        </action>
        """
        ast = build_ast(full_cfg, think, action=action)
        result = check(full_cfg, ast)
        assert not result.passed
        assert any("action hợp lệ phải thuộc" in v for v in result.violations)

    def test_resistance_zone_allows_sell(self, full_cfg):
        think = """
        <think>
        <trend>DOWN</trend>
        <current_price>0500</current_price>
        <zone_resistance>0510:0520</zone_resistance>
        </think>
        """
        action = """
        <action>
        SELL
        SL:0530
        <RR_3>
        </action>
        """
        ast = build_ast(full_cfg, think, action=action)
        result = check(full_cfg, ast)
        assert result.passed

    def test_resistance_zone_rejects_buy(self, full_cfg):
        think = """
        <think>
        <trend>DOWN</trend>
        <current_price>0500</current_price>
        <zone_resistance>0510:0520</zone_resistance>
        </think>
        """
        action = """
        <action>
        BUY
        SL:0480
        <RR_3>
        </action>
        """
        ast = build_ast(full_cfg, think, action=action)
        result = check(full_cfg, ast)
        assert not result.passed
        assert any("action hợp lệ phải thuộc" in v for v in result.violations)

    @pytest.mark.skip(
        reason=(
            "KHÔNG PHẢI BUG (đã xác nhận với team): _check_action_group() và "
            "_check_sl_valid() truy cập think.zone.direction / think.zone.lower_bin "
            "mà không kiểm tra None, nên về mặt lý thuyết cú pháp thuần tuý, "
            "trend=RANGE + mode='full' + không có zone (well-formed hợp lệ theo "
            "Parser) sẽ khiến check() crash AttributeError. NHƯNG ở mode='full', "
            "toàn bộ think_block nằm trong PHẦN PROMPT CỐ ĐỊNH (dữ liệu ground-truth "
            "đã qua bước filter chỉ giữ sample có zone + đủ last_n_touch) — model "
            "trong action project chỉ sinh action_block, không sinh trend/zone. Do đó "
            "input (RANGE, zone=None) trong mode='full' là bất khả thi trong pipeline "
            "thực tế, dù Parser không cấm nó về mặt cú pháp. Giữ test này lại làm tài "
            "liệu cho invariant đó, không coi là lỗi cần sửa."
        )
    )
    def test_range_trend_without_zone_in_full_mode_would_crash_but_is_unreachable(self, full_cfg):
        think = """
        <think>
        <trend>RANGE</trend>
        <current_price>0500</current_price>
        </think>
        """
        action = """
        <action>
        BUY
        SL:0460
        <RR_3>
        </action>
        """
        ast = build_ast(full_cfg, think, action=action)
        result = check(full_cfg, ast)
        assert isinstance(result.passed, bool)


# ======================================================================
# SL hợp lệ (khoảng cách + vị trí so với zone)
# ======================================================================
class TestSLValid:
    def test_sl_distance_within_range_is_ok(self, full_cfg):
        # sl_range=(1,50); current=500, sl=460 -> dist=40
        think = """
        <think>
        <trend>UP</trend>
        <current_price>0500</current_price>
        <zone_support>0480:0490</zone_support>
        </think>
        """
        ast = build_ast(full_cfg, think, action=VALID_ACTION)
        result = check(full_cfg, ast)
        dist_violations = [v for v in result.violations if "nằm ngoài phạm vi hợp lệ" in v]
        assert dist_violations == []

    def test_sl_distance_too_far_is_violation(self, full_cfg):
        # sl_range=(1,50); current=500, sl=10 -> dist=490 > 50
        think = """
        <think>
        <trend>UP</trend>
        <current_price>0500</current_price>
        <zone_support>0480:0490</zone_support>
        </think>
        """
        action = """
        <action>
        BUY
        SL:0010
        <RR_3>
        </action>
        """
        ast = build_ast(full_cfg, think, action=action)
        result = check(full_cfg, ast)
        assert any("nằm ngoài phạm vi hợp lệ" in v for v in result.violations)

    def test_buy_sl_must_be_below_support_zone(self, full_cfg):
        # BUY nhưng SL (485) nằm TRONG zone_support (480:490) thay vì dưới nó
        think = """
        <think>
        <trend>UP</trend>
        <current_price>0500</current_price>
        <zone_support>0480:0490</zone_support>
        </think>
        """
        action = """
        <action>
        BUY
        SL:0485
        <RR_3>
        </action>
        """
        ast = build_ast(full_cfg, think, action=action)
        result = check(full_cfg, ast)
        assert any("BUY SL=485 phải nằm dưới zone" in v for v in result.violations)

    def test_sell_sl_must_be_above_resistance_zone(self, full_cfg):
        # SELL nhưng SL (515) nằm TRONG zone_resistance (510:520) thay vì trên nó
        think = """
        <think>
        <trend>DOWN</trend>
        <current_price>0500</current_price>
        <zone_resistance>0510:0520</zone_resistance>
        </think>
        """
        action = """
        <action>
        SELL
        SL:0515
        <RR_3>
        </action>
        """
        ast = build_ast(full_cfg, think, action=action)
        result = check(full_cfg, ast)
        assert any("SELL SL=515 phải nằm trên zone" in v for v in result.violations)

    def test_hold_skips_sl_checks_entirely(self, full_cfg):
        think = """
        <think>
        <trend>UP</trend>
        <current_price>0500</current_price>
        <zone_support>0480:0490</zone_support>
        </think>
        """
        action = """
        <action>
        HOLD
        </action>
        """
        ast = build_ast(full_cfg, think, action=action)
        result = check(full_cfg, ast)
        assert result.passed


# ======================================================================
# Score liên tục theo số lượng violation
# ======================================================================
class TestScoreGradient:
    def test_score_decreases_with_violation_count(self, zone_cfg):
        # zone_support (700:920): vừa "entirely above price" (direction, bảng B)
        # vừa width=220 vượt max (zone_range) -> đúng 2 violation, geometry né
        # được bug vì extend=220*50 rất lớn.
        think = """
        <think>
        <trend>UP</trend>
        <current_price>0500</current_price>
        <zone_support>0700:0920</zone_support>
        </think>
        """
        ast = build_ast(zone_cfg, think)
        result = check(zone_cfg, ast)
        assert not result.passed
        assert len(result.violations) == 2
        expected = max(0.0, 1.0 - SemanticChecker.VIOLATION_PENALTY * len(result.violations))
        assert result.score == pytest.approx(expected)