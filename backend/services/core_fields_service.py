"""核心字段清单(``core_fields``)—— 一份清单管三件事。

规格
----
``docs/superpowers/plans/2026-11-07-semantic-core-field-spec.md`` §3.1:

* **落库列**   —— ``core_fields`` 全集; 只为核心字段建物理列;
* **data_hash** —— ``core_fields`` 中 ``in_hash=true`` 的 + 系统身份;
* **漂移阻断** —— ``core_fields`` 中 ``required=true`` 的 ∪ 域级契约 required。

用户勾一次, 三件事一起生效 —— 这就是「同一事实一份副本」。

清单结构
--------
::

    core_fields = [
        {
            "semantic_key": "product_id",  # 规范语义键(翻译不出来时为 None)
            "raw_name": "商品编号",         # 物理列名(降级逐字匹配时要用)
            "required": False,             # 缺失是否阻断
            "in_hash": True,               # 是否参与 data_hash
        },
    ]

为什么 ``semantic_key`` 与 ``raw_name`` 要并存
---------------------------------------------
规格 §1.3 说「指纹取你勾的字段的**内容**——**按标准含义取, 不看列名叫什么**」,
但 §6.1 同时指出: ``*商品SKU`` 这类**占位符列名**「无法翻译 ⇒ 须降级为逐字匹配并明确告警」。

⇒ 两件事必须同时成立:

1. **优先按标准含义取**(语义键);
2. **语义路径取不到时, 退回逐字取原始列**, 并记录降级告警。

只留 ``semantic_key`` ⇒ 降级路径没有列名可用, 字段会被静默丢掉
⇒ hash 变了 ⇒ 历史行变成「没见过的数据」。
只留 ``raw_name`` ⇒ 等于没做翻译层, 平台改列名就认不出来。

所以两个都留, 取值顺序是「**逐字优先, 语义兜底**」。

为什么是「逐字优先」(而不是语义优先)
------------------------------------
规格 §1.3 说「指纹取你勾的字段的**内容**——**按标准含义取, 不看列名叫什么**」,
规格 §6.1 同时要求「口径切换不得改已入库行的 hash」。

两条要求只有在**取值**与**键名**分开时才同时成立:

* **键名** = 旧口径的键名(``raw_name`` 优先)⇒ 键不变 ⇒ hash 不变;
* **取值** = 先按旧口径逐字取(同值同键), 取不到才按标准含义兜底
  ⇒ 旧口径能取到的值一模一样; 只有平台改了列名(旧口径会**丢掉**这个字段)
  时, 新口径才把字段救回来。

即: **等价性由「逐字优先」保证, 抗漂移由「语义兜底」提供**。
两者不冲突, 所以不必在「规格」与「不破存量」之间二选一。
"""

from __future__ import annotations

import os
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from backend.services.semantic_field_registry import (
    is_canonical_semantic_key,
    normalize_semantic_key,
    resolve_semantic_value,
)


#: ``core_fields`` 单项的字段名(SSOT)。
CORE_FIELD_KEYS = ("semantic_key", "raw_name", "required", "in_hash")

#: 口径切换开关(环境变量)。
#:
#: 规格 §6.1-4: 「口径切换必须是**显式开关**, 可一键回退到旧口径」。
#: 默认**关闭** —— 旧口径是当前生产口径, 开关打开前不影响任何一行数据。
CORE_FIELDS_HASH_ENV_KEY = "SYNC_CORE_FIELDS_HASH_ENABLED"

_TRUTHY = {"1", "true", "yes", "on"}


def core_fields_hash_enabled() -> bool:
    """是否启用「按核心字段清单算 hash」的新口径。

    规格 §6.1 的硬要求: 口径切换是**显式开关**, 出问题一键回退。
    默认关闭 ⇒ 新旧口径并存期内零风险; 打开前必须先看离线回放报告
    (``scripts/replay_core_fields_hash.py``)。
    """
    return str(os.getenv(CORE_FIELDS_HASH_ENV_KEY, "")).strip().lower() in _TRUTHY


