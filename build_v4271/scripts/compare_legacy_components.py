"""
对比 legacy_components 与 modules/platforms 中的组件差异

用途：
- 识别哪些文件完全相同（无需迁移）
- 识别哪些文件有差异（需要合并或覆盖）
- 识别哪些文件只在 legacy 中存在（需要新增）
- 识别哪些文件只在 target 中存在（需要保留）
"""

import difflib
import json
from pathlib import Path
from typing import Dict, List, Any


LEGACY_DIR = Path("migration_temp/legacy_components/modules/platforms")
TARGET_DIR = Path("modules/platforms")


def compare_file_content(legacy_file: Path, target_file: Path) -> Dict[str, Any]:
    """对比两个文件的内容"""
    try:
        legacy_content = legacy_file.read_text(encoding="utf-8")
        target_content = target_file.read_text(encoding="utf-8")
        
        if legacy_content == target_content:
            return {
                "status": "identical",
                "similarity": 1.0,
                "legacy_lines": len(legacy_content.splitlines()),
                "target_lines": len(target_content.splitlines()),
            }
        else:
            # 计算相似度
            ratio = difflib.SequenceMatcher(None, legacy_content, target_content).ratio()
            
            # 计算差异行数（粗略）
            legacy_lines = legacy_content.splitlines()
            target_lines = target_content.splitlines()
            
            # 生成差异摘要
            diff = list(difflib.unified_diff(
                legacy_lines,
                target_lines,
                fromfile=str(legacy_file),
                tofile=str(target_file),
                lineterm="",
                n=3
            ))
            
            return {
                "status": "different",
                "similarity": round(ratio, 3),
                "legacy_lines": len(legacy_lines),
                "target_lines": len(target_lines),
                "diff_summary": diff[:50],  # 只保留前50行差异
                "diff_line_count": len(diff),
            }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
        }


def compare_components() -> Dict[str, Any]:
    """对比所有组件文件"""
    results = {
        "identical": [],  # 完全相同的文件
        "different": [],  # 有差异的文件
        "legacy_only": [],  # 只在 legacy 中存在的文件
        "target_only": [],  # 只在 target 中存在的文件
        "errors": [],  # 对比过程中的错误
    }
    
    platforms = ["shopee", "tiktok", "miaoshou"]
    
    for platform in platforms:
        legacy_platform_dir = LEGACY_DIR / platform / "components"
        target_platform_dir = TARGET_DIR / platform / "components"
        
        if not legacy_platform_dir.exists():
            results["errors"].append(f"Legacy platform dir not found: {legacy_platform_dir}")
            continue
        
        if not target_platform_dir.exists():
            results["errors"].append(f"Target platform dir not found: {target_platform_dir}")
            continue
        
        # 获取所有 Python 文件
        legacy_files = {f.name: f for f in legacy_platform_dir.glob("*.py")}
        target_files = {f.name: f for f in target_platform_dir.glob("*.py")}
        
        # 对比共同文件
        common_files = set(legacy_files.keys()) & set(target_files.keys())
        for filename in common_files:
            legacy_file = legacy_files[filename]
            target_file = target_files[filename]
            
            comparison = compare_file_content(legacy_file, target_file)
            comparison["platform"] = platform
            comparison["file"] = filename
            try:
                comparison["legacy_path"] = str(legacy_file.relative_to(Path.cwd()))
            except ValueError:
                comparison["legacy_path"] = str(legacy_file)
            try:
                comparison["target_path"] = str(target_file.relative_to(Path.cwd()))
            except ValueError:
                comparison["target_path"] = str(target_file)
            
            if comparison["status"] == "identical":
                results["identical"].append({
                    "platform": platform,
                    "file": filename,
                    "lines": comparison["legacy_lines"],
                })
            elif comparison["status"] == "different":
                results["different"].append(comparison)
            else:
                results["errors"].append(f"Error comparing {platform}/{filename}: {comparison.get('error', 'Unknown error')}")
        
        # 只在 legacy 中存在的文件
        legacy_only = set(legacy_files.keys()) - set(target_files.keys())
        for filename in legacy_only:
            legacy_path = legacy_files[filename]
            try:
                path_str = str(legacy_path.relative_to(Path.cwd()))
            except ValueError:
                path_str = str(legacy_path)
            results["legacy_only"].append({
                "platform": platform,
                "file": filename,
                "path": path_str,
                "lines": len(legacy_path.read_text(encoding="utf-8").splitlines()),
            })
        
        # 只在 target 中存在的文件
        target_only = set(target_files.keys()) - set(legacy_files.keys())
        for filename in target_only:
            target_path = target_files[filename]
            try:
                path_str = str(target_path.relative_to(Path.cwd()))
            except ValueError:
                path_str = str(target_path)
            results["target_only"].append({
                "platform": platform,
                "file": filename,
                "path": path_str,
                "lines": len(target_path.read_text(encoding="utf-8").splitlines()),
            })
    
    return results


