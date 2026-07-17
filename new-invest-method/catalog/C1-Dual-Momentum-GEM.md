# C1. Dual Momentum — GEM (Global Equities Momentum)

```yaml
name: "Dual Momentum GEM (Global Equities Momentum) v1"
origin: >
  Gary Antonacci, 저서 "Dual Momentum Investing: An Innovative Strategy for
  Higher Returns with Lower Risk" (2014). 공식 사이트 optimalmomentum.com에
  월간 시그널 공개. 절대모멘텀 개념의 최초 논문화: Antonacci, "Risk Premia
  Harvesting Through Dual Momentum" (SSRN, 2012, 2014 개정).
  참고: https://www.quantifiedstrategies.com/dual-momentum-trading-strategy/ ,
       https://reblnc.com/insights/dual-momentum ,
       https://bestfolio.app/blog/strategy-spotlight-gem
category: C (모멘텀·추세추종형)
assets:
  - ticker: SPY      # 미국 주식 (원저에서는 S&P500 인덱스/펀드)
    role: 국내(자국) 위험자산 후보
    lot_size: 정수 주
  - ticker: EFA       # 선진국(미국 제외) 주식. 커뮤니티 변형은 VEU(전세계 제외 미국) 사용
    role: 해외 위험자산 후보
    lot_size: 정수 주
  - ticker: AGG       # 미국 총채권(agg bond). 방어자산
    role: 방어자산(절대모멘텀 탈락 시)
    lot_size: 정수 주
  - ticker: BIL_or_SHY  # 무위험수익률 벤치마크(3개월 T-bill류). 매매 대상 아님, 비교 기준값
    role: 절대모멘텀 기준선(직접 보유하지 않음 — AGG로 대체 매수)
    lot_size: 해당 없음(벤치마크 전용)
state:
  numeric_type: Decimal
  held_asset: "SPY | EFA | AGG | CASH"   # 현재 보유 중인 단일 자산(GEM은 항상 1개 자산 100% 보유)
  last_evaluation_month: Date            # 마지막 평가월(월말 1회 평가 가드용)
params:
  lookback_months: 12          # 상대·절대 모멘텀 공통 관찰기간
  risk_free_proxy: "BIL(3개월 T-bill ETF) 또는 SHY(1-3년 단기채) 12개월 수익률"  # 원저는 T-bill 실효수익률 사용
  rebalance_day: "매월 마지막 거래일"
  initial_capital: 20000  # USD, 프로젝트 공통 비교 조건
rounding:
  - {항목: "12개월 수익률 계산", 모드: "반올림 없음(원시 비율로 비교만)", 자릿수: "비교용 — 표시시 소수점 4자리"}
  - {항목: "매수 주식수", 모드: DOWN, 자릿수: "정수(lot_size=1주)"}
schedule:
  evaluation_frequency: "월 1회 (월말 마지막 거래일 종가 기준)"
  trigger_condition: "월말 평가 시점에만 판단 — 월중에는 어떤 신호도 무시(월 1회 재구성 원칙)"
cycle_definition:
  trigger: "해당 없음 — GEM은 무한매수식 사이클이 아니라 매월 재평가하는 상태전환형 전략"
  resets: "없음 (T값·pool 등 누적 상태 없음, 매월 독립 판단)"
  carries: "보유 자산 자체가 상태이며 리밸런싱 시 전량 교체"
mode_transition:
  states: [HOLD_SPY, HOLD_EFA, HOLD_AGG, ALL_CASH_TRANSIENT]
  transitions:
    - {from: ANY, to: HOLD_SPY, condition: "SPY_12m_return > EFA_12m_return AND SPY_12m_return > riskfree_12m_return"}
    - {from: ANY, to: HOLD_EFA, condition: "EFA_12m_return >= SPY_12m_return AND EFA_12m_return > riskfree_12m_return"}
    - {from: ANY, to: HOLD_AGG, condition: "max(SPY_12m_return, EFA_12m_return) <= riskfree_12m_return  # 절대모멘텀 탈락 → 방어자산"}
order_roles:
  - {role: MONTHLY_REBALANCE_SELL, 설명: "월말 목표자산과 현재 보유자산이 다르면 보유분 전량 매도"}
  - {role: MONTHLY_REBALANCE_BUY, 설명: "매도 대금(+기존 현금)으로 목표자산 전량 매수"}
fill_interaction_rules:
  - "GEM은 항상 단일자산 100% 보유 — 매도·매수 체결은 같은 리밸런싱일에 순차 실행(매도 체결 후 매수)되며 조합별 특수 상태갱신 규칙 없음"
rules: |
  # 매월 마지막 거래일 종가 기준 (pseudocode)
  def monthly_rebalance(prices, riskfree_series, today):
      if not is_last_trading_day_of_month(today):
          return NO_ACTION

      spy_r  = total_return(prices["SPY"], lookback_months=12)
      efa_r  = total_return(prices["EFA"], lookback_months=12)
      rf_r   = total_return(riskfree_series, lookback_months=12)  # 절대모멘텀 기준

      # 1) 상대모멘텀: SPY vs EFA 승자 결정
      winner = "SPY" if spy_r >= efa_r else "EFA"
      winner_return = spy_r if winner == "SPY" else efa_r

      # 2) 절대모멘텀: 승자 vs 무위험수익률
      if winner_return > rf_r:
          target = winner            # SPY 또는 EFA 100%
      else:
          target = "AGG"             # 방어자산으로 전환

      if target != state.held_asset:
          sell_all(state.held_asset)   # MONTHLY_REBALANCE_SELL
          buy_all(target)              # MONTHLY_REBALANCE_BUY
          state.held_asset = target

      state.last_evaluation_month = today
orders:
  type: "시장가/MOC 가정 (원저는 일중 체결 시점 특정하지 않음 — 백테스터는 월말 종가 체결로 근사)"
  note: "실거래에서는 지정가 대신 월말 종가 부근 시장가 주문이 일반적 관행"
fee_model:
  commission_rate_bps: "브로커 수수료율 파라미터화 (예: 0.05% 편도 가정)"
  turnover: "낮음~중간 — 연 2~5회 정도 자산 교체가 전형적(추세 지속 구간에서는 무교체)"
dividend_handling: >
  분배금은 재투자 가정(총수익 기준 12개월 수익률 계산 — Adjusted Close 또는 배당 재투자 지수 사용).
  단, PLAN.md 4.3 원칙(원종가+배당 별도 현금흐름)과 정합성 위해 백테스터 구현 시 모멘텀 계산용
  수익률만 배당조정가로 산출하고 실제 체결가는 원종가를 쓰는 이원화가 필요함 — 구현 시 결정 필요(가정 표시).
cash_profile: >
  절대모멘텀 탈락 시에도 AGG(채권)로 이동하므로 순수 현금 보유 구간은 없음(GEM 표준형).
  일부 변형은 AGG 대신 단기국채/현금을 쓰기도 함 — 본 문서는 표준 3자산(SPY/EFA/AGG) 기준.
risk_notes: >
  절대모멘텀 필터가 완만한 하락장(수년간 옆으로 횡보하며 서서히 하락)에서는 뒤늦게 작동할 수 있음.
  2014~2022 강세장 구간에서는 S&P500 단순보유 대비 열위였다는 지적 다수(방어 메커니즘이 거의
  발동하지 않았기 때문). 월 1회 판단이라 월중 급락에 대한 대응은 다음 평가월까지 지연됨(가정: 이는
  전략의 설계 의도이며 결함이 아님).
automation: >
  KIS API로 자동화 난이도 낮음 — 월 1회 배치(마지막 거래일 종가 확인 후 자산 교체)만 필요.
  LOC/MOC 어느 쪽이든 무방(월말 종가 근접 체결이면 충분). 무매/VR처럼 매일 계산할 필요 없음.
backtest_notes: >
  체결가는 월말 거래일 종가(MOC 가정) 사용. 12개월 수익률은 절대 수익률(단순 수익률)이며
  로그수익률이 아님 — 원저 명시. 무위험수익률 계열(BIL vs SHY)에 따라 결과가 미세하게 달라질 수
  있어 두 옵션을 파라미터로 두고 민감도 확인 권장(가정: 본 프로젝트는 SHY를 기본값으로 채택,
  BIL 데이터 확보 어려우면 SHY로 대체).
```

## 미확정/가정 요약
- **무위험수익률 벤치마크 소스**: 원저는 90일 T-bill 실효수익률을 쓰나, 백테스트 편의상 BIL 또는
  SHY ETF 12개월 수익률로 근사 — 어느 쪽을 표준으로 할지 결정 필요(가정: SHY 우선).
- **EFA vs VEU**: 최신 대중 재현본은 VEU(전세계 제외 미국, 신흥국 포함)를 쓰기도 함. 원저 표준은
  EFA(선진국 한정) — 본 문서는 EFA 기준, VEU는 옵션 각주로만 취급.
- **배당 처리**: 모멘텀 계산에 배당조정가를 쓸지, 원종가+배당 현금흐름을 쓸지는 PLAN.md 데이터
  방침과 충돌 소지 있어 구현 단계에서 확정 필요.
- **체결가정**: 월말 "종가 부근 체결"이 원저의 실제 관행이나, MOC/지정가 등 구체적 주문유형은
  원저에 특정되어 있지 않음 — 백테스터 편의상 MOC(종가체결)로 통일 가정.
