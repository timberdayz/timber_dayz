#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据质量评分器 - 方案B+数据治理组件

功能：
1. 评估DataFrame的数据质量（0-100分）
2. 检测数据问题（空值、重复、异常值等）
3. 生成质量报告

质量评分规则：
- 基础分100分
- 空值比例 > 10% -> 扣分（每1%扣0.5分）
- 重复行 > 1% -> 扣分（最多20分）
- 列名异常 -> 扣分
"""

import pandas as pd
from typing import Dict, List, Optional
from modules.core.logger import get_logger

logger = get_logger(__name__)


class DataQualityScorer:
    """数据质量评分器"""
    
    @staticmethod
    def score_dataframe(df: pd.DataFrame) -> Dict:
        """
        评估DataFrame的数据质量（0-100分）
        
        Args:
            df: 待评估的DataFrame
            
        Returns:
            质量评分字典
            {
                'row_count': int,
                'column_count': int,
                'null_percentage': float,
                'duplicate_rows': int,
                'quality_score': float,
                'issues': List[str]
            }
            
        Examples:
            >>> df = pd.DataFrame({'a': [1, 2, 3], 'b': [4, 5, 6]})
            >>> result = DataQualityScorer.score_dataframe(df)
            >>> result['quality_score']
            100.0
        """
        if df is None or df.empty:
            return {
                "row_count": 0,
                "column_count": 0,
                "null_percentage": 0.0,
                "duplicate_rows": 0,
                "quality_score": 0.0,
                "issues": ["文件为空"]
            }
        
        # 基础统计
        row_count = len(df)
        column_count = len(df.columns)
        
        # 空值统计
        total_cells = row_count * column_count
        null_cells = df.isnull().sum().sum()
        null_percentage = (null_cells / total_cells * 100) if total_cells > 0 else 0.0
        
        # 重复行统计
        duplicate_rows = df.duplicated().sum()
        duplicate_percentage = (duplicate_rows / row_count * 100) if row_count > 0 else 0.0
        
        # 质量问题列表
        issues = []
        
        # 计算质量分数（基础100分）
        score = 100.0
        
        # 扣分规则1：空值扣分
        if null_percentage > 10:
            penalty = (null_percentage - 10) * 0.5
            score -= penalty
            issues.append(f"空值比例过高: {null_percentage:.1f}%")
        
        # 扣分规则2：重复行扣分（最多20分）
        if duplicate_percentage > 1:
            penalty = min(duplicate_percentage * 2, 20)
            score -= penalty
            issues.append(f"重复行过多: {duplicate_rows}行 ({duplicate_percentage:.1f}%)")
        
        # 扣分规则3：列名异常扣分
        unnamed_cols = [col for col in df.columns if 'Unnamed' in str(col)]
        if unnamed_cols:
            score -= len(unnamed_cols) * 2
            issues.append(f"发现{len(unnamed_cols)}个未命名列")
        
        # 扣分规则4：数据行数过少
        if row_count < 10:
            score -= 10
            issues.append(f"数据行数过少: {row_count}行")
        
        # 确保分数在0-100范围内
        score = max(0.0, min(100.0, score))
        
        return {
            "row_count": int(row_count),
            "column_count": int(column_count),
            "null_percentage": round(null_percentage, 2),
            "duplicate_rows": int(duplicate_rows),
            "duplicate_percentage": round(duplicate_percentage, 2),
            "quality_score": round(score, 2),
            "issues": issues
        }
    
    @staticmethod
    def validate_schema(df: pd.DataFrame, required_columns: List[str]) -> Dict:
        """
        验证DataFrame的schema（必须包含的列）
        
        Args:
            df: DataFrame
            required_columns: 必须包含的列名列表
            
        Returns:
            验证结果
            {
                'valid': bool,
                'missing_columns': List[str],
                'extra_columns': List[str]
            }
        """
        df_columns = set(df.columns)
        required_set = set(required_columns)
        
        missing = list(required_set - df_columns)
        extra = list(df_columns - required_set)
        
        return {
            'valid': len(missing) == 0,
            'missing_columns': missing,
            'extra_columns': extra
        }
    
    @staticmethod
    def detect_anomalies(df: pd.DataFrame, column: str) -> Dict:
        """
        检测数值列的异常值（使用IQR方法）
        
        Args:
            df: DataFrame
            column: 列名
            
        Returns:
            异常检测结果
            {
                'has_anomalies': bool,
                'anomaly_count': int,
                'anomaly_indices': List[int]
            }
        """
        if column not in df.columns:
            return {'has_anomalies': False, 'anomaly_count': 0, 'anomaly_indices': []}
        
        try:
            series = pd.to_numeric(df[column], errors='coerce')
            
            # IQR方法检测异常
            Q1 = series.quantile(0.25)
            Q3 = series.quantile(0.75)
            IQR = Q3 - Q1
            
            lower_bound = Q1 - 1.5 * IQR
            upper_bound = Q3 + 1.5 * IQR
            
            anomalies = (series < lower_bound) | (series > upper_bound)
            anomaly_indices = df[anomalies].index.tolist()
            
            return {
                'has_anomalies': len(anomaly_indices) > 0,
                'anomaly_count': len(anomaly_indices),
                'anomaly_indices': anomaly_indices[:100]  # 最多返回100个
            }
        except Exception as e:
            logger.warning(f"异常检测失败 {column}: {e}")
            return {'has_anomalies': False, 'anomaly_count': 0, 'anomaly_indices': []}


# 便捷函数
def score_dataframe(df: pd.DataFrame) -> Dict:
    """便捷函数：评估DataFrame质量"""
    return DataQualityScorer.score_dataframe(df)


def validate_schema(df: pd.DataFrame, required_columns: List[str]) -> Dict:
    """便捷函数：验证schema"""
    return DataQualityScorer.validate_schema(df, required_columns)
