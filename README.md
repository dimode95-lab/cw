# 무한매수법 v4.0 자동매매 시스템

라오어 **무한매수법 v4.0** (TQQQ/SOXL)을 한국투자증권 OpenAPI로 자동 실행하고, 결과를 **텔레그램으로 알림**, 로우데이터를 **구글 스프레드시트 + SQLite**에 기록하는 시스템입니다. AWS EC2에서 크론으로 돌아갑니다.

## 하루 흐름

```
평일 18:10 (한국시간)
  └─ 종목별 상태(T값·평단·잔금)로 오늘의 주문표 자동 계산
     · 일반모드 전반전: 별지점-0.01 LOC ½ + 평단 LOC ½ + 하락대비 사다리
     · 일반모드 후반전: 별지점-0.01 LOC 전량 + 사다리
     · 매도: 쿼터매도 LOC(별지점) + 지정가매도(평단+15%/20%)
     · 리버스모드: MOC/LOC 매도 + 쿼터매수 (별지점 = 5일 종가평균)
     · 큰수매수: 첫 매수/급락 시 전일종가 +10% 로 자동 전환
  └─ 📱 텔레그램: 주문표 + 현재 상태 (T, 평단, 별지점, 잔금)

그날 밤 22:30~05:00 미국장 마감 때 LOC/MOC 체결

다음날 08:20 (화~토)
  └─ 체결 확인 → T값·평단·잔금·모드 자동 갱신
     (쿼터매도 T×0.75, 지정가매도 T×0.25, 1회매수 +1, 절반매수 +0.5,
      소진 시 리버스모드 진입, 사이클 종료 시 원금 재설정)
  └─ 📱 텔레그램: 체결 내역 + 갱신된 상태 + 이벤트(사이클 종료 등)
  └─ 📊 구글시트 기록
```

## 구글시트 구조 (기존 엑셀과 동일)

| 탭 | 내용 |
|---|---|
| `주문` | 매일 나간 주문 로우데이터 (가격/수량/주문번호/성공여부) |
| `체결` | 매일 체결 로우데이터 |
| `DB` | 엑셀 DB 시트와 같은 일일 스냅샷: 날짜·전략명·모드·종가·평단가·보유수량·T값·P값(⭐%)·5일평균·매입금액·잔금·1회매수금·실현손익·주문요약 |
| `수익 일지` | 사이클 종료 시: 종료날짜·종목·시작원금·종료금액·수익금·수익률·최종T |

서버의 SQLite(`moap.db`)에도 동일 데이터 + 원시 API 응답이 백업됩니다.

## 프로젝트 구조

```
config/mubae.yaml      ← 종목/원금/분할수 설정
moap/
  mubae.py             ← 무한매수법 v4.0 엔진 (별%·T값·매수표·리버스모드)
  kis_client.py        ← 한국투자 OpenAPI (LOC/MOC/지정가 주문, 시세, 체결)
  place_orders.py      ← 18:10 잡 / check_fills.py ← 08:20 잡
  state_store.py       ← 종목별 상태(T·평단·잔금) SQLite 저장
  sheets.py / storage.py / telegram_notify.py
tests/test_mubae.py    ← 방법론 문서 예시 숫자로 엔진 검증 (41개 통과)
scripts/setup_ec2.sh · crontab.example
```

## 설치 (EC2 기준)

### 1. 사전 준비물

