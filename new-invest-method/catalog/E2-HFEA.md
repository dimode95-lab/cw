# E2. HFEA — Hedgefundie's Excellent Adventure (UPRO/TMF 리스크 패리티)

★ 1차 코드 구현 대상. Bogleheads 포럼발 커뮤니티 전략이지만 규칙이 완전히 공개돼 있고, "3배 레버리지
ETF + 규칙적 리밸런싱"이라는 구조가 무한매수법·합성 TQQQ와 직접 비교 가능해 코어 6종에 포함.

## origin

- 창안자: Bogleheads 포럼 유저 "Hedgefundie" (익명 핸들). 2019년 2월 최초 스레드 게시.
- 원문 스레드 ①(원조, 40/60 제안): *"HEDGEFUNDIE's excellent adventure [risk parity strategy using
  3x leveraged ETFs]"*, Bogleheads.org (2019-02):
  https://www.bogleheads.org/forum/viewtopic.php?t=272007
- 원문 스레드 ②(속편, 55/45로 개정 이후 장기 추적): *"HEDGEFUNDIE's excellent adventure Part II:
  The next journey"*:
  https://www.bogleheads.org/forum/viewtopic.php?t=288192
- 커뮤니티 정리 자료:
  - https://www.optimizedportfolio.com/hedgefundie-adventure/
  - https://www.etfcentral.com/news/hedgefundies-excellent-adventure-3x-leveraged-etf-portfolio
  - 백테스트 시각화: https://curvo.eu/backtest/en/portfolio/hfea--NoIgEgYgoggiA0xQQEoAY0EY0HYCseAbJpgmgHR4C6iIAklBgEIQCyhAKgMJ4AcZlKkKA

## category

E (레버리지 운용 프레임) — 다만 실행 규칙이 완전 기계적(리밸런싱 규칙만)이라 백테스트 구현은
B(리밸런싱형) 계열과 사실상 동일한 패턴.

## assets

| 티커 | 설명 | 비중 |
|---|---|---|
| UPRO | ProShares UltraPro S&P500 (S&P500 일간수익률 3배) | 55% |
| TMF | Direxion Daily 20+ Year Treasury Bull 3X (ICE 20년+ 국채지수 일간수익률 3배) | 45% |

lot_size: 정수 주 (KIS 미국주식 제약).

## state

| 변수 | 타입 | 설명 |
|---|---|---|
| `last_rebalance_date` | date | 마지막 분기 리밸런싱 실행일 |
| `next_eval_date` | date | 다음 평가(리밸런싱 후보)일 — 분기 첫 거래일 |
| `carry_cash` | Decimal | 정수 주 절사로 남은 잔여 현금(다음 리밸런싱까지 이월) |

`numeric_type`: 금액·비중 계산은 Decimal. 상태기계(mode_transition)는 없음 — 목표비중이 고정된
단순 주기적 리밸런싱.

## params

| 파라미터 | 기본값 | 설명 |
|---|---|---|
| `target_weights` | `{UPRO: 0.55, TMF: 0.45}` | **2019-08 개정 이후 확정 비중** (아래 "배분 비중 변경 이력" 참조) |
| `rebalance_frequency` | 분기 (연 4회) | 1·4·7·10월 **첫 거래일** |
| `rebalance_band` | 없음(순수 캘린더 방식) | 원문 스레드에서 밴드 리밸런싱·변동성 타겟팅 등 변형이 파생됐으나
  **정식 규칙은 순수 분기 캘린더 리밸런싱** — 변형은 참고만 |
| `initial_capital` | $20,000 (백테스터 공통 조건) | |

## schedule

- `evaluation_frequency`: 매 거래일 `on_bar` 호출, 전략 내부에서 "오늘이 분기 첫 거래일인가"만 판단.
- `trigger_condition`: `today == 해당 분기(1/4/7/10월)의 첫 거래일`이면 리밸런싱 실행. 원문 규칙은
  "1월·4월·7월·10월 첫 거래일에 리밸런싱"으로 알려져 있음 — Bogleheads 포럼·White Coat Investor
  포럼 등에서 공통적으로 인용되는 관행값 (정확한 날짜 산정은 거래소 캘린더 기준 첫 개장일).

## cycle_definition

- HFEA는 무한매수법과 달리 "포지션 소진 → 리셋"되는 사이클 개념이 없음 — **영구 보유 + 주기적
  리밸런싱**이 전부. `trigger`/`resets`/`carries` 필드는 리밸런싱 이벤트 단위로만 의미를 가짐:
  - `trigger`: 분기 첫 거래일 도래.
  - `resets`: 없음(상태 자체가 거의 없음).
  - `carries`: 정수 주 절사 잔여 현금(`carry_cash`)만 다음 리밸런싱까지 이월.

