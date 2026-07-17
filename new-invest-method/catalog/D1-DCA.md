# D1. DCA (정액 적립식 분할매수, Dollar-Cost Averaging)

★ 1차 코드 구현 대상 — 코어 6종의 **기준선(baseline)**. 다른 모든 전략의 초과수익·MDD·현금비중은
결국 "그냥 정해진 날 정해진 금액을 기계적으로 사도 됐잖아?"라는 이 전략과 비교해야 의미가 생긴다.

## origin

- 특정 창안자 없음. 자산운용업계 표준 용어. Investopedia, Vanguard, Fidelity, Schwab 등 대부분의
  운용사 교육자료에 등장하는 일반 개념.
- 실증 비교 연구(핵심 출처):
  - Vanguard, *"Cost averaging: invest now or temporarily hold your cash?"* (2012, 2023 갱신) —
    미국·영국·호주 3개 시장, 1926~2022(미국 기준) 롤링 10년 구간 분석.
    https://corporate.vanguard.com/content/dam/corp/research/pdf/cost_averaging_invest_now_or_temporarily_hold_your_cash.pdf
  - Vanguard 요약 페이지: https://investor.vanguard.com/investor-resources-education/online-trading/dollar-cost-averaging-vs-lump-sum
  - Wikipedia, *Dollar cost averaging*: https://en.wikipedia.org/wiki/Dollar_cost_averaging

## category

D (적립·기계식 매입형)

## assets

- 대상: 단일 종목(예: TQQQ, QQQ, SPY 등) — 다자산 분산 버전도 가능하나 1차 구현은 단일 종목.
- lot_size: **정수 주** (KIS 미국주식 주문은 정수 주 단위. 소수점 매수 미지원 — MumaeApp과 동일 제약).

## state

전략 고유 상태변수는 원칙적으로 없음(무상태 반복 규칙). 백테스터 구현 편의를 위해 최소한만 유지:

| 변수 | 타입 | 설명 |
|---|---|---|
| `next_buy_date` | date | 다음 적립 예정일 (스케줄 계산용, Decimal 아님) |
| `carry_cash` | Decimal | 이번 회차에 정수 주로 못 쓴 잔돈(옵션 B 선택 시에만 사용) |
| `buy_count` | int | 누적 적립 횟수 (리포트용) |

`numeric_type`: 금액은 Decimal, 날짜/횟수는 int — 상태기계(mode_transition) 없음, 단일 규칙 반복.

## params

| 파라미터 | 기본값(예시) | 설명 |
|---|---|---|
| `contribution_amount` (C) | $500 | 1회 적립 금액 |
| `interval` | 2주 (biweekly) | 적립 주기. PLAN.md 지시대로 "2주마다 $X" 기본, `monthly`/`weekly`로 파라미터화 |
| `start_date` | 백테스트 시작일 | 첫 적립일 |
| `end_condition` | 무기한 또는 `total_budget` 소진 | 총 예산 한도를 두면 `contribution_amount × 예정 횟수 = total_budget`로 역산 가능 |
| `leftover_cash_policy` | A: 매회 전액 소진(잔돈은 다음 회차 원금에 합산 안 함, 그냥 유휴) / B: 잔돈 이월(carry_cash 누적 후 다음 회차 원금에 가산) | 아래 "잔여 현금 처리 방침" 참조 |

## schedule

- `evaluation_frequency`: 매 거래일 (`on_bar` 호출) — 전략 내부에서 오늘이 적립일인지 판단.
- `trigger_condition`: `today == next_buy_date` (주기가 캘린더 기준이라 거래일이 아니면 **다음 거래일로
  이월** — 예: 매수 예정일이 토요일이면 다음 월요일 체결). 이월 시 `next_buy_date`는 원래 캘린더 주기로
  계속 전진(밀린 날짜가 누적되지 않도록 원래 스케줄 기준 유지).
- 격주(2주) 기준: `next_buy_date += 14일`. 월간 기준: `next_buy_date`를 다음 달 같은 일자(또는 지정 요일,
  예: "매월 첫 거래일")로 갱신.

## cycle_definition

없음. DCA는 포지션 생애주기 개념이 없는 **연속 누적 매수** 전략 — `trigger`/`resets`/`carries` 필드는
해당 없음(N/A). 굳이 사이클을 정의한다면 "적립 예산 소진" 또는 "백테스트 종료일"이 유일한 종료 조건.

## mode_transition

없음(N/A). 상태(NORMAL/REVERSE 같은) 전이가 없는 단일 상태 전략.

## order_roles

| role | 설명 | 상태갱신 |
|---|---|---|
| `PERIODIC_BUY` | 적립일마다 발생하는 유일한 주문 역할 | 체결 시 `buy_count += 1`, `next_buy_date` 전진, (옵션 B) `carry_cash` 갱신 |

## fill_interaction_rules

