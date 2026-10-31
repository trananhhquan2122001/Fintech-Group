# du_lieu/doc_bctc_goc_v56.py
# ============================================================================
# [v56] — KẾ THỪA 100% v55 + THÊM 100-MÃ DỮ LIỆU CHÍNH
# ----------------------------------------------------------------------------
# ƯU TIÊN MỚI (từ cao xuống):
#   1. _FIN_100_MA_V56    — EPS + LNST 2024/2025 của 100 mã (file 1)
#   2. _PRICE_100_MA_V56  — Bảng giá 23/10/2026 của ~70 mã (file 2)
#   3. 9 CSV gốc mới (v55)
#   4. 3 CSV cũ + SUPPLEMENT + SNAPSHOT (v54)
#   5. Derived metrics (PE/PB/BVPS/ROE/ROA)
#
# KHÔNG SỬA v55: import + mở rộng + override pipeline.
# ============================================================================

from du_lieu.doc_bctc_goc import (
    # Core helpers
    _canonical_ticker, COMPANY_MAPPING,
    BANK_DATA_LATEST, CORP_DATA_LATEST,
    BANK_TICKERS, CORP_TICKERS,
    LATEST_MARKET_SNAPSHOT, LATEST_FINANCIAL_SUPPLEMENT,
    SNAPSHOT_PRICE_DATE, SNAPSHOT_BUILD_DATE,
    _SNAPSHOT_BANK_SET,
    # Pipeline v55/v54
    _apply_latest_market_snapshot,
    _to_flat_dict, _build_result_dict, _merge_with_hardcoded,
    _extract_long_csv_metrics,
    get_financials_csv_first_v55,
    _populate_from_csv_v55,
    _load_csv_as_long_df_v55,
    _read_statement_csv_v55,
    _CSV_DB_PATHS_V55,
    MIN_REAL_EPS, MIN_REAL_BVPS,
    PE_MIN, PE_MAX, PB_MIN, PB_MAX,
    ROE_MIN_PCT, ROE_MAX_PCT, ROA_MIN_PCT, ROA_MAX_PCT,
)

import math
import numpy as np
import pandas as pd


