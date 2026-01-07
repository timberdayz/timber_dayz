#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
智能字段映射引擎

功能:
1. 粒度感知的映射键生成
2. 多策略字段匹配（精确/模糊/语义/历史）
3. 返回带置信度的映射结果

作者: AI 专家级数据工程师
创建日期: 2025-01-26
"""

import yaml
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from difflib import SequenceMatcher
from loguru import logger


@dataclass
class FieldMapping:
    """单个字段的映射结果"""
    standard_field: str  # 标准字段名
    source_column: Optional[str]  # 源列名
    confidence: float  # 置信度 (0-100)
    method: str  # 匹配方法


@dataclass
class MappingResult:
    """完整的映射结果"""
    mapping_key: str  # 映射键 (例如: "tiktok:products" 或 "tiktok:traffic_daily")
    mappings: Dict[str, FieldMapping]  # 字段映射字典
    metadata: Dict  # 元数据
    unmapped_columns: List[str]  # 未映射的列
    confidence_score: float  # 整体置信度分数


class SmartFieldMapper:
    """智能字段映射引擎"""
    
    def __init__(
        self,
        config_path: str = "config/field_mappings_v2.yaml",
        history_manager=None
    ):
        """
        初始化智能字段映射引擎
        
        Args:
            config_path: 字段映射配置文件路径
            history_manager: 映射历史管理器（可选）
        """
        self.config_path = Path(config_path)
        self.history_manager = history_manager
        self.config = self._load_config()
        
        # 同义词字典（用于语义匹配）
        self.synonyms = {
            "gmv": ["revenue", "sales", "销售额", "营收", "成交额"],
            "quantity": ["qty", "count", "数量", "件数"],
            "price": ["单价", "价格", "售价"],
            "product_name": ["商品", "产品", "title", "name", "标题"],
            "product_id": ["id", "sku", "编号", "商品ID"],
            "order_id": ["订单号", "订单编号", "order_no"],
        }
    
    def _load_config(self) -> Dict:
        """加载字段映射配置"""
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
            logger.info(f"已加载字段映射配置: {self.config_path}")
            return config
        except Exception as e:
            logger.error(f"加载配置文件失败: {e}")
            return {}
    
    def map_fields(
        self,
        columns: List[str],
        metadata: Dict
    ) -> MappingResult:
        """
        执行字段映射
        
        Args:
            columns: Excel文件的列名列表
            metadata: 文件元数据（包含platform, data_type, granularity等）
        
        Returns:
            MappingResult: 映射结果
        """
        # 1. 生成映射键
        mapping_key = self._generate_mapping_key(metadata)
        logger.info(f"映射键: {mapping_key}")
        
        # 2. 加载字段映射规则
        field_rules = self._load_field_rules(mapping_key)
        if not field_rules:
            logger.warning(f"未找到映射规则: {mapping_key}")
            return self._create_empty_result(mapping_key, columns, metadata)
        
        # 3. 对每个标准字段，尝试多策略匹配
        mappings = {}
        mapped_columns = set()
        
        for std_field, candidates in field_rules.items():
            matched_col, confidence, method = self._match_column(
                columns, candidates, std_field, mapping_key
            )
            
            mappings[std_field] = FieldMapping(
                standard_field=std_field,
                source_column=matched_col,
                confidence=confidence,
                method=method
            )
            
            if matched_col:
                mapped_columns.add(matched_col)
        
        # 4. 找出未映射的列
        unmapped_columns = [col for col in columns if col not in mapped_columns]
        
        # 5. 计算整体置信度分数
        confidence_score = self._calculate_confidence_score(mappings)
        
        return MappingResult(
            mapping_key=mapping_key,
            mappings=mappings,
            metadata=metadata,
            unmapped_columns=unmapped_columns,
            confidence_score=confidence_score
        )
    
    def _generate_mapping_key(self, metadata: Dict) -> str:
        """
        生成粒度感知的映射键
        
        Args:
            metadata: 文件元数据
        
        Returns:
            映射键字符串
        """
        platform = metadata.get("platform", "generic")
        data_type = metadata.get("data_type", "unknown")
        granularity = metadata.get("granularity", "")
        
        # 对于traffic/services等时序数据，必须包含粒度
        if data_type in ["traffic", "services", "analytics"] and granularity:
            return f"{platform}:{data_type}_{granularity}"
        else:
            # 对于products/orders等非时序数据，粒度不影响字段结构
            return f"{platform}:{data_type}"
    
    def _load_field_rules(self, mapping_key: str) -> Dict[str, List[str]]:
        """
        加载指定映射键的字段映射规则
        
        Args:
            mapping_key: 映射键 (例如: "tiktok:products" 或 "tiktok:traffic_daily")
        
        Returns:
            字段映射规则字典
        """
        # 解析映射键
        parts = mapping_key.split(":")
        if len(parts) != 2:
            logger.warning(f"无效的映射键格式: {mapping_key}")
            return {}
        
        platform, data_spec = parts
        
        # 检查是否包含粒度
        if "_" in data_spec:
            data_type, granularity = data_spec.rsplit("_", 1)
        else:
            data_type = data_spec
            granularity = "common"
        
        # 从配置中获取规则
        try:
            platform_config = self.config.get(platform, {})
            data_type_config = platform_config.get(data_type, {})
            field_rules = data_type_config.get(granularity, {})
            
            if not field_rules:
                logger.warning(f"未找到字段规则: {platform}.{data_type}.{granularity}")
                # 尝试使用通用规则
                generic_config = self.config.get("generic", {})
                generic_data_config = generic_config.get(data_type, {})
                field_rules = generic_data_config.get("common", {})
            
            return field_rules
        except Exception as e:
            logger.error(f"加载字段规则失败: {e}")
            return {}
    
    def _match_column(
        self,
        columns: List[str],
        candidates: List[str],
        std_field: str,
        mapping_key: str
    ) -> Tuple[Optional[str], float, str]:
        """
        使用多策略匹配列名
        
        Args:
            columns: 可用的列名列表
            candidates: 候选列名列表
            std_field: 标准字段名
            mapping_key: 映射键
        
        Returns:
            (matched_column, confidence, method)
        """
        # 策略1: 精确匹配 (100%置信度)
        for candidate in candidates:
            for col in columns:
                if col.strip().lower() == candidate.strip().lower():
                    return col, 100.0, "exact_match"
        
        # 策略2: 历史匹配 (100%置信度)
        if self.history_manager:
            historical_match = self.history_manager.get_mapping(mapping_key, std_field)
            if historical_match and historical_match in columns:
                return historical_match, 100.0, "history_match"
        
        # 策略3: 模糊匹配 (80-95%置信度)
        best_fuzzy_match = None
        best_fuzzy_score = 0

        for candidate in candidates:
            for col in columns:
                # 使用SequenceMatcher计算相似度
                ratio = SequenceMatcher(None, col.strip().lower(), candidate.strip().lower()).ratio()
                score = ratio * 100  # 转换为0-100分数
                if score > best_fuzzy_score and score >= 80:
                    best_fuzzy_score = score
                    best_fuzzy_match = col

        if best_fuzzy_match:
            confidence = min(95.0, best_fuzzy_score * 0.95)
            return best_fuzzy_match, confidence, "fuzzy_match"
        
        # 策略4: 语义匹配 (70-90%置信度)
        synonyms = self.synonyms.get(std_field, [])
        for synonym in synonyms:
            for col in columns:
                if synonym.lower() in col.lower() or col.lower() in synonym.lower():
                    return col, 80.0, "semantic_match"
        
        # 策略5: 部分匹配 (60-75%置信度)
        for candidate in candidates:
            for col in columns:
                if candidate.lower() in col.lower() or col.lower() in candidate.lower():
                    return col, 70.0, "partial_match"
        
        # 未找到匹配
        return None, 0.0, "no_match"
    
    def _calculate_confidence_score(self, mappings: Dict[str, FieldMapping]) -> float:
        """
        计算整体置信度分数
        
        Args:
            mappings: 字段映射字典
        
        Returns:
            整体置信度分数 (0-100)
        """
        if not mappings:
            return 0.0
        
        total_confidence = sum(m.confidence for m in mappings.values())
        avg_confidence = total_confidence / len(mappings)
        
        # 考虑映射成功率
        mapped_count = sum(1 for m in mappings.values() if m.source_column is not None)
        mapping_rate = mapped_count / len(mappings)
        
        # 综合分数 = 平均置信度 * 映射成功率
        return avg_confidence * mapping_rate
    
    def _create_empty_result(
        self,
        mapping_key: str,
        columns: List[str],
        metadata: Dict
    ) -> MappingResult:
        """创建空的映射结果"""
        return MappingResult(
            mapping_key=mapping_key,
            mappings={},
            metadata=metadata,
            unmapped_columns=columns,
            confidence_score=0.0
        )


if __name__ == "__main__":
    # 测试代码
    from loguru import logger
    
    logger.info("=== 智能字段映射引擎测试 ===")
    
    # 创建映射器
    mapper = SmartFieldMapper()
    
    # 测试案例1: TikTok商品数据
    test_columns_1 = [
        "ID", "商品", "状态", "商品交易总额", "成交件数", "订单数",
        "商城商品交易总额", "商城商品成交件数", "商城发品曝光次数"
    ]
    test_metadata_1 = {
        "platform": "tiktok",
        "data_type": "products",
        "granularity": "daily"
    }
    
    result_1 = mapper.map_fields(test_columns_1, test_metadata_1)
    logger.info(f"\n测试案例1: {result_1.mapping_key}")
    logger.info(f"  整体置信度: {result_1.confidence_score:.2f}%")
    logger.info(f"  映射字段数: {len([m for m in result_1.mappings.values() if m.source_column])}/{len(result_1.mappings)}")
    logger.info(f"  未映射列: {result_1.unmapped_columns}")
    
    # 测试案例2: TikTok客流数据（日粒度）
    test_columns_2 = [
        "小时", "页面浏览次数", "去重页面浏览次数", "点击率", "转化率"
    ]
    test_metadata_2 = {
        "platform": "tiktok",
        "data_type": "traffic",
        "granularity": "daily"
    }
    
    result_2 = mapper.map_fields(test_columns_2, test_metadata_2)
    logger.info(f"\n测试案例2: {result_2.mapping_key}")
    logger.info(f"  整体置信度: {result_2.confidence_score:.2f}%")
    logger.info(f"  映射字段数: {len([m for m in result_2.mappings.values() if m.source_column])}/{len(result_2.mappings)}")

