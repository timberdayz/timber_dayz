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
from backend.services.template_family_service import _normalize_dimension
from modules.core.db import FieldMappingTemplate
from modules.core.logger import get_logger

logger = get_logger(__name__)
VERSION_SUFFIX_PATTERN = re.compile(r"_v\d+$")

#: 家族投影状态(写入保存响应)
PROJECTION_STATUS_PROJECTED = "projected"
PROJECTION_STATUS_FAILED = "failed"
PROJECTION_STATUS_SKIPPED = "skipped"


class TemplateFamilyProjectionError(RuntimeError):
    """模板家族投影失败。

    保存模板 = 「归档旧模板 + 插入新模板 + 家族投影」**同一个事务**。
    投影失败 ⇒ 整体回滚 ⇒ 必须用**可区分**的异常类型抛出去,
    由路由层翻译成明确错误码(不能泛化成 500)。
    """

    def __init__(self, message: str, *, cause: Optional[BaseException] = None) -> None:
        super().__init__(message)
        self.cause = cause


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
        header_bindings: Optional[List[Dict[str, Any]]] = None,
        field_parse_rules: Optional[List[Dict[str, Any]]] = None,
        save_mode: str = "create",
        base_template_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """保存模板(归档旧版本 + 插入新版本 + 家族投影, **同一个事务**)。

        [*] 第 3 批 3.1: 以前是「先 commit 模板, 再单独 commit 投影」,
        于是有两种坏状态:
          A. 写库成功但接口报 500(用户以为失败, 模板其实已改);
          B. 接口报成功但没投影(家族目录与真实模板对不上)。
        现在三步合并进一个事务: 投影失败 ⇒ 整体回滚 ⇒ 抛
        :class:`TemplateFamilyProjectionError`。
        """
        try:
            sub_domain = _normalize_dimension(sub_domain)
            account = _normalize_dimension(account)
            granularity = _normalize_dimension(granularity)
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

            # [*] 同维度可能存在多个 published 模板(历史脏数据)。
            # 用 scalar_one_or_none() 会在这种数据上直接抛 MultipleResultsFound,
            # 导致「保存模板」接口整体 500; 这里改成全量取出并全部归档。
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
            existing_templates = list(existing_result.scalars().all())

            new_version = 1
            if existing_templates:
                new_version = max(
                    (item.version or 0) for item in existing_templates
                ) + 1

            current_time = datetime.now(timezone.utc)
            resolved_template_name = self._resolve_template_name(
                platform=platform,
                data_domain=data_domain,
                sub_domain=sub_domain,
                granularity=granularity,
                template_name=template_name,
                version=new_version,
            )

            # [*] 结束读取阶段可能已经开启的隐式事务(只有读操作),
            #     让下面的 `db.begin()` 能开出一个**干净**的事务。
            #     get_async_db 会在请求结束时再 commit 一次 —— 这里不重复提交业务数据。
            if self.db.in_transaction():
                await self.db.commit()

            archived_template_id: Optional[int] = None
            projection_family_id: Optional[int] = None
            projection_version_id: Optional[int] = None

            try:
                async with self.db.begin():
                    if existing_templates:
                        for existing in existing_templates:
                            existing.status = "archived"
                            existing.updated_at = current_time
                            self.db.add(existing)
                        archived_template_id = existing_templates[0].id

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
                        header_bindings=header_bindings,
                        field_parse_rules=field_parse_rules,
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
                    await self.db.flush()

                    # [*] 家族投影: 与模板写入**同一个事务**。
                    #     commit=False —— 提交权归外层事务。
                    try:
                        projection_family_id, projection_version_id = await self._project_family(
                            platform=platform,
                            data_domain=data_domain,
                            granularity=granularity,
                            sub_domain=sub_domain,
                            account=account,
                        )
                    except TemplateFamilyProjectionError:
                        raise
                    except Exception as exc:  # noqa: BLE001 - 统一成可区分的异常类型
                        raise TemplateFamilyProjectionError(
                            f"模板家族投影失败: {exc}",
                            cause=exc,
                        ) from exc
            except TemplateFamilyProjectionError:
                await self.db.rollback()
                logger.error(
                    "[Template] 家族投影失败, 已回滚本次保存: platform=%s, domain=%s",
                    platform,
                    data_domain,
                )
                raise
            except Exception as exc:
                await self.db.rollback()
                logger.error(f"[Template] 保存失败: {exc}")
                raise

            await self.db.refresh(template)

            logger.info(
                f"[Template] 保存成功: {template.template_name} (ID={template.id}, {len(header_columns)}个字段), "
                f"family_id={projection_family_id}, active_version_id={projection_version_id}"
            )
            return {
                "template_id": template.id,
                "template_name": template.template_name,
                "version": template.version,
                "operation": "new_version" if archived_template_id else "created",
                "archived_template_id": archived_template_id,
                "save_mode": save_mode,
                "base_template_id": base_template_id,
                "family_id": projection_family_id,
                "active_version_id": projection_version_id,
                "projection_status": PROJECTION_STATUS_PROJECTED,
            }
        except Exception as exc:
            await self.db.rollback()
            logger.error(f"[Template] 保存失败: {exc}")
            raise

    async def _project_family(
        self,
        *,
        platform: str,
        data_domain: str,
        granularity: Optional[str] = None,
        sub_domain: Optional[str] = None,
        account: Optional[str] = None,
    ) -> tuple[Optional[int], Optional[int]]:
        """在当前事务里投影模板家族。

        失败时抛 :class:`TemplateFamilyProjectionError` —— 调用方据此回滚整个事务。
        """
        from backend.services.template_family_service import get_template_family_service

        try:
            projection = await get_template_family_service(self.db).project_legacy_templates(
                platform=platform,
                data_domain=data_domain,
                commit=False,
            )
        except TemplateFamilyProjectionError:
            raise
        except Exception as exc:  # noqa: BLE001 - 统一转成可区分的异常类型
            raise TemplateFamilyProjectionError(
                f"模板家族投影失败: {exc}",
                cause=exc,
            ) from exc

        families = projection.get("families") or []
        # [*] 只取本次保存所命中的那个维度(严格 5 维)
        target_key = (
            str(platform).strip(),
            str(data_domain).strip(),
            sub_domain,
            granularity,
            account,
        )
        target = None
        for item in families:
            if tuple(item.get("key") or ()) == target_key:
                target = item
                break
        if target is None:
            return None, None
        return target.get("family_id"), target.get("active_version_id")

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
                        "header_bindings": tmpl.header_bindings or [],
                        "field_parse_rules": tmpl.field_parse_rules or [],
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
                    "header_bindings": template.header_bindings or [],
                    "field_parse_rules": template.field_parse_rules or [],
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
        """删除模板 = **归档 + 重投影**(第 3 批 3.6)。

        以前是硬删(``db.delete`` + commit), 后果是:

        * 家族目录完全不知道模板没了 —— ``active_version_id`` 还挂着,
          变体还指向已经不存在的模板行;
        * resolver 仍然报 ``matched=True / governance_status='ready'``,
          而入库判定走模板匹配得到「没有模板」⇒ **同一文件两处结论相反**。

        现在: 模板行保留(status='archived'), 家族目录重投影,
        该维度若已无 published 模板 ⇒ 家族标记 ``missing_template``
        且清空 ``active_version_id``。
        """
        template = await self.db.get(FieldMappingTemplate, template_id)
        if not template:
            logger.warning(f"[Template] 删除失败: 模板{template_id}不存在")
            return False

        try:
            if self.db.in_transaction():
                await self.db.commit()

            async with self.db.begin():
                template.status = "archived"
                template.updated_at = datetime.now(timezone.utc)
                self.db.add(template)
                await self.db.flush()

                # [*] 重投影: 让家族目录反映「该维度已无 published 模板」
                await self._reproject_family(
                    platform=template.platform,
                    data_domain=template.data_domain,
                )

            logger.info(
                f"[Template] 删除成功(已归档): {template.template_name} (ID={template_id})"
            )
            return True
        except TemplateFamilyProjectionError:
            await self.db.rollback()
            logger.error(
                "[Template] 删除失败: 家族重投影失败, 已回滚归档: template_id=%s", template_id
            )
            raise
        except Exception as exc:
            await self.db.rollback()
            logger.error(f"[Template] 删除失败: {exc}")
            raise

    async def _reproject_family(
        self,
        *,
        platform: str,
        data_domain: str,
    ) -> None:
        """在当前事务里重投影模板家族(删除/归档模板后调用)。"""
        from backend.services.template_family_service import get_template_family_service

        try:
            await get_template_family_service(self.db).project_legacy_templates(
                platform=platform,
                data_domain=data_domain,
                commit=False,
            )
        except TemplateFamilyProjectionError:
            raise
        except Exception as exc:  # noqa: BLE001 - 统一转成可区分的异常类型
            raise TemplateFamilyProjectionError(
                f"模板家族重投影失败: {exc}",
                cause=exc,
            ) from exc


def get_template_service(db: AsyncSession) -> FieldMappingTemplateService:
    """获取模板服务实例"""
    return FieldMappingTemplateService(db)
