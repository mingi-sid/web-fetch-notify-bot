import telegram
from telegram.constants import ParseMode
from loguru import logger
from typing import Dict
import html
import asyncio
from datetime import datetime


async def send_notification(
    bot_token: str, chat_id: str, news_item: Dict, keyword: str
):
    """
    Sends a formatted news notification to a Telegram chat asynchronously.

    Args:
        bot_token: The Telegram Bot API token.
        chat_id: The target chat ID.
        news_item: The news article dictionary to send.
        keyword: The search keyword, to be bolded in the title.
    """
    try:
        bot = telegram.Bot(token=bot_token)

        # The Naver API provides HTML tags (<b>) for keywords. We use HTML parsing.
        # html.unescape is used to decode entities like &quot; into ".
        # Keep <b> tags for bolding keywords, and unescape HTML entities.
        title = html.unescape(news_item["title"])
        description = html.unescape(news_item["description"])
        link = news_item["link"]
        pub_date = news_item.get("pubDate")

        # Format the publication date if it exists
        formatted_date = ""
        if pub_date:
            try:
                # Parse RFC 1123 date string (e.g., "Fri, 09 Jan 2026 07:26:38 +0900")
                dt_object = datetime.strptime(pub_date, '%a, %d %b %Y %H:%M:%S %z')
                formatted_date = f"{dt_object.year}년 {dt_object.month}월 {dt_object.day}일 {dt_object.hour}시 {dt_object.minute}분"
            except (ValueError, KeyError) as e:
                logger.warning(f"Could not parse date '{pub_date}': {e}")

        # This is a fallback and might not be perfect if the title was modified.
        if keyword and f"<b>{keyword}</b>" not in title.lower():
            # A simple case-insensitive replace
            import re

            title = re.sub(
                f"({re.escape(keyword)})", r"<b>\1</b>", title, flags=re.IGNORECASE
            )

        # Format the message using HTML tags, including the formatted date if available.
        message_parts = [f"<b>{title}</b>"]
        if formatted_date:
            message_parts.append(f"<i>{formatted_date}</i>")
        message_parts.append(description)
        message_parts.append(f'<a href="{link}">기사 링크</a>')

        message = "\n\n".join(message_parts)

        await bot.send_message(
            chat_id=chat_id,
            text=message,
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=False,
        )

        # Use a cleaned title for logging to avoid messy logs.
        clean_title = title.replace("<b>", "").replace("</b>", "")
        logger.info(f"Notification sent successfully for: {clean_title}")

    except telegram.error.TelegramError as e:
        logger.error(f"Telegram error occurred: {e}")
        logger.error(f"Failed to send notification for: {news_item.get('title')}")
    except Exception as e:
        logger.error(f"An unexpected error occurred in send_notification: {e}")


if __name__ == "__main__":
    # Example usage:
    # To test this, you need to have a config.yaml file in the ../config directory
    # with your actual Telegram bot token and chat ID.
    import yaml
    import os

    logger.info("Running notifier.py directly for testing.")

    async def test_run():
        try:
            config_path = os.path.join(
                os.path.dirname(__file__), "..", "config", "config.yaml"
            )
            with open(config_path, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f)

            telegram_config = config.get("telegram", {})
            bot_token = telegram_config.get("bot_token")
            chat_id = telegram_config.get("chat_id")

            if (
                not bot_token
                or "YOUR_" in bot_token
                or not chat_id
                or "YOUR_" in chat_id
            ):
                logger.warning(
                    "Telegram bot_token or chat_id is not configured in config/config.yaml. Skipping live API test."
                )
            else:
                # Mock news item for testing
                mock_item = {
                    "title": "<b>테스트 뉴스</b>: 봇 작동 확인",
                    "description": "이 메시지는 notifier.py에서 직접 보낸 <b>테스트</b> 알림입니다.",
                    "link": "https://www.google.com",
                }
                test_keyword = "테스트"

                logger.info("Sending a test notification to your Telegram chat...")
                await send_notification(bot_token, chat_id, mock_item, test_keyword)
                logger.info("Test notification sent. Please check your Telegram chat.")

        except FileNotFoundError:
            logger.error("config/config.yaml not found. Please create it for testing.")
        except Exception as e:
            logger.error(f"An error occurred during testing: {e}")

    # Run the async test function
    asyncio.run(test_run())
