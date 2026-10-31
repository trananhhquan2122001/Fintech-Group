# du_lieu/doc_bctc_goc_v56.py
# ============================================================================
# [v56] — MASTER CSV PIPELINE (đọc động toàn bộ mã)
# ----------------------------------------------------------------------------
# NGUỒN CHÍNH:  data/vietnam_stock_database_tong_hop.csv   (đầy đủ mã)
# NGUỒN 2:     vietnam_stock_database.xlsx                 (sheet bảng giá)
# FALLBACK:    Embedded 100-mã (EPS/LNST 2024-25) + ~70 giá
# FALLBACK:    9 CSV gốc mới (v55) → 3 CSV cũ (v54) → SNAPSHOT
#
# Không hardcode mã. Không giới hạn 100. Đọc động bằng _load_csv_db_to_df().
# ============================================================================

import os
import re
import numpy as np
import pandas as pd

from du_lieu.doc_bctc_goc import (
    _canonical_ticker, COMPANY_MAPPING,
    BANK_DATA_LATEST, CORP_DATA_LATEST,
    BANK_TICKERS, CORP_TICKERS,
    LATEST_MARKET_SNAPSHOT, LATEST_FINANCIAL_SUPPLEMENT,
    SNAPSHOT_PRICE_DATE, SNAPSHOT_BUILD_DATE,
    _SNAPSHOT_BANK_SET,
    _apply_latest_market_snapshot,
    _to_flat_dict, _build_result_dict, _merge_with_hardcoded,
    _extract_long_csv_metrics,
    _is_long_financial_csv,
    _load_csv_db_to_df,
    _detect_file_scale,
    _populate_one_group,
    get_financials_csv_first_v55,
    _populate_from_csv_v55,
    _load_csv_as_long_df_v55,
    _CSV_DB_PATHS_V55,
    MIN_REAL_EPS, MIN_REAL_BVPS,
    PE_MIN, PE_MAX, PB_MIN, PB_MAX,
    ROE_MIN_PCT, ROE_MAX_PCT, ROA_MIN_PCT, ROA_MAX_PCT,
    _parse_vn_number,
)


# ============================================================================
# [v56.1] KHAI BÁO ĐƯỜNG DẪN CHÍNH
# ============================================================================
_MASTER_CSV_FILENAME = 'vietnam_stock_database_tong_hop.csv'
_MASTER_CSV_RELATIVE = 'data/vietnam_stock_database_tong_hop.csv'
_PRICE_XLSX_FILENAME = 'vietnam_stock_database.xlsx'
_PRICE_CSV_ALT       = 'bang_gia_100_ma.csv'
_PRICE_SHEET_CANDIDATES = ('BangGia', 'Bang_Gia', 'Gia', 'Price', 'Prices',
                            'BangGiaHienTai', 'Bảng giá', 'Bảng Giá')


def _resolve_master_csv_path_v56():
    here   = os.path.dirname(os.path.abspath(__file__))
    parent = os.path.dirname(here)
    grand  = os.path.dirname(parent)
    cand = [
        _MASTER_CSV_RELATIVE,
        os.path.join(os.getcwd(), 'data', _MASTER_CSV_FILENAME),
        os.path.join(os.getcwd(), _MASTER_CSV_FILENAME),
        os.path.join(parent, 'data', _MASTER_CSV_FILENAME),
        os.path.join(grand,  'data', _MASTER_CSV_FILENAME),
        os.path.join(here,   'data', _MASTER_CSV_FILENAME),
        os.path.join('/app', 'data', _MASTER_CSV_FILENAME),
        os.path.join('/content', 'data', _MASTER_CSV_FILENAME),
        os.path.join('/workspace', 'data', _MASTER_CSV_FILENAME),
    ]
    for p in cand:
        try:
            if os.path.isfile(p) and os.path.getsize(p) > 0:
                return os.path.abspath(p)
        except OSError:
            continue
    return None


def _resolve_price_paths_v56():
    """Tìm xlsx + csv alt (bảng giá) trong base dirs."""
    here   = os.path.dirname(os.path.abspath(__file__))
    parent = os.path.dirname(here)
    grand  = os.path.dirname(parent)
    bases = [
        os.getcwd(), os.path.join(os.getcwd(), 'data'),
        parent, os.path.join(parent, 'data'),
        grand,  os.path.join(grand,  'data'),
        here,   os.path.join(here,   'data'),
        '/app', '/app/data', '/content', '/content/data', '/workspace', '/workspace/data',
    ]
    out = {'xlsx': None, 'csv': None}
    for key, fname in [('xlsx', _PRICE_XLSX_FILENAME), ('csv', _PRICE_CSV_ALT)]:
        for base in bases:
            p = os.path.join(base, fname)
            try:
                if os.path.isfile(p) and os.path.getsize(p) > 0:
                    out[key] = os.path.abspath(p)
                    break
            except OSError:
                continue
    return out


