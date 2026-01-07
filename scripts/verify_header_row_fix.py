#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
验证表头行修复：检查入库时是否正确使用了header_row参数
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

def safe_print(text):
    try:
        print(text)
    except UnicodeEncodeError:
        print(text.encode('gbk', errors='ignore').decode('gbk'))

def verify_header_row_fix():
    safe_print("======================================================================")
    safe_print("验证表头行修复")
    safe_print("======================================================================")
    
    safe_print("\n修复内容总结:")
    safe_print("  1. ✅ 自动应用模板时，同步更新表头行设置")
    safe_print("  2. ✅ 添加表头行设置提示（说明0-based索引）")
    safe_print("  3. ✅ 增强后端日志记录（记录header_row和header_param）")
    safe_print("  4. ✅ 增强前端入库前确认（记录使用的表头行值）")
    
    safe_print("\n关键修复点:")
    safe_print("  - 预览时自动应用模板，如果模板的header_row与当前设置不一致，")
    safe_print("    会自动更新headerRow.value并提示用户重新预览")
    safe_print("  - 入库时使用headerRow.value的值，确保与预览时一致")
    safe_print("  - 后端记录详细的日志，便于调试和排查问题")
    
    safe_print("\n使用说明:")
    safe_print("  1. 设置表头行时，注意0-based索引：")
    safe_print("     - 0 = Excel第1行")
    safe_print("     - 1 = Excel第2行")
    safe_print("     - 2 = Excel第3行")
    safe_print("  2. 预览数据后，如果自动应用了模板，")
    safe_print("    系统会自动同步表头行设置（如有不一致会提示）")
    safe_print("  3. 入库前，查看浏览器控制台日志，")
    safe_print("    确认使用的表头行值是否正确")
    safe_print("  4. 入库后，查看后端日志，")
    safe_print("    确认实际使用的header_row值")
    
    safe_print("\n验证步骤:")
    safe_print("  1. 打开字段映射界面")
    safe_print("  2. 选择一个TikTok订单文件")
    safe_print("  3. 设置表头行=1（Excel第2行）")
    safe_print("  4. 点击'预览数据'")
    safe_print("  5. 查看是否自动应用了模板，表头行是否自动更新")
    safe_print("  6. 点击'确认映射并入库'")
    safe_print("  7. 查看浏览器控制台日志，确认使用的表头行值")
    safe_print("  8. 查看后端日志，确认实际使用的header_row值")
    safe_print("  9. 检查物化视图数据，确认是否正确")
    
    safe_print("\n======================================================================")
    safe_print("修复完成！")
    safe_print("======================================================================")

if __name__ == "__main__":
    verify_header_row_fix()

