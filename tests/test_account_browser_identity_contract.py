"""账号浏览器运行环境契约（2026-11-14 方向修订后）。

口径
----
**账号之间只隔离「状态」，不造「指纹差异」。**

依据（实测，见计划文档「设备指纹实测」）：

* 同一台机器上开两个**独立 profile**，14 项指纹（canvas / WebGL 像素 / 字体集合 /
  UA / platform / 核数 / 屏幕 / 时区 / 语言 …）**完全相同**，同一 profile 重开则稳定
  ⇒ **独立 profile 不产生任何指纹隔离**，它隔开的是**账号状态层**
  （cookie / localStorage / 缓存 / 登录态 / 平台自己的设备令牌）；
* 同型号同配置的电脑，硬件指纹**大量重复**（全球几百万台）⇒ 平台**不可能**把
  「指纹相同」当成「同一台电脑」的判据；
* Chromium 的 ``machine_id`` **网页读不到** ⇒ 平台看不到它。

⇒ 按账号派生指纹（每人一个分辨率 / 浏览器版本 / 语言）在同机多账号场景下
**收益接近零**，反而造出「分布外」的异常特征（真实用户不会 12 个账号
12 个不重复分辨率）。

本文件锁死四件事：

1. **不造账号差异**：浏览器环境参数与账号无关（同一个函数、同一份取值）。
2. **不露馅**：UA 里不得出现 ``HeadlessChrome``（采集跑 headless）。
3. **地区跟出口**：locale / 时区 / Accept-Language 跟随**出口 IP 所在地区**。
4. **旧机制整套移除**：按账号派生的设备画像与 ``machine_id`` 隔离已删；
   巡店 / 顺序采集 / 并行采集三条路径统一走新的运行环境。

不碰数据库，全部是纯函数、纯源码断言与临时目录。
"""

from __future__ import annotations

import inspect
import re
from pathlib import Path

from modules.utils.sessions.account_browser_identity import (
    _OS_UA_TOKEN,
    browser_cdp_overrides,
    browser_context_options,
    browser_user_agent,
    host_os_key,
    host_region_key,
    region_profile,
    strip_headless_marker,
)


REPO_ROOT = Path(__file__).resolve().parents[1]


def _source(relative: str) -> str:
    return (REPO_ROOT / relative).read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# 1. 不造账号差异
# ---------------------------------------------------------------------------


def test_browser_environment_has_no_per_account_knob() -> None:
    """浏览器环境的**公开入口不得**接受账号参数。

    为什么锁这一条：一旦又出现「按 account_id 派 UA / 派分辨率」这种入口，
    差异就会悄悄回来 —— 而它既没有关联收益，又制造「分布外」的异常特征。
    """
    for func in (browser_context_options, browser_cdp_overrides, browser_user_agent):
        params = set(inspect.signature(func).parameters)
        assert "account_id" not in params, f"{func.__name__} 又开始按账号派差异了"
        assert "account" not in params, f"{func.__name__} 又开始按账号派差异了"


def test_browser_context_options_are_identical_across_calls() -> None:
    """两次调用必须给出**完全相同**的环境参数（没有随机、没有账号维度）。"""
    assert browser_context_options() == browser_context_options()
    assert browser_context_options(headless=True) == browser_context_options(
        headless=True
    )


def test_context_options_only_contain_whitelisted_keys() -> None:
    """只注入"不露馅 / 与出口自洽"的字段，其余一律不碰。"""
    options = browser_context_options()

    assert set(options.keys()) <= {
        "user_agent",
        "locale",
        "timezone_id",
        "extra_http_headers",
    }


def test_context_options_only_inject_user_agent_when_headless() -> None:
    """UA **只在 headless 时**注入。

    headless 的 UA 里带 ``HeadlessChrome`` ⇒ 平台一眼认出自动化（比撞同型号
    硬件指纹严重得多）；headful 时浏览器自己的 UA 本来就正常 ⇒ 不碰。
    """
    headless_options = browser_context_options(headless=True)
    headful_options = browser_context_options(headless=False)

    assert "HeadlessChrome" not in headless_options["user_agent"]
    assert "user_agent" not in headful_options


def test_context_options_do_not_override_locale_without_explicit_exit() -> None:
    """**没明确给出出口国家时，不覆盖** locale / 时区 / Accept-Language。

    现在出口就是宿主 IP ⇒ 浏览器原生语言 / 时区**已经**与出口一致，
    覆盖纯属冗余，而且会破坏 profile 原生设置（用户手动改过语言时）。
    真正需要覆盖的是"出口 ≠ 宿主"的时候 —— 那正是代理到位之后，
    由调用方把出口国家传进来。
    """
    default_options = browser_context_options()

    assert "locale" not in default_options
    assert "timezone_id" not in default_options
    assert "extra_http_headers" not in default_options


