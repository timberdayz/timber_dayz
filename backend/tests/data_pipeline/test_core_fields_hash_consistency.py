# -*- coding: utf-8 -*-
"""核心字段清单与去重字段表的**跨维度**一致性守护（2026-11-14）。

背景
----
同一件事在两处各写一遍，是最容易复发的一类债：

* **清单**（``core_fields`` 里 ``in_hash=true`` 的条目）声明「哪些字段参与指纹」；
* **去重字段表**（``deduplication_fields``）声明同一件事。

两处必须**逐字一致**。2026-11-14 实测：27 个维度**当前全部一致**（人工逐个比对），
但**只有库存维度有守护测试** —— 其余 26 个维度一旦有人加字段只改一处，
就会漂移，而且**不报错**：

* 清单里的 ``in_hash`` **当前不参与指纹字段集合**
  （``deduplication_service.py:365``：
  ``fields = list(deduplication_fields or entry_by_key.keys())``）
  ⇒ 两边漂移时，指纹照旧按去重字段表算 ⇒ 表面一切正常；
* 直到有人打开 ``SYNC_CORE_FIELDS_HASH_ENABLED``（取值方式改变 ⇒ 部分行 hash 变）
  ⇒ 已入库的行被当成新数据 ⇒ 事实表膨胀
  ⇒ **与 v7.29.3 修掉的 256 组重复行是同一类病**。

⇒ 把「人工比对过」升级成「机器保证」。

两种声明形态（**有意分工**，不是缺陷）
------------------------------------
* 带 ``raw_name`` 的条目 ⇒ 管「某个物理列缺不缺」；
* 纯 ``semantic_key`` 的条目 ⇒ 管「这个语义键参与去重/校验」。

⇒ 比对时用**身份键**（``raw_name or semantic_key``），两种形态都能比。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFINITIONS_DIR = REPO_ROOT / "templates" / "definitions"


def _definition_paths() -> List[Path]:
    paths = sorted(DEFINITIONS_DIR.glob("*.json"))
    assert paths, "templates/definitions 下没有任何维度定义文件"
    return paths


def _load(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _in_hash_identities(definition: Dict[str, Any]) -> List[str]:
    """清单里声明参与指纹的字段身份（``raw_name`` 优先，其次 ``semantic_key``）。

    取值顺序与 ``backend/services/core_fields_service.py::core_field_hash_identities``
    一致：**``raw_name`` 优先** —— 键名就是写进指纹载荷的键，
    换键名就等于换指纹。
    """
    identities: List[str] = []
    for entry in definition.get("core_fields") or []:
        if not isinstance(entry, dict) or not entry.get("in_hash"):
            continue
        key = entry.get("raw_name") or entry.get("semantic_key") or ""
        if key and key not in identities:
            identities.append(str(key))
    return identities


def test_every_dimension_declares_deduplication_fields():
    """每个维度都必须配了去重字段。

    没有 ⇒ 一旦走到「域默认回落」，会算出「所有行同一个指纹」
    （同一天互相覆盖，一天只剩一行，**且不报错**）。
    """
    for path in _definition_paths():
        definition = _load(path)
        dedup = definition.get("deduplication_fields") or []
        assert dedup, "{0} 没有配置 deduplication_fields".format(path.name)


def test_every_dimension_declares_core_fields():
    """每个维度都必须配了核心字段清单。

    没有清单 ⇒ 「哪些列是需求」没人声明 ⇒ 缺列不阻断、也不参与指纹。
    """
    for path in _definition_paths():
        definition = _load(path)
        core_fields = definition.get("core_fields") or []
        assert core_fields, "{0} 没有配置 core_fields".format(path.name)


def test_in_hash_entries_match_deduplication_fields_in_every_dimension():
    """清单声明的指纹字段必须与去重字段表**逐字一致**（27 个维度全查）。

    这条断言是「同一件事只有一个说了算的地方」的机器保证：
    清单是**声明**，去重字段表是**权威**，两者不一致时必须有人先发现，
    而不是等到某次口径切换把事实表撑爆才发现。
    """
    for path in _definition_paths():
        definition = _load(path)
        dedup = {str(field) for field in (definition.get("deduplication_fields") or [])}
        in_hash = set(_in_hash_identities(definition))
        assert (
            in_hash == dedup
        ), "{0} 的清单声明与去重字段表不一致：清单={1} 去重字段表={2}。" "两处必须逐字一致（清单是声明，去重字段表是权威）".format(
            path.name, sorted(in_hash), sorted(dedup)
        )


def test_deduplication_fields_are_not_duplicated_within_a_dimension():
    """去重字段表内部不许重复（重复项会让指纹载荷多写一个同键）。

    清单侧同键会被 ``normalize_core_fields`` 去重；
    去重字段表侧是**原始列表**，重复不会被消掉 ⇒ 两边就不可能逐字一致。
    """
    for path in _definition_paths():
        definition = _load(path)
        dedup = [str(field) for field in (definition.get("deduplication_fields") or [])]
        assert len(dedup) == len(set(dedup)), "{0} 的去重字段表里有重复项：{1}".format(
            path.name, dedup
        )
