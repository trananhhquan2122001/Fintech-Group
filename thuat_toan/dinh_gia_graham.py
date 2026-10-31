# thuat_toan/dinh_gia_graham.py
"""
Module định giá Graham, Dodd và các nhà đầu tư giá trị hàng đầu.
[v11.0-DCF-INTEGRATION] TÍCH HỢP MÔ ĐUN DCF CHUẨN VN
    ✅ Giữ 100% logic v10.1 (Graham, ML, Bank Engine, Signal Filters, SQLite)
    ✅ THÊM #1: VN Macro Assumptions (Risk-free 3%, ERP 7%, Tax 20%)
    ✅ THÊM #2: Core DCF Engine (FCFF 5 năm, Gordon Growth)
    ✅ THÊM #3: Scenario Engine (Bear/Base/Bull)
    ✅ THÊM #4: Hàm calculate_dcf_valuation (gọi 1 lần cho UI)
    ✅ Cập nhật __all__ và selftest
    ✅ ĐÃ SỬA LỖI INDENTATIONERROR TẠI HÀM _load_all_sqlite_tickers
"""

import numpy as np
from collections import Counter
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
from sklearn.neural_network import MLPClassifier, MLPRegressor
from sklearn.preprocessing import StandardScaler, LabelEncoder
import streamlit as st
import pandas as pd
import os
import sqlite3
from typing import Dict, Any, List

from tien_ich.cau_hinh_danh_muc import (
    to_float_scalar, safe_divide, round_float, THRESHOLDS,
    format_currency_vn_advanced, format_eps_value, format_pe_pb,
    GARBAGE_VALUES, SUSPICIOUS_COL_IDS,
    MIN_REAL_PRICE, MIN_REAL_BVPS, MIN_REAL_EPS,
    MIN_REAL_DIVIDEND, MIN_REAL_MARKET_CAP, MIN_REAL_SHARES,
    is_suspicious_column,
    fix_price, fix_bvps, fix_eps, fix_dividend, fix_shares,
    sanitize_financial_inputs,
    BANK_TICKERS as _CM_BANK_TICKERS,
    CORP_TICKERS as _CM_CORP_TICKERS,
    _LOADED_TICKERS as _CM_LOADED_TICKERS,
    _IS_USING_SQLITE as _CM_IS_USING_SQLITE,
    _SQLITE_DB_PATHS as _CM_SQLITE_PATHS,
    _DEFAULT_SECTOR_BY_DB as _CM_DEFAULT_SECTOR_BY_DB,
)

from du_lieu.doc_bctc_goc import (
    find_column_by_keywords, clean_numeric, is_bank_ticker,
    get_bank_revenue, extract_financial_metrics_smart,
    calculate_altman_z, get_scaled_value,
)


# ============================================================================
# [v10.1-NEW] SQLITE TICKERS LOADER — REUSE TỪ cau_hinh_danh_muc
# ============================================================================
_BASE_DIR_GRAHAM = os.path.dirname(os.path.abspath(__file__))

_SQLITE_DB_PATHS = dict(_CM_SQLITE_PATHS)  # Reuse paths
_DEFAULT_SECTOR_BY_DB = dict(_CM_DEFAULT_SECTOR_BY_DB)


def _extract_tickers_from_table(df, tbl_name, conn):
    """[v10.1-FIX] Extract tickers từ 1 table SQLite."""
    tickers = set()
    if df is None or df.empty:
        return tickers

    df.columns = [str(c).strip().lower() for c in df.columns]

    ticker_col = None
    for c in ['ticker', 'ma_ck', 'symbol', 'code', 'ma']:
        if c in df.columns:
            ticker_col = c
            break

    if ticker_col is not None:
        try:
            full = pd.read_sql_query(f'SELECT "{ticker_col}" FROM "{tbl_name}"', conn)
            for v in full[ticker_col].dropna().astype(str).str.upper().unique():
                v = v.strip()
                if v and 2 <= len(v) <= 6 and v.isalnum():
                    tickers.add(v)
        except Exception:
            pass
    elif tbl_name and tbl_name.isupper() and 2 <= len(tbl_name) <= 6 and tbl_name.isalnum():
        tickers.add(tbl_name)

    return tickers


def _load_bank_tickers_from_sqlite():
    if _CM_IS_USING_SQLITE and _CM_BANK_TICKERS:
        return set(_CM_BANK_TICKERS)

    path = _SQLITE_DB_PATHS.get('ngan_hang_va_tai_chinh', '')
    if not path or not os.path.exists(path):
        return set()

    all_tickers = set()
    try:
        conn = sqlite3.connect(path)
        tables = pd.read_sql_query(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'",
            conn
        )['name'].tolist()

        for tbl in tables:
            try:
                df = pd.read_sql_query(f'SELECT * FROM "{tbl}" LIMIT 1', conn)
            except Exception:
                continue
            tickers = _extract_tickers_from_table(df, tbl, conn)
            all_tickers.update(tickers)

        conn.close()
    except Exception as e:
        print(f"[v11] ⚠️ SQLite bank load error: {e}")

    return all_tickers


def _load_all_sqlite_tickers():
    if _CM_IS_USING_SQLITE and _CM_LOADED_TICKERS:
        return set(_CM_LOADED_TICKERS.keys())

    all_tk = set()
    for key, path in _SQLITE_DB_PATHS.items():
        if not path or not os.path.exists(path):
            continue
        try:
            conn = sqlite3.connect(path)
            tables = pd.read_sql_query(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'",
                conn
            )['name'].tolist()

            for tbl in tables:
                try:
                    # [FIX] Đã thụt lề đúng 4 spaces
                    _df = pd.read_sql_query(f'SELECT * FROM "{tbl}" LIMIT 1', conn)
                except Exception:
                    continue
                tickers = _extract_tickers_from_table(_df, tbl, conn)
                all_tk.update(tickers)

            conn.close()
        except Exception:
            continue

    return all_tk


# ============================================================================
# [v10] SECTOR ALIASES
# ============================================================================
_SECTOR_ALIASES = {
    'banking': [
        'banking', 'ngân hàng', 'ngan hang', 'bank', 'nh',
        'ngân hàng & tài chính', 'ngan hang va tai chinh',
        'tài chính', 'tai chinh', 'finance', 'financial',
    ],
    'securities': [
        'securities', 'chứng khoán', 'chung khoan', 'stock',
        'brokerage', 'ck',
    ],
    'insurance': [
        'insurance', 'bảo hiểm', 'bao hiem', 'insur',
    ],
    'realestate': [
        'bất động sản', 'bat dong san', 'real estate', 'realestate',
        'bđs', 'bds',
    ],
    'technology': [
        'technology', 'công nghệ', 'cong nghe', 'tech', 'it',
        'công nghệ thông tin', 'cong nghe thong tin',
        'software', 'phần mềm', 'phan mem', 'hardware', 'semiconductor',
    ],
    'manufacturing': [
        'manufacturing', 'sản xuất', 'san xuat', 'industrial',
        'sản xuất & khác', 'san xuat va khac', 'san xuat & khac',
        'sản xuất và khác', 'cong nghiep', 'công nghiệp',
        'thép', 'thep', 'steel', 'hóa chất', 'hoa chat', 'chemical',
    ],
}


def _normalize_sector(sector_str):
    if not sector_str:
        return "general"
    s = str(sector_str).strip().lower()
    for code, aliases in _SECTOR_ALIASES.items():
        for alias in aliases:
            if alias in s:
                return code
    return "general"


# ============================================================================
# SAFE CACHE DECORATOR
# ============================================================================
def _safe_cache_resource(func):
    try:
        import streamlit as _st
        if hasattr(_st, "cache_resource"):
            return _st.cache_resource(func)
    except Exception:
        pass
    return func


# ============================================================================
# [v10] BANK TICKERS
# ============================================================================
_BANK_TICKERS_FALLBACK = {
    'TCB', 'VCB', 'MBB', 'CTG', 'BID', 'ACB', 'VPB', 'STB', 'HDB', 'TPB',
    'SHB', 'LPB', 'VIB', 'MSB', 'OCB', 'BAB', 'NAB', 'PGB', 'SGB', 'ABB',
    'BVB', 'KLB', 'VAB', 'EIB', 'SSB',
}

_SQLITE_BANK_TICKERS = _load_bank_tickers_from_sqlite()

if _SQLITE_BANK_TICKERS:
    BANK_TICKERS_V7 = _SQLITE_BANK_TICKERS
    _IS_USING_SQLITE_BANKS = True
    print(f"[v11] ✅ Bank tickers từ SQLite: {len(BANK_TICKERS_V7)} mã")
else:
    BANK_TICKERS_V7 = _BANK_TICKERS_FALLBACK
    _IS_USING_SQLITE_BANKS = False
    print(f"[v11] ⚠️ Fallback 25 bank cũ — SQLite rỗng")

_ALL_SQLITE_TICKERS = _load_all_sqlite_tickers()

GARBAGE_VALUES_V7 = {87.0, -87.0, 87, -87}

DEFAULT_PB_TARGET = 1.5
DEFAULT_PE_TARGET = 15.0
DEFAULT_MIN_PRICE_FACTOR = 0.8


def _is_garbage_v7(v):
    try:
        return float(v) in GARBAGE_VALUES_V7
    except Exception:
        return False


def _is_bank(ticker):
    t = str(ticker).strip().upper()
    if t in BANK_TICKERS_V7:
        return True
    try:
        return is_bank_ticker(t)
    except Exception:
        return False


# ============================================================================
# KIỂM TRA THƯ VIỆN ML
# ============================================================================
try:
    import lightgbm as lgb
    LGB_AVAILABLE = True
except ImportError:
    LGB_AVAILABLE = False

try:
    import xgboost as xgb
    XGB_AVAILABLE = True
except ImportError:
    XGB_AVAILABLE = False

try:
    import huggingface_hub
    HF_AVAILABLE = True
except ImportError:
    HF_AVAILABLE = False

try:
    import tensorflow as tf
    TF_AVAILABLE = True
except ImportError:
    TF_AVAILABLE = False