## mode_transition

없음(N/A) — 단일 상태(목표비중 고정) 반복. 다만 **배분 비중 자체가 전략 역사상 한 번 개정된 사실**은
반드시 문서에 남겨야 함(아래).

### 배분 비중 변경 이력 (확정 규칙)

1. **원안 (2019-02, 최초 스레드)**: UPRO 40% / TMF 60%. 주식과 장기국채의 "리스크 패리티(risk
   parity)"가 대략 40:60에서 성립한다는 논리(변동성 기준 균형).
2. **개정 (2019-08)**: UPRO 55% / TMF 45%로 변경. Hedgefundie가 향후 채권 수익률 하락(저금리 지속)을
   예상해 주식 비중을 원래의 "리스크 패리티 최적값(40/60)"보다 높였다고 설명.
3. 이후 포럼 참여자들 사이에서 월간 리밸런싱, 밴드 리밸런싱(예: ±X%p 이탈 시만), 변동성 타겟팅 등
   다양한 변형이 파생됐으나, **"HFEA"로 통칭될 때 가장 널리 인용되는 확정 규칙은 55/45 비중 + 분기
   캘린더 리밸런싱**이며 본 카탈로그의 구현 스펙도 이를 기준으로 한다.
   출처: https://www.bogleheads.org/forum/viewtopic.php?t=288192 (Part II 스레드, 개정 배경 논의),
   https://www.optimizedportfolio.com/hedgefundie-adventure/

## order_roles

| role | 설명 | 상태갱신 |
|---|---|---|
| `REBALANCE_BUY` | 목표비중 대비 부족한 자산 매수 | 체결 후 포트폴리오 비중 갱신 |
| `REBALANCE_SELL` | 목표비중 대비 초과한 자산 매도 | 체결 후 포트폴리오 비중 갱신 |

## fill_interaction_rules

- 분기 평가일에 UPRO·TMF 두 종목의 매수/매도 주문이 **동시에** 발생할 수 있음(한쪽은 팔고 한쪽은
  사는 전형적 리밸런싱). 두 체결이 같은 날 이뤄져도 상태갱신 로직에 비선형 상호작용은 없음 —
  각 종목별로 독립적으로 목표비중에 맞춰 수량을 계산.
- 매도를 먼저 체결시켜 확보한 현금으로 매수 자금을 대는 구조가 이상적이나(당일 매도대금 매수 재사용),
  MOC 동시 주문은 실제로는 같은 날 종가로 양쪽이 동시 체결되므로 백테스트에서는 "당일 리밸런싱 후
  포트폴리오 전체를 목표비중에 맞춘 최종 상태"로 계산하면 충분(현금 확보 선후관계를 별도로 모델링할
  필요 없음).

## rounding

| 항목 | 모드 | 자릿수 |
|---|---|---|
| 목표 금액 `target_value_i = portfolio_total_value × target_weights[i]` | HALF_UP | 센트(소수 2자리) |
| 목표 수량 `target_qty_i = floor(target_value_i / price_i)` | **ROUND_DOWN (내림)** | 정수 주 |
| 주문 수량 `order_qty_i = target_qty_i - current_qty_i` | 그대로(정수 차) | 정수 주 (음수면 매도) |
| 리밸런싱 후 잔여 현금(양쪽 다 정수 주 절사 후 남는 금액) | 그대로 보관 | `carry_cash`에 누적, 다음
  분기 `portfolio_total_value` 계산 시 현금으로 포함(자연 반영) |

## rules (의사코드)

```python
def on_bar(state, bars, portfolio):
    today = bars["UPRO"].date
    if today < state.next_eval_date:
        return []
    # 분기 첫 거래일 도래 — 리밸런싱 실행
    total_value = portfolio.cash + sum(
        portfolio.qty[t] * bars[t].close for t in ("UPRO", "TMF")
    )
    orders = []
    for ticker, weight in params.target_weights.items():
        target_value = total_value * weight
        target_qty = floor(target_value / bars[ticker].close)   # ROUND_DOWN
        delta = target_qty - portfolio.qty[ticker]
        if delta != 0:
            side = BUY if delta > 0 else SELL
            orders.append(Order(ticker, side, MOC, qty=abs(delta), role="REBALANCE_BUY" if delta>0 else "REBALANCE_SELL"))
    return orders

def on_fill(state, fills):
    state.last_rebalance_date = fills[0].date
    state.next_eval_date = next_quarter_first_trading_day(state.last_rebalance_date)
    # 잔여 현금은 portfolio.cash에 자연히 남으므로 별도 state 갱신 불필요
    return state
```

