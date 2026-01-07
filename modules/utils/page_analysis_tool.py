#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
专业页面分析工具
用于分析电商平台页面的元素结构、可下载数据和功能选项
支持Shopee、妙手ERP、TikTok等平台
"""

import time
import json
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime
import logging
from playwright.sync_api import Page, Locator
from dataclasses import dataclass, asdict

logger = logging.getLogger(__name__)

@dataclass
class PageElement:
    """页面元素信息"""
    selector: str
    text: str
    tag_name: str
    attributes: Dict[str, str]
    is_visible: bool
    is_clickable: bool
    position: Dict[str, int]
    size: Dict[str, int]

@dataclass
class DownloadOption:
    """下载选项信息"""
    name: str
    selector: str
    file_types: List[str]
    date_ranges: List[str]
    data_types: List[str]
    is_available: bool

@dataclass
class PageAnalysisResult:
    """页面分析结果"""
    url: str
    title: str
    platform: str
    analysis_time: str
    elements: List[PageElement]
    download_options: List[DownloadOption]
    navigation_menus: List[Dict[str, Any]]
    data_containers: List[Dict[str, Any]]
    interactive_elements: List[Dict[str, Any]]

class PageAnalysisTool:
    """专业页面分析工具"""
    
    def __init__(self, page: Page, platform: str = "unknown"):
        """
        初始化页面分析工具
        
        Args:
            page: Playwright页面对象
            platform: 平台名称 (shopee, miaoshou, tiktok等)
        """
        self.page = page
        self.platform = platform
        self.analysis_results = []
        
        # 平台特定的分析配置
        self.platform_configs = {
            "shopee": {
                "base_url": "https://seller.shopee.cn",
                "download_keywords": ["导出", "下载", "Export", "Download"],
                "data_keywords": ["数据", "分析", "报表", "Data", "Analytics"],
                "menu_keywords": ["菜单", "导航", "Menu", "Navigation"]
            },
            "miaoshou": {
                "base_url": "https://erp.91miaoshou.com",
                "download_keywords": ["导出", "下载", "Export", "Download"],
                "data_keywords": ["数据", "分析", "报表", "Data", "Analytics"],
                "menu_keywords": ["菜单", "导航", "Menu", "Navigation"]
            },
            "tiktok": {
                "base_url": "https://seller.tiktok.com",
                "download_keywords": ["导出", "下载", "Export", "Download"],
                "data_keywords": ["数据", "分析", "报表", "Data", "Analytics"],
                "menu_keywords": ["菜单", "导航", "Menu", "Navigation"]
            }
        }
        
        logger.info(f"🔍 初始化页面分析工具: {platform}")
    
    def analyze_current_page(self) -> PageAnalysisResult:
        """
        分析当前页面
        
        Returns:
            PageAnalysisResult: 页面分析结果
        """
        try:
            logger.info(f"🔍 开始分析页面: {self.page.url}")
            
            # 获取页面基本信息
            url = self.page.url
            title = self.page.title()
            
            # 分析页面元素
            elements = self._analyze_page_elements()
            
            # 分析下载选项
            download_options = self._analyze_download_options()
            
            # 分析导航菜单
            navigation_menus = self._analyze_navigation_menus()
            
            # 分析数据容器
            data_containers = self._analyze_data_containers()
            
            # 分析交互元素
            interactive_elements = self._analyze_interactive_elements()
            
            result = PageAnalysisResult(
                url=url,
                title=title,
                platform=self.platform,
                analysis_time=datetime.now().isoformat(),
                elements=elements,
                download_options=download_options,
                navigation_menus=navigation_menus,
                data_containers=data_containers,
                interactive_elements=interactive_elements
            )
            
            self.analysis_results.append(result)
            logger.info(f"✅ 页面分析完成，发现 {len(elements)} 个元素，{len(download_options)} 个下载选项")
            
            return result
            
        except Exception as e:
            logger.error(f"❌ 页面分析失败: {e}")
            raise
    
    def _analyze_page_elements(self) -> List[PageElement]:
        """分析页面元素"""
        elements = []
        
        try:
            # 获取所有可见元素
            selectors = [
                "button", "a", "input", "select", "textarea",
                "[class*='btn']", "[class*='button']", "[class*='link']",
                "[class*='menu']", "[class*='nav']", "[class*='tab']",
                "[class*='export']", "[class*='download']", "[class*='data']"
            ]
            
            for selector in selectors:
                try:
                    locators = self.page.locator(selector)
                    count = locators.count()
                    
                    for i in range(min(count, 50)):  # 限制每个选择器最多50个元素
                        try:
                            element = locators.nth(i)
                            if element.is_visible():
                                element_info = self._extract_element_info(element, selector)
                                if element_info:
                                    elements.append(element_info)
                        except Exception:
                            continue
                            
                except Exception:
                    continue
            
            logger.info(f"📊 分析了 {len(elements)} 个页面元素")
            return elements
            
        except Exception as e:
            logger.error(f"❌ 分析页面元素失败: {e}")
            return []
    
    def _extract_element_info(self, element: Locator, selector: str) -> Optional[PageElement]:
        """提取元素信息"""
        try:
            # 获取元素文本
            text = element.inner_text().strip()
            
            # 获取标签名
            tag_name = element.evaluate("el => el.tagName.toLowerCase()")
            
            # 获取属性
            attributes = element.evaluate("""
                el => {
                    const attrs = {};
                    for (let attr of el.attributes) {
                        attrs[attr.name] = attr.value;
                    }
                    return attrs;
                }
            """)
            
            # 检查是否可点击
            is_clickable = element.is_enabled() and (
                tag_name in ['button', 'a'] or 
                'click' in str(attributes.get('onclick', '')).lower() or
                'cursor: pointer' in str(attributes.get('style', '')).lower()
            )
            
            # 获取位置和大小
            bounding_box = element.bounding_box()
            position = {"x": bounding_box['x'], "y": bounding_box['y']} if bounding_box else {"x": 0, "y": 0}
            size = {"width": bounding_box['width'], "height": bounding_box['height']} if bounding_box else {"width": 0, "height": 0}
            
            return PageElement(
                selector=selector,
                text=text,
                tag_name=tag_name,
                attributes=attributes,
                is_visible=True,
                is_clickable=is_clickable,
                position=position,
                size=size
            )
            
        except Exception as e:
            logger.debug(f"提取元素信息失败: {e}")
            return None
    
    def _analyze_download_options(self) -> List[DownloadOption]:
        """分析下载选项"""
        download_options = []
        config = self.platform_configs.get(self.platform, {})
        keywords = config.get("download_keywords", [])
        
        try:
            # 查找包含下载关键词的元素
            for keyword in keywords:
                selectors = [
                    f"button:has-text('{keyword}')",
                    f"a:has-text('{keyword}')",
                    f"[title*='{keyword}']",
                    f"[aria-label*='{keyword}']",
                    f".{keyword.lower()}-btn",
                    f".{keyword.lower()}-button"
                ]
                
                for selector in selectors:
                    try:
                        elements = self.page.locator(selector)
                        count = elements.count()
                        
                        for i in range(count):
                            try:
                                element = elements.nth(i)
                                if element.is_visible():
                                    text = element.inner_text().strip()
                                    
                                    # 分析下载选项
                                    download_option = DownloadOption(
                                        name=text,
                                        selector=selector,
                                        file_types=self._detect_file_types(element),
                                        date_ranges=self._detect_date_ranges(),
                                        data_types=self._detect_data_types(),
                                        is_available=element.is_enabled()
                                    )
                                    
                                    download_options.append(download_option)
                                    
                            except Exception:
                                continue
                                
                    except Exception:
                        continue
            
            logger.info(f"📥 发现 {len(download_options)} 个下载选项")
            return download_options
            
        except Exception as e:
            logger.error(f"❌ 分析下载选项失败: {e}")
            return []
    
    def _detect_file_types(self, element: Locator) -> List[str]:
        """检测文件类型"""
        file_types = []
        
        try:
            # 检查元素文本和属性中的文件类型
            text = element.inner_text().lower()
            attributes = element.evaluate("""
                el => {
                    const attrs = {};
                    for (let attr of el.attributes) {
                        attrs[attr.name] = attr.value;
                    }
                    return attrs;
                }
            """)
            
            # 常见文件类型检测
            file_type_patterns = {
                "excel": ["excel", "xlsx", "xls", "表格"],
                "csv": ["csv", "逗号分隔"],
                "json": ["json", "数据"],
                "pdf": ["pdf", "报告"],
                "zip": ["zip", "压缩"]
            }
            
            for file_type, patterns in file_type_patterns.items():
                for pattern in patterns:
                    if pattern in text or pattern in str(attributes).lower():
                        file_types.append(file_type)
                        break
            
            return list(set(file_types))  # 去重
            
        except Exception:
            return []
    
    def _detect_date_ranges(self) -> List[str]:
        """检测日期范围选项"""
        date_ranges = []
        
        try:
            # 查找日期选择器
            date_selectors = [
                "select[name*='date']",
                "select[name*='time']",
                "input[type='date']",
                "[class*='date']",
                "[class*='time']"
            ]
            
            for selector in date_selectors:
                try:
                    elements = self.page.locator(selector)
                    count = elements.count()
                    
                    for i in range(count):
                        element = elements.nth(i)
                        if element.is_visible():
                            # 获取选项
                            options = element.evaluate("""
                                el => {
                                    if (el.tagName === 'SELECT') {
                                        return Array.from(el.options).map(opt => opt.text);
                                    }
                                    return [];
                                }
                            """)
                            
                            date_ranges.extend(options)
                            
                except Exception:
                    continue
            
            return list(set(date_ranges))  # 去重
            
        except Exception:
            return []
    
    def _detect_data_types(self) -> List[str]:
        """检测数据类型"""
        data_types = []
        config = self.platform_configs.get(self.platform, {})
        keywords = config.get("data_keywords", [])
        
        try:
            # 查找数据相关元素
            for keyword in keywords:
                selectors = [
                    f"[class*='{keyword.lower()}']",
                    f"[id*='{keyword.lower()}']",
                    f"div:has-text('{keyword}')",
                    f"span:has-text('{keyword}')"
                ]
                
                for selector in selectors:
                    try:
                        elements = self.page.locator(selector)
                        count = elements.count()
                        
                        for i in range(count):
                            element = elements.nth(i)
                            if element.is_visible():
                                text = element.inner_text().strip()
                                if text and len(text) < 50:  # 避免过长的文本
                                    data_types.append(text)
                                    
                    except Exception:
                        continue
            
            return list(set(data_types))  # 去重
            
        except Exception:
            return []
    
    def _analyze_navigation_menus(self) -> List[Dict[str, Any]]:
        """分析导航菜单"""
        menus = []
        
        try:
            # 查找导航菜单
            menu_selectors = [
                "nav", "[class*='nav']", "[class*='menu']",
                "[role='navigation']", "[aria-label*='导航']"
            ]
            
            for selector in menu_selectors:
                try:
                    elements = self.page.locator(selector)
                    count = elements.count()
                    
                    for i in range(count):
                        element = elements.nth(i)
                        if element.is_visible():
                            menu_info = {
                                "selector": selector,
                                "text": element.inner_text().strip(),
                                "items": self._extract_menu_items(element)
                            }
                            menus.append(menu_info)
                            
                except Exception:
                    continue
            
            return menus
            
        except Exception as e:
            logger.error(f"❌ 分析导航菜单失败: {e}")
            return []
    
    def _extract_menu_items(self, menu_element: Locator) -> List[Dict[str, str]]:
        """提取菜单项"""
        items = []
        
        try:
            # 查找菜单项
            item_selectors = ["a", "button", "[class*='item']", "[class*='link']"]
            
            for selector in item_selectors:
                try:
                    elements = menu_element.locator(selector)
                    count = elements.count()
                    
                    for i in range(count):
                        element = elements.nth(i)
                        if element.is_visible():
                            item = {
                                "text": element.inner_text().strip(),
                                "href": element.get_attribute("href") or "",
                                "selector": selector
                            }
                            if item["text"]:
                                items.append(item)
                                
                except Exception:
                    continue
            
            return items
            
        except Exception:
            return []
    
    def _analyze_data_containers(self) -> List[Dict[str, Any]]:
        """分析数据容器"""
        containers = []
        
        try:
            # 查找数据容器
            container_selectors = [
                "[class*='data']", "[class*='table']", "[class*='list']",
                "[class*='grid']", "[class*='chart']", "[class*='stats']",
                "table", "div[role='grid']", "div[role='table']"
            ]
            
            for selector in container_selectors:
                try:
                    elements = self.page.locator(selector)
                    count = elements.count()
                    
                    for i in range(count):
                        element = elements.nth(i)
                        if element.is_visible():
                            container_info = {
                                "selector": selector,
                                "text": element.inner_text().strip()[:200],  # 限制文本长度
                                "has_data": self._check_has_data(element),
                                "data_count": self._count_data_items(element)
                            }
                            containers.append(container_info)
                            
                except Exception:
                    continue
            
            return containers
            
        except Exception as e:
            logger.error(f"❌ 分析数据容器失败: {e}")
            return []
    
    def _check_has_data(self, element: Locator) -> bool:
        """检查是否有数据"""
        try:
            text = element.inner_text().strip()
            # 检查是否包含数字、日期等数据特征
            import re
            has_numbers = bool(re.search(r'\d+', text))
            has_dates = bool(re.search(r'\d{4}-\d{2}-\d{2}|\d{2}/\d{2}/\d{4}', text))
            return has_numbers or has_dates
        except Exception:
            return False
    
    def _count_data_items(self, element: Locator) -> int:
        """计算数据项数量"""
        try:
            # 查找表格行或列表项
            items = element.locator("tr, li, [class*='item'], [class*='row']")
            return items.count()
        except Exception:
            return 0
    
    def _analyze_interactive_elements(self) -> List[Dict[str, Any]]:
        """分析交互元素"""
        interactive_elements = []
        
        try:
            # 查找交互元素
            interactive_selectors = [
                "button", "a", "input", "select", "textarea",
                "[onclick]", "[onchange]", "[oninput]",
                "[class*='btn']", "[class*='button']", "[class*='link']"
            ]
            
            for selector in interactive_selectors:
                try:
                    elements = self.page.locator(selector)
                    count = elements.count()
                    
                    for i in range(min(count, 20)):  # 限制数量
                        element = elements.nth(i)
                        if element.is_visible() and element.is_enabled():
                            element_info = {
                                "selector": selector,
                                "text": element.inner_text().strip(),
                                "type": element.get_attribute("type") or "",
                                "tag_name": element.evaluate("el => el.tagName.toLowerCase()"),
                                "is_clickable": element.is_enabled()
                            }
                            interactive_elements.append(element_info)
                            
                except Exception:
                    continue
            
            return interactive_elements
            
        except Exception as e:
            logger.error(f"❌ 分析交互元素失败: {e}")
            return []
    
    def save_analysis_result(self, result: PageAnalysisResult, output_dir: str = "temp/analysis") -> str:
        """
        保存分析结果
        
        Args:
            result: 分析结果
            output_dir: 输出目录
            
        Returns:
            str: 保存的文件路径
        """
        try:
            output_path = Path(output_dir)
            output_path.mkdir(parents=True, exist_ok=True)
            
            # 生成文件名
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{self.platform}_page_analysis_{timestamp}.json"
            file_path = output_path / filename
            
            # 转换为字典并保存
            result_dict = asdict(result)
            
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(result_dict, f, ensure_ascii=False, indent=2)
            
            logger.info(f"💾 分析结果已保存: {file_path}")
            return str(file_path)
            
        except Exception as e:
            logger.error(f"❌ 保存分析结果失败: {e}")
            raise
    
    def generate_analysis_report(self, result: PageAnalysisResult) -> str:
        """
        生成分析报告
        
        Args:
            result: 分析结果
            
        Returns:
            str: 报告内容
        """
        try:
            report = []
            report.append("=" * 60)
            report.append(f"📊 {self.platform.upper()} 页面分析报告")
            report.append("=" * 60)
            report.append(f"📅 分析时间: {result.analysis_time}")
            report.append(f"🌐 页面URL: {result.url}")
            report.append(f"📄 页面标题: {result.title}")
            report.append("")
            
            # 下载选项
            report.append("📥 下载选项:")
            if result.download_options:
                for i, option in enumerate(result.download_options, 1):
                    report.append(f"  {i}. {option.name}")
                    report.append(f"     选择器: {option.selector}")
                    report.append(f"     文件类型: {', '.join(option.file_types) if option.file_types else '未知'}")
                    report.append(f"     日期范围: {', '.join(option.date_ranges) if option.date_ranges else '未知'}")
                    report.append(f"     数据类型: {', '.join(option.data_types) if option.data_types else '未知'}")
                    report.append(f"     可用状态: {'✅' if option.is_available else '❌'}")
                    report.append("")
            else:
                report.append("  ❌ 未发现下载选项")
                report.append("")
            
            # 导航菜单
            report.append("🧭 导航菜单:")
            if result.navigation_menus:
                for i, menu in enumerate(result.navigation_menus, 1):
                    report.append(f"  {i}. {menu['text'][:50]}...")
                    if menu['items']:
                        for item in menu['items'][:5]:  # 只显示前5个
                            report.append(f"     - {item['text']}")
                    report.append("")
            else:
                report.append("  ❌ 未发现导航菜单")
                report.append("")
            
            # 数据容器
            report.append("📊 数据容器:")
            if result.data_containers:
                for i, container in enumerate(result.data_containers, 1):
                    report.append(f"  {i}. {container['selector']}")
                    report.append(f"     数据项数: {container['data_count']}")
                    report.append(f"     包含数据: {'✅' if container['has_data'] else '❌'}")
                    report.append("")
            else:
                report.append("  ❌ 未发现数据容器")
                report.append("")
            
            # 交互元素统计
            report.append("🖱️ 交互元素统计:")
            report.append(f"  总元素数: {len(result.elements)}")
            report.append(f"  可点击元素: {len([e for e in result.elements if e.is_clickable])}")
            report.append(f"  交互元素: {len(result.interactive_elements)}")
            report.append("")
            
            report.append("=" * 60)
            report.append("📋 分析完成")
            report.append("=" * 60)
            
            return "\n".join(report)
            
        except Exception as e:
            logger.error(f"❌ 生成分析报告失败: {e}")
            return f"生成报告失败: {e}"


def create_page_analysis_tool(page: Page, platform: str = "unknown") -> PageAnalysisTool:
    """
    创建页面分析工具
    
    Args:
        page: Playwright页面对象
        platform: 平台名称
        
    Returns:
        PageAnalysisTool: 页面分析工具实例
    """
    return PageAnalysisTool(page, platform) 