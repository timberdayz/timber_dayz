#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
测试数据浏览器API的多schema支持
验证在数据浏览器中可以看到所有schema中的表

使用方法:
    python scripts/test_data_browser_schema.py
"""

import sys
import requests
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from modules.core.logger import get_logger

logger = get_logger(__name__)


def test_data_browser_api():
    """测试数据浏览器API的多schema支持"""
    
    base_url = "http://localhost:8001"
    api_url = f"{base_url}/api/data-browser/tables"
    
    results = {
        "success": True,
        "tests": [],
        "errors": []
    }
    
    try:
        logger.info(f"测试数据浏览器API: {api_url}")
        
        # 发送请求
        response = requests.get(api_url, timeout=10)
        
        if response.status_code != 200:
            results["success"] = False
            results["errors"].append(f"API请求失败: HTTP {response.status_code}")
            logger.error(f"❌ API请求失败: HTTP {response.status_code}")
            return results
        
        data = response.json()
        
        if not data.get("success"):
            results["success"] = False
            results["errors"].append(f"API返回失败: {data.get('message', 'Unknown error')}")
            logger.error(f"❌ API返回失败: {data.get('message')}")
            return results
        
        tables = data.get("data", {}).get("tables", [])
        
        # 按schema分组统计
        schema_stats = {}
        required_schemas = ['public', 'b_class', 'a_class', 'c_class', 'core', 'finance']
        
        for table in tables:
            schema = table.get("schema", "public")
            if schema not in schema_stats:
                schema_stats[schema] = []
            schema_stats[schema].append(table.get("name"))
        
        # 验证每个schema都有表
        print("\n" + "="*60)
        print("数据浏览器API多schema支持测试结果")
        print("="*60)
        
        for schema in required_schemas:
            if schema in schema_stats:
                table_count = len(schema_stats[schema])
                results["tests"].append({
                    "schema": schema,
                    "status": "success",
                    "table_count": table_count,
                    "tables": schema_stats[schema][:5]  # 只显示前5个表名
                })
                print(f"✅ {schema}: {table_count} 张表")
                if table_count > 0:
                    print(f"   示例表: {', '.join(schema_stats[schema][:3])}")
            else:
                results["success"] = False
                results["errors"].append(f"Schema {schema} 中没有表")
                print(f"⚠️ {schema}: 没有表（可能正常，如果该schema确实为空）")
        
        print(f"\n总计: {len(tables)} 张表")
        
        if results["success"]:
            print("\n✅ 数据浏览器API多schema支持测试通过！")
        else:
            print("\n⚠️ 部分Schema没有表，请检查是否正常")
        
        return results
        
    except requests.exceptions.ConnectionError:
        results["success"] = False
        results["errors"].append("无法连接到后端API，请确保后端服务正在运行（http://localhost:8001）")
        logger.error("❌ 无法连接到后端API")
        print("\n❌ 无法连接到后端API，请确保后端服务正在运行")
        print("   启动命令: python run.py")
        return results
    except Exception as e:
        results["success"] = False
        results["errors"].append(f"测试执行失败: {str(e)}")
        logger.error(f"❌ 测试执行失败: {e}", exc_info=True)
        print(f"\n❌ 测试执行失败: {e}")
        return results


if __name__ == "__main__":
    results = test_data_browser_api()
    sys.exit(0 if results["success"] else 1)

