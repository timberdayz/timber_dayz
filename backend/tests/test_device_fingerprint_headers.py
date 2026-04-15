from modules.utils.sessions.device_fingerprint import DeviceFingerprintManager


def test_device_fingerprint_context_headers_do_not_include_cache_control_or_accept_encoding(tmp_path):
    manager = DeviceFingerprintManager(base_path=tmp_path)

    options = manager.get_playwright_context_options(
        platform="tiktok",
        account_id="acc-1",
        account_config={"region": "SG"},
    )

    headers = options.get("extra_http_headers", {})

    assert "Cache-Control" not in headers
    assert "Accept-Encoding" not in headers
    assert "Upgrade-Insecure-Requests" not in headers
    assert headers.get("Accept-Language")


def test_device_fingerprint_uses_shop_region_when_region_is_missing(tmp_path):
    manager = DeviceFingerprintManager(base_path=tmp_path)

    options = manager.get_playwright_context_options(
        platform="tiktok",
        account_id="acc-shop-region",
        account_config={"shop_region": "SG"},
    )

    assert options["locale"] == "en-SG"
    assert options["timezone_id"] == "Asia/Singapore"
    assert options["extra_http_headers"]["Accept-Language"].startswith("en-SG")


def test_device_fingerprint_ua_pool_includes_recent_chromium_versions():
    chromium_uas = [
        ua
        for ua in DeviceFingerprintManager.STABLE_USER_AGENTS
        if "Chrome/" in ua and "Chromium/" not in ua
    ]

    recent_versions = []
    for ua in chromium_uas:
        marker = "Chrome/"
        start = ua.index(marker) + len(marker)
        major = int(ua[start:].split(".", 1)[0])
        recent_versions.append(major)

    assert max(recent_versions) >= 132