def _is_user_confirmed_binding(binding: Dict[str, Any]) -> bool:
    """这条绑定是不是「用户确认过」的。

    口径与 :func:`backend.services.semantic_field_registry.is_confirmed_semantic_binding`
    一致, 再额外排除 ``semantic_review_source == 'inferred'``
    (系统按表头名猜出来的, 不能当成用户确认)。

    为什么必须这么严
    ----------------
    批次 D 之前, 历史绑定只要推断出了 ``semantic_key`` 就算「确认」,
    于是「产品ID」这种中文列名会被当成 ``product_id`` 身份,
    与真正写成 ``product_id`` 的模板判成口径一致 ⇒ **假一致**。
    这里不能重蹈覆辙。
    """
    status = str(binding.get("semantic_review_status") or "").strip()
    if status and status != "confirmed_semantic":
        return False
    source = str(binding.get("semantic_review_source") or "").strip()
    if source == "inferred":
        return False
    return True


def build_confirmed_binding_index(
    header_bindings: Optional[Iterable[Dict[str, Any]]],
) -> Dict[str, str]:
    """列名 → 语义键 的**已确认**映射。

    只收录「用户确认过」的绑定:
    * ``semantic_review_status`` 明确是 ``confirmed_non_semantic`` 的排除;
    * ``semantic_review_source == 'inferred'`` 的排除(机器猜的);
    * 语义键必须是规范键。

    历史上 ``semantic_review_status`` 为空但带 ``semantic_key`` 的绑定,
    按迁移期兼容口径视为已确认(与
    :func:`resolve_binding_review_status` 同一口径)。
    """
    index: Dict[str, str] = {}
    for binding in header_bindings or []:
        if not isinstance(binding, dict):
            continue
        if not _is_user_confirmed_binding(binding):
            continue
        semantic_key = normalize_semantic_key(binding.get("semantic_key"))
        if not semantic_key or not is_canonical_semantic_key(semantic_key):
            continue
        raw_name = str(
            binding.get("source_header") or binding.get("raw_name") or ""
        ).strip()
        if not raw_name:
            continue
        # 同一个列名被确认到两个语义键 ⇒ 取第一个, 并由别名裁决流程负责报警。
        index.setdefault(raw_name, semantic_key)
    return index


def translate_to_semantic_key(
    raw_name: str,
    *,
    data_domain: str = "",
    header_bindings: Optional[Iterable[Dict[str, Any]]] = None,
) -> Optional[str]:
    """把一个物理列名翻译成规范语义键(翻译不出来返回 None, 不猜)。

    翻译顺序(与迁移 ``20261125`` 的 SQL **逐条一致**):

    1. 本身已是规范语义键 ⇒ 就是它;
    2. **用户确认过**的绑定 ⇒ 绑定的语义键。

    为什么**不**走推断层(域限定列名表 / 全局别名表)
    ----------------------------------------------
    批次 D 的硬结论: 「只有用户确认过的绑定才允许被提升成语义身份」。
    推断出来的语义键(例如把中文「商品编号」推成 ``product_id``)一旦写进清单,
    就会与「真的写成 product_id 的模板」判成口径一致 ⇒ **假一致**
    (这正是批次 D 修掉的那个问题)。

    ⇒ 清单里的 ``semantic_key`` 只认**显式确认**;
    推断留给「列名 → 语义键」的**运行时匹配**(那里不影响口径判定)。

    口径漂移由守护测试 ``backend/tests/data_pipeline/test_core_fields_guardrails.py``
    锁住(迁移回填结果与本函数推导结果必须一致)。
    """
    text = str(raw_name or "").strip()
    if not text:
        return None
    if is_canonical_semantic_key(text):
        return normalize_semantic_key(text)

    confirmed_index = build_confirmed_binding_index(header_bindings)
    confirmed = confirmed_index.get(text)
    if confirmed:
        return confirmed

    return None


