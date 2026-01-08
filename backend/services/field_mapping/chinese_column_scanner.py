#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
中文名词扫描与翻译工具

功能：
1. 扫描所有数据域文件中的中文字段名
2. 翻译中文名词为英文标准字段
3. 确保一对一映射（每个中文名称只对应一个英文标准字段）
"""

import re
import json
from pathlib import Path
from typing import Dict, List, Set, Tuple, Optional
from collections import defaultdict
from backend.services.excel_parser import ExcelParser
from modules.core.db import CatalogFile
from sqlalchemy.orm import Session
from backend.models.database import get_db
from modules.core.logger import get_logger

# 尝试导入pypinyin，如果失败则使用简化版
try:
    from pypinyin import lazy_pinyin, Style
    HAS_PYPINYIN = True
except ImportError:
    HAS_PYPINYIN = False
    logger = get_logger(__name__)
    logger.warning("pypinyin未安装，将使用简化版拼音转换。建议安装: pip install pypinyin")

logger = get_logger(__name__)


def is_date_range_column(column_name: str) -> bool:
    """
    判断字段名是否为日期范围格式（如：2025_09_25_2025_09_25 或 2025-09-25 ~ 2025-09-25）
    
    [*] 重要：日期范围字段不应该进入辞典，因为会带来时间索引混乱
    所有时间字段应该统一为date或datetime两种格式
    
    Args:
        column_name: 字段名
    
    Returns:
        如果是日期范围格式，返回True
    """
    if not column_name:
        return False
    
    col_str = str(column_name).strip()
    
    # 匹配日期范围格式：YYYY_MM_DD_YYYY_MM_DD 或 YYYY-MM-DD ~ YYYY-MM-DD
    date_range_patterns = [
        r'^\d{4}[-_]\d{1,2}[-_]\d{1,2}[-_~]\d{4}[-_]\d{1,2}[-_]\d{1,2}',  # 2025_09_25_2025_09_25 或 2025-09-25~2025-09-25
        r'^\d{4}[-_]\d{1,2}[-_]\d{1,2}.*\d{4}[-_]\d{1,2}[-_]\d{1,2}',  # 包含两个日期
        r'^\d{4}_\d{2}_\d{2}_\d{4}_\d{2}_\d{2}',  # 精确匹配下划线格式
        r'\d{4}[-_]\d{1,2}[-_]\d{1,2}[-_~]\d{4}[-_]\d{1,2}[-_]\d{1,2}',  # 任意位置包含日期范围
    ]
    
    for pattern in date_range_patterns:
        if re.search(pattern, col_str):
            return True
    
    # [*] 新增：匹配包含"日期范围"、"fan_wei"、"范围"等关键词的字段
    if 'fan_wei' in col_str.lower() or '日期范围' in col_str or '[日期范围]' in col_str:
        return True
    
    # [*] 新增：匹配包含两个日期格式的字段（如：2025_09_25_2025_09_25）
    date_pattern = r'\d{4}[-_]\d{1,2}[-_]\d{1,2}'
    matches = re.findall(date_pattern, col_str)
    if len(matches) >= 2:
        # 检查是否是日期范围格式（两个日期之间用下划线、横线或空格分隔）
        return True
    
    return False


def should_filter_column(column_name: str) -> bool:
    """
    判断字段是否应该被过滤掉（不进入辞典）
    
    过滤规则：
    1. 日期范围格式字段（如：2025_09_25_2025_09_25）
    2. 空字段或只有特殊字符
    3. 明显是文件元数据字段（如：Unnamed、Sheet等）
    
    Args:
        column_name: 字段名
        
    Returns:
        如果应该过滤，返回True
    """
    if not column_name or not str(column_name).strip():
        return True
    
    col_str = str(column_name).strip()
    
    # 过滤日期范围格式
    if is_date_range_column(col_str):
        return True
    
    # 过滤Unnamed列
    if col_str.startswith('Unnamed') or col_str.startswith('unnamed'):
        return True
    
    # 过滤明显是元数据的字段
    meta_keywords = ['Sheet', 'sheet', '工作表', '表', 'Tab', 'tab']
    if any(keyword in col_str for keyword in meta_keywords):
        return True
    
    return False


def contains_chinese(text: str) -> bool:
    """检查字符串是否包含中文字符"""
    if not text:
        return False
    return bool(re.search(r'[\u4e00-\u9fff]', str(text)))


def extract_chinese_columns(file_path: str, header_row: int = 0) -> List[str]:
    """从Excel文件中提取中文字段名（过滤掉日期范围和不合理的字段）"""
    try:
        # 尝试多个表头行，找到包含中文最多的那一行
        best_columns = []
        best_count = 0
        
        for hr in [0, 1, 2]:
            try:
                df = ExcelParser.read_excel(file_path, header=hr, nrows=0)  # 只读表头
                chinese_cols = []
                for col in df.columns:
                    col_str = str(col).strip()
                    # 过滤掉日期范围和不合理的字段
                    if should_filter_column(col_str):
                        continue
                    if col_str:  # 只要字段名不为空就添加
                        chinese_cols.append(col_str)
                
                # 选择包含中文最多的那一行
                if len(chinese_cols) > best_count:
                    best_count = len(chinese_cols)
                    best_columns = chinese_cols
            except Exception:
                continue
        
        return best_columns if best_columns else []
    except Exception as e:
        logger.warning(f"读取文件失败 {file_path}: {e}")
        return []


def scan_all_chinese_columns(db: Session, max_files: int = None, include_english: bool = True) -> Dict[str, int]:
    """
    扫描所有已注册文件中的字段名（默认包含中英文）
    
    Args:
        max_files: 最大扫描文件数（None表示全部）
        include_english: 是否包含英文字段名（默认True）
    
    Returns:
        Dict[字段名, 出现次数]
    """
    columns_counter = defaultdict(int)
    
    # 查询所有已注册的文件
    query = db.query(CatalogFile).filter(CatalogFile.status.in_(["pending", "validated", "ingested"]))
    if max_files:
        query = query.limit(max_files)
    
    files = query.all()
    logger.info(f"开始扫描 {len(files)} 个文件...")
    
    for file_record in files:
        try:
            file_path = Path(file_record.file_path)
            if not file_path.exists():
                continue
            
            # 提取字段名（内部已处理多个表头行）
            columns = extract_chinese_columns(str(file_path))
            
            # 如果需要包含英文，也提取英文字段
            if include_english:
                # 尝试读取所有列名
                for hr in [0, 1, 2]:
                    try:
                        df = ExcelParser.read_excel(str(file_path), header=hr, nrows=0)
                        all_cols = [str(c).strip() for c in df.columns if str(c).strip()]
                        # 过滤掉日期范围、Unnamed等不合理字段
                        valid_cols = [
                            c for c in all_cols 
                            if c and not c.startswith('Unnamed') and not should_filter_column(c)
                        ]
                        if valid_cols:
                            columns.extend(valid_cols)
                            break
                    except Exception:
                        continue
            
            if columns:
                # 去重并统计
                seen_in_file = set()
                for col in columns:
                    if col not in seen_in_file:
                        columns_counter[col] += 1
                        seen_in_file.add(col)
        except Exception as e:
            logger.warning(f"处理文件失败 {file_record.file_name}: {e}")
            continue
    
    logger.info(f"扫描完成，发现 {len(columns_counter)} 个不同的字段名")
    return dict(columns_counter)


def translate_chinese_to_english(chinese_name: str) -> str:
    """
    将中文名词翻译为英文标准字段名
    
    策略：
    1. 使用常见的中英文映射词典
    2. 分词后翻译
    3. 使用拼音库进行拼音转换（替代Unicode编码）
    4. 转换为snake_case格式
    
    Returns:
        英文标准字段名（如：order_id, metric_date）
    """
    # 扩展的中英文映射词典（包含更多业务术语）
    translation_dict = {
        # 时间相关（使用数据库列名）
        "日期": "metric_date",
        "订单日期": "order_date_local",
        "统计日期": "metric_date",
        "费用日期": "service_date",
        "时间": "order_time_utc",
        "订单时间": "order_time_utc",
        "下单时间": "order_time_utc",
        "付款时间": "payment_time",
        "发货时间": "ship_time",
        "结算时间": "settlement_time",
        "采购时间": "purchase_time",
        
        # 订单相关
        "订单号": "order_id",
        "订单": "order",
        "订单金额": "order_amount",
        "订单状态": "order_status",
        "订单信息": "order_info",
        
        # 产品相关
        "产品": "product",
        "商品": "product",
        "产品名称": "product_name",
        "商品名称": "product_name",
        "产品标题": "product_title",
        "平台产品标题": "product_platform_title",
        "SKU": "sku",
        "平台SKU": "platform_sku",
        "商品SKU": "product_sku",
        "价格": "price",
        "原价": "original_price",
        "折后价格": "discounted_price",
        "库存": "stock",
        "规格": "specification",
        "规格名称": "spec_name",
        "规格编号": "spec_code",
        "规格货号": "spec_sku",
        
        # 金额相关（扩展）
        "金额": "amount",
        "总金额": "total_amount",
        "实付金额": "paid_amount",
        "退款金额": "refund_amount",
        "成本": "cost",  # 基础成本字段
        "采购成本": "purchase_cost",
        "运费成本": "shipping_cost",
        "运营成本": "operation_cost",
        "其他成本": "other_cost",
        "广告成本": "advertising_cost",
        "利润": "profit",
        "毛利率": "gross_profit_rate",
        "销售利润率": "sales_profit_rate",
        "成本利润率": "cost_profit_rate",
        
        # 运费相关
        "运费": "shipping_fee",
        "实际运费": "actual_shipping_fee",
        "运费成本": "shipping_cost",
        "运费补偿": "shipping_compensation",
        "运费回扣": "shipping_rebate",
        "运费调整": "shipping_adjustment",
        "运费折扣": "shipping_discount",
        "运费补贴": "shipping_subsidy",
        
        # 数量相关（扩展）
        "数量": "quantity",
        "总数": "total",
        "成交件数": "transaction_count",
        "销售数量": "sales_quantity",
        "出库数量": "outbound_quantity",
        "件数": "piece_count",
        
        # 流量相关（扩展）
        "浏览量": "page_views",
        "访问次数": "page_views",
        "访客数": "visitors",
        "访客": "visitors",
        "新访客": "new_visitors",
        "平均访客数": "avg_visitors",
        "平均服务的访客人数": "avg_service_visitors",
        "平均停留时长": "avg_time_on_page",
        "平均页面访问数": "avg_page_views",
        "平均转化率": "avg_conversion_rate",
        "跳出率": "bounce_rate",
        "转化率": "conversion_rate",
        "点击率": "click_rate",
        "曝光次数": "impressions",
        
        # 平台相关（使用数据库列名）
        "平台": "platform_code",
        "店铺": "shop_id",
        "账号": "account",
        "站点": "site",
        
        # 服务相关
        "服务费": "service_fee",
        "佣金": "commission",
        "平台佣金": "platform_commission",
        "佣金补偿": "commission_compensation",
        "佣金折扣": "commission_discount",
        "佣金调整": "commission_adjustment",
        
        # 其他
        "状态": "status",
        "类型": "type",
        "备注": "remark",
        "说明": "description",
        "补偿": "compensation",
        "调整": "adjustment",
        "折扣": "discount",
        "补贴": "subsidy",
        "回扣": "rebate",
    }
    
    # 直接匹配
    if chinese_name in translation_dict:
        return translation_dict[chinese_name]
    
    # 尝试部分匹配（优先匹配较长的关键词）
    sorted_keys = sorted(translation_dict.keys(), key=len, reverse=True)
    for key in sorted_keys:
        if key in chinese_name:
            # 提取剩余部分
            remaining = chinese_name.replace(key, "").strip()
            if remaining:
                # 递归翻译剩余部分
                remaining_en = translate_chinese_to_english(remaining) if remaining else ""
                if remaining_en and remaining_en != f"field_{abs(hash(remaining)) % 10000}":
                    # 组合结果
                    return f"{translation_dict[key]}_{remaining_en}"
                else:
                    return translation_dict[key]
            else:
                return translation_dict[key]
    
    # 如果无法翻译，使用拼音库（pypinyin）进行转换
    if HAS_PYPINYIN:
        # 使用pypinyin生成拼音
        pinyin_list = lazy_pinyin(chinese_name, style=Style.NORMAL)
        # 转换为snake_case
        base_str = "_".join(pinyin_list).lower()
    else:
        # 简化版：使用Unicode编码（向后兼容，但不可读）
        pinyin_chars = []
        for char in chinese_name:
            if '\u4e00' <= char <= '\u9fff':
                # 使用Unicode编码（这是临时方案，应该安装pypinyin）
                pinyin_chars.append(f"c{ord(char) % 100:02d}")
            else:
                pinyin_chars.append(char.lower())
        base_str = "_".join(pinyin_chars)
    
    # 清理非ASCII字符，确保只返回英文和数字
    base_str = re.sub(r'[^\w]', '_', base_str)
    base_str = re.sub(r'_+', '_', base_str).strip('_')
    
    # 如果清理后为空，使用默认值
    if not base_str or re.search(r'[\u4e00-\u9fff]', base_str):
        return f"field_{abs(hash(chinese_name)) % 10000}"
    
    return base_str


def generate_english_field_code(chinese_name: str, existing_fields: Set[str] = None) -> str:
    """
    生成英文标准字段代码，确保唯一性
    
    Args:
        chinese_name: 中文名称
        existing_fields: 已存在的字段代码集合
    
    Returns:
        唯一的英文字段代码
    """
    if existing_fields is None:
        existing_fields = set()
    
    # 基础翻译
    base_code = translate_chinese_to_english(chinese_name)
    
    # 转换为snake_case
    base_code = re.sub(r'[^\w]', '_', base_code)
    base_code = re.sub(r'_+', '_', base_code).strip('_')
    
    # 确保唯一性
    field_code = base_code
    counter = 1
    while field_code in existing_fields:
        field_code = f"{base_code}_{counter}"
        counter += 1
    
    return field_code


def scan_and_translate(db: Session, max_files: int = None, include_english: bool = True) -> List[Dict[str, any]]:
    """
    扫描所有文件中的字段名并翻译为英文标准字段
    
    Args:
        max_files: 最大扫描文件数（None表示全部）
        include_english: 是否包含英文字段名（默认True）
    
    Returns:
        List[{
            "cn_name": "日期" 或 "SKU ID",
            "field_code": "metric_date" 或 "sku_id",
            "frequency": 10,
            "data_domains": ["traffic", "orders"],
            ...
        }]
    """
    # 1. 扫描所有字段名（中英文）
    all_columns = scan_all_chinese_columns(db, max_files, include_english=include_english)
    
    # 2. 按数据域分类
    domain_mapping = defaultdict(set)
    files = db.query(CatalogFile).filter(CatalogFile.status.in_(["pending", "validated", "ingested"])).all()
    if max_files:
        files = files[:max_files]
    
    for file_record in files:
        if file_record.data_domain:
            file_path = Path(file_record.file_path)
            if file_path.exists():
                columns = extract_chinese_columns(str(file_path))
                # 如果需要包含英文，也提取英文字段
                if include_english:
                    for hr in [0, 1, 2]:
                        try:
                            df = ExcelParser.read_excel(str(file_path), header=hr, nrows=0)
                            all_cols = [str(c).strip() for c in df.columns if str(c).strip()]
                            # 过滤掉日期范围、Unnamed等不合理字段
                            valid_cols = [
                                c for c in all_cols 
                                if c and not c.startswith('Unnamed') and not should_filter_column(c)
                            ]
                            columns.extend(valid_cols)
                            break
                        except Exception:
                            continue
                
                if columns:
                    for col in columns:
                        if col in all_columns:
                            domain_mapping[col].add(file_record.data_domain)
    
    # 3. 生成英文标准字段（确保一对一映射）
    existing_fields = set()
    result = []
    
    # 按出现频率排序，优先处理高频字段
    sorted_columns = sorted(all_columns.items(), key=lambda x: x[1], reverse=True)
    
    for column_name, frequency in sorted_columns:
        # 再次过滤：跳过日期范围格式字段
        if should_filter_column(column_name):
            logger.debug(f"跳过不合理字段: {column_name}")
            continue
        
        # 生成唯一的英文字段代码
        # 如果字段名已经是英文且符合标准格式，直接使用；否则翻译
        if not contains_chinese(column_name):
            # 英文字段名，清理后作为基础代码
            base_code = column_name.lower().replace(' ', '_').replace('-', '_')
            base_code = re.sub(r'[^\w]', '_', base_code)
            base_code = re.sub(r'_+', '_', base_code).strip('_')
            field_code = base_code if base_code else f"field_{len(result)+1}"
        else:
            # 中文字段名，使用翻译逻辑
            field_code = generate_english_field_code(column_name, existing_fields)
        
        # 确保唯一性
        while field_code in existing_fields:
            field_code = f"{field_code}_{len([r for r in result if r['field_code'].startswith(field_code)]) + 1}"
        
        existing_fields.add(field_code)
        
        # 确定数据域（取最常见的）
        domains = list(domain_mapping.get(column_name, {"general"}))
        primary_domain = domains[0] if domains else "general"
        
        result.append({
            "cn_name": column_name,  # 原始字段名（可能是中文或英文）
            "field_code": field_code,
            "en_name": field_code if not contains_chinese(column_name) else translate_chinese_to_english(column_name),
            "frequency": frequency,
            "data_domains": domains,
            "primary_domain": primary_domain,
            "description": f"从{len(domains)}个数据域扫描发现，出现{frequency}次",
        })
    
    logger.info(f"扫描翻译完成，生成 {len(result)} 个标准字段映射")
    return result


if __name__ == "__main__":
    # 测试扫描
    db = next(get_db())
    try:
        results = scan_and_translate(db, max_files=100)
        print(f"\n扫描结果（前10个）：")
        for r in results[:10]:
            print(f"  {r['cn_name']} -> {r['field_code']} (出现{r['frequency']}次)")
    finally:
        db.close()

