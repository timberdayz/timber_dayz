#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
映射历史管理器

功能:
1. 读取和写入映射历史（data/mapping_history.json）
2. 支持用户确认的映射记录持久化
3. 支持映射历史查询和应用

作者: AI 专家级数据工程师
创建日期: 2025-01-26
"""

import json
from pathlib import Path
from typing import Dict, Optional
from datetime import datetime
from loguru import logger


class MappingHistoryManager:
    """映射历史管理器"""
    
    def __init__(self, history_file: str = "data/mapping_history.json"):
        """
        初始化映射历史管理器
        
        Args:
            history_file: 映射历史文件路径
        """
        self.history_file = Path(history_file)
        self.history = self._load_history()
    
    def _load_history(self) -> Dict:
        """加载映射历史"""
        if not self.history_file.exists():
            logger.info(f"映射历史文件不存在，创建新文件: {self.history_file}")
            self._save_history({})
            return {}
        
        try:
            with open(self.history_file, 'r', encoding='utf-8') as f:
                history = json.load(f)
            logger.info(f"已加载映射历史: {len(history)} 个映射键")
            return history
        except Exception as e:
            logger.error(f"加载映射历史失败: {e}")
            return {}
    
    def _save_history(self, history: Dict) -> bool:
        """保存映射历史"""
        try:
            # 确保目录存在
            self.history_file.parent.mkdir(parents=True, exist_ok=True)
            
            with open(self.history_file, 'w', encoding='utf-8') as f:
                json.dump(history, f, ensure_ascii=False, indent=2)
            logger.info(f"已保存映射历史: {len(history)} 个映射键")
            return True
        except Exception as e:
            logger.error(f"保存映射历史失败: {e}")
            return False
    
    def get_mapping(self, mapping_key: str, standard_field: str) -> Optional[str]:
        """
        获取历史映射
        
        Args:
            mapping_key: 映射键 (例如: "tiktok:products")
            standard_field: 标准字段名
        
        Returns:
            源列名（如果存在历史映射）
        """
        if mapping_key not in self.history:
            return None
        
        key_history = self.history[mapping_key]
        if "mappings" not in key_history:
            return None
        
        return key_history["mappings"].get(standard_field)
    
    def save_mapping(
        self,
        mapping_key: str,
        standard_field: str,
        source_column: str,
        confidence: float = 100.0,
        method: str = "user_confirmed"
    ) -> bool:
        """
        保存单个字段映射
        
        Args:
            mapping_key: 映射键
            standard_field: 标准字段名
            source_column: 源列名
            confidence: 置信度
            method: 映射方法
        
        Returns:
            是否保存成功
        """
        if mapping_key not in self.history:
            self.history[mapping_key] = {
                "mappings": {},
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat(),
                "version": "1.0"
            }
        
        # 更新映射
        self.history[mapping_key]["mappings"][standard_field] = source_column
        self.history[mapping_key]["updated_at"] = datetime.now().isoformat()
        
        # 保存元数据（可选）
        if "metadata" not in self.history[mapping_key]:
            self.history[mapping_key]["metadata"] = {}
        
        self.history[mapping_key]["metadata"][standard_field] = {
            "confidence": confidence,
            "method": method,
            "confirmed_at": datetime.now().isoformat()
        }
        
        return self._save_history(self.history)
    
    def save_batch_mappings(
        self,
        mapping_key: str,
        mappings: Dict[str, str],
        metadata: Optional[Dict] = None
    ) -> bool:
        """
        批量保存字段映射
        
        Args:
            mapping_key: 映射键
            mappings: 字段映射字典 {standard_field: source_column}
            metadata: 可选的元数据
        
        Returns:
            是否保存成功
        """
        if mapping_key not in self.history:
            self.history[mapping_key] = {
                "mappings": {},
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat(),
                "version": "1.0"
            }
        
        # 批量更新映射
        self.history[mapping_key]["mappings"].update(mappings)
        self.history[mapping_key]["updated_at"] = datetime.now().isoformat()
        
        # 保存元数据
        if metadata:
            if "metadata" not in self.history[mapping_key]:
                self.history[mapping_key]["metadata"] = {}
            self.history[mapping_key]["metadata"].update(metadata)
        
        return self._save_history(self.history)
    
    def get_all_mappings(self, mapping_key: str) -> Dict[str, str]:
        """
        获取指定映射键的所有映射
        
        Args:
            mapping_key: 映射键
        
        Returns:
            字段映射字典
        """
        if mapping_key not in self.history:
            return {}
        
        return self.history[mapping_key].get("mappings", {})
    
    def delete_mapping(self, mapping_key: str, standard_field: Optional[str] = None) -> bool:
        """
        删除映射
        
        Args:
            mapping_key: 映射键
            standard_field: 标准字段名（如果为None，删除整个映射键）
        
        Returns:
            是否删除成功
        """
        if mapping_key not in self.history:
            logger.warning(f"映射键不存在: {mapping_key}")
            return False
        
        if standard_field is None:
            # 删除整个映射键
            del self.history[mapping_key]
            logger.info(f"已删除映射键: {mapping_key}")
        else:
            # 删除单个字段映射
            if standard_field in self.history[mapping_key]["mappings"]:
                del self.history[mapping_key]["mappings"][standard_field]
                logger.info(f"已删除字段映射: {mapping_key}.{standard_field}")
            else:
                logger.warning(f"字段映射不存在: {mapping_key}.{standard_field}")
                return False
        
        return self._save_history(self.history)
    
    def get_statistics(self) -> Dict:
        """
        获取映射历史统计信息
        
        Returns:
            统计信息字典
        """
        total_keys = len(self.history)
        total_mappings = sum(
            len(v.get("mappings", {})) for v in self.history.values()
        )
        
        # 按平台统计
        platform_stats = {}
        for key in self.history.keys():
            if ":" in key:
                platform = key.split(":")[0]
                platform_stats[platform] = platform_stats.get(platform, 0) + 1
        
        return {
            "total_mapping_keys": total_keys,
            "total_field_mappings": total_mappings,
            "platforms": platform_stats,
            "last_updated": max(
                (v.get("updated_at", "") for v in self.history.values()),
                default=""
            )
        }
    
    def export_to_yaml(self, output_file: str) -> bool:
        """
        导出映射历史到YAML文件
        
        Args:
            output_file: 输出文件路径
        
        Returns:
            是否导出成功
        """
        try:
            import yaml
            
            with open(output_file, 'w', encoding='utf-8') as f:
                yaml.dump(self.history, f, allow_unicode=True, default_flow_style=False)
            
            logger.info(f"已导出映射历史到: {output_file}")
            return True
        except Exception as e:
            logger.error(f"导出映射历史失败: {e}")
            return False


if __name__ == "__main__":
    # 测试代码
    from loguru import logger
    
    logger.info("=== 映射历史管理器测试 ===")
    
    # 创建管理器
    manager = MappingHistoryManager()
    
    # 测试保存映射
    logger.info("\n测试1: 保存单个映射")
    manager.save_mapping(
        mapping_key="tiktok:products",
        standard_field="product_id",
        source_column="ID",
        confidence=100.0,
        method="exact_match"
    )
    
    # 测试批量保存
    logger.info("\n测试2: 批量保存映射")
    manager.save_batch_mappings(
        mapping_key="tiktok:products",
        mappings={
            "product_name": "商品",
            "status": "状态",
            "gmv": "商品交易总额"
        }
    )
    
    # 测试查询
    logger.info("\n测试3: 查询映射")
    product_id_mapping = manager.get_mapping("tiktok:products", "product_id")
    logger.info(f"  product_id -> {product_id_mapping}")
    
    all_mappings = manager.get_all_mappings("tiktok:products")
    logger.info(f"  所有映射: {all_mappings}")
    
    # 测试统计
    logger.info("\n测试4: 统计信息")
    stats = manager.get_statistics()
    logger.info(f"  {stats}")
    
    logger.info("\n[OK] 映射历史管理器测试完成")