def print_summary(results: Dict[str, Any]) -> None:
    """打印对比结果摘要"""
    print("=" * 80)
    print("组件差异对比结果摘要")
    print("=" * 80)
    print()
    
    print(f"[STAT] 统计信息:")
    print(f"  - 完全相同文件: {len(results['identical'])} 个")
    print(f"  - 有差异文件: {len(results['different'])} 个")
    print(f"  - 仅在 legacy 中: {len(results['legacy_only'])} 个")
    print(f"  - 仅在 target 中: {len(results['target_only'])} 个")
    print(f"  - 对比错误: {len(results['errors'])} 个")
    print()
    
    if results['identical']:
        print("[OK] 完全相同的文件（无需迁移）:")
        for item in sorted(results['identical'], key=lambda x: (x['platform'], x['file'])):
            print(f"  - {item['platform']}/{item['file']} ({item['lines']} 行)")
        print()
    
    if results['different']:
        print("[DIFF] 有差异的文件（需要检查）:")
        # 按相似度排序
        sorted_diff = sorted(results['different'], key=lambda x: x['similarity'])
        for item in sorted_diff:
            print(f"  - {item['platform']}/{item['file']}")
            print(f"    相似度: {item['similarity']:.1%}")
            print(f"    Legacy: {item['legacy_lines']} 行, Target: {item['target_lines']} 行")
            print(f"    差异行数: {item.get('diff_line_count', 0)}")
        print()
    
    if results['legacy_only']:
        print("[NEW] 仅在 legacy 中存在的文件（可能需要迁移）:")
        for item in sorted(results['legacy_only'], key=lambda x: (x['platform'], x['file'])):
            print(f"  - {item['platform']}/{item['file']} ({item['lines']} 行)")
            print(f"    路径: {item['path']}")
        print()
    
    if results['target_only']:
        print("[KEEP] 仅在 target 中存在的文件（保留现有版本）:")
        for item in sorted(results['target_only'], key=lambda x: (x['platform'], x['file'])):
            print(f"  - {item['platform']}/{item['file']} ({item['lines']} 行)")
            print(f"    路径: {item['path']}")
        print()
    
    if results['errors']:
        print("[ERROR] 对比过程中的错误:")
        for error in results['errors']:
            print(f"  - {error}")
        print()


def save_detailed_report(results: Dict[str, Any], output_file: str = "scripts/component_comparison_report.json") -> None:
    """保存详细报告到 JSON 文件"""
    output_path = Path(output_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    
    print(f"[INFO] 详细报告已保存到: {output_path}")
    print()


if __name__ == "__main__":
    print("开始对比组件文件...")
    print()
    
    results = compare_components()
    
    print_summary(results)
    
    save_detailed_report(results)
    
    print("=" * 80)
    print("对比完成！")
    print("=" * 80)

