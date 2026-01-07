#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
账号定制采集模板（妙手ERP）

用法：复制为 <normalized_account_key>.py，例如： miaoshou_erp_18876067809.py
然后在 run.py -> 5. 运行数据采集 时会自动优先加载该定制脚本。

注意：
- 严格使用账号配置的 login_url 作为唯一入口，禁止硬编码或猜测URL。
- 仅保留你用Inspector确认稳定的操作步骤与选择器，必要时删掉多余录制动作。
"""

from typing import Dict, Any
from modules.collectors.miaoshou.playwright_miaoshou_collector import MiaoshouPlaywrightCollector


def collect(account: Dict[str, Any], start_date: str | None = None, end_date: str | None = None) -> Dict[str, Any]:
    """账号定制采集入口

    Args:
        account: 账号信息（包含 username/password/login_url 等）
        start_date: 开始日期 (YYYY-MM-DD)
        end_date: 结束日期 (YYYY-MM-DD)

    Returns:
        采集结果字典，与通用采集器保持一致结构
    """
    config = {
        "headless": False,
        "slow_mo": 100,
        "timeout": 30000,
        "proxy": {},
    }
    collector = MiaoshouPlaywrightCollector(config)

    # 这里可根据录制结果做少量覆盖：
    # 例如：collector.selectors["start_date"] = "input[placeholder='开始日期']"
    #       collector.selectors["end_date"] = "input[placeholder='结束日期']"
    #       在 collector.set_date_range_popup / download_data 内也可以调用自定义的click顺序

    return collector.collect_data(account, start_date=start_date, end_date=end_date)


