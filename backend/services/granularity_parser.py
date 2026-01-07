"""
数据粒度解析器 - 从文件路径和名称中识别时间粒度

功能：
- 从文件路径识别 daily/weekly/monthly
- 支持多种命名规范
- 提供默认值回退机制
"""

import re
from pathlib import Path
from typing import Optional, Literal

GranularityType = Literal["daily", "weekly", "monthly"]


class GranularityParser:
    """数据粒度解析器"""
    
    # 粒度关键词映射
    GRANULARITY_KEYWORDS = {
        "daily": ["daily", "day", "日", "每日", "日度"],
        "weekly": ["weekly", "week", "周", "每周", "周度"],
        "monthly": ["monthly", "month", "月", "每月", "月度"],
    }
    
    @classmethod
    def parse_from_path(cls, file_path: str) -> Optional[GranularityType]:
        """
        从文件路径解析粒度
        
        Args:
            file_path: 文件路径
            
        Returns:
            粒度类型或None
            
        示例:
            >>> parse_from_path("temp/outputs/shopee/daily/file.xlsx")
            'daily'
            >>> parse_from_path("temp/outputs/shopee/shop1/weekly/file.xlsx")
            'weekly'
        """
        if not file_path:
            return None
            
        path_lower = file_path.lower()
        
        # 检查路径段中的粒度关键词
        for granularity, keywords in cls.GRANULARITY_KEYWORDS.items():
            for keyword in keywords:
                # 检查是否作为独立路径段存在
                if f"/{keyword}/" in path_lower or f"\\{keyword}\\" in path_lower:
                    return granularity
                # 检查是否在路径末尾
                if path_lower.endswith(f"/{keyword}") or path_lower.endswith(f"\\{keyword}"):
                    return granularity
        
        return None
    
    @classmethod
    def parse_from_filename(cls, filename: str) -> Optional[GranularityType]:
        """
        从文件名解析粒度
        
        Args:
            filename: 文件名
            
        Returns:
            粒度类型或None
            
        示例:
            >>> parse_from_filename("20251022_daily_sales.xlsx")
            'daily'
            >>> parse_from_filename("shopee_weekly_report_20251022.xlsx")
            'weekly'
        """
        if not filename:
            return None
            
        filename_lower = filename.lower()
        
        # 检查文件名中的粒度关键词
        for granularity, keywords in cls.GRANULARITY_KEYWORDS.items():
            for keyword in keywords:
                # 使用单词边界匹配
                pattern = rf"\b{re.escape(keyword)}\b"
                if re.search(pattern, filename_lower):
                    return granularity
        
        return None
    
    @classmethod
    def parse_from_date_range(cls, start_date: str, end_date: str) -> Optional[GranularityType]:
        """
        从日期范围推断粒度
        
        Args:
            start_date: 开始日期 (YYYY-MM-DD)
            end_date: 结束日期 (YYYY-MM-DD)
            
        Returns:
            粒度类型或None
            
        示例:
            >>> parse_from_date_range("2025-10-22", "2025-10-22")
            'daily'
            >>> parse_from_date_range("2025-10-01", "2025-10-31")
            'monthly'
        """
        if not start_date or not end_date:
            return None
            
        try:
            from datetime import datetime
            
            start = datetime.strptime(start_date, "%Y-%m-%d")
            end = datetime.strptime(end_date, "%Y-%m-%d")
            
            delta_days = (end - start).days
            
            # 根据日期跨度判断粒度
            if delta_days == 0:
                return "daily"
            elif 1 <= delta_days <= 7:
                return "weekly"
            elif 20 <= delta_days <= 35:
                return "monthly"
            else:
                return None
                
        except Exception:
            return None
    
    @classmethod
    def parse(
        cls,
        file_path: Optional[str] = None,
        filename: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        default: GranularityType = "daily"
    ) -> GranularityType:
        """
        综合解析粒度，优先级：路径 > 文件名 > 日期范围 > 默认值
        
        Args:
            file_path: 文件路径
            filename: 文件名
            start_date: 开始日期
            end_date: 结束日期
            default: 默认粒度
            
        Returns:
            粒度类型
        """
        # 优先级1: 从路径解析
        if file_path:
            granularity = cls.parse_from_path(file_path)
            if granularity:
                return granularity
        
        # 优先级2: 从文件名解析
        if filename:
            granularity = cls.parse_from_filename(filename)
            if granularity:
                return granularity
        
        # 优先级3: 从日期范围推断
        if start_date and end_date:
            granularity = cls.parse_from_date_range(start_date, end_date)
            if granularity:
                return granularity
        
        # 优先级4: 返回默认值
        return default
    
    @classmethod
    def validate(cls, granularity: str) -> bool:
        """
        验证粒度值是否有效
        
        Args:
            granularity: 粒度值
            
        Returns:
            是否有效
        """
        return granularity in ["daily", "weekly", "monthly"]
    
    @classmethod
    def get_display_name(cls, granularity: GranularityType, lang: str = "zh") -> str:
        """
        获取粒度的显示名称
        
        Args:
            granularity: 粒度类型
            lang: 语言 ('zh' 或 'en')
            
        Returns:
            显示名称
        """
        display_names = {
            "zh": {
                "daily": "每日",
                "weekly": "每周",
                "monthly": "每月",
            },
            "en": {
                "daily": "Daily",
                "weekly": "Weekly",
                "monthly": "Monthly",
            }
        }
        
        return display_names.get(lang, display_names["zh"]).get(granularity, granularity)


