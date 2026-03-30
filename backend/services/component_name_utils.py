"""
组件名称标准化工具 (optimize-component-version-management)

按 (platform, component_type) 约束逻辑组件唯一性;
component_name 格式: {platform}/{component_type} 或 {platform}/{domain}_export
"""

from typing import Optional, Tuple, List

# 有子类型的数据域
DATA_DOMAIN_SUB_TYPES = {
    "orders": ["shopee", "tiktok"],
    "services": ["agent", "ai_assistant"],
}


def build_component_name(
    platform: str,
    component_type: str,
    data_domain: Optional[str] = None,
    sub_domain: Optional[str] = None,
) -> str:
    """
    由 platform + component_type 推导 component_name。

    - login/navigation/shop_switch/date_picker/filters: {platform}/{component_type}
    - export: {platform}/{domain}_export 或 {platform}/{domain}_{sub}_export
    """
    platform = (platform or "").strip()
    component_type = (component_type or "").strip()
    if not platform or not component_type:
        raise ValueError("platform and component_type are required")

    if component_type == "export":
        if not data_domain:
            raise ValueError("export component requires data_domain")
        data_domain = data_domain.strip()
        if sub_domain:
            sub = sub_domain.strip()
            return f"{platform}/{data_domain}_{sub}_export"
        return f"{platform}/{data_domain}_export"

    return f"{platform}/{component_type}"


def parse_component_name(component_name: str) -> Tuple[Optional[str], Optional[str], Optional[str], Optional[str]]:
    """
    从 component_name 解析 platform, component_type, data_domain, sub_domain。
    用于列表筛选、冲突检测、按平台分组。
    """
    if not component_name or "/" not in component_name:
        return None, None, None, None

    platform, rest = component_name.split("/", 1)
    platform = platform.strip() or None
    rest = rest.strip() or None
    if not platform or not rest:
        return platform, None, None, None

    if rest.endswith("_export"):
        base = rest[:-7]
        if "_" in base:
            parts = base.split("_")
            domain = parts[0] if parts else None
            sub = "_".join(parts[1:]) if len(parts) > 1 else None
            return platform, "export", domain, sub
        return platform, "export", base, None

    type_map = {
        "login": "login",
        "navigation": "navigation",
        "shop_switch": "shop_switch",
        "date_picker": "date_picker",
        "filters": "filters",
    }
    return platform, type_map.get(rest, rest), None, None


def is_standard_component_name(component_name: str) -> bool:
    """校验 component_name 是否符合标准化规则"""
    platform, comp_type, domain, sub = parse_component_name(component_name)
    if not platform or not comp_type:
        return False
    try:
        built = build_component_name(
            platform=platform,
            component_type=comp_type,
            data_domain=domain,
            sub_domain=sub,
        )
        return built == component_name
    except ValueError:
        return False


def parse_semver(version: str) -> Tuple[int, int, int]:
    """解析语义版本号，返回 (major, minor, patch)"""
    parts = version.strip().split(".")
    major = int(parts[0]) if len(parts) > 0 and parts[0].isdigit() else 0
    minor = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0
    patch = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 0
    return (major, minor, patch)


def next_patch_version(versions: List[str]) -> str:
    """
    在应用层解析版本号，取最大 (major, minor, patch) 后 patch+1。
    不得依赖 SQL MAX(version) 字典序（否则 1.0.9 > 1.0.10）。
    """
    if not versions:
        return "1.0.0"
    max_ver = max(versions, key=lambda v: parse_semver(v))
    major, minor, patch = parse_semver(max_ver)
    return f"{major}.{minor}.{patch + 1}"


def version_to_filename_suffix(version: str) -> str:
    """版本号转为文件名安全格式：1.1.0 -> v1_1_0"""
    return "v" + version.replace(".", "_")


def parse_filename_to_component_and_version(
    filename: str, platform: str
) -> Tuple[Optional[str], str]:
    """
    从文件名解析 component_name 与 version。
    - login_v1_1_0.py -> (platform/login, 1.1.0)
    - orders_export_v1_0_0.py -> (platform/orders_export, 1.0.0)
    - services_agent_export_v1_0_0.py -> (platform/services_agent_export, 1.0.0)
    - login.py -> (platform/login, 1.0.0)
    """
    if not filename.endswith(".py"):
        return None, "1.0.0"
    stem = filename[:-3]
    if "_v" in stem and stem[-1].isdigit():
        idx = stem.rfind("_v")
        base = stem[:idx]
        ver_part = stem[idx + 2 :].replace("_", ".")
        try:
            parts = ver_part.split(".")
            if len(parts) >= 3:
                version = f"{int(parts[0])}.{int(parts[1])}.{int(parts[2])}"
            else:
                version = "1.0.0"
        except (ValueError, IndexError):
            version = "1.0.0"
    else:
        base = stem
        version = "1.0.0"

    if not base:
        return None, version
    comp_name = f"{platform}/{base}"
    return comp_name, version
