#!/usr/bin/env bash
# AWS EC2 (Ubuntu) 초기 설정 스크립트
# 사용법: EC2에 접속한 뒤  bash scripts/setup_ec2.sh
set -euo pipefail

echo "== 1. 시간대를 Asia/Seoul 로 변경 =="
sudo timedatectl set-timezone Asia/Seoul

echo "== 2. 파이썬 설치 =="
sudo apt-get update -y
sudo apt-get install -y python3 python3-venv python3-pip

echo "== 3. 가상환경 + 의존성 설치 =="
cd "$(dirname "$0")/.."
python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt

echo "== 4. 설정 파일 준비 =="
if [ ! -f .env ]; then
  cp .env.example .env
  echo "  → .env 파일을 생성했습니다. 반드시 편집해서 API 키를 넣으세요: nano .env"
fi
mkdir -p logs

echo ""
echo "완료! 다음 단계:"
echo "  1) nano .env                          # API 키 입력"
echo "  2) service_account.json 업로드         # 구글 서비스계정 키"
echo "  3) .venv/bin/python -m moap test-telegram"
echo "  4) .venv/bin/python -m moap test-kis"
echo "  5) .venv/bin/python -m moap test-sheets"
echo "  6) crontab -e                         # scripts/crontab.example 내용 등록"