MASTER_CSV_PATH_V56 = _resolve_master_csv_path_v56()
PRICE_PATHS_V56     = _resolve_price_paths_v56()

print("\n" + "=" * 78)
print("[v56-PATHS] 🔍 ĐƯỜNG DẪN NGUỒN CHÍNH")
print("=" * 78)
if MASTER_CSV_PATH_V56:
    sz = os.path.getsize(MASTER_CSV_PATH_V56) / 1024
    print(f"   ✅ MASTER CSV   {MASTER_CSV_PATH_V56}  ({sz:,.1f} KB)")
else:
    print(f"   ❌ MASTER CSV   {_MASTER_CSV_RELATIVE}   (KHÔNG TÌM THẤY → dùng FALLBACK)")
for k, v in PRICE_PATHS_V56.items():
    if v:
        print(f"   ✅ PRICE {k:<4}   {v}")
    else:
        print(f"   ⚪ PRICE {k:<4}   (không có)")
print("=" * 78 + "\n")


# ============================================================================
# [v56.2] LOADER MASTER CSV → LONG-DF CHUẨN
# ============================================================================
_EMPTY_LONG_V56 = pd.DataFrame(columns=['ticker', 'metric_name', 'period', 'value'])


def _parse_unit_value_v56(raw):
    """Parse '16.79 nghìn tỷ' → 16790; '368.6 tỷ' → 368.6; 827 → 827; -3004 → -3004."""
    if raw is None or (isinstance(raw, float) and not np.isfinite(raw)):
        return None
    if isinstance(raw, (int, float, np.integer, np.floating)):
        v = float(raw)
        return v if np.isfinite(v) else None
    s = str(raw).strip().lower()
    if not s or s in ('none', 'nan', '', '-', '—', 'n/a'):
        return None
    neg = s.startswith('-')
    s = s.lstrip('-').strip()

    mult = 1.0
    if 'nghìn tỷ' in s or 'nghin ty' in s or 'nghìn ty' in s:
        mult = 1000.0
    elif 'tỷ' in s or 'ty' in s or ' tỷ' in s:
        mult = 1.0

    num = re.sub(r'[^\d.,]', '', s)
    if not num:
        return None
    # VN number: 1.234.567 (thousands), 16,79 (decimal), 12,103 (thousands)
    if ',' in num and '.' in num:
        if num.rfind(',') > num.rfind('.'):
            num = num.replace('.', '').replace(',', '.')
        else:
            num = num.replace(',', '')
    elif ',' in num:
        parts = num.split(',')
        if len(parts) == 2 and 1 <= len(parts[1]) <= 2:
            num = num.replace(',', '.')
        else:
            num = num.replace(',', '')
    elif '.' in num:
        parts = num.split('.')
        if len(parts) > 2:
            num = num.replace('.', '')
        elif len(parts) == 2 and len(parts[1]) == 3 and parts[1].isdigit():
            # 1.234 → 1234 (thousands)
            if mult == 1.0 and len(parts[0]) <= 3:
                num = num.replace('.', '')
    try:
        v = float(num) * mult
        return -v if neg else v
    except Exception:
        return None


def _parse_wide_year_columns_v56(df):
    """
    Parse wide format có cột dạng '2024_EPS', '2024_LNST', '2025_EPS'...
    → long format [ticker, metric_name, period, value]
    """
    if df is None or df.empty:
        return _EMPTY_LONG_V56

    def _n(c):
        s = str(c).strip().lower()
        s = re.sub(r'[\s\-\.\(\)]+', '_', s)
        return re.sub(r'_+', '_', s).strip('_')

    df = df.rename(columns={c: _n(c) for c in df.columns})
    ticker_col = None
    for c in df.columns:
        if c in ('mã', 'ma', 'ma_ck', 'ticker', 'symbol', 'mã_cp'):
            ticker_col = c
            break
    if ticker_col is None:
        return _EMPTY_LONG_V56

    METRIC_MAP = {
        'eps': 'eps',
        'lnst': 'loi_nhuan_sau_thue',
        'loi_nhuan_sau_thue': 'loi_nhuan_sau_thue',
        'lntt': 'loi_nhuan_truoc_thue',
        'loi_nhuan_truoc_thue': 'loi_nhuan_truoc_thue',
        'doanh_thu': 'doanh_thu_thuan',
        'doanh_thu_thuan': 'doanh_thu_thuan',
        'von_chu_so_huu': 'von_chu_so_huu',
        'tong_tai_san': 'tong_tai_san',
        'co_tuc': 'co_tuc_cp',
        'pe': 'pe', 'pb': 'pb',
        'roe': 'roe', 'roa': 'roa',
    }

    records = []
    for col in df.columns:
        if col == ticker_col:
            continue
        m = re.match(r'^(\d{4})_(.+)$', col)
        if not m:
            continue
        year   = m.group(1)
        metric = m.group(2)
        metric_name = METRIC_MAP.get(metric, metric)

        for _, row in df.iterrows():
            tk = str(row[ticker_col]).strip().upper()
            if not tk or tk in ('NAN', 'NONE', '', 'MÃ', 'MA'):
                continue
            v = _parse_unit_value_v56(row[col])
            if v is None:
                continue
            records.append({'ticker': tk, 'metric_name': metric_name,
                            'period': year, 'value': v})
    if not records:
        return _EMPTY_LONG_V56
    out = pd.DataFrame(records).drop_duplicates(
        subset=['ticker', 'metric_name', 'period'], keep='last').reset_index(drop=True)
    return out