def derive_core_fields(
    *,
    deduplication_fields: Optional[Sequence[str]] = None,
    header_bindings: Optional[Iterable[Dict[str, Any]]] = None,
    data_domain: str = "",
    sub_domain: Optional[str] = None,
    required_semantic_keys: Optional[Iterable[str]] = None,
) -> List[Dict[str, Any]]:
    """从 ``deduplication_fields`` 推导出一份 ``core_fields`` 清单。

    推导规则(逐条可还原):

    1. 条目本身就是规范语义键 ⇒ ``semantic_key = 该键``、``raw_name = None``;
    2. 条目是物理列名 ⇒ ``raw_name = 原样``、``semantic_key`` 走翻译层
       (用户确认 > 域限定 > 全局), 翻译不出来就是 None;
    3. ``in_hash`` 全部继承为 True(现有 ``deduplication_fields`` 就是 hash 字段表);
    4. ``required`` 取「域级契约要求的语义键」∩「本条目的语义键」。

    Args:
        deduplication_fields: 现有的核心字段列表(字符串)。
        header_bindings: 模板的字段绑定(用于确认列名对应的语义键)。
        data_domain: 数据域(翻译层需要它做域限定)。
        sub_domain: 子类型(保留参数, 便于将来按子类型补默认清单)。
        required_semantic_keys: 域级契约里 ``required`` 的语义键集合。

    Returns:
        ``core_fields`` 清单。
    """
    required_keys = {str(key).strip() for key in (required_semantic_keys or []) if str(key).strip()}

    core_fields: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for entry in deduplication_fields or []:
        text = str(entry or "").strip()
        if not text:
            continue
        if is_canonical_semantic_key(text):
            semantic_key = normalize_semantic_key(text)
            raw_name: Optional[str] = None
        else:
            raw_name = text
            semantic_key = translate_to_semantic_key(
                text,
                data_domain=data_domain,
                header_bindings=header_bindings,
            )

        identity = raw_name or semantic_key or text
        if identity in seen:
            continue
        seen.add(identity)

        core_fields.append(
            {
                "semantic_key": semantic_key,
                "raw_name": raw_name,
                "required": bool(semantic_key and semantic_key in required_keys),
                "in_hash": True,
            }
        )
    return core_fields


def normalize_core_fields(raw: Any) -> List[Dict[str, Any]]:
    """把数据库里读出来的 ``core_fields`` 规整成规范形状。

    兼容三种历史形态:

    * ``None`` / ``[]`` ⇒ 空清单;
    * 字符串数组(旧 ``deduplication_fields``)⇒ 按物理列名处理;
    * 字典数组 ⇒ 补齐缺省字段。
    """
    if not raw:
        return []
    if isinstance(raw, str):
        import json

        try:
            raw = json.loads(raw)
        except (TypeError, ValueError):
            return []

    normalized: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for item in raw if isinstance(raw, list) else []:
        if isinstance(item, str):
            text = item.strip()
            if not text:
                continue
            semantic_key = normalize_semantic_key(text) if is_canonical_semantic_key(text) else None
            entry = {
                "semantic_key": semantic_key,
                "raw_name": None if semantic_key else text,
                "required": False,
                "in_hash": True,
            }
        elif isinstance(item, dict):
            semantic_key = normalize_semantic_key(item.get("semantic_key"))
            if semantic_key and not is_canonical_semantic_key(semantic_key):
                semantic_key = None
            raw_name = str(item.get("raw_name") or "").strip() or None
            if not semantic_key and not raw_name:
                continue
            entry = {
                "semantic_key": semantic_key,
                "raw_name": raw_name,
                "required": bool(item.get("required")),
                "in_hash": bool(item.get("in_hash", True)),
            }
        else:
            continue

        identity = entry["raw_name"] or entry["semantic_key"] or ""
        if not identity or identity in seen:
            continue
        seen.add(identity)
        normalized.append(entry)
    return normalized


def core_field_hash_identities(core_fields: Any) -> List[str]:
    """清单里参与 hash 的字段身份(喂给旧的 ``deduplication_fields`` 口径)。

    规则: **``raw_name`` 优先, 没有才用 ``semantic_key``**。

    为什么是 ``raw_name`` 优先(而不是语义键优先)
    ------------------------------------------
    写进 hash 载荷的**键名**必须与旧口径逐字一致, 否则**键一变、hash 就变**,
    已入库的行会全部变成「没见过的数据」。

    * 条目本身就是规范语义键(如 ``metric_date``)⇒ ``raw_name`` 为空
      ⇒ 键名 = ``metric_date``, 与旧口径一致;
    * 条目是物理列名(如 ``商品编号``)⇒ 键名 = ``商品编号``
      ⇒ 与旧口径一致。

    「按标准含义取」(规格 §1.3)落在**取值**上, 不落在键名上 ——
    见 :func:`resolve_core_field_value`。
    """
    identities: List[str] = []
    seen: set[str] = set()
    for entry in normalize_core_fields(core_fields):
        if not entry.get("in_hash"):
            continue
        identity = entry.get("raw_name") or entry.get("semantic_key") or ""
        if not identity or identity in seen:
            continue
        seen.add(identity)
        identities.append(identity)
    return identities


