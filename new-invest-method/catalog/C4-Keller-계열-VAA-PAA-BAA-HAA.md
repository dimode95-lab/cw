# C4. Keller 계열 자산배분 — VAA / PAA / BAA / HAA 통합

> Wouter J. Keller(Vrije Universiteit Amsterdam)와 Jan Willem Keuning이
> SSRN에 공개한 일련의 "카나리아 자산(canary asset)" 기반 전술적 자산배분
> 논문 계열. 본 문서는 PLAN.md 지시대로 **VAA-G4와 BAA를 대표로 상세 기술**하고,
> PAA·HAA는 계보·차별점만 간결히 정리한다. 모든 전략이 공통으로 쓰는
> **13612W 모멘텀 공식**과 **카나리아 자산 개념**을 먼저 정의한다.

## 0. 공통 개념

### 13612W 모멘텀 (VAA/PAA/DAA 계열이 쓰는 가중 모멘텀)
```
13612W(asset) = 12 × R(1개월) + 4 × R(3개월) + 2 × R(6개월) + 1 × R(12개월)
                 ───────────────────────────────────────────────────────
                                        19
```
R(n개월) = 최근 n개월 단순수익률(가격비율-1). 가중치(12,4,2,1)는 최근 1개월 수익률에
"연환산 관점에서 동일 크기"가 되도록 설계된 것 — 최근월에 극도로 민감한 필터.
(HAA는 이와 달리 **13612U**(Unweighted, 균등가중 평균) 사용 — §4 참조)
출처: https://trendxplorer1.rssing.com/chan-11399986/all_p4.html ,
      Keller & Keuning, "Breadth Momentum and Vigilant Asset Allocation (VAA)" (SSRN
      abstract_id=3002624)

### 카나리아(canary) 자산
포트폴리오 실제 보유와 분리된 **별도의 신호 전용 자산 그룹**. 카나리아 자산들의
13612W 모멘텀이 양(+)인지 음(-)인지만 보고 "나쁜(bad) 자산 개수"를 세어 공격
자산군 비중을 얼마나 방어자산군으로 돌릴지 결정한다("광산의 카나리아" 비유 —
위험을 먼저 감지해 경보). DAA(Defensive Asset Allocation) 논문에서 최초 도입,
VAA/PAA/BAA/HAA가 공통 채택.
출처: https://www.researchgate.net/publication/326859452

---

## 1. VAA-G4 (Vigilant Asset Allocation, Global-4) — 대표 상세

