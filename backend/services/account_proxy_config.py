"""账号级代理配置解析 —— core.shop_accounts.extra_config["proxy"]。

单一定义源：AccountLoaderService 与 ShopAccountLoaderService 共用，
避免同一套解析规则出现两份实现而漂移。

存放位置：``core.shop_accounts.extra_config`` jsonb（不加列、不写迁移）。

关于 ``proxy_region`` 的词汇表
--------------------------------
本模块产出的 ``proxy_region`` 是**自由地区标识**（例如 ``"sg"``），
取自 ``extra_config.proxy.region``，由运维按账号自行约定。

它与遗留的 ``AccountConfig.proxy_region``（``modules/core/config_schemas.py``）
**不是同一套词汇表**：遗留那个用的是"地区池 key"词汇表
（``config/proxy_config.py`` 里的 ``"china"`` / ``"singapore"`` / ``"malaysia"`` …），
并受"需要代理时必须指定代理地区"的校验约束。

本模块刻意不做该校验：账号自有代理是显式配置，不应被遗留地区池的枚举卡住。
两个字段同名不同义，引用时务必看清来源。

兜底范围（重要）
----------------
本模块里**只有** ``extract_proxy_config`` 承诺"任何异常输入都安全兜底、不抛异常"。
loader 层（``AccountLoaderService._build_account_dict`` /
``ShopAccountLoaderService._build_payload``）不承诺这一点：它们在解析代理之前
就会访问 legacy 字段，属性缺失会先抛 ``AttributeError``。
"""

from typing import Any, Dict, Mapping, Optional

from modules.core.logger import get_logger

logger = get_logger(__name__)

_FALSEY_FLAG_STRINGS = {"", "false", "0", "no", "off"}

# 本仓约定：代理串必须带 scheme（见 modules/utils/proxy_config_manager.py:61）
_DEFAULT_PROXY_SCHEME = "http"


def _parse_enabled_flag(value: Any) -> bool:
    """解析 enabled 标志，显式处理字符串真值陷阱（bool("false") is True）。"""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() not in _FALSEY_FLAG_STRINGS
    if isinstance(value, (int, float)):
        return bool(value)
    return False


def _normalize_text(value: Any) -> str:
    """只接受字符串/数字；其它类型（dict/list/bool）一律丢弃，避免产出 Python repr。"""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return str(value)
    return ""


def extract_proxy_config(extra_config: Optional[Mapping[str, Any]]) -> Dict[str, Any]:
    """从 extra_config 解析出平铺的代理配置；任何异常输入都安全兜底，不抛异常。

    输入可以是 None、缺字段、``proxy`` 不是 dict、``enabled`` 是字符串
    （``"false"`` 视为未启用）、``server`` 是非标量 —— 一律不抛异常。

    ``proxy_region`` 是**自由地区标识**（例如 ``"sg"``），与遗留地区池 key
    词汇表（``"china"`` / ``"singapore"``）**不是同一套**，详见模块 docstring。

    凭据有两种形态，都会被透出（``proxy_username`` / ``proxy_password``）：
    内嵌在 URL 里的 ``user:pass``，以及独立的 ``proxy.username`` / ``proxy.password``。
    """
    data = extra_config if isinstance(extra_config, Mapping) else {}
    raw = data.get("proxy")
    if not isinstance(raw, Mapping):
        raw = {}
    return {
        "proxy_enabled": _parse_enabled_flag(raw.get("enabled")),
        "proxy_server": _normalize_text(raw.get("server")),
        "proxy_region": _normalize_text(raw.get("region")),
        "proxy_username": _normalize_text(raw.get("username")),
        "proxy_password": _normalize_text(raw.get("password")),
    }


def _normalize_proxy_server(proxy_server: str) -> str:
    """补齐 scheme：本仓约定代理串必须带 scheme。

    Playwright 的 python 绑定不校验 ``proxy["server"]``，畸形值只会在导航期报
    ``ERR_PROXY_CONNECTION_FAILED``，看不出是配置写错 —— 所以缺 scheme 必须在这里补。
    """
    raw = (proxy_server or "").strip()
    if not raw:
        return ""
    if "://" in raw:
        return raw
    return f"{_DEFAULT_PROXY_SCHEME}://{raw}"


def split_proxy_credentials(proxy_server: str) -> Dict[str, str]:
    """http://user:pass@host:port -> Playwright 的 server/username/password。

    两种凭据形态在这里只认「内嵌在 URL 里的 user:pass」；独立的
    ``proxy.username`` / ``proxy.password`` 由 :func:`resolve_account_proxy` 叠加。

    缺 scheme 的输入会被归一成 ``http://``（见 :func:`_normalize_proxy_server`）。
    """
    raw = (proxy_server or "").strip()
    if not raw:
        return {}
    scheme, sep, rest = raw.partition("://")
    if not sep:
        scheme, rest = "", raw
    userinfo, at, host_part = rest.rpartition("@")
    if not at:
        return {"server": _normalize_proxy_server(raw)}
    username, _, password = userinfo.partition(":")
    host_with_scheme = f"{scheme}://{host_part}" if scheme else host_part
    return {
        "server": _normalize_proxy_server(host_with_scheme),
        "username": username,
        "password": password,
    }


def mask_proxy_server(
    proxy_server: str,
    username: str = "",
    password: str = "",
) -> str:
    """诊断字段用：只留 scheme+host，抹掉凭据（规范 §8 要求脱敏）。

    凭据有两种形态：内嵌在 URL 里的 ``user:pass``、以及独立的
    ``username`` / ``password``。两种形态都不得出现在诊断字段里，
    所以独立形态的凭据也在这里一并抹掉。
    """
    masked = split_proxy_credentials(proxy_server).get("server", "")
    for secret in (username, password):
        text = str(secret or "").strip()
        if text:
            masked = masked.replace(text, "***")
    return masked


def resolve_account_proxy(account: Optional[Mapping[str, Any]]) -> Optional[Dict[str, str]]:
    """P1/P3/C1/C2/C3/C4：账号级代理 -> Playwright 代理参数。

    规则：

    - **账号自有 ``proxy_server`` 优先**；账号没有可用自有代理时返回 ``None``。
    - **绝不**回退到遗留地区池链路（``proxy_config_manager.get_playwright_proxy_config``）：
      那条链路只按 account_id + 地区池选代理，不读账号自有的 server，
      与自有代理同时生效就是「一账号两个 IP」，直接违反 P1/P2。
    - **绝不**走遗留链路的 ``fallback_to_direct``（``config/proxy_config.py:221``）：
      代理失败静默回退直连会让账号从宿主 IP 出现，IP 隔离形同虚设。
      自有代理场景下代理不可用必须**显式失败**（浏览器导航报错、任务失败），
      不得直连。新链路不经过那条静默回退。
    - 返回 Playwright 形态：``{"server": ..., "username": ..., "password": ...}``。
    """
    data = account if isinstance(account, Mapping) else {}
    server = _normalize_text(data.get("proxy_server"))
    if not server or not _parse_enabled_flag(data.get("proxy_enabled")):
        return None

    proxy = split_proxy_credentials(server)

    # 独立的 username/password 形态优先；没有才用 URL 内嵌凭据。
    username = _normalize_text(data.get("proxy_username"))
    password = _normalize_text(data.get("proxy_password"))
    if username:
        proxy["username"] = username
    if password:
        proxy["password"] = password

    logger.info(
        "账号级代理已解析: account_id=%s proxy=%s",
        _normalize_text(data.get("account_id"))
        or _normalize_text(data.get("main_account_id")),
        mask_proxy_server(server, username=username, password=password),
    )
    return proxy
