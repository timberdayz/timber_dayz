#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
代码扫描脚本：分析字段使用情况（v4.7.0）

功能：
1. 扫描backend/routers目录，提取API端点中使用的数据库字段
2. 扫描frontend/src目录，提取前端组件中使用的API参数
3. 建立字段使用链路：数据库字段 → API参数 → 前端组件
4. 将结果存储到field_usage_tracking表

使用方法：
    python scripts/analyze_field_usage.py
"""

import sys
import re
from pathlib import Path
from typing import List, Dict, Set

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from backend.models.database import engine
from sqlalchemy import text


class FieldUsageAnalyzer:
    """字段使用分析器"""
    
    def __init__(self):
        self.backend_dir = project_root / "backend" / "routers"
        self.frontend_dir = project_root / "frontend" / "src"
        self.usages = []
    
    def analyze_backend_api(self):
        """分析后端API文件"""
        print("\n=== 分析后端API ===")
        
        if not self.backend_dir.exists():
            print(f"  目录不存在: {self.backend_dir}")
            return
        
        for file_path in self.backend_dir.glob("*.py"):
            self._analyze_api_file(file_path)
    
    def _analyze_api_file(self, file_path: Path):
        """分析单个API文件"""
        try:
            content = file_path.read_text(encoding='utf-8')
            file_name = file_path.name
            
            # 提取API端点
            # 匹配 @router.get("/products/products") 或 @router.post("/xxx")
            api_pattern = r'@router\.(get|post|put|delete|patch)\("([^"]+)"\)'
            
            for match in re.finditer(api_pattern, content):
                method = match.group(1)
                endpoint = match.group(2)
                
                # 查找这个端点使用的字段
                # 通过查找filter()、query()等方法
                self._extract_field_usage_from_endpoint(
                    content, endpoint, file_name, match.start()
                )
        
        except Exception as e:
            print(f"  [WARN] 分析文件失败 {file_path.name}: {e}")
    
    def _extract_field_usage_from_endpoint(self, content: str, endpoint: str, file_name: str, start_pos: int):
        """从端点代码中提取字段使用情况"""
        # 简化版：查找常见模式
        # 1. FactProductMetric.platform_sku
        # 2. filter(FactProductMetric.platform_sku == ...)
        # 3. or_(FactProductMetric.platform_sku.ilike(...), FactProductMetric.product_name.ilike(...))
        
        # 提取端点后面约200行的代码（作为上下文）
        lines = content[start_pos:start_pos + 5000].split('\n')
        
        # 查找表名
        table_pattern = r'(Fact\w+|Dim\w+|Staging\w+)\.'
        # 查找字段名
        field_pattern = r'\.(platform_code|shop_id|platform_sku|product_name|price|stock|available_stock|total_stock|order_id|order_status|payment_status)'
        
        found_fields = set()
        for line in lines[:100]:  # 只看前100行
            # 查找 TableName.field_name 模式
            matches = re.findall(r'(Fact\w+|Dim\w+|Staging\w+)\.(\w+)', line)
            for table_class, field in matches:
                found_fields.add((self._class_to_table(table_class), field))
        
        # 提取API参数
        api_params = self._extract_api_params(lines[:50])
        
        # 记录usage
        for table_name, field_name in found_fields:
            for param in api_params:
                self.usages.append({
                    "table_name": table_name,
                    "field_name": field_name,
                    "api_endpoint": f"/api{endpoint}",
                    "api_param": param,
                    "api_file": f"backend/routers/{file_name}",
                    "usage_type": "query",
                    "source_type": "scanned"
                })
    
    def _extract_api_params(self, lines: List[str]) -> Set[str]:
        """提取API参数"""
        params = set()
        # 查找 @Query 或 Query(...) 或 keyword: str = Query(...)
        param_pattern = r'(\w+):\s*\w+\s*=\s*Query\('
        
        for line in lines:
            matches = re.findall(param_pattern, line)
            params.update(matches)
        
        return params
    
    def _class_to_table(self, class_name: str) -> str:
        """类名转表名"""
        # FactProductMetric → fact_product_metrics
        # DimProduct → dim_products
        
        # 插入下划线
        table_name = re.sub(r'(?<!^)(?=[A-Z])', '_', class_name).lower()
        
        # 复数化（简化版）
        if not table_name.endswith('s'):
            table_name += 's'
        
        return table_name
    
    def analyze_frontend_components(self):
        """分析前端组件文件"""
        print("\n=== 分析前端组件 ===")
        
        views_dir = self.frontend_dir / "views"
        if not views_dir.exists():
            print(f"  目录不存在: {views_dir}")
            return
        
        for file_path in views_dir.glob("*.vue"):
            self._analyze_vue_file(file_path)
    
    def _analyze_vue_file(self, file_path: Path):
        """分析单个Vue文件"""
        try:
            content = file_path.read_text(encoding='utf-8')
            file_name = file_path.name
            
            # 提取API调用
            # api.get('/products/products', ...)
            # api.post('/field-mapping/ingest', ...)
            api_call_pattern = r'api\.(get|post|put|delete)\([\'"]([^\'"]+)[\'"]'
            
            for match in re.finditer(api_call_pattern, content):
                endpoint = match.group(2)
                # 提取params
                params = self._extract_frontend_params(content, match.start())
                
                for param in params:
                    self.usages.append({
                        "table_name": None,  # 前端不知道表名
                        "field_name": None,  # 前端不知道字段名
                        "api_endpoint": f"/api{endpoint}" if not endpoint.startswith('/api') else endpoint,
                        "api_param": None,
                        "frontend_component": file_name,
                        "frontend_param": param,
                        "frontend_file": f"frontend/src/views/{file_name}",
                        "usage_type": "query",
                        "source_type": "scanned"
                    })
        
        except Exception as e:
            print(f"  [WARN] 分析文件失败 {file_path.name}: {e}")
    
    def _extract_frontend_params(self, content: str, start_pos: int) -> Set[str]:
        """提取前端参数"""
        params = set()
        # 提取 params: { platform: filters.platform, ... }
        
        # 简化版：查找常见参数名
        param_pattern = r'(platform|shop_id|keyword|category|status|low_stock|page|page_size):'
        
        # 查找API调用后面的200个字符
        context = content[start_pos:start_pos + 500]
        
        matches = re.findall(param_pattern, context)
        params.update(matches)
        
        return params
    
    def save_to_database(self):
        """保存到数据库"""
        print("\n=== 保存到数据库 ===")
        
        if not self.usages:
            print("  没有发现字段使用情况")
            return
        
        with engine.connect() as conn:
            # 清空旧数据
            conn.execute(text("DELETE FROM field_usage_tracking WHERE source_type = 'scanned'"))
            conn.commit()
            print(f"  已清空旧的扫描数据")
            
            # 插入新数据
            inserted = 0
            for usage in self.usages:
                try:
                    # 跳过不完整的记录
                    if not usage.get("table_name") and not usage.get("frontend_component"):
                        continue
                    
                    conn.execute(text("""
                        INSERT INTO field_usage_tracking
                          (table_name, field_name, api_endpoint, api_param, api_file,
                           frontend_component, frontend_param, frontend_file,
                           usage_type, source_type, created_by)
                        VALUES
                          (:table_name, :field_name, :api_endpoint, :api_param, :api_file,
                           :frontend_component, :frontend_param, :frontend_file,
                           :usage_type, :source_type, :created_by)
                        ON CONFLICT (table_name, field_name, api_endpoint, frontend_component) DO NOTHING
                    """), {
                        "table_name": usage.get("table_name"),
                        "field_name": usage.get("field_name"),
                        "api_endpoint": usage.get("api_endpoint"),
                        "api_param": usage.get("api_param"),
                        "api_file": usage.get("api_file"),
                        "frontend_component": usage.get("frontend_component"),
                        "frontend_param": usage.get("frontend_param"),
                        "frontend_file": usage.get("frontend_file"),
                        "usage_type": usage.get("usage_type", "query"),
                        "source_type": "scanned",
                        "created_by": "scanner"
                    })
                    inserted += 1
                except Exception as e:
                    print(f"  [WARN] 插入失败: {e}")
            
            conn.commit()
            print(f"  已插入 {inserted} 条使用记录")
    
    def run(self):
        """执行分析"""
        print("=== 字段使用情况分析 ===")
        print(f"项目根目录: {project_root}")
        
        self.analyze_backend_api()
        self.analyze_frontend_components()
        self.save_to_database()
        
        print("\n=== 分析完成 ===")
        print(f"总计发现: {len(self.usages)} 条使用记录")


if __name__ == "__main__":
    analyzer = FieldUsageAnalyzer()
    analyzer.run()

