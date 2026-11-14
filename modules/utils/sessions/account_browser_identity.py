"""账号浏览器运行环境（account browser identity）。

口径（2026-11-14 方向修订）
--------------------------
**账号之间只隔离「状态」，不造「指纹差异」。**

为什么这么定位
--------------
平台做账号关联时，能看到的信息分三层：

=========================  ==========================================  ==========
层                        平台能看到吗                                 我们能改吗
=========================  ==========================================  ==========
账号状态层                能（cookie / localStorage / 缓存 / 登录态 /  ======  能
（cookie、存储、令牌）      平台自己的设备令牌）                          「每个账号
                                                                            一个独立
                                                                            profile」
                                                                            目录」天然
                                                                            隔开
浏览器可改项              能（UA / 语言 / 时区 / 屏幕 / 浏览器版本）        能，但**不
                                                                            该造差异**
硬件指纹层                能（GPU/渲染器、CPU 核数、内存、字体、canvas）  **不能**
=========================  ==========================================  ==========

实测（本机，见计划文档「设备指纹实测」）：同一台机器上开两个**独立 profile**，
14 项指纹（canvas / WebGL 像素 / 字体集合 / UA / platform / 核数 / 屏幕 / 时区 / 语言 …）
**完全相同**，同一 profile 重开则完全稳定。

⇒ **独立 profile 不产生任何指纹隔离**，它隔开的是「账号状态层」——
   而状态层正是平台识别"同一操作者同一浏览器"的主要依据。

⇒ 同理，硬件指纹层**同型号同配置的机器大量重复**（全球几百万台同配置电脑
   的 canvas / WebGL / 字体 / 核数完全一样）⇒ 平台**不可能**把「指纹相同」
   当成「同一台电脑」的判据，否则会误杀几百万正常卖家。

⇒ 所以本模块**不再按账号派生任何指纹**。主动差异化（每人一个分辨率、
   每人一个浏览器版本）在同机多账号场景下**收益接近零**，反而会造出
   "分布外"的异常特征（真实用户不会 12 个账号 12 个不重复分辨率）。

本模块只做两件「不露馅」的事
---------------------------
1. **UA 去 ``HeadlessChrome``** —— 采集侧跑 headless，UA 里带
   ``HeadlessChrome`` 会让平台一眼认出自动化（实测）。
   **这不是「差异化」，是「别自曝」**：版本号、OS token 全部取自真实二进制。
2. **地区跟随出口 IP** —— 平台会把「浏览器语言/时区」与「出口 IP 所在国家」
   交叉比对，不一致就判「环境异常」（例如德国 IP + 中文 + 上海时区）。
   现在出口就是宿主 IP ⇒ 地区取宿主；等 G1 代理到位，按账号各自的出口放开。

安全边界
--------
只产出**浏览器环境参数**，**没有**任何凭据：不写 cookie / token / 代理口令 / 账号密码。

依据：``docs/guides/COLLECTION_SESSION_LIFECYCLE.md``（R8）。
"""

from __future__ import annotations

import os
import platform as _platform
import subprocess
from pathlib import Path
from typing import Any, Dict, Optional

