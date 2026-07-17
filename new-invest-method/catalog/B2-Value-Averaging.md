# B2. Value Averaging (Edleson)

★ 1차 코드 구현 대상 — VR5.0(B1)의 원조가 되는 목표가치 전략

## 출처

- Michael E. Edleson, "Value Averaging: A New Approach to Investing", *Journal of Portfolio Management*,
  Summer 1988 (최초 학술 발표).
- Michael E. Edleson, *Value Averaging: The Safe and Easy Strategy for Higher Investment Returns*
  (Wiley Investment Classics, 1993년 초판/2006년 재간행). "Dollar Value Averaging(DVA)"라고도 불림.
- 웹서치 보강(2026-07-17): [Wikipedia "Value averaging"](https://en.wikipedia.org/wiki/Value_averaging),
  [StockGro "What is Value Averaging: Formula and Benefits"](https://www.stockgro.club/blogs/stock-market-101/value-averaging/),
  [Do the Financial — Establishing the Value Path](https://www.dothefinancial.info/value-averaging/establishing-the-value-path.html),
  [Bogleheads wiki "Value averaging"](https://www.bogleheads.org/wiki/Value_averaging),
  [US News "Value Averaging: An Investing Strategy to Avoid"](https://money.usnews.com/investing/buy-and-hold-strategy/articles/2017-09-26/value-averaging-an-investing-strategy-to-avoid),
  Bogleheads 포럼 스레드("Value averaging rate of return", "Value Averaging. Any practicionors?").
  대부분의 원본 사이트(Bogleheads 본문, finiki.org, valueaveraging.ca, sigmainvesting.com,
  breakingdownfinance.com, grokipedia.com)는 이 세션에서 접근 시도 시 403(차단)으로 직접 인용을
  확보하지 못했고, 검색엔진 스니펫으로만 교차확인함 — 정확한 표현은 원문 대조가 필요할 수 있음.
- 추가 보강(같은 날 재확인, 별도 조사 라운드): [Sigma Investing "Value Averaging"](https://www.sigmainvesting.com/advanced-topics/value-averaging)
  및 [AAII "Value Averaging Spreadsheet"](https://www.aaii.com/journal/article/value-averaging-spreadsheet)
  (Markese & Bajkowski, *Computerized Investing* 2001년 7-8월호 — Edleson 공식을 재구현한 실무
  스프레드시트, "매도 여부"를 입력 셀 하나(예: A9=1이면 매도 허용, 0이면 no-sell)로 토글하는 구조가
  확인됨. 이는 본 문서 mode_transition 절의 "no-sell은 전략 시작 시 고정하는 파라미터"라는 해석과
  일치). 이 두 사이트도 WebFetch 전체 페이지 인출은 403으로 실패, 검색 스니펫으로만 확인.
  [valueaveraging.ca](http://www.valueaveraging.ca/)(Edleson 방법론 전용 사이트, 연구자료 PDF
  ["The Value Averaging Investment Strategy"](http://www.valueaveraging.ca/research/The%20Value%20Averaging%20Investment%20Strategy.pdf)
  포함)와 [bioequity.org의 S&P500 1950-2013 VA 백테스트](https://bioequity.org/value-averaging-backtested/)도
  같은 방식(스니펫)으로만 확인 — 구체 수치는 backtest_notes 참고.
  Paul S. Marshall, "A Statistical Comparison of Value Averaging vs. Dollar Cost Averaging and
  Random Investment Techniques," *Journal of Financial and Strategic Decisions*, Spring 2000 —
  Edleson와 함께 VA의 수익 우위를 통계적으로 지지한 논문으로 서지정보만 검색 확인(원문 미대조).
- B1(밸류 리밸런싱 VR5.0, 라오어)과의 관계: VR은 Edleson의 VA 개념(목표 가치경로 + 부족분 매수/
  초과분 매도)을 골자로 하되, V값 갱신 공식·Pool·G·밴드(±15%) 등 라오어 고유의 파라미터를 얹은
  한국형 변형이다. 상세 비교는 아래 "VA vs VR" 절 참조. VR 자체 규칙은 이 문서에서 반복하지 않음
  (`/home/user/cw/new-invest-method/catalog/B1-밸류리밸런싱-VR5.0.md` 참조).

## category

B. 목표가치·리밸런싱형

## assets

| 항목 | 값 |
|---|---|
| 대상 자산 | 원래는 뮤추얼펀드/인덱스펀드 대상으로 고안(1980년대 미국 개인투자자 정기적립 문맥). 현대 적용은 ETF(예: S&P500/QQQ 등)로 일반화 가능 |
| lot_size | **미확정** — Edleson 원저는 펀드 단위 매매(소수점 좌수 허용)를 전제로 설계됨. ETF·개별주로 옮기면 정수 주 제약이 걸려 목표값을 정확히 못 맞추는 오차가 생김(브로커가 소수 주 매매 지원하면 해소). 백테스트는 소수 허용을 기본 가정하고, 정수 lot 가정 시의 오차도 별도 시나리오로 검토 권장 |
| 레버리지 확장 | 원저는 레버리지 상품을 다루지 않음. 이 프로젝트에서 TQQQ 등에 적용 시 변동성이 커 목표 미달/초과 폭이 커지고 유사시 필요 매수액이 급증하는 리스크가 커짐(VR이 이를 Pool 상한으로 완충한 것과 대비) |

## state

| 변수 | numeric_type | 설명 |
|---|---|---|
| t (경과 기간 수) | Int | 전략 시작 이후 경과한 평가주기 횟수(보통 월 단위) |
| V_t (목표가치, 이번 주기) | Decimal 권장 | 그 시점까지 쌓여 있어야 할 목표 포트폴리오 가치 |
| 실제 포트폴리오 가치 | Decimal | 보유수량 × 현재가 |
| 보유수량 | Decimal(소수 허용) 또는 Int(정수 lot 가정 시) | |
| 누적 투입원금 | Decimal | 세금·수익률 계산용 참고 상태(전략 로직 자체엔 불필요, 리포팅용) |
| side fund(사이드펀드, no-sell 변형 한정) | Decimal | 미래 필요 매수액을 대비해 별도로 보유하는 유동자산 풀 — 표준 매도형 VA에는 없음 |

## params

| 파라미터 | 기호 | 설명 |
|---|---|---|
| 기준 증가액 | C | 매 평가주기마다 목표가치가 늘어나는 기준 금액(적립식 DCA의 "매기 투입액"에 대응하는 개념이지만, VA에서는 실제 투입액이 아니라 목표선의 기울기 파라미터) |
| 가정 투자수익률 | r | 연 단위 기대수익률을 평가주기 단위로 환산한 값(예: 연 8%→월 환산) |
| 가정 기여금 성장률 | g | 목표선이 기여금 자체의 성장(예: 매년 추가 저축액 증가)까지 반영할 경우의 성장률. 순수 VA(기여금 고정)라면 g=0으로 두면 됨 |
| 결합 성장률 | R = (r + g) / 2 | 다수의 공개 자료가 채택하는 형태(§rules 참조). **주의**: 자료마다 R을 r과 g의 산술평균으로 단순화하는 근사식과, r·g를 각각 별도 항으로 넣는 좀 더 정밀한 형태가 혼재 — 아래 "미확정" 절 참조 |
| 평가주기 | monthly(표준) | 분기 단위 변형도 문헌에 존재 |
| no-sell 여부 | boolean | true면 초과분 매도 대신 매수를 건너뛰거나 최소화(§rules 참조) |
| 목표기간(선택) | N주기 | 목표 자산 형성 후 종료하는 유한기간형으로 쓸 경우(예: 20년 은퇴자금 목표) 지정. 무기한 반복형으로 써도 무방 |

## schedule

- `evaluation_frequency`: **월간(표준)**. Edleson 원저의 기본 단위. 분기 단위 변형도 문헌에서
  언급되나 월간이 압도적으로 표준.
- `trigger_condition`: **매 평가주기마다 무조건 매매**(무한매수법·VR과 달리 "밴드 이탈시에만"이
  아니라 "매 주기마다 목표가치와의 차액을 반드시 메꾼다"가 원칙). 단, no-sell 변형에서 실제가치가
  목표를 초과한 주기는 매수 생략(=사실상 무매매)로 처리되므로, 그 경우에 한해 밴드형 전략과
  유사한 "조건부 무매매" 양상을 보임.

## cycle_definition

VA는 무한매수법처럼 "보유수량 0 → 사이클 종료" 개념이 없다. 목표기간이 있는 경우(예: N개월 후
목표달성) 그 시점에 전략을 종료하는 유한 사이클, 없으면 무기한 반복.

| 항목 | 값 |
|---|---|
| trigger(시작) | t=0, V_0 = 초기 투입액(또는 0, 자료에 따라 다름 — 아래 미확정 참고) |
| trigger(종료, 선택) | t == N(목표기간 도달) — 유한기간형일 때만 |
| resets | 없음(목표선은 계속 갱신, 리셋 없음) |
| carries | 실현손익, 세금 로그는 계속 누적 |

## mode_transition

표준 VA(매도형)와 no-sell 변형 사이의 전환은 원저에 정의된 자동 상태기계가 아니라, **전략 시작
시점에 사용자가 선택하는 고정 파라미터(no-sell boolean)**다. 두 변형을 매 주기 자동으로 오가는
규칙은 문헌에서 확인되지 않음.

```yaml
states: [BELOW_TARGET, AT_TARGET, ABOVE_TARGET]   # 매 평가주기 독립 판정 (VR의 3구간과 유사한 형태로 통일)
transitions:
  - from: "*"
    to: BELOW_TARGET
    condition: "실제가치 < V_t"
  - from: "*"
    to: ABOVE_TARGET
    condition: "실제가치 > V_t"
  - from: "*"
    to: AT_TARGET
    condition: "실제가치 == V_t"
# BELOW_TARGET -> 매수(부족분), ABOVE_TARGET -> 매도(표준형) 또는 매수생략(no-sell형), AT_TARGET -> 무매매
```

## order_roles

| role(제안) | 발생 조건 | 방향 |
|---|---|---|
| `TOPUP_BUY` | 실제가치 < V_t | BUY — 부족분(V_t − 실제가치)만큼 매수 |
| `TRIM_SELL` | 실제가치 > V_t, no-sell=false | SELL — 초과분(실제가치 − V_t)만큼 매도 |
| `SKIP` | 실제가치 ≥ V_t, no-sell=true | 무주문 — 매수를 생략(현금은 side fund에 유보) |

## fill_interaction_rules

VA는 평가주기당 매매가 최대 1건(매수 또는 매도 중 하나, 혹은 SKIP)이라 무한매수법과 같은 "같은 날
복수 role 조합" 문제가 구조적으로 발생하지 않는다.

| 이벤트 | 상태 갱신 |
|---|---|
| `TOPUP_BUY` 체결 | 보유수량 += 매수수량, 누적투입원금 += 매수금액(+수수료) |
| `TRIM_SELL` 체결 | 보유수량 -= 매도수량, 실현손익 기록(매도가−평균단가)×수량, 매도대금은 재투자 대상이 아니라 인출(현금화)됨이 원칙 — VA는 무한매수법처럼 "잔금 재순환" 구조가 아니라 "포트폴리오 가치 자체를 목표선에 맞추는" 구조이므로, 매도금의 용처(다음 주기 투입 재원 vs 즉시 인출)는 **미확정 — 구현 시 가정 필요** |
| `SKIP` 체결(no-sell 변형) | 무포지션 변경. side fund에 그날 예정이었던 기여금(있다면)만 적립 |

## rounding

| 항목 | 계산식 | 모드 | 자릿수 |
|---|---|---|---|
| 목표가치 V_t | C × t × (1+R)^t | 원문 확정 규칙 없음 — 제안: 센트 HALF_UP | 2 |
| 결합성장률 R | (r + g) / 2 | 원문 확정 규칙 없음 — 제안: 소수점 6자리 무반올림 유지(연산 정밀도 확보) | 6(연산용), 표시는 %로 반올림 |
| 매수/매도 금액(차액) | V_t − 실제가치(매수) / 실제가치 − V_t(매도) | 제안: 센트 HALF_UP | 2 |
| 매수/매도 수량 | 금액 / 현재가 | lot_size가 정수면 **DOWN(내림)**, 소수 허용이면 반올림 불필요 | 정수 lot: 0 / 소수 lot: 미확정 |

**전체 rounding 정책은 원저에 명시적 규정이 없다 — 위 표는 무한매수법(A1)·VR(B1)과의 프로젝트
일관성을 위한 제안 값이며, 전부 "미확정 — 구현 시 가정 필요"로 취급할 것.**

## rules (의사코드)

```
# 파라미터: C(기준 증가액), r(가정 투자수익률/주기), g(가정 기여금 성장률/주기, 기본 0), noSell(bool)
# R = (r + g) / 2   # 다수 공개자료가 채택하는 근사식(§params 참고, 정밀도 이슈는 "미확정" 참조)

function targetValue(t):
    return C * t * (1 + R) ** t      # V_t 표준형(Edleson). t=0일 때 V_0=0 또는 초기입금(자료마다 다름 — 미확정)

# 매 평가주기(월간)마다 실행
function onEvaluationPeriod(state, currentPrice):
    t = state.t + 1
    V_t = targetValue(t)
    actualValue = state.quantity * currentPrice
    diff = V_t - actualValue

    if diff > 0:
        # 부족 -> 매수 (표준형·no-sell형 공통)
        qty = floorOrExact(diff / currentPrice)   # lot_size에 따라 내림 또는 소수 허용
        emit BUY role=TOPUP_BUY qty=qty
    elif diff < 0:
        if not noSell:
            # 초과 -> 매도 (표준 VA)
            qty = floorOrExact(-diff / currentPrice)
            emit SELL role=TRIM_SELL qty=qty
        else:
            # no-sell 변형: 매도하지 않고 이번 주기는 매수도 생략(SKIP)
            # side fund에 예정 기여금만 적립, 실제 포트폴리오 매매는 없음
            emit SKIP
    else:
        emit SKIP   # 정확히 일치하는 경우(드묾)

    state.t = t
    return state
```

### VA vs VR(라오어) 비교 — 간단 대조

| 항목 | Value Averaging (Edleson) | VR5.0 (라오어, B1 참조) |
|---|---|---|
| 목표선 공식 | V_t = C×t×(1+R)^t (사전에 확정된 지수형 목표선) | 다음V = 현재V + Pool/G + 적립금 (매 사이클 Pool·G에 의존해 동적으로 갱신) |
| 매매 트리거 | **매 평가주기마다 항상**(목표와의 차액을 그때그때 메꿈) | **밴드(±15%) 이탈시에만** — 밴드 안에서는 무매매 |
| 매도 시 재원 처리 | 인출 개념에 가까움(원저는 순수 목표가치 유지가 목적) | Pool(예수금)로 유보되어 다음 매수 재원으로 재순환, 사용 한도(75%/50%/25%) 있음 |
| 하락장 대응 | 부족분을 전액 매수 시도(대형 하락 시 필요 매수액 급증 — cash reserve 필요) | Pool 사용 한도로 매수 규모를 완충(전액 소진 방지) |

## orders

원저는 특정 브로커·호가 방식을 규정하지 않는다(1980년대 뮤추얼펀드 정기 매매 문맥). 이 프로젝트
맥락(ETF, KIS API)에서는:

| 상황 | 추정 유형 | 비고 |
|---|---|---|
| 부족분 매수 | 시장가 또는 해당 평가일 종가 기준 체결 가정 | **미확정** — 원저에 호가 유형 규정 없음. 백테스트는 평가일 종가 체결로 단순화 권장 |
| 초과분 매도(표준형) | 시장가 또는 종가 기준 | 위와 동일 |

## fee_model

원저에 수수료 명시적 모델 없음. 다른 문서(A1·B1)와 일관되게 파라미터화된 요율 가정 재사용 권장.
매 주기 소액이라도 매매가 발생할 수 있어(특히 목표선 근처에서 미세한 매수/매도 반복), 저원가
브로커·수수료 무료 환경을 전제하지 않으면 거래비용이 누적될 수 있음 — risk_notes 참고.

## dividend_handling

원저·공개자료에 명시적 배당 처리 규정 없음. 일반적으로는 배당 재투자를 가정(인덱스펀드 토탈리턴
기준)하는 것이 통상적 해석이나, **미확정 — 구현 시 가정 필요**. 이 프로젝트의 PLAN.md 방침(원종가
기준 체결가 + 배당은 별도 현금흐름)과 일관되게 처리하고, 배당금은 "부족분 매수" 판정 시 현금
잔고에 합산하는 방식을 제안.

## cash_profile

- 표준 VA(매도형)는 이론상 "필요한 만큼 매수, 초과한 만큼 매도"라 사이클 내내 순수 재원이 크게
  필요하지 않지만, **하락장이 장기화되면 매 주기 필요 매수액이 계속 커져 상당한 현금 여유가
  요구된다**(검색 소스 공통 지적: "cash reserve" 필요, 확인 소스: US News, HeyGoTrade).
- no-sell 변형은 "side fund"(유동자산 풀)를 별도로 유지해야 하며, 이 풀이 즉시 전액 투자되지
  않아 발생하는 "cash drag"(현금 끌림에 의한 수익률 저하)가 구조적 단점으로 지적됨.
- VR(B1)의 Pool 개념은 VA의 이 문제(무제한 매수 요구)를 사용 한도(75/50/25%)로 명시적으로
  완충한 것으로 볼 수 있음.

## risk_notes

- **하락장 심화 시 필요 매수액 급증**: 목표선을 유지하려면 시장이 나쁠수록 더 많이 투입해야 하는데,
  이는 심리적으로 가장 어려운 시점과 겹친다 — 다수 소스가 공통 지적(US News, Lucia Capital Group).
- **초과분 매도의 세금 비효율**: 상승장에서 반복적으로 이익 실현(매도)이 발생해 과세계좌에서는
  단기/장기 양도소득세 이벤트가 잦아짐 — no-sell 변형이 이를 회피하기 위해 고안된 배경.
- **레버리지 자산 적용 시 리스크 증폭**: 이 프로젝트에서 TQQQ 등에 적용할 경우, 변동성이 커
  필요 매수액의 진폭이 일반 인덱스펀드보다 훨씬 커질 것으로 예상됨 — 구체적 계수는 백테스트로
  확인 필요(미확정).
- **강제 손절·파산 조건**: 원저·공개자료 모두 명시적 강제 손절선을 정의하지 않음. 이론상 목표선을
  계속 따라가려면 자금이 무한정 필요할 수 있어(특히 장기 우하향장), 실전에서는 현금 조달 한도가
  사실상의 리스크 상한이 된다.
- **비판 요약**(US News 등): 목표선의 "매끄러운 우상향"이 심리적 안정감은 주지만 실제 수익률
  개선 효과는 크지 않다는 비판이 존재하며, DCA 대비 우위가 시장 상황에 따라 달라진다는 반론도 있음.

## automation

| 구분 | 자동화 수준 |
|---|---|
| 목표가치 V_t 계산 | 완전 자동화 가능(공식 확정) |
| 부족분/초과분 판정·주문 수량 계산 | 완전 자동화 가능 |
| no-sell 여부 전환 | 전략 시작 시 1회 설정하는 파라미터 — 주기별 자동 전환 아님 |
| 현금 조달(하락장 중 필요 매수액 확보) | **사람 판단 개입 지점** — 자동화된 신용한도·마진 사용은 원저가 권장하지 않음(레버리지 없는 현금 매수가 원칙) |
| 세금 처리(매도 시 실현손익 집계) | PLAN.md의 세금 엔진(연 250만원 공제·22%)과 연동 가능, 별도 확인 불필요 |

## backtest_notes

- 원저(Edleson & Marshall)는 VA가 DCA보다 높은 내부수익률(IRR)을 낸다고 주장 — 이는 "더 많이
  살수록 유리한 시점(저가)에 더 많이 사게 되는" 구조적 특성 때문. 다만 이는 "심리적으로 어려운
  하락장 매수를 실제로 실행했을 때"의 결과이며, 백테스트는 이 가정(무조건 규칙 준수)을 전제한다.
  통계적 근거로 자주 인용되는 논문: Marshall, P.S. (2000), "A Statistical Comparison of Value
  Averaging vs. Dollar Cost Averaging and Random Investment Techniques," *Journal of Financial
  and Strategic Decisions*, Spring 2000(서지정보만 확인, 수치는 미확보 — 재조사 필요).
- **공개 백테스트 인용치**(bioequity.org, "Value Averaging Backtested with S&P 500 Index
  1950-2013", 배당 제외·인플레이션 미반영 명시): 1951년부터 3년 간격으로 시작하는 20년 구간 15개
  (1951~1993 시작)로 비교. **DCA(분기 $1,000씩, 20년간 총 $80,000 투입)의 최종가치 평균
  $191,000, 표준편차 $85,600**이 검색 스니펫으로 확인됨. 같은 조건에서의 **VA측 수치는 이번
  조사(WebFetch 403으로 원문 미접근)로 확보하지 못함 — 미확정, 원문 직접 확인 필요**. 이 글은
  또한 "VA의 가정성장률(quarterly growth rate) 설정이 결과에 크게 영향을 주며, 실제보다 낮게
  (심지어 음수로) 설정하면 DCA 대비 상대수익률이 오히려 개선된다"는 시사점을 스니펫에서 확인 —
  파라미터 선택이 사후적으로 유리하게 보정될 위험(과최적화)을 시사하므로 백테스트 설계 시 주의.
- **VA vs DCA 승률 관련 인용(출처 특정 실패, 주의해서 인용)**: 기대수익률 0% 가정 시뮬레이션에서
  "VA가 DCA를 이기는 경우는 약 39%(평균 우위 0.87%p), DCA가 VA를 이기는 경우는 약 61%(평균 우위
  3.2%p)"라는 수치가 검색 스니펫에 존재 — **원 논문/저자를 특정하지 못해 미확정으로 표시**.
  인용할 경우 반드시 1차 출처 재확인 후 사용할 것.
- **체결 가정**: 평가일 종가 기준 체결로 단순화 권장(원저는 호가 방식 미규정).
- **레버리지 자산(TQQQ) 적용 시**: 목표선 자체가 레버리지 자산에 맞게 설계된 것이 아니므로, r
  (가정 투자수익률) 파라미터를 레버리지 자산의 기대수익률에 맞게 상향 조정해야 하며, 그 값의
  적정 수준은 **미확정 — 백테스트로 민감도 분석 필요**.
- no-sell 변형과 표준(매도형) 변형을 모두 구현해 비교할 것(PLAN.md 취지상 "무매도 vs 매도" 세후
  수익률 비교가 유의미한 실험이 될 것으로 예상).
- 데이터 요구: 평가주기가 월간이 표준이므로 일봉 데이터에서 월말(또는 월초) 종가로 리샘플링 필요.

## 미확정/가정 필요 (요약)

1. **V_0(t=0)의 정확한 정의** — 공식 V_t=C×t×(1+R)^t는 t=0에서 0이 되므로, 첫 주기 초기입금을
   어떻게 반영하는지(첫 매수를 V_1부터 시작하는지, 별도 초기값을 더하는지) 원저 대조 필요.
2. **결합성장률 R=(r+g)/2의 정밀도** — 산술평균 근사식 외에, 더 정밀한 형태(r·g를 개별 항으로
   반영하는 버전)가 원저에 있을 가능성 — 이번 세션에서 원저 원문(도서/논문 PDF)에 직접 접근하지
   못해 확정 못함.
3. **매도 대금의 용처** — 표준 매도형에서 매도금이 즉시 인출되는지, 다음 주기 매수 재원으로
   보유되는지 불명확.
4. **주문 유형(시장가/지정가/종가 등)** — 원저에 규정 없음, 프로젝트 맥락에서 임의 가정 필요.
5. **배당 처리 방침** — 명시적 규정 없음, 재투자 가정 여부 확정 필요.
6. **rounding 표 전체** — 원저에 반올림 규칙 자체가 없어 프로젝트 표준(HALF_UP/DOWN, 센트)을
   임의로 제안한 상태.
7. **레버리지 자산 적용 시 r 파라미터 보정값** — 백테스트로 확인 필요.
8. 이번 세션에서 Bogleheads·finiki.org·valueaveraging.ca·sigmainvesting.com·breakingdownfinance.com·
   grokipedia.com·bioequity.org·AAII·Wikipedia·example.com(테스트용) 등 접근한 거의 모든 외부
   사이트가 WebFetch 도구 자체의 환경 프록시 문제로 403 차단되어 직접 인용 확보에 실패, 검색엔진
   (WebSearch) 스니펫으로만 교차확인함 — 원저(Edleson 1988 논문/1993년 책/Marshall 2000 논문) 원문
   대조는 추후 세션에서(WebFetch 정상 동작 시) 재시도 권장.
9. **bioequity.org 백테스트의 VA측 구체 수치(평균/표준편차)** — DCA측 수치($191,000 평균,
   $85,600 표준편차, 분기 $1,000×20년)만 확보, 동일 조건의 VA측 수치는 미확보.
10. **"VA 39% 승률 vs DCA 61% 승률(기대수익률 0% 가정)" 인용** — 1차 논문/저자 특정 못함, 사용 시
    재검증 필요.
