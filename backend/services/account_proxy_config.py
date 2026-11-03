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

关于凭据安全
------------
本模块保证：**代理凭据不会留在 ``server`` 字段里**（``server`` 会进日志、也会
作为 Playwright 的代理地址下发）。

- 内嵌形态（``http://user:pass@host:port``）拆成 server/username/password；
- 漏写 host 的形态（``http://user:pass``）同样按 userinfo 拆，server 只剩 scheme；
- 拆不出主机部分时 :func:`resolve_account_proxy` **显式失败**（不静默直连），
  报错信息用脱敏后的代理标识；
- 独立形态的凭据由 :func:`strip_account_proxy_credentials` 从账号 dict 里剔除，
  凭据只随 ``proxy=`` 参数下传，不随账号字典扩散进组件 config。
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


def _authority_of(raw: str) -> str:
    """取 authority 部分（去掉 userinfo，即最后一个 "@" 之前的部分）。"""
    text = (raw or "").strip()
    _scheme, sep, rest = text.partition("://")
    if not sep:
        rest = text
    _userinfo, at, host = rest.rpartition("@")
    return host if at else rest


# 裸 IPv6 字面量（"::1:8080"）的合法字符集：十六进制数字、冒号、点
_IPV6_LITERAL_CHARS = frozenset("0123456789abcdefABCDEF:.")


def _looks_like_bare_ipv6(text: str) -> bool:
    """裸 IPv6 字面量（``::1:8080``）不是 userinfo。

    括号形式（``[::1]:8080``）由调用方先排除；这里只认**裸**写法：
    含 ``::`` 且整串只由十六进制数字、冒号、点组成。

    含字母的形态（例如 ``user::pass``）仍然是 userinfo —— 那种串拆不出主机，
    凭据必须从 server 里剥掉，否则明文密码会进日志、也会被当成代理地址下发。
    """
    if "::" not in text:
        return False
    return all(ch in _IPV6_LITERAL_CHARS for ch in text)


def _looks_like_userinfo(authority: str) -> bool:
    """authority 形如 ``user:pass``（漏写 host）时必须按 userinfo 处理。

    判定规则：

    - IPv6 字面量（``[::1]:8080``、裸 ``::1:8080``）不是 userinfo；
    - 路径段不参与判定：``host:8080/path`` 的端口位是 ``8080``（不是 ``8080/path``）；
    - 端口位是纯数字时是正常的 ``host:port``；
    - 端口位为空（``h:``）也是 ``host`` 形态 —— 主机还在，缺的是端口；
    - 其余带 ``:`` 的形态（端口位不是数字、或有多个 ``:``）都按 userinfo 处理 ——
      这种串拆不出可用主机，凭据必须从 server 里剥掉，否则明文密码会进日志、
      也会被当成代理地址下发。
    """
    text = (authority or "").strip()
    if not text or ":" not in text:
        return False
    if text.startswith("["):
        return False
    # 路径段（"host:8080/path"）不参与 userinfo 判定；整串以 "/" 开头时保持原样。
    text = text.split("/", 1)[0] or text
    if _looks_like_bare_ipv6(text):
        return False
    if text.count(":") > 1:
        return True
    _host, _sep, port = text.rpartition(":")
    if not port:
        # 空端口（"h:"）：主机还在，缺的是端口 —— 不是 userinfo
        return False
    return not port.isdigit()


def split_proxy_credentials(proxy_server: str) -> Dict[str, str]:
    """http://user:pass@host:port -> Playwright 的 server/username/password。

    两种凭据形态在这里只认「内嵌在 URL 里的 user:pass」；独立的
    ``proxy.username`` / ``proxy.password`` 由 :func:`resolve_account_proxy` 叠加。

    - 缺 scheme 的输入会被归一成 ``http://``（见 :func:`_normalize_proxy_server`）；
    - 缺 host 的 ``user:pass`` 形态（没有 ``@``）同样按 userinfo 拆开，
      **凭据绝不会留在 server 里**（否则明文密码会进日志、也会被当成代理地址下发）。
    """
    raw = (proxy_server or "").strip()
    if not raw:
        return {}
    scheme, sep, rest = raw.partition("://")
    if not sep:
        scheme, rest = "", raw
    userinfo, at, host_part = rest.rpartition("@")
    if at:
        username, _, password = userinfo.partition(":")
        host_with_scheme = f"{scheme}://{host_part}" if scheme else host_part
        split = {"server": _normalize_proxy_server(host_with_scheme)}
        # 空 userinfo（"http://@h:8080"）不产出空的 username/password 键：
        # 空凭据键带给 Playwright 会被当成"有用户名无密码"，代理直接 407。
        if username:
            split["username"] = username
        if password:
            split["password"] = password
        return split
    if _looks_like_userinfo(host_part):
        # 形如 "http://user:pass"（漏写 host）：按 userinfo 拆，凭据从 server 里剥掉
        username, _, password = host_part.partition(":")
        return {
            "server": _normalize_proxy_server(f"{scheme}://" if scheme else ""),
            "username": username,
            "password": password,
        }
    return {"server": _normalize_proxy_server(raw)}


