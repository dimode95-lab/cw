# D2. 가중 DCA (Weighted / Scaled DCA — 낙폭 구간별 매수액 증액)

D1(DCA)의 변형. "그냥 정액을 사는 대신, 많이 빠졌을 때 더 산다"는 아이디어의 다양한 버전을 통칭.
단일 창안자·표준 명칭이 없는 **커뮤니티 관행(folk strategy)** 계열이라, 카탈로그 목적상 가장 구체적으로
규칙이 문서화된 공개 변형 2개를 대표 사례로 정형화한다.

## origin

- 통칭: "Weighted DCA", "Value-scaled DCA", 국내에서는 "물타기 배수법"/"낙폭 대응 분할매수"로 불림.
  단일 창안자 없음 — 여러 블로그·중개사 교육자료·자동매매 봇 서비스에 유사한 규칙이 반복 등장.
- 대표 공개 변형 ①: **암호화폐 DCA 봇의 "Safety Order" 방식** (3Commas 등 대중적 자동매매 봇의
  표준 파라미터화 — 코인 시장에서 시작됐지만 규칙 자체는 종목·자산군에 무관해 주식에도 그대로 이식
  가능하고, 유일하게 수식이 완전히 공개돼 있어 정형화 근거로 채택):
  - 3Commas Help Center, *"DCA Bot: Interface and Main Settings"*:
    https://help.3commas.io/en/articles/3108940-dca-bot-interface-and-main-settings
  - 3Commas Blog, *"DCA Bots: Creating a DCA Bot..."*:
    https://3commas.io/blog/dca-bots-creating-a-dca-bot-using-a-built-in-technical-analysis-indicator
- 대표 공개 변형 ②: **계단식 비중배분(고정 낙폭 구간 + 고정 비중표)** — 예: "기준가 도달 시 30% 매수,
  -4% 추가하락 시 20%, -6.7% 시 20%, -9.3% 시 15%, -13.3% 시 잔여 15%" 식으로 낙폭 구간마다 **총
  투자금 중 미리 정한 비율**을 배분하는 방식. 국내 블로그 다수에 유사 사례 등장:
  https://brunch.co.kr/@00b68069c88e4c0/117 (구체 수치 예시)
- 참고(개념적 배경, VR5.0·Value Averaging과의 구분): 가중 DCA는 "목표 가치 경로"를 계산하지 않고
  **낙폭 구간 자체를 트리거로 매수액을 스케일링**한다는 점에서 B2(Value Averaging)와 다르다. VA는
  포트폴리오 가치가 목표선에 미달한 만큼 사서 미달분을 정확히 채우지만, 가중 DCA는 사전에 정한
  배율표를 그대로 따를 뿐 목표값 개념이 없다.

## category

D (적립·기계식 매입형)

## assets

- 단일 종목. lot_size: 정수 주 (KIS 미국주식 제약과 동일).

## state

| 변수 | 타입 | 설명 |
|---|---|---|
| `reference_price` | Decimal | 낙폭 기준가 (직전 고점 또는 최초 진입가 — 변형에 따라 다름, 아래 params 참조) |
| `tier_index` | int | 현재까지 트리거된 낙폭 구간 인덱스 (변형 ①의 안전주문 카운트에 해당) |
| `next_buy_date` | date | 변형 ②(정기+가중 혼합)에서 정기 스케줄 관리용 |

## params

**변형 ① (Safety-Order 스케일 방식, 연속 낙폭 트리거)**

| 파라미터 | 예시값 | 설명 |
|---|---|---|
| `base_order_amount` | $500 | 최초(기준) 매수 금액 |
| `price_deviation` | 5% | 기준가 대비 다음 매수를 트리거하는 하락폭 |
| `step_scale` | 1.5 | 매 단계 하락폭 간격에 곱해지는 배율 (예: 5% → 7.5% → 11.25% ...) |
| `volume_scale` | 1.5 | 매 단계 매수 금액에 곱해지는 배율 (예: $500 → $750 → $1125 ...) |
| `max_tiers` | 5 | 최대 추가매수 단계 수 (무한 확장 방지 — 자금 소진 리스크 제한) |

**변형 ② (고정 구간 + 고정 비중표 방식)**

