# B3. Shannon's Demon (섀넌의 도깨비)

```yaml
name: Shannon's Demon — 변동성 자산:현금(또는 두 변동성 자산) 정기 리밸런싱

origin: >
  Claude Shannon(정보이론 창시자, MIT)이 1960년대 강의·비공식 메모에서 제시한
  사고실험으로 알려짐 — 공식 논문 없이 구전·강의노트로만 전해짐. 대중화는
  William Poundstone, "Fortune's Formula"(2005, Hill & Wang) 8장. 학술적 뿌리는
  Kelly criterion(1956)과 다자산 리밸런싱의 "diversification return"/
  "volatility pumping" 개념(Booth & Fama 1992, Luenberger "Investment Science").
  참고자료(공개):
  - https://www.1nve.st/p/shannons-demon
  - https://portfoliocharts.com/2022/04/12/unexpected-returns-shannons-demon-the-rebalancing-bonus/
  - https://www.richmondquant.com/news/2021/9/21/shannons-demon-amp-how-portfolio-returns-can-be-created-out-of-thin-air
  - https://thepfengineer.com/2016/04/25/rebalancing-with-shannons-demon/
  - https://www.gestaltu.com/2012/02/volatility-harvesting-and-the-importance-of-rebalancing.html/
  - https://investresolve.com/maximizing-the-rebalancing-premium-why-risk-parity-portfolios-are-much-greater-than-the-sum-of-their-parts/
  - https://www.kitces.com/blog/best-opportunistic-rebalancing-frequency-time-horizons-vs-tolerance-band-thresholds/

category: B  # 목표가치·리밸런싱형

assets: >
  기본형: 변동성 자산(주식 ETF 1종) + 현금. 변형: 상관관계 낮은 변동성 자산 2종
  (예: TQQQ+현금, 혹은 서로 다른 섹터/자산군 ETF 페어). 목표비율은 통상 50:50이나
  임의 비율(예: 60:40) 채택 가능 — 원 개념은 비율을 규정하지 않음, 50:50이 기하
  평균 최대화 관점에서 논의될 뿐. lot_size는 정수 주 가정(현금은 무제한 분할).
  ※ UPRO/TMF 조합(HFEA)은 별도 카탈로그 문서(E2)에서 다루므로 본 문서는 개념만
  언급하고 상세 비교는 생략.

state: >
  자산별 평가금액(Decimal): value_risky(위험자산), value_cash(현금 또는 2번째
  자산). 목표비율은 params 고정값 — 별도 추적 상태변수 없음.

params: >
  target_ratio(예: 0.5/0.5, 임의 조정 가능), rebalance_frequency(일/주/월/분기 —
  구현자 선택), band(밴드형 변형 시 허용 이탈폭, 예: ±5%p — 원 개념은 캘린더
  리밸런싱이 기본이며 밴드는 응용), 원금.

schedule: >
  evaluation_frequency = rebalance_frequency에 따름(전형적으로 월간 또는 분기,
  이론적 극한은 매 틱). trigger_condition = 캘린더형(주기 도래 시 무조건 실행)이
  원형. 밴드형 변형 시 trigger_condition = 목표비율 대비 이탈폭이 band 초과.
  두 방식 모두 원 개념(순수 Shannon's Demon)의 핵심 변형이며 실증적으로 유의한
  차이가 없다는 보고 다수(아래 backtest_notes 참고) — 프로젝트 백테스트는
  캘린더형(월간)을 기본으로 채택 권장.

cycle_definition: >
  포지션 생애주기 없음 — 영구 반복형. 명확한 시작/종료 개념이 없으며, 각
  리밸런싱 시점이 독립적 이벤트.

mode_transition: 해당 없음 — 단일 상태, 상태기계 없음.

order_roles: >
  REBALANCE_SELL(목표비율 대비 초과 자산을 목표치까지 매도),
  REBALANCE_BUY(목표비율 대비 부족 자산을 목표치까지 매수). 두 자산 조합(현금
  아닌 두 변동성 자산) 버전에서는 한쪽 SELL과 반대쪽 BUY가 항상 쌍으로 발생.

fill_interaction_rules: >
  해당 없음 — 단순 구조, 동일일 체결 조합에 의존하는 비선형 상태갱신 없음.
  체결 후 value_risky/value_cash를 체결가×수량으로 갱신하면 종료.

rounding:
  | 항목            | 모드      | 자릿수 |
  |-----------------|-----------|--------|
  | 목표 매매금액   | HALF_UP   | 센트(2) |
  | 매수 주수       | DOWN      | 정수    |
  | 매도 주수       | DOWN(보유수량 한도 내) | 정수 |
  | 리밸런싱 후 잔여현금 | 그대로 보유(재투자 안 함) | - |

rules: |
  # 평가 시점마다 실행 (캘린더형 기본; 밴드형은 조건 추가)
  total = value_risky + value_cash
  target_risky = total * target_ratio_risky
  diff = target_risky - value_risky        # 양수=매수 필요, 음수=매도 필요

  if band 미사용 or abs(diff / total) > band:
      if diff > 0:
          buy_amount = diff                 # REBALANCE_BUY, 현금에서 조달
          qty = floor(buy_amount / price)
      elif diff < 0:
          sell_amount = -diff               # REBALANCE_SELL
          qty = floor(sell_amount / price)   # 보유수량 초과 방지

  # --- 참고: Shannon의 원형 사고실험 (변동성 수확의 직관) ---
  # 자산가치가 매 기간 동전던지기로 2배(+100%) 또는 반토막(-50%)되는
  # 극단적 변동성 자산을 가정. 순수 보유 시 기하평균 = sqrt(2*0.5) = 1
  # (장기적으로 원금 보존, 산술평균 +25%와 괴리 — 변동성 드래그).
  # 이 자산과 현금을 50:50, 매 기간 리밸런싱하면:
  #   시작 1.00 (위험 0.50 / 현금 0.50)
  #   상승(×2): 위험 1.00, 현금 0.50, 합계 1.50 → 리밸런싱 후 0.75/0.75
  #   하락(×0.5): 위험 0.375, 현금 0.75, 합계 1.125 → 리밸런싱 후 0.5625/0.5625
  #   → 상승+하락 한 사이클(순서 무관)마다 총자산 1.00→1.125 (+12.5%)
  #   → 기간당 기하성장률 ≈ sqrt(1.125) - 1 ≈ 6.07%
  # 자산 자체는 무성장(기하평균 1.0)인데 리밸런싱만으로 초과수익이 발생 —
  # "무위험 초과수익"이 아니라, 매 기간 고점 매도/저점 매수를 강제하는
  # 효과이며 실제로는 자산이 계속 왕복(평균회귀)해야 성립. 추세가 한
  # 방향으로 지속되면(예: 우상향만 반복) 리밸런싱이 오히려 성장을 깎아먹음
  # (Buy&Hold 대비 열위) — 리밸런싱 프리미엄은 변동성×평균회귀성의 함수.

orders: >
  시장가(MOC/MKT) 또는 지정가 모두 가능 — 원 개념은 체결가격 방식을 규정하지
  않음. 리밸런싱일 종가 기준 체결이 통상적 가정(월간/분기 주기라 LOC의
  가격개선 이점이 무매법 대비 작음).

fee_model: >
  매매수수료율 파라미터화. 리밸런싱 주기가 짧을수록(일간 등) 왕복매매 빈도가
  급증해 수수료·스프레드 영향이 커짐 — 백테스트 시 반드시 주기별 회전율을
  함께 리포트.

dividend_handling: >
  배당은 현금(현금 자산군)으로 유입 후 다음 리밸런싱 시점에 비중 계산에
  자동 반영. 별도 로직 불필요(현금이 이미 상태변수 중 하나이므로).

cash_profile: >
  현금 비중이 항상 목표비율(예: 50%)로 유지되는 것이 이 전략의 정의적 특징 —
  다른 카탈로그 전략(무매법 등 잔고소진형)과 달리 현금이 "소진되는 버퍼"가
  아니라 "영구 고정비중 자산"으로 취급됨.

risk_notes: >
  하락장에서 위험자산 비중이 낮아지면 자동으로 저가 매수(역발상), 상승장에서는
  자동 이익실현 — 원리적으로 강제손절·파산 조건 없음(변동성 자산이 0으로
  수렴하지만 않으면). 단, **핵심 함정**: 리밸런싱 프리미엄은 자산이 평균회귀적
  (왕복) 변동성을 보일 때만 발생. 강한 추세장(장기 우상향)에서는 Buy&Hold 대비
  성과가 열위일 수 있음 — "무위험 초과수익"이 아니라 변동성의 형태에 의존하는
  조건부 효과. 위험자산 변동성이 매우 클수록(레버리지 ETF 등) 프리미엄도
  커지지만 동시에 MDD·개별자산 감가(decay)도 커짐.

automation: >
  캘린더형은 KIS API 자동화 난이도 낮음(주기 도래 시 목표비율 재계산 후 주문
  생성 — 상태기계·체결조합 로직 없음). 밴드형은 매일 평가 필요하나 실제
  주문은 밴드 이탈 시에만 발생해 매매빈도는 오히려 낮을 수 있음. 사람 개입
  지점: 목표비율·주기·밴드폭 선택.

backtest_notes: >
  - 리밸런싱 프리미엄(초과성장률)의 일반형 근사: 0.5 × (자산별 분산의 가중평균
    − 포트폴리오 분산). 두 자산 동일변동성·무상관·50:50 가정 시 약 0.56%/년
    수준이 보고된 사례 있음(ReSolve Asset Management, 자산 변동성 가정 미상 —
    "미확정, 구현 시 가정 필요"). 실측 수치는 채택 변동성·상관계수에 크게
    좌우되므로 프로젝트 백테스트에서 직접 산출 권장.
  - 리밸런싱 주기 영향: 여러 공개 분석(Kitces, WiserAdvisor 등)에서 연간
    ±5%p 밴드가 이론적(일간) 리밸런싱 효과의 대부분(≈99% 수준 보고 사례)을
    포착하면서 거래빈도·비용은 크게 낮춘다고 보고. 반대로 월간/주간 등
    과도하게 잦은 리밸런싱은 특히 변동성 급등기에 거래비용이 함께 늘어
    순효과가 줄어들 수 있음 — 정확한 최적 주기는 자산군·비용구조에 따라
    달라 "미확정 — 구현 시 가정 필요"(프로젝트는 월간/분기/밴드 3가지를
    비교 리포트하는 것을 권장).
  - 상관관계 낮은 변동성 자산 페어(현금 대신 두 번째 위험자산) 사용 시
    리밸런싱 기회(자산간 가치 괴리)가 늘어 프리미엄이 커진다는 논의가
    다수 문헌에서 확인됨(상관계수가 낮을수록 유리) — 단, 자산 자체 변동성·
    MDD도 함께 커지므로 순효과는 백테스트로 확인 필요. TQQQ+현금 같은
    레버리지 단일자산+현금 조합, 또는 UPRO/TMF류 저상관 페어(HFEA, 별도
    E2 문서)가 실전 응용 예로 언급됨 — 본 문서에서는 개념만 소개.
  - 체결가정: 리밸런싱일 종가 체결, 부분체결 미모델링(공통 가정 준용).
    데이터 요구: 대상 자산 일봉 종가 + 배당(현금 유입) — 공통 데이터 파이프라인
    재사용 가능.
```
