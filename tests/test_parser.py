"""
Unit tests cho app/tlang/lang/parser.py

Chạy: pytest tests/test_parser.py -v
"""
from __future__ import annotations

import pytest

from app.tlang.lang.config import TLangConfig
from app.tlang.lang.parser import Parser, ParseResult


# ======================================================================
# Fixtures / helpers
# ======================================================================
@pytest.fixture
def full_cfg() -> TLangConfig:
    return TLangConfig(
        expected_candle_count=3,
        bin_range=(0, 1023),
        digit_pad=4,
        mode="full",
        zone_range=(1, 20),
        sl_range=(1, 50),
        zone_extend_multiplier=1.0,
        last_n_touch=3,
    )


@pytest.fixture
def zone_cfg() -> TLangConfig:
    return TLangConfig(
        expected_candle_count=3,
        bin_range=(0, 1023),
        digit_pad=4,
        mode="zone",
        zone_range=(1, 20),
        sl_range=(1, 50),
        zone_extend_multiplier=1.0,
        last_n_touch=3,
    )


VALID_CHART = """
<chart>
<O_100> <H_110> <L_95> <C_105>
<O_105> <H_115> <L_100> <C_108>
<O_108> <H_120> <L_104> <C_112>
</chart>
"""

VALID_THINK = """
<think>
<trend>UP</trend>
<current_price>0112</current_price>
<zone_support>0100:0110</zone_support>
</think>
"""

VALID_ACTION = """
<action>
BUY
SL:0090
<RR_3>
</action>
"""


def parse(cfg: TLangConfig, text: str) -> ParseResult:
    return Parser.from_text(cfg, text).parse()


def messages(result: ParseResult) -> list[str]:
    return [e.message for e in result.errors]


# ======================================================================
# Toàn bộ chương trình hợp lệ
# ======================================================================
class TestValidProgram:
    def test_full_mode_no_errors(self, full_cfg):
        result = parse(full_cfg, VALID_CHART + VALID_THINK + VALID_ACTION)
        assert result.errors == []
        assert result.is_well_formed()
        assert result.well_form_score() == 1.0

    def test_zone_mode_no_errors(self, zone_cfg):
        result = parse(zone_cfg, VALID_CHART + VALID_THINK)
        assert result.errors == []
        assert result.is_well_formed()
        assert result.well_form_score() == 1.0

    def test_ast_values_full_mode(self, full_cfg):
        result = parse(full_cfg, VALID_CHART + VALID_THINK + VALID_ACTION)
        ast = result.ast
        assert len(ast.chart.candles) == 3
        assert ast.chart.candles[-1].close == 112
        assert ast.think.trend == "UP"
        assert ast.think.current_price_bin == 112
        assert ast.think.zone.direction == "support"
        assert ast.think.zone.lower_bin == 100
        assert ast.think.zone.upper_bin == 110
        assert ast.action.action_type == "BUY"
        assert ast.action.sl == 90
        assert ast.action.rr == 3

    def test_trailing_garbage_after_program_is_error(self, full_cfg):
        result = parse(full_cfg, VALID_CHART + VALID_THINK + VALID_ACTION + "EXTRA")
        assert any("Dư thừa token" in m for m in messages(result))
        assert not result.is_well_formed()


# ======================================================================
# chart_block
# ======================================================================
class TestChartBlock:
    def test_missing_chart_open(self, full_cfg):
        text = VALID_CHART.replace("<chart>", "") + VALID_THINK + VALID_ACTION
        result = parse(full_cfg, text)
        assert any("<chart>" in m for m in messages(result))
        # panic-mode: chart node vẫn None nhưng parse tiếp think/action mà không crash
        assert result.ast is not None

    def test_missing_chart_close_triggers_synchronize(self, full_cfg):
        text = VALID_CHART.replace("</chart>", "") + VALID_THINK + VALID_ACTION
        result = parse(full_cfg, text)
        assert any("</chart>" in m for m in messages(result))

    def test_wrong_candle_count_is_value_severity(self, full_cfg):
        # chỉ 1 nến thay vì 3 -> lỗi "value"
        one_candle_chart = """
        <chart>
        <O_100> <H_110> <L_95> <C_105>
        </chart>
        """
        result = parse(full_cfg, one_candle_chart + VALID_THINK + VALID_ACTION)
        count_errors = [e for e in result.errors if "Số nến" in e.message]
        assert len(count_errors) == 1
        assert count_errors[0].severity == "value"

    def test_candle_bin_out_of_range_is_value_severity(self, full_cfg):
        # bin_range = (0, 1023) -> 9999 vượt phạm vi
        bad_chart = """
        <chart>
        <O_9999> <H_110> <L_95> <C_105>
        <O_105> <H_115> <L_100> <C_108>
        <O_108> <H_120> <L_104> <C_112>
        </chart>
        """
        result = parse(full_cfg, bad_chart + VALID_THINK + VALID_ACTION)
        value_errors = [e for e in result.errors if e.severity == "value" and "bin" in e.message.lower()]
        assert len(value_errors) >= 1

    def test_unknown_token_inside_chart_does_not_crash(self, full_cfg):
        # ký tự lạ chen giữa các nến -> UNKNOWN token, lexer/parser không raise
        weird_chart = """
        <chart>
        <O_100> <H_110> <L_95> <C_105> $$$garbage$$$
        <O_105> <H_115> <L_100> <C_108>
        <O_108> <H_120> <L_104> <C_112>
        </chart>
        """
        # Không assert nội dung cụ thể — chỉ cần không raise exception
        result = parse(full_cfg, weird_chart + VALID_THINK + VALID_ACTION)
        assert result.ast is not None


