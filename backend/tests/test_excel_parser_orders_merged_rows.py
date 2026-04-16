import pandas as pd
from pathlib import Path

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


def test_orders_normalize_table_restores_real_blank_profit_cells_from_merged_source_file():
    path = Path(r"F:\Vscode\python_programme\AI_code\xihong_erp\data\raw\2026\shopee_orders_monthly_20260414_222241.xls")
    df = ExcelParser.read_excel(path, header=1, nrows=1943)
    df.columns = [str(c).strip() for c in df.columns]

    normalized, _ = ExcelParser.normalize_table(
        df,
        data_domain="orders",
        file_size_mb=path.stat().st_size / (1024 * 1024),
        source_path=path,
        header_row=1,
    )

    # Excel row 1936 is the order head; 1937-1943 are merged-detail rows that must keep order-level profit blank
    assert normalized.iloc[1933]["订单编号"] == "260306DRVKC6W4"
    assert float(normalized.iloc[1933]["利润(RMB)"]) == 106.79
    assert normalized.iloc[1934]["订单编号"] == "260306DRVKC6W4"
    assert normalized.iloc[1934]["利润(RMB)"] == ""
