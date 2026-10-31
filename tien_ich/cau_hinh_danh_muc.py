# tien_ich/cau_hinh_danh_muc_v56.py
# ============================================================================
# [v56] — KẾ THỪA 100% v54 + ĐỌC DYNAMIC TỪ MASTER CSV
# ----------------------------------------------------------------------------
# NGUỒN TICKER:
#   1. data/vietnam_stock_database_tong_hop.csv  (chính — 100+ mã)
#   2. 41 mã v54 (BANK_TICKERS_FALLBACK + CORP_TICKERS_FALLBACK + SNAPSHOT)
#   3. vietnam_stock_database.xlsx (nếu có sheet ticker — optional)
#
# KHÔNG ĐỔI: mọi helper, format, fix_*, sanitize, threshold của v54.
# ============================================================================

import os
import re
import numpy as np
import pandas as pd

# ---- Import toàn bộ public API của v54 (bao gồm _CSV_DB_PATHS, _SNAPSHOT_TICKERS_MAP, ...)
from tien_ich.cau_hinh_danh_muc import *          # noqa: F401,F403
from tien_ich.cau_hinh_danh_muc import (
    # Private cần dùng
    _BANK_NAME_MAP, _CORP_NAME_MAP, _CORP_SECTOR_MAP,
    _BANK_TICKERS_FALLBACK, _CORP_TICKERS_FALLBACK,
    _CSV_DB_PATHS, _LOADED_TICKERS, _IS_USING_SQLITE,
    _SNAPSHOT_TICKERS_MAP, _DEFAULT_SECTOR_BY_DB,
    _read_tickers_from_csv, _load_all_tickers, _resolve_csv_db_paths,
    _find_fallback_csv,
    # Giữ bản gốc để tham chiếu
    BANK_TICKERS_V41 as _BANK_V54,
    CORP_TICKERS_V41 as _CORP_V54,
    ALL_TICKERS_V41  as _ALL_V54,
    COMPANY_MAPPING  as _CMAP_V54,
    TICKER_DISPLAY   as _TD_V54,
    __all__          as _V54_ALL,
)


# ============================================================================
# [v56.1] ĐƯỜNG DẪN MASTER CSV
# ============================================================================
_MASTER_CSV_FILENAME_V56 = 'vietnam_stock_database_tong_hop.csv'
_MASTER_CSV_RELATIVE_V56 = 'data/vietnam_stock_database_tong_hop.csv'


def _resolve_master_csv_path_v56():
    here   = os.path.dirname(os.path.abspath(__file__))
    parent = os.path.dirname(here)
    grand  = os.path.dirname(parent)
    cand = [
        _MASTER_CSV_RELATIVE_V56,
        os.path.join(os.getcwd(), 'data', _MASTER_CSV_FILENAME_V56),
        os.path.join(os.getcwd(), _MASTER_CSV_FILENAME_V56),
        os.path.join(parent, 'data', _MASTER_CSV_FILENAME_V56),
        os.path.join(grand,  'data', _MASTER_CSV_FILENAME_V56),
        os.path.join(here,   'data', _MASTER_CSV_FILENAME_V56),
        os.path.join('/app', 'data', _MASTER_CSV_FILENAME_V56),
        os.path.join('/content', 'data', _MASTER_CSV_FILENAME_V56),
        os.path.join('/workspace', 'data', _MASTER_CSV_FILENAME_V56),
    ]
    for p in cand:
        try:
            if os.path.isfile(p) and os.path.getsize(p) > 0:
                return os.path.abspath(p)
        except OSError:
            continue
    return None


MASTER_CSV_PATH_V56 = _resolve_master_csv_path_v56()

print("\n" + "=" * 78)
print("[v56-TICKERS] 🔍 ĐỌC DANH MỤC TICKER TỪ MASTER CSV")
print("=" * 78)
if MASTER_CSV_PATH_V56:
    print(f"   ✅ {MASTER_CSV_PATH_V56}  "
          f"({os.path.getsize(MASTER_CSV_PATH_V56)/1024:,.1f} KB)")