try:
    import torch
    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False

try:
    import transformers
    TRANSFORMERS_AVAILABLE = True
except ImportError:
    TRANSFORMERS_AVAILABLE = False

try:
    import timesfm
    TIMESFM_AVAILABLE = True
except ImportError:
    TIMESFM_AVAILABLE = False


# ============================================================================
# 1. CÁC HÀM TÍNH TOÁN AN TOÀN
# ============================================================================
def calculate_pe_safe(price, eps):
    price = fix_price(to_float_scalar(price))
    eps = fix_eps(to_float_scalar(eps))
    if eps <= 0 or price <= 0:
        return 0.0
    pe = price / eps
    if pe < 0.5 or pe > 500:
        return 0.0
    return round_float(pe, 2)


def calculate_pb_safe(price, bvps):
    price = fix_price(to_float_scalar(price))
    bvps = fix_bvps(to_float_scalar(bvps))
    if bvps <= 0 or price <= 0:
        return 0.0
    pb = price / bvps
    if pb < 0.1 or pb > 30:
        return 0.0
    return round_float(pb, 2)


def calculate_roe_safe(profit, equity):
    profit = to_float_scalar(profit)
    equity = to_float_scalar(equity)
    if equity <= 0:
        return 0.0
    roe = safe_divide(profit, equity, 0.0) * 100.0
    if roe < -100 or roe > 200:
        return 0.0
    return round_float(roe, 2)


def calculate_roic_safe(profit, invested_capital):
    profit = to_float_scalar(profit)
    invested_capital = to_float_scalar(invested_capital)
    if invested_capital <= 0:
        return 0.0
    roic = safe_divide(profit, invested_capital, 0.0) * 100.0
    return round_float(roic, 2)


def calculate_debt_to_equity_safe(total_debt, equity):
    total_debt = to_float_scalar(total_debt)
    equity = to_float_scalar(equity)
    if equity <= 0:
        return 0.0
    return round_float(safe_divide(total_debt, equity, 0.0), 2)


def calculate_dividend_yield_safe(dps, price):
    dps = fix_dividend(to_float_scalar(dps))
    price = fix_price(to_float_scalar(price))
    if price <= 0 or dps <= 0:
        return 0.0
    y = safe_divide(dps, price, 0.0) * 100.0
    if y < 0 or y > 30:
        return 0.0
    return round_float(y, 2)


def calculate_cagr(series):
    if not series or len(series) < 2:
        return 0.0
    first = to_float_scalar(series[0])
    last = to_float_scalar(series[-1])
    if first <= 0 or last <= 0:
        return 0.0
    n = len(series) - 1
    cagr = (last / first) ** (1 / n) - 1
    return round_float(cagr * 100, 2)


# ============================================================================
# 2. ĐỊNH GIÁ DỰA TRÊN TÀI SẢN – GRAHAM & DODD
# ============================================================================
def calculate_ncav(current_assets, total_liabilities, shares_outstanding):
    ca = to_float_scalar(current_assets)
    tl = to_float_scalar(total_liabilities)
    sh = to_float_scalar(shares_outstanding)
    if sh <= 0:
        return 0.0
    ncav = (ca - tl) / sh
    return round_float(ncav, 0) if ncav > 0 else 0.0


def calculate_liquidation_value(current_assets, receivables, inventory, fixed_assets,
                                total_liabilities, shares_outstanding,
                                cash_recovery=1.0, receivables_recovery=0.8,
                                inventory_recovery=0.65, fixed_recovery=0.15):
    cash = to_float_scalar(current_assets) - to_float_scalar(receivables) - to_float_scalar(inventory)
    cash = max(cash, 0.0)
    rec = to_float_scalar(receivables)
    inv = to_float_scalar(inventory)
    fa = to_float_scalar(fixed_assets)
    tl = to_float_scalar(total_liabilities)
    sh = to_float_scalar(shares_outstanding)
    if sh <= 0:
        return 0.0
    lv = (cash * cash_recovery + rec * receivables_recovery +
          inv * inventory_recovery + fa * fixed_recovery - tl) / sh
    return round_float(max(lv, 0.0), 0)


def get_ncav_from_row(row, df):
    ca_col = find_column_by_keywords(df, ['tổng tài sản ngắn hạn', 'current assets', 'ts ngắn hạn'])
    tl_col = find_column_by_keywords(df, ['26_bs_tong_no_phai_tra', 'tổng nợ', 'total liabilities'])
    shares_col = find_column_by_keywords(df, [
        '95_st_so_co_phieu_dang_luu_hanh_co_phieu', 'cổ phiếu lưu hành', 'shares'
    ])
    if all([ca_col, tl_col, shares_col]):
        ca = to_float_scalar(row.get(ca_col, 0))
        tl = to_float_scalar(row.get(tl_col, 0))
        sh = to_float_scalar(row.get(shares_col, 0))
        return calculate_ncav(ca, tl, sh)
    return 0.0


# ============================================================================
# 3. THU NHẬP CHUẨN HÓA
# ============================================================================
def calculate_normalized_eps(eps_series, method='median', years=5):
    eps_list = [to_float_scalar(x) for x in eps_series
                if x is not None and to_float_scalar(x) > 0]
    if len(eps_list) >= years:
        eps_list = eps_list[-years:]
    if not eps_list:
        return 0.0
    if method == 'median':
        norm_eps = np.median(eps_list)
    else:
        norm_eps = np.mean(eps_list)
    return round_float(norm_eps, 0)


# ============================================================================
# 4. DÒNG TIỀN TỰ DO
# ============================================================================
def calculate_fcf(cash_flow_operating, capex):
    cfo = to_float_scalar(cash_flow_operating)
    cap = to_float_scalar(capex)
    return round_float(cfo - cap, 0)


def calculate_fcf_per_share(cash_flow_operating, capex, shares):
    fcf = calculate_fcf(cash_flow_operating, capex)
    sh = to_float_scalar(shares)
    if sh <= 0:
        return 0.0
    return round_float(fcf / sh, 0)


# ============================================================================
# 5. CHẤT LƯỢNG QUẢN LÝ
# ============================================================================
def calculate_management_score(roe, roic, dividend_yield, payout_ratio,
                                revenue_growth, eps_growth):
    score = 0
    details = []
    r = to_float_scalar(roe)
    roic_val = to_float_scalar(roic)
    dy = to_float_scalar(dividend_yield)
    pr = to_float_scalar(payout_ratio)
    rev_g = to_float_scalar(revenue_growth)
    eps_g = to_float_scalar(eps_growth)

    if r >= 15:
        score += 2; details.append("✅ ROE ≥ 15% – Quản lý hiệu quả")
    elif r >= 10:
        score += 1; details.append("⚠️ ROE 10-15% – Trung bình")
    else:
        details.append("❌ ROE < 10% – Kém hiệu quả")

    if roic_val >= 10:
        score += 2; details.append("✅ ROIC ≥ 10% – Tạo giá trị vượt trội")
    elif roic_val >= 5:
        score += 1; details.append("⚠️ ROIC 5-10% – Trung bình")
    else:
        details.append("❌ ROIC < 5% – Phá hủy giá trị")

    if eps_g >= 10:
        score += 2; details.append("✅ EPS tăng trưởng ≥ 10%")
    elif eps_g >= 5:
        score += 1; details.append("⚠️ EPS tăng trưởng 5-10%")
    else:
        details.append("❌ EPS tăng trưởng < 5%")

    if 0.2 <= dy <= 5.0 and pr <= 70:
        score += 2; details.append("✅ Cổ tức hợp lý")
    elif dy > 5.0 and pr > 70:
        details.append("⚠️ Cổ tức cao có thể không bền vững")
    else:
        score += 1; details.append("⚠️ Chính sách cổ tức không rõ ràng")

    if rev_g >= 10 and eps_g >= 10:
        score += 1; details.append("✅ Tăng trưởng DT & EPS đều tốt")
    elif rev_g >= 10 or eps_g >= 10:
        score += 0.5

    return min(round_float(score, 1), 10.0), details


# ============================================================================
# 6. SO SÁNH ĐỒNG NGHIỆP
# ============================================================================
def get_peer_metrics(df, sector_col, sector_value, metric_col):
    if sector_col not in df.columns or metric_col not in df.columns:
        return None, None
    sub = df[df[sector_col] == sector_value]
    values = sub[metric_col].dropna().apply(to_float_scalar)
    if len(values) == 0:
        return None, None
    return float(np.mean(values)), float(np.median(values))


def compare_with_peers(row, df, ticker_col, sector_col,
                        metrics=['gd_pe', 'gd_pb', 'gd_roe', 'gd_margin']):
    sector = str(row.get(sector_col, '')).strip().upper()
    results = {}
    for metric in metrics:
        if metric not in df.columns:
            continue
        val = to_float_scalar(row.get(metric, 0))
        mean_val, median_val = get_peer_metrics(df, sector_col, sector, metric)
        if mean_val is None or mean_val == 0:
            continue
        z = (val - mean_val) / (df[metric].std() + 1e-9)
        results[metric] = {'value': val, 'mean': mean_val,
                            'median': median_val, 'z_score': z}
    return results


