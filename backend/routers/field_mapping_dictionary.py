#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
字段映射辞典API路由 - v4.3.7
提供中文友好的字段映射辞典查询与建议服务
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Dict, Any, Optional
from backend.models.database import get_db, get_async_db
from backend.services.field_mapping_dictionary_service import get_dictionary_service
from backend.services.field_mapping_template_service import get_template_service  # v4.3.7阶段C
from backend.utils.api_response import success_response, error_response
from backend.utils.error_codes import ErrorCode, get_error_type
from modules.core.logger import get_logger
from modules.core.db import FieldMappingDictionary
from sqlalchemy import text

logger = get_logger(__name__)
router = APIRouter()


@router.get("/dictionary")
async def get_field_dictionary(
    data_domain: str = None,
    search: str = None,
    db: AsyncSession = Depends(get_async_db)
):
    """
    获取字段映射辞典（中文友好）
    
    缓存策略：1小时（v4.6.3新增）
    
    支持：
    - 全量加载（不传data_domain时返回所有字段）
    - 按数据域过滤（可选，传data_domain参数）
    - 中文/拼音/缩写搜索
    - 必填字段置顶
    - 字段分组
    
    Query Parameters:
        data_domain: 数据域过滤（可选，orders/products/traffic/services），不传则返回全量
        search: 搜索关键词（支持中文/拼音/缩写，如：金额/je/gmv）
    
    Returns:
        {
            "success": true,
            "fields": [
                {
                    "field_code": "order_id",
                    "cn_name": "订单号",
                    "description": "订单唯一标识符",
                    "is_required": true,
                    "synonyms": ["订单号", "订单编号", "order_id", ...],
                    "example_values": ["240925AB12345"],
                    ...
                }
            ],
            "groups": {
                "dimension": [...],
                "amount": [...],
                ...
            },
            "required_fields": [...]
        }
    """
    try:
        service = get_dictionary_service(db)
        
        # 搜索或全量获取
        if search:
            fields = service.search_fields(query=search, data_domain=data_domain)
        else:
            fields = service.get_dictionary(data_domain=data_domain)
        
        # 按分组归类
        groups = {}
        required_fields = []
        
        # [*] 新增：过滤掉日期范围字段（避免时间索引混乱）
        def is_date_range_field(field_code: str, cn_name: str) -> bool:
            """判断是否为日期范围字段"""
            import re
            field_str = str(field_code).strip()
            cn_str = str(cn_name).strip()
            
            # 匹配日期范围格式：YYYY_MM_DD_YYYY_MM_DD
            if re.search(r'\d{4}[-_]\d{1,2}[-_]\d{1,2}[-_~]\d{4}[-_]\d{1,2}[-_]\d{1,2}', field_str):
                return True
            
            # 匹配包含"fan_wei"、"日期范围"、"范围"等关键词
            if 'fan_wei' in field_str.lower() or '日期范围' in cn_str or '[日期范围]' in cn_str:
                return True
            
            # 匹配包含两个日期格式的字段
            date_pattern = r'\d{4}[-_]\d{1,2}[-_]\d{1,2}'
            matches = re.findall(date_pattern, field_str)
            if len(matches) >= 2:
                return True
            
            return False
        
        filtered_fields = []
        for field in fields:
            # 过滤掉日期范围字段
            if is_date_range_field(field.get("field_code", ""), field.get("cn_name", "")):
                logger.debug(f"过滤日期范围字段: {field.get('field_code')}")
                continue
            
            filtered_fields.append(field)
        
        # 使用过滤后的字段列表
        for field in filtered_fields:
            # 分组
            group = field.get("field_group", "other")
            if group not in groups:
                groups[group] = []
            groups[group].append(field)
            
            # 必填字段
            if field.get("is_required"):
                required_fields.append(field)
        
        # [*] 修复：使用标准API响应格式
        return success_response(
            data={
                "fields": filtered_fields,  # 返回过滤后的字段
                "groups": groups,
                "required_fields": required_fields,
                "total": len(filtered_fields)  # 返回过滤后的总数
            }
        )
        
    except Exception as e:
        logger.error(f"获取字段辞典失败: {e}", exc_info=True)
        return error_response(
            code=ErrorCode.DATABASE_QUERY_ERROR,
            message="获取字段辞典失败",
            error_type=get_error_type(ErrorCode.DATABASE_QUERY_ERROR),
            detail=str(e),
            recovery_suggestion="请检查数据库连接和查询参数，或联系系统管理员",
            status_code=500
        )


