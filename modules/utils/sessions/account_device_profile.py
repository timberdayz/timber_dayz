"""账号设备画像（account device profile）—— 账号间**不可关联**的第一层设备侧载体。

业务目标
--------
让电商平台**无法把这批账号关联成「同一台电脑 + 同一个出口的账号矩阵」**。

平台做关联时看的是一整套设备特征，而不是单个字段：

* ``machine_id`` —— Chromium 的机器级标识（Windows MachineGuid 派生）。
  **同一台机器上的所有 profile 必然相同** ⇒ 不处理 = 一眼关联。
* UA / 屏幕 / 时区 / 语言 / ``navigator.platform`` / ``devicePixelRatio`` ——
  浏览器画像。必须**整套自洽**（不能 UA 说 macOS 而 platform 说 Win32）。
* profile 内生的 ``client_id2`` / ``ablation_seed`` / cookie / LocalStorage ——
  天然按 profile 目录隔离 ✅

本模块负责两件事：

1. **设备画像**：为每个主账号生成并落盘**一套自洽的**浏览器画像，
   落在 profile 目录内（``profiles/<平台>/<账号>/.device_profile.json``）——
   与登录态**同生共死**，删账号删目录、拷账号拷目录。
2. **机器标识隔离**：把 profile 的 ``machine_id`` 改写成**按 account_id 确定性派生**的
   独立值（实测 Chromium 不会覆盖改写值，见计划文档的实测记录）。

为什么画像绑**主账号**
----------------------
一个登录身份 = 一台设备。其下的店铺账号**继承**同一套画像与同一个出口 ——
这与真实业务一致（一个卖家用一个邮箱登多个店）。真正致命的是
「8 个主账号在同一个 IP、同一个 machine_id 下」。

分配规则
--------
画像由 ``md5(account_id)`` **确定性**派生 ⇒ 同一账号永远得到同一套画像
（设备人格稳定，**不随代码版本变**）。落盘时做**占用校验**：
若目标槽位已被别的账号占用，则顺延到下一个可用槽位 ⇒ 账号变多也不撞。

**OS 只取宿主 OS**（见 ``host_os_key``）：Playwright 路径改不了 ``navigator.platform``，
派一个与宿主不同的 OS = 头身不符，比不伪装更露馅。账号间的隔离靠浏览器/版本/视口/
时区/语言/``machine_id``/出口 IP，**不靠假装换操作系统**。

安全边界
--------
画像里**只有设备特征**，**没有**任何凭据：不写 cookie / token / 代理口令 / 账号密码。

依据：``docs/guides/COLLECTION_SESSION_LIFECYCLE.md``（R8 及其设备画像小节）。
"""

from __future__ import annotations

import hashlib
import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


#: 画像文件名（放在 profile 目录内，与登录态同生共死）
DEVICE_PROFILE_FILENAME = ".device_profile.json"

#: 画像结构版本。读到不认识的版本 ⇒ 视为「无画像」（降级，不报错）。
DEVICE_PROFILE_SCHEMA_VERSION = 1

#: 画像来源：按账号确定性生成
DEVICE_PROFILE_SOURCE_DERIVED = "account_derived"

#: ``machine_id`` 的 UUID 命名空间（固定值 ⇒ 派生结果可复现）
MACHINE_ID_NAMESPACE = uuid.UUID("6f2d9d4a-1f3b-4a8e-9c21-7b0e5d3a8c14")


def host_os_key() -> str:
    """宿主机的 OS 键（画像**必须**与之一致）。

    为什么必须一致
    --------------
    ``navigator.platform`` 在 **Playwright 路径**（顺序采集 / 并行扇出）**无法覆盖** ——
    Playwright 的 ``new_context`` 没有 platform 参数；只有 CDP
    ``Emulation.setUserAgentOverride`` 才带 platform，而那条路**只有巡店窗口**走。
    ⇒ 若给 Windows 主机派了 macOS 画像，浏览器里 ``navigator.platform`` 仍是
    ``Win32``，UA 却写着 ``Macintosh`` ⇒ **头身不符**。
    而且这种伪装会被立刻识破：字体列表、WebGL 渲染器、canvas、音频栈、GPU vendor
    全都是 Windows 特征 —— 比不伪装**更露馅**。

    所以画像的 OS **只取宿主 OS**。账号之间的隔离靠：
    浏览器与版本、视口、时区、语言、``machine_id``、出口 IP —— **不靠假装换操作系统**。
    """
    import platform as _platform

    system = _platform.system().strip().lower()
    if system.startswith("win"):
        return "windows"
    if system == "darwin":
        return "macos"
    if system == "linux":
        return "linux"
    return "windows"


