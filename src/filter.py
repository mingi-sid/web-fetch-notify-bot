from typing import List, Dict
from loguru import logger

def filter_news(
    news_items: List[Dict], 
    include_keywords: List[str], 
    exclude_keywords: List[str]
) -> List[Dict]:
    """
    Filters a list of news articles based on keywords.

    Args:
        news_items: A list of news item dictionaries from the fetcher.
        include_keywords: A list of keywords that MUST be present in the title or description.
                          The logic is OR-based; any one of these keywords is a match.
        exclude_keywords: A list of keywords that MUST NOT be present in the title or description.

    Returns:
        A new list of news items that match the filter criteria.
    """
    if not news_items:
        return []

    filtered_list = []
    
    # Normalize keywords to lowercase for case-insensitive matching
    include_keywords_lower = [kw.lower() for kw in include_keywords]
    exclude_keywords_lower = [kw.lower() for kw in exclude_keywords]

    for item in news_items:
        # Combine title and description for searching
        title = item.get('title', '').lower()
        description = item.get('description', '').lower()
        content_to_search = f"{title} {description}"
        
        # 1. Check for inclusion criteria (OR logic)
        # If there are inclusion keywords, at least one must be met.
        passes_include = False
        if not include_keywords_lower:
            passes_include = True  # No include keywords means all items pass this check
        else:
            if any(kw in content_to_search for kw in include_keywords_lower):
                passes_include = True
        
        if not passes_include:
            continue # Skip to the next item if inclusion criteria are not met

        # 2. Check for exclusion criteria (AND logic)
        # If any exclusion keyword is found, the item is rejected.
        passes_exclude = True
        if exclude_keywords_lower:
            if any(kw in content_to_search for kw in exclude_keywords_lower):
                passes_exclude = False
        
        if not passes_exclude:
            logger.trace(f"Excluding '{item['title']}' due to exclusion keyword.")
            continue # Skip to the next item if exclusion criteria are met
            
        # 3. If both checks pass, add to the list
        filtered_list.append(item)

    logger.info(f"Filtered {len(news_items)} items down to {len(filtered_list)} based on keywords.")
    return filtered_list

if __name__ == '__main__':
    logger.info("Running filter.py directly for testing.")
    
    # Test Data
    mock_news = [
        {'title': '새로운 차별금지법안 발의', 'description': '국회에서 중요한 법안이 논의됩니다.'},
        {'title': '스포츠 뉴스: 손흥민 득점', 'description': '프리미어리그 소식입니다.'},
        {'title': '속보: 트랜스젠더 인권 보호 시급', 'description': '시민 단체 촉구.'},
        {'title': '광고 상품 안내', 'description': '이것은 광고입니다.'},
        {'title': '차별금지법, 찬반 논쟁 (광고 포함)', 'description': '의견이 분분합니다.'},
        {'title': '날씨 정보', 'description': '전국이 맑겠습니다.'},
    ]
    
    # Test Keywords from user's example
    include_kws = ["차별금지법", "트랜스젠더"]
    exclude_kws = ["광고"]
    
    logger.info(f"Include Keywords: {include_kws}")
    logger.info(f"Exclude Keywords: {exclude_kws}")
    
    # Run the filter
    filtered_results = filter_news(mock_news, include_kws, exclude_kws)
    
    # Assertions to verify the logic
    assert len(filtered_results) == 2, f"Expected 2 results, but got {len(filtered_results)}"
    assert filtered_results[0]['title'] == '새로운 차별금지법안 발의'
    assert filtered_results[1]['title'] == '속보: 트랜스젠더 인권 보호 시급'

    # Test with no include keywords
    filtered_no_include = filter_news(mock_news, [], exclude_kws)
    assert len(filtered_no_include) == 4
    logger.info(f"Filtering with only exclude keywords resulted in {len(filtered_no_include)} items.")

    # Test with no exclude keywords
    filtered_no_exclude = filter_news(mock_news, include_kws, [])
    assert len(filtered_no_exclude) == 3
    logger.info(f"Filtering with only include keywords resulted in {len(filtered_no_exclude)} items.")
    
    logger.info("filter.py test completed successfully.")
    for item in filtered_results:
        logger.info(f"  - Passed: {item['title']}")
