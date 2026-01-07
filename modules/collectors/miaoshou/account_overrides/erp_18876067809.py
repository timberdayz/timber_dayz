#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
账号定制采集（xihong）

说明：将Inspector录制后确认稳定的步骤，整合为少量关键操作与选择器，
严格以账号 login_url 为唯一入口，不要硬编码其他URL。

建议仅覆盖：登录后的弹窗关闭、Tab切换、日期设置、导出下载按钮。

生成规则：platform_username -> 小写与下划线，用作文件名。

"""

from typing import Dict, Any
from modules.collectors.miaoshou.playwright_miaoshou_collector import MiaoshouPlaywrightCollector

def collect(account: Dict[str, Any], start_date: str | None = None, end_date: str | None = None) -> Dict[str, Any]:
    config = {
        'headless': False,
        'slow_mo': 120,
        'timeout': 30000,
        'proxy': {},
    }
    collector = MiaoshouPlaywrightCollector(config)

    # 示例：根据你的录制结果，放入更稳的选择器
    # collector.selectors['start_date'] = "input[placeholder='开始日期']"
    # collector.selectors['end_date'] = "input[placeholder='结束日期']"
    # 也可在 collector.set_date_range_popup / download_data 扩展精确点击顺序

    return collector.collect_data(account, start_date=start_date, end_date=end_date)