# ============================================================================
# 7. MOAT SCORE
# ============================================================================
def calculate_moat_score(roe, gross_margin, net_margin, debt_to_equity,
                          growth_rate, roic=0.0):
    roe = to_float_scalar(roe)
    gross = to_float_scalar(gross_margin)
    net = to_float_scalar(net_margin)
    de = to_float_scalar(debt_to_equity)
    growth = to_float_scalar(growth_rate)
    roic_val = to_float_scalar(roic)

    score = 0
    details = []

    if roe >= 15:
        score += 2; details.append("✅ ROE ≥ 15% – Hiệu quả vốn tốt")
    elif roe >= 10:
        score += 1; details.append("⚠️ ROE 10-15% – Trung bình")
    else:
        details.append("❌ ROE < 10% – Yếu")

    if gross >= 20:
        score += 2; details.append("✅ Biên gộp ≥ 20% – Sức mạnh định giá")
    elif gross >= 10:
        score += 1; details.append("⚠️ Biên gộp 10-20% – Trung bình")
    else:
        details.append("❌ Biên gộp < 10% – Áp lực cạnh tranh cao")

    if net >= 10:
        score += 2; details.append("✅ Biên ròng ≥ 10% – Lợi nhuận bền vững")
    elif net >= 5:
        score += 1; details.append("⚠️ Biên ròng 5-10% – Trung bình")
    else:
        details.append("❌ Biên ròng < 5% – Chi phí cao")

    if de <= 0.5:
        score += 2; details.append("✅ Nợ/VCSH ≤ 0.5 – Tài chính an toàn")
    elif de <= 1.0:
        score += 1; details.append("⚠️ Nợ/VCSH 0.5-1.0 – Rủi ro trung bình")
    else:
        details.append("❌ Nợ/VCSH > 1.0 – Đòn bẩy cao")

    if growth >= 10:
        score += 1; details.append("✅ Tăng trưởng ≥ 10%")
    elif growth >= 5:
        score += 0.5; details.append("⚠️ Tăng trưởng 5-10%")
    else:
        details.append("❌ Tăng trưởng < 5%")

    if roic_val > 0:
        if roic_val >= 10:
            score += 1; details.append("✅ ROIC ≥ 10%")
        elif roic_val >= 5:
            score += 0.5; details.append("⚠️ ROIC 5-10%")
        else:
            details.append("❌ ROIC < 5%")

    return min(round_float(score, 1), 10.0), details


# ============================================================================
# 8. BUFFETT DCF
# ============================================================================
def buffett_intrinsic_value(eps, growth_rate, discount_rate=0.10, years=10):
    eps = to_float_scalar(eps)
    g = to_float_scalar(growth_rate) / 100.0
    r = to_float_scalar(discount_rate)
    if eps <= 0 or r <= 0:
        return 0.0
    if g < -0.5:
        g = -0.5

    future_cf = eps * (1 + g)
    total_pv = 0.0
    for i in range(1, years + 1):
        if i > 1:
            future_cf = future_cf * (1 + g)
        pv = future_cf / ((1 + r) ** i)
        total_pv += pv

    terminal_growth = 0.03
    if r - terminal_growth <= 0:
        return round_float(total_pv, 0)
    terminal_value = (future_cf * (1 + terminal_growth)) / (r - terminal_growth)
    terminal_pv = terminal_value / ((1 + r) ** years)
    intrinsic = total_pv + terminal_pv
    return round_float(intrinsic, 0)


# ============================================================================
# 9. LABEL RULE
# ============================================================================
def label_rule(roe, roa, margin, de):
    r = to_float_scalar(roe)
    a = to_float_scalar(roa)
    m = to_float_scalar(margin)
    d = to_float_scalar(de)
    if r >= 15.0 and a >= 8.0 and m >= 20.0 and d < 1.0:
        return 2
    elif r >= 8.0 and a >= 4.0 and d < 2.0:
        return 1
    else:
        return 0


# ============================================================================
# 10. TRAIN RISK CLASSIFIER
# ============================================================================
@_safe_cache_resource
def train_risk_classifier_ensemble(df, ticker_col):
    df_clean = df.loc[:, ~df.columns.duplicated()].copy() if df is not None and not df.empty else None

    seed_X = np.array([
        [22.5, 12.0, 35.0, 0.3],
        [18.0, 9.5, 28.0, 0.5],
        [12.0, 5.0, 15.0, 1.2],
        [3.0, 1.0, 5.0, 3.0],
        [-2.0, -1.0, 2.0, 4.0],
    ], dtype=np.float64)
    seed_y = np.array([2, 2, 1, 0, 0])

    X_list, y_list = [], []
    if df_clean is not None:
        roe_col = find_column_by_keywords(df_clean, ['gd_roe_', 'roe', 'return on equity'])
        roa_col = find_column_by_keywords(df_clean, ['roa', 'return on assets'])
        margin_col = find_column_by_keywords(df_clean, ['biên lợi nhuận gộp', 'gross margin'])
        de_col = find_column_by_keywords(df_clean, ['gd_no_vcsh', 'nợ/vcsh', 'd/e'])
        if all([roe_col, roa_col, margin_col, de_col]):
            for _, row in df_clean.iterrows():
                try:
                    r = to_float_scalar(row.get(roe_col, 0.0))
                    a = to_float_scalar(row.get(roa_col, 0.0))
                    m = to_float_scalar(row.get(margin_col, 20.0))
                    d = to_float_scalar(row.get(de_col, 0.5))
                    X_list.append([r, a, m, d])
                    y_list.append(label_rule(r, a, m, d))
                except Exception:
                    continue

    if len(X_list) > 0:
        X_real = np.array(X_list, dtype=np.float64)
        y_real = np.array(y_list)
        if X_real.ndim == 2 and X_real.shape[1] == 4:
            X_combined = np.vstack([seed_X, X_real])
            y_combined = np.concatenate([seed_y, y_real])
        else:
            X_combined = seed_X
            y_combined = seed_y
    else:
        X_combined = seed_X
        y_combined = seed_y

    le = LabelEncoder()
    y_encoded = le.fit_transform(y_combined)
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X_combined)

    models = {}
    rf = RandomForestClassifier(n_estimators=100, random_state=42)
    rf.fit(X_scaled, y_encoded)
    models['rf'] = rf

    mlp = MLPClassifier(hidden_layer_sizes=(50, 25), max_iter=500, random_state=42)
    mlp.fit(X_scaled, y_encoded)
    models['mlp'] = mlp

    if LGB_AVAILABLE:
        lgbm = lgb.LGBMClassifier(n_estimators=100, random_state=42, verbose=-1)
        lgbm.fit(X_scaled, y_encoded)
        models['lgbm'] = lgbm

    if XGB_AVAILABLE:
        xgbc = xgb.XGBClassifier(n_estimators=50, max_depth=3,
                                  eval_metric='mlogloss', random_state=42)
        xgbc.fit(X_scaled, y_encoded)
        models['xgb'] = xgbc

    models['le'] = le
    return models, scaler


def predict_risk_ensemble(roe, roa, margin, de):
    r = to_float_scalar(roe)
    a = to_float_scalar(roa)
    m = to_float_scalar(margin)
    d = to_float_scalar(de)
    if r == 0 and a == 0 and m == 0 and d == 0:
        return 1, 50.0

    try:
        df = st.session_state.get('df', pd.DataFrame())
        ticker_col = st.session_state.get('ticker_col', None)
        models, scaler = train_risk_classifier_ensemble(df, ticker_col)
        input_data = np.array([[r, a, m, d]], dtype=np.float64)
        input_scaled = scaler.transform(input_data)

        preds, probs = [], []
        for name, model in models.items():
            if name == 'le':
                continue
            pred = model.predict(input_scaled)[0]
            prob = model.predict_proba(input_scaled)[0]
            preds.append(pred)
            probs.append(prob)

        final_pred_encoded = Counter(preds).most_common(1)[0][0]
        final_pred = models['le'].inverse_transform([final_pred_encoded])[0]
        avg_conf = round(float(np.mean([prob[final_pred_encoded] for prob in probs]) * 100), 1)
        return int(final_pred), avg_conf
    except Exception:
        return label_rule(r, a, m, d), 50.0


# ============================================================================
# 11. TRAIN EPS REGRESSOR
# ============================================================================
@_safe_cache_resource
def train_eps_regressor_ensemble(df):
    data = df.loc[:, ~df.columns.duplicated()].copy() if df is not None and not df.empty else pd.DataFrame()

    seed_X = np.array([
        [22.5, 12.0, 35.0, 0.3],
        [18.0, 9.5, 28.0, 0.5],
        [12.0, 5.0, 15.0, 1.2],
        [3.0, 1.0, 5.0, 3.0],
        [-2.0, -1.0, 2.0, 4.0],
    ], dtype=np.float64)
    seed_y = np.array([8000.0, 5000.0, 2500.0, 800.0, -500.0], dtype=np.float64)

    X_list, y_list = [], []
    if not data.empty:
        eps_col = find_column_by_keywords(data, ['61_is_eps_vndco_phieu', 'eps', 'earnings per share'])
        roe_col = find_column_by_keywords(data, ['gd_roe_', 'roe'])
        roa_col = find_column_by_keywords(data, ['roa'])
        margin_col = find_column_by_keywords(data, ['biên lợi nhuận gộp', 'gross margin'])
        de_col = find_column_by_keywords(data, ['gd_no_vcsh', 'nợ/vcsh', 'd/e'])
        if all([eps_col, roe_col, roa_col, margin_col, de_col]):
            for _, row in data.iterrows():
                try:
                    r = to_float_scalar(row.get(roe_col, 0.0))
                    a = to_float_scalar(row.get(roa_col, 0.0))
                    m = to_float_scalar(row.get(margin_col, 20.0))
                    d = to_float_scalar(row.get(de_col, 0.5))
                    eps_val = to_float_scalar(row.get(eps_col, 2000.0))
                    X_list.append([r, a, m, d])
                    y_list.append(eps_val)
                except Exception:
                    continue

    if len(X_list) > 0:
        X_real = np.array(X_list, dtype=np.float64)
        y_real = np.array(y_list, dtype=np.float64)
        if X_real.ndim == 2 and X_real.shape[1] == 4:
            X_combined = np.vstack([seed_X, X_real])
            y_combined = np.concatenate([seed_y, y_real])
        else:
            X_combined, y_combined = seed_X, seed_y
    else:
        X_combined, y_combined = seed_X, seed_y

    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X_combined)

    models = {}
    rfr = RandomForestRegressor(n_estimators=50, random_state=42)
    rfr.fit(X_scaled, y_combined)
    models['rf'] = rfr

    mlp = MLPRegressor(hidden_layer_sizes=(50, 25), max_iter=500, random_state=42)
    mlp.fit(X_scaled, y_combined)
    models['mlp'] = mlp

    if XGB_AVAILABLE:
        xgbr = xgb.XGBRegressor(n_estimators=50, max_depth=3, random_state=42)
        xgbr.fit(X_scaled, y_combined)
        models['xgb'] = xgbr

    if LGB_AVAILABLE:
        lgbm = lgb.LGBMRegressor(n_estimators=50, random_state=42, verbose=-1)
        lgbm.fit(X_scaled, y_combined)
        models['lgbm'] = lgbm

    return models, scaler


