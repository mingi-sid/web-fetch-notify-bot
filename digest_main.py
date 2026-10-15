"""
Daily LLM news digest.

    python digest_main.py collect   # run hourly: gather titles from RSS feeds / list pages
    python digest_main.py send      # run daily at 18:00 KST: screen, summarize, send to Telegram
"""
import argparse
import asyncio
from datetime import datetime
from loguru import logger

from main import setup_logging, load_config
from src import digest_store, notifier
from src.briefs import fetch_brief
from src.digest import build_digest, KST
from src.llm import LLMClient
from src.sources import collect_source, DEFAULT_USER_AGENT


def collect(config: dict):
    sources_conf = config["digest"]["sources"]
    user_agent = config["digest"].get("user_agent", DEFAULT_USER_AGENT)

    total_new = 0
    for source_id, source_conf in sources_conf.items():
        articles = collect_source(source_id, source_conf, user_agent)
        total_new += digest_store.save_articles(articles)
    logger.info(f"Collection finished: {total_new} new articles stored.")
    digest_store.prune()


async def send(config: dict, dry_run: bool = False):
    digest_conf = config["digest"]
    sources_conf = digest_conf["sources"]
    user_agent = digest_conf.get("user_agent", DEFAULT_USER_AGENT)
    telegram_conf = config["telegram"]
    llm = LLMClient(config["llm"])
    briefs_conf = digest_conf.get("briefs") or {}
    brief_cache = {}

    def load_briefs(brief_ids):
        """Fetches each brief once per run and returns {display name: text}."""
        loaded = {}
        for brief_id in brief_ids:
            if brief_id not in briefs_conf:
                logger.error(f"Unknown brief: {brief_id}")
                continue
            if brief_id not in brief_cache:
                brief_cache[brief_id] = fetch_brief(brief_id, briefs_conf[brief_id], datetime.now(KST), user_agent)
            if brief_cache[brief_id]:
                loaded[briefs_conf[brief_id].get("name", brief_id)] = brief_cache[brief_id]
        return loaded

    for entry in digest_conf["digests"]:
        name = entry["name"]
        unknown = [sid for sid in entry["sources"] if sid not in sources_conf]
        if unknown:
            logger.error(f"Digest '{name}' references unknown sources: {unknown}. Skipping.")
            continue

        candidates = digest_store.get_candidates(name, entry["sources"], entry.get("hours", 24))
        logger.info(f"Digest '{name}': {len(candidates)} candidate articles.")
        if not candidates:
            continue

        loop = asyncio.get_running_loop()
        messages, links = await loop.run_in_executor(
            None, build_digest, llm, entry, candidates, sources_conf, user_agent,
            digest_conf.get("exclude_title_keywords") or [],
            digest_conf.get("exclude_url_patterns") or [],
            load_briefs(entry.get("briefs") or []),
        )
        if not messages:
            logger.info(f"Digest '{name}': nothing relevant today.")
            continue

        if dry_run:
            print("\n\n----- 8< -----\n\n".join(messages))
            continue

        if await notifier.send_messages(telegram_conf["bot_token"], telegram_conf["chat_id"], messages):
            digest_store.mark_sent(name, links)
            logger.info(f"Digest '{name}' sent ({len(links)} articles).")


def run():
    parser = argparse.ArgumentParser(description="LLM news digest")
    parser.add_argument("command", choices=["collect", "send"])
    parser.add_argument("--dry-run", action="store_true", help="print the digest instead of sending it")
    args = parser.parse_args()

    try:
        setup_logging()
        config = load_config()
        digest_store.setup_database()
        if args.command == "collect":
            collect(config)
        else:
            asyncio.run(send(config, dry_run=args.dry_run))
    except Exception as e:
        logger.critical(f"A critical error occurred in the digest pipeline: {e}", exc_info=True)


if __name__ == "__main__":
    run()
