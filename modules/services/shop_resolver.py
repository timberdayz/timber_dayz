#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ShopResolver - 全域店铺归属解析器

功能：
- 从文件路径/元数据/配置多策略解析shop_id
- 返回置信度与来源，便于审计
- 失败时提供可操作建议

优先级：
1. .meta.json伴生文件
2. 路径规则（profiles/<platform>/<account>/<shop_id>/...）
3. config/platform_accounts/*.json别名映射
4. local_accounts.py店铺映射
5. 文件名正则提取
6. config/shop_aliases.yaml人工映射表
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional
import json
import re

from modules.core.logger import get_logger

logger = get_logger(__name__)


@dataclass
class ResolvedShop:
    """店铺解析结果"""
    shop_id: Optional[str]
    confidence: float  # 0.0 - 1.0
    source: str  # meta_json | path_rule | config_alias | filename | manual_mapping | failed
    detail: str  # 详细说明


class ShopResolver:
    """全域店铺解析器"""
    
    def __init__(self, db_session=None):
        """
        初始化店铺解析器
        
        v4.3.6: 改用数据库+缓存（现代化ERP标准）
        - YAML仅作导入/导出通道
        - 运行时从account_aliases表+内存缓存读取
        """
        self._db_session = db_session
        self._alias_cache: Dict[str, str] = {}
        # YAML不再在线读取（已废弃）
    
    def _load_db_aliases(self):
        """从数据库加载别名到缓存（按需加载）"""
        if not self._db_session or self._alias_cache:
            return  # 已加载或无DB会话
        
        try:
            from modules.core.db import AccountAlias
            from sqlalchemy import select
            
            stmt = select(AccountAlias).where(AccountAlias.active == True)
            aliases = self._db_session.execute(stmt).scalars().all()
            
            for alias in aliases:
                # 构建查找key（兼容旧格式）
                key = f"{alias.platform}:{alias.account or ''}:{alias.site or ''}:{alias.store_label_raw}"
                self._alias_cache[key] = alias.target_id
            
            logger.debug(f"从数据库加载店铺别名: {len(self._alias_cache)}条")
        except Exception as e:
            logger.warning(f"加载数据库别名失败（可能表未创建）: {e}")
    
    def resolve(
        self,
        file_path: str,
        platform_code: Optional[str] = None,
        file_metadata: Optional[Dict] = None
    ) -> ResolvedShop:
        """
        解析店铺归属（仅从.meta.json提取）
        
        [*] 修改：只从.meta.json伴生文件中提取shop_id，不从其他来源提取
        
        Args:
            file_path: 文件路径
            platform_code: 平台代码（保留参数以兼容，但不使用）
            file_metadata: 文件元数据（保留参数以兼容，但不使用）
            
        Returns:
            ResolvedShop: 解析结果
        """
        path = Path(file_path)
        
        # [*] 唯一策略：.meta.json伴生文件
        meta_file = path.with_suffix('.meta.json')
        if meta_file.exists():
            try:
                with open(meta_file, 'r', encoding='utf-8') as f:
                    meta = json.load(f)
                    
                    # 尝试从 business_metadata 提取
                    shop_id = meta.get('business_metadata', {}).get('shop_id')
                    if shop_id:
                        return ResolvedShop(
                            shop_id=str(shop_id).strip(),
                            confidence=0.95,
                            source='meta_json',
                            detail=f'从{meta_file.name}的business_metadata读取'
                        )
                    
                    # 尝试从 collection_info 提取（兼容旧格式）
                    shop_id = meta.get('collection_info', {}).get('shop_id')
                    if shop_id:
                        return ResolvedShop(
                            shop_id=str(shop_id).strip(),
                            confidence=0.90,
                            source='meta_json',
                            detail=f'从{meta_file.name}的collection_info读取'
                        )
            except Exception as e:
                logger.debug(f"读取.meta.json失败: {e}")
        
        # [*] 如果没有.meta.json或其中没有shop_id，返回失败（但不阻止同步）
        return ResolvedShop(
            shop_id=None,
            confidence=0.0,
            source='meta_json_not_found',
            detail=f'.meta.json文件不存在或其中没有shop_id字段'
        )
    
    def _extract_shop_from_path(self, path: Path, platform_code: str) -> Optional[str]:
        """从路径提取店铺ID（profiles/<platform>/<account>/<shop_id>/...）"""
        try:
            parts = [p.lower() for p in path.parts]
            pc = platform_code.lower()
            
            # 查找平台目录索引
            platform_idx = -1
            for i, p in enumerate(parts):
                if pc in p:
                    platform_idx = i
                    break
            
            if platform_idx >= 0 and platform_idx + 2 < len(parts):
                # profiles/<platform>/<account>/<shop_id>
                candidate = parts[platform_idx + 2]
                # 验证：至少6位数字或包含连字符
                if len(candidate) >= 6 or '-' in candidate or '.' in candidate:
                    return candidate
            
        except Exception as e:
            logger.debug(f"路径提取失败: {e}")
        return None
    
    def _lookup_platform_accounts(self, platform_code: str, filename: str) -> Optional[str]:
        """从config/platform_accounts/*.json查找店铺别名"""
        try:
            config_file = Path(f"config/platform_accounts/{platform_code}.json")
            if not config_file.exists():
                return None
            
            with open(config_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                # 简单匹配：filename包含alias则返回对应shop_id
                for account_data in data.get('accounts', []):
                    for shop in account_data.get('shops', []):
                        alias = shop.get('alias', '').lower()
                        if alias and alias in filename.lower():
                            return shop.get('shop_id')
        except Exception as e:
            logger.debug(f"查找platform_accounts失败: {e}")
        return None
    
    def _lookup_local_accounts(self, platform_code: Optional[str], filename: str) -> Optional[str]:
        """从local_accounts.py查找店铺映射"""
        try:
            # 动态导入local_accounts
            import sys
            if 'local_accounts' in sys.modules:
                del sys.modules['local_accounts']
            
            import local_accounts
            
            # 查找ACCOUNTS列表
            accounts = getattr(local_accounts, 'ACCOUNTS', [])
            for acc in accounts:
                if not isinstance(acc, dict):
                    continue
                if platform_code and acc.get('platform', '').lower() != platform_code.lower():
                    continue
                
                # 检查shops列表
                for shop in acc.get('shops', []):
                    shop_id = shop.get('shop_id', '')
                    shop_name = shop.get('shop_name', '')
                    # 文件名包含shop_id或shop_name
                    if shop_id and shop_id.lower() in filename.lower():
                        return shop_id
                    if shop_name and shop_name.lower() in filename.lower():
                        return shop_id
        except Exception as e:
            logger.debug(f"查找local_accounts失败: {e}")
        return None
    
    def _extract_shop_from_filename(self, filename: str, platform_code: Optional[str]) -> Optional[str]:
        """从文件名正则提取店铺ID"""
        try:
            # 模式1：shop_<id>
            m = re.search(r'shop_([a-zA-Z0-9_\-\.]+)', filename, re.IGNORECASE)
            if m:
                candidate = m.group(1)
                # [*] v4.17.0修复：排除包含日期或snapshot的模式
                if not (re.search(r'\d{8}', candidate) or '_snapshot_' in candidate.lower()):
                    return candidate
            
            # 模式2：<platform>_<shop_id>_...
            if platform_code:
                pattern = rf'{re.escape(platform_code)}_([a-zA-Z0-9_\-\.]+)_'
                m = re.search(pattern, filename, re.IGNORECASE)
                if m:
                    candidate = m.group(1)
                    # [*] v4.17.0修复：排除包含日期或snapshot的模式
                    has_date_pattern = bool(re.search(r'\d{8}', candidate))
                    has_snapshot = '_snapshot_' in candidate.lower()
                    if has_date_pattern or has_snapshot:
                        return None
                    # 排除常见非店铺标识（orders/products/traffic等）
                    excluded = {'orders', 'products', 'traffic', 'services', 'daily', 'weekly', 'monthly', 'inventory', 'snapshot'}
                    if candidate.lower() not in excluded:
                        return candidate
            
            # 模式3：纯数字ID（至少8位）
            # [WARN] 注意：8位数字可能是日期（YYYYMMDD），需要谨慎处理
            # 对于miaoshou平台，8位数字很可能是日期，不应作为shop_id
            m = re.search(r'(\d{8,})', filename)
            if m:
                candidate = m.group(1)
                # 如果平台是miaoshou，且8位数字看起来像日期（在合理范围内），跳过
                if platform_code and platform_code.lower() == 'miaoshou':
                    # 检查是否是合理的日期范围（2000-2099）
                    if len(candidate) == 8 and candidate.startswith(('20', '21')):
                        return None
                return candidate
            
        except Exception as e:
            logger.debug(f"文件名提取失败: {e}")
        return None


# 全局单例
_resolver_instance: Optional[ShopResolver] = None


def get_shop_resolver() -> ShopResolver:
    """获取店铺解析器单例"""
    global _resolver_instance
    if _resolver_instance is None:
        _resolver_instance = ShopResolver()
    return _resolver_instance