| 파라미터 | 예시값 | 설명 |
|---|---|---|
| `total_budget` | $10,000 | 이 사이클에 배정할 총 예산 |
| `tier_table` | `[(0%, 30%), (-4%, 20%), (-6.7%, 20%), (-9.3%, 15%), (-13.3%, 15%)]` | (낙폭 구간, 총예산 대비 매수비율) 목록 — 합계 100% |
| `reference_price_basis` | `entry` 또는 `rolling_high` | 낙폭 기준을 최초 진입가로 고정할지, 갱신되는 직전 고점으로 할지 |

## schedule

- `evaluation_frequency`: 매 거래일.
- `trigger_condition`:
  - 변형 ①: `current_close <= reference_price × (1 - cumulative_deviation(tier_index))`이면 다음
    단계 매수 트리거. `cumulative_deviation`은 `price_deviation × step_scale^k`의 누적합.
  - 변형 ②: `current_close`가 `tier_table`의 다음 미체결 구간 가격 이하로 하락하면 해당 구간 비율만큼
    매수.

## cycle_definition

- `trigger`: 포지션 미보유(qty==0) 또는 예산 전액 소진 시 사이클 종료.
- `resets`: 사이클 종료(전량 매도 또는 리셋 결정) 시 `tier_index=0`, `reference_price=None`(다음 진입
  시 재설정).
- `carries`: 사이클 간 수익 로그는 상위 리포트로 이관(무한매수법과 동일 패턴을 재사용).
- 매도 규칙은 이 변형들 자체에는 명시적으로 없음(순수 매수 전술) — 별도의 익절/리밸런싱 규칙과
  결합해야 완결된 사이클이 됨. 1차 카탈로그 문서에서는 "매수 스케일링 규칙"만 정형화하고, 매도는
  구현 시 목표수익률 청산 등 보조 규칙을 별도로 정의해야 함(미확정 항목 참조).

## mode_transition

- 상태기계 단순: `WAITING(다음 트리거 대기) → BUYING(트리거 충족, 주문 발생) → WAITING`.
- `max_tiers` 도달 시 `EXHAUSTED` 상태로 전이(더 이상 자동 추가매수 없음, 사람 개입 또는 사이클 종료
  대기).

## order_roles

| role | 설명 | 상태갱신 |
|---|---|---|
| `TIER_BUY_0` (base) | 기준가 도달 시 최초 매수 | `reference_price` 설정, `tier_index=1` |
| `TIER_BUY_k` (k≥1) | k번째 낙폭 구간 매수 | `tier_index += 1` |

## fill_interaction_rules

- 하루에 한 단계만 트리거되도록 설계(전일 대비 낙폭이 여러 구간을 동시에 관통하는 갭다운의 경우
  **한 번의 평가에서 통과한 모든 구간을 즉시 소급 매수할지, 다음 거래일까지 한 단계씩만 처리할지**는
  변형별 정책 선택 사항 — 1차 구현은 "갭다운 시 통과한 모든 구간을 당일 즉시 일괄 매수"로 단순화 권장
  (미확정 항목 참조).

## rounding

| 항목 | 모드 | 자릿수 |
|---|---|---|
| 매수 수량 `qty = floor(tier_amount / price)` | ROUND_DOWN | 정수 주 |
| 낙폭 트리거 가격 | HALF_UP | 소수 4자리(퍼센트 계산 중간값) → 최종 비교는 종가와 직접 비교 |
| 잔여 현금(정수 주 절사분) | 그대로 보관, 다음 단계 예산에 합산하지 않음(단순화) | 센트 |

## rules (의사코드, 변형 ① 기준)

```python
def on_bar(state, bars, portfolio):
    close = bars[ticker].close
    if state.reference_price is None:
        # 최초 진입: 기준가 설정 + base order
        state.reference_price = close
        return [Order(ticker, BUY, MOC, qty=floor(base_order_amount/close), role="TIER_BUY_0")]

    if state.tier_index >= params.max_tiers:
        return []  # EXHAUSTED

    cum_dev = sum(price_deviation * step_scale**k for k in range(state.tier_index + 1))
    trigger_price = state.reference_price * (1 - cum_dev)
    if close <= trigger_price:
        amount = base_order_amount * (volume_scale ** state.tier_index)
        return [Order(ticker, BUY, MOC, qty=floor(amount/close), role=f"TIER_BUY_{state.tier_index+1}")]
    return []

def on_fill(state, fills):
    for f in fills:
        if f.order.role.startswith("TIER_BUY"):
            state.tier_index += 1
    return state
```

## orders

- MOC 기본(D1과 동일 이유). 지정가(트리거 가격 그대로 LIMIT BUY)로 구현하면 갭다운 시 트리거 가격보다
  낮게 체결되는 상황을 재현하지 못하므로, 백테스트 정확성 면에서는 "당일 종가가 트리거 가격 이하이면
  종가에 체결"로 처리하는 편(broker_sim의 LOC 판정 로직과 동일 패턴)이 3Commas 실제 봇 동작(지정가
  주문이되 트리거 즉시 시장가 체결에 가까움)에 더 가깝다.

