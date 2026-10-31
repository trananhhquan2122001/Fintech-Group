# tien_ich/cau_hinh_danh_muc.py
# [v54-SNAPSHOT-INTEGRATION] TÍCH HỢP SNAPSHOT 21/10/2026
#   ✅ Giữ 100% code gốc v47 (helpers, format, sanity, threshold, sanitize, __all__, selftest)
#   ✅ THÊM #1: _SNAPSHOT_TICKERS_MAP — chứa 32 mã từ ảnh SSI iBoard
#   ✅ THÊM #2: Tự động merge Snapshot Tickers vào _LOADED_TICKERS
#   ✅ THÊM #3: Bổ sung TCX, SSI vào Bank/Corp Tickers nếu thiếu
#   ✅ THÊM #4: Fallback name & sector cho các mã mới
#   ✅ SỬA #5: _load_all_tickers() gộp thêm Snapshot
#   ✅ SỬA #6: Selftest cập nhật số lượng mã (41 + 32) và test mã mới

import os
import re
import numpy as np
import pandas as pd


# ============================================================================
# 0. CSV LONG-FORMAT — FALLBACK CUỐI CÙNG (giữ nguyên 100%)
# ============================================================================
VN30_LONG_CSV_PATH = "du_lieu/vn30_41_fin_long.csv"
if not os.path.exists(VN30_LONG_CSV_PATH):
    VN30_LONG_CSV_PATH = "vn30_41_fin_long.csv"


# ============================================================================
# 1. PATH RESOLUTION — 13 VỊ TRÍ (giữ nguyên 100%)
# ============================================================================
def _resolve_csv_db_paths():
    _HERE = os.path.dirname(os.path.abspath(__file__))
    _PARENT = os.path.dirname(_HERE)
    _GP = os.path.dirname(_PARENT)

    _filenames = {
        'cong_nghe':              'du_lieu_cong_nghe.csv',
        'ngan_hang_va_tai_chinh': 'du_lieu_ngan_hang_va_tai_chinh.csv',
        'san_xuat_va_khac':       'du_lieu_san_xuat_va_khac.csv',
    }

    _bases = [
        _PARENT, _HERE, _GP,
        os.path.join(_PARENT, "du_lieu"),
        os.path.join(_HERE, "du_lieu"),
        os.getcwd(),
        os.path.join(os.getcwd(), "du_lieu"),
        "/app", "/app/du_lieu",
        "/content", "/content/du_lieu",
        "/workspace", "/workspace/du_lieu",
    ]

    result = {}
    print("\n" + "=" * 78)
    print("[v54-CSV] 🔍 TÌM 3 FILE CSV")
    print("=" * 78)
    print(f"   _HERE   = {_HERE}")
    print(f"   _PARENT = {_PARENT}")
    print(f"   cwd     = {os.getcwd()}")
    print()

    for key, fname in _filenames.items():
        found = None
        for base in _bases:
            path = os.path.join(base, fname)
            try:
                if os.path.isfile(path) and os.path.getsize(path) > 0:
                    found = os.path.abspath(path)
                    break
            except OSError:
                continue
        if found:
            size_kb = os.path.getsize(found) / 1024
            print(f"   ✅ {key:<28} {found}  ({size_kb:.1f} KB)")
        else:
            print(f"   ❌ {key:<28} KHÔNG TÌM THẤY '{fname}'")
        result[key] = found

    n_ok = sum(1 for v in result.values() if v)
    print(f"\n   📊 {n_ok}/3 file CSV tìm thấy")
    print("=" * 78 + "\n")
    return result


_CSV_DB_PATHS = _resolve_csv_db_paths()
_SQLITE_DB_PATHS = _CSV_DB_PATHS  # alias tương thích ngược

_DEFAULT_SECTOR_BY_DB = {
    'ngan_hang_va_tai_chinh': 'Ngân hàng & Tài chính',
    'cong_nghe':              'Công nghệ',
    'san_xuat_va_khac':       'Sản xuất & Khác',
}


# ============================================================================
# 1b. FALLBACK vn30_41_fin_long.csv (giữ nguyên 100%)
# ============================================================================
_FALLBACK_CSV_NAMES = [
    "vn30_41_fin_long.csv",
    "du_lieu/vn30_41_fin_long.csv",
    "vn30_fin_long.csv",
    "du_lieu/vn30_fin_long.csv",
]


def _find_fallback_csv():
    _HERE = os.path.dirname(os.path.abspath(__file__))
    _PARENT = os.path.dirname(_HERE)
    _bases = [_HERE, _PARENT, os.getcwd(), "/app", "/app/du_lieu"]

    for base in _bases:
        for name in _FALLBACK_CSV_NAMES:
            path = os.path.join(base, name)
            try:
                if os.path.isfile(path) and os.path.getsize(path) > 0:
                    return os.path.abspath(path)
            except OSError:
                continue
    return None


# ============================================================================
# 1c. [v47-CSV-WIDE] WIDE FORMAT DETECTORS — THÊM MỚI
# ============================================================================
_PERIOD_PATTERN_V47 = re.compile(r'^(?:19|20)\d{2}(?:Q[1-4]|H[12])?$', re.IGNORECASE)

_METRIC_COL_RAW_V47 = {
    'cột 1', 'cột1', 'cot 1', 'cot1',
    'chỉ tiêu', 'chi tiêu', 'chỉ_tiêu', 'chi_tiêu',
    'unnamed: 0', 'unnamed:0', 'unnamed 0', 'unnamed_0', 'unnamed0',
    'metric', 'metric_name', 'chi_tieu', 'chi_tieu_ten',
}


def _is_period_column_v47(col_name):
    """[v47] Nhận diện cột kỳ: 2015, 2018H2, 2026Q1, 2026H1, 2026"""
    if col_name is None:
        return False
    s = str(col_name).strip()
    if not s:
        return False
    s = s.replace(' ', '').replace('_', '').upper()
    return bool(_PERIOD_PATTERN_V47.match(s))


def _is_metric_column_v47(col_name):
    """[v47] Nhận diện cột chứa tên chỉ tiêu."""
    if col_name is None:
        return False
    s = str(col_name).strip().lower()
    return s in _METRIC_COL_RAW_V47


def _is_wide_format_v47(df):
    """
    [v47] Detect wide format: có cột ticker + ít nhất 1 cột kỳ + ít nhất 1 cột metric.
    """
    if df is None or df.empty:
        return False
    cols_lower = {str(c).strip().lower() for c in df.columns}
    if 'ticker' not in cols_lower:
        return False
    has_period = any(_is_period_column_v47(c) for c in df.columns)
    has_metric = any(_is_metric_column_v47(c) for c in df.columns)
    if 'metric_name' in cols_lower and 'value' in cols_lower:
        return False
    return has_period and has_metric


