#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
统一模板匹配服务（SSOT）

v4.5.0新增：
- 提供统一的模板查找和应用逻辑
- 避免手动映射和自动入库的重复逻辑
- 确保模板选择策略一致性

v4.18.2新增：
- 支持异步会话（AsyncSession）
- 双模式设计：同步/异步自动检测

调用方：
- FieldMappingEnhanced.vue（手动映射）
- auto_ingest_orchestrator.py（自动入库）
"""

from typing import Optional, Dict, List, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, or_
from datetime import datetime

from modules.core.db import FieldMappingTemplate
# FieldMappingTemplateItem,  # v4.6.0移除：不再使用明细表，改用header_columns JSONB
from modules.core.logger import get_logger
from backend.services.currency_extractor import get_currency_extractor  # ⭐ v4.15.0新增

logger = get_logger(__name__)


class TemplateMatcher:
    """
    统一模板匹配服务
    
    核心原则：
    - 精确匹配：(platform, data_domain, granularity)
    - 状态筛选：status = 'published'（只用已发布模板）
    - 版本选择：MAX(version)（最新版本）
    - 忽略sub_domain：宽松匹配，提高覆盖率
    
    v4.18.2新增：
    - 支持异步会话（AsyncSession）
    v4.19.0更新：
    - 移除同步/异步双模式支持，统一为异步架构
    """
    
    def __init__(self, db: AsyncSession):
        """
        初始化模板匹配器
        
        Args:
            db: 异步数据库会话（AsyncSession）
        """
        self.db = db
    
    @staticmethod
    def _match_dimension(column, value: Optional[str]):
        """
        构造维度匹配条件

        Treat empty string as None so that 用户保存的空值和实际None一致.
        """
        if value is None:
            return or_(column.is_(None), column == "")
        return column == value

    def _normalize_dimension(self, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        value = str(value).strip()
        return value or None

    async def find_best_template(
        self, 
        platform: str, 
        data_domain: str, 
        granularity: str = None,
        sub_domain: str = None  # v4.5.1启用：支持子数据类型识别
    ) -> Optional[FieldMappingTemplate]:
        """
        查找最佳模板（v4.5.1增强版，v4.18.2异步支持）
        
        匹配策略（三级智能降级）：
        Level 1: 精确匹配（platform + data_domain + sub_domain + granularity）
        Level 2: 忽略sub_domain（向后兼容）
        Level 3: 忽略granularity（最宽松）
        
        状态筛选：status = 'published'（只用已发布模板）
        版本选择：MAX(version)（最新版本）
        
        Args:
            platform: 平台代码（必填）
            data_domain: 数据域（必填）
            granularity: 粒度（可选）
            sub_domain: 子域（可选，如ai_assistant/agent）
        
        Returns:
            FieldMappingTemplate对象 或 None
        """
        try:
            norm_granularity = self._normalize_dimension(granularity)
            norm_sub_domain = self._normalize_dimension(sub_domain)

            # Level 1: 精确匹配（最优）
            level1_conditions = [
                FieldMappingTemplate.platform == platform,
                FieldMappingTemplate.data_domain == data_domain,
                self._match_dimension(FieldMappingTemplate.granularity, norm_granularity),
                FieldMappingTemplate.status == 'published',
            ]

            # ⭐ v4.16.0修复：只有当调用方提供了sub_domain时，才要求模板的sub_domain与之匹配
            # 当文件没有sub_domain时，不添加sub_domain条件，允许匹配任何sub_domain的模板
            if norm_sub_domain is not None:
                level1_conditions.append(
                    self._match_dimension(FieldMappingTemplate.sub_domain, norm_sub_domain)
                )
            # else分支：不添加sub_domain条件，允许匹配任何sub_domain的模板（包括None）

            stmt = select(FieldMappingTemplate).where(
                *level1_conditions
            ).order_by(desc(FieldMappingTemplate.version))

            # ⭐ v4.18.2：支持异步会话
            result = await self.db.execute(stmt)
            template = result.scalars().first()
            
            if template:
                # ⭐ v4.19.5 优化：降低日志级别（INFO → DEBUG），减少日志噪音
                logger.debug(
                    f"[Level 1] 精确匹配: {template.template_name} "
                    f"(v{template.version}, {platform}/{data_domain}/{norm_sub_domain or 'None'}/{norm_granularity or 'None'})"
                )
                return template
            
            # Level 2: 忽略sub_domain（向后兼容）
            # ⭐ v4.16.0修复：services域不允许忽略sub_domain（ai_assistant和agent表头完全不同）
            # 对于services域，如果提供了sub_domain但没有匹配到模板，不应该降级匹配其他sub_domain的模板
            if norm_granularity is not None or (sub_domain is not None and data_domain.lower() != 'services'):
                # 对于services域，如果提供了sub_domain，不允许降级匹配
                if data_domain.lower() == 'services' and norm_sub_domain is not None:
                    # ⭐ v4.19.5 优化：降低日志级别
                    logger.debug(
                        f"[Level 2] services域已提供sub_domain={norm_sub_domain}，不允许降级匹配其他sub_domain的模板"
                    )
                else:
                    stmt = select(FieldMappingTemplate).where(
                        FieldMappingTemplate.platform == platform,
                        FieldMappingTemplate.data_domain == data_domain,
                        self._match_dimension(FieldMappingTemplate.granularity, norm_granularity),
                        FieldMappingTemplate.status == 'published'
                    ).order_by(desc(FieldMappingTemplate.version))
                    
                    # ⭐ v4.18.2：支持异步会话
                    result = await self.db.execute(stmt)
                    template = result.scalars().first()
                    
                    if template:
                        # ⭐ v4.19.5 优化：降低日志级别
                        logger.debug(
                            f"[Level 2] 模糊匹配（忽略sub_domain）: {template.template_name} "
                            f"(v{template.version}, {platform}/{data_domain}/{norm_granularity or 'None'})"
                        )
                        return template
            
            # Level 3（已禁用）：忽略granularity的宽松匹配会导致错误模板，直接返回None
            logger.info(
                f"[TemplateMatcher] 未找到严格匹配模板（platform={platform}, domain={data_domain}, "
                f"sub_domain={norm_sub_domain or 'None'}, granularity={norm_granularity or 'None'}）"
            )
            logger.info(
                f"[TemplateMatcher] 未找到模板: {platform}/{data_domain}/{norm_sub_domain or 'ANY'}/{norm_granularity or 'ANY'}"
            )
            return None
            
        except Exception as e:
            logger.error(f"[TemplateMatcher] 查找模板失败: {e}", exc_info=True)
            return None
    
    async def get_template_config(self, template_id: int) -> Dict[str, Any]:
        """
        获取模板的完整配置（v4.6.0重构版，v4.18.2异步支持）
        
        v4.6.0变更：
        - mappings改为header_columns（原始表头字段列表）
        
        包含：
        - header_row: 表头行索引
        - sub_domain: 子数据类型
        - sheet_name: Excel工作表名称
        - encoding: 文件编码
        - field_count: 字段数量
        - header_columns: 原始表头字段列表（v4.6.0新增）
        """
        try:
            # ⭐ v4.18.2：支持异步会话
            result = await self.db.execute(
                select(FieldMappingTemplate).where(
                    FieldMappingTemplate.id == template_id
                )
            )
            template = result.scalar_one_or_none()
            
            if not template:
                logger.warning(f"[TemplateMatcher] 模板不存在: ID={template_id}")
                return {}
            
            # v4.6.0：从header_columns读取原始表头字段列表
            header_columns = template.header_columns or []
            
            return {
                'header_row': template.header_row or 0,
                'sub_domain': template.sub_domain,
                'sheet_name': template.sheet_name,
                'encoding': template.encoding or 'utf-8',
                'field_count': template.field_count or len(header_columns),
                'header_columns': header_columns,  # v4.6.0：返回原始表头字段列表
                'template_name': template.template_name,
                'version': template.version,
                'status': template.status
            }
            
        except Exception as e:
            logger.error(f"[TemplateMatcher] 获取模板配置失败: {e}", exc_info=True)
            return {}
    
    async def get_template_mappings(self, template_id: int) -> Dict[str, Dict]:
        """
        获取模板的字段映射（v4.6.0重构版，v4.18.2异步支持）
        
        v4.6.0变更：
        - 不再查询FieldMappingTemplateItem表
        - 改为从template.header_columns读取原始表头字段列表
        - 返回格式：{original_field: {standard_field: None, confidence: 1.0, method: 'template', reason: '模板应用'}}
        
        Args:
            template_id: 模板ID
        
        Returns:
            {original_field: {standard_field, confidence, ...}}
        """
        try:
            # ⭐ v4.18.2：支持异步会话
            result = await self.db.execute(
                select(FieldMappingTemplate).where(
                    FieldMappingTemplate.id == template_id
                )
            )
            template = result.scalar_one_or_none()
            
            if not template:
                logger.warning(f"[TemplateMatcher] 模板不存在: ID={template_id}")
                return {}
            
            header_columns = template.header_columns or []
            
            # 构建映射字典（v4.6.0：不再有标准字段映射，只返回原始表头）
            mappings = {}
            for col in header_columns:
                mappings[col] = {
                    'standard_field': None,  # v4.6.0：不再存储标准字段映射
                    'confidence': 1.0,
                    'method': 'template',
                    'reason': f'模板应用（原始表头）'
                }
            
            logger.info(f"[TemplateMatcher] 获取模板映射: {len(mappings)}个字段")
            return mappings
            
        except Exception as e:
            logger.error(f"[TemplateMatcher] 获取模板映射失败: {e}", exc_info=True)
            return {}
    
    async def apply_template_to_columns(
        self, 
        template: FieldMappingTemplate,
        columns: List[str]
    ) -> Dict[str, Dict]:
        """
        应用模板到列（匹配列名，v4.18.2异步支持）
        
        支持：
        - 精确匹配
        - 模糊匹配（去除空格、特殊字符）
        
        Args:
            template: 模板对象
            columns: 列名列表
        
        Returns:
            {column: {standard_field, confidence, method, reason}}
        """
        import re
        
        try:
            # ⭐ v4.18.2：获取模板映射（异步）
            template_mappings = await self.get_template_mappings(template.id)
            
            # 应用到列
            result = {}
            for col in columns:
                matched = False
                
                # 1. 精确匹配
                if col in template_mappings:
                    result[col] = template_mappings[col]
                    result[col]['reason'] = f'模板: {template.template_name}'
                    matched = True
                else:
                    # 2. 模糊匹配（去除空格、特殊字符）
                    col_normalized = re.sub(r'[\s_\-()（）]', '', col.lower())
                    for template_col, mapping in template_mappings.items():
                        template_col_normalized = re.sub(r'[\s_\-()（）]', '', template_col.lower())
                        if col_normalized == template_col_normalized:
                            result[col] = mapping.copy()
                            result[col]['reason'] = f'模板: {template.template_name} (模糊匹配)'
                            matched = True
                            break
                
                if not matched:
                    # 未匹配的列不强制映射（由AI建议兜底）
                    pass
            
            logger.info(
                f"[TemplateMatcher] 应用模板: {template.template_name}, "
                f"匹配 {len(result)}/{len(columns)} 个字段"
            )
            
            return result
            
        except Exception as e:
            logger.error(f"[TemplateMatcher] 应用模板失败: {e}", exc_info=True)
            return {}
    
    async def get_template_coverage(self, platform: str = None) -> Dict[str, Any]:
        """
        获取模板覆盖度统计（v4.18.2异步支持）
        
        返回：
        - total_combinations: 总的域×粒度组合数
        - covered_combinations: 有模板覆盖的组合数
        - coverage_percentage: 覆盖率百分比
        - missing_combinations: 缺少模板的组合列表
        """
        try:
            from modules.core.db import CatalogFile
            
            # 查询所有唯一的域×粒度组合（从catalog_files）
            stmt = select(
                CatalogFile.data_domain,
                CatalogFile.granularity
            ).where(
                CatalogFile.status == 'pending'  # 只统计待处理的
            ).distinct()
            
            if platform:
                stmt = stmt.where(CatalogFile.platform_code == platform)
            
            # ⭐ v4.18.2：支持异步会话
            result = await self.db.execute(stmt)
            all_combinations = result.all()
            
            total = len(all_combinations)
            
            # 查询有模板的组合
            covered = []
            missing = []
            
            for domain, granularity in all_combinations:
                if granularity is None:
                    continue  # 跳过无粒度的文件
                
                # ⭐ v4.18.2：异步调用
                template = await self.find_best_template(
                    platform or 'shopee',  # 如果未指定，默认shopee
                    domain,
                    granularity
                )
                
                if template:
                    covered.append((domain, granularity))
                else:
                    missing.append((domain, granularity))
            
            coverage_percentage = (len(covered) / total * 100) if total > 0 else 0
            
            return {
                'total_combinations': total,
                'covered_combinations': len(covered),
                'coverage_percentage': round(coverage_percentage, 1),
                'missing_combinations': [
                    {'domain': d, 'granularity': g} 
                    for d, g in missing
                ]
            }
            
        except Exception as e:
            logger.error(f"[TemplateMatcher] 获取模板覆盖度失败: {e}", exc_info=True)
            return {
                'total_combinations': 0,
                'covered_combinations': 0,
                'coverage_percentage': 0,
                'missing_combinations': []
            }
    
    async def detect_header_changes(
        self,
        template_id: int,
        current_columns: List[str]
    ) -> Dict[str, Any]:
        """
        检测表头变化（v4.14.0安全版本，v4.18.2异步支持）
        
        ⚠️ 安全原则：不进行相似度匹配，任何变化都需要用户手动确认
        
        比较当前表头与模板表头，检测：
        - 新增字段（current中有，template中没有）
        - 删除字段（template中有，current中没有）
        - 字段顺序变化（通过完全匹配检查）
        
        Args:
            template_id: 模板ID
            current_columns: 当前表头字段列表
        
        Returns:
            {
                'detected': bool,
                'added_fields': List[str],
                'removed_fields': List[str],
                'match_rate': float,  # 匹配率（0-100）
                'is_exact_match': bool,  # 是否完全匹配（字段名和顺序都一致）
                'template_columns': List[str],  # 模板字段列表（供前端对比）
                'current_columns': List[str]  # 当前字段列表（供前端对比）
            }
        """
        try:
            # ⭐ v4.18.2：支持异步会话
            result = await self.db.execute(
                select(FieldMappingTemplate).where(
                    FieldMappingTemplate.id == template_id
                )
            )
            template = result.scalar_one_or_none()
            
            if not template:
                logger.warning(f"[HeaderChange] 模板不存在: ID={template_id}")
                return {
                    'detected': True,  # 模板不存在视为变化
                    'added_fields': [],
                    'removed_fields': [],
                    'match_rate': 0.0,
                    'is_exact_match': False,
                    'template_columns': [],
                    'current_columns': current_columns
                }
            
            template_columns = template.header_columns or []
            
            # ⭐ v4.15.0新增：货币代码归一化
            # 在比较前，将字段名归一化（移除货币代码部分）
            currency_extractor = get_currency_extractor()
            normalized_current = currency_extractor.normalize_field_list(current_columns)
            normalized_template = currency_extractor.normalize_field_list(template_columns)
            
            # 使用归一化后的字段名进行比较
            current_set = set(normalized_current)
            template_set = set(normalized_template)
            
            # 1. 检测新增字段（current中有，template中没有）
            added_fields = list(current_set - template_set)
            
            # 2. 检测删除字段（template中有，current中没有）
            removed_fields = list(template_set - current_set)
            
            # ⭐ v4.14.0安全版本：移除相似度匹配逻辑
            # 任何字段名变化都需要用户手动确认
            # ⭐ v4.15.0更新：但货币代码差异不视为变化（已通过归一化处理）
            
            # 3. 计算匹配率（基于归一化后的字段集合的交集）
            matched_fields = len(current_set & template_set)
            total_fields = len(current_set | template_set)
            match_rate = (matched_fields / total_fields * 100) if total_fields > 0 else 0.0
            
            # 4. 检查是否完全匹配（归一化后的字段名和顺序都一致）
            is_exact_match = (
                len(added_fields) == 0 and 
                len(removed_fields) == 0 and 
                normalized_current == normalized_template  # 顺序也要一致（基于归一化后的字段名）
            )
            
            # 5. 判断是否检测到变化
            # ⚠️ 安全原则：任何变化（新增、删除、顺序变化）都视为变化
            detected = not is_exact_match
            
            result_dict = {
                'detected': detected,
                'added_fields': added_fields,
                'removed_fields': removed_fields,
                'match_rate': round(match_rate, 1),
                'is_exact_match': is_exact_match,
                'template_columns': template_columns,  # 返回原始模板字段列表（供前端对比，保留货币代码）
                'current_columns': current_columns,     # 返回原始当前字段列表（供前端对比，保留货币代码）
                'normalized_template_columns': normalized_template,  # ⭐ v4.15.0新增：归一化后的模板字段
                'normalized_current_columns': normalized_current     # ⭐ v4.15.0新增：归一化后的当前字段
            }
            
            if detected:
                logger.warning(
                    f"[HeaderChange] [WARN] 检测到表头变化: "
                    f"新增{len(added_fields)}个, 删除{len(removed_fields)}个, "
                    f"匹配率{match_rate:.1f}% - 需要用户手动确认"
                )
            
            return result_dict
            
        except Exception as e:
            logger.error(f"[HeaderChange] 检测表头变化失败: {e}", exc_info=True)
            return {
                'detected': True,  # 检测失败视为变化（安全策略）
                'added_fields': [],
                'removed_fields': [],
                'match_rate': 0.0,
                'is_exact_match': False,
                'template_columns': [],
                'current_columns': current_columns if 'current_columns' in locals() else []
            }


def get_template_matcher(db: AsyncSession) -> TemplateMatcher:
    """
    获取模板匹配器实例
    
    v4.18.2新增：支持异步会话（AsyncSession）
    v4.19.0更新：移除同步/异步双模式支持，统一为异步架构
    """
    return TemplateMatcher(db)

