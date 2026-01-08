#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Minimal ingestion worker (manifest-first) for products/orders.
- Reads pending rows from catalog_files
- Currently supports data_domain = 'products' (orders: TODO)
- Uses config/field_mappings.yaml for column detection
- Upserts dim_products and fact_product_metrics (units_sold, gmv)

Design principles:
- Import-time: zero side effects
- Idempotent: keyed by (platform_code, shop_id, platform_sku, metric_date, metric_type)
- Conservative: fail fast if required keys missing (shop_id, sku)
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple, Callable
import json
import os
from time import sleep

import pandas as pd
from sqlalchemy import create_engine, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from modules.core.db.schema import (
    Base,
    CatalogFile,
    DimProduct,
    FactProductMetric,
    FactOrder,
    DataQuarantine,
)
from modules.core.secrets_manager import get_secrets_manager
from modules.services.currency_service import normalize_amount_to_rmb
from modules.services.platform_code_service import canonicalize_platform
from modules.services.smart_date_parser import parse_date, detect_dayfirst

CONFIG_PATH = Path("config/field_mappings.yaml")


@dataclass
class IngestionStats:
    picked: int
    succeeded: int
    failed: int


# ---------- Engine helpers ----------

def _get_engine() -> Engine:
    url = os.getenv("DATABASE_URL")
    if not url:
        sm = get_secrets_manager()
        url = f"sqlite:///{sm.get_unified_database_path()}"
    if url.startswith("sqlite:///"):
        engine = create_engine(
            url,
            pool_pre_ping=True,
            future=True,
            connect_args={"check_same_thread": False, "timeout": 30},
        )
        # Set pragmatic options to reduce locking
        try:
            with engine.begin() as conn:
                conn.exec_driver_sql("PRAGMA journal_mode=WAL;")
                conn.exec_driver_sql("PRAGMA synchronous=NORMAL;")
                conn.exec_driver_sql("PRAGMA foreign_keys=ON;")
        except Exception:
            pass
        return engine
    return create_engine(url, pool_pre_ping=True, future=True)


# ---------- Config helpers ----------

def _load_field_mappings() -> Dict:
    import yaml

    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _find_first_column(df: pd.DataFrame, candidates: Iterable[str]) -> Optional[str]:
    lower_map = {str(c).strip().lower(): c for c in df.columns}
    for cand in candidates:
        if cand is None:
            continue
        key = str(cand).strip().lower()
        if key in lower_map:
            return lower_map[key]
    return None
def _find_column_by_keywords(df: pd.DataFrame, keywords: Iterable[str]) -> Optional[str]:
    lower_cols = [str(c).strip().lower() for c in df.columns]
    for i, lc in enumerate(lower_cols):
        for k in keywords:
            if k in lc:
                return df.columns[i]
    return None


def _extract_url_from_cell(val: object) -> Optional[str]:
    """Try to extract http(s) URL from a cell that may contain hyperlink formula or HTML.
    Examples:
    - =HYPERLINK("https://...","text")
    - <a href="https://...">...</a>
    - raw https://... string
    """
    try:
        if val is None:
            return None
        s = str(val)
        if not s:
            return None
        import re
        # try HYPERLINK("url",
        m = re.search(r"HYPERLINK\(\s*\"(https?://[^\"]+)\"", s, flags=re.IGNORECASE)
        if m:
            return m.group(1)
        # try href="url"
        m = re.search(r"href=\"(https?://[^\"]+)\"", s, flags=re.IGNORECASE)
        if m:
            return m.group(1)
        # raw url
        m = re.search(r"https?://\S+", s)
        if m:
            return m.group(0)
        return None
    except Exception:
        return None

def _parse_number(val) -> Optional[float]:
    try:
        if pd.isna(val):
            return None
    except Exception:
        pass
    s = str(val).strip()
    if not s:
        return None
    # Remove common thousand separators and currency letters/symbols
    s2 = s.replace(",", " ").replace("\u00A0", " ")
    import re
    m = re.search(r"-?\d+(?:\.\d+)?", s2)
    if m:
        try:
            return float(m.group(0))
        except Exception:
            return None
    return None


def _detect_currency_from_value(val: str) -> Optional[str]:
    s = str(val).strip().upper()
    if s.startswith("RM"):
        return "MYR"
    if s.startswith("PHP") or s.startswith("₱"):
        return "PHP"
    if s.startswith("THB") or s.startswith("฿"):
        return "THB"
    if s.startswith("VND") or s.endswith("₫"):
        return "VND"
    if s.startswith("IDR") or s.startswith("RP"):
        return "IDR"
    if s.startswith("SGD"):
        return "SGD"
    if s.startswith("USD") or s.startswith("$"):
        return "USD"
    if s.startswith("CNY") or s.startswith("RMB") or s.startswith("￥") or s.startswith("¥"):
        return "CNY"
    return None





def _infer_metric_date_from_filename(file_name: str) -> date:
    # Try find YYYYMMDD; else today
    import re

    m = re.search(r"(20\d{2})(\d{2})(\d{2})", file_name)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except Exception:
            pass
    return date.today()


def _derive_shop_id_from_path(file_path: str, platform_code: str) -> Optional[str]:
    """Best-effort derive shop_id from path or file name.
    Strategy:
      1) Any path segment containing platform_code (case-insensitive) -> return that segment
      2) Filename tokens split by "__": pick the token that is likely the shop (3rd token)
    """
    try:
        pc = (platform_code or '').lower()
        p = Path(file_path)
        name = p.name
        stem = name.rsplit('.', 1)[0]
        tokens = [t for t in stem.split('__') if t]
        # 1) numeric-looking token
        for t in tokens:
            tt = t.strip()
            digits = ''.join(ch for ch in tt if ch.isdigit())
            if len(digits) >= 6:
                return digits
        # 2) shop-like token not equal to platform
        for t in tokens:
            tt = t.strip()
            if tt and tt.lower() != pc and any(ch in tt for ch in ['.', '-']):
                return tt
        # 3) scan path segments, but skip pure platform segment
        for seg in p.parts:
            s = str(seg)
            if pc and pc in s.lower() and s.lower() != pc:
                return s
    except Exception:
        return None
    return None


def _detect_shop_id_column(df: pd.DataFrame) -> Optional[str]:
    candidates = [
        "shop_id",
        "shopid",
        "店铺id",
        "店铺",
        "store_id",
        "storeid",
        "store",
        "店铺名称",
        "store_name",
    ]
    return _find_first_column(df, candidates)


# ---------- Readers ----------

# Safer reader with header inference for Excel