def test_context_options_do_not_set_viewport() -> None:
    """**不注入**屏幕尺寸。

    屏幕是**宿主级**事实（真人管多个店，显示器只有一台）⇒ 按账号差异化会造出
    「分布外」的异常特征；而且 Chromium 的 ``screen`` 与真实显示器对不上时
    本身就是破绽。
    """
    assert "viewport" not in browser_context_options()
    assert "viewport" not in browser_cdp_overrides()


# ---------------------------------------------------------------------------
# 2. 不露馅：UA 去 HeadlessChrome
# ---------------------------------------------------------------------------


def test_user_agent_has_no_headless_marker() -> None:
    """采集侧跑 headless ⇒ UA 里带 ``HeadlessChrome`` 会被一眼认出自动化。"""
    assert "HeadlessChrome" not in browser_user_agent()


def test_strip_headless_marker_only_touches_the_marker() -> None:
    """只换标记：**版本号与 OS token 一字不动**（改了就是露馅）。"""
    raw = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) HeadlessChrome/139.0.7258.5 Safari/537.36"
    )

    cleaned = strip_headless_marker(raw)

    assert "HeadlessChrome" not in cleaned
    assert "Chrome/139.0.7258.5" in cleaned
    assert "Windows NT 10.0; Win64; x64" in cleaned
    assert strip_headless_marker(cleaned) == cleaned
    assert strip_headless_marker("") == ""


def test_user_agent_matches_host_os() -> None:
    """UA 的 OS token 必须与**真实宿主**一致。

    ``navigator.platform`` 改不了 ⇒ UA 说 macOS 而系统是 Windows = 头身不符，
    比不伪装更露馅。
    """
    ua = browser_user_agent()
    token = _OS_UA_TOKEN[host_os_key()]

    assert token in ua
    assert ua.startswith("Mozilla/5.0 (")
    if host_os_key() == "windows":
        assert "Windows NT" in ua
    elif host_os_key() == "macos":
        assert "Macintosh" in ua
    elif host_os_key() == "linux":
        assert "X11; Linux" in ua


def test_user_agent_version_is_numeric() -> None:
    """版本号必须是数字（不是占位符、不是 ``Headless``）。"""
    match = re.search(r"Chrome/([0-9.]+)", browser_user_agent())

    assert match, "UA 里没有 Chrome 版本号"
    assert all(part.isdigit() for part in match.group(1).split("."))


# ---------------------------------------------------------------------------
# 3. 地区跟出口
# ---------------------------------------------------------------------------


def test_region_profile_maps_exit_region_to_matching_locale() -> None:
    """出口在德国 ⇒ 浏览器就说德语 / 柏林时间 —— 平台拿 IP 一比就知道对不对。"""
    region = region_profile("de")

    assert region["locale"] == "de-DE"
    assert region["timezone_id"] == "Europe/Berlin"
    assert region["accept_language"].startswith(region["locale"])


def test_region_profile_defaults_to_host_region() -> None:
    """不给出口 ⇒ 取当前出口（= 宿主 IP）对应的地区。"""
    assert region_profile() == region_profile(host_region_key())


def test_every_region_profile_is_internally_consistent() -> None:
    """地区池里的每一项都必须自洽（locale / 时区 / Accept-Language 对得上）。"""
    for key in ("cn", "sg", "my", "ph", "th", "vn", "id", "tw", "hk", "us", "gb", "de"):
        region = region_profile(key)

        assert region["locale"].strip(), key
        assert region["timezone_id"].strip(), key
        assert region["accept_language"].startswith(region["locale"]), key


def test_context_options_region_drives_locale_and_timezone() -> None:
    """**明确给出出口国家时**，locale / 时区 / Accept-Language 必须跟着它走。

    这是代理资源到位（G1）后的挂钩：出口在德国，浏览器就说德语 / 柏林时间
    —— 否则平台拿 IP 一比就知道环境异常。
    """
    options = browser_context_options(region_key="de")
    region = region_profile("de")

    assert options["locale"] == region["locale"]
    assert options["timezone_id"] == region["timezone_id"]
    assert options["extra_http_headers"]["Accept-Language"] == region["accept_language"]


# ---------------------------------------------------------------------------
# 4. 旧机制整套移除 + 三条路径同源
# ---------------------------------------------------------------------------