else:
    print(f"   ❌ {_MASTER_CSV_RELATIVE_V56}  (KHÔNG TÌM THẤY → fallback v54)")
print("=" * 78 + "\n")


# ============================================================================
# [v56.2] ĐỌC TICKERS TỪ MASTER CSV
# ============================================================================
def _load_tickers_from_master_csv_v56():
    if not MASTER_CSV_PATH_V56:
        return set()
    try:
        try:
            df = pd.read_csv(MASTER_CSV_PATH_V56, encoding='utf-8-sig',
                             low_memory=False, nrows=10000)
        except UnicodeDecodeError:
            df = pd.read_csv(MASTER_CSV_PATH_V56, encoding='cp1258',
                             low_memory=False, nrows=10000)
    except Exception as e:
        print(f"[v56-TICKERS] ⚠️ Đọc CSV lỗi: {e}")
        return set()

    if df is None or df.empty:
        return set()

    def _n(c):
        s = str(c).strip().lower()
        s = re.sub(r'[\s\-\.\(\)]+', '_', s)
        return re.sub(r'_+', '_', s).strip('_')

    df = df.rename(columns={c: _n(c) for c in df.columns})

    ticker_col = None
    for c in ('ticker', 'ma', 'ma_ck', 'symbol', 'code', 'mã'):
        if c in df.columns:
            ticker_col = c
            break

    if not ticker_col:
        print(f"[v56-TICKERS] ⚠️ Không có cột ticker. Có: {list(df.columns)[:10]}")
        return set()

    s = df[ticker_col].astype(str).str.strip().str.upper()
    s = s.replace({'': None, 'NAN': None, 'NONE': None, 'MÃ': None, 'MA': None})
    tickers = set()
    for tk in s.dropna().unique():
        t = str(tk).strip().upper()
        if not t or t in ('NAN', 'NONE', 'MÃ', 'MA', ''):
            continue
        if not (2 <= len(t) <= 6):
            continue
        if not t.replace('.', '').replace('-', '').isalnum():
            continue
        tickers.add(t)

    print(f"[v56-TICKERS] ✅ Đọc {len(tickers)} ticker từ master CSV")
    return tickers


_MASTER_TICKERS_V56 = _load_tickers_from_master_csv_v56()


# ============================================================================
# [v56.3] NAME + SECTOR cho ~75 mã mới (chưa có trong v54)
# ----------------------------------------------------------------------------
# BANK group = Ngân hàng + Chứng khoán + Bảo hiểm (theo convention v54)
# CORP group = Tất cả ngành còn lại
# ============================================================================
_NEW_BANK_V56 = {
    # --- Banks mới ---
    'MSB': {'name': 'Ngân hàng TMCP Hàng Hải Việt Nam (MSB)', 'sector': 'Ngân hàng'},
    'NAB': {'name': 'Ngân hàng TMCP Nam Á (Nam A Bank)', 'sector': 'Ngân hàng'},
    'OCB': {'name': 'Ngân hàng TMCP Phương Đông (OCB)', 'sector': 'Ngân hàng'},
    # --- Securities ---
    'AGR': {'name': 'CTCP Chứng khoán Agribank', 'sector': 'Chứng khoán'},
    'BSI': {'name': 'CTCP Chứng khoán BIDV (BSC)', 'sector': 'Chứng khoán'},
    'CTS': {'name': 'CTCP Chứng khoán VietinBank', 'sector': 'Chứng khoán'},
    'DSC': {'name': 'CTCP Chứng khoán DSC', 'sector': 'Chứng khoán'},
    'FTS': {'name': 'CTCP Chứng khoán FPT', 'sector': 'Chứng khoán'},
    'HCM': {'name': 'CTCP Chứng khoán TP.HCM (HSC)', 'sector': 'Chứng khoán'},
    'ORS': {'name': 'CTCP Chứng khoán Tiên Phong', 'sector': 'Chứng khoán'},
    # --- Insurance ---
    'BIC': {'name': 'Tổng CTCP Bảo hiểm BIDV (BIC)', 'sector': 'Bảo hiểm'},
    'BMI': {'name': 'Tổng CTCP Bảo Minh', 'sector': 'Bảo hiểm'},
    'MIG': {'name': 'Tổng CTCP Bảo hiểm Quân Đội (MIC)', 'sector': 'Bảo hiểm'},
    'PGI': {'name': 'Tổng CTCP Bảo hiểm PJICO', 'sector': 'Bảo hiểm'},
}

