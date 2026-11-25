from card_bot import extract_urls, is_allowed


def test_extract_urls():
    assert extract_urls("이거 https://a.com/x?id=1 봐") == ["https://a.com/x?id=1"]
    assert extract_urls("없음") == []
    assert extract_urls("https://a.com https://b.com") == ["https://a.com", "https://b.com"]
    assert extract_urls("https://a.com https://a.com") == ["https://a.com"]


def test_is_allowed():
    assert is_allowed(1, [1]) and not is_allowed(2, [1])
    assert not is_allowed(1, [])
    assert is_allowed(-100123, ["-100123"])  # YAML may give strings


def test_handler_ignores_edited_messages():
    from card_bot import build_app
    app = build_app({"telegram": {"bot_token": "1:a"}, "card": {"allowed_chat_ids": [1]}})
    handler = app.handlers[0][0]
    assert "UpdateType.MESSAGE" in str(handler.filters) or "MESSAGE" in repr(handler.filters)
    assert "EDITED" not in repr(handler.filters).upper()