## fee_model

D1과 동일 (`fee_rate` 파라미터, 매수 건당 부과). 매수 빈도가 하락장에서 급증하므로 회전율(연간
매매횟수) 지표에 미치는 영향이 D1보다 큼 — 세후 비교(단기/장기 보유기간 구분)에서 유의미한 차이 예상.

## dividend_handling

D1과 동일 방침 준용(무배당 레버리지 ETF 기준 해당 없음, 배당종목은 별도 현금흐름 가산).

## cash_profile

- D1과 동일하게 잔여 현금 방침(무이자 vs 단기금리)을 명시해야 하나, **가중 DCA는 하락이 깊어질수록
  필요 현금이 기하급수적으로 늘어나므로 (`volume_scale > 1`), 유한한 `total_budget` 가정 시
  `max_tiers` 도달 전 예산이 먼저 소진될 위험이 있음** — 백테스트 시 `qty` 계산에서 가용 현금이
  부족하면 주문을 스킵(또는 가용 현금만큼만 매수)하는 가드가 반드시 필요.

## risk_notes

- **마틴게일(martingale) 구조의 본질적 위험**: 하락이 깊고 길게 지속되면(`max_tiers`를 넘어서는
  장기 약세장) 추가 매수가 중단된 채 평가손실만 누적 — 강제 손절 없음.
- `volume_scale`이 클수록(예: 2.0) 이론상 평단을 빠르게 낮출 수 있지만, 필요 자금이 기하급수적으로
  커져 실제로는 "자금이 바닥나는 시점"이 하락 추세가 끝나는 시점보다 먼저 올 위험 — 그리드/코인 DCA
  봇 커뮤니티에서 가장 흔히 지적되는 리스크와 동일.
- D1(단순 DCA) 대비 상승장에서는 초반 매수 비중이 낮아 상대적으로 불리(underperform)하고, 완만한
  하락 후 반등 구간에서는 평단 개선 효과로 유리 — 국면 의존적 전략이라는 점을 리포트에 명시 필요.

## automation

- D1과 동일한 스케줄러 구조로 구현 가능하나 트리거 조건이 매일 낙폭 재계산을 요구해 로직이 약간 더
  복잡. KIS API 자동화 자체의 난이도는 D1과 동일(단순 시장가/LOC 매수 반복).

## backtest_notes

- 갭다운으로 여러 구간을 동시에 통과하는 경우의 처리 방식(즉시 일괄 매수 vs 단계적 처리)에 따라
  결과가 달라지므로 반드시 테스트 케이스로 고정.
- `reference_price_basis`(최초 진입가 고정 vs 롤링 고점)에 따라 결과가 크게 달라짐 — 1차 구현은
  "최초 진입가 고정" 단순 버전을 기본으로 권장(문서 변형 ①과 동일).

## 미확정/가정 항목

- **매도(청산) 규칙이 정형화되어 있지 않음**: 조사한 두 공개 변형 모두 "언제 얼마나 파는지"에 대한
  표준 규칙이 없다(순수 매수 스케일링 전술). 1차 코드 구현 시 별도로 익절 조건(예: 평단 대비 +X%
  도달 시 전량 매도)을 보조 규칙으로 추가해야 사이클이 완결되며, 이 보조 규칙의 구체값은 미확정 —
  백테스트 비교의 공정성을 위해 D1/무한매수법과 유사한 청산 기준을 준용할지 결정 필요.
- `step_scale`/`volume_scale`/`price_deviation`의 "표준값"은 존재하지 않음(암호화폐 봇 커뮤니티의
  관행값 1.5~2.0을 차용) — 실제 백테스트에서는 여러 조합에 대한 민감도 분석이 필요할 수 있음.
- 변형 ②(고정 비중표)의 구체적 낙폭 구간·비율은 예시 출처(브런치 블로그)의 개인 사례를 인용한 것으로
  "공식적으로 검증된 표"가 아님 — 대표성 있는 변형이라기보다 "이런 방식이 흔히 쓰인다"는 예시로만
  참고할 것.
