#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
全面系统排查脚本 - 检查双维护和设计漏洞
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.models.database import get_db
from modules.core.db import FieldMappingDictionary
from sqlalchemy import or_, func, text
import json

def safe_print(text):
    try:
        print(text)
    except UnicodeEncodeError:
        print(text.encode('gbk', errors='ignore').decode('gbk'))

def check_ssot_compliance():
    """检查SSOT合规性"""
    safe_print("\n" + "="*80)
    safe_print("1. SSOT合规性检查")
    safe_print("="*80)
    
    db = next(get_db())
    
    # 检查拼音字段
    pinyin_patterns = [
        'xiao_shou_%', '%_num_ven', '%_num_wen', 'mai_jia_%', 
        'jian_shu_%', 'liu_lian_%', 'ping_jun_%', 'yong_hu_%',
        'shou_ci_%', 'xun_wen_%', 'hui_fu_%', 'wei_hui_fu_%',
        'yi_hui_fu_%', 'conversion_rate_xun_%', 'conversion_rate_hui_%'
    ]
    
    conditions = [FieldMappingDictionary.field_code.like(p) for p in pinyin_patterns]
    pinyin_count = db.query(FieldMappingDictionary).filter(or_(*conditions)).count()
    
    if pinyin_count > 0:
        safe_print(f"[FAIL] 发现 {pinyin_count} 个拼音字段（违反SSOT）")
        return False
    else:
        safe_print("[OK] 无拼音字段")
    
    # 检查重复定义
    duplicates = db.query(
        FieldMappingDictionary.field_code,
        func.count(FieldMappingDictionary.id).label('count')
    ).group_by(FieldMappingDictionary.field_code).having(
        func.count(FieldMappingDictionary.id) > 1
    ).all()
    
    if len(duplicates) > 0:
        safe_print(f"[FAIL] 发现 {len(duplicates)} 个重复定义")
        for code, count in duplicates:
            safe_print(f"  - {code}: {count} 个定义")
        return False
    else:
        safe_print("[OK] 无重复定义")
    
    return True

def check_pattern_matching():
    """检查Pattern匹配逻辑"""
    safe_print("\n" + "="*80)
    safe_print("2. Pattern匹配逻辑检查")
    safe_print("="*80)
    
    db = next(get_db())
    
    # 检查销售字段的pattern
    sales_fields = db.query(FieldMappingDictionary).filter(
        FieldMappingDictionary.field_code.like('sales_amount%'),
        FieldMappingDictionary.is_pattern_based == True
    ).all()
    
    safe_print(f"[INFO] 找到 {len(sales_fields)} 个Pattern-based销售字段")
    
    # 测试"销售 (SGD)"匹配
    test_field = "销售 (SGD)"
    import re
    
    for field in sales_fields:
        if field.field_pattern:
            match = re.match(field.field_pattern, test_field, re.IGNORECASE)
            if match:
                safe_print(f"[OK] {field.field_code} 匹配成功")
                safe_print(f"    Pattern: {field.field_pattern}")
                safe_print(f"    Groups: {match.groupdict()}")
                return True
    
    safe_print("[WARNING] '销售 (SGD)' 未匹配到任何Pattern")
    return False

def check_database_indexes():
    """检查数据库索引"""
    safe_print("\n" + "="*80)
    safe_print("3. 数据库索引检查")
    safe_print("="*80)
    
    db = next(get_db())
    
    # 检查重复索引
    result = db.execute(text("""
        SELECT indexname, tablename 
        FROM pg_indexes 
        WHERE schemaname = 'public' 
        AND indexname LIKE '%field_mappings%'
        ORDER BY indexname
    """))
    
    indexes = result.fetchall()
    safe_print(f"[INFO] 找到 {len(indexes)} 个field_mappings相关索引")
    
    # 检查是否有重复的索引名
    index_names = [row[0] for row in indexes]
    if len(index_names) != len(set(index_names)):
        safe_print("[WARNING] 发现重复的索引名")
        return False
    
    safe_print("[OK] 索引检查通过")
    return True

def check_frontend_backend_sync():
    """检查前后端同步"""
    safe_print("\n" + "="*80)
    safe_print("4. 前后端同步检查")
    safe_print("="*80)
    
    # 检查前端文件是否存在
    frontend_file = Path(__file__).parent.parent / "frontend" / "src" / "views" / "FieldMappingEnhanced.vue"
    
    if not frontend_file.exists():
        safe_print("[FAIL] 前端文件不存在")
        return False
    
    # 检查是否包含"无需映射"
    content = frontend_file.read_text(encoding='utf-8')
    if '无需映射' in content:
        safe_print("[OK] 前端已包含'无需映射'选项")
    else:
        safe_print("[FAIL] 前端未包含'无需映射'选项")
        return False
    
    safe_print("[OK] 前后端同步检查通过")
    return True

def main():
    safe_print("\n" + "="*80)
    safe_print("全面系统排查 - 双维护和设计漏洞检查")
    safe_print("="*80)
    
    results = []
    
    # 执行所有检查
    results.append(("SSOT合规性", check_ssot_compliance()))
    results.append(("Pattern匹配逻辑", check_pattern_matching()))
    results.append(("数据库索引", check_database_indexes()))
    results.append(("前后端同步", check_frontend_backend_sync()))
    
    # 汇总
    safe_print("\n" + "="*80)
    safe_print("检查汇总")
    safe_print("="*80)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for name, result in results:
        status = "[OK]" if result else "[FAIL]"
        safe_print(f"  {status} {name}")
    
    safe_print(f"\n总计: {passed}/{total} 项检查通过")
    
    if passed == total:
        safe_print("\n[SUCCESS] 所有检查通过！")
        return 0
    else:
        safe_print("\n[WARNING] 部分检查未通过，请修复")
        return 1

if __name__ == "__main__":
    sys.exit(main())