def load_master_csv_v56(quiet=False):
    """
    Đọc master CSV. Ưu tiên:
      1. Long format (ticker/metric_name/period/value) — qua _load_csv_db_to_df
      2. Wide format với cột 'YYYY_METRIC'
    """
    if not MASTER_CSV_PATH_V56:
        if not quiet:
            print(f"[v56-MASTER] ❌ Không tìm thấy {_MASTER_CSV_RELATIVE}")
        return _EMPTY_LONG_V56

    if not quiet:
        mb = os.path.getsize(MASTER_CSV_PATH_V56) / (1024 * 1024)
        print(f"[v56-MASTER] 📂 {MASTER_CSV_PATH_V56}  ({mb:.2f} MB)")

    df = _load_csv_db_to_df(MASTER_CSV_PATH_V56)
    if not df.empty:
        if not quiet:
            print(f"[v56-MASTER] ✅ LONG format: {len(df):,} rows · "
                  f"{df['ticker'].nunique()} tickers · {df['period'].nunique()} kỳ")
        return df

    # Fallback wide
    if not quiet:
        print(f"[v56-MASTER] ⚠️ Long parse thất bại → thử wide YYYY_METRIC")
    try:
        raw = pd.read_csv(MASTER_CSV_PATH_V56, encoding='utf-8-sig', low_memory=False)
    except UnicodeDecodeError:
        raw = pd.read_csv(MASTER_CSV_PATH_V56, encoding='cp1258', low_memory=False)
    wide = _parse_wide_year_columns_v56(raw)
    if not wide.empty:
        if not quiet:
            print(f"[v56-MASTER] ✅ WIDE format: {len(wide):,} rows · "
                  f"{wide['ticker'].nunique()} tickers")
        return wide
    return _EMPTY_LONG_V56