_NEW_CORP_V56 = {
    'AAA': {'name': 'CTCP Nhựa An Phát Xanh', 'sector': 'Nhựa & Vật liệu'},
    'ADS': {'name': 'CTCP Damsan', 'sector': 'Dệt may'},
    'ANV': {'name': 'CTCP Nam Việt (Navico)', 'sector': 'Thủy sản'},
    'BAF': {'name': 'CTCP BAF Việt Nam', 'sector': 'Nông nghiệp'},
    'BCM': {'name': 'Tổng CTCP Đầu tư và Phát triển Công nghiệp (Becamex IDC)', 'sector': 'BĐS KCN'},
    'BFC': {'name': 'CTCP Phân bón Bình Điền', 'sector': 'Phân bón'},
    'BHN': {'name': 'Tổng CTCP Bia - Rượu - Nước giải khát Hà Nội (Habeco)', 'sector': 'Đồ uống'},
    'BMP': {'name': 'CTCP Nhựa Bình Minh', 'sector': 'Nhựa & Vật liệu'},
    'BWE': {'name': 'CTCP Nước - Môi trường Bình Dương', 'sector': 'Tiện ích'},
    'CHP': {'name': 'CTCP Thủy điện Miền Trung', 'sector': 'Điện & Năng lượng'},
    'CII': {'name': 'CTCP Đầu tư Hạ tầng Kỹ thuật TP.HCM', 'sector': 'Hạ tầng'},
    'CSM': {'name': 'CTCP Công nghiệp Cao su Miền Nam (Casumina)', 'sector': 'Cao su & Lốp xe'},
    'CTD': {'name': 'CTCP Xây dựng Coteccons', 'sector': 'Xây dựng'},
    'DBD': {'name': 'CTCP Dược - Trang thiết bị Y tế Bình Định', 'sector': 'Dược phẩm'},
    'DCM': {'name': 'CTCP Phân bón Dầu khí Cà Mau', 'sector': 'Phân bón'},
    'DGC': {'name': 'CTCP Tập đoàn Hóa chất Đức Giang', 'sector': 'Hóa chất'},
    'DHG': {'name': 'CTCP Dược Hậu Giang', 'sector': 'Dược phẩm'},
    'DIG': {'name': 'Tổng CTCP Đầu tư Phát triển Xây dựng (DIC Corp)', 'sector': 'Bất động sản'},
    'DLG': {'name': 'CTCP Tập đoàn Đức Long Gia Lai', 'sector': 'Đa ngành'},
    'DMC': {'name': 'CTCP Xuất nhập khẩu Y tế Domesco', 'sector': 'Dược phẩm'},
    'DPM': {'name': 'Tổng CTCP Phân bón và Hóa chất Dầu khí (PVFCCo)', 'sector': 'Phân bón'},
    'DRC': {'name': 'CTCP Cao su Đà Nẵng', 'sector': 'Cao su & Lốp xe'},
    'DVP': {'name': 'CTCP Đầu tư và Phát triển Cảng Đình Vũ', 'sector': 'Logistics & Cảng biển'},
    'DXG': {'name': 'CTCP Tập đoàn Đất Xanh', 'sector': 'Bất động sản'},
    'DXS': {'name': 'CTCP Dịch vụ Bất động sản Đất Xanh', 'sector': 'Bất động sản'},
    'FIT': {'name': 'CTCP Tập đoàn FIT', 'sector': 'Đa ngành'},
    'FMC': {'name': 'CTCP Thủy sản Bình An', 'sector': 'Thủy sản'},
    'GEG': {'name': 'CTCP Điện Gia Lai', 'sector': 'Điện & Năng lượng'},
    'HAH': {'name': 'CTCP Vận tải và Xếp dỡ Hải An', 'sector': 'Logistics & Cảng biển'},
    'HDC': {'name': 'CTCP Phát triển Nhà Bà Rịa - Vũng Tàu (Hodeco)', 'sector': 'Bất động sản'},
    'HDG': {'name': 'CTCP Tập đoàn Hà Đô', 'sector': 'Bất động sản'},
    'HHV': {'name': 'CTCP Đầu tư Hạ tầng Giao thông Đèo Cả', 'sector': 'Hạ tầng'},
    'HNA': {'name': 'CTCP Thủy điện Hủa Na', 'sector': 'Điện & Năng lượng'},
    'HT1': {'name': 'CTCP Xi măng Hà Tiên 1', 'sector': 'Vật liệu xây dựng'},
    'HVN': {'name': 'Tổng Công ty Hàng không Việt Nam (Vietnam Airlines)', 'sector': 'Hàng không'},
    'IDI': {'name': 'CTCP Đầu tư và Phát triển Đa Quốc gia', 'sector': 'Thủy sản'},
    'IJC': {'name': 'CTCP Phát triển Hạ tầng Kỹ thuật (Becamex IJC)', 'sector': 'Bất động sản'},
    'IMP': {'name': 'CTCP Dược phẩm Imexpharm', 'sector': 'Dược phẩm'},
    'KBC': {'name': 'Tổng Công ty Phát triển Đô thị Kinh Bắc', 'sector': 'BĐS KCN'},
    'KDC': {'name': 'CTCP Tập đoàn Kido', 'sector': 'Thực phẩm & Đồ uống'},
    'KDH': {'name': 'CTCP Đầu tư và Kinh doanh Nhà Khang Điền', 'sector': 'Bất động sản'},
    'KOS': {'name': 'CTCP Kosy', 'sector': 'Bất động sản'},
    'LGC': {'name': 'CTCP Cơ khí - Điện Lữ Gia', 'sector': 'Xây dựng'},
    'MCM': {'name': 'CTCP Giống Bò sữa Mộc Châu (Moc Chau Milk)', 'sector': 'Sữa & Thực phẩm'},
    'MSH': {'name': 'CTCP May Sông Hồng', 'sector': 'Dệt may'},
    'NKG': {'name': 'CTCP Thép Nam Kim', 'sector': 'Thép & Vật liệu'},
    'NLG': {'name': 'CTCP Đầu tư Nam Long', 'sector': 'Bất động sản'},
    'NSC': {'name': 'CTCP Tập đoàn Giống cây trồng Việt Nam', 'sector': 'Nông nghiệp'},
    'NT2': {'name': 'CTCP Điện lực Dầu khí Nhơn Trạch 2', 'sector': 'Điện & Năng lượng'},
    'NTC': {'name': 'CTCP Khu Công nghiệp Nam Tân Uyên', 'sector': 'BĐS KCN'},
    'NTL': {'name': 'CTCP Phát triển Đô thị Từ Liêm', 'sector': 'Bất động sản'},
    'NVL': {'name': 'CTCP Tập đoàn Đầu tư Địa ốc No Va (Novaland)', 'sector': 'Bất động sản'},
    'OGC': {'name': 'CTCP Tập đoàn Đại Dương (Ocean Group)', 'sector': 'Bất động sản'},
    'PAN': {'name': 'CTCP Tập đoàn PAN', 'sector': 'Đa ngành'},
    'PC1': {'name': 'CTCP Xây lắp điện 1', 'sector': 'Xây dựng'},
    'PDN': {'name': 'CTCP Cảng Đồng Nai', 'sector': 'Logistics & Cảng biển'},
    'PDR': {'name': 'CTCP Phát triển Bất động sản Phát Đạt', 'sector': 'Bất động sản'},
    'PET': {'name': 'Tổng CTCP Dịch vụ Tổng hợp Dầu khí (PETROSETCO)', 'sector': 'Đa ngành'},
    'PGD': {'name': 'CTCP Phân bón và Hóa chất Dầu khí Miền Nam', 'sector': 'Phân bón'},
    'PGV': {'name': 'Tổng Công ty Phát điện 3 (EVN Genco 3)', 'sector': 'Điện & Năng lượng'},
    'PHR': {'name': 'CTCP Cao su Phước Hòa', 'sector': 'Cao su & Công nghiệp'},
    'PLX': {'name': 'Tập đoàn Xăng dầu Việt Nam (Petrolimex)', 'sector': 'Xăng dầu'},
    'PNJ': {'name': 'CTCP Vàng bạc Đá quý Phú Nhuận (PNJ)', 'sector': 'Bán lẻ'},
    'PPC': {'name': 'CTCP Nhiệt điện Phả Lại', 'sector': 'Điện & Năng lượng'},
}


