# D3. Grid Trading (격자 매매)

## origin

- 기원: 외환(FX)·암호화폐 자동매매 봇에서 대중화된 방식. 특정 창안자 없음 — "그리드 봇"으로 브로커·
  거래소들이 표준 상품화(Binance, Pionex, 3Commas, 각종 FX 브로커 등).
- 참고 자료:
  - Quantpedia, *"A Primer on Grid Trading Strategy"*: https://quantpedia.com/a-primer-on-grid-trading-strategy/
  - moomoo, *"Grid Trading Strategy"*: https://www.moomoo.com/us/learn/detail-02-grid-trading-strategy-53267-220471030
  - Admirals, *"Forex Grid Trading Strategy Explained"*: https://admiralmarkets.com/education/articles/forex-strategy/forex-grid-trading-strategy-explained

## category

D (적립·기계식 매입형 — 다만 성격상 "매수 전용"인 D1/D2와 달리 매수·매도 양방향 규칙을 가짐)

## assets

- 횡보(레인지) 구간이 예상되는 단일 종목. 레버리지 ETF(TQQQ 등)처럼 추세가 강한 자산에는 부적합
  (아래 risk_notes).
- lot_size: **정수 주 — 이 프로젝트에서 가장 문제가 되는 지점**. FX·코인 원조 그리드 전략은 소수점
  단위(예: 0.0001 BTC, 0.01 lot)로 격자당 수량을 자유롭게 나눌 수 있지만, KIS 미국주식 주문은
  정수 주 단위만 가능 → 격자 간격이나 격자당 투입금을 아무리 촘촘히 설계해도 **실제로는
  `floor(격자당투입금 / 가격)`으로 정수 주 절사**해야 하며, 저가 종목이 아닌 이상(TQQQ가 $50~$90대
  라면 격자당 투입금이 작을 경우 절사 오차가 커짐) 격자 수를 늘릴수록 이론값과 실제 체결의 괴리가
  커진다. 격자 수를 줄이거나(격자당 투입금 확대) 종목을 저가 종목으로 한정하는 두 가지 완화책 중
  하나가 필요.

## state

| 변수 | 타입 | 설명 |
|---|---|---|
| `grid_levels` | list[Decimal] | 격자 가격 목록 (등간격 또는 등비간격) |
| `level_position` | dict[level → qty] | 각 격자 라인에서 현재 보유 중인 수량(매수했지만 아직 대응 매도 미체결분) |
| `base_price` | Decimal | 격자 생성 기준가 (설정 시점 가격) |

## params

| 파라미터 | 예시값 | 설명 |
|---|---|---|
| `grid_type` | `arithmetic`(등차) 또는 `geometric`(등비, %) | 격자 간격 방식 |
| `grid_spacing` | $2 또는 2% | 격자 간 가격 간격 |
| `grid_count` | 10 (상단 5 + 하단 5) | 총 격자 라인 수 |
| `qty_per_grid` | 정수 (예: 5주) 또는 `amount_per_grid`(달러, 내부에서 정수 주로 절사) | 격자당 매수/매도 수량 |
| `price_range` | `[base_price × 0.8, base_price × 1.2]` | 격자가 커버하는 가격 범위 (범위 이탈 시 정책은 risk_notes 참조) |

## schedule