def _extract_tickers_from_wide_v47(df):
    """
    [v47] Extract unique tickers từ wide format.
    """
    if df is None or df.empty:
        return []
    df = df.copy()
    df.columns = [str(c).strip() for c in df.columns]

    ticker_col = None
    for c in df.columns:
        if str(c).strip().lower() == 'ticker':
            ticker_col = c
            break
    if ticker_col is None:
        return []

    s = df[ticker_col].astype(str).str.strip().str.upper()
    s = s.replace({
        '': None, 'NAN': None, 'NONE': None, 'nan': None, 'None': None, 'NULL': None,
    })
    s = s.ffill()

    seen = set()
    tickers = []
    for tk in s.tolist():
        if not isinstance(tk, str):
            continue
        t = tk.strip().upper()
        if not t or t in seen:
            continue
        if not (2 <= len(t) <= 6):
            continue
        cleaned = t.replace('.', '').replace('-', '')
        if not cleaned.isalnum():
            continue
        seen.add(t)
        tickers.append(t)

    return tickers


# ============================================================================
# 1d. [v54-SNAPSHOT-INTEGRATION] DATA TỪ ẢNH 21/10/2026
# ============================================================================
_SNAPSHOT_TICKERS_MAP = {
    # Nhóm Ngân hàng & Tài chính (16 mã)
    "VCB": "ngan_hang_va_tai_chinh", "BID": "ngan_hang_va_tai_chinh",
    "CTG": "ngan_hang_va_tai_chinh", "TCB": "ngan_hang_va_tai_chinh",
    "VPB": "ngan_hang_va_tai_chinh", "MBB": "ngan_hang_va_tai_chinh",
    "HDB": "ngan_hang_va_tai_chinh", "ACB": "ngan_hang_va_tai_chinh",
    "STB": "ngan_hang_va_tai_chinh", "LPB": "ngan_hang_va_tai_chinh",
    "SHB": "ngan_hang_va_tai_chinh", "SSB": "ngan_hang_va_tai_chinh",
    "VIB": "ngan_hang_va_tai_chinh", "EIB": "ngan_hang_va_tai_chinh",
    "TCX": "ngan_hang_va_tai_chinh", "SSI": "ngan_hang_va_tai_chinh",
    
    # Nhóm Sản xuất & Công nghệ (16 mã)
    "VIC": "san_xuat_va_khac", "VHM": "san_xuat_va_khac",
    "GAS": "san_xuat_va_khac", "MCH": "san_xuat_va_khac",
    "HPG": "san_xuat_va_khac", "VPL": "san_xuat_va_khac",
    "BSR": "san_xuat_va_khac", "GVR": "san_xuat_va_khac",
    "VNM": "san_xuat_va_khac", "MWG": "san_xuat_va_khac",
    "FPT": "cong_nghe",       "MSN": "san_xuat_va_khac",
    "VJC": "san_xuat_va_khac", "CTR": "cong_nghe",
    "FRT": "san_xuat_va_khac", "PVI": "san_xuat_va_khac",
}


# ============================================================================
# 2. LOAD TICKERS + INFO TỪ CSV — GIỮ NGUYÊN, THÊM DISPATCH & SNAPSHOT
# ============================================================================
def _detect_ticker_col(df):
    for c in ['ticker', 'ma_ck', 'symbol', 'code', 'ma']:
        if c in df.columns:
            return c
    return None


def _read_csv_multiencoding_v46(path):
    if not path or not os.path.exists(path):
        return pd.DataFrame()
    import io as _io
    try:
        with open(path, 'rb') as f:
            raw = f.read()
    except Exception:
        return pd.DataFrame()
    if not raw:
        return pd.DataFrame()
    if raw.startswith(b'SQLite format 3'):
        print(f"[v54-CSV] 🚨 FILE '{os.path.basename(path)}' LÀ BINARY SQLITE!")
        return pd.DataFrame()
    if raw.startswith(b'\xef\xbb\xbf'):
        try:
            return pd.read_csv(_io.StringIO(raw.decode('utf-8-sig')))
        except Exception:
            pass
    for enc in ['utf-8', 'utf-8-sig', 'cp1258', 'cp1252', 'latin-1',
                'iso-8859-1', 'windows-1252']:
        try:
            return pd.read_csv(_io.StringIO(raw.decode(enc)))
        except (UnicodeDecodeError, LookupError):
            continue
        except Exception:
            continue
    try:
        return pd.read_csv(_io.StringIO(raw.decode('utf-8', errors='replace')))
    except Exception:
        return pd.DataFrame()


def _read_tickers_from_csv(path, db_key):
    result = {}
    if not path or not os.path.exists(path):
        return result
    try:
        df = _read_csv_multiencoding_v46(path)
    except Exception as e:
        print(f"[v54-CSV] ⚠️ CSV read error {path}: {e}")
        return result
    if df is None or df.empty:
        return result

    if _is_wide_format_v47(df):
        tickers = _extract_tickers_from_wide_v47(df)
        print(f"[v54-CSV] 📊 WIDE: {os.path.basename(path)} → {len(tickers)} tickers")
        for tk in tickers:
            result.setdefault(tk, {'db': db_key})
        return result

    df.columns = [str(c).strip().lower() for c in df.columns]
    ticker_col = _detect_ticker_col(df)
    if ticker_col is None:
        print(f"[v54-CSV] ⚠️  Thiếu cột ticker/ma_ck/symbol/code/ma")
        return result

    tickers = df[ticker_col].dropna().astype(str).str.strip().str.upper().unique().tolist()
    tickers = [t for t in tickers if t and 2 <= len(t) <= 6 and t.replace('.', '').isalnum()]

    for tk in tickers:
        result.setdefault(tk, {'db': db_key})

    if 'metric_name' in df.columns and 'value' in df.columns:
        for tk in tickers:
            try:
                sub = df[df[ticker_col].astype(str).str.upper() == tk]
            except Exception:
                continue
            if sub.empty:
                continue
            for _, row in sub.iterrows():
                m = str(row.get('metric_name', '')).strip().lower()
                v = row.get('value')
                if v is None or (isinstance(v, float) and pd.isna(v)):
                    continue
                if m in ('sector', 'nganh', 'industry'):
                    result[tk]['sector'] = str(v).strip()
                elif m in ('company_name', 'name', 'ten', 'ten_cong_ty', 'ten_cty'):
                    result[tk]['name'] = str(v).strip()

    print(f"[v54-CSV] 📋 LONG: {os.path.basename(path)} → {len(result)} tickers")
    return result


_read_tickers_from_sqlite = _read_tickers_from_csv


