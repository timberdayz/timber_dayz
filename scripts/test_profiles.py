#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""快速测试 profiles 配置"""

with open('docker-compose.prod.yml', 'r', encoding='utf-8') as f:
    content = f.read()

services = ['backend', 'frontend', 'nginx', 'celery-worker', 'celery-beat']

for service in services:
    pattern = f"  {service}:"
    if pattern in content:
        start = content.find(pattern)
        # 查找下一个服务或文件结束
        next_start = content.find("\n  ", start + len(pattern))
        if next_start == -1:
            next_start = len(content)
        
        block = content[start:next_start]
        has_profiles = "profiles:" in block
        print(f"{service}: {'[OK]' if has_profiles else '[FAIL]'} profiles={'存在' if has_profiles else '缺失'}")
        
        if has_profiles:
            # 显示 profiles 内容
            profiles_start = block.find("profiles:")
            if profiles_start != -1:
                profiles_end = block.find("\n\n", profiles_start)
                if profiles_end == -1:
                    profiles_end = profiles_start + 100
                print(f"  内容: {block[profiles_start:profiles_end].strip()}")
    else:
        print(f"{service}: [FAIL] 服务未找到")