- `evaluation_frequency`: 매 거래일(원래 그리드봇은 틱 단위지만 이 프로젝트는 일봉 백테스트이므로
  당일 저가~고가 범위 통과 여부로 체결 판정 — PLAN.md 4.1 `broker_sim` "지정가 → 정규장 고저 범위
  판정" 규칙 그대로 사용).
- `trigger_condition`: 당일 고저 범위가 미체결 매수/매도 격자 라인을 통과하면 해당 라인 체결.

## cycle_definition

- 격자 라인 하나하나가 독립적인 "매수→매도" 미니 사이클: `trigger`는 해당 라인에서 매수 체결,
  `resets`는 대응 매도(매수가 + `grid_spacing`)가 체결되면 그 라인이 다시 매수 대기 상태로 복귀.
  전체 전략 차원의 사이클 개념(무한매수법 같은 T 리셋)은 없음 — 라인별 독립 사이클의 집합.

## mode_transition

- 라인별 상태기계: `EMPTY(매수 대기) → HOLDING(매수 체결, 매도 대기) → EMPTY(매도 체결, 재매수 대기)`.
- 전체 전략 차원에서는 `price_range` 이탈 시 `OUT_OF_RANGE` 상태로 전이(격자 재설정 또는 정지 —
  정책 미확정, 아래 risk_notes).

## order_roles

| role | 설명 | 상태갱신 |
|---|---|---|
| `GRID_BUY_i` | i번째 격자 라인 매수 | `level_position[i] += qty`, 상태 EMPTY→HOLDING |
| `GRID_SELL_i` | i번째 격자 라인 대응 매도(매수가+spacing) | `level_position[i] -= qty`, 상태 HOLDING→EMPTY |

## fill_interaction_rules

- 하루에 여러 라인이 동시에 통과되는 경우(변동성 급등일) 모든 해당 라인을 당일 일괄 체결 처리
  (부분체결 미모델링 원칙, PLAN.md 4.1과 동일).
- 매수·매도가 같은 라인에서 같은 날 동시에 트리거되는 경우는 구조상 발생하지 않음(매수가와 매도가가
  다르므로) — 단, 인접 라인의 매수와 다른 라인의 매도가 같은 날 동시 발생하는 것은 정상적인 동작.

## rounding

| 항목 | 모드 | 자릿수 |
|---|---|---|
| 격자당 수량 `qty = floor(amount_per_grid / grid_price)` | ROUND_DOWN | 정수 주 |
| 격자 가격(등비 방식) | HALF_UP | 소수 2자리 |

## rules (의사코드)

```python
def on_bar(state, bars, portfolio):
    high, low = bars[ticker].high, bars[ticker].low
    orders = []
    for i, level_price in enumerate(state.grid_levels):
        pos = state.level_position.get(i, 0)
        if pos == 0 and low <= level_price:
            # 매수 라인 통과
            orders.append(Order(ticker, BUY, LIMIT, price=level_price,
                                 qty=floor(qty_per_grid), role=f"GRID_BUY_{i}"))
        elif pos > 0:
            sell_price = level_price + grid_spacing
            if high >= sell_price:
                orders.append(Order(ticker, SELL, LIMIT, price=sell_price,
                                     qty=pos, role=f"GRID_SELL_{i}"))
    return orders

def on_fill(state, fills):
    for f in fills:
        i = extract_level_index(f.order.role)
        if f.order.side == BUY:
            state.level_position[i] = state.level_position.get(i, 0) + f.qty
        else:
            state.level_position[i] = 0
    return state
```

## orders

- **지정가(LIMIT)** — MOC/LOC가 아닌 진짜 지정가 주문. 격자 매매의 본질이 "정해진 가격에 걸어두고
  기다리는 것"이라 시가/종가 개념(LOC/MOC)과 맞지 않음. KIS 미국주식 지정가 주문 + 유효기간(GTC 유사)
  설정이 필요 — MumaeApp의 기존 주문 흐름(LOC/MOC 중심)과는 다른 주문 타입이라 별도 어댑터 검토 필요.

## fee_model

- 격자 수가 많을수록 매매 빈도가 급증 → 수수료·회전율이 다른 코어 전략 대비 압도적으로 높을 가능성.
  `fee_rate` 동일 파라미터화하되, 리포트에서 회전율 지표를 특히 강조해야 함.

## dividend_handling

D1과 동일 방침(별도 현금흐름 가산). 그리드 전략은 보유기간이 짧아 배당 영향 미미.

## cash_profile

- 상단 격자까지 전부 매수될 경우를 대비한 **최대 필요 현금 = grid_count × amount_per_grid**를 항상
  확보해야 함 — 하락장에서 모든 하단 격자가 순차 체결되면 현금이 급격히 소진되므로, 이 최대 소요
  현금을 넘지 않도록 사전에 격자 수·투입금을 설계해야 한다(사실상 D2의 마틴게일 리스크와 유사한
  자금 소진 문제를 안고 있음, 다만 그리드는 증액이 아니라 등액이라 소진 속도는 더 느림).

## risk_notes

- **추세장(트렌딩 마켓)에서 치명적**: 가격이 한 방향으로만 움직이면(특히 지속 하락) 매수 라인만
  계속 체결되고 대응 매도가 이뤄지지 않아 미실현 손실과 미회수 현금이 계속 쌓임 — "박스권에서만
  작동하는 전략"이라는 것이 그리드 매매의 가장 널리 알려진 한계.
- `price_range`를 벗어나는 추세 발생 시 정책 선택 필요: (a) 격자를 그대로 방치(범위 밖은 무대응),
  (b) 상단/하단 돌파 시 격자를 새 기준가로 재설정(recentering), (c) 특정 손실률 도달 시 전량 손절.
  이 프로젝트가 대상으로 삼는 TQQQ/SOXL류 고변동성 레버리지 ETF는 추세가 강해 그리드 매매 자체와
  궁합이 나쁠 수 있음 — 코어 6종에 포함되지 않은 이유이기도 함(참고용 카탈로그 문서로만 정형화).
- 강제 손절·파산 조건이 규칙 자체에는 없음(정책 (c)를 별도로 얹지 않는 한).

## automation

- 지정가 다건 상시 미체결 주문을 관리해야 해 LOC/MOC 중심의 MumaeApp 주문 흐름보다 자동화 난이도가
  높음. KIS API가 다건 지정가 주문의 동시 유지·부분 취소·재설정을 지원하는지 별도 확인 필요.

## backtest_notes

- `broker_sim`의 "지정가 → 정규장 고저 범위 판정" 규칙을 그대로 사용 (PLAN.md 4.1). 프리마켓 미반영
  편향과 부분체결 미모델링 가정이 동일하게 적용됨.
- 정수 주 절사로 인해 이론적 격자 수익(가격 차익 × 수량)과 실제 체결 수익 사이에 괴리가 발생 —
  리포트에 "이론 격자 수익 대비 절사 손실률"을 별도 지표로 남기는 것을 권장.

## 미확정/가정 항목

- `price_range` 이탈 시 정책(방치/재설정/손절) 중 무엇을 기본값으로 할지 미확정 — 백테스트 결과가
  이 선택에 크게 좌우되므로 W2 구현 단계에서 결정 필요.
- 등차(arithmetic) vs 등비(geometric) 격자 중 어느 것을 1차 구현 기본값으로 할지 미확정. 가격대가
  넓게 움직이는 레버리지 ETF 특성상 등비 방식이 더 적합해 보이나 검증 안 됨.
- 코어 6종에 포함되지 않아(카탈로그 문서만 작성 대상) 실제 Python 구현·백테스트는 이번 프로젝트
  범위 밖 — 향후 필요 시 이 문서를 기준으로 구현.
