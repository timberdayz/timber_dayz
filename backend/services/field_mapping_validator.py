#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
字段映射验证和质量评分服务（v4.13.0新增）

功能：
1. 验证字段映射的完整性
2. 评估字段映射质量
3. 识别映射问题
"""

from typing import Dict, Any, List, Optional, Set
from sqlalchemy.orm import Session
from collections import Counter

from modules.core.db import FieldMappingDictionary
from modules.core.logger import get_logger

logger = get_logger(__name__)


def validate_field_mapping(
    mapped_rows: List[Dict[str, Any]],
    data_domain: str,
    required_fields: Optional[List[str]] = None
) -> Dict[str, Any]:
    """
    验证字段映射的完整性
    
    Args:
        mapped_rows: 映射后的数据行列表
        data_domain: 数据域
        required_fields: 必填字段列表（可选）
    
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
                "unmapped_fields": []
            }
        
        # 统计所有字段
        all_fields = set()
        mapped_fields = set()
        unmapped_fields = set()
        
        for row in mapped_rows:
            for field_name, value in row.items():
                all_fields.add(field_name)
                # 判断字段是否已映射（简单判断：如果字段名包含中文或特殊字符，可能是未映射）
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
            "unmapped_fields": list(unmapped_fields)
        }
    
    except Exception as e:
        logger.error(f"[FieldMappingValidator] 验证字段映射失败: {e}", exc_info=True)
        return {
            "success": False,
            "error": str(e),
            "coverage": 0.0,
            "missing_fields": [],
            "mapped_fields": [],
            "unmapped_fields": []
        }


def calculate_mapping_quality_score(
    mapped_rows: List[Dict[str, Any]],
    data_domain: str,
    mappings: Dict[str, Any],
    required_fields: Optional[List[str]] = None
) -> Dict[str, Any]:
    """
    计算字段映射质量评分
    
    Args:
        mapped_rows: 映射后的数据行列表
        data_domain: 数据域
        mappings: 字段映射配置
        required_fields: 必填字段列表（可选）
    
    Returns:
        质量评分结果
    """
    try:
        # 1. 验证字段映射完整性
        validation_result = validate_field_mapping(mapped_rows, data_domain, required_fields)
        
        if not validation_result.get("success"):
            return {
                "success": False,
                "error": validation_result.get("error"),
                "score": 0.0,
                "issues": []
            }
        
        # 2. 计算各项指标
        coverage = validation_result.get("coverage", 0.0)
        missing_fields = validation_result.get("missing_fields", [])
        unmapped_fields = validation_result.get("unmapped_fields", [])
        
        # 3. 计算置信度（基于mappings中的confidence）
        confidence_scores = []
        for orig_col, mapping_info in mappings.items():
            if isinstance(mapping_info, dict):
                confidence = mapping_info.get("confidence", 0.5)
                confidence_scores.append(confidence)
        
        avg_confidence = sum(confidence_scores) / len(confidence_scores) if confidence_scores else 0.5
        
        # 4. 计算质量评分（加权平均）
        # 覆盖率权重：40%
        # 置信度权重：30%
        # 必填字段完整性权重：20%
        # 未映射字段惩罚：10%
        
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
            coverage_score * 0.4 +
            confidence_score * 0.3 +
            required_fields_score * 0.2 +
            unmapped_score * 0.1
        ) * 100  # 转换为0-100分
        
        # 5. 识别问题
        issues = []
        
        if coverage < 80:
            issues.append({
                "type": "low_coverage",
                "severity": "high",
                "message": f"字段映射覆盖率较低（{coverage:.1f}%），建议检查未映射字段"
            })
        
        if missing_fields:
            issues.append({
                "type": "missing_required_fields",
                "severity": "high",
                "message": f"缺少必填字段: {', '.join(missing_fields)}",
                "fields": missing_fields
            })
        
        if len(unmapped_fields) > 5:
            issues.append({
                "type": "too_many_unmapped_fields",
                "severity": "medium",
                "message": f"未映射字段过多（{len(unmapped_fields)}个），可能影响数据质量",
                "fields": list(unmapped_fields)[:10]  # 只显示前10个
            })
        
        if avg_confidence < 0.7:
            issues.append({
                "type": "low_confidence",
                "severity": "medium",
                "message": f"字段映射置信度较低（{avg_confidence:.2f}），建议人工审核"
            })
        
        return {
            "success": True,
            "score": round(total_score, 2),
            "coverage": round(coverage, 2),
            "confidence": round(avg_confidence, 2),
            "required_fields_score": round(required_fields_score * 100, 2),
            "unmapped_score": round(unmapped_score * 100, 2),
            "issues": issues,
            "validation_result": validation_result
        }
    
    except Exception as e:
        logger.error(f"[FieldMappingValidator] 计算字段映射质量评分失败: {e}", exc_info=True)
        return {
            "success": False,
            "error": str(e),
            "score": 0.0,
            "issues": []
        }


def _is_mapped_field(field_name: str) -> bool:
    """
    判断字段是否已映射
    
    简单判断规则：
    - 如果字段名包含中文字符，可能是未映射
    - 如果字段名包含特殊字符（如括号、空格），可能是未映射
    - 标准字段名通常是英文小写加下划线
    """
    import re
    
    # 检查是否包含中文字符
    if re.search(r'[\u4e00-\u9fff]', field_name):
        return False
    
    # 检查是否包含特殊字符（括号、空格等）
    if re.search(r'[()（）\s]', field_name):
        return False
    
    # 标准字段名通常是英文小写加下划线
    if re.match(r'^[a-z_]+$', field_name):
        return True
    
    return True  # 默认认为已映射
