"""
C类数据查询服务（混合查询模式）

实现C类数据的智能路由查询策略：
1. 物化视图查询（标准时间维度，2年内数据）
2. 实时计算查询（自定义范围或超出2年数据）
3. 归档表查询（5年以上数据）

设计原则：
- 根据查询条件自动选择最优查询方式
- 前端统一API接口，无需关心查询方式
- 支持分层存储架构（热数据/温数据/冷数据）
"""

from sqlalchemy.orm import Session
from sqlalchemy import text, select, func, and_, or_
from typing import Dict, List, Optional, Any, Tuple
from datetime import date, datetime, timedelta
from modules.core.logger import get_logger

logger = get_logger(__name__)


class CClassDataService:
    """
    C类数据查询服务（混合查询模式）
    
    支持三种查询方式：
    1. 物化视图查询（热数据层）：标准粒度 + 2年内 + 小规模筛选
    2. 实时计算查询（温数据层）：自定义范围 OR 超出2年 OR 大规模筛选
    3. 归档表查询（冷数据层）：5年以上数据（未来实现）
    """
    
    # 物化视图保留期限（天）
    MATERIALIZED_VIEW_RETENTION_DAYS = 730  # 2年
    
    # 实时计算阈值
    MAX_SHOPS_FOR_MV = 10  # 物化视图最大店铺数
    MAX_ACCOUNTS_FOR_MV = 5  # 物化视图最大账号数
    MAX_PLATFORMS_FOR_MV = 3  # 物化视图最大平台数
    
    # 归档表阈值（天）
    ARCHIVE_THRESHOLD_DAYS = 1825  # 5年
    
    def __init__(self, db: Session):
        """
        初始化C类数据查询服务
        
        Args:
            db: 数据库会话
        """
        self.db = db
        # 初始化缓存（延迟初始化，单例模式）
        self._cache = None
    
    @property
    def cache(self):
        """获取缓存实例（延迟初始化）"""
        if self._cache is None:
            from backend.utils.c_class_cache import get_c_class_cache
            import os
            redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
            self._cache = get_c_class_cache(redis_url=redis_url)
        return self._cache
    
    def should_use_materialized_view(
        self,
        start_date: date,
        end_date: date,
        granularity: str,
        platform_codes: Optional[List[str]] = None,
        shop_ids: Optional[List[str]] = None,
        account_ids: Optional[List[str]] = None
    ) -> bool:
        """
        判断是否应该使用物化视图查询
        
        判断规则（多维度判断矩阵）：
        1. 时间范围：在物化视图保留期限内（2年内）
        2. 粒度：标准粒度（daily/weekly/monthly）
        3. 店铺数：≤10个店铺
        4. 账号数：≤5个账号
        5. 平台数：≤3个平台
        
        如果所有条件都满足，使用物化视图；否则使用实时计算
        
        Args:
            start_date: 开始日期
            end_date: 结束日期
            granularity: 数据粒度（daily/weekly/monthly）
            platform_codes: 平台代码列表（可选）
            shop_ids: 店铺ID列表（可选）
            account_ids: 账号ID列表（可选）
        
        Returns:
            bool: True表示使用物化视图，False表示使用实时计算
        """
        # 1. 检查时间范围（2年内）
        days_diff = (end_date - start_date).days
        if days_diff > self.MATERIALIZED_VIEW_RETENTION_DAYS:
            logger.debug(f"[C-Class] 时间范围超出物化视图保留期限（{days_diff}天 > {self.MATERIALIZED_VIEW_RETENTION_DAYS}天），使用实时计算")
            return False
        
        # 检查是否在保留期限内（从今天往前推2年）
        cutoff_date = date.today() - timedelta(days=self.MATERIALIZED_VIEW_RETENTION_DAYS)
        if start_date < cutoff_date:
            logger.debug(f"[C-Class] 开始日期超出物化视图保留期限（{start_date} < {cutoff_date}），使用实时计算")
            return False
        
        # 2. 检查粒度（标准粒度）
        if granularity not in ['daily', 'weekly', 'monthly']:
            logger.debug(f"[C-Class] 非标准粒度（{granularity}），使用实时计算")
            return False
        
        # 3. 检查店铺数（≤10个）
        if shop_ids and len(shop_ids) > self.MAX_SHOPS_FOR_MV:
            logger.debug(f"[C-Class] 店铺数超出阈值（{len(shop_ids)} > {self.MAX_SHOPS_FOR_MV}），使用实时计算")
            return False
        
        # 4. 检查账号数（≤5个）
        if account_ids and len(account_ids) > self.MAX_ACCOUNTS_FOR_MV:
            logger.debug(f"[C-Class] 账号数超出阈值（{len(account_ids)} > {self.MAX_ACCOUNTS_FOR_MV}），使用实时计算")
            return False
        
        # 5. 检查平台数（≤3个）
        if platform_codes and len(platform_codes) > self.MAX_PLATFORMS_FOR_MV:
            logger.debug(f"[C-Class] 平台数超出阈值（{len(platform_codes)} > {self.MAX_PLATFORMS_FOR_MV}），使用实时计算")
            return False
        
        # 所有条件都满足，使用物化视图
        logger.debug(f"[C-Class] 满足物化视图查询条件，使用物化视图查询")
        return True
    
    def query_health_scores_from_mv(
        self,
        start_date: date,
        end_date: date,
        granularity: str,
        platform_codes: Optional[List[str]] = None,
        shop_ids: Optional[List[str]] = None,
        page: int = 1,
        page_size: int = 20
    ) -> Dict[str, Any]:
        """
        从物化视图查询健康度评分
        
        注意：目前系统中可能还没有专门的健康度评分物化视图，
        这里提供一个框架，实际使用时需要根据物化视图结构调整
        
        Args:
            start_date: 开始日期
            end_date: 结束日期
            granularity: 数据粒度
            platform_codes: 平台代码列表（可选）
            shop_ids: 店铺ID列表（可选）
            page: 页码
            page_size: 每页数量
        
        Returns:
            Dict: 查询结果（包含data和total）
        """
        try:
            # TODO: 根据实际的物化视图名称和结构调整
            # 假设物化视图名称为 mv_shop_health_summary
            mv_name = "mv_shop_health_summary"
            
            # 构建查询SQL
            query = text(f"""
                SELECT 
                    platform_code,
                    shop_id,
                    metric_date,
                    granularity,
                    health_score,
                    gmv_score,
                    conversion_score,
                    inventory_score,
                    service_score,
                    gmv,
                    conversion_rate,
                    inventory_turnover,
                    customer_satisfaction,
                    risk_level
                FROM {mv_name}
                WHERE metric_date >= :start_date
                  AND metric_date <= :end_date
                  AND granularity = :granularity
            """)
            
            params = {
                "start_date": start_date,
                "end_date": end_date,
                "granularity": granularity
            }
            
            # 添加平台筛选
            if platform_codes:
                query = text(str(query).replace(
                    "WHERE metric_date",
                    f"WHERE platform_code IN ({','.join([':platform_' + str(i) for i in range(len(platform_codes))])}) AND metric_date"
                ))
                for i, platform_code in enumerate(platform_codes):
                    params[f"platform_{i}"] = platform_code
            
            # 添加店铺筛选
            if shop_ids:
                query = text(str(query).replace(
                    "AND metric_date",
                    f"AND shop_id IN ({','.join([':shop_' + str(i) for i in range(len(shop_ids))])}) AND metric_date"
                ))
                for i, shop_id in enumerate(shop_ids):
                    params[f"shop_{i}"] = shop_id
            
            # 总数查询
            count_query = text(f"SELECT COUNT(*) FROM ({str(query)}) AS subquery")
            total = self.db.execute(count_query, params).scalar() or 0
            
            # 分页查询
            query = text(str(query) + " ORDER BY health_score DESC LIMIT :limit OFFSET :offset")
            params["limit"] = page_size
            params["offset"] = (page - 1) * page_size
            
            results = self.db.execute(query, params).fetchall()
            
            # 转换为字典列表
            data = []
            for row in results:
                data.append({
                    "platform_code": row.platform_code,
                    "shop_id": row.shop_id,
                    "metric_date": row.metric_date,
                    "granularity": row.granularity,
                    "health_score": float(row.health_score) if row.health_score else 0.0,
                    "gmv_score": float(row.gmv_score) if row.gmv_score else 0.0,
                    "conversion_score": float(row.conversion_score) if row.conversion_score else 0.0,
                    "inventory_score": float(row.inventory_score) if row.inventory_score else 0.0,
                    "service_score": float(row.service_score) if row.service_score else 0.0,
                    "gmv": float(row.gmv) if row.gmv else 0.0,
                    "conversion_rate": float(row.conversion_rate) if row.conversion_rate else 0.0,
                    "inventory_turnover": float(row.inventory_turnover) if row.inventory_turnover else 0.0,
                    "customer_satisfaction": float(row.customer_satisfaction) if row.customer_satisfaction else 0.0,
                    "risk_level": row.risk_level
                })
            
            logger.info(f"[C-Class] 从物化视图查询健康度评分成功：{len(data)}条记录")
            
            return {
                "data": data,
                "total": total,
                "query_type": "materialized_view"
            }
            
        except Exception as e:
            logger.error(f"[C-Class] 从物化视图查询健康度评分失败: {e}", exc_info=True)
            raise
    
    def query_health_scores_realtime(
        self,
        start_date: date,
        end_date: date,
        granularity: str,
        platform_codes: Optional[List[str]] = None,
        shop_ids: Optional[List[str]] = None,
        page: int = 1,
        page_size: int = 20
    ) -> Dict[str, Any]:
        """
        实时计算健康度评分（从fact表查询）
        
        注意：这里需要调用ShopHealthService进行计算，
        实际实现时需要根据业务逻辑调整
        
        Args:
            start_date: 开始日期
            end_date: 结束日期
            granularity: 数据粒度
            platform_codes: 平台代码列表（可选）
            shop_ids: 店铺ID列表（可选）
            page: 页码
            page_size: 每页数量
        
        Returns:
            Dict: 查询结果（包含data和total）
        """
        try:
            # 导入ShopHealthService（避免循环导入）
            from backend.services.shop_health_service import ShopHealthService
            
            service = ShopHealthService(self.db)
            
            # 获取要计算的店铺列表
            from modules.core.db import DimShop
            
            shops_query = select(DimShop)
            if platform_codes:
                shops_query = shops_query.where(DimShop.platform_code.in_(platform_codes))
            if shop_ids:
                shops_query = shops_query.where(DimShop.shop_id.in_(shop_ids))
            
            shops = self.db.execute(shops_query).scalars().all()
            
            # 计算每个店铺的健康度评分
            calculated_scores = []
            
            # 根据粒度确定计算日期列表
            if granularity == "daily":
                current_date = start_date
                while current_date <= end_date:
                    for shop in shops:
                        try:
                            result = service.calculate_health_score(
                                shop.platform_code,
                                shop.shop_id,
                                current_date,
                                granularity
                            )
                            calculated_scores.append({
                                "platform_code": shop.platform_code,
                                "shop_id": shop.shop_id,
                                "metric_date": current_date,
                                "granularity": granularity,
                                **result
                            })
                        except Exception as e:
                            logger.warning(f"[C-Class] 计算店铺{shop.shop_id}健康度评分失败: {e}")
                            continue
                    current_date += timedelta(days=1)
            elif granularity == "weekly":
                # TODO: 实现周度聚合
                current_date = start_date
                while current_date <= end_date:
                    # 计算周度数据
                    week_end = min(current_date + timedelta(days=6), end_date)
                    for shop in shops:
                        try:
                            # 使用周度最后一天作为指标日期
                            result = service.calculate_health_score(
                                shop.platform_code,
                                shop.shop_id,
                                week_end,
                                granularity
                            )
                            calculated_scores.append({
                                "platform_code": shop.platform_code,
                                "shop_id": shop.shop_id,
                                "metric_date": week_end,
                                "granularity": granularity,
                                **result
                            })
                        except Exception as e:
                            logger.warning(f"[C-Class] 计算店铺{shop.shop_id}健康度评分失败: {e}")
                            continue
                    current_date += timedelta(days=7)
            elif granularity == "monthly":
                # TODO: 实现月度聚合
                current_date = start_date
                while current_date <= end_date:
                    # 计算月度数据（使用月份最后一天）
                    if current_date.month == 12:
                        month_end = date(current_date.year, 12, 31)
                    else:
                        month_end = date(current_date.year, current_date.month + 1, 1) - timedelta(days=1)
                    month_end = min(month_end, end_date)
                    
                    for shop in shops:
                        try:
                            result = service.calculate_health_score(
                                shop.platform_code,
                                shop.shop_id,
                                month_end,
                                granularity
                            )
                            calculated_scores.append({
                                "platform_code": shop.platform_code,
                                "shop_id": shop.shop_id,
                                "metric_date": month_end,
                                "granularity": granularity,
                                **result
                            })
                        except Exception as e:
                            logger.warning(f"[C-Class] 计算店铺{shop.shop_id}健康度评分失败: {e}")
                            continue
                    
                    # 移动到下个月
                    if current_date.month == 12:
                        current_date = date(current_date.year + 1, 1, 1)
                    else:
                        current_date = date(current_date.year, current_date.month + 1, 1)
            
            # 分页处理
            total = len(calculated_scores)
            start_idx = (page - 1) * page_size
            end_idx = start_idx + page_size
            paginated_data = calculated_scores[start_idx:end_idx]
            
            logger.info(f"[C-Class] 实时计算健康度评分成功：{len(paginated_data)}条记录（总计{total}条）")
            
            return {
                "data": paginated_data,
                "total": total,
                "query_type": "realtime"
            }
            
        except Exception as e:
            logger.error(f"[C-Class] 实时计算健康度评分失败: {e}", exc_info=True)
            raise
    
    def query_health_scores(
        self,
        start_date: date,
        end_date: date,
        granularity: str = "daily",
        platform_codes: Optional[List[str]] = None,
        shop_ids: Optional[List[str]] = None,
        account_ids: Optional[List[str]] = None,
        page: int = 1,
        page_size: int = 20
    ) -> Dict[str, Any]:
        """
        查询健康度评分（智能路由）
        
        根据查询条件自动选择最优查询方式：
        1. 物化视图查询（标准维度 + 2年内 + 小规模筛选）
        2. 实时计算查询（自定义范围 OR 超出2年 OR 大规模筛选）
        3. 归档表查询（5年以上，未来实现）
        
        Args:
            start_date: 开始日期
            end_date: 结束日期
            granularity: 数据粒度（daily/weekly/monthly）
            platform_codes: 平台代码列表（可选）
            shop_ids: 店铺ID列表（可选）
            account_ids: 账号ID列表（可选）
            page: 页码（从1开始）
            page_size: 每页数量
        
        Returns:
            Dict: 查询结果（包含data、total、query_type）
        """
        try:
            # 尝试从缓存获取
            cache_key_params = {
                "start_date": str(start_date),
                "end_date": str(end_date),
                "granularity": granularity,
                "platform_codes": ",".join(sorted(platform_codes)) if platform_codes else "",
                "shop_ids": ",".join(sorted(shop_ids)) if shop_ids else "",
                "account_ids": ",".join(sorted(account_ids)) if account_ids else "",
                "page": page,
                "page_size": page_size
            }
            cached_result = self.cache.get("health_score", **cache_key_params)
            if cached_result:
                logger.info(f"[C-Class] 从缓存获取健康度评分（{start_date} 到 {end_date}）")
                return cached_result
            
            # 判断是否应该使用物化视图
            use_mv = self.should_use_materialized_view(
                start_date=start_date,
                end_date=end_date,
                granularity=granularity,
                platform_codes=platform_codes,
                shop_ids=shop_ids,
                account_ids=account_ids
            )
            
            if use_mv:
                # 使用物化视图查询
                logger.info(f"[C-Class] 使用物化视图查询健康度评分（{start_date} 到 {end_date}，粒度：{granularity}）")
                result = self.query_health_scores_from_mv(
                    start_date=start_date,
                    end_date=end_date,
                    granularity=granularity,
                    platform_codes=platform_codes,
                    shop_ids=shop_ids,
                    page=page,
                    page_size=page_size
                )
            else:
                # 使用实时计算
                logger.info(f"[C-Class] 使用实时计算查询健康度评分（{start_date} 到 {end_date}，粒度：{granularity}）")
                result = self.query_health_scores_realtime(
                    start_date=start_date,
                    end_date=end_date,
                    granularity=granularity,
                    platform_codes=platform_codes,
                    shop_ids=shop_ids,
                    page=page,
                    page_size=page_size
                )
            
            # 缓存结果（5分钟）
            self.cache.set("health_score", result, **cache_key_params)
            
            return result
                
        except Exception as e:
            logger.error(f"[C-Class] 查询健康度评分失败: {e}", exc_info=True)
            raise
    
    def query_shop_ranking(
        self,
        start_date: date,
        end_date: date,
        granularity: str,
        platform_codes: Optional[List[str]] = None,
        shop_ids: Optional[List[str]] = None,
        metric: str = "gmv",  # gmv/orders/conversion_rate
        group_by: str = "shop",  # shop/platform
        page: int = 1,
        page_size: int = 20
    ) -> Dict[str, Any]:
        """
        查询店铺排名（智能路由）
        
        根据查询条件自动选择最优查询方式：
        1. 物化视图查询（标准维度 + 2年内 + 小规模筛选）
        2. 实时计算查询（自定义范围 OR 超出2年 OR 大规模筛选）
        
        Args:
            start_date: 开始日期
            end_date: 结束日期
            granularity: 数据粒度（daily/weekly/monthly）
            platform_codes: 平台代码列表（可选）
            shop_ids: 店铺ID列表（可选）
            metric: 排名指标（gmv/orders/conversion_rate）
            group_by: 分组方式（shop/platform）
            page: 页码（从1开始）
            page_size: 每页数量
        
        Returns:
            Dict: 查询结果（包含data、total、query_type）
        """
        try:
            # 尝试从缓存获取
            cache_key_params = {
                "start_date": str(start_date),
                "end_date": str(end_date),
                "granularity": granularity,
                "platform_codes": ",".join(sorted(platform_codes)) if platform_codes else "",
                "shop_ids": ",".join(sorted(shop_ids)) if shop_ids else "",
                "metric": metric,
                "group_by": group_by,
                "page": page,
                "page_size": page_size
            }
            cached_result = self.cache.get("ranking", **cache_key_params)
            if cached_result:
                logger.info(f"[C-Class] 从缓存获取店铺排名（{start_date} 到 {end_date}，指标：{metric}）")
                return cached_result
            
            # 判断是否应该使用物化视图
            use_mv = self.should_use_materialized_view(
                start_date=start_date,
                end_date=end_date,
                granularity=granularity,
                platform_codes=platform_codes,
                shop_ids=shop_ids
            )
            
            if use_mv:
                # 使用物化视图查询
                logger.info(f"[C-Class] 使用物化视图查询店铺排名（{start_date} 到 {end_date}，粒度：{granularity}，指标：{metric}）")
                result = self.query_shop_ranking_from_mv(
                    start_date=start_date,
                    end_date=end_date,
                    granularity=granularity,
                    platform_codes=platform_codes,
                    shop_ids=shop_ids,
                    metric=metric,
                    group_by=group_by,
                    page=page,
                    page_size=page_size
                )
            else:
                # 使用实时计算
                logger.info(f"[C-Class] 使用实时计算查询店铺排名（{start_date} 到 {end_date}，粒度：{granularity}，指标：{metric}）")
                result = self.query_shop_ranking_realtime(
                    start_date=start_date,
                    end_date=end_date,
                    granularity=granularity,
                    platform_codes=platform_codes,
                    shop_ids=shop_ids,
                    metric=metric,
                    group_by=group_by,
                    page=page,
                    page_size=page_size
                )
            
            # 缓存结果（5分钟）
            self.cache.set("ranking", result, **cache_key_params)
            
            return result
                
        except Exception as e:
            logger.error(f"[C-Class] 查询店铺排名失败: {e}", exc_info=True)
            raise
    
    def query_shop_ranking_from_mv(
        self,
        start_date: date,
        end_date: date,
        granularity: str,
        platform_codes: Optional[List[str]] = None,
        shop_ids: Optional[List[str]] = None,
        metric: str = "gmv",
        group_by: str = "shop",
        page: int = 1,
        page_size: int = 20
    ) -> Dict[str, Any]:
        """
        从物化视图查询店铺排名
        
        注意：目前系统中可能还没有专门的排名物化视图，
        这里提供一个框架，实际使用时需要根据物化视图结构调整
        
        Args:
            start_date: 开始日期
            end_date: 结束日期
            granularity: 数据粒度
            platform_codes: 平台代码列表（可选）
            shop_ids: 店铺ID列表（可选）
            metric: 排名指标
            group_by: 分组方式
            page: 页码
            page_size: 每页数量
        
        Returns:
            Dict: 查询结果（包含data和total）
        """
        try:
            # TODO: 根据实际的物化视图名称和结构调整
            # 假设物化视图名称为 mv_shop_daily_performance
            mv_name = "mv_shop_daily_performance"
            
            # 构建查询SQL（根据metric选择排序字段）
            order_field = {
                "gmv": "gmv_rmb",
                "orders": "order_count",
                "conversion_rate": "conversion_rate"
            }.get(metric, "gmv_rmb")
            
            query = text(f"""
                SELECT 
                    platform_code,
                    shop_id,
                    shop_name,
                    SUM(gmv_rmb) AS total_gmv,
                    SUM(order_count) AS total_orders,
                    AVG(conversion_rate) AS avg_conversion_rate
                FROM {mv_name}
                WHERE metric_date >= :start_date
                  AND metric_date <= :end_date
            """)
            
            params = {
                "start_date": start_date,
                "end_date": end_date
            }
            
            # 添加平台筛选
            if platform_codes:
                query = text(str(query).replace(
                    "WHERE metric_date",
                    f"WHERE platform_code IN ({','.join([':platform_' + str(i) for i in range(len(platform_codes))])}) AND metric_date"
                ))
                for i, platform_code in enumerate(platform_codes):
                    params[f"platform_{i}"] = platform_code
            
            # 添加店铺筛选
            if shop_ids:
                query = text(str(query).replace(
                    "AND metric_date",
                    f"AND shop_id IN ({','.join([':shop_' + str(i) for i in range(len(shop_ids))])}) AND metric_date"
                ))
                for i, shop_id in enumerate(shop_ids):
                    params[f"shop_{i}"] = shop_id
            
            # 分组
            if group_by == "shop":
                query = text(str(query) + " GROUP BY platform_code, shop_id, shop_name")
            else:  # platform
                query = text(str(query) + " GROUP BY platform_code")
            
            # 排序
            query = text(str(query) + f" ORDER BY {order_field} DESC")
            
            # 总数查询
            count_query = text(f"SELECT COUNT(*) FROM ({str(query)}) AS subquery")
            total = self.db.execute(count_query, params).scalar() or 0
            
            # 分页查询
            query = text(str(query) + " LIMIT :limit OFFSET :offset")
            params["limit"] = page_size
            params["offset"] = (page - 1) * page_size
            
            results = self.db.execute(query, params).fetchall()
            
            # 转换为字典列表
            data = []
            rank = (page - 1) * page_size + 1
            for row in results:
                data.append({
                    "rank": rank,
                    "platform_code": row.platform_code,
                    "shop_id": row.shop_id,
                    "shop_name": row.shop_name if hasattr(row, 'shop_name') else None,
                    "gmv": float(row.total_gmv) if row.total_gmv else 0.0,
                    "orders": int(row.total_orders) if row.total_orders else 0,
                    "conversion_rate": float(row.avg_conversion_rate) if row.avg_conversion_rate else 0.0
                })
                rank += 1
            
            logger.info(f"[C-Class] 从物化视图查询店铺排名成功：{len(data)}条记录")
            
            return {
                "data": data,
                "total": total,
                "query_type": "materialized_view"
            }
            
        except Exception as e:
            logger.error(f"[C-Class] 从物化视图查询店铺排名失败: {e}", exc_info=True)
            raise
    
    def query_shop_ranking_realtime(
        self,
        start_date: date,
        end_date: date,
        granularity: str,
        platform_codes: Optional[List[str]] = None,
        shop_ids: Optional[List[str]] = None,
        metric: str = "gmv",
        group_by: str = "shop",
        page: int = 1,
        page_size: int = 20
    ) -> Dict[str, Any]:
        """
        实时计算店铺排名（从fact表查询）
        
        Args:
            start_date: 开始日期
            end_date: 结束日期
            granularity: 数据粒度
            platform_codes: 平台代码列表（可选）
            shop_ids: 店铺ID列表（可选）
            metric: 排名指标
            group_by: 分组方式
            page: 页码
            page_size: 每页数量
        
        Returns:
            Dict: 查询结果（包含data和total）
        """
        try:
            from modules.core.db import FactOrder, DimShop, FactProductMetric
            
            # 构建基础查询
            base_filter = [
                FactOrder.order_date_local >= start_date,
                FactOrder.order_date_local <= end_date,
                FactOrder.order_status.in_(["completed", "paid"])
            ]
            
            if platform_codes:
                base_filter.append(FactOrder.platform_code.in_(platform_codes))
            if shop_ids:
                base_filter.append(FactOrder.shop_id.in_(shop_ids))
            
            # 根据metric构建查询
            if metric == "gmv":
                # GMV排名
                query = select(
                    FactOrder.platform_code,
                    FactOrder.shop_id,
                    func.sum(FactOrder.total_amount_rmb).label("total_gmv"),
                    func.count(FactOrder.order_id).label("total_orders")
                ).where(
                    *base_filter
                )
                
                if group_by == "shop":
                    query = query.group_by(FactOrder.platform_code, FactOrder.shop_id)
                    query = query.order_by(func.sum(FactOrder.total_amount_rmb).desc())
                else:  # platform
                    query = query.group_by(FactOrder.platform_code)
                    query = query.order_by(func.sum(FactOrder.total_amount_rmb).desc())
                
            elif metric == "orders":
                # 订单数排名
                query = select(
                    FactOrder.platform_code,
                    FactOrder.shop_id,
                    func.sum(FactOrder.total_amount_rmb).label("total_gmv"),
                    func.count(FactOrder.order_id).label("total_orders")
                ).where(
                    *base_filter
                )
                
                if group_by == "shop":
                    query = query.group_by(FactOrder.platform_code, FactOrder.shop_id)
                    query = query.order_by(func.count(FactOrder.order_id).desc())
                else:  # platform
                    query = query.group_by(FactOrder.platform_code)
                    query = query.order_by(func.count(FactOrder.order_id).desc())
                
            else:  # conversion_rate
                # 转化率排名（需要关联流量数据）
                # TODO: 实现转化率排名查询（需要关联fact_product_metrics）
                # 这里先使用GMV排名作为占位
                query = select(
                    FactOrder.platform_code,
                    FactOrder.shop_id,
                    func.sum(FactOrder.total_amount_rmb).label("total_gmv"),
                    func.count(FactOrder.order_id).label("total_orders")
                ).where(
                    *base_filter
                )
                
                if group_by == "shop":
                    query = query.group_by(FactOrder.platform_code, FactOrder.shop_id)
                    query = query.order_by(func.sum(FactOrder.total_amount_rmb).desc())
                else:  # platform
                    query = query.group_by(FactOrder.platform_code)
                    query = query.order_by(func.sum(FactOrder.total_amount_rmb).desc())
            
            # 总数查询
            total_query = select(func.count()).select_from(query.subquery())
            total = self.db.execute(total_query).scalar() or 0
            
            # 分页查询
            query = query.offset((page - 1) * page_size).limit(page_size)
            results = self.db.execute(query).all()
            
            # 获取店铺名称
            data = []
            rank = (page - 1) * page_size + 1
            for row in results:
                shop_name = None
                if group_by == "shop" and row.shop_id:
                    shop = self.db.execute(
                        select(DimShop).where(
                            DimShop.platform_code == row.platform_code,
                            DimShop.shop_id == row.shop_id
                        )
                    ).scalar_one_or_none()
                    if shop:
                        shop_name = shop.shop_name
                
                data.append({
                    "rank": rank,
                    "platform_code": row.platform_code,
                    "shop_id": row.shop_id if hasattr(row, 'shop_id') else None,
                    "shop_name": shop_name,
                    "gmv": float(row.total_gmv) if row.total_gmv else 0.0,
                    "orders": int(row.total_orders) if row.total_orders else 0,
                    "conversion_rate": 0.0  # TODO: 计算转化率
                })
                rank += 1
            
            logger.info(f"[C-Class] 实时计算店铺排名成功：{len(data)}条记录（总计{total}条）")
            
            return {
                "data": data,
                "total": total,
                "query_type": "realtime"
            }
            
        except Exception as e:
            logger.error(f"[C-Class] 实时计算店铺排名失败: {e}", exc_info=True)
            raise
    
    def query_shop_sales_for_comparison(
        self,
        start_date: date,
        end_date: date,
        platform_codes: Optional[List[str]] = None,
        shop_ids: Optional[List[str]] = None
    ) -> Dict[str, float]:
        """
        查询店铺销售额（用于对比期间计算）
        
        返回格式：{platform_code_shop_id: sales_amount}
        
        Args:
            start_date: 开始日期
            end_date: 结束日期
            platform_codes: 平台代码列表（可选）
            shop_ids: 店铺ID列表（可选）
        
        Returns:
            Dict: 店铺销售额字典，key为"platform_code_shop_id"，value为销售额（元）
        """
        try:
            from modules.core.db import FactOrder
            
            # 构建查询
            query = select(
                FactOrder.platform_code,
                FactOrder.shop_id,
                func.sum(FactOrder.total_amount_rmb).label("sales_amount")
            ).where(
                FactOrder.order_date_local >= start_date,
                FactOrder.order_date_local <= end_date,
                FactOrder.order_status.in_(["completed", "paid"])
            )
            
            if platform_codes:
                query = query.where(FactOrder.platform_code.in_(platform_codes))
            if shop_ids:
                query = query.where(FactOrder.shop_id.in_(shop_ids))
            
            query = query.group_by(FactOrder.platform_code, FactOrder.shop_id)
            
            results = self.db.execute(query).all()
            
            # 构建字典
            sales_dict = {}
            for row in results:
                key = f"{row.platform_code}_{row.shop_id}"
                sales_dict[key] = float(row.sales_amount or 0)
            
            logger.debug(f"[C-Class] 查询对比期间销售额成功：{len(sales_dict)}条记录")
            
            return sales_dict
            
        except Exception as e:
            logger.error(f"[C-Class] 查询对比期间销售额失败: {e}", exc_info=True)
            raise
    
    def query_shop_sales_by_period(
        self,
        start_date: date,
        end_date: date,
        platform_code: Optional[str] = None,
        shop_id: Optional[str] = None,
        platform_codes: Optional[List[str]] = None,
        shop_ids: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        查询指定时间范围和店铺的销售数据（用于达成率计算）
        
        支持单个店铺或批量店铺查询
        
        Args:
            start_date: 开始日期
            end_date: 结束日期
            platform_code: 单个平台代码（可选，与platform_codes互斥）
            shop_id: 单个店铺ID（可选，与shop_ids互斥）
            platform_codes: 平台代码列表（可选）
            shop_ids: 店铺ID列表（可选）
        
        Returns:
            Dict: 查询结果
            {
                "total_amount": float,  # 总销售额（元）
                "total_orders": int,    # 总订单数
                "shops": [              # 店铺明细（如果查询多个店铺）
                    {
                        "platform_code": str,
                        "shop_id": str,
                        "amount": float,
                        "orders": int
                    }
                ]
            }
        """
        try:
            from modules.core.db import FactOrder
            
            # 处理参数（单个或批量）
            if platform_code and not platform_codes:
                platform_codes = [platform_code]
            if shop_id and not shop_ids:
                shop_ids = [shop_id]
            
            # 构建查询
            query = select(
                FactOrder.platform_code,
                FactOrder.shop_id,
                func.sum(FactOrder.total_amount_rmb).label("amount"),
                func.count(FactOrder.order_id).label("orders")
            ).where(
                FactOrder.order_date_local >= start_date,
                FactOrder.order_date_local <= end_date,
                FactOrder.order_status.in_(["completed", "paid"])
            )
            
            if platform_codes:
                query = query.where(FactOrder.platform_code.in_(platform_codes))
            if shop_ids:
                query = query.where(FactOrder.shop_id.in_(shop_ids))
            
            # 如果查询单个店铺，不需要分组
            if platform_code and shop_id and not platform_codes and not shop_ids:
                # 单个店铺查询，直接返回汇总数据
                result = self.db.execute(query).first()
                if result:
                    return {
                        "total_amount": float(result.amount or 0),
                        "total_orders": int(result.orders or 0),
                        "shops": [{
                            "platform_code": result.platform_code,
                            "shop_id": result.shop_id,
                            "amount": float(result.amount or 0),
                            "orders": int(result.orders or 0)
                        }]
                    }
                else:
                    return {
                        "total_amount": 0.0,
                        "total_orders": 0,
                        "shops": []
                    }
            else:
                # 多个店铺查询，需要分组
                query = query.group_by(FactOrder.platform_code, FactOrder.shop_id)
                results = self.db.execute(query).all()
                
                shops = []
                total_amount = 0.0
                total_orders = 0
                
                for row in results:
                    amount = float(row.amount or 0)
                    orders = int(row.orders or 0)
                    shops.append({
                        "platform_code": row.platform_code,
                        "shop_id": row.shop_id,
                        "amount": amount,
                        "orders": orders
                    })
                    total_amount += amount
                    total_orders += orders
                
                return {
                    "total_amount": total_amount,
                    "total_orders": total_orders,
                    "shops": shops
                }
            
        except Exception as e:
            logger.error(f"[C-Class] 查询店铺销售数据失败: {e}", exc_info=True)
            raise

