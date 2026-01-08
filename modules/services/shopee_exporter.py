#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Shopee 商品数据导出服务
======================

基于 HAR 解析结果，实现参数化的 Shopee 商品表现数据导出：
- 支持按周导出
- 自动处理 export -> report_id -> download 流程
- 复用持久化登录态，直连 API
"""

import json
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Optional, Tuple

import requests
from modules.utils.logger import logger


class ShopeeExporter:
    """Shopee 商品数据导出器"""

    def __init__(self, session_cookies: Optional[Dict] = None):
        """
        初始化导出器
        
        Args:
            session_cookies: 可选的会话 cookies，如果不提供将尝试从持久化会话加载
        """
        self.session = requests.Session()
        self.base_url = "https://seller.shopee.cn"
        
        # 设置通用请求头
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'Referer': 'https://seller.shopee.cn/',
        })
        
        if session_cookies:
            self.session.cookies.update(session_cookies)

    def export_product_performance_weekly(
        self, 
        shop_id: str, 
        start_date: str, 
        end_date: str,
        output_dir: Path = None
    ) -> Tuple[bool, str, Optional[Path]]:
        """
        导出商品表现数据（按周）
        
        Args:
            shop_id: 店铺ID (cnsc_shop_id)
            start_date: 开始日期 YYYY-MM-DD
            end_date: 结束日期 YYYY-MM-DD  
            output_dir: 输出目录，默认 temp/outputs
            
        Returns:
            (成功标志, 消息, 文件路径)
        """
        if not output_dir:
            output_dir = Path("temp/outputs")
            output_dir.mkdir(parents=True, exist_ok=True)
            
        try:
            # 转换日期为时间戳
            start_ts = int(datetime.strptime(start_date, "%Y-%m-%d").timestamp())
            end_ts = int(datetime.strptime(end_date, "%Y-%m-%d").timestamp())
            
            logger.info(f"开始导出 Shopee 商品数据: shop_id={shop_id}, {start_date} ~ {end_date}")
            
            # 1. 调用导出接口
            export_url = f"{self.base_url}/api/mydata/cnsc/shop/v2/product/performance/export/"
            export_params = {
                'start_ts': start_ts,
                'end_ts': end_ts,
                'period': 'week',
                'sort_by': '',
                'SPC_CDS': self._get_spc_cds(),
                'SPC_CDS_VER': '2',
                'cnsc_shop_id': shop_id,
                'cbsc_shop_region': 'sg'  # 默认新加坡，可根据需要调整
            }
            
            logger.info(f"调用导出接口: {export_url}")
            export_resp = self.session.get(export_url, params=export_params, timeout=30)
            export_resp.raise_for_status()
            
            export_data = export_resp.json()
            if export_data.get('code') != 0:
                return False, f"导出请求失败: {export_data.get('message', '未知错误')}", None
                
            report_id = export_data.get('data', {}).get('report_id')
            if not report_id:
                return False, "未获取到 report_id", None
                
            logger.info(f"导出请求成功，report_id: {report_id}")
            
            # 2. 轮询下载接口
            download_url = f"{self.base_url}/api/v3/settings/download_report/"
            download_params = {
                'SPC_CDS': self._get_spc_cds(),
                'SPC_CDS_VER': '2',
                'report_id': report_id,
                'cnsc_shop_id': shop_id,
                'cbsc_shop_region': 'sg'
            }
            
            max_attempts = 30  # 最多等待5分钟
            for attempt in range(max_attempts):
                logger.info(f"检查报告状态 ({attempt + 1}/{max_attempts})")
                
                download_resp = self.session.get(download_url, params=download_params, timeout=30)
                download_resp.raise_for_status()
                
                download_data = download_resp.json()
                if download_data.get('code') != 0:
                    logger.warning(f"下载检查失败: {download_data.get('message')}")
                    time.sleep(10)
                    continue
                    
                report_info = download_data.get('data', {})
                status = report_info.get('status')
                download_link = report_info.get('download_link')
                
                if status == 2 and download_link:  # 状态2表示完成
                    logger.info(f"报告生成完成，开始下载: {download_link}")
                    
                    # 3. 下载文件
                    file_resp = self.session.get(download_link, timeout=60)
                    file_resp.raise_for_status()
                    
                    # 生成文件名
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    filename = f"shopee_products_{shop_id}_{start_date}_{end_date}_{timestamp}.xlsx"
                    file_path = output_dir / filename
                    
                    # 保存文件
                    file_path.write_bytes(file_resp.content)
                    file_size = len(file_resp.content)
                    
                    # 保存元数据
                    meta_path = output_dir / f"{filename}.meta.json"
                    meta_data = {
                        "platform": "shopee",
                        "data_type": "product_performance",
                        "shop_id": shop_id,
                        "period": "week",
                        "start_date": start_date,
                        "end_date": end_date,
                        "report_id": report_id,
                        "file_size": file_size,
                        "created_at": timestamp,
                        "download_link": download_link
                    }
                    meta_path.write_text(json.dumps(meta_data, ensure_ascii=False, indent=2), encoding='utf-8')
                    
                    logger.success(f"导出完成: {file_path} ({file_size:,} bytes)")
                    return True, f"导出成功，文件大小: {file_size:,} bytes", file_path
                    
                elif status == 3:  # 状态3表示失败
                    return False, f"报告生成失败: {report_info.get('message', '未知错误')}", None
                    
                else:
                    logger.info(f"报告生成中，状态: {status}")
                    time.sleep(10)
                    
            return False, "报告生成超时，请稍后重试", None
            
        except requests.RequestException as e:
            logger.error(f"网络请求失败: {e}")
            return False, f"网络请求失败: {e}", None
        except Exception as e:
            logger.error(f"导出过程异常: {e}")
            return False, f"导出异常: {e}", None

    def _get_spc_cds(self) -> str:
        """获取 SPC_CDS 参数，这里使用固定值，实际可能需要从页面动态获取"""
        return "84cc39dc-9437-4f51-908d-1a1104b84c9f"

    @classmethod
    def from_persistent_session(cls, platform: str, account_id: str) -> 'ShopeeExporter':
        """从持久化会话创建导出器"""
        try:
            from modules.utils.sessions.session_manager import SessionManager
            
            sm = SessionManager()
            session_data = sm.load_session(platform, account_id)
            
            if session_data and 'cookies' in session_data:
                cookies = {cookie['name']: cookie['value'] for cookie in session_data['cookies']}
                return cls(session_cookies=cookies)
            else:
                logger.warning(f"未找到持久化会话: {platform}/{account_id}")
                return cls()
                
        except Exception as e:
            logger.error(f"加载持久化会话失败: {e}")
            return cls()


def get_week_range(week_offset: int = 0) -> Tuple[str, str]:
    """
    获取周范围
    
    Args:
        week_offset: 周偏移，0=本周，-1=上周，-2=上上周
        
    Returns:
        (start_date, end_date) 格式: YYYY-MM-DD
    """
    today = datetime.now()
    # 获取本周一
    monday = today - timedelta(days=today.weekday())
    # 应用偏移
    target_monday = monday + timedelta(weeks=week_offset)
    target_sunday = target_monday + timedelta(days=6)
    
    return target_monday.strftime("%Y-%m-%d"), target_sunday.strftime("%Y-%m-%d")