#: 地区 ⇒ (locale, timezone_id, accept_language)
#:
#: ⚠️ 这张表**不是**"按账号派差异"的素材池，而是「**出口 IP 在哪 ⇒ 浏览器就说哪**」
#: 的对照表：给定出口所在地区 ⇒ 给出与之自洽的语言/时区/请求头。
#: 现在出口 = 宿主 IP ⇒ 取宿主地区（G1 代理到位后按账号各自的出口查）。
_REGION_PROFILES: Dict[str, Dict[str, str]] = {
    "cn": {
        "locale": "zh-CN",
        "timezone_id": "Asia/Shanghai",
        "accept_language": "zh-CN,zh;q=0.9,en;q=0.8",
    },
    "sg": {
        "locale": "en-SG",
        "timezone_id": "Asia/Singapore",
        "accept_language": "en-SG,en;q=0.9,zh-CN;q=0.8,zh;q=0.7",
    },
    "my": {
        "locale": "ms-MY",
        "timezone_id": "Asia/Kuala_Lumpur",
        "accept_language": "ms-MY,ms;q=0.9,en;q=0.8,zh-CN;q=0.7",
    },
    "ph": {
        "locale": "en-PH",
        "timezone_id": "Asia/Manila",
        "accept_language": "en-PH,en;q=0.9,en;q=0.8,zh-CN;q=0.7",
    },
    "th": {
        "locale": "th-TH",
        "timezone_id": "Asia/Bangkok",
        "accept_language": "th-TH,th;q=0.9,en;q=0.8,zh-CN;q=0.7",
    },
    "vn": {
        "locale": "vi-VN",
        "timezone_id": "Asia/Ho_Chi_Minh",
        "accept_language": "vi-VN,vi;q=0.9,en;q=0.8,zh-CN;q=0.7",
    },
    "id": {
        "locale": "id-ID",
        "timezone_id": "Asia/Jakarta",
        "accept_language": "id-ID,id;q=0.9,en;q=0.8,zh-CN;q=0.7",
    },
    "tw": {
        "locale": "zh-TW",
        "timezone_id": "Asia/Taipei",
        "accept_language": "zh-TW,zh;q=0.9,en;q=0.8,zh-CN;q=0.7",
    },
    "hk": {
        "locale": "zh-HK",
        "timezone_id": "Asia/Hong_Kong",
        "accept_language": "zh-HK,zh;q=0.9,en;q=0.8,zh-CN;q=0.7",
    },
    "us": {
        "locale": "en-US",
        "timezone_id": "America/New_York",
        "accept_language": "en-US,en;q=0.9",
    },
    "gb": {
        "locale": "en-GB",
        "timezone_id": "Europe/London",
        "accept_language": "en-GB,en;q=0.9",
    },
    "de": {
        "locale": "de-DE",
        "timezone_id": "Europe/Berlin",
        "accept_language": "de-DE,de;q=0.9,en;q=0.8",
    },
}

#: 操作系统 ⇒ UA 里的 OS token（**必须与真实宿主一致**）
_OS_UA_TOKEN: Dict[str, str] = {
    "windows": "Windows NT 10.0; Win64; x64",
    "macos": "Macintosh; Intel Mac OS X 10_15_7",
    "linux": "X11; Linux x86_64",
}

#: 标准 Chrome UA 模板（版本号填真实二进制版本）
_UA_TEMPLATE = (
    "Mozilla/5.0 ({os_token}) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/{version} Safari/537.36"
)

#: 读不到真实版本时的兜底版本号（只影响 UA 字符串里的版本字段）
_FALLBACK_CHROME_VERSION = "140.0.0.0"

#: 浏览器可执行文件（读版本用）。解析失败 ⇒ 空串。
_cached_executable_path: Optional[str] = None
_cached_user_agent: Optional[str] = None


# ---------------------------------------------------------------------------
# 宿主
# ---------------------------------------------------------------------------


def host_os_key() -> str:
    """宿主机的 OS 键（**只能**是真实宿主 OS）。

    UA 里的 OS token 必须与真实宿主一致 —— 否则平台会拿字体列表、WebGL
    渲染器、canvas 栈去对，一眼看出"头身不符"。
    """
    system = _platform.system().strip().lower()
    if system.startswith("win"):
        return "windows"
    if system == "darwin":
        return "macos"
    if system == "linux":
        return "linux"
    return "windows"


def host_timezone_id() -> str:
    """宿主机的 IANA 时区名（读不出来 ⇒ 兜底 ``Asia/Shanghai``）。"""
    try:
        from tzlocal import get_localzone

        name = str(get_localzone() or "").strip()
        if name:
            return name
    except Exception:  # pragma: no cover - tzlocal 不可用时走兜底
        pass
    return "Asia/Shanghai"


def host_region_key() -> str:
    """当前出口对应的地区键。

    现在所有账号的出口就是**宿主 IP** ⇒ 地区必须跟着宿主走；等 G1 代理到位，
    改成按账号各自的出口 IP 所在国家查即可（``region_profile`` 的入参）。

    为什么地区不能各编各的：平台会把「浏览器语言/时区」与「出口 IP 所在国家」
    交叉比对，不一致就判「环境异常」。自己制造「中国 IP + 德国时区」三重矛盾，
    比不伪装更露馅。
    """
    timezone_id = host_timezone_id()
    for key, profile in _REGION_PROFILES.items():
        if profile.get("timezone_id") == timezone_id:
            return key
    # 池子里没有对应时区（如宿主在某个欧洲城市）⇒ 用同一时区口径的兜底地区
    for key in ("cn", "sg", "tw"):
        if key in _REGION_PROFILES:
            return key
    return "cn"