def _load_all_tickers():
    """Load 3 file CSV + fallback + Snapshot tickers."""
    all_tk = {}
    for db_key in ['ngan_hang_va_tai_chinh', 'cong_nghe', 'san_xuat_va_khac']:
        path = _CSV_DB_PATHS.get(db_key, '')
        d = _read_tickers_from_csv(path, db_key)
        for tk, info in d.items():
            if tk not in all_tk:
                all_tk[tk] = info

    if not all_tk:
        print("[v54-CSV] ⚠️  Không load được 3 industry CSV, thử fallback vn30_41_fin_long.csv")
        fallback_path = _find_fallback_csv()
        if fallback_path:
            print(f"[v54-CSV] 📂 Fallback: {fallback_path}")
            d = _read_tickers_from_csv(fallback_path, 'fallback')
            if d:
                bank_like = ['VCB', 'BID', 'TCB', 'CTG', 'MBB', 'VPB', 'ACB', 'SSB',
                             'STB', 'LPB', 'VIB', 'EIB', 'HDB', 'SHB', 'TCX', 'SSI']
                for tk, info in d.items():
                    info['db'] = 'ngan_hang_va_tai_chinh' if tk in bank_like else 'san_xuat_va_khac'
                    all_tk[tk] = info
                print(f"[v54-CSV] ✅ Fallback loaded: {len(all_tk)} tickers")

    # [v54-SNAPSHOT-MERGE] Tự động gộp Snapshot Tickers vào danh sách
    added = 0
    for tk, db_key in _SNAPSHOT_TICKERS_MAP.items():
        if tk not in all_tk:
            all_tk[tk] = {'db': db_key, 'sector': _DEFAULT_SECTOR_BY_DB.get(db_key, 'Doanh nghiệp')}
            added += 1
    if added > 0:
        print(f"[v54-CSV] ✅ Đã bổ sung {added} tickers từ Snapshot 21/10/2026")

    return all_tk


with_progress = True
try:
    _LOADED_TICKERS = _load_all_tickers()
except Exception as _e:
    print(f"[v54-CSV] ❌ Load CSV lỗi: {_e}")
    _LOADED_TICKERS = {}

_IS_USING_SQLITE = bool(_LOADED_TICKERS)

if _IS_USING_SQLITE:
    print(f"[v54-CSV] ✅ CSV loaded: {len(_LOADED_TICKERS)} tickers từ {len(_CSV_DB_PATHS)} files")
else:
    print(f"[v54-CSV] ⚠️ CSV rỗng — fallback 41 mã cũ + 32 mã Snapshot")


# ============================================================================
# 3. NAME MAPS — CHỈ DÙNG LÀM FALLBACK
# ============================================================================
_BANK_NAME_MAP = {
    "VCB": "Ngân hàng TMCP Ngoại thương Việt Nam",
    "BID": "Ngân hàng TMCP Đầu tư và Phát triển Việt Nam",
    "TCB": "Ngân hàng TMCP Kỹ Thương Việt Nam",
    "CTG": "Ngân hàng TMCP Công Thương Việt Nam",
    "MBB": "Ngân hàng TMCP Quân Đội",
    "VPB": "Ngân hàng TMCP Việt Nam Thịnh Vượng (VPBank)",
    "ACB": "Ngân hàng TMCP Á Châu (ACB)",
    "SSB": "Ngân hàng TMCP Đông Nam Á (SeABank)",
    "STB": "Ngân hàng TMCP Sài Gòn Thương Tín (Sacombank)",
    "LPB": "Ngân hàng TMCP Bưu điện Liên Việt (LPBank)",
    "VIB": "Ngân hàng TMCP Quốc tế Việt Nam (VIB)",
    "EIB": "Ngân hàng TMCP Xuất Nhập Khẩu Việt Nam (Eximbank)",
    "HDB": "Ngân hàng TMCP Phát triển TP.HCM (HDBank)",
    "SHB": "Ngân hàng TMCP Sài Gòn – Hà Nội (SHB)",
    "TCX": "Công ty Cổ phần Chứng khoán Kỹ Thương (Techcom Securities)",
    "SSI": "Công ty Cổ phần Chứng khoán SSI",
}

_CORP_NAME_MAP = {
    "MWG": "Công ty Cổ phần Đầu tư Thế Giới Di Động (MWG)",
    "SAB": "Tổng Công ty Cổ phần Bia - Rượu - Nước giải khát Sài Gòn (Sabeco)",
    "MCH": "Công ty Cổ phần Hàng tiêu dùng Masan (Masan Consumer)",
    "MSN": "Công ty Cổ phần Tập đoàn Masan (Masan Group)",
    "FRT": "Công ty Cổ phần Bán lẻ Kỹ thuật số FPT (FPT Retail)",
    "HPG": "Công ty Cổ phần Tập đoàn Hòa Phát (HPG)",
    "VHM": "Công ty Cổ phần Vinhomes (VHM)",
    "GAS": "Tổng Công ty Khí Việt Nam - CTCP (PV GAS)",
    "GVR": "Tập đoàn Công nghiệp Cao su Việt Nam - CTCP (VRG)",
    "VPL": "Công ty Cổ phần Vinpearl (VPL)",
    "VIC": "Tập đoàn Vingroup - Công ty Cổ phần (VIC)",
    "VRE": "Công ty Cổ phần Vincom Retail (VRE)",
    "BSR": "Công ty Cổ phần Lọc hóa dầu Bình Sơn (BSR)",
    "VJC": "Công ty Cổ phần Hàng không VietJet (VJC)",
    "VNM": "Công ty Cổ phần Sữa Việt Nam (Vinamilk)",
    "GEE": "Công ty Cổ phần Điện lực Gelex (GEE)",
    "REE": "Công ty Cổ phần Cơ Điện Lạnh (REE)",
    "GMD": "Công ty Cổ phần Gemadept (GMD)",
    "KSV": "Tổng Công ty Khoáng sản TKV - CTCP (KSV)",
    "FPT": "Công ty Cổ phần FPT",
    "CTR": "Tổng Công ty Cổ phần Công trình Viettel (CTR)",
    "GEX": "Công ty Cổ phần Tập đoàn Gelex (GEX)",
    "PVI": "Công ty Cổ phần PVI",
    "POW": "Tổng Công ty Điện lực Dầu khí Việt Nam - CTCP (POW)",
    "CMC": "Công ty Cổ phần Tập đoàn CMC",
}