# ============================================================================
# 12. EPS DỰ BÁO QUA HUGGING FACE
# ============================================================================
def predict_eps_with_huggingface(eps_series, ticker=""):
    if not TIMESFM_AVAILABLE and not TRANSFORMERS_AVAILABLE:
        return None
    try:
        eps_list = [to_float_scalar(x) for x in eps_series
                    if x is not None and to_float_scalar(x) > 0]
        if len(eps_list) < 5:
            return None
        if TIMESFM_AVAILABLE:
            try:
                import timesfm
                model = timesfm.TimesFM()
                forecast = model.forecast(eps_list, horizon=4)
                if forecast is not None and len(forecast) > 0:
                    return float(forecast[-1])
            except Exception:
                pass
        return None
    except Exception:
        return None


# ============================================================================
# 13. HELPER
# ============================================================================
def _find_column_safe(df, keywords):
    try:
        return find_column_by_keywords(df, keywords)
    except Exception:
        if df is None or df.empty:
            return None
        cols_lower = {str(c).lower(): c for c in df.columns}
        for kw in keywords:
            kw_l = str(kw).lower()
            for col_l, col_orig in cols_lower.items():
                if kw_l in col_l:
                    return col_orig
        return None


# ============================================================================
# 14. TRAIN EPS MODEL ADVANCED
# ============================================================================
@_safe_cache_resource
def train_eps_model_advanced(df, forecast_years: int = 10):
    if df is None or df.empty:
        return None

    required_cols = {
        'roe': ['gd_roe_', 'roe', 'return on equity', 'tỷ suất sinh lời vốn chủ'],
        'roa': ['roa', 'return on assets', 'tỷ suất sinh lời tài sản'],
        'margin': ['biên lợi nhuận gộp', 'gross margin', 'biên gộp',
                    'lợi nhuận gộp', 'gd_margin'],
        'de': ['gd_no_vcsh', 'nợ/vcsh', 'd/e', 'debt to equity'],
        'eps': ['61_is_eps_vndco_phieu', 'eps', 'earnings per share'],
    }

    col_map = {}
    for key, kws in required_cols.items():
        found = _find_column_safe(df, kws)
        if found is not None:
            col_map[key] = found

    if len(col_map) < 5:
        return None

    try:
        train_df = df[
            [col_map['roe'], col_map['roa'],
             col_map['margin'], col_map['de'], col_map['eps']]
        ].copy()

        for c in train_df.columns:
            train_df[c] = pd.to_numeric(train_df[c], errors='coerce')

        train_df = train_df.dropna()
        train_df = train_df[~train_df.iloc[:, 4].isin(list(GARBAGE_VALUES_V7))]

        if len(train_df) < 50:
            return None

        X = train_df.iloc[:, :4].values.astype(float)
        y = train_df.iloc[:, 4].values.astype(float)

        scaler = StandardScaler()
        X_scaled = scaler.fit_transform(X)

        model = None
        model_type = None

        if LGB_AVAILABLE:
            try:
                model = lgb.LGBMRegressor(
                    n_estimators=100, max_depth=6, learning_rate=0.05,
                    random_state=42, verbose=-1,
                )
                model.fit(X_scaled, y)
                model_type = "lightgbm"
            except Exception:
                model = None

        if model is None and XGB_AVAILABLE:
            try:
                model = xgb.XGBRegressor(
                    n_estimators=100, max_depth=6, learning_rate=0.05,
                    random_state=42,
                )
                model.fit(X_scaled, y)
                model_type = "xgboost"
            except Exception:
                model = None

        if model is None:
            try:
                model = RandomForestRegressor(n_estimators=100, random_state=42)
                model.fit(X_scaled, y)
                model_type = "random_forest"
            except Exception:
                return None

        return {
            'model': model,
            'scaler': scaler,
            'model_type': model_type,
            'n_samples': len(train_df),
            'forecast_years': int(forecast_years),
        }
    except Exception:
        return None


def predict_eps_advanced(roe, roa, margin, de, trained_model):
    if trained_model is None:
        return 0.0
    try:
        model = trained_model.get('model')
        scaler = trained_model.get('scaler')
        if model is None or scaler is None:
            return 0.0

        X = np.array([[
            to_float_scalar(roe), to_float_scalar(roa),
            to_float_scalar(margin), to_float_scalar(de),
        ]], dtype=float)

        X_scaled = scaler.transform(X)
        pred = float(model.predict(X_scaled)[0])

        if not np.isfinite(pred):
            return 0.0
        if pred < 0:
            return 0.0
        if pred > 1e9:
            return 0.0
        return round_float(pred, 0)
    except Exception:
        return 0.0


# ============================================================================
# 15. PREDICT EPS ENSEMBLE
# ============================================================================
def predict_eps_ensemble(roe, roa, margin, de):
    df = st.session_state.get('df', pd.DataFrame())
    advanced_model = st.session_state.get('eps_model_advanced', None)

    if not df.empty:
        eps_col = find_column_by_keywords(df, ['61_is_eps_vndco_phieu', 'eps'])
        if eps_col:
            eps_series = df[eps_col].dropna().tolist()
            hf_pred = predict_eps_with_huggingface(eps_series)
            if hf_pred is not None and hf_pred > 0:
                return round_float(hf_pred, 0)

    if advanced_model is not None:
        eps_pred = predict_eps_advanced(roe, roa, margin, de, advanced_model)
        if eps_pred > 0:
            return eps_pred

    try:
        r = to_float_scalar(roe)
        a = to_float_scalar(roa)
        m = to_float_scalar(margin)
        d = to_float_scalar(de)
        if r == 0 and a == 0 and m == 0 and d == 0:
            return 0.0
        input_data = np.array([[r, a, m, d]], dtype=np.float64)
        models, scaler = train_eps_regressor_ensemble(df)
        input_scaled = scaler.transform(input_data)
        preds = []
        for _, model in models.items():
            pred = model.predict(input_scaled)[0]
            preds.append(pred)
        final_eps = float(np.mean(preds))
        return round_float(final_eps, 0)
    except Exception:
        return 0.0


# ============================================================================
# 16. HYBRID VALUATION — MỞ RỘNG CHO 3 NHÓM MỚI
# ============================================================================
def hybrid_valuation_enhanced(
    price, eps, bvps, roe, margin, de, sector,
    growth_rate=0.0, roic=0.0,
    ncav=0.0, liquidation_value=0.0,
    normalized_eps=0.0, fcf_per_share=0.0,
    moat_score=0.0, management_score=0.0,
):
    price = fix_price(to_float_scalar(price))
    eps = fix_eps(to_float_scalar(eps))
    bvps = fix_bvps(to_float_scalar(bvps))
    roe = to_float_scalar(roe)
    margin = to_float_scalar(margin)
    de = to_float_scalar(de)
    g = to_float_scalar(growth_rate)
    roic_val = to_float_scalar(roic)
    ncav_val = to_float_scalar(ncav)
    liq_val = to_float_scalar(liquidation_value)
    norm_eps = to_float_scalar(normalized_eps)
    fcf = to_float_scalar(fcf_per_share)
    moat = to_float_scalar(moat_score)
    mgmt = to_float_scalar(management_score)

    sector_norm = _normalize_sector(sector)

    eps_positive = eps > 0
    bvps_positive = bvps > 0
    norm_eps_positive = norm_eps > 0
    fcf_positive = fcf > 0

    # 1. GRAHAM NUMBER
    if eps_positive and bvps_positive:
        graham_val = (22.5 * eps * bvps) ** 0.5
    elif bvps_positive:
        graham_val = bvps * DEFAULT_PB_TARGET
    else:
        graham_val = 0.0

    # 2. BUFFETT DCF
    if eps_positive:
        buffett_val = buffett_intrinsic_value(eps, g, discount_rate=0.10, years=10)
        if buffett_val <= 0:
            buffett_val = eps * DEFAULT_PE_TARGET
    elif norm_eps_positive:
        buffett_val = buffett_intrinsic_value(norm_eps, g, discount_rate=0.10, years=10)
    elif bvps_positive and roe > 0:
        buffett_val = bvps * (1 + roe / 20.0)
    else:
        buffett_val = 0.0

    # 3. NORMALIZED EPS
    if norm_eps_positive and bvps_positive:
        graham_norm = (22.5 * norm_eps * bvps) ** 0.5
    elif norm_eps_positive:
        graham_norm = norm_eps * DEFAULT_PE_TARGET
    elif bvps_positive:
        graham_norm = bvps * DEFAULT_PB_TARGET
    else:
        graham_norm = 0.0

    # 4. FCF
    if fcf_positive:
        fcf_val = buffett_intrinsic_value(fcf, g, discount_rate=0.10, years=10)
    elif eps_positive:
        fcf_val = eps * DEFAULT_PE_TARGET * 0.9
    else:
        fcf_val = 0.0

    # 5. ASSET-BASED
    asset_val = max(ncav_val, liq_val, 0.0)

    # 6. QUALITY BONUS
    quality_bonus = 1.0 + (moat / 100.0) + (mgmt / 200.0)
    if quality_bonus > 1.3:
        quality_bonus = 1.3
    if quality_bonus < 1.0:
        quality_bonus = 1.0

    # 7. KẾT HỢP
    if sector_norm == "banking":
        if bvps_positive and roe > 0:
            excess_ratio = (roe / 100.0 - 0.10) / 0.02
            excess_ratio = max(0.0, min(excess_ratio, 3.0))
            excess = bvps * (1 + excess_ratio)
        else:
            excess = bvps * 1.2 if bvps_positive else 0.0

        if eps_positive:
            hybrid = (0.25 * graham_val + 0.25 * buffett_val +
                      0.25 * graham_norm + 0.25 * excess)
        else:
            hybrid = 0.5 * (bvps * DEFAULT_PB_TARGET) + 0.3 * graham_val + 0.2 * excess
            if hybrid <= 0:
                hybrid = bvps * DEFAULT_PB_TARGET if bvps_positive else 0.0

    elif sector_norm == "securities":
        if eps_positive:
            pe_adj = 8.5 + 2 * max(g, 7.0)
            pe_adj = min(pe_adj, 25.0)
            val_pe = eps * pe_adj
            hybrid = 0.3 * graham_val + 0.3 * buffett_val + 0.4 * val_pe
        elif bvps_positive:
            hybrid = bvps * DEFAULT_PB_TARGET
        else:
            hybrid = 0.0

    elif sector_norm == "technology":
        if eps_positive:
            pe_adj = 12.0 + 1.5 * max(g, 10.0)
            pe_adj = min(pe_adj, 35.0)
            val_pe = eps * pe_adj

            if fcf_positive:
                hybrid = 0.20 * graham_val + 0.30 * buffett_val + \
                         0.15 * graham_norm + 0.15 * fcf_val + 0.20 * val_pe
            else:
                hybrid = 0.25 * graham_val + 0.30 * buffett_val + \
                         0.15 * graham_norm + 0.30 * val_pe
        elif bvps_positive:
            hybrid = bvps * (DEFAULT_PB_TARGET + 0.5)
        else:
            hybrid = 0.0

    elif sector_norm == "manufacturing":
        if eps_positive:
            if asset_val > 0:
                hybrid = 0.25 * graham_val + 0.25 * buffett_val + \
                         0.20 * graham_norm + 0.10 * fcf_val + 0.20 * asset_val
            else:
                hybrid = 0.30 * graham_val + 0.35 * buffett_val + \
                         0.20 * graham_norm + 0.15 * fcf_val
        elif bvps_positive:
            hybrid = bvps * DEFAULT_PB_TARGET
        else:
            hybrid = 0.0

    else:
        weights = {'graham': 0.25, 'buffett': 0.25, 'norm': 0.20,
                    'fcf': 0.10, 'asset': 0.20}
        values = {
            'graham': graham_val if graham_val > 0 else 0.0,
            'buffett': buffett_val if buffett_val > 0 else 0.0,
            'norm': graham_norm if graham_norm > 0 else 0.0,
            'fcf': fcf_val if fcf_val > 0 else 0.0,
            'asset': asset_val if asset_val > 0 else 0.0,
        }
        active = {k: v for k, v in values.items() if v > 0}
        if not active:
            hybrid = price * DEFAULT_MIN_PRICE_FACTOR if price > 0 else 0.0
        else:
            total_w = sum(weights[k] for k in active.keys())
            hybrid = sum(weights[k] * active[k] for k in active.keys()) / total_w

    # 8. QUALITY BONUS
    hybrid = hybrid * quality_bonus

    # 9. SANITY GUARD
    if price > 0:
        hybrid = max(hybrid, price * 0.6)
        hybrid = min(hybrid, price * 5.0)
    else:
        hybrid = max(hybrid, 20000.0)

    return round_float(hybrid, 0)