def mask_proxy_server(
    proxy_server: str,
    username: str = "",
    password: str = "",
) -> str:
    """诊断字段用：只留 scheme+host，抹掉凭据（规范 §8 要求脱敏）。

    凭据有两种形态：内嵌在 URL 里的 ``user:pass``、以及独立的
    ``username`` / ``password``。独立形态的凭据本来就不在 server 字符串里，
    所以这里**不做任何字符串替换**（早期实现用 replace 会误伤 host 段/端口/scheme）。
    ``username`` / ``password`` 形参保留给调用方显式声明"这里有凭据"，
    结果里不会出现它们。
    """
    raw = (proxy_server or "").strip()
    if _looks_like_userinfo(_authority_of(raw)):
        # 兜底：authority 形如 user:pass（缺 host），拆不出可用 server —— 整体脱敏
        scheme, sep, _ = raw.partition("://")
        return f"{scheme}://***" if sep else "***"
    return split_proxy_credentials(raw).get("server", "")


def _proxy_server_has_host(server: str) -> bool:
    """server 里是否真有主机部分（只有 scheme 不算）。"""
    text = (server or "").strip()
    _scheme, sep, netloc = text.partition("://")
    host_part = netloc if sep else text
    if host_part.startswith("["):
        return bool(host_part[1:].split("]")[0].strip())
    if _looks_like_bare_ipv6(host_part):
        # 裸 IPv6（"::1:8080"）：主机是在的，只是没写括号 —— 不该报"缺少代理主机"
        return True
    return bool(host_part.split(":")[0].strip())


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
    - 代理串拆不出主机部分（例如漏写 host 的 ``http://user:pass``）时**抛 ValueError**：
      配置坏了必须显式失败，不能退回"没配代理"（那等于静默直连）。
    - 返回 Playwright 形态：``{"server": ..., "username": ..., "password": ...}``。
    """
    data = account if isinstance(account, Mapping) else {}
    server = _normalize_text(data.get("proxy_server"))
    if not server or not _parse_enabled_flag(data.get("proxy_enabled")):
        return None

    proxy = split_proxy_credentials(server)
    account_label = (
        _normalize_text(data.get("account_id"))
        or _normalize_text(data.get("main_account_id"))
    )
    if not proxy.get("server") or not _proxy_server_has_host(proxy["server"]):
        # 配置坏了（例如漏写 host 的 http://user:pass）：显式失败，绝不静默直连（C2）。
        # 报错信息用脱敏后的代理标识，不能带明文凭据。
        raise ValueError(
            f"账号代理配置无效（缺少代理主机）: {mask_proxy_server(server)}"
            f" account_id={account_label}"
        )

    # 独立的 username/password 形态优先；没有才用 URL 内嵌凭据。
    username = _normalize_text(data.get("proxy_username"))
    password = _normalize_text(data.get("proxy_password"))
    if username:
        proxy["username"] = username
    if password:
        proxy["password"] = password

    logger.debug(
        "账号级代理已解析: account_id=%s proxy=%s",
        account_label,
        mask_proxy_server(server, username=username, password=password),
    )
    return proxy


def strip_account_proxy_credentials(
    account: Optional[Mapping[str, Any]],
) -> Dict[str, Any]:
    """P0-4：把账号 dict 里的代理凭据剔除（组件 config 不能带明文密码）。

    组件 config（``params["account"]``）会整体扩散给组件，也可能进日志或落盘；
    代理凭据只应随 ``proxy=`` 参数下传，不该跟着账号字典走。

    - 独立的 ``proxy_username`` / ``proxy_password`` 直接删掉；
    - ``proxy_server`` 里内嵌的 ``user:pass`` 也被剥掉，只留 scheme+host。

    返回**新字典**，不改调用方手里的原对象（调用方还要用它解析代理）。
    """
    data = dict(account or {})
    data.pop("proxy_username", None)
    data.pop("proxy_password", None)
    server = _normalize_text(data.get("proxy_server"))
    if server:
        split = split_proxy_credentials(server)
        if split.get("server") and _proxy_server_has_host(split["server"]):
            data["proxy_server"] = split["server"]
        else:
            # 畸形串（拆不出主机，例如 "user:pass" / "http://user:pass"）：宁可丢掉这个键，
            # 也不能把明文凭据或垃圾代理地址（"http://"）留在组件 config 里。
            data.pop("proxy_server", None)
    return data

