#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Dashboard 缓存验证脚本

用法:
  1. 确保 Redis 和后端均已启动（Docker 模式: docker-compose 需包含 redis）
  2. python scripts/test_dashboard_cache.py
  3. 观察输出：
     - 第一次 X-Cache: MISS，后续应为 HIT
     - 首次 ~700ms，后续 ~10-50ms（明显加速）

若 X-Cache 一直为 BYPASS:
  - Redis 未连接或 cache_service 未初始化
  - Docker 模式: 确认 redis 容器运行中，backend 能连 redis:6379
  - 本地模式: 确认 Redis 在 localhost:6379，REDIS_URL 正确
"""

import time
import sys
import os
from pathlib import Path

# 添加项目根目录到 path
root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root))


def safe_print(text):
    try:
        print(text, flush=True)
    except UnicodeEncodeError:
        print(text.encode("utf-8", errors="ignore").decode("utf-8", errors="ignore"), flush=True)


try:
    import requests
except ImportError:
    safe_print("请安装: pip install requests")
    sys.exit(1)

# 默认 API 地址（与 run.py 后端端口一致）
BASE_URL = os.getenv("API_BASE_URL", "http://127.0.0.1:8001")
KPI_URL = f"{BASE_URL}/api/dashboard/business-overview/kpi"

# 需要 token 时: export DASHBOARD_TEST_TOKEN=xxx 或取消下一行
HEADERS = {}
_token = os.getenv("DASHBOARD_TEST_TOKEN")
if _token:
    HEADERS["Authorization"] = f"Bearer {_token}"


def check_redis_from_health():
    """尝试从 /health 判断 Redis 状态（若有）"""
    try:
        r = requests.get(f"{BASE_URL}/health", timeout=5)
        if r.status_code == 200:
            d = r.json()
            if "redis" in str(d).lower() or "cache" in str(d).lower():
                return d
    except Exception:
        pass
    return None


def test_kpi_cache(rounds: int = 5, month: str = "2025-01"):
    """多次请求 KPI 接口，验证缓存命中与耗时"""
    safe_print(f"\n[*] KPI 缓存测试: {rounds} 次请求, month={month}")
    safe_print("-" * 55)

    times_ms = []
    cache_statuses = []

    for i in range(rounds):
        start = time.perf_counter()
        try:
            r = requests.get(KPI_URL, params={"month": month}, headers=HEADERS, timeout=30)
        except requests.exceptions.ConnectionError:
            safe_print(f"[ERROR] 无法连接 {KPI_URL}，请确认后端已启动")
            return
        except Exception as e:
            safe_print(f"[ERROR] 请求失败: {e}")
            return
        elapsed_ms = (time.perf_counter() - start) * 1000
        times_ms.append(elapsed_ms)

        cache = r.headers.get("X-Cache", "(无)")
        cache_statuses.append(cache)

        status_icon = "[HIT]" if cache == "HIT" else "[MISS]" if cache == "MISS" else "[BYPASS]"
        safe_print(f"  第{i+1}次: {elapsed_ms:>8.1f} ms  X-Cache: {cache:<6} {status_icon}")

    safe_print("-" * 55)
    if cache_statuses[0] == "BYPASS":
        safe_print("[!] X-Cache=BYPASS: Redis 未启用，缓存未生效")
        safe_print("    处理: 1) 启动 Redis  2) 重启后端  3) Docker 模式确认 redis 服务已启动")
    elif cache_statuses[0] == "MISS" and all(s == "HIT" for s in cache_statuses[1:]):
        avg_miss = times_ms[0]
        avg_hit = sum(times_ms[1:]) / max(1, len(times_ms) - 1)
        safe_print(f"[OK] 缓存正常: 首次 {avg_miss:.0f}ms, 后续平均 {avg_hit:.0f}ms")
        if avg_miss > avg_hit * 1.2:
            safe_print(f"     加速约 {avg_miss/avg_hit:.1f}x")
    elif cache_statuses[0] == "MISS":
        safe_print("[?] 首次 MISS 正常，但后续未全部 HIT，请检查请求参数是否一致")
    else:
        safe_print(f"[?] 缓存状态: {cache_statuses}")


if __name__ == "__main__":
    url = os.getenv("API_BASE_URL", BASE_URL)
    if url != BASE_URL:
        globals()["BASE_URL"] = url
        globals()["KPI_URL"] = f"{url}/api/dashboard/business-overview/kpi"
    test_kpi_cache()
