import requests
from loguru import logger
from typing import List, Dict, Optional
from urllib.parse import urlparse, parse_qs
import json
import os

# --- Constants and Global Cache ---

NAVER_API_URL = "https://openapi.naver.com/v1/search/news.json"

# --- Core Fetcher Logic ---


def fetch_news(
    client_id: str, client_secret: str, query: str, display: int = 10
) -> Optional[List[Dict]]:
    """
    Fetches news articles from the Naver Search API.

    Args:
        client_id: Your Naver API client ID.
        client_secret: Your Naver API client secret.
        query: The search query (keyword).
        display: The number of news items to retrieve (default is 10).

    Returns:
        A list of news item dictionaries, or None if an error occurs.
    """
    headers = {
        "X-Naver-Client-Id": client_id,
        "X-Naver-Client-Secret": client_secret,
    }

    params = {
        "query": query,
        "display": display,
        "sort": "date",  # Sort by date to get the latest news
    }

    try:
        response = requests.get(
            NAVER_API_URL, headers=headers, params=params, timeout=10
        )
        response.raise_for_status()
        data = response.json()

        if "items" in data:
            news_items = data["items"]
            for item in news_items:
                item["keyword"] = query

            logger.info(
                f"Successfully fetched {len(news_items)} news items for query: '{query}'"
            )
            return news_items
        else:
            logger.warning(
                f"No 'items' field in API response for query: '{query}'. Response: {data}"
            )
            return []

    except requests.exceptions.HTTPError as http_err:
        logger.error(f"HTTP error occurred: {http_err} - Response: {response.text}")
    except requests.exceptions.RequestException as req_err:
        logger.error(f"Request error occurred: {req_err}")
    except Exception as e:
        logger.error(f"An unexpected error occurred in fetch_news: {e}")

    return None


# --- Test Execution Block ---

if __name__ == "__main__":
    import yaml

    logger.info("Running fetcher.py directly for testing.")

    try:
        current_dir = os.path.dirname(os.path.abspath(__file__))
        config_path = os.path.join(current_dir, "..", "config", "config.yaml")

        with open(config_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)

        naver_config = config.get("naver", {})
        client_id = naver_config.get("client_id")
        client_secret = naver_config.get("client_secret")
        test_query = config.get("filter", {}).get("keywords", ["뉴스"])[0]

        if not client_id or "YOUR_" in client_id:
            logger.warning(
                "Naver client_id is not configured in config/config.yaml. Skipping live API test."
            )
        else:
            logger.info(f"Testing with query: '{test_query}'")
            news_items = fetch_news(client_id, client_secret, test_query)

            if news_items is not None:
                logger.info(f"Found {len(news_items)} articles.")
                for i, item in enumerate(news_items[:2]):
                    logger.info(f"      Keyword: {item.get('keyword', 'N/A')}")
                    logger.info(f"      Title: {item['title']}")
                    logger.info(f"      Link: {item['link']}")
            else:
                logger.error("Failed to fetch news from Naver API.")

    except FileNotFoundError:
        logger.error(
            f"config/config.yaml not found at '{config_path}'. Please create it for testing."
        )
    except Exception as e:
        logger.error(f"An error occurred during testing: {e}")