# ============================================================================
# [v56.3] EMBEDDED FALLBACK — chỉ dùng khi master CSV VẮNG
# ============================================================================
_FIN_100_MA_FALLBACK = {
    'AAA': (827, 368.6, 966, 372.9), 'ACB': (2824, 16790.0, 2674, 15620.0),
    'ADS': (667, 50.1, 1266, 96.7), 'AGR': (474, 135.2, 500, 141.9),
    'ANV': (179, 47.8, 3754, 999.5), 'BAF': (1286, 317.0, 412, 126.6),
    'BCM': (2008, 2190.0, 3249, 3500.0), 'BFC': (5486, 357.5, 4878, 309.9),
    'BHN': (1599, 370.7, 2016, 467.2), 'BIC': (2083, 495.8, 2686, 542.7),
    'BID': (3008, 25210.0, 3532, 29900.0), 'BMI': (1278, 237.7, 1469, 257.2),
    'BMP': (12103, 990.8, 15010, 1230.0), 'BSI': (1413, 413.1, 1829, 493.7),
    'BSR': (796, 31.1, 1040, 5210.0), 'BWE': (2357, 638.9, 3657, 991.0),
    'CHP': (1897, 313.8, 2781, 458.3), 'CII': (641, 259.7, 196, 124.1),
    'CMG': (1157, 336.5, 1234, 348.6), 'CSM': (623, 72.1, 411, 42.6),
    'CTD': (2768, 309.6, 4136, 453.8), 'CTG': (3083, 25350.0, 4455, 34600.0),
    'CTR': (4201, 538.2, 4681, 599.7), 'CTS': (759, 231.1, 2121, 577.4),
    'DBD': (2530, 275.2, 2674, 291.9), 'DCM': (2359, 1420.0, 3203, 1960.0),
    'DGC': (7392, 2990.0, 7402, 2990.0), 'DHG': (5763, 778.9, 6308, 852.4),
    'DIG': (155, 114.5, 988, 646.5), 'DLG': (695, 207.9, 1218, 364.7),
    'DMC': (4962, 202.7, 4856, 198.4), 'DPM': (620, 537.8, 1427, 1070.0),
    'DRC': (1559, 240.8, 767, 118.5), 'DSC': (669, 176.8, 1268, 275.2),
    'DVP': (8406, 336.2, 8454, 338.2), 'DXG': (254, 255.9, 188, 230.9),
    'DXS': (236, 140.7, 589, 351.5), 'EIB': (1663, 3330.0, 610, 1140.0),
    'FIT': (351, 119.3, 118, 40.0), 'FMC': (4675, 305.7, 5332, 348.7),
    'FPT': (4292, 7860.0, 5216, 9380.0), 'FRT': (1748, 317.5, 4431, 794.9),
    'FTS': (1431, 567.3, 1055, 396.8), 'GAS': (4140, 10400.0, 4647, 11410.0),
    'GEE': (2495, 1590.0, 5098, 3260.0), 'GEG': (166, 114.8, 1655, 708.5),
    'GEX': (1165, 1630.0, 1092, 1480.0), 'GMD': (4276, 1460.0, 3839, 1760.0),
    'GVR': (895, 3990.0, 1250, 5320.0), 'HAH': (3773, 650.5, 6830, 1210.0),
    'HCM': (1267, 1040.0, 1468, 1180.0), 'HDB': (2816, 12760.0, 3297, 16500.0),
    'HDC': (336, 66.1, 3095, 639.1), 'HDG': (855, 348.3, 1893, 770.4),
    'HHV': (907, 426.4, 1183, 580.8), 'HNA': (1076, 271.6, 2023, 475.8),
    'HPG': (1368, 12020.0, 1794, 15450.0), 'HT1': (101, 60.1, 717, 273.7),
    'HVN': (2692, 7560.0, 2949, 7200.0), 'IDI': (248, 60.5, 469, 128.0),
    'IJC': (809, 354.1, 1318, 597.4), 'IMP': (1932, 320.9, 1976, 349.1),
    'KBC': (498, 381.9, 2450, 2100.0), 'KDC': (88, 37.3, 1803, 522.4),
    'KDH': (720, 810.4, 870, 1050.0), 'KOS': (99, 21.4, 88, 18.9),
    'LGC': (2532, 531.8, 2590, 510.4), 'LPB': (3221, 9720.0, 3824, 11420.0),
    'MBB': (2251, 22630.0, 2891, 26780.0), 'MCH': (5998, 7800.0, 5557, 6670.0),
    'MCM': (1799, 219.9, 1765, 215.7), 'MIG': (1163, 238.5, 1553, 324.9),
    'MSB': (1474, 5520.0, 1503, 5630.0), 'MSH': (3322, 412.5, 5456, 613.9),
    'MSN': (1345, 2000.0, 2710, 4110.0), 'MWG': (2546, 3720.0, 4774, 7030.0),
    'NAB': (2361, 6100.0, 2418, 6250.0), 'NKG': (1225, 453.0, 411, 197.1),
    'NLG': (1177, 517.9, 1363, 701.4), 'NSC': (9981, 217.9, 12278, 219.3),
    'NT2': (190, 54.7, 3829, 1100.0), 'NTC': (12050, None, 13410, 321.8),
    'NTL': (4728, 620.1, 133, 17.4), 'NVL': (-3004, -6450.0, 807, 1740.0),
    'OCB': (1026, 3170.0, 1299, 4010.0), 'OGC': (394, 119.3, 224, 67.1),
    'ORS': (1135, 379.1, 352, 118.5), 'PAN': (2091, 608.9, 2556, 672.7),
    'PC1': (1001, 467.6, 2235, 1040.0), 'PDN': (5808, 347.2, 7350, 436.5),
    'PDR': (170, 155.1, 534, 515.1), 'PET': (904, 149.7, 1567, 258.1),
    'PGD': (2265, 249.2, 1579, 168.4), 'PGI': (1493, 232.2, 2214, 245.5),
    'PGV': (-724, -878.4, 3067, 3720.0), 'PHR': (1731, 460.0, 1802, 478.2),
    'PLX': (1509, 2890.0, 1472, 2680.0), 'PNJ': (3809, 2110.0, 5101, 2830.0),
    'POW': (321, 1110.0, 871, 2430.0), 'PPC': (1332, 427.1, 530, 169.9),
}