| 항목 | 발급처 |
|---|---|
| KIS APP KEY/SECRET | [KIS Developers](https://apiportal.koreainvestment.com) |
| 텔레그램 봇 토큰 | @BotFather → `/newbot` |
| 텔레그램 chat_id | 봇에게 메시지 보낸 후 `https://api.telegram.org/bot<토큰>/getUpdates` 의 `chat.id` |
| 구글 서비스계정 JSON | Google Cloud Console → Sheets API 활성화 → 서비스계정 키 다운로드 |
| 구글 스프레드시트 | 새 시트 생성 → 서비스계정 이메일에 **편집자 공유** → URL의 시트 ID |

### 2. 서버 설정 & 테스트

```bash
git clone https://github.com/dimode95-lab/cw.git && cd cw
bash scripts/setup_ec2.sh        # KST 시간대·파이썬·의존성 자동 설치
nano .env                        # 키 입력 (.env.example 참고)
# service_account.json 업로드

.venv/bin/python -m moap test-telegram
.venv/bin/python -m moap test-kis
.venv/bin/python -m moap test-sheets

nano config/mubae.yaml           # 원금/분할수 확인 (기본: 각 $10,000 · 40분할)
.venv/bin/python -m moap init-state   # T=0, 잔금=원금으로 시작
.venv/bin/python -m moap status       # 상태 확인
```

### 3. 검증 순서: DRY_RUN 시뮬레이션 → 실전

```bash
# ① DRY_RUN=true (기본): 실제 주문 없이 매일 주문표를 계산하고,
#    다음날 아침 실제 종가로 LOC/MOC 체결을 "시뮬레이션"하여 상태를 굴립니다.
#    → 진짜 페이퍼 트레이딩. 며칠 돌려보며 텔레그램 알림과 시트 기록을 확인하세요.
.venv/bin/python -m moap place   # 저녁
.venv/bin/python -m moap check   # 다음날 아침

# ② 검증 후 실전 전환: .env 에서
#    DRY_RUN=false / KIS_ENV=real / 실전 APP KEY·SECRET·계좌번호
#    ⚠️ 실전 전환 시 init-state --force 로 상태를 리셋하고 시작하세요.
```

> **모의투자 계좌 주의**: KIS 모의투자는 미국주식 **LOC/MOC 주문을 지원하지 않습니다.**
> 무한매수법은 LOC가 핵심이므로, 페이퍼 검증은 모의투자 주문이 아니라 **DRY_RUN 시뮬레이션**으로 하도록 설계했습니다 (`KIS_ENV=paper`는 시세 조회용으로만 사용).

### 4. 자동 실행 등록

```bash
crontab -e   # scripts/crontab.example 내용 붙여넣기
```

## 무한매수법 파라미터 (config/mubae.yaml)

- `principal` 원금, `divisions` 분할수(20/40), `target_pct` 지정가매도 % (TQQQ 15 / SOXL 20 — 별% 공식 `target_pct × (1 - 2T/분할수)` 도 여기서 유도)
- `big_pct` 큰수매수 % (기본 10), `ladder_levels` 하락 대비 1주 LOC 단계 수 (기본 8)
- `compound` 사이클 종료 시 복리 재투자 여부

## 주의사항

- **주문 접수 시간**: 18:10 LOC 주문이 "주문 가능 시간이 아닙니다" 오류를 내면, 크론을 미국장 개장 직후(서머타임 22:35 / 비서머타임 23:35)로 옮기세요. LOC는 장마감 때 체결되므로 결과는 동일합니다.
- **매도 거부**: 큰 하락장에서 별지점 매도가 현재가와 너무 멀면 증권사가 거부합니다. 방법론대로 정상이며(매도점을 바꾸지 않음), 알림에 실패 사유가 표시됩니다.
- **수동 개입 금지**: 이 시스템은 자체 상태(T·평단·잔금)로 굴러갑니다. HTS/MTS에서 수동 매매하면 상태가 어긋나요. 수동 개입했다면 `init-state --force` 후 원금·상태를 다시 맞춰야 합니다.
- TR ID 등은 [KIS Developers 문서](https://apiportal.koreainvestment.com) 기준이며 오류 시 `moap/kis_client.py` 상단에서 수정하세요.
- `.env`, `service_account.json`, `moap.db` 는 커밋되지 않습니다.

## 면책

이 소프트웨어는 교육/개인 자동화 목적입니다. 투자 손실에 대한 책임은 본인에게 있으며, 무한매수법의 저작권은 '라오어'님에게 있습니다.
