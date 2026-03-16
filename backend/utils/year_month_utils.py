"""
年月参数规范化工具

兼容输入：
- YYYY-MM
- YYYY-MM-DD（会截断为 YYYY-MM）
"""

from datetime import date, datetime


def normalize_year_month(value: str) -> str:
    """规范化年月字符串为 YYYY-MM。"""
    if not isinstance(value, str):
        raise ValueError("月份格式须为 YYYY-MM")

    s = value.strip()
    if len(s) >= 10 and s[4] == "-" and s[7] == "-":
        s = s[:7]

    try:
        datetime.strptime(s, "%Y-%m")
    except ValueError as exc:
        raise ValueError("月份格式须为 YYYY-MM") from exc
    return s


def year_month_to_first_day(value: str) -> date:
    """将 YYYY-MM / YYYY-MM-DD 转为当月 1 日 date。"""
    ym = normalize_year_month(value)
    return datetime.strptime(ym, "%Y-%m").date().replace(day=1)