# ============================================================================
# [v56.1] EMBED 100-MÃ FINANCIAL (2024 + 2025)
# ----------------------------------------------------------------------------
# ticker: (EPS_2024, LNST_2024_tỷ, EPS_2025, LNST_2025_tỷ)
# LNST đơn vị tỷ VND. EPS đơn vị VND/cp.
# Nguồn: file "Từ dữ liệu trong file CSV của bạn – 100 mã có đủ.txt"
# ============================================================================
_FIN_100_MA_V56 = {
    'AAA': (827,    368.6,   966,    372.9),
    'ACB': (2824,   16790.0, 2674,   15620.0),
    'ADS': (667,    50.1,    1266,   96.7),
    'AGR': (474,    135.2,   500,    141.9),
    'ANV': (179,    47.8,    3754,   999.5),
    'BAF': (1286,   317.0,   412,    126.6),
    'BCM': (2008,   2190.0,  3249,   3500.0),
    'BFC': (5486,   357.5,   4878,   309.9),
    'BHN': (1599,   370.7,   2016,   467.2),
    'BIC': (2083,   495.8,   2686,   542.7),
    'BID': (3008,   25210.0, 3532,   29900.0),
    'BMI': (1278,   237.7,   1469,   257.2),
    'BMP': (12103,  990.8,   15010,  1230.0),
    'BSI': (1413,   413.1,   1829,   493.7),
    'BSR': (796,    31.1,    1040,   5210.0),
    'BWE': (2357,   638.9,   3657,   991.0),
    'CHP': (1897,   313.8,   2781,   458.3),
    'CII': (641,    259.7,   196,    124.1),
    'CMG': (1157,   336.5,   1234,   348.6),
    'CSM': (623,    72.1,    411,    42.6),
    'CTD': (2768,   309.6,   4136,   453.8),
    'CTG': (3083,   25350.0, 4455,   34600.0),
    'CTR': (4201,   538.2,   4681,   599.7),
    'CTS': (759,    231.1,   2121,   577.4),
    'DBD': (2530,   275.2,   2674,   291.9),
    'DCM': (2359,   1420.0,  3203,   1960.0),
    'DGC': (7392,   2990.0,  7402,   2990.0),
    'DHG': (5763,   778.9,   6308,   852.4),
    'DIG': (155,    114.5,   988,    646.5),
    'DLG': (695,    207.9,   1218,   364.7),
    'DMC': (4962,   202.7,   4856,   198.4),
    'DPM': (620,    537.8,   1427,   1070.0),
    'DRC': (1559,   240.8,   767,    118.5),
    'DSC': (669,    176.8,   1268,   275.2),
    'DVP': (8406,   336.2,   8454,   338.2),
    'DXG': (254,    255.9,   188,    230.9),
    'DXS': (236,    140.7,   589,    351.5),
    'EIB': (1663,   3330.0,  610,    1140.0),
    'FIT': (351,    119.3,   118,    40.0),
    'FMC': (4675,   305.7,   5332,   348.7),
    'FPT': (4292,   7860.0,  5216,   9380.0),
    'FRT': (1748,   317.5,   4431,   794.9),
    'FTS': (1431,   567.3,   1055,   396.8),
    'GAS': (4140,   10400.0, 4647,   11410.0),
    'GEE': (2495,   1590.0,  5098,   3260.0),
    'GEG': (166,    114.8,   1655,   708.5),
    'GEX': (1165,   1630.0,  1092,   1480.0),
    'GMD': (4276,   1460.0,  3839,   1760.0),
    'GVR': (895,    3990.0,  1250,   5320.0),
    'HAH': (3773,   650.5,   6830,   1210.0),
    'HCM': (1267,   1040.0,  1468,   1180.0),
    'HDB': (2816,   12760.0, 3297,   16500.0),
    'HDC': (336,    66.1,    3095,   639.1),
    'HDG': (855,    348.3,   1893,   770.4),
    'HHV': (907,    426.4,   1183,   580.8),
    'HNA': (1076,   271.6,   2023,   475.8),
    'HPG': (1368,   12020.0, 1794,   15450.0),
    'HT1': (101,    60.1,    717,    273.7),
    'HVN': (2692,   7560.0,  2949,   7200.0),
    'IDI': (248,    60.5,    469,    128.0),
    'IJC': (809,    354.1,   1318,   597.4),
    'IMP': (1932,   320.9,   1976,   349.1),
    'KBC': (498,    381.9,   2450,   2100.0),
    'KDC': (88,     37.3,    1803,   522.4),
    'KDH': (720,    810.4,   870,    1050.0),
    'KOS': (99,     21.4,    88,     18.9),
    'LGC': (2532,   531.8,   2590,   510.4),
    'LPB': (3221,   9720.0,  3824,   11420.0),
    'MBB': (2251,   22630.0, 2891,   26780.0),
    'MCH': (5998,   7800.0,  5557,   6670.0),
    'MCM': (1799,   219.9,   1765,   215.7),
    'MIG': (1163,   238.5,   1553,   324.9),
    'MSB': (1474,   5520.0,  1503,   5630.0),
    'MSH': (3322,   412.5,   5456,   613.9),
    'MSN': (1345,   2000.0,  2710,   4110.0),
    'MWG': (2546,   3720.0,  4774,   7030.0),
    'NAB': (2361,   6100.0,  2418,   6250.0),  # ước tính — nguồn format lỗi
    'NKG': (1225,   453.0,   411,    197.1),
    'NLG': (1177,   517.9,   1363,   701.4),
    'NSC': (9981,   217.9,   12278,  219.3),
    'NT2': (190,    54.7,    3829,   1100.0),
    'NTC': (12050,  None,    13410,  321.8),
    'NTL': (4728,   620.1,   133,    17.4),
    'NVL': (-3004,  -6450.0, 807,    1740.0),
    'OCB': (1026,   3170.0,  1299,   4010.0),
    'OGC': (394,    119.3,   224,    67.1),
    'ORS': (1135,   379.1,   352,    118.5),
    'PAN': (2091,   608.9,   2556,   672.7),
    'PC1': (1001,   467.6,   2235,   1040.0),
    'PDN': (5808,   347.2,   7350,   436.5),
    'PDR': (170,    155.1,   534,    515.1),
    'PET': (904,    149.7,   1567,   258.1),
    'PGD': (2265,   249.2,   1579,   168.4),
    'PGI': (1493,   232.2,   2214,   245.5),
    'PGV': (-724,   -878.4,  3067,   3720.0),
    'PHR': (1731,   460.0,   1802,   478.2),
    'PLX': (1509,   2890.0,  1472,   2680.0),
    'PNJ': (3809,   2110.0,  5101,   2830.0),
    'POW': (321,    1110.0,  871,    2430.0),
    'PPC': (1332,   427.1,   530,    169.9),
}