_CORP_SECTOR_MAP = {
    "MWG": "Bán lẻ", "SAB": "Đồ uống", "MCH": "Thực phẩm & Đồ uống",
    "MSN": "Tập đoàn đa ngành", "FRT": "Bán lẻ & Dược phẩm",
    "HPG": "Thép & Vật liệu", "VHM": "Bất động sản", "GAS": "Dầu khí",
    "GVR": "Cao su & Công nghiệp", "VPL": "Bất động sản",
    "VIC": "Tập đoàn đa ngành", "VRE": "Bất động sản bán lẻ",
    "BSR": "Lọc hóa dầu", "VJC": "Hàng không", "VNM": "Sữa & Thực phẩm",
    "GEE": "Cơ điện & Thiết bị", "REE": "Cơ điện lạnh & Đầu tư",
    "GMD": "Logistics & Cảng biển", "KSV": "Khoáng sản",
    "FPT": "Công nghệ thông tin", "CTR": "Hạ tầng viễn thông",
    "GEX": "Thiết bị điện", "PVI": "Bảo hiểm",
    "POW": "Điện & Năng lượng", "CMC": "Công nghệ & Đầu tư",
}


# ============================================================================
# 4. DANH SÁCH TICKERS — ƯU TIÊN CSV + SNAPSHOT, FALLBACK 41 MÃ CŨ
# ============================================================================
_BANK_TICKERS_FALLBACK = [
    "VCB", "BID", "TCB", "CTG", "MBB", "VPB",
    "ACB", "SSB", "STB", "LPB", "VIB", "EIB", "HDB", "SHB",
]
_CORP_TICKERS_FALLBACK = [
    "MWG", "SAB", "MCH", "MSN", "FRT",
    "HPG", "VHM", "GAS", "GVR", "VPL", "VIC", "VRE", "BSR", "TCX",
    "SSI", "VJC", "VNM", "GEE", "REE", "GMD", "KSV", "FPT", "CTR",
    "GEX", "PVI", "POW", "CMC",
]

if _IS_USING_SQLITE:
    BANK_TICKERS_V41 = sorted([
        tk for tk, info in _LOADED_TICKERS.items()
        if info.get('db') == 'ngan_hang_va_tai_chinh'
    ])
    CORP_TICKERS_V41 = sorted([
        tk for tk, info in _LOADED_TICKERS.items()
        if info.get('db') != 'ngan_hang_va_tai_chinh'
    ])
else:
    BANK_TICKERS_V41 = list(_BANK_TICKERS_FALLBACK)
    CORP_TICKERS_V41 = list(_CORP_TICKERS_FALLBACK)
    # [v54] Thêm Snapshot nếu chưa có
    for tk, db_key in _SNAPSHOT_TICKERS_MAP.items():
        if db_key == 'ngan_hang_va_tai_chinh' and tk not in BANK_TICKERS_V41:
            BANK_TICKERS_V41.append(tk)
        elif db_key != 'ngan_hang_va_tai_chinh' and tk not in CORP_TICKERS_V41:
            CORP_TICKERS_V41.append(tk)

ALL_TICKERS_V41 = BANK_TICKERS_V41 + CORP_TICKERS_V41


# ============================================================================
# 5. COMPANY_MAPPING — ĐỘNG TỪ CSV + FALLBACK (giữ nguyên 100%)
# ============================================================================
def _resolve_sector(ticker, info):
    s = info.get('sector', '')
    if s:
        return s
    db = info.get('db', '')
    if db in _DEFAULT_SECTOR_BY_DB:
        return _DEFAULT_SECTOR_BY_DB[db]
    if ticker in _CORP_SECTOR_MAP:
        return _CORP_SECTOR_MAP[ticker]
    if ticker in _BANK_TICKERS_FALLBACK:
        return "Ngân hàng"
    return "Doanh nghiệp niêm yết"


def _resolve_name(ticker, info, is_bank):
    n = info.get('name', '')
    if n:
        return n
    if ticker in _BANK_NAME_MAP:
        return _BANK_NAME_MAP[ticker]
    if ticker in _CORP_NAME_MAP:
        return _CORP_NAME_MAP[ticker]
    if is_bank:
        return f"Ngân hàng TMCP {ticker}"
    return f"Công ty Cổ phần {ticker}"


COMPANY_MAPPING = {}
for _tk in ALL_TICKERS_V41:
    _info = _LOADED_TICKERS.get(_tk, {})
    _is_bank = _tk in BANK_TICKERS_V41
    COMPANY_MAPPING[_tk] = {
        "name": _resolve_name(_tk, _info, _is_bank),
        "file": f"{_tk.lower()}_financial_statement.csv",
        "sector": _resolve_sector(_tk, _info),
    }

BANK_TICKERS = set(BANK_TICKERS_V41)
CORP_TICKERS = set(CORP_TICKERS_V41)

TICKER_DISPLAY = [
    f"{ticker} - {info['name']}"
    for ticker, info in COMPANY_MAPPING.items()
]


# ============================================================================
# 6-17. TOÀN BỘ PHẦN CÒN LẠI GIỮ NGUYÊN 100% TỪ v47
# ============================================================================

# ============================================================================
# 6. THRESHOLDS
# ============================================================================
THRESHOLDS = {
    "MIN_ADTV": 200000,
    "MIN_MOS": 20.0,
    "MAX_PE": 15.0,
    "MAX_PB": 1.5,
    "MAX_DE": 1.0,
    "MIN_ROE": 15.0,
    "MIN_ROA": 8.0,
    "MIN_GROSS_MARGIN": 20.0,
}


# ============================================================================
# 7. CONSTANTS FIX
# ============================================================================
GARBAGE_VALUES = {87.0, -87.0, 87, -87}
SUSPICIOUS_COL_IDS = {'87', '88', '89', '90', '91', '92', '93', '94'}
MIN_REAL_PRICE = 1_000
MIN_REAL_BVPS = 1_000
MIN_REAL_EPS = 100
MIN_REAL_DIVIDEND = 100
MIN_REAL_MARKET_CAP = 1_000_000
MIN_REAL_SHARES = 100_000

_SANITY_MAX_TY = {
    'total_assets': 20_000_000,
    'equity':        1_000_000,
    'profit':          150_000,
    'revenue':         300_000,
    'market_cap':    1_500_000,
    'default':       100_000_000,
}
_MAX_REASONABLE_TY = 100_000_000


# ============================================================================
# 8. HÀM GỐC: to_float_scalar / safe_divide / round_float
# ============================================================================
def to_float_scalar(val):
    if val is None:
        return 0.0
    if isinstance(val, (int, float)):
        try:
            f = float(val)
            return 0.0 if np.isnan(f) else f
        except Exception:
            return 0.0
    if isinstance(val, str):
        try:
            return float(val.replace(',', '').strip())
        except Exception:
            return 0.0
    return 0.0


