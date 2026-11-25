"""Share cards: turn an article URL into a 1080x1080 image for social media.

Metadata comes from the page's own meta tags (no LLM). Style follows the
mingisidviz dark tokens: one key-yellow accent, title, description, photo,
then a rule and the source/URL footer.
"""
import io
import re
from dataclasses import dataclass
from typing import List, Optional
from urllib.parse import urlparse

from bs4 import BeautifulSoup
from loguru import logger
from PIL import Image, ImageDraw, ImageFont

from src.sources import DEFAULT_USER_AGENT, _get

ELLIPSIS = "…"
SENTENCE_END = ".!?…\"'”’"


@dataclass
class ArticleMeta:
    title: str
    description: str
    image_url: Optional[str]
    source: str
    url: str


# --- metadata ---------------------------------------------------------------

def _meta(soup: BeautifulSoup, *keys: str) -> Optional[str]:
    for key in keys:
        tag = soup.find("meta", attrs={"property": key}) or soup.find("meta", attrs={"name": key})
        if tag and tag.get("content", "").strip():
            return tag["content"].strip()
    return None


def _domain(url: str) -> str:
    return urlparse(url).netloc.removeprefix("www.")


def parse_meta(html: str, url: str) -> ArticleMeta:
    soup = BeautifulSoup(html, "html.parser")
    source = None
    if _domain(url).endswith("news.naver.com"):
        # og:site_name is "네이버 뉴스"; the press name lives in twitter:creator.
        source = _meta(soup, "twitter:creator")
    source = source or _meta(soup, "og:site_name") or _domain(url)

    title = _meta(soup, "og:title", "twitter:title")
    if not title and soup.title and soup.title.string:
        title = soup.title.string.strip()
    description = _meta(soup, "og:description", "description", "twitter:description") or ""
    return ArticleMeta(
        title=clean_title(title or "", source),
        description=clean_description(description),
        image_url=_meta(soup, "og:image", "twitter:image"),
        source=source,
        url=url,
    )


def fetch_meta(url: str) -> Optional[ArticleMeta]:
    response = _get(url, DEFAULT_USER_AGENT)
    if response is None:
        return None
    if response.encoding in (None, "ISO-8859-1"):
        response.encoding = response.apparent_encoding
    return parse_meta(response.text, response.url)


# --- text cleanup -----------------------------------------------------------

def clean_title(title: str, source: str) -> str:
    title = title.strip()
    if source:
        title = re.sub(rf"\s*[-|:–—]\s*{re.escape(source)}\s*$", "", title)
    return title


_BYLINE = re.compile(r"^\s*[\[(【][^\])】]{0,40}기자[^\])】]{0,20}[\])】]\s*")


def clean_description(desc: str) -> str:
    desc = _BYLINE.sub("", desc.strip())
    # "건수가,5년" -> "건수가, 5년"; leave decimals like "3.5" alone.
    desc = re.sub(r"(?<!\d)([.,])(?=\S)|(?<=\d)([.,])(?=[^\s\d])",
                  lambda m: (m.group(1) or m.group(2)) + " ", desc)
    desc = re.sub(r"\s+", " ", desc).strip()
    if not desc or desc[-1] in SENTENCE_END:
        return desc
    cut = max(desc.rfind(c + " ") for c in ".!?")
    if cut > 0:
        return desc[:cut + 1]
    return desc + ELLIPSIS


def wrap_text(draw: ImageDraw.ImageDraw, text: str, font, width: int, max_lines: int) -> List[str]:
    """Wraps on spaces; a word wider than `width` is split by character.
    Overflow past `max_lines` ends the last line with an ellipsis."""
    fits = lambda s: draw.textlength(s, font=font) <= width
    lines: List[str] = []
    cur = ""
    overflow = False
    for word in text.split():
        candidate = f"{cur} {word}" if cur else word
        if fits(candidate):
            cur = candidate
            continue
        if cur:
            lines.append(cur)
            cur = ""
        while not fits(word):  # split an over-wide token
            i = len(word)
            while i > 1 and not fits(word[:i]):
                i -= 1
            lines.append(word[:i])
            word = word[i:]
        cur = word
        if len(lines) >= max_lines:
            overflow = True
            break
    if cur and not overflow:
        lines.append(cur)
    if len(lines) > max_lines:
        overflow = True
    lines = lines[:max_lines]
    if overflow and lines:
        last = lines[-1]
        while last and not fits(last + ELLIPSIS):
            last = last[:-1]
        lines[-1] = last.rstrip() + ELLIPSIS
    return lines
