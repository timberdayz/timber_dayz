#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
字段映射验证和质量评分服务(v4.13.0新增)

功能:
1. 验证字段映射的完整性
2. 评估字段映射质量
3. 识别映射问题
"""

from typing import Dict, Any, List, Optional, Set
from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import AsyncSession
from collections import Counter

from modules.core.db import FieldMappingDictionary
from modules.core.logger import get_logger

logger = get_logger(__name__)


def validate_field_mapping(
    mapped_rows: List[Dict[str, Any]],
    data_domain: str,
    required_fields: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    验证字段映射的完整性

    Args:
        mapped_rows: 映射后的数据行列表
        data_domain: 数据域
        required_fields: 必填字段列表(可选)

    Returns:
        验证结果
    """
    try:
        if not mapped_rows:
            return {
                "success": False,
                "error": "没有数据行需要验证",
                "coverage": 0.0,
                "missing_fields": [],
                "mapped_fields": [],
                "unmapped_fields": [],
            }

        # 统计所有字段
        all_fields = set()
        mapped_fields = set()
        unmapped_fields = set()

        for row in mapped_rows:
            for field_name, value in row.items():
                all_fields.add(field_name)
                # 判断字段是否已映射(简单判断:如果字段名包含中文或特殊字符,可能是未映射)
                if _is_mapped_field(field_name):
                    mapped_fields.add(field_name)
                else:
                    unmapped_fields.add(field_name)

        # 检查必填字段
        missing_fields = []
        if required_fields:
            for field in required_fields:
                if field not in all_fields:
                    missing_fields.append(field)

        # 计算映射覆盖率
        total_fields = len(all_fields)
        mapped_count = len(mapped_fields)
        coverage = (mapped_count / total_fields * 100) if total_fields > 0 else 0.0

        return {
            "success": True,
            "coverage": coverage,
            "total_fields": total_fields,
            "mapped_fields_count": mapped_count,
            "unmapped_fields_count": len(unmapped_fields),
            "missing_fields": missing_fields,
            "mapped_fields": list(mapped_fields),
            "unmapped_fields": list(unmapped_fields),
        }

    except Exception as e:
        logger.error(f"[FieldMappingValidator] 验证字段映射失败: {e}", exc_info=True)
        return {
            "success": False,
            "error": str(e),
            "coverage": 0.0,
            "missing_fields": [],
            "mapped_fields": [],
            "unmapped_fields": [],
        }


# 看起来是数值/金额/比率的字段名 —— 这类字段如果 data_type 写成 string，
# 采集入库时会拿到字符串，下游算账就会炸。
_NUMERIC_FIELD_HINTS = (
    "amount",
    "price",
    "quantity",
    "qty",
    "count",
    "fee",
    "rate",
    "discount",
    "percent",
    "revenue",
    "profit",
    "cost",
)

_NUMERIC_DATA_TYPES = (
    "integer",
    "int",
    "float",
    "numeric",
    "decimal",
    "currency",
    "ratio",
    "number",
)


