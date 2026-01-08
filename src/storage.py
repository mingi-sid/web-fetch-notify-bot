import sqlite3
import os
from datetime import datetime
from loguru import logger

# Set the database path relative to the project structure
# The DB will be created in the 'data' directory.
DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'sent_news.db')

def setup_database():
    """
    Ensures the database and the 'sent_news' table exist.
    """
    try:
        # Ensure the data directory exists
        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
        
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # Create table if it doesn't exist
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS sent_news (
                link TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                sent_at TIMESTAMP NOT NULL
            )
        ''')
        
        conn.commit()
        conn.close()
        logger.info(f"Database setup complete. Path: {DB_PATH}")
    except sqlite3.Error as e:
        logger.error(f"Database error during setup: {e}")
        raise

def is_link_sent(link: str) -> bool:
    """
    Checks if a news article link has already been sent.

    Args:
        link: The URL of the news article.

    Returns:
        True if the link exists in the database, False otherwise.
    """
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        cursor.execute("SELECT 1 FROM sent_news WHERE link = ?", (link,))
        result = cursor.fetchone()
        
        conn.close()
        return result is not None
    except sqlite3.Error as e:
        logger.error(f"Error checking link in database: {e}")
        # In case of error, assume it was sent to avoid duplicates
        return True

def add_sent_link(link: str, title: str):
    """
    Adds a sent news article link to the database.

    Args:
        link: The URL of the news article.
        title: The title of the news article.
    """
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        sent_at = datetime.now()
        cursor.execute(
            "INSERT INTO sent_news (link, title, sent_at) VALUES (?, ?, ?)",
            (link, title, sent_at)
        )
        
        conn.commit()
        conn.close()
        logger.info(f"Added to DB: {title}")
    except sqlite3.IntegrityError:
        logger.warning(f"Link already exists in DB (IntegrityError): {link}")
    except sqlite3.Error as e:
        logger.error(f"Error adding link to database: {e}")

if __name__ == '__main__':
    # Example usage and testing
    logger.info("Running storage.py directly for testing.")
    
    # 1. Setup DB
    setup_database()
    
    # 2. Test data
    test_link1 = "https://example.com/news/1"
    test_title1 = "Example News 1"
    test_link2 = "https://example.com/news/2"
    test_title2 = "Example News 2"
    
    # 3. Clear old test data if it exists
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM sent_news WHERE link LIKE 'https://example.com/%'")
        conn.commit()
        conn.close()
        logger.info("Cleared previous test data.")
    except sqlite3.Error as e:
        logger.error(f"Could not clear test data: {e}")


    # 4. Check if link is sent (should be False)
    is_sent = is_link_sent(test_link1)
    logger.info(f"Is '{test_link1}' sent? {is_sent}")
    assert not is_sent

    # 5. Add link to DB
    add_sent_link(test_link1, test_title1)
    
    # 6. Check again (should be True)
    is_sent = is_link_sent(test_link1)
    logger.info(f"Is '{test_link1}' sent again? {is_sent}")
    assert is_sent
    
    # 7. Test another link
    is_sent_2 = is_link_sent(test_link2)
    logger.info(f"Is '{test_link2}' sent? {is_sent_2}")
    assert not is_sent_2
    
    logger.info("storage.py test completed successfully.")
