"""무한매수법 v4.0 엔진 검증 — 방법론 문서의 예시 숫자 그대로 재현.

실행: python tests/test_mubae.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from moap.mubae import (StockCfg, State, star_pct, star_point, one_buy_amount,
                        plan_orders, apply_fills, simulate_fills, _ladder)


def check(name, actual, expected):
    ok = actual == expected
    print(f"{'✅' if ok else '❌'} {name}: {actual}" + ("" if ok else f" (기대값 {expected})"))
    assert ok, name


# ── 1. 별% 공식 (문서 3-(2)) ─────────────────────────────
check("20분할 TQQQ 별% (T=2)", star_pct(StockCfg("TQQQ", divisions=20, target_pct=15), 2), 15 - 1.5 * 2)
check("40분할 TQQQ 별% (T=8)", star_pct(StockCfg("TQQQ", divisions=40, target_pct=15), 8), 15 - 0.75 * 8)
check("20분할 SOXL 별% (T=8.6)", round(star_pct(StockCfg("SOXL", divisions=20, target_pct=20), 8.6), 4), 2.8)
check("40분할 SOXL 별% (T=10)", star_pct(StockCfg("SOXL", divisions=40, target_pct=20), 10), 20 - 10)

# 문서 예시: 20분할 SOXL 평단 38.30, T=8.6 → 별지점 39.37
cfg20s = StockCfg("SOXL", divisions=20, target_pct=20)
st = State("SOXL", principal=20000, cash=10000, shares=100, avg_price=38.30, T=8.6)
check("별지점 (SOXL 평단38.30 T=8.6)", star_point(cfg20s, st), 39.37)

# ── 2. 1회매수금 (문서 4) ────────────────────────────────
cfg40 = StockCfg("TQQQ", divisions=40, target_pct=15)
st = State("TQQQ", principal=20000, cash=19522, T=1)
check("1회매수금 (잔금19522 T=1 40분할)", round(one_buy_amount(cfg40, st), 4), round(19522 / 39, 4))

# ── 3. 첫 매수표 (문서 5-(1): 617.89$, 종가 45.93, 큰수 51.44) ──
cfg = StockCfg("TQQQ", divisions=40, target_pct=15, big_pct=12.0, ladder_levels=3)
st = State("TQQQ", principal=24715.6, cash=24715.6, T=0, shares=0)
# 1회매수금 = 24715.6/40 = 617.89
orders = plan_orders(cfg, st, prev_close=45.93, avg5=45.93)
check("첫매수 큰수 가격", orders[0].price, 51.44)
check("첫매수 큰수 수량", orders[0].qty, 12)
check("첫매수 사다리1 (617.89/13)", orders[1].price, 47.53)
check("첫매수 사다리2 (617.89/14)", orders[2].price, 44.13)

# ── 4. 전반전 매수표 (문서 5-(2): 별지점 78.12, 평단 69.75) ──
# 예시 재현: B=539.20 → 78.11×3, 69.75×4, 사다리 67.40, 59.91
cfg = StockCfg("TQQQ", divisions=40, target_pct=15, ladder_levels=2)
st = State("TQQQ", principal=30000, avg_price=69.75, shares=50, T=4.0)  # 별% 12%
st.cash = 539.20 * (40 - 4)  # 1회매수금이 정확히 539.20 이 되도록
sp = star_point(cfg, st)
check("전반전 별지점", sp, 78.12)
orders = [o for o in plan_orders(cfg, st, prev_close=75.0, avg5=75.0) if o.side == "buy"]
check("전반전 별점매수", (orders[0].price, orders[0].qty), (78.11, 3))
check("전반전 평단매수", (orders[1].price, orders[1].qty), (69.75, 4))
check("전반전 사다리1 (539.2/8)", (orders[2].price, orders[2].qty), (67.4, 1))
check("전반전 사다리2 (539.2/9)", (orders[3].price, orders[3].qty), (59.91, 1))

# ── 5. 후반전 매수표 (문서 5-(3): 별지점 59.55 → 59.54×9, 56.85, 51.68, 47.37) ──
cfg = StockCfg("TQQQ", divisions=40, target_pct=15, ladder_levels=3)
st = State("TQQQ", principal=30000, avg_price=65.88, shares=141, T=25.0)
# 별% = 15×(1-50/40) = -3.75 → 별지점 = 65.88×0.9625 = 63.41 …
# 예시 별지점 59.55를 맞추기 위해 평단 역산: 59.55/ (1+15*(1-2*25/40)/100)
st.avg_price = round(59.55 / (1 + star_pct(cfg, 25.0) / 100), 4)
st.cash = 568.50 * (40 - 25)  # 1회매수금 568.50
orders = [o for o in plan_orders(cfg, st, prev_close=60.0, avg5=60.0) if o.side == "buy"]
check("후반전 별점매수", (orders[0].price, orders[0].qty), (59.54, 9))
check("후반전 사다리1 (568.5/10)", orders[1].price, 56.85)
check("후반전 사다리2 (568.5/11)", orders[2].price, 51.68)
check("후반전 사다리3 (568.5/12)", orders[3].price, 47.38)  # 568.5/12=47.375 반올림

# ── 6. 매도표 (문서 6: 별지점 59.55 → LOC 35개, 지정가 75.76 106개) ──
cfg = StockCfg("TQQQ", divisions=40, target_pct=15)
st = State("TQQQ", principal=30000, cash=100, shares=141, T=25.0)
st.avg_price = round(59.55 / (1 + star_pct(cfg, 25.0) / 100), 4)  # 별지점 59.55
sells = [o for o in plan_orders(cfg, st, prev_close=60.0, avg5=60.0) if o.side == "sell"]
check("쿼터매도 (141//4)", (sells[0].order_type, sells[0].price, sells[0].qty), ("LOC", 59.55, 35))
check("지정가매도 수량", (sells[1].order_type, sells[1].qty), ("LIMIT", 106))
# 평단 65.88 기준이면 지정가는 65.88×1.15 = 75.76
st.avg_price = 65.88
sells = [o for o in plan_orders(cfg, st, prev_close=60.0, avg5=60.0) if o.side == "sell"]
check("지정가매도 가격 (65.88×1.15)", sells[1].price, 75.76)

# ── 7. 리버스모드 T값 (문서 5: 40분할 T=39.5 → 매도 37.525 → 매수 38.14375) ──
cfg = StockCfg("TQQQ", divisions=40, target_pct=15)
st = State("TQQQ", principal=20000, mode="REVERSE", T=39.5, shares=200, avg_price=50.0,
           cash=400, reverse_day=0)
# 첫날: MOC 매도 200//20 = 10개
orders = plan_orders(cfg, st, prev_close=40.0, avg5=41.0)
check("리버스 첫날 MOC 매도", (orders[0].order_type, orders[0].qty), ("MOC", 10))
check("리버스 첫날 매수 없음", len(orders), 1)
# 첫날 매도 체결 반영
fills = simulate_fills([{"intent": "reverse_moc", "side": "sell", "order_type": "MOC",
                         "price": 0.0, "qty": 10, "t_inc": 0.0}], close=30.0, high=31.0)
apply_fills(cfg, st, fills, close=30.0, close_date="2026-07-01")
check("리버스 매도 후 T (39.5×0.95)", round(st.T, 4), 37.525)
check("리버스 둘째날 매도수량 (190//20)", plan_orders(cfg, st, 30.0, avg5=41.0)[0].qty, 9)
# 둘째날 쿼터매수 체결 반영
fills = simulate_fills([{"intent": "quarter_buy", "side": "buy", "order_type": "LOC",
                         "price": 40.99, "qty": 3, "t_inc": 1.0}], close=29.0, high=30.0)
apply_fills(cfg, st, fills, close=29.0, close_date="2026-07-02")
check("리버스 매수 후 T (37.525+(40-37.525)×0.25)", round(st.T, 5), 38.14375)

# ── 8. 일반모드 T 갱신/전환 ──────────────────────────────
cfg = StockCfg("TQQQ", divisions=40, target_pct=15)
st = State("TQQQ", principal=20000, cash=10000, shares=100, avg_price=50.0, T=7.0)
apply_fills(cfg, st, [{"intent": "quarter_sell", "side": "sell", "qty": 25,
                       "price": 52.0, "amount": 1300.0, "t_inc": 0}], 52.0, "d")
check("쿼터매도 T (7×0.75)", st.T, 5.25)
apply_fills(cfg, st, [{"intent": "star_half", "side": "buy", "qty": 3,
                       "price": 51.0, "amount": 153.0, "t_inc": 0.5}], 50.5, "d")
check("절반매수 T (+0.5)", st.T, 5.75)
apply_fills(cfg, st, [
    {"intent": "star_half", "side": "buy", "qty": 3, "price": 49.0, "amount": 147.0, "t_inc": 0.5},
    {"intent": "avg_half", "side": "buy", "qty": 3, "price": 49.0, "amount": 147.0, "t_inc": 1.0},
], 49.0, "d")
check("1회매수 T (+1)", st.T, 6.75)

# 소진 → 리버스 진입
st.T = 38.5
apply_fills(cfg, st, [{"intent": "avg_half", "side": "buy", "qty": 2,
                       "price": 45.0, "amount": 90.0, "t_inc": 1.0}], 45.0, "d")
check("T>39 → 리버스 진입", st.mode, "REVERSE")

# 리버스 종료: 종가 > 평단×0.85
st.reverse_day = 2
close_exit = round(st.avg_price * 0.86, 2)
apply_fills(cfg, st, [], close_exit, "d")
check("리버스 → 일반모드 복귀", st.mode, "NORMAL")

# ── 9. 사이클 종료 (전량 매도 → 원금 재설정) ─────────────
cfg = StockCfg("TQQQ", divisions=40, target_pct=15, compound=True)
st = State("TQQQ", principal=20000, cash=1000, shares=100, avg_price=50.0, T=10.0)
apply_fills(cfg, st, [
    {"intent": "quarter_sell", "side": "sell", "qty": 25, "price": 57.5, "amount": 1437.5, "t_inc": 0},
    {"intent": "limit_sell", "side": "sell", "qty": 75, "price": 57.5, "amount": 4312.5, "t_inc": 0},
], 57.5, "2026-07-03")
check("사이클 종료 후 T=0", st.T, 0.0)
check("사이클 종료 후 보유 0", st.shares, 0)
check("복리 원금 = 잔금 (1000+5750)", st.principal, 6750.0)
check("사이클 번호 증가", st.cycle_no, 2)

# ── 10. LOC 체결 시뮬레이션 ──────────────────────────────
pend = [
    {"intent": "star_half", "side": "buy", "order_type": "LOC", "price": 78.11, "qty": 3, "t_inc": 0.5},
    {"intent": "avg_half", "side": "buy", "order_type": "LOC", "price": 69.75, "qty": 4, "t_inc": 1.0},
    {"intent": "quarter_sell", "side": "sell", "order_type": "LOC", "price": 78.12, "qty": 35, "t_inc": 0},
    {"intent": "limit_sell", "side": "sell", "order_type": "LIMIT", "price": 75.76, "qty": 106, "t_inc": 0},
]
# 종가 72.0 (별점 아래, 평단 위), 고가 76.0 (지정가 위)
fills = simulate_fills(pend, close=72.0, high=76.0)
check("LOC매수(별점) 체결", fills[0]["qty"], 3)      # 72 ≤ 78.11
check("LOC매수(평단) 미체결", fills[1]["qty"], 0)    # 72 > 69.75
check("LOC매도 미체결", fills[2]["qty"], 0)          # 72 < 78.12
check("지정가매도 체결(고가 도달)", (fills[3]["qty"], fills[3]["price"]), (106, 75.76))

print("\n모든 테스트 통과 🎉")
