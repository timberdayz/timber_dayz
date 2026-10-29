from __future__ import annotations

import copy
import hashlib
import re
import time
import weakref
from collections import defaultdict
from typing import Any, Dict, Iterable, Optional

from sqlalchemy import and_, event, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.services.semantic_field_registry import is_canonical_semantic_key, normalize_semantic_key
from backend.services.template_variant_takeover import (
    TAKEOVER_FLAG,
    build_takeover_report,
    evaluate_variant_takeover,
    select_best_takeover,
)
from modules.core.db import (
    CatalogFile,
    FieldMappingTemplate,
    FieldMappingTemplateFamily,
    FieldMappingTemplateVariant,
    FieldMappingTemplateVersion,
)
from modules.core.logger import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# 模板目录缓存 (2026-10-29)
# ---------------------------------------------------------------------------
# 问题
# ----
# 治理看板一次要解析 27 个组合, 而每个组合的解析会**递归**展开:
#   resolve → get_family_versions → list_families → project_legacy_templates(写库 + commit)
#   resolve → get_version_variants → get_family_versions → list_families → …
#   resolve → list_cross_family_variants → 每个兄弟族都再来一遍
# 实测一次看板请求打出 **3 万多次查询 + 1.5 万次 commit** ⇒ 13~17 秒。
#
# 做法(保守方案: 只加缓存, 不动查询结构, 不改判定口径)
# ----------------------------------------------------
# * 进程内缓存「模板目录」(族 / 版本 / 变体 / 文件计数), **只读不写库**;
# * **目录一变, 缓存立即作废**:
#     - 模板目录表(模板/族/版本/变体)写入 ⇒ 目录变了 ⇒ 缓存作废;
#     - ``catalog_files`` 写入 ⇒ 文件计数变了 ⇒ 缓存作废;
#   作废信号挂在**引擎级** ``after_cursor_execute`` 上 —— 只有真的执行了
#   写 SQL 才算 ⇒ **不依赖"记得在某个路由里手动清缓存"**, 任何写入口都会触发;
# * TTL(默认 10 分钟)只是兜底, 防住 ORM 之外的裸 SQL 改动;
# * 缓存按**引擎(连接池)**分桶 ⇒ 同一个库的所有会话共享一份缓存,
#   而"同一个 URL 但不同实例"的库(典型: 测试里各建各的 SQLite 内存库)
#   **不会串味** ⇒ 真实库与测试隔离库、测试之间互不干扰。
#
# 口径不变: 缓存里放的就是原来算出来的同一份 payload, 判定逻辑一行没改。
_CATALOG_GENERATION = 0
_FILE_GENERATION = 0
_CATALOG_CACHE_TTL_SECONDS = 600.0

#: 目录表的表名片段(用于识别写 SQL)
_CATALOG_TABLE_MARKERS = (
    "field_mapping_templates",
    "field_mapping_template_families",
    "field_mapping_template_versions",
    "field_mapping_template_variants",
)


def _bump_catalog_generation() -> None:
    """模板目录(模板/族/版本/变体)发生写入 ⇒ 缓存作废。"""
    global _CATALOG_GENERATION
    _CATALOG_GENERATION += 1


def _bump_file_generation() -> None:
    """catalog_files 发生写入 ⇒ 文件计数过期 ⇒ 缓存作废。"""
    global _FILE_GENERATION
    _FILE_GENERATION += 1


def _watch_engine_writes(engine: Any) -> None:
    """监听引擎上的**真实写 SQL** —— 只有真的写了目录表才让缓存作废。

    为什么不用 ORM 的 ``after_insert`` / ``after_update`` 钩子:
    SQLAlchemy 2.0 会给「被重新赋了等值」的对象也派发 ``after_update``
    (实测目录投影每跑一次就白触发 9 次) ⇒ 缓存永远不命中, 看板还是 13 秒。
    引擎级的 ``after_cursor_execute`` 只在**真的执行了写 SQL** 时才触发,
    既是精确信号, 又覆盖所有写入口(ORM / 裸 SQL / 批量语句)。
    """

    @event.listens_for(engine, "after_cursor_execute")
    def _on_execute(conn, cursor, statement, parameters, context, executemany):  # noqa: ANN001
        head = statement.lstrip().lower()
        if not head.startswith(("insert ", "update ", "delete ")):
            return
        if any(marker in head for marker in _CATALOG_TABLE_MARKERS):
            _bump_catalog_generation()
        elif "catalog_files" in head:
            _bump_file_generation()


class _TemplateCatalogCache:
    """单个数据库上的模板目录缓存。

    失效条件(任一命中即整体清空):
      * 模板目录被写入(引擎级写 SQL 监听)
      * catalog_files 被写入(引擎级写 SQL 监听)
      * TTL 到期(兜底: 防住 ORM 之外的裸 SQL)
    """

    __slots__ = ("_entries", "_catalog_generation", "_file_generation", "_expires_at")

    def __init__(self) -> None:
        self._entries: dict[str, Any] = {}
        self._catalog_generation = -1
        self._file_generation = -1
        self._expires_at = 0.0

    def _is_stale(self) -> bool:
        return (
            self._catalog_generation != _CATALOG_GENERATION
            or self._file_generation != _FILE_GENERATION
            or time.monotonic() >= self._expires_at
        )

    def clear(self) -> None:
        self._entries.clear()
        self._catalog_generation = _CATALOG_GENERATION
        self._file_generation = _FILE_GENERATION
        self._expires_at = time.monotonic() + _CATALOG_CACHE_TTL_SECONDS

    def get(self, key: str) -> Any:
        if self._is_stale():
            self.clear()
        return self._entries.get(key)

    def set(self, key: str, value: Any) -> None:
        self._entries[key] = value


#: 拿不到 bind 时的退化桶(不参与隔离, 但保证功能不挂)
_FALLBACK_CACHE_KEY = object()

#: 引擎 → 缓存桶。用 WeakKeyDictionary: 引擎被回收时缓存自动释放, 不留内存。
_CATALOG_CACHES: "weakref.WeakKeyDictionary[Any, _TemplateCatalogCache]" = (
    weakref.WeakKeyDictionary()
)
#: 已经挂过写监听的引擎(同一个引擎只挂一次)
_WATCHED_ENGINES: "weakref.WeakSet[Any]" = weakref.WeakSet()


