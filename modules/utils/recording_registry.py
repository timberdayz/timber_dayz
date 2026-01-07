"""
Recording Registry
==================

目的
- 为各平台/账号的录制脚本提供标准化索引与检索
- 规范“自动登录 + 自动采集(订单/商品/分析/财务)”的文件命名与目录结构
- 在不改动历史录制文件的前提下，通过扫描与索引做到向后兼容

核心能力
- 约定数据类型 RecordingType: orders, products, analytics, finance
- 从 temp/recordings/<platform>/ 扫描历史脚本并建立索引
- 始终返回“该账号的最新可用脚本”（可配“金标/稳定版”）
- 将索引持久化到 data/recordings/registry.json

注意
- 不删除任何历史文件；索引仅做映射
- 索引更新为幂等操作，可随时 reindex()
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from modules.utils.logger import get_logger

logger = get_logger(__name__)


REGISTRY_FILE = Path("data/recordings/registry.json")
RECORDINGS_ROOT = Path("temp/recordings")


class RecordingType(str, Enum):
    ORDERS = "orders"
    PRODUCTS = "products"
    ANALYTICS = "analytics"
    FINANCE = "finance"
    SERVICES = "services"


@dataclass
class RecordingEntry:
    platform: str
    account: str
    kind: str  # "login" or "collection"
    data_type: Optional[RecordingType]
    path: str  # 相对路径字符串
    timestamp: str  # 20250829_174710
    stable: bool = False  # 是否标记为“金标/稳定版”


def _safe_slug(name: str) -> str:
    """将账号名转换为文件系统友好的 slug。"""
    slug = re.sub(r"[^0-9A-Za-z\u4e00-\u9fa5_\-]+", "_", name).strip("_")
    return slug or "account"


def _platform_dir(platform: str) -> Path:
    return RECORDINGS_ROOT / platform


def _load_registry() -> Dict:
    try:
        if REGISTRY_FILE.exists():
            return json.loads(REGISTRY_FILE.read_text(encoding="utf-8"))
    except Exception as e:
        logger.warning(f"加载录制索引失败，将重建: {e}")
    return {"platforms": {}}


def _save_registry(registry: Dict) -> None:
    REGISTRY_FILE.parent.mkdir(parents=True, exist_ok=True)
    REGISTRY_FILE.write_text(json.dumps(registry, ensure_ascii=False, indent=2),
                             encoding="utf-8")


def _ensure_platform(registry: Dict, platform: str) -> Dict:
    platforms = registry.setdefault("platforms", {})
    return platforms.setdefault(platform, {"accounts": {}})


def _ensure_account(node: Dict, account: str) -> Dict:
    accounts = node.setdefault("accounts", {})
    return accounts.setdefault(account, {
        "login": {"latest": None, "stable": None},
        "collections": {
            "orders": {"latest": None, "stable": None},
            "products": {"latest": None, "stable": None},
            "analytics": {"latest": None, "stable": None},
            "finance": {"latest": None, "stable": None},
            "services": {"latest": None, "stable": None},
        },
    })


LOGIN_PATTERNS = [
    re.compile(r"(?P<account>.+?)_login_auto_(?P<ts>\d{8}_\d{6})\.py$"),
    re.compile(r"(?P<account>.+?)_login_(?P<ts>\d{8}_\d{6})\.py$"),
]

COLLECT_PATTERNS = [
    # e.g. shopee_KR_collection_orders_20250829_181053.py
    re.compile(
        r"(?P<account>.+?)_collection_(?P<dtype>orders|products|analytics|finance|services)_(?P<ts>\d{8}_\d{6})\.py$"
    ),
    # e.g. TestStore_complete_products_20250826_164858.py (兼容历史 "complete_*" 命名)
    re.compile(
        r"(?P<account>.+?)_complete_(?P<dtype>orders|products|analytics|finance|services)_(?P<ts>\d{8}_\d{6})\.py$"
    ),
    # e.g. shopee_TestStore_products_complete_20250830_120000.py （新命名规范：{平台}_{账号}_{数据类型}_complete_{时间戳}.py）
    re.compile(
        r"(?P<platform>[a-zA-Z]+)_(?P<account>.+?)_(?P<dtype>orders|products|analytics|finance|services)_complete_(?P<ts>\d{8}_\d{6})\.py$"
    ),
]


def reindex(platform: str) -> Dict:
    """从磁盘扫描 platform 录制脚本，更新索引并保存。

    返回该平台的索引节点(字典)。
    """
    platform = platform.lower()
    registry = _load_registry()
    pnode = _ensure_platform(registry, platform)

    root = _platform_dir(platform)
    if not root.exists():
        logger.info(f"录制目录不存在，创建: {root}")
        root.mkdir(parents=True, exist_ok=True)
        _save_registry(registry)
        return pnode

    # 遍历两级以内文件
    all_files = [
        p for p in root.rglob("*.py") if p.is_file()
    ]

    for f in all_files:
        name = f.name
        matched = False

        # 登录脚本
        for pat in LOGIN_PATTERNS:
            m = pat.match(name)
            if m:
                matched = True
                account = m.group("account")
                ts = m.group("ts")
                anode = _ensure_account(pnode, account)
                current = anode["login"].get("latest")
                if not current or ts > current.get("timestamp", ""):
                    anode["login"]["latest"] = {
                        "path": str(f.as_posix()), "timestamp": ts
                    }
                break

        if matched:
            continue

        # 采集脚本
        for pat in COLLECT_PATTERNS:
            m = pat.match(name)
            if m:
                matched = True
                account = m.group("account")
                dtype = m.group("dtype")
                ts = m.group("ts")
                anode = _ensure_account(pnode, account)
                # 兼容历史 registry.json 可能缺少某些 dtype 键的情况
                cnode = _ensure_dtype_node(anode, dtype)
                current = cnode.get("latest")
                if not current or ts > current.get("timestamp", ""):
                    cnode["latest"] = {
                        "path": str(f.as_posix()), "timestamp": ts
                    }
                break

    _save_registry(registry)
    return pnode


def get_latest_login(platform: str, account: str) -> Optional[str]:
    registry = _load_registry()
    pnode = registry.get("platforms", {}).get(platform.lower(), {})
    anode = pnode.get("accounts", {}).get(account)
    if not anode:
        # 尝试 reindex
        pnode = reindex(platform)
        anode = pnode.get("accounts", {}).get(account)
    if not anode:
        return None
    node = anode["login"]["stable"] or anode["login"]["latest"]
    return node and node.get("path")


def _ensure_dtype_node(anode: Dict, dtype_value: str) -> Dict:
    """确保账号节点下的某个数据类型子节点存在。"""
    collections = anode.setdefault("collections", {})
    return collections.setdefault(dtype_value, {"latest": None, "stable": None})


def get_latest_collection(platform: str, account: str,
                           dtype: RecordingType) -> Optional[str]:
    registry = _load_registry()
    pnode = registry.get("platforms", {}).get(platform.lower(), {})
    anode = pnode.get("accounts", {}).get(account)
    if not anode:
        pnode = reindex(platform)
        anode = pnode.get("accounts", {}).get(account)
    if not anode:
        return None
    cnode = _ensure_dtype_node(anode, dtype.value)
    node = cnode["stable"] or cnode["latest"]
    return node and node.get("path")


def get_stable_collection(platform: str, account: str,
                           dtype: RecordingType) -> Optional[str]:
    """仅返回稳定版脚本路径（无则返回None）"""
    registry = _load_registry()
    pnode = registry.get("platforms", {}).get(platform.lower(), {})
    anode = pnode.get("accounts", {}).get(account)
    if not anode:
        pnode = reindex(platform)
        anode = pnode.get("accounts", {}).get(account)
    if not anode:
        return None
    cnode = _ensure_dtype_node(anode, dtype.value)
    node = cnode.get("stable")
    return node and node.get("path")


def mark_stable(platform: str, account: str, kind: str,
                dtype: Optional[RecordingType], path: str) -> None:
    """将某脚本标记为稳定版(stable)。"""
    registry = _load_registry()
    pnode = _ensure_platform(registry, platform.lower())
    anode = _ensure_account(pnode, account)
    if kind == "login":
        anode["login"]["stable"] = {"path": path, "timestamp": _extract_ts(path)}
    else:
        cnode = _ensure_dtype_node(anode, dtype.value)
        cnode["stable"] = {"path": path, "timestamp": _extract_ts(path)}
    _save_registry(registry)


def clear_stable(platform: str, account: str, kind: str,
                 dtype: Optional[RecordingType]) -> None:
    """清除某类脚本的稳定版标记。"""
    registry = _load_registry()
    pnode = _ensure_platform(registry, platform.lower())
    anode = _ensure_account(pnode, account)
    if kind == "login":
        anode["login"]["stable"] = None
    else:
        cnode = _ensure_dtype_node(anode, dtype.value)
        cnode["stable"] = None
    _save_registry(registry)


def _extract_ts(path: str) -> str:
    m = re.search(r"(\d{8}_\d{6})", path)
    return m.group(1) if m else ""


def plan_flow(platform: str, account: str,
              dtype: RecordingType) -> Tuple[Optional[str], Optional[str]]:
    """返回“自动登录 + 指定数据类型采集”的脚本路径组合。"""
    login = get_latest_login(platform, account)
    collect = get_latest_collection(platform, account, dtype)
    return login, collect


def ensure_index(platform: str) -> None:
    """对平台录制目录进行索引更新（幂等）。"""
    reindex(platform)


__all__ = [
    "RecordingType",
    "reindex",
    "get_latest_login",
    "get_latest_collection",
    "mark_stable",
    "plan_flow",
    "ensure_index",
    "get_stable_collection",
    "clear_stable",
]

