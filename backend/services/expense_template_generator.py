#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
费用导入Excel模板生成器

生成标准的费用导入模板，包含：
- 标准字段列
- 字段说明
- 示例数据
- 数据验证规则
"""

import pandas as pd
from pathlib import Path
from datetime import datetime
from typing import Optional


class ExpenseTemplateGenerator:
    """费用模板生成器"""
    
    @staticmethod
    def generate_template(
        output_path: Optional[str] = None,
        period_month: str = None
    ) -> str:
        """
        生成费用导入模板
        
        Args:
            output_path: 输出路径（不指定则生成到temp/）
            period_month: 会计期间（如2025-01）
        
        Returns:
            str: 生成的文件路径
        """
        # 默认输出路径
        if not output_path:
            output_dir = Path("temp") / "templates"
            output_dir.mkdir(parents=True, exist_ok=True)
            output_path = output_dir / f"费用导入模板_{datetime.now().strftime('%Y%m%d')}.xlsx"
        
        # 模板列定义
        columns = [
            "期间",  # period_month
            "费用类型",  # expense_type_raw
            "供应商",  # vendor
            "金额",  # amount
            "货币",  # currency
            "税率",  # tax_rate
            "店铺代码",  # shop_id (可选)
            "成本中心",  # cost_center (可选)
            "备注"  # memo
        ]
        
        # 示例数据
        examples = [
            {
                "期间": period_month or "2025-01",
                "费用类型": "租金",
                "供应商": "物业公司A",
                "金额": 12316.0,
                "货币": "CNY",
                "税率": 0.09,
                "店铺代码": "",
                "成本中心": "店铺运营",
                "备注": "铁像寺水街店1月租金"
            },
            {
                "期间": period_month or "2025-01",
                "费用类型": "工资",
                "供应商": "",
                "金额": 14437.6,
                "货币": "CNY",
                "税率": 0,
                "店铺代码": "shopee_sg_3c",
                "成本中心": "人力资源",
                "备注": "KA员工1月工资"
            },
            {
                "期间": period_month or "2025-01",
                "费用类型": "广告费",
                "供应商": "广告公司B",
                "金额": 10676.0,
                "货币": "CNY",
                "税率": 0.06,
                "店铺代码": "",
                "成本中心": "市场推广",
                "备注": "LED广告位投放"
            }
        ]
        
        # 创建DataFrame
        df_examples = pd.DataFrame(examples)
        
        # 字段说明
        field_descriptions = {
            "字段名": columns,
            "必填": ["是", "是", "否", "是", "是", "否", "否", "否", "否"],
            "数据类型": ["文本(YYYY-MM)", "文本", "文本", "数字", "文本(CNY/USD等)", "小数(0-1)", "文本", "文本", "文本"],
            "说明": [
                "会计期间，格式YYYY-MM",
                "费用类型（如：租金/工资/广告费/水电费等）",
                "供应商名称（可选）",
                "费用金额（正数）",
                "货币代码（CNY/USD/SGD等）",
                "税率（如0.09表示9%，0表示无税）",
                "店铺代码（不填则需分摊到所有店铺）",
                "成本中心（可选分类）",
                "备注说明"
            ]
        }
        
        df_descriptions = pd.DataFrame(field_descriptions)
        
        # 写入Excel（多sheet）
        with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
            # Sheet1: 示例数据
            df_examples.to_excel(writer, sheet_name='示例数据', index=False)
            
            # Sheet2: 字段说明
            df_descriptions.to_excel(writer, sheet_name='字段说明', index=False)
            
            # Sheet3: 空白模板（供用户填写）
            df_blank = pd.DataFrame(columns=columns)
            df_blank.to_excel(writer, sheet_name='导入数据', index=False)
        
        print(f"[OK] 模板生成成功: {output_path}")
        return str(output_path)


def generate_po_template(output_path: Optional[str] = None) -> str:
    """
    生成采购订单导入模板
    
    Args:
        output_path: 输出路径
    
    Returns:
        str: 生成的文件路径
    """
    if not output_path:
        output_dir = Path("temp") / "templates"
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / f"采购订单模板_{datetime.now().strftime('%Y%m%d')}.xlsx"
    
    columns = [
        "供应商代码",
        "采购日期",
        "预计到货日期",
        "货币",
        "平台SKU",
        "产品名称",
        "订购数量",
        "单价",
        "备注"
    ]
    
    examples = [
        {
            "供应商代码": "V001",
            "采购日期": "2025-01-29",
            "预计到货日期": "2025-02-15",
            "货币": "CNY",
            "平台SKU": "SKU001",
            "产品名称": "华为Pura70Ultra",
            "订购数量": 100,
            "单价": 5000.0,
            "备注": "春节前备货"
        }
    ]
    
    df = pd.DataFrame(examples)
    df.to_excel(output_path, index=False)
    
    print(f"[OK] 采购模板生成成功: {output_path}")
    return str(output_path)


if __name__ == "__main__":
    # 生成费用模板
    ExpenseTemplateGenerator.generate_template()
    
    # 生成采购模板
    generate_po_template()


