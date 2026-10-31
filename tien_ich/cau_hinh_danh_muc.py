# tien_ich/cau_hinh_danh_muc_v56.py
# ============================================================================
# [v56] MASTER CONFIG — Single Source of Truth cho toàn bộ paths + tickers
# ----------------------------------------------------------------------------
# Nguyên tắc:
#   1. Kế thừa 100% v54 (helpers, format, fix_*, sanitize, threshold)
#   2. Path Registry = SINGLE SOURCE OF TRUTH (mọi module khác import từ đây)
#   3. Đọc tickers từ MASTER CSV TRƯỚC → union với 41 mã v54 (backward-compat)
#   4. Cung cấp name/sector cho ~77 mã mới (AAA → PPC)
#   5. Hot-reload an toàn (reload_paths_v56 + reload_tickers_v56)
# ============================================================================

import os
import re
import numpy as np
import pandas as pd


# ============================================================================
# [v56.1] IMPORT 100% v54 — KHÔNG SỬA
# ============================================================================
from tien_ich.cau_hinh_danh_muc import *   # noqa: F401,F403

from tien_ich.cau_hinh_danh_muc import (
    # Private maps v54 (dùng làm fallback)
    _BANK_NAME_MAP, _CORP_NAME_MAP, _CORP_SECTOR_MAP,
    _BANK_TICKERS_FALLBACK, _CORP_TICKERS_FALLBACK,
    _SNAPSHOT_TICKERS_MAP, _DEFAULT_SECTOR_BY_DB,
    # Đối tượng v54 tham chiếu
    _CSV_DB_PATHS           as _CSV_DB_PATHS_V54,
    _LOADED_TICKERS         as _LOADED_TICKERS_V54,
    _IS_USING_SQLITE        as _IS_USING_SQLITE_V54,
    BANK_TICKERS_V41        as _BANK_TICKERS_V54,
    CORP_TICKERS_V41        as _CORP_TICKERS_V54,
    ALL_TICKERS_V41         as _ALL_TICKERS_V54,
    COMPANY_MAPPING         as _COMPANY_MAPPING_V54,
    TICKER_DISPLAY          as _TICKER_DISPLAY_V54,
    __all__                 as _V54_ALL,
)


# ============================================================================
# [v56.2] PATH REGISTRY — SINGLE SOURCE OF TRUTH
# ============================================================================
_PATHS_REGISTRY_V56 = {
    # ⭐ NGUỒN CHÍNH — 100+ mã, đầy đủ BCTC
    'master_csv':    'data/vietnam_stock_database_tong_hop.csv',

    # Bảng giá
    'price_xlsx':    'vietnam_stock_database.xlsx',
    'price_csv_alt': 'bang_gia_100_ma.csv',

    # 9 CSV gốc mới (v55)
    'lctt_san_xuat':   'LCTT_SanXuat.csv',
    'lctt_ngan_hang':  'LCTT_NganHang.csv',
    'lctt_cong_nghe':  'LCTT_CongNghe.csv',
    'kqkd_san_xuat':   'KQKD_SanXuat.csv',
    'kqkd_ngan_hang':  'KQKD_NganHang.csv',
    'kqkd_cong_nghe':  'KQKD_CongNghe.csv',
    'bcdkt_san_xuat':  'BCDKT_SanXuat.csv',
    'bcdkt_ngan_hang': 'BCDKT_NganHang.csv',
    'bcdkt_cong_nghe': 'BCDKT_CongNghe.csv',

    # 3 CSV cũ (v54)
    'san_xuat_va_khac':       'du_lieu_san_xuat_va_khac.csv',
    'ngan_hang_va_tai_chinh': 'du_lieu_ngan_hang_va_tai_chinh.csv',
    'cong_nghe':              'du_lieu_cong_nghe.csv',

    # Legacy
    'vn30_legacy': 'du_lieu/vn30_41_fin_long.csv',
}