# ============================================================================
# [v56.2] EMBED BẢNG GIÁ 23/10/2026 (~70 mã)
# ----------------------------------------------------------------------------
# Nguồn: file "Bảng giá hiện tại (sắp xếp theo mã).txt"
# Mã không có giá → 0 (sẽ fallback snapshot)
# ============================================================================
_PRICE_100_MA_V56 = {
    'AAA': 7075,    # ~6,900–7,250 → lấy midpoint
    'ACB': 21000,
    'ANV': 22900,
    'BAF': 30600,
    'BCM': 38400,
    'BHN': 26200,
    'BID': 33400,
    'BMP': 137500,
    'BSI': 26600,
    'BSR': 27600,
    'BWE': 42800,
    'CII': 13200,
    'CTD': 64000,
    'CTG': 30300,
    'CTR': 67400,
    'CTS': 21000,
    'DBD': 45750,
    'DCM': 33300,
    'DGC': 33300,
    'DHG': 86900,
    'DIG': 9550,
    'DPM': 20400,
    'DXG': 10100,
    'EIB': 16100,
    'FPT': 52700,
    'FRT': 148700,
    'FTS': 17900,
    'GAS': 78000,
    'GEE': 66300,
    'GEG': 11700,
    'GEX': 22200,
    'GMD': 52700,
    'GVR': 31250,
    'HAH': 49650,
    'HCM': 23200,
    'HDB': 22400,
    'HDG': 15000,
    'HHV': 9300,
    'HNA': 21000,
    'HPG': 21000,
    'HT1': 12900,
    'HVN': 20750,
    'IMP': 35800,
    'KBC': 26000,
    'KDC': 50200,
    'KDH': 13900,
    'LGC': 64800,
    'LPB': 36100,
    'MBB': 19300,
    'MCH': 135000,
    'MSB': 15800,
    'MSN': 70000,
    'MWG': 74000,
    'NAB': 12650,
    'NKG': 11900,
    'NLG': 22000,
    'NT2': 22500,
    'NVL': 10400,
    'OCB': 10600,
    'ORS': 14150,
    'PC1': 18500,
    'PDN': 82900,
    'PDR': 11300,
    'PET': 51100,
    'PGV': 20550,
    'PHR': 31000,
    'PLX': 34000,
    'PNJ': 15500,
    'POW': 12200,
}

PRICE_100_MA_AS_OF_V56 = '2026-10-23'
PRICE_100_MA_SOURCE_V56 = 'Bang gia 100 ma (file 2)'


# ============================================================================
# [v56.3] DERIVE: SLCP từ LNST ÷ EPS, rồi VỐN HÓA = GIÁ × SLCP
# ============================================================================
def _compute_shares_100_ma_v56(ticker):
    """SLCP suy ra = LNST_2025(tỷ) × 1e9 ÷ EPS_2025. Fallback 2024."""
    t = _canonical_ticker(ticker)
    d = _FIN_100_MA_V56.get(t)
    if not d:
        return 0.0
    eps24, lnst24, eps25, lnst25 = d
    # Ưu tiên 2025
    if eps25 and lnst25 and eps25 > 0 and lnst25 > 0:
        return (float(lnst25) * 1e9) / float(eps25)
    if eps24 and lnst24 and eps24 > 0 and lnst24 > 0:
        return (float(lnst24) * 1e9) / float(eps24)
    return 0.0