해당 없음 — 회차당 주문이 1건뿐이라 "동일일 체결 조합"이 존재하지 않음. (무한매수법처럼 별+평단 동시
체결 같은 비선형 규칙이 발생할 조합 자체가 없음.)

## rounding

| 항목 | 모드 | 자릿수 |
|---|---|---|
| 매수 수량 `qty = floor(C / price)` | ROUND_DOWN (내림) | 정수 주 |
| 잔여 현금 `carry_cash = C - qty * price - fee` | 그대로 보관(반올림 없음) | 센트(소수 2자리) |
| 금액 표시 | HALF_UP | 소수 2자리 |

## rules (의사코드)

```python
def on_bar(state, bars, portfolio):
    today = bars[ticker].date
    if today < state.next_buy_date:
        return []
    # 적립일 도래 (거래일이 아니었다면 이월된 첫 거래일)
    budget = params.contribution_amount
    if params.leftover_cash_policy == "B_CARRY":
        budget += state.carry_cash

    return [Order(
        ticker=ticker, side=BUY, type=MOC,   # 정액 적립은 시점 자체가 무의미 → 당일 종가 매수(MOC)로 단순화
        price=None,
        qty=None,  # 체결가(당일 종가) 확정 후 broker_sim이 floor(budget/close)로 수량 계산
        role="PERIODIC_BUY",
    )]

def on_fill(state, fills):
    for f in fills:
        if f.order.role == "PERIODIC_BUY":
            spent = f.price * f.qty + f.fee
            leftover = (params.contribution_amount + (state.carry_cash if B else 0)) - spent
            state.carry_cash = leftover if params.leftover_cash_policy == "B_CARRY" else Decimal(0)
            state.buy_count += 1
    state.next_buy_date = advance_by_interval(state.next_buy_date, params.interval)
    return state
```

주: MOC는 당일 종가 매수라 `qty`를 사전에 정할 수 없고 체결가(=종가) 확정 후 역산해야 하므로,
`broker_sim`에서 "금액 지정 시장가" 주문 타입을 지원하거나(권장) LOC로 전일 종가 기준 근사치를 미리
계산해 정수 주를 넘기는 방식 중 택1 필요. 백테스터 구현 시 `broker_sim.py`에 반영.

## orders

- 기본: **MOC** (정액 적립은 매수 타이밍 최적화가 목적이 아니므로 당일 종가 매수가 논리적으로 가장 단순).
- 대안: 지정가 없이 시가(MOO) 매수도 가능 — 1차 구현은 MOC로 고정, 민감도는 다루지 않음.

## fee_model

- `fee_rate` 파라미터화 (예: 0.05%, KIS 해외주식 수수료 근사치). 매수 1건당 `qty * price * fee_rate`.

## dividend_handling

- TQQQ/SOXL 등 레버리지 성장주 ETF는 사실상 무배당이라 해당 없음.
- QQQ/SPY로 백테스트할 경우 배당은 별도 현금흐름으로 가산(PLAN.md 4.3 방침과 동일) — 재투자 여부는
  파라미터 `dividend_reinvest: bool`로 분리(기본 False, 재투자 시 다음 적립 회차 예산에 합산).

## cash_profile

**잔여 현금 처리 방침 — 반드시 명시 필요(PLAN.md 요구사항):**

1. **방침 A (무이자 가정, 기본값)**: 매 회차 `C - qty*price - fee`의 잔돈은 그냥 유휴 현금으로 남고
   수익률 계산에는 포함하되 별도 이자를 붙이지 않음. 구현이 가장 단순하고 보수적(실제보다 살짝 불리한
   방향의 편향 — DCA의 현금 비중이 매우 낮으므로 편향 크기는 미미).
2. **방침 B (단기금리 가정)**: 유휴 현금에 단기금리(예: 미국 MMF 연 4~5%대 또는 한국 CMA 금리)를
   일할 적용해 이자 수익을 가산. DCA는 구조상 현금 보유 기간이 짧아(최대 2주) 영향이 작지만, VR5.0·
   무한매수법처럼 현금 비중이 큰 전략과 **공정 비교**하려면 동일한 금리 가정을 모든 전략에 일괄
   적용해야 함(백테스터 공통 파라미터로 승격 권장).
3. 1차 구현은 **방침 A**를 기본으로 하되 `cash_yield_rate` 파라미터를 0으로 두면 A, 0보다 크면 B와
   동일하게 동작하도록 설계 — 다른 코어 전략(무매·VR5.0 등)과 동일한 현금 수익 가정을 공유해야
   "현금비중" 지표 비교가 왜곡되지 않음.

## risk_notes

- 하락장에서도 규칙대로 계속 매수 → 하락이 길어지면 평가손실 누적(강제 손절 없음, 파산 조건도 없음 —
  예산이 유한하면 자연 종료).
- 상승장 초입에 예산을 다 쓰지 못하고 나눠 사는 구조라 **강세장에서는 럼프섬 대비 기대수익이 낮음**
  (아래 비교 논점 참조). "리스크 관리형"이라기보다 "타이밍 리스크 회피형" 전략.