def test_legacy_device_profile_module_is_removed() -> None:
    """按账号派生的设备画像模块必须**不存在**（否则差异会悄悄回来）。"""
    assert not (
        REPO_ROOT / "modules" / "utils" / "sessions" / "account_device_profile.py"
    ).exists()


def test_inspection_window_no_longer_allocates_device_profile_or_machine_id() -> None:
    """巡店不再分配画像、不再改写 machine_id。

    machine_id 要改写 ``Local State``，而 ``Local State`` 是 Chromium **首次启动时**
    才创建的 ⇒ 每个账号的第一次巡店必然漏掉，改了也没意义；
    何况平台根本读不到它。
    """
    source = _source("modules/utils/pwcli_native.py")

    assert "prepare_account_device_identity" not in source
    assert "ensure_profile_machine_id" not in source
    assert "assign_device_profile" not in source
    assert "derive_machine_id" not in source


def test_inspection_window_injects_identity_before_navigation() -> None:
    """巡店是裸 Chromium ⇒ 走 CDP，且**必须在首次导航之前**注入。"""
    source = _source("modules/utils/pwcli_native.py")

    assert "apply_browser_identity_to_context" in source
    assert "Emulation.setTimezoneOverride" in source
    assert "Emulation.setLocaleOverride" in source

    inject_at = source.index("apply_browser_identity_to_context(context, page)")
    goto_at = source.index('page.goto(url, wait_until="domcontentloaded"')
    assert inject_at < goto_at, "浏览器环境必须在首次导航之前注入"


def test_inspection_window_does_not_override_user_agent() -> None:
    """巡店窗口是 **headed** ⇒ UA 本来就正常，覆盖只会多一处可能写错的地方。"""
    overrides = browser_cdp_overrides()

    assert "userAgent" not in overrides
    assert "platform" not in overrides
    assert set(overrides.keys()) <= {"acceptLanguage", "locale", "timezoneId"}


def test_collector_paths_use_the_shared_browser_identity() -> None:
    """顺序采集与并行扇出必须走**同一个**运行环境真源。"""
    sequential = _source("modules/apps/collection_center/runtime_session.py")
    parallel = _source("modules/apps/collection_center/executor_v2.py")

    for source in (sequential, parallel):
        assert "browser_context_options" in source
        assert "read_device_profile" not in source
        assert "assign_device_profile" not in source
        assert "ensure_profile_machine_id" not in source


def test_sequential_collection_keeps_profile_native_environment() -> None:
    """顺序采集挂 profile ⇒ 必须**沿用原生环境**（不叠加 runtime 覆盖）。"""
    source = _source("modules/apps/collection_center/runtime_session.py")

    assert "normalize_persistent_profile_context_options" in source
    assert "use_device_fingerprint=False" in source


def test_parallel_fanout_no_longer_warns_about_missing_device_profile() -> None:
    """并行扇出不再有「缺画像」的概念 ⇒ 那条 WARN 必须一起消失。

    留着它会误导运维去"先巡店一次生成画像"，而画像机制已经整体移除。
    """
    source = _source("modules/apps/collection_center/executor_v2.py")

    assert "PARALLEL_COLLECTION_NO_DEVICE_PROFILE" not in source
    assert "STANDARD_HEADLESS_VIEWPORT" in source


# ---------------------------------------------------------------------------
# 5. 出口同源（主账号级代理）
# ---------------------------------------------------------------------------


def test_proxy_source_is_main_account_first() -> None:
    """代理权威位在**主账号**（一个登录身份 = 一个出口），店铺级仅回退。"""
    inventory = _source("scripts/pwcli_account_inventory.py")
    assert "m.extra_config as main_extra_config" in inventory
    assert "row.main_extra_config" in inventory

    for loader in (
        "backend/services/account_loader_service.py",
        "backend/services/shop_account_loader_service.py",
    ):
        text = _source(loader)
        assert "main_account" in text
        assert "extra_config" in text


# ---------------------------------------------------------------------------
# 6. 文档口径（SSOT：只有一处定义）
# ---------------------------------------------------------------------------


def test_browser_environment_has_single_authoritative_definition() -> None:
    """「账号浏览器环境」的语义真源只能有一处（规范 R8）。"""
    lifecycle = _source("docs/guides/COLLECTION_SESSION_LIFECYCLE.md")

    assert "浏览器运行环境" in lifecycle, "R8 必须写明浏览器运行环境的口径"
    assert "HeadlessChrome" in lifecycle, "R8 必须写明为什么要去 Headless 标记"
