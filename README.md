# 모압매수 자동매매 시스템

한국투자증권 OpenAPI로 **미국 주식을 매일 자동 주문**하고, 결과를 **텔레그램으로 알림**, 로우데이터를 **구글 스프레드시트 + SQLite**에 기록하는 시스템입니다. AWS EC2에서 크론으로 돌아갑니다.

## 하루 흐름

```
평일 18:10 (한국시간)
  └─ config/orders.yaml 기준 매수 2종목 + 매도 2종목 예약주문
  └─ 📱 텔레그램: "예약주문 완료" + 종목/수량/지정가
  └─ 📊 구글시트 '주문' 탭 + SQLite 기록

그날 밤 22:30~05:00 미국장에서 체결

다음날 08:20 (화~토)
  └─ 전일 주문 체결내역 조회
  └─ 📱 텔레그램: "체결 완료" (체결가/수량/금액, 미체결 여부)
  └─ 📊 구글시트 '체결' 탭 + SQLite 기록
```

## 프로젝트 구조

```
config/orders.yaml     ← 매일 주문할 종목/수량 설정 (여기만 고치면 됨)
moap/
  strategy.py          ← 종목 선정 로직 (★모압매수 로직 통합 지점)
  kis_client.py        ← 한국투자 OpenAPI (토큰, 시세, 예약주문, 체결조회)
  place_orders.py      ← 18:10 잡
  check_fills.py       ← 08:20 잡
  telegram_notify.py   ← 텔레그램 알림
  sheets.py            ← 구글시트 기록
  storage.py           ← SQLite 백업
scripts/
  setup_ec2.sh         ← EC2 초기 설정
  crontab.example      ← 크론 설정
```

## 설치 (EC2 기준)

### 1. 사전 준비물 (각 사이트에서 발급)

| 항목 | 발급처 |
|---|---|
| KIS 모의투자 APP KEY/SECRET | [KIS Developers](https://apiportal.koreainvestment.com) → 모의투자 신청 후 키 발급 |
| 텔레그램 봇 토큰 | 텔레그램 @BotFather → `/newbot` |
| 텔레그램 chat_id | 봇에게 메시지 1개 보낸 후 `https://api.telegram.org/bot<토큰>/getUpdates` 접속해서 `chat.id` 확인 |
| 구글 서비스계정 JSON | [Google Cloud Console](https://console.cloud.google.com) → 프로젝트 생성 → Sheets API 사용 설정 → 서비스계정 생성 → 키(JSON) 다운로드 |
| 구글 스프레드시트 | 새 시트 생성 → **서비스계정 이메일에 편집자로 공유** → URL의 시트 ID 복사 |

### 2. 서버 설정

```bash
git clone https://github.com/dimode95-lab/cw.git
cd cw
bash scripts/setup_ec2.sh   # 시간대(KST)·파이썬·의존성 자동 설치
nano .env                   # 발급받은 키들 입력
# service_account.json 을 저장소 루트에 업로드 (scp 등)
```

### 3. 연결 테스트

```bash
.venv/bin/python -m moap test-telegram   # 텔레그램으로 테스트 메시지 도착하면 OK
.venv/bin/python -m moap test-kis        # AAPL 현재가 출력되면 OK
.venv/bin/python -m moap test-sheets     # 구글시트 '주문' 탭에 행 추가되면 OK
```

### 4. DRY RUN → 모의투자 → 실전 순서로 검증

```bash
# ① .env 에 DRY_RUN=true 상태로 (실제 주문 없이 알림/기록만)
.venv/bin/python -m moap place

# ② 괜찮으면 DRY_RUN=false 로 바꾸고 모의투자 주문 테스트
.venv/bin/python -m moap place
# 다음날 아침
.venv/bin/python -m moap check

# ③ 며칠 검증 후 실전 전환: .env 에서
#    KIS_ENV=real + 실전용 APP KEY/SECRET/계좌번호로 교체
```

### 5. 자동 실행 등록

```bash
crontab -e
# scripts/crontab.example 내용을 붙여넣기 (경로 확인!)
```

## 종목/수량 바꾸기

`config/orders.yaml` 만 수정하면 됩니다. 다음 18:10 주문부터 바로 반영됩니다.

## 모압매수 로직 통합하기

지금은 yaml에 적힌 종목을 그대로 주문합니다. 데스크탑 `C:\dev` 의 모압매수 앱 코드를 이 저장소에 올리면 `moap/strategy.py` 의 `select_orders()` 를 그 계산 로직으로 교체해서, 매일 18:10에 **자동으로 종목을 계산 → 주문**하도록 확장할 수 있습니다.

## 주의사항

- **미국 휴장일**에는 주문이 체결되지 않으며, 다음날 아침 "체결 내역 없음/미체결" 알림이 옵니다.
- KIS **모의투자는 일부 API(해외 예약주문 등)를 지원하지 않을 수 있습니다.** `test-kis` 는 되는데 `place` 에서 "지원하지 않는 TR" 류의 오류가 나면, 모의투자 제약이므로 실전 키로 소액 테스트하거나 주문 시각을 미국장 개장 직후(22:35)로 옮겨 일반주문으로 전환해야 합니다.
- TR ID는 [KIS Developers 문서](https://apiportal.koreainvestment.com) 기준이며 변경될 수 있으니 오류 시 문서를 확인하세요 (`moap/kis_client.py` 상단에 모여 있음).
- `.env`, `service_account.json` 은 절대 깃에 커밋하지 마세요 (`.gitignore` 처리됨).