# 便捷函数
def parse_granularity(
    file_path: Optional[str] = None,
    filename: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    default: GranularityType = "daily"
) -> GranularityType:
    """
    解析数据粒度的便捷函数
    
    示例:
        >>> parse_granularity(file_path="temp/outputs/shopee/daily/sales.xlsx")
        'daily'
        >>> parse_granularity(filename="weekly_report_20251022.xlsx")
        'weekly'
        >>> parse_granularity(start_date="2025-10-01", end_date="2025-10-31")
        'monthly'
    """
    return GranularityParser.parse(
        file_path=file_path,
        filename=filename,
        start_date=start_date,
        end_date=end_date,
        default=default
    )


if __name__ == "__main__":
    # 测试代码
    print("=" * 60)
    print("粒度解析器测试")
    print("=" * 60)
    
    # 测试路径解析
    test_paths = [
        "temp/outputs/shopee/daily/sales.xlsx",
        "temp/outputs/shopee/shop1/weekly/report.xlsx",
        "F:/data/tiktok/monthly/2025-10.xlsx",
        "temp/outputs/amazon/unknown/file.xlsx",
    ]
    
    print("\n路径解析测试:")
    for path in test_paths:
        result = GranularityParser.parse_from_path(path)
        print(f"  {path:50s} → {result or 'None'}")
    
    # 测试文件名解析
    test_filenames = [
        "20251022_daily_sales.xlsx",
        "shopee_weekly_report_20251022.xlsx",
        "monthly_summary_202510.xlsx",
        "sales_report.xlsx",
    ]
    
    print("\n文件名解析测试:")
    for filename in test_filenames:
        result = GranularityParser.parse_from_filename(filename)
        print(f"  {filename:50s} → {result or 'None'}")
    
    # 测试日期范围推断
    test_date_ranges = [
        ("2025-10-22", "2025-10-22"),
        ("2025-10-20", "2025-10-26"),
        ("2025-10-01", "2025-10-31"),
        ("2025-01-01", "2025-12-31"),
    ]
    
    print("\n日期范围推断测试:")
    for start, end in test_date_ranges:
        result = GranularityParser.parse_from_date_range(start, end)
        delta = (
            __import__("datetime").datetime.strptime(end, "%Y-%m-%d") -
            __import__("datetime").datetime.strptime(start, "%Y-%m-%d")
        ).days
        print(f"  {start} ~ {end} ({delta:2d}天) → {result or 'None'}")
    
    # 测试综合解析
    print("\n综合解析测试:")
    test_cases = [
        {"file_path": "temp/outputs/shopee/daily/sales.xlsx"},
        {"filename": "weekly_report.xlsx"},
        {"start_date": "2025-10-01", "end_date": "2025-10-31"},
        {"filename": "unknown_report.xlsx"},  # 应使用默认值
    ]
    
    for case in test_cases:
        result = parse_granularity(**case)
        print(f"  {str(case):60s} → {result}")
    
    print("\n" + "=" * 60)