# ============================================================================
# [v56.4] MERGE: 41 mã v54 + 100+ mã master CSV
# ============================================================================
def _merge_and_build_tickers_v56():
    """Trả (bank_list, corp_list, company_mapping_dict)."""
    bank_set = set(_BANK_V54)
    corp_set = set(_CORP_V54)
    cmap     = dict(_CMAP_V54)   # copy v54

    def _add(tk, info, is_bank):
        tk = str(tk).strip().upper()
        if not tk or tk in ('NAN', 'NONE', ''):
            return
        if tk not in cmap:
            cmap[tk] = {
                'name':   info['name'],
                'file':   f"{tk.lower()}_financial_statement.csv",
                'sector': info.get('sector', 'Doanh nghiệp niêm yết'),
            }
        if is_bank:
            bank_set.add(tk)
            corp_set.discard(tk)
        else:
            corp_set.add(tk)
            bank_set.discard(tk)

    # 1. Master CSV tickers
    for tk in _MASTER_TICKERS_V56:
        tk = tk.upper()
        if tk in cmap:                  # đã có v54 → giữ info v54
            is_bank = tk in bank_set
            if not is_bank and tk in _NEW_BANK_V56:
                is_bank = True
                bank_set.add(tk); corp_set.discard(tk)
            continue

        if tk in _NEW_BANK_V56:
            _add(tk, _NEW_BANK_V56[tk], True)
        elif tk in _NEW_CORP_V56:
            _add(tk, _NEW_CORP_V56[tk], False)
        else:
            # Ticker lạ → auto classify
            _add(tk, {'name': f'CTCP {tk}', 'sector': 'Doanh nghiệp niêm yết'}, False)

    # 2. NEW_BANK_V56 còn sót (nếu không có trong CSV nhưng vẫn cần)
    for tk, info in _NEW_BANK_V56.items():
        if tk not in cmap:
            _add(tk, info, True)

    # 3. NEW_CORP_V56 còn sót
    for tk, info in _NEW_CORP_V56.items():
        if tk not in cmap:
            _add(tk, info, False)

    bank_list = sorted(bank_set)
    corp_list = sorted(corp_set)
    return bank_list, corp_list, cmap