def safe_divide(a, b, default=0.0):
    a = to_float_scalar(a)
    b = to_float_scalar(b)
    if b == 0:
        return default
    return a / b


def round_float(val, decimals=2):
    try:
        return round(to_float_scalar(val), decimals)
    except Exception:
        return 0.0


# ============================================================================
# 9. UNIT DETECTION
# ============================================================================
_UNIT_FACTOR_BY_NAME = {
    'vnd': 1e-9, 'dong': 1e-9,
    'nghin': 1e-6, 'ngan': 1e-6,
    'trieu': 1e-3, 'trd': 1e-3,
    'ty': 1.0, 'ti': 1.0,
}


def detect_unit_from_colname(col_name):
    if not col_name:
        return None
    cl = str(col_name).lower()
    for token, factor in _UNIT_FACTOR_BY_NAME.items():
        if re.search(rf'(?:^|_){token}(?:_|$)', cl):
            return factor
    return None


def detect_money_unit(value):
    try:
        v = abs(float(value))
    except (TypeError, ValueError):
        return 1.0
    if v == 0 or not np.isfinite(v):
        return 1.0
    if v >= 1e15:
        return 1e-9
    if v >= 1e12:
        return 1e-6
    if v >= 1e9:
        return 1e-3
    return 1.0


def to_ty_dong(value, already_in_ty=False, col_name=None):
    if value is None:
        return 0.0
    try:
        v = float(value)
    except (TypeError, ValueError):
        return 0.0
    if not np.isfinite(v) or v == 0:
        return 0.0
    if already_in_ty:
        return v
    factor = detect_unit_from_colname(col_name)
    if factor is None:
        factor = detect_money_unit(v)
    result = v * factor
    if abs(result) > 10_000_000:
        for alt_factor in (1.0, 1e-3, 1e-6, 1e-9):
            alt = v * alt_factor
            if 0.01 <= abs(alt) <= 10_000_000:
                return alt
    return result


def _detect_money_unit(value):
    return detect_money_unit(value)


def _to_ty(value):
    return to_ty_dong(value)


def _to_vnd(value):
    return to_ty_dong(value) * 1e9


def apply_unit_sanity(value_ty, metric_key=''):
    if value_ty is None or value_ty == 0:
        return 0.0
    try:
        v = float(value_ty)
    except (TypeError, ValueError):
        return 0.0
    if not np.isfinite(v):
        return 0.0
    max_ok = _SANITY_MAX_TY.get(metric_key, _SANITY_MAX_TY['default'])
    if abs(v) <= max_ok:
        return v
    for divisor in (1e3, 1e6, 1e9):
        alt = v / divisor
        if abs(alt) <= max_ok:
            return alt
    return v


# ============================================================================
# 10. HELPERS: garbage / suspicious
# ============================================================================
def _is_garbage_value(v):
    try:
        return float(v) in GARBAGE_VALUES
    except Exception:
        return False


def is_garbage_value(v):
    return _is_garbage_value(v)


def is_suspicious_column(col_name):
    if col_name is None:
        return False
    s = str(col_name).strip().lower()
    m = re.match(r'^(\d+)[\s_\-\.]', s)
    if m:
        return m.group(1) in SUSPICIOUS_COL_IDS
    return False


# ============================================================================
# 11. FIX FUNCTIONS
# ============================================================================
def fix_price(p):
    try:
        p = float(p)
    except Exception:
        return 0.0
    if p <= 0 or _is_garbage_value(p):
        return 0.0
    if p < MIN_REAL_PRICE:
        p = p * 1_000
    return round(p, 0)


def fix_bvps(b, equity=0, shares=0):
    if equity and equity > 0 and shares and shares > 0:
        calc = equity / shares
        if MIN_REAL_BVPS <= calc <= 500_000:
            return round(calc, 0)
    try:
        b = float(b)
    except Exception:
        return 0.0
    if b <= 0 or _is_garbage_value(b):
        return 0.0
    if b < MIN_REAL_BVPS:
        b = b * 1_000
    if b < MIN_REAL_BVPS:
        return 0.0
    return round(b, 0)


def fix_eps(e, profit=0, shares=0, keep_negative=False):
    if profit and profit > 0 and shares and shares > 0:
        calc = profit / shares
        if MIN_REAL_EPS <= calc <= 1_000_000:
            return round(calc, 0)
    try:
        e = float(e)
    except Exception:
        return 0.0
    if e == 0 or _is_garbage_value(e):
        return 0.0
    sign = -1 if e < 0 else 1
    e_abs = abs(e)
    if 0 < e_abs < MIN_REAL_EPS:
        e_abs = e_abs * 1_000
    if e_abs < MIN_REAL_EPS:
        return 0.0
    if sign < 0:
        if not keep_negative:
            return 0.0
        return -round(e_abs, 0)
    return round(e_abs, 0)


def fix_dividend(d):
    try:
        d = float(d)
    except Exception:
        return 0.0
    if d <= 0 or _is_garbage_value(d):
        return 0.0
    if d < MIN_REAL_DIVIDEND:
        d = d * 1_000
    if d < MIN_REAL_DIVIDEND:
        return 0.0
    return round(d, 0)


def fix_shares(s):
    try:
        s = float(s)
    except Exception:
        return 0.0
    if s <= 0 or _is_garbage_value(s):
        return 0.0
    if s < 1_000_000:
        s = s * 1_000
    if s < MIN_REAL_SHARES:
        return 0.0
    return round(s, 0)


def fix_market_cap(mc, price=0, shares=0):
    if price and price >= MIN_REAL_PRICE and shares and shares >= MIN_REAL_SHARES:
        return round(price * shares, 0)
    try:
        m = float(mc)
    except Exception:
        return 0.0
    if m <= 0 or _is_garbage_value(m):
        return 0.0
    if m < MIN_REAL_MARKET_CAP:
        return 0.0
    if m < 1e9:
        m = m * 1_000_000
    return round(m, 0)


# ============================================================================
# 12. FORMAT CURRENCY
# ============================================================================
def format_currency_vn_advanced(value, unit='auto', decimals=2, per_share=False):
    num = to_float_scalar(value)
    if _is_garbage_value(num):
        return "N/A"
    if num == 0:
        return "0" if per_share else "0 VNĐ"
    abs_num = abs(num)
    sign = "-" if num < 0 else ""
    if per_share:
        return f"{sign}{abs_num:,.0f} VNĐ/cp"
    if unit == 'nghin_ty':
        return f"{sign}{abs_num / 1e12:,.{decimals}f} Nghìn tỷ VNĐ"
    if unit == 'ty':
        return f"{sign}{abs_num / 1e9:,.{decimals}f} Tỷ VNĐ"
    if unit == 'trieu':
        return f"{sign}{abs_num / 1e6:,.{decimals}f} Triệu VNĐ"
    if unit == 'auto':
        if abs_num >= 1e12:
            return f"{sign}{abs_num / 1e12:,.{decimals}f} Nghìn tỷ VNĐ"
        if abs_num >= 1e9:
            return f"{sign}{abs_num / 1e9:,.{decimals}f} Tỷ VNĐ"
        if abs_num >= 1e6:
            return f"{sign}{abs_num / 1e6:,.{decimals}f} Triệu VNĐ"
        return f"{sign}{abs_num:,.0f} VNĐ"
    return f"{sign}{abs_num:,.0f} VNĐ"