```yaml
name: "VAA-G4 (Vigilant Asset Allocation, Global 4-asset)"
origin: >
  Wouter J. Keller, Jan Willem Keuning, "Breadth Momentum and Vigilant Asset
  Allocation (VAA): Winning More by Losing Less" (SSRN, 2017).
  https://papers.ssrn.com/sol3/papers.cfm?abstract_id=3002624
  해설: https://allocatesmartly.com/vigilant-asset-allocation-dr-wouter-keller-jw-keuning/
category: C (모멘텀·추세추종형)
assets:
  offensive_and_canary_universe:   # VAA-G4는 공격자산군 = 카나리아 자산군 (동일 4개)
    - {ticker: SPY, role: "미국 주식"}
    - {ticker: VEA, role: "선진국(미국 제외) 주식"}
    - {ticker: VWO, role: "신흥국 주식"}
    - {ticker: BND, role: "미국 총채권"}
  defensive_universe:               # 방어(현금) 자산군 — 카나리아 경보 시 여기서 선택
    - {ticker: SHY, role: "단기국채(1-3년)"}
    - {ticker: IEF, role: "중기국채(7-10년)"}
    - {ticker: LQD, role: "투자등급 회사채"}
  lot_size: 정수 주 (전량 ETF)
state:
  numeric_type: Decimal
  held_assets: "최대 2개 티커 + 비중 (offensive 100% 또는 defensive 100%)"
  bad_canary_count: "정수 0~4 — 매월 평가 시 계산되는 중간값"
params:
  breadth_threshold_T: 1     # VAA-G4는 "T=1개 자산 보유"가 기본형(가장 공격적 변형)
  top_n_when_all_clear: 1    # 카나리아 전원 양호 시 공격자산군 중 13612W 1위 1개 자산 100% 보유
  rebalance_day: "매월 마지막 거래일"
  initial_capital: 20000
rounding:
  - {항목: "13612W 모멘텀", 모드: "반올림 없음", 자릿수: "표시 시 소수점 4자리"}
  - {항목: "매수 주식수", 모드: DOWN, 자릿수: 정수}
schedule:
  evaluation_frequency: "월 1회 (월말)"
  trigger_condition: "매월 무조건 카나리아 판정 → 목표자산 재계산 → 필요시 전량 교체"
cycle_definition:
  trigger: "해당 없음 — 매월 독립 재평가형"
  resets: "없음"
  carries: "없음"
mode_transition:
  states: [OFFENSIVE_100, DEFENSIVE_100]
  transitions:
    - {from: ANY, to: OFFENSIVE_100,
       condition: "bad_canary_count == 0  # SPY/VEA/VWO/BND 4개 모두 13612W > 0"}
    - {from: ANY, to: DEFENSIVE_100,
       condition: "bad_canary_count >= 1  # 4개 중 1개라도 13612W <= 0 이면 즉시 전량 방어 전환"}
  note: >
    VAA는 "any negative" 트리거 — DAA(카나리아 2개, breadth 비례식)보다 훨씬 민감(느슨한
    breadth 비례가 아니라 이산 스위치형). bad_canary_count가 1이든 4든 결과는 동일하게
    DEFENSIVE_100(G4 기본형 기준 — G12 변형은 breadth 비례 배분도 있음, 본 문서는 G4만 상세)
order_roles:
  - {role: VAA_REBAL_SELL, 설명: "목표자산이 현재 보유와 다르면 전량 매도"}
  - {role: VAA_REBAL_BUY, 설명: "매도대금으로 목표자산(공격 1개 또는 방어 1개) 전량 매수"}
fill_interaction_rules:
  - "GEM과 동일하게 항상 단일자산 100% 보유(G4 기본형) — 조합별 특수 규칙 없음"
rules: |
  def monthly_rebalance(prices, today):
      if not is_last_trading_day_of_month(today):
          return NO_ACTION

      canary = ["SPY","VEA","VWO","BND"]
      mom = {t: momentum_13612w(prices[t]) for t in canary}
      bad_count = sum(1 for t in canary if mom[t] <= 0)

      if bad_count == 0:
          target = max(canary, key=lambda t: mom[t])         # 공격 1위 자산
      else:
          defensive = ["SHY","IEF","LQD"]
          def_mom = {t: momentum_13612w(prices[t]) for t in defensive}
          target = max(defensive, key=lambda t: def_mom[t])  # 방어 1위 자산

      if target != state.held_asset:
          sell_all(state.held_asset)   # VAA_REBAL_SELL
          buy_all(target)              # VAA_REBAL_BUY
          state.held_asset = target
orders:
  type: "MOC 가정(월말 종가 근접 체결) — 원문은 체결 메커니즘을 특정하지 않음"
fee_model:
  commission_rate_bps: "파라미터화"
  turnover: "GEM보다 다소 높음 — 카나리아 판정이 4자산 각각의 부호에 의존해 더 민감하게 전환"
dividend_handling: "배당 재투자 가정(모멘텀 계산에 총수익 반영) — GEM과 동일 이슈"
cash_profile: "항상 방어자산(채권 ETF) 100% 또는 공격자산 100% — 순수 현금 보유 없음"
risk_notes: >
  "any negative" 트리거는 민감한 만큼 잦은 오탐(false alarm)에 취약 — 2022년처럼 채권·주식이
  동반 약세인 국면에서는 카나리아 4개 전원이 쉽게 나빠져 방어 전환이 잦고, 방어자산(채권)도
  동반 하락하면 방어 효과가 제한적일 수 있음(2022 실측 사례가 BestFolio 등에서 논의됨).
automation: "GEM과 유사 — 월 1회 배치, 자산 4개+방어 3개 총 7개 티커의 13612W 계산만 필요."
backtest_notes: >
  13612W는 1,3,6,12개월 수익률이 모두 필요 — 최소 12개월 워밍업 데이터 필요. G4는 미국편중
  카나리아가 없어(글로벌 4자산) 해외자산 데이터(VEA/VWO) 확보 필요.
```

---

## 2. BAA (Bold Asset Allocation) — 대표 상세