_PRICE_100_MA_FALLBACK = {
    'AAA': 7075, 'ACB': 21000, 'ANV': 22900, 'BAF': 30600, 'BCM': 38400,
    'BHN': 26200, 'BID': 33400, 'BMP': 137500, 'BSI': 26600, 'BSR': 27600,
    'BWE': 42800, 'CII': 13200, 'CTD': 64000, 'CTG': 30300, 'CTR': 67400,
    'CTS': 21000, 'DBD': 45750, 'DCM': 33300, 'DGC': 33300, 'DHG': 86900,
    'DIG': 9550, 'DPM': 20400, 'DXG': 10100, 'EIB': 16100, 'FPT': 52700,
    'FRT': 148700, 'FTS': 17900, 'GAS': 78000, 'GEE': 66300, 'GEG': 11700,
    'GEX': 22200, 'GMD': 52700, 'GVR': 31250, 'HAH': 49650, 'HCM': 23200,
    'HDB': 22400, 'HDG': 15000, 'HHV': 9300, 'HNA': 21000, 'HPG': 21000,
    'HT1': 12900, 'HVN': 20750, 'IMP': 35800, 'KBC': 26000, 'KDC': 50200,
    'KDH': 13900, 'LGC': 64800, 'LPB': 36100, 'MBB': 19300, 'MCH': 135000,
    'MSB': 15800, 'MSN': 70000, 'MWG': 74000, 'NAB': 12650, 'NKG': 11900,
    'NLG': 22000, 'NT2': 22500, 'NVL': 10400, 'OCB': 10600, 'ORS': 14150,
    'PC1': 18500, 'PDN': 82900, 'PDR': 11300, 'PET': 51100, 'PGV': 20550,
    'PHR': 31000, 'PLX': 34000, 'PNJ': 15500, 'POW': 12200,
}
PRICE_FALLBACK_AS_OF = '2026-10-23'


# ============================================================================
# [v56.4] LOADER GIÁ — XLSX → CSV ALT → EMBEDDED → SNAPSHOT
# ============================================================================
def _parse_price_value_v56(raw):
    if raw is None:
        return 0
    if isinstance(raw, (int, float)):
        try:
            v = float(raw)
            return int(v) if v > 0 else 0
        except Exception:
            return 0
    s = str(raw).strip()
    if not s or '—' in s or s.lower() in ('none', 'nan', '', '-'):
        return 0
    nums = re.findall(r'\d[\d,\.]*', s)
    parsed = []
    for n in nums:
        n2 = n.replace(',', '').replace('.', '')
        try:
            parsed.append(float(n2))
        except Exception:
            continue
    if not parsed:
        return 0
    if len(parsed) >= 2:
        return int(round((parsed[0] + parsed[1]) / 2))
    return int(parsed[0])


def _price_dict_from_df_v56(df):
    if df is None or df.empty:
        return {}
    def _n(c):
        s = str(c).strip().lower()
        s = re.sub(r'[\s\-\.\(\)]+', '_', s)
        return re.sub(r'_+', '_', s).strip('_')
    df = df.rename(columns={c: _n(c) for c in df.columns})
    tcol = next((c for c in df.columns if c in ('mã', 'ma', 'ticker', 'symbol')), None)
    pcol = next((c for c in df.columns if c.startswith('gia') or 'price' in c), None)
    if not tcol or not pcol:
        return {}
    out = {}
    for _, r in df.iterrows():
        tk = str(r[tcol]).strip().upper()
        if not tk or tk in ('NAN', 'NONE', 'MÃ', ''):
            continue
        p = _parse_price_value_v56(r[pcol])
        if p > 0:
            out[tk] = p
    return out


def load_price_table_v56():
    """Trả dict {ticker: price_vnd}. Nguồn: XLSX sheet → CSV alt → Embedded."""
    # 1. XLSX sheet
    xp = PRICE_PATHS_V56.get('xlsx')
    if xp:
        try:
            xl = pd.ExcelFile(xp)
            sheets = xl.sheet_names
            cand = None
            for cs in _PRICE_SHEET_CANDIDATES:
                for s in sheets:
                    if s.lower().strip() == cs.lower():
                        cand = s
                        break
                if cand:
                    break
            order = ([cand] if cand else []) + [s for s in sheets if s != cand]
            for sh in order:
                try:
                    prices = _price_dict_from_df_v56(xl.parse(sh))
                    if prices:
                        print(f"[v56-PRICE] ✅ {len(prices)} mã ← xlsx sheet '{sh}'")
                        return prices
                except Exception:
                    continue
        except Exception as e:
            print(f"[v56-PRICE] ⚠️ Đọc xlsx lỗi: {e}")

    # 2. CSV alt
    cp = PRICE_PATHS_V56.get('csv')
    if cp:
        try:
            try:
                df = pd.read_csv(cp, encoding='utf-8-sig', low_memory=False)
            except UnicodeDecodeError:
                df = pd.read_csv(cp, encoding='cp1258', low_memory=False)
            prices = _price_dict_from_df_v56(df)
            if prices:
                print(f"[v56-PRICE] ✅ {len(prices)} mã ← csv '{os.path.basename(cp)}'")
                return prices
        except Exception as e:
            print(f"[v56-PRICE] ⚠️ Đọc csv alt lỗi: {e}")

    # 3. Embedded
    print(f"[v56-PRICE] ℹ️ Dùng EMBEDDED fallback ({len(_PRICE_100_MA_FALLBACK)} mã)")
    return dict(_PRICE_100_MA_FALLBACK)


