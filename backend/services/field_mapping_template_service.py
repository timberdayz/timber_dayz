#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
字段映射模板服务
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import and_, desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.services.deduplication_fields_config import get_default_deduplication_fields
from modules.core.db import FieldMappingTemplate
from modules.core.logger import get_logger

logger = get_logger(__name__)
VERSION_SUFFIX_PATTERN = re.compile(r"_v\d+$")


class FieldMappingTemplateService:
    """字段映射模板服务"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def save_template(
        self,
        platform: str,
        data_domain: str,
        header_columns: List[str],
        granularity: str = None,
        account: str = None,
        template_name: str = None,
        created_by: str = "user",
        header_row: int = 0,
        sub_domain: str = None,
        sheet_name: str = None,
        encoding: str = "utf-8",
        deduplication_fields: Optional[List[str]] = None,
        save_mode: str = "create",
        base_template_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        try:
            if not (0 <= header_row <= 100):
                raise ValueError(f"header_row必须在0-100之间, 当前值: {header_row}")

            if not header_columns or not isinstance(header_columns, list):
                raise ValueError(f"header_columns必须是非空列表, 当前值: {header_columns}")

            if deduplication_fields is None:
                deduplication_fields = get_default_deduplication_fields(data_domain, sub_domain)
                logger.debug(f"[Template] 使用默认核心字段配置: {deduplication_fields}")
            elif not isinstance(deduplication_fields, list):
                raise ValueError(
                    f"deduplication_fields必须是列表, 当前值: {deduplication_fields}"
                )

            existing_result = await self.db.execute(
                select(FieldMappingTemplate).where(
                    and_(
                        FieldMappingTemplate.platform == platform,
                        FieldMappingTemplate.data_domain == data_domain,
                        FieldMappingTemplate.granularity == granularity,
                        FieldMappingTemplate.sub_domain == sub_domain,
                        FieldMappingTemplate.account == account,
                        FieldMappingTemplate.status == "published",
                    )
                )
            )
            existing = existing_result.scalar_one_or_none()

            archived_template_id = None
            if existing:
                new_version = existing.version + 1
                existing.status = "archived"
                existing.updated_at = datetime.now(timezone.utc)
                self.db.add(existing)
                archived_template_id = existing.id
            else:
                new_version = 1

            current_time = datetime.now(timezone.utc)
            resolved_template_name = self._resolve_template_name(
                platform=platform,
                data_domain=data_domain,
                sub_domain=sub_domain,
                granularity=granularity,
                template_name=template_name,
                version=new_version,
            )

            template = FieldMappingTemplate(
                platform=platform,
                data_domain=data_domain,
                granularity=granularity,
                account=account,
                sub_domain=sub_domain,
                header_row=header_row,
                sheet_name=sheet_name,
                encoding=encoding,
                header_columns=header_columns,
                deduplication_fields=deduplication_fields,
                template_name=resolved_template_name,
                version=new_version,
                status="published",
                field_count=len(header_columns),
                usage_count=0,
                success_rate=0.0,
                created_by=created_by,
                created_at=current_time,
                updated_at=current_time,
                notes="DSS架构重构(v4.6.0)+ 核心字段去重(v4.14.0)",
            )

            self.db.add(template)
            await self.db.commit()
            await self.db.refresh(template)

            logger.info(
                f"[Template] 保存成功: {template.template_name} (ID={template.id}, {len(header_columns)}个字段)"
            )
            return {
                "template_id": template.id,
                "template_name": template.template_name,
                "version": template.version,
                "operation": "new_version" if archived_template_id else "created",
                "archived_template_id": archived_template_id,
                "save_mode": save_mode,
                "base_template_id": base_template_id,
            }
        except Exception as exc:
            await self.db.rollback()
            logger.error(f"[Template] 保存失败: {exc}")
            raise

    @staticmethod
    def _resolve_template_name(
        platform: str,
        data_domain: str,
        sub_domain: Optional[str],
        granularity: Optional[str],
        template_name: Optional[str],
        version: int,
    ) -> str:
        default_name = f"{platform}_{data_domain}_{sub_domain or ''}_{granularity}_v{version}"
        if not template_name:
            return default_name
        if VERSION_SUFFIX_PATTERN.search(template_name):
            return VERSION_SUFFIX_PATTERN.sub(f"_v{version}", template_name)
        return template_name

    async def list_templates(
        self,
        platform: str = None,
        data_domain: str = None,
        status: str = "published",
    ) -> List[Dict[str, Any]]:
        try:
            stmt = select(FieldMappingTemplate)

            if platform:
                stmt = stmt.where(FieldMappingTemplate.platform == platform)
            if data_domain:
                stmt = stmt.where(FieldMappingTemplate.data_domain == data_domain)
            if status:
                stmt = stmt.where(FieldMappingTemplate.status == status)

            stmt = stmt.order_by(desc(FieldMappingTemplate.created_at))

            result = await self.db.execute(stmt)
            templates = result.scalars().all()

            payload: List[Dict[str, Any]] = []
            for tmpl in templates:
                payload.append(
                    {
                        "id": tmpl.id,
                        "platform": tmpl.platform,
                        "data_domain": tmpl.data_domain,
                        "granularity": tmpl.granularity,
                        "account": tmpl.account,
                        "sub_domain": tmpl.sub_domain,
                        "header_row": tmpl.header_row or 0,
                        "sheet_name": tmpl.sheet_name,
                        "encoding": tmpl.encoding or "utf-8",
                        "template_name": tmpl.template_name,
                        "version": tmpl.version,
                        "status": tmpl.status,
                        "field_count": tmpl.field_count,
                        "deduplication_fields": tmpl.deduplication_fields or [],
                        "usage_count": tmpl.usage_count,
                        "success_rate": tmpl.success_rate,
                        "created_by": tmpl.created_by,
                        "created_at": tmpl.created_at.isoformat() if tmpl.created_at else None,
                    }
                )

            logger.info(f"[Template] 列出模板: 找到{len(payload)}个")
            return payload
        except Exception as exc:
            logger.error(f"[Template] 列出失败: {exc}")
            return []

    async def get_template(self, template_id: int) -> Optional[Dict[str, Any]]:
        try:
            template = await self.db.get(FieldMappingTemplate, template_id)
            if not template:
                return None

            header_columns = template.header_columns or []
            return {
                "template": {
                    "id": template.id,
                    "platform": template.platform,
                    "data_domain": template.data_domain,
                    "granularity": template.granularity,
                    "sub_domain": template.sub_domain,
                    "header_row": template.header_row or 0,
                    "sheet_name": template.sheet_name,
                    "encoding": template.encoding or "utf-8",
                    "template_name": template.template_name,
                    "version": template.version,
                    "field_count": template.field_count or len(header_columns),
                    "status": template.status,
                    "deduplication_fields": template.deduplication_fields or [],
                },
                "header_columns": header_columns,
            }
        except Exception as exc:
            logger.error(f"[Template] 获取失败: {exc}")
            return None

    async def apply_template(
        self,
        template_id: int,
        current_columns: List[str],
    ) -> Dict[str, Any]:
        try:
            template_data = await self.get_template(template_id)
            if not template_data:
                raise ValueError("模板不存在")

            template_header_columns = template_data.get("header_columns", [])
            matched = 0
            unmatched_columns = []

            template_normalized = {
                re.sub(r"[\s_\-()（）]", "", col.lower()): col for col in template_header_columns
            }

            for column in current_columns:
                if column in template_header_columns:
                    matched += 1
                    continue

                normalized = re.sub(r"[\s_\-()（）]", "", column.lower())
                if normalized in template_normalized:
                    matched += 1
                else:
                    unmatched_columns.append(column)

            template = await self.db.get(FieldMappingTemplate, template_id)
            if template:
                template.usage_count += 1
                template.updated_at = datetime.now(timezone.utc)
                await self.db.commit()

            match_rate = round(matched / len(current_columns) * 100, 1) if current_columns else 0
            logger.info(
                f"[Template] 应用模板{template_id}: {matched}/{len(current_columns)}匹配 ({match_rate}%)"
            )

            return {
                "header_columns": template_header_columns,
                "matched": matched,
                "unmatched": len(unmatched_columns),
                "unmatched_columns": unmatched_columns,
                "match_rate": match_rate,
            }
        except Exception as exc:
            logger.error(f"[Template] 应用失败: {exc}")
            raise

    async def delete_template(self, template_id: int) -> bool:
        try:
            template = await self.db.get(FieldMappingTemplate, template_id)
            if not template:
                logger.warning(f"[Template] 删除失败: 模板{template_id}不存在")
                return False

            await self.db.delete(template)
            await self.db.commit()
            logger.info(f"[Template] 删除成功: {template.template_name} (ID={template_id})")
            return True
        except Exception as exc:
            await self.db.rollback()
            logger.error(f"[Template] 删除失败: {exc}")
            raise


def get_template_service(db: AsyncSession) -> FieldMappingTemplateService:
    """获取模板服务实例"""
    return FieldMappingTemplateService(db)
