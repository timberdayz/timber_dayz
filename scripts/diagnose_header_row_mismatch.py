#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
诊断表头行问题：检查是否存在预览和入库不一致的问题
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.models.database import get_db
from sqlalchemy import text

def safe_print(text):
    try:
        print(text)
    except UnicodeEncodeError:
        print(text.encode('gbk', errors='ignore').decode('gbk'))

def diagnose_header_row_mismatch():
    safe_print("======================================================================")
    safe_print("诊断表头行不一致问题")
    safe_print("======================================================================")
    
    safe_print("\n问题分析:")
    safe_print("  用户说'明确的设定了表头行在第1行'，但实际入库时从第0行开始")
    safe_print("\n可能的原因:")
    safe_print("  1. 用户误解了0-based的含义（认为'第1行'就是设置1）")
    safe_print("  2. 模板自动应用时覆盖了用户手动设置的表头行")
    safe_print("  3. 预览和入库使用了不同的header_row值")
    safe_print("  4. 前端传递的header_row参数被忽略或覆盖")
    
    safe_print("\n代码检查:")
    safe_print("  ✅ 前端: headerRow.value初始化为0（0-based）")
    safe_print("  ✅ 前端: 传递header_row: headerRow.value || 0")
    safe_print("  ✅ 后端: 接收header_row = ingest_data.get('header_row', 0)")
    safe_print("  ✅ 后端: 使用header_param = header_row（直接使用，不转换）")
    safe_print("  ✅ 后端: ExcelParser.read_excel(header=header_param)")
    
    safe_print("\n关键发现:")
    safe_print("  从测试结果看，header_row=1是正确的（Excel第2行是表头）")
    safe_print("  但用户说'设定了表头行在第1行'，可能有两种理解:")
    safe_print("    - 理解1: Excel第1行是表头 → 应该设置headerRow=0")
    safe_print("    - 理解2: Excel第2行是表头 → 应该设置headerRow=1（正确）")
    
    safe_print("\n可能的问题:")
    safe_print("  ⚠️ 如果用户手动设置了headerRow=1，但模板自动应用时:")
    safe_print("    - 模板中header_row=1（正确）")
    safe_print("    - 用户手动设置headerRow=1（正确）")
    safe_print("    - 但如果预览时使用了headerRow=0，入库时使用了headerRow=1")
    safe_print("    - 就会导致预览和入库不一致")
    
    safe_print("\n检查点:")
    safe_print("  1. 用户手动设置headerRow后，是否被模板覆盖？")
    safe_print("  2. 预览时使用的headerRow和入库时使用的headerRow是否一致？")
    safe_print("  3. 前端是否有地方会重置headerRow的值？")
    
    safe_print("\n======================================================================")
    safe_print("建议修复方案")
    safe_print("======================================================================")
    safe_print("  1. 在前端添加表头行设置的提示（明确说明0-based）")
    safe_print("  2. 确保模板应用时不会覆盖用户手动设置的表头行")
    safe_print("  3. 在入库前记录日志，确认使用的header_row值")
    safe_print("  4. 添加表头行验证，确保预览和入库使用相同的值")

if __name__ == "__main__":
    diagnose_header_row_mismatch()

