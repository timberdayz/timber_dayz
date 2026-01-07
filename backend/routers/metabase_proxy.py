"""
Metabase代理API
用于前端与Metabase交互的代理层
"""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import Optional, Dict, Any, List
import requests
import os
from modules.core.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/metabase", tags=["metabase"])

# Metabase配置
METABASE_URL = os.getenv("METABASE_URL", "http://localhost:8080")
METABASE_EMBEDDING_SECRET_KEY = os.getenv("METABASE_EMBEDDING_SECRET_KEY", "change-this-embedding-key-in-production")


class EmbeddingTokenRequest(BaseModel):
    """嵌入token请求"""
    dashboard_id: int
    filters: Optional[Dict[str, Any]] = None


class DashboardEmbedUrlRequest(BaseModel):
    """Dashboard嵌入URL请求"""
    dashboard_id: int
    filters: Optional[Dict[str, Any]] = None
    granularity: Optional[str] = "daily"


@router.get("/health")
async def check_metabase_health():
    """
    检查Metabase健康状态
    """
    try:
        # Metabase健康检查端点不需要认证
        # 使用更长的超时时间，并添加重试逻辑
        response = requests.get(
            f"{METABASE_URL}/api/health",
            timeout=10,
            allow_redirects=True,
            verify=False  # 开发环境可以跳过SSL验证
        )
        
        if response.status_code == 200:
            return {
                "healthy": True,
                "metabase_url": METABASE_URL,
                "status": "available"
            }
        elif response.status_code in [302, 301]:
            # 重定向通常表示Metabase正在运行但需要设置
            return {
                "healthy": True,
                "metabase_url": METABASE_URL,
                "status": "available_but_setup_required",
                "message": "Metabase正在运行，但可能需要完成初始设置"
            }
        else:
            return {
                "healthy": False,
                "metabase_url": METABASE_URL,
                "status": "unavailable",
                "status_code": response.status_code
            }
    except requests.exceptions.ConnectionError:
        logger.warning(f"Metabase连接失败: {METABASE_URL} 不可访问")
        return {
            "healthy": False,
            "metabase_url": METABASE_URL,
            "status": "connection_error",
            "error": "无法连接到Metabase服务"
        }
    except Exception as e:
        logger.error(f"Metabase健康检查失败: {e}")
        return {
            "healthy": False,
            "metabase_url": METABASE_URL,
            "status": "error",
            "error": str(e)
        }


@router.post("/embedding-token")
async def get_embedding_token(request: EmbeddingTokenRequest):
    """
    获取Metabase嵌入token
    
    注意：实际实现中，应该使用Metabase API生成JWT token
    这里简化处理，返回配置的密钥（生产环境需要实现JWT生成逻辑）
    """
    try:
        # TODO: 实现JWT token生成逻辑
        # 参考Metabase文档：https://www.metabase.com/docs/latest/embedding/signed-embeds
        
        # 简化实现：返回配置的密钥
        # 生产环境应该使用jwt库生成token
        token = METABASE_EMBEDDING_SECRET_KEY
        
        logger.info(f"生成嵌入token for dashboard {request.dashboard_id}")
        
        return {
            "token": token,
            "dashboard_id": request.dashboard_id,
            "expires_in": 3600  # 1小时
        }
    except Exception as e:
        logger.error(f"获取嵌入token失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"获取嵌入token失败: {str(e)}")


@router.get("/dashboard/{dashboard_id}/embed-url")
async def get_dashboard_embed_url(
    dashboard_id: int,
    filters: Optional[str] = Query(None, description="筛选器JSON字符串"),
    granularity: Optional[str] = Query("daily", description="时间粒度")
):
    """
    获取Dashboard嵌入URL
    """
    try:
        # 解析筛选器
        import json
        filter_dict = {}
        if filters:
            try:
                filter_dict = json.loads(filters)
            except json.JSONDecodeError:
                logger.warning(f"筛选器JSON解析失败: {filters}")
        
        # 构建URL参数
        params = {
            "granularity": granularity,
            "theme": "transparent",
            "hide_parameters": "false"
        }
        
        # 添加筛选器参数
        if filter_dict:
            if "date_range" in filter_dict:
                params["date_range"] = filter_dict["date_range"]
            if "platform" in filter_dict:
                params["platform"] = filter_dict["platform"]
            if "shop_id" in filter_dict:
                params["shop_id"] = filter_dict["shop_id"]
            if "shop_name" in filter_dict:
                params["shop_name"] = filter_dict["shop_name"]
        
        # 构建完整URL
        base_url = f"{METABASE_URL}/embed/dashboard/{dashboard_id}"
        query_string = "&".join([f"{k}={v}" for k, v in params.items()])
        embed_url = f"{base_url}?{query_string}"
        
        return {
            "url": embed_url,
            "dashboard_id": dashboard_id,
            "filters": filter_dict,
            "granularity": granularity
        }
    except Exception as e:
        logger.error(f"获取Dashboard嵌入URL失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"获取Dashboard嵌入URL失败: {str(e)}")


@router.post("/refresh-views")
async def refresh_metabase_views():
    """
    刷新Metabase相关的物化视图
    
    注意：这个接口应该触发PostgreSQL物化视图刷新
    而不是Metabase的视图刷新
    """
    try:
        # TODO: 实现物化视图刷新逻辑
        # 应该调用MaterializedViewService刷新相关视图
        
        logger.info("刷新Metabase相关物化视图")
        
        # 这里应该调用实际的刷新服务
        # from backend.services.materialized_view_service import MaterializedViewService
        # service = MaterializedViewService()
        # service.refresh_all()
        
        return {
            "success": True,
            "message": "物化视图刷新已启动",
            "status": "pending"
        }
    except Exception as e:
        logger.error(f"刷新物化视图失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"刷新物化视图失败: {str(e)}")

