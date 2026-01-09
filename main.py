import os
import yaml
import logging.config
import asyncio
from loguru import logger

from src import fetcher, filter, notifier, storage

# --- Configuration and Logging Setup ---

# Define the project root directory as the directory containing this script.
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))

def setup_logging():
    """Sets up logging using the logging.yaml configuration."""
    try:
        log_config_path = os.path.join(PROJECT_ROOT, 'config', 'logging.yaml')
        if os.path.exists(log_config_path):
            with open(log_config_path, 'rt') as f:
                config = yaml.safe_load(f.read())
            
            # Ensure the log file path is absolute
            if 'file' in config.get('handlers', {}):
                log_filename = config['handlers']['file'].get('filename')
                if log_filename and not os.path.isabs(log_filename):
                    config['handlers']['file']['filename'] = os.path.join(PROJECT_ROOT, log_filename)

            logging.config.dictConfig(config)
            logger.info("Logging configured from logging.yaml")
        else:
            # Basic fallback logging
            logging.basicConfig(level=logging.INFO)
            logger.info(f"logging.yaml not found at '{log_config_path}', using basic logging config.")

    except Exception as e:
        logging.basicConfig(level=logging.ERROR)
        logger.critical(f"Error configuring logging: {e}", exc_info=True)
        raise

def load_config():
    """Loads the main configuration from config.yaml."""
    try:
        config_path = os.path.join(PROJECT_ROOT, 'config', 'config.yaml')
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
        logger.info("Configuration loaded from config.yaml")
        return config
    except FileNotFoundError:
        logger.error(f"config.yaml not found at '{config_path}'. The application cannot run.")
        raise
    except Exception as e:
        logger.error(f"Error loading configuration: {e}")
        raise

# --- Main Application Logic ---

async def main():
    """
    The main asynchronous pipeline for the news bot.
    """
    try:
        setup_logging()
        config = load_config()
        
        # Extract configs
        naver_conf = config['naver']
        telegram_conf = config['telegram']
        filter_conf = config['filter']
        
        # 1. Setup the database
        storage.setup_database()
        
        # 2. Fetch news for each keyword
        all_news_items = []
        search_keywords = filter_conf.get('keywords', [])
        if not search_keywords:
            logger.warning("No 'keywords' found in filter configuration. No news will be fetched.")
            return

        logger.info(f"Fetching news for keywords: {search_keywords}")
        loop = asyncio.get_running_loop()
        for keyword in search_keywords:
            # Run the synchronous `fetch_news` in a separate thread to avoid blocking
            news_for_keyword = await loop.run_in_executor(
                None,  # Use the default thread pool executor
                fetcher.fetch_news,
                naver_conf['client_id'],
                naver_conf['client_secret'],
                keyword
            )
            if news_for_keyword:
                all_news_items.extend(news_for_keyword)
            
            # Add a delay to avoid hitting API rate limits
            await asyncio.sleep(0.2)
        
        if not all_news_items:
            logger.info("No news items fetched from Naver API. Exiting.")
            return
            
        # 3. Filter the collected news
        filtered_news = filter.filter_news(
            news_items=all_news_items,
            include_keywords=filter_conf.get('keywords', []),
            exclude_keywords=filter_conf.get('exclude_keywords', [])
        )
        
        # 4. Process and send notifications
        if not filtered_news:
            logger.info("No news items remained after filtering.")
            return
            
        logger.info(f"{len(filtered_news)} news items remaining after filtering. Checking against database...")
        
        new_articles_sent = 0
        # Process older items first to send them in chronological order
        for item in reversed(filtered_news): 
            link = item['link']
            
            # 5. Check for duplicates
            if not storage.is_link_sent(link):
                clean_title = item['title'].replace('<b>', '').replace('</b>', '')
                logger.info(f"New article found: '{clean_title}'. Sending notification...")
                
                # 6. Send notification
                await notifier.send_notification(
                    bot_token=telegram_conf['bot_token'],
                    chat_id=telegram_conf['chat_id'],
                    news_item=item,
                    keyword=item.get('keyword') # Pass the keyword for highlighting
                )
                
                # 7. Record the sent link
                storage.add_sent_link(link, clean_title)
                new_articles_sent += 1
            else:
                logger.trace(f"Article already sent, skipping: '{item['title']}'")

        if new_articles_sent == 0:
            logger.info("No new articles to send.")
        else:
            logger.info(f"Finished sending {new_articles_sent} new articles.")

    except Exception as e:
        logger.critical(f"A critical error occurred in the main pipeline: {e}", exc_info=True)

if __name__ == "__main__":
    asyncio.run(main())