def host_device_baseline() -> Dict[str, Any]:
    """宿主机的设备基线（OS / ``navigator.platform`` / ``devicePixelRatio``）。

    画像里的这三项**必须**等于它 —— 理由见 :func:`host_os_key`。
    """
    os_key = host_os_key()
    profile = _OS_PROFILES[os_key]
    return {
        "os": os_key,
        "platform_id": profile["platform_id"],
        "device_scale_factor": profile["device_scale_factor"],
    }


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
    """宿主所在地区（画像的 locale / 时区 / Accept-Language 取这里）。

    为什么地区也锁宿主
    ------------------
    平台会把**浏览器时区/语言**与**出口 IP 所在国家**做交叉比对，不一致就是
    「环境异常」信号。而当前**所有账号的出口就是宿主 IP**（库里代理配置 0 条）⇒
    给账号派 ``de-DE / Europe/Berlin`` 之类，等于**自己制造**
    「中国 IP + 德国时区 + 德国语言」的三重矛盾 —— 比不伪装更露馅。

    真实卖家就是中国人在管海外店：浏览器语言是中文、时区是本地、IP 走海外代理。
    ⇒ **地区维度跟着出口走**：现在出口是宿主，地区就取宿主；
    等 G1（代理资源）到位，再按账号各自的出口放开地区维度。
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


# ---------------------------------------------------------------------------
# 设备画像素材池
#
# 原则：**整套自洽** —— UA 的操作系统 / 浏览器 / 版本，必须与
# ``navigator.platform``、``devicePixelRatio``、``Accept-Language``、时区对得上。
# 只改 UA 而不改其它字段 = 头身不符，比不伪装更露馅。
# ---------------------------------------------------------------------------

#: 操作系统 ⇒ (navigator.platform, devicePixelRatio, 常见视口列表)
_OS_PROFILES: Dict[str, Dict[str, Any]] = {
    "windows": {
        "platform_id": "Win32",
        "device_scale_factor": 1.0,
        "viewports": [(1920, 1080), (1536, 864), (1440, 900), (1660, 1050), (1366, 768)],
    },
    "macos": {
        "platform_id": "MacIntel",
        "device_scale_factor": 2.0,
        "viewports": [(1440, 900), (1512, 982), (1728, 1080), (1280, 800), (1680, 1050)],
    },
    "linux": {
        "platform_id": "Linux x86_64",
        "device_scale_factor": 1.0,
        "viewports": [(1920, 1080), (1600, 900), (1366, 768), (1440, 900), (1280, 1024)],
    },
}

#: 浏览器 ⇒ (UA 模板, 版本序列)
_BROWSER_PROFILES: Dict[str, Dict[str, Any]] = {
    "chrome": {
        "versions": [136, 135, 134, 133, 132],
        "ua": (
            "Mozilla/5.0 ({os_token}) AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/{version}.0.0.0 Safari/537.36"
        ),
        "os_token": {
            "windows": "Windows NT 10.0; Win64; x64",
            "macos": "Macintosh; Intel Mac OS X 10_15_7",
            "linux": "X11; Linux x86_64",
        },
    },
    "edge": {
        "versions": [136, 135, 134, 133],
        "ua": (
            "Mozilla/5.0 ({os_token}) AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/{version}.0.0.0 Safari/537.36 Edg/{version}.0.0.0"
        ),
        "os_token": {
            "windows": "Windows NT 10.0; Win64; x64",
            "macos": "Macintosh; Intel Mac OS X 10_15_7",
            "linux": "X11; Linux x86_64",
        },
    },
    "firefox": {
        "versions": [121, 120, 119],
        "ua": "Mozilla/5.0 ({os_token}; rv:{version}.0) Gecko/20100101 Firefox/{version}.0",
        "os_token": {
            "windows": "Windows NT 10.0; Win64; x64",
            "macos": "Macintosh; Intel Mac OS X 10.15",
            "linux": "X11; Linux x86_64",
        },
    },
    "safari": {
        "versions": ["17.2", "17.1", "17.0"],
        "ua": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
            "(KHTML, like Gecko) Version/{version} Safari/605.1.15"
        ),
        "os_token": {"macos": "Macintosh; Intel Mac OS X 10_15_7"},
    },
}

#: 地区 ⇒ (locale, timezone_id, accept_language, currency)
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
        "accept_language": "en-PH,en;q=0.9,fil;q=0.8",
    },
    "th": {
        "locale": "th-TH",
        "timezone_id": "Asia/Bangkok",
        "accept_language": "th-TH,th;q=0.9,en;q=0.8",
    },
    "vn": {
        "locale": "vi-VN",
        "timezone_id": "Asia/Ho_Chi_Minh",
        "accept_language": "vi-VN,vi;q=0.9,en;q=0.8",
    },
    "id": {
        "locale": "id-ID",
        "timezone_id": "Asia/Jakarta",
        "accept_language": "id-ID,id;q=0.9,en;q=0.8",
    },
    "tw": {
        "locale": "zh-TW",
        "timezone_id": "Asia/Taipei",
        "accept_language": "zh-TW,zh;q=0.9,en;q=0.8",
    },
    "hk": {
        "locale": "zh-HK",
        "timezone_id": "Asia/Hong_Kong",
        "accept_language": "zh-HK,zh;q=0.9,en;q=0.8",
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

#: 画像里**不参与** Playwright context 注入的字段（它们由 Chromium 运行时决定，
#: 硬改会与真实渲染不一致）。
_NON_INJECTED_KEYS = (
    "device_scale_factor",
    "is_mobile",
    "has_touch",
    "color_scheme",
    "reduced_motion",
    "forced_colors",
)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _seed_for(account_id: str, salt: str = "") -> int:
    payload = f"{salt}|{str(account_id or '').strip()}".encode("utf-8")
    return int(hashlib.md5(payload).hexdigest()[:8], 16)


# ---------------------------------------------------------------------------
# 画像生成
# ---------------------------------------------------------------------------

def build_device_profile(
    account_id: str,
    *,
    platform: str = "",
    slot: int = 0,
    region_key: Optional[str] = None,
) -> Dict[str, Any]:
    """按 account_id **确定性**生成一套自洽的设备画像。

    Args:
        account_id: 主账号 ID（决定画像内容）。
        platform: 平台代码（记入画像，便于排障）。
        slot: 冲突顺延槽位。不同槽位 ⇒ 不同画像（用于占用校验失败时顺延）。
        region_key: 地区键（locale / 时区 / Accept-Language）。
            默认取**宿主所在地区**（``host_region_key()``）——
            地区必须与**出口 IP** 一致，而当前出口就是宿主 IP（见 ``host_region_key``）。

    Returns:
        画像 payload（未落盘）。
    """
    seed = _seed_for(account_id, salt=f"slot:{slot}")

    # OS 只取宿主：Playwright 路径改不了 ``navigator.platform``，
    # 派一个与宿主不同的 OS = 头身不符（详见 ``host_os_key``）。
    os_keys = [host_os_key()]
    browser_keys = list(_BROWSER_PROFILES.keys())

    # Safari 只存在于 macOS —— 组合时必须过滤，否则会出现不自洽的画像。
    os_key = os_keys[seed % len(os_keys)]
    candidates = [key for key in browser_keys if "safari" not in key or os_key == "macos"]
    browser_key = candidates[(seed // len(os_keys)) % len(candidates)]

    os_profile = _OS_PROFILES[os_key]
    browser_profile = _BROWSER_PROFILES[browser_key]

    versions = browser_profile["versions"]
    version = versions[(seed // 7) % len(versions)]
    version_text = str(version)

    os_token = browser_profile["os_token"].get(os_key)
    if not os_token:
        # 组合不成立（例如 Safari + 非 macOS）⇒ 退回 Chrome + 当前 OS
        browser_key = "chrome"
        browser_profile = _BROWSER_PROFILES["chrome"]
        versions = browser_profile["versions"]
        version = versions[(seed // 7) % len(versions)]
        version_text = str(version)
        os_token = browser_profile["os_token"][os_key]

    user_agent = browser_profile["ua"].format(
        os_token=os_token,
        version=version_text,
    )

    viewports = os_profile["viewports"]
    width, height = viewports[(seed // 11) % len(viewports)]

    resolved_region = str(region_key or "").strip().lower()
    if resolved_region not in _REGION_PROFILES:
        # 地区默认取宿主（出口就是宿主 IP ⇒ 地区必须跟着出口走）
        resolved_region = host_region_key()
    region = _REGION_PROFILES[resolved_region]

    return {
        "schema_version": DEVICE_PROFILE_SCHEMA_VERSION,
        "platform": str(platform or "").strip(),
        "account_id": str(account_id or "").strip(),
        "source": DEVICE_PROFILE_SOURCE_DERIVED,
        "slot": int(slot),
        "created_at": _utc_now_iso(),
        "updated_at": _utc_now_iso(),
        "device": {
            "os": os_key,
            "browser": browser_key,
            "browser_version": version_text,
            "user_agent": user_agent,
            "platform_id": os_profile["platform_id"],
            "device_scale_factor": os_profile["device_scale_factor"],
            "viewport": {"width": width, "height": height},
            "locale": region["locale"],
            "timezone_id": region["timezone_id"],
            "accept_language": region["accept_language"],
            "region": resolved_region,
            "is_mobile": False,
            "has_touch": False,
            "color_scheme": "light",
            "reduced_motion": "no-preference",
            "forced_colors": "none",
        },
    }


# ---------------------------------------------------------------------------
# 画像读写
# ---------------------------------------------------------------------------

def device_profile_path(profile_dir: Path | str) -> Path:
    """画像路径：``<profile_dir>/.device_profile.json``。"""
    return Path(profile_dir) / DEVICE_PROFILE_FILENAME


def read_device_profile(profile_dir: Path | str) -> Optional[Dict[str, Any]]:
    """读画像；读不到 / 损坏 / 版本不认识 ⇒ ``None``（降级，不抛异常）。"""
    path = device_profile_path(profile_dir)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, TypeError, ValueError):
        return None

    if not isinstance(payload, dict):
        return None
    if payload.get("schema_version") != DEVICE_PROFILE_SCHEMA_VERSION:
        return None
    device = payload.get("device")
    if not isinstance(device, dict) or not device:
        return None
    return payload


def write_device_profile(
    profile_dir: Path | str,
    payload: Dict[str, Any],
) -> Path:
    """原子写画像（先写 ``.tmp`` 再 ``replace``）。"""
    path = device_profile_path(profile_dir)
    path.parent.mkdir(parents=True, exist_ok=True)

    normalized = dict(payload or {})
    normalized["schema_version"] = DEVICE_PROFILE_SCHEMA_VERSION
    normalized.setdefault("created_at", _utc_now_iso())
    normalized["updated_at"] = _utc_now_iso()

    tmp_path = path.with_name(f"{path.name}.tmp")
    tmp_path.write_text(
        json.dumps(normalized, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    tmp_path.replace(path)
    return path


def _assigned_profiles(profiles_root: Path | str) -> List[Dict[str, Any]]:
    """扫描已落盘的画像（用于占用校验）。只读，不写。"""
    root = Path(profiles_root)
    found: List[Dict[str, Any]] = []
    if not root.exists():
        return found
    for platform_dir in sorted(root.iterdir()):
        if not platform_dir.is_dir():
            continue
        for account_dir in sorted(platform_dir.iterdir()):
            if not account_dir.is_dir():
                continue
            payload = read_device_profile(account_dir)
            if payload:
                found.append(payload)
    return found


def assign_device_profile(
    profiles_root: Path | str,
    profile_dir: Path | str,
    *,
    platform: str,
    account_id: str,
    max_slots: int = 64,
) -> Tuple[Path, Dict[str, Any]]:
    """给账号**分配**一套画像（已分配则复用，否则新建）。

    占用校验
    --------
    画像是"一个槽位"的产物。若目标槽位已被**别的账号**占用（画像内容完全相同），
    则顺延到下一个槽位 ⇒ 账号变多也不撞。

    Returns:
        ``(画像文件路径, 画像 payload)``
    """
    existing = read_device_profile(profile_dir)
    if existing:
        return device_profile_path(profile_dir), existing

    target = Path(profile_dir)
    assigned = _assigned_profiles(profiles_root)

    for slot in range(max_slots):
        candidate = build_device_profile(account_id, platform=platform, slot=slot)
        signature = _profile_signature(candidate)
        taken = any(
            _profile_signature(item) == signature
            and str(item.get("account_id") or "") != str(account_id or "")
            for item in assigned
        )
        if not taken:
            path = write_device_profile(target, candidate)
            return path, candidate

    # 全部槽位都被占满（账号数远超槽位）⇒ 退回确定性槽位 0 并记 WARN
    candidate = build_device_profile(account_id, platform=platform, slot=0)
    path = write_device_profile(target, candidate)
    return path, candidate


def _profile_signature(payload: Dict[str, Any]) -> str:
    device = (payload or {}).get("device") or {}
    parts = [
        str(device.get("user_agent") or ""),
        str(device.get("platform_id") or ""),
        str(device.get("locale") or ""),
        str(device.get("timezone_id") or ""),
        json.dumps(device.get("viewport") or {}, sort_keys=True),
    ]
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# 注入
# ---------------------------------------------------------------------------

def device_context_options(payload: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """画像 ⇒ Playwright context options。

    只注入**能整套自洽**的字段：UA / 屏幕 / locale / 时区 / Accept-Language。
    ``device_scale_factor`` 等由 Chromium 运行时决定的字段**不注入**
    （改了会与真实渲染不一致）。
    """
    device = (payload or {}).get("device") or {}
    if not isinstance(device, dict):
        return {}

    options: Dict[str, Any] = {}

    user_agent = str(device.get("user_agent") or "").strip()
    if user_agent:
        options["user_agent"] = user_agent

    viewport = device.get("viewport")
    if isinstance(viewport, dict):
        try:
            width = int(viewport.get("width") or 0)
            height = int(viewport.get("height") or 0)
        except (TypeError, ValueError):
            width = height = 0
        if width > 0 and height > 0:
            options["viewport"] = {"width": width, "height": height}

    locale = str(device.get("locale") or "").strip()
    if locale:
        options["locale"] = locale

    timezone_id = str(device.get("timezone_id") or "").strip()
    if timezone_id:
        options["timezone_id"] = timezone_id

    accept_language = str(device.get("accept_language") or "").strip()
    if accept_language:
        options["extra_http_headers"] = {"Accept-Language": accept_language}

    return options


def device_cdp_overrides(payload: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """画像 ⇒ CDP ``Emulation.*`` 参数（供**裸 Chromium** 的巡店窗口使用）。

    巡店走的是 Chromium 子进程 + CDP，不是 Playwright context ⇒ 注入方式不同。
    返回值可直接喂给 ``Emulation.setUserAgentOverride`` 等命令。
    """
    device = (payload or {}).get("device") or {}
    if not isinstance(device, dict):
        return {}

    overrides: Dict[str, Any] = {}

    user_agent = str(device.get("user_agent") or "").strip()
    if user_agent:
        overrides["userAgent"] = user_agent

    platform_id = str(device.get("platform_id") or "").strip()
    if platform_id:
        overrides["platform"] = platform_id

    accept_language = str(device.get("accept_language") or "").strip()
    if accept_language:
        overrides["acceptLanguage"] = accept_language

    locale = str(device.get("locale") or "").strip()
    if locale:
        overrides["locale"] = locale

    timezone_id = str(device.get("timezone_id") or "").strip()
    if timezone_id:
        overrides["timezoneId"] = timezone_id

    viewport = device.get("viewport")
    if isinstance(viewport, dict):
        try:
            width = int(viewport.get("width") or 0)
            height = int(viewport.get("height") or 0)
        except (TypeError, ValueError):
            width = height = 0
        if width > 0 and height > 0:
            overrides["viewport"] = {"width": width, "height": height}

    return overrides


# ---------------------------------------------------------------------------
# 机器标识隔离
# ---------------------------------------------------------------------------

def derive_machine_id(platform: str, account_id: str) -> str:
    """按 (平台, 账号) **确定性**派生一个 machine_id。

    确定性 ⇒ 同一账号永远同一个值（不会每次启动都变），
    不同账号 ⇒ 不同值（uuid5 碰撞概率可忽略）。
    """
    return str(
        uuid.uuid5(MACHINE_ID_NAMESPACE, f"{platform}|{account_id}")
    )


def ensure_profile_machine_id(
    profile_dir: Path | str,
    *,
    platform: str,
    account_id: str,
) -> Optional[str]:
    """把 profile 的 ``machine_id`` 改写成账号专属值（幂等）。

    Chromium 的 ``machine_id`` 来自 Windows MachineGuid ⇒ **同一台机器上所有
    profile 完全相同** ⇒ 平台一眼就能把这些账号关联起来。

    实测：改写后的值会被 Chromium **持久接受**（headed / headless 均不会被
    重新生成），因此这里只写一次、之后不再动。

    Returns:
        最终的 machine_id；写不进去时返回 ``None``（不抛异常 —— 隔离是增强项，
        不该让巡店/采集因此失败）。
    """
    target = Path(profile_dir)
    local_state = target / "Local State"
    expected = derive_machine_id(platform, account_id)

    try:
        if not local_state.exists():
            return None
        payload = json.loads(local_state.read_text(encoding="utf-8", errors="replace"))
        if not isinstance(payload, dict):
            return None
    except (OSError, TypeError, ValueError):
        return None

    metrics = payload.get("user_experience_metrics")
    if not isinstance(metrics, dict):
        metrics = {}
        payload["user_experience_metrics"] = metrics

    current = str(metrics.get("machine_id") or "").strip()
    if current == expected:
        return expected

    metrics["machine_id"] = expected
    try:
        tmp_path = local_state.with_name("Local State.tmp")
        tmp_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        tmp_path.replace(local_state)
    except OSError:
        return None

    return expected