# ============================================================================
# [v56.5] POPULATE PIPELINE — 5 BƯỚC
# ============================================================================
def _populate_from_master_v56(quiet=False):
    """Bước 1: đọc MASTER CSV → populate 2 dict (động, mọi mã)."""
    global BANK_DATA_LATEST, CORP_DATA_LATEST, BANK_TICKERS, CORP_TICKERS

    long_df = load_master_csv_v56(quiet=quiet)
    if long_df.empty:
        return 0, 0

    # Auto-detect scale (dữ liệu tỷ vs VND vs triệu)
    scale = _detect_file_scale(long_df, quiet=quiet)

    # Tách bank vs corp
    bank_subs, corp_subs = [], []
    for tk in long_df['ticker'].unique():
        t = _canonical_ticker(tk)
        sub = long_df[long_df['ticker'] == tk]
        if t in _SNAPSHOT_BANK_SET or t in BANK_TICKERS:
            bank_subs.append(sub)
        else:
            corp_subs.append(sub)
    bank_long = pd.concat(bank_subs, ignore_index=True) if bank_subs else _EMPTY_LONG_V56
    corp_long = pd.concat(corp_subs, ignore_index=True) if corp_subs else _EMPTY_LONG_V56

    n_b = _populate_one_group(bank_long, BANK_DATA_LATEST, "Ngân hàng & Tài chính", scale=scale)
    n_c = _populate_one_group(corp_long, CORP_DATA_LATEST, "Doanh nghiệp niêm yết",     scale=scale)

    BANK_TICKERS = set(BANK_TICKERS) | set(BANK_DATA_LATEST.keys())
    CORP_TICKERS = set(CORP_DATA_LATEST.keys())
    if not quiet:
        print(f"[v56-MASTER] ✅ Populate: {n_b} bank + {n_c} corp từ master CSV")
    return n_b, n_c


def _populate_from_embedded_fallback_v56(fill_only=True):
    """Bước dự phòng: chỉ fill mã KHÔNG có trong master CSV."""
    global BANK_DATA_LATEST, CORP_DATA_LATEST, BANK_TICKERS, CORP_TICKERS
    n = 0
    for t, (eps24, lnst24, eps25, lnst25) in _FIN_100_MA_FALLBACK.items():
        t = _canonical_ticker(t)
        if fill_only and (t in BANK_DATA_LATEST or t in CORP_DATA_LATEST):
            continue
        is_bank = t in _SNAPSHOT_BANK_SET
        target  = BANK_DATA_LATEST if is_bank else CORP_DATA_LATEST

        eps_use  = eps25 if eps25 else eps24
        lnst_use = lnst25 if lnst25 else lnst24

        existing = target.get(t, {})
        if not existing.get('eps') and eps_use:
            existing['eps'] = float(eps_use)
            existing['eps_ttm_vnd'] = float(eps_use)
            existing['has_eps'] = True
            existing['_eps_source'] = 'FALLBACK_100MA'
        if lnst24 is not None and not existing.get('lnst_2024_ty'):
            existing['lnst_2024_ty'] = float(lnst24)
        if lnst25 is not None and not existing.get('lnst_2025_ty'):
            existing['lnst_2025_ty'] = float(lnst25)
        if lnst_use and not existing.get('lnst_6m_ty'):
            existing['lnst_6m_ty'] = float(lnst_use)
            existing['profit_ty']   = float(lnst_use)
        existing['sector'] = (existing.get('sector')
                              or COMPANY_MAPPING.get(t, {}).get(
                                  'sector', 'Ngân hàng' if is_bank else 'Doanh nghiệp niêm yết'))
        existing.setdefault('_data_source', 'FALLBACK_100MA')
        target[t] = existing
        n += 1

    BANK_TICKERS = set(BANK_TICKERS) | set(BANK_DATA_LATEST.keys())
    CORP_TICKERS = set(CORP_DATA_LATEST.keys())
    return n


