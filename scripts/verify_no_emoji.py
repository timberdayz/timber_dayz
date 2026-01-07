"""
验证脚本：检查代码中是否存在 emoji 字符

Windows 控制台默认使用 GBK 编码，无法正确显示 emoji 字符，
会导致 UnicodeEncodeError 异常。此脚本用于检测并报告需要修复的文件。

使用方法:
    python scripts/verify_no_emoji.py [--fix]
    
    --fix: 自动替换检测到的 emoji 为 ASCII 符号
"""

import re
import sys
from pathlib import Path


# Emoji 到 ASCII 的替换映射
EMOJI_REPLACEMENTS = {
    '✅': '[OK]',
    '❌': '[FAIL]',
    '⚠️': '[WARN]',
    '✓': '[OK]',
    '✗': '[FAIL]',
    '🔎': '[SEARCH]',
    '↪': '->',
    '▶': '[START]',
    '➜': '->',
    '⏩': '[FAST]',
    '🏬': '[SHOP]',
    '🔍': '[SEARCH]',
    '📅': '[DATE]',
    '⏱️': '[TIME]',
    '⏱': '[TIME]',
    '🚀': '[START]',
    '🎉': '[DONE]',
    '…': '...',
    '👉': '->',
    '👈': '<-',
    '📊': '[DATA]',
    '🔄': '[RETRY]',
    '📝': '[NOTE]',
    '💡': '[TIP]',
    '⚡': '[FLASH]',
    '🔧': '[TOOL]',
    '📁': '[DIR]',
    '📂': '[FOLDER]',
    '✨': '[NEW]',
    '🎯': '[TARGET]',
    '📌': '[PIN]',
    '🔗': '[LINK]',
    '⬆️': '[UP]',
    '⬇️': '[DOWN]',
    '➡️': '[RIGHT]',
    '⬅️': '[LEFT]',
}

# Emoji 检测正则表达式
# 匹配常见的 emoji 字符范围
EMOJI_PATTERN = re.compile(
    "["
    "\U0001F600-\U0001F64F"  # 表情
    "\U0001F300-\U0001F5FF"  # 符号和图标
    "\U0001F680-\U0001F6FF"  # 交通和地图
    "\U0001F1E0-\U0001F1FF"  # 旗帜
    "\U00002702-\U000027B0"  # 杂项符号
    "\U0001F900-\U0001F9FF"  # 补充符号
    "\U00002600-\U000026FF"  # 杂项符号
    "\U00002B50-\U00002B55"  # 星星
    "\u2700-\u27BF"          # 装饰符号
    "\u2190-\u21FF"          # 箭头
    "\u2300-\u23FF"          # 技术符号
    "\u25A0-\u25FF"          # 几何形状
    "\u2600-\u26FF"          # 杂项符号
    "\u2700-\u27BF"          # 装饰符号
    "\u2900-\u297F"          # 补充箭头
    "\u231A-\u231B"          # 时钟
    "\u23E9-\u23F3"          # 媒体控制
    "\u23F8-\u23FA"          # 媒体控制
    "\u25AA-\u25AB"          # 方形
    "\u25B6\u25C0"           # 播放
    "\u25FB-\u25FE"          # 方形
    "\u2600-\u2604"          # 天气
    "\u260E\u2611"           # 电话、复选框
    "\u2614-\u2615"          # 雨伞、咖啡
    "\u2618\u261D"           # 植物、手指
    "\u2620\u2622-\u2623"    # 骷髅、辐射
    "\u2626\u262A"           # 宗教
    "\u262E-\u262F"          # 和平
    "\u2638-\u263A"          # 表情
    "\u2640\u2642"           # 性别
    "\u2648-\u2653"          # 星座
    "\u2660\u2663\u2665-\u2666"  # 扑克牌
    "\u2668\u267B\u267F"     # 温泉、回收、残疾
    "\u2692-\u2694\u2696-\u2697"  # 工具
    "\u2699\u269B-\u269C"    # 齿轮
    "\u26A0-\u26A1"          # 警告、闪电
    "\u26AA-\u26AB"          # 圆圈
    "\u26B0-\u26B1"          # 棺材
    "\u26BD-\u26BE"          # 运动
    "\u26C4-\u26C5"          # 天气
    "\u26CE\u26CF"           # 星座、工具
    "\u26D1\u26D3-\u26D4"    # 头盔、禁止
    "\u26E9-\u26EA"          # 建筑
    "\u26F0-\u26F5"          # 交通
    "\u26F7-\u26FA"          # 活动
    "\u26FD"                 # 加油站
    "✅✓✗❌⚠️🔎▶➜⏩🏬📅⏱️🚀🎉"
    "…"
    "]+"
)


