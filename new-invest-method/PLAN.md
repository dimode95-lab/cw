# new-invest-method — 규칙 기반 투자 방법론 수집·정형화·백테스트 프로젝트

> v2 — 2026-07-17. 솔검증(3개 에이전트) 반영 + 사용자 토론 결정 반영.
> 파이프라인: **페이블계획 → 솔검증 → 토론 → 페이블오케스트 → 솔구현** (현재: 오케스트/구현)

## 0. 확정된 결정 (토론 단계, 사용자 승인)

1. **1차 코드 구현 전략 = 코어 6종**: DCA(기준선), 무한매수법 V4.0(MumaeEngine 교차검증),
   VR5.0, Value Averaging, TQQQ 200일선 추세추종, HFEA. 카탈로그 문서는 전체 작성.
2. **변동성 돌파는 완전 제외** — 당일 진입·청산 데이트레이딩이라 프로젝트 취지
   ("일희일비하지 않는 장기 규칙 투자")와 KIS LOC/MOC 운영 리듬에 안 맞음.
3. **세후 비교 1차 포함** — 연도별 실현손익 집계 → 250만원 공제 → 22% 세율의 경량 세금 엔진.
   손실 이월공제 없음(한국 양도세 구조) 반영. 회전율 높은 전략 vs 낮은 전략의 세후 역전 확인.
4. **합성 TQQQ 포함** — 2000~2010 닷컴버블 스트레스 구간. 일별 3×QQQ수익률 − 드래그,
   드래그 민감도 3시나리오(1.0/1.5/2.0%), 실측 구간(2010~) 대조 오차율 리포트 명시.

## 1. 배경과 목표

무한매수법 V4.0을 MumaeApp(안드로이드+KIS API)으로 실운용 중. 무한매수법·VR이 매력적인
이유는 "주가 등락에 일희일비하지 않고 사전에 정한 규칙만 기계적으로 따르는 투자"라는 점.

1. **수집**: 국내외 규칙 기반(mechanical) 투자 방법론 조사
2. **정형화**: 동일 스키마(StrategySpec)로 기술해 비교 가능하게
3. **검증**: Python 백테스터로 동일 조건 비교 (수익률·MDD·현금비중·세후)
4. **(후속) 실전화**: 유망 전략의 MumaeApp(Kotlin) 이식 여부 판단 — 이번 범위 아님

## 2. 전략 카탈로그 (v2 — 검증 반영 확정본)

★ = 1차 코드 구현 대상 (코어 6종)

### A. 분할매수·사이클형
| # | 전략 | 출처 | 요약 | 규칙 접근성 |
|---|------|------|------|------------|
| A1 ★ | 무한매수법 V4.0 | 라오어(한국) | T회차 LOC 분할매수+쿼터매도, 소진 시 리버스모드 | 서적+카페 (본 프로젝트에 규칙 문서·실구현 보유) |
| A2 | 무한매수법 변형들 | 무매 카페 | 분할수·별% 변형 등 — 조사·문서만 | 커뮤니티 |

### B. 목표가치·리밸런싱형
| # | 전략 | 출처 | 요약 | 규칙 접근성 |
|---|------|------|------|------------|
| B1 ★ | 밸류리밸런싱 VR5.0 | 라오어 | V경로+±15%밴드 이탈 시만 매매, Pool·G로 상승률 조절, 2주 평가 | 서적+카페 (규칙 문서 보유) |
| B2 ★ | Value Averaging | Edleson | 목표 가치경로 부족분 매수/초과분 매도. VR의 원조 | 공개 (공식 재현 자료 다수) |
| B3 | Shannon's Demon | Shannon | 주식:현금 50:50 주기 리밸런싱 | 공개 |
| B4 | 밴드 리밸런싱(5/25룰) | Swedroe | 절대5%p/상대25% 이탈 시만 리밸런싱 | 공개 |
| B5 | 영구 포트폴리오 | H. Browne | 주식/채권/금/현금 25%×4, 연 리밸런싱 | 공개 |
| B6 | 올웨더 | R. Dalio | 리스크패리티형 자산배분 | 공개(근사 레시피) |
| B7 | 골든 버터플라이 | Portfolio Charts | 5자산 20%×5, 연 리밸런싱 | 완전 공개 |
| B8 | K-올웨더 | 김성일(한국) | 주식/대체/국채 50:20:30 한국형 | 부분 공개(골자만) |

### C. 모멘텀·추세추종형
| # | 전략 | 출처 | 요약 | 규칙 접근성 |
|---|------|------|------|------------|
| C1 | Dual Momentum(GEM) | Antonacci | 12개월 상대+절대 모멘텀 월간 전환 | 완전 공개 |
| C2 ★ | 200일선(10개월 이평) 추세추종 | Faber GTAA → TQQQ 응용(한국 커뮤니티) | 이평 위 보유/아래 현금. 1차 구현은 TQQQ 단일종목 버전 | 원리 공개(논문), TQQQ 변형은 커뮤니티 |
| C3 | 평균모멘텀 스코어 | systrader79(한국) | 1~12개월 모멘텀 평균 스코어로 비중 조절 | **부분 공개 — 파라미터 자체 추정 필요 표시** |
| C4 | Keller 계열(VAA/PAA/BAA/HAA) | W. Keller | 카나리아 자산 모멘텀으로 공격/방어 전환 | 완전 공개(SSRN 무료) |

