#!/usr/bin/env python3
"""
项目清理脚本 - 清理过期、重复、临时文件
"""

import os
import shutil
from pathlib import Path
from datetime import datetime

class ProjectCleaner:
    def __init__(self, project_root="."):
        self.project_root = Path(project_root)
        self.timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.cleanup_report = []
        
    def log(self, message):
        """记录日志"""
        print(f"[CLEANUP] {message}")
        self.cleanup_report.append(message)
    
    def cleanup_temp_directory(self):
        """清理temp目录"""
        self.log("=" * 60)
        self.log("清理 temp/ 目录")
        self.log("=" * 60)
        
        temp_dir = self.project_root / "temp"
        if not temp_dir.exists():
            self.log("temp/ 目录不存在")
            return
        
        # 需要保留的目录
        keep_dirs = {"outputs", "cache"}
        
        # 需要清理的目录
        cleanup_dirs = {
            "archive": "已归档的开发文件",
            "archived_docs": "已归档的文档",
            "archived_tests": "已归档的测试",
            "backups": "旧备份文件",
            "debug": "调试截图",
            "debug_screenshots": "调试截图",
            "development": "开发测试文件",
            "har": "HAR文件",
            "logs": "旧日志文件",
            "recordings": "录制脚本",
            "test_recordings": "测试录制",
            "screenshots": "截图文件",
            "sessions": "会话文件",
            "test_outputs": "测试输出"
        }
        
        for dir_name, description in cleanup_dirs.items():
            dir_path = temp_dir / dir_name
            if dir_path.exists():
                try:
                    # 移动到archive而不是删除
                    archive_path = temp_dir / "archive" / self.timestamp / dir_name
                    archive_path.parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(dir_path), str(archive_path))
                    self.log(f"✓ 归档 temp/{dir_name}/ ({description})")
                except Exception as e:
                    self.log(f"✗ 归档失败 temp/{dir_name}/: {e}")
        
        # 清理临时Python文件
        temp_py_files = list(temp_dir.glob("*.py"))
        if temp_py_files:
            for file in temp_py_files:
                try:
                    archive_path = temp_dir / "archive" / self.timestamp / file.name
                    archive_path.parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(file), str(archive_path))
                    self.log(f"✓ 归档 {file.name}")
                except Exception as e:
                    self.log(f"✗ 归档失败 {file.name}: {e}")
    
    def cleanup_docs_directory(self):
        """清理docs目录 - 整理重复文档"""
        self.log("\n" + "=" * 60)
        self.log("整理 docs/ 目录")
        self.log("=" * 60)
        
        docs_dir = self.project_root / "docs"
        if not docs_dir.exists():
            self.log("docs/ 目录不存在")
            return
        
        # 核心文档（保留在根目录）
        core_docs = {
            "FINAL_DEVELOPMENT_SUMMARY.md",
            "PROJECT_COMPLETION_REPORT_20251023.md",
            "PRODUCTION_DEPLOYMENT_GUIDE.md",
            "USER_MANUAL.md",
            "ARCHITECTURE_COMPARISON.md",
            "POSTGRESQL_OPTIMIZATION_SUMMARY_20251023.md"
        }
        
        # Phase报告（保留）
        phase_reports = {
            "PHASE3_COMPLETION_REPORT_20251023.md",
            "PHASE4_COMPLETION_REPORT_20251023.md",
            "PHASE5_COMPLETION_REPORT_20251023.md",
            "PHASE6_COMPLETION_REPORT_20251023.md"
        }
        
        # 需要归档的文档模式
        archive_patterns = [
            "PHASE4_DAY1_",
            "PHASE4_PROGRESS_",
            "PHASE4_FINAL_",
            "PHASE4_SUMMARY_",
            "PHASE4_FRONTEND_",
            "PHASE5_PROGRESS_",
            "IMPLEMENTATION_REPORT_",
            "IMPLEMENTATION_STATUS_",
            "FILES_CHANGELOG_",
            "QUICK_START_POSTGRESQL_",
            "DEPLOYMENT_CHECKLIST_",
            "QUICK_REFERENCE_CARD",
            "USER_ACCEPTANCE_GUIDE",
            "FINAL_SUMMARY_FOR_USER",
            "API_USAGE_EXAMPLES",
            "ACCEPTANCE_REPORT_"
        ]
        
        # 归档过期文档
        for md_file in docs_dir.glob("*.md"):
            if md_file.name in core_docs or md_file.name in phase_reports:
                continue
            
            # 检查是否需要归档
            should_archive = any(pattern in md_file.name for pattern in archive_patterns)
            
            if should_archive:
                try:
                    archive_path = docs_dir / "archive" / "2025_01" / md_file.name
                    archive_path.parent.mkdir(parents=True, exist_ok=True)
                    if not archive_path.exists():
                        shutil.move(str(md_file), str(archive_path))
                        self.log(f"✓ 归档 docs/{md_file.name}")
                except Exception as e:
                    self.log(f"✗ 归档失败 {md_file.name}: {e}")
    
    def cleanup_backend_tests(self):
        """清理backend/tests目录 - 保留核心测试文件"""
        self.log("\n" + "=" * 60)
        self.log("检查 backend/tests/ 目录")
        self.log("=" * 60)
        
        tests_dir = self.project_root / "backend" / "tests"
        if not tests_dir.exists():
            self.log("backend/tests/ 目录不存在")
            return
        
        # 核心测试文件（保留）
        core_tests = {
            "concurrent_test.py",
            "batch_import_test.py",
            "stability_test.py",
            "__init__.py"
        }
        
        test_files = list(tests_dir.glob("*.py"))
        self.log(f"检查 {len(test_files)} 个测试文件")
        
        for test_file in test_files:
            if test_file.name not in core_tests:
                try:
                    archive_path = self.project_root / "temp" / "archive" / self.timestamp / "old_tests" / test_file.name
                    archive_path.parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(test_file), str(archive_path))
                    self.log(f"✓ 归档测试文件 {test_file.name}")
                except Exception as e:
                    self.log(f"✗ 归档失败 {test_file.name}: {e}")
    
    def cleanup_root_directory(self):
        """清理项目根目录 - 移除过时启动脚本"""
        self.log("\n" + "=" * 60)
        self.log("检查项目根目录")
        self.log("=" * 60)
        
        # 需要归档的根目录文件
        archive_files = [
            "start_backend.py",
            "start_frontend.py",
            "start_erp.py"
        ]
        
        for filename in archive_files:
            file_path = self.project_root / filename
            if file_path.exists():
                try:
                    archive_path = self.project_root / "temp" / "archive" / self.timestamp / filename
                    archive_path.parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(file_path), str(archive_path))
                    self.log(f"✓ 归档根目录文件 {filename} (已被run.py替代)")
                except Exception as e:
                    self.log(f"✗ 归档失败 {filename}: {e}")
    
    def generate_report(self):
        """生成清理报告"""
        self.log("\n" + "=" * 60)
        self.log("生成清理报告")
        self.log("=" * 60)
        
        report_path = self.project_root / "temp" / f"cleanup_report_{self.timestamp}.txt"
        report_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(f"项目清理报告\n")
            f.write(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"=" * 60 + "\n\n")
            for line in self.cleanup_report:
                f.write(f"{line}\n")
        
        self.log(f"清理报告已保存到: {report_path}")
        return report_path
    
    def run(self):
        """运行清理流程"""
        self.log(f"\n{'='*60}")
        self.log(f"西虹ERP系统 - 项目清理工具")
        self.log(f"开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        self.log(f"{'='*60}\n")
        
        # 执行清理
        self.cleanup_temp_directory()
        self.cleanup_docs_directory()
        self.cleanup_backend_tests()
        self.cleanup_root_directory()
        
        # 生成报告
        report_path = self.generate_report()
        
        self.log(f"\n{'='*60}")
        self.log(f"清理完成！")
        self.log(f"{'='*60}\n")
        
        return report_path

def main():
    """主函数"""
    print("西虹ERP系统 - 项目清理工具")
    print("=" * 60)
    print("此工具将清理以下内容：")
    print("1. temp/ 目录中的临时文件和旧备份")
    print("2. docs/ 目录中的重复和过期文档")
    print("3. backend/tests/ 中的旧测试文件")
    print("4. 项目根目录中的过时启动脚本")
    print("\n所有文件将被归档而不是删除。")
    print("=" * 60)
    
    response = input("\n确认开始清理？(yes/no): ")
    if response.lower() != 'yes':
        print("清理已取消")
        return
    
    cleaner = ProjectCleaner()
    report_path = cleaner.run()
    
    print(f"\n查看详细报告: {report_path}")

if __name__ == "__main__":
    main()
