"""账号设备隔离契约守护（2026-11-14）。

业务目标
--------
让电商平台**无法把这批账号关联成「同一台电脑 + 同一个出口的账号矩阵」**。

本文件锁死四件事：

1. **账号设备画像**：每账号一套**自洽**的浏览器画像，确定性分配，账号间不撞车。
2. **机器标识隔离**：``machine_id`` 按账号确定性派生 ⇒ 不再是"同一台机器"。
3. **三条路径同一套设备**：人工巡店 / 顺序采集 / 并行采集用同一份画像。
4. **出口同源**：代理取自主账号级（权威位），巡店与采集同源。

不碰数据库，全部是纯函数与临时目录。
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from modules.utils.sessions.account_device_profile import (
    DEVICE_PROFILE_FILENAME,
    DEVICE_PROFILE_SCHEMA_VERSION,
    assign_device_profile,
    build_device_profile,
    derive_machine_id,
    device_cdp_overrides,
    device_context_options,
    device_profile_path,
    ensure_profile_machine_id,
    host_device_baseline,
    host_os_key,
    read_device_profile,
    write_device_profile,
)


REPO_ROOT = Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------------------
# 1. 画像生成
# ---------------------------------------------------------------------------

def test_device_profile_is_deterministic_for_same_account():
    """同一账号 ⇒ 同一套画像（设备人格稳定，不随代码版本/调用次数变）。"""
    first = build_device_profile("hongxikeji:main", platform="shopee")
    second = build_device_profile("hongxikeji:main", platform="shopee")

    assert first["device"] == second["device"]
    assert first["device"]["user_agent"]


def test_device_profile_differs_between_accounts():
    """不同账号 ⇒ 不同画像（否则平台一眼看出同机多账号）。"""
    accounts = [
        "miaoshou_real_001",
        "chenewei666:main",
        "hongxikeji:main",
        "shopee KR",
        "Tiktok 1店",
        "chenzeweinbnb@163.com",
        "虾皮巴西（东朗照明主体）",
        "accept_main_1775126941575",
    ]
    signatures = {
        json.dumps(build_device_profile(acc, platform="shopee")["device"], sort_keys=True)
        for acc in accounts
    }

    assert len(signatures) == len(accounts), "不同账号拿到了相同画像"


def test_device_profile_uses_host_os():
    """画像的 OS **必须等于宿主 OS**。

    为什么：``navigator.platform`` 在 Playwright 路径（顺序采集 / 并行扇出）
    **无法覆盖** —— Playwright 的 ``new_context`` 没有 platform 参数，
    只有 CDP ``Emulation.setUserAgentOverride`` 才带，而那条路只有巡店窗口走。

    ⇒ 给 Windows 主机派 macOS 画像 ⇒ 浏览器里 ``navigator.platform`` 还是 ``Win32``，
    UA 却写着 ``Macintosh`` ⇒ **头身不符**；而且字体列表 / WebGL 渲染器 / canvas /
    音频栈全是 Windows 特征 ⇒ 伪装当场被识破，**比不伪装更露馅**。

    账号之间的隔离靠浏览器/版本/视口/时区/语言/machine_id/出口 IP，
    **不靠假装换操作系统**。
    """
    host = host_os_key()
    baseline = host_device_baseline()

    for account_id in ("acc-a", "acc-b", "acc-c", "acc-d", "acc-e", "acc-f"):
        device = build_device_profile(account_id, platform="shopee")["device"]
        assert device["os"] == host
        # 宿主 OS ⇒ 对应的 navigator.platform 取值必须固定
        assert device["platform_id"] == baseline["platform_id"]
        # devicePixelRatio 必须与宿主显示一致
        assert device["device_scale_factor"] == baseline["device_scale_factor"]


def test_device_profile_os_does_not_vary_between_accounts():
    """OS 不再是账号间的差异维度 —— 差异必须来自别处（否则就是自相矛盾）。"""
    devices = [
        build_device_profile(account_id, platform="shopee")["device"]
        for account_id in ("acc-a", "acc-b", "acc-c", "acc-d", "acc-e", "acc-f")
    ]
    assert len({device["os"] for device in devices}) == 1


def test_device_profile_is_internally_consistent():
    """画像必须**整套自洽** —— 只改 UA 而不改时区/语言/平台 = 头身不符，比不伪装更露馅。"""
    for account_id in ("acc-a", "acc-b", "acc-c", "acc-d", "acc-e", "acc-f"):
        device = build_device_profile(account_id, platform="shopee")["device"]
        ua = device["user_agent"]
        platform_id = device["platform_id"]

        # UA 的操作系统必须与 navigator.platform 对得上
        if platform_id == "Win32":
            assert "Windows NT" in ua
        elif platform_id == "MacIntel":
            assert "Macintosh" in ua
        elif platform_id == "Linux x86_64":
            assert "X11; Linux" in ua
        else:  # pragma: no cover - 池子外的取值
            pytest.fail(f"未知 platform_id: {platform_id}")

        # Safari 只在 macOS 上成立
        if "Version/" in ua and "Safari" in ua:
            assert platform_id == "MacIntel"

        # locale 与 Accept-Language 必须同源
        assert device["accept_language"].startswith(device["locale"])

        # 视口必须是正整数
        assert device["viewport"]["width"] > 0
        assert device["viewport"]["height"] > 0


def test_device_profile_uids_do_not_contain_empty_fields():
    """画像里不得出现空的关键字段（空 UA 等于没隔离）。"""
    for account_id in ("x1", "x2", "x3", "x4", "x5", "x6", "x7", "x8"):
        device = build_device_profile(account_id, platform="tiktok")["device"]
        assert device["user_agent"].strip()
        assert device["platform_id"].strip()
        assert device["locale"].strip()
        assert device["timezone_id"].strip()
        assert device["accept_language"].strip()


# ---------------------------------------------------------------------------
# 2. 画像读写与分配
# ---------------------------------------------------------------------------

def test_device_profile_roundtrip(tmp_path):
    profile_dir = tmp_path / "shopee" / "acc1"
    payload = build_device_profile("acc1", platform="shopee")

    path = write_device_profile(profile_dir, payload)
    assert path == profile_dir / DEVICE_PROFILE_FILENAME

    loaded = read_device_profile(profile_dir)
    assert loaded is not None
    assert loaded["device"]["user_agent"] == payload["device"]["user_agent"]
    assert loaded["schema_version"] == DEVICE_PROFILE_SCHEMA_VERSION


def test_read_device_profile_returns_none_for_unknown_schema(tmp_path):
    profile_dir = tmp_path / "acc"
    profile_dir.mkdir(parents=True)
    (profile_dir / DEVICE_PROFILE_FILENAME).write_text(
        json.dumps({"schema_version": 999, "device": {"user_agent": "x"}}),
        encoding="utf-8",
    )

    assert read_device_profile(profile_dir) is None


def test_read_device_profile_returns_none_for_corrupt_file(tmp_path):
    profile_dir = tmp_path / "acc"
    profile_dir.mkdir(parents=True)
    (profile_dir / DEVICE_PROFILE_FILENAME).write_text("{not json", encoding="utf-8")

    assert read_device_profile(profile_dir) is None


def test_assign_device_profile_is_stable_and_idempotent(tmp_path):
    profiles_root = tmp_path / "profiles"
    profile_dir = profiles_root / "shopee" / "acc-stable"

    path, first = assign_device_profile(
        profiles_root, profile_dir, platform="shopee", account_id="acc-stable"
    )
    assert path.exists()

    path2, second = assign_device_profile(
        profiles_root, profile_dir, platform="shopee", account_id="acc-stable"
    )

    assert path2 == path
    assert second["device"] == first["device"]


def test_assign_device_profile_avoids_collision_with_existing_account(tmp_path):
    """占用校验：目标槽位已被别的账号占用 ⇒ 顺延到不撞的槽位。"""
    profiles_root = tmp_path / "profiles"
    first_dir = profiles_root / "shopee" / "acc-1"
    second_dir = profiles_root / "shopee" / "acc-2"

    _, first = assign_device_profile(
        profiles_root, first_dir, platform="shopee", account_id="acc-1"
    )
    _, second = assign_device_profile(
        profiles_root, second_dir, platform="shopee", account_id="acc-2"
    )

    assert first["device"] != second["device"], "两个账号拿到了同一套画像"


# ---------------------------------------------------------------------------
# 3. 机器标识隔离
# ---------------------------------------------------------------------------

def test_derive_machine_id_is_deterministic_and_unique():
    a = derive_machine_id("shopee", "acc-1")
    b = derive_machine_id("shopee", "acc-1")
    c = derive_machine_id("shopee", "acc-2")
    d = derive_machine_id("tiktok", "acc-1")

    assert a == b, "同一账号的 machine_id 必须稳定"
    assert a != c, "不同账号的 machine_id 必须不同"
    assert a != d, "不同平台的同一账号也必须不同"
    assert re.match(r"^[0-9a-f-]{36}$", a)


def test_ensure_profile_machine_id_writes_account_specific_value(tmp_path):
    profile_dir = tmp_path / "shopee" / "acc-1"
    profile_dir.mkdir(parents=True)
    (profile_dir / "Local State").write_text(
        json.dumps(
            {
                "user_experience_metrics": {
                    "machine_id": "shared-machine-id",
                    "client_id2": "keep-me",
                }
            }
        ),
        encoding="utf-8",
    )

    result = ensure_profile_machine_id(
        profile_dir, platform="shopee", account_id="acc-1"
    )

    assert result == derive_machine_id("shopee", "acc-1")
    payload = json.loads((profile_dir / "Local State").read_text(encoding="utf-8"))
    assert payload["user_experience_metrics"]["machine_id"] == result
    # 其它字段不能被破坏
    assert payload["user_experience_metrics"]["client_id2"] == "keep-me"


def test_ensure_profile_machine_id_is_idempotent(tmp_path):
    profile_dir = tmp_path / "shopee" / "acc-1"
    profile_dir.mkdir(parents=True)
    (profile_dir / "Local State").write_text(
        json.dumps({"user_experience_metrics": {}}), encoding="utf-8"
    )

    first = ensure_profile_machine_id(
        profile_dir, platform="shopee", account_id="acc-1"
    )
    second = ensure_profile_machine_id(
        profile_dir, platform="shopee", account_id="acc-1"
    )

    assert first == second


def test_ensure_profile_machine_id_tolerates_missing_local_state(tmp_path):
    """Local State 不存在时不能抛异常（巡店/采集不该因此失败）。"""
    profile_dir = tmp_path / "shopee" / "new-account"

    assert (
        ensure_profile_machine_id(
            profile_dir, platform="shopee", account_id="new-account"
        )
        is None
    )


# ---------------------------------------------------------------------------
# 4. 注入
# ---------------------------------------------------------------------------

def test_device_context_options_only_contains_whitelisted_keys():
    payload = build_device_profile("acc-1", platform="shopee")
    options = device_context_options(payload)

    assert set(options.keys()) <= {
        "user_agent",
        "viewport",
        "locale",
        "timezone_id",
        "extra_http_headers",
    }
    assert options["user_agent"] == payload["device"]["user_agent"]
    assert options["locale"] == payload["device"]["locale"]
    assert options["timezone_id"] == payload["device"]["timezone_id"]
    assert options["viewport"] == payload["device"]["viewport"]
    assert set(options["extra_http_headers"].keys()) == {"Accept-Language"}


def test_device_context_options_empty_for_missing_profile():
    assert device_context_options(None) == {}
    assert device_context_options({}) == {}


def test_device_cdp_overrides_carry_user_agent_platform_and_locale():
    payload = build_device_profile("acc-1", platform="shopee")
    overrides = device_cdp_overrides(payload)

    assert overrides["userAgent"] == payload["device"]["user_agent"]
    assert overrides["platform"] == payload["device"]["platform_id"]
    assert overrides["acceptLanguage"] == payload["device"]["accept_language"]
    assert overrides["locale"] == payload["device"]["locale"]
    assert overrides["timezoneId"] == payload["device"]["timezone_id"]
    assert overrides["viewport"]["width"] > 0


# ---------------------------------------------------------------------------
# 5. 三条路径必须用同一套设备（口径不分裂）
# ---------------------------------------------------------------------------

def test_collector_and_inspection_share_one_device_profile():
    """巡店与采集读的是**同一个**画像文件 ⇒ 同一台设备。"""
    profile_dir = REPO_ROOT / "profiles" / "shopee" / "unit-test-acc"
    payload = build_device_profile("unit-test-acc", platform="shopee")
    write_device_profile(profile_dir, payload)

    assert device_profile_path(profile_dir).name == DEVICE_PROFILE_FILENAME
    loaded = read_device_profile(profile_dir)
    assert loaded is not None
    assert device_context_options(loaded) == device_context_options(payload)

    # 清理（避免污染真实 profiles 目录）
    device_profile_path(profile_dir).unlink(missing_ok=True)


def test_profile_mode_does_not_load_legacy_fingerprint_manager():
    """profile 模式**不得**再加载旧的 ``DeviceFingerprintManager``。

    旧机制池子小（组合上限 60）且实测已有账号撞车，注入的 UA 与 profile 内生标识
    头身不符 ⇒ 反而更容易被平台关联。
    """
    source = (
        REPO_ROOT / "modules" / "apps" / "collection_center" / "runtime_session.py"
    ).read_text(encoding="utf-8")

    # profile 路径必须显式关闭旧指纹
    assert "use_device_fingerprint=False" in source
    # 顺序路径必须读账号设备画像
    assert "read_device_profile" in source
    assert "device_context_options" in source


def test_parallel_fanout_uses_same_device_profile_and_warns_when_missing():
    """并行扇出必须与顺序路径用同一套画像；缺画像时必须告警（不能静默）。"""
    source = (
        REPO_ROOT / "modules" / "apps" / "collection_center" / "executor_v2.py"
    ).read_text(encoding="utf-8")

    assert "read_device_profile" in source
    assert "device_context_options" in source
    assert "PARALLEL_COLLECTION_NO_DEVICE_PROFILE" in source


def test_inspection_window_injects_device_profile_before_navigation():
    """巡店是裸 Chromium ⇒ 必须走 CDP，且**必须在首次导航之前**注入。"""
    source = (REPO_ROOT / "modules" / "utils" / "pwcli_native.py").read_text(
        encoding="utf-8"
    )

    assert "apply_device_profile_to_context" in source
    assert "Emulation.setUserAgentOverride" in source
    assert "Emulation.setTimezoneOverride" in source
    assert "Emulation.setLocaleOverride" in source
    assert "Emulation.setDeviceMetricsOverride" in source

    inject_at = source.index("apply_device_profile_to_context(context, page, device_payload)")
    goto_at = source.index("page.goto(url, wait_until=\"domcontentloaded\"")
    assert inject_at < goto_at, "设备画像必须在首次导航之前注入"


def test_inspection_window_isolates_machine_id_before_launch():
    """machine_id 要在 Chromium **启动前**改写（启动后就晚了一轮）。"""
    source = (REPO_ROOT / "modules" / "utils" / "pwcli_native.py").read_text(
        encoding="utf-8",
    )

    assert "prepare_account_device_identity" in source
    prepare_at = source.index("prepare_account_device_identity(")
    launch_at = source.index("process = subprocess.Popen(")
    assert prepare_at < launch_at


# ---------------------------------------------------------------------------
# 6. 出口同源（主账号级代理）
# ---------------------------------------------------------------------------

def test_proxy_source_is_main_account_first():
    """代理权威位在**主账号**（一个登录身份 = 一个出口），店铺级仅回退。"""
    inventory = (REPO_ROOT / "scripts" / "pwcli_account_inventory.py").read_text(
        encoding="utf-8"
    )
    assert "m.extra_config as main_extra_config" in inventory
    assert "row.main_extra_config" in inventory

    for loader in (
        REPO_ROOT / "backend" / "services" / "account_loader_service.py",
        REPO_ROOT / "backend" / "services" / "shop_account_loader_service.py",
    ):
        text = loader.read_text(encoding="utf-8")
        assert "main_account" in text
        assert "extra_config" in text


# ---------------------------------------------------------------------------
# 7. 文档口径（SSOT：只有一处定义）
# ---------------------------------------------------------------------------

def test_device_identity_has_single_authoritative_definition():
    """「账号设备身份」的语义真源只能有一处（规范 R8 及其设备画像小节）。"""
    lifecycle = (
        REPO_ROOT / "docs" / "guides" / "COLLECTION_SESSION_LIFECYCLE.md"
    ).read_text(encoding="utf-8")

    assert "设备画像" in lifecycle, "R8 必须写明设备画像是设备身份的载体"
    assert "machine_id" in lifecycle, "R8 必须写明 machine_id 隔离"
