"""Telegram bot: send an article URL, get back a square share card.

Runs continuously (long polling). See run_card_bot.sh for a systemd example.
"""
import asyncio
import os
import re
from typing import Iterable, List

import yaml
from loguru import logger
from telegram import Update
from telegram.ext import Application, ContextTypes, MessageHandler, filters

from src.card import CardStyle, make_card_png

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
URL_RE = re.compile(r"https?://[^\s<>\"']+")


def extract_urls(text: str) -> List[str]:
    seen: List[str] = []
    for url in URL_RE.findall(text or ""):
        url = url.rstrip(").,]>")
        if url not in seen:
            seen.append(url)
    return seen


def is_allowed(chat_id: int, allowed: Iterable) -> bool:
    return str(chat_id) in {str(a) for a in allowed}


def _message_urls(update: Update) -> List[str]:
    msg = update.effective_message
    text = msg.text or msg.caption or ""
    urls = extract_urls(text)
    for entity in (msg.entities or []) + (msg.caption_entities or []):
        if entity.type == "text_link" and entity.url and entity.url not in urls:
            urls.append(entity.url)
    return urls


def build_app(config: dict) -> Application:
    card_conf = config.get("card", {})
    token = card_conf.get("bot_token") or config["telegram"]["bot_token"]
    allowed = card_conf.get("allowed_chat_ids", [])
    style = CardStyle(
        font_bold=card_conf.get("font_bold", "/usr/share/fonts/truetype/nanum/NanumSquareB.ttf"),
        font_regular=card_conf.get("font_regular", "/usr/share/fonts/truetype/nanum/NanumSquare_acR.ttf"),
        show_description=card_conf.get("show_description", True),
    )
    for path in (style.font_bold, style.font_regular):
        if not os.path.exists(path):
            raise SystemExit(f"Font not found: {path} (set card.font_bold / card.font_regular)")
    if not allowed:
        logger.warning("card.allowed_chat_ids is empty: the bot will ignore every chat")

    async def on_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        chat_id = update.effective_chat.id
        if not is_allowed(chat_id, allowed):
            logger.info(f"Ignoring message from chat {chat_id}")
            return
        for url in _message_urls(update):
            try:
                png = await asyncio.to_thread(make_card_png, url, style)
            except Exception:
                logger.exception(f"Card failed for {url}")
                png = None
            if png is None:
                await update.effective_message.reply_text(f"기사를 읽지 못했습니다: {url}")
            else:
                await update.effective_message.reply_photo(photo=png, caption=url)

    app = Application.builder().token(token).build()
    app.add_handler(MessageHandler(filters.UpdateType.MESSAGE & (filters.TEXT | filters.CAPTION) & ~filters.COMMAND, on_message))
    return app


def main() -> None:
    with open(os.path.join(PROJECT_ROOT, "config", "config.yaml"), encoding="utf-8") as f:
        config = yaml.safe_load(f)
    logger.add(os.path.join(PROJECT_ROOT, "card_bot.log"), rotation="5 MB", retention=3)
    logger.info("Card bot starting (long polling)")
    build_app(config).run_polling(allowed_updates=[Update.MESSAGE])


if __name__ == "__main__":
    main()