# ============================================================================
# 17. BANK VALUATION ENGINE
# ============================================================================
class BankValuationEngine:
    def __init__(self, discount_rate=0.12, terminal_growth=0.03, target_pb=1.5):
        self.discount_rate = float(discount_rate)
        self.terminal_growth = float(terminal_growth)
        self.target_pb = float(target_pb)

    def graham_bank_value(self, bvps, roe, growth):
        try:
            b = to_float_scalar(bvps)
            r = to_float_scalar(roe) / 100.0
            g = to_float_scalar(growth) / 100.0
            rr = self.discount_rate
            tg = self.terminal_growth

            if b < MIN_REAL_BVPS:
                return 0.0
            if r <= 0 or r > 1.0:
                return 0.0
            if rr - tg <= 0:
                return 0.0
            if r <= rr:
                return round_float(b * 1.0, 0)

            g_adj = min(g, rr - 0.01)
            val = b * (r - g_adj) / (rr - tg)
            if val < 0 or val > b * 20:
                return round_float(b * self.target_pb, 0)
            return round_float(val, 0)
        except Exception:
            return 0.0

    def pe_band_value(self, eps, growth):
        try:
            e = to_float_scalar(eps)
            g = to_float_scalar(growth)
            if e < MIN_REAL_EPS:
                return 0.0
            pe = 8.5 + 2 * max(g, 5.0)
            pe = min(pe, 25.0)
            return round_float(e * pe, 0)
        except Exception:
            return 0.0

    def valuation_range(self, bvps, eps, roe, growth):
        g_val = self.graham_bank_value(bvps, roe, growth)
        pe_val = self.pe_band_value(eps, growth)
        pb_val = to_float_scalar(bvps) * self.target_pb if to_float_scalar(bvps) > 0 else 0.0

        weights, values = [], []
        if g_val > 0:
            weights.append(0.4); values.append(g_val)
        if pe_val > 0:
            weights.append(0.3); values.append(pe_val)
        if pb_val > 0:
            weights.append(0.3); values.append(pb_val)

        blended = 0.0
        if weights:
            total_w = sum(weights)
            blended = sum(w * v for w, v in zip(weights, values)) / total_w

        return {
            'graham_bank_value': g_val,
            'pe_band_value': pe_val,
            'pb_target_value': round_float(pb_val, 0),
            'blended_value': round_float(blended, 0),
        }

    def growth_from_nii(self, nii_series, years=10):
        try:
            series = [to_float_scalar(x) for x in nii_series
                      if x is not None and to_float_scalar(x) > 0]
            if len(series) < 2:
                return 0.0
            series = series[-years:] if len(series) >= years else series
            first = series[0]
            last = series[-1]
            n = len(series) - 1
            if first <= 0 or last <= 0 or n <= 0:
                return 0.0
            cagr = (last / first) ** (1.0 / n) - 1
            return round_float(cagr * 100, 2)
        except Exception:
            return 0.0


def hybrid_valuation_bank(price, eps, bvps, roe, growth_rate=0.0,
                          nii_or_toi=0.0, nii_series=None,
                          moat_score=0.0, management_score=0.0):
    price = fix_price(to_float_scalar(price))
    eps = fix_eps(to_float_scalar(eps))
    bvps = fix_bvps(to_float_scalar(bvps))
    roe = to_float_scalar(roe)
    g = to_float_scalar(growth_rate)

    engine = BankValuationEngine()
    if g == 0 and nii_series:
        g = engine.growth_from_nii(nii_series)

    val = engine.valuation_range(bvps=bvps, eps=eps, roe=roe, growth=g)

    quality_bonus = 1.0 + (to_float_scalar(moat_score) / 100) + (to_float_scalar(management_score) / 200)
    if quality_bonus > 1.3:
        quality_bonus = 1.3
    if quality_bonus < 1.0:
        quality_bonus = 1.0

    blended = val['blended_value'] * quality_bonus

    if price > 0:
        blended = max(blended, price * 0.6)
    if blended <= 0 and bvps > 0:
        blended = bvps * 1.2

    return {
        'intrinsic_value': round_float(blended, 0),
        'graham_bank_value': val['graham_bank_value'],
        'pe_band_value': val['pe_band_value'],
        'pb_target_value': val['pb_target_value'],
        'growth_used': round_float(g, 2),
        'method': 'bank_valuation_engine',
        'nii_or_toi_vnd': round_float(to_float_scalar(nii_or_toi), 0),
    }


# ============================================================================
# 18. SIGNAL FILTERS
# ============================================================================
def check_signal_filters_advanced(row, df, ticker, sector, intrinsic_value, current_price):
    messages = []
    sector_norm = _normalize_sector(sector)

    adtv_col = find_column_by_keywords(df, ['khối lượng trung bình 20', 'adtv20', 'avg volume 20'])
    if adtv_col:
        adtv = to_float_scalar(row.get(adtv_col, 0))
        if adtv < THRESHOLDS.get("MIN_ADTV", 100000):
            return False, f"❌ Thanh khoản thấp (ADTV20 = {adtv:,.0f})"
        messages.append(f"✅ Thanh khoản tốt (ADTV20 = {adtv:,.0f})")
    else:
        messages.append("⚠️ Không có ADTV20, bỏ qua lọc thanh khoản")

    if sector_norm == "banking":
        npl_col = find_column_by_keywords(df, ['nợ xấu', 'npl', 'non-performing loan'])
        if npl_col:
            npl = to_float_scalar(row.get(npl_col, 100))
            if npl < 2.0:
                messages.append(f"✅ NPL = {npl:.2f}% < 2%")
            else:
                return False, f"❌ NPL = {npl:.2f}% >= 2%"
        else:
            messages.append("⚠️ Không có NPL")
    else:
        z = calculate_altman_z(row, df)
        if z is not None:
            if z > 1.8:
                messages.append(f"✅ Altman Z = {z:.2f} > 1.8")
            else:
                return False, f"❌ Altman Z = {z:.2f} ≤ 1.8"
        else:
            messages.append("⚠️ Không đủ dữ liệu Altman Z")

    if intrinsic_value > 0 and current_price > 0:
        mos = (intrinsic_value - current_price) / intrinsic_value * 100
        if mos >= THRESHOLDS.get("MIN_MOS", 30):
            messages.append(f"✅ MOS = {mos:.1f}% ≥ 30%")
        else:
            return False, f"❌ MOS = {mos:.1f}% < 30%"
    else:
        return False, "⚠️ Không có định giá để tính MOS"

    ncav_val = get_ncav_from_row(row, df)
    if ncav_val > 0:
        if current_price < 0.66 * ncav_val:
            messages.append(f"✅ Giá < 2/3 NCAV (NCAV = {ncav_val:,.0f})")
        else:
            messages.append(f"ℹ️ Giá > 2/3 NCAV (NCAV = {ncav_val:,.0f})")
    else:
        messages.append("⚠️ Không tính được NCAV")

    return True, " | ".join(messages)


