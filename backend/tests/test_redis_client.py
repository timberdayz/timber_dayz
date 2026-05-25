from backend.utils.redis_client import sanitize_redis_url_for_log


def test_sanitize_redis_url_for_log_masks_password():
    url = "redis://:secret-pass@localhost:16379/0"

    assert sanitize_redis_url_for_log(url) == "redis://***@localhost:16379/0"


def test_sanitize_redis_url_for_log_keeps_passwordless_url():
    url = "redis://localhost:16379/0"

    assert sanitize_redis_url_for_log(url) == url