_BANK_V56, _CORP_V56, _CMAP_V56 = _merge_and_build_tickers_v56()


# ============================================================================
# [v56.5] GHI ĐÈ EXPORT v54 (nhưng giữ name gốc cho v54 compatibility)
# ============================================================================
BANK_TICKERS_V41 = _BANK_V56
CORP_TICKERS_V41 = _CORP_V56
ALL_TICKERS_V41  = BANK_TICKERS_V41 + CORP_TICKERS_V41
COMPANY_MAPPING  = _CMAP_V56
BANK_TICKERS     = set(BANK_TICKERS_V41)
CORP_TICKERS     = set(CORP_TICKERS_V41)
TICKER_DISPLAY   = [
    f"{tk} - {info['name']}"
    for tk, info in COMPANY_MAPPING.items()
]

print(f"[v56-TICKERS] ✅ HOÀN TẤT")
print(f"[v56-TICKERS]   BANK = {len(BANK_TICKERS_V41)} mã "
      f"(v54: {len(_BANK_V54)} → +{len(BANK_TICKERS_V41) - len(_BANK_V54)})")
print(f"[v56-TICKERS]   CORP = {len(CORP_TICKERS_V41)} mã "
      f"(v54: {len(_CORP_V54)} → +{len(CORP_TICKERS_V41) - len(_CORP_V54)})")
