from typing import List
from app.tlang import (
    TLangConfig,
    Parser,
    ParseError,
    ParseResult,
    SemanticChecker,
    ProgramNode,
    CandleNode,
    ChartNode,
    ThinkNode,
    ZoneNode,
    ActionNode
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

def test_full():
    import random
    import pandas as pd
    from app.tlang import ChartCodec, plot_program
    import numpy as np
    
    n_bins = 2048
    cfg: TLangConfig = TLangConfig(
        expected_candle_count=100,
        bin_range=(0, n_bins-1),
        digit_pad=4,
        mode="full",
        zone_range=(50, 100),
        sl_range=(50, 201),
        zone_extend_multiplier=1.0,
        last_n_touch=10,
    )
    
    df = pd.read_csv("data/XAUUSD_Daily.csv")
    
    ran_idx = random.randint(0, len(df) - 200)
    df = df.iloc[ran_idx:]
    
    input_df = df.iloc[:100]
    input_window = input_df[["Open", "High", "Low", "Close"]].values
    atr = input_df["ATR_100"].values[0]
    
    future_window = df.iloc[100:200][["Open", "High", "Low", "Close"]].values
    
    codec = ChartCodec(scale=24, n_bins=n_bins)
    input_candles, anchor_open = codec._encode_input(input_window, atr)
    future_candles = codec._encode_future(future_window, anchor_open, atr)
    
    chart: ChartNode = ChartNode(candles=input_candles)
    
    program: ProgramNode = ProgramNode(
        chart=chart, 
        think=ThinkNode(
            trend="UP",
            current_price_bin=chart.current_price,
            zone=ZoneNode(
                direction="support",
                lower_bin=chart.current_price - 50,
                upper_bin=chart.current_price + 50
            )
        ),
        action=ActionNode(
            action_type="BUY",
            sl=chart.current_price - 51,
            rr=3
        )
    )
    
    from app.tlang import ASTVisitor
    ast_visitor = ASTVisitor(digit_pad=cfg.digit_pad)
    txt = ast_visitor.visit_program(program)
    test(txt, cfg)
    
    plot_program(program)

if __name__ == "__main__":
    test_mode_zone()
    test_mode_full()
    
    print("=== FULL ===")
    test_full()