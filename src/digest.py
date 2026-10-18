import html
import math
import re
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Tuple
from loguru import logger

from src.llm import LLMClient
from src.sources import fetch_article_body

KST = timezone(timedelta(hours=9))
TRIAGE_CHUNK_SIZE = 300     # titles per triage request
SCORING_CHUNK_SIZE = 80     # articles per scoring request
TELEGRAM_LIMIT = 4000       # Telegram caps messages at 4096 chars; leave headroom
DEFAULT_MIN_SCORE = 7

# Each section picks articles by its primary score, breaking ties with the other.
# How each section picks articles. Eligibility and ordering are separate:
#   - eligible: primary >= min_score (digest setting) and secondary >= min_secondary
#   - ordered by: primary * (1 - secondary_weight) + secondary * secondary_weight
#   - must_include: primary at or above this is always picked first, whatever the secondary
#     score (e.g. breaking news in the importance section). None disables it.
# So the secondary score shapes the ranking without cutting off major news.
# Each key can be overridden per digest under `sections.<key>`.
SECTIONS = [
    {"key": "relevance", "title": "🎯 관심사 기사", "primary": "relevance", "secondary": "importance",
     "secondary_weight": 0.3, "min_secondary": 4, "must_include": None},
    {"key": "importance", "title": "📌 오늘의 주요 기사", "primary": "importance", "secondary": "relevance",
     "secondary_weight": 0.3, "min_secondary": 1, "must_include": 9},
]

DEFAULT_PERSPECTIVE = "한국 사회 전반의 독자"

TRIAGE_SYSTEM = (
    "당신은 뉴스 편집 보조입니다. 기사 제목 목록에서 독자에게 전혀 쓸모없는 기사만 걸러냅니다. "
    "다음 중 하나라도 해당할 가능성이 있으면 남깁니다: (1) 독자 관심사와 조금이라도 관련됨, "
    "(2) 관심사와 무관해도 주어진 관점에서 중요한 사안(큰 사건사고, 주요 정책·정치, 공공성이 큰 이슈). "
    "단순 행사 홍보, 동정, 연예·스포츠, 생활정보, 단신처럼 둘 다 아닌 기사만 제외합니다. "
    "애매하면 남깁니다. "
    "반드시 JSON만 출력합니다: {\"keep\": [<번호>, ...]}"
)

RELEVANCE_SYSTEM = (
    "당신은 깐깐한 뉴스 큐레이터입니다. 독자 관심사와 기사 목록(제목, 짧은 요약)을 받아 "
    "기사마다 관심사와의 관련도(relevance)를 1~10점으로 매깁니다. 사안의 중요도는 따지지 않습니다.\n"
    "  10: 관심사의 핵심 주제를 정면으로 다루고, 독자가 반드시 챙겨야 할 기사\n"
    "  7-9: 관심사 주제를 직접 다룸\n"
    "  4-6: 관심사와 부분적으로 겹치거나 간접적으로 관련됨\n"
    "  1-3: 관련이 희박하거나 무관함 (같은 지역·분야라는 이유만으로는 4점 미만)\n"
    "점수는 목록 전체에서 상대적으로 매기고 고르게 분포시킵니다. 7점 이상은 목록의 일부 기사에만 줍니다.\n"
    "같은 사건을 다룬 기사가 여러 개면, 대표 기사 하나를 정하고 나머지는 duplicate_of에 대표 기사 번호를 적습니다.\n"
    "반드시 JSON만 출력합니다: "
    "{\"scores\": [{\"id\": <번호>, \"relevance\": <1-10>, \"duplicate_of\": <번호 또는 null>}]}"
)

IMPORTANCE_SYSTEM = (
    "당신은 깐깐한 뉴스 데스크입니다. 주어진 관점의 독자에게 각 기사가 다루는 사안이 얼마나 중요한지"
    "(importance)를 1~10점으로 매깁니다. 독자의 개인적 관심사는 고려하지 않고, 사안의 파급력, 공공성, "
    "새로움, 후속 보도 가치만 봅니다.\n"
    "  10: 그 관점에서 그날 최상위 뉴스 (중대 속보, 큰 사건사고)\n"
    "  7-9: 주요 정책·정치·사회 사안\n"
    "  4-6: 의미는 있지만 파급력이 제한적인 기사\n"
    "  1-3: 단신, 행사·홍보, 동정, 사진·책 소개 기사\n"
    "점수는 목록 전체에서 상대적으로 매기고 고르게 분포시킵니다. 7점 이상은 목록의 일부 기사에만 줍니다.\n"
    "반드시 JSON만 출력합니다: {\"scores\": [{\"id\": <번호>, \"importance\": <1-10>}]}"
)

