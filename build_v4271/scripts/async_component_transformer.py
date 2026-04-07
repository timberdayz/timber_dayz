"""
异步组件转换辅助脚本

此脚本用于辅助将 Python 组件从同步模式转换为异步模式。
注意：此脚本仅做基本转换，复杂的嵌套结构需要手动处理。

使用方法:
    python scripts/async_component_transformer.py [file_path]

转换规则:
1. def run(...) -> async def run(...)
2. page.xxx() -> await page.xxx()
3. locator.xxx() -> await locator.xxx()
4. time.sleep() -> await asyncio.sleep()
5. page.wait_for_timeout() -> await page.wait_for_timeout()
"""

import re
import sys
from pathlib import Path


def transform_to_async(content: str) -> str:
    """将同步 Playwright 代码转换为异步版本"""
    
    # 1. 转换方法签名
    content = re.sub(
        r'(\s+)def (run|_\w+)\(self,',
        r'\1async def \2(self,',
        content
    )
    
    # 2. 转换 Playwright 页面方法调用
    # 注意：这是一个简化的转换，可能需要手动调整
    playwright_methods = [
        'goto', 'wait_for_timeout', 'wait_for_load_state', 'wait_for_selector',
        'wait_for_event', 'fill', 'click', 'press', 'type', 'check', 'uncheck',
        'select_option', 'hover', 'focus', 'blur', 'scroll_into_view_if_needed',
        'screenshot', 'content', 'evaluate', 'wait_for', 'is_visible', 'is_checked',
        'is_enabled', 'is_disabled', 'count', 'get_attribute', 'inner_text',
        'inner_html', 'text_content', 'input_value', 'all_inner_texts',
        'all_text_contents', 'bounding_box', 'dblclick', 'dispatch_event',
        'save_as', 'path', 'expect_download',
    ]
    
    for method in playwright_methods:
        # 匹配 page.method() 或 locator.method() 或 element.method()
        # 仅在非 await 和非 async with 上下文中添加 await
        pattern = rf'(?<!await )(?<!async with )((?:page|loc|locator|el|btn|cb|cont|header|toggle|item|footer|inputs|download)\w*\.{method}\()'
        content = re.sub(pattern, r'await \1', content)
    
    # 3. 转换 time.sleep -> asyncio.sleep
    content = re.sub(
        r'import time as _t',
        'import asyncio\nimport time as _t',
        content
    )
    content = re.sub(r'_t\.sleep\(', 'await asyncio.sleep(', content)
    content = re.sub(r'time\.sleep\(', 'await asyncio.sleep(', content)
    
    # 4. 转换 with page.expect_download -> async with page.expect_download
    content = re.sub(
        r'(\s+)with (page\.expect_download|page\.context\.expect_download)',
        r'\1async with \2',
        content
    )
    
    # 5. 替换 emoji 为 ASCII 符号（Windows 兼容性）
    emoji_replacements = {
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
        '🚀': '[START]',
        '🎉': '[DONE]',
        '…': '...',
    }
    for emoji, ascii_symbol in emoji_replacements.items():
        content = content.replace(emoji, ascii_symbol)
    
    return content


def main():
    if len(sys.argv) < 2:
        print("Usage: python scripts/async_component_transformer.py <file_path>")
        print("\nThis script helps convert synchronous Playwright components to async.")
        print("Note: Manual review is still required after conversion.")
        sys.exit(1)
    
    file_path = Path(sys.argv[1])
    if not file_path.exists():
        print(f"[FAIL] File not found: {file_path}")
        sys.exit(1)
    
    print(f"[INFO] Reading file: {file_path}")
    content = file_path.read_text(encoding='utf-8')
    
    print("[INFO] Applying async transformations...")
    transformed = transform_to_async(content)
    
    # 创建备份
    backup_path = file_path.with_suffix(file_path.suffix + '.bak')
    file_path.rename(backup_path)
    print(f"[INFO] Backup created: {backup_path}")
    
    # 写入转换后的内容
    file_path.write_text(transformed, encoding='utf-8')
    print(f"[OK] Transformed file saved: {file_path}")
    print("\n[WARN] Please review the file manually for:")
    print("  - Nested function calls that need await")
    print("  - Context managers that need 'async with'")
    print("  - Helper method calls that now need await")
    print("  - Any remaining emoji characters")


if __name__ == "__main__":
    main()