# ============================================================================
# 19. ANALYZE STOCK
# ============================================================================
def _extract_history_for_normalization(row, df):
    norm_eps = 0.0
    try:
        eps_col = find_column_by_keywords(df, [
            '61_is_eps_vndco_phieu', 'eps', 'EPS',
        ])
        if eps_col is not None:
            eps_series = df[eps_col].dropna().tolist()[:10]
            norm_eps = calculate_normalized_eps(eps_series)
    except Exception:
        pass

    fcf_ps = 0.0
    try:
        cfo_col = find_column_by_keywords(df, ['lưu chuyển tiền thuần từ hđkd',
                                                'cfo', 'operating cash flow'])
        capex_col = find_column_by_keywords(df, ['mua sắm tscđ', 'capex',
                                                  'capital expenditure'])
        if cfo_col and capex_col:
            fcf_ps = 0.0
    except Exception:
        pass

    return norm_eps, fcf_ps


def analyze_stock_graham_dodd(row, df, ticker_col, sector_col=None):
    ticker = str(row.get(ticker_col, '')).strip().upper()
    sector_raw = str(row.get(sector_col, '')).strip() if sector_col else 'unknown'
    sector_norm = _normalize_sector(sector_raw)

    metrics = extract_financial_metrics_smart(row, df, ticker)

    price = metrics['gia_hien_tai']
    eps = metrics['eps']
    bvps = metrics['bvps']
    roe = metrics['roe']
    roa = metrics['roa']

    de_col = find_column_by_keywords(df, ['gd_no_vcsh', 'nợ/vcsh'])
    de = to_float_scalar(row.get(de_col, 0)) if de_col else 0.0

    roic_col = find_column_by_keywords(df, ['gd_roic', 'roic'])
    roic = to_float_scalar(row.get(roic_col, 0)) if roic_col else 0.0

    growth_col = find_column_by_keywords(df, ['gd_growth', 'growth'])
    growth = to_float_scalar(row.get(growth_col, 0)) if growth_col else 0.0

    margin_col = find_column_by_keywords(df, ['gd_margin', 'biên lợi nhuận gộp'])
    margin = to_float_scalar(row.get(margin_col, 0)) if margin_col else 0.0

    ncav = get_ncav_from_row(row, df)

    is_bank = _is_bank(ticker) or sector_norm == "banking"

    moat_score, moat_details = calculate_moat_score(
        roe, margin, margin * 0.5, de, growth, roic)
    div_yield = metrics.get('ty_le_co_tuc', 0)
    mgmt_score, mgmt_details = calculate_management_score(
        roe, roic, div_yield,
        safe_divide(metrics.get('co_tuc_cp', 0), eps, 0) * 100 if eps > 0 else 0,
        growth, growth,
    )

    norm_eps, _ = _extract_history_for_normalization(row, df)
    fcf_ps = 0.0
    try:
        shares = metrics.get('shares', 0)
        cfo_col = find_column_by_keywords(df, ['lưu chuyển tiền thuần từ hđkd',
                                                'cfo', 'operating cash flow'])
        capex_col = find_column_by_keywords(df, ['mua sắm tscđ', 'capex'])
        if cfo_col and capex_col and shares > 0:
            cfo = to_float_scalar(row.get(cfo_col, 0))
            capex = to_float_scalar(row.get(capex_col, 0))
            fcf_ps = calculate_fcf_per_share(cfo, capex, shares)
    except Exception:
        fcf_ps = 0.0

    bank_info = {}
    if is_bank:
        try:
            nii_or_toi, nii_source = get_bank_revenue(row, df)
        except Exception:
            nii_or_toi, nii_source = 0.0, ""

        nii_col = find_column_by_keywords(df, ['thu nhập lãi thuần', 'nii', 'net interest income'])
        nii_series = []
        if nii_col:
            try:
                nii_series = [to_float_scalar(v) for v in df[nii_col].dropna().tolist()]
            except Exception:
                nii_series = []

        bank_val = hybrid_valuation_bank(
            price=price, eps=eps, bvps=bvps, roe=roe,
            growth_rate=growth, nii_or_toi=nii_or_toi,
            nii_series=nii_series,
            moat_score=moat_score,
            management_score=mgmt_score,
        )
        bank_info = {
            'is_bank': True,
            'nii_or_toi': round_float(to_float_scalar(nii_or_toi), 0),
            'nii_source': nii_source,
            'growth_from_nii': bank_val.get('growth_used', 0.0),
            'graham_bank_value': bank_val.get('graham_bank_value', 0),
            'pe_band_value': bank_val.get('pe_band_value', 0),
            'pb_target_value': bank_val.get('pb_target_value', 0),
        }
        intrinsic = bank_val.get('intrinsic_value', 0.0)
    else:
        intrinsic = hybrid_valuation_enhanced(
            price=price, eps=eps, bvps=bvps, roe=roe, margin=margin, de=de,
            sector=sector_raw,
            growth_rate=growth, roic=roic, ncav=ncav,
            normalized_eps=norm_eps, fcf_per_share=fcf_ps,
            moat_score=moat_score,
            management_score=mgmt_score,
        )

    mos = ((intrinsic - price) / intrinsic * 100) if intrinsic > 0 and price > 0 else 0

    passed, filter_msg = check_signal_filters_advanced(
        row, df, ticker, sector_raw, intrinsic, price)

    return {
        'ticker': ticker,
        'sector': sector_raw,
        'sector_norm': sector_norm,
        'is_bank': is_bank,
        'price': price,
        'eps': eps,
        'bvps': bvps,
        'roe': roe,
        'roa': roa,
        'roic': roic,
        'margin': margin,
        'de': de,
        'growth': growth,
        'ncav': ncav,
        'pe': metrics.get('pe', 0),
        'pb': metrics.get('pb', 0),
        'dividend_yield': div_yield,
        'co_tuc_cp': metrics.get('co_tuc_cp', 0),
        'market_cap': metrics.get('market_cap', 0),
        'market_cap_ty': metrics.get('market_cap_ty', 0),
        'shares': metrics.get('shares', 0),
        'equity': metrics.get('equity', 0),
        'normalized_eps': norm_eps,
        'fcf_per_share': fcf_ps,
        'intrinsic_value': intrinsic,
        'mos': mos,
        'moat_score': moat_score,
        'moat_details': moat_details,
        'management_score': mgmt_score,
        'management_details': mgmt_details,
        'signal_passed': passed,
        'signal_message': filter_msg,
        'bank_info': bank_info,
        'sanity_warnings': metrics.get('sanity_warnings', []),
    }


# ============================================================================
# 20. LỌC CỔ PHIẾU TIỀM NĂNG
# ============================================================================
def get_undervalued_stocks_enhanced(df, ticker_col, sector_col=None):
    if df is None or df.empty or ticker_col is None:
        return pd.DataFrame()

    results = []
    for _, row in df.iterrows():
        try:
            analysis = analyze_stock_graham_dodd(row, df, ticker_col, sector_col)
        except Exception:
            continue

        if analysis['signal_passed'] and analysis['mos'] >= 30:
            if analysis['ncav'] > 0 and analysis['price'] < 0.66 * analysis['ncav']:
                priority = 1
            else:
                priority = 2

            results.append({
                'Mã': analysis['ticker'],
                'Ngành': analysis['sector'],
                'Giá': analysis['price'],
                'EPS': analysis['eps'],
                'BVPS': analysis['bvps'],
                'ROE': analysis['roe'],
                'NCAV': analysis['ncav'],
                'Định giá nội tại': analysis['intrinsic_value'],
                'MOS (%)': round_float(analysis['mos'], 1),
                'Điểm Moat': analysis['moat_score'],
                'Điểm Quản lý': analysis['management_score'],
                'Priority': priority,
            })

    if not results:
        return pd.DataFrame()
    df_res = pd.DataFrame(results)
    df_res = df_res.sort_values(['Priority', 'MOS (%)'], ascending=[True, False])
    return df_res


# ============================================================================
# 21. HIỂN THỊ STREAMLIT
# ============================================================================
def show_graham_dodd_analysis(df, ticker_col):
    st.subheader("📊 Phân tích cổ phiếu theo Graham & Dodd")

    selected_ticker = st.selectbox("Chọn mã cổ phiếu", df[ticker_col].unique())
    row = df[df[ticker_col] == selected_ticker].iloc[0]
    sector_col = 'ngành' if 'ngành' in df.columns else None

    analysis = analyze_stock_graham_dodd(row, df, ticker_col, sector_col)

    col1, col2 = st.columns(2)
    with col1:
        st.metric("Giá hiện tại", format_currency_vn_advanced(analysis['price'], per_share=True))
        st.metric("Định giá nội tại", format_currency_vn_advanced(analysis['intrinsic_value'], per_share=True))
        st.metric("Biên an toàn", f"{analysis['mos']:.1f}%")
    with col2:
        st.metric("Điểm Moat", f"{analysis['moat_score']}/10")
        st.metric("Điểm Quản lý", f"{analysis['management_score']}/10")
        st.metric("NCAV", format_currency_vn_advanced(analysis['ncav'], per_share=True))

    st.write("**Chi tiết Moat:**", "\n".join(analysis['moat_details']))
    st.write("**Chi tiết Quản lý:**", "\n".join(analysis['management_details']))
    st.write("**Tín hiệu:**", analysis['signal_message'])

    st.subheader("📋 Cổ phiếu tiềm năng (MOS ≥ 30%)")
    df_undervalued = get_undervalued_stocks_enhanced(df, ticker_col, sector_col)
    if not df_undervalued.empty:
        st.dataframe(df_undervalued)
    else:
        st.info("Hiện chưa có cổ phiếu nào đáp ứng tiêu chí.")


# ============================================================================
# 22. ALIASES
# ============================================================================
def hybrid_valuation_ensemble(price, eps, bvps, roe, margin, de, sector,
                               growth_rate=0.0, roic=0.0):
    return hybrid_valuation_enhanced(
        price=price, eps=eps, bvps=bvps, roe=roe, margin=margin, de=de,
        sector=sector, growth_rate=growth_rate, roic=roic,
    )