print(f"[v56-TICKERS]   TOTAL = {len(ALL_TICKERS_V41)} mã "
      f"(v54: {len(_ALL_V54)})")


# ============================================================================
# [v56.6] API TRUY VẤN
# ============================================================================
def get_ticker_info_v56(ticker):
    tk = str(ticker).strip().upper()
    return COMPANY_MAPPING.get(tk, {})


def get_all_tickers_v56():
    return list(ALL_TICKERS_V41)


def reload_tickers_v56():
    """Hot reload khi file CSV đổi."""
    global MASTER_CSV_PATH_V56, _MASTER_TICKERS_V56
    global BANK_TICKERS_V41, CORP_TICKERS_V41, ALL_TICKERS_V41
    global COMPANY_MAPPING, BANK_TICKERS, CORP_TICKERS, TICKER_DISPLAY
    global _BANK_V56, _CORP_V56, _CMAP_V56

    MASTER_CSV_PATH_V56 = _resolve_master_csv_path_v56()
    _MASTER_TICKERS_V56 = _load_tickers_from_master_csv_v56()
    _BANK_V56, _CORP_V56, _CMAP_V56 = _merge_and_build_tickers_v56()

    BANK_TICKERS_V41 = _BANK_V56
    CORP_TICKERS_V41 = _CORP_V56
    ALL_TICKERS_V41  = BANK_TICKERS_V41 + CORP_TICKERS_V41
    COMPANY_MAPPING  = _CMAP_V56
    BANK_TICKERS     = set(BANK_TICKERS_V41)
    CORP_TICKERS     = set(CORP_TICKERS_V41)
    TICKER_DISPLAY   = [
        f"{tk} - {info['name']}" for tk, info in COMPANY_MAPPING.items()
    ]
    print(f"[v56-RELOAD] ✅ MASTER={len(_MASTER_TICKERS_V56)} · "
          f"TOTAL={len(ALL_TICKERS_V41)} mã")
    return len(ALL_TICKERS_V41)


def print_ticker_audit_v56():
    """Bảng audit danh mục."""
    print("\n" + "=" * 90)
    print("[v56-AUDIT] DANH MỤC TICKER")
    print("=" * 90)
    print(f"  MASTER CSV: {MASTER_CSV_PATH_V56 or '❌ KHÔNG TÌM THẤY'}")
    print(f"  Tickers trong CSV:   {len(_MASTER_TICKERS_V56)}")
    print(f"  Tổng BANK_TICKERS:   {len(BANK_TICKERS_V41)}")
    print(f"  Tổng CORP_TICKERS:   {len(CORP_TICKERS_V41)}")
    print(f"  Tổng ALL_TICKERS:    {len(ALL_TICKERS_V41)}")
    print(f"  COMPANY_MAPPING:     {len(COMPANY_MAPPING)}")
    print(f"  Có trong CSV nhưng không có trong dict: "
          f"{len(_MASTER_TICKERS_V56 - set(ALL_TICKERS_V41))}")
    print("-" * 90)
    df = pd.DataFrame([
        {'ticker': tk, 'group': 'BANK' if tk in BANK_TICKERS_V41 else 'CORP',
         'sector': info.get('sector', ''), 'name': info.get('name', '')[:55]}
        for tk, info in sorted(COMPANY_MAPPING.items())
    ])
    print(df.to_string(index=False))
    print("=" * 90 + "\n")
    return df