def _compute_market_cap_100_ma_v56(ticker):
    """Vốn hóa (tỷ VND) = Giá × SLCP ÷ 1e9."""
    t = _canonical_ticker(ticker)
    price = _PRICE_100_MA_V56.get(t, 0)
    shares = _compute_shares_100_ma_v56(t)
    if price > 0 and shares > 0:
        return (float(price) * shares) / 1e9
    return 0.0


def _compute_pe_100_ma_v56(ticker, use_2025=True):
    """P/E = Giá ÷ EPS. Dùng EPS 2025 (mặc định) hoặc 2024."""
    t = _canonical_ticker(ticker)
    d = _FIN_100_MA_V56.get(t)
    price = _PRICE_100_MA_V56.get(t, 0)
    if not d or price <= 0:
        return 0.0
    eps = d[2] if use_2025 else d[0]
    if not eps or eps <= 0:
        return 0.0
    pe = float(price) / float(eps)
    return round(pe, 2) if PE_MIN <= pe <= PE_MAX * 3 else 0.0


# ============================================================================
# [v56.4] 🔷 HÀM ƯU TIÊN — ĐỌC 100-MÃ TRƯỚC (hàm chính)
# ============================================================================
def get_financials_100_ma_priority(ticker):
    """
    ⭐ HÀM ƯU TIÊN SỐ 1 — Đọc 100-mã trước.
    Trả dict theo schema chuẩn của get_financials_csv_first_v55.
    Trả None nếu ticker không có trong bảng 100-mã.
    """
    t = _canonical_ticker(ticker)
    if t not in _FIN_100_MA_V56:
        return None

    eps24, lnst24, eps25, lnst25 = _FIN_100_MA_V56[t]
    price = float(_PRICE_100_MA_V56.get(t, 0))
    shares = _compute_shares_100_ma_v56(t)
    mcap = _compute_market_cap_100_ma_v56(t)
    pe25 = _compute_pe_100_ma_v56(t, use_2025=True)
    pe24 = _compute_pe_100_ma_v56(t, use_2025=False)

    # Ưu tiên EPS 2025; nếu LNST 2025 thiếu thì lấy 2024
    eps_use = float(eps25) if eps25 else float(eps24 or 0)
    lnst_use = float(lnst25) if lnst25 else float(lnst24 or 0)

    is_bank = t in _SNAPSHOT_BANK_SET or t in BANK_TICKERS

    result = {
        # ---- MARKET (từ file 2) ----
        'gia_hien_tai': price,
        'price_vnd': price,
        'price_as_of': PRICE_100_MA_AS_OF_V56,
        'price_is_stale': False,
        'price_stale_days': 0,
        'shares': shares,
        'shares_is_official': False,
        'shares_is_estimated': True,
        'shares_basis': 'computed_lnst_div_eps',
        'market_cap': mcap * 1e9,
        'market_cap_ty': mcap,
        'dividend_yield_pct': 0.0,
        'co_tuc_cp': 0.0,
        'ty_le_co_tuc': 0.0,

        # ---- FINANCIAL (từ file 1) — 100% thắng ----
        'eps': eps_use,
        'eps_ttm_vnd': eps_use,
        'has_eps': eps_use > 0,
        'lnst_2024_ty': float(lnst24) if lnst24 is not None else 0.0,
        'lnst_2025_ty': float(lnst25) if lnst25 is not None else 0.0,
        'lnst_6m_ty': lnst_use,          # proxy: dùng 2025 làm "gần nhất"
        'profit_ty': lnst_use,
        'lnst_6t2026_ty': lnst_use,      # proxy
        'lntt_6m_ty': 0.0,               # không có trong nguồn
        'lntt_2024_ty': 0.0,
        'lntt_2025_ty': 0.0,
        'lnst_me_2024_ty': 0.0,          # nguồn là hợp nhất
        'lnst_me_2025_ty': 0.0,
        'equity_ty': 0.0,
        'total_assets_ty': 0.0,
        'nii_ty': 0.0,

        # ---- DERIVED ----
        'pe': pe25,
        'pe_ttm': pe25,
        'pe_2024': pe24,
        'pb': 0.0,
        'bvps': 0.0,
        'bvps_vnd': 0.0,
        'has_bvps': False,
        'roe': 0.0,
        'roe_pct': 0.0,
        'roa': 0.0,
        'roa_pct': 0.0,
        'casa_pct': 0.0,

        # ---- META ----
        '_data_source': '100_MA_V56',
        '_eps_source': '100_MA_2025' if eps25 else '100_MA_2024',
        '_pe_source': '100_MA_COMPUTED',
        '_lnst_source': '100_MA_2025' if lnst25 else '100_MA_2024',
        'financial_as_of': '2025-12-31',
        'financial_note': 'EPS + LNST 2024/2025 từ 100-mã; PE = Giá 23/10/2026 ÷ EPS 2025',
        'is_bank': is_bank,
        'sector': COMPANY_MAPPING.get(t, {}).get(
            'sector', 'Ngân hàng' if is_bank else 'Doanh nghiệp niêm yết'),
    }
    return result


