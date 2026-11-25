# 기사 공유 카드 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 텔레그램으로 받은 기사 URL을 1080×1080 공유 카드 PNG로 만들어 답장한다.

**Architecture:** `src/card.py`가 메타데이터 추출·텍스트 정리(순수 함수)·Pillow 렌더링을 맡고, `card_bot.py`가 python-telegram-bot 22 `Application.run_polling()`으로 메시지를 받아 `reply_photo`한다. 기존 cron 진입점은 건드리지 않는다.

**Tech Stack:** Python 3, requests, beautifulsoup4, Pillow, python-telegram-bot 22.5, pytest.

**Spec:** `docs/superpowers/specs/2026-11-25-share-card-design.md`

## Global Constraints
- 캔버스 1080×1080, 여백 64px. 색: surface `#121005`, ink1 `#f3f2e9`, ink2 `#d3d1c6`, muted `#adab9f`, rule `#4f4d41`, key `#FFED00`(제목 위 막대 한 곳만).
- LLM 사용 금지. 브랜딩/로고 없음.
- 의존성 추가는 Pillow(+ 개발용 pytest)만.
- HTTP는 `src/sources.py`의 `_get(url, user_agent)`와 `DEFAULT_USER_AGENT` 재사용.

## Review Focus
1. og 태그가 전혀 없는 페이지 → `<title>`·도메인으로 카드가 나와야 함 (Task 1 `test_parse_meta_fallbacks`).
2. og:image가 404·비이미지 → 예외 없이 이미지 없는 레이아웃 (Task 2 `test_render_without_image`, `fetch_image` None 처리).
3. 메시지에 URL이 없거나 여러 개 → 없으면 무시, 여러 개면 각각 카드 (Task 3 `test_extract_urls`).
4. 허용되지 않은 chat id → 무응답 (Task 3 `test_is_allowed`).
5. 매우 긴 제목/공백 없는 긴 토큰 → 3줄 안에서 "…"로 끝남, 폭 초과 없음 (Task 1 `test_wrap_long_token`).

---

### Task 1: 메타데이터 추출과 텍스트 정리

**Files:**
- Create: `src/card.py`, `tests/__init__.py`, `tests/test_card.py`, `tests/fixtures/` (HTML 3개: og 완비, og 없음, 네이버)
- Modify: `requirements.txt` (Pillow 추가)

**Interfaces:**
- Produces:
  - `@dataclass ArticleMeta(title: str, description: str, image_url: Optional[str], source: str, url: str)`
  - `parse_meta(html: str, url: str) -> ArticleMeta` — 네트워크 없음
  - `fetch_meta(url: str) -> Optional[ArticleMeta]` — `_get` 후 최종 URL(`response.url`)로 `parse_meta`
  - `clean_title(title: str, source: str) -> str`
  - `clean_description(desc: str) -> str`
  - `wrap_text(draw: ImageDraw.ImageDraw, text: str, font, width: int, max_lines: int) -> List[str]`

- [ ] **Step 1: 실패 테스트 작성** (`tests/test_card.py`)

```python
def test_clean_title_strips_source_suffix():
    assert clean_title("과속하는 인공지능에 브레이크를 걸다 - 단비뉴스", "단비뉴스") == "과속하는 인공지능에 브레이크를 걸다"
    assert clean_title("제목 | 충청투데이", "충청투데이") == "제목"
    assert clean_title("A - B 대결", "단비뉴스") == "A - B 대결"

def test_clean_description_byline_spacing_and_cut():
    assert clean_description("[충청투데이 권오선 기자] 정부가 발표했다.") == "정부가 발표했다."
    assert clean_description("적발건수가,5년여간 늘었다.") == "적발건수가, 5년여간 늘었다."
    assert clean_description("수렴해 왔다. 그") == "수렴해 왔다."
    assert clean_description("끝나지 않는 문장") == "끝나지 않는 문장…"
    assert clean_description("3.5% 올랐다.") == "3.5% 올랐다."   # 소수점은 건드리지 않음

def test_parse_meta_og(): ...        # fixture og 완비 → title/description/image_url/source(og:site_name)
def test_parse_meta_fallbacks(): ... # og 없음 → <title>, meta description, image None, source=도메인(www. 제거)
def test_parse_meta_naver_press():   # 네이버 fixture → source == 실제 언론사명 ("네이버 뉴스" 아님)
    assert m.source != "네이버 뉴스"

def test_wrap_breaks_on_words(): ... # 반환된 모든 줄이 어절 경계, textlength <= width
def test_wrap_long_token():         # 공백 없는 200자 → len<=3, 마지막 줄 "…"로 끝, 각 줄 폭 <= width
```