def _ensure_watched(bind: Any) -> None:
    """给引擎挂一次「写 SQL ⇒ 缓存作废」的监听。"""
    try:
        if bind in _WATCHED_ENGINES:
            return
        _WATCHED_ENGINES.add(bind)
    except TypeError:
        # 不可 weakref / 不可 hash 的对象 ⇒ 退化成"不挂监听"(只损失立即作废的及时性)
        return
    try:
        _watch_engine_writes(bind)
    except Exception:  # noqa: BLE001 - 监听失败只影响"立即作废"的及时性
        logger.warning("[TemplateFamily] 目录缓存写监听挂载失败", exc_info=True)


def _cache_for(db: AsyncSession) -> _TemplateCatalogCache:
    """取当前数据库对应的缓存桶(按**引擎/连接池**隔离)。

    为什么按引擎而不是按库地址:
        ``sqlite+aiosqlite://`` 这类"空地址"的内存库, 每个测试自己建引擎,
        地址字符串完全相同但**库内容不同** ⇒ 按地址分桶会让不同测试互相串味。
        按引擎分桶才能保证"同一个库共享缓存、不同库各自分开"。
    """
    try:
        bind = db.get_bind()
    except Exception:  # noqa: BLE001 - 拿不到引擎就退化成"不分桶"
        bind = None

    key: Any = bind if bind is not None else _FALLBACK_CACHE_KEY
    try:
        cache = _CATALOG_CACHES.get(key)
    except TypeError:
        key = _FALLBACK_CACHE_KEY
        cache = _CATALOG_CACHES.get(key)

    if cache is None:
        cache = _TemplateCatalogCache()
        try:
            _CATALOG_CACHES[key] = cache
        except TypeError:
            key = _FALLBACK_CACHE_KEY
            _CATALOG_CACHES[key] = cache
        if bind is not None:
            _ensure_watched(bind)
    return cache


def clear_template_catalog_cache() -> None:
    """手动清空所有模板目录缓存(测试/运维用)。"""
    for cache in list(_CATALOG_CACHES.values()):
        cache.clear()
    _CATALOG_CACHES.clear()


def _extract_semantic_key_sets(
    deduplication_fields: list[str] | None,
    header_bindings: list[dict[str, Any]] | None,
) -> tuple[list[str], list[str]]:
    required_keys: list[str] = []
    hash_keys: list[str] = []
    seen_required: set[str] = set()
    seen_hash: set[str] = set()

    for field in deduplication_fields or []:
        semantic_key = normalize_semantic_key(field)
        if semantic_key and is_canonical_semantic_key(semantic_key) and semantic_key not in seen_hash:
            seen_hash.add(semantic_key)
            hash_keys.append(semantic_key)

    for binding in header_bindings or []:
        semantic_key = normalize_semantic_key(
            binding.get("semantic_key") or binding.get("semantic_role") or binding.get("display_name")
        )
        if not semantic_key:
            continue
        if binding.get("required") and semantic_key not in seen_required:
            seen_required.add(semantic_key)
            required_keys.append(semantic_key)
        if binding.get("hash_participates") and semantic_key not in seen_hash:
            seen_hash.add(semantic_key)
            hash_keys.append(semantic_key)

    return required_keys, hash_keys