# ============================================================================
# [v56.7] MỞ RỘNG __all__
# ============================================================================
__all__ = list(_V54_ALL) + [
    # Master CSV
    '_MASTER_CSV_FILENAME_V56', '_MASTER_CSV_RELATIVE_V56',
    'MASTER_CSV_PATH_V56', '_MASTER_TICKERS_V56',
    '_resolve_master_csv_path_v56',
    '_load_tickers_from_master_csv_v56',
    # New ticker maps
    '_NEW_BANK_V56', '_NEW_CORP_V56',
    '_BANK_V56', '_CORP_V56', '_CMAP_V56',
    '_merge_and_build_tickers_v56',
    # Public API
    'get_ticker_info_v56', 'get_all_tickers_v56',
    'reload_tickers_v56', 'print_ticker_audit_v56',
]


# ============================================================================
# [v56.8] SELFTEST
# ============================================================================
if __name__ == "__main__":
    print("\n" + "=" * 78)
    print("SELFTEST tien_ich/cau_hinh_danh_muc_v56.py")
    print("=" * 78)

    # 1. Master CSV có được đọc?
    assert MASTER_CSV_PATH_V56, "❌ Không tìm thấy master CSV"
    assert len(_MASTER_TICKERS_V56) > 50, f"❌ Chỉ đọc được {len(_MASTER_TICKERS_V56)} mã"
    print(f"✅ MASTER CSV: {len(_MASTER_TICKERS_V56)} tickers")

    # 2. v54 compatibility - mọi mã v54 phải còn
    for tk in _ALL_V54:
        assert tk in COMPANY_MAPPING, f"❌ Mất mã v54: {tk}"
    print(f"✅ Bảo toàn v54: {len(_ALL_V54)} mã")

    # 3. New tickers có trong COMPANY_MAPPING?
    sample_new = ['AAA', 'DGC', 'MSH', 'PNJ', 'PLX', 'NVL', 'HVN']
    for tk in sample_new:
        info = get_ticker_info_v56(tk)
        assert info, f"❌ Thiếu {tk}"
        assert info['name'] and info['sector'], f"❌ Thiếu name/sector cho {tk}"
    print(f"✅ Mã mới OK: {sample_new}")

    # 4. Phân loại bank/corp
    assert 'MSB' in BANK_TICKERS, "❌ MSB phải là BANK"
    assert 'BSI' in BANK_TICKERS, "❌ BSI (chứng khoán) phải là BANK group"
    assert 'BIC' in BANK_TICKERS, "❌ BIC (bảo hiểm) phải là BANK group"
    assert 'DGC' in CORP_TICKERS, "❌ DGC phải là CORP"
    assert 'PNJ' in CORP_TICKERS, "❌ PNJ phải là CORP"
    print("✅ Phân loại BANK/CORP chính xác")

    # 5. Helper còn hoạt động
    assert to_float_scalar("1,234") == 1234.0
    assert safe_divide(10, 0, -1) == -1
    assert format_pe_pb(15.5) == "15.50"
    print("✅ Helpers v54 còn OK")

    # 6. In audit
    print_ticker_audit_v56()

    print("=" * 78)
    print("✅ ALL TESTS PASSED")
    print("=" * 78)
