"""
Collection Template Generator - 采集模板生成器
=============================================

为不同数据类型生成标准化的采集脚本模板，支持：
- 深链接直达模式
- API导出优先，点击导出兜底
- 统一的run(page, account)入口
- 参数化配置（shop_id, 日期范围等）

版本：v1.0.0
作者：跨境电商ERP系统
更新：2025-08-29
"""

from pathlib import Path
from typing import Dict, Optional
from datetime import datetime

from modules.utils.recording_registry import RecordingType
from modules.utils.logger import get_logger

logger = get_logger(__name__)


class CollectionTemplateGenerator:
    """采集模板生成器"""
    
    def __init__(self, platform: str):
        self.platform = platform.lower()
        
    def generate_template(self, data_type: RecordingType, account_name: str, 
                         shop_id: Optional[str] = None) -> str:
        """
        生成采集脚本模板
        
        Args:
            data_type: 数据类型
            account_name: 账号名称
            shop_id: 店铺ID（可选）
            
        Returns:
            str: 生成的脚本路径
        """
        template_content = self._get_template_content(data_type, shop_id)
        
        # 生成文件名
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{account_name}_collection_{data_type.value}_{timestamp}.py"
        
        # 保存路径
        output_dir = Path("temp/recordings") / self.platform
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / filename
        
        # 写入文件
        output_path.write_text(template_content, encoding='utf-8')
        
        logger.info(f"✅ 生成采集模板: {output_path}")
        return str(output_path)
    
    def _get_template_content(self, data_type: RecordingType, shop_id: Optional[str]) -> str:
        """获取模板内容"""
        
        if self.platform == "shopee":
            return self._get_shopee_template(data_type, shop_id)
        else:
            return self._get_generic_template(data_type, shop_id)
    
    def _get_shopee_template(self, data_type: RecordingType, shop_id: Optional[str]) -> str:
        """生成Shopee采集模板"""
        
        # 根据数据类型确定URL和配置
        url_mapping = {
            RecordingType.PRODUCTS: "/datacenter/product/overview",
            RecordingType.ORDERS: "/portal/order/list", 
            RecordingType.ANALYTICS: "/datacenter/traffic/overview",
            RecordingType.FINANCE: "/portal/finance/revenue"
        }
        
        selector_mapping = {
            RecordingType.PRODUCTS: {
                "export_button": "text=导出数据",
                "data_table": "[data-testid='product-table']"
            },
            RecordingType.ORDERS: {
                "export_button": "text=导出订单", 
                "data_table": "[data-testid='order-table']"
            },
            RecordingType.ANALYTICS: {
                "export_button": "text=导出报告",
                "data_table": ".analytics-chart"
            },
            RecordingType.FINANCE: {
                "export_button": "text=导出财务数据",
                "data_table": ".finance-table"
            }
        }
        
        route = url_mapping.get(data_type, "/portal")
        selectors = selector_mapping.get(data_type, {})
        
        template = f'''#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Shopee {data_type.value.title()} 数据采集脚本
自动生成于: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

功能：
- 深链接直达 {data_type.value} 页面
- API导出优先，点击导出兜底
- 支持参数化配置（shop_id, 日期范围等）
"""

import time
from pathlib import Path
from typing import Dict, Optional


def run(page, account: Dict, shop_id: Optional[str] = None, **kwargs):
    """
    执行 {data_type.value} 数据采集
    
    Args:
        page: Playwright页面对象
        account: 账号配置
        shop_id: 店铺ID（可选）
        **kwargs: 额外参数（如日期范围等）
    """
    try:
        print(f"🚀 开始采集 {{data_type.value}} 数据...")
        
        # 1. 构造深链接（如果提供了shop_id）
        if shop_id:
            base_url = "https://seller.shopee.cn"
            deep_link = f"{{base_url}}{route}?cnsc_shop_id={{shop_id}}"
            
            # 添加额外参数
            if kwargs:
                params = []
                for key, value in kwargs.items():
                    if value is not None:
                        params.append(f"{{key}}={{value}}")
                if params:
                    deep_link += "&" + "&".join(params)
            
            print(f"🔗 导航到深链接: {{deep_link}}")
            page.goto(deep_link, wait_until="domcontentloaded", timeout=60000)
            
            # 等待页面稳定
            time.sleep(3)
            
            # 验证页面加载
            if "cnsc_shop_id={{shop_id}}" not in page.url:
                raise Exception(f"页面导航失败，当前URL: {{page.url}}")
        
        # 2. 等待关键元素加载
        data_table_selector = "{selectors.get('data_table', '.data-content')}"
        try:
            page.wait_for_selector(data_table_selector, timeout=20000)
            print("✅ 数据表格已加载")
        except:
            print("⚠️ 数据表格加载超时，但继续执行")
        
        # 3. 尝试API导出（优先方案）
        try:
            print("🚀 尝试API导出...")
            
            # TODO: 通过录制确定真实的API端点
            api_endpoint = f"https://seller.shopee.cn/api/{data_type.value}/export"
            params = {{
                "shop_id": shop_id or "default",
                "type": "overview",
                "range": kwargs.get("date_range", "last_30_days")
            }}
            
            response = page.request.get(api_endpoint, params=params, timeout=30000)
            
            if response.ok:
                # 保存文件
                output_dir = Path("temp/outputs/shopee") / (shop_id or "default") / "{data_type.value}"
                output_dir.mkdir(parents=True, exist_ok=True)
                
                timestamp = time.strftime("%Y%m%d_%H%M%S")
                filename = f"{{timestamp}}_{data_type.value}_{{shop_id or 'default'}}.csv"
                output_path = output_dir / filename
                
                output_path.write_bytes(response.body())
                print(f"✅ API导出成功: {{output_path}}")
                return
            else:
                print(f"⚠️ API导出失败 (状态码: {{response.status}})，尝试点击导出")
                
        except Exception as api_error:
            print(f"⚠️ API导出异常: {{api_error}}，尝试点击导出")
        
        # 4. 点击导出按钮（兜底方案）
        export_button_selector = "{selectors.get('export_button', 'text=导出')}"
        
        try:
            page.wait_for_selector(export_button_selector, timeout=10000)
        except:
            raise Exception(f"导出按钮未找到: {{export_button_selector}}")
        
        # 监听下载事件
        with page.expect_download(timeout=60000) as download_info:
            page.click(export_button_selector)
            print("🖱️ 已点击导出按钮，等待下载...")
        
        download = download_info.value
        
        # 保存下载文件
        output_dir = Path("temp/outputs/shopee") / (shop_id or "default") / "{data_type.value}"
        output_dir.mkdir(parents=True, exist_ok=True)
        
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        file_extension = download.suggested_filename.split('.')[-1] if '.' in download.suggested_filename else 'unknown'
        filename = f"{{timestamp}}_{data_type.value}_{{shop_id or 'default'}}.{{file_extension}}"
        output_path = output_dir / filename
        
        download.save_as(str(output_path))
        print(f"✅ 点击导出成功: {{output_path}}")
        
    except Exception as e:
        print(f"❌ {data_type.value} 数据采集失败: {{e}}")
        raise


if __name__ == "__main__":
    # 测试用例
    print("这是一个采集脚本模板，需要在Playwright环境中运行")
    print("使用方法: run(page, account, shop_id='1234567890')")
'''
        
        return template
    
    def _get_generic_template(self, data_type: RecordingType, shop_id: Optional[str]) -> str:
        """生成通用采集模板"""
        
        template = f'''#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
{self.platform.title()} {data_type.value.title()} 数据采集脚本
自动生成于: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

注意：这是通用模板，需要根据具体平台进行调整
"""

import time
from pathlib import Path
from typing import Dict, Optional


def run(page, account: Dict, shop_id: Optional[str] = None, **kwargs):
    """
    执行 {data_type.value} 数据采集
    
    Args:
        page: Playwright页面对象
        account: 账号配置
        shop_id: 店铺ID（可选）
        **kwargs: 额外参数
    """
    try:
        print(f"🚀 开始采集 {data_type.value} 数据...")
        
        # TODO: 根据具体平台实现采集逻辑
        # 1. 导航到目标页面
        # 2. 等待页面加载
        # 3. 执行数据导出
        # 4. 保存文件
        
        print("⚠️ 通用模板需要根据具体平台进行实现")
        
    except Exception as e:
        print(f"❌ {data_type.value} 数据采集失败: {{e}}")
        raise


if __name__ == "__main__":
    print("这是一个采集脚本模板，需要在Playwright环境中运行")
'''
        
        return template


def generate_collection_template(platform: str, data_type: RecordingType, 
                               account_name: str, shop_id: Optional[str] = None) -> str:
    """
    便捷函数：生成采集模板
    
    Args:
        platform: 平台名称
        data_type: 数据类型
        account_name: 账号名称
        shop_id: 店铺ID（可选）
        
    Returns:
        str: 生成的脚本路径
    """
    generator = CollectionTemplateGenerator(platform)
    return generator.generate_template(data_type, account_name, shop_id)


__all__ = [
    "CollectionTemplateGenerator",
    "generate_collection_template"
]