# ======================================================================
# think_block
# ======================================================================
class TestThinkBlock:
    def test_missing_think_open(self, full_cfg):
        text = VALID_CHART + VALID_THINK.replace("<think>", "") + VALID_ACTION
        result = parse(full_cfg, text)
        assert any("<think>" in m for m in messages(result))

    def test_missing_trend(self, full_cfg):
        think = """
        <think>
        <current_price>0112</current_price>
        <zone_support>0100:0110</zone_support>
        </think>
        """
        result = parse(full_cfg, VALID_CHART + think + VALID_ACTION)
        assert any("<trend>" in m for m in messages(result))
        assert result.ast.think.trend is None

    def test_missing_current_price_is_value_severity(self, full_cfg):
        think = """
        <think>
        <trend>UP</trend>
        <zone_support>0100:0110</zone_support>
        </think>
        """
        result = parse(full_cfg, VALID_CHART + think + VALID_ACTION)
        cp_errors = [e for e in result.errors if "current_price" in e.message and e.severity == "value"]
        assert len(cp_errors) == 1

    def test_digit_pad_mismatch_is_value_severity(self, full_cfg):
        # digit_pad=4, "112" chỉ có 3 digit -> lỗi value, nhưng vẫn parse được giá trị
        think = """
        <think>
        <trend>UP</trend>
        <current_price>112</current_price>
        <zone_support>0100:0110</zone_support>
        </think>
        """
        result = parse(full_cfg, VALID_CHART + think + VALID_ACTION)
        pad_errors = [e for e in result.errors if "digit" in e.message and e.severity == "value"]
        assert len(pad_errors) >= 1
        assert result.ast.think.current_price_bin == 112

    def test_zone_resistance_parses(self, full_cfg):
        think = """
        <think>
        <trend>DOWN</trend>
        <current_price>0112</current_price>
        <zone_resistance>0115:0125</zone_resistance>
        </think>
        """
        result = parse(full_cfg, VALID_CHART + think + VALID_ACTION)
        zone = result.ast.think.zone
        assert zone.direction == "resistance"
        assert zone.lower_bin == 115
        assert zone.upper_bin == 125

    def test_zone_missing_colon(self, full_cfg):
        think = """
        <think>
        <trend>UP</trend>
        <current_price>0112</current_price>
        <zone_support>01000110</zone_support>
        </think>
        """
        result = parse(full_cfg, VALID_CHART + think + VALID_ACTION)
        assert any("phân cách" in m for m in messages(result))

    def test_zone_missing_close_tag(self, full_cfg):
        think = """
        <think>
        <trend>UP</trend>
        <current_price>0112</current_price>
        <zone_support>0100:0110
        </think>
        """
        result = parse(full_cfg, VALID_CHART + think + VALID_ACTION)
        assert any("tag đóng" in m for m in messages(result))

    def test_no_zone_is_allowed_by_parser_itself(self, zone_cfg):
        # Parser (well-form) không bắt buộc zone phải tồn tại — đó là việc
        # của SemanticChecker (bảng A). Ở tầng cú pháp, RANGE không có zone
        # vẫn well-formed.
        think = """
        <think>
        <trend>RANGE</trend>
        <current_price>0112</current_price>
        </think>
        """
        result = parse(zone_cfg, VALID_CHART + think)
        assert result.is_well_formed()
        assert result.ast.think.zone is None