def lookup_literal_value(row: Dict[str, Any], field: str) -> Tuple[Any, Optional[str]]:
    """逐字查找一个字段的值(复刻旧口径的查找结构)。

    **刻意复刻旧口径的单次遍历**: 精确匹配与「忽略大小写」匹配在**同一轮**
    里按 ``row`` 的列顺序判断, 先命中先算。

    为什么不能改成「先扫精确、再扫大小写」
    --------------------------------------
    ``row`` 里若同时有 ``Order ID`` 与 ``order id`` 两列:
    * 旧口径(单次遍历)⇒ 命中 ``Order ID``(大小写宽松先撞上);
    * 「两轮扫描」⇒ 命中 ``order id``(精确优先)。

    载荷键不同 ⇒ hash 不同。**查找结构必须一模一样。**
    """
    for key in row.keys():
        if key == field:
            return row[key], key
        if str(key).lower() == str(field).lower():
            return row[key], key
    return None, None


def resolve_core_field_value(
    row: Dict[str, Any],
    entry: Dict[str, Any],
    *,
    header_bindings: Optional[Iterable[Dict[str, Any]]] = None,
) -> Tuple[Any, Optional[str], bool]:
    """按「逐字优先, 语义兜底」取一行里某核心字段的值。

    取值顺序
    --------
    1. **逐字命中** ⇒ 取到的值与旧口径**完全相同**, 载荷键 = 实际命中的列名;
    2. 逐字没命中、但条目本身就是规范语义键 ⇒ 走语义解析(旧口径同款);
    3. 逐字没命中、条目是物理列名 ⇒ **走语义解析兜底**(规格 §1.3 的抗漂移),
       并标记 ``degraded=True`` 让调用方记告警。

    为什么「逐字优先」而不是「语义优先」
    ------------------------------------
    规格 §1.3 说「按标准含义取, 不看列名叫什么」。若把语义放在逐字前面:

    * ``row`` 里同时存在 ``product_id`` 列与 ``商品编号`` 列(内容还不一样)时,
      旧口径取 ``商品编号``, 新口径取 ``product_id`` ⇒ **hash 变了**;
    * 「先逐字、拿不到再语义」则: 旧口径能取到的值, 新口径**一模一样**;
      只有旧口径**取不到**(平台改了列名)时, 新口径才把字段救回来。

    ⇒ 等价性由「逐字优先」保证, 抗漂移能力由「语义兜底」提供。两者不冲突。
    """
    semantic_key = entry.get("semantic_key")
    raw_name = entry.get("raw_name")
    hash_key = raw_name or semantic_key or ""
    if not hash_key:
        return None, None, False

    # 1) 逐字命中 —— 与旧口径同值同键
    #    注意: 命中但值为 None 时, 旧口径也算「命中」(载荷键仍要写进去),
    #    所以判断依据是**匹配到的列名**, 不是值。
    if raw_name:
        value, matched_key = lookup_literal_value(row, raw_name)
        if matched_key is not None:
            return value, matched_key, False

    # 2) 条目本身就是规范语义键 ⇒ 语义解析(与旧口径的语义分支一致)
    if semantic_key and not raw_name:
        value, _matched = resolve_semantic_value(
            row,
            semantic_key,
            header_bindings=header_bindings,
        )
        if value is not None:
            return value, semantic_key, False
        return None, None, False

    # 3) 逐字没命中 ⇒ 语义兜底(抗列名漂移)
    if semantic_key:
        value, _matched = resolve_semantic_value(
            row,
            semantic_key,
            header_bindings=header_bindings,
        )
        if value is not None:
            # 载荷键仍用清单里的键名 ⇒ 键集合不因漂移而变
            return value, hash_key, True

    return None, None, False


