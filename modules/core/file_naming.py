#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
标准化文件命名工具 - 方案B+核心组件

功能：
1. 生成标准化文件名（扁平化存储）
2. 解析标准化文件名（提取元数据）
3. 支持sub_domain识别（services子数据域）

命名格式：{source_platform}_{data_domain}[_{sub_domain}]_{granularity}_{timestamp}.{ext}

示例：
- shopee_products_monthly_20250925_100234.xlsx
- tiktok_services_agent_daily_20250925_001033.xlsx
- miaoshou_inventory_snapshot_20250925_095046.xlsx  # v4.10.0更新：库存快照使用inventory域
"""

from pathlib import Path
from datetime import datetime
from typing import Dict, Optional


class StandardFileName:
    """标准化文件命名工具"""
    
    # 已知的子数据域（用于解析识别）- v4.3.5: 明确包含完整名称
    KNOWN_SUB_DOMAINS = {'agent', 'ai_assistant', 'ai', 'assistant'}
    
    # 已知的数据域
    KNOWN_DATA_DOMAINS = {'orders', 'products', 'services', 'traffic', 'finance', 'analytics', 'inventory'}  # v4.10.0更新：traffic域已废弃（兼容性保留），统一使用analytics域
    
    # 已知的粒度
    KNOWN_GRANULARITIES = {'daily', 'weekly', 'monthly', 'snapshot', 'hourly'}
    
    @staticmethod
    def generate(
        source_platform: str,
        data_domain: str,
        granularity: str,
        sub_domain: str = "",
        ext: str = "xlsx",
        timestamp: Optional[str] = None
    ) -> str:
        """
        生成标准化文件名
        
        Args:
            source_platform: 数据来源平台（shopee/tiktok/miaoshou/amazon）
            data_domain: 数据域（orders/products/inventory/services/traffic/finance/analytics）
            granularity: 时间粒度（daily/weekly/monthly/snapshot）
            sub_domain: 子数据域（agent/ai_assistant，仅services等需要）
            ext: 文件扩展名（默认xlsx）
            timestamp: 时间戳（可选，默认当前时间）
            
        Returns:
            标准化文件名
            
        Examples:
            >>> StandardFileName.generate('shopee', 'products', 'monthly')
            'shopee_products_monthly_20250925_100234.xlsx'
            
            >>> StandardFileName.generate('tiktok', 'services', 'daily', sub_domain='agent')
            'tiktok_services_agent_daily_20250925_100234.xlsx'
            
            >>> StandardFileName.generate('miaoshou', 'inventory', 'snapshot')
            'miaoshou_inventory_snapshot_20250925_100234.xlsx'
        """
        if not timestamp:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        parts = [source_platform.lower(), data_domain.lower()]
        
        if sub_domain:
            parts.append(sub_domain.lower())
        
        parts.extend([granularity.lower(), timestamp])
        
        return "_".join(parts) + f".{ext}"
    
    @staticmethod
    def parse(filename: str) -> Dict:
        """
        解析标准化文件名，提取元数据
        
        Args:
            filename: 文件名（带或不带扩展名）
            
        Returns:
            元数据字典
            
        Raises:
            ValueError: 文件名格式不符合标准
            
        Examples:
            >>> StandardFileName.parse('shopee_products_monthly_20250925_100234.xlsx')
            {
                'source_platform': 'shopee',
                'data_domain': 'products',
                'sub_domain': '',
                'granularity': 'monthly',
                'timestamp': '20250925_100234'
            }
            
            >>> StandardFileName.parse('tiktok_services_agent_daily_20250925_001033.xlsx')
            {
                'source_platform': 'tiktok',
                'data_domain': 'services',
                'sub_domain': 'agent',
                'granularity': 'daily',
                'timestamp': '20250925_001033'
            }
        """
        stem = Path(filename).stem
        parts = stem.split('_')
        
        # 最少4部分：platform_domain_granularity_timestamp
        if len(parts) < 4:
            raise ValueError(f"文件名格式不符合标准: {filename} (至少需要4部分)")
        
        metadata = {
            'source_platform': parts[0],
            'data_domain': parts[1],
            'sub_domain': '',
            'granularity': '',
            'timestamp': ''
        }
        
        # 判断是否有sub_domain
        # 格式1：platform_domain_subdomain_granularity_timestamp (至少5部分)
        # 格式2：platform_domain_sub1_sub2_granularity_timestamp（子域可能被分割，如ai_assistant）
        # 格式3：platform_domain_granularity_timestamp (4部分)
        
        # v4.3.5: 智能识别复合子域（如ai_assistant）
        if len(parts) >= 6 and parts[2] == 'ai' and parts[3] == 'assistant':
            # 特殊处理：ai_assistant被分割成两部分
            metadata['sub_domain'] = 'ai_assistant'
            metadata['granularity'] = parts[4]
            # timestamp可能是两部分：YYYYMMDD_HHMMSS
            if len(parts) >= 7:
                metadata['timestamp'] = '_'.join(parts[5:7])
            else:
                metadata['timestamp'] = parts[5]
        elif len(parts) >= 5 and parts[2] in StandardFileName.KNOWN_SUB_DOMAINS:
            # 有子域：platform_domain_subdomain_granularity_timestamp
            metadata['sub_domain'] = parts[2]
            metadata['granularity'] = parts[3]
            # timestamp可能是两部分：YYYYMMDD_HHMMSS
            if len(parts) >= 6:
                metadata['timestamp'] = '_'.join(parts[4:6])
            else:
                metadata['timestamp'] = parts[4]
        else:
            # 无子域：platform_domain_granularity_timestamp
            metadata['granularity'] = parts[2]
            # timestamp可能是两部分
            if len(parts) >= 5:
                metadata['timestamp'] = '_'.join(parts[3:5])
            else:
                metadata['timestamp'] = parts[3]
        
        return metadata
    
    @staticmethod
    def validate(filename: str) -> bool:
        """
        验证文件名是否符合标准格式
        
        Args:
            filename: 文件名
            
        Returns:
            是否符合标准
        """
        try:
            metadata = StandardFileName.parse(filename)
            
            # 验证平台、数据域、粒度是否在已知列表中
            if metadata['data_domain'] not in StandardFileName.KNOWN_DATA_DOMAINS:
                return False
            
            if metadata['granularity'] not in StandardFileName.KNOWN_GRANULARITIES:
                return False
            
            return True
        except ValueError:
            return False
    
    @staticmethod
    def get_template_key(
        source_platform: str,
        data_domain: str,
        granularity: str,
        sub_domain: str = ""
    ) -> str:
        """
        生成模板匹配键（3级精确匹配）
        
        Args:
            source_platform: 数据来源平台
            data_domain: 数据域
            granularity: 时间粒度
            sub_domain: 子数据域（可选）
            
        Returns:
            模板键
            
        Examples:
            >>> StandardFileName.get_template_key('shopee', 'orders', 'monthly')
            'shopee_orders_monthly'
            
            >>> StandardFileName.get_template_key('tiktok', 'services', 'daily', 'agent')
            'tiktok_services_agent_daily'
        """
        parts = [source_platform, data_domain]
        if sub_domain:
            parts.append(sub_domain)
        parts.append(granularity)
        return "_".join(parts)


# 便捷函数
def generate_filename(**kwargs) -> str:
    """便捷函数：生成标准化文件名"""
    return StandardFileName.generate(**kwargs)


def parse_filename(filename: str) -> Dict:
    """便捷函数：解析标准化文件名"""
    return StandardFileName.parse(filename)


def validate_filename(filename: str) -> bool:
    """便捷函数：验证文件名格式"""
    return StandardFileName.validate(filename)