# ======================================================================
# current_price khớp Close nến cuối (bảng 2.2.C)
# ======================================================================
class TestCurrentPriceMatchesChart:
    def test_zone_mode_detects_mismatch(self, zone_cfg):
        think = VALID_THINK.replace("<current_price>0112</current_price>", "<current_price>0200</current_price>")
        result = parse(zone_cfg, VALID_CHART + think)
        assert any("không khớp Close nến cuối" in m for m in messages(result))

    def test_zone_mode_accepts_match(self, zone_cfg):
        result = parse(zone_cfg, VALID_CHART + VALID_THINK)
        assert not any("không khớp Close nến cuối" in m for m in messages(result))

    @pytest.mark.xfail(
        reason=(
            "BUG: Parser.parse() chỉ gọi _check_current_price_matches_chart() ở "
            "nhánh mode=='zone'. Ở mode=='full' current_price sai lệch so với Close "
            "nến cuối KHÔNG bị phát hiện, dù docstring của class mô tả bảng 2.2.C "
            "áp dụng chung. Sửa: gọi check này cho cả 2 mode trong parse()."
        ),
        strict=True,
    )
    def test_full_mode_should_also_detect_mismatch(self, full_cfg):
        think = VALID_THINK.replace("<current_price>0112</current_price>", "<current_price>0200</current_price>")
        result = parse(full_cfg, VALID_CHART + think + VALID_ACTION)
        assert any("không khớp Close nến cuối" in m for m in messages(result))


# ======================================================================
# action_block + bảng 2.2.F (field bắt buộc/cấm theo action_type)
# ======================================================================
class TestActionBlock:
    def test_missing_action_open(self, full_cfg):
        action = VALID_ACTION.replace("<action>", "")
        result = parse(full_cfg, VALID_CHART + VALID_THINK + action)
        assert any("<action>" in m for m in messages(result))

    def test_missing_action_type(self, full_cfg):
        action = """
        <action>
        SL:0090
        <RR_3>
        </action>
        """
        result = parse(full_cfg, VALID_CHART + VALID_THINK + action)
        assert any("ACTION_TYPE" in m for m in messages(result))

    def test_buy_missing_sl_and_rr_is_error(self, full_cfg):
        action = """
        <action>
        BUY
        </action>
        """
        result = parse(full_cfg, VALID_CHART + VALID_THINK + action)
        assert any("Thiếu SL bắt buộc" in m for m in messages(result))
        assert any("Thiếu RR bắt buộc" in m for m in messages(result))

    def test_sell_missing_sl_and_rr_is_error(self, full_cfg):
        action = """
        <action>
        SELL
        </action>
        """
        result = parse(full_cfg, VALID_CHART + VALID_THINK + action)
        assert any("Thiếu SL bắt buộc" in m for m in messages(result))
        assert any("Thiếu RR bắt buộc" in m for m in messages(result))

    def test_hold_forbids_sl_and_rr(self, full_cfg):
        action = """
        <action>
        HOLD
        SL:0090
        <RR_3>
        </action>
        """
        result = parse(full_cfg, VALID_CHART + VALID_THINK + action)
        assert any("SL không được xuất hiện" in m for m in messages(result))
        assert any("RR không được xuất hiện" in m for m in messages(result))

    def test_hold_without_sl_rr_is_clean(self, full_cfg):
        action = """
        <action>
        HOLD
        </action>
        """
        result = parse(full_cfg, VALID_CHART + VALID_THINK + action)
        assert result.is_well_formed()
        assert result.ast.action.action_type == "HOLD"
        assert result.ast.action.sl is None
        assert result.ast.action.rr is None

    def test_rr_value_extracted_correctly(self, full_cfg):
        for n in range(1, 10):
            action = f"""
            <action>
            BUY
            SL:0090
            <RR_{n}>
            </action>
            """
            result = parse(full_cfg, VALID_CHART + VALID_THINK + action)
            assert result.ast.action.rr == n


# ======================================================================
# ParseResult.well_form_score / SEVERITY_PENALTY
# ======================================================================
class TestWellFormScore:
    def test_score_decreases_with_structural_errors(self, full_cfg):
        # Thiếu <trend> -> 1 lỗi structural (0.15)
        think = """
        <think>
        <current_price>0112</current_price>
        <zone_support>0100:0110</zone_support>
        </think>
        """
        result = parse(full_cfg, VALID_CHART + think + VALID_ACTION)
        structural_count = sum(1 for e in result.errors if e.severity == "structural")
        expected = max(0.0, 1.0 - 0.15 * structural_count)
        # value-severity errors (nếu có) cũng phải được tính vào
        value_count = sum(1 for e in result.errors if e.severity == "value")
        expected = max(0.0, 1.0 - 0.15 * structural_count - 0.30 * value_count)
        assert result.well_form_score() == pytest.approx(expected)

    def test_score_never_goes_below_zero(self, full_cfg):
        # Cố tình phá nát toàn bộ input để dồn thật nhiều lỗi
        result = parse(full_cfg, "garbage garbage garbage" * 20)
        assert result.well_form_score() >= 0.0

    def test_is_well_formed_false_when_any_error(self, full_cfg):
        result = parse(full_cfg, VALID_CHART + VALID_THINK)  # thiếu action_block trong mode full
        assert not result.is_well_formed()