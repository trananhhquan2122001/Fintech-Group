# ============================================================================
# FINEX VN Terminal — app.py [v58-FINAL-COMPLETE]
# Tích hợp toàn diện: 3 CSV + Snapshot + Biểu đồ Plotly + Máy tính cổ tức
# ============================================================================

import streamlit as st
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import plotly.express as px
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import json
import time
import threading
import os
import glob as _glob_v50
from contextlib import contextmanager
from decimal import Decimal, ROUND_FLOOR
import math

# [v57-DIVIDEND] Thư viện PostgreSQL
try:
    import psycopg2
    from psycopg2 import pool
    _HAS_PSYCOPG2 = True
except ImportError:
    _HAS_PSYCOPG2 = False

# [v57-DIVIDEND] KHAI BÁO CẤU HÌNH CỔ TỨC
PAR_VALUE_DEFAULT = 10_000
MIN_CAPITAL_VND = 1_000_000_000
MAX_CAPITAL_VND = 100_000_000_000
CAPITAL_STEP_VND = 1_000_000_000
MIN_MARKET_PRICE = 15_000
MAX_MARKET_PRICE = 150_000
MARKET_PRICE_STEP = 5_000
MIN_DIVIDEND_PERCENT = 5
MAX_DIVIDEND_PERCENT = 100
DIVIDEND_PERCENT_STEP = 5
MIN_OWNED_SHARES = 50_000
MAX_OWNED_SHARES = 100_000_000
DEFAULT_PRICE_LIST = list(range(MIN_MARKET_PRICE, MAX_MARKET_PRICE + 1, MARKET_PRICE_STEP))
DIVIDEND_RATIO_LIST = list(range(MIN_DIVIDEND_PERCENT, MAX_DIVIDEND_PERCENT + 1, DIVIDEND_PERCENT_STEP))

@st.cache_resource(show_spinner=False)
def _get_db_connection_pool():
    if not _HAS_PSYCOPG2: return None
    db_host = st.secrets.get("DB_HOST", os.getenv("DB_HOST", "localhost"))
    db_name = st.secrets.get("DB_NAME", os.getenv("DB_NAME", "fintech_group"))
    db_user = st.secrets.get("DB_USER", os.getenv("DB_USER", "postgres"))
    db_pass = st.secrets.get("DB_PASS", os.getenv("DB_PASS", ""))
    db_port = st.secrets.get("DB_PORT", os.getenv("DB_PORT", "5432"))
    try:
        return psycopg2.pool.SimpleConnectionPool(1, 10, host=db_host, database=db_name, user=db_user, password=db_pass, port=db_port)
    except Exception as e:
        print(f"[Dividend DB] ⚠️ Lỗi kết nối PostgreSQL: {e}")
        return None

def _fetch_dividend_events(ticker: str, dividend_type: str):
    pool_obj = _get_db_connection_pool()
    if not pool_obj: return None
    conn = None
    try:
        conn = pool_obj.getconn()
        with conn.cursor() as cursor:
            query = """SELECT ticker, dividend_type, cash_per_share, stock_ratio_percent, 
                       record_date, payment_date, status, source, updated_at
                       FROM dividend_events WHERE ticker = %s AND dividend_type = %s AND status = 'ACTIVE'
                       ORDER BY record_date DESC LIMIT 1;"""
            cursor.execute(query, (ticker.upper(), dividend_type.upper()))
            result = cursor.fetchone()
            if result:
                columns = [desc[0] for desc in cursor.description]
                return pd.DataFrame([result], columns=columns)
            return None
    except Exception as e:
        return None
    finally:
        if conn: pool_obj.putconn(conn)

