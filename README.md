# 네이버 뉴스 텔레그램 봇 (Naver News Telegram Bot)

## 프로젝트 설명

이 프로젝트는 지정된 키워드로 네이버 뉴스를 주기적으로 검색하여, 새로운 뉴스가 있을 경우 텔레그램 봇으로 알림을 보내는 파이썬 애플리케이션입니다.

## 주요 기능

- 키워드 기반 네이버 뉴스 검색 (Naver Search API 사용)
- 텔레그램을 통한 실시간 뉴스 알림
- 중복 뉴스 발송 방지를 위한 전송 이력 관리 (SQLite 사용)
- 설정 파일을 통한 간편한 설정 (키워드, API 토큰 등)
- 알림 메시지 내 키워드 강조 및 언론사 정보 표시

## 디렉터리 구조

```
/
├── config/
│   ├── config.yaml.example     # 설정 파일 예시
│   ├── logging.yaml            # 로깅 설정
│   └── press_map.json          # 언론사 정보
├── data/
│   └── sent_news.db            # 전송된 뉴스 기록 (SQLite)
├── src/
│   ├── __init__.py
│   ├── fetcher.py              # 뉴스 수집
│   ├── filter.py               # 뉴스 필터링
│   ├── notifier.py             # 텔레그램 알림
│   └── storage.py              # DB 관리
├── .gitignore
├── main.py                     # 메인 실행 파일
├── README.md
├── requirements.txt            # 의존성 목록
└── run.sh                      # 실행 스크립트
```

## 설치 및 설정

1.  **저장소 복제**
    ```bash
    git clone <repository_url>
    cd web-fetch-notify-bot
    ```

2.  **가상 환경 생성 및 활성화**
    ```bash
    python3 -m venv .venv
    source .venv/bin/activate
    ```

3.  **의존성 설치**
    ```bash
    pip install -r requirements.txt
    ```

4.  **설정 파일 생성**
    `config/` 디렉토리에 `config.yaml` 파일을 생성하고, 아래 내용을 자신의 정보에 맞게 수정합니다. (`config.yaml.example` 파일을 복사하여 사용해도 됩니다.)

    ```yaml
    # config/config.yaml
    naver:
      client_id: "YOUR_NAVER_CLIENT_ID"
      client_secret: "YOUR_NAVER_CLIENT_SECRET"

    telegram:
      bot_token: "YOUR_TELEGRAM_BOT_TOKEN"
      chat_id: "YOUR_TELEGRAM_CHAT_ID" # 또는 channel ID

    filter:
      keywords:
        - "검색할 키워드 1"
        - "검색할 키워드 2"
      exclude_keywords:
        - "제외할 키워드"
    ```
    - **Naver API**: [네이버 개발자 센터](https://developers.naver.com/)에서 API 이용 신청 후 `client_id`와 `client_secret`을 발급받으세요.
    - **Telegram Bot**: `BotFather`를 통해 봇을 생성하고 `bot_token`을 발급받으세요. `chat_id`는 메시지를 받을 사용자의 ID 또는 채널의 ID입니다.

## 사용법

프로젝트 루트 디렉토리에서 아래 스크립트를 실행합니다.

```bash
./run.sh
```

또는 `main.py`를 직접 실행할 수도 있습니다.

```bash
python main.py
```

`cron`이나 `systemd timer`를 사용하여 주기적으로 스크립트를 실행하도록 설정하면 자동화된 뉴스 모니터링이 가능합니다.

## 개발 노트

> 이 프로젝트의 일부 코드는 **Google Gemini Code Assist**의 도움을 받아 작성되었습니다.
