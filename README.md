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
      exclude_urls:
        - "example.com"
        - "another-domain.com/news"
    ```
    - **Naver API**: [네이버 개발자 센터](https://developers.naver.com/)에서 API 이용 신청 후 `client_id`와 `client_secret`을 발급받으세요.
    - **Telegram Bot**: `BotFather`를 통해 봇을 생성하고 `bot_token`을 발급받으세요. `chat_id`는 메시지를 받을 사용자의 ID 또는 채널의 ID입니다.
    - **Filter**: `keywords`에 원하는 키워드를, `exclude_keywords`에 제외하고 싶은 키워드를, `exclude_urls`에 제외하고 싶은 url을 추가하세요.

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

## LLM 뉴스 다이제스트

지정한 언론사의 하루치 기사 중 관심사에 맞는 기사를 LLM이 골라, 매일 저녁 요약 다이제스트를 텔레그램으로 보냅니다. 키워드 알림(`main.py`)과는 별개로 동작하며 별도 DB(`data/digest.db`)를 사용합니다.

### 동작 방식

1. **수집** (`collect`, 1시간마다): 언론사 RSS 또는 목록 페이지에서 제목·링크·요약만 모아 DB에 쌓습니다. 기사 본문은 열지 않습니다.
2. **선별** (`send`, 매일 18시): 지난 24시간 동안 모인 기사의 제목·요약과 관심사 설명을 저렴한 모델에 넘겨 관련 기사만 고릅니다.
3. **요약**: 선별된 기사만 본문을 열어 요약합니다. `fetch_body: false`인 언론사는 본문에 접근하지 않고 제목과 링크만 전달합니다.
4. **전송**: `digests` 항목마다 한 통씩 `telegram.chat_id`로 보냅니다. 길면 여러 메시지로 나눕니다.

### 설정

`config/config.yaml.example`의 `llm`, `digest` 섹션을 `config/config.yaml`에 추가합니다.

- `llm.provider`: `anthropic` 또는 `gemini`. 각 제공자별로 선별용(`screening_model`)과 요약용(`digest_model`) 모델을 지정합니다.
- `digest.sources`: 언론사 목록. `type: rss`는 `url`의 피드를, `type: html_list`는 `urls` 페이지에서 `link_pattern`이 포함된 링크를 수집합니다.
- `digest.digests`: `(언론사 목록, 관심사 설명)` 조합. `max_articles`로 기사 수 상한을 정합니다.

### 실행

```bash
./run_digest.sh collect          # 기사 수집
./run_digest.sh send --dry-run   # 전송하지 않고 다이제스트를 화면에 출력
./run_digest.sh send             # 다이제스트 전송
```

cron 설정 예시는 `run_digest.sh` 하단을 참고하세요. 서버 시간대가 UTC인 경우 `CRON_TZ=Asia/Seoul`을 지정해야 합니다.

## 개발 노트

> 이 프로젝트의 일부 코드는 **Google Gemini Code Assist**의 도움을 받아 작성되었습니다.