```yaml
name: "BAA-G4 (Aggressive) / BAA-G12 (Balanced)"
origin: >
  Wouter J. Keller, "Relative and Absolute Momentum in Times of Rising/Low
  Yields: Bold Asset Allocation (BAA)" (SSRN, abstract_id=4166845).
  https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4166845
  해설: https://allocatesmartly.com/bold-asset-allocation/ ,
       https://www.turingtrader.com/portfolios/keller-bold-asset-allocation/
category: C (모멘텀·추세추종형)
assets:
  canary_universe:                  # G4/G12 공통 — VAA-G4와 동일 4자산
    - {ticker: SPY, role: "카나리아1"}
    - {ticker: VEA, role: "카나리아2"}
    - {ticker: VWO, role: "카나리아3"}
    - {ticker: BND, role: "카나리아4"}
  offensive_universe_G4:            # 공격적(Aggressive) 변형 — 4자산 중 Top1
    - {ticker: QQQ, note: "카나리아의 SPY 대신 QQQ로 대체(더 공격적) — 출처 해설 기준"}
    - {ticker: VEA}
    - {ticker: VWO}
    - {ticker: BND}
  offensive_universe_G12:           # 균형(Balanced) 변형 — 12자산 중 Top6 (가정: 정확한 12종목
                                     # 리스트는 원문 PDF 표에서만 확인 가능 — 본 문서는 미확정 처리)
    note: "미확인 — 미국/해외주식·리츠·원자재·금·장기국채·회사채·하이일드 등 12종 혼합으로
           추정되나 정확한 티커 리스트는 SSRN 원문 표 확인 필요 (가정 표시)"
  defensive_universe:                # 카나리아 경보 시 방어자산 선택 풀
    - {ticker: BIL_or_SHY, note: "단기국채/현금성"}
    - {ticker: IEF, note: "중기국채"}
    - {ticker: LQD, note: "투자등급 회사채"}
    note: "정확한 방어자산군 구성(3종 vs 그 이상)은 원문 표 확인 필요 (가정)"
state:
  numeric_type: Decimal
  held_assets: "G4: 1개 자산 100%. G12: 최대 6개 자산 균등가중(각 1/6)"
  bad_canary_count: "정수 0~4"
params:
  canary_breadth_B: 1     # "1개 이상 카나리아 나쁨 → 전량 방어 전환"
  top_n_offense_G4: 1
  top_n_offense_G12: 6    # 상위 6개 균등가중
  ranking_metric: "SMA12 상대모멘텀 — 가격/12개월 단순이동평균 - 1 (카나리아의 13612W와 다른 지표)"
  rebalance_day: "매월 마지막 거래일"
  initial_capital: 20000
rounding:
  - {항목: "SMA12 상대모멘텀, 13612W(카나리아용)", 모드: "반올림 없음", 자릿수: "표시 시 4자리"}
  - {항목: "매수 주식수", 모드: DOWN, 자릿수: 정수}
schedule:
  evaluation_frequency: "월 1회"
  trigger_condition: "매월 카나리아 판정 → 공격/방어 유니버스에서 종목 선정 → 리밸런싱"
cycle_definition: {trigger: "해당 없음", resets: "없음", carries: "없음"}
mode_transition:
  states: [OFFENSE, DEFENSE]
  transitions:
    - {from: ANY, to: OFFENSE, condition: "bad_canary_count == 0"}
    - {from: ANY, to: DEFENSE, condition: "bad_canary_count >= canary_breadth_B(=1)"}
  note: >
    OFFENSE 진입 시: 공격 유니버스(G4는 4종 중 SMA12 1위, G12는 12종 중 SMA12 상위 6종
    균등가중) 매수. DEFENSE 진입 시: 방어 유니버스에서 SMA12 상위 자산 선택(단, "SHY/BIL 등
    무위험자산보다 모멘텀이 낮은 방어자산은 제외하고 대체" — 절대모멘텀 필터 추가 적용,
    해설 자료 기준: "if any of these assets show less momentum than BIL, they're substituted out")
order_roles:
  - {role: BAA_OFFENSE_BUY, 설명: "카나리아 전원 양호 시 공격 유니버스 목표종목 매수"}
  - {role: BAA_DEFENSE_BUY, 설명: "카나리아 1개 이상 불량 시 방어 유니버스 목표종목 매수"}
  - {role: BAA_REBAL_SELL, 설명: "목표 구성과 다른 기존 보유분 매도"}
fill_interaction_rules:
  - "G12는 최대 6종목 동시 보유 — 월별 재구성 시 기존 보유 중 이번달 상위6에서 탈락한 종목은
    매도, 신규 진입 종목은 매수, 유지 종목은 무거래(회전율 절감) — 원문 명시는 아니나 통상적
    구현 관례로 가정."
rules: |
  def monthly_rebalance(prices, today):
      if not is_last_trading_day_of_month(today):
          return NO_ACTION

      canary = ["SPY","VEA","VWO","BND"]
      bad_count = sum(1 for t in canary if momentum_13612w(prices[t]) <= 0)

      if bad_count == 0:
          # OFFENSE
          universe = OFFENSIVE_G4 if variant == "G4" else OFFENSIVE_G12
          ranked = sorted(universe, key=lambda t: sma12_momentum(prices[t]), reverse=True)
          top_n = 1 if variant == "G4" else 6
          targets = {t: 1.0/top_n for t in ranked[:top_n]}
      else:
          # DEFENSE — 방어 유니버스 중 BIL 대비 모멘텀 열위 자산은 제외 후 상위 선택(가정: top1)
          eligible = [t for t in DEFENSIVE if sma12_momentum(prices[t]) > sma12_momentum(prices["BIL"])]
          pool = eligible if eligible else ["BIL"]
          best = max(pool, key=lambda t: sma12_momentum(prices[t]))
          targets = {best: 1.0}

      rebalance_to(targets)   # 기존 보유 중 미포함분 매도(BAA_REBAL_SELL) + 신규매수(BAA_*_BUY)
orders:
  type: "MOC 가정(월말 종가 근접 체결)"
fee_model:
  commission_rate_bps: "파라미터화"
  turnover: "G4 > G12 (G4는 1자산 집중이라 자산 교체 시 회전율이 더 크게 튐, G12는 6종목 분산이라
             부분 교체로 완충됨)"
dividend_handling: "배당 재투자 가정"
cash_profile: "카나리아 경보 시에도 순수 현금이 아니라 방어자산(채권 등) 보유"
risk_notes: >
  BAA는 방어 유니버스에서 절대모멘텀 필터(BIL 대비)를 추가로 적용해 "약한 방어자산마저
  회피"하는 이중 방어 구조 — VAA-G4보다 방어 국면 손실을 더 줄이는 설계 의도(원문 성과
  주장: 2022년 국면에서 상대적으로 선방). 다만 자산군이 12개(G12)로 늘어나는 만큼 구현·검증
  복잡도가 높고, 정확한 G12 종목 리스트를 확인하지 못하면 재현 오차가 커질 위험 있음.
automation: >
  G4는 VAA-G4와 자동화 난이도 유사(월 1회, 소수 자산). G12는 다자산 랭킹·균등가중 리밸런싱
  로직이 필요해 구현 난이도가 다소 높음.
backtest_notes: >
  G12의 정확한 12종목 리스트가 미확정이므로, 코드 구현 우선순위는 BAA-G4(4종목, VAA-G4와
  카나리아 자산 재사용 가능)를 권장. G12는 원문 SSRN PDF의 종목 표를 직접 확인한 뒤 착수할 것.
```