def find_emoji_in_file(file_path: Path) -> list[tuple[int, str, str]]:
    """在文件中查找 emoji 字符
    
    Returns:
        List of (line_number, line_content, matched_emoji)
    """
    results = []
    try:
        content = file_path.read_text(encoding='utf-8')
        for i, line in enumerate(content.split('\n'), 1):
            # 检查已知 emoji
            for emoji in EMOJI_REPLACEMENTS:
                if emoji in line:
                    results.append((i, line.strip()[:100], emoji))
            # 检查其他 emoji
            matches = EMOJI_PATTERN.findall(line)
            for match in matches:
                if match not in EMOJI_REPLACEMENTS:
                    results.append((i, line.strip()[:100], match))
    except Exception as e:
        print(f"[WARN] Cannot read {file_path}: {e}")
    return results


def fix_emoji_in_file(file_path: Path) -> int:
    """替换文件中的 emoji 字符
    
    Returns:
        替换的数量
    """
    try:
        content = file_path.read_text(encoding='utf-8')
        original = content
        
        for emoji, replacement in EMOJI_REPLACEMENTS.items():
            content = content.replace(emoji, replacement)
        
        if content != original:
            file_path.write_text(content, encoding='utf-8')
            return len([e for e in EMOJI_REPLACEMENTS if e in original])
        return 0
    except Exception as e:
        print(f"[FAIL] Cannot fix {file_path}: {e}")
        return 0


def main():
    fix_mode = '--fix' in sys.argv
    
    # 扫描目录
    scan_dirs = ['modules', 'backend', 'tools']
    exclude_patterns = ['node_modules', '__pycache__', '.git', 'venv', '.venv', 'backups']
    
    total_files = 0
    files_with_emoji = 0
    total_fixes = 0
    
    print("=" * 60)
    print("Emoji 检测验证脚本")
    print("=" * 60)
    
    for scan_dir in scan_dirs:
        scan_path = Path(scan_dir)
        if not scan_path.exists():
            continue
            
        for file_path in scan_path.rglob('*.py'):
            # 跳过排除的目录
            if any(p in str(file_path) for p in exclude_patterns):
                continue
            
            total_files += 1
            results = find_emoji_in_file(file_path)
            
            if results:
                files_with_emoji += 1
                print(f"\n[WARN] {file_path}")
                for line_num, line_content, emoji in results[:5]:  # 只显示前5个
                    # 将 emoji 转换为 Unicode 码点表示，避免 GBK 编码错误
                    emoji_repr = emoji.encode('unicode-escape').decode('ascii')
                    line_safe = line_content[:60].encode('ascii', 'replace').decode('ascii')
                    print(f"  L{line_num}: {emoji_repr} -> {line_safe}...")
                
                if fix_mode:
                    fixed = fix_emoji_in_file(file_path)
                    total_fixes += fixed
                    print(f"  [OK] Fixed {fixed} emoji(s)")
    
    print("\n" + "=" * 60)
    print(f"扫描完成: {total_files} 文件")
    print(f"包含 Emoji 的文件: {files_with_emoji}")
    
    if fix_mode:
        print(f"已修复: {total_fixes} 处")
    else:
        if files_with_emoji > 0:
            print(f"\n[TIP] 运行 'python scripts/verify_no_emoji.py --fix' 自动修复")
    
    # 返回状态码
    if files_with_emoji > 0 and not fix_mode:
        print("\n[FAIL] 检测到 emoji 字符，可能导致 Windows 编码错误")
        sys.exit(1)
    else:
        print("\n[OK] 验证通过")
        sys.exit(0)


if __name__ == "__main__":
    main()