DIGEST_SYSTEM = (
    "당신은 뉴스 다이제스트 편집자입니다. 독자의 관심사와 기사들을 받아 한국어로 요약합니다. "
    "각 기사는 2~3문장으로 핵심 사실과 그 기사가 왜 중요한지를 담아 요약하고, 주어진 자료에 없는 내용은 추측하지 않습니다. "
    "요약문에서 가장 중요한 핵심어나 구절 1~2개는 **이렇게** 감쌉니다. 남용하지 않습니다.\n"
    "- 본문이 있는 기사는 본문을 근거로 요약하고 basis는 \"본문\"으로 둡니다.\n"
    "- 본문이 없는 기사(본문: 없음)는 참고 브리프에 같은 사안이 분명히 다뤄진 경우에만 그 내용으로 요약하고, "
    "basis에 해당 브리프 이름을 적습니다. 브리프에서 찾을 수 없으면 summary와 basis를 빈 문자열로 둡니다.\n"
    "기사마다 section 값(relevance 또는 importance)이 붙어 있습니다. "
    "overview에는 섹션별로 오늘 기사들을 관통하는 흐름을 2~3문장으로 씁니다. "
    "반드시 JSON만 출력합니다: "
    "{\"overview\": {\"relevance\": \"...\", \"importance\": \"...\"}, "
    "\"items\": [{\"id\": <번호>, \"summary\": \"...\", \"basis\": \"...\"}]}"
)


def _render_summary(text: str) -> str:
    """Escapes a summary for Telegram HTML, turning **key phrases** into bold."""
    return re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", html.escape(text))


def _title_link(article: Dict) -> str:
    return f'<a href="{html.escape(article["link"], quote=True)}">{html.escape(article["title"])}</a>'


def _source_name(source_names: Dict[str, str], article: Dict) -> str:
    return source_names.get(article["source_id"], article["source_id"])


# --- Stage 1: rule-based pre-filter ---


def prefilter(candidates: List[Dict], exclude_title_keywords: List[str],
              exclude_url_patterns: List[str]) -> List[Dict]:
    """Drops articles whose title contains an excluded keyword or whose link matches an excluded pattern."""
    kept = [
        a for a in candidates
        if not any(kw in a["title"] for kw in exclude_title_keywords)
        and not any(p in a["link"] for p in exclude_url_patterns)
    ]
    logger.info(f"Pre-filter: {len(candidates)} -> {len(kept)} articles.")
    return kept


# --- Stage 2: lenient LLM triage on titles ---


def triage(llm: LLMClient, interests: str, perspective: str, candidates: List[Dict],
           source_names: Dict[str, str]) -> List[Dict]:
    """Removes clearly irrelevant and unimportant articles, keeping anything borderline."""
    keep = set()
    for start in range(0, len(candidates), TRIAGE_CHUNK_SIZE):
        chunk = candidates[start:start + TRIAGE_CHUNK_SIZE]
        lines = [f"[{start + i}] ({_source_name(source_names, a)}) {a['title']}" for i, a in enumerate(chunk)]
        prompt = (f"## 독자 관심사\n{interests}\n\n## 중요도 판단 관점\n{perspective}\n\n"
                  f"## 기사 제목 ({len(chunk)}건)\n" + "\n".join(lines))
        try:
            result = llm.complete_json(llm.screening_model, TRIAGE_SYSTEM, prompt, max_tokens=16000,
                                       thinking=False, stage="triage")
        except Exception as e:
            # Fail open: if triage breaks, let scoring see the whole chunk.
            logger.error(f"Triage request failed, keeping the whole chunk: {e}")
            keep.update(range(start, start + len(chunk)))
            continue
        keep.update(i for i in result.get("keep", []) if isinstance(i, int) and start <= i < start + len(chunk))

    kept = [candidates[i] for i in sorted(keep)]
    logger.info(f"Triage: {len(candidates)} -> {len(kept)} articles.")
    return kept


# --- Stage 3: score relevance and importance ---


def _score_pass(llm: LLMClient, system: str, context: str, candidates: List[Dict],
                source_names: Dict[str, str], stage: str) -> Dict[int, Dict]:
    """Runs one scoring prompt over all candidates in chunks; returns {candidate index: item}."""
    scored: Dict[int, Dict] = {}
    for start in range(0, len(candidates), SCORING_CHUNK_SIZE):
        chunk = candidates[start:start + SCORING_CHUNK_SIZE]
        lines = [
            f"[{start + i}] ({_source_name(source_names, a)}) {a['title']}"
            + (f" — {a['description'][:150]}" if a.get("description") else "")
            for i, a in enumerate(chunk)
        ]
        prompt = f"{context}\n\n## 기사 목록 ({len(chunk)}건)\n" + "\n".join(lines)
        try:
            result = llm.complete_json(llm.screening_model, system, prompt, max_tokens=16000,
                                       thinking=False, stage=stage)
        except Exception as e:
            logger.error(f"{stage} request failed for articles {start}-{start + len(chunk) - 1}: {e}")
            continue
        for item in result.get("scores", []):
            idx = item.get("id")
            if isinstance(idx, int) and start <= idx < start + len(chunk):
                scored[idx] = item
    return scored