def region_profile(region_key: Optional[str] = None) -> Dict[str, str]:
    """出口地区 ⇒ 浏览器该自报的语言 / 时区 / Accept-Language。

    Args:
        region_key: 出口 IP 所在地区键。``None`` ⇒ 取当前出口（= 宿主地区）。
    """
    key = str(region_key or "").strip().lower()
    if key not in _REGION_PROFILES:
        key = host_region_key()
    return dict(_REGION_PROFILES[key])


# ---------------------------------------------------------------------------
# UA：唯一的「去 Headless」处理
# ---------------------------------------------------------------------------


#: Playwright 浏览器目录里的 Chromium 可执行文件相对路径（按平台分）。
_CHROMIUM_EXECUTABLE_GLOBS = (
    "chromium-*/chrome-win/chrome.exe",
    "chromium-*/chrome-linux/chrome",
    "chromium-*/chrome-mac/Chromium.app/Contents/MacOS/Chromium",
)


def _chromium_executable_path() -> str:
    """Playwright 的 Chromium 可执行文件路径（读不到 ⇒ 空串）。

    ⚠️ **不启动 Playwright**：``sync_playwright()`` 在 asyncio 上下文里会直接抛错，
    而本模块会被采集的异步路径调用 ⇒ 改成直接扫 Playwright 的浏览器目录
    （布局是稳定的：``<browsers path>/chromium-<build>/...``）。
    """
    global _cached_executable_path
    if _cached_executable_path is not None:
        return _cached_executable_path

    roots: list[Path] = []
    env_root = os.getenv("PLAYWRIGHT_BROWSERS_PATH", "").strip()
    if env_root:
        roots.append(Path(env_root))
    # Linux/macOS 默认 ~/.cache/ms-playwright；Windows 默认 %LOCALAPPDATA%\ms-playwright
    roots.append(Path.home() / ".cache" / "ms-playwright")
    local_appdata = os.getenv("LOCALAPPDATA", "").strip()
    if local_appdata:
        roots.append(Path(local_appdata) / "ms-playwright")
    roots.append(Path("/ms-playwright"))

    candidates: list[Path] = []
    for root in roots:
        if not root.exists():
            continue
        for pattern in _CHROMIUM_EXECUTABLE_GLOBS:
            candidates.extend(root.glob(pattern))

    path = ""
    if candidates:
        newest = max(candidates, key=lambda item: item.stat().st_mtime)
        path = str(newest)
    _cached_executable_path = path
    return path


def _windows_file_version(path: str) -> str:
    """读 Windows PE 文件的版本号（``139.0.7258.5``）。"""
    if not path:
        return ""
    try:
        import ctypes

        size = ctypes.windll.version.GetFileVersionInfoSizeW(path, None)
        if not size:
            return ""
        buffer = ctypes.create_string_buffer(size)
        if not ctypes.windll.version.GetFileVersionInfoW(path, 0, size, buffer):
            return ""
        pointer = ctypes.c_void_p()
        length = ctypes.c_uint()
        if not ctypes.windll.version.VerQueryValueW(
            buffer, "\\", ctypes.byref(pointer), ctypes.byref(length)
        ):
            return ""
        # VS_FIXEDFILEINFO：dwFileVersionMS 是第 3 个 DWORD（索引 2），LS 是索引 3
        fixed = ctypes.cast(pointer, ctypes.POINTER(ctypes.c_uint32))
        ms = int(fixed[2])
        ls = int(fixed[3])
        return f"{ms >> 16}.{ms & 0xFFFF}.{ls >> 16}.{ls & 0xFFFF}"
    except Exception:
        return ""


def _subprocess_file_version(path: str) -> str:
    """跑 ``<chromium> --version`` 读版本号（**仅非 Windows**：Windows 会拉起窗口）。"""
    if not path or _platform.system().strip().lower().startswith("win"):
        return ""
    try:
        completed = subprocess.run(
            [path, "--version"],
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=15,
            check=False,
        )
    except Exception:
        return ""
    text = f"{completed.stdout or ''}\n{completed.stderr or ''}"
    for token in text.replace(",", " ").split():
        parts = token.split(".")
        if len(parts) >= 2 and all(part.isdigit() for part in parts[:2]):
            return ".".join(parts[:4]) if len(parts) >= 4 else ".".join(parts[:2])
    return ""


def _chromium_version() -> str:
    """真实 Chromium 版本号（读不到 ⇒ 兜底）。"""
    path = _chromium_executable_path()
    version = _windows_file_version(path)
    if not version:
        version = _subprocess_file_version(path)
    return version or _FALLBACK_CHROME_VERSION