---

## 3. PAA (Protective Asset Allocation) — 계보·차별점만 간결 정리

```yaml
name: "PAA (Protective Asset Allocation)"
origin: >
  Keller & Keuning, "Protective Asset Allocation (PAA): A Simple Momentum-Based
  Alternative for Term Deposits" (SSRN, abstract_id=2759734, 2016).
  해설: https://allocatesmartly.com/protective-asset-allocation/
category: C
요약: >
  VAA/BAA보다 앞서 발표된 원조 격 모델. 모멘텀을 MOM(asset) = 종가/SMA(lookback개월) - 1
  로 정의(13612W가 아닌 단순 SMA 대비 괴리율). "보호계수(protection factor) a ∈ {0,1,2}"를
  두어 카나리아 나쁜 자산 비율에 비례해 현금 비중을 조절하는 것이 VAA의 이산적 "all-or-nothing"
  스위치와의 핵심 차이 — a가 클수록 카나리아 신호에 더 공격적으로(현금 비중을 더 크게) 반응.
  카나리아 개념(별도 신호 전용 자산군)은 PAA에서 이미 등장하며 VAA/DAA/BAA가 계승.
차별점_vs_VAA_BAA: >
  - 모멘텀 지표: PAA는 SMA 괴리율, VAA/BAA 카나리아는 13612W.
  - 방어 강도: PAA는 protection factor로 현금 비중을 연속적(비례식)으로 조절 가능,
    VAA-G4는 이산 스위치(bad_count>=1 → 전량 방어).
자동화_비고: "월 1회 배치, VAA와 유사한 난이도 — 1차 구현 우선순위 낮음(BAA-G4로 대체 가능한
             유사 계열로 판단, PLAN.md는 VAA-G4/BAA를 대표로 지정)"
```

## 4. HAA (Hybrid Asset Allocation) — 계보·차별점만 간결 정리