# ============================================================================
# [v56.5] 🛡️ HÀM DỰ PHÒNG — CHỈ KHI 100-MÃ THIẾU
# ============================================================================
def get_financials_fallback_v56(ticker, csv_df=None, use_supplement=True):
    """
    Hàm dự phòng: gọi pipeline v55 (9 CSV mới → 3 CSV cũ → snapshot).
    Chỉ dùng khi get_financials_100_ma_priority() trả None hoặc thiếu giá/EPS.
    """
    return get_financials_csv_first_v55(
        ticker, csv_df=csv_df, use_supplement=use_supplement
    )


# ============================================================================
# [v56.6] 🚀 PUBLIC API — TỰ ĐỘNG THỬ 100-MÃ → FALLBACK
# ============================================================================
def get_financials_v56(ticker, csv_df=None, use_supplement=True):
    """
    API chính của v56 — thay thế get_financials_csv_first_v55.
    Thứ tự: 100-MÃ → v55 pipeline (9 CSV → 3 CSV → supplement → snapshot).
    """
    t = _canonical_ticker(ticker)

    # 1️⃣ Ưu tiên 100-mã
    primary = get_financials_100_ma_priority(t)
    if primary and primary.get('price_vnd', 0) > 0 and primary.get('eps_ttm_vnd', 0) != 0:
        primary['_priority_trace'] = {
            'ticker': t,
            'data_source': '100_MA_V56',
            'price_source': '100_MA_PRICE',
            'eps_source': primary['_eps_source'],
            'lnst_source': primary['_lnst_source'],
            'pe_source': '100_MA_COMPUTED',
            'csv_file_found': True,
        }
        primary['sanity_warnings'] = []
        primary['_data_quality_warnings'] = []
        return primary

    # 2️⃣ Fallback v55
    fb = get_financials_fallback_v56(t, csv_df=csv_df, use_supplement=use_supplement)
    if not isinstance(fb, dict):
        return fb

    # Nếu fallback thiếu nhưng 100-mã có 1 phần (vd thiếu giá) → merge những gì 100-mã có
    if primary:
        for k, v in primary.items():
            if k.startswith('_'):
                continue
            cur = fb.get(k)
            if isinstance(v, (int, float)) and v != 0:
                if not isinstance(cur, (int, float)) or cur == 0:
                    fb[k] = v
        fb['_data_source'] = (fb.get('_data_source', '') + '+100_MA_PARTIAL').strip('+')
    return fb


def get_price_v56(ticker):
    """Đọc giá: 100-MÃ trước → SNAPSHOT."""
    t = _canonical_ticker(ticker)
    p = _PRICE_100_MA_V56.get(t, 0)
    if p > 0:
        return {
            'ticker': t,
            'price_vnd': float(p),
            'price_as_of': PRICE_100_MA_AS_OF_V56,
            'source': '100_MA_PRICE',
        }
    snap = LATEST_MARKET_SNAPSHOT.get(t, {})
    if snap.get('price_vnd', 0) > 0:
        return {
            'ticker': t,
            'price_vnd': float(snap['price_vnd']),
            'price_as_of': snap.get('price_as_of', ''),
            'source': 'SNAPSHOT_V54',
        }
    return {'ticker': t, 'price_vnd': 0.0, 'price_as_of': '', 'source': 'MISSING'}