def score(llm: LLMClient, interests: str, perspective: str, candidates: List[Dict],
          source_names: Dict[str, str]) -> List[Dict]:
    """
    Annotates candidates with relevance and importance, scored in separate requests so that
    importance (judged from `perspective`, without the reader's interests) isn't pulled up by
    relevance. Duplicates (per the relevance pass) are removed.
    """
    relevance = _score_pass(llm, RELEVANCE_SYSTEM, f"## 독자 관심사\n{interests}",
                            candidates, source_names, "relevance")
    importance = _score_pass(llm, IMPORTANCE_SYSTEM, f"## 중요도 판단 관점\n{perspective}",
                             candidates, source_names, "importance")

    articles = []
    for idx, rel in relevance.items():
        if rel.get("duplicate_of") not in (None, idx) and rel["duplicate_of"] in relevance:
            continue
        if idx not in importance:
            logger.warning(f"No importance score for '{candidates[idx]['title']}'; skipping.")
            continue
        try:
            articles.append({
                **candidates[idx],
                "relevance": int(rel.get("relevance", 0)),
                "importance": int(importance[idx].get("importance", 0)),
            })
        except (TypeError, ValueError):
            continue

    for a in sorted(articles, key=lambda a: (a["relevance"], a["importance"]), reverse=True):
        logger.debug(f"score R{a['relevance']} I{a['importance']} | {a['title']}")
    logger.info(f"Scoring: {len(candidates)} -> {len(articles)} unique articles scored.")
    return articles


def select_sections(articles: List[Dict], max_articles: int, min_score: float,
                    overrides: Dict[str, Dict] = {}) -> Dict[str, List[Dict]]:
    """
    Picks articles for each section (see SECTIONS): must-include articles first, then eligible
    articles by mixed score. If that yields fewer than half of `max_articles`, the next best
    articles that still meet `min_secondary` fill the gap. Sections are filled in order, and an
    article appears in only one section.
    """
    minimum = math.ceil(max_articles / 2)
    used, sections = set(), {}
    for section in SECTIONS:
        conf = {**section, **overrides.get(section["key"], {})}
        primary, secondary = conf["primary"], conf["secondary"]
        weight, min_secondary, must_include = conf["secondary_weight"], conf["min_secondary"], conf["must_include"]

        def mixed(a):
            return a[primary] * (1 - weight) + a[secondary] * weight

        pool = sorted(
            (a for a in articles if a["link"] not in used),
            key=lambda a: (mixed(a), a[primary]),
            reverse=True,
        )
        forced = [a for a in pool if must_include is not None and a[primary] >= must_include]
        eligible = [a for a in pool if a not in forced
                    and a[primary] >= min_score and a[secondary] >= min_secondary]
        picked = (forced + eligible)[:max_articles]
        if len(picked) < minimum:
            filler = [a for a in pool if a not in picked and a[secondary] >= min_secondary]
            picked += filler[:minimum - len(picked)]

        used.update(a["link"] for a in picked)
        sections[section["key"]] = picked
        logger.info(f"Section '{section['key']}': {len(picked)} articles "
                    f"({len(forced)} must-include, {len(eligible)} eligible).")
    return sections


# --- Summarize and format ---


def summarize_articles(llm: LLMClient, interests: str, articles: List[Tuple[str, Dict, bool]],
                       source_names: Dict[str, str], user_agent: str, briefs: Dict[str, str]) -> Dict:
    """
    Asks the digest model for summaries of (section, article, can_fetch) triples.
    Bodies are fetched only when allowed; otherwise the model may summarize from `briefs`
    ({brief name: text}).
    """
    blocks = []
    for i, (section, a, can_fetch) in enumerate(articles):
        if can_fetch:
            body = fetch_article_body(a["link"], user_agent) or a.get("description") or ""
        else:
            body = "없음"
        blocks.append(
            f"<article id=\"{i}\" section=\"{section}\">\n언론사: {_source_name(source_names, a)}\n"
            f"제목: {a['title']}\n본문:\n{body}\n</article>"
        )
    if not blocks:
        return {}

    prompt = f"## 독자 관심사\n{interests}\n\n"
    if briefs:
        prompt += "## 참고 브리프\n" + "\n\n".join(
            f"<brief name=\"{name}\">\n{text}\n</brief>" for name, text in briefs.items()
        ) + "\n\n"
    prompt += "## 기사\n" + "\n\n".join(blocks)
    try:
        return llm.complete_json(llm.digest_model, DIGEST_SYSTEM, prompt, max_tokens=16000, stage="summary")
    except Exception as e:
        logger.error(f"Digest summarization failed: {e}")
        return {}


