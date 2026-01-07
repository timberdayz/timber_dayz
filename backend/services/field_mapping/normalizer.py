#!/usr/bin/env python3
"""
字段映射标准化工具

提供：
- 列名标准化 normalize_column_name()
- 模板匹配键标准化 normalize_template_key()
"""

from __future__ import annotations

import re
from typing import Dict


_FULLWIDTH_MAP = str.maketrans({
    '（': '(', '）': ')', '【': '[', '】': ']', '，': ',', '：': ':', '；': ';', '。': '.', '、': '/', '％': '%',
})


def normalize_column_name(name: str) -> str:
    if not name:
        return ''
    n = str(name).strip()
    n = n.translate(_FULLWIDTH_MAP)
    n = re.sub(r'[\s\t\r\n]+', '', n)  # 去空白
    n = re.sub(r'[\-_/\\]+', '', n)     # 去常见分隔符
    n = n.replace('%', 'pct')
    return n.lower()


def normalize_template_key(payload: Dict) -> Dict:
    """归一化 source_platform/domain/sub_domain/granularity/sheet_name。"""
    def norm(v: str) -> str:
        if v is None:
            return ''
        s = str(v).strip().lower()
        s = s.replace(' ', '').replace('-', '').replace('_', '')
        mapping = {
            'monthly': 'month', 'weekly': 'week', 'daily': 'day',
            'services': 'services', 'orders': 'orders', 'products': 'products', 'analytics': 'analytics',
        }
        return mapping.get(s, s)

    return {
        'source_platform': norm(payload.get('source_platform') or payload.get('platform')),
        'domain': norm(payload.get('domain')),
        'sub_domain': norm(payload.get('sub_domain') or ''),
        'granularity': norm(payload.get('granularity')),
        'sheet_name': norm(payload.get('sheet_name') or ''),
    }