def get_market_cap_v56(ticker):
    """Vốn hóa: 100-MÃ (computed) trước → SNAPSHOT."""
    t = _canonical_ticker(ticker)
    mcap = _compute_market_cap_100_ma_v56(t)
    if mcap > 0:
        return {'ticker': t, 'market_cap_ty': mcap, 'source': '100_MA_COMPUTED'}
    snap = LATEST_MARKET_SNAPSHOT.get(t, {})
    if snap.get('market_cap_ty', 0) > 0:
        return {'ticker': t, 'market_cap_ty': float(snap['market_cap_ty']),
                'source': 'SNAPSHOT_V54'}
    return {'ticker': t, 'market_cap_ty': 0.0, 'source': 'MISSING'}


# ============================================================================
# [v56.7] PIPELINE POPULATE MỚI: 100-MÃ → v55 (9 CSV → 3 CSV → snapshot)
# ============================================================================
def _populate_from_100_ma_first_v56():
    """
    Bước 1 của pipeline v56: NẠP 100-MÃ vào 2 dict toàn cục.
    100-mã THẮNG tuyệt đối các nguồn cũ (trừ meta dividend/casa của snapshot).
    """
    global BANK_DATA_LATEST, CORP_DATA_LATEST
    global BANK_TICKERS, CORP_TICKERS

    n_bank = n_corp = 0
    for t in _FIN_100_MA_V56.keys():
        fin = get_financials_100_ma_priority(t)
        if not fin:
            continue

        is_bank = fin['is_bank']
        target = BANK_DATA_LATEST if is_bank else CORP_DATA_LATEST

        # Flatten về schema dict chuẩn của v54/v55
        flat = {k: v for k, v in fin.items() if not k.startswith('_')}
        flat['sector'] = fin['sector']

        # Gộp: 100-mã THẮNG về price/shares/eps/lnst/pe/market_cap
        existing = target.get(t, {})
        existing.update(flat)

        # Snapshot chỉ fill các field 100-mã KHÔNG có (dividend, casa, ...)
        existing = _apply_latest_market_snapshot(
            t, existing, prioritize_csv_financials=False
            # ^ False = KHÔNG cho snapshot đè financial 100-mã; chỉ fill gap
        )

        # Đảm bảo price/shares/eps của 100-mã vẫn thắng sau khi qua snapshot
        existing['price_vnd'] = fin['price_vnd']
        existing['gia_hien_tai'] = fin['price_vnd']
        existing['shares'] = fin['shares']
        existing['eps'] = fin['eps']
        existing['eps_ttm_vnd'] = fin['eps_ttm_vnd']
        existing['pe'] = fin['pe']
        existing['pe_ttm'] = fin['pe_ttm']
        existing['market_cap_ty'] = fin['market_cap_ty']
        existing['market_cap'] = fin['market_cap'] if 'market_cap' in fin else fin['market_cap_ty'] * 1e9

        target[t] = existing
        if is_bank:
            n_bank += 1
        else:
            n_corp += 1

    BANK_TICKERS = set(BANK_TICKERS) | set(BANK_DATA_LATEST.keys())
    CORP_TICKERS = set(CORP_DATA_LATEST.keys())

    print(f"[v56] ✅ Nạp 100-MÃ: {n_bank} bank + {n_corp} corp "
          f"(tổng {n_bank + n_corp} mã)")
    return n_bank + n_corp


def _populate_from_csv_v56():
    """
    Pipeline v56 hoàn chỉnh:
        1) 100-MÃ (ưu tiên tuyệt đối)
        2) v55 pipeline (9 CSV mới → 3 CSV cũ → supplement → snapshot) — chỉ fill gap
    """
    print("\n" + "=" * 78)
    print("[v56-PIPELINE] 🚀 BẮT ĐẦU: 100-MÃ → 9 CSV → 3 CSV → SNAPSHOT")
    print("=" * 78)

    _populate_from_100_ma_first_v56()

    print("\n[v56-PIPELINE] ⏭  Chạy v55 pipeline để fill gap (KHÔNG đè 100-mã)")
    _populate_from_csv_v55()

    print(f"\n[v56-PIPELINE] ✅ HOÀN TẤT — BANK={len(BANK_DATA_LATEST)} "
          f"CORP={len(CORP_DATA_LATEST)}")
    print("=" * 78 + "\n")