- 원금이 정해져 있고 매수만 반복하므로 무한매수법과 달리 **매도 규칙이 없음** — 배당·비교 목적의
  스냅샷 평가만 존재. 청산 시점은 백테스트 종료일의 평가금액으로 판단.

## automation

- 구현 난이도 최저. KIS API로는 "특정 날짜에 정액 매수"를 예약할 수단이 없으므로 MumaeApp처럼
  WorkManager 기반 스케줄러(예: `MorningSyncWorker`와 유사한 별도 워커)로 매 적립일 아침 LOC/MOC
  주문을 자동 접수해야 함. 사람 판단 개입 지점 없음(완전 기계적).

## backtest_notes

- 체결가 가정: MOC → 당일 종가. LOC로 구현 시 "전일 종가 대비 소폭 낮은 지정가"류의 근사치가 필요해
  불필요한 자유도가 생기므로 1차 구현은 MOC로 고정.
- 적립일이 비거래일(주말·공휴일)이면 다음 거래일로 이월 — 이월 로직이 없으면 스케줄이 영구히
  어긋나므로 테스트 케이스에 공휴일 이월 포함 필요.
- 잔여 현금 방침(A/B)에 따라 최종 수익률이 소폭 달라지므로 리포트에 어떤 방침을 썼는지 반드시 명시.

## Lump Sum 대비 비교 논점 (요약)

DCA를 "기준선"으로 쓰는 이유는 그 자체가 최적이라서가 아니라 **가장 직관적인 대안**이기 때문. 실제
DCA vs Lump Sum(전액 즉시 투자) 비교의 핵심 논점:

1. **기대수익 관점**: Vanguard(2012, 2023 갱신) 연구에 따르면 미국·영국·호주 시장에서 **럼프섬이
   DCA를 약 2/3(약 68%) 확률로 능가**했고, 평균 초과수익은 약 +2.3%p(전액 주식 포트폴리오 기준
   +2.4%p) 수준. 시장은 장기적으로 우상향하는 경우가 더 많으므로 "일찍, 한번에 넣는" 편이 기대값상
   유리하다는 것이 요지.
   출처: https://corporate.vanguard.com/content/dam/corp/research/pdf/cost_averaging_invest_now_or_temporarily_hold_your_cash.pdf
2. **DCA가 유리한 국면**: 2008년 금융위기 직전처럼 **투자 직후 큰 폭락이 온 경우**, 분할 매수가 하락
   구간에서 더 낮은 가격에 추가 매수하는 효과를 내 럼프섬보다 결과가 좋았던 사례가 있음. 즉 DCA의
   가치는 "평균 기대수익"이 아니라 **후회 회피(사후 최악 시나리오의 변동성 완화)**에 있음.
3. **행동재무학적 논점**: 목돈을 한번에 넣는 것에 대한 심리적 저항(투자 직후 폭락에 대한 후회 회피)이
   실제 투자자의 이탈률을 낮춘다는 점에서, "수학적으로 최적"과 "실제로 완주 가능"은 다른 기준.
4. **Vanguard 권고**: 분할 투입을 선택한다면 기간을 **12개월 이내**로 제한할 것을 권고 — 너무 길게
   끌면 시장 노출 지연에 따른 기회비용이 커짐.
5. **본 프로젝트 맥락**: 무한매수법·VR5.0은 "럼프섬으로 원금을 한번에 넣지 않고 규칙적으로 분할·되사는"
   구조라는 점에서 DCA와 태생이 같은 계열(변동성 완화 우선)이며, 백테스트 비교표에서 DCA는 이 계열
   전략들의 "가장 단순한 버전"으로서 초과 알파(추가 규칙이 실제로 돈값을 하는지)를 판별하는 기준선
   역할을 한다.

## 미확정/가정 항목

- `contribution_amount`·`interval`의 구체적 기본값은 백테스터 공통 조건($20,000 시작, PLAN.md 4.5)에
  맞춰 역산 필요 — 예: 10년간 격주 적립이면 1회당 금액을 총 예산/회차수로 정할지, 아니면 무제한 추가
  납입을 가정할지는 W2 구현 단계에서 다른 코어 전략과의 "동일 조건" 정의에 맞춰 확정해야 함.
- `leftover_cash_policy`의 기본값(A vs B)과 `cash_yield_rate`의 구체적 수치(한국 CMA vs 미국 MMF 금리
  중 어느 것을 기준으로 할지)는 미확정 — 세후 비교(원화 환산 여부 포함)와 맞물려 있어 백테스터
  공통설계 단계에서 다른 전략 담당자와 합의 필요.
- MOC "금액 지정 시장가"를 `broker_sim.py`가 지원하는지 여부는 엔진 담당(W1) 산출물 확인 필요 —
  안 되면 이 문서의 `rules` 의사코드를 LOC 근사 방식으로 수정해야 함.