def strip_headless_marker(user_agent: str) -> str:
    """把 UA 里的 ``HeadlessChrome`` 换成 ``Chrome``（其余一字不动）。

    ⚠️ **只去标记，不改版本、不改 OS token** —— 那些必须是真的，
    否则平台一比对就露馅。
    """
    text = str(user_agent or "")
    if not text:
        return text
    return text.replace("HeadlessChrome/", "Chrome/").replace(
        "HeadlessChrome", "Chrome"
    )


def browser_user_agent() -> str:
    """本机浏览器的真实 UA（**已去掉 Headless 标记**）。

    组成：真实 Chromium 版本号 + 真实宿主 OS token + 标准 Chrome UA 模板。
    """
    global _cached_user_agent
    if _cached_user_agent is not None:
        return _cached_user_agent
    os_token = _OS_UA_TOKEN.get(host_os_key(), _OS_UA_TOKEN["windows"])
    version = _chromium_version()
    _cached_user_agent = _UA_TEMPLATE.format(os_token=os_token, version=version)
    return _cached_user_agent


# ---------------------------------------------------------------------------
# 注入
# ---------------------------------------------------------------------------


def browser_context_options(
    region_key: Optional[str] = None,
    *,
    headless: bool = True,
) -> Dict[str, Any]:
    """浏览器运行环境 ⇒ Playwright context options。

    只注入**不露馅 / 与出口自洽**的字段：

    * ``user_agent`` —— **仅 headless 时**注入：真实版本 + 真实 OS token，
      去掉 ``HeadlessChrome``。headful 时浏览器自己的 UA 本来就正常 ⇒ 不碰。
    * ``locale`` / ``timezone_id`` / ``Accept-Language`` —— **仅在明确给出
      出口地区时**注入（``region_key``）。

    为什么 locale / 时区默认**不**注入
    ------------------------------
    现在所有账号的出口就是**宿主 IP** ⇒ 浏览器原生语言 / 时区**已经**与出口一致
    ⇒ 注入的是**同一个值**，纯属冗余；而且它会**覆盖 profile 原生设置**
    （用户在 Chrome 里手动改过语言时，那才是"这个账号真实的环境"）。
    ⇒ 真正需要覆盖的是「出口 ≠ 宿主」的时候 —— 那正是代理到位之后，
    此时由调用方把出口国家传进来（``region_key``）即可。

    ⚠️ **不注入** ``viewport``：屏幕尺寸是**宿主级**事实（真人管多个店，
    显示器只有一台），按账号差异化会造出「分布外」的异常特征，
    且 Chromium 的 ``screen`` 与真实显示器对不上时本身就是破绽。
    """
    options: Dict[str, Any] = {}

    if headless:
        options["user_agent"] = browser_user_agent()

    if region_key:
        region = region_profile(region_key)
        locale = str(region.get("locale") or "").strip()
        if locale:
            options["locale"] = locale
        timezone_id = str(region.get("timezone_id") or "").strip()
        if timezone_id:
            options["timezone_id"] = timezone_id
        accept_language = str(region.get("accept_language") or "").strip()
        if accept_language:
            options["extra_http_headers"] = {"Accept-Language": accept_language}

    return options


def browser_cdp_overrides(region_key: Optional[str] = None) -> Dict[str, Any]:
    """浏览器运行环境 ⇒ CDP ``Emulation.*`` 参数（供**裸 Chromium** 的巡店窗口用）。

    巡店走的是 Chromium 子进程 + CDP，不是 Playwright context ⇒ 注入方式不同。

    ⚠️ 这里**不覆盖 UA**：巡店窗口是 **headed**，UA 本来就正常，
    覆盖反而多一处可能写错的地方。
    ⚠️ 默认**不注入** locale / 时区：现在出口就是宿主 IP ⇒ 浏览器原生语言 / 时区
    已经与出口一致；等代理到位（出口 ≠ 宿主）再由调用方传入 ``region_key``。
    """
    if not region_key:
        return {}

    overrides: Dict[str, Any] = {}
    region = region_profile(region_key)

    accept_language = str(region.get("accept_language") or "").strip()
    if accept_language:
        overrides["acceptLanguage"] = accept_language
    locale = str(region.get("locale") or "").strip()
    if locale:
        overrides["locale"] = locale
    timezone_id = str(region.get("timezone_id") or "").strip()
    if timezone_id:
        overrides["timezoneId"] = timezone_id

    return overrides