### D. 적립·기계식 매입형
| # | 전략 | 출처 | 요약 | 규칙 접근성 |
|---|------|------|------|------------|
| D1 ★ | DCA(정액 적립) | 일반 | 매달 정액 매수 — 기준선 | 공개 |
| D2 | 가중 DCA | 변형 다수 | 낙폭 구간별 매수액 증액 | 공개 |
| D3 | Grid Trading | FX/코인 유래 | 가격 격자 매수/매도 (소수 단위 lot 주의) | 공개 |

### E. 레버리지 운용 프레임
| # | 전략 | 출처 | 요약 | 규칙 접근성 |
|---|------|------|------|------------|
| E1 | Lifecycle Investing | Ayres&Nalebuff | 생애주기 레버리지 조절 — 프레임 조사만 | 서적(요약 공개) |
| E2 ★ | HFEA | Bogleheads | UPRO 55/TMF 45 분기 리밸런싱 — 레버리지 리스크패리티 | 완전 공개(포럼 원문) |

제외: 변동성 돌파(데이트레이딩 — 결정 2), 마법공식(재무팩터 스크리닝이라 성격 상이 — 참고만).

## 3. 전략 정형화 스키마 StrategySpec v2

`catalog/` 폴더에 전략당 1개 md. 솔검증 ②의 지적을 반영해 필드 확장:

```yaml
name:                  # 전략명(버전)
origin:                # 창안자/출처/공개자료 링크
category:              # A~E
assets:                # 대상 자산 + lot_size(정수 주 / 소수 허용)
state:                 # 상태변수 (T, V, pool 등) — numeric_type(Decimal|float) 명시
params:                # 파라미터 (원금, 분할수, 밴드폭, G 등)
schedule:              # 복합 구조: evaluation_frequency(매일/2주/월간) + trigger_condition(밴드 이탈 등)
cycle_definition:      # 포지션 생애주기 — trigger(예: qty==0), resets(T·mode), carries(수익 로그)
mode_transition:       # 상태기계 — states, transitions[{from,to,condition}] (무매 NORMAL↔REVERSE 등)
order_roles:           # 주문의 논리적 역할 목록 (FIRST_BUY/STAR_HALF_BUY/…) + 역할별 상태갱신 연결
fill_interaction_rules:# 동일일 체결 조합 → 상태갱신 표 (무매: 별+평단 동시 체결 시 T+1 등 비선형 규칙)
rounding:              # 계산 항목별 표: {항목, 모드(HALF_UP|DOWN), 자릿수} — rules 산문에 묻지 않는다
rules:                 # 매수·매도·상태전이 의사코드
orders:                # 주문 유형 (LOC/MOC/지정가/시장가)
fee_model:             # 수수료 가정 (요율 파라미터화)
dividend_handling:     # 배당·분할 처리 방침
cash_profile:          # 현금 보유 특성
risk_notes:            # 하락장 거동, 강제 손절, 파산 조건
automation:            # KIS API 자동화 난이도, 사람 판단 개입 지점
backtest_notes:        # 체결 가정, 데이터 요구
```

## 4. 백테스터 설계 v2 (Python)

위치: `backtester/`. 솔검증 ②③ 반영.

### 4.1 구조
```
backtester/
  data/              # 커밋된 일봉 CSV (원종가 + 배당 이벤트 분리)
  fetch_data.py      # yfinance 우선(레이트리밋 대비 재시도) — Close(원종가)와 Dividends를 분리 저장.
                     # stooq는 apikey 정책 변경으로 자동화 불가 → 폴백은 수동 다운로드+커밋
  synth.py           # 합성 TQQQ: 일별 3×QQQ수익률 − drag/252, drag∈{1.0,1.5,2.0}%,
                     # 실측 구간(2010~) 대조 오차율 산출
  engine.py          # 일봉 루프 (매일 on_bar 호출 — 평가일 판단은 전략 내부)
  broker_sim.py      # 체결 판정: LOC매수 close<=limit → close 체결 / LOC매도 close>=limit → close
                     # MOC → close / 지정가 → 정규장 고저 범위 판정 (전량 체결만, 부분체결 미모델링)
                     # ※ 프리마켓 체결 미반영 편향(매도 지연 방향) — 리포트 명시
  strategies/        # Strategy 구현 (코어 6종)
  metrics.py         # CAGR, MDD, 변동성, Sharpe, 현금비중, 회전율
  tax.py             # 연도별 실현손익 집계 → 250만원 공제 → 22% (손실 이월 없음)
  report.py          # 비교표 md + 차트 PNG
  tests/             # MumaeEngine 교차검증 픽스처 포함
```