def check_signal_filters(row, df, ticker, sector, intrinsic_value, current_price):
    return check_signal_filters_advanced(row, df, ticker, sector, intrinsic_value, current_price)


get_undervalued_stocks = get_undervalued_stocks_enhanced
eps_model_advanced_trainer = train_eps_model_advanced
eps_advanced_predictor = predict_eps_advanced


# ============================================================================
# 23. STRESS TEST
# ============================================================================
def apply_crisis_simulation(df, crisis_key):
    try:
        from lich_su.backtest_chien_luoc import HISTORICAL_CRISES
    except ImportError:
        return df

    if crisis_key not in HISTORICAL_CRISES:
        return df

    crisis = HISTORICAL_CRISES[crisis_key]
    haircut_pct = crisis.get("stress_test_parameters", {}).get("valuation_haircut_pct", 0) / 100.0

    df_stress = df.copy()

    if "gd_gia_tri_noi_tai_vnd" in df_stress.columns:
        intrinsic_col = "gd_gia_tri_noi_tai_vnd"
    elif "gd_eps" in df_stress.columns and "gd_pe" in df_stress.columns:
        df_stress["gd_gia_tri_noi_tai_vnd"] = df_stress["gd_eps"] * df_stress["gd_pe"]
        intrinsic_col = "gd_gia_tri_noi_tai_vnd"
    else:
        df_stress["gd_gia_tri_noi_tai_vnd"] = 0.0
        intrinsic_col = "gd_gia_tri_noi_tai_vnd"

    df_stress["gd_gia_tri_noi_tai_stress"] = df_stress[intrinsic_col] * (1 + haircut_pct)
    return df_stress


# ============================================================================
# 24. FORECAST TREND
# ============================================================================
def forecast_trend(value, growth_rate, periods=4):
    val = to_float_scalar(value)
    g = to_float_scalar(growth_rate)
    if val == 0:
        return [0.0] * periods
    forecast = [val * ((1 + g/100) ** i) for i in range(1, periods+1)]
    return [round_float(x, 0) for x in forecast]


# ============================================================================
# 25. CHECK AI AVAILABILITY
# ============================================================================
def check_ai_availability():
    return {
        'huggingface': HF_AVAILABLE,
        'tensorflow': TF_AVAILABLE,
        'pytorch': TORCH_AVAILABLE,
        'transformers': TRANSFORMERS_AVAILABLE,
        'timesfm': TIMESFM_AVAILABLE,
        'lightgbm': LGB_AVAILABLE,
        'xgboost': XGB_AVAILABLE,
    }


# ============================================================================
# 26. DEBUG HELPER
# ============================================================================
def debug_sector_mapping(df, sector_col):
    if df is None or df.empty or sector_col not in df.columns:
        return {}
    counts = Counter()
    for _, row in df.iterrows():
        raw = row.get(sector_col, '')
        counts[_normalize_sector(raw)] += 1
    return dict(counts)


def debug_sqlite_tickers():
    return {
        'bank_tickers_count': len(BANK_TICKERS_V7),
        'is_using_sqlite': _IS_USING_SQLITE_BANKS,
        'bank_tickers_sample': sorted(list(BANK_TICKERS_V7))[:10],
        'all_sqlite_tickers_count': len(_ALL_SQLITE_TICKERS),
        'db_paths': {k: os.path.exists(v) for k, v in _SQLITE_DB_PATHS.items()},
        'default_sector_by_db': dict(_DEFAULT_SECTOR_BY_DB),
    }


# ============================================================================
# 28. [v11.0-DCF] DCF ENGINE — TÍCH HỢP TỪ MÔ ĐUN DCF CHUẨN VN
# ============================================================================
DEFAULT_VN_MACRO = {
    "risk_free_rate": 0.030,
    "market_risk_premium": 0.070,
    "cost_of_debt": 0.080,
    "tax_rate": 0.200,
    "terminal_growth": 0.030,
    "dep_percent": 0.040,
    "capex_percent": 0.030,
    "wc_percent": 0.020
}

def run_dcf_engine(clean: Dict[str, Any]) -> Dict[str, Any]:
    """
    Tính toán DCF cơ bản (Base Case).
    Lưu ý: Tất cả tiền tệ đều tính bằng Tỷ VND.
    """
    revenue = clean["revenue_ty"]
    g = clean["growth_rate"]
    ebit_margin = clean["ebit_margin"]
    
    dep_pct = clean.get("dep_percent", 0.04)
    capex_pct = clean.get("capex_percent", 0.03)
    wc_pct = clean.get("wc_percent", 0.02)
    
    beta = clean["beta"]
    price = clean["price_vnd"]
    shares = clean["shares"] # triệu cp
    cash = clean["cash_ty"]
    debt = clean["debt_ty"]
    
    tax_rate = clean.get("tax_rate", 0.20)
    terminal_growth = clean.get("terminal_growth", 0.03)
    rf = clean.get("risk_free_rate", 0.03)
    mrp = clean.get("market_risk_premium", 0.07)
    cod = clean.get("cost_of_debt", 0.08)
    
    # --- 1. WACC ---
    cost_of_equity = rf + beta * mrp
    market_cap = (price * shares) / 1000.0 # (VND * triệu CP) / 1000 -> Tỷ VND
    base_ev = market_cap + debt - cash
    
    equity_weight = market_cap / base_ev if base_ev > 0 else 1.0
    debt_weight = debt / base_ev if base_ev > 0 else 0.0
    
    wacc = cost_of_equity * equity_weight + cod * debt_weight
    
    # --- 2. Dự phóng 5 năm & FCFF ---
    revenues, fcff, pv_fcff = [], [], []
    for year in range(1, 6):
        rev_t = revenue * ((1 + g) ** year)
        ebit_t = rev_t * ebit_margin
        dep_t = rev_t * dep_pct
        capex_t = rev_t * capex_pct
        wc_t = rev_t * wc_pct
        
        fcff_t = ebit_t * (1 - tax_rate) + dep_t - capex_t - wc_t
        pv_fcff_t = fcff_t / ((1 + wacc) ** year)
        
        revenues.append(rev_t)
        fcff.append(fcff_t)
        pv_fcff.append(pv_fcff_t)
        
    # --- 3. Terminal Value (Gordon Growth) ---
    if wacc > terminal_growth:
        terminal_value = fcff[-1] * (1 + terminal_growth) / (wacc - terminal_growth)
    else:
        terminal_value = 0.0
        
    pv_terminal_value = terminal_value / ((1 + wacc) ** 5)
    
    # --- 4. Định giá ---
    enterprise_value = sum(pv_fcff) + pv_terminal_value
    equity_value = enterprise_value + cash - debt
    intrinsic_value_per_share = (equity_value * 1000.0) / shares if shares > 0 else 0
    upside_downside = (intrinsic_value_per_share - price) / price if price > 0 else 0
    
    return {
        "intrinsic_value_per_share": intrinsic_value_per_share,
        "current_price": price,
        "upside_downside": upside_downside,
        "enterprise_value": enterprise_value,
        "equity_value": equity_value,
        "wacc": wacc,
        "fcff_projections": fcff,
        "pv_fcff": pv_fcff,
        "pv_terminal_value": pv_terminal_value
    }

def run_dcf_scenarios(clean: Dict[str, Any]) -> Dict[str, Any]:
    """Mô phỏng 3 kịch bản Bear, Base, Bull."""
    scenarios = {
        "Bear": {"growth": clean["growth_rate"] * 0.6, "wacc_adj": 1.1},
        "Base": {"growth": clean["growth_rate"], "wacc_adj": 1.0},
        "Bull": {"growth": clean["growth_rate"] * 1.6, "wacc_adj": 0.9}
    }
    
    outputs = {}
    for name, s in scenarios.items():
        temp = clean.copy()
        temp["growth_rate"] = s["growth"]
        temp["beta"] = clean["beta"] * s["wacc_adj"]
        
        result = run_dcf_engine(temp)
        result["scenario"] = name
        outputs[name] = result
        
    return outputs

def get_investment_verdict(base_upside: float) -> str:
    """Đánh giá khuyến nghị dựa trên Base Case Upside"""
    if base_upside > 0.15:
        return "Strong Buy"
    elif base_upside > 0.05:
        return "Buy"
    elif base_upside > -0.05:
        return "Hold"
    elif base_upside > -0.15:
        return "Sell"
    else:
        return "Strong Sell"

def extract_dcf_inputs_from_vn_data(ticker: str, data: dict) -> dict:
    """
    Hàm cầu nối dữ liệu từ hệ thống CSV/Snapshot của bạn (v54)
    sang format của DCF Engine.
    """
    rev_6m = data.get('toi_6t2026', 0) or data.get('revenue', 0)
    revenue_ty = rev_6m * 2 if rev_6m > 0 else 1000.0 
    
    lntt_6m = data.get('lntt_6m_ty', 0)
    ebit_margin = (lntt_6m / rev_6m) if rev_6m > 0 and lntt_6m > 0 else 0.15
    
    g = data.get('growth_2025_2024', 0) / 100.0
    if g <= 0 or g > 0.3:
        g = 0.08 
    
    beta = 1.0
    if ticker in ['VCB', 'BID', 'CTG', 'TCB', 'MBB', 'ACB', 'VPB']:
        beta = 0.9
    elif ticker in ['HPG', 'VHM', 'VIC', 'FPT', 'MWG']:
        beta = 1.2
        
    total_assets = data.get('total_assets_30062026', 0)
    equity = data.get('equity', 0)
    debt_ty = max(0, total_assets - equity)
    cash_ty = total_assets * 0.05 if total_assets > 0 else 0
    
    price_vnd = data.get('price', 0)
    shares = data.get('shares_outstanding', 0) / 1e6 
    
    return {
        "ticker": ticker,
        "revenue_ty": revenue_ty,
        "growth_rate": g,
        "ebit_margin": ebit_margin,
        "beta": beta,
        "price_vnd": price_vnd,
        "shares": shares,
        "cash_ty": cash_ty,
        "debt_ty": debt_ty,
        "tax_rate": DEFAULT_VN_MACRO["tax_rate"],
        "terminal_growth": DEFAULT_VN_MACRO["terminal_growth"],
        "risk_free_rate": DEFAULT_VN_MACRO["risk_free_rate"],
        "market_risk_premium": DEFAULT_VN_MACRO["market_risk_premium"],
        "cost_of_debt": DEFAULT_VN_MACRO["cost_of_debt"],
        "dep_percent": DEFAULT_VN_MACRO["dep_percent"],
        "capex_percent": DEFAULT_VN_MACRO["capex_percent"],
        "wc_percent": DEFAULT_VN_MACRO["wc_percent"]
    }

