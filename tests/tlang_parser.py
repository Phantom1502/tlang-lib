from app.tlang import (
    TLangConfig,
    Parser,
    ParseError,
    ParseResult,
    SemanticChecker
)

def test(text: str, cfg: TLangConfig):
    parser_result: ParseResult = Parser.from_text(
        cfg=cfg,
        text=text, 
    ).parse()
    print(parser_result)
    semantic_checker = SemanticChecker(
        cfg=cfg
    )
    print(semantic_checker.check(parser_result.ast))

def test_mode_zone():
    txt = """
    <chart>
    <O_1> <H_1> <L_1> <C_1>
    </chart>
    <think>
    <trend>UP</trend>
    <current_price>0001</current_price>
    <zone_support>0000:0003</zone_support>
    </think>
    <action>
    BUY
    SL:0000
    <RR_1>
    </action>
    """
    
    cfg: TLangConfig = TLangConfig(
        expected_candle_count=1,
        bin_range=(0, 3),
        digit_pad=4,
        mode="zone",
        zone_range=(0, 3),
        sl_range=(0, 3),
        zone_extend_multiplier=1.0,
        last_n_touch=10,
    )
    test(txt, cfg)

def test_mode_full():
    txt = """
    <chart>
    <O_1> <H_1> <L_1> <C_1>
    </chart>
    <think>
    <trend>UP</trend>
    <current_price>0001</current_price>
    <zone_support>0001:0003</zone_support>
    </think>
    <action>
    BUY
    SL:0000
    <RR_1>
    </action>
    """
    
    cfg: TLangConfig = TLangConfig(
        expected_candle_count=1,
        bin_range=(0, 3),
        digit_pad=4,
        mode="full",
        zone_range=(0, 3),
        sl_range=(0, 3),
        zone_extend_multiplier=1.0,
        last_n_touch=10,
    )
    test(txt, cfg)

if __name__ == "__main__":
    test_mode_zone()
    test_mode_full()