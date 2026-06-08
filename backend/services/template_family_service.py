from __future__ import annotations

import hashlib
import re
from collections import defaultdict
from typing import Any, Dict, Iterable, Optional

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.services.semantic_field_registry import is_canonical_semantic_key, normalize_semantic_key
from modules.core.db import (
    CatalogFile,
    FieldMappingTemplate,
    FieldMappingTemplateFamily,
    FieldMappingTemplateVariant,
    FieldMappingTemplateVersion,
)
from modules.core.logger import get_logger

logger = get_logger(__name__)


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
    raw_value = str(row.get(source_column, "") or "").strip()
    if not raw_value:
        return False

    date_format = str(rule.get("date_format", "")).lower()
    if "/" in date_format and "/" in raw_value:
        return True
    if "-" in date_format and "/" not in raw_value and "-" in raw_value:
        return True
    return False


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
            version.deduplication_fields = list(newest.deduplication_fields or [])
            version.header_bindings = list(newest.header_bindings or [])
            version.notes = newest.notes
            version.legacy_template_ids = [template.id for template in group if template.id is not None]

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
            variant.required_headers = _required_headers(template)
            variant.parse_profile = _build_parse_profile(template)
            variant.field_parse_rules = list(template.field_parse_rules or [])
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
        return payload

    async def get_family_versions(self, family_id: int) -> tuple[dict[str, Any], list[dict[str, Any]]]:
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
        return family_payload, payload

    async def get_version_variants(self, version_id: int) -> tuple[dict[str, Any], list[dict[str, Any]]]:
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