async def validate_field_mapping_dictionary(db: AsyncSession) -> Dict[str, Any]:
    """校验字段映射字典（core.field_mapping_dictionary）本身够不够用。

    业务问题：这张表是采集映射的**单一数据源** —— 采集配置页展示的、
    模板自动匹配用的都是它。如果标准字段元数据本身有缺口，
    采集就会在入库那一步对不上，而**没有人在入库前知道**。

    回答四个问题：
      1. 每个数据域配了多少字段、其中多少是必填、多少真的生效；
      2. 数值型字段（amount/price/quantity…）的 data_type 是不是被写成了 string
         —— 这是最要命的一类：采集能进来，算账时炸；
      3. field_group / data_type 有没有填 —— 采集配置页按组展示、类型转换都靠它；
      4. 有没有**一个必填字段都没标**的数据域 —— 那种域采集时没有守门，
         缺列也能入库，直到下游才发现。

    Args:
        db: **异步**数据库会话（路由层直接传请求自己的 AsyncSession，
            纯读操作，不开事务写锁）。

    Returns:
        {"success": bool, "is_valid": bool, "summary": {...}, "issues": [...]}
    """
    from sqlalchemy import text

    issues: List[Dict[str, Any]] = []

    def add(
        severity: str,
        category: str,
        issue: str,
        suggestion: str,
        field_name: Optional[str] = None,
        code_location: Optional[str] = None,
    ) -> None:
        issues.append(
            {
                "severity": severity,
                "category": category,
                "issue": issue,
                "suggestion": suggestion,
                "field_name": field_name,
                "code_location": code_location,
            }
        )

    try:
        result = await db.execute(
            text(
                """
                SELECT data_domain, field_code, cn_name, en_name, field_group,
                       is_required, data_type, active, status, synonyms
                FROM core.field_mapping_dictionary
                """
            )
        )
        rows = result.fetchall()
    except Exception as exc:  # noqa: BLE001
        logger.error(
            f"[FieldMappingValidator] 读取字段映射字典失败: {exc}", exc_info=True
        )
        return {
            "success": False,
            "is_valid": False,
            "error": str(exc),
            "summary": {"total_issues": 0},
            "issues": [],
        }

    by_domain: Dict[str, List[Any]] = {}
    for row in rows:
        by_domain.setdefault(str(row[0] or "unknown"), []).append(row)

    domain_summary: Dict[str, Any] = {}
    for domain, domain_rows in sorted(by_domain.items()):
        active_rows = [
            r for r in domain_rows if r[7] and str(r[8] or "active") == "active"
        ]
        required_rows = [r for r in domain_rows if r[5]]

        for row in domain_rows:
            field_code = str(row[1] or "")
            data_type = str(row[6] or "").strip().lower()
            field_group = str(row[4] or "").strip()
            is_active = bool(row[7]) and str(row[8] or "active") == "active"

            if is_active and not data_type:
                add(
                    "warning",
                    "data_type",
                    f"字段 {field_code} 没有填 data_type",
                    "采集时无法决定该列怎么转成数值/日期",
                    field_name=field_code,
                    code_location="core.field_mapping_dictionary",
                )
            elif (
                is_active
                and data_type == "string"
                and any(hint in field_code.lower() for hint in _NUMERIC_FIELD_HINTS)
            ):
                add(
                    "error",
                    "data_type",
                    f"字段 {field_code} 是数值型字段，data_type 却写成 string",
                    "采集能进来但下游算账会拿到字符串，改成对应数值类型",
                    field_name=field_code,
                    code_location="core.field_mapping_dictionary",
                )

            if is_active and not field_group:
                add(
                    "info",
                    "field_group",
                    f"字段 {field_code} 没有填 field_group",
                    "采集配置页按分组展示，缺分组会挤成一坨",
                    field_name=field_code,
                    code_location="core.field_mapping_dictionary",
                )

        if not active_rows:
            add(
                "error",
                "coverage",
                f"数据域 {domain} 没有任何生效字段",
                "这个域采集时一定对不上标准字段",
                code_location=f"core.field_mapping_dictionary:{domain}",
            )
        elif not required_rows:
            add(
                "warning",
                "required",
                f"数据域 {domain} 一个必填字段都没标",
                "缺列也能入库，直到下游才发现；至少把身份字段标成必填",
                code_location=f"core.field_mapping_dictionary:{domain}",
            )

        domain_summary[domain] = {
            "total_fields": len(domain_rows),
            "active_fields": len(active_rows),
            "required_fields": len(required_rows),
            "with_data_type": len([r for r in active_rows if str(r[6] or "").strip()]),
            "with_field_group": len(
                [r for r in active_rows if str(r[4] or "").strip()]
            ),
        }

    error_count = len([i for i in issues if i["severity"] == "error"])
    warning_count = len([i for i in issues if i["severity"] == "warning"])
    info_count = len([i for i in issues if i["severity"] == "info"])
    return {
        "success": True,
        "is_valid": error_count == 0,
        "summary": {
            "total_issues": len(issues),
            "error_count": error_count,
            "warning_count": warning_count,
            "info_count": info_count,
            "total_fields": len(rows),
            "total_domains": len(by_domain),
            "domains": domain_summary,
        },
        "issues": issues,
    }


