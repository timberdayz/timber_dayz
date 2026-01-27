"""
Metabase Question查询服务
用于通过Metabase REST API查询Question并返回数据
"""

import os
import httpx
from typing import Dict, Any, Optional, List
from modules.core.logger import get_logger

logger = get_logger(__name__)

# 禁用代理,避免通过代理连接 localhost
# 设置环境变量,让 httpx 不使用代理
os.environ.setdefault("NO_PROXY", "localhost,127.0.0.1,0.0.0.0")
os.environ.setdefault("no_proxy", "localhost,127.0.0.1,0.0.0.0")


class MetabaseQuestionService:
    """Metabase Question查询服务"""
    
    def __init__(self):
        """初始化Metabase服务"""
        self.base_url = os.getenv("METABASE_URL", "http://localhost:8080").rstrip('/')
        self.username = os.getenv("METABASE_USERNAME", "")
        self.password = os.getenv("METABASE_PASSWORD", "")
        # 优先使用API Key,去除首尾空白字符
        self.api_key = os.getenv("METABASE_API_KEY", "").strip() if os.getenv("METABASE_API_KEY") else ""
        
        # Session Token缓存
        self.session_token: Optional[str] = None
        
        # Question ID映射(从环境变量读取)
        self.question_ids = {
            "business_overview_kpi": int(os.getenv("METABASE_QUESTION_BUSINESS_OVERVIEW_KPI", "0")),
            "business_overview_comparison": int(os.getenv("METABASE_QUESTION_BUSINESS_OVERVIEW_COMPARISON", "0")),
            "business_overview_shop_racing": int(os.getenv("METABASE_QUESTION_BUSINESS_OVERVIEW_SHOP_RACING", "0")),
            "business_overview_traffic_ranking": int(os.getenv("METABASE_QUESTION_BUSINESS_OVERVIEW_TRAFFIC_RANKING", "0")),
            "business_overview_inventory_backlog": int(os.getenv("METABASE_QUESTION_BUSINESS_OVERVIEW_INVENTORY_BACKLOG", "0")),
            "business_overview_operational_metrics": int(os.getenv("METABASE_QUESTION_BUSINESS_OVERVIEW_OPERATIONAL_METRICS", "0")),
            "clearance_ranking": int(os.getenv("METABASE_QUESTION_CLEARANCE_RANKING", "0")),
        }
        
        # HTTP客户端(支持异步)
        self.client = httpx.AsyncClient(timeout=30.0)
    
    async def _ensure_session_token(self) -> str:
        """确保有有效的Session Token"""
        if self.session_token:
            return self.session_token
        
        # 优先使用API Key(推荐方式)
        if self.api_key:
            self.session_token = self.api_key
            logger.debug("使用Metabase API Key进行认证")
            return self.session_token
        
        # 使用用户名密码获取Session Token
        if not self.username or not self.password:
            raise ValueError("Metabase认证信息未配置:需要设置METABASE_USERNAME和METABASE_PASSWORD,或METABASE_API_KEY")
        
        try:
            response = await self.client.post(
                f"{self.base_url}/api/session",
                json={
                    "username": self.username,
                    "password": self.password
                }
            )
            response.raise_for_status()
            data = response.json()
            self.session_token = data.get("id")
            
            if not self.session_token:
                raise ValueError("Metabase登录失败:未返回Session Token")
            
            logger.info("Metabase Session Token获取成功")
            return self.session_token
            
        except httpx.HTTPStatusError as e:
            logger.error(f"Metabase登录失败: HTTP {e.response.status_code}")
            raise ValueError(f"Metabase认证失败: {e.response.status_code}")
        except Exception as e:
            logger.error(f"Metabase登录异常: {e}")
            raise ValueError(f"Metabase认证异常: {str(e)}")
    
    def _get_question_id(self, question_key: str) -> int:
        """
        获取Question ID(增强错误提示)
        
        Args:
            question_key: Question键名
            
        Returns:
            Question ID
            
        Raises:
            ValueError: Question ID未配置时抛出,包含详细的配置说明
        """
        question_id = self.question_ids.get(question_key)
        if not question_id or question_id == 0:
            env_var_name = f"METABASE_QUESTION_{question_key.upper()}"
            error_msg = (
                f"Question ID未配置: {question_key}\n"
                f"请在环境变量中设置 {env_var_name}\n"
                f"获取方式:\n"
                f"  1. 在Metabase UI中创建Question\n"
                f"  2. 记录Question ID(在Question URL或详情中)\n"
                f"  3. 配置到.env文件: {env_var_name}=<question_id>"
            )
            logger.error(error_msg)
            raise ValueError(error_msg)
        return question_id
    
    def _convert_params(self, params: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        转换前端参数为Metabase参数格式
        
        Metabase参数格式:
        [
            {
                "type": "string",
                "target": ["variable", ["template-tag", "variable_name"]],
                "value": "value1"
            }
        ]
        """
        metabase_params = []
        
        # 月份参数(用于核心KPI等月度筛选)
        # 格式:YYYY-MM-DD(月初日期)
        if params.get("month"):
            metabase_params.append({
                "type": "date",
                "target": ["variable", ["template-tag", "month"]],
                "value": params["month"]
            })
        
        # 单平台参数(用于核心KPI的平台筛选,可选)
        # 注意:与 platforms 不同,这是单个平台代码
        if params.get("platform"):
            metabase_params.append({
                "type": "text",
                "target": ["variable", ["template-tag", "platform"]],
                "value": params["platform"]
            })
        
        # 日期范围参数
        if params.get("start_date"):
            metabase_params.append({
                "type": "date",
                "target": ["variable", ["template-tag", "start_date"]],
                "value": params["start_date"]
            })
        if params.get("end_date"):
            metabase_params.append({
                "type": "date",
                "target": ["variable", ["template-tag", "end_date"]],
                "value": params["end_date"]
            })
        
        # 日期参数(单日期)
        if params.get("date"):
            metabase_params.append({
                "type": "date",
                "target": ["variable", ["template-tag", "date"]],
                "value": params["date"]
            })
        if params.get("date_value"):
            metabase_params.append({
                "type": "date",
                "target": ["variable", ["template-tag", "date"]],
                "value": params["date_value"]
            })
        
        # 平台参数
        if params.get("platforms"):
            platforms = params["platforms"]
            if isinstance(platforms, str):
                platforms = [p.strip() for p in platforms.split(",") if p.strip()]
            elif not isinstance(platforms, list):
                platforms = [platforms]
            
            metabase_params.append({
                "type": "string",
                "target": ["variable", ["template-tag", "platform"]],
                "value": platforms if len(platforms) > 1 else (platforms[0] if platforms else None)
            })
        
        # 店铺参数
        if params.get("shops"):
            shops = params["shops"]
            if isinstance(shops, str):
                shops = [s.strip() for s in shops.split(",") if s.strip()]
            elif not isinstance(shops, list):
                shops = [shops]
            
            metabase_params.append({
                "type": "string",
                "target": ["variable", ["template-tag", "shop_id"]],
                "value": shops if len(shops) > 1 else (shops[0] if shops else None)
            })
        
        # 粒度参数
        if params.get("granularity"):
            metabase_params.append({
                "type": "string",
                "target": ["variable", ["template-tag", "granularity"]],
                "value": params["granularity"]
            })
        
        # 分组参数
        if params.get("group_by"):
            metabase_params.append({
                "type": "string",
                "target": ["variable", ["template-tag", "group_by"]],
                "value": params["group_by"]
            })
        
        # 维度参数
        if params.get("dimension"):
            metabase_params.append({
                "type": "string",
                "target": ["variable", ["template-tag", "dimension"]],
                "value": params["dimension"]
            })
        
        # 天数参数
        if params.get("days"):
            metabase_params.append({
                "type": "number",
                "target": ["variable", ["template-tag", "days"]],
                "value": int(params["days"])
            })
        
        # 限制参数
        if params.get("limit"):
            metabase_params.append({
                "type": "number",
                "target": ["variable", ["template-tag", "limit"]],
                "value": int(params["limit"])
            })
        
        # 记录参数转换日志(调试用)
        if metabase_params:
            logger.debug(
                f"参数转换完成: {len(metabase_params)}个参数\n"
                f"原始参数: {params}\n"
                f"转换后参数: {metabase_params}"
            )
        
        return metabase_params
    
    def _convert_response(self, question_key: str, metabase_response: Dict[str, Any]) -> Dict[str, Any]:
        """
        转换Metabase响应为前端格式(根据question_key进行不同转换)
        
        Args:
            question_key: Question键名
            metabase_response: Metabase原始响应
            
        Returns:
            转换后的数据格式(根据question_key可能返回不同结构)
        """
        # Metabase响应格式:
        # {
        #   "data": {
        #     "rows": [[value1, value2, ...], ...],
        #     "cols": [{"name": "col1", "display_name": "Column 1", ...}, ...]
        #   }
        # }
        
        data = metabase_response.get("data", {})
        rows = data.get("rows", [])
        cols = data.get("cols", [])
        
        # 先转换为字典列表格式(基础转换)
        result_list = []
        
        # ⭐ 修复:Metabase /api/card/{id}/query/json 返回的是字典列表
        # 如果 rows 中的元素已经是字典,直接使用它们
        if rows and isinstance(rows[0], dict):
            # 已经是字典列表格式,直接使用
            result_list = rows
            logger.debug(f"[_convert_response] 使用字典列表格式,行数: {len(result_list)}")
        else:
            # 需要用 cols 来映射列名(传统的 data.rows + data.cols 格式)
            for row in rows:
                row_dict = {}
                for idx, col in enumerate(cols):
                    col_name = col.get("name") or col.get("display_name", f"col_{idx}")
                    row_dict[col_name] = row[idx] if idx < len(row) else None
                result_list.append(row_dict)
            logger.debug(f"[_convert_response] 使用 cols 映射格式,行数: {len(result_list)}")
        
        # ⭐ 根据question_key进行特定格式转换
        if question_key == "business_overview_kpi":
            # KPI数据:转换为单个对象
            # Metabase SQL 返回:GMV(元), 订单数, 访客数, 转化率(%), 客单价(元) + 5 个环比列
            if result_list and len(result_list) > 0:
                first_row = result_list[0]
                
                # 提取本月指标(支持中文和英文字段名)
                gmv = first_row.get("GMV(元)") or first_row.get("gmv") or first_row.get("total_gmv") or 0
                order_count = first_row.get("订单数") or first_row.get("order_count") or first_row.get("total_orders") or 0
                visitor_count = first_row.get("访客数") or first_row.get("visitor_count") or first_row.get("total_visitors") or 0
                conversion_rate = first_row.get("转化率(%)") or first_row.get("conversion_rate") or 0
                avg_order_value = first_row.get("客单价(元)") or first_row.get("avg_order_value") or first_row.get("average_order_value") or 0
                
                # 提取环比(SQL 返回 "GMV环比(%)" 等,上月为 0 时为 None)
                def _num_or_none(v):
                    if v is None:
                        return None
                    try:
                        return float(v)
                    except (TypeError, ValueError):
                        return None
                gmv_change = _num_or_none(first_row.get("GMV环比(%)"))
                order_count_change = _num_or_none(first_row.get("订单数环比(%)"))
                visitor_count_change = _num_or_none(first_row.get("访客数环比(%)"))
                conversion_rate_change = _num_or_none(first_row.get("转化率环比(%)"))
                avg_order_value_change = _num_or_none(first_row.get("客单价环比(%)"))
                
                return {
                    # 核心 KPI 指标(直接返回数值)
                    "gmv": gmv,
                    "order_count": order_count,
                    "visitor_count": visitor_count,
                    "conversion_rate": conversion_rate,
                    "avg_order_value": avg_order_value,
                    # 环比(百分比数值,可为 None)
                    "gmv_change": gmv_change,
                    "order_count_change": order_count_change,
                    "visitor_count_change": visitor_count_change,
                    "conversion_rate_change": conversion_rate_change,
                    "avg_order_value_change": avg_order_value_change,
                    # 兼容旧格式(current/change)
                    "traffic": {"current": visitor_count, "change": visitor_count_change},
                    "average_order_value": {"current": avg_order_value, "change": avg_order_value_change},
                    "conversion_rate_obj": {"current": conversion_rate, "change": conversion_rate_change},
                    "attach_rate": {"current": None, "change": None},
                    "labor_efficiency": {"current": None, "change": None},
                }
            logger.warning(f"[{question_key}] 返回数据为空,返回空对象")
            return {
                "gmv": 0,
                "order_count": 0,
                "visitor_count": 0,
                "conversion_rate": 0,
                "avg_order_value": 0,
                "gmv_change": None,
                "order_count_change": None,
                "visitor_count_change": None,
                "conversion_rate_change": None,
                "avg_order_value_change": None,
                "traffic": {"current": 0, "change": None},
                "average_order_value": {"current": 0, "change": None},
                "conversion_rate_obj": {"current": 0, "change": None},
                "attach_rate": {"current": None, "change": None},
                "labor_efficiency": {"current": None, "change": None},
            }
        
        elif question_key == "business_overview_comparison":
            # 对比数据:返回metrics对象(包含today/yesterday/average/change)
            if result_list and len(result_list) > 0:
                first_row = result_list[0]
                metrics = {}
                
                # 动态提取所有指标(以_today, _yesterday, _average, _change结尾的字段)
                for key, value in first_row.items():
                    if key.endswith("_today"):
                        metric_name = key[:-6]  # 移除"_today"后缀
                        if metric_name not in metrics:
                            metrics[metric_name] = {}
                        metrics[metric_name]["today"] = value
                    elif key.endswith("_yesterday"):
                        metric_name = key[:-10]  # 移除"_yesterday"后缀
                        if metric_name not in metrics:
                            metrics[metric_name] = {}
                        metrics[metric_name]["yesterday"] = value
                    elif key.endswith("_average"):
                        metric_name = key[:-8]  # 移除"_average"后缀
                        if metric_name not in metrics:
                            metrics[metric_name] = {}
                        metrics[metric_name]["average"] = value
                    elif key.endswith("_change"):
                        metric_name = key[:-7]  # 移除"_change"后缀
                        if metric_name not in metrics:
                            metrics[metric_name] = {}
                        metrics[metric_name]["change"] = value
                
                # 如果没有找到结构化字段,尝试常见字段名
                if not metrics:
                    metrics = {
                        "sales_amount": {
                            "today": first_row.get("sales_today") or first_row.get("sales_amount_today"),
                            "yesterday": first_row.get("sales_yesterday") or first_row.get("sales_amount_yesterday"),
                            "average": first_row.get("sales_average") or first_row.get("sales_amount_average"),
                            "change": first_row.get("sales_change") or first_row.get("sales_amount_change")
                        },
                        "order_count": {
                            "today": first_row.get("orders_today") or first_row.get("order_count_today"),
                            "yesterday": first_row.get("orders_yesterday") or first_row.get("order_count_yesterday"),
                            "average": first_row.get("orders_average") or first_row.get("order_count_average"),
                            "change": first_row.get("orders_change") or first_row.get("order_count_change")
                        },
                        # ... 其他指标可以继续添加
                    }
                
                return {"metrics": metrics}
            logger.warning(f"[{question_key}] 返回数据为空,返回空metrics对象")
            return {"metrics": {}}
        
        elif question_key == "business_overview_operational_metrics":
            # 经营指标:单行汇总,映射为 API 对象(金额字段转为万元)
            if result_list and len(result_list) > 0:
                r = result_list[0]
                def _v(key, default=0):
                    v = r.get(key)
                    if v is None:
                        return default
                    try:
                        return float(v)
                    except (TypeError, ValueError):
                        return default
                def _i(key, default=0):
                    v = r.get(key)
                    if v is None:
                        return default
                    try:
                        return int(v)
                    except (TypeError, ValueError):
                        return default
                # 金额类字段 SQL 返回元,转为万元与前端「(w)」一致
                to_wan = 10000.0
                return {
                    "monthly_target": _v("monthly_target") / to_wan,
                    "monthly_total_achieved": _v("monthly_total_achieved") / to_wan,
                    "today_sales": _v("today_sales") / to_wan,
                    "monthly_achievement_rate": _v("monthly_achievement_rate"),
                    "time_gap": _v("time_gap"),
                    "estimated_gross_profit": _v("estimated_gross_profit") / to_wan,
                    "estimated_expenses": _v("estimated_expenses") / to_wan,
                    "operating_result": (_v("operating_result") or 0) / to_wan,
                    "operating_result_text": r.get("operating_result_text") or "亏损",
                    "monthly_order_count": _i("monthly_order_count"),
                    "today_order_count": _i("today_order_count"),
                }
            return {
                "monthly_target": 0,
                "monthly_total_achieved": 0,
                "today_sales": 0,
                "monthly_achievement_rate": 0,
                "time_gap": 0,
                "estimated_gross_profit": 0,
                "estimated_expenses": 0,
                "operating_result": 0,
                "operating_result_text": "--",
                "monthly_order_count": 0,
                "today_order_count": 0,
            }
        
        # 默认返回字典列表格式(适用于表格数据)
        return {
            "data": result_list,
            "columns": [col.get("display_name") or col.get("name", "") for col in cols],
            "row_count": len(result_list)
        }
    
    async def query_question(
        self, 
        question_key: str, 
        params: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        查询Metabase Question
        
        Args:
            question_key: Question键名(如"business_overview_kpi")
            params: 查询参数(如日期范围、平台、店铺等)
        
        Returns:
            转换后的数据格式
        """
        if params is None:
            params = {}
        
        try:
            # 1. 获取Question ID
            question_id = self._get_question_id(question_key)
            
            # 2. 确保有Session Token
            token = await self._ensure_session_token()
            
            # 3. 转换参数
            metabase_params = self._convert_params(params)
            
            # 4. 调用Metabase Question API
            headers = {}
            if self.api_key:
                # 使用API Key认证(推荐方式)
                # 注意:Metabase 使用 X-API-Key header(不是 X-Metabase-Api-Key)
                headers["X-API-Key"] = token
            else:
                # 使用Session Token认证
                headers["X-Metabase-Session"] = token
            
            # Metabase Question查询API
            # POST /api/card/{card-id}/query/json
            url = f"{self.base_url}/api/card/{question_id}/query/json"
            
            # 构建请求体
            payload = {}
            if metabase_params:
                payload["parameters"] = metabase_params
                # 调试日志:记录传递给Metabase的参数
                logger.info(
                    f"[Metabase Question {question_id} ({question_key})] 查询参数:\n"
                    f"  URL: {url}\n"
                    f"  参数数量: {len(metabase_params)}\n"
                    f"  参数详情: {metabase_params}"
                )
            
            # 禁用代理,避免通过代理连接 localhost
            # 通过设置环境变量 NO_PROXY 来禁用代理(在初始化时已设置)
            response = await self.client.post(
                url,
                headers=headers,
                json=payload
            )
            response.raise_for_status()
            metabase_data = response.json()
            
            # ⭐ 调试日志:打印 Metabase 原始返回数据
            logger.info(f"[Metabase 原始响应] 类型: {type(metabase_data).__name__}")
            if isinstance(metabase_data, list) and len(metabase_data) > 0:
                logger.info(f"[Metabase 原始响应] 第一行数据: {metabase_data[0]}")
                logger.info(f"[Metabase 原始响应] 第一行键名: {list(metabase_data[0].keys()) if isinstance(metabase_data[0], dict) else 'N/A'}")
            elif isinstance(metabase_data, dict):
                logger.info(f"[Metabase 原始响应] 键: {list(metabase_data.keys())}")
            
            # 5. 处理返回数据格式
            # Metabase 的 /api/card/{id}/query/json 可能返回列表或字典
            if isinstance(metabase_data, list):
                # 如果是列表,转换为标准格式
                metabase_data = {
                    "data": {
                        "rows": metabase_data,
                        "cols": []
                    }
                }
            elif not isinstance(metabase_data, dict):
                # 其他格式,包装成标准格式
                metabase_data = {
                    "data": {
                        "rows": [metabase_data],
                        "cols": []
                    }
                }
            
            # 6. 转换响应格式
            result = self._convert_response(question_key, metabase_data)
            
            # 对于 KPI 类型返回,没有 row_count 字段,使用 .get() 安全获取
            row_count = result.get('row_count', '1行' if question_key.endswith('kpi') else '未知')
            logger.debug(f"Question查询成功: {question_key} (ID: {question_id}), 返回 {row_count}")
            return result
            
        except httpx.HTTPStatusError as e:
            logger.error(f"Metabase Question查询失败: HTTP {e.response.status_code}, {e.response.text}")
            raise ValueError(f"Metabase查询失败: HTTP {e.response.status_code}")
        except ValueError as e:
            # 重新抛出ValueError(配置错误)
            raise
        except Exception as e:
            logger.error(f"Metabase Question查询异常: {e}", exc_info=True)
            raise ValueError(f"Metabase查询异常: {str(e)}")
    
    async def close(self):
        """关闭HTTP客户端"""
        await self.client.aclose()


# 全局服务实例(单例模式)
_service_instance: Optional[MetabaseQuestionService] = None


def get_metabase_service() -> MetabaseQuestionService:
    """获取Metabase服务实例(单例)"""
    global _service_instance
    if _service_instance is None:
        _service_instance = MetabaseQuestionService()
    return _service_instance

