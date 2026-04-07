#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
修复 .env 文件中的 Redis 配置格式
"""

import re
from pathlib import Path

env_file = Path('.env')
if not env_file.exists():
    print("[ERROR] .env 文件不存在")
    exit(1)

# 读取文件（尝试多种编码）
encodings = ['utf-8', 'gbk', 'utf-8-sig', 'latin-1']
content = None
for encoding in encodings:
    try:
        with open(env_file, 'r', encoding=encoding) as f:
            content = f.read()
        break
    except UnicodeDecodeError:
        continue

if content is None:
    print("[ERROR] 无法读取 .env 文件（编码问题）")
    exit(1)

# 修复方式2的注释格式
# 查找包含 `n 的行并修复
lines = content.split('\n')
new_lines = []
fixed = False

i = 0
while i < len(lines):
    line = lines[i]
    # 查找包含方式2注释且有 `n 转义字符的行
    if '方式2：使用独立配置项' in line and '`n' in line:
        # 替换为正确的多行格式
        new_lines.append('# 方式2：使用独立配置项（如果未设置 REDIS_URL，将自动构建）')
        new_lines.append('# REDIS_HOST=localhost')
        new_lines.append('# REDIS_PORT=6379')
        new_lines.append('# REDIS_PASSWORD=your_redis_password')
        new_lines.append('# REDIS_DB=0')
        fixed = True
        # 跳过后续的 REDIS_ 相关行（它们已经在上面添加了）
        i += 1
        while i < len(lines) and ('REDIS_HOST' in lines[i] or 'REDIS_PORT' in lines[i] or 'REDIS_PASSWORD' in lines[i] or 'REDIS_DB' in lines[i]):
            i += 1
    elif '方式2：使用独立配置项' in line:
        # 如果方式2行存在但没有 `n，检查下一行
        new_lines.append(line)
        i += 1
        # 如果下一行是 REDIS_HOST，说明格式可能已经正确，直接添加
        if i < len(lines) and 'REDIS_HOST' in lines[i]:
            new_lines.append(lines[i])
            i += 1
            if i < len(lines) and 'REDIS_PORT' in lines[i]:
                new_lines.append(lines[i])
                i += 1
            if i < len(lines) and 'REDIS_PASSWORD' in lines[i]:
                new_lines.append(lines[i])
                i += 1
            if i < len(lines) and 'REDIS_DB' in lines[i]:
                new_lines.append(lines[i])
                i += 1
    else:
        new_lines.append(line)
        i += 1

if fixed:
    content = '\n'.join(new_lines)
    # 使用与读取时相同的编码写入
    with open(env_file, 'w', encoding='utf-8', newline='') as f:
        f.write(content)
    print("[OK] 已修复 .env 文件中的 Redis 配置格式")
else:
    print("[INFO] 未找到需要修复的内容，或已修复")

