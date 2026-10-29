"""模板契约服务 (SSOT)

背景
----
采集落库时, ``catalog_files`` 只记录了「文件是谁」的业务元数据(店铺归属、
采集信息), **没有记录「这个文件是按哪一版模板解释的」**。

后果(这是模板漂移误报的根本来源):

* 表头比对只能拿「当前最新已发布模板」当唯一基准
* 我们自己把模板从 v5 升到 v6, 历史上按 v5 采集的文件全被判定成「结构漂移」
* 系统无法区分「**源文件**结构变了」与「**我们自己**升级了模板」

本模块负责模板契约的读写, 契约落在
``catalog_files.file_metadata['template_contract']``。

契约字段
--------
==================  ==========================================================
``template_id``     采集当时生效的模板行 ID (``core.field_mapping_templates.id``)
``template_version``采集当时的模板版本号
``header_row``      采集当时的表头行索引(0-based)
``columns_hash``    模板表头列指纹(sha256), 用于校验模板行事后是否被改动
``column_count``    模板表头列数量
``captured_at``     契约采集时刻(UTC ISO8601)
``source``          契约来源, 例如 ``collection_registration``
==================  ==========================================================

设计约定
--------
* 契约只引用模板行, **不复制表头列** —— 模板行本身是版本化留存的,
  归档后的模板仍然可以按 ``template_id`` 读回, 不必在每个文件上冗余一份列清单。
* ``columns_hash`` 是**完整性校验位**: 模板行如果事后被原地改写,
  指纹就对不上, 调用方据此判定「契约基准已失效」并回退到当前已发布模板。
* 契约缺失是**正常状态**(历史文件), 调用方必须支持「无契约」回退路径。
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional

from sqlalchemy import select

from modules.core.db import FieldMappingTemplate

# file_metadata 中存放模板契约的顶层键
TEMPLATE_CONTRACT_KEY = "template_contract"

# 契约来源: 采集落库登记
CONTRACT_SOURCE_COLLECTION = "collection_registration"

# 契约来源: 跨 family 变体接管回填
# 文件本身所属粒度没有匹配变体, 由**其他粒度**的变体解释 ——
# 契约里除了模板引用, 还要留痕「是被谁接管的」。
CONTRACT_SOURCE_TAKEOVER = "cross_family_variant_takeover"

# 契约来源: 契约晋升(模板升级后回写)
#
# 场景: 文件在采集当时就与当时的模板对不上(源文件结构先变了), 于是契约钉在
# 旧模板上。用户随后把新字段补进模板并发布新版本 —— 新版本能解释这个文件,
# 但契约仍指向旧模板, 于是判定永远停在「结构漂移」, 文件永远进不了入库队列。
#
# 契约晋升把契约改写成「当前能解释这个文件的那一版模板」, 让基准重新稳定。
CONTRACT_SOURCE_PROMOTION = "contract_promotion"

# columns_hash 的格式版本, 便于将来更换归一化策略时区分指纹
_COLUMNS_HASH_VERSION = "v1"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_columns(columns: Optional[Iterable[Any]]) -> List[str]:
    """列名归一化: 只做去空白, 不改变大小写与顺序。

    顺序必须保留 —— ``detect_header_changes`` 的「精确匹配」要求字段名与
    顺序都一致, 因此指纹也必须是顺序敏感的。
    """
    if not columns:
        return []
    normalized: List[str] = []
    for column in columns:
        if column is None:
            continue
        normalized.append(str(column).strip())
    return normalized


def compute_columns_hash(columns: Optional[Iterable[Any]]) -> str:
    """计算表头列指纹(顺序敏感)。"""
    payload = "\x1f".join(normalize_columns(columns))
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return f"{_COLUMNS_HASH_VERSION}:{digest}"


def build_template_contract(
    template: Any,
    *,
    source: str = CONTRACT_SOURCE_COLLECTION,
    captured_at: Optional[str] = None,
    takeover: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """把一个模板整理成可持久化的模板契约。

    ``template`` 可以是 ORM 对象, 也可以是任何带同名属性的对象。

    ``takeover`` 非空时, 契约里会额外留痕「这份契约来自跨 family 变体接管」:
    接管来源(哪个 family 的哪个变体)、匹配率、缺失列 —— 便于事后回答
    「这个文件当年是被谁接管的」。
    """
    if template is None:
        return {}

    header_columns = getattr(template, "header_columns", None) or []
    normalized = normalize_columns(header_columns)
    contract = {
        "template_id": getattr(template, "id", None),
        "template_version": getattr(template, "version", None),
        "template_status": getattr(template, "status", None),
        "template_name": getattr(template, "template_name", None),
        "header_row": getattr(template, "header_row", None),
        "columns_hash": compute_columns_hash(normalized),
        "column_count": len(normalized),
        "captured_at": captured_at or _utc_now_iso(),
        "source": source,
    }
    if isinstance(takeover, dict) and takeover:
        contract["takeover"] = dict(takeover)
    return contract


def read_template_contract(catalog_file: Any) -> Optional[Dict[str, Any]]:
    """读取文件上已保存的模板契约; 没有或格式不对返回 None。"""
    if catalog_file is None:
        return None
    metadata = getattr(catalog_file, "file_metadata", None) or {}
    if not isinstance(metadata, dict):
        return None
    contract = metadata.get(TEMPLATE_CONTRACT_KEY)
    if not isinstance(contract, dict):
        return None
    if contract.get("template_id") is None:
        return None
    return contract


def write_template_contract(catalog_file: Any, contract: Dict[str, Any]) -> Dict[str, Any]:
    """把模板契约写入 ``file_metadata``(不落盘, 由调用方决定 commit 时机)。"""
    if catalog_file is None or not contract:
        return {}
    metadata = getattr(catalog_file, "file_metadata", None)
    metadata = dict(metadata) if isinstance(metadata, dict) else {}
    metadata[TEMPLATE_CONTRACT_KEY] = contract
    catalog_file.file_metadata = metadata
    return contract


def contract_template_id(contract: Optional[Dict[str, Any]]) -> Optional[int]:
    """取出契约指向的模板行 ID。"""
    if not isinstance(contract, dict):
        return None
    try:
        template_id = contract.get("template_id")
    except AttributeError:
        return None
    if template_id is None:
        return None
    try:
        return int(template_id)
    except (TypeError, ValueError):
        return None


def parse_contract_captured_at(
    contract: Optional[Dict[str, Any]],
) -> Optional[datetime]:
    """取出契约的采集时刻(带时区)。

    拿不到时返回 ``None`` —— 调用方据此**保守处理**(不认定「事后追平」)。
    """
    if not isinstance(contract, dict):
        return None
    raw = contract.get("captured_at")
    if not raw:
        return None
    if isinstance(raw, datetime):
        return raw if raw.tzinfo else raw.replace(tzinfo=timezone.utc)
    try:
        parsed = datetime.fromisoformat(str(raw))
    except (TypeError, ValueError):
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def promote_template_contract(
    catalog_file: Any,
    template: Any,
    *,
    source: str = CONTRACT_SOURCE_PROMOTION,
    takeover: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    """把文件的契约晋升为「当前能解释它的那一版模板」。

    为什么需要
    ----------
    契约的语义是「这个文件当年是按哪一版模板解释的」, 但它**只保证采集当时成立**。
    当源文件结构先于模板发生变化时(采集时模板就解释不了这个文件), 契约指向的
    模板从此再也不可能解释这个文件 —— 于是:

    * 判定永远停在「结构漂移」
    * 用户唯一能做的补救(把新字段补进模板并发布新版本)**不产生任何效果**
    * 文件永远进不了入库队列

    实测(tiktok/analytics/monthly, 2026-10-29): 文件 29 列(含「商品卡 GMV」),
    契约指向 v6(28 列) ⇒ 永久漂移; 用户发布 v8(29 列)后仍漂移 —— 因为契约没变。

    晋升把契约改写成新版本, 让基准重新稳定, 且留痕 ``source`` 以便事后追溯。

    Returns:
        写入的契约; 模板为空时返回 ``None``。
    """
    if catalog_file is None or template is None:
        return None

    contract = build_template_contract(
        template,
        source=source,
        takeover=takeover,
    )
    if not contract:
        return None
    return write_template_contract(catalog_file, contract)


async def resolve_contract_template(db, contract: Optional[Dict[str, Any]]):
    """按契约取出模板行。

    模板行可能被物理删除, 因此找不到时返回 None, 由调用方回退到
    「当前已发布模板」口径。
    """
    template_id = contract_template_id(contract)
    if template_id is None:
        return None
    result = await db.execute(
        select(FieldMappingTemplate).where(FieldMappingTemplate.id == template_id)
    )
    return result.scalars().first()


def is_contract_baseline_valid(contract: Optional[Dict[str, Any]], template: Any) -> bool:
    """校验契约基准是否仍然可信。

    模板行被原地改写(列清单变了但版本号没变)时, 指纹会不一致,
    此时契约记录的表头结构已经不是模板现在的样子, 不能再拿它当基准。
    """
    if not isinstance(contract, dict) or template is None:
        return False
    expected_hash = contract.get("columns_hash")
    if not expected_hash:
        # 老契约没有指纹, 只要模板行还在就认为可用
        return True
    actual_hash = compute_columns_hash(getattr(template, "header_columns", None) or [])
    return actual_hash == expected_hash


async def resolve_valid_contract_template(db, catalog_file: Any):
    """取出「文件契约指向且仍然可信」的模板行。

    契约缺失 / 模板行已被删除 / 模板行被原地改写时返回 ``None``,
    由调用方回退到「当前已发布模板」或跨 family 接管。

    这是契约读取的**唯一入口** —— 判定链路与治理路由都走这里,
    避免两处对「契约还有效吗」给出不同结论。
    """
    contract = read_template_contract(catalog_file)
    if not contract:
        return None
    try:
        candidate = await resolve_contract_template(db, contract)
    except Exception:  # noqa: BLE001
        return None
    if candidate is None:
        return None
    if not is_contract_baseline_valid(contract, candidate):
        return None
    return candidate


def describe_contract_baseline(
    contract: Optional[Dict[str, Any]],
    template: Any,
) -> Dict[str, Any]:
    """对比「契约基准」与「当前模板」, 给出可展示的差异说明。

    返回字段:

    * ``has_contract``      文件是否带契约
    * ``baseline_valid``    契约基准是否仍然可信
    * ``baseline_template_id`` / ``baseline_template_version``
    * ``current_template_id`` / ``current_template_version``
    * ``template_outdated`` 当前模板已经不是契约记录的那一版(我们升级过模板)
    * ``outdated_reason``   人类可读的差异说明
    """
    if not isinstance(contract, dict):
        return {
            "has_contract": False,
            "baseline_valid": False,
            "template_outdated": False,
            "outdated_reason": None,
        }

    baseline_template_id = contract_template_id(contract)
    baseline_version = contract.get("template_version")
    current_template_id = getattr(template, "id", None) if template is not None else None
    current_version = getattr(template, "version", None) if template is not None else None

    baseline_valid = is_contract_baseline_valid(contract, template) if template is not None else False

    template_outdated = False
    outdated_reason = None
    if baseline_template_id is not None and current_template_id is not None:
        if int(baseline_template_id) != int(current_template_id):
            template_outdated = True
            outdated_reason = (
                f"文件按模板 v{baseline_version} 采集, 当前已发布模板为 v{current_version}"
            )
        elif baseline_version is not None and current_version is not None:
            if int(baseline_version) != int(current_version):
                template_outdated = True
                outdated_reason = (
                    f"文件按模板 v{baseline_version} 采集, 当前模板已升级到 v{current_version}"
                )

    return {
        "has_contract": True,
        "baseline_valid": baseline_valid,
        "baseline_template_id": baseline_template_id,
        "baseline_template_version": baseline_version,
        "current_template_id": current_template_id,
        "current_template_version": current_version,
        "template_outdated": template_outdated,
        "outdated_reason": outdated_reason,
    }