def _populate_from_csv_v56():
    """
    PIPELINE v56 HOÀN CHỈNH:
        1) MASTER CSV (đầy đủ mã, đọc động)
        2) 9 CSV gốc mới (v55) — fill gap
        3) 3 CSV cũ + supplement + snapshot (v55/v54) — fill gap
        4) Embedded 100-mã — fallback nếu master CSV thiếu
    """
    print("\n" + "=" * 78)
    print("[v56-PIPELINE] 🚀 MASTER CSV → 9 CSV → 3 CSV → EMBEDDED FALLBACK")
    print("=" * 78)

    # 1. Master
    _populate_from_master_v56(quiet=False)

    # 2. v55 (9 CSV mới + v54 gốc + snapshot) — chỉ fill gap
    try:
        _populate_from_csv_v55()
    except Exception as e:
        print(f"[v56-PIPELINE] ⚠️ v55 lỗi: {e}")

    # 3. Embedded fallback cho mã KHÔNG có trong CSV
    n_fb = _populate_from_embedded_fallback_v56(fill_only=True)
    if n_fb:
        print(f"[v56-PIPELINE] ✅ Embedded fallback bổ sung: {n_fb} mã")

    print(f"\n[v56-PIPELINE] ✅ HOÀN TẤT — BANK={len(BANK_DATA_LATEST)} "
          f"CORP={len(CORP_DATA_LATEST)}")
    print("=" * 78 + "\n")


# ============================================================================
# [v56.6] PUBLIC API — TỰ CHỌN NGUỒN ĐÚNG
# ============================================================================
def _compute_shares_from_lnst_eps(lnst_ty, eps):
    if lnst_ty and eps and eps > 0 and lnst_ty > 0:
        return (float(lnst_ty) * 1e9) / float(eps)
    return 0.0


def _enrich_100_ma_dict(t, existing):
    """Nếu thiếu giá/SLCP/vốn hóa → thử từ embedded price table."""
    price = _PRICE_100_MA_FALLBACK.get(t, 0)
    if price > 0 and not existing.get('price_vnd'):
        existing['price_vnd'] = float(price)
        existing['gia_hien_tai'] = float(price)
        existing.setdefault('price_as_of', PRICE_FALLBACK_AS_OF)
    # SLCP từ LNST/EPS
    eps = existing.get('eps_ttm_vnd') or existing.get('eps') or 0
    lnst = existing.get('lnst_2025_ty') or existing.get('lnst_6m_ty') or 0
    if not existing.get('shares') and lnst and eps:
        shares = _compute_shares_from_lnst_eps(lnst, eps)
        if shares > 0:
            existing['shares'] = shares
            existing['shares_is_estimated'] = True
            existing['shares_basis'] = 'computed_lnst_div_eps'
    # Vốn hóa = Giá × SLCP
    p = existing.get('price_vnd', 0)
    s = existing.get('shares', 0)
    if p > 0 and s > 0 and not existing.get('market_cap_ty'):
        mc = p * s / 1e9
        existing['market_cap_ty'] = mc
        existing['market_cap'] = mc * 1e9
    # P/E
    if not existing.get('pe'):
        if p > 0 and eps and eps > 0:
            pe = p / eps
            if PE_MIN <= pe <= PE_MAX * 3:
                existing['pe'] = round(pe, 2)
                existing['pe_ttm'] = existing['pe']
                existing.setdefault('_pe_source', 'COMPUTED')
    return existing


def get_financials_v56(ticker, csv_df=None, use_supplement=True):
    """API chính v56 — ưu tiên dict toàn cục (đã populate từ master CSV)."""
    t = _canonical_ticker(ticker)
    data = BANK_DATA_LATEST.get(t) or CORP_DATA_LATEST.get(t)
    if data:
        data = dict(data)
        data = _enrich_100_ma_dict(t, data)
        # Đảm bảo schema chuẩn
        if 'gia_hien_tai' not in data:
            data['gia_hien_tai'] = data.get('price_vnd', 0)
        if 'eps' not in data:
            data['eps'] = data.get('eps_ttm_vnd', 0)
        data['_priority_trace'] = {
            'ticker': t,
            'data_source': data.get('_data_source', 'POPULATED_DICT'),
            'eps_source': data.get('_eps_source', ''),
            'pe_source': data.get('_pe_source', ''),
            'shares_basis': data.get('shares_basis', 'unknown'),
        }
        return data
    # Fallback: v55 dynamic (đọc lại CSV)
    return get_financials_csv_first_v55(t, csv_df=csv_df, use_supplement=use_supplement)


def get_price_v56(ticker):
    t = _canonical_ticker(ticker)
    data = BANK_DATA_LATEST.get(t) or CORP_DATA_LATEST.get(t) or {}
    p = float(data.get('price_vnd') or 0)
    if p > 0:
        return {'ticker': t, 'price_vnd': p,
                'price_as_of': data.get('price_as_of', PRICE_FALLBACK_AS_OF),
                'source': data.get('_data_source', 'POPULATED')}
    p = _PRICE_100_MA_FALLBACK.get(t, 0)
    if p > 0:
        return {'ticker': t, 'price_vnd': float(p),
                'price_as_of': PRICE_FALLBACK_AS_OF, 'source': 'EMBEDDED'}
    snap = LATEST_MARKET_SNAPSHOT.get(t, {})
    if snap.get('price_vnd', 0) > 0:
        return {'ticker': t, 'price_vnd': float(snap['price_vnd']),
                'price_as_of': snap.get('price_as_of', ''), 'source': 'SNAPSHOT_V54'}
    return {'ticker': t, 'price_vnd': 0.0, 'price_as_of': '', 'source': 'MISSING'}