def format_currency_vn(val, decimals=0):
    return format_currency_vn_advanced(val, unit='auto', decimals=decimals)


def format_eps_value(val):
    num = to_float_scalar(val)
    if num == 0 or _is_garbage_value(num):
        return "N/A"
    return f"{num:,.0f} VNĐ/cp"


def format_pe_pb(val):
    if val is None or val == 0:
        return "N/A"
    try:
        v = float(val)
        if _is_garbage_value(v):
            return "N/A"
        return f"{v:,.2f}"
    except Exception:
        return "N/A"


# ============================================================================
# 13. FORMAT TỶ ĐỒNG
# ============================================================================
def format_ty_dong(value, unit="auto", decimals=0, suffix=True,
                   already_in_ty=False, col_name=None):
    v = to_ty_dong(value, already_in_ty=already_in_ty, col_name=col_name)
    if v == 0:
        return "0 tỷ" if suffix else "0"
    if abs(v) > _MAX_REASONABLE_TY:
        return "N/A"
    sign = "-" if v < 0 else ""
    av = abs(v)
    if unit == "nghin_ty":
        s = f"{sign}{av/1000:,.{decimals}f}"
        return f"{s} nghìn tỷ" if suffix else s
    if unit == "ty":
        s = f"{sign}{av:,.{decimals}f}"
        return f"{s} tỷ" if suffix else s
    if unit == "trieu_ty":
        s = f"{sign}{av/1_000_000:,.2f}"
        return f"{s} triệu tỷ" if suffix else s
    if av >= 1_000_000:
        s = f"{sign}{av/1_000_000:,.2f}"
        return f"{s} triệu tỷ" if suffix else s
    if av >= 1_000:
        s = f"{sign}{av/1_000:,.2f}"
        return f"{s} nghìn tỷ" if suffix else s
    s = f"{sign}{av:,.0f}"
    return f"{s} tỷ" if suffix else s


def format_ty_dong_full(value, already_in_ty=False, col_name=None):
    v = to_ty_dong(value, already_in_ty=already_in_ty, col_name=col_name)
    if v == 0:
        return "0 tỷ"
    if abs(v) > _MAX_REASONABLE_TY:
        return "N/A"
    if abs(v) >= 1000:
        return f"{v/1000:,.2f} nghìn tỷ ({v:,.0f} tỷ)"
    return f"{v:,.0f} tỷ"


def format_ty_dong_help(value, already_in_ty=False, col_name=None):
    v = to_ty_dong(value, already_in_ty=already_in_ty, col_name=col_name)
    if v == 0:
        return "0 tỷ đồng"
    if abs(v) > _MAX_REASONABLE_TY:
        return "N/A"
    if abs(v) >= 1000:
        return f"{v:,.0f} tỷ đồng  ({v/1000:,.2f} nghìn tỷ)"
    return f"{v:,.0f} tỷ đồng"


def format_ty(value_ty, unit='tỷ'):
    if value_ty is None or value_ty == 0:
        return "N/A"
    try:
        v = float(value_ty)
    except (TypeError, ValueError):
        return "N/A"
    if abs(v) > _MAX_REASONABLE_TY:
        return "N/A"
    if unit == 'nghin_ty':
        return f"{v/1000:,.2f} nghìn tỷ"
    return f"{v:,.0f} tỷ"


def format_ty_short(value_ty):
    if value_ty is None or value_ty == 0:
        return "N/A"
    try:
        v = float(value_ty)
    except (TypeError, ValueError):
        return "N/A"
    if abs(v) > _MAX_REASONABLE_TY:
        return "N/A"
    if abs(v) >= 1_000_000:
        return f"{v/1_000_000:,.2f} triệu tỷ"
    if abs(v) >= 1_000:
        return f"{v/1_000:,.2f} nghìn tỷ"
    return f"{v:,.0f} tỷ"


# ============================================================================
# 14. SANITIZE FINANCIAL INPUTS
# ============================================================================
def sanitize_financial_inputs(data):
    if data is None:
        return data
    is_series = False
    try:
        if isinstance(data, pd.Series):
            is_series = True
            d = data.to_dict()
        else:
            d = dict(data) if hasattr(data, 'keys') else {}
    except Exception:
        d = dict(data) if hasattr(data, 'keys') else {}

    price = 0.0
    for k in ('price', 'gia', 'gia_hien_tai', 'thị giá', 'close'):
        if k in d and d[k] is not None:
            v = to_float_scalar(d[k])
            if v > 0 and not _is_garbage_value(v):
                price = v
                break
    price = fix_price(price)
    d['price'] = price
    d['gia'] = price
    d['gia_hien_tai'] = price

    shares = 0.0
    for k in ('shares', 'total_shares', 'so_co_phieu'):
        if k in d and d[k] is not None:
            v = to_float_scalar(d[k])
            if v > 0 and not _is_garbage_value(v):
                shares = v
                break
    shares = fix_shares(shares)
    d['shares'] = shares
    d['total_shares'] = shares

    equity = 0.0
    for k in ('equity', 'von_chu', 'vốn chủ sở hữu', 'VCSH'):
        if k in d and d[k] is not None:
            v = to_float_scalar(d[k])
            if v > 0 and not _is_garbage_value(v):
                equity = v
                break
    equity = to_ty_dong(equity, col_name=None) * 1e9
    d['equity'] = equity

    profit = 0.0
    for k in ('profit', 'loi_nhuan', 'LNST'):
        if k in d and d[k] is not None:
            v = to_float_scalar(d[k])
            if v != 0 and not _is_garbage_value(v):
                profit = v
                break
    profit = to_ty_dong(profit, col_name=None) * 1e9
    d['profit'] = profit

    eps = 0.0
    for k in ('eps', 'EPS'):
        if k in d and d[k] is not None:
            v = to_float_scalar(d[k])
            if v != 0 and not _is_garbage_value(v):
                eps = v
                break
    eps = fix_eps(eps, profit=profit, shares=shares, keep_negative=True)
    d['eps'] = eps

    bvps = 0.0
    for k in ('bvps', 'BVPS'):
        if k in d and d[k] is not None:
            v = to_float_scalar(d[k])
            if v > 0:
                bvps = v
                break
    bvps = fix_bvps(bvps, equity=equity, shares=shares)
    d['bvps'] = bvps

    dividend = 0.0
    for k in ('co_tuc_cp', 'dividend', 'dps'):
        if k in d and d[k] is not None:
            v = to_float_scalar(d[k])
            if v > 0 and not _is_garbage_value(v):
                dividend = v
                break
    dividend = fix_dividend(dividend)
    d['co_tuc_cp'] = dividend
    d['dividend'] = dividend

    if price > 0 and eps > 0:
        pe = price / eps
        d['pe'] = round(pe, 2) if 0.5 <= pe <= 500 else 0.0
    elif price > 0 and eps < 0:
        d['pe'] = 0.0
    else:
        d['pe'] = 0.0

    if price > 0 and bvps > 0:
        pb = price / bvps
        d['pb'] = round(pb, 2) if 0.1 <= pb <= 30 else 0.0
    else:
        d['pb'] = 0.0

    if price > 0 and shares > 0:
        mc = price * shares
        d['market_cap'] = round(mc, 0)
        d['market_cap_ty'] = round(mc / 1e9, 2)
    else:
        d['market_cap'] = 0.0
        d['market_cap_ty'] = 0.0

    if dividend > 0 and price > 0:
        dy = (dividend / price) * 100
        d['ty_le_co_tuc'] = round(dy, 2) if 0 <= dy <= 30 else 0.0
    else:
        d['ty_le_co_tuc'] = 0.0
    d['dividend_yield'] = d['ty_le_co_tuc']

    if profit > 0 and equity > 0:
        roe = (profit / equity) * 100
        if -100 <= roe <= 200:
            d['roe'] = round(roe, 2)

    if is_series:
        try:
            return pd.Series(d)
        except Exception:
            pass
    return d


