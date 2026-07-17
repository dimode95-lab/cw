"""B1. 밸류 리밸런싱 VR5.0 (catalog/B1-밸류리밸런싱-VR5.0.md 채택 가정 구현).

2주(10거래일)마다 평가금(보유수량×종가)이 목표값 V의 ±band 밴드를 벗어나면 V로
복귀시킬 만큼 매수/매도(MOC)한다. 밴드 안이면 무매매. **매 평가 사이클마다(체결 유무와
무관하게) 다음V = V + pool/G + 적립금 으로 갱신한다** — 아래 가정 3 참고.

## 채택 가정 (catalog "미확정/가정 필요" 절 + 이 구현이 추가로 확정한 것)

1. **목표 복귀지점 = V (catalog 가정 A)**: catalog 원문 의사코드가 채택한 방식을 그대로
   따른다(밴드 경계가 아니라 V 자체로 복귀). catalog가 명시한 대안(가정 B: 밴드 경계로
   복귀)은 구현하지 않았다 — 필요하면 별도 파라미터로 확장 가능.
2. **평가 캘린더 = 정확한 거래일 카운트(sma200.py와 동일한 해법)**: "2주(10거래일)"을
   실제 데이터의 거래일 인덱스로 정확히 센다. `sma200.py`가 200일 이동평균을 위해
   price_history를 미리 받아 date→index를 구축한 것과 동일한 패턴 — 생성자에
   `price_history`(이 티커의 전체 백테스트 구간 OHLC)를 받아 `date→trading_day_index`
   맵을 만들고, `index % eval_interval_trading_days == 0`인 날을 평가일로 판정한다
   (달력일 근사가 아니라 데이터의 실제 거래일을 그대로 세므로 휴장일 근처 근사 오차가
   없다).
3. **V·Pool은 `mumae.py`와 동일한 패턴으로 "전략 인스턴스 속성"이 권위값이다 — 매
   평가일마다 체결 유무와 무관하게 V를 갱신한다.**
   최초 구현은 "V/Pool 갱신은 실제 체결이 있는 사이클에서만" 방식이었으나, 코디네이터
   검토에서 방법론 왜곡(밴드 안/무거래 사이클이 많은 VR 특성상 V 경로가 계통적으로
   낮아짐)으로 반려되어 이 패턴으로 교체했다. `core.py`의 계약("state는 on_fill에서만
   갱신되고, on_fill은 그날 체결이 있을 때만 호출된다")은 여전히 유효하지만, 그 규칙이
   구속하는 대상은 **엔진이 스레딩하는 `state`(`VRState`) 매개변수**이지 전략 구현체
   자신의 인스턴스 속성이 아니다 — `mumae.py`가 모드 전환(`self._mode_cache`)·가격이력
   (`self._prev_close`, `self._recent_closes`)에 쓴 것과 정확히 같은 해법이다
   (`mumae.py` 모듈 docstring "상태 소유권에 대한 설계 결정" 절 참고). 이 구현은
   `self._V`/`self._pool`을 그 권위값으로 두고, `on_bar`가 평가일마다 **무조건**
   `self._V = self._V + self._pool/G + 적립금`을 갱신한다("bars+fills로부터 결정론적으로
   재유도되는 값"이므로 재현성은 훼손되지 않는다 — 같은 가격 이력을 다시 넣으면 항상 같은
   `self._V` 경로가 나온다). `self._pool`은 실제 체결이 있어야만 바뀌므로(매수/매도 금액
   가감) `on_fill`에서 갱신한다.
   **문언과 어긋나는 지점(명시)**: `on_bar`는 이제 그 자신의 결과(주문)와 무관하게
   `self._V`라는 부수효과를 갖는다 — "on_bar는 state를 읽어 주문을 만들 뿐 반환값 외의
   부수효과로 state를 변형해서는 안 된다"는 core.py 문언은 **엔진이 스레딩하는 `state`
   매개변수**에 대해서만 지켜진다(그 매개변수 자체는 절대 변형하지 않는다 — 아래
   `on_bar`가 `state`를 읽기만 하고 한 번도 대입하지 않는 것을 확인할 것). 엔진에
   전달/반환되는 `VRState`(`state`)는 `self._V`/`self._pool`의 **리포팅용 미러**일 뿐이며,
   `on_fill`이 실제로 호출된 날에만 동기화된다 — 밴드 안(무거래) 사이클이 연속되는 동안은
   `run_backtest(...).final_state.V`가 최신값보다 지연될 수 있다(마지막 평가일이 무거래로
   끝난 경우). **매매 판단 자체는 항상 `self._V`(최신값)로 이루어지므로 이 지연은 리포팅
   필드에만 있는 문제이지 전략의 실제 행동에는 영향이 없다.** 정확한 최신값이 필요하면
   `VRStrategy.current_V`/`current_pool` 프로퍼티를 직접 읽는다(런 종료 후에도 같은
   전략 인스턴스를 계속 들고 있으면 접근 가능).
4. **Pool은 전략이 자체 부기**(포트폴리오 현금과 별개 부기, `on_fill`이 portfolio를
   받지 못하므로 불가피): 체결가·수량·수수료로 직접 가감한다. 호출자는
   `VRStrategy.initial_state()`의 `pool0`을 `run_backtest(initial_cash=...)`와 반드시
   같은 값으로 맞춰야 한다. TQQQ 배당은 미미하다는 catalog 가정에 따라 배당으로 인한
   실제 포트폴리오 현금 증가는 이 자체 부기 Pool에 반영하지 않는다(알려진 한계 — 배당이
   있으면 pool과 실제 현금이 미세하게 어긋난다).
5. **적립금(contribution)은 V 목표식에만 반영되고 실제 현금 유입은 없다**:
   core.Portfolio에는 매수/매도/배당 외의 입금 프리미티브가 없어 "적립식"의 실제 현금
   투입을 재현할 수 없다 — 기본값 0(거치식)만 검증 대상이고, 0이 아닌 값은 V만 앞서
   나가고 실제로 살 수 없는 상태를 유발할 수 있는 미완성 기능임을 명시한다.
6. **Pool 사용 한도 기본값 0.75**(과업 지시 "적립식 75% 기본"을 파라미터 기본값으로
   채택). catalog의 거치식(50%)/인출식(25%)은 호출자가 `pool_limit`으로 직접 지정한다.
7. **반올림**: V·밴드 경계는 센트 HALF_UP(catalog 제안, core.round_cents), 매수/매도
   수량은 정수 내림(DOWN).
8. **주문 유형 = MOC**(catalog가 "미확정, 종가체결로 단순화 권장"한 것을 과업 지시대로
   채택).
9. **매수 수량에 수수료 버퍼 적용**: `_util.max_affordable_qty`로 계산해, 계산된
   buy_value가 수수료 때문에 broker_sim에서 insufficient_cash로 통째 거부되는 것을
   방지한다(DCA/SMA200과 동일한 이유·동일한 헬퍼 재사용).
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from datetime import date as Date
from decimal import ROUND_DOWN, Decimal
from pathlib import Path
from typing import Dict, List, Optional

_BACKTESTER_DIR = str(Path(__file__).resolve().parent.parent)
if _BACKTESTER_DIR not in sys.path:
    sys.path.insert(0, _BACKTESTER_DIR)

from broker_sim import DEFAULT_FEE_RATE  # noqa: E402
from core import Fill, OHLC, Order, OrderType, PortfolioView, Side, Strategy, round_cents  # noqa: E402

from strategies._util import max_affordable_qty  # noqa: E402

ROLE_BUY = "VR_BUY"
ROLE_SELL = "VR_SELL"


@dataclass
class VRState:
    """엔진이 스레딩하는 리포팅용 미러. 권위값은 `VRStrategy` 인스턴스의
    `self._V`/`self._pool` — 모듈 docstring 가정 3 참고."""

    V: Decimal
    pool: Decimal
    cycles_traded: int = 0  # 참고용: 실제 매매가 발생한 평가 사이클 수


class VRStrategy(Strategy):
    """밸류 리밸런싱 VR5.0. 단일 종목 + 현금 Pool 구조 (catalog B1 참조)."""

    def __init__(
        self,
        ticker: str,
        price_history: List[OHLC],
        band: Decimal = Decimal("0.15"),
        G: int = 10,
        pool_limit: Decimal = Decimal("0.75"),
        contribution: Decimal = Decimal("0"),
        contribution_interval_cycles: int = 1,
        eval_interval_trading_days: int = 10,
        fee_rate_hint: Decimal = DEFAULT_FEE_RATE,
    ) -> None:
        self.ticker = ticker
        self.band = band if isinstance(band, Decimal) else Decimal(str(band))
        self.G = Decimal(G)
        self.pool_limit = (
            pool_limit if isinstance(pool_limit, Decimal) else Decimal(str(pool_limit))
        )
        self.contribution = (
            contribution if isinstance(contribution, Decimal) else Decimal(str(contribution))
        )
        self.contribution_interval_cycles = contribution_interval_cycles
        self.eval_interval_trading_days = eval_interval_trading_days
        self.fee_rate_hint = fee_rate_hint

        sorted_bars = sorted(price_history, key=lambda b: b.date)
        self._date_index: Dict[Date, int] = {b.date: i for i, b in enumerate(sorted_bars)}

        # 권위값(가정 3) — 최초 on_bar/on_fill 호출 시 initial_state()로부터 시드된다.
        self._V: Optional[Decimal] = None
        self._pool: Optional[Decimal] = None
        self._cycles_traded: int = 0

    @staticmethod
    def initial_state(V0: Decimal, pool0: Decimal) -> VRState:
        """pool0은 run_backtest(initial_cash=...)와 반드시 같은 값이어야 한다(가정 4)."""
        return VRState(V=V0, pool=pool0)

    @property
    def current_V(self) -> Optional[Decimal]:
        """가장 최신 V(리포팅 지연 없는 권위값). 아직 on_bar가 한 번도 안 불렸으면 None."""
        return self._V

    @property
    def current_pool(self) -> Optional[Decimal]:
        """가장 최신 Pool(리포팅 지연 없는 권위값)."""
        return self._pool

    def _seed_if_needed(self, state: VRState) -> None:
        if self._V is None:
            self._V = state.V
        if self._pool is None:
            self._pool = state.pool

    def _cycle_index(self, today: Date) -> Optional[int]:
        idx = self._date_index.get(today)
        if idx is None:
            return None
        return idx // self.eval_interval_trading_days

    def _is_eval_day(self, today: Date) -> bool:
        idx = self._date_index.get(today)
        if idx is None:
            return False
        return idx % self.eval_interval_trading_days == 0

    def _contribution_for(self, cycle_idx: int) -> Decimal:
        if self.contribution == 0 or cycle_idx <= 0:
            return Decimal("0")
        if cycle_idx % self.contribution_interval_cycles == 0:
            return self.contribution
        return Decimal("0")

    def on_bar(
        self, state: VRState, bars: Dict[str, OHLC], portfolio: PortfolioView
    ) -> List[Order]:
        bar = bars.get(self.ticker)
        if bar is None:
            return []
        self._seed_if_needed(state)  # state 매개변수는 읽기만 한다 — 대입하지 않는다.
        if not self._is_eval_day(bar.date):
            return []

        # 매 평가일마다 체결 유무와 무관하게 V를 갱신한다(가정 3 — self._V/self._pool은
        # 인스턴스 속성이라 engine.py의 "state는 on_fill에서만" 계약 대상이 아니다).
        cycle_idx = self._cycle_index(bar.date) or 0
        contribution = self._contribution_for(cycle_idx)
        self._V = round_cents(self._V + (self._pool / self.G) + contribution)

        band_lower = round_cents(self._V * (Decimal("1") - self.band))
        band_upper = round_cents(self._V * (Decimal("1") + self.band))

        price = bar.close
        qty_held = portfolio.position(self.ticker).qty
        current_value = price * qty_held

        if current_value > band_upper:
            sell_value = current_value - self._V
            sell_qty = int((sell_value / price).to_integral_value(rounding=ROUND_DOWN))
            sell_qty = min(sell_qty, qty_held)
            if sell_qty > 0:
                return [Order(self.ticker, Side.SELL, OrderType.MOC, None, sell_qty, ROLE_SELL)]
        elif current_value < band_lower:
            max_buy_value = self._pool * self.pool_limit
            buy_value = self._V - current_value
            if buy_value > max_buy_value:
                buy_value = max_buy_value
            if buy_value > portfolio.cash:
                buy_value = portfolio.cash
            if buy_value > 0:
                buy_qty = max_affordable_qty(buy_value, price, self.fee_rate_hint)
                if buy_qty > 0:
                    return [Order(self.ticker, Side.BUY, OrderType.MOC, None, buy_qty, ROLE_BUY)]
        return []

    def on_fill(self, state: VRState, fills: List[Fill]) -> VRState:
        self._seed_if_needed(state)
        for f in fills:
            if f.order.ticker != self.ticker or f.order.role not in (ROLE_BUY, ROLE_SELL):
                continue
            if f.order.side == Side.BUY:
                self._pool = self._pool - (f.price * f.order.qty + f.fee)
            else:
                self._pool = self._pool + (f.price * f.order.qty - f.fee)
            self._cycles_traded += 1
        # 리포팅용 미러 동기화(가정 3) — 권위값은 여전히 self._V/self._pool.
        return VRState(V=self._V, pool=self._pool, cycles_traded=self._cycles_traded)