def _iter_search_bases_v56():
    """15 vị trí tìm file — rộng hơn v54 để tương thích GitHub Actions, Colab, Docker."""
    here   = os.path.dirname(os.path.abspath(__file__))
    parent = os.path.dirname(here)
    grand  = os.path.dirname(parent)
    return [
        os.getcwd(),
        os.path.join(os.getcwd(), 'data'),
        os.path.join(os.getcwd(), 'du_lieu'),
        parent,
        os.path.join(parent, 'data'),
        os.path.join(parent, 'du_lieu'),
        grand,
        os.path.join(grand,  'data'),
        os.path.join(grand,  'du_lieu'),
        here,
        os.path.join(here,   'data'),
        os.path.join(here,   'du_lieu'),
        '/app', '/app/data', '/app/du_lieu',
        '/content', '/content/data', '/content/du_lieu',
        '/workspace', '/workspace/data', '/workspace/du_lieu',
    ]


def _resolve_one_path_v56(rel_path):
    """Tìm 1 file: thử path trực tiếp → rồi quét 15 base dirs theo basename."""
    # Ưu tiên: đường dẫn tương đối giữ nguyên (nếu path có prefix 'data/')
    for p in (rel_path, os.path.join(os.getcwd(), rel_path)):
        try:
            if os.path.isfile(p) and os.path.getsize(p) > 0:
                return os.path.abspath(p)
        except OSError:
            continue
    # Fallback: tìm theo basename trong 15 base
    fname = os.path.basename(rel_path)
    for base in _iter_search_bases_v56():
        p = os.path.join(base, fname)
        try:
            if os.path.isfile(p) and os.path.getsize(p) > 0:
                return os.path.abspath(p)
        except OSError:
            continue
    return None


def _resolve_all_paths_v56():
    return {k: _resolve_one_path_v56(v) for k, v in _PATHS_REGISTRY_V56.items()}


# --- RESOLVE 1 LẦN KHI IMPORT ---
RESOLVED_PATHS_V56     = _resolve_all_paths_v56()
MASTER_CSV_PATH_V56    = RESOLVED_PATHS_V56['master_csv']
PRICE_XLSX_PATH_V56    = RESOLVED_PATHS_V56['price_xlsx']
PRICE_CSV_ALT_PATH_V56 = RESOLVED_PATHS_V56['price_csv_alt']
PRICE_PATHS_V56        = {'xlsx': PRICE_XLSX_PATH_V56, 'csv': PRICE_CSV_ALT_PATH_V56}

_CSV_DB_PATHS_V55_V56 = {
    k: RESOLVED_PATHS_V56[k] for k in (
        'lctt_san_xuat', 'lctt_ngan_hang', 'lctt_cong_nghe',
        'kqkd_san_xuat', 'kqkd_ngan_hang', 'kqkd_cong_nghe',
        'bcdkt_san_xuat', 'bcdkt_ngan_hang', 'bcdkt_cong_nghe',
    )
}
_CSV_DB_PATHS_V54_V56 = {
    k: RESOLVED_PATHS_V56[k] for k in (
        'san_xuat_va_khac', 'ngan_hang_va_tai_chinh', 'cong_nghe',
    )
}

# --- IN TRẠNG THÁI ---
print("\n" + "=" * 82)
print("[v56-PATHS] 📂 PATH REGISTRY (single source of truth)")
print("=" * 82)
for _k in _PATHS_REGISTRY_V56:
    _p = RESOLVED_PATHS_V56[_k]
    _flag = '✅' if _p else '⚪'
    _label = os.path.basename(_p) if _p else _PATHS_REGISTRY_V56[_k]
    _size = f"{os.path.getsize(_p)/1024:>8.1f} KB" if _p else "       ---"
    print(f"   {_flag} {_k:<24} {_label:<42} {_size}")
_n_ok = sum(1 for v in RESOLVED_PATHS_V56.values() if v)
print(f"\n   📊 {_n_ok}/{len(RESOLVED_PATHS_V56)} paths tìm thấy")
print("=" * 82 + "\n")


