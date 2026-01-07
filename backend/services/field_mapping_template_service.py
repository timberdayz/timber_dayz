#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
字段映射模板服务 - v4.3.7阶段C
模板学习与版本化管理
"""

from typing import List, Dict, Optional
from sqlalchemy.orm import Session
from sqlalchemy import select, and_, desc
from modules.core.db import (
    FieldMappingTemplate,
    # FieldMappingTemplateItem,  # v4.6.0移除：不再使用明细表，改用header_columns JSONB
)
from modules.core.logger import get_logger
from datetime import datetime
from backend.services.deduplication_fields_config import get_default_deduplication_fields

logger = get_logger(__name__)


class FieldMappingTemplateService:
    """字段映射模板服务"""
    
    def __init__(self, db: Session):
        self.db = db
    
    def save_template(
        self,
        platform: str,
        data_domain: str,
        header_columns: List[str],  # v4.6.0修改：改为原始表头字段列表
        granularity: str = None,
        account: str = None,
        template_name: str = None,
        created_by: str = 'user',
        # v4.5.1新增参数
        header_row: int = 0,
        sub_domain: str = None,
        sheet_name: str = None,
        encoding: str = 'utf-8',
        # v4.14.0新增参数
        deduplication_fields: Optional[List[str]] = None  # 核心去重字段列表（可选）
    ) -> int:
        """
        保存映射模板（v4.6.0重构版 + v4.14.0增强）
        
        v4.6.0变更：
        - 不再保存字段映射关系（FieldMappingTemplateItem）
        - 改为保存原始表头字段列表（header_columns JSONB）
        - 匹配逻辑基于原始表头字段列表
        
        v4.14.0新增：
        - 支持保存核心去重字段列表（deduplication_fields）
        - 如果用户未指定，使用默认核心字段配置
        
        Args:
            platform: 平台代码
            data_domain: 数据域
            header_columns: 原始表头字段列表（v4.6.0新增）
            granularity: 粒度（可选）
            account: 账号（可选）
            template_name: 模板名称（可选）
            created_by: 创建人
            header_row: 表头行索引（v4.5.1新增，默认0）
            sub_domain: 子数据类型（v4.5.1新增，如ai_assistant/agent）
            sheet_name: Excel工作表名称（v4.5.1新增）
            encoding: 文件编码（v4.5.1新增，默认utf-8）
            deduplication_fields: 核心去重字段列表（v4.14.0新增，可选）
            
        Returns:
            template_id: 新创建的模板ID
        """
        try:
            # 验证header_row范围（企业级数据治理标准）
            if not (0 <= header_row <= 100):
                raise ValueError(f"header_row必须在0-100之间，当前值: {header_row}")
            
            # 验证header_columns
            if not header_columns or not isinstance(header_columns, list):
                raise ValueError(f"header_columns必须是非空列表，当前值: {header_columns}")
            
            # v4.14.0新增：处理deduplication_fields
            # 如果用户未指定，使用默认核心字段配置
            if deduplication_fields is None:
                deduplication_fields = get_default_deduplication_fields(data_domain, sub_domain)
                logger.debug(f"[Template] 使用默认核心字段配置: {deduplication_fields}")
            elif not isinstance(deduplication_fields, list):
                raise ValueError(f"deduplication_fields必须是列表，当前值: {deduplication_fields}")
            
            # 查找是否已有同维度的published模板（v4.5.1扩展：包含sub_domain）
            existing = self.db.execute(
                select(FieldMappingTemplate).where(
                    and_(
                        FieldMappingTemplate.platform == platform,
                        FieldMappingTemplate.data_domain == data_domain,
                        FieldMappingTemplate.granularity == granularity,
                        FieldMappingTemplate.sub_domain == sub_domain,
                        FieldMappingTemplate.account == account,
                        FieldMappingTemplate.status == 'published'
                    )
                )
            ).scalar_one_or_none()
            
            # 计算新版本号
            if existing:
                new_version = existing.version + 1
                # 将旧版本归档
                existing.status = 'archived'
                self.db.add(existing)
            else:
                new_version = 1
            
            # 创建新模板（v4.6.0：保存header_columns JSONB + v4.14.0：保存deduplication_fields）
            template = FieldMappingTemplate(
                platform=platform,
                data_domain=data_domain,
                granularity=granularity,
                account=account,
                sub_domain=sub_domain,  # v4.5.1新增
                header_row=header_row,  # v4.5.1新增
                sheet_name=sheet_name,  # v4.5.1新增
                encoding=encoding,  # v4.5.1新增
                header_columns=header_columns,  # v4.6.0新增：原始表头字段列表
                deduplication_fields=deduplication_fields,  # v4.14.0新增：核心去重字段列表
                template_name=template_name or f"{platform}_{data_domain}_{sub_domain or ''}_{granularity}_v{new_version}",
                version=new_version,
                status='published',
                field_count=len(header_columns),  # v4.6.0：使用header_columns长度
                usage_count=0,
                success_rate=0.0,
                created_by=created_by,
                notes=f"DSS架构重构（v4.6.0）+ 核心字段去重（v4.14.0）"
            )
            
            self.db.add(template)
            self.db.commit()
            
            logger.info(f"[Template] 保存成功: {template.template_name} (ID={template.id}, {len(header_columns)}个字段)")
            return template.id
            
        except Exception as e:
            self.db.rollback()
            logger.error(f"[Template] 保存失败: {e}")
            raise
    
    def list_templates(
        self,
        platform: str = None,
        data_domain: str = None,
        status: str = 'published'
    ) -> List[Dict]:
        """
        列出模板
        
        Args:
            platform: 平台过滤
            data_domain: 数据域过滤
            status: 状态过滤（published/archived/draft）
            
        Returns:
            模板列表
        """
        try:
            stmt = select(FieldMappingTemplate)
            
            if platform:
                stmt = stmt.where(FieldMappingTemplate.platform == platform)
            
            if data_domain:
                stmt = stmt.where(FieldMappingTemplate.data_domain == data_domain)
            
            if status:
                stmt = stmt.where(FieldMappingTemplate.status == status)
            
            # 按创建时间倒序
            stmt = stmt.order_by(desc(FieldMappingTemplate.created_at))
            
            templates = self.db.execute(stmt).scalars().all()
            
            result = []
            for tmpl in templates:
                result.append({
                    "id": tmpl.id,
                    "platform": tmpl.platform,
                    "data_domain": tmpl.data_domain,
                    "granularity": tmpl.granularity,
                    "account": tmpl.account,
                    "sub_domain": tmpl.sub_domain,  # v4.5.1新增
                    "header_row": tmpl.header_row or 0,  # v4.5.1新增
                    "sheet_name": tmpl.sheet_name,  # v4.5.1新增
                    "encoding": tmpl.encoding or 'utf-8',  # v4.5.1新增
                    "template_name": tmpl.template_name,
                    "version": tmpl.version,
                    "status": tmpl.status,
                    "field_count": tmpl.field_count,
                    "deduplication_fields": tmpl.deduplication_fields if hasattr(tmpl, 'deduplication_fields') and tmpl.deduplication_fields else [],  # v4.14.0新增：核心字段列表
                    "usage_count": tmpl.usage_count,
                    "success_rate": tmpl.success_rate,
                    "created_by": tmpl.created_by,
                    "created_at": tmpl.created_at.isoformat() if tmpl.created_at else None
                })
            
            logger.info(f"[Template] 列出模板: 找到{len(result)}个")
            return result
            
        except Exception as e:
            logger.error(f"[Template] 列出失败: {e}")
            return []
    
    def get_template(self, template_id: int) -> Optional[Dict]:
        """
        获取模板详情（v4.6.0重构版）
        
        v4.6.0变更：
        - 不再查询FieldMappingTemplateItem表
        - 改为返回header_columns数组
        """
        try:
            template = self.db.get(FieldMappingTemplate, template_id)
            
            if not template:
                return None
            
            # v4.6.0：从header_columns JSONB读取原始表头字段列表
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
                    "encoding": template.encoding or 'utf-8',
                    "template_name": template.template_name,
                    "version": template.version,
                    "field_count": template.field_count or len(header_columns),
                    "status": template.status
                },
                "header_columns": header_columns  # v4.6.0：返回原始表头字段列表
            }
            
        except Exception as e:
            logger.error(f"[Template] 获取失败: {e}")
            return None
    
    def apply_template(
        self,
        template_id: int,
        current_columns: List[str]
    ) -> Dict:
        """
        应用模板到当前文件（v4.6.0重构版）
        
        v4.6.0变更：
        - 基于header_columns进行匹配
        - 如果当前文件的列名与模板的header_columns匹配，则认为可以使用该模板
        
        Args:
            template_id: 模板ID
            current_columns: 当前文件的列名列表
            
        Returns:
            {
                "header_columns": [模板的原始表头字段列表],
                "matched": 匹配数,
                "unmatched": 未匹配数,
                "unmatched_columns": [未匹配的列名],
                "match_rate": 匹配率
            }
        """
        import re
        
        try:
            template_data = self.get_template(template_id)
            
            if not template_data:
                raise ValueError("模板不存在")
            
            template_header_columns = template_data.get('header_columns', [])
            
            # 应用模板：基于原始表头字段列表进行匹配
            matched = 0
            unmatched_columns = []
            
            # 创建模板字段的标准化集合（用于模糊匹配）
            template_normalized = {
                re.sub(r'[\s_\-()（）]', '', col.lower()): col
                for col in template_header_columns
            }
            
            for col in current_columns:
                # 1. 精确匹配
                if col in template_header_columns:
                    matched += 1
                else:
                    # 2. 模糊匹配（去除空格、特殊字符）
                    col_normalized = re.sub(r'[\s_\-()（）]', '', col.lower())
                    if col_normalized in template_normalized:
                        matched += 1
                    else:
                        unmatched_columns.append(col)
            
            # 更新使用次数
            template = self.db.get(FieldMappingTemplate, template_id)
            if template:
                template.usage_count += 1
                self.db.commit()
            
            match_rate = round(matched / len(current_columns) * 100, 1) if current_columns else 0
            logger.info(f"[Template] 应用模板{template_id}: {matched}/{len(current_columns)}匹配 ({match_rate}%)")
            
            return {
                "header_columns": template_header_columns,
                "matched": matched,
                "unmatched": len(unmatched_columns),
                "unmatched_columns": unmatched_columns,
                "match_rate": match_rate
            }
            
        except Exception as e:
            logger.error(f"[Template] 应用失败: {e}")
            raise
    
    def delete_template(self, template_id: int) -> bool:
        """
        删除模板
        
        Args:
            template_id: 模板ID
            
        Returns:
            bool: 是否删除成功
        """
        try:
            template = self.db.get(FieldMappingTemplate, template_id)
            
            if not template:
                logger.warning(f"[Template] 删除失败: 模板{template_id}不存在")
                return False
            
            # 删除模板
            self.db.delete(template)
            self.db.commit()
            
            logger.info(f"[Template] 删除成功: {template.template_name} (ID={template_id})")
            return True
            
        except Exception as e:
            self.db.rollback()
            logger.error(f"[Template] 删除失败: {e}")
            raise


def get_template_service(db: Session) -> FieldMappingTemplateService:
    """获取模板服务实例"""
    return FieldMappingTemplateService(db)

