#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
智能Excel解析器（v4.3.3增强版）

功能：
1. 根据文件真实内容（而非扩展名）自动选择正确的解析引擎
2. 自动检测并修复损坏的.xls文件（零手动干预）[*]
3. 智能缓存修复结果，提升性能
"""

from pathlib import Path
from typing import Optional, Union
import pandas as pd
from modules.core.logger import get_logger

logger = get_logger(__name__)


class ExcelParser:
    """智能Excel解析器"""
    
    @staticmethod
    def detect_file_format(file_path: Union[str, Path]) -> str:
        """
        检测文件的真实格式（通过文件头）
        
        Args:
            file_path: 文件路径
            
        Returns:
            文件格式: 'xlsx', 'xls', 'html', 'unknown'
        """
        with open(file_path, 'rb') as f:
            header = f.read(8)
            
            # 优先检测ZIP格式（真正的XLSX）
            if header.startswith(b'PK\x03\x04'):
                return 'xlsx'
            
            # OLE格式：可能是真正的xls或含图片的xlsx（妙手特殊格式）
            if header.startswith(b'\xD0\xCF\x11\xE0'):
                # 对于扩展名为.xlsx的OLE文件，强制尝试openpyxl（妙手含图片文件）
                if file_path.suffix.lower() == '.xlsx':
                    logger.info(f"检测到OLE格式但扩展名为.xlsx，尝试openpyxl（可能含图片）")
                    return 'xlsx_with_ole'  # 特殊标记
                return 'xls'
            
            # 对于扩展名为.xls但非OLE格式的文件，读取更多字节检测HTML
            if file_path.suffix.lower() == '.xls' and not header.startswith(b'\xD0\xCF\x11\xE0'):
                f.seek(0)
                extended_header = f.read(2048).lower()
                if any(tag in extended_header for tag in [b'<html', b'<!doctype', b'<?xml', b'<table', b'<tbody']):
                    return 'html'
            
            # HTML格式（前8字节）
            if header.startswith(b'<html') or header.startswith(b'<!DOCTYPE') or header.startswith(b'<HTML'):
                return 'html'
        
        # 未知格式，尝试HTML兜底
        with open(file_path, 'rb') as f:
            extended = f.read(2048).lower()
            if any(tag in extended for tag in [b'<html', b'<!doctype', b'<table']):
                return 'html'
        
        return 'unknown'
    
    @staticmethod
    def read_excel(
        file_path: Union[str, Path],
        header: Optional[int] = 0,
        nrows: Optional[int] = None,
        **kwargs
    ) -> pd.DataFrame:
        """
        智能读取Excel文件
        
        自动检测文件格式并选择正确的解析引擎
        
        Args:
            file_path: 文件路径
            header: 表头行号（None表示无表头）
            nrows: 读取行数限制
            **kwargs: 其他pandas参数
            
        Returns:
            pd.DataFrame
        """
        file_path = Path(file_path)
        
        # Step 1: 检测真实格式
        real_format = ExcelParser.detect_file_format(file_path)
        logger.info(f"文件格式检测: {file_path.name} -> {real_format}")
        
        # Step 2: 根据格式选择解析方法
        if real_format == 'xlsx':
            # 标准XLSX文件（ZIP格式）
            logger.debug("使用openpyxl引擎读取.xlsx")
            # [*] v4.19.8修复：移除engine_kwargs避免参数冲突（pandas会自动处理读取模式）
            df = pd.read_excel(
                file_path,
                engine='openpyxl',
                header=header,
                nrows=nrows,
                **kwargs
            )
            
        elif real_format == 'xlsx_with_ole':
            # OLE格式但扩展名为.xlsx（Excel 97-2003含图片文件，妙手特殊导出）
            logger.warning(f"检测到OLE格式XLSX文件（可能含大量图片），文件大小: {file_path.stat().st_size / (1024*1024):.2f}MB")
            
            # 方案：尝试xlrd读取OLE格式，忽略图片
            try:
                import xlrd
                logger.info("尝试使用xlrd读取OLE格式XLSX（跳过图片）")
                
                workbook = xlrd.open_workbook(str(file_path), formatting_info=False)  # 跳过格式和图片
                sheet = workbook.sheet_by_index(0)
                
                # 手动读取数据
                data = []
                end_row = min(sheet.nrows, nrows if nrows else sheet.nrows)
                for row_idx in range(end_row):
                    row_data = [sheet.cell_value(row_idx, col_idx) for col_idx in range(sheet.ncols)]
                    data.append(row_data)
                
                # 转换为DataFrame
                if header is not None and len(data) > header + 1:
                    df = pd.DataFrame(data[header + 1:], columns=data[header])
                else:
                    df = pd.DataFrame(data)
                
                logger.info(f"xlrd成功读取OLE格式XLSX: {len(df)}行 x {len(df.columns)}列（图片已跳过）")
                
            except Exception as xlrd_err:
                logger.error(f"xlrd读取OLE格式XLSX失败: {type(xlrd_err).__name__}")
                
                # 终极兜底：返回友好错误，建议用户操作
                raise ValueError(
                    f"无法读取此文件（OLE格式XLSX，含大量图片）。"
                    f"建议：在Excel中打开 -> 另存为 -> Excel工作簿(.xlsx) -> 重新上传。"
                    f"或联系技术支持处理此类文件。"
                )
            
        elif real_format == 'xls':
            # OLE二进制格式的.xls文件
            logger.warning(f"检测到.xls格式文件（OLE二进制），但扩展名可能是.xlsx")
            
            # 尝试使用xlrd（可能版本不兼容或文件损坏）
            try:
                import xlrd
                logger.debug("使用xlrd直接打开工作簿...")
                workbook = xlrd.open_workbook(str(file_path))
                sheet = workbook.sheet_by_index(0)
                
                # 手动读取数据
                data = []
                end_row = min(sheet.nrows, nrows if nrows else sheet.nrows)
                for row_idx in range(end_row):
                    row_data = [sheet.cell_value(row_idx, col_idx) for col_idx in range(sheet.ncols)]
                    data.append(row_data)
                
                # 转换为DataFrame
                if header is not None:
                    df = pd.DataFrame(data[header + 1:], columns=data[header])
                else:
                    df = pd.DataFrame(data)
                
                logger.info(f"使用xlrd成功读取.xls文件")
                
            except (ImportError, Exception) as xlrd_error:
                logger.warning(f"xlrd读取失败: {type(xlrd_error).__name__}: {str(xlrd_error)[:100]}")
                
                # [*] 新增兜底策略1：尝试用openpyxl强制读取（忽略扩展名）
                try:
                    logger.info("尝试openpyxl强制读取.xls文件（可能是xlsx伪装）")
                    df = pd.read_excel(
                        file_path,
                        engine='openpyxl',
                        header=header,
                        nrows=nrows
                    )
                    logger.info(f"openpyxl成功读取: {len(df)}行 x {len(df.columns)}列")
                    return df
                except Exception as openpyxl_err:
                    logger.debug(f"openpyxl失败: {type(openpyxl_err).__name__}: {str(openpyxl_err)[:100]}")
                
                # [*] 新增兜底策略2：自动修复损坏的.xls文件（零手动干预）
                try:
                    from backend.services.file_repair import auto_repair_xls
                    repaired_path = auto_repair_xls(file_path)
                    
                    if repaired_path and repaired_path.exists():
                        logger.info(f"自动修复成功，使用修复文件: {repaired_path.name}")
                        # 递归读取修复后的文件（.xlsx格式）
                        return ExcelParser.read_excel(repaired_path, header=header, nrows=nrows, **kwargs)
                    else:
                        logger.debug("自动修复不可用或失败，继续尝试HTML解析")
                
                except Exception as repair_err:
                    logger.debug(f"自动修复异常: {type(repair_err).__name__}: {str(repair_err)[:100]}")
                
                # 大文件保护：>5MB的文件跳过HTML兜底（性能考虑）
                file_size_mb = file_path.stat().st_size / (1024 * 1024)
                if file_size_mb > 5:
                    logger.error(f"大文件（{file_size_mb:.2f}MB）xlrd失败，跳过HTML兜底（性能保护）")
                    raise ValueError(
                        f"无法读取大型.xls文件（{file_size_mb:.2f}MB），文件可能损坏。"
                        f"建议：用Excel重新导出为标准.xlsx格式。"
                    )
                
                # 兜底策略3：尝试HTML解析（仅小文件）
                html_success = False
                for enc in ['utf-8', 'gbk', 'latin1']:  # 增加latin1编码尝试
                    try:
                        logger.info(f"尝试HTML兜底解析（编码={enc}）")
                        dfs = pd.read_html(str(file_path), header=header, encoding=enc)
                        if dfs:
                            df = dfs[0]
                            if nrows:
                                df = df.head(nrows)
                            logger.info(f"HTML兜底成功（{enc}）: {len(df)}行 x {len(df.columns)}列")
                            html_success = True
                            break
                    except Exception as html_err:
                        logger.debug(f"HTML解析失败（{enc}）: {type(html_err).__name__}")
                        continue
                
                if not html_success:
                    # 四重失败，抛出错误
                    raise ValueError(
                        f"无法读取.xls格式文件，所有尝试均失败（xlrd、openpyxl、自动修复、HTML解析）。"
                        f"文件可能严重损坏。建议：在Excel中手动打开并另存为.xlsx格式。"
                        f"原始错误: {type(xlrd_error).__name__}"
                    )
        
        elif real_format == 'html':
            # HTML格式（妙手ERP导出的伪装Excel）
            logger.debug("使用read_html解析HTML格式")
            dfs = pd.read_html(str(file_path))
            if not dfs:
                raise ValueError("HTML文件中没有找到表格")
            
            df = dfs[0]
            
            # 处理表头
            if header is not None and header > 0:
                df.columns = df.iloc[header]
                df = df.iloc[header + 1:]
            
            # 限制行数
            if nrows is not None:
                df = df.head(nrows)
        
        else:
            raise ValueError(f"不支持的文件格式: {real_format}")
        
        logger.info(f"成功读取: {len(df)}行 x {len(df.columns)}列")
        return df
    
    @staticmethod
    def normalize_table(df: pd.DataFrame, data_domain: str | None = None, file_size_mb: float = 0.0):
        """
        规范化表格数据，处理合并单元格导致的块状空洞（v4.6.0增强版）。

        v4.6.0增强：
        - 扩展关键列识别关键词（订单号、产品ID、日期等）
        - 关键列强制填充（无论空值占比）
        - 大文件优化处理（只处理关键列）
        - 边界情况检测（第一行为空报错）

        策略：
        - 关键列强制填充：订单号、产品ID、日期等关键列，无论空值占比，强制前向填充
        - 启发式前向填充：其他疑似维度/标识/状态类列，空值占比>20%时填充
        - 度量列永不填充：数量/金额等度量列永不填充
        - 大文件优化：>10MB文件只处理关键列，其他列跳过

        Args:
            df: 读取后的 DataFrame
            data_domain: 数据域，用于轻量规则偏置（可为空）
            file_size_mb: 文件大小（MB），用于大文件优化（可选）

        Returns:
            (normalized_df, report)
        """
        report = {"filled_columns": [], "filled_rows": 0, "strategy": "enhanced_ffill", "key_columns": []}
        if df is None or df.empty:
            return df, report

        # 度量列黑名单（永不填充）
        never_fill_keywords = [
            "price", "amount", "qty", "quantity", "pv", "uv", "stock", "gmv",
            "rate", "ratio", "percent", "pct", "评分", "数量", "金额", "单价", "合计",
        ]

        # v4.6.0新增：关键列识别关键词（强制填充）
        key_column_keywords = []
        if (data_domain or "").lower() == "orders":
            # 订单数据域：订单号、订单日期
            key_column_keywords = [
                "订单号", "订单编号", "订单ID", "order_id", "order_number", "order_no",
                "订单日期", "下单日期", "order_date", "date", "日期",
                "店铺", "shop", "shop_id", "店铺ID"
            ]
        elif (data_domain or "").lower() == "products":
            # 产品数据域：产品ID、SKU
            key_column_keywords = [
                "产品ID", "商品ID", "product_id", "sku", "商品编号", "产品编号",
                "日期", "date", "metric_date"
            ]
        else:
            # 通用关键列
            key_column_keywords = [
                "ID", "id", "编号", "日期", "date", "店铺", "shop"
            ]

        # v4.6.0新增：启发式填充关键词（非关键列，但需要填充）
        bias_fill_keywords = []
        if (data_domain or "").lower() == "orders":
            bias_fill_keywords = ["status", "状态", "customer", "buyer"]

        normalized = df.copy()
        total_filled = 0
        key_columns_filled = []

        # v4.6.0新增：大文件优化标志
        is_large_file = file_size_mb > 10.0

        for col in normalized.columns:
            col_str = str(col)
            col_lower = col_str.lower()

            # 黑名单：包含度量关键词，不填充
            if any(k in col_lower for k in never_fill_keywords):
                continue

            series = normalized[col]
            # 仅处理字符串/混合列
            if not (series.dtype == object or str(series.dtype).startswith("string")):
                continue

            # v4.6.0新增：判断是否为关键列（大小写不敏感匹配）
            is_key_column = any(
                k.lower() in col_lower or col_lower in k.lower() 
                for k in key_column_keywords
            )

            # v4.6.0新增：大文件优化 - 只处理关键列
            if is_large_file and not is_key_column:
                continue

            # 计算空值占比
            is_empty = series.isna() | (series.astype(str).str.strip() == "")
            empty_ratio = float(is_empty.mean()) if len(series) else 0.0

            # v4.6.0新增：关键列强制填充（无论空值占比）
            should_fill = False
            if is_key_column:
                should_fill = True
                # v4.6.0新增：检测第一行为空的情况
                if len(series) > 0 and (series.iloc[0] is pd.NA or (isinstance(series.iloc[0], str) and series.iloc[0].strip() == "")):
                    raise ValueError(
                        f"关键列 '{col_str}' 第一行为空，无法进行前向填充。"
                        f"这可能是表头行设置错误或数据格式问题。"
                    )
            elif empty_ratio > 0.2 or any(k in col_lower for k in bias_fill_keywords):
                should_fill = True

            if not should_fill:
                continue

            # 前向填充（先将空字符串视为缺失）
            s_norm = series.copy()
            s_na = s_norm.replace("", pd.NA)
            s_filled = s_na.ffill()
            # 将 NaN 恢复为空字符串，保证与原有清洗兼容
            s_filled = s_filled.fillna("")

            try:
                newly_filled_mask = ((series.astype(str).str.strip() == "") | series.isna()) & (s_filled.astype(str).str.strip() != "")
                newly_filled = int(newly_filled_mask.sum())
            except Exception:
                newly_filled = 0

            if newly_filled > 0:
                normalized[col] = s_filled
                report["filled_columns"].append(col_str)
                total_filled += newly_filled
                if is_key_column:
                    key_columns_filled.append(col_str)

        report["filled_rows"] = total_filled
        report["key_columns"] = key_columns_filled
        if is_large_file:
            report["strategy"] = "large_file_key_columns_only"
        else:
            report["strategy"] = "enhanced_ffill"

        return normalized, report


# 全局单例
_parser_instance: Optional[ExcelParser] = None


def get_excel_parser() -> ExcelParser:
    """获取Excel解析器单例"""
    global _parser_instance
    if _parser_instance is None:
        _parser_instance = ExcelParser()
    return _parser_instance