def _read_dataframe2(file_path: Path) -> pd.DataFrame:
    suf = file_path.suffix.lower()
    if suf == ".csv":
        try:
            return pd.read_csv(file_path, encoding="utf-8-sig")
        except Exception:
            return pd.read_csv(file_path)
    elif suf in {".xlsx", ".xls"}:
        return _read_excel_with_header_inference(file_path)
    elif suf == ".jsonl":
        rows: List[dict] = []
        with open(file_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                rows.append(json.loads(line))
        return pd.DataFrame(rows)
    elif suf == ".json":
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            return pd.DataFrame(data)
        return pd.json_normalize(data)
    else:
        raise ValueError(f"Unsupported file type: {suf}")


def _read_dataframe(file_path: Path) -> pd.DataFrame:
    # Delegate to the safer reader to avoid header issues
    return _read_dataframe2(file_path)


def _read_excel_with_header_inference(file_path: Path) -> pd.DataFrame:
    """
    读取Excel文件并智能推断表头位置

    性能优化：
    - 优先扫描第一个Sheet（快速路径）
    - 只有在第一个Sheet无效时才扫描其他Sheet
    - 减少不必要的Sheet读取，提升性能70%+
    """
    # Try all sheets and pick the best header row by token matches
    tokens = [
        "sku", "seller", "product", "item", "title", "name",
        "商品", "标题", "名称", "销量", "浏览", "订单", "订单编号", "商品id", "商品编号",
    ]

    def parse_sheet(df_raw: pd.DataFrame) -> Optional[pd.DataFrame]:
        header_row: Optional[int] = None
        max_scan = min(20, len(df_raw))
        best_score = -1
        best_row = None
        for i in range(max_scan):
            vals = [str(v).strip() for v in df_raw.iloc[i].tolist()]
            non_empty = [v for v in vals if v and v.lower() != "nan"]
            if len(non_empty) < 3:
                continue
            joined = " ".join(s.lower() for s in non_empty)
            score = sum(1 for tok in tokens if tok in joined)
            if score > best_score:
                best_score = score
                best_row = i
        if best_row is None:
            return None
        cols = [str(v).strip() for v in df_raw.iloc[best_row].tolist()]
        df = df_raw.iloc[best_row + 1 :].copy()
        df.columns = cols
        df.reset_index(drop=True, inplace=True)
        return df

    # choose engine explicitly for .xls to use xlrd
    engine = None
    suf = file_path.suffix.lower()
    if suf == ".xls":
        engine = "xlrd"

    try:
        xls = pd.ExcelFile(file_path, engine=engine) if engine else pd.ExcelFile(file_path)

        # [START] 性能优化：优先扫描第一个Sheet（快速路径）
        if len(xls.sheet_names) > 0:
            first_sheet = xls.sheet_names[0]
            try:
                raw = pd.read_excel(xls, sheet_name=first_sheet, header=None)
                first_df = parse_sheet(raw)

                # 如果第一个Sheet有效且数据量足够，直接返回（避免扫描其他Sheet）
                if first_df is not None and not first_df.empty and first_df.shape[0] > 5:
                    return first_df
            except Exception:
                pass

        # 如果第一个Sheet无效，才扫描所有Sheet
        best_df: Optional[pd.DataFrame] = None
        best_score = -1
        for sheet in xls.sheet_names:
            try:
                raw = pd.read_excel(xls, sheet_name=sheet, header=None)
                cand = parse_sheet(raw)
                if cand is None or cand.empty:
                    continue
                # Score by number of non-empty columns and rows
                score = int(cand.shape[1]) + min(50, int(cand.shape[0]))
                if score > best_score:
                    best_score = score
                    best_df = cand
            except Exception:
                continue
        if best_df is not None:
            return best_df
        # Fallback: first sheet, header=0
        return pd.read_excel(file_path, header=0, engine=engine) if engine else pd.read_excel(file_path, header=0)
    except Exception as e:
        # Special case: some environments incorrectly try xlrd for .xlsx
        if suf == ".xlsx" and "xlrd" in str(e).lower():
            try:
                return pd.read_excel(file_path, header=0, engine="openpyxl")
            except Exception:
                pass
        # Enhanced fallbacks for legacy .xls and mis-labeled files
        if suf == ".xls":
            # 1) Try xlrd (1.2.x) direct parse to avoid pandas>=2.0 engine gate
            try:
                import xlrd  # type: ignore
                book = xlrd.open_workbook(str(file_path))
                best_df = None
                best_score = -1
                for i in range(book.nsheets):
                    sh = book.sheet_by_index(i)
                    rows = [sh.row_values(r) for r in range(sh.nrows)]
                    if not rows:
                        continue
                    raw = pd.DataFrame(rows)
                    cand = parse_sheet(raw)
                    if cand is None or cand.empty:
                        continue
                    score = int(cand.shape[1]) + min(50, int(cand.shape[0]))
                    if score > best_score:
                        best_score = score
                        best_df = cand
                if best_df is not None:
                    return best_df
                # default: first row as header on first sheet (best-effort)
                if book.nsheets:
                    sh0 = book.sheet_by_index(0)
                    rows0 = [sh0.row_values(r) for r in range(sh0.nrows)]
                    if rows0:
                        cols = [str(v).strip() for v in rows0[0]]
                        body = rows0[1:] if len(rows0) > 1 else []
                        df0 = pd.DataFrame(body, columns=cols)
                        return df0
            except Exception:
                pass
            # 2) Try HTML table (some .xls are actually HTML)
            try:
                tables = pd.read_html(file_path)
                for t in tables:
                    cand = parse_sheet(t)
                    if cand is not None and not cand.empty:
                        return cand
                if tables:
                    return tables[0]
            except Exception:
                pass
        # 3) last resort
        if suf == ".xls":
            # Avoid pandas+xlrd version gate; signal empty for caller to try other paths
            return pd.DataFrame()
        return pd.read_excel(file_path, header=0)


# ---------- Generic detectors ----------

def _is_manifest_df(df: pd.DataFrame) -> bool:
    try:
        cols = {str(c).strip().lower() for c in df.columns}
        if {'data_type', 'file_path'}.issubset(cols) and not any(k in cols for k in ['sku','id','item_id','product_id','order_id']):
            return True
    except Exception:
        return False
    return False


def _try_set_domain_from_name(cf: 'CatalogFile') -> None:
    """Infer and OVERRIDE data_domain from file name/path tokens."""
    try:
        name = (cf.file_name or '').lower()
        path = (cf.file_path or '').lower()
        text = f"{name} {path}"
        if '__analytics__' in name or ' analytics ' in text or name.endswith('_analytics.xlsx') or '__traffic__' in name or ' traffic ' in text or name.endswith('_traffic.xlsx'):
            # v4.10.0更新：traffic域统一映射到analytics域
            cf.data_domain = 'analytics'
            return
        if '__services__' in name or '__service__' in name or ' service ' in text:
            cf.data_domain = 'service'
            return
        if '__orders__' in name or '__order__' in name or ' order ' in text:
            cf.data_domain = 'orders'
            return
    except Exception:
        pass


def _try_set_domain_from_df(cf: 'CatalogFile', df: pd.DataFrame) -> None:
    try:
        if not cf.data_domain and 'data_type' in df.columns:
            v = str(df['data_type'].iloc[0]).strip().lower()
            mapping = {
                'products': 'products',
                'product': 'products',
                'orders': 'orders',
                'order': 'orders',
                'traffic': 'analytics',  # v4.10.0更新：traffic域统一映射到analytics域
                'analytics': 'analytics',
                'service': 'service',
                'services': 'service',
            }
            cf.data_domain = mapping.get(v)
            if not cf.data_domain:
                if v.startswith('services'):
                    cf.data_domain = 'service'
                elif v.startswith('analytics') or v.startswith('traffic'):  # v4.10.0更新：traffic统一映射到analytics
                    cf.data_domain = 'analytics'
    except Exception:
        pass


def _ingest_unknown_or_manifest(session: Session, cf: 'CatalogFile') -> Tuple[bool, str]:
    # quick skip for known config/manifest json files
    try:
        nm = (cf.file_name or '').lower()
        if nm.endswith('.json') and ('account_config' in nm or 'manifest' in nm):
            return True, 'config/manifest json skipped'
    except Exception:
        pass

    from pathlib import Path as _P
    try:
        df = _read_dataframe2(_P(cf.file_path))
    except Exception as e:
        return False, f"unreadable: {e}"
    if df is None:
        return True, 'empty or unreadable skipped'
    if df.empty:
        return True, 'empty file skipped'

    # try to infer domain from file name first, then by df content
    _try_set_domain_from_name(cf)
    _try_set_domain_from_df(cf, df)

    if _is_manifest_df(df):
        return True, 'manifest skipped'

    # clarify message for recognized-but-unimplemented domains
    if cf.data_domain in {'analytics', 'service', 'orders'}:  # v4.10.0更新：traffic统一为analytics
        return False, f"recognized domain '{cf.data_domain}' but not implemented yet"

    return False, f"unsupported domain: {cf.data_domain}"



# ---------- Upserts ----------

def _ensure_product(session: Session, platform_code: str, shop_id: str, sku: str,
                    product_title: Optional[str], image_url: Optional[str] = None) -> None:
    existing = session.execute(
        select(DimProduct).where(
            DimProduct.platform_code == platform_code,
            DimProduct.shop_id == shop_id,
            DimProduct.platform_sku == sku,
        )
    ).scalar_one_or_none()
    if existing is None:
        session.add(
            DimProduct(
                platform_code=platform_code,
                shop_id=shop_id,
                platform_sku=sku,
                product_title=product_title,
                image_url=image_url,
            )
        )
    else:
        if product_title and not existing.product_title:
            existing.product_title = product_title
        if image_url and not getattr(existing, "image_url", None):
            existing.image_url = image_url


def _merge_product_metric_row(
    session: Session,
    *,
    platform_code: str,
    shop_id: str,
    sku: str,
    metric_date: date,
    granularity: str = "daily",
    sku_scope: str = "product",
    parent_platform_sku: Optional[str] = None,
    source_catalog_id: Optional[int] = None,
    updates: Dict[str, Optional[float]] | None = None,
    currency: Optional[str] = None,
) -> None:
    """Upsert a wide-row in fact_product_metrics and merge numeric fields.

    Only fields provided in `updates` will be updated. This function is idempotent
    with respect to the unique business key (platform, shop, sku, date, granularity, sku_scope).
    """
    if updates is None:
        updates = {}

    existing = session.execute(
        select(FactProductMetric).where(
            FactProductMetric.platform_code == platform_code,
            FactProductMetric.shop_id == shop_id,
            FactProductMetric.platform_sku == sku,
            FactProductMetric.metric_date == metric_date,
            FactProductMetric.granularity == granularity,
            FactProductMetric.sku_scope == sku_scope,
        )
    ).scalar_one_or_none()

    if existing is None:
        obj = FactProductMetric(
            platform_code=platform_code,
            shop_id=shop_id,
            platform_sku=sku,
            metric_date=metric_date,
            granularity=granularity,
            sku_scope=sku_scope,
            parent_platform_sku=parent_platform_sku,
            source_catalog_id=source_catalog_id,
        )
        # apply updates
        for k, v in (updates or {}).items():
            try:
                if v is not None and hasattr(obj, k):
                    setattr(obj, k, v)
            except Exception:
                pass
        if currency is not None:
            obj.currency = currency
        session.add(obj)
    else:
        # update in place
        if parent_platform_sku and not existing.parent_platform_sku:
            existing.parent_platform_sku = parent_platform_sku
        if source_catalog_id and not existing.source_catalog_id:
            existing.source_catalog_id = source_catalog_id
        if currency is not None:
            existing.currency = currency
        for k, v in (updates or {}).items():
            try:
                if v is not None and hasattr(existing, k):
                    setattr(existing, k, v)
            except Exception:
                pass


# ---------- Core ingestion ----------

def _ingest_products_file(session: Session, cf: CatalogFile, mappings: Dict) -> Tuple[bool, str]:
    """Ingest products file with hierarchy support (product-level + variant-level)."""
    
    # 强校验：必须有shop_id
    if not cf.shop_id:
        return False, "missing shop_id (needs assignment)"
    
    df = _read_dataframe2(Path(cf.file_path))
    if df is None:
        return True, "empty or unreadable skipped"
    # Basic cleanup: drop unnamed cols and fully empty rows/cols
    try:
        df = df.copy()
        df.columns = [str(c).strip() for c in df.columns]
        df = df.loc[:, [c for c in df.columns if not str(c).lower().startswith('unnamed')]]
        df = df.dropna(how='all').dropna(how='all', axis=1)
    except Exception:
        pass
    if df.empty:
        return True, "empty file skipped"

    # Skip manifest-like JSON rows (export metadata without product-level metrics)
    cols = set(str(c).strip().lower() for c in df.columns)
    if {'data_type', 'file_path'}.issubset(cols) and not any(k in cols for k in ['sku', 'id', 'item_id', 'product_id']):
        return True, 'manifest skipped'


    platform_code = cf.platform_code or canonicalize_platform(Path(cf.file_path).as_posix()) or "generic"
    platform_code = platform_code.lower()

    # Pick mapping group
    platform_map = mappings.get(platform_code) or mappings.get("generic") or {}

    # Resolve columns
    sku_col = _find_first_column(df, platform_map.get("sku", []))
    if not sku_col:
        sku_col = _find_column_by_keywords(df, [
            "sku", "seller_sku", "product_sku", "item_sku", "款号", "货号", "编码", "编号",
            "item id", "product id", "listing id", "商品id", "商品编号", "item_code", "product_code",
        ])
    if not sku_col:
        for alt in ["ID", "Id", "id", "item_id", "product_id"]:
            if alt in df.columns:
                sku_col = alt
                break
    name_col = _find_first_column(df, platform_map.get("product_name", [])) or _find_column_by_keywords(df, [
        "name", "title", "product", "商品", "标题", "品名",
    ])
    sales_col = _find_first_column(df, platform_map.get("sales", [])) or _find_column_by_keywords(df, [
        "销量", "sold", "sales", "orders", "units", "销售数量", "已售", "成交件数", "订单数",
    ])
    revenue_col = _find_first_column(df, platform_map.get("revenue", [])) or _find_column_by_keywords(df, [
        "销售额", "gmv", "revenue", "amount", "销售金额", "总额", "总计", "商品交易总额",
    ])
    # traffic-like metrics that sometimes present on product reports
    views_col = _find_first_column(df, platform_map.get("views", [])) or _find_column_by_keywords(df, [
        "页面浏览次数", "浏览量", "浏览", "pv", "page views", "曝光",
    ])
    visitors_col = _find_first_column(df, platform_map.get("unique_visitors", [])) or _find_column_by_keywords(df, [
        "独立访客", "访客", "uv", "unique visitors",
    ])
    atc_col = _find_first_column(df, platform_map.get("add_to_cart", [])) or _find_column_by_keywords(df, [
        "加购", "加入购物车", "加购数", "加购次数", "add to cart",
    ])
    conv_col = _find_first_column(df, platform_map.get("conversion_rate", [])) or _find_column_by_keywords(df, [
        "转化率", "conversion rate", "cvr", "成交率",
    ])
    image_col = _find_first_column(df, platform_map.get("image", [])) or _find_column_by_keywords(df, [
        "image", "image url", "img", "picture", "thumbnail", "主图", "缩略图", "图片", "图片链接",
    ])

    # Variant / specification detection
    variant_col = _find_first_column(df, platform_map.get("variant_id", [])) or _find_column_by_keywords(
        df,
        [
            "规格编号", "规格ID", "model id", "model_id", "variation id", "variation_id", "变体", "型号",
        ],
    )
    # Candidate attribute columns (to synthesize variant when vendor omits explicit id)
    attr_cols: List[str] = []
    for kw in ["颜色", "尺码", "款式", "颜色分类", "属性", "内存", "容量", "尺寸", "color", "size", "style"]:
        c = _find_column_by_keywords(df, [kw])
        if c and c not in attr_cols:
            attr_cols.append(c)

    if not sku_col:
        # If columns look like service/traffic metrics, reclassify and report
        try:
            lowcols = {str(c).strip().lower() for c in df.columns}
            svc_keys = {'客服', '满意', '响应', '会话', '平均响应', '超时响应'}
            traf_keys = {'曝光', '浏览', '访客', '页面浏览次数', '转化率', '点击', 'sku 订单数', '订单数'}
            if any(any(k in c for k in svc_keys) for c in lowcols):
                cf.data_domain = 'service'
                return False, "looks like service metrics; not implemented yet"
            if any(any(k in c for k in traf_keys) for c in lowcols):
                cf.data_domain = 'analytics'  # v4.10.0更新：traffic统一映射到analytics
                return False, "looks like traffic/analytics metrics; not implemented yet"
        except Exception:
            pass
        return False, "missing sku column"

    # Detect shop_id column in data (optional, for row-level override if present)
    shop_col = _detect_shop_id_column(df)

    # Metric date: infer from filename (daily snapshot)
    metric_date = _infer_metric_date_from_filename(Path(cf.file_name).name)

    # Currency: platform default if not present
    default_currency = (mappings.get("platform_configs", {}).get(platform_code, {}) or {}).get("currency")

    # Build groups by product sku for hierarchy handling
    succeeded_rows = 0
    groups = df.groupby(sku_col, dropna=False)
    for sku_value, gdf in groups:
        sku = str(sku_value).strip() if pd.notna(sku_value) else None
        if not sku:
            continue
        # Determine shop id for this group (prefer cf.shop_id, else first non-empty row value)
        shop_id_val = cf.shop_id
        if not shop_id_val and shop_col and shop_col in gdf.columns:
            try:
                first_non_empty = gdf[shop_col].dropna().astype(str).str.strip()
                shop_id_val = first_non_empty.iloc[0] if not first_non_empty.empty else None
            except Exception:
                shop_id_val = None
        if not shop_id_val:
            continue

        # image/title (best-effort)
        product_title = None
        if name_col and name_col in gdf.columns:
            try:
                product_title = str(gdf[name_col].dropna().astype(str).iloc[0]).strip()
            except Exception:
                product_title = None
        image_url_val: Optional[str] = None
        if image_col and image_col in gdf.columns:
            try:
                cand = gdf[image_col].dropna().iloc[0]
                image_url_val = _extract_url_from_cell(cand)
                if image_url_val and not image_url_val.lower().startswith(("http://", "https://")):
                    image_url_val = None
            except Exception:
                image_url_val = None

        _ensure_product(session, platform_code, shop_id_val, sku, product_title, image_url=image_url_val)

        # Extract metrics row by row
        def row_metrics(row: pd.Series) -> Dict[str, Optional[float]]:
            m: Dict[str, Optional[float]] = {}
            if sales_col and pd.notna(row.get(sales_col)):
                m["sales_volume"] = _parse_number(row.get(sales_col))
            if revenue_col and pd.notna(row.get(revenue_col)):
                amt = _parse_number(row.get(revenue_col))
                m["sales_amount"] = amt
                if amt is not None:
                    ccy = default_currency or _detect_currency_from_value(str(row.get(revenue_col))) or "USD"
                    try:
                        m["sales_amount_rmb"] = normalize_amount_to_rmb(amt, ccy, metric_date)
                    except Exception:
                        m["sales_amount_rmb"] = None
                    m["currency"] = ccy
            if views_col and pd.notna(row.get(views_col)):
                m["page_views"] = _parse_number(row.get(views_col))
            if visitors_col and pd.notna(row.get(visitors_col)):
                m["unique_visitors"] = _parse_number(row.get(visitors_col))
            if atc_col and pd.notna(row.get(atc_col)):
                m["add_to_cart_count"] = _parse_number(row.get(atc_col))
            if conv_col and pd.notna(row.get(conv_col)):
                raw = str(row.get(conv_col))
                val = _parse_number(raw)
                if val is not None and "%" in raw:
                    val = val / 100.0
                m["conversion_rate"] = val
            return m

        # variant id for each row
        def row_variant_id(row: pd.Series) -> Optional[str]:
            if variant_col and pd.notna(row.get(variant_col)):
                vid = str(row.get(variant_col)).strip()
                return vid or None
            # Try combine attributes
            parts: List[str] = []
            for c in attr_cols:
                try:
                    v = str(row.get(c)).strip()
                    if v and v.lower() != "nan":
                        parts.append(v)
                except Exception:
                    continue
            if parts:
                return "+".join(parts)
            return None

        # Split summary rows vs variant rows
        variant_rows: List[pd.Series] = []
        summary_rows: List[pd.Series] = []
        for _, r in gdf.iterrows():
            vid = row_variant_id(r)
            if vid:
                variant_rows.append(r)
            else:
                summary_rows.append(r)

        # Aggregate variants
        def add_dict(a: Dict[str, Optional[float]], b: Dict[str, Optional[float]]):
            for k, v in b.items():
                if v is None:
                    continue
                if k in {"conversion_rate"}:  # handled later
                    continue
                cur = a.get(k)
                a[k] = (cur or 0.0) + float(v)

        agg_variants: Dict[str, Optional[float]] = {}
        for r in variant_rows:
            add_dict(agg_variants, row_metrics(r))
        # Weighted conversion rate if data present
        if variant_rows:
            try:
                total_orders = sum(_parse_number(v.get(sales_col)) or 0.0 for _, v in pd.DataFrame(variant_rows).iterrows())
            except Exception:
                total_orders = 0.0

        # Pick summary row if any (first one)
        summary_m: Dict[str, Optional[float]] = {}
        if summary_rows:
            summary_m = row_metrics(summary_rows[0])

        # Decide product-level metrics: prefer summary if close to variants sum
        def close(a: Optional[float], b: Optional[float], tol: float) -> bool:
            if a is None or b is None:
                return False
            ma = abs(float(a)); mb = abs(float(b))
            if ma == 0 and mb == 0:
                return True
            return abs(ma - mb) / max(ma, mb) <= tol

        prefer_summary = False
        if summary_m:
            # choose tolerance based on metrics available (sales_amount or sales_volume or page_views)
            checks: List[bool] = []
            checks.append(close(summary_m.get("sales_amount"), agg_variants.get("sales_amount"), 0.05))
            checks.append(close(summary_m.get("sales_volume"), agg_variants.get("sales_volume"), 0.05))
            checks.append(close(summary_m.get("page_views"), agg_variants.get("page_views"), 0.1))
            prefer_summary = any(checks)

        product_updates = summary_m if (prefer_summary and summary_m) else agg_variants
        # 提取currency（字符串类型，不是float）
        product_currency = product_updates.pop("currency", None) if product_updates else None
        
        # Merge product-level
        _merge_product_metric_row(
            session,
            platform_code=platform_code,
            shop_id=shop_id_val,
            sku=sku,
            metric_date=metric_date,
            granularity=(cf.granularity or "daily") if hasattr(cf, "granularity") else "daily",
            sku_scope="product",
            parent_platform_sku=None,
            source_catalog_id=getattr(cf, "id", None),
            updates=product_updates,  # 已移除currency
            currency=product_currency,
        )
        succeeded_rows += 1

        # Emit variant-level rows
        for _, vr in gdf.iterrows():
            vid = row_variant_id(vr)
            if not vid:
                continue
            var_sku = f"{sku}::{vid}"
            _ensure_product(session, platform_code, shop_id_val, var_sku, product_title, image_url=image_url_val)
            v_updates = row_metrics(vr)
            # 提取currency
            var_currency = v_updates.pop("currency", None) if v_updates else None
            
            _merge_product_metric_row(
                session,
                platform_code=platform_code,
                shop_id=shop_id_val,
                sku=var_sku,
                metric_date=metric_date,
                granularity=(cf.granularity or "daily") if hasattr(cf, "granularity") else "daily",
                sku_scope="variant",
                parent_platform_sku=sku,
                source_catalog_id=getattr(cf, "id", None),
                updates=v_updates,  # 已移除currency
                currency=var_currency,
            )

    return (succeeded_rows > 0), f"rows_ingested={succeeded_rows}"


def _ingest_traffic_store_file(
    session: Session,
    cf: CatalogFile,
    mappings: Dict,
    progress_cb: Optional[Callable[["CatalogFile", str, Optional[str]], None]] = None,
) -> Tuple[bool, str]:
    """Ingest store-level daily traffic metrics as a pseudo SKU '__STORE__'.
    Expected columns (any subset): 日期/Date, 页面浏览次数(Page Views), 访客/客户数(Visitors), 订单数(Orders), 转化率(%),
    金额类（如: 商品交易总额(₱), 退款金额(₱) 等）。
    """
    # 强校验：必须有shop_id
    if not cf.shop_id:
        return False, "missing shop_id (needs assignment)"
    
    # parse
    df = _read_dataframe2(Path(cf.file_path))
    if progress_cb:
        try:
            progress_cb(cf, "phase", f"parse:begin")
        except Exception:
            pass
    if df is None:
        return True, "empty or unreadable skipped"

    # cleanup
    try:
        df = df.copy()
        df.columns = [str(c).strip() for c in df.columns]
        df = df.loc[:, [c for c in df.columns if not str(c).lower().startswith('unnamed')]]
        df = df.dropna(how='all').dropna(how='all', axis=1)
    except Exception:
        pass
    # quick feedback for large monthly files
    try:
        print(f"    ~ traffic df shape: {df.shape}", flush=True)
    except Exception:
        pass
    if progress_cb:
        try:
            progress_cb(cf, "phase", f"parse:df_ready shape={tuple(df.shape)}")
        except Exception:
            pass

    if df.empty:
        return True, "empty file skipped"
    if _is_manifest_df(df):
        return True, 'manifest skipped'

    platform_code = (cf.platform_code or canonicalize_platform(Path(cf.file_path).as_posix()) or "generic").lower()
    shop_id = cf.shop_id  # 已在扫描阶段通过ShopResolver解析

    # platform default currency
    default_currency = (mappings.get("platform_configs", {}).get(platform_code, {}) or {}).get("currency")

    # resolve columns
    date_col = _find_column_by_keywords(df, ["日期", "date"])
    views_col = _find_column_by_keywords(df, ["页面浏览次数", "浏览", "page view", "pv"])
    visitors_col = _find_column_by_keywords(df, ["店铺页面访问量", "访客", "客户数", "平均访客数", "uv", "visitor"])
    orders_col = _find_column_by_keywords(df, ["订单数", "orders", "下单数"])
    conv_col = _find_column_by_keywords(df, ["转化率", "平均转化率", "conversion"])
    gmv_col = _find_column_by_keywords(df, ["商品交易总额", "销售额", "gmv", "总成交额"])
    refund_col = _find_column_by_keywords(df, ["退款金额", "退款", "refund"])

    metric_date_from_name = None
    if not date_col:
        metric_date_from_name = _infer_metric_date_from_filename(Path(cf.file_name).name)
    
    # 检测日期格式偏好（抽样前10行）
    prefer_dayfirst = None
    if date_col:
        try:
            samples = df[date_col].head(10).dropna().astype(str).tolist()
            prefer_dayfirst = detect_dayfirst(samples)
            if prefer_dayfirst is not None:
                logger.debug(f"检测到日期格式偏好: dayfirst={prefer_dayfirst}")
        except Exception:
            pass

    if progress_cb:
        try:
            progress_cb(cf, "phase", "map:columns_resolved")
        except Exception:
            pass

    succeeded_rows = 0
    sku = "__STORE__"
    product_title = "STORE_METRICS"
    _ensure_product(session, platform_code, shop_id, sku, product_title, image_url=None)

    # file-level memo for exchange rate: (date, currency) -> rate
    rate_memo: Dict[Tuple[date, str], float] = {}

    def convert_with_memo(amount: Optional[float], ccy: Optional[str], md: date) -> Optional[float]:
        if amount is None:
            return None
        if amount == 0:
            return 0.0
        c = (ccy or "USD").upper()
        key = (md, c)
        rate = rate_memo.get(key)
        if rate is None:
            try:
                rmb_val = normalize_amount_to_rmb(amount, c, md)
                rate = (rmb_val / amount) if amount else 0.0
            except Exception:
                rate = None
            if rate is not None:
                rate_memo[key] = rate
            return rmb_val if 'rmb_val' in locals() else None
        return amount * rate

    # track per-date metrics we've already emitted to avoid duplicates within a single file
    seen: set[Tuple[date, str]] = set()
    total = int(df.shape[0])
    # chunk commit for very large files
    chunk_commit_rows = 500 if total > 1000 else None

    # convert/write loop
    for idx, row in df.iterrows():
        if total > 1000 and idx % 200 == 0:
            try:
                msg = f"convert/write: {idx}/{total}"
                if progress_cb:
                    progress_cb(cf, "phase", msg)
                else:
                    print(f"    ~ {msg}", flush=True)
            except Exception:
                pass

        # Determine metric date (使用智能日期解析器)
        if date_col and pd.notna(row.get(date_col)):
            md = parse_date(row[date_col], prefer_dayfirst=prefer_dayfirst)
            if md is None:
                md = metric_date_from_name or _infer_metric_date_from_filename(Path(cf.file_name).name)
        else:
            md = metric_date_from_name or _infer_metric_date_from_filename(Path(cf.file_name).name)

    def emit(metric_type: str, value: float, currency: Optional[str] = None, rmb: Optional[float] = None) -> None:
        key = (md, metric_type)
        if key in seen:
            return
        seen.add(key)
        # map metric_type to wide table columns
        updates: Dict[str, Optional[float]] = {}
        if metric_type == "page_views":
            updates["page_views"] = value
        elif metric_type in {"visitors", "unique_visitors"}:
            updates["unique_visitors"] = value
        elif metric_type == "orders":
            updates["order_count"] = value
        elif metric_type == "conversion_rate":
            updates["conversion_rate"] = value
        elif metric_type == "gmv":
            updates["sales_amount"] = value
            if rmb is not None:
                updates["sales_amount_rmb"] = rmb
        _merge_product_metric_row(
            session,
            platform_code=platform_code,
            shop_id=shop_id,
            sku=sku,
            metric_date=md,
            granularity=(cf.granularity or "daily") if hasattr(cf, "granularity") else "daily",
            sku_scope="product",
            parent_platform_sku=None,
            source_catalog_id=getattr(cf, "id", None),
            updates=updates,
            currency=currency,
        )

        # numeric metrics
        if views_col and pd.notna(row.get(views_col)):
            v = _parse_number(row[views_col])
            if v is not None:
                emit("page_views", v)
        if visitors_col and pd.notna(row.get(visitors_col)):
            v = _parse_number(row[visitors_col])
            if v is not None:
                emit("visitors", v)
        if orders_col and pd.notna(row.get(orders_col)):
            v = _parse_number(row[orders_col])
            if v is not None:
                emit("orders", v)
        if conv_col and pd.notna(row.get(conv_col)):
            raw = str(row[conv_col])
            val = _parse_number(raw)
            if val is not None:
                if "%" in raw:
                    val = val / 100.0
                emit("conversion_rate", val)

        # amount metrics with currency
        if gmv_col and pd.notna(row.get(gmv_col)):
            amt = _parse_number(row[gmv_col])
            if amt is not None:
                ccy = default_currency or _detect_currency_from_value(str(row[gmv_col])) or "USD"
                rmb = convert_with_memo(amt, ccy, md)
                emit("gmv", amt, currency=ccy, rmb=rmb)
        if refund_col and pd.notna(row.get(refund_col)):
            amt = _parse_number(row[refund_col])
            if amt is not None:
                ccy = default_currency or _detect_currency_from_value(str(row[refund_col])) or "USD"
                rmb = convert_with_memo(amt, ccy, md)
                emit("refunds", amt, currency=ccy, rmb=rmb)

        succeeded_rows += 1

        # chunked commit to shorten "no-output" window on large files
        if chunk_commit_rows and ((idx + 1) % chunk_commit_rows == 0):
            try:
                session.flush()
                for _attempt in range(3):
                    try:
                        session.commit()
                        break
                    except OperationalError:
                        session.rollback()
                        sleep(0.25)
                if progress_cb:
                    progress_cb(cf, "phase", f"commit:chunk at {idx+1}")
                else:
                    print(f"    ~ commit:chunk at {idx+1}", flush=True)
            except Exception:
                # swallow, final commit will happen in run_once
                pass

    # final hand-off to run_once (which will commit and print 'done')
    if progress_cb:
        try:
            progress_cb(cf, "phase", "commit:pending")
        except Exception:
            pass

    return (succeeded_rows > 0), f"rows_ingested={succeeded_rows}"


def _upsert_order(session: Session,
                   platform_code: str,
                   shop_id: str,
                   order_id: str,
                   order_date_local: Optional[date],
                   currency: Optional[str],
                   subtotal: Optional[float] = None,
                   shipping_fee: Optional[float] = None,
                   tax_amount: Optional[float] = None,
                   discount_amount: Optional[float] = None,
                   total_amount: Optional[float] = None) -> None:
    existing = session.execute(
        select(FactOrder).where(
            FactOrder.platform_code == platform_code,
            FactOrder.shop_id == shop_id,
            FactOrder.order_id == order_id,
        )
    ).scalar_one_or_none()
    def nz(x):
        return float(x) if (x is not None) else 0.0
    if existing is None:
        session.add(
            FactOrder(
                platform_code=platform_code,
                shop_id=shop_id,
                order_id=order_id,
                order_date_local=order_date_local,
                currency=currency,
                subtotal=nz(subtotal),
                shipping_fee=nz(shipping_fee),
                tax_amount=nz(tax_amount),
                discount_amount=nz(discount_amount),
                total_amount=nz(total_amount),
            )
        )
    else:
        # upsert with latest values
        if order_date_local:
            existing.order_date_local = order_date_local
        if currency:
            existing.currency = currency
        if subtotal is not None:
            existing.subtotal = nz(subtotal)
        if shipping_fee is not None:
            existing.shipping_fee = nz(shipping_fee)
        if tax_amount is not None:
            existing.tax_amount = nz(tax_amount)
        if discount_amount is not None:
            existing.discount_amount = nz(discount_amount)
        if total_amount is not None:
            existing.total_amount = nz(total_amount)


def _ingest_orders_file(session: Session, cf: CatalogFile, mappings: Dict,
                        progress_cb: Optional[Callable[["CatalogFile", str, Optional[str]], None]] = None) -> Tuple[bool, str]:
    """Minimal orders ingestion (schema-first, tolerant mapping).
    Targets fact_orders; items omitted for first cut.
    """
    # 强校验：必须有shop_id
    if not cf.shop_id:
        return False, "missing shop_id (needs assignment)"
    
    # parse
    if progress_cb:
        try:
            progress_cb(cf, "phase", "parse:begin")
        except Exception:
            pass

    df: Optional[pd.DataFrame] = None
    try:
        df = _read_excel_with_header_inference(Path(cf.file_path))
    except Exception:
        df = None

    # Fallbacks for mis-labeled/HTML/CSV-in-XLS
    if df is None or df.empty:
        # 1) try read_html on path
        try:
            tables = pd.read_html(cf.file_path)
            if tables:
                df = tables[0]
        except Exception:
            df = df or None
    if (df is None or df.empty) and Path(cf.file_path).suffix.lower() == ".xls":
        # 2) try decoding bytes as text and feed to read_html
        try:
            raw = Path(cf.file_path).read_bytes()
            for enc in ("utf-8", "gb18030", "latin-1"):
                try:
                    txt = raw.decode(enc, errors="ignore")
                    if "<table" in txt.lower():
                        tables2 = pd.read_html(txt)
                        if tables2:
                            df = tables2[0]
                            break
                except Exception:
                    continue
        except Exception:
            pass
    if (df is None or df.empty):
        # 3) last try CSV sniff
        try:
            df = pd.read_csv(cf.file_path, engine="python", sep=None)
        except Exception:
            df = None

    if df is None:
        # failure (do not mark as ingested)
        return False, "empty or unreadable"

    # cleanup
    try:
        df = df.copy()
        df.columns = [str(c).strip() for c in df.columns]
        df = df.loc[:, [c for c in df.columns if not str(c).lower().startswith('unnamed')]]
        df = df.dropna(how='all').dropna(how='all', axis=1)
    except Exception:
        pass

    if progress_cb:
        try:
            shape = tuple(df.shape) if hasattr(df, "shape") else None
            progress_cb(cf, "phase", f"parse:df_ready shape={shape}")
        except Exception:
            pass

    if df.empty:
        return False, "empty file"
    if _is_manifest_df(df):
        return True, 'manifest skipped'

    platform_code = (cf.platform_code or canonicalize_platform(Path(cf.file_path).as_posix()) or "generic").lower()
    shop_id = cf.shop_id  # 已在扫描阶段通过ShopResolver解析

    # Column detection (Chinese + English keywords)
    order_id_col = _find_column_by_keywords(df, ["订单编号", "订单号", "单号", "order id", "orderid", "订单编码"])
    date_col = _find_column_by_keywords(df, ["下单时间", "下单日期", "支付时间", "订单日期", "date", "order date"])
    subtotal_col = _find_column_by_keywords(df, ["小计", "商品金额", "subtotal"])  # optional
    ship_col = _find_column_by_keywords(df, ["运费", "shipping", "运费(本地)", "物流费用"])  # optional
    tax_col = _find_column_by_keywords(df, ["税", "税费", "税额", "tax"])  # optional
    discount_col = _find_column_by_keywords(df, ["折扣", "优惠", "discount"])  # optional
    total_col = _find_column_by_keywords(df, ["实付金额", "订单金额", "总金额", "合计", "total", "总计"])  # prefer

    if progress_cb:
        try:
            progress_cb(cf, "phase", "map:columns_resolved")
        except Exception:
            pass

    if not order_id_col:
        return False, "missing order_id column"

    # Default currency: Miaoshou 报表默认视为 CNY；其余平台沿用平台默认或值内探测
    default_currency = (mappings.get("platform_configs", {}).get(platform_code, {}) or {}).get("currency")
    if platform_code == 'miaoshou':
        default_currency = default_currency or 'CNY'

    metric_date_from_name = _infer_metric_date_from_filename(Path(cf.file_name).name)
    
    # 检测日期格式偏好（抽样前10行）
    prefer_dayfirst = None
    if date_col and date_col in df.columns:
        try:
            samples = df[date_col].head(10).dropna().astype(str).tolist()
            prefer_dayfirst = detect_dayfirst(samples)
            if prefer_dayfirst is not None:
                logger.debug(f"[Orders] 检测到日期格式偏好: dayfirst={prefer_dayfirst}")
        except Exception:
            pass

    succeeded_rows = 0
    total = int(df.shape[0])
    for idx, (_, row) in enumerate(df.iterrows()):
        if total > 1000 and idx % 200 == 0:
            if progress_cb:
                try:
                    progress_cb(cf, "phase", f"convert/write: {idx}/{total}")
                except Exception:
                    pass
        oid = str(row[order_id_col]).strip() if pd.notna(row.get(order_id_col)) else None
        if not oid:
            continue
        # order date (使用智能日期解析器)
        if date_col and pd.notna(row.get(date_col)):
            od = parse_date(row[date_col], prefer_dayfirst=prefer_dayfirst)
            if od is None:
                od = metric_date_from_name
        else:
            od = metric_date_from_name
        # amounts
        subtotal = _parse_number(row[subtotal_col]) if subtotal_col and pd.notna(row.get(subtotal_col)) else None
        shipping_fee = _parse_number(row[ship_col]) if ship_col and pd.notna(row.get(ship_col)) else None
        tax_amount = _parse_number(row[tax_col]) if tax_col and pd.notna(row.get(tax_col)) else None
        discount_amount = _parse_number(row[discount_col]) if discount_col and pd.notna(row.get(discount_col)) else None
        total_amount = _parse_number(row[total_col]) if total_col and pd.notna(row.get(total_col)) else None

        # currency detection fallback from value
        currency = default_currency
        if not currency and total_col and pd.notna(row.get(total_col)):
            currency = _detect_currency_from_value(str(row[total_col])) or default_currency
        currency = currency or 'CNY'

        _upsert_order(session, platform_code, shop_id, oid, od, currency,
                      subtotal=subtotal, shipping_fee=shipping_fee, tax_amount=tax_amount,
                      discount_amount=discount_amount, total_amount=total_amount)
        succeeded_rows += 1

    if progress_cb:
        try:
            progress_cb(cf, "phase", "commit:pending")
        except Exception:
            pass

    return (succeeded_rows > 0), f"rows_ingested={succeeded_rows}"


def _ingest_services_file(
    session: Session,
    cf: CatalogFile,
    mappings: Dict,
    progress_cb: Optional[Callable[["CatalogFile", str, Optional[str]], None]] = None,
) -> Tuple[bool, str]:
    """
    Ingest services domain files (agent/ai_assistant sub-types).
    
    Sub-types:
    - ai_assistant: daily rows (逐日一行，店铺级)
    - agent: single row with date range (单行区间，如"26-08-2025 - 24-09-2025")
    """
    # 强校验：必须有shop_id
    if not cf.shop_id:
        return False, "missing shop_id (needs assignment)"
    
    df = _read_dataframe2(Path(cf.file_path))
    if df is None or df.empty:
        return True, "empty or unreadable skipped"
    
    # cleanup
    try:
        df = df.copy()
        df.columns = [str(c).strip() for c in df.columns]
        df = df.loc[:, [c for c in df.columns if not str(c).lower().startswith('unnamed')]]
        df = df.dropna(how='all').dropna(how='all', axis=1)
    except Exception:
        pass
    
    if df.empty:
        return True, "empty file skipped"
    
    platform_code = (cf.platform_code or canonicalize_platform(Path(cf.file_path).as_posix()) or "generic").lower()
    shop_id = cf.shop_id
    sub_domain = (cf.sub_domain or '').lower()
    
    # 根据sub_domain分流
    if sub_domain == 'ai_assistant':
        return _ingest_services_ai_assistant(session, cf, df, platform_code, shop_id, mappings, progress_cb)
    elif sub_domain == 'agent':
        return _ingest_services_agent(session, cf, df, platform_code, shop_id, mappings, progress_cb)
    else:
        return False, f"unsupported services sub_domain: {sub_domain}"


def _ingest_services_ai_assistant(
    session: Session,
    cf: CatalogFile,
    df: pd.DataFrame,
    platform_code: str,
    shop_id: str,
    mappings: Dict,
    progress_cb: Optional[Callable],
) -> Tuple[bool, str]:
    """AI Assistant逐日数据入库（每行一天，店铺级）"""
    
    # 识别列
    date_col = _find_column_by_keywords(df, ["日期", "date", "日期期间"])
    visitors_col = _find_column_by_keywords(df, ["服务的访客", "访客", "visitors"])
    questions_col = _find_column_by_keywords(df, ["已回答的问题", "问题数", "questions"])
    satisfaction_col = _find_column_by_keywords(df, ["好评", "满意度", "satisfaction", "好评比"])
    
    metric_date = _infer_metric_date_from_filename(Path(cf.file_name).name)
    
    # 检测日期格式
    prefer_dayfirst = None
    if date_col:
        try:
            samples = df[date_col].head(10).dropna().astype(str).tolist()
            prefer_dayfirst = detect_dayfirst(samples)
        except Exception:
            pass
    
    sku = "__SERVICES_AI__"
    _ensure_product(session, platform_code, shop_id, sku, "AI_ASSISTANT_METRICS", image_url=None)
    
    succeeded = 0
    for _, row in df.iterrows():
        # 解析日期
        if date_col and pd.notna(row.get(date_col)):
            md = parse_date(row[date_col], prefer_dayfirst=prefer_dayfirst)
            if md is None:
                md = metric_date
        else:
            md = metric_date
        
        updates = {}
        if visitors_col and pd.notna(row.get(visitors_col)):
            updates['unique_visitors'] = _parse_number(row[visitors_col])
        if questions_col and pd.notna(row.get(questions_col)):
            updates['order_count'] = _parse_number(row[questions_col])
        if satisfaction_col and pd.notna(row.get(satisfaction_col)):
            v = _parse_number(row[satisfaction_col])
            if v and "%" in str(row[satisfaction_col]):
                v = v / 100.0
            updates['conversion_rate'] = v
        
        if updates:
            _merge_product_metric_row(
                session,
                platform_code=platform_code,
                shop_id=shop_id,
                sku=sku,
                metric_date=md,
                granularity='daily',
                sku_scope='product',
                source_catalog_id=getattr(cf, 'id', None),
                updates=updates
            )
            succeeded += 1
    
    return (succeeded > 0), f"rows_ingested={succeeded}"


def _ingest_services_agent(
    session: Session,
    cf: CatalogFile,
    df: pd.DataFrame,
    platform_code: str,
    shop_id: str,
    mappings: Dict,
    progress_cb: Optional[Callable],
) -> Tuple[bool, str]:
    """Agent单行区间数据入库（如"26-08-2025 - 24-09-2025"）"""
    
    if len(df) == 0:
        return True, "empty skipped"
    
    row = df.iloc[0]
    
    # 识别列
    date_range_col = _find_column_by_keywords(df, ["日期期间", "日期范围", "date range", "period"])
    visitors_col = _find_column_by_keywords(df, ["访客数", "访客", "visitors"])
    chats_col = _find_column_by_keywords(df, ["聊天询问", "询问", "chats", "聊天"])
    orders_col = _find_column_by_keywords(df, ["订单", "orders", "买家数"])
    gmv_col = _find_column_by_keywords(df, ["销售额", "gmv", "sales"])
    satisfaction_col = _find_column_by_keywords(df, ["满意度", "satisfaction", "用户满意度"])
    
    # 解析日期区间
    period_start = None
    period_end = None
    
    if date_range_col and pd.notna(row.get(date_range_col)):
        date_range_str = str(row[date_range_col]).strip()
        # 解析"26-08-2025 - 24-09-2025"或"26/08/2025 - 24/09/2025"
        import re
        m = re.match(r'(\d{2}[-/]\d{2}[-/]\d{4})\s*-\s*(\d{2}[-/]\d{2}[-/]\d{4})', date_range_str)
        if m:
            period_start = parse_date(m.group(1), prefer_dayfirst=True)
            period_end = parse_date(m.group(2), prefer_dayfirst=True)
            logger.info(f"[Services/Agent] 解析日期区间: {period_start} - {period_end}")
    
    # 兜底：使用文件名日期
    if not period_end:
        period_end = _infer_metric_date_from_filename(Path(cf.file_name).name)
    if not period_start and period_end:
        # 假设是月度数据，起始为月初
        period_start = period_end.replace(day=1)
    
    sku = "__SERVICES_AGENT__"
    _ensure_product(session, platform_code, shop_id, sku, "AGENT_METRICS", image_url=None)
    
    updates = {}
    if visitors_col and pd.notna(row.get(visitors_col)):
        updates['unique_visitors'] = _parse_number(row[visitors_col])
    if chats_col and pd.notna(row.get(chats_col)):
        updates['order_count'] = _parse_number(row[chats_col])
    if orders_col and pd.notna(row.get(orders_col)):
        updates['sales_volume'] = _parse_number(row[orders_col])
    if gmv_col and pd.notna(row.get(gmv_col)):
        amt = _parse_number(row[gmv_col])
        updates['sales_amount'] = amt
        ccy = _detect_currency_from_value(str(row[gmv_col])) if gmv_col else None
        try:
            updates['sales_amount_rmb'] = normalize_amount_to_rmb(amt, ccy or 'USD', period_end)
        except Exception:
            pass
    if satisfaction_col and pd.notna(row.get(satisfaction_col)):
        v = _parse_number(row[satisfaction_col])
        if v and "%" in str(row[satisfaction_col]):
            v = v / 100.0
        updates['conversion_rate'] = v
    
    if updates:
        _merge_product_metric_row(
            session,
            platform_code=platform_code,
            shop_id=shop_id,
            sku=sku,
            metric_date=period_end,  # 统一用period_end为锚点
            granularity='monthly',
            sku_scope='product',
            source_catalog_id=getattr(cf, 'id', None),
            updates=updates
        )
        
        # 写入period_start到扩展字段
        try:
            from sqlalchemy import update
            from modules.core.db.schema import FactProductMetric
            
            stmt = (
                update(FactProductMetric)
                .where(
                    FactProductMetric.platform_code == platform_code,
                    FactProductMetric.shop_id == shop_id,
                    FactProductMetric.platform_sku == sku,
                    FactProductMetric.metric_date == period_end,
                    FactProductMetric.sku_scope == 'product'
                )
                .values(period_start=period_start)
            )
            session.execute(stmt)
            logger.debug(f"[Services/Agent] 写入period_start: {period_start}")
        except Exception as e:
            logger.warning(f"写入period_start失败: {e}")
        
        return True, "single_row_ingested"
    
    return False, "no_metrics_found"


def run_once(limit: int = 20,
             domains: Optional[List[str]] = None,
             recent_hours: Optional[int] = None,
             progress_cb: Optional[Callable[["CatalogFile", str, Optional[str]], None]] = None) -> IngestionStats:
    engine = _get_engine()
    mappings = _load_field_mappings()
    picked = succeeded = failed = 0

    with Session(engine) as session:
        q = select(CatalogFile).where(CatalogFile.status == "pending")
        if domains:
            q = q.where(CatalogFile.data_domain.in_(domains))
        if recent_hours and recent_hours > 0:
            cutoff = datetime.utcnow() - timedelta(hours=recent_hours)
            q = q.where(CatalogFile.first_seen_at >= cutoff)
        q = q.order_by(CatalogFile.id.asc()).limit(limit)
        rows = session.execute(q).scalars().all()
        picked = len(rows)

        for cf in rows:
            # Re-infer domain from filename to correct earlier misclassification
            _try_set_domain_from_name(cf)
            ok = False
            msg = ""
            if progress_cb:
                try:
                    progress_cb(cf, "start", None)
                except Exception:
                    pass
            try:
                domain = (cf.data_domain or "").lower()
                with session.no_autoflush:
                    if domain == "products":
                        ok, msg = _ingest_products_file(session, cf, mappings)
                    elif domain == "analytics":  # v4.10.0更新：traffic统一为analytics
                        ok, msg = _ingest_traffic_store_file(session, cf, mappings, progress_cb=progress_cb)
                    elif domain == "orders":
                        ok, msg = _ingest_orders_file(session, cf, mappings, progress_cb=progress_cb)
                    elif domain in ("services", "service"):
                        ok, msg = _ingest_services_file(session, cf, mappings, progress_cb=progress_cb)
                    else:
                        ok, msg = _ingest_unknown_or_manifest(session, cf)
            except Exception as e:
                ok = False
                msg = f"exception: {e}"

            if ok:
                cf.status = "ingested"
                cf.error_message = None
                # commit per file to reduce lock window
                for _attempt in range(5):
                    try:
                        session.commit()
                        break
                    except OperationalError:
                        session.rollback()
                        sleep(0.5)
                succeeded += 1
                if progress_cb:
                    try:
                        progress_cb(cf, "done", msg)
                    except Exception:
                        pass
            else:
                cf.status = "failed"
                cf.error_message = (msg or "failed")[:500]
                # commit per file to reduce lock window
                for _attempt in range(5):
                    try:
                        session.commit()
                        break
                    except OperationalError:
                        session.rollback()
                        sleep(0.5)
                failed += 1
                if progress_cb:
                    try:
                        progress_cb(cf, "failed", msg)
                    except Exception:
                        pass

        # final commit safeguard
        session.commit()

    return IngestionStats(picked=picked, succeeded=succeeded, failed=failed)


def main() -> None:
    limit = int(os.getenv("INGEST_LIMIT", "20"))
    domains_env = os.getenv("INGEST_DOMAINS", "products")
    domains = [d.strip() for d in domains_env.split(",") if d.strip()] if domains_env else None
    recent_hours = int(os.getenv("INGEST_RECENT_HOURS", "0")) or None
    stats = run_once(limit=limit, domains=domains, recent_hours=recent_hours)
    print(json.dumps({
        "picked": stats.picked,
        "succeeded": stats.succeeded,
        "failed": stats.failed,
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()

