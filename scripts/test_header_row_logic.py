#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试表头行设置：检查用户设置headerRow=1时，实际入库使用的值
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.models.database import get_db
from sqlalchemy import text
import pandas as pd

def safe_print(text):
    try:
        print(text)
    except UnicodeEncodeError:
        print(text.encode('gbk', errors='ignore').decode('gbk'))

def test_header_row_logic():
    safe_print("======================================================================")
    safe_print("测试表头行逻辑")
    safe_print("======================================================================")
    
    db = next(get_db())
    try:
        # 1. 查找一个tiktok订单文件
        safe_print("\n[1] 查找TikTok订单文件:")
        result = db.execute(text("""
            SELECT id, file_name, file_path, data_domain
            FROM catalog_files 
            WHERE platform_code = 'tiktok' 
              AND data_domain = 'orders'
              AND status = 'ingested'
            ORDER BY id DESC 
            LIMIT 1
        """)).fetchone()
        
        if not result:
            safe_print("  未找到已入库的TikTok订单文件")
            return
        
        file_id, file_name, file_path, data_domain = result
        safe_print(f"  文件ID={file_id}, 文件名={file_name}")
        safe_print(f"  文件路径={file_path}")
        
        # 2. 检查文件是否存在
        if not Path(file_path).exists():
            safe_print(f"  [ERROR] 文件不存在: {file_path}")
            return
        
        # 3. 测试不同的header_row值
        safe_print("\n[2] 测试不同的header_row值:")
        for test_header in [0, 1, 2]:
            try:
                from backend.services.excel_parser import ExcelParser
                df = ExcelParser.read_excel(file_path, header=test_header, nrows=5)
                columns = df.columns.tolist()
                safe_print(f"\n  header_row={test_header} (0-based, Excel第{test_header+1}行):")
                safe_print(f"    列名: {columns[:5]}...")
                if len(df) > 0:
                    first_row = df.iloc[0].to_dict()
                    safe_print(f"    第一行数据示例: {list(first_row.items())[:3]}...")
            except Exception as e:
                safe_print(f"  header_row={test_header} 读取失败: {e}")
        
        # 4. 检查模板中的header_row设置
        safe_print("\n[3] 检查模板中的header_row设置:")
        result = db.execute(text("""
            SELECT id, template_name, header_row
            FROM field_mapping_templates 
            WHERE platform = 'tiktok' 
              AND data_domain = 'orders'
            ORDER BY id DESC 
            LIMIT 1
        """)).fetchone()
        if result:
            safe_print(f"  模板: {result[1]}, header_row={result[2]} (0-based)")
            safe_print(f"  说明: header_row={result[2]}表示Excel的第{result[2]+1}行是表头")
        
        safe_print("\n======================================================================")
        safe_print("测试完成")
        safe_print("======================================================================")
        safe_print("\n关键发现:")
        safe_print("  - 如果模板中header_row=1，表示Excel的第2行是表头")
        safe_print("  - 如果用户设置headerRow=1，这是正确的（与模板一致）")
        safe_print("  - 但如果实际Excel的第1行是表头，应该设置headerRow=0")
        safe_print("\n问题分析:")
        safe_print("  用户说'设定了表头行在第1行'，可能有两种理解:")
        safe_print("  1. Excel的第1行是表头 → 应该设置headerRow=0")
        safe_print("  2. Excel的第2行是表头 → 应该设置headerRow=1（与模板一致）")
        safe_print("\n需要确认:")
        safe_print("  - 实际Excel文件中，哪一行是表头？")
        safe_print("  - 用户设置的headerRow值是多少？")
        safe_print("  - 入库时实际使用的header_row值是多少？")
        
    except Exception as e:
        safe_print(f"测试失败: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()

if __name__ == "__main__":
    test_header_row_logic()