def _buyable_shares(capital_vnd: float, market_price: float) -> int:
    if market_price <= 0 or capital_vnd < 0: return 0
    return int(Decimal(str(capital_vnd)) // Decimal(str(market_price)))

def _cash_dividend_actual(shares: int, cash_per_share: float, tax_rate: float = 0) -> dict:
    if shares <= 0 or cash_per_share <= 0: return {"before_tax": 0, "tax": 0, "after_tax": 0}
    before_tax = Decimal(str(shares)) * Decimal(str(cash_per_share))
    tax = before_tax * Decimal(str(tax_rate)) / Decimal('100')
    after_tax = before_tax - tax
    return {"before_tax": float(before_tax), "tax": float(tax), "after_tax": float(after_tax)}

def _cash_dividend_par(shares: int, dividend_percent: float, par_value: float = PAR_VALUE_DEFAULT, tax_rate: float = 0) -> dict:
    if shares <= 0 or dividend_percent <= 0 or par_value <= 0: return {"before_tax": 0, "tax": 0, "after_tax": 0, "cash_per_share": 0}
    cash_per_share = Decimal(str(par_value)) * Decimal(str(dividend_percent)) / Decimal('100')
    res = _cash_dividend_actual(shares, float(cash_per_share), tax_rate)
    res["cash_per_share"] = float(cash_per_share)
    return res

def _format_vnd(value):
    if value is None or pd.isna(value): return "0"
    try: return f"{int(value):,}".replace(",", ".")
    except: return "0"

def _format_shares(value):
    if value is None or pd.isna(value): return "0"
    try: return f"{int(value):,}".replace(",", ".")
    except: return "0"

# ============================================================================
# [v52-MARKET-SNAPSHOT + v56] IMPORT SNAPSHOT & v54 PRIORITY FUNCTIONS
# ============================================================================
try:
    from du_lieu.doc_bctc_goc import (
        LATEST_MARKET_SNAPSHOT, get_latest_market_snapshot, _apply_latest_market_snapshot,
        get_financials_csv_first, get_snapshot_coverage_report, validate_snapshot,
        get_price_freshness, get_shares_status, get_snapshot_as_of,
        SNAPSHOT_PRICE_DATE, SNAPSHOT_BUILD_DATE, LATEST_FINANCIAL_SUPPLEMENT,
        TICKER_ALIASES, REFERENCE_ONLY_MARKET_SNAPSHOT, _canonical_ticker,
    )
    _HAS_SNAPSHOT = True
    print(f"[v56-SNAPSHOT] ✅ Imported LATEST_MARKET_SNAPSHOT ({len(LATEST_MARKET_SNAPSHOT)} mã)")
except ImportError as _e:
    _HAS_SNAPSHOT = False
    LATEST_MARKET_SNAPSHOT, LATEST_FINANCIAL_SUPPLEMENT, TICKER_ALIASES, REFERENCE_ONLY_MARKET_SNAPSHOT = {}, {}, {}, {}
    SNAPSHOT_PRICE_DATE, SNAPSHOT_BUILD_DATE = "2026-10-22", "2026-10-23"
    print(f"[v56-SNAPSHOT] ⚠️ Không import được snapshot/v54: {_e}")
    def get_latest_market_snapshot(ticker, include_reference=False): return {}
    def _apply_latest_market_snapshot(ticker, data, prioritize_csv_financials=True): return data
    def get_financials_csv_first(ticker, csv_df=None, use_supplement=True): return {}
    def get_snapshot_coverage_report(): return pd.DataFrame()
    def validate_snapshot(): return []
    def get_price_freshness(ticker): return {}
    def get_shares_status(ticker): return {}
    def get_snapshot_as_of(ticker=None): return {}
    def _canonical_ticker(ticker): return str(ticker).strip().upper()

# ============================================================================
# [v47-FIX] SAFE DATAFRAME & PYARROW COMPAT
# ============================================================================
def _safe_dataframe(data, **kwargs):
    try:
        st.dataframe(data, **kwargs)
    except Exception:
        if data is None or (hasattr(data, "empty") and data.empty):
            st.info("Không có dữ liệu để hiển thị")
            return
        if hasattr(data, "to_html"):
            html = data.to_html(index=False, classes="df-table", escape=False, border=0)
            st.markdown(html, unsafe_allow_html=True)
        else:
            st.write(data)

_ST_DATAFRAME_ORIGINAL_V56 = st.dataframe

def _st_dataframe_numpy_compat_v56(data=None, *args, **kwargs):
    try:
        return _ST_DATAFRAME_ORIGINAL_V56(data, *args, **kwargs)
    except Exception:
        return _safe_dataframe(data, **kwargs)

st.dataframe = _st_dataframe_numpy_compat_v56

# ============================================================================
# 🔬 PROFILER
# ============================================================================
_SLOW_THRESHOLD = 500
_WARN_THRESHOLD = 200
PROFILE_ON = True

def _prof_init():
    if "profiler_log" not in st.session_state: st.session_state["profiler_log"] = []
    if "profiler_start" not in st.session_state: st.session_state["profiler_start"] = time.perf_counter()

@contextmanager
def prof(name):
    if not PROFILE_ON: yield; return
    t0 = time.perf_counter()
    try: yield
    finally:
        ms = (time.perf_counter() - t0) * 1000
        if "profiler_log" not in st.session_state: st.session_state["profiler_log"] = []
        st.session_state["profiler_log"].append((name, ms))

def _ensure_session_defaults_v56():
    pass

st.set_page_config(page_title="FINEX VN Terminal - Công Nghệ Định Giá Doanh Nghiệp", page_icon="📈", layout="wide", initial_sidebar_state="expanded")
_prof_init()

# ============================================================================
# 1a. LOAD 3 CSV GỐC
# ============================================================================
def _resolve_csv_paths():
    _HERE = os.path.dirname(os.path.abspath(__file__))
    _PARENT = os.path.dirname(_HERE)
    _GP = os.path.dirname(_PARENT)
    _filenames = {'cong_nghe': 'du_lieu_cong_nghe.csv', 'ngan_hang_va_tai_chinh': 'du_lieu_ngan_hang_va_tai_chinh.csv', 'san_xuat_va_khac': 'du_lieu_san_xuat_va_khac.csv'}
    _bases = [_PARENT, _HERE, _GP, os.path.join(_PARENT, "du_lieu"), os.path.join(_HERE, "du_lieu"), os.getcwd(), os.path.join(os.getcwd(), "du_lieu"), "/app", "/app/du_lieu"]
    result = {}
    for key, fname in _filenames.items():
        found = None
        for base in _bases:
            path = os.path.join(base, fname)
            try:
                if os.path.isfile(path) and os.path.getsize(path) > 0:
                    found = os.path.abspath(path); break
            except OSError: continue
        result[key] = found
    return result

_CSV_DB_PATHS = _resolve_csv_paths()

def _normalize_table_v50(df, tbl_name=None):
    if df is None or df.empty: return None
    cols = set(df.columns)
    if {'ticker', 'metric_name', 'period', 'value'}.issubset(cols): return df[['ticker', 'metric_name', 'period', 'value']].copy()
    ticker_aliases = ['ticker', 'ma', 'symbol', 'code', 'stock_code', 'ma_ck']
    period_aliases = ['period', 'ky', 'quarter', 'year', 'quy', 'nam', 'ky_bao_cao']
    metric_aliases = ['metric_name', 'metric', 'chi_tieu', 'chi_tieu_ten']
    value_aliases = ['value', 'gia_tri', 'val']
    ticker_col = next((c for c in ticker_aliases if c in cols), None)
    period_col = next((c for c in period_aliases if c in cols), None)
    metric_col = next((c for c in metric_aliases if c in cols), None)
    value_col = next((c for c in value_aliases if c in cols), None)
    if ticker_col and metric_col and value_col:
        out = df.rename(columns={ticker_col: 'ticker', metric_col: 'metric_name', value_col: 'value'})
        if period_col: out = out.rename(columns={period_col: 'period'})
        else: out['period'] = '2026H1'
        return out[['ticker', 'metric_name', 'period', 'value']]
    return None

import re as _re_v51
_PERIOD_PATTERN_V51 = _re_v51.compile(r'^(?:19|20)\d{2}(?:Q[1-4]|H[12])?$', _re_v51.IGNORECASE)
_METRIC_COL_RAW_V51 = {'cột 1', 'cột1', 'cot 1', 'cot1', 'chỉ tiêu', 'chi tiêu', 'chỉ_tiêu', 'chi_tiêu', 'unnamed: 0', 'unnamed:0', 'metric', 'metric_name'}

def _is_period_column_v51(cn):
    if cn is None: return False
    s = str(cn).strip().replace(' ', '').replace('_', '').upper()
    return bool(_PERIOD_PATTERN_V51.match(s))

def _is_metric_column_v51(cn):
    if cn is None: return False
    return str(cn).strip().lower() in _METRIC_COL_RAW_V51

def _parse_vn_number_v51(value):
    if value is None: return None
    if isinstance(value, (int, float, np.integer, np.floating)):
        v = float(value); return None if (np.isnan(v) or np.isinf(v)) else v
    s = str(value).strip()
    if not s or s.lower() in ('na', 'n/a', 'none', 'nan', 'null', '-', '--', '—'): return None
    s = _re_v51.sub(r'[^\d,.\-]', '', s)
    if not s or s == '-': return None
    is_neg = s.startswith('-')
    if is_neg: s = s[1:]
    has_dot, has_comma = '.' in s, ',' in s
    try:
        if has_dot and has_comma:
            ld, lc = s.rfind('.'), s.rfind(',')
            norm = s[:lc].replace('.', '').replace(',', '') + '.' + s[lc+1:] if lc > ld else s[:ld].replace(',', '') + '.' + s[ld+1:]
        elif has_comma:
            parts = s.split(','); last = parts[-1]
            norm = ''.join(parts[:-1]) + '.' + last if (len(parts) >= 2 and len(last) <= 2 and last.isdigit()) else s.replace(',', '')
        elif has_dot:
            norm = s.replace('.', '') if s.count('.') > 1 else s
        else: norm = s
        v = float(norm); return -v if is_neg else v
    except Exception: return None

def _read_csv_multiencoding_v50(path):
    if not path or not os.path.exists(path): return pd.DataFrame()
    try:
        with open(path, 'rb') as f: raw = f.read()
    except Exception: return pd.DataFrame()
    if not raw: return pd.DataFrame()
    import io as _io
    for enc in ['utf-8-sig', 'utf-8', 'cp1258', 'cp1252', 'latin-1']:
        try: return pd.read_csv(_io.StringIO(raw.decode(enc)))
        except Exception: continue
    return pd.DataFrame()

def _load_csv_db_to_df_v50(path):
    empty = pd.DataFrame(columns=['ticker', 'metric_name', 'period', 'value'])
    df = _read_csv_multiencoding_v50(path)
    if df is None or df.empty: return empty
    df.columns = [str(c).strip().lower() for c in df.columns]
    norm = _normalize_table_v50(df)
    if norm is None or norm.empty: return empty
    norm['ticker'] = norm['ticker'].astype(str).str.strip().str.upper()
    norm['metric_name'] = norm['metric_name'].astype(str).str.strip().str.lower()
    norm['period'] = norm['period'].astype(str).str.strip()
    norm['value'] = pd.to_numeric(norm['value'], errors='coerce')
    return norm.dropna(subset=['value', 'ticker', 'metric_name']).drop_duplicates(subset=['ticker', 'metric_name', 'period'], keep='last').reset_index(drop=True)

@st.cache_data(ttl=3600)
def load_all_data_cached():
    combined_dfs = []
    for k, p in _CSV_DB_PATHS.items():
        if p:
            df_sub = _load_csv_db_to_df_v50(p)
            if not df_sub.empty:
                combined_dfs.append(df_sub)
    if combined_dfs:
        return pd.concat(combined_dfs, ignore_index=True)
    return pd.DataFrame(columns=['ticker', 'metric_name', 'period', 'value'])

long_df = load_all_data_cached()

_LONG_PERIOD_PRIORITY_V48 = ("2026H1", "2026", "2026Q1", "2025H2", "2025H1", "2025", "2024H2", "2024H1", "2024", "2023")
_LONG_METRIC_ALIASES_V48 = {
    "price": ("gia_thi_truong", "gia_co_phieu_hien_tai", "gia_co_phieu", "close"),
    "shares": ("so_cp_luu_hanh", "so_co_phieu", "shares"),
    "total_assets": ("tong_tai_san", "total_assets"),
    "equity": ("von_chu_so_huu", "von_csh", "equity"),
    "profit": ("lnst_cong_ty_me", "loi_nhuan_sau_thue", "profit"),
    "profit_before_tax": ("loi_nhuan_truoc_thue", "profit_before_tax"),
    "revenue": ("doanh_thu_thuan", "revenue"),
    "market_cap": ("von_hoa_ty", "market_cap"),
    "eps": ("eps_cong_ty_me", "eps", "eps_ttm"),
    "bvps": ("bvps_huu_tinh", "bvps"),
    "pe": ("pe", "pe_ttm"), "pb": ("pb", "p_b"), "roe": ("roe", "roe_pct"), "roa": ("roa", "roa_pct"),
    "dividend": ("co_tuc_cp", "co_tuc", "dividend_per_share", "dps"),
}

def _long_period_rank_v48(period):
    p = str(period).strip().upper().replace(" ", "")
    try: return _LONG_PERIOD_PRIORITY_V48.index(p)
    except ValueError: return len(_LONG_PERIOD_PRIORITY_V48) + 1

def _long_get_value_v48(sub, metric_aliases, periods=None):
    if sub is None or sub.empty: return None, None, None
    aliases = {str(x).strip().lower() for x in metric_aliases}
    tmp = sub[sub["_metric_norm"].isin(aliases)].copy()
    if tmp.empty: return None, None, None
    if periods is not None:
        wanted = {str(x).strip().upper() for x in periods}
        tmp = tmp[tmp["_period_norm"].isin(wanted)]
        if tmp.empty: return None, None, None
    tmp["_period_rank"] = tmp["_period_norm"].map(_long_period_rank_v48)
    alias_rank = {str(name).strip().lower(): i for i, name in enumerate(metric_aliases)}
    tmp["_metric_rank"] = tmp["_metric_norm"].map(alias_rank).fillna(len(alias_rank))
    tmp = tmp.sort_values(["_period_rank", "_metric_rank"], kind="stable")
    row = tmp.iloc[0]; val = row["value"]
    try: val_f = float(val) if val is not None else None
    except Exception: val_f = _parse_vn_number_v51(val)
    return val_f, str(row["metric_name"]), str(row["period"])

def _detect_global_scale_v50(long_df):
    if long_df is None or long_df.empty: return 1.0
    mask = long_df['metric_name'].astype(str).str.contains(r'tong_tai_san|total_assets', na=False, regex=True)
    if not mask.any(): return 1.0
    vals = pd.to_numeric(long_df.loc[mask, 'value'], errors='coerce').dropna()
    vals = vals[vals > 0]
    if len(vals) == 0: return 1.0
    max_val = float(vals.max())
    if max_val >= 1e11: return 1e-9
    elif max_val >= 1e8: return 1e-3
    return 1.0

def _build_fin_data_from_long_v50(long_df):
    out = {}
    if long_df is None or long_df.empty: return out
    for ticker in long_df['ticker'].dropna().unique():
        t = _canonical_ticker(ticker)
        if not t: continue
        sub = long_df[long_df['ticker'] == t].copy()
        if sub.empty: continue
        ticker_scale = _detect_global_scale_v50(sub)
        sub["_metric_norm"] = sub["metric_name"].astype(str).str.strip().str.lower()
        sub["_period_norm"] = sub["period"].astype(str).str.strip().str.upper().str.replace(" ", "", regex=False)
        values = {}
        for key, aliases in _LONG_METRIC_ALIASES_V48.items():
            val, _, _ = _long_get_value_v48(sub, aliases)
            if val is not None: values[key] = val
        def money_ty(key):
            v = values.get(key); return 0.0 if v is None else v * ticker_scale
        d = {
            "price": values.get("price", 0.0),
            "eps_ttm": values.get("eps", 0.0), "pe_ttm": values.get("pe", 0.0), "pb": values.get("pb", 0.0),
            "bvps": values.get("bvps", 0.0), "roe_2025": values.get("roe", 0.0), "roa_2025": values.get("roa", 0.0),
            "total_assets_30062026": money_ty("total_assets"),
            "market_cap": values.get("market_cap", 0.0), "shares_outstanding": values.get("shares", 0.0),
            "equity": money_ty("equity"), "lnst_6t2026": money_ty("profit"),
            "div_per_share": values.get("dividend", 0.0), "div_yield": 0.0,
        }
        if d["div_per_share"] > 0 and d["price"] > 0: d["div_yield"] = round((d["div_per_share"] / d["price"]) * 100, 2)
        out[t] = d
    return out

fin_data = _build_fin_data_from_long_v50(long_df)

def _apply_snapshot_to_fin_data(fin_data):
    if not isinstance(fin_data, dict): return fin_data
    if not _HAS_SNAPSHOT or not LATEST_MARKET_SNAPSHOT: return fin_data
    for t_raw, snap in LATEST_MARKET_SNAPSHOT.items():
        t = _canonical_ticker(t_raw)
        if t not in fin_data: fin_data[t] = {}
        d = fin_data[t]
        if snap.get('price_vnd'): d['price'] = float(snap['price_vnd'])
        if snap.get('market_cap_ty'): d['market_cap'] = float(snap['market_cap_ty'])
        if snap.get('shares'): d['shares_outstanding'] = float(snap['shares'])
        if snap.get('dividend_yield_pct') is not None:
            d['div_yield'] = float(snap['dividend_yield_pct'])
    return fin_data

fin_data = _apply_snapshot_to_fin_data(fin_data)

# ============================================================================
# GIAO DIỆN STREAMLIT CHÍNH (UI)
# ============================================================================
st.title("🏛️ FINEX VN Terminal - Hệ Thống Dữ Liệu & Định Giá 500 Mã Cổ Phiếu")
st.markdown("---")

# Sidebar lựa chọn doanh nghiệp & tính năng
st.sidebar.header("🔍 Bộ Lọc & Tra Cứu")
all_tickers = sorted(list(fin_data.keys())) if fin_data else sorted(long_df['ticker'].unique().tolist())

if not all_tickers:
    st.warning("⚠️ Chưa có dữ liệu mã chứng khoán nào trong cơ sở dữ liệu.")
else:
    default_idx = all_tickers.index("FPT") if "FPT" in all_tickers else 0
    selected_ticker = st.sidebar.selectbox("Chọn mã chứng khoán:", all_tickers, index=default_idx)
    
    # Menu chọn tính năng hiển thị
    nav_mode = st.sidebar.radio("Chọn chức năng:", ["📊 Tổng quan & Biểu đồ", "💰 Máy tính Cổ tức", "📋 Dữ liệu Thọ Chi Tiết"])

    # Xử lý lấy thông tin mã được chọn
    ticker_info = fin_data.get(selected_ticker, {})
    sub_df = long_df[long_df['ticker'] == selected_ticker]

    if nav_mode == "📊 Tổng quan & Biểu đồ":
        st.subheader(f"📌 Báo Cáo Tài Chính & Chỉ Số: {selected_ticker}")
        
        # Hiển thị các chỉ số cốt lõi dạng metric
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Giá thị trường", f"{_format_vnd(ticker_info.get('price', 0))} đ")
        col2.metric("Vốn hóa", f"{ticker_info.get('market_cap', 0):,.1f} Tỷ")
        col3.metric("P/E TTM", f"{ticker_info.get('pe_ttm', 0):.2f}")
        col4.metric("ROE", f"{ticker_info.get('roe_2025', 0):.2f}%")

        st.markdown("---")
        st.markdown("### 📈 Biểu đồ trực quan chỉ tiêu tài chính")
        
        if not sub_df.empty:
            # Vẽ biểu đồ trực quan bằng Plotly cho các chỉ tiêu chính có sẵn
            chart_metrics = sub_df[sub_df['metric_name'].isin(['doanh_thu_thuan', 'loi_nhuan_sau_thue', 'tong_tai_san', 'von_chu_so_huu'])]
            if not chart_metrics.empty:
                fig = px.bar(chart_metrics, x='period', y='value', color='metric_name', barmode='group',
                             title=f"Biến động tài chính theo kỳ của {selected_ticker}")
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("Chưa đủ dữ liệu biểu đồ chuyên sâu cho các chỉ tiêu cốt lõi này.")
        else:
            st.info("Không có dữ liệu chi tiết kỳ báo cáo cho mã này.")

    elif nav_mode == "💰 Máy tính Cổ tức":
        st.subheader(f"💰 Mô Phỏng Đầu Tư & Cổ Tức: {selected_ticker}")
        
        col_m1, col_m2 = st.columns(2)
        with col_m1:
            capital_input = st.number_input("Vốn đầu tư dự kiến (VNĐ):", min_value=100_000_000, max_value=50_000_000_000, value=1_000_000_000, step=500_000_000)
        with col_m2:
            market_price_input = st.number_input("Giá mua giả định (VNĐ):", value=float(ticker_info.get('price', 50000) or 50000), step=1000)

        div_per_share_input = st.number_input("Cổ tức tiền mặt dự kiến mỗi CP (VNĐ):", value=float(ticker_info.get('div_per_share', 2000) or 2000), step=500)

        if st.button("🚀 Tính toán kịch bản cổ tức", use_container_width=True):
            shares_bought = _buyable_shares(capital_input, market_price_input)
            div_res = _cash_dividend_actual(shares_bought, div_per_share_input)
            
            st.success(f"🔹 Số lượng cổ phiếu sở hữu: **{_format_shares(shares_bought)} CP**")
            st.info(f"💵 Tổng tiền cổ tức nhận được (Trước thuế): **{_format_vnd(div_res['before_tax'])} VNĐ**")
            if market_price_input > 0:
                div_yield_calc = (div_per_share_input / market_price_input) * 100
                st.write(f"📊 **Tỷ suất cổ tức thực tế (Dividend Yield):** `{div_yield_calc:.2f}%`")

    elif nav_mode == "📋 Dữ liệu Thọ Chi Tiết":
        st.subheader(f"📋 Bảng dữ liệu thô của: {selected_ticker}")
        if not sub_df.empty:
            _safe_dataframe(sub_df, use_container_width=True)
        else:
			st.warning("Không tìm thấy dữ liệu thô.")