```yaml
name: "HAA (Hybrid Asset Allocation)"
origin: >
  Keller & Keuning, "Dual and Canary Momentum with Rising Yields/Inflation:
  Hybrid Asset Allocation (HAA)" (SSRN, abstract_id=4346906, 2023).
  해설: https://allocatesmartly.com/hybrid-asset-allocation/ ,
       https://indexswingtrader.blogspot.com/2023/02/introducing-hybrid-asset-allocation-haa.html
category: C
요약: >
  가장 최신(2023) 모델. 카나리아 자산이 **단 1개**(TIP, 물가연동국채)로 단순화된 것이 특징 —
  "금리 상승/인플레 국면"에 특화 설계. 모멘텀 계산은 13612W가 아니라 **13612U**(1,3,6,12개월
  수익률의 단순 평균, 가중치 없음)를 사용. 공격 유니버스 9자산 중 13612U 상위 4개를 균등가중
  보유, 카나리아(TIP) 모멘텀이 음(-)이면 방어 유니버스(BIL, IEF 2자산 중 택1 또는 배분)로 전환.
차별점_vs_VAA_BAA: >
  - 카나리아 자산 수: HAA=1개(TIP) vs VAA/BAA=4개(SPY/VEA/VWO/BND) — HAA가 훨씬 단순.
  - 모멘텀 공식: HAA는 13612U(균등가중) vs VAA/BAA canary는 13612W(최근월 가중).
  - 설계 의도: HAA는 금리 상승기 채권 카나리아의 오탐(2022년형 채권·주식 동반 약세)을
    줄이기 위해 물가연동국채(TIP)를 카나리아로 채택한 것으로 해설됨(가정: 원문 저자 의도를
    2차 해설 기준으로 요약, 원문 직접 확인 권장).
자동화_비고: "카나리아 1개로 VAA/BAA보다 더 단순 — 1차 구현 우선순위는 낮으나(PLAN.md는
             VAA-G4/BAA를 대표 지정), 코드 재사용성이 높아 VAA-G4 구현 후 추가 확장 후보로 적합."
```

## 미확정/가정 항목 요약

1. **BAA-G12 정확한 12종목 리스트**: 원문 SSRN PDF 표를 직접 확인하지 못함 — 미국/해외
   주식·리츠·원자재·금·국채·회사채·하이일드 혼합으로 추정만 함(가정). 코드 구현 전 원문 표
   대조 필수.
2. **BAA-G12 정확한 방어 유니버스 종목 수·구성**: 3종(BIL/IEF/LQD)으로 가정했으나 원문에서
   G4/G12가 방어 유니버스를 공유하는지, 다른지 확인 필요.
3. **BAA 방어 유니버스 절대모멘텀 필터 세부**: "BIL 대비 열위 자산 제외"라는 규칙의 정확한
   대체(substitution) 로직(예: 그 다음 순위로 대체하는지, 전액 BIL로 가는지)은 2차 해설
   문구("substituted out")만 확인, 원문 수식은 미확인 — pseudocode는 합리적 해석으로 가정.
4. **VAA-G4 vs BAA-G4의 공격 유니버스 차이(SPY vs QQQ)**: 2차 해설(BestFolio)에서 "BAA-G4는
   VAA-G4 유니버스를 쓰되 QQQ로 대체한 aggressive 버전"이라 설명하나, 카나리아 자산까지 QQQ로
   바뀌는지 아니면 카나리아는 SPY 그대로 두고 공격자산 선택 풀만 QQQ로 바뀌는지 원문 표
   미확인 — 본 문서는 후자(카나리아=SPY 고정, 공격자산 선택 풀만 QQQ)로 가정.
5. **PAA protection factor a의 정확한 산식**: a값에 따른 현금비중 비례식(예: cash% = bad_count/
   universe_size × (a 관련 계수))의 정확한 수식은 원문 미확인 — 1차 구현 대상이 아니므로 상세
   pseudocode는 생략.
6. **13612W/13612U 배당조정 여부**: 모든 Keller 계열 모멘텀 계산에 배당 재투자 총수익 데이터를
   쓰는지 원종가만 쓰는지 원문에 명시적 언급을 찾지 못함 — GEM과 동일하게 "총수익 기준 모멘텀
   계산 + 원종가 체결" 이원화를 가정.
7. **BAA 실제 대표 변형 선택**: PLAN.md는 "BAA를 대표로"라고만 지시 — G4(Aggressive)와
   G12(Balanced) 중 1차 코드 구현은 원문 확인이 쉬운 G4를 우선 권장(본 문서 backtest_notes 참고).
