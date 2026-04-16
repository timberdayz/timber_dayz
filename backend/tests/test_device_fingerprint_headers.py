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


def test_tiktok_browser_environment_stays_cn_even_when_shop_region_is_non_cn(tmp_path):
    manager = DeviceFingerprintManager(base_path=tmp_path)

    options = manager.get_playwright_context_options(
        platform="tiktok",
        account_id="acc-shop-region",
        account_config={"shop_region": "SG"},
    )

    assert options["locale"] == "zh-CN"
    assert options["timezone_id"] == "Asia/Shanghai"
    assert options["extra_http_headers"]["Accept-Language"].startswith("zh-CN")


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


def test_tiktok_generated_fingerprint_uses_chromium_only_user_agent(tmp_path):
    manager = DeviceFingerprintManager(base_path=tmp_path)

    fingerprint = manager.get_or_create_fingerprint(
        platform="tiktok",
        account_id="acc-tiktok",
        account_config={"region": "MY"},
    )

    ua = fingerprint["user_agent"]
    assert "Chrome/" in ua
    assert "Firefox/" not in ua
    assert "Safari/" in ua
    assert "OPR/" not in ua
    assert "Edg/" not in ua
    assert "Brave/" not in ua
    assert "Version/" not in ua


def test_tiktok_legacy_fingerprint_is_rebuilt_when_version_or_headers_are_stale(tmp_path):
    manager = DeviceFingerprintManager(base_path=tmp_path)
    fingerprint_file = manager.get_fingerprint_file("tiktok", "acc-stale")
    fingerprint_file.parent.mkdir(parents=True, exist_ok=True)
    fingerprint_file.write_text(
        """
{
  "platform": "tiktok",
  "account_id": "acc-stale",
  "version": "1.0",
  "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:120.0) Gecko/20100101 Firefox/120.0",
  "viewport": {"width": 1536, "height": 864},
  "locale": "zh-CN",
  "timezone": "Asia/Shanghai",
  "extra_http_headers": {
    "Accept-Language": "zh,CN;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Cache-Control": "max-age=0",
    "Upgrade-Insecure-Requests": "1"
  }
}
        """.strip(),
        encoding="utf-8",
    )

    fingerprint = manager.get_or_create_fingerprint(
        platform="tiktok",
        account_id="acc-stale",
        account_config={"region": "MY"},
    )

    assert fingerprint["version"] != "1.0"
    assert "Chrome/" in fingerprint["user_agent"]
    assert "Firefox/" not in fingerprint["user_agent"]
    assert set(fingerprint["extra_http_headers"].keys()) == {"Accept-Language"}


def test_tiktok_persisted_fingerprint_file_drops_non_minimal_headers(tmp_path):
    manager = DeviceFingerprintManager(base_path=tmp_path)

    fingerprint = manager.get_or_create_fingerprint(
        platform="tiktok",
        account_id="acc-clean",
        account_config={"region": "MY"},
    )

    fingerprint_file = manager.get_fingerprint_file("tiktok", "acc-clean")
    persisted = __import__("json").loads(fingerprint_file.read_text(encoding="utf-8"))

    assert persisted["version"] == fingerprint["version"]
    assert set(persisted["extra_http_headers"].keys()) == {"Accept-Language"}


def test_tiktok_fingerprint_keeps_shop_region_for_business_context_but_not_browser_locale(tmp_path):
    manager = DeviceFingerprintManager(base_path=tmp_path)

    fingerprint = manager.get_or_create_fingerprint(
        platform="tiktok",
        account_id="acc-sg",
        account_config={"region": "SG", "shop_region": "SG"},
    )

    assert fingerprint["region"] == "SG"
    assert fingerprint["locale"] == "zh-CN"
    assert fingerprint["timezone"] == "Asia/Shanghai"
    assert fingerprint["extra_http_headers"]["Accept-Language"].startswith("zh-CN")


def test_tiktok_fingerprint_ignores_account_level_locale_and_timezone_overrides(tmp_path):
    manager = DeviceFingerprintManager(base_path=tmp_path)

    fingerprint = manager.get_or_create_fingerprint(
        platform="tiktok",
        account_id="acc-override",
        account_config={
            "region": "SG",
            "shop_region": "SG",
            "locale": "en-SG",
            "timezone": "Asia/Singapore",
        },
    )

    assert fingerprint["region"] == "SG"
    assert fingerprint["locale"] == "zh-CN"
    assert fingerprint["timezone"] == "Asia/Shanghai"
    assert fingerprint["extra_http_headers"]["Accept-Language"].startswith("zh-CN")
