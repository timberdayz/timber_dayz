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