def _normalize_dimension(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    if text.lower() in {"n/a", "na", "none", "null"}:
        return None
    return text or None


def _dimension_key(
    platform: str,
    data_domain: str,
    sub_domain: Optional[str],
    granularity: Optional[str],
    account: Optional[str],
) -> tuple[str, str, Optional[str], Optional[str], Optional[str]]:
    return (
        str(platform).strip(),
        str(data_domain).strip(),
        _normalize_dimension(sub_domain),
        _normalize_dimension(granularity),
        _normalize_dimension(account),
    )


def infer_variant_key_from_legacy_template(template: FieldMappingTemplate) -> str:
    template_name = str(getattr(template, "template_name", "") or "").lower()
    if "slash" in template_name:
        return f"{template.granularity or 'generic'}_slash"
    if "dash" in template_name:
        return f"{template.granularity or 'generic'}_dash"

    rules = list(getattr(template, "field_parse_rules", None) or [])
    for rule in rules:
        date_format = str(rule.get("date_format", "")).strip().lower()
        if "/" in date_format:
            return f"{template.granularity or 'generic'}_slash"
        if "-" in date_format:
            return f"{template.granularity or 'generic'}_dash"

    header_row = getattr(template, "header_row", None)
    if header_row not in (None, 0):
        signature = _header_signature(template.header_columns or [])
        return f"{template.granularity or 'generic'}_header_{header_row}_{signature}"
    return f"{template.granularity or 'generic'}_default"


def _header_signature(columns: Iterable[str]) -> str:
    normalized = [str(column).strip().lower() for column in columns if str(column).strip()]
    joined = "|".join(normalized)
    if not joined:
        return "empty"
    return hashlib.md5(joined.encode("utf-8")).hexdigest()[:8]


def build_projection_variant_key(
    template: FieldMappingTemplate,
    *,
    existing_keys: set[str],
) -> str:
    variant_key = infer_variant_key_from_legacy_template(template)
    if variant_key not in existing_keys:
        return variant_key
    template_id = getattr(template, "id", None)
    if template_id is not None:
        return f"{variant_key}_{template_id}"
    return f"{variant_key}_{_header_signature(template.header_columns or [])}"


def build_projection_variant_key(
    template: FieldMappingTemplate,
    *,
    existing_keys: set[str],
) -> str:
    variant_key = infer_variant_key_from_legacy_template(template)
    if variant_key not in existing_keys:
        return variant_key
    template_id = getattr(template, "id", None)
    if template_id is not None:
        return f"{variant_key}_{template_id}"
    return f"{variant_key}_{abs(hash(template.template_name or 'variant')) % 100000}"


def _build_parse_profile(template: FieldMappingTemplate) -> dict[str, Any]:
    rules = list(template.field_parse_rules or [])
    date_formats = sorted(
        {
            str(rule.get("date_format", "")).strip()
            for rule in rules
            if str(rule.get("date_format", "")).strip()
        }
    )
    value_kinds = sorted(
        {
            str(rule.get("value_kind", "")).strip()
            for rule in rules
            if str(rule.get("value_kind", "")).strip()
        }
    )
    return {
        "date_formats": date_formats,
        "value_kinds": value_kinds,
    }


def _required_headers(template: FieldMappingTemplate) -> list[str]:
    return [str(column).strip() for column in (template.header_columns or []) if str(column).strip()]


def _match_rule_to_row(rule: dict[str, Any], row: dict[str, Any]) -> bool:
    source_column = str(rule.get("source_column", "")).strip()
    if not source_column:
        return False
    raw_value = row.get(source_column)
    if not str(raw_value or "").strip():
        return False

    try:
        from modules.services.smart_date_parser import parse_date_by_declared_format

        parsed_date, parsed_datetime = parse_date_by_declared_format(
            raw_value,
            date_format=str(rule.get("date_format", "")).strip(),
            value_kind=str(rule.get("value_kind", "single_date")).strip(),
            range_pick=rule.get("range_pick"),
            date_anchor=rule.get("date_anchor"),
        )
    except Exception:
        return False
    return parsed_date is not None or parsed_datetime is not None


def _variant_matches_sample_rows(
    field_parse_rules: Iterable[dict[str, Any]],
    sample_rows: Iterable[dict[str, Any]],
) -> bool:
    rules = list(field_parse_rules or [])
    rows = list(sample_rows or [])
    if not rules or not rows:
        return True
    for rule in rules:
        if any(_match_rule_to_row(rule, row) for row in rows):
            continue
        return False
    return True


def _account_dimension_matches(
    family_account: Optional[str],
    file_account: Optional[str],
) -> bool:
    """模板族的账号维度是否适用于该文件。

    模板族绝大多数是 **account=None**(与店铺无关的通用模板),
    而 ``catalog_files.account`` 是具体店铺 —— 所以 ``None`` 一侧表示「适用任意账号」。

    实测本地库 34 个 family 全部 ``account=None``, 而文件的 account 是
    ``chenzeweinbnb@163.com`` 之类的具体值 —— 若按字面相等判断,
    「自家 family」永远匹配不上, 接管就会抢走自家文件的解释权。
    """
    if family_account is None:
        return True
    if file_account is None:
        return False
    return str(family_account) == str(file_account)


def _variant_header_row_matches(
    variant: dict[str, Any],
    header_row: Optional[int],
) -> bool:
    """变体声明的表头行是否与实际读取的表头行一致。

    ``header_columns`` 是按**某一行**读出来的, 只有与变体声明的行一致时,
    比对结果才有意义。

    * 变体没声明表头行 -> 视为「任意行可用」(无法证伪, 不阻塞)
    * 调用方不知道实际行号 -> 同样放行(保持既有调用方行为)
    """
    variant_row = variant.get("header_row")
    if variant_row is None or header_row is None:
        return True
    try:
        return int(variant_row) == int(header_row)
    except (TypeError, ValueError):
        return False


def _assign_if_changed(target: Any, attr: str, value: Any) -> None:
    """只在**值真的变了**时才写属性。

    为什么必须这么做: JSON 列(``deduplication_fields`` / ``header_bindings`` /
    ``legacy_template_ids`` / ``required_headers`` / ``parse_profile`` /
    ``field_parse_rules``)每次赋值都会被 SQLAlchemy 标记为脏 —— 即使内容一模一样。
    于是 ``project_legacy_templates`` 每跑一次就发出 9 条无意义的 UPDATE,
    把「目录变了」的作废钩子无谓地触发 ⇒ 目录缓存永远不命中(看板还是 13 秒)。
    """
    current = getattr(target, attr, None)
    if current == value:
        return
    setattr(target, attr, value)


class TemplateFamilyService:
    def __init__(self, db: AsyncSession):
        self.db = db

    @staticmethod
    def _is_canonical_dimension_value(value: Optional[str]) -> bool:
        normalized = _normalize_dimension(value)
        if normalized is None:
            return value is None
        return str(value).strip() == normalized

    @classmethod
    def _canonical_dimension_rank(
        cls,
        family: FieldMappingTemplateFamily,
    ) -> int:
        return sum(
            0 if cls._is_canonical_dimension_value(value) else 1
            for value in (family.sub_domain, family.granularity, family.account)
        )

    @staticmethod
    def _family_dimension_key(
        family: FieldMappingTemplateFamily,
    ) -> tuple[str, str, Optional[str], Optional[str], Optional[str]]:
        return _dimension_key(
            family.platform,
            family.data_domain,
            family.sub_domain,
            family.granularity,
            family.account,
        )

    @classmethod
    def _prefer_family_record(
        cls,
        families: list[FieldMappingTemplateFamily],
    ) -> FieldMappingTemplateFamily:
        return sorted(
            families,
            key=lambda item: (
                item.active_version_id is None,
                cls._canonical_dimension_rank(item),
                -(item.id or 0),
            ),
        )[0]

    async def project_legacy_templates(
        self,
        *,
        platform: Optional[str] = None,
        data_domain: Optional[str] = None,
    ) -> None:
        stmt = select(FieldMappingTemplate).where(FieldMappingTemplate.status == "published")
        if platform:
            stmt = stmt.where(FieldMappingTemplate.platform == platform)
        if data_domain:
            stmt = stmt.where(FieldMappingTemplate.data_domain == data_domain)
        result = await self.db.execute(stmt)
        templates = list(result.scalars().all())
        if not templates:
            return

        groups: dict[tuple[str, str, Optional[str], Optional[str], Optional[str]], list[FieldMappingTemplate]] = defaultdict(list)
        for template in templates:
            groups[
                _dimension_key(
                    template.platform,
                    template.data_domain,
                    template.sub_domain,
                    template.granularity,
                    template.account,
                )
            ].append(template)

        for key, group in groups.items():
            await self._upsert_projection_group(key, group)

        await self.db.commit()

    async def _upsert_projection_group(
        self,
        key: tuple[str, str, Optional[str], Optional[str], Optional[str]],
        group: list[FieldMappingTemplate],
    ) -> None:
        platform, data_domain, sub_domain, granularity, account = key
        matching_group = [
            template
            for template in group
            if _dimension_key(
                template.platform,
                template.data_domain,
                template.sub_domain,
                template.granularity,
                template.account,
            )
            == key
        ]
        skipped_count = len(group) - len(matching_group)
        if skipped_count:
            logger.warning(
                "[TemplateFamily] skipped %s cross-dimension template(s) for projection key=%s",
                skipped_count,
                key,
            )
        if not matching_group:
            return
        group = matching_group

        family = await self._get_family(key)
        if family is None:
            family = FieldMappingTemplateFamily(
                platform=platform,
                data_domain=data_domain,
                sub_domain=sub_domain,
                granularity=granularity,
                account=account,
                display_name=self._build_display_name(platform, data_domain, sub_domain, granularity),
                governance_status="ready",
                source_mode="legacy_projection",
            )
            self.db.add(family)
            await self.db.flush()

        newest = max(group, key=lambda item: (item.version or 0, item.id or 0))
        version = await self._get_active_version(family.id)
        if version is None:
            version = FieldMappingTemplateVersion(
                family_id=family.id,
                version_no=newest.version or 1,
                status="active",
                template_name=newest.template_name,
                deduplication_fields=list(newest.deduplication_fields or []),
                header_bindings=list(newest.header_bindings or []),
                notes=newest.notes,
                legacy_template_ids=[template.id for template in group if template.id is not None],
                created_by=newest.created_by or "system",
            )
            self.db.add(version)
            await self.db.flush()
        else:
            version.version_no = newest.version or version.version_no
            version.template_name = newest.template_name
            _assign_if_changed(version, "deduplication_fields", list(newest.deduplication_fields or []))
            _assign_if_changed(version, "header_bindings", list(newest.header_bindings or []))
            version.notes = newest.notes
            _assign_if_changed(
                version,
                "legacy_template_ids",
                [template.id for template in group if template.id is not None],
            )

        existing_variants_result = await self.db.execute(
            select(FieldMappingTemplateVariant).where(
                FieldMappingTemplateVariant.template_version_id == version.id
            )
        )
        existing_variants = {
            variant.variant_key: variant for variant in existing_variants_result.scalars().all()
        }

        sorted_group = sorted(group, key=lambda item: (item.version or 0, item.id or 0), reverse=True)
        desired_variant_keys: set[str] = set()
        desired_variants: list[tuple[str, int, FieldMappingTemplate]] = []
        for index, template in enumerate(sorted_group):
            variant_key = build_projection_variant_key(
                template,
                existing_keys=desired_variant_keys,
            )
            desired_variant_keys.add(variant_key)
            desired_variants.append((variant_key, index, template))

        for variant_key, variant in list(existing_variants.items()):
            if variant_key not in desired_variant_keys:
                await self.db.delete(variant)
                existing_variants.pop(variant_key, None)

        for variant_key, index, template in desired_variants:
            variant = existing_variants.get(variant_key)
            if variant is None:
                variant = FieldMappingTemplateVariant(
                    template_version_id=version.id,
                    variant_key=variant_key,
                )
                self.db.add(variant)
            variant.match_priority = index + 1
            variant.header_row = template.header_row or 0
            variant.sheet_name_pattern = template.sheet_name
            _assign_if_changed(variant, "required_headers", _required_headers(template))
            _assign_if_changed(variant, "parse_profile", _build_parse_profile(template))
            _assign_if_changed(
                variant, "field_parse_rules", list(template.field_parse_rules or [])
            )
            variant.source_legacy_template_id = template.id
            variant.template_name = template.template_name

        family.active_version_id = version.id
        family.governance_status = "ready"
        family.display_name = self._build_display_name(platform, data_domain, sub_domain, granularity)

    async def _get_family(
        self,
        key: tuple[str, str, Optional[str], Optional[str], Optional[str]],
    ) -> Optional[FieldMappingTemplateFamily]:
        platform, data_domain, _sub_domain, _granularity, _account = key
        result = await self.db.execute(
            select(FieldMappingTemplateFamily).where(
                and_(
                    FieldMappingTemplateFamily.platform == platform,
                    FieldMappingTemplateFamily.data_domain == data_domain,
                )
            )
        )
        families = [
            family
            for family in result.scalars().all()
            if self._family_dimension_key(family) == key
        ]
        if not families:
            return None
        if len(families) > 1:
            logger.warning(
                "[TemplateFamily] duplicate family rows detected for key=%s count=%s",
                key,
                len(families),
            )
        return self._prefer_family_record(families)

    async def _get_active_version(self, family_id: int) -> Optional[FieldMappingTemplateVersion]:
        result = await self.db.execute(
            select(FieldMappingTemplateVersion).where(
                and_(
                    FieldMappingTemplateVersion.family_id == family_id,
                    FieldMappingTemplateVersion.status == "active",
                )
            )
        )
        versions = list(result.scalars().all())
        if not versions:
            return None
        if len(versions) > 1:
            logger.warning(
                "[TemplateFamily] multiple active versions detected for family_id=%s count=%s",
                family_id,
                len(versions),
            )
        return sorted(
            versions,
            key=lambda item: (item.version_no or 0, item.id or 0),
            reverse=True,
        )[0]

    async def ensure_projected_family(
        self,
        *,
        platform: str,
        data_domain: str,
        granularity: Optional[str] = None,
        sub_domain: Optional[str] = None,
        account: Optional[str] = None,
    ) -> Optional[FieldMappingTemplateFamily]:
        key = _dimension_key(platform, data_domain, sub_domain, granularity, account)
        family = await self._get_family(key)
        if family:
            return family

        await self.project_legacy_templates(platform=platform, data_domain=data_domain)
        return await self._get_family(key)

    async def list_families(
        self,
        *,
        platform: Optional[str] = None,
        data_domain: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        # [*] 目录缓存: 命中就不重算(也不再重复投影 + commit)
        cache = _cache_for(self.db)
        cache_key = f"list_families|{platform}|{data_domain}"
        cached = cache.get(cache_key)
        if cached is not None:
            return copy.deepcopy(cached)

        await self.project_legacy_templates(platform=platform, data_domain=data_domain)

        stmt = select(FieldMappingTemplateFamily)
        if platform:
            stmt = stmt.where(FieldMappingTemplateFamily.platform == platform)
        if data_domain:
            stmt = stmt.where(FieldMappingTemplateFamily.data_domain == data_domain)
        result = await self.db.execute(stmt)
        raw_families = list(result.scalars().all())
        grouped_families: dict[
            tuple[str, str, Optional[str], Optional[str], Optional[str]],
            list[FieldMappingTemplateFamily],
        ] = defaultdict(list)
        for family in raw_families:
            grouped_families[self._family_dimension_key(family)].append(family)
        families = [
            self._prefer_family_record(items)
            for items in grouped_families.values()
        ]
        payload: list[dict[str, Any]] = []
        for family in families:
            version = await self._get_active_version(family.id)
            variants_result = await self.db.execute(
                select(FieldMappingTemplateVariant).where(
                    FieldMappingTemplateVariant.template_version_id == (version.id if version else -1)
                )
                .order_by(FieldMappingTemplateVariant.match_priority.asc(), FieldMappingTemplateVariant.id.asc())
            )
            variants = list(variants_result.scalars().all())
            primary_variant = variants[0] if variants else None
            file_count_result = await self.db.execute(
                select(func.count(CatalogFile.id)).where(
                    and_(
                        CatalogFile.platform_code == family.platform,
                        CatalogFile.data_domain == family.data_domain,
                        CatalogFile.sub_domain == family.sub_domain,
                        CatalogFile.granularity == family.granularity,
                    )
                )
            )
            file_count = int(file_count_result.scalar() or 0)
            current_file_count_result = await self.db.execute(
                select(func.count(CatalogFile.id)).where(
                    and_(
                        CatalogFile.platform_code == family.platform,
                        CatalogFile.data_domain == family.data_domain,
                        CatalogFile.sub_domain == family.sub_domain,
                        CatalogFile.granularity == family.granularity,
                        CatalogFile.status.in_(["pending", "failed"]),
                    )
                )
            )
            current_file_count = int(current_file_count_result.scalar() or 0)
            pending_file_count_result = await self.db.execute(
                select(func.count(CatalogFile.id)).where(
                    and_(
                        CatalogFile.platform_code == family.platform,
                        CatalogFile.data_domain == family.data_domain,
                        CatalogFile.sub_domain == family.sub_domain,
                        CatalogFile.granularity == family.granularity,
                        CatalogFile.status == "pending",
                    )
                )
            )
            pending_file_count = int(pending_file_count_result.scalar() or 0)
            sample_file_result = await self.db.execute(
                select(CatalogFile).where(
                    and_(
                        CatalogFile.platform_code == family.platform,
                        CatalogFile.data_domain == family.data_domain,
                        CatalogFile.sub_domain == family.sub_domain,
                        CatalogFile.granularity == family.granularity,
                        CatalogFile.status.in_(["pending", "failed", "ingested"]),
                    )
                ).order_by(CatalogFile.first_seen_at.desc(), CatalogFile.id.desc()).limit(1)
            )
            sample_file = sample_file_result.scalar_one_or_none()
            legacy_template_ids = list(getattr(version, "legacy_template_ids", None) or [])
            payload.append(
                {
                    "id": family.id,
                    "platform": family.platform,
                    "data_domain": family.data_domain,
                    "granularity": family.granularity,
                    "account": family.account,
                    "sub_domain": family.sub_domain,
                    "display_name": family.display_name,
                    "governance_status": family.governance_status or "ready",
                    "display_governance_status": family.governance_status or "ready",
                    "variant_count": len(variants),
                    "file_count": current_file_count or pending_file_count or file_count,
                    "current_file_count": current_file_count,
                    "pending_file_count": pending_file_count,
                    "historical_file_count": file_count,
                    "active_template_id": (
                        primary_variant.source_legacy_template_id
                        if primary_variant and primary_variant.source_legacy_template_id
                        else legacy_template_ids[0] if legacy_template_ids else None
                    ),
                    "sample_file_id": sample_file.id if sample_file else None,
                    "sample_file_name": sample_file.file_name if sample_file else None,
                    "active_version": (
                        {
                            "id": version.id,
                            "version_no": version.version_no,
                            "status": version.status,
                            "template_name": version.template_name,
                        }
                        if version
                        else None
                    ),
                }
            )
        payload.sort(key=lambda item: (item["platform"], item["data_domain"], item["sub_domain"] or "", item["granularity"] or ""))
        cache.set(cache_key, payload)
        return payload

    async def get_family_versions(self, family_id: int) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        # [*] 目录缓存: 版本/变体是纯目录数据, 目录一变立即作废
        cache = _cache_for(self.db)
        cache_key = f"get_family_versions|{family_id}"
        cached = cache.get(cache_key)
        if cached is not None:
            family_cached, versions_cached = cached
            return copy.deepcopy(family_cached), copy.deepcopy(versions_cached)

        family = await self.db.get(FieldMappingTemplateFamily, family_id)
        if family is None:
            raise ValueError(f"template family {family_id} not found")
        families = await self.list_families(platform=family.platform, data_domain=family.data_domain)
        family_payload = next((item for item in families if item["id"] == family_id), None)
        if family_payload is None:
            logger.debug(
                "[TemplateFamily] requested family_id=%s hidden by normalized duplicate; using raw family row",
                family_id,
            )
            version = await self._get_active_version(family_id)
            variants: list[FieldMappingTemplateVariant] = []
            if version:
                variants_result = await self.db.execute(
                    select(FieldMappingTemplateVariant).where(
                        FieldMappingTemplateVariant.template_version_id == version.id
                    )
                    .order_by(FieldMappingTemplateVariant.match_priority.asc(), FieldMappingTemplateVariant.id.asc())
                )
                variants = list(variants_result.scalars().all())
            primary_variant = variants[0] if variants else None
            legacy_template_ids = list(getattr(version, "legacy_template_ids", None) or [])
            family_payload = {
                "id": family.id,
                "platform": family.platform,
                "data_domain": family.data_domain,
                "granularity": family.granularity,
                "account": family.account,
                "sub_domain": family.sub_domain,
                "display_name": family.display_name,
                "governance_status": family.governance_status or "ready",
                "display_governance_status": family.governance_status or "ready",
                "variant_count": len(variants),
                "file_count": 0,
                "current_file_count": 0,
                "pending_file_count": 0,
                "historical_file_count": 0,
                "active_template_id": (
                    primary_variant.source_legacy_template_id
                    if primary_variant and primary_variant.source_legacy_template_id
                    else legacy_template_ids[0] if legacy_template_ids else None
                ),
                "sample_file_id": None,
                "sample_file_name": None,
                "active_version": (
                    {
                        "id": version.id,
                        "version_no": version.version_no,
                        "status": version.status,
                        "template_name": version.template_name,
                    }
                    if version
                    else None
                ),
            }

        versions_result = await self.db.execute(
            select(FieldMappingTemplateVersion).where(
                FieldMappingTemplateVersion.family_id == family_id
            ).order_by(FieldMappingTemplateVersion.version_no.desc(), FieldMappingTemplateVersion.id.desc())
        )
        versions = list(versions_result.scalars().all())
        payload: list[dict[str, Any]] = []
        for version in versions:
            variants_result = await self.db.execute(
                select(FieldMappingTemplateVariant).where(
                    FieldMappingTemplateVariant.template_version_id == version.id
                )
            )
            variants = list(variants_result.scalars().all())
            required_semantic_keys, hash_participating_semantic_keys = _extract_semantic_key_sets(
                list(version.deduplication_fields or []),
                list(version.header_bindings or []),
            )
            payload.append(
                {
                    "id": version.id,
                    "family_id": version.family_id,
                    "version_no": version.version_no,
                    "status": version.status,
                    "template_name": version.template_name,
                    "deduplication_fields": list(version.deduplication_fields or []),
                    "required_semantic_keys": required_semantic_keys,
                    "hash_participating_semantic_keys": hash_participating_semantic_keys,
                    "header_bindings": list(version.header_bindings or []),
                    "notes": version.notes,
                    "variant_count": len(variants),
                    "created_by": version.created_by,
                    "created_at": version.created_at.isoformat() if version.created_at else None,
                    "legacy_template_ids": list(version.legacy_template_ids or []),
                }
            )
        cache.set(cache_key, (family_payload, payload))
        return family_payload, payload

    async def get_version_variants(self, version_id: int) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        # [*] 目录缓存: 变体是纯目录数据
        cache = _cache_for(self.db)
        cache_key = f"get_version_variants|{version_id}"
        cached = cache.get(cache_key)
        if cached is not None:
            version_cached, variants_cached = cached
            return copy.deepcopy(version_cached), copy.deepcopy(variants_cached)

        version = await self.db.get(FieldMappingTemplateVersion, version_id)
        if version is None:
            raise ValueError(f"template version {version_id} not found")
        family_payload, versions = await self.get_family_versions(version.family_id)
        version_payload = next(item for item in versions if item["id"] == version_id)
        variants_result = await self.db.execute(
            select(FieldMappingTemplateVariant).where(
                FieldMappingTemplateVariant.template_version_id == version_id
            ).order_by(FieldMappingTemplateVariant.match_priority.asc(), FieldMappingTemplateVariant.id.asc())
        )
        variants = list(variants_result.scalars().all())
        payload = [
            {
                "id": variant.id,
                "template_version_id": variant.template_version_id,
                "variant_key": variant.variant_key,
                "match_priority": variant.match_priority,
                "header_row": variant.header_row or 0,
                "sheet_name_pattern": variant.sheet_name_pattern,
                "required_headers": list(variant.required_headers or []),
                "parse_profile": dict(variant.parse_profile or {}),
                "field_parse_rules": list(variant.field_parse_rules or []),
                "source_legacy_template_id": variant.source_legacy_template_id,
                "template_name": variant.template_name,
                "created_at": variant.created_at.isoformat() if variant.created_at else None,
                "family": family_payload,
            }
            for variant in variants
        ]
        cache.set(cache_key, (version_payload, payload))
        return version_payload, payload

    @staticmethod
    def _build_display_name(
        platform: str,
        data_domain: str,
        sub_domain: Optional[str],
        granularity: Optional[str],
    ) -> str:
        return " / ".join(
            [
                platform,
                data_domain,
                sub_domain or "default",
                granularity or "any",
            ]
        )


def get_template_family_service(db: AsyncSession) -> TemplateFamilyService:
    return TemplateFamilyService(db)


class TemplateResolver:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.family_service = TemplateFamilyService(db)

    async def resolve(
        self,
        *,
        platform: str,
        data_domain: str,
        granularity: Optional[str] = None,
        sub_domain: Optional[str] = None,
        account: Optional[str] = None,
        header_row: Optional[int] = None,
        sheet_name: Optional[str] = None,
        header_columns: Optional[list[str]] = None,
        sample_rows: Optional[list[dict[str, Any]]] = None,
    ) -> dict[str, Any]:
        family = await self.family_service.ensure_projected_family(
            platform=platform,
            data_domain=data_domain,
            granularity=granularity,
            sub_domain=sub_domain,
            account=account,
        )
        if family is None:
            return {
                "matched": False,
                "governance_status": "missing_family",
                "family": None,
                "active_version": None,
                "variant": None,
                "semantic_bindings": [],
                "required_semantic_keys": [],
                "hash_participating_semantic_keys": [],
                "shadow_compare": await self._legacy_shadow_compare(
                    platform=platform,
                    data_domain=data_domain,
                    granularity=granularity,
                    sub_domain=sub_domain,
                    header_columns=header_columns or [],
                    sample_rows=sample_rows or [],
                    selected_variant=None,
                ),
            }

        family_payload, versions = await self.family_service.get_family_versions(family.id)
        active_version = next((item for item in versions if item["status"] == "active"), None)
        if active_version is None:
            return {
                "matched": False,
                "governance_status": "missing_variant",
                "family": family_payload,
                "active_version": None,
                "variant": None,
                "semantic_bindings": [],
                "required_semantic_keys": [],
                "hash_participating_semantic_keys": [],
                "shadow_compare": await self._legacy_shadow_compare(
                    platform=platform,
                    data_domain=data_domain,
                    granularity=granularity,
                    sub_domain=sub_domain,
                    header_columns=header_columns or [],
                    sample_rows=sample_rows or [],
                    selected_variant=None,
                ),
            }

        _version_payload, variants = await self.family_service.get_version_variants(active_version["id"])
        selected_variant = self._select_variant(
            variants=variants,
            header_row=header_row,
            sheet_name=sheet_name,
            header_columns=header_columns or [],
            sample_rows=sample_rows or [],
        )

        # [D7] 本 family 内没有匹配变体时 -> 跨 family 兜底(同 platform + 同 data_domain)。
        #
        # 导出格式不一定跟着粒度走: tiktok 商品导出实际只有一种表结构(176 列),
        # 但模板按粒度分别登记, monthly 的模板停留在旧版 38 列 ->
        # monthly 的文件在 family 27 里匹配不到任何变体, 永远判漂移。
        # 命中跨 family 变体时, 由它解释该文件, 并显式标注接管来源。
        takeover_report = None
        if selected_variant is None:
            takeover = await self._select_cross_family_variant(
                platform=platform,
                data_domain=data_domain,
                exclude_family_id=family.id,
                header_row=header_row,
                sheet_name=sheet_name,
                header_columns=header_columns or [],
                sample_rows=sample_rows or [],
                granularity=granularity,
                sub_domain=sub_domain,
                account=account,
            )
            if takeover is not None:
                selected_variant = takeover["variant"]
                takeover_report = takeover["report"]

        governance_status = "ready" if selected_variant else "missing_variant"
        shadow_compare = await self._legacy_shadow_compare(
            platform=platform,
            data_domain=data_domain,
            granularity=granularity,
            sub_domain=sub_domain,
            header_columns=header_columns or [],
            sample_rows=sample_rows or [],
            selected_variant=selected_variant,
        )
        semantic_bindings = list(active_version.get("header_bindings") or [])
        deduplication_fields = list(active_version.get("deduplication_fields") or [])
        field_parse_rules = list(active_version.get("field_parse_rules") or [])
        if selected_variant and selected_variant.get("source_legacy_template_id"):
            legacy_template = await self.db.get(
                FieldMappingTemplate,
                selected_variant["source_legacy_template_id"],
            )
            if legacy_template:
                semantic_bindings = list(legacy_template.header_bindings or [])
                deduplication_fields = list(legacy_template.deduplication_fields or [])
                field_parse_rules = list(legacy_template.field_parse_rules or [])
        required_semantic_keys, hash_participating_semantic_keys = _extract_semantic_key_sets(
            deduplication_fields,
            semantic_bindings,
        )
        return {
            "matched": selected_variant is not None,
            "governance_status": governance_status,
            "family": family_payload,
            "active_version": active_version,
            "variant": selected_variant,
            "semantic_bindings": semantic_bindings,
            "deduplication_fields": deduplication_fields,
            "field_parse_rules": field_parse_rules,
            "required_semantic_keys": required_semantic_keys,
            "hash_participating_semantic_keys": hash_participating_semantic_keys,
            "shadow_compare": shadow_compare,
            # [D7] 跨 family 变体接管: 非空表示本文件是由**其他粒度**的变体解释的
            "takeover": takeover_report,
            "takeover_flag": TAKEOVER_FLAG if takeover_report else None,
        }

    def _select_variant(
        self,
        *,
        variants: list[dict[str, Any]],
        header_row: Optional[int],
        sheet_name: Optional[str],
        header_columns: list[str],
        sample_rows: list[dict[str, Any]],
    ) -> Optional[dict[str, Any]]:
        candidates: list[tuple[int, int, dict[str, Any]]] = []
        normalized_headers = {str(column).strip().lower() for column in header_columns}
        for variant in variants:
            score = 0
            if header_row is not None and variant.get("header_row") == header_row:
                score += 3
            if variant.get("sheet_name_pattern") and sheet_name:
                if re.search(str(variant["sheet_name_pattern"]), sheet_name, flags=re.IGNORECASE):
                    score += 2
                else:
                    continue
            required_headers = {
                str(column).strip().lower() for column in (variant.get("required_headers") or [])
            }
            if required_headers:
                if not required_headers.issubset(normalized_headers):
                    continue
                score += 5
            if not _variant_matches_sample_rows(
                variant.get("field_parse_rules") or [],
                sample_rows,
            ):
                continue
            if sample_rows and variant.get("field_parse_rules"):
                score += 20
            candidates.append((score, int(variant.get("match_priority") or 100), variant))

        if not candidates:
            return None
        candidates.sort(key=lambda item: (-item[0], item[1], item[2]["id"]))
        return candidates[0][2]

    async def list_cross_family_variants(
        self,
        *,
        platform: str,
        data_domain: str,
        exclude_family_id: Optional[int] = None,
        exclude_granularity: Optional[str] = None,
        exclude_sub_domain: Optional[str] = None,
        exclude_account: Optional[str] = None,
        own_granularity: Optional[str] = None,
        own_sub_domain: Optional[str] = None,
        own_account: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        """列出同 platform + 同 data_domain 下**所有** family 的 active 版本变体。

        边界刻意收窄 —— 只允许同 ``platform`` + 同 ``data_domain``:
        不同平台的导出格式不可类比, 跨平台接管一定会误判。

        每项带 ``is_own_family`` 标记: 文件**自身所属**的 family 不算「其他 family」。
        接管的前提是「自己家解释不了」—— 自身 family 的变体必须优先,
        否则 monthly 的文件会被 daily 的变体抢走解释权。

        ``exclude_*`` 用于排除指定维度下的 family; ``own_*`` 用于标记自身 family。
        """
        # [*] 目录缓存: 跨族变体清单是纯目录数据
        cache = _cache_for(self.db)
        cache_key = (
            "list_cross_family_variants"
            f"|{platform}|{data_domain}|{exclude_family_id}|{exclude_granularity}"
            f"|{exclude_sub_domain}|{exclude_account}|{own_granularity}"
            f"|{own_sub_domain}|{own_account}"
        )
        cached = cache.get(cache_key)
        if cached is not None:
            return copy.deepcopy(cached)
        result = await self.db.execute(
            select(FieldMappingTemplateFamily).where(
                FieldMappingTemplateFamily.platform == platform,
                FieldMappingTemplateFamily.data_domain == data_domain,
            )
        )
        sibling_families = list(result.scalars().all())

        collected: list[dict[str, Any]] = []
        for sibling in sibling_families:
            if exclude_family_id is not None and sibling.id == exclude_family_id:
                continue
            if (
                exclude_granularity is not None
                and sibling.granularity == exclude_granularity
                and (sibling.sub_domain or None) == (exclude_sub_domain or None)
                and _account_dimension_matches(sibling.account, exclude_account)
            ):
                continue
            if sibling.active_version_id is None:
                continue

            family_payload, versions = await self.family_service.get_family_versions(
                sibling.id
            )
            active_version = next(
                (item for item in versions if item["status"] == "active"), None
            )
            if active_version is None:
                continue

            is_own_family = bool(
                own_granularity is not None
                and sibling.granularity == own_granularity
                and (sibling.sub_domain or None) == (own_sub_domain or None)
                and _account_dimension_matches(sibling.account, own_account)
            )

            _version_payload, variants = await self.family_service.get_version_variants(
                active_version["id"]
            )
            for variant in variants:
                collected.append(
                    {
                        "variant": variant,
                        "family": family_payload,
                        "version": active_version,
                        "is_own_family": is_own_family,
                    }
                )
        cache.set(cache_key, collected)
        return collected

    async def _select_cross_family_variant(
        self,
        *,
        platform: str,
        data_domain: str,
        exclude_family_id: Optional[int],
        header_row: Optional[int],
        sheet_name: Optional[str],
        header_columns: list[str],
        sample_rows: list[dict[str, Any]],
        granularity: Optional[str] = None,
        sub_domain: Optional[str] = None,
        account: Optional[str] = None,
    ) -> Optional[dict[str, Any]]:
        """跨 family 变体接管 (D7) —— 本 family 内没有匹配变体时的兜底。

        在**同 platform + 同 data_domain** 的其他 family 里找能解释当前文件的变体。
        命中门槛由 :mod:`backend.services.template_variant_takeover` 统一裁决:
        ``required_headers`` 匹配率 >= 95% 且缺失列 <= 1。

        表头行一致性
        ------------
        ``header_columns`` 是按**某个具体表头行**读出来的。变体各自声明了
        ``header_row``, 只有当两者一致时, 比对结果才有意义 ——
        否则是拿第 2 行的「全部.N」分组行去和第 3 行的真实指标名比对,
        匹配率必然是 0。

        注意: 这是**兜底**, 不是主路径。主路径是
        :mod:`backend.services.template_variant_takeover_service` 的表头行感知
        候选发现 —— 它会**按候选变体自己的 header_row 读表头**再评估。
        """
        candidates = await self.list_cross_family_variants(
            platform=platform,
            data_domain=data_domain,
            exclude_family_id=exclude_family_id,
            own_granularity=granularity,
            own_sub_domain=sub_domain,
            own_account=account,
        )
        evaluated: list[dict[str, Any]] = []
        for candidate in candidates:
            variant = candidate["variant"]
            if not _variant_header_row_matches(variant, header_row):
                continue
            decision = evaluate_variant_takeover(variant, header_columns)
            if decision is None:
                continue
            # 样本行校验: 与 family 内选择保持同一套硬约束
            if sample_rows and not _variant_matches_sample_rows(
                variant.get("field_parse_rules") or [], sample_rows
            ):
                continue
            evaluated.append({**candidate, "decision": decision})

        best = select_best_takeover(evaluated)
        if best is None:
            return None
        if best.get("is_own_family"):
            # 自家变体: 不是「接管」, 不应产出接管报告
            return {
                "variant": best["variant"],
                "decision": best["decision"],
                "report": None,
                "family": best.get("family"),
                "version": best.get("version"),
            }

        report = build_takeover_report(
            best["decision"],
            source_family=best["family"],
            source_version=best["version"],
        )
        return {
            "variant": best["variant"],
            "decision": best["decision"],
            "report": report,
            "family": best["family"],
            "version": best["version"],
        }

    async def _legacy_shadow_compare(
        self,
        *,
        platform: str,
        data_domain: str,
        granularity: Optional[str],
        sub_domain: Optional[str],
        header_columns: list[str],
        sample_rows: list[dict[str, Any]],
        selected_variant: Optional[dict[str, Any]],
    ) -> dict[str, Any]:
        stmt = select(FieldMappingTemplate).where(
            and_(
                FieldMappingTemplate.platform == platform,
                FieldMappingTemplate.data_domain == data_domain,
                FieldMappingTemplate.granularity == granularity,
                FieldMappingTemplate.sub_domain == sub_domain,
                FieldMappingTemplate.status == "published",
            )
        )
        result = await self.db.execute(stmt)
        templates = list(result.scalars().all())
        if not templates:
            return {
                "legacy_template_id": None,
                "legacy_template_name": None,
                "projected_variant_legacy_template_id": selected_variant.get("source_legacy_template_id") if selected_variant else None,
                "is_consistent": selected_variant is None,
            }

        selected_legacy = None
        if sample_rows:
            for template in sorted(templates, key=lambda item: (item.version or 0, item.id or 0), reverse=True):
                if _variant_matches_sample_rows(template.field_parse_rules or [], sample_rows):
                    selected_legacy = template
                    break
        if selected_legacy is None:
            selected_legacy = max(templates, key=lambda item: (item.version or 0, item.id or 0))

        projected_legacy_template_id = selected_variant.get("source_legacy_template_id") if selected_variant else None
        return {
            "legacy_template_id": selected_legacy.id,
            "legacy_template_name": selected_legacy.template_name,
            "projected_variant_legacy_template_id": projected_legacy_template_id,
            "is_consistent": selected_legacy.id == projected_legacy_template_id,
        }


def get_template_resolver(db: AsyncSession) -> TemplateResolver:
    return TemplateResolver(db)