# ============================================================================
# [v56.3] ĐỌC TICKERS TỪ MASTER CSV (nguồn chính)
# ============================================================================
def _load_tickers_from_master_csv_v56(path=None):
    """
    Đọc unique tickers từ master CSV. Hỗ trợ:
      • Long format:      ticker | metric_name | period | value
      • Wide format:      ticker | 2024_EPS | 2024_LNST | 2025_EPS | 2025_LNST | ...
    Tự động ffill nếu có merged cells.
    """
    path = path or MASTER_CSV_PATH_V56
    if not path or not os.path.exists(path):
        return set()
    try:
        try:
            df = pd.read_csv(path, encoding='utf-8-sig', low_memory=False)
        except UnicodeDecodeError:
            df = pd.read_csv(path, encoding='cp1258', low_memory=False)
    except Exception as e:
        print(f"[v56-TICKERS] ⚠️ Đọc {path} lỗi: {e}")
        return set()

    if df is None or df.empty:
        return set()

    def _norm(c):
        s = str(c).strip().lower()
        s = re.sub(r'[\s\-\.\(\)]+', '_', s)
        return re.sub(r'_+', '_', s).strip('_')

    df = df.rename(columns={c: _norm(c) for c in df.columns})

    ticker_col = None
    for c in ('ticker', 'ma', 'ma_ck', 'symbol', 'code', 'mã', 'mã_cp'):
        if c in df.columns:
            ticker_col = c
            break

    if not ticker_col:
        print(f"[v56-TICKERS] ⚠️ Không có cột ticker. Có: {list(df.columns)[:8]}")
        return set()

    s = df[ticker_col].astype(str).str.strip().str.upper()
    s = s.replace({'': None, 'NAN': None, 'NONE': None, 'MÃ': None, 'MA': None})
    s = s.ffill()  # Merged cells → fill down
    s = s.dropna()

    valid = set()
    for tk in s.unique():
        t = str(tk).strip().upper()
        if not t or t in ('NAN', 'NONE', 'MÃ', 'MA', ''):
            continue
        if not (2 <= len(t) <= 6):
            continue
        if not t.replace('.', '').replace('-', '').isalnum():
            continue
        valid.add(t)

    print(f"[v56-TICKERS] ✅ Đọc {len(valid)} ticker từ {os.path.basename(path)}")
    return valid


_MASTER_TICKERS_V56 = _load_tickers_from_master_csv_v56()


# ============================================================================
# [v56.4] NAME + SECTOR CHO 77 MÃ MỚI (chưa có trong v54)
# ----------------------------------------------------------------------------
# BANK group v56 = Ngân hàng + Chứng khoán + Bảo hiểm (theo convention v54)
# ============================================================================
_NEW_BANK_V56 = {
    # --- Ngân hàng (3) ---
    'MSB': {'name': 'Ngân hàng TMCP Hàng Hải Việt Nam (MSB)', 'sector': 'Ngân hàng'},
    'NAB': {'name': 'Ngân hàng TMCP Nam Á (Nam A Bank)',      'sector': 'Ngân hàng'},
    'OCB': {'name': 'Ngân hàng TMCP Phương Đông (OCB)',       'sector': 'Ngân hàng'},
    # --- Chứng khoán (7) ---
    'AGR': {'name': 'CTCP Chứng khoán Agribank',              'sector': 'Chứng khoán'},
    'BSI': {'name': 'CTCP Chứng khoán BIDV (BSC)',            'sector': 'Chứng khoán'},
    'CTS': {'name': 'CTCP Chứng khoán VietinBank',            'sector': 'Chứng khoán'},
    'DSC': {'name': 'CTCP Chứng khoán DSC',                   'sector': 'Chứng khoán'},
    'FTS': {'name': 'CTCP Chứng khoán FPT',                   'sector': 'Chứng khoán'},
    'HCM': {'name': 'CTCP Chứng khoán TP.HCM (HSC)',          'sector': 'Chứng khoán'},
    'ORS': {'name': 'CTCP Chứng khoán Tiên Phong',            'sector': 'Chứng khoán'},
    # --- Bảo hiểm (4) ---
    'BIC': {'name': 'Tổng CTCP Bảo hiểm BIDV (BIC)',          'sector': 'Bảo hiểm'},
    'BMI': {'name': 'Tổng CTCP Bảo Minh',                     'sector': 'Bảo hiểm'},
    'MIG': {'name': 'Tổng CTCP Bảo hiểm Quân Đội (MIC)',      'sector': 'Bảo hiểm'},
    'PGI': {'name': 'Tổng CTCP Bảo hiểm PJICO',               'sector': 'Bảo hiểm'},
}