- [ ] **Step 2: 실패 확인** — `.venv/bin/pip install Pillow pytest && .venv/bin/python -m pytest tests -q` → ImportError.
- [ ] **Step 3: 구현.** 규칙(spec "데이터 정리 규칙"):
  - 메타 우선순위: `og:*` → `name="description"`/`twitter:*` → `<title>`·도메인.
  - 네이버(`n.news.naver.com`): `.media_end_head_top_logo img[title]` 또는 `alt`, 없으면 `meta[name="twitter:creator"]`; 실제 fixture로 셀렉터 확인.
  - 바이라인 정규식은 맨 앞 `[...기자...]`/`(...기자...)`만. 쉼표/마침표 뒤 공백 보정은 "숫자.숫자"(소수점) 제외.
  - 문장 종결(`.!?…"'”’` 로 끝)이 아니면 마지막 `[.!?]` 뒤를 자르고, 없으면 "…".
  - `wrap_text`: 어절 단위, 한 어절이 폭 초과면 글자 단위로 쪼갬, `max_lines` 초과 시 마지막 줄 "…".
- [ ] **Step 4: 통과 확인** — `.venv/bin/python -m pytest tests -q` → all passed.
- [ ] **Step 5: Commit** — `feat: extract and clean article metadata for share cards`

### Task 2: 카드 렌더링

**Files:** Modify `src/card.py`, `tests/test_card.py`

**Interfaces:**
- Consumes: Task 1 전부.
- Produces:
  - `@dataclass CardStyle(font_bold: str, font_regular: str, show_description: bool = True)`
  - `fetch_image(url: Optional[str]) -> Optional[Image.Image]` — 실패 시 None
  - `render_card(meta: ArticleMeta, image: Optional[Image.Image], style: CardStyle) -> Image.Image`
  - `make_card_png(url: str, style: CardStyle) -> Optional[bytes]` — fetch_meta 실패 시 None

- [ ] **Step 1: 실패 테스트**

```python
def test_render_size_and_key_bar():   # 크기 (1080,1080); 픽셀 (64+10, 64+4) == key 색
def test_render_without_image():      # image=None → 예외 없음, 사진 영역 대신 제목 크게(폰트 크기 > 이미지 있을 때)
def test_render_hides_description():  # show_description=False → 요약 영역 픽셀이 surface 색만
```
폰트는 테스트에서 `/usr/share/fonts/truetype/nanum/NanumSquareB.ttf`, 없으면 `pytest.skip`.

- [ ] **Step 2: 실패 확인.**
- [ ] **Step 3: 구현.** 레이아웃(spike `spike2.py`와 동일): 키 막대 72×8 → 제목 54px bold 최대 3줄(행간 70) → 요약 30px regular 최대 2줄(행간 44) → 사진(남은 영역, 가로 가운데·세로 위쪽 기준 cover-crop) → 하단 구분선(바닥 −124px) → "출처: {source}" 24px ink2 / URL(scheme·www. 제거) 24px muted 1줄. 이미지 없으면 제목 72px 최대 6줄.
- [ ] **Step 4: 통과 확인** + 수동 확인: `.venv/bin/python -c "from src.card import *; open('/tmp/c.png','wb').write(make_card_png('https://www.danbinews.com/news/articleView.html?idxno=34203', CardStyle(...)))"` 후 이미지 열어 제목에 "- 단비뉴스" 없음, 요약 "…수렴해 왔다."로 끝남.
- [ ] **Step 5: Commit** — `feat: render share cards in mingisidviz style`

### Task 3: 텔레그램 봇과 실행 설정

**Files:**
- Create: `card_bot.py`, `run_card_bot.sh`, `tests/test_card_bot.py`
- Modify: `config/config.yaml.example`, `README.md`

**Interfaces:**
- Consumes: `CardStyle`, `make_card_png`.
- Produces: `extract_urls(text: str) -> List[str]`, `is_allowed(chat_id: int, allowed: List[int]) -> bool`

- [ ] **Step 1: 실패 테스트**

```python
def test_extract_urls():
    assert extract_urls("이거 https://a.com/x?id=1 봐") == ["https://a.com/x?id=1"]
    assert extract_urls("없음") == []
    assert extract_urls("https://a.com https://b.com") == ["https://a.com", "https://b.com"]
def test_is_allowed():
    assert is_allowed(1, [1]) and not is_allowed(2, [1])
    assert not is_allowed(1, [])   # 빈 목록은 아무도 허용 안 함
```
- [ ] **Step 2: 실패 확인.**
- [ ] **Step 3: 구현.** 
  - `config.yaml`의 `card:` (`bot_token` 생략 시 `telegram.bot_token`, `allowed_chat_ids`, `show_description: true`, `font_bold`, `font_regular`) — example에 주석과 함께 추가.
  - 메시지 핸들러: 허용 안 된 chat 무시 → URL마다 `make_card_png`를 `asyncio.to_thread`로 실행 → `reply_photo(photo=bytes, caption=url)`; None이면 `"기사를 읽지 못했습니다: {url}"` 답장. 메시지 엔티티(`url`, `text_link`)도 반영.
  - `run_card_bot.sh`: venv 활성화 후 `exec python3 card_bot.py`. 파일 끝에 systemd 유닛 예시(`Restart=always`) 주석.
  - README에 기능·설정·systemd 실행법 한 절.
- [ ] **Step 4: 통과 확인** — `pytest tests -q` 전부 통과; 실제 봇 토큰으로 `./run_card_bot.sh` 띄우고 단비뉴스 URL을 보내 카드 답장 확인.
- [ ] **Step 5: Commit** — `feat: add Telegram share-card bot`
