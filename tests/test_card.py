from pathlib import Path

import pytest
from PIL import Image, ImageDraw, ImageFont

from src.card import clean_description, clean_title, parse_meta, wrap_text

FIX = Path(__file__).parent / "fixtures"
FONT_B = "/usr/share/fonts/truetype/nanum/NanumSquareB.ttf"


def _font(size=40):
    if not Path(FONT_B).exists():
        pytest.skip("Korean font not installed")
    return ImageFont.truetype(FONT_B, size)


def test_clean_title_strips_source_suffix():
    assert clean_title("과속하는 인공지능에 브레이크를 걸다 - 단비뉴스", "단비뉴스") == "과속하는 인공지능에 브레이크를 걸다"
    assert clean_title("제목 | 충청투데이", "충청투데이") == "제목"
    assert clean_title("제목 : 충청투데이", "충청투데이") == "제목"
    assert clean_title("A - B 대결", "단비뉴스") == "A - B 대결"


def test_clean_description_byline_spacing_and_cut():
    assert clean_description("[충청투데이 권오선 기자] 정부가 발표했다.") == "정부가 발표했다."
    assert clean_description("적발건수가,5년여간 늘었다.") == "적발건수가, 5년여간 늘었다."
    assert clean_description("수렴해 왔다. 그") == "수렴해 왔다."
    assert clean_description("끝나지 않는 문장") == "끝나지 않는 문장…"
    assert clean_description("3.5% 올랐다.") == "3.5% 올랐다."
    assert clean_description("") == ""


def test_parse_meta_og():
    m = parse_meta((FIX / "og.html").read_text(), "https://www.danbinews.com/news/1")
    assert m.title == "과속하는 인공지능에 브레이크를 걸다"
    assert m.description == "논의는 수렴해 왔다."
    assert m.image_url == "https://cdn.example.com/a.jpg"
    assert m.source == "단비뉴스"
    assert m.url == "https://www.danbinews.com/news/1"


def test_parse_meta_fallbacks():
    m = parse_meta((FIX / "bare.html").read_text(), "https://www.example.co.kr/a")
    assert m.title == "그냥 제목"
    assert m.description == "설명입니다."
    assert m.image_url is None
    assert m.source == "example.co.kr"


def test_parse_meta_naver_press():
    m = parse_meta((FIX / "naver.html").read_text(), "https://n.news.naver.com/mnews/article/023/1")
    assert m.source == "조선일보"


def _check_lines(lines, font, width, max_lines):
    d = ImageDraw.Draw(Image.new("RGB", (10, 10)))
    assert 1 <= len(lines) <= max_lines
    for ln in lines:
        assert d.textlength(ln, font=font) <= width
    return d


def test_wrap_breaks_on_words():
    f = _font()
    d = ImageDraw.Draw(Image.new("RGB", (10, 10)))
    text = "하루 7건꼴 산림 불법행위 5년간 피해액 3천39억 원 적발 건수 늘어"
    lines = wrap_text(d, text, f, 400, 5)
    _check_lines(lines, f, 400, 5)
    words = text.split()
    for ln in lines:
        for w in ln.split():
            assert w in words
    assert " ".join(lines) == text


def test_wrap_long_token():
    f = _font()
    d = ImageDraw.Draw(Image.new("RGB", (10, 10)))
    lines = wrap_text(d, "가" * 200, f, 400, 3)
    _check_lines(lines, f, 400, 3)
    assert len(lines) == 3 and lines[-1].endswith("…")