def get_market_cap_v56(ticker):
    t = _canonical_ticker(ticker)
    data = BANK_DATA_LATEST.get(t) or CORP_DATA_LATEST.get(t) or {}
    mc = float(data.get('market_cap_ty') or 0)
    if mc > 0:
        return {'ticker': t, 'market_cap_ty': mc,
                'source': data.get('_data_source', 'POPULATED')}
    p = get_price_v56(t)['price_vnd']
    s = data.get('shares', 0)
    if p > 0 and s > 0:
        return {'ticker': t, 'market_cap_ty': p * s / 1e9, 'source': 'COMPUTED'}
    return {'ticker': t, 'market_cap_ty': 0.0, 'source': 'MISSING'}


# ============================================================================
# [v56.7] AUDIT
# ============================================================================
def get_master_status_v56():
    """DataFrame trạng thái nguồn dữ liệu."""
    rows = [
        {'source': 'MASTER CSV', 'path': MASTER_CSV_PATH_V56 or _MASTER_CSV_RELATIVE,
         'found': bool(MASTER_CSV_PATH_V56),
         'size_kb': round(os.path.getsize(MASTER_CSV_PATH_V56)/1024, 1) if MASTER_CSV_PATH_V56 else 0},
    ]
    for k, v in PRICE_PATHS_V56.items():
        rows.append({'source': f'PRICE_{k}', 'path': v or '',
                     'found': bool(v),
                     'size_kb': round(os.path.getsize(v)/1024, 1) if v else 0})
    rows.append({'source': 'EMBEDDED_FIN', 'path': 'inline',
                 'found': True, 'size_kb': len(_FIN_100_MA_FALLBACK)})
    rows.append({'source': 'EMBEDDED_PRICE', 'path': 'inline',
                 'found': True, 'size_kb': len(_PRICE_100_MA_FALLBACK)})
    return pd.DataFrame(rows)


def get_coverage_v56():
    """DataFrame các mã đã nạp + nguồn."""
    rows = []
    for t in sorted(set(list(BANK_DATA_LATEST.keys()) + list(CORP_DATA_LATEST.keys()))):
        d = BANK_DATA_LATEST.get(t) or CORP_DATA_LATEST.get(t) or {}
        rows.append({
            'ticker': t,
            'is_bank': t in BANK_DATA_LATEST,
            'price_vnd': d.get('price_vnd', 0),
            'eps': d.get('eps', 0),
            'pe': d.get('pe', 0),
            'lnst_2024_ty': d.get('lnst_2024_ty', 0),
            'lnst_2025_ty': d.get('lnst_2025_ty', 0),
            'shares_mn': (d.get('shares') or 0) / 1e6,
            'market_cap_ty': d.get('market_cap_ty', 0),
            'data_source': d.get('_data_source', ''),
        })
    return pd.DataFrame(rows)


def print_audit_v56():
    print("\n" + "=" * 92)
    print("[v56-AUDIT] NGUỒN + PHỦ SÓNG")
    print("=" * 92)
    print(get_master_status_v56().to_string(index=False))
    cov = get_coverage_v56()
    print(f"\n  Tổng mã đã nạp: {len(cov)}  "
          f"(bank={int(cov['is_bank'].sum())}, corp={int((~cov['is_bank']).sum())})")
    print(f"  Có giá:        {int((cov['price_vnd'] > 0).sum())}/{len(cov)}")
    print(f"  Có EPS:        {int((cov['eps'] != 0).sum())}/{len(cov)}")
    print(f"  Có P/E:        {int((cov['pe'] > 0).sum())}/{len(cov)}")
    print("=" * 92 + "\n")
    return cov


# ============================================================================
# [v56.8] MỞ RỘNG __all__
# ============================================================================
try:
    from du_lieu.doc_bctc_goc import __all__ as _V55_ALL
    __all__ = list(_V55_ALL) + [
        'MASTER_CSV_PATH_V56', 'PRICE_PATHS_V56',
        '_MASTER_CSV_FILENAME', '_MASTER_CSV_RELATIVE',
        '_FIN_100_MA_FALLBACK', '_PRICE_100_MA_FALLBACK',
        'load_master_csv_v56', 'load_price_table_v56',
        '_populate_from_master_v56',
        '_populate_from_embedded_fallback_v56',
        '_populate_from_csv_v56',
        'get_financials_v56', 'get_price_v56', 'get_market_cap_v56',
        'get_master_status_v56', 'get_coverage_v56', 'print_audit_v56',
    ]
except Exception:
    pass