## orders

- **MOC** (분기 첫 거래일 종가 기준 리밸런싱) — 원문 스레드의 관행이 특정 시각의 "당일 종가 기준
  리밸런싱"에 가깝고, 지정가로 하면 정확한 목표비중 도달을 보장할 수 없어 MOC가 규칙 재현에 가장
  근접.

## fee_model

- `fee_rate` 파라미터화. 분기 1회(연 4회) 리밸런싱이라 회전율은 낮은 편(D2/D3 대비) — 세후 비교에서
  단순 DCA와 함께 "회전율 낮은 전략" 그룹으로 분류될 가능성.
- **레버리지 ETF 자체의 내재 비용(운용보수·스왑 비용)은 이 문서의 fee_model이 다루는 "매매 수수료"와
  별개**. UPRO/TMF 모두 연 1% 안팎의 운용보수가 일별 순자산가치(NAV)에 이미 반영돼 있으므로,
  백테스트에 이 종목들의 실제 가격 데이터(NAV 기준 종가)를 쓰면 운용보수는 자동 반영됨 — 별도
  차감 로직 불필요(단, 데이터가 시뮬레이션/합성 가격일 경우는 별도 처리 필요, PLAN.md 4.1
  `synth.py`의 드래그 파라미터가 이 역할).

## dividend_handling

- UPRO는 기초지수(S&P500) 배당의 스왑/선물 기반 익스포저를 통해 총수익 성격을 일부 반영하나 실제
  분배금 지급 방식은 펀드마다 다름 — 실측 종가 데이터(배당 포함 총수익이 이미 가격에 근접 반영되는
  구조인지, 별도 분배금이 있는지)를 확인해 PLAN.md 4.3 방침(원종가+배당 분리)대로 처리.
- TMF는 국채 이자수익 성격의 분배금을 정기적으로 지급 — 별도 현금흐름으로 가산(재투자 여부는
  `dividend_reinvest` 파라미터, 기본값 True 권장: HFEA는 배당 재투자를 전제하는 전략이 일반적).

## cash_profile

- 이상적으로는 리밸런싱 시점 외에는 현금 비중이 거의 0(전액 UPRO+TMF 보유)에 가까움 — 정수 주 절사로
  인한 소액 `carry_cash`만 발생. D1/D2와 달리 "잔여 현금 방침"이 결과에 미치는 영향은 미미.

## risk_notes (알려진 리스크 — 반드시 명시)

1. **레버리지 ETF 일일 재조정(daily reset) 구조의 변동성 드래그**: UPRO/TMF는 매일 종가 기준으로
   3배 노출을 재설정하므로, 횡보하며 변동성만 큰 구간에서는 기초지수가 제자리여도 레버리지 ETF는
   손실이 누적되는 "복리 감쇠(volatility decay)"가 발생. HFEA 성과의 핵심 리스크 요인.
2. **2022년 금리 상승기 동반 폭락 (알려진 최대 리스크 사례)**: HFEA의 핵심 전제는 "주식과 장기국채가
   반대(또는 최소한 무상관) 방향으로 움직인다"는 것인데, 2022년 연준의 공격적 금리 인상으로
   **주식과 채권이 동시에 급락**하면서 이 전제가 정면으로 무너짐. 3배 레버리지가 걸린 양쪽 자산이
   함께 폭락하며 **2022년 한 해 원안(40/60) 기준 약 -67%, 개정판(55/45) 기준 약 -64%** 하락한 것으로
   보도됨(자산 손실 -50%대 후반~-60%대 후반 범위로 보고서마다 소폭 차이) — S&P500 자체는 같은 해
   -16%대 하락에 그쳤던 것과 대비. 백테스트 리포트에 이 구간을 "최악 5구간" 지표로 반드시 포함 필요
   (PLAN.md 4.5).
   출처: https://www.optimizedportfolio.com/hedgefundie-adventure/,
   https://www.etfcentral.com/news/hedgefundies-excellent-adventure-3x-leveraged-etf-portfolio