_NEW_CORP_V56 = {
    'AAA': {'name': 'CTCP Nhựa An Phát Xanh',                                    'sector': 'Nhựa & Vật liệu'},
    'ADS': {'name': 'CTCP Damsan',                                               'sector': 'Dệt may'},
    'ANV': {'name': 'CTCP Nam Việt (Navico)',                                    'sector': 'Thủy sản'},
    'BAF': {'name': 'CTCP BAF Việt Nam',                                         'sector': 'Nông nghiệp'},
    'BCM': {'name': 'Tổng CTCP Đầu tư và Phát triển Công nghiệp (Becamex IDC)',  'sector': 'BĐS KCN'},
    'BFC': {'name': 'CTCP Phân bón Bình Điền',                                   'sector': 'Phân bón'},
    'BHN': {'name': 'Tổng CTCP Bia - Rượu - NGK Hà Nội (Habeco)',                'sector': 'Đồ uống'},
    'BMP': {'name': 'CTCP Nhựa Bình Minh',                                       'sector': 'Nhựa & Vật liệu'},
    'BWE': {'name': 'CTCP Nước - Môi trường Bình Dương',                         'sector': 'Tiện ích'},
    'CHP': {'name': 'CTCP Thủy điện Miền Trung',                                 'sector': 'Điện & Năng lượng'},
    'CII': {'name': 'CTCP Đầu tư Hạ tầng Kỹ thuật TP.HCM',                       'sector': 'Hạ tầng'},
    'CSM': {'name': 'CTCP Công nghiệp Cao su Miền Nam (Casumina)',               'sector': 'Cao su & Lốp xe'},
    'CTD': {'name': 'CTCP Xây dựng Coteccons',                                   'sector': 'Xây dựng'},
    'DBD': {'name': 'CTCP Dược - Trang thiết bị Y tế Bình Định',                 'sector': 'Dược phẩm'},
    'DCM': {'name': 'CTCP Phân bón Dầu khí Cà Mau',                              'sector': 'Phân bón'},
    'DGC': {'name': 'CTCP Tập đoàn Hóa chất Đức Giang',                          'sector': 'Hóa chất'},
    'DHG': {'name': 'CTCP Dược Hậu Giang',                                       'sector': 'Dược phẩm'},
    'DIG': {'name': 'Tổng CTCP Đầu tư Phát triển Xây dựng (DIC Corp)',           'sector': 'Bất động sản'},
    'DLG': {'name': 'CTCP Tập đoàn Đức Long Gia Lai',                            'sector': 'Đa ngành'},
    'DMC': {'name': 'CTCP Xuất nhập khẩu Y tế Domesco',                          'sector': 'Dược phẩm'},
    'DPM': {'name': 'Tổng CTCP Phân bón và Hóa chất Dầu khí (PVFCCo)',           'sector': 'Phân bón'},
    'DRC': {'name': 'CTCP Cao su Đà Nẵng',                                       'sector': 'Cao su & Lốp xe'},
    'DVP': {'name': 'CTCP Đầu tư và Phát triển Cảng Đình Vũ',                    'sector': 'Logistics & Cảng biển'},
    'DXG': {'name': 'CTCP Tập đoàn Đất Xanh',                                    'sector': 'Bất động sản'},
    'DXS': {'name': 'CTCP Dịch vụ Bất động sản Đất Xanh',                        'sector': 'Bất động sản'},
    'FIT': {'name': 'CTCP Tập đoàn FIT',                                         'sector': 'Đa ngành'},
    'FMC': {'name': 'CTCP Thủy sản Bình An',                                     'sector': 'Thủy sản'},
    'GEG': {'name': 'CTCP Điện Gia Lai',                                         'sector': 'Điện & Năng lượng'},
    'HAH': {'name': 'CTCP Vận tải và Xếp dỡ Hải An',                             'sector': 'Logistics & Cảng biển'},
    'HDC': {'name': 'CTCP Phát triển Nhà Bà Rịa - Vũng Tàu (Hodeco)',            'sector': 'Bất động sản'},
    'HDG': {'name': 'CTCP Tập đoàn Hà Đô',                                       'sector': 'Bất động sản'},
    'HHV': {'name': 'CTCP Đầu tư Hạ tầng Giao thông Đèo Cả',                     'sector': 'Hạ tầng'},
    'HNA': {'name': 'CTCP Thủy điện Hủa Na',                                     'sector': 'Điện & Năng lượng'},
    'HT1': {'name': 'CTCP Xi măng Hà Tiên 1',                                    'sector': 'Vật liệu xây dựng'},
    'HVN': {'name': 'Tổng Công ty Hàng không Việt Nam (Vietnam Airlines)',       'sector': 'Hàng không'},
    'IDI': {'name': 'CTCP Đầu tư và Phát triển Đa Quốc gia',                     'sector': 'Thủy sản'},
    'IJC': {'name': 'CTCP Phát triển Hạ tầng Kỹ thuật (Becamex IJC)',            'sector': 'Bất động sản'},
    'IMP': {'name': 'CTCP Dược phẩm Imexpharm',                                  'sector': 'Dược phẩm'},
    'KBC': {'name': 'Tổng Công ty Phát triển Đô thị Kinh Bắc',                   'sector': 'BĐS KCN'},
    'KDC': {'name': 'CTCP Tập đoàn Kido',                                        'sector': 'Thực phẩm & Đồ uống'},
    'KDH': {'name': 'CTCP Đầu tư và Kinh doanh Nhà Khang Điền',                  'sector': 'Bất động sản'},
    'KOS': {'name': 'CTCP Kosy',                                                 'sector': 'Bất động sản'},
    'LGC': {'name': 'CTCP Cơ khí - Điện Lữ Gia',                                 'sector': 'Xây dựng'},
    'MCM': {'name': 'CTCP Giống Bò sữa Mộc Châu (Moc Chau Milk)',                'sector': 'Sữa & Thực phẩm'},
    'MSH': {'name': 'CTCP May Sông Hồng',                                        'sector': 'Dệt may'},
    'NKG': {'name': 'CTCP Thép Nam Kim',                                         'sector': 'Thép & Vật liệu'},
    'NLG': {'name': 'CTCP Đầu tư Nam Long',                                      'sector': 'Bất động sản'},
    'NSC': {'name': 'CTCP Tập đoàn Giống cây trồng Việt Nam',                    'sector': 'Nông nghiệp'},
    'NT2': {'name': 'CTCP Điện lực Dầu khí Nhơn Trạch 2',                        'sector': 'Điện & Năng lượng'},
    'NTC': {'name': 'CTCP Khu Công nghiệp Nam Tân Uyên',                         'sector': 'BĐS KCN'},
    'NTL': {'name': 'CTCP Phát triển Đô thị Từ Liêm',                            'sector': 'Bất động sản'},
    'NVL': {'name': 'CTCP Tập đoàn Đầu tư Địa ốc No Va (Novaland)',              'sector': 'Bất động sản'},
    'OGC': {'name': 'CTCP Tập đoàn Đại Dương (Ocean Group)',                     'sector': 'Bất động sản'},
    'PAN': {'name': 'CTCP Tập đoàn PAN',                                         'sector': 'Đa ngành'},
    'PC1': {'name': 'CTCP Xây lắp điện 1',                                       'sector': 'Xây dựng'},
    'PDN': {'name': 'CTCP Cảng Đồng Nai',                                        'sector': 'Logistics & Cảng biển'},
    'PDR': {'name': 'CTCP Phát triển Bất động sản Phát Đạt',                     'sector': 'Bất động sản'},
    'PET': {'name': 'Tổng CTCP Dịch vụ Tổng hợp Dầu khí (PETROSETCO)',           'sector': 'Đa ngành'},
    'PGD': {'name': 'CTCP Phân bón và Hóa chất Dầu khí Miền Nam',                'sector': 'Phân bón'},
    'PGV': {'name': 'Tổng Công ty Phát điện 3 (EVN Genco 3)',                    'sector': 'Điện & Năng lượng'},
    'PHR': {'name': 'CTCP Cao su Phước Hòa',                                     'sector': 'Cao su & Công nghiệp'},
    'PLX': {'name': 'Tập đoàn Xăng dầu Việt Nam (Petrolimex)',                   'sector': 'Xăng dầu'},
    'PNJ': {'name': 'CTCP Vàng bạc Đá quý Phú Nhuận (PNJ)',                      'sector': 'Bán lẻ'},
    'PPC': {'name': 'CTCP Nhiệt điện Phả Lại',                                   'sector': 'Điện & Năng lượng'},
}