def merge_core_fields(
    existing_core_fields: Any,
    deduplication_fields: Optional[Sequence[str]] = None,
    *,
    header_bindings: Optional[Iterable[Dict[str, Any]]] = None,
    data_domain: str = "",
    sub_domain: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """把「已有清单」与「新的去重字段」合并成一份新清单。

    为什么要合并而不是直接重算
    ------------------------
    已有清单里的 ``raw_name`` 是**原始物理列名**(迁移回填时从存库的
    ``deduplication_fields`` 取的), 它是 hash 载荷的**键名**。

    若直接按新的 ``deduplication_fields`` 重算, 键名会从物理列名变成
    规范语义键 ⇒ **hash 变了** ⇒ 已入库的行被当成新数据
    (离线回放实测: 6 个版本 / 81 行受影响)。

    ⇒ 合并规则:
    1. **键名优先沿用已有清单**;
    2. ``in_hash`` 按新的 ``deduplication_fields`` 同步;
    3. 新勾的、清单里没有的字段 ⇒ 追加(键名按新口径推导);
    4. 清单里有、但不再参与去重的字段 ⇒ 保留, ``in_hash=False``。
    """
    existing = normalize_core_fields(existing_core_fields)
    existing_by_key: Dict[str, Dict[str, Any]] = {}
    for entry in existing:
        key = entry.get("raw_name") or entry.get("semantic_key") or ""
        if key and key not in existing_by_key:
            existing_by_key[key] = entry

    derived = derive_core_fields(
        deduplication_fields=deduplication_fields,
        header_bindings=header_bindings,
        data_domain=data_domain,
        sub_domain=sub_domain,
    )

    hash_keys: set[str] = set()
    for entry in derived:
        key = entry.get("raw_name") or entry.get("semantic_key") or ""
        if key:
            hash_keys.add(key)

    merged: List[Dict[str, Any]] = []
    used_existing: set[str] = set()

    for entry in derived:
        key = entry.get("raw_name") or entry.get("semantic_key") or ""
        previous = existing_by_key.get(key)
        if previous is not None:
            used_existing.add(key)
            merged.append(
                {
                    "semantic_key": previous.get("semantic_key") or entry.get("semantic_key"),
                    # 键名沿用旧清单 ⇒ hash 口径不变
                    "raw_name": previous.get("raw_name"),
                    "required": bool(previous.get("required")),
                    "in_hash": True,
                }
            )
        else:
            merged.append(
                {
                    "semantic_key": entry.get("semantic_key"),
                    "raw_name": entry.get("raw_name"),
                    "required": bool(entry.get("required")),
                    "in_hash": True,
                }
            )

    # 清单里有、但不再参与去重的字段 ⇒ 保留(仍要落库), 只是不进指纹
    for key, entry in existing_by_key.items():
        if key in used_existing or key in hash_keys:
            continue
        merged.append(
            {
                "semantic_key": entry.get("semantic_key"),
                "raw_name": entry.get("raw_name"),
                "required": bool(entry.get("required")),
                "in_hash": False,
            }
        )

    return merged


def core_field_semantic_keys(core_fields: Any) -> List[str]:
    """清单里所有能对上语义键的字段(落库列 / 契约判定用)。"""
    keys: List[str] = []
    seen: set[str] = set()
    for entry in normalize_core_fields(core_fields):
        semantic_key = entry.get("semantic_key")
        if not semantic_key or semantic_key in seen:
            continue
        seen.add(semantic_key)
        keys.append(semantic_key)
    return keys


def core_field_column_names(core_fields: Any) -> List[str]:
    """清单对应的物理列名(落库建列用)。

    规格 §3.1 说「列名 = 标准字段键」, 但**历史已建的列不能物理删**(§6.2),
    所以这里同时给出两种口径:

    * :func:`core_field_column_names` —— 语义键(新库建列用);
    * :func:`core_field_legacy_column_names` —— 原始列名(读兼容用)。
    """
    names: List[str] = []
    seen: set[str] = set()
    for entry in normalize_core_fields(core_fields):
        name = entry.get("semantic_key") or entry.get("raw_name") or ""
        if not name or name in seen:
            continue
        seen.add(name)
        names.append(name)
    return names


def core_field_legacy_column_names(core_fields: Any) -> List[str]:
    """清单对应的**原始**列名(读兼容 / 降级匹配用)。"""
    names: List[str] = []
    seen: set[str] = set()
    for entry in normalize_core_fields(core_fields):
        name = entry.get("raw_name") or entry.get("semantic_key") or ""
        if not name or name in seen:
            continue
        seen.add(name)
        names.append(name)
    return names


#: 落库列收窄开关(环境变量)—— 批次 F-1 / F-2。
#:
#: 规格 §4 步骤 8: 「落库：**只为 ``core_fields`` 全集建物理列**; 其余字段只进
#: ``raw_data`` JSONB 存档」。
#:
#: 为什么**默认开启**
#: ------------------
#: 收窄的收益是「消除同一业务字段存两份」(物理列 + JSONB);
#: 风险是「历史已建的列不再更新 ⇒ 新老数据在同一列上不一致」。
#:
#: 实测结论(2026-11-07):
#:
#: * 下游 ``semantic`` view(``sql/semantic/*.sql``)只选**系统列 + raw_data**,
#:   **零引用业务动态列** ⇒ 收窄不会让语义层/看板取不到数;
#: * 历史列**不物理删**(规格 §6.2)⇒ 存量数据仍可读;
#: * 非核心字段的完整内容始终在 ``raw_data`` JSONB 里 ⇒ 可回溯。
#:
#: ⇒ 收窄是安全的, 且必须默认开启才能达成「消除双份存储」的目标。
#: 保留开关是为了**一键回退**(出问题时不用发版)。
CORE_FIELDS_COLUMNS_ENV_KEY = "SYNC_CORE_FIELDS_CORE_COLUMNS_ENABLED"

#: 落库列收窄开关的**默认状态**。
#:
#: 环境变量未设置时用这个值; 显式设置成 ``0/false/no/off`` 才关闭。
CORE_FIELDS_COLUMNS_DEFAULT_ENABLED = True


def core_fields_columns_enabled() -> bool:
    """是否启用「只为核心字段建物理列」(批次 F-1 / F-2)。

    默认**开启**; 显式设成 ``0/false/no/off`` 可一键回退到旧行为
    (所有表头列都建列)。
    """
    raw = str(os.getenv(CORE_FIELDS_COLUMNS_ENV_KEY, "")).strip().lower()
    if not raw:
        return CORE_FIELDS_COLUMNS_DEFAULT_ENABLED
    if raw in _TRUTHY:
        return True
    if raw in {"0", "false", "no", "off"}:
        return False
    return CORE_FIELDS_COLUMNS_DEFAULT_ENABLED


def core_field_storage_column_names(core_fields: Any) -> List[str]:
    """清单里**真正要建物理列**的列名(批次 F-1 的唯一口径)。

    为什么用「原始列名」而不是「标准字段键」
    ----------------------------------------
    规格 §3.1 写的是「列名 = 标准字段键」, 但同时 §6.2 要求「历史已建的列
    **保留读兼容, 不物理删**」。两条放在一起只有一个自洽解:

    * 若按**标准字段键**建列 ⇒ 表里会多出一批 ``product_id`` 之类的英文列,
      而原有的 ``商品编号`` 列还在 ⇒ **同一业务字段存两份**,
      正是 F 要消除的那个问题;
    * 按**原始列名**建列 ⇒ 与历史已建的列**同名** ⇒ 同一字段一列,
      存量数据与新数据在同一列上, 读兼容天然成立。

    ⇒ 建列一律用**原始列名**。

    只有 ``semantic_key``、没有 ``raw_name`` 的条目
    --------------------------------------------
    这类条目(目前只有 ``metric_date`` 这类系统字段)的**物理列名不确定** ——
    语义键是「标准含义」, 不等于文件里的列名。
    它们**不参与建列**: 系统字段(如 ``metric_date``)本来就有列,
    业务语义键则等它有 ``raw_name`` 时再落列。
    """
    names: List[str] = []
    seen: set[str] = set()
    for entry in normalize_core_fields(core_fields):
        raw_name = str(entry.get("raw_name") or "").strip()
        if not raw_name or raw_name in seen:
            continue
        seen.add(raw_name)
        names.append(raw_name)
    return names


def core_field_required_semantic_keys(core_fields: Any) -> List[str]:
    """清单里「缺失算阻断」的语义键。"""
    keys: List[str] = []
    seen: set[str] = set()
    for entry in normalize_core_fields(core_fields):
        semantic_key = entry.get("semantic_key")
        if not semantic_key or not entry.get("required") or semantic_key in seen:
            continue
        seen.add(semantic_key)
        keys.append(semantic_key)
    return keys
