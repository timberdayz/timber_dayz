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
"""

from typing import Any, Dict, Mapping, Optional

_FALSEY_FLAG_STRINGS = {"", "false", "0", "no", "off"}


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
    """
    data = extra_config if isinstance(extra_config, Mapping) else {}
    raw = data.get("proxy")
    if not isinstance(raw, Mapping):
        raw = {}
    return {
        "proxy_enabled": _parse_enabled_flag(raw.get("enabled")),
        "proxy_server": _normalize_text(raw.get("server")),
        "proxy_region": _normalize_text(raw.get("region")),
    }


def split_proxy_credentials(proxy_server: str) -> Dict[str, str]:
    """http://user:pass@host:port -> Playwright 的 server/username/password。

    Playwright 完全不校验 proxy["server"] 的形态，畸形值只会在导航期报
    ERR_PROXY_CONNECTION_FAILED，看不出是配置写错 —— 所以必须在这里就拆干净。
    """
    raw = (proxy_server or "").strip()
    if not raw:
        return {}
    scheme, sep, rest = raw.partition("://")
    if not sep:
        scheme, rest = "", raw
    userinfo, at, host_part = rest.rpartition("@")
    if not at:
        return {"server": raw}
    username, _, password = userinfo.partition(":")
    return {
        "server": f"{scheme}://{host_part}" if scheme else host_part,
        "username": username,
        "password": password,
    }


def mask_proxy_server(proxy_server: str) -> str:
    """诊断字段用：只留 scheme+host，抹掉凭据（规范 §8 要求脱敏）。"""
    return split_proxy_credentials(proxy_server).get("server", "")