# ============================================================================
# [v56.5] MERGE — TICKERS CSV + 41 MÃ v54 (không mất mã nào)
# ============================================================================
def _merge_and_build_tickers_v56():
    bank_set = set(_BANK_TICKERS_V54)
    corp_set = set(_CORP_TICKERS_V54)
    cmap     = dict(_COMPANY_MAPPING_V54)

    def _ensure(tk, info, is_bank):
        tk = str(tk).strip().upper()
        if not tk:
            return
        if tk not in cmap:
            cmap[tk] = {
                'name':   info.get('name', f'CTCP {tk}'),
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
        tk_up = str(tk).strip().upper()
        if not tk_up:
            continue
        if tk_up in cmap:
            continue                              # đã có v54 → giữ nguyên
        if tk_up in _NEW_BANK_V56:
            _ensure(tk_up, _NEW_BANK_V56[tk_up], True)
        elif tk_up in _NEW_CORP_V56:
            _ensure(tk_up, _NEW_CORP_V56[tk_up], False)
        else:
            _ensure(tk_up, {'name': f'CTCP {tk_up}',
                            'sector': 'Doanh nghiệp niêm yết'}, False)

    # 2. NEW_BANK còn sót (nếu CSV không có)
    for tk, info in _NEW_BANK_V56.items():
        if tk not in cmap:
            _ensure(tk, info, True)

    # 3. NEW_CORP còn sót
    for tk, info in _NEW_CORP_V56.items():
        if tk not in cmap:
            _ensure(tk, info, False)

    return sorted(bank_set), sorted(corp_set), cmap


_BANK_V56, _CORP_V56, _CMAP_V56 = _merge_and_build_tickers_v56()


# ============================================================================
# [v56.6] GHI ĐÈ EXPORT v54
# ============================================================================
BANK_TICKERS_V41 = _BANK_V56
CORP_TICKERS_V41 = _CORP_V56
ALL_TICKERS_V41  = BANK_TICKERS_V41 + CORP_TICKERS_V41
COMPANY_MAPPING  = _CMAP_V56
BANK_TICKERS     = set(BANK_TICKERS_V41)
CORP_TICKERS     = set(CORP_TICKERS_V41)
TICKER_DISPLAY   = [f"{tk} - {info['name']}" for tk, info in COMPANY_MAPPING.items()]

print(f"[v56-TICKERS] ✅ BANK={len(BANK_TICKERS_V41)} "
      f"(v54: {len(_BANK_TICKERS_V54)}, +{len(BANK_TICKERS_V41) - len(_BANK_TICKERS_V54)})  |  "
      f"CORP={len(CORP_TICKERS_V41)} "
      f"(v54: {len(_CORP_TICKERS_V54)}, +{len(CORP_TICKERS_V41) - len(_CORP_TICKERS_V54)})  |  "
      f"TOTAL={len(ALL_TICKERS_V41)} (v54: {len(_ALL_TICKERS_V54)})")


# ============================================================================
# [v56.7] PUBLIC API
# ============================================================================
def get_ticker_info_v56(ticker):
    """Trả dict {name, sector, file} hoặc {} nếu không có."""
    tk = str(ticker).strip().upper()
    return COMPANY_MAPPING.get(tk, {})


def get_all_tickers_v56():
    return list(ALL_TICKERS_V41)


def reload_paths_v56():
    """Hot-reload paths từ registry (dùng khi file mới được thêm vào)."""
    global RESOLVED_PATHS_V56, MASTER_CSV_PATH_V56, PRICE_XLSX_PATH_V56
    global PRICE_CSV_ALT_PATH_V56, PRICE_PATHS_V56
    global _CSV_DB_PATHS_V55_V56, _CSV_DB_PATHS_V54_V56

    RESOLVED_PATHS_V56     = _resolve_all_paths_v56()
    MASTER_CSV_PATH_V56    = RESOLVED_PATHS_V56['master_csv']
    PRICE_XLSX_PATH_V56    = RESOLVED_PATHS_V56['price_xlsx']
    PRICE_CSV_ALT_PATH_V56 = RESOLVED_PATHS_V56['price_csv_alt']
    PRICE_PATHS_V56        = {'xlsx': PRICE_XLSX_PATH_V56, 'csv': PRICE_CSV_ALT_PATH_V56}
    _CSV_DB_PATHS_V55_V56  = {k: RESOLVED_PATHS_V56[k] for k in _CSV_DB_PATHS_V55_V56}
    _CSV_DB_PATHS_V54_V56  = {k: RESOLVED_PATHS_V56[k] for k in _CSV_DB_PATHS_V54_V56}

    n = sum(1 for v in RESOLVED_PATHS_V56.values() if v)
    print(f"[v56-PATHS] 🔄 Reload: {n}/{len(RESOLVED_PATHS_V56)} paths OK")
    return RESOLVED_PATHS_V56


def reload_tickers_v56():
    """Hot-reload danh mục ticker (dùng khi master CSV đổi)."""
    global _MASTER_TICKERS_V56, _BANK_V56, _CORP_V56, _CMAP_V56
    global BANK_TICKERS_V41, CORP_TICKERS_V41, ALL_TICKERS_V41
    global COMPANY_MAPPING, BANK_TICKERS, CORP_TICKERS, TICKER_DISPLAY

    _MASTER_TICKERS_V56 = _load_tickers_from_master_csv_v56()
    _BANK_V56, _CORP_V56, _CMAP_V56 = _merge_and_build_tickers_v56()

    BANK_TICKERS_V41 = _BANK_V56
    CORP_TICKERS_V41 = _CORP_V56
    ALL_TICKERS_V41  = BANK_TICKERS_V41 + CORP_TICKERS_V41
    COMPANY_MAPPING  = _CMAP_V56
    BANK_TICKERS     = set(BANK_TICKERS_V41)
    CORP_TICKERS     = set(CORP_TICKERS_V41)
    TICKER_DISPLAY   = [f"{tk} - {info['name']}" for tk, info in COMPANY_MAPPING.items()]

    print(f"[v56-RELOAD] ✅ MASTER={len(_MASTER_TICKERS_V56)} | "
          f"BANK={len(BANK_TICKERS_V41)} | CORP={len(CORP_TICKERS_V41)} | "
          f"TOTAL={len(ALL_TICKERS_V41)}")
    return len(ALL_TICKERS_V41)


def get_paths_status_v56():
    """DataFrame trạng thái 17 paths (dùng cho UI sidebar)."""
    rows = []
    for key, path in RESOLVED_PATHS_V56.items():
        rows.append({
            'key':      key,
            'filename': _PATHS_REGISTRY_V56[key],
            'path':     path or '',
            'found':    bool(path),
            'size_kb':  round(os.path.getsize(path) / 1024, 1) if path else 0,
        })
    return pd.DataFrame(rows)


def print_ticker_audit_v56():
    """In bảng audit danh mục ticker + paths."""
    print("\n" + "=" * 96)
    print("[v56-AUDIT] DANH MỤC TICKER")
    print("=" * 96)
    print(f"  MASTER CSV:              {MASTER_CSV_PATH_V56 or '❌ KHÔNG TÌM THẤY'}")
    print(f"  Tickers trong CSV:       {len(_MASTER_TICKERS_V56)}")
    print(f"  BANK_TICKERS_V41:        {len(BANK_TICKERS_V41)}  (v54: {len(_BANK_TICKERS_V54)})")
    print(f"  CORP_TICKERS_V41:        {len(CORP_TICKERS_V41)}  (v54: {len(_CORP_TICKERS_V54)})")
    print(f"  ALL_TICKERS_V41:         {len(ALL_TICKERS_V41)}  (v54: {len(_ALL_TICKERS_V54)})")
    print(f"  COMPANY_MAPPING:         {len(COMPANY_MAPPING)}")
    missing_in_dict = _MASTER_TICKERS_V56 - set(ALL_TICKERS_V41)
    extra_in_dict   = set(ALL_TICKERS_V41) - _MASTER_TICKERS_V56
    print(f"  CSV có / dict thiếu:     {len(missing_in_dict)}")
    print(f"  Dict có / CSV thiếu:     {len(extra_in_dict)}  (thường là mã v54)")
    print("-" * 96)
    df = pd.DataFrame([
        {'ticker': tk,
         'group':  'BANK' if tk in BANK_TICKERS_V41 else 'CORP',
         'sector': info.get('sector', ''),
         'name':   info.get('name', '')[:60]}
        for tk, info in sorted(COMPANY_MAPPING.items())
    ])
    print(df.to_string(index=False))
    print("=" * 96 + "\n")
    return df


# ============================================================================
# [v56.8] MỞ RỘNG __all__ (không xoá mục nào của v54)
# ============================================================================
__all__ = list(_V54_ALL) + [
    # Paths
    '_PATHS_REGISTRY_V56', 'RESOLVED_PATHS_V56',
    'MASTER_CSV_PATH_V56', 'PRICE_XLSX_PATH_V56', 'PRICE_CSV_ALT_PATH_V56',
    'PRICE_PATHS_V56',
    '_CSV_DB_PATHS_V55_V56', '_CSV_DB_PATHS_V54_V56',
    '_iter_search_bases_v56', '_resolve_one_path_v56', '_resolve_all_paths_v56',
    # Tickers
    '_MASTER_TICKERS_V56', '_NEW_BANK_V56', '_NEW_CORP_V56',
    '_BANK_V56', '_CORP_V56', '_CMAP_V56',
    '_load_tickers_from_master_csv_v56', '_merge_and_build_tickers_v56',
    # Public API
    'get_ticker_info_v56', 'get_all_tickers_v56',
    'reload_paths_v56', 'reload_tickers_v56',
    'get_paths_status_v56', 'print_ticker_audit_v56',
]


# ============================================================================
# [v56.9] SELFTEST
# ============================================================================
if __name__ == "__main__":
    print("\n" + "=" * 78)
    print("SELFTEST tien_ich/cau_hinh_danh_muc_v56.py")
    print("=" * 78)

    # 1. Master CSV
    assert MASTER_CSV_PATH_V56, "❌ Không tìm thấy master CSV"
    print(f"✅ MASTER CSV: {MASTER_CSV_PATH_V56}")

    # 2. Tickers
    assert len(_MASTER_TICKERS_V56) >= 10, \
        f"❌ Chỉ đọc được {len(_MASTER_TICKERS_V56)} ticker"
    print(f"✅ Đọc {len(_MASTER_TICKERS_V56)} tickers từ CSV")

    # 3. Backward-compat v54
    for tk in _ALL_TICKERS_V54:
        assert tk in COMPANY_MAPPING, f"❌ Mất mã v54: {tk}"
    print(f"✅ Bảo toàn {len(_ALL_TICKERS_V54)} mã v54")

    # 4. Mã mới
    for tk in ['AAA', 'DGC', 'MSH', 'PNJ', 'PLX', 'NVL']:
        if tk in _MASTER_TICKERS_V56:
            info = get_ticker_info_v56(tk)
            assert info and info.get('name'), f"❌ Thiếu name cho {tk}"
            assert info.get('sector'),           f"❌ Thiếu sector cho {tk}"
    print(f"✅ Mã mới trong COMPANY_MAPPING đầy đủ name + sector")

    # 5. Phân loại
    if 'MSB' in _MASTER_TICKERS_V56:
        assert 'MSB' in BANK_TICKERS, "❌ MSB phải ở BANK"
    if 'BSI' in _MASTER_TICKERS_V56:
        assert 'BSI' in BANK_TICKERS, "❌ BSI (CK) phải ở BANK group"
    if 'BIC' in _MASTER_TICKERS_V56:
        assert 'BIC' in BANK_TICKERS, "❌ BIC (BH) phải ở BANK group"
    if 'DGC' in _MASTER_TICKERS_V56:
        assert 'DGC' in CORP_TICKERS, "❌ DGC phải ở CORP"
    print(f"✅ Phân loại BANK/CORP chính xác")

    # 6. Helpers v54 còn chạy
    assert to_float_scalar("1,234") == 1234.0
    assert safe_divide(10, 0, -1) == -1
    assert round_float(3.14159, 2) == 3.14
    assert format_pe_pb(15.5) == "15.50"
    assert fix_price(52.7) == 52_700.0
    print(f"✅ Helpers v54 còn hoạt động")

    # 7. Print audit
    print_ticker_audit_v56()
    print(f"✅ TOTAL EXPORTS: {len(__all__)} items")
    print("=" * 78)
    print("✅ ALL TESTS PASSED")
    print("=" * 78)