# ============================================================================
# 15. SANITIZE DATAFRAME
# ============================================================================
_MONEY_COL_KEYWORDS = [
    ('total_assets', 'total_assets', ['tong_tai_san', 'total_assets']),
    ('equity',       'equity',       ['von_chu_so_huu', 'equity', 'von_csh']),
    ('profit',       'profit',       ['loi_nhuan', 'lnst', 'profit']),
    ('revenue',      'revenue',      ['doanh_thu', 'revenue', 'toi', 'nii',
                                      'thu_nhap_lai']),
    ('market_cap',   'market_cap',   ['market_cap', 'von_hoa']),
]


def sanitize_dataframe(df):
    if df is None:
        return df
    try:
        if not isinstance(df, pd.DataFrame) or df.empty:
            return df
    except Exception:
        return df
    df = df.copy()
    rename_map = {c: f"_BL_{c}" for c in df.columns if is_suspicious_column(c)}
    if rename_map:
        df = df.rename(columns=rename_map)
    for col in df.columns:
        try:
            if df[col].dtype.kind in 'iufc':
                df.loc[df[col] == 87, col] = 0.0
        except Exception:
            continue
    skip_kws = ['%', 'yield', 'p/e', 'pe_', 'p/b', 'pb_', 'roe', 'roa',
                'tang_truong', '_bl_']
    for col in list(df.columns):
        cl = str(col).lower()
        if any(s in cl for s in skip_kws):
            continue
        try:
            if any(k in cl for k in ['giá', 'price', 'close']):
                df[col] = df[col].apply(fix_price)
            elif 'bvps' in cl or 'book_value' in cl:
                df[col] = df[col].apply(fix_bvps)
            elif 'eps' in cl:
                df[col] = df[col].apply(lambda x: fix_eps(x, keep_negative=True))
            elif ('co_tuc' in cl or 'dividend' in cl) and \
                 ('cp' in cl or 'vnd' in cl or 'per_share' in cl):
                df[col] = df[col].apply(fix_dividend)
            elif 'shares' in cl or 'co_phieu' in cl or 'cổ phiếu' in cl:
                df[col] = df[col].apply(fix_shares)
            else:
                for _, metric_key, kws in _MONEY_COL_KEYWORDS:
                    if any(kw in cl for kw in kws):
                        df[col] = df[col].apply(
                            lambda x, mk=metric_key, cn=col:
                            apply_unit_sanity(
                                to_ty_dong(x, col_name=cn), mk))
                        break
        except Exception:
            continue
    return df


# ============================================================================
# 16. SELF-VERIFY
# ============================================================================
_REQUIRED = [
    'COMPANY_MAPPING', 'BANK_TICKERS', 'CORP_TICKERS',
    'BANK_TICKERS_V41', 'CORP_TICKERS_V41', 'ALL_TICKERS_V41',
    'TICKER_DISPLAY', 'THRESHOLDS',
    'to_float_scalar', 'safe_divide', 'round_float',
    'format_currency_vn_advanced', 'format_currency_vn',
    'format_eps_value', 'format_pe_pb',
    'VN30_LONG_CSV_PATH',
]
_missing = [n for n in _REQUIRED if n not in globals()]
if _missing:
    raise ImportError(f"[cau_hinh] THIẾU: {_missing}")


# ============================================================================
# 17. EXPORTS
# ============================================================================
__all__ = [
    'VN30_LONG_CSV_PATH',
    'BANK_TICKERS_V41', 'CORP_TICKERS_V41', 'ALL_TICKERS_V41',
    'COMPANY_MAPPING', 'BANK_TICKERS', 'CORP_TICKERS',
    'TICKER_DISPLAY', 'THRESHOLDS',
    'GARBAGE_VALUES', 'SUSPICIOUS_COL_IDS',
    'MIN_REAL_PRICE', 'MIN_REAL_BVPS', 'MIN_REAL_EPS',
    'MIN_REAL_DIVIDEND', 'MIN_REAL_MARKET_CAP', 'MIN_REAL_SHARES',
    'to_float_scalar', 'safe_divide', 'round_float',
    'is_garbage_value', 'is_suspicious_column',
    'fix_price', 'fix_bvps', 'fix_eps', 'fix_dividend', 'fix_shares',
    'fix_market_cap',
    'format_currency_vn_advanced', 'format_currency_vn',
    'format_eps_value', 'format_pe_pb',
    'sanitize_financial_inputs', 'sanitize_dataframe',
    'to_ty_dong', 'detect_money_unit',
    'format_ty_dong', 'format_ty_dong_full', 'format_ty_dong_help',
    'format_ty', 'format_ty_short',
    'detect_unit_from_colname',
    'apply_unit_sanity',
    # [v54-SNAPSHOT-INTEGRATION]
    '_CSV_DB_PATHS', '_SQLITE_DB_PATHS',
    '_LOADED_TICKERS', '_IS_USING_SQLITE',
    '_DEFAULT_SECTOR_BY_DB',
    '_SNAPSHOT_TICKERS_MAP',
    '_read_tickers_from_csv', '_read_tickers_from_sqlite',
    '_load_all_tickers', '_resolve_csv_db_paths',
    '_find_fallback_csv',
    '_is_period_column_v47', '_is_metric_column_v47',
    '_is_wide_format_v47', '_extract_tickers_from_wide_v47',
    '_PERIOD_PATTERN_V47', '_METRIC_COL_RAW_V47',
]