def calculate_mapping_quality_score(
    mapped_rows: List[Dict[str, Any]],
    data_domain: str,
    mappings: Dict[str, Any],
    required_fields: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    计算字段映射质量评分

    Args:
        mapped_rows: 映射后的数据行列表
        data_domain: 数据域
        mappings: 字段映射配置
        required_fields: 必填字段列表(可选)

    Returns:
        质量评分结果
    """
    try:
        # 1. 验证字段映射完整性
        validation_result = validate_field_mapping(
            mapped_rows, data_domain, required_fields
        )

        if not validation_result.get("success"):
            return {
                "success": False,
                "error": validation_result.get("error"),
                "score": 0.0,
                "issues": [],
            }

        # 2. 计算各项指标
        coverage = validation_result.get("coverage", 0.0)
        missing_fields = validation_result.get("missing_fields", [])
        unmapped_fields = validation_result.get("unmapped_fields", [])

        # 3. 计算置信度(基于mappings中的confidence)
        confidence_scores = []
        for orig_col, mapping_info in mappings.items():
            if isinstance(mapping_info, dict):
                confidence = mapping_info.get("confidence", 0.5)
                confidence_scores.append(confidence)

        avg_confidence = (
            sum(confidence_scores) / len(confidence_scores)
            if confidence_scores
            else 0.5
        )

        # 4. 计算质量评分(加权平均)
        # 覆盖率权重:40%
        # 置信度权重:30%
        # 必填字段完整性权重:20%
        # 未映射字段惩罚:10%

        coverage_score = coverage / 100.0  # 转换为0-1范围
        confidence_score = avg_confidence  # 已经是0-1范围

        required_fields_score = 1.0
        if required_fields:
            missing_count = len(missing_fields)
            required_fields_score = 1.0 - (missing_count / len(required_fields))

        unmapped_penalty = min(len(unmapped_fields) / 10.0, 1.0)  # 最多扣10分
        unmapped_score = 1.0 - unmapped_penalty

        # 计算总分
        total_score = (
            coverage_score * 0.4
            + confidence_score * 0.3
            + required_fields_score * 0.2
            + unmapped_score * 0.1
        ) * 100  # 转换为0-100分

        # 5. 识别问题
        issues = []

        if coverage < 80:
            issues.append(
                {
                    "type": "low_coverage",
                    "severity": "high",
                    "message": f"字段映射覆盖率较低({coverage:.1f}%),建议检查未映射字段",
                }
            )

        if missing_fields:
            issues.append(
                {
                    "type": "missing_required_fields",
                    "severity": "high",
                    "message": f"缺少必填字段: {', '.join(missing_fields)}",
                    "fields": missing_fields,
                }
            )

        if len(unmapped_fields) > 5:
            issues.append(
                {
                    "type": "too_many_unmapped_fields",
                    "severity": "medium",
                    "message": f"未映射字段过多({len(unmapped_fields)}个),可能影响数据质量",
                    "fields": list(unmapped_fields)[:10],  # 只显示前10个
                }
            )

        if avg_confidence < 0.7:
            issues.append(
                {
                    "type": "low_confidence",
                    "severity": "medium",
                    "message": f"字段映射置信度较低({avg_confidence:.2f}),建议人工审核",
                }
            )

        return {
            "success": True,
            "score": round(total_score, 2),
            "coverage": round(coverage, 2),
            "confidence": round(avg_confidence, 2),
            "required_fields_score": round(required_fields_score * 100, 2),
            "unmapped_score": round(unmapped_score * 100, 2),
            "issues": issues,
            "validation_result": validation_result,
        }

    except Exception as e:
        logger.error(
            f"[FieldMappingValidator] 计算字段映射质量评分失败: {e}", exc_info=True
        )
        return {"success": False, "error": str(e), "score": 0.0, "issues": []}


def _is_mapped_field(field_name: str) -> bool:
    """
    判断字段是否已映射

    简单判断规则:
    - 如果字段名包含中文字符,可能是未映射
    - 如果字段名包含特殊字符(如括号、空格),可能是未映射
    - 标准字段名通常是英文小写加下划线
    """
    import re

    # 检查是否包含中文字符
    if re.search(r"[\u4e00-\u9fff]", field_name):
        return False

    # 检查是否包含特殊字符(括号、空格等)
    if re.search(r"[()()\s]", field_name):
        return False

    # 标准字段名通常是英文小写加下划线
    if re.match(r"^[a-z_]+$", field_name):
        return True

    return True  # 默认认为已映射
