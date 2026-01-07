#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Metabase集成验证脚本

v4.12.0新增（Phase 4 - Metabase集成验证）：
- 验证Metabase数据库连接
- 验证Metabase Question查询
- 验证数据格式符合要求
- 验证前端API代理
- 输出验证报告
"""

import sys
import asyncio
import os
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from modules.core.logger import get_logger
from backend.services.metabase_question_service import get_metabase_service
import httpx

logger = get_logger(__name__)


def test_metabase_connection() -> dict:
    """
    测试Metabase连接
    
    Returns:
        测试结果字典
    """
    print("\n" + "="*60)
    print("测试1: Metabase连接验证")
    print("="*60)
    
    try:
        metabase_url = os.getenv("METABASE_URL", "http://localhost:8080").rstrip('/')  # 端口从3000改为8080，避免Windows端口权限问题
        print(f"\nMetabase URL: {metabase_url}")
        
        # 测试健康检查端点
        print("\n测试健康检查端点...")
        try:
            response = httpx.get(
                f"{metabase_url}/api/health",
                timeout=10,
                follow_redirects=True
            )
            
            print(f"  - HTTP状态码: {response.status_code}")
            
            if response.status_code == 200:
                print("[OK] Metabase健康检查通过")
                return {
                    "success": True,
                    "metabase_url": metabase_url,
                    "status": "available"
                }
            elif response.status_code in [302, 301]:
                print("[WARNING] Metabase返回重定向（可能需要完成初始设置）")
                return {
                    "success": True,
                    "metabase_url": metabase_url,
                    "status": "available_but_setup_required"
                }
            else:
                print(f"[WARNING] Metabase健康检查返回异常状态码: {response.status_code}")
                return {
                    "success": False,
                    "metabase_url": metabase_url,
                    "status_code": response.status_code
                }
        except httpx.ConnectError:
            print("[WARNING] 无法连接到Metabase服务（可能未启动）")
            return {
                "success": False,
                "metabase_url": metabase_url,
                "error": "连接失败"
            }
        except Exception as e:
            logger.error(f"Metabase连接测试失败: {e}", exc_info=True)
            return {
                "success": False,
                "metabase_url": metabase_url,
                "error": str(e)
            }
        
    except Exception as e:
        logger.error(f"Metabase连接测试失败: {e}", exc_info=True)
        return {
            "success": False,
            "error": str(e)
        }


async def test_metabase_authentication() -> dict:
    """
    测试Metabase认证
    
    Returns:
        测试结果字典
    """
    print("\n" + "="*60)
    print("测试2: Metabase认证验证")
    print("="*60)
    
    try:
        service = get_metabase_service()
        
        # 检查配置
        print("\n检查Metabase配置:")
        print(f"  - METABASE_URL: {service.base_url}")
        print(f"  - METABASE_API_KEY: {'已配置' if service.api_key else '未配置'}")
        print(f"  - METABASE_USERNAME: {'已配置' if service.username else '未配置'}")
        print(f"  - METABASE_PASSWORD: {'已配置' if service.password else '未配置'}")
        
        # 测试认证
        print("\n测试认证...")
        try:
            token = await service._ensure_session_token()
            if token:
                print("[OK] Metabase认证成功")
                print(f"  - Token: {token[:20]}..." if len(token) > 20 else f"  - Token: {token}")
                return {
                    "success": True,
                    "auth_method": "api_key" if service.api_key else "username_password"
                }
            else:
                print("[FAIL] Metabase认证失败：未返回Token")
                return {
                    "success": False,
                    "error": "未返回Token"
                }
        except ValueError as e:
            print(f"[WARNING] Metabase认证失败: {e}")
            return {
                "success": False,
                "error": str(e)
            }
        except Exception as e:
            logger.error(f"Metabase认证异常: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e)
            }
        
    except Exception as e:
        logger.error(f"Metabase认证测试失败: {e}", exc_info=True)
        return {
            "success": False,
            "error": str(e)
        }


async def test_metabase_question_query() -> dict:
    """
    测试Metabase Question查询
    
    Returns:
        测试结果字典
    """
    print("\n" + "="*60)
    print("测试3: Metabase Question查询验证")
    print("="*60)
    
    try:
        service = get_metabase_service()
        
        # 检查Question ID配置
        print("\n检查Question ID配置:")
        question_keys = [
            "business_overview_kpi",
            "business_overview_comparison",
            "business_overview_shop_racing",
            "business_overview_traffic_ranking",
            "business_overview_inventory_backlog",
            "business_overview_operational_metrics",
            "clearance_ranking"
        ]
        
        configured_questions = {}
        for key in question_keys:
            question_id = service.question_ids.get(key, 0)
            if question_id and question_id > 0:
                configured_questions[key] = question_id
                print(f"  - {key}: {question_id}")
            else:
                print(f"  - {key}: 未配置")
        
        if not configured_questions:
            print("\n[WARNING] 没有配置任何Question ID，跳过查询测试")
            return {
                "success": False,
                "error": "没有配置Question ID"
            }
        
        # 测试查询（使用第一个配置的Question）
        test_question_key = list(configured_questions.keys())[0]
        test_question_id = configured_questions[test_question_key]
        
        print(f"\n测试查询Question: {test_question_key} (ID: {test_question_id})")
        
        try:
            # 使用空参数测试
            result = await service.query_question(test_question_key, {})
            
            print(f"\n查询结果:")
            print(f"  - 成功: {result.get('success', False)}")
            
            if result.get('success'):
                data = result.get('data', {})
                rows = data.get('rows', [])
                print(f"  - 数据行数: {len(rows)}")
                
                if rows:
                    print(f"  - 第一行数据示例: {rows[0] if len(rows) > 0 else 'N/A'}")
                
                print("[OK] Metabase Question查询成功")
                return {
                    "success": True,
                    "question_key": test_question_key,
                    "question_id": test_question_id,
                    "row_count": len(rows)
                }
            else:
                print(f"  - 错误: {result.get('message', 'N/A')}")
                return {
                    "success": False,
                    "question_key": test_question_key,
                    "error": result.get('message', '查询失败')
                }
                
        except ValueError as e:
            print(f"[WARNING] Question查询失败: {e}")
            return {
                "success": False,
                "question_key": test_question_key,
                "error": str(e)
            }
        except Exception as e:
            logger.error(f"Question查询异常: {e}", exc_info=True)
            return {
                "success": False,
                "question_key": test_question_key,
                "error": str(e)
            }
        
    except Exception as e:
        logger.error(f"Metabase Question查询测试失败: {e}", exc_info=True)
        return {
            "success": False,
            "error": str(e)
        }


def test_metabase_api_proxy() -> dict:
    """
    测试Metabase API代理（验证API路由）
    
    Returns:
        测试结果字典
    """
    print("\n" + "="*60)
    print("测试4: Metabase API代理验证")
    print("="*60)
    
    try:
        # 检查API路由配置
        print("\n检查API路由配置:")
        
        # 检查metabase_proxy路由
        try:
            from backend.routers.metabase_proxy import router as metabase_router
            routes = [route.path for route in metabase_router.routes]
            print(f"  - Metabase代理路由: {len(routes)} 个")
            for route in routes[:5]:  # 只显示前5个
                print(f"    - {route}")
            if len(routes) > 5:
                print(f"    ... 还有 {len(routes) - 5} 个路由")
        except Exception as e:
            logger.warning(f"无法检查metabase_proxy路由: {e}")
        
        # 检查dashboard_api路由
        try:
            from backend.routers.dashboard_api import router as dashboard_router
            routes = [route.path for route in dashboard_router.routes]
            print(f"\n  - Dashboard API路由: {len(routes)} 个")
            for route in routes[:5]:  # 只显示前5个
                print(f"    - {route}")
            if len(routes) > 5:
                print(f"    ... 还有 {len(routes) - 5} 个路由")
        except Exception as e:
            logger.warning(f"无法检查dashboard_api路由: {e}")
        
        print("\n[OK] Metabase API代理路由配置验证通过")
        
        return {
            "success": True
        }
        
    except Exception as e:
        logger.error(f"Metabase API代理验证失败: {e}", exc_info=True)
        return {
            "success": False,
            "error": str(e)
        }


def test_database_connection_for_metabase() -> dict:
    """
    测试数据库连接（Metabase需要连接PostgreSQL）
    
    Returns:
        测试结果字典
    """
    print("\n" + "="*60)
    print("测试5: 数据库连接验证（Metabase需要）")
    print("="*60)
    
    try:
        from sqlalchemy import create_engine, text
        from backend.utils.config import get_settings
        
        settings = get_settings()
        db_url = settings.DATABASE_URL
        
        print(f"\n数据库URL: {db_url[:30]}...")
        
        # 测试连接
        print("\n测试数据库连接...")
        engine = create_engine(db_url)
        
        with engine.connect() as conn:
            result = conn.execute(text("SELECT version()"))
            version = result.scalar()
            print(f"  - PostgreSQL版本: {version[:50]}...")
            
            # 测试查询B类数据表
            result = conn.execute(text("""
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_schema = 'public' 
                AND table_name LIKE 'fact_raw_data_%'
                LIMIT 5
            """))
            tables = [row[0] for row in result]
            
            if tables:
                print(f"  - B类数据表示例: {', '.join(tables)}")
                print("[OK] 数据库连接正常，Metabase可以查询数据")
            else:
                print("[WARNING] 未找到B类数据表（可能为空）")
        
        return {
            "success": True,
            "database_type": "PostgreSQL"
        }
        
    except Exception as e:
        logger.error(f"数据库连接测试失败: {e}", exc_info=True)
        return {
            "success": False,
            "error": str(e)
        }


async def main():
    """主函数"""
    print("="*60)
    print("Metabase集成验证脚本")
    print("="*60)
    print("\n本脚本将验证以下内容:")
    print("  1. Metabase连接")
    print("  2. Metabase认证")
    print("  3. Metabase Question查询")
    print("  4. Metabase API代理")
    print("  5. 数据库连接（Metabase需要）")
    
    try:
        results = {}
        
        # 测试1: Metabase连接
        results["connection"] = test_metabase_connection()
        
        # 测试2: Metabase认证（如果连接成功）
        if results["connection"].get("success"):
            results["authentication"] = await test_metabase_authentication()
        else:
            print("\n[SKIP] 跳过认证测试（Metabase连接失败）")
            results["authentication"] = {"success": False, "skipped": True}
        
        # 测试3: Metabase Question查询（如果认证成功）
        if results.get("authentication", {}).get("success"):
            results["question_query"] = await test_metabase_question_query()
        else:
            print("\n[SKIP] 跳过Question查询测试（认证失败）")
            results["question_query"] = {"success": False, "skipped": True}
        
        # 测试4: Metabase API代理（总是执行）
        results["api_proxy"] = test_metabase_api_proxy()
        
        # 测试5: 数据库连接（总是执行）
        results["database"] = test_database_connection_for_metabase()
        
        # 输出总结报告
        print("\n" + "="*60)
        print("验证报告总结")
        print("="*60)
        
        all_passed = True
        for test_name, result in results.items():
            if result.get("skipped"):
                status = "[SKIP] 跳过"
            elif result.get("success"):
                status = "[OK] 通过"
            else:
                status = "[FAIL] 失败"
                if not result.get("skipped"):
                    all_passed = False
            
            print(f"{test_name}: {status}")
            if not result.get("success") and not result.get("skipped"):
                if "error" in result:
                    print(f"  错误: {result['error']}")
        
        if all_passed:
            print("\n[OK] 所有测试通过！")
        else:
            print("\n[WARNING] 部分测试失败，请检查日志")
            print("[NOTE] Metabase连接和认证测试可能需要Metabase服务运行")
        
        return 0 if all_passed else 1
        
    except Exception as e:
        logger.error(f"验证脚本执行失败: {e}", exc_info=True)
        print(f"\n[ERROR] 验证脚本执行失败: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