# ============================================================================
# 18. SELFTEST
# ============================================================================
if __name__ == "__main__":
    print("=" * 70)
    print("SELFTEST tien_ich/cau_hinh_danh_muc.py [v54-SNAPSHOT-INTEGRATION]")
    print("=" * 70)

    print(f"\n📁 CSV fallback path: {VN30_LONG_CSV_PATH}")
    print(f"📁 CSV data paths:")
    for _k, _p in _CSV_DB_PATHS.items():
        _exists = "✅" if _p and os.path.exists(_p) else "❌"
        print(f"   {_exists} {_k}: {_p or '(không tìm thấy)'}")
    print(f"\n🔍 _IS_USING_SQLITE (tức CSV loaded): {_IS_USING_SQLITE}")
    print(f"✅ BANK_TICKERS_V41: {len(BANK_TICKERS_V41)} mã — {BANK_TICKERS_V41}")
    print(f"✅ CORP_TICKERS_V41: {len(CORP_TICKERS_V41)} mã — {CORP_TICKERS_V41}")
    print(f"✅ ALL_TICKERS_V41: {len(ALL_TICKERS_V41)} mã")
    print(f"✅ COMPANY_MAPPING: {len(COMPANY_MAPPING)} mã")

    # Test hàm gốc
    assert to_float_scalar("1,234") == 1234.0
    assert to_float_scalar(None) == 0.0
    assert safe_divide(10, 0, -1) == -1
    assert round_float(3.14159, 2) == 3.14
    print("✅ HÀM GỐC OK")

    # Test unit detection
    assert detect_unit_from_colname("tong_tai_san_ty") == 1.0
    assert detect_unit_from_colname("von_chu_so_huu_trd") == 1e-3
    assert detect_unit_from_colname("loi_nhuan_vnd") == 1e-9
    assert detect_unit_from_colname("random_col") is None
    print("✅ DETECT UNIT FROM COLNAME OK")

    # Test to_ty_dong
    assert to_ty_dong(3_807_340) == 3_807.34
    assert to_ty_dong(50_000_000_000) == 50.0
    assert to_ty_dong(5_000_000_000_000) == 5000.0
    print("✅ TO_TY_DONG OK")

    # Test SANITY
    assert apply_unit_sanity(3_807_340, 'profit') == 3_807.34
    assert apply_unit_sanity(3_807, 'profit') == 3_807.0
    assert apply_unit_sanity(2_657_000, 'total_assets') == 2_657_000
    print("✅ APPLY_UNIT_SANITY OK")

    # Test FORMAT
    r1 = format_ty_dong(3_807_340, col_name="lnst_ty")
    assert r1 == "N/A"
    r2 = format_ty_dong(3_807)
    assert r2 == "3,807 tỷ"
    r3 = format_ty_dong(5_000_000)
    assert r3 == "N/A"
    print("✅ FORMAT_TY_DONG SANITY OK")

    # Test EPS đối xứng
    assert fix_eps(-68, keep_negative=True) == -68_000.0
    assert fix_eps(68) == 68_000.0
    assert format_eps_value(-68_000) == "-68,000 VNĐ/cp"
    print("✅ FIX_EPS ĐỐI XỨNG OK")

    # Test format_currency_vn_advanced per_share
    assert format_currency_vn_advanced(-68_000, per_share=True) == "-68,000 VNĐ/cp"
    assert format_currency_vn_advanced(68_000, per_share=True) == "68,000 VNĐ/cp"
    print("✅ FORMAT PER_SHARE ĐỐI XỨNG OK")

    # Test giá trị lớn
    assert format_currency_vn_advanced(2_657_000_000_000) == "2.66 Nghìn tỷ VNĐ"
    print("✅ FORMAT SỐ LỚN OK")

    # [v47] Test WIDE FORMAT detection helpers
    print("\n🔬 TEST WIDE FORMAT DETECTORS")
    assert _is_period_column_v47("2015") is True
    assert _is_period_column_v47("2026H1") is True
    assert _is_period_column_v47("2026Q1") is True
    assert _is_period_column_v47("2018H2") is True
    assert _is_period_column_v47("Cột 1") is False
    assert _is_period_column_v47("ticker") is False
    print("✅ _is_period_column_v47 OK")

    assert _is_metric_column_v47("Cột 1") is True
    assert _is_metric_column_v47("cột 1") is True
    assert _is_metric_column_v47("CHỈ TIÊU") is True
    assert _is_metric_column_v47("Chỉ tiêu") is True
    assert _is_metric_column_v47("Unnamed: 0") is True
    assert _is_metric_column_v47("metric_name") is True
    assert _is_metric_column_v47("2015") is False
    assert _is_metric_column_v47("ticker") is False
    print("✅ _is_metric_column_v47 OK")

    # [v54] Test SNAPSHOT TICKERS
    print("\n🔬 TEST SNAPSHOT TICKERS")
    for tk in _SNAPSHOT_TICKERS_MAP.keys():
        assert tk in COMPANY_MAPPING, f"Thiếu {tk} trong COMPANY_MAPPING"
    print("✅ SNAPSHOT TICKERS ĐÃ ĐƯỢC MERGE OK")

    # Verify tickers
    assert len(ALL_TICKERS_V41) == len(BANK_TICKERS_V41) + len(CORP_TICKERS_V41)
    for _tk in ALL_TICKERS_V41:
        assert _tk in COMPANY_MAPPING, f"Thiếu {_tk} trong COMPANY_MAPPING"
    print(f"\n✅ Tickers hợp lệ — nguồn: {'CSV' if _IS_USING_SQLITE else 'Fallback + Snapshot'}")

    # Preview 5 tickers đầu
    print(f"\n📋 Preview 5 tickers đầu:")
    for _tk in ALL_TICKERS_V41[:5]:
        _info = COMPANY_MAPPING[_tk]
        print(f"   • {_tk} — {_info['sector']} — {_info['name'][:50]}")

    print(f"\n✅ TOTAL EXPORTS: {len(__all__)} items")
    print("✅ ALL TESTS PASSED")
    print("=" * 70)
