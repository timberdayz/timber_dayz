#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
账号对齐服务 - v4.3.6

功能：
- 基于account_aliases表，将妙手(miaoshou)导出的订单数据对齐到标准账号ID
- 仅影响platform=miaoshou且data_domain=orders的数据
- 支持批量回填历史数据和增量对齐新数据
"""

from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from sqlalchemy.orm import Session
from sqlalchemy import select, and_, func, text

from modules.core.db import AccountAlias, FactOrder
from modules.core.logger import get_logger

logger = get_logger(__name__)


@dataclass
class AlignmentStats:
    """对齐统计"""
    total_orders: int = 0
    aligned: int = 0
    unaligned: int = 0
    coverage_rate: float = 0.0
    unique_raw_labels: int = 0
    missing_mappings: List[str] = None  # 缺失的映射（待补充）


class AccountAlignmentService:
    """账号对齐服务（仅针对miaoshou/orders）"""
    
    def __init__(self, db: Session):
        self.db = db
        self._alias_cache: Dict[Tuple, str] = {}
        self._load_alias_cache()
    
    def _load_alias_cache(self):
        """加载别名映射到内存缓存"""
        try:
            stmt = select(AccountAlias).where(
                AccountAlias.active == True,
                AccountAlias.platform == 'miaoshou',
                AccountAlias.data_domain == 'orders'
            )
            aliases = self.db.execute(stmt).scalars().all()
            
            for alias in aliases:
                # 缓存key：(account, site, store_label_raw)
                # site可选（None时仅按account+label匹配）
                key = (
                    alias.account or '',
                    alias.site or '',
                    alias.store_label_raw
                )
                self._alias_cache[key] = alias.target_id
            
            logger.info(f"[AccountAlignment] 加载{len(self._alias_cache)}条别名映射")
            
        except Exception as e:
            logger.warning(f"[AccountAlignment] 加载别名失败: {e}")
    
    def align_order(
        self,
        account: Optional[str],
        site: Optional[str],
        store_label_raw: Optional[str],
        platform_code: Optional[str] = None  # [*] v4.6.1新增：平台代码
    ) -> Optional[str]:
        """
        对齐单个订单（v4.6.1增强 - 支持部分匹配和自动认领）
        
        Args:
            account: 采购账号或原始账号名（如"3C店"）
            site: 站点
            store_label_raw: 原始店铺名（如"3C店"）
            platform_code: 平台代码（如"shopee"、"miaoshou"）
            
        Returns:
            str: 标准账号ID，未找到返回None
        """
        # [*] v4.6.1增强：如果account字段有值，优先使用account进行匹配
        match_label = account or store_label_raw
        
        if not match_label:
            return None
        
        # 1. 尝试精确匹配（优先使用AccountAlias表）
        # 尝试精确匹配（account + site + label）
        key_full = (account or '', site or '', match_label)
        if key_full in self._alias_cache:
            return self._alias_cache[key_full]
        
        # 尝试宽松匹配（仅account + label，忽略site）
        key_loose = (account or '', '', match_label)
        if key_loose in self._alias_cache:
            return self._alias_cache[key_loose]
        
        # 尝试最宽松匹配（仅label，忽略account和site）
        for (cached_acc, cached_site, cached_label), target in self._alias_cache.items():
            if cached_label == match_label:
                return target
        
        # [*] v4.6.1新增：2. 尝试部分匹配（从local_accounts.py读取账号列表）
        if platform_code:
            matched_account_id = self._try_partial_match(match_label, platform_code)
            if matched_account_id:
                # 自动创建AccountAlias映射记录（方便后续查询）
                self._auto_create_alias(
                    platform_code=platform_code,
                    account=account,
                    site=site,
                    store_label_raw=match_label,
                    target_id=matched_account_id
                )
                return matched_account_id
        
        return None
    
    def _try_partial_match(self, account_label: str, platform_code: str) -> Optional[str]:
        """
        尝试部分匹配账号（v4.6.1增强 - 支持another_name字段）
        
        匹配规则（优先级递减）：
        1. another_name精确匹配：account_label == another_name（最高优先级）
        2. another_name包含匹配：account_label in another_name
        3. account_id精确匹配：account_label == account_id
        4. account_id包含匹配：account_label in account_id（如"3C店"匹配"shopee新加坡3C店"）
        5. account_id后缀匹配：account_id.endswith(account_label)
        
        Args:
            account_label: 原始账号标签（如"3C店"）
            platform_code: 平台代码（如"shopee"）
            
        Returns:
            str: 匹配的标准账号ID，未找到返回None
        """
        try:
            # 加载local_accounts.py中的账号列表
            accounts = self._load_local_accounts()
            
            if not accounts:
                return None
            
            # 过滤同一平台的账号
            platform_accounts = [
                acc for acc in accounts
                if acc.get('platform', '').lower() == platform_code.lower()
            ]
            
            if not platform_accounts:
                return None
            
            # [*] v4.6.1新增：1. another_name精确匹配（最高优先级）
            for acc in platform_accounts:
                another_name = acc.get('another_name')
                if another_name and another_name == account_label:
                    logger.info(f"[AccountAlignment] another_name精确匹配: '{account_label}' -> '{acc.get('account_id')}'")
                    return acc.get('account_id')
            
            # [*] v4.6.1新增：2. another_name包含匹配
            for acc in platform_accounts:
                another_name = acc.get('another_name')
                if another_name and account_label in another_name:
                    logger.info(f"[AccountAlignment] another_name包含匹配: '{account_label}' -> '{acc.get('account_id')}'")
                    return acc.get('account_id')
            
            # 3. account_id精确匹配
            for acc in platform_accounts:
                account_id = acc.get('account_id', '')
                if account_id == account_label:
                    logger.info(f"[AccountAlignment] account_id精确匹配: '{account_label}' -> '{account_id}'")
                    return account_id
            
            # 4. account_id包含匹配（account_label包含在account_id中）
            for acc in platform_accounts:
                account_id = acc.get('account_id', '')
                if account_label in account_id:
                    logger.info(f"[AccountAlignment] account_id包含匹配: '{account_label}' -> '{account_id}'")
                    return account_id
            
            # 5. account_id后缀匹配（account_id以account_label结尾）
            for acc in platform_accounts:
                account_id = acc.get('account_id', '')
                if account_id.endswith(account_label):
                    logger.info(f"[AccountAlignment] account_id后缀匹配: '{account_label}' -> '{account_id}'")
                    return account_id
            
            return None
            
        except Exception as e:
            logger.warning(f"[AccountAlignment] 部分匹配失败: {e}")
            return None
    
    def _load_local_accounts(self) -> List[Dict]:
        """加载local_accounts.py中的账号列表（v4.6.1新增）"""
        try:
            import importlib.util
            import sys
            from pathlib import Path
            
            local_accounts_path = Path("local_accounts.py")
            if not local_accounts_path.exists():
                return []
            
            spec = importlib.util.spec_from_file_location("local_accounts", str(local_accounts_path))
            local_accounts = importlib.util.module_from_spec(spec)
            sys.modules["local_accounts"] = local_accounts
            spec.loader.exec_module(local_accounts)
            
            all_accounts = []
            for group, accounts_list in getattr(local_accounts, "LOCAL_ACCOUNTS", {}).items():
                all_accounts.extend(accounts_list)
            
            return all_accounts
            
        except Exception as e:
            logger.warning(f"[AccountAlignment] 加载local_accounts.py失败: {e}")
            return []
    
    def _auto_create_alias(
        self,
        platform_code: str,
        account: Optional[str],
        site: Optional[str],
        store_label_raw: str,
        target_id: str,
        confidence: float = 0.8  # [*] 自动匹配的置信度较低（0.8），人工确认=1.0
    ):
        """
        自动创建AccountAlias映射记录（v4.6.1新增）
        
        注意：如果映射已存在，不会重复创建
        """
        try:
            from sqlalchemy import select
            
            # 检查是否已存在
            existing = self.db.execute(
                select(AccountAlias).where(
                    AccountAlias.platform == platform_code,
                    AccountAlias.account == (account or ''),
                    AccountAlias.site == (site or ''),
                    AccountAlias.store_label_raw == store_label_raw,
                    AccountAlias.active == True
                )
            ).scalar_one_or_none()
            
            if existing:
                # 如果已存在但target_id不同，更新它
                if existing.target_id != target_id:
                    existing.target_id = target_id
                    existing.confidence = confidence
                    existing.updated_by = 'system_auto_match'
                    self.db.commit()
                    logger.info(f"[AccountAlignment] 更新映射: '{store_label_raw}' -> '{target_id}'")
                return
            
            # 创建新映射
            new_alias = AccountAlias(
                platform=platform_code,
                data_domain='orders',
                account=account,
                site=site,
                store_label_raw=store_label_raw,
                target_type='account',
                target_id=target_id,
                confidence=confidence,
                active=True,
                created_by='system_auto_match',
                notes=f'自动匹配（部分匹配：{store_label_raw} -> {target_id}）'
            )
            
            self.db.add(new_alias)
            self.db.commit()
            
            # 更新缓存
            key = (account or '', site or '', store_label_raw)
            self._alias_cache[key] = target_id
            
            logger.info(f"[AccountAlignment] 自动创建映射: '{store_label_raw}' -> '{target_id}'")
            
        except Exception as e:
            logger.warning(f"[AccountAlignment] 自动创建映射失败: {e}")
            self.db.rollback()
    
    def backfill_alignment(self, limit: int = None) -> AlignmentStats:
        """
        回填历史数据的aligned_account_id
        
        Args:
            limit: 限制处理数量（None=全量）
            
        Returns:
            AlignmentStats: 对齐统计
        """
        logger.info("=" * 60)
        logger.info("[Backfill] 开始回填aligned_account_id...")
        logger.info("=" * 60)
        
        stats = AlignmentStats(missing_mappings=[])
        
        try:
            # 查询需要对齐的订单（仅miaoshou且shop_id=none）
            stmt = select(FactOrder).where(
                FactOrder.platform_code == 'miaoshou',
                FactOrder.shop_id == 'none'
            )
            
            if limit:
                stmt = stmt.limit(limit)
            
            orders = self.db.execute(stmt).scalars().all()
            stats.total_orders = len(orders)
            
            logger.info(f"  待对齐订单: {stats.total_orders}条")
            
            # 统计缺失的映射
            missing_labels = set()
            
            for order in orders:
                # 尝试对齐（v4.6.1增强：传递platform_code参数）
                aligned_id = self.align_order(
                    order.account,
                    order.site,
                    order.store_label_raw,
                    platform_code=order.platform_code  # [*] v4.6.1新增：传递platform_code
                )
                
                if aligned_id:
                    order.aligned_account_id = aligned_id
                    stats.aligned += 1
                else:
                    stats.unaligned += 1
                    if order.store_label_raw:
                        missing_labels.add(
                            f"{order.account or 'N/A'}|{order.site or 'N/A'}|{order.store_label_raw}"
                        )
            
            # 提交
            self.db.commit()
            
            # 计算覆盖率
            if stats.total_orders > 0:
                stats.coverage_rate = (stats.aligned / stats.total_orders) * 100
            
            stats.missing_mappings = sorted(list(missing_labels))
            
            logger.info("\n" + "=" * 60)
            logger.info("[Backfill] 回填完成！")
            logger.info("=" * 60)
            logger.info(f"  总订单数: {stats.total_orders}")
            logger.info(f"  已对齐: {stats.aligned} ({stats.coverage_rate:.1f}%)")
            logger.info(f"  未对齐: {stats.unaligned}")
            logger.info(f"  缺失映射数: {len(stats.missing_mappings)}")
            
            if stats.missing_mappings:
                logger.warning("\n  [待补充] 以下店铺别名缺失映射:")
                for label in stats.missing_mappings[:20]:
                    logger.warning(f"    - {label}")
                if len(stats.missing_mappings) > 20:
                    logger.warning(f"    ... 还有{len(stats.missing_mappings) - 20}个")
            
            return stats
            
        except Exception as e:
            self.db.rollback()
            logger.error(f"[Backfill] 失败: {e}", exc_info=True)
            raise
    
    def get_alignment_stats(self) -> AlignmentStats:
        """
        获取对齐统计（不执行回填）
        
        Returns:
            AlignmentStats: 统计信息
        """
        stats = AlignmentStats(missing_mappings=[])
        
        try:
            # 统计总订单数
            total = self.db.execute(
                select(func.count(FactOrder.order_id)).where(
                    FactOrder.platform_code == 'miaoshou',
                    FactOrder.shop_id == 'none'
                )
            ).scalar()
            
            stats.total_orders = total or 0
            
            # 统计已对齐数量
            aligned = self.db.execute(
                select(func.count(FactOrder.order_id)).where(
                    FactOrder.platform_code == 'miaoshou',
                    FactOrder.shop_id == 'none',
                    FactOrder.aligned_account_id.isnot(None)
                )
            ).scalar()
            
            stats.aligned = aligned or 0
            stats.unaligned = stats.total_orders - stats.aligned
            
            if stats.total_orders > 0:
                stats.coverage_rate = (stats.aligned / stats.total_orders) * 100
            
            # 统计唯一的raw店铺名数量
            unique_labels = self.db.execute(
                select(func.count(func.distinct(FactOrder.store_label_raw))).where(
                    FactOrder.platform_code == 'miaoshou',
                    FactOrder.shop_id == 'none',
                    FactOrder.store_label_raw.isnot(None)
                )
            ).scalar()
            
            stats.unique_raw_labels = unique_labels or 0
            
            return stats
            
        except Exception as e:
            logger.error(f"获取统计失败: {e}")
            return stats
    
    def suggest_missing_mappings(self, min_orders: int = 5) -> List[Dict]:
        """
        生成缺失映射建议（按订单数量排序）
        
        Args:
            min_orders: 最小订单数（过滤低频店铺）
            
        Returns:
            list: 建议映射列表
        """
        try:
            # 查询未对齐的店铺名及其订单数
            stmt = text("""
                SELECT 
                    account,
                    site,
                    store_label_raw,
                    COUNT(*) as order_count,
                    MIN(order_date_local) as first_order_date,
                    MAX(order_date_local) as last_order_date
                FROM fact_orders
                WHERE platform_code = 'miaoshou'
                  AND shop_id = 'none'
                  AND aligned_account_id IS NULL
                  AND store_label_raw IS NOT NULL
                GROUP BY account, site, store_label_raw
                HAVING COUNT(*) >= :min_orders
                ORDER BY COUNT(*) DESC
            """)
            
            results = self.db.execute(stmt, {"min_orders": min_orders}).all()
            
            suggestions = []
            for row in results:
                suggestions.append({
                    'account': row[0],
                    'site': row[1],
                    'store_label_raw': row[2],
                    'order_count': row[3],
                    'first_order_date': str(row[4]) if row[4] else None,
                    'last_order_date': str(row[5]) if row[5] else None,
                    'suggested_target_id': self._generate_target_id_suggestion(
                        row[0], row[1], row[2]
                    )
                })
            
            return suggestions
            
        except Exception as e:
            logger.error(f"生成建议失败: {e}")
            return []
    
    def _generate_target_id_suggestion(
        self,
        account: Optional[str],
        site: Optional[str],
        store_label: str
    ) -> str:
        """
        生成建议的target_id
        
        逻辑：
        - 账号前缀 + 站点简称 + 店铺序号
        - 示例：虾皮巴西_东朗 + 菲律宾 + 1店 -> shopee_ph_1
        """
        # 简化账号名（取前缀）
        acc_prefix = 'shopee'  # 默认
        if account:
            if '虾皮' in account or 'shopee' in account.lower():
                acc_prefix = 'shopee'
            elif 'tiktok' in account.lower():
                acc_prefix = 'tiktok'
        
        # 站点简称
        site_code = ''
        if site:
            site_map = {
                '菲律宾': 'ph',
                '新加坡': 'sg',
                '马来': 'my',
                '马来西亚': 'my',
                '泰国': 'th',
                '越南': 'vn',
                '印尼': 'id',
                '巴西': 'br'
            }
            site_code = site_map.get(site, site.lower()[:2])
        
        # 店铺标识（从label提取）
        shop_suffix = ''
        import re
        # 提取数字（如"1店"->"1"）
        match = re.search(r'(\d+)店', store_label)
        if match:
            shop_suffix = match.group(1)
        elif '3c' in store_label.lower() or '3C' in store_label:
            shop_suffix = '3c'
        elif '玩具' in store_label:
            shop_suffix = 'toys'
        else:
            # 使用完整label（简化）
            shop_suffix = re.sub(r'[^\w]', '_', store_label.lower())[:10]
        
        # 组合
        if site_code and shop_suffix:
            return f"{acc_prefix}_{site_code}_{shop_suffix}"
        elif shop_suffix:
            return f"{acc_prefix}_{shop_suffix}"
        else:
            return f"{acc_prefix}_unknown"
    
    def add_alias(
        self,
        account: str,
        site: str,
        store_label_raw: str,
        target_id: str,
        notes: str = None,
        created_by: str = 'manual'
    ) -> bool:
        """
        添加别名映射
        
        Args:
            account: 采购账号
            site: 站点
            store_label_raw: 原始店铺名
            target_id: 标准账号ID
            notes: 备注
            created_by: 创建人
            
        Returns:
            bool: 是否成功
        """
        try:
            alias = AccountAlias(
                platform='miaoshou',
                data_domain='orders',
                account=account,
                site=site,
                store_label_raw=store_label_raw,
                target_type='account',
                target_id=target_id,
                confidence=1.0,
                active=True,
                notes=notes,
                created_by=created_by
            )
            
            self.db.add(alias)
            self.db.commit()
            
            # 更新缓存
            key = (account or '', site or '', store_label_raw)
            self._alias_cache[key] = target_id
            
            logger.info(f"[AddAlias] {store_label_raw} -> {target_id}")
            return True
            
        except Exception as e:
            self.db.rollback()
            logger.error(f"[AddAlias] 失败: {e}")
            return False
    
    def batch_add_aliases(
        self,
        mappings: List[Dict],
        created_by: str = 'batch_import'
    ) -> Tuple[int, int]:
        """
        批量添加别名映射
        
        Args:
            mappings: 映射列表，每项包含：
                {
                    'account': str,
                    'site': str,
                    'store_label_raw': str,
                    'target_id': str,
                    'notes': str (可选)
                }
            created_by: 创建人
            
        Returns:
            (成功数, 失败数)
        """
        success = 0
        failed = 0
        
        for mapping in mappings:
            try:
                self.add_alias(
                    account=mapping.get('account'),
                    site=mapping.get('site'),
                    store_label_raw=mapping['store_label_raw'],
                    target_id=mapping['target_id'],
                    notes=mapping.get('notes'),
                    created_by=created_by
                )
                success += 1
            except Exception as e:
                logger.warning(f"[BatchAdd] 跳过: {mapping.get('store_label_raw')} - {e}")
                failed += 1
        
        logger.info(f"[BatchAdd] 完成: 成功{success}, 失败{failed}")
        return success, failed


def get_account_alignment_service(db: Session) -> AccountAlignmentService:
    """获取账号对齐服务实例"""
    return AccountAlignmentService(db)

