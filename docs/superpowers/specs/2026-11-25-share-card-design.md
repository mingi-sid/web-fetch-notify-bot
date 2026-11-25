# 기사 공유 카드 생성 — 설계 (short)

## 목적
텔레그램 채팅에 기사 URL을 보내면, 개인 SNS에 올릴 1080×1080 정사각 카드 이미지를 답장으로 받는다. 로고·브랜딩 없음. LLM 사용 안 함.

## 목표 / 비목표
- 목표: 대표 이미지, 제목, 요약문(기본 on, 설정 가능), 출처(언론사), URL을 담은 카드.
- 비목표: 브랜딩, LLM 요약, 기존 cron 작업(main.py, digest_main.py) 변경.
- 실패로 볼 것: 단어 중간 줄바꿈, 중간에 끊긴 요약문, 출처가 "네이버 뉴스"로 표시, 제목 중복된 언론사명.

## 제약
- 서버: Oracle Always Free. long polling 상주는 CPU·트래픽 부담이 무시할 수준.
- 폰트는 서버마다 다르므로 경로를 설정으로 받는다.

## Approaches
1. **Long polling 상주 프로세스 (선택)** — systemd 서비스, 즉시 응답, python-telegram-bot 기본 방식.
2. Webhook — HTTPS/포트/웹서버 필요, 개인용엔 과함.
3. cron getUpdates — 최대 1분 지연, 매번 프로세스 기동이라 오히려 비효율.

## 스타일 (mingisidviz dark 토큰)
surface `#121005`, ink1 `#f3f2e9`(제목), ink2 `#d3d1c6`(요약·출처), muted `#adab9f`(URL), rule `#4f4d41`, key `#FFED00`(제목 위 짧은 막대 한 곳에만).
레이아웃(위→아래, 여백 64px): 키 막대 → 굵은 제목(최대 3줄) → 요약(최대 2줄) → 사진(남는 영역, cover-crop, 위쪽 기준) → 구분선 → "출처: 언론사" / URL(1줄).
이미지 없으면 사진 영역 없이 제목을 크게.

## 데이터 정리 규칙
- 메타데이터: og:title / og:description / og:image / og:site_name, 없으면 name·twitter 태그, 마지막으로 `<title>`·도메인.
- 출처: n.news.naver.com이면 페이지의 실제 언론사명 → og:site_name → 도메인.
- 제목: 끝의 " - 언론사", " | 언론사", " : 언론사" 제거.
- 요약: 앞머리 "[매체 OOO 기자]" 류 제거, 구두점 뒤 띄어쓰기 보정(숫자 포함), 문장부호로 끝나지 않으면 마지막 완결 문장까지 자르고 완결 문장이 없을 때만 "…".
- 줄바꿈은 어절 단위, 넘치면 "…".

## 구성
- `src/card.py`: 추출·정리·렌더링 (순수 함수 위주, 테스트 대상).
- `card_bot.py` + `run_card_bot.sh`: 메시지에서 URL 추출 → 카드 생성 → reply_photo. 실패 시 오류 문구 답장.
- `config.yaml`의 `card:` — `show_description`(기본 true), `allowed_chat_ids`, `font_bold`, `font_regular`.
- 의존성: Pillow 추가.

## 빌더 재량
폰트 크기 세부, 네이버 언론사명 셀렉터, systemd 유닛 예시 문구.
