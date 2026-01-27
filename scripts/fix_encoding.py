#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""修复 c_class_data_validator.py 中的全角字符问题"""

import re
from pathlib import Path

file_path = Path("backend/services/c_class_data_validator.py")

# 读取文件
with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

# 替换全角字符为半角字符
fixed = content.replace('（', '(').replace('）', ')').replace('：', ':')

# 写回文件
with open(file_path, 'w', encoding='utf-8') as f:
    f.write(fixed)

print("[OK] 已修复全角字符")
