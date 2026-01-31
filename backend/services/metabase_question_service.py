"""
Metabase Question查询服务
用于通过Metabase REST API查询Question并返回数据
支持通过名称动态查询 Question ID（优先），环境变量 ID 为向后兼容兜底。
"""

import asyncio
import os
import httpx
import yaml
from pathlib import Path
from typing import Dict, Any, Optional, List
from modules.core.logger import get_logger

logger = get_logger(__name__)

# 禁用代理,避免通过代理连接 localhost
# 设置环境变量,让 httpx 不使用代理
os.environ.setdefault("NO_PROXY", "localhost,127.0.0.1,0.0.0.0")
os.environ.setdefault("no_proxy", "localhost,127.0.0.1,0.0.0.0")


def _get_project_root() -> Path:
    """项目根目录（backend/services -> backend -> 根）"""
    return Path(__file__).resolve().parent.parent.parent


def _load_question_key_to_display_name() -> Dict[str, str]:
    """从 config/metabase_config.yaml 加载 question_key -> display_name 映射"""
    config_path = _get_project_root() / "config" / "metabase_config.yaml"
    if not config_path.exists():
        return {}
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)
        questions = config.get("questions") or []
        return {
            str(q.get("name", "")): str(q.get("display_name") or q.get("name", ""))
            for q in questions
            if q.get("name")
        }
    except Exception as e:
        logger.warning(f"加载 metabase_config.yaml 失败: {e}")
        return {}


