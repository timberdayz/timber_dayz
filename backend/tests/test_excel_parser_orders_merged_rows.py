import pandas as pd

from backend.services.excel_parser import ExcelParser


def test_orders_normalize_table_does_not_forward_fill_order_level_profit_fields():
    df = pd.DataFrame(
        [
            {
                "订单编号": "260306DRVKC6W4",
                "店铺": "Shopee菲律宾2店",
                "产品ID": 27984946015,
                "平台SKU": "HKR-LRI9-Transparent-035",
                "SKU ID": 224169128209,
                "销售数量": 2,
                "出库数量": 2,
                "下单时间": "2026-03-06 13:16:50",
                "利润(RMB)": "106.79",
                "买家支付(RMB)": "335.71",
            },
            {
                "订单编号": "",
                "店铺": "",
                "产品ID": 27984946015,
                "平台SKU": "HKR-LRI9-Transparent-035",
                "SKU ID": 224169128209,
                "销售数量": 4,
                "出库数量": 4,
                "下单时间": "",
                "利润(RMB)": "",
                "买家支付(RMB)": "",
            },
        ]
    )

    normalized, report = ExcelParser.normalize_table(df, data_domain="orders")

    assert normalized.loc[0, "利润(RMB)"] == "106.79"
    assert normalized.loc[1, "利润(RMB)"] == ""
    assert normalized.loc[0, "买家支付(RMB)"] == "335.71"
    assert normalized.loc[1, "买家支付(RMB)"] == ""
    assert "利润(RMB)" not in report["filled_columns"]
    assert "买家支付(RMB)" not in report["filled_columns"]


def test_orders_normalize_table_still_forward_fills_order_identity_fields():
    df = pd.DataFrame(
        [
            {
                "订单编号": "260306DRVKC6W4",
                "店铺": "Shopee菲律宾2店",
                "产品ID": 27984946015,
                "平台SKU": "HKR-LRI9-Transparent-035",
                "SKU ID": 224169128209,
                "销售数量": 2,
                "出库数量": 2,
                "下单时间": "2026-03-06 13:16:50",
                "利润(RMB)": "106.79",
            },
            {
                "订单编号": "",
                "店铺": "",
                "产品ID": 27984946015,
                "平台SKU": "HKR-LRI9-Transparent-035",
                "SKU ID": 224169128209,
                "销售数量": 4,
                "出库数量": 4,
                "下单时间": "",
                "利润(RMB)": "",
            },
        ]
    )

    normalized, report = ExcelParser.normalize_table(df, data_domain="orders")

    assert normalized.loc[1, "订单编号"] == "260306DRVKC6W4"
    assert normalized.loc[1, "店铺"] == "Shopee菲律宾2店"
    assert normalized.loc[1, "下单时间"] == "2026-03-06 13:16:50"
    assert "订单编号" in report["filled_columns"]
    assert "店铺" in report["filled_columns"]


def test_orders_normalize_table_restores_real_blank_profit_cells_from_merged_source_file(tmp_path):
    """真实「合并单元格」源文件：订单级利润/买家支付在明细行必须保持空白。

    原始用例依赖本机 raw 目录下的 .xls 导出件（``data/**/*.xls`` 已被 .gitignore
    忽略，仓库里并不存在），无法在 CI/他人机器上复现；这里用 openpyxl 现场造一份
    带合并单元格等价形态的源文件，跑同一条 ``normalize_table`` 路径。
    """
    import openpyxl

    path = tmp_path / "shopee_orders_monthly_merged.xlsx"
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.cell(1, 1, "导出时间: 2026-04-14 22:22:41")
    headers = [
        "订单编号",
        "店铺",
        "产品ID",
        "平台SKU",
        "SKU ID",
        "销售数量",
        "出库数量",
        "下单时间",
        "利润(RMB)",
        "买家支付(RMB)",
    ]
    for col_idx, header in enumerate(headers, start=1):
        sheet.cell(2, col_idx, header)

    # Excel 第 3 行是订单头，第 4/5 行是合并出来的明细行。
    sheet.cell(3, 1, "260306DRVKC6W4")
    sheet.cell(3, 2, "Shopee菲律宾2店")
    sheet.cell(3, 3, 27984946015)
    sheet.cell(3, 4, "HKR-LRI9-Transparent-035")
    sheet.cell(3, 5, 224169128209)
    sheet.cell(3, 6, 2)
    sheet.cell(3, 7, 2)
    sheet.cell(3, 8, "2026-03-06 13:16:50")
    sheet.cell(3, 9, "106.79")
    sheet.cell(3, 10, "335.71")
    # 明细行只带商品维度，订单级字段靠合并单元格继承。
    sheet.cell(4, 3, 27984946015)
    sheet.cell(4, 4, "HKR-LRI9-Transparent-035")
    sheet.cell(4, 5, 224169128209)
    sheet.cell(4, 6, 4)
    sheet.cell(4, 7, 4)
    sheet.cell(5, 3, 27984946016)
    sheet.cell(5, 4, "HKR-LRI9-Transparent-036")
    sheet.cell(5, 5, 224169128210)
    sheet.cell(5, 6, 1)
    sheet.cell(5, 7, 1)

    for column_letter in ("A", "B", "H", "I", "J"):
        sheet.merge_cells(f"{column_letter}3:{column_letter}5")
    workbook.save(path)

    df = ExcelParser.read_excel(path, header=1)
    df.columns = [str(c).strip() for c in df.columns]

    normalized, _ = ExcelParser.normalize_table(
        df,
        data_domain="orders",
        file_size_mb=path.stat().st_size / (1024 * 1024),
        source_path=path,
        header_row=1,
    )

    # 订单头行保留真实金额；合并出来的明细行必须保持空白（不得被前向填充）。
    assert normalized.iloc[0]["订单编号"] == "260306DRVKC6W4"
    assert float(normalized.iloc[0]["利润(RMB)"]) == 106.79
    assert normalized.iloc[1]["订单编号"] == "260306DRVKC6W4"
    assert normalized.iloc[1]["利润(RMB)"] == ""
    assert normalized.iloc[2]["利润(RMB)"] == ""
    assert normalized.iloc[1]["买家支付(RMB)"] == ""