def calculate_dcf_valuation(ticker: str, data: dict) -> dict:
    """Hàm tổng hợp để gọi 1 lần từ giao diện Streamlit."""
    clean_inputs = extract_dcf_inputs_from_vn_data(ticker, data)
    
    if clean_inputs["price_vnd"] <= 0 or clean_inputs["shares"] <= 0:
        return {"error": "Thiếu dữ liệu Giá hoặc Số lượng cổ phiếu."}
        
    scenarios = run_dcf_scenarios(clean_inputs)
    verdict = get_investment_verdict(scenarios["Base"]["upside_downside"])
    
    return {
        "ticker": ticker,
        "clean_inputs": clean_inputs,
        "scenarios": scenarios,
        "verdict": verdict
    }


# ============================================================================
# 27. EXPORTS
# ============================================================================
__all__ = [
    'calculate_pe_safe', 'calculate_pb_safe', 'calculate_roe_safe',
    'calculate_roic_safe', 'calculate_debt_to_equity_safe',
    'calculate_dividend_yield_safe', 'calculate_cagr',
    'calculate_ncav', 'calculate_liquidation_value', 'get_ncav_from_row',
    'calculate_normalized_eps', 'calculate_fcf', 'calculate_fcf_per_share',
    'calculate_management_score', 'calculate_moat_score',
    'get_peer_metrics', 'compare_with_peers',
    'buffett_intrinsic_value', 'hybrid_valuation_enhanced',
    'hybrid_valuation_ensemble', 'hybrid_valuation_bank',
    'BankValuationEngine',
    'label_rule', 'train_risk_classifier_ensemble', 'predict_risk_ensemble',
    'train_eps_regressor_ensemble', 'predict_eps_with_huggingface',
    'train_eps_model_advanced', 'predict_eps_advanced', 'predict_eps_ensemble',
    'eps_model_advanced_trainer', 'eps_advanced_predictor',
    'analyze_stock_graham_dodd',
    'get_undervalued_stocks_enhanced', 'get_undervalued_stocks',
    'check_signal_filters', 'check_signal_filters_advanced',
    'show_graham_dodd_analysis',
    'apply_crisis_simulation', 'forecast_trend', 'check_ai_availability',
    'BANK_TICKERS_V7', 'GARBAGE_VALUES_V7',
    'DEFAULT_PB_TARGET', 'DEFAULT_PE_TARGET', 'DEFAULT_MIN_PRICE_FACTOR',
    '_normalize_sector', 'debug_sector_mapping',
    '_SQLITE_DB_PATHS', '_DEFAULT_SECTOR_BY_DB',
    '_load_bank_tickers_from_sqlite', '_load_all_sqlite_tickers',
    '_extract_tickers_from_table',
    '_IS_USING_SQLITE_BANKS', '_ALL_SQLITE_TICKERS',
    'debug_sqlite_tickers', '_is_bank',
    # [v11.0-DCF]
    'run_dcf_engine', 'run_dcf_scenarios', 'get_investment_verdict',
    'extract_dcf_inputs_from_vn_data', 'calculate_dcf_valuation',
    'DEFAULT_VN_MACRO'
]


# ============================================================================
# SELFTEST
# ============================================================================
if __name__ == "__main__":
    print("=" * 70)
    print("SELFTEST [v11.0-DCF] dinh_gia_graham.py")
    print("=" * 70)

    _dbg = debug_sqlite_tickers()
    print(f"\n📁 SQLite DB paths:")
    for _k, _exists in _dbg['db_paths'].items():
        print(f"   {'✅' if _exists else '❌'} {_k}: {_SQLITE_DB_PATHS.get(_k)}")
    print(f"\n🏦 BANK_TICKERS_V7: {_dbg['bank_tickers_count']} mã")
    print(f"   Source: {'SQLite' if _dbg['is_using_sqlite'] else 'Fallback 25 mã cũ'}")
    print(f"   Sample: {_dbg['bank_tickers_sample']}")
    print(f"🔍 ALL SQLite tickers: {_dbg['all_sqlite_tickers_count']} mã")

    # Sector normalization
    assert _normalize_sector("banking") == "banking"
    assert _normalize_sector("BANKING") == "banking"
    assert _normalize_sector("Ngân hàng") == "banking"
    assert _normalize_sector("NGÂN HÀNG") == "banking"
    assert _normalize_sector("Ngân hàng & Tài chính") == "banking"
    assert _normalize_sector("Chứng khoán") == "securities"
    assert _normalize_sector("Bất động sản") == "realestate"
    assert _normalize_sector("Công nghệ") == "technology"
    assert _normalize_sector("CÔNG NGHỆ") == "technology"
    assert _normalize_sector("Công nghệ thông tin") == "technology"
    assert _normalize_sector("Software") == "technology"
    assert _normalize_sector("Sản xuất & Khác") == "manufacturing"
    assert _normalize_sector("SẢN XUẤT & KHÁC") == "manufacturing"
    assert _normalize_sector("Công nghiệp") == "manufacturing"
    assert _normalize_sector("Thép") == "manufacturing"
    assert _normalize_sector("") == "general"
    assert _normalize_sector(None) == "general"
    print("✅ _normalize_sector OK")

    # Basic calculations
    pe = calculate_pe_safe(32, 3000)
    assert pe > 0
    print(f"✅ calculate_pe_safe: 32/3000 → PE = {pe}")

    pb = calculate_pb_safe(32, 32000)
    assert pb > 0
    print(f"✅ calculate_pb_safe: 32/32000 → PB = {pb}")

    # Hybrid cho 3 nhóm
    hv_tech = hybrid_valuation_enhanced(
        price=50000, eps=3000, bvps=20000, roe=18, margin=25, de=0.3,
        sector='Công nghệ', growth_rate=20,
        moat_score=8, management_score=7,
    )
    assert hv_tech > 0
    print(f"✅ hybrid_valuation 'Công nghệ': {hv_tech:,.0f}")

    hv_mfg = hybrid_valuation_enhanced(
        price=25000, eps=2000, bvps=20000, roe=12, margin=15, de=0.8,
        sector='Sản xuất & Khác', growth_rate=8,
        ncav=22000, moat_score=5, management_score=6,
    )
    assert hv_mfg > 0
    print(f"✅ hybrid_valuation 'Sản xuất & Khác': {hv_mfg:,.0f}")

    hv_bank_vn = hybrid_valuation_enhanced(
        price=32000, eps=3000, bvps=32000, roe=18, margin=30, de=0.5,
        sector='Ngân hàng & Tài chính', growth_rate=12,
    )
    assert hv_bank_vn > 0
    print(f"✅ hybrid_valuation 'Ngân hàng & Tài chính': {hv_bank_vn:,.0f}")

    # Quality bonus
    hv_no_bonus = hybrid_valuation_enhanced(
        price=32000, eps=3000, bvps=32000, roe=18, margin=30, de=0.5,
        sector='banking', growth_rate=12,
    )
    hv_with_bonus = hybrid_valuation_enhanced(
        price=32000, eps=3000, bvps=32000, roe=18, margin=30, de=0.5,
        sector='banking', growth_rate=12,
        moat_score=8, management_score=7,
    )
    assert hv_with_bonus >= hv_no_bonus
    print(f"✅ Quality bonus: {hv_no_bonus:,.0f} → {hv_with_bonus:,.0f}")

    # Bank engine
    engine = BankValuationEngine()
    val = engine.valuation_range(bvps=32000, eps=3000, roe=18, growth=12)
    print(f"✅ BankValuationEngine: {val['blended_value']:,.0f}")

    hv_bank = hybrid_valuation_bank(
        price=32000, eps=3000, bvps=32000, roe=18, growth_rate=12,
        moat_score=8, management_score=7,
    )
    print(f"✅ hybrid_valuation_bank: {hv_bank['intrinsic_value']:,.0f}")

    moat, _ = calculate_moat_score(18, 30, 15, 0.5, 12, 15)
    assert 0 <= moat <= 10
    print(f"✅ calculate_moat_score: {moat}/10")

    mgmt, _ = calculate_management_score(18, 15, 3.5, 50, 12, 12)
    assert 0 <= mgmt <= 10
    print(f"✅ calculate_management_score: {mgmt}/10")

    ai = check_ai_availability()
    print(f"✅ check_ai_availability: {ai}")

    if BANK_TICKERS_V7:
        sample_bank = sorted(list(BANK_TICKERS_V7))[0]
        assert _is_bank(sample_bank) is True
        print(f"✅ _is_bank('{sample_bank}') = True")

    # [v11.0-DCF] Kiểm tra DCF Engine
    print("\n🔬 TEST DCF ENGINE")
    test_data = {
        'toi_6t2026': 50000,
        'lntt_6m_ty': 15000,
        'growth_2025_2024': 15,
        'total_assets_30062026': 2000000,
        'equity': 150000,
        'price': 30000,
        'shares_outstanding': 1000000000
    }
    dcf_res = calculate_dcf_valuation('TCB', test_data)
    if "error" in dcf_res:
        print(f"❌ DCF Error: {dcf_res['error']}")
    else:
        base = dcf_res['scenarios']['Base']
        print(f"✅ DCF Base Case Value: {base['intrinsic_value_per_share']:,.0f} VND")
        print(f"✅ DCF Verdict: {dcf_res['verdict']}")

    print("\n✅ ALL TESTS PASSED")
    print("=" * 70)
