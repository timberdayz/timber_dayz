#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
docs目录清理脚本 - v4.11.1
清理过时和无用文档，仅保留重要文件
"""

import os
import shutil
from pathlib import Path

# 项目根目录
PROJECT_ROOT = Path(__file__).parent.parent
DOCS_DIR = PROJECT_ROOT / "docs"
ARCHIVE_DIR = DOCS_DIR / "archive" / "20251113_cleanup"

# 核心文档（必须保留）
CORE_DOCS = {
    "README.md",
    "AGENT_START_HERE.md",
    "CORE_DATA_FLOW.md",
    "DATA_SOURCE_AND_FIELD_MAPPING_DESIGN.md",
    "FINAL_ARCHITECTURE_STATUS.md",
    "SEMANTIC_LAYER_DESIGN.md",
    "MATERIALIZED_VIEW_MANAGEMENT_BEST_PRACTICES.md",
    "ERP_UI_DESIGN_STANDARDS.md",
    "BACKEND_DATABASE_DESIGN_SUMMARY.md",
    "QUICK_START_ALL_FEATURES.md",
    "V4_4_0_FINANCE_DOMAIN_GUIDE.md",
    "V4_6_0_USER_GUIDE.md",
}

# 版本报告（保留最新）
VERSION_REPORTS_KEEP = {
    "V4_11_1_TRAFFIC_ANALYSIS_WORK_SUMMARY.md",
    "V4_11_1_DOCUMENTATION_UPDATE.md",
    "V4_11_1_DOCUMENTATION_UPDATE_SUMMARY.md",
    "V4_11_0_COMPLETE_WORK_SUMMARY.md",
    "V4_11_0_IMPLEMENTATION_SUMMARY.md",
    "V4_11_0_TESTING_SUMMARY.md",
    "V4_10_1_SESSION_SUMMARY.md",
    "MATERIALIZED_VIEW_REFRESH_FIX_V4_10_1.md",
    "V4_9_3_COMPLETE_FINAL_REPORT.md",
    "V4_9_SERIES_COMPLETE_SUMMARY.md",
}

# 用户指南（保留）
USER_GUIDES_KEEP = {
    "FINAL_USER_GUIDE_MIAOSHOU.md",
    "HOW_TO_IMPORT_MIAOSHOU_PRODUCTS.md",
    "STEP_BY_STEP_MIAOSHOU_IMPORT.md",
    "MIAOSHOU_PRODUCT_MAPPING_GUIDE.md",
}

# 其他重要文档（保留）
OTHER_IMPORTANT = {
    "DATA_QUARANTINE_STANDARDS.md",
    "MATERIALIZED_VIEW_FAQ_FOR_BEGINNERS.md",
    "PRODUCT_IMAGE_MANAGEMENT_GUIDE.md",
    "SYSTEM_STARTUP_GUIDE.md",
    "DATA_PREPARATION_GUIDE.md",
}

# 需要归档的文档（按类别）
FILES_TO_ARCHIVE = {
    # v4.10.1系列（除保留的）
    "V4_10_1_CLEANUP_CHECKLIST.md",
    "V4_10_1_CLEANUP_COMPLETE.md",
    "V4_10_1_FIX_SUMMARY.md",
    "V4_10_1_NEXT_STEPS.md",
    
    # v4.9.x系列（除保留的）
    "V4_9_3_FINAL_DELIVERY.md",
    "V4_9_3_SHORT_TERM_OPTIMIZATION.md",
    "V4_9_3_UI_UX_OPTIMIZATION.md",
    "V4_9_FINAL_SUMMARY.md",
    "V4_8_0_FINAL_SUMMARY.md",
    "V4_8_0_DOUBLE_MAINTENANCE_CLEANUP.md",
    "V4_8_0_MATERIALIZED_VIEW_COMPLETE.md",
    "V4_8_0_SSOT_VERIFICATION_REPORT.md",
    "V4_7_0_DEVELOPMENT_SUMMARY.md",
    "V4_7_0_VARIABLE_NAME_BUG_FIX.md",
    "V4_7_0_DASHBOARD_AND_USER_MANAGEMENT_PLAN.md",
    "V4_6_0_COMPLETE.md",
    "V4_6_0_READY_TO_TEST.md",
    "V4_6_0_ARCHITECTURE_GUIDE.md",
    "v4_6_1_COMPLETE.md",
    "PROJECT_STATUS_v4_5_0.md",
    
    # 订单入库修复
    "ORDER_INGESTION_FIX_COMPLETE.md",
    "ORDER_INGESTION_FIX_SUMMARY_V4_10_0.md",
    "TIKTOK_ORDER_INGESTION_FIX_PLAN.md",
    "ORDER_ITEM_INGESTION_FIX_V4_10_0.md",
    "ORDER_MV_DIAGNOSIS_REPORT.md",
    "SYNC_AND_MV_ISSUES_DIAGNOSIS.md",
    
    # 表头行修复
    "HEADER_ROW_FIX_V4_10_0.md",
    "HEADER_ROW_FIX.md",
    "HEADER_ROW_AUTO_DETECTION_FIX.md",
    
    # 库存域修复
    "INVENTORY_DOMAIN_COMPLETION_REPORT.md",
    "INVENTORY_DOMAIN_FINAL_COMPLETE.md",
    "INVENTORY_DOMAIN_FINAL_STATUS.md",
    "INVENTORY_DOMAIN_IMPLEMENTATION_SUMMARY.md",
    "INVENTORY_MANAGEMENT_500_ERROR_FIX.md",
    "INVENTORY_VALIDATION_FIX_COMPLETE.md",
    "INVENTORY_VALIDATION_RULE_FIX.md",
    "MIAOSHU_INVENTORY_FILE_NAMING_FIX.md",
    
    # 产品管理修复
    "PRODUCT_MANAGEMENT_FIX_20251105.md",
    "PRODUCT_MANAGEMENT_FIX_REPORT.md",
    "PRODUCT_ISSUES_ANSWER_20251105.md",
    "PRODUCT_IMAGE_STOCK_ISSUE_RESOLUTION.md",
    "PRODUCT_TO_INVENTORY_MANAGEMENT_RENAME.md",
    
    # 字段映射修复
    "FIELD_MAPPING_COMPLETE_SUMMARY_20251105.md",
    "COMPLETE_FIELD_MAPPING_FIX_REPORT.md",
    "FIELD_MAPPING_SIMPLIFICATION_ANALYSIS.md",
    "FIELD_MAPPING_SIMPLIFICATION_COMPLETE.md",
    "FIELD_MAPPING_SIMPLIFICATION_PLAN.md",
    "SKU_PRICE_FIELDS_FIX_COMPLETE.md",
    "SKU_CURRENCY_FIX_REPORT.md",
    "ALL_PINYIN_MAPPINGS_FIXED_SUMMARY.md",
    
    # 双维护修复
    "DOUBLE_MAINTENANCE_COMPLETE_REPORT.md",
    "DOUBLE_MAINTENANCE_FIX_REPORT.md",
    "FINAL_DOUBLE_MAINTENANCE_FIX.md",
    
    # 其他修复
    "COMPLETE_FIX_SUMMARY.md",
    "FINAL_FIX_DATA_IMPORTER.md",
    "ALL_ISSUES_FIXED_SUMMARY.md",
    "API_RESPONSE_FORMAT_FIX_COMPLETE.md",
    "AUDIT_IMPROVEMENTS_COMPLETE_20251105.md",
    
    # 工作总结
    "WORK_SUMMARY_20251109.md",
    "WORK_SUMMARY_20251105.md",
    "WORK_SUMMARY_20251103.md",
    "TODAY_WORK_SUMMARY_20251105.md",
    "TOMORROW_AGENT_GUIDE.md",
    "NEW_CONVERSATION_QUICK_REFERENCE.md",
    
    # 优化报告
    "COMPLETE_OPTIMIZATION_REPORT_20251105.md",
    "OPTIMIZATION_PROGRESS_20251105.md",
    "README_OPTIMIZATION_20251105.md",
    "FINAL_IMPLEMENTATION_REPORT_20251105.md",
    "SYSTEM_AUDIT_REPORT_20251105.md",
    
    # 计划文档
    "PLAN_DOUBLE_MAINTENANCE_AND_VULNERABILITY_CHECK.md",
    "BUSINESS_OVERVIEW_PLAN_FIXED.md",
    "MATERIALIZED_VIEW_IMPLEMENTATION_PLAN.md",
    
    # 数据浏览器（除最终版）
    "DATA_BROWSER_V3_SUMMARY.md",
    "DATA_BROWSER_V3_COMPLETE_REPORT.md",
    "DATA_BROWSER_V3_DEMO_GUIDE.md",
    
    # 数据同步（与CORE_DATA_FLOW重复）
    "BATCH_SYNC_DETAILED_FLOW.md",
    "BATCH_SYNC_ISSUE_ANALYSIS.md",
    "BATCH_SYNC_ISSUE_FIX_REPORT.md",
    "DATA_SYNC_CORE_FLOW.md",
    "SYNC_DATA_CORE_FLOW_ANALYSIS.md",
    "AUTO_SYNC_DATA_INGESTION_FIX.md",
    "MANUAL_VS_AUTO_INGEST_ISSUE.md",
    
    # 架构文档（已包含在FINAL_ARCHITECTURE_STATUS.md）
    "ARCHITECTURE_AUDIT_REPORT_20250130.md",
    "ARCHITECTURE_CLEANUP_COMPLETE.md",
    "ARCHITECTURE_RISK_ASSESSMENT_20251103.md",
    "DEVELOPMENT_RULES_AUDIT_REPORT.md",
    "DOCUMENT_CLEANUP_REPORT_20250130.md",
    
    # 其他专题（已包含在其他文档）
    "ANALYTICS_DOMAIN_EXPLANATION.md",
    "ANALYTICS_TRAFFIC_DUPLICATE_ANALYSIS.md",
    "TRAFFIC_TO_ANALYTICS_MIGRATION_COMPLETE.md",
    "CORE_PROCESS_FLOW_DIAGRAM.md",
    "CHINESE_STANDARD_FIELD_ANALYSIS.md",
    "CURRENCY_FIELDS_DESIGN_PRINCIPLE.md",
    "FOUR_LAYER_MAPPING_ARCHITECTURE.md",
    "FULL_DICTIONARY_SCAN_AND_TRANSLATE.md",
    
    # 用户指南（重复/过时）
    "USER_QUICK_START_GUIDE.md",
    "USER_GUIDE_AUTO_INGEST_v4_5_0.md",
    "USER_GUIDE_REIMPORT.md",
    "NEXT_STEPS_USER_GUIDE.md",
    "URGENT_MIAOSHOU_IMPORT_SOLUTION.md",
    "HOW_TO_CONFIGURE_FILTERS.md",
    
    # 其他文档
    "TODO_CLASSIFICATION.md",
    "PERFORMANCE_OPTIMIZATION_SUGGESTIONS.md",
    "SECURITY_HARDENING_SUGGESTIONS.md",
    "TESTING_IMPROVEMENT_SUGGESTIONS.md",
    "API_VERSIONING_VS_FEATURE_FLAG.md",
    "DIRECTORY_STRUCTURE.md",
    "DATA_INGESTION_BEHAVIOR.md",
    
    # 物化视图相关（除保留的）
    "MATERIALIZED_VIEW_SEMANTIC_SEPARATION.md",
    "ORDER_MATERIALIZED_VIEWS.md",
    "INVENTORY_MANAGEMENT_MATERIALIZED_VIEWS.md",
    
    # 其他
    "WAREHOUSE_SALES_FIELDS_SOLUTION.md",
}

def main():
    """主函数"""
    print("[OK] Starting docs cleanup...")
    print(f"[OK] Docs directory: {DOCS_DIR}")
    print(f"[OK] Archive directory: {ARCHIVE_DIR}")
    
    # 创建归档目录
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    print(f"[OK] Created archive directory: {ARCHIVE_DIR}")
    
    # 统计
    archived_count = 0
    not_found = []
    
    # 归档文件
    for filename in FILES_TO_ARCHIVE:
        src = DOCS_DIR / filename
        dst = ARCHIVE_DIR / filename
        
        if src.exists():
            try:
                shutil.move(str(src), str(dst))
                archived_count += 1
                print(f"[OK] Archived: {filename}")
            except Exception as e:
                print(f"[ERROR] Failed to archive {filename}: {e}")
        else:
            not_found.append(filename)
    
    # 统计保留的文档
    all_md_files = [f for f in DOCS_DIR.iterdir() if f.is_file() and f.suffix == '.md']
    keep_files = CORE_DOCS | VERSION_REPORTS_KEEP | USER_GUIDES_KEEP | OTHER_IMPORTANT
    
    print(f"\n[OK] Cleanup completed!")
    print(f"[OK] Archived: {archived_count} files")
    print(f"[OK] Not found: {len(not_found)} files")
    print(f"[OK] Remaining MD files in docs root: {len(all_md_files)}")
    
    if not_found:
        print(f"\n[INFO] Files not found (may already be archived):")
        for f in not_found[:10]:  # 只显示前10个
            print(f"  - {f}")
        if len(not_found) > 10:
            print(f"  ... and {len(not_found) - 10} more")
    
    print(f"\n[OK] Cleanup script completed successfully!")

if __name__ == "__main__":
    main()