3. **금리 환경 의존성**: 저금리·완화적 통화정책 국면(2010년대)에서는 채권이 안전자산+수익원 역할을
   동시에 해내며 HFEA 성과가 매우 좋았으나, 금리 인상기에는 TMF 자체가 이중으로 불리(채권가격 하락
   ×3배 레버리지). 즉 HFEA의 과거 고성과는 특정 금리 국면(2010~2021 저금리·완화기)에 상당 부분
   기인한다는 비판이 Bogleheads 커뮤니티 내에서도 지배적.
4. **공식적으로 "권장 전략 아님"**: Bogleheads 위키/커뮤니티 자체가 HFEA를 표준 투자 원칙(저비용
   인덱스, 저레버리지)에서 벗어난 투기적 전략으로 취급 — 원문 스레드들도 "본인 책임 하에" 실행하는
   실험적 성격이 강하다는 점을 스레드 제목과 서두에서부터 명시.
5. 강제 손절·파산 조건은 규칙 자체에 없음(리밸런싱만 반복) — 이론상 두 레버리지 자산이 동시에
   거의 0에 수렴하면 사실상 전액 손실 가능(2022년 사례가 그 방향성의 실제 사례).

## automation

- 분기 1회(연 4회) 실행이라 자동화 난이도는 낮음 — MorningSyncWorker와 유사한 저빈도 스케줄러로
  구현 가능. 매매 자체는 두 종목 MOC 주문 각 1건씩(많아야 연 8건)이라 KIS API 부담도 작음.
- 사람 판단 개입 지점: 목표비중을 40/60에서 55/45로 바꾼 것과 같은 **비중 자체의 개정**은 기계적
  규칙이 아니라 커뮤니티(또는 사용자)의 재량적 판단 — 자동화 대상은 "정해진 비중을 유지하는 것"까지.

## backtest_notes

- 체결가 가정: MOC(분기 첫 거래일 종가) 리밸런싱.
- **UPRO는 2009년 상장, TMF는 2009년 상장** — 실측 데이터로 커버 가능한 구간은 2010년 이후. PLAN.md
  4.5의 "2000~현재(합성 포함)" 구간 비교 시 UPRO/TMF의 2000년대 데이터는 존재하지 않으므로, 합성
  TQQQ와 마찬가지로 합성 UPRO(3×SPY 일간수익률−드래그)·합성 TMF(3×TLT 또는 장기국채지수 일간수익률
  −드래그)가 필요할 수 있음 — 다만 PLAN.md는 합성 대상으로 TQQQ만 명시(결정 4번), TMF/UPRO 합성
  여부는 이 문서 범위를 넘는 백테스터 설계 결정 사항.
- 분기 첫 거래일 산정 로직(거래소 휴장일 캘린더 반영)이 테스트 케이스로 필요.

## 구현 스펙 요약 (지시사항 재확인)

> 분기 평가일에 목표 비중과의 차이를 MOC 주문으로 리밸런싱, 정수 주 내림, 잔여 현금 이월.

위 `rules` 의사코드가 이 스펙을 그대로 구현한 것 — `target_qty = floor(target_value/price)`로
정수 주 내림, 두 종목 모두 정수 주 절사 후 남는 금액은 `portfolio.cash`에 자연히 남아 다음 분기
`total_value` 계산에 포함되므로 별도 이월 로직 없이도 잔여 현금이 이월된다.

## 미확정/가정 항목

- 리밸런싱 밴드(예: 목표비중 대비 ±5%p 이탈 시에만 리밸런싱) 변형은 원문 스레드에서 파생 언급만
  있고 "표준"은 아니므로 1차 구현에서는 **순수 캘린더 방식(밴드 없음)**을 기본으로 확정. 밴드 방식은
  민감도 분석용 변형으로만 향후 고려.
- 2022년 정확한 하락률(원안 -67% / 개정판 -64%)은 커뮤니티 정리 자료 기준 수치로, 실제 데이터 소스
  (yfinance 등)로 백테스터가 재계산한 값과 소폭 다를 수 있음 — 이 문서의 수치는 "알려진 리스크의
  크기감"을 전달하기 위한 참고치이며, 최종 확정치는 W2/W3 백테스트 실행 결과로 대체해야 함.
- `dividend_reinvest` 기본값(True)과 TMF 분배금의 구체적 처리(월별/분기별 지급 주기, 재투자 시점)는
  가정 사항 — 실제 데이터 확보 후 확정 필요.
- 합성 UPRO/TMF(2000년대 구간) 필요 여부는 PLAN.md 결정사항에 명시되지 않아 미확정 — 백테스터
  설계자(W1 담당)와 조율 필요.