class MetabaseQuestionService:
    """Metabase Question查询服务（支持按名称动态查询 Question ID）"""
    
    def __init__(self):
        """初始化Metabase服务"""
        self.base_url = os.getenv("METABASE_URL", "http://localhost:8080").rstrip('/')
        self.username = os.getenv("METABASE_USERNAME", "")
        self.password = os.getenv("METABASE_PASSWORD", "")
        # 优先使用API Key,去除首尾空白字符
        self.api_key = os.getenv("METABASE_API_KEY", "").strip() if os.getenv("METABASE_API_KEY") else ""
        
        # Session Token缓存
        self.session_token: Optional[str] = None
        
        # 按名称查到的 Question ID 缓存（name -> id）
        self._question_cache: Dict[str, int] = {}
        self._cache_loaded: bool = False
        self._cache_lock: asyncio.Lock = asyncio.Lock()
        
        # 环境变量 Question ID（向后兼容，名称查询失败时使用）
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
    
    async def _load_question_cache(self) -> None:
        """
        通过 Metabase API 按名称加载 Question ID 缓存。
        使用 config/metabase_config.yaml 中的 question_key -> display_name，
        再通过 GET /api/card 匹配 Metabase 中的 card name（即 display_name）得到 ID。
        """
        async with self._cache_lock:
            if self._cache_loaded:
                return
            await self._ensure_session_token()
            headers: Dict[str, str] = {}
            if self.api_key:
                headers["X-API-Key"] = self.session_token or self.api_key
            else:
                headers["X-Metabase-Session"] = self.session_token or ""
            key_to_display = _load_question_key_to_display_name()
            if not key_to_display:
                logger.warning("metabase_config.yaml 中无 questions，将仅使用环境变量 Question ID")
                self._cache_loaded = True
                return
            try:
                # GET /api/card 可返回列表或 {"data": [...], "total": N}
                response = await self.client.get(
                    f"{self.base_url}/api/card",
                    headers=headers,
                    params={"type": "question"},
                )
                response.raise_for_status()
                data = response.json()
                cards = data.get("data", data) if isinstance(data, dict) else data
                if not isinstance(cards, list):
                    cards = []
                display_name_to_id: Dict[str, int] = {}
                for card in cards:
                    name = card.get("name")
                    cid = card.get("id")
                    if name and cid is not None and card.get("type") == "question":
                        display_name_to_id[name] = int(cid)
                for question_key, display_name in key_to_display.items():
                    if display_name in display_name_to_id:
                        self._question_cache[question_key] = display_name_to_id[display_name]
                        logger.debug(f"Question 名称解析: {question_key} -> {display_name} (ID: {display_name_to_id[display_name]})")
                self._cache_loaded = True
                if self._question_cache:
                    logger.info(f"Metabase Question 缓存已加载: {len(self._question_cache)} 个")
            except Exception as e:
                logger.warning(f"按名称加载 Question 缓存失败，将使用环境变量: {e}")
                self._cache_loaded = True
    
    async def _get_question_id(self, question_key: str) -> int:
        """
        获取 Question ID：优先从名称缓存，其次从环境变量。
        
        Args:
            question_key: Question 键名（如 business_overview_kpi）
            
        Returns:
            Question ID
            
        Raises:
            ValueError: 未找到 Question ID 时抛出
        """
        await self._load_question_cache()
        question_id = self._question_cache.get(question_key) or self.question_ids.get(question_key) or 0
        if not question_id:
            env_var_name = f"METABASE_QUESTION_{question_key.upper()}"
            error_msg = (
                f"Question ID 未找到: {question_key}\n"
                f"请确保已运行 init_metabase.py 创建 Question，或设置环境变量 {env_var_name}\n"
                f"获取方式: 运行 python scripts/init_metabase.py 后，在 Metabase 中查看 Question ID"
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
        
        # 日期参数(单日期)：规范化为 YYYY-MM-DD，避免带时间或时区导致 Metabase 报错
        def _normalize_date(v: Any) -> Optional[str]:
            if v is None:
                return None
            if isinstance(v, str):
                s = v.strip()
                if len(s) >= 10 and s[4] == "-" and s[7] == "-":
                    return s[:10]
                return s if s else None
            return str(v)[:10] if v else None

        if params.get("date"):
            date_val = _normalize_date(params["date"])
            if date_val:
                metabase_params.append({
                    "type": "date",
                    "target": ["variable", ["template-tag", "date"]],
                    "value": date_val
                })
        elif params.get("date_value"):
            date_val = _normalize_date(params["date_value"])
            if date_val:
                metabase_params.append({
                    "type": "date",
                    "target": ["variable", ["template-tag", "date"]],
                    "value": date_val
                })
        
        # 平台参数（SQL 中 [[and o.platform_code = {{platform}}]] 为单值，统一传第一个平台）
        if params.get("platforms"):
            platforms = params["platforms"]
            if isinstance(platforms, str):
                platforms = [p.strip() for p in platforms.split(",") if p.strip()]
            elif not isinstance(platforms, list):
                platforms = [platforms]
            platform_value = platforms[0] if platforms else None
            if platform_value is not None:
                metabase_params.append({
                    "type": "text",
                    "target": ["variable", ["template-tag", "platform"]],
                    "value": platform_value
                })
        
        # 店铺参数
        if params.get("shops"):
            shops = params["shops"]
            if isinstance(shops, str):
                shops = [s.strip() for s in shops.split(",") if s.strip()]
            elif not isinstance(shops, list):
                shops = [shops]
            
            metabase_params.append({
                "type": "text",
                "target": ["variable", ["template-tag", "shop_id"]],
                "value": shops if len(shops) > 1 else (shops[0] if shops else None)
            })
        
        # 粒度参数（Metabase 要求 text 类型参数用 type: "text"，不能用 "string"）
        if params.get("granularity"):
            metabase_params.append({
                "type": "text",
                "target": ["variable", ["template-tag", "granularity"]],
                "value": params["granularity"]
            })
        
        # 分组参数
        if params.get("group_by"):
            metabase_params.append({
                "type": "text",
                "target": ["variable", ["template-tag", "group_by"]],
                "value": params["group_by"]
            })
        
        # 维度参数
        if params.get("dimension"):
            metabase_params.append({
                "type": "text",
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
            # Metabase SQL 返回:GMV(元), 订单数, 访客数, 转化率(%), 客单价(元), 连带率, 人效(元/人) + 7 个环比列
            if result_list and len(result_list) > 0:
                first_row = result_list[0]
                
                # 提取本月指标(支持中文和英文字段名)
                gmv = first_row.get("GMV(元)") or first_row.get("gmv") or first_row.get("total_gmv") or 0
                order_count = first_row.get("订单数") or first_row.get("order_count") or first_row.get("total_orders") or 0
                visitor_count = first_row.get("访客数") or first_row.get("visitor_count") or first_row.get("total_visitors") or 0
                conversion_rate = first_row.get("转化率(%)") or first_row.get("conversion_rate") or 0
                avg_order_value = first_row.get("客单价(元)") or first_row.get("avg_order_value") or first_row.get("average_order_value") or 0
                attach_rate = first_row.get("连带率") or first_row.get("attach_rate") or 0
                labor_efficiency = first_row.get("人效(元/人)") or first_row.get("labor_efficiency") or 0
                
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
                attach_rate_change = _num_or_none(first_row.get("连带率环比(%)"))
                labor_efficiency_change = _num_or_none(first_row.get("人效环比(%)"))
                
                return {
                    # 核心 KPI 指标(直接返回数值)
                    "gmv": gmv,
                    "order_count": order_count,
                    "visitor_count": visitor_count,
                    "conversion_rate": conversion_rate,
                    "avg_order_value": avg_order_value,
                    "attach_rate": attach_rate,
                    "labor_efficiency": labor_efficiency,
                    # 环比(百分比数值,可为 None)
                    "gmv_change": gmv_change,
                    "order_count_change": order_count_change,
                    "visitor_count_change": visitor_count_change,
                    "conversion_rate_change": conversion_rate_change,
                    "avg_order_value_change": avg_order_value_change,
                    "attach_rate_change": attach_rate_change,
                    "labor_efficiency_change": labor_efficiency_change,
                    # 兼容旧格式(current/change)
                    "traffic": {"current": visitor_count, "change": visitor_count_change},
                    "average_order_value": {"current": avg_order_value, "change": avg_order_value_change},
                    "conversion_rate_obj": {"current": conversion_rate, "change": conversion_rate_change},
                    "attach_rate_obj": {"current": attach_rate, "change": attach_rate_change},
                    "labor_efficiency_obj": {"current": labor_efficiency, "change": labor_efficiency_change},
                }
            logger.warning(f"[{question_key}] 返回数据为空,返回空对象")
            return {
                "gmv": 0,
                "order_count": 0,
                "visitor_count": 0,
                "conversion_rate": 0,
                "avg_order_value": 0,
                "attach_rate": 0,
                "labor_efficiency": 0,
                "gmv_change": None,
                "order_count_change": None,
                "visitor_count_change": None,
                "conversion_rate_change": None,
                "avg_order_value_change": None,
                "attach_rate_change": None,
                "labor_efficiency_change": None,
                "traffic": {"current": 0, "change": None},
                "average_order_value": {"current": 0, "change": None},
                "conversion_rate_obj": {"current": 0, "change": None},
                "attach_rate_obj": {"current": 0, "change": None},
                "labor_efficiency_obj": {"current": 0, "change": None},
            }
        
        elif question_key == "business_overview_comparison":
            # 对比数据:返回metrics对象(包含today/yesterday/average/change)，对齐经营指标用显式列名兜底
            if result_list and len(result_list) > 0:
                first_row = result_list[0]
                # 兼容 Metabase 返回列名大小写或格式差异：优先用精确 key，再试小写匹配
                def _row_val(row: dict, *keys: str):
                    for k in keys:
                        if k in row and row[k] is not None:
                            return row[k]
                    for k in keys:
                        for rk in row:
                            if rk is not None and str(rk).lower() == k.lower():
                                return row[rk]
                    return None

                metrics = {}
                # 统一用小写指标名，与前端 metrics.sales_amount 等一致（避免 API 返回列名大小写导致取不到）
                def _norm_metric_name(name: str) -> str:
                    return (name or "").lower().rstrip("_")

                # 1) 动态提取(以_today/_yesterday/_average/_change 结尾的字段)
                for key, value in first_row.items():
                    k = str(key) if key is not None else ""
                    if k.endswith("_today"):
                        metric_name = _norm_metric_name(k[:-6])
                        if metric_name not in metrics:
                            metrics[metric_name] = {}
                        metrics[metric_name]["today"] = value
                    elif k.endswith("_yesterday"):
                        metric_name = _norm_metric_name(k[:-10])
                        if metric_name not in metrics:
                            metrics[metric_name] = {}
                        metrics[metric_name]["yesterday"] = value
                    elif k.endswith("_average"):
                        metric_name = _norm_metric_name(k[:-8])
                        if metric_name not in metrics:
                            metrics[metric_name] = {}
                        metrics[metric_name]["average"] = value
                    elif k.endswith("_change"):
                        metric_name = _norm_metric_name(k[:-7])
                        if metric_name not in metrics:
                            metrics[metric_name] = {}
                        metrics[metric_name]["change"] = value

                # 2) 显式列名兜底（与 business_overview_comparison.sql 输出列一致，参考经营指标）
                metric_cols = (
                    "sales_amount", "sales_quantity", "traffic", "conversion_rate",
                    "avg_order_value", "attach_rate", "profit"
                )
                for name in metric_cols:
                    if name not in metrics:
                        metrics[name] = {}
                    m = metrics[name]
                    if m.get("today") is None:
                        m["today"] = _row_val(first_row, f"{name}_today")
                    if m.get("yesterday") is None:
                        m["yesterday"] = _row_val(first_row, f"{name}_yesterday")
                    if m.get("average") is None:
                        m["average"] = _row_val(first_row, f"{name}_average")
                    if m.get("change") is None:
                        m["change"] = _row_val(first_row, f"{name}_change")

                # 根据 change 推导 change_type
                for _name, _m in metrics.items():
                    if "change" in _m and _m["change"] is not None:
                        try:
                            v = float(_m["change"])
                            _m["change_type"] = "increase" if v > 0 else ("decrease" if v < 0 else "neutral")
                        except (TypeError, ValueError):
                            _m["change_type"] = "neutral"
                    else:
                        _m["change_type"] = "neutral"

                # 3) 目标数据：先动态 target_ 前缀，再显式兜底
                target_data = {}
                for key, value in first_row.items():
                    if key.startswith("target_"):
                        target_data[key[7:]] = value
                target_data.setdefault("sales_amount", _row_val(first_row, "target_sales_amount"))
                target_data.setdefault("sales_quantity", _row_val(first_row, "target_sales_quantity"))
                target_data.setdefault("achievement_rate", _row_val(first_row, "target_achievement_rate"))

                return {"metrics": metrics, "target": target_data}
            logger.warning(f"[{question_key}] 返回数据为空,返回空metrics对象")
            return {"metrics": {}, "target": {}}
        
        elif question_key == "business_overview_traffic_ranking":
            # 流量排名：多行转英文 key，兼容中文列名，补 name 兜底
            if not result_list:
                return []
            out = []
            for row in result_list:
                def _v(keys):
                    for k in keys:
                        if k in row and row[k] is not None:
                            return row[k]
                        for rk in row:
                            if rk is not None and str(rk).lower() == k.lower():
                                return row[rk]
                    return None
                name = _v(["名称", "name"]) or _v(["平台", "platform_code"]) or "平台汇总"
                out.append({
                    "rank": _v(["排名", "rank"]),
                    "name": name,
                    "platform_code": _v(["平台", "platform_code"]),
                    "unique_visitors": _v(["访客数", "unique_visitors"]) or 0,
                    "page_views": _v(["浏览量", "page_views"]) or 0,
                    "uv_change_rate": _v(["uv_change_rate"]),
                    "pv_change_rate": _v(["pv_change_rate"]),
                    "compare_unique_visitors": _v(["compare_unique_visitors"]),
                    "compare_page_views": _v(["compare_page_views"]),
                })
            return out
        
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
        
        elif question_key == "business_overview_shop_racing":
            # 店铺赛马：转为前端表格所需格式（名称、目标、完成、完成率、排名）
            # SQL 返回：平台、名称、店铺ID、GMV、订单数、客单价、目标、完成率、排名
            def _row_val(row: dict, *keys: str):
                for k in keys:
                    if k in row and row[k] is not None:
                        return row[k]
                for k in keys:
                    for rk in row:
                        if rk is not None and str(rk).lower() == k.lower():
                            return row[rk]
                return None
            out = []
            for r in result_list:
                name = _row_val(r, "名称", "name") or _row_val(r, "店铺ID", "平台") or "unknown店铺"
                gmv = _row_val(r, "GMV", "gmv")
                try:
                    achieved = float(gmv) if gmv is not None else 0
                except (TypeError, ValueError):
                    achieved = 0
                target_val = _row_val(r, "目标", "target")
                try:
                    target = float(target_val) if target_val is not None else 0
                except (TypeError, ValueError):
                    target = 0
                rate_val = _row_val(r, "完成率", "achievement_rate")
                try:
                    # SQL 返回百分比（如 85.5），前端需 0～1（如 0.855）
                    achievement_rate = float(rate_val) / 100.0 if rate_val is not None else 0
                except (TypeError, ValueError):
                    achievement_rate = 0
                rank_val = _row_val(r, "排名", "rank")
                try:
                    rank = int(rank_val) if rank_val is not None else 0
                except (TypeError, ValueError):
                    rank = 0
                out.append({
                    "name": name,
                    "target": target,
                    "achieved": achieved,
                    "achievement_rate": achievement_rate,
                    "rank": rank,
                })
            return out
        
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
        
        url = ""
        metabase_params_list: List[Dict[str, Any]] = []
        try:
            # 1. 获取 Question ID（按名称或环境变量）
            question_id = await self._get_question_id(question_key)
            
            # 2. 确保有 Session Token
            token = await self._ensure_session_token()
            
            # 3. 转换参数
            metabase_params_list = self._convert_params(params)
            metabase_params = metabase_params_list
            
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
            # 流量排名等返回 list，其他返回 dict；仅对 dict 使用 .get，避免 'list' object has no attribute 'get'
            if isinstance(result, list):
                row_count = len(result)
            else:
                row_count = result.get('row_count', '1行' if question_key.endswith('kpi') else '未知')
            logger.debug(f"Question查询成功: {question_key} (ID: {question_id}), 返回 {row_count}")
            return result
            
        except httpx.HTTPStatusError as e:
            body = e.response.text
            if not url:
                url = f"{self.base_url}/api/card/<id>/query/json"
            logger.error(
                f"Metabase Question查询失败: HTTP {e.response.status_code}\n"
                f"  请求: POST {url}\n"
                f"  参数: {metabase_params_list if metabase_params_list else '无'}\n"
                f"  响应体: {body[:2000] if body else '(空)'}"
            )
            raise ValueError(
                f"Metabase查询失败: HTTP {e.response.status_code} 请检查输入参数是否正确。"
                + (f" 详情: {body[:500]}" if body and len(body) < 500 else " 详情请查看后端日志。")
            )
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

