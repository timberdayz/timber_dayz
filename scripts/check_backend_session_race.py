"""运行期巡检：扫后端日志里的「数据库会话并发冲突」异常。

为什么静态守卫还不够
------------------
``scripts/check_async_session_concurrency.py`` 只能看**本文件里**的写法。
跨模块传递的会话、藏在方法内部的共享 session、第三方封装 —— 这些静态看不见。

这一层是**运行期**兜底：不管错误从哪来，只要后端日志里出现
SQLAlchemy 的会话并发异常特征，就把它捞出来报警。

特征串（SQLAlchemy 2.x）::

    IllegalStateChangeError: Method 'close()' can't be called here;
      method 'commit()' is already in progress
    InvalidRequestError: Method 'execute()' can't be called here;
      method 'commit()' is already in progress

用法::

    python scripts/check_backend_session_race.py              # 报告 + 非零退出
    python scripts/check_backend_session_race.py --hours 24   # 只看最近 24 小时
"""

from __future__ import annotations

import argparse
import io
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
LOG_DIR = REPO_ROOT / "temp" / "logs"
MAIN_LOG = LOG_DIR / "backend_main.log"
PERF_LOG = LOG_DIR / "backend_middleware_performance_logging.log"

# 会话并发冲突的特征
RACE_PATTERNS = (
    re.compile(
        r"Method '(close|execute|commit|rollback|flush|refresh)\(\)' can't be called here"
    ),
    re.compile(r"is already in progress"),
    re.compile(r"IllegalStateChangeError"),
)

TIMESTAMP_RE = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})")


def _parse_ts(line: str) -> datetime | None:
    match = TIMESTAMP_RE.match(line)
    if not match:
        return None
    try:
        return datetime.strptime(match.group(1), "%Y-%m-%d %H:%M:%S").replace(
            tzinfo=timezone.utc
        )
    except ValueError:
        return None


def _scan_file(path: Path, since: datetime | None) -> list[tuple[str, int, str]]:
    """只报**事件行**（带时间戳的日志行），traceback 碎片不单独报。

    一次事故会在日志里留下几十行 traceback，按事件行计数才是「发生了几次」。
    """
    if not path.exists():
        return []
    hits: list[tuple[str, int, str]] = []
    with io.open(path, encoding="utf-8", errors="replace") as handle:
        for lineno, line in enumerate(handle, start=1):
            stamp = _parse_ts(line)
            if stamp is None:
                continue  # traceback 片段 / 续行，不是事件
            if since is not None and stamp < since:
                continue
            if any(pattern.search(line) for pattern in RACE_PATTERNS):
                hits.append((path.name, lineno, line.rstrip()))
    return hits


def main() -> int:
    parser = argparse.ArgumentParser(description="巡检后端日志里的数据库会话并发冲突")
    parser.add_argument("--hours", type=int, default=None, help="只看最近 N 小时")
    args = parser.parse_args()

    since = None
    if args.hours:
        since = datetime.now(timezone.utc) - timedelta(hours=args.hours)

    hits: list[tuple[str, int, str]] = []
    for path in (MAIN_LOG, PERF_LOG):
        hits.extend(_scan_file(path, since))

    if not hits:
        print("✅ 未发现数据库会话并发冲突")
        return 0

    print(f"❌ 发现 {len(hits)} 处数据库会话并发冲突：")
    for name, lineno, line in hits:
        print(f"  {name}:{lineno} {line[:240]}")
    print()
    print(
        "这类异常说明同一个 AsyncSession 被多个协程并发使用 → "
        "接口会 500、页面上的数据会整片变成 --。\n"
        "排查命令：python scripts/check_async_session_concurrency.py"
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