@router.get("/dictionary/field/{field_code}")
async def get_field_detail(
    field_code: str,
    db: AsyncSession = Depends(get_async_db)
):
    """
    获取单个字段详情
    
    Args:
        field_code: 字段代码（如：order_id, total_amount）
    
    Returns:
        {
            "success": true,
            "field": {
                "field_code": "order_id",
                "cn_name": "订单号",
                "description": "订单唯一标识符",
                ...
            }
        }
    """
    try:
        service = get_dictionary_service(db)
        field = service.get_field_by_code(field_code)
        
        if not field:
            return error_response(
                code=ErrorCode.DATA_VALIDATION_FAILED,
                message="字段不存在",
                error_type=get_error_type(ErrorCode.DATA_VALIDATION_FAILED),
                recovery_suggestion="请检查字段代码是否正确，或确认该字段已创建",
                status_code=404
            )
        
        return {
            "success": True,
            "field": field
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取字段详情失败: {e}", exc_info=True)
        return error_response(
            code=ErrorCode.DATABASE_QUERY_ERROR,
            message="获取字段详情失败",
            error_type=get_error_type(ErrorCode.DATABASE_QUERY_ERROR),
            detail=str(e),
            recovery_suggestion="请检查数据库连接和查询参数，或联系系统管理员",
            status_code=500
        )


@router.post("/suggest-mappings")
async def suggest_field_mappings(
    request: Dict[str, Any],
    db: AsyncSession = Depends(get_async_db)
):
    """
    智能建议字段映射（v4.3.7阶段B - 完整实现）
    
    Request Body:
        {
            "columns": ["订单号", "下单时间", "金额", ...],
            "data_domain": "orders",
            "platform": "shopee",
            "sample_data": [...]  # 可选：样例数据用于值模式检测
        }
    
    Returns:
        {
            "success": true,
            "mappings": {
                "订单号": {
                    "standard_field": "order_id",
                    "confidence": 0.95,
                    "method": "synonym_exact_match",
                    "reason": "精确匹配同义词: 订单号"
                },
                ...
            },
            "statistics": {
                "total_columns": 27,
                "high_confidence": 20,  # >=0.90
                "medium_confidence": 5,  # 0.70-0.90
                "low_confidence": 2,    # <0.70
                "auto_match_rate": 92.6  # 自动映射率
            }
        }
    """
    try:
        columns = request.get("columns", [])
        data_domain = request.get("data_domain", "products")
        platform = request.get("platform")
        sample_data = request.get("sample_data", [])
        
        if not columns:
            return error_response(
                code=ErrorCode.DATA_REQUIRED_FIELD_MISSING,
                message="缺少columns参数",
                error_type=get_error_type(ErrorCode.DATA_REQUIRED_FIELD_MISSING),
                recovery_suggestion="请提供columns参数",
                status_code=400
            )
        
        logger.info(f"[Suggest] 智能建议请求: {len(columns)}列, 数据域={data_domain}, 平台={platform}")
        
        # 获取辞典
        dict_service = get_dictionary_service(db)
        dictionary_fields = dict_service.get_dictionary(data_domain=data_domain)
        
        if not dictionary_fields:
            return error_response(
                code=ErrorCode.DATA_VALIDATION_FAILED,
                message=f"未找到{data_domain}域的字段辞典",
                error_type=get_error_type(ErrorCode.DATA_VALIDATION_FAILED),
                recovery_suggestion="请检查数据域名称是否正确，或确认该数据域的字段辞典已创建",
                status_code=404
            )
        
        # [*] v4.6.0: 优先使用PatternMatcher（支持货币字段等Pattern-based映射）
        from backend.services.pattern_matcher import PatternMatcher
        pattern_matcher = PatternMatcher(db)
        
        mappings = {}
        
        # 第一阶段：Pattern-based匹配（v4.6.0新增）
        for col in columns:
            pattern_result = pattern_matcher.match_field(col, data_domain=data_domain)
            if pattern_result and pattern_result.get('matched') and pattern_result.get('standard_field'):
                mappings[col] = {
                    "standard_field": pattern_result['standard_field'],
                    "confidence": pattern_result.get('confidence', 0.95),
                    "method": pattern_result.get('match_type', 'pattern_match'),
                    "reason": pattern_result.get('match_reason', 'Pattern-based匹配'),
                    "dimensions": pattern_result.get('dimensions', {}),
                    "target_table": pattern_result.get('target_table'),
                    "target_columns": pattern_result.get('target_columns')
                }
        
        # 第二阶段：传统匹配器（处理未被Pattern匹配的字段）
        unmatched_cols = [col for col in columns if col not in mappings]
        if unmatched_cols:
            from backend.services.smart_field_matcher import get_smart_matcher
            matcher = get_smart_matcher(dictionary_fields, platform)
            traditional_mappings = matcher.batch_match(unmatched_cols, sample_data)
            mappings.update(traditional_mappings)
        
        # [*] 新增：自动检测字段类型（date或datetime）
        # 根据样本数据自动识别是否需要保留时间信息
        from backend.services.field_mapping.type_detector import enhance_mapping_with_type_detection
        
        enhanced_mappings = {}
        for col in columns:
            if col in mappings:
                mapping = mappings[col]
                # 提取该列的样本值
                column_samples = []
                if sample_data:
                    for row in sample_data[:20]:  # 只取前20行
                        if col in row and row[col] is not None:
                            column_samples.append(row[col])
                
                # 增强映射建议，添加自动检测的字段类型
                enhanced_mapping = enhance_mapping_with_type_detection(
                    mapping,
                    col,
                    column_samples if column_samples else None
                )
                enhanced_mappings[col] = enhanced_mapping
            else:
                enhanced_mappings[col] = mappings.get(col, {})
        
        mappings = enhanced_mappings
        high_conf = sum(1 for r in mappings.values() if r['confidence'] >= 0.90)
        medium_conf = sum(1 for r in mappings.values() if 0.70 <= r['confidence'] < 0.90)
        low_conf = sum(1 for r in mappings.values() if r['confidence'] < 0.70)
        
        # 自动映射率（置信度>=0.70视为可自动确认）
        auto_mappable = high_conf + medium_conf
        auto_match_rate = (auto_mappable / len(columns) * 100) if columns else 0
        
        logger.info(f"[Suggest] 智能建议完成: 高{high_conf}/中{medium_conf}/低{low_conf}, 自动映射率{auto_match_rate:.1f}%")
        
        return {
            "success": True,
            "mappings": mappings,
            "statistics": {
                "total_columns": len(columns),
                "high_confidence": high_conf,
                "medium_confidence": medium_conf,
                "low_confidence": low_conf,
                "auto_match_rate": round(auto_match_rate, 1)
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"建议映射失败: {e}", exc_info=True)
        return error_response(
            code=ErrorCode.DATABASE_QUERY_ERROR,
            message="建议映射失败",
            error_type=get_error_type(ErrorCode.DATABASE_QUERY_ERROR),
            detail=str(e),
            recovery_suggestion="请检查数据库连接和查询参数，或联系系统管理员",
            status_code=500
        )


@router.get("/dictionary/cache/clear")
async def clear_dictionary_cache(db: AsyncSession = Depends(get_async_db)):
    """
    清空辞典缓存（管理员操作）
    
    Returns:
        {
            "success": true,
            "message": "辞典缓存已清空"
        }
    """
    try:
        service = get_dictionary_service(db)
        service.clear_cache()
        return success_response(data={}, message="辞典缓存已清空")
    except Exception as e:
        logger.error(f"清空缓存失败: {e}")
        return error_response(
            code=ErrorCode.CACHE_OPERATION_ERROR,
            message="清空缓存失败",
            error_type=get_error_type(ErrorCode.CACHE_OPERATION_ERROR),
            detail=str(e),
            status_code=500
        )


# ========== 辞典健康与自愈工具 ==========

@router.post("/dictionary/field")
async def add_field_to_dictionary(payload: Dict[str, Any], db: AsyncSession = Depends(get_async_db)):
    """添加单个标准字段到辞典。
    
    Request Body:
        {
            "field_code": "field_name" 或 "订单号",  # 字段代码（中文或英文，必填）
            "cn_name": "字段中文名",      # 中文名称（必填）
            "data_domain": "orders",      # 数据域（必填）
            "field_group": "dimension",   # 字段分组（可选）
            "is_required": false,         # 是否必填（可选）
            "data_type": "string",        # 数据类型（可选）
            "description": "字段描述",    # 描述（可选）
            "synonyms": ["同义词1", "同义词2"]  # 同义词列表（可选）
        }
    
    Returns:
        {"success": true, "field_code": "field_name", "message": "字段已添加"}
    
    Note:
        - field_code支持中文，例如："订单号"、"采购金额"等
        - PostgreSQL完全支持UTF-8，中文field_code可以正常使用
        - 建议：中文用户可以使用中文field_code，代码中使用字符串字面量即可
    """
    try:
        from sqlalchemy import text
        
        field_code = payload.get("field_code")
        cn_name = payload.get("cn_name")
        data_domain = payload.get("data_domain")
        
        if not field_code or not cn_name or not data_domain:
            return error_response(
                code=ErrorCode.DATA_REQUIRED_FIELD_MISSING,
                message="缺少必填字段：field_code, cn_name, data_domain",
                error_type=get_error_type(ErrorCode.DATA_REQUIRED_FIELD_MISSING),
                recovery_suggestion="请提供所有必填字段：field_code, cn_name, data_domain",
                status_code=400
            )
        
        # 检查字段是否已存在
        result = await db.execute(
            text("SELECT COUNT(*) FROM field_mapping_dictionary WHERE field_code = :code"),
            {"code": field_code}
        ).scalar()
        
        if exists > 0:
            return error_response(
                code=ErrorCode.DATA_UNIQUE_CONSTRAINT_VIOLATION,
                message=f"字段 {field_code} 已存在",
                error_type=get_error_type(ErrorCode.DATA_UNIQUE_CONSTRAINT_VIOLATION),
                recovery_suggestion="请使用不同的字段代码，或更新现有字段信息",
                status_code=400
            )
        
        # 插入新字段
        field_group = payload.get("field_group") or (
            "dimension" if field_code.endswith("_id") or field_code.endswith("code") else
            ("datetime" if ("date" in field_code or field_code.endswith("ts")) else
             ("amount" if ("amount" in field_code or field_code=="price") else "metric"))
        )
        
        synonyms_json = payload.get("synonyms", [])
        if isinstance(synonyms_json, list):
            import json
            synonyms_json = json.dumps(synonyms_json, ensure_ascii=False)
        
        sql_str = text("""
            INSERT INTO field_mapping_dictionary
              (field_code, cn_name, data_domain, field_group, is_required, data_type, description, synonyms, active, created_by, created_at)
            VALUES
              (:code, :cn, :domain, :group, :req, :dtype, :desc, :synonyms, true, :by, NOW())
        """)
        
        await db.execute(sql_str, {
            "code": field_code,
            "cn": cn_name,
            "domain": data_domain,
            "group": field_group,
            "req": payload.get("is_required", False),
            "dtype": payload.get("data_type", "string"),
            "desc": payload.get("description"),
            "synonyms": synonyms_json,
            "by": payload.get("created_by", "web_ui")
        })
        await db.commit()
        
        # 清空缓存
        service = get_dictionary_service(db)
        service.clear_cache()
        
        return {
            "success": True,
            "field_code": field_code,
            "message": f"字段 {cn_name} ({field_code}) 已成功添加到 {data_domain} 域"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"添加字段失败: {e}", exc_info=True)
        await db.rollback()
        return error_response(
            code=ErrorCode.DATABASE_QUERY_ERROR,
            message="添加字段失败",
            error_type=get_error_type(ErrorCode.DATABASE_QUERY_ERROR),
            detail=str(e),
            recovery_suggestion="请检查数据库连接和权限，或联系系统管理员",
            status_code=500
        )


@router.get("/dictionary/summary")
async def dictionary_summary(db: AsyncSession = Depends(get_async_db)):
    """返回各数据域的字段数量，用于快速发现“0条”异常。"""
    try:
        domains = ["orders", "products", "analytics", "services", "traffic", "general"]
        summary = {}
        for d in domains:
            result = await db.execute(text("SELECT COUNT(*) FROM field_mapping_dictionary WHERE active = true AND data_domain = :d"), {"d": d})
            cnt = result.scalar() or 0
            summary[d] = int(cnt)
        result = await db.execute(text("SELECT COUNT(*) FROM field_mapping_dictionary WHERE active = true"))
        total = result.scalar() or 0
        data = {
            "summary": summary,
            "total": int(total)
        }
        
        return success_response(data=data)
    except Exception as e:
        logger.error(f"辞典摘要失败: {e}")
        return error_response(
            code=ErrorCode.DATABASE_QUERY_ERROR,
            message="辞典摘要失败",
            error_type=get_error_type(ErrorCode.DATABASE_QUERY_ERROR),
            detail=str(e),
            status_code=500
        )


@router.post("/dictionary/rebuild")
async def dictionary_rebuild(payload: Dict[str, Any] = None, db: AsyncSession = Depends(get_async_db)):
    """当辞典为空或条数不足时，灌入“关键字段最小集”。"""
    try:
        domain = (payload or {}).get("data_domain")
        seeds = {
            "orders": [
                ("order_ts", "下单时间", True, "datetime"),
                ("order_id", "订单号", True, "string"),
                ("platform_sku", "平台SKU", True, "string"),
                ("quantity", "数量", True, "integer"),
                ("total_amount", "订单金额", True, "float"),
                ("currency", "币种", True, "string"),
                ("platform_code", "平台", True, "string"),
                ("account_id", "账号", False, "string"),
                ("shop_id", "店铺", True, "string"),
            ],
            "products": [
                ("platform_sku", "平台SKU", True, "string"),
                ("product_name", "商品名称", True, "string"),
                ("price", "价格", False, "float"),
                ("currency", "币种", False, "string"),
                ("stock", "库存", False, "integer"),
            ],
            "analytics": [
                ("metric_date", "统计日期", True, "date"),
                ("page_views", "浏览量", False, "integer"),
                ("unique_visitors", "访客数", False, "integer"),
                ("conversion_rate", "转化率", False, "ratio"),
            ],
            "services": [
                ("service_date", "费用日期", True, "date"),
                ("service_type", "费用类型", True, "string"),
                ("amount", "金额", True, "float"),
                ("currency", "币种", False, "string"),
                ("platform_code", "平台", False, "string"),
                ("shop_id", "店铺", False, "string"),
            ],
            "traffic": [
                ("metric_date", "统计日期", True, "date"),
                ("page_views", "页面浏览数", False, "integer"),
                ("unique_visitors", "访客数", False, "integer"),
                ("new_visitors", "新访客", False, "integer"),
                ("bounce_rate", "跳出率", False, "ratio"),
                ("avg_time_on_page", "平均停留时长", False, "integer"),
                ("conversion_rate", "转化率", False, "ratio"),
            ],
        }

        targets = [domain] if domain else list(seeds.keys())
        created = 0
        # 只使用PostgreSQL（按用户要求）
        for d in targets:
            for code, cn, required, dtype in seeds[d]:
                field_group = (
                    "dimension" if code.endswith("_id") or code.endswith("code") else
                    ("datetime" if ("date" in code or code.endswith("ts")) else
                     ("amount" if ("amount" in code or code=="price") else "metric"))
                )
                # PostgreSQL原生SQL插入（ON CONFLICT DO NOTHING）
                # 注意：数据库表可能没有version和status字段，只插入存在的字段
                sql_str = text(
                    """
                    INSERT INTO field_mapping_dictionary
                      (field_code, cn_name, data_domain, field_group, is_required, data_type, active, created_by, created_at)
                    VALUES
                      (:code, :cn, :domain, :group, :req, :dtype, true, 'seed', NOW())
                    ON CONFLICT (field_code) DO NOTHING
                    """
                )
                result = await db.execute(sql_str, {
                    "code": code,
                    "cn": cn,
                    "domain": d,
                    "group": field_group,
                    "req": required,
                    "dtype": dtype,
                })
                # PostgreSQL rowcount表示实际插入的行数（0表示冲突已存在）
                if result.rowcount > 0:
                    created += 1
        await db.commit()
        
        return success_response(data={"created": created}, message=f"成功创建{created}个字段")
    except Exception as e:
        logger.error(f"辞典重建失败: {e}")
        await db.rollback()
        # 返回可诊断信息（200），便于前端/脚本快速定位
        return {"success": False, "error": str(e)}


# ========== v4.3.7阶段C: 模板管理API ==========

@router.post("/templates/save")
async def save_mapping_template(
    request: Dict[str, Any],
    db: AsyncSession = Depends(get_async_db)
):
    """
    保存映射模板（v4.5.1增强版 + v4.14.0新增）
    
    v4.5.1新增字段：
    - header_row: 表头行索引（解决问题1：模板保存表头行）
    - sub_domain: 子数据类型（解决问题2：子类型识别）
    - sheet_name: Excel工作表名称
    - encoding: 文件编码
    
    v4.14.0新增字段：
    - deduplication_fields: 核心去重字段列表（可选，如果未指定则使用默认配置）
    """
    try:
        template_service = get_template_service(db)
        
        # 验证必填参数
        if not request.get('platform'):
            raise ValueError("platform参数必填")
        if not request.get('data_domain'):
            raise ValueError("data_domain参数必填")
        
        # [*] v4.6.0 DSS架构：使用header_columns而非mappings
        header_columns = request.get('header_columns')
        if not header_columns and 'mappings' in request:
            # 兼容旧格式：从mappings提取header_columns
            mappings = request.get('mappings', {})
            if isinstance(mappings, dict):
                header_columns = list(mappings.keys())
            else:
                header_columns = []
        
        if not header_columns:
            raise ValueError("header_columns参数必填（DSS架构：保存原始表头字段列表）")
        
        # [*] v4.16.0新增：自动归一化header_columns（移除货币代码部分）
        # 这样保存的模板中，header_columns不包含货币代码，后续同步时表头也不会包含货币代码
        from backend.services.currency_extractor import get_currency_extractor
        currency_extractor = get_currency_extractor()
        
        # 保存原始header_columns（用于日志）
        original_header_columns = header_columns.copy()
        
        # 归一化header_columns（移除货币代码）
        normalized_header_columns = currency_extractor.normalize_field_list(header_columns)
        
        # 检查是否有变化
        if normalized_header_columns != original_header_columns:
            changed_fields = []
            for orig, norm in zip(original_header_columns, normalized_header_columns):
                if orig != norm:
                    changed_fields.append(f"{orig} -> {norm}")
            
            logger.info(
                f"[Template] [v4.16.0] 自动归一化header_columns: "
                f"{len(changed_fields)}个字段移除了货币代码: {changed_fields[:5]}..."
            )
        
        # 使用归一化后的header_columns
        header_columns = normalized_header_columns
        
        # 验证header_row范围
        header_row = request.get('header_row', 0)
        if not isinstance(header_row, int) or header_row < 0 or header_row > 100:
            raise ValueError(f"header_row必须在0-100之间，当前值: {header_row}")
        
        # v4.14.0新增：验证deduplication_fields格式（必填）
        deduplication_fields = request.get('deduplication_fields')
        if deduplication_fields is None:
            # 向后兼容：如果未提供，使用默认配置，但记录警告
            from backend.services.deduplication_fields_config import get_default_deduplication_fields
            deduplication_fields = get_default_deduplication_fields(
                data_domain=request['data_domain'],
                sub_domain=request.get('sub_domain')
            )
            logger.warning(
                f"[Template] [WARN] 警告：保存模板时未提供deduplication_fields，"
                f"使用默认配置: {deduplication_fields}。"
                f"建议用户手动选择核心字段以确保去重正确。"
            )
        elif not isinstance(deduplication_fields, list):
            raise ValueError(f"deduplication_fields必须是列表，当前值: {deduplication_fields}")
        elif len(deduplication_fields) == 0:
            raise ValueError("deduplication_fields不能为空列表，至少需要选择1个核心字段")
        else:
            # 验证列表中的元素都是字符串
            if not all(isinstance(field, str) for field in deduplication_fields):
                raise ValueError("deduplication_fields列表中的元素必须是字符串")
            
            # 验证核心字段是否在归一化后的header_columns中（软验证，记录警告但不阻止保存）
            # [*] v4.16.0修复：使用归一化后的header_columns（已在上面处理）
            if header_columns:
                missing_fields = []
                for field in deduplication_fields:
                    # 检查精确匹配和忽略大小写匹配
                    found = False
                    for col in header_columns:
                        if col == field or col.lower() == field.lower():
                            found = True
                            break
                    if not found:
                        missing_fields.append(field)
                
                if missing_fields:
                    logger.warning(
                        f"[Template] [WARN] 警告：以下核心字段不在表头中: {missing_fields}，"
                        f"可能导致去重失败。表头字段: {header_columns[:10]}..."
                    )
        
        template_id = template_service.save_template(
            platform=request['platform'],
            data_domain=request['data_domain'],
            header_columns=header_columns,  # [*] v4.6.0 DSS架构：使用header_columns
            granularity=request.get('granularity'),
            account=request.get('account'),
            template_name=request.get('template_name'),
            created_by=request.get('created_by', 'web_ui'),
            # v4.5.1新增参数
            header_row=header_row,
            sub_domain=request.get('sub_domain'),
            sheet_name=request.get('sheet_name'),
            encoding=request.get('encoding', 'utf-8'),
            # v4.14.0新增参数
            deduplication_fields=deduplication_fields  # 如果为None，服务层会使用默认配置
        )
        
        logger.info(f"[Template] 保存成功: platform={request['platform']}, domain={request['data_domain']}, template_id={template_id}")
        
        return {
            "success": True,
            "data": {
            "template_id": template_id
            },
            "message": "模板保存成功"
        }
    except ValueError as e:
        logger.error(f"保存模板失败（参数错误）: {e}", exc_info=True)
        return error_response(
            code=ErrorCode.VALIDATION_ERROR,
            message=f"保存模板失败: {str(e)}",
            error_type=get_error_type(ErrorCode.VALIDATION_ERROR),
            detail=str(e),
            recovery_suggestion="请检查请求参数是否正确",
            status_code=400
        )
    except Exception as e:
        logger.error(f"保存模板失败: {e}", exc_info=True)
        return error_response(
            code=ErrorCode.DATABASE_QUERY_ERROR,
            message=f"保存模板失败: {str(e)}",
            error_type=get_error_type(ErrorCode.DATABASE_QUERY_ERROR),
            detail=str(e),
            recovery_suggestion="请检查数据库连接和权限，或联系系统管理员",
            status_code=500
        )


@router.get("/templates/default-deduplication-fields")
async def get_default_deduplication_fields(
    data_domain: str = Query(..., description="数据域（如：orders, products, inventory）"),
    sub_domain: Optional[str] = Query(None, description="子类型（可选，如：ai_assistant）"),
    db: AsyncSession = Depends(get_async_db)
):
    """
    获取默认核心字段推荐（v4.14.0新增）
    
    根据数据域和子类型返回默认核心字段列表，用于前端推荐。
    
    Query Parameters:
        data_domain: 数据域（必填）
        sub_domain: 子类型（可选）
    
    Returns:
        {
            "success": true,
            "data": {
                "fields": ["order_id", "order_date", "platform_code", "shop_id"],
                "description": "订单数据的默认核心字段",
                "reason": "这些字段能够唯一标识每行订单数据"
            }
        }
    """
    try:
        from backend.services.deduplication_fields_config import (
            get_default_deduplication_fields,
            DEFAULT_DEDUPLICATION_FIELDS
        )
        
        fields = get_default_deduplication_fields(data_domain, sub_domain)
        
        # 生成描述和推荐原因
        descriptions = {
            'orders': '订单数据的默认核心字段',
            'products': '产品数据的默认核心字段',
            'inventory': '库存数据的默认核心字段',
            'traffic': '流量数据的默认核心字段',
            'services': '服务数据的默认核心字段',
            'analytics': '分析数据的默认核心字段',
        }
        
        reasons = {
            'orders': '这些字段能够唯一标识每行订单数据（订单ID + 日期 + 平台 + 店铺）',
            'products': '这些字段能够唯一标识每个产品（产品SKU + 产品ID + 平台 + 店铺）',
            'inventory': '这些字段能够唯一标识每个库存记录（产品SKU + 仓库ID + 平台 + 店铺）',
            'traffic': '这些字段能够唯一标识每条流量数据（日期 + 平台 + 店铺）',
            'services': '这些字段能够唯一标识每条服务数据（服务ID + 日期 + 平台 + 店铺）',
            'analytics': '这些字段能够唯一标识每条分析数据（日期 + 平台 + 店铺）',
        }
        
        description = descriptions.get(data_domain, f'{data_domain}数据的默认核心字段')
        reason = reasons.get(data_domain, '这些字段能够唯一标识每行数据')
        
        if sub_domain:
            description = f'{sub_domain}子类型的{description}'
        
        return success_response(
            data={
                "fields": fields,
                "description": description,
                "reason": reason
            },
            message="获取默认核心字段推荐成功"
        )
    except Exception as e:
        logger.error(f"获取默认核心字段推荐失败: {e}", exc_info=True)
        return error_response(
            code=ErrorCode.INTERNAL_ERROR,
            message=f"获取默认核心字段推荐失败: {str(e)}",
            error_type=get_error_type(ErrorCode.INTERNAL_ERROR),
            detail=str(e),
            recovery_suggestion="请检查数据域参数是否正确",
            status_code=500
        )


@router.get("/templates/list")
async def list_mapping_templates(
    platform: Optional[str] = Query(None, description="平台代码"),
    data_domain: Optional[str] = Query(None, description="数据域"),
    db: AsyncSession = Depends(get_async_db)
):
    """列出模板"""
    try:
        template_service = get_template_service(db)
        # 如果platform或data_domain为空字符串，转换为None
        platform = platform if platform else None
        data_domain = data_domain if data_domain else None
        templates = template_service.list_templates(platform, data_domain)
        
        return {
            "success": True,
            "data": {
            "templates": templates,
            "count": len(templates)
            }
        }
    except Exception as e:
        logger.error(f"列出模板失败: {e}", exc_info=True)
        return error_response(
            code=ErrorCode.DATABASE_QUERY_ERROR,
            message="列出模板失败",
            error_type=get_error_type(ErrorCode.DATABASE_QUERY_ERROR),
            detail=str(e),
            recovery_suggestion="请检查数据库连接和查询参数，或联系系统管理员",
            status_code=500
        )


@router.delete("/templates/{template_id}")
async def delete_mapping_template(
    template_id: int,
    db: AsyncSession = Depends(get_async_db)
):
    """删除模板"""
    try:
        template_service = get_template_service(db)
        success = template_service.delete_template(template_id)
        
        if success:
            return {
                "success": True,
                "data": {"template_id": template_id},
                "message": "模板删除成功"
            }
        else:
            return error_response(
                code=ErrorCode.NOT_FOUND,
                message="模板不存在",
                error_type=get_error_type(ErrorCode.NOT_FOUND),
                detail=f"模板ID {template_id} 不存在",
                recovery_suggestion="请检查模板ID是否正确",
                status_code=404
            )
    except Exception as e:
        logger.error(f"删除模板失败: {e}", exc_info=True)
        return error_response(
            code=ErrorCode.DATABASE_QUERY_ERROR,
            message="删除模板失败",
            error_type=get_error_type(ErrorCode.DATABASE_QUERY_ERROR),
            detail=str(e),
            recovery_suggestion="请检查数据库连接和权限，或联系系统管理员",
            status_code=500
        )


@router.post("/templates/apply")
async def apply_mapping_template(
    request: Dict[str, Any],
    db: AsyncSession = Depends(get_async_db)
):
    """
    应用模板（v4.5.1增强版 + v4.6.0表头变化检测）
    
    返回增强：
    - config: 模板配置对象（包含header_row、sub_domain等）
    - match_level: 匹配等级（exact/fuzzy/fallback）
    - header_changes: 表头变化检测结果（v4.6.0新增）
    
    前端使用config.header_row自动设置表头行，解决问题1
    """
    try:
        template_service = get_template_service(db)
        
        result = template_service.apply_template(
            template_id=request['template_id'],
            current_columns=request['columns']
        )
        
        # v4.5.1新增：获取模板完整配置
        from backend.services.template_matcher import get_template_matcher
        matcher = get_template_matcher(db)
        config = matcher.get_template_config(request['template_id'])
        
        # v4.6.0新增：检测表头变化
        header_changes = matcher.detect_header_changes(
            template_id=request['template_id'],
            current_columns=request['columns']
        )
        
        return {
            "success": True,
            "mappings": result['mappings'],
            "matched": result['matched'],
            "unmatched": result['unmatched'],
            "unmatched_columns": result['unmatched_columns'],
            "match_rate": result['match_rate'],
            # v4.5.1新增：返回完整配置
            "config": {
                "header_row": config.get('header_row', 0),
                "sub_domain": config.get('sub_domain'),
                "sheet_name": config.get('sheet_name'),
                "encoding": config.get('encoding', 'utf-8')
            },
            "template_name": config.get('template_name'),
            "template_version": config.get('version'),
            # v4.6.0新增：返回表头变化检测结果
            "header_columns": config.get('header_columns', []),  # 模板原始表头字段列表
            "header_changes": header_changes  # 表头变化详情
        }
    except Exception as e:
        logger.error(f"应用模板失败: {e}", exc_info=True)
        return error_response(
            code=ErrorCode.DATABASE_QUERY_ERROR,
            message="应用模板失败",
            error_type=get_error_type(ErrorCode.DATABASE_QUERY_ERROR),
            detail=str(e),
            recovery_suggestion="请检查数据库连接和权限，或联系系统管理员",
            status_code=500
        )


@router.post("/templates/detect-header-changes")
async def detect_header_changes(
    request: Dict[str, Any],
    db: AsyncSession = Depends(get_async_db)
):
    """
    检测表头变化（v4.14.0安全版本）
    
    [WARN] 安全原则：不进行相似度匹配，任何变化都需要用户手动确认
    
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
        from backend.services.template_matcher import get_template_matcher
        
        template_id = request.get('template_id')
        current_columns = request.get('current_columns', [])
        
        if not template_id:
            return error_response(
                code=ErrorCode.DATA_VALIDATION_FAILED,
                message="参数错误",
                error_type=get_error_type(ErrorCode.DATA_VALIDATION_FAILED),
                detail="template_id是必填参数",
                recovery_suggestion="请提供有效的template_id",
                status_code=400
            )
        
        if not current_columns or not isinstance(current_columns, list):
            return error_response(
                code=ErrorCode.DATA_VALIDATION_FAILED,
                message="参数错误",
                error_type=get_error_type(ErrorCode.DATA_VALIDATION_FAILED),
                detail="current_columns必须是非空列表",
                recovery_suggestion="请提供有效的current_columns列表",
                status_code=400
            )
        
        matcher = get_template_matcher(db)
        header_changes = matcher.detect_header_changes(
            template_id=template_id,
            current_columns=current_columns
        )
        
        return {
            "success": True,
            "header_changes": header_changes
        }
        
    except Exception as e:
        logger.error(f"检测表头变化失败: {e}", exc_info=True)
        return error_response(
            code=ErrorCode.DATABASE_QUERY_ERROR,
            message="检测表头变化失败",
            error_type=get_error_type(ErrorCode.DATABASE_QUERY_ERROR),
            detail=str(e),
            recovery_suggestion="请检查数据库连接和权限，或联系系统管理员",
            status_code=500
        )