def format_section(digest_name: str, section_title: str, overview: str, summarized: List[Dict],
                   title_only: List[Dict], source_names: Dict[str, str]) -> List[str]:
    """Builds Telegram HTML messages for one section, split so each stays under the size limit."""
    today = datetime.now(KST)
    header = f"📰 <b>{html.escape(digest_name)}</b> · {today.month}월 {today.day}일\n<b>{section_title}</b>"
    if overview:
        header += f"\n\n{html.escape(overview)}"

    # (text, separator before it) — summaries are spaced apart, title-only bullets are not.
    parts = [(header, "")]
    for n, a in enumerate(summarized, 1):
        part = f"<b>{n}. [{html.escape(_source_name(source_names, a))}] {_title_link(a)}</b>"
        if a.get("summary"):
            part += f"\n{_render_summary(a['summary'])}"
        if a.get("basis") and a["basis"] != "본문":
            part += f" <i>({html.escape(a['basis'])} 참고)</i>"
        parts.append((part, "\n\n"))

    if title_only:
        parts.append(("📎 <b>함께 볼 기사</b> (제목만 제공)", "\n\n"))
        for a in title_only:
            source = html.escape(_source_name(source_names, a))
            line = f"• [{source}] {_title_link(a)}"
            parts.append((line, "\n"))

    messages, current = [], ""
    for part, sep in parts:
        candidate = f"{current}{sep}{part}" if current else part
        if len(candidate) > TELEGRAM_LIMIT and current:
            messages.append(current)
            current = part
        else:
            current = candidate
    if current:
        messages.append(current)
    return messages


def build_digest(llm: LLMClient, digest_conf: Dict, candidates: List[Dict], sources_conf: Dict[str, Dict],
                 user_agent: str, exclude_title_keywords: List[str] = [],
                 exclude_url_patterns: List[str] = [], briefs: Dict[str, str] = {}) -> Tuple[List[str], List[str]]:
    """
    Runs the selection pipeline and summarization for one digest.
    Returns (telegram messages, links included in the digest). Each section starts a new message.
    """
    name = digest_conf["name"]
    interests = digest_conf["interests"]
    max_articles = digest_conf.get("max_articles", 10)
    min_score = digest_conf.get("min_score", DEFAULT_MIN_SCORE)
    perspective = digest_conf.get("importance_perspective", DEFAULT_PERSPECTIVE)
    source_names = {sid: conf.get("name", sid) for sid, conf in sources_conf.items()}

    candidates = prefilter(
        candidates,
        exclude_title_keywords + digest_conf.get("exclude_title_keywords", []),
        exclude_url_patterns + digest_conf.get("exclude_url_patterns", []),
    )
    llm.reset_usage()
    candidates = triage(llm, interests, perspective, candidates, source_names)
    articles = score(llm, interests, perspective, candidates, source_names)
    if not articles:
        llm.log_usage(name)
        return [], []
    sections = select_sections(articles, max_articles, min_score, digest_conf.get("sections") or {})

    def can_fetch(a):
        return sources_conf[a["source_id"]].get("fetch_body", True)

    # Without briefs, articles that can't be fetched have nothing to be summarized from.
    to_summarize = [
        (key, a, can_fetch(a)) for key, picked in sections.items() for a in picked
        if can_fetch(a) or briefs
    ]
    result = summarize_articles(llm, interests, to_summarize, source_names, user_agent, briefs)
    items = {item.get("id"): item for item in result.get("items", []) if isinstance(item, dict)}
    overviews = result.get("overview") or {}
    if not isinstance(overviews, dict):
        overviews = {}

    # Fetchable articles are always listed with a summary; the rest only if a brief covered them.
    summarized_by_section: Dict[str, List[Dict]] = {s["key"]: [] for s in SECTIONS}
    for i, (key, a, fetchable) in enumerate(to_summarize):
        item = items.get(i, {})
        summary = item.get("summary") or ""
        if fetchable or summary:
            summarized_by_section[key].append({**a, "summary": summary, "basis": item.get("basis") or ""})
    summarized_links = {a["link"] for picked in summarized_by_section.values() for a in picked}

    messages, links = [], []
    for section in SECTIONS:
        picked = sections[section["key"]]
        if not picked:
            continue
        messages += format_section(
            name, section["title"], overviews.get(section["key"], ""),
            summarized_by_section[section["key"]],
            [a for a in picked if a["link"] not in summarized_links], source_names,
        )
        links += [a["link"] for a in picked]
    llm.log_usage(name)
    return messages, links