# ============================================================================
# [v56.8] AUDIT 100-MÃ
# ============================================================================
def get_100_ma_coverage_v56():
    """DataFrame audit 100-mã: EPS/LNST/Giá/SLCP/Vốn hóa/PE."""
    rows = []
    for t in sorted(_FIN_100_MA_V56.keys()):
        eps24, lnst24, eps25, lnst25 = _FIN_100_MA_V56[t]
        price = _PRICE_100_MA_V56.get(t, 0)
        shares = _compute_shares_100_ma_v56(t)
        mcap = _compute_market_cap_100_ma_v56(t)
        pe25 = _compute_pe_100_ma_v56(t, use_2025=True)
        pe24 = _compute_pe_100_ma_v56(t, use_2025=False)
        rows.append({
            'ticker': t,
            'eps_2024': eps24,
            'lnst_2024_ty': lnst24,
            'eps_2025': eps25,
            'lnst_2025_ty': lnst25,
            'price_vnd': price,
            'shares_mn': shares / 1e6,
            'market_cap_ty': mcap,
            'pe_2024': pe24,
            'pe_2025': pe25,
            'has_price': price > 0,
            'has_fin': eps25 is not None and lnst25 is not None,
        })
    return pd.DataFrame(rows)


def print_100_ma_audit_v56():
    print("\n" + "=" * 104)
    print(f"[v56-AUDIT] 100-MÃ — Ngày giá {PRICE_100_MA_AS_OF_V56}")
    print("=" * 104)
    df = get_100_ma_coverage_v56()
    n_fin = int(df['has_fin'].sum())
    n_price = int(df['has_price'].sum())
    print(f"  • Tài chính 2024/2025: {n_fin}/100 mã")
    print(f"  • Có giá:              {n_price}/100 mã")
    print("-" * 104)
    for _, r in df.iterrows():
        flag = '✅' if (r['has_fin'] and r['has_price']) else (
            '📊' if r['has_fin'] else ('💰' if r['has_price'] else '❌'))
        eps24 = f"{r['eps_2024']:>8,}" if r['eps_2024'] is not None else "    N/A"
        eps25 = f"{r['eps_2025']:>8,}" if r['eps_2025'] is not None else "    N/A"
        lnst25 = f"{r['lnst_2025_ty']:>10,.1f}" if r['lnst_2025_ty'] is not None else "       N/A"
        pe25 = f"{r['pe_2025']:>6.2f}" if r['pe_2025'] > 0 else "   N/A"
        print(f"{flag} {r['ticker']:<5}  EPS24={eps24}  EPS25={eps25}  "
              f"LNST25={lnst25} tỷ  Giá={r['price_vnd']:>8,.0f}  "
              f"SLCP={r['shares_mn']:>8.1f}tr  VốnHóa={r['market_cap_ty']:>10,.0f} tỷ  PE={pe25}")
    print("=" * 104 + "\n")
    return df


# ============================================================================
# [v56.9] MỞ RỘNG __all__
# ============================================================================
try:
    from du_lieu.doc_bctc_goc import __all__ as _V55_ALL
    __all__ = list(_V55_ALL) + [
        '_FIN_100_MA_V56', '_PRICE_100_MA_V56',
        'PRICE_100_MA_AS_OF_V56', 'PRICE_100_MA_SOURCE_V56',
        '_compute_shares_100_ma_v56',
        '_compute_market_cap_100_ma_v56',
        '_compute_pe_100_ma_v56',
        'get_financials_100_ma_priority',
        'get_financials_fallback_v56',
        'get_financials_v56',
        'get_price_v56', 'get_market_cap_v56',
        '_populate_from_100_ma_first_v56',
        '_populate_from_csv_v56',
        'get_100_ma_coverage_v56',
        'print_100_ma_audit_v56',
    ]
except Exception:
    pass