### 4.2 핵심 인터페이스 (v2 — on_fill 신설, 다자산, role 태그)
```python
@dataclass
class Order:
    ticker: str
    side: Side                  # BUY | SELL
    type: OrderType             # LOC | MOC | LIMIT | MKT
    price: Decimal | None
    qty: int                    # (Grid 등 소수 lot 전략은 Decimal 허용 플래그)
    role: str                   # 전략별 논리 역할 태그 (예: STAR_HALF_BUY) — 상태갱신의 키

@dataclass
class Fill:                     # Order + 체결가/일자/수수료
    order: Order; price: Decimal; date: date; fee: Decimal

class Strategy:
    def on_bar(self, state, bars: dict[str, OHLC], portfolio) -> list[Order]: ...
    def on_fill(self, state, fills: list[Fill]) -> State: ...
    # on_fill은 "그날 체결된 Fill 전체"를 1회에 받는다 — 무매의 체결 조합 의존
    # T값 갱신(별+평단 동시 체결 → +1 등)을 재현하기 위한 필수 계약.
```
- `portfolio`(현금·보유수량)는 **엔진 소유, 전략엔 read-only 스냅샷**. 전략 고유 상태(state)는
  `on_fill`에서만 갱신 — 소유권 경계 명시.
- 엔진은 매 거래일 `on_bar` 호출. 2주/월간 전략은 내부에서 평가일 여부를 판단.
- 금액 계산은 `decimal.Decimal` + 항목별 명시적 반올림(ROUND_HALF_UP / ROUND_DOWN).
  **무매 구현은 MumaeEngine.kt의 계산 경로(Double 연산 → 특정 지점 BigDecimal 변환) 순서를
  그대로 재현**해야 1센트 오차 없이 교차검증 통과 가능.

### 4.3 데이터 방침
- 체결가 계산은 **원종가(raw close)**, 배당은 **별도 현금흐름으로 가산** (수정종가로 LOC
  주문가를 계산하면 실제 주문과 어긋나는 모순 방지). yfinance 사용 시 Close/Adj Close/
  Dividends를 구분 저장하는 가드 필수.
- 종목: TQQQ, SOXL, QQQ, SPY, UPRO, TMF, TLT, GLD, SHY (+ 합성 TQQQ)
- 받은 CSV는 커밋 (재현성). 다운로드 일자·조정 여부를 메타파일에 기록.

### 4.4 교차검증 (백테스터 정확성의 닻)
- `MumaeEngineTest.kt`의 **23개** 테스트(입력→출력 쌍)를 JSON 픽스처로 이식:
  starPercent/별지점/최종매도가(DOWN)/사다리/1회매수금/리버스 별지점/applyFills T값 조합.
- Python 무매 구현이 전체 픽스처를 통과해야 다른 전략 백테스트 결과를 신뢰.

### 4.5 비교 리포트
- 공통 조건: $20,000 시작. 구간 2010~현재(실측) + 2000~현재(합성 포함, 별도 표기).
- 지표: CAGR, MDD, 최악 5구간, 평균 현금비중, 연간 매매횟수, **세전/세후 CAGR**,
  드래그 민감도(합성 구간).
- 명시할 가정: LOC=종가 체결, 프리마켓 미반영 편향(방향: 매도 지연), 부분체결 미모델링,
  합성 오차율(실측 구간 대조).

## 5. 오케스트레이션 (단계 4→5 실행 계획)

| 웨이브 | 작업 | 담당 | 의존성 |
|--------|------|------|--------|
| W1 (병렬) | 카탈로그 문서 19건 (4~5건씩 4개 에이전트) | Sonnet ×4 | 없음 |
| W1 (병렬) | 데이터 파이프라인 + 합성 TQQQ (fetch_data/synth + CSV 커밋) | Sonnet ×1 | 없음 |
| W1 (병렬) | 엔진 코어 (engine/broker_sim/metrics/tax + 인터페이스) + MumaeEngine 픽스처 추출 | Sonnet ×1 | 없음 |
| W2 (병렬) | 코어 6종 전략 구현 + 단위테스트 (무매는 픽스처 교차검증) | Sonnet ×3 | W1 완료 |
| W3 | 백테스트 실행 + 비교 리포트 + 전체 품질 검토 | Sonnet + Fable | W2 완료 |

품질 게이트: 각 웨이브 종료 시 Fable이 통합 검토 (인터페이스 일관성, 테스트 통과, 문서-구현 일치).

## 6. 산출물

```
new-invest-method/
  PLAN.md               # 본 문서 (v2)
  catalog/              # 전략별 StrategySpec 문서 19건
  backtester/           # Python 백테스터 + 코어 6종 + 테스트
  report/comparison.md  # 세전/세후 비교 리포트 + 차트
```
