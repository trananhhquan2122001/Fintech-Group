# du_lieu/doc_bctc_goc.py
# ============================================================================
# [v55] — KẾ THỪA 100% v54 (KHÔNG SỬA BẤT KỲ DÒNG NÀO CỦA v54)
# ----------------------------------------------------------------------------
# GIỮ NGUYÊN TOÀN BỘ v54:
#   ✅ _parse_vn_number, clean_numeric
#   ✅ _METRIC_ALIASES / _LONG_METRIC_ALIASES
#   ✅ _extract_smart_v33, _wide_df_to_long, _read_csv_multiencoding
#   ✅ fix_price / fix_bvps / fix_eps / fix_dividend / fix_shares
#   ✅ _detect_unit_from_colname / _to_ty / _detect_file_scale
#   ✅ _load_csv_db_to_df / _load_csv_as_long_df / _populate_from_csv
#   ✅ LATEST_MARKET_SNAPSHOT (41 mã) — snapshot luôn thắng về MARKET
#   ✅ LATEST_FINANCIAL_SUPPLEMENT (REE / FPT / BSR / CTG)
#   ✅ _apply_latest_market_snapshot — CSV thắng về FINANCIAL
#   ✅ get_financials_csv_first, validate_snapshot, print_snapshot_audit, ...
#
# BỔ SUNG v55 (chỉ APPEND, không ghi đè):
#   1. 9 file CSV gốc mới (LCTT / KQKD / BCDKT × 3 nhóm ngành)
#   2. Reader riêng cho format "wide với meta cột" của 9 file mới
#   3. Quy đổi period thông minh (KQKD cộng Q1+Q2 → H1; LCTT lấy Q2 = H1;
#      BCDKT Q2 → H1, Q4 → Năm)
#   4. _populate_from_csv_v55()  : chạy v54 trước, MERGE 9 CSV mới vào dict
#   5. get_financials_csv_first_v55() : pipeline CSV-first 12 file
#   6. get_csv_v55_coverage_report() / print_csv_v55_audit() : audit 9 file mới
#   7. Mở rộng __all__ (list + extend, KHÔNG xoá mục cũ)
#
# THỨ TỰ DỮ LIỆU TUYỆT ĐỐI (v55 kế thừa v54, không đổi):
#  Market  (giá, vốn hóa, SLCP, CASA, dividend yield)   -> SNAPSHOT thắng
#  Financial (LNST, LNTT, doanh thu, VCSH, tổng TS)     -> CSV 100% thắng
#  Gap fill                                             -> SUPPLEMENT rồi SNAPSHOT
#  Derived (P/E, P/B, EPS, BVPS, ROE, ROA)              -> tính lại từ data cuối
# ============================================================================

import os
import re
import io
import json
import random
import requests
import pandas as pd
import polars as pl
import numpy as np
import streamlit as st
from datetime import datetime as _dt
from rapidfuzz import process, fuzz

from tien_ich.cau_hinh_danh_muc import (
    COMPANY_MAPPING, BANK_TICKERS, THRESHOLDS,
    to_float_scalar, safe_divide, round_float,
    format_currency_vn, format_currency_vn_advanced,
    format_eps_value, format_pe_pb,
)


# ============================================================================
# [v36.1] HARDCODED 3 PATHS — GIỮ NGUYÊN
# ============================================================================
_CSV_FILENAMES = {
    'san_xuat_va_khac':       'du_lieu_san_xuat_va_khac.csv',
    'ngan_hang_va_tai_chinh': 'du_lieu_ngan_hang_va_tai_chinh.csv',
    'cong_nghe':              'du_lieu_cong_nghe.csv',
}

_DEFAULT_CSV_PATHS = {
    'san_xuat_va_khac':       r'du_lieu_san_xuat_va_khac.csv',
    'ngan_hang_va_tai_chinh': r'du_lieu_ngan_hang_va_tai_chinh.csv',
    'cong_nghe':              r'du_lieu_cong_nghe.csv',
}


# ============================================================================
# [v54] NGÀY ĐÓNG BỘ DỮ LIỆU
# ============================================================================
SNAPSHOT_PRICE_DATE   = '2026-10-22'
SNAPSHOT_BUILD_DATE   = '2026-10-23'
SNAPSHOT_SOURCE       = 'Bang gia + BCTC cap nhat 22-23/10/2026'
STALE_PRICE_DAYS      = 1
MATERIALLY_STALE_DAYS = 7
CAP_SHARES_TOL        = 0.01

_TODAY = _dt(2026, 10, 23)

TICKER_ALIASES = {
    'CMC': 'CMG',
}

_SNAPSHOT_BANK_SET = {
    'VCB', 'BID', 'CTG', 'TCB', 'VPB', 'MBB', 'HDB', 'ACB',
    'STB', 'LPB', 'SHB', 'SSB', 'VIB', 'EIB', 'TCX', 'SSI',
}


def _canonical_ticker(ticker):
    t = str(ticker).strip().upper()
    return TICKER_ALIASES.get(t, t)


def _days_between(date_str):
    try:
        d = _dt.strptime(str(date_str).strip(), '%Y-%m-%d')
        return max(0, (_TODAY - d).days)
    except Exception:
        return 999


# ============================================================================
# [v54] BẢNG GIÁ 22/10/2026 — 41 MÃ
# ============================================================================
_SNAPSHOT_ROWS = [
    ('HPG',   21250,   179413,      8443.0,    2.35,  False, '2026-10-22', ''),
    ('VHM',   64000,   525748,      8215.0,    9.38,  False, '2026-10-22', ''),
    ('GAS',   78100,   188451,      2413.0,    3.20,  False, '2026-10-22', ''),
    ('GVR',   31900,   127600,      4000.0,    1.25,  False, '2026-10-22', ''),
    ('VPL',   85500,   153327,      1793.0,    0.00,  False, '2026-10-22', ''),
    ('VIC',  232900,  1807813,      7762.0,    0.00,  False, '2026-10-22', ''),
    ('VRE',   25300,    57490,      2272.3,    3.95,  True,  '2026-10-22',
        'SLCP chính thức 2.272,3 triệu; 1.000đ tiền mặt + thưởng 22,5%; chốt quyền 28/10/2026'),
    ('BSR',   29200,   146213,      5007.0,    1.03,  False, '2026-10-22', ''),
    ('VJC',  128600,    98905,       769.0,    0.00,  False, '2026-10-22', ''),
    ('VNM',   58100,   121426,      2090.0,    3.18,  False, '2026-10-22', ''),
    ('GEE',   73000,    46756,       640.5,    4.50,  True,  '2026-10-22',
        'SLCP chính thức 640,5 triệu; cổ tức 500đ/lần, ~4,5%/năm (nhiều đợt)'),
    ('REE',   46000,    28676,       623.4,    2.17,  True,  '2026-10-23',
        'SLCP chính thức 623,4 triệu; giá 23/10 (giảm 0,54%); 1.000đ + 15% cổ phiếu (2025)'),
    ('GMD',   57500,    37300,       649.0,    2.84,  False, '2026-10-22',
        'SLCP ~649 triệu SAU thưởng 2:1; tỷ suất 2,84% tính TRƯỚC thưởng'),
    ('KSV',  127000,    38100,       300.0,    3.60,  True,  '2026-10-12',
        'SLCP chính thức 300,0 triệu; GIÁ 12/10 CHƯA xác nhận 22/10'),
    ('GEX',       0,        0,         0.0,    0.00,  False, '',
        'CHƯA LẤY ĐƯỢC giá 22/10/2026 — chờ bổ sung'),
    ('PVI',   66300,    17083,       258.0,    8.20,  False, '2026-09-29',
        'GIÁ 29/9 CHƯA cập nhật'),
    ('POW',   12550,    38500,      3067.8,    0.00,  True,  '2026-10-22',
        'SLCP chính thức 3.067,8 triệu; KHÔNG chia tiền mặt (năm thứ 5); '
        '4% cổ phiếu (chốt 11/12/2025) + thưởng 15% + chào bán 12% giá 10.000đ'),
    ('FRT',  142000,    25391,       179.0,    0.00,  False, '2026-09-29',
        'GIÁ 29/9 CHƯA cập nhật'),
    ('MCH',  141000,   184344,      1307.0,    3.19,  False, '2026-10-22', ''),
    ('MSN',   73900,   107921,      1460.0,    0.00,  False, '2026-10-22', ''),
    ('MWG',   75300,   111119,      1476.0,    2.66,  False, '2026-10-22', ''),
    ('SAB',       0,        0,         0.0,    0.00,  False, '',
        'CHƯA LẤY ĐƯỢC giá 22/10/2026 — chờ bổ sung'),

    ('VCB',   56300,   470424,      8356.0,    0.80,  False, '2026-10-22', ''),
    ('BID',   33800,   262904,      7778.0,    1.33,  False, '2026-10-22', ''),
    ('TCB',   34150,   241995,      7086.0,    2.05,  False, '2026-10-22',
        'không chia cổ tức năm 2026; 2,05% là tỷ suất TTM'),
    ('VPB',   23950,   239500,     10000.0,    2.09,  False, '2026-10-22', ''),
    ('CTG',   30550,   237280,      7767.0,    1.47,  False, '2026-10-22',
        'LNTT 2025: 43.400 tỷ | LNST mẹ 2025: 34.600 tỷ | LNST mẹ 6T/2026: 20.657 tỷ'),
    ('MBB',   19900,   200368,     10069.0,    5.03,  False, '2026-10-22',
        'SLCP 10.069 triệu CHƯA chốt: vừa 15% cổ phiếu + quyền mua 10:1; '
        '1.000đ tiền mặt (09/07/2026)'),
    ('HDB',   22350,   145428,      6507.0,    0.00,  False, '2026-10-22', ''),
    ('STB',   64100,   120842,      1885.0,    0.00,  False, '2026-10-22', ''),
    ('ACB',   20500,   118990,      5804.0,    3.41,  False, '2026-10-22', ''),
    ('LPB',   39000,   116504,      2987.0,    7.69,  False, '2026-10-22', ''),
    ('TCX',   29850,    99380,      3329.0,    1.68,  False, '2026-10-22', ''),
    ('SSI',   20250,    59875,      3001.0,    4.94,  False, '2026-10-21',
        'GIÁ 21/10; LỆCH bộ ba: 20.250 x 3.001tr = 60.770 tỷ != 59.875 tỷ '
        '-> tự suy SLCP = vốn hóa/g giá = ~2.956,8 triệu'),
    ('SHB',   10550,    56376,      5344.0,    0.00,  False, '2026-10-21',
        'GIÁ 21/10; dự kiến 6% tiền mặt 11/2026 + 10% cổ phiếu'),
    ('SSB',   15750,    54633,      3469.0,    0.00,  False, '2026-10-21',
        'GIÁ 21/10'),
    ('VIB',   13750,    51361,      3735.0,    6.50,  False, '2026-10-21',
        'GIÁ 21/10'),
    ('EIB',   16300,    30362,      1863.0,    0.00,  False, '2026-10-21',
        'GIÁ 21/10'),

    ('FPT',   57400,   108240,  1885.727620,    3.48,  True,  '2026-10-22',
        'SLCP CHÍNH XÁC 1.885.727.620; cổ tức 2025: 2.000đ/cp; '
        'thưởng 10:1 đã thực hiện 28/05/2026; đứng giá 22/10'),
    ('CTR',   69300,     8877,   128.112184,    2.20,  True,  '2026-10-21',
        'SLCP lưu hành 128.112.184 (niêm yết 128.109.533); '
        'cổ tức 2024: 2.150đ/cp; GIÁ 20-21/10 CHƯA xác nhận 22/10'),
    ('CMG',   19750,     4600,   232.900908,    0.00,  True,  '2026-10-20',
        'Tập đoàn Công nghệ CMC — HOSE (alias CMC -> CMG); '
        'SLCP chính thức 232.900.908; GIÁ 20/10; cổ tức chưa có số'),
]


_BANK_STRUCTURE_V37 = {
    'VCB': {'casa_pct': 32.78, 'total_assets_ty': 2_657_000, 'lntt_6m_ty': 29222,
            'lnst_2024_ty': 33831, 'lnst_2025_ty': 35200},
    'BID': {'casa_pct': 20.37, 'total_assets_ty': 3_440_844, 'lntt_6m_ty': 18905,
            'lnst_2024_ty': 25140, 'lnst_2025_ty': 29900},
    'CTG': {'casa_pct': 23.17, 'total_assets_ty': 2_924_000,
            'lntt_2025_ty': 43400, 'lnst_2024_ty': 25300,
            'lnst_2025_ty': 34600, 'lnst_6t2026_ty': 20657,
            'roe_pct': 21.2, 'roa_pct': 1.69},
    'TCB': {'casa_pct': 35.02, 'total_assets_ty': 1_273_000, 'lntt_6m_ty': 18540,
            'lnst_2024_ty': 21500, 'lnst_2025_ty': 25300},
    'VPB': {'casa_pct': None, 'total_assets_ty': 1_500_000, 'lntt_6m_ty': 18900},
    'MBB': {'casa_pct': 34.43, 'total_assets_ty': 1_730_000, 'lntt_6m_ty': 20188,
            'lnst_2024_ty': 22650, 'lnst_2025_ty': 26800},
    'HDB': {'casa_pct': 12.4, 'total_assets_ty': 1_040_000, 'lntt_6m_ty': 13202},
    'ACB': {'casa_pct': 20.52, 'total_assets_ty': 1_070_000, 'lntt_6m_ty': 10700},
    'STB': {'casa_pct': 16.58, 'total_assets_ty': 917_120, 'lntt_6m_ty': 1950},
    'LPB': {'casa_pct': 6.37, 'total_assets_ty': 615_502, 'lntt_6m_ty': 5973},
    'SHB': {'casa_pct': 8.4, 'total_assets_ty': 892_571, 'lntt_6m_ty': 9000},
    'SSB': {'casa_pct': 15.4, 'total_assets_ty': 396_443},
    'VIB': {'casa_pct': 11.89, 'total_assets_ty': 580_000, 'lntt_6m_ty': 5180},
    'EIB': {'casa_pct': 14.07, 'total_assets_ty': 273_270, 'lntt_6m_ty': 730},
}


_CORP_FINANCIAL_V37 = {
    'VHM': {'lnst_2024_ty': 35100, 'lnst_2025_ty': 42111},
    'GAS': {'lnst_2025_ty': 14359},
    'HPG': {'lnst_2024_ty': 13670, 'lnst_2025_ty': 18041},
    'VNM': {'lnst_2025_ty': 11650},
}

_LEGACY_PE_V37 = {
    'VIC': 76.2, 'VHM': 5.9, 'GAS': 14.5, 'MCH': 26.1, 'HPG': 7.7,
    'VPL': 47.8, 'BSR': 7.2, 'GVR': 18.2, 'VNM': 11.0, 'MWG': 11.2,
    'FPT': 10.8, 'MSN': 15.2, 'VJC': 45.0, 'CTR': 13.6, 'FRT': 22.3,
    'PVI': 12.7,
}


_DIVIDEND_DETAIL = {
    'VRE': {
        'dividend_cash_vnd': 1000.0, 'dividend_stock_pct': 22.5,
        'dividend_ex_date': '2026-10-28',
        'dividend_note': '1.000đ tiền mặt (~3,95%) + thưởng cổ phiếu 22,5%; chốt quyền 28/10/2026',
    },
    'GEE': {
        'dividend_cash_per_event_vnd': 500.0, 'dividend_is_approx': True,
        'dividend_note': '500đ mỗi lần, khoảng 4,5%/năm (chia nhiều đợt); số năm là ước tính',
    },
    'REE': {
        'dividend_cash_vnd': 1000.0, 'dividend_stock_pct': 15.0,
        'dividend_yield_is_derived': True,
        'dividend_note': '1.000đ tiền mặt + 15% cổ phiếu (cổ tức 2025); '
                         'tiền mặt tương đương 2,17% tại giá 46.000đ',
    },
    'POW': {
        'dividend_cash_vnd': 0.0, 'dividend_stock_pct': 4.0,
        'dividend_bonus_pct': 15.0, 'dividend_rights_pct': 12.0,
        'dividend_rights_price_vnd': 10000.0, 'dividend_ex_date': '2025-12-11',
        'dividend_is_zero_confirmed': True,
        'dividend_note': 'Không chia tiền mặt năm 2025 (năm thứ 5 liên tiếp). '
                         'Chỉ chia cổ phiếu: 4% (chốt 11/12/2025) + thưởng 15% '
                         '+ chào bán 12% giá 10.000đ. Định hướng đến 2030: chia cổ phiếu 1-2 lần.',
    },
    'FPT': {
        'dividend_cash_vnd': 2000.0, 'dividend_stock_pct': 10.0,
        'dividend_ex_date': '2026-05-28',
        'dividend_note': 'Cổ tức 2025: 2.000đ/cp (3,48% tại 57.400đ); '
                         'thưởng 10:1 đã thực hiện 28/05/2026',
    },
    'CTR': {
        'dividend_cash_vnd': 2150.0, 'dividend_yield_reported_pct': 2.2,
        'dividend_note': '2.150đ/cp (cổ tức 2024). Bảng gốc ghi ~2,2%; '
                         'tại giá 69.300đ, 2.150đ tương đương 3,10% -> CẦN ĐỐI CHIẾU.',
    },
    'MBB': {
        'dividend_cash_vnd': 1000.0, 'dividend_stock_pct': 15.0,
        'dividend_rights_ratio': '10:1', 'dividend_ex_date': '2026-07-09',
        'shares_is_provisional': True,
        'dividend_note': '1.000đ tiền mặt (09/07/2026) + 15% cổ phiếu + quyền mua 10:1. '
                         'SLCP thực tế có thể cao hơn 10.069 triệu.',
    },
    'TCB': {'dividend_note': 'Không chia cổ tức năm 2026; tỷ suất 2,05% là TTM.'},
    'SHB': {'dividend_note': 'Dự kiến 6% tiền mặt 11/2026 + 10% cổ phiếu.'},
    'GMD': {'dividend_note': '2,84% tính TRƯỚC thưởng cổ phiếu 2:1; SLCP ~649tr là SAU thưởng.'},
    'KSV': {'dividend_note': 'Khoảng 3,6%; giá 12/10 chưa xác nhận 22/10.'},
    'VPL': {'dividend_note': 'Không có cổ tức trong 12 tháng.'},
    'VJC': {'dividend_note': 'Không có cổ tức trong 12 tháng.'},
    'VIC': {'dividend_note': 'Không có cổ tức.'},
    'MSN': {'dividend_note': 'Không có cổ tức.'},
    'FRT': {'dividend_note': 'Không có cổ tức; giá 29/9.'},
    'CMG': {'dividend_note': 'Chưa có số cổ tức.'},
}


LATEST_FINANCIAL_SUPPLEMENT = {
    'REE': {
        'lnst_2024_ty': 2404.0,
        'lnst_2024_is_approx': True,
        'lnst_2025_ty': 3149.0,
        'lnst_6t2026_ty': 1720.0,
        'profit_ty': 1720.0,
        'lnst_q1_2026_ty': 938.7,
        'lnst_q2_2026_ty': 781.3,
        'plan_lnst_me_2026_ty': 2814.0,
        'eps_ttm_vnd': 4237.0,
        'pe': 10.9,
        'financial_as_of': '2026-10-23',
        'financial_note': 'LNST HỢP NHẤT. Q3/2026 CHƯA công bố. '
                          'Kế hoạch cả năm 2.814 tỷ là CÔNG TY MẸ (không đồng nhất hợp nhất). '
                          'P/E 10,9 dùng EPS TTM 4.237đ, không phải EPS FY2025.',
    },
    'FPT': {
        'lnst_2024_ty': 9427.0,
        'lnst_me_2024_ty': 7857.0,
        'lntt_2024_ty': 11070.0,
        'lnst_2025_ty': 11226.0,
        'lnst_me_2025_ty': 9370.0,
        'lntt_2025_ty': 13039.0,
        'lnst_9t2026_me_ty': 7778.0,
        'lntt_9t2026_ty': 8770.0,
        'eps_9t2026_vnd': 4142.0,
        'plan_lntt_2026_ty': 10875.0,
        'growth_lnst_me_9t2026_pct': 13.3,
        'growth_lntt_9t2026_pct': 17.0,
        'financial_as_of': '2026-10-23',
        'financial_note': 'TỪ 2026 FPT hợp nhất FPT Telecom theo PHƯƠNG PHÁP VỐN CHỦ SỞ HỮU '
                          '-> số 2026 KHÔNG SO SÁNH TRỰC TIẾP với 2024-2025. '
                          'v54 đã tách rõ LNST hợp nhất / LNST mẹ / LNTT.',
    },
    'BSR': {
        'lnst_2024_ty': 590.0,
        'lnst_2024_is_approx': True,
        'lnst_9m2024_ty': 674.0,
        'lnst_q4_2024_ty': -83.4,
        'lnst_2025_ty': 5217.0,
        'lnst_q1_2026_ty': 3347.0,
        'plan_lnst_2026_ty': 2162.0,
        'financial_as_of': '2026-10-23',
        'financial_note': 'Q1/2026 LNST 3.347 tỷ ĐÃ VƯỢT kế hoạch cả năm 2026 (2.162 tỷ). '
                          'LNST 2024 ~590 tỷ là số SUY RA từ 9T/2024 và lỗ Q4.',
    },
    'CTG': {
        'lntt_2025_ty': 43400.0,
        'lnst_2025_ty': 34600.0,
        'lnst_6t2026_ty': 20657.0,
        'lnst_2024_ty': 25300.0,
        'lnst_2024_is_approx': True,
        'financial_as_of': '2026-10-22',
        'financial_note': 'BCTC hợp nhất 2025: LNTT 43.400 tỷ; LNST mẹ 34.600 tỷ; '
                          'LNST mẹ 6T/2026 20.657 tỷ.',
    },
}


def _build_latest_market_snapshot():
    out = {}
    for row in _SNAPSHOT_ROWS:
        t, price, cap, sh_mn, dy, official, pdate, note = row
        t = str(t).upper()

        shares = float(sh_mn) * 1e6 if sh_mn else 0.0
        stale_days = _days_between(pdate) if pdate else 999

        d = {
            'price_vnd': float(price),
            'market_cap_ty': float(cap),
            'shares': shares,
            'dividend_yield_pct': float(dy),

            'price_as_of': pdate,
            'price_is_stale': bool(pdate and stale_days > 0),
            'price_is_materially_stale': bool(stale_days >= MATERIALLY_STALE_DAYS),
            'price_stale_days': int(stale_days),
            'price_is_missing': not bool(price),

            'shares_as_of': pdate,
            'shares_is_official': bool(official),
            'shares_is_estimated': not bool(official),
            'shares_basis': (
                'official_registry' if official
                else ('reported_unverified' if t in _SNAPSHOT_BANK_SET
                      else 'estimated_market_cap_div_price')
            ),
            'shares_is_provisional': False,

            'snapshot_as_of': SNAPSHOT_PRICE_DATE,
            'snapshot_build_date': SNAPSHOT_BUILD_DATE,
            'snapshot_source': SNAPSHOT_SOURCE,
            'note': note,
        }

        d.update(_BANK_STRUCTURE_V37.get(t, {}))
        d.update(_CORP_FINANCIAL_V37.get(t, {}))
        if t in _LEGACY_PE_V37:
            d['pe_legacy_v37'] = float(_LEGACY_PE_V37[t])
        d.update(_DIVIDEND_DETAIL.get(t, {}))

        if d.get('dividend_stock_pct') and t == 'MBB':
            d['shares_is_provisional'] = True

        out[t] = d
    return out


LATEST_MARKET_SNAPSHOT = _build_latest_market_snapshot()


REFERENCE_ONLY_MARKET_SNAPSHOT = {
    'CVT': {
        'price_vnd': 26800.0,
        'shares': 36_690_000.0,
        'market_cap_ty': round(26800.0 * 36_690_000.0 / 1e9, 3),
        'price_as_of': '2026-10-08',
        'price_stale_days': _days_between('2026-10-08'),
        'shares_is_official': True,
        'shares_basis': 'official_registry',
        'note': 'Công ty CP CMC (vật liệu xây dựng), KHÁC CMG (Tập đoàn Công nghệ CMC). '
                'Giá 08/10/2026 — REFERENCE ONLY, không vào universe 41 mã.',
        'snapshot_source': SNAPSHOT_SOURCE,
    },
}


def _snap_for(ticker):
    t = _canonical_ticker(ticker)
    return LATEST_MARKET_SNAPSHOT.get(t, {})


# ============================================================================
# [v36-CSV] PATH RESOLUTION — GIỮ NGUYÊN
# ============================================================================
def _resolve_csv_db_paths():
    _HERE = os.path.dirname(os.path.abspath(__file__))
    _PARENT = os.path.dirname(_HERE)
    _GP = os.path.dirname(_PARENT)
    _filenames = _CSV_FILENAMES
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
    print("[v54-CSV] 🔍 TÌM 3 FILE CSV (ƯU TIÊN TUYỆT ĐỐI)")
    print("=" * 78)
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
        if not found:
            cand = _DEFAULT_CSV_PATHS.get(key)
            if cand and os.path.isfile(cand) and os.path.getsize(cand) > 0:
                found = os.path.abspath(cand)
        result[key] = found
        if found:
            print(f"   ✅ {key:<28} {found}  ({os.path.getsize(found)/1024:.1f} KB)")
        else:
            print(f"   ❌ {key:<28} KHÔNG TÌM THẤY")
    print(f"\n   📊 {sum(1 for v in result.values() if v)}/3 file CSV tìm thấy")
    print("=" * 78 + "\n")
    return result


_CSV_DB_PATHS = _resolve_csv_db_paths()
_SQLITE_DB_PATHS = _CSV_DB_PATHS


# ============================================================================
# [v36-CSV] FALLBACK CSV PATHS — GIỮ NGUYÊN
# ============================================================================
_FALLBACK_CSV_NAMES = [
    "vn30_41_fin_long.csv", "du_lieu/vn30_41_fin_long.csv",
    "vn30_fin_long.csv", "du_lieu/vn30_fin_long.csv",
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
# [v36.1] WIDE FORMAT DETECTORS — GIỮ NGUYÊN 100%
# ============================================================================
_PERIOD_PATTERN = re.compile(r'^(?:19|20)\d{2}(?:Q[1-4]|H[12])?$', re.IGNORECASE)

_METRIC_COL_RAW = {
    'cột 1', 'cột1', 'cot 1', 'cot1',
    'chỉ tiêu', 'chi tiêu', 'chỉ_tiêu', 'chi_tiêu',
    'unnamed: 0', 'unnamed:0', 'unnamed 0', 'unnamed_0', 'unnamed0',
    'metric', 'metric_name', 'chi_tieu', 'chi_tieu_ten',
}
_METRIC_COL_NORM = {
    'cột_1', 'cot_1', 'chỉ_tiêu', 'chi_tieu',
    'unnamed_0', 'unnamed0', 'metric', 'metric_name', 'chi_tieu_ten',
}


def _normalize_colname(name):
    if name is None:
        return ''
    s = str(name).strip().lower()
    s = re.sub(r'[\s\-\.\,\(\)\[\]\{\}]+', '_', s)
    s = re.sub(r'_+', '_', s).strip('_')
    return s


def _is_period_column(col_name):
    if col_name is None:
        return False
    s = str(col_name).strip()
    if not s:
        return False
    s = s.replace(' ', '').replace('_', '').upper()
    return bool(_PERIOD_PATTERN.match(s))


def _is_metric_column(col_name):
    if col_name is None:
        return False
    s = str(col_name).strip().lower()
    if s in _METRIC_COL_RAW:
        return True
    return _normalize_colname(s) in _METRIC_COL_NORM


def _wide_df_to_long(df):
    empty = pd.DataFrame(columns=['ticker', 'metric_name', 'period', 'value'])
    if df is None or df.empty:
        return empty
    cols = [str(c).strip() for c in df.columns]
    df = df.copy()
    df.columns = cols
    ticker_col = None
    for cand in ('ticker', 'Ticker', 'TICKER', 'ma', 'Mã', 'symbol', 'Mã CP', 'mã'):
        if cand in cols:
            ticker_col = cand
            break
    if ticker_col is None and cols:
        ticker_col = cols[0]
    metric_cols = [c for c in cols if _is_metric_column(c)]
    period_cols = [c for c in cols if _is_period_column(c)]
    if not period_cols:
        print(f"[v54-WIDE] ⚠️ Không có cột kỳ nào. Cols: {cols}")
        return empty
    df[ticker_col] = df[ticker_col].astype(str).str.strip().str.upper()
    df[ticker_col] = df[ticker_col].replace({'': None, 'NAN': None, 'NONE': None, 'nan': None})
    df[ticker_col] = df[ticker_col].ffill()
    df = df[df[ticker_col].notna() & (df[ticker_col] != '')].copy()
    records = []
    for _, row in df.iterrows():
        ticker = str(row[ticker_col]).strip().upper()
        if not ticker or ticker in ('NAN', 'NONE'):
            continue
        metric_name = ''
        for mc in metric_cols:
            val = row.get(mc)
            if pd.isna(val):
                continue
            s = str(val).strip()
            if not s or s.lower() in ('na', 'n/a', 'none', 'nan', '-', '--', '—'):
                continue
            metric_name = s
            break
        if not metric_name:
            continue
        for pc in period_cols:
            val = row.get(pc)
            if pd.isna(val):
                continue
            if isinstance(val, str) and not val.strip():
                continue
            try:
                parsed = _parse_vn_number(val)
            except Exception:
                continue
            if not np.isfinite(parsed):
                continue
            records.append({'ticker': ticker, 'metric_name': metric_name.lower().strip(),
                            'period': str(pc).strip(), 'value': parsed})
    if not records:
        return empty
    out = pd.DataFrame(records)
    out = out.drop_duplicates(subset=['ticker', 'metric_name', 'period'], keep='last')
    return out.reset_index(drop=True)


# ============================================================================
# [v33-FIX-1] UNIT DETECTION — GIỮ NGUYÊN 100%
# ============================================================================
_UNIT_FACTOR_BY_NAME = {
    'vnd': 1e-9, 'dong': 1e-9, 'nghin': 1e-6, 'ngan': 1e-6,
    'trieu': 1e-3, 'trd': 1e-3, 'ty': 1.0, 'ti': 1.0,
}


def _detect_unit_from_colname(col_name):
    if not col_name:
        return None
    cl = str(col_name).lower()
    for token, factor in _UNIT_FACTOR_BY_NAME.items():
        if re.search(rf'(?:^|_){token}(?:_|$)', cl):
            return factor
    return None


def _detect_money_unit_fallback(value):
    try:
        v = abs(float(value))
    except (TypeError, ValueError):
        return 1.0
    if v == 0 or not np.isfinite(v):
        return 1.0
    if v >= 1e15: return 1e-9
    if v >= 1e12: return 1e-6
    if v >= 1e9:  return 1e-3
    return 1.0


def _to_ty(value, col_name=None):
    try:
        v = float(value)
    except (TypeError, ValueError):
        return 0.0
    if v == 0 or not np.isfinite(v):
        return 0.0
    factor = _detect_unit_from_colname(col_name)
    if factor is None:
        factor = _detect_money_unit_fallback(v)
    return v * factor


def _to_vnd(value, col_name=None):
    return _to_ty(value, col_name) * 1e9


# ============================================================================
# [v53-FIX-1] ALIAS MAP — GIỮ NGUYÊN THỨ TỰ
# ============================================================================
_METRIC_ALIASES = {
    'price': ['gia_thi_truong', 'gia_co_phieu', 'gia_co_phieu_vnd',
              'gia_hien_tai', 'gia_hientai', 'price', 'close', 'cp_hientai',
              'gia_dong_cua', 'gia', 'giá'],
    'shares': ['so_co_phieu', 'so_cp_luu_hanh', 'so_luong_cp_luu_hanh',
               'cp_hientai', 'shares', 'shares_outstanding', 'klcp_luu_hanh',
               'khoi_luong_cp_luu_hanh'],
    'total_assets': ['tong_tai_san', 'tong_tai_san_co', 'tong_tai_san_trd',
                     'total_assets', '19_bs_tong_tai_san_co', 'tongtai_san'],
    'equity': ['von_chu_so_huu', 'von_chu_so_huu_trd', 'von_csh',
               'equity', '37_bs_tong_von_chu_so_huu', 'vonchusohuu',
               'von_chu_so_huu_ty'],
    'profit_6t': ['lnst_6t2026', 'lnst_6t_2026', 'loi_nhuan_sau_thue_6t',
                  'loi_nhuan_sau_thue', 'profit_6t', 'lnst_6thang',
                  '58_is_loi_nhuan_sau_thue'],
    'lntt_6t': ['lntt_6t2026', 'lntt_6t_2026', 'loi_nhuan_truoc_thue_6t',
                'loi_nhuan_truoc_thue', 'lntt_6thang', 'profit_before_tax'],
    'revenue': ['thu_nhap_lai_thuan', 'doanh_thu_thuan', 'doanh_thu',
                'revenue', 'toi', 'nii', '38_is_thu_nhap_lai'],
    'market_cap': ['von_hoa_ty', 'von_hoa', 'market_cap', 'von_hoa_ty_vnd',
                   'von_hoa_hien_tai', 'vonhoa'],
    'eps': ['eps', 'eps_vnd', 'eps_co_phieu', '61_is_eps_vndco_phieu',
            'earnings_per_share', 'eps_ttm'],
    'bvps': ['bvps', 'bvps_vnd', 'bvps_huu_tinh', 'gd_book_value_ty_vndcp',
             'book_value_per_share', 'bvps_co_phieu'],
    'pe': ['pe', 'pe_ttm', 'p_e', 'pe_ratio'],
    'pb': ['pb', 'p_b', 'pb_ratio'],
    'roe': ['roe', 'roe_pct', 'roe_ttm', 'return_on_equity', 'roe_%'],
    'roa': ['roa', 'roa_pct', 'roa_ttm', 'return_on_assets', 'roa_%'],
    'casa': ['casa', 'casa_pct', 'ty_le_casa', 'casa_%'],
    'dividend': ['co_tuc_cp', 'co_tuc', 'co_tuc_vnd', 'dividend', 'dps',
                 'co_tuc_bang_tien', 'dividend_per_share'],
    'growth_lnst': ['tang_truong_loi_nhuan', 'tang_truong_lnst', 'growth',
                    'growth_lnst_pct', 'tang_truong_lnst_pct'],
    'lnst_2024': ['lnst_2024', 'lnst_nam_2024', 'profit_2024', 'lnst_2024_ty',
                  'loi_nhuan_sau_thue_2024'],
    'lnst_2025': ['lnst_2025', 'lnst_nam_2025', 'profit_2025', 'lnst_2025_ty',
                  'loi_nhuan_sau_thue_2025'],
    'lnst_me_2025': ['lnst_me_2025_ty', 'lnst_cong_ty_me_2025',
                     'loi_nhuan_csh_2025', 'lnst_me_2025'],
    'lntt_2025': ['lntt_2025_ty', 'lntt_2025', 'loi_nhuan_truoc_thue_2025'],
}


def _find_col_strict(df, aliases):
    if df is None or df.empty:
        return None
    cols = list(df.columns)
    cols_norm = [_normalize_colname(c) for c in cols]
    for alias in aliases:
        a = _normalize_colname(alias)
        for i, c_norm in enumerate(cols_norm):
            if c_norm == a:
                return cols[i]
    for alias in aliases:
        a = _normalize_colname(alias)
        if len(a) < 4:
            continue
        a_tokens = set(a.split('_'))
        for i, c_norm in enumerate(cols_norm):
            if a in c_norm or c_norm in a:
                c_tokens = set(c_norm.split('_'))
                period_alias = a_tokens & {'2024', '2025', '2026', '6t', '6t2026', 'nam', 'quy'}
                period_col = c_tokens & {'2024', '2025', '2026', '6t', '6t2026', 'nam', 'quy'}
                if period_alias and period_col and period_alias != period_col:
                    continue
                return cols[i]
    best, best_score = None, 0
    for alias in aliases:
        a = _normalize_colname(alias)
        if len(a) < 4:
            continue
        for i, c_norm in enumerate(cols_norm):
            score = fuzz.WRatio(a, c_norm)
            if score > best_score:
                best_score, best = score, cols[i]
    return best if best_score >= 92 else None


def _get_val_strict(row, df, metric_key):
    aliases = _METRIC_ALIASES.get(metric_key, [])
    if not aliases:
        return 0.0, None
    col = _find_col_strict(df, aliases)
    if col is None:
        return 0.0, None
    v = _parse_vn_number(row.get(col, 0))
    return v, col


# ============================================================================
# ĐỌC CSV ĐA ENCODING — GIỮ NGUYÊN 100%
# ============================================================================
def _read_csv_multiencoding(file_path):
    try:
        with open(file_path, 'rb') as f:
            magic = f.read(8)
        if magic[:4] == b'PK\x03\x04':
            return pd.read_excel(file_path)
        if magic[:4] == b'\xd0\xcf\x11\xe0':
            return pd.read_excel(file_path)
    except Exception:
        pass
    try:
        with open(file_path, 'rb') as f:
            raw_bytes = f.read()
    except Exception as e:
        raise RuntimeError(f"Không mở được file {file_path}: {e}")
    if not raw_bytes:
        raise RuntimeError(f"File rỗng: {file_path}")
    if raw_bytes.startswith(b'SQLite format 3'):
        raise RuntimeError(
            f"❌ FILE '{os.path.basename(file_path)}' LÀ BINARY SQLITE!\n"
            f"   Bạn chỉ rename .db → .csv nhưng nội dung vẫn là SQLite.\n"
            f"   Fix: chạy script convert SQLite → CSV thật sự."
        )
    if raw_bytes.startswith(b'\xef\xbb\xbf'):
        try:
            text = raw_bytes.decode('utf-8-sig')
            return pd.read_csv(io.StringIO(text))
        except Exception:
            pass
    encodings = ['utf-8', 'cp1252', 'windows-1252', 'cp1258', 'latin-1',
                 'iso-8859-1', 'cp936', 'gbk', 'gb2312', 'big5', 'cp950',
                 'shift_jis', 'cp932', 'euc-kr', 'cp949', 'cp1251', 'koi8-r',
                 'cp1250', 'cp1254', 'cp1256', 'cp874']
    first_fallback = None
    for enc in encodings:
        try:
            text = raw_bytes.decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue
        has_replacement = '\ufffd' in text
        try:
            df = pd.read_csv(io.StringIO(text))
        except Exception:
            continue
        if not has_replacement:
            return df
        elif first_fallback is None:
            first_fallback = df
    if first_fallback is not None:
        return first_fallback
    text = raw_bytes.decode('utf-8', errors='replace')
    for attempt in [
        lambda: pd.read_csv(io.StringIO(text)),
        lambda: pd.read_csv(io.StringIO(text), engine='python', sep=None, on_bad_lines='skip'),
    ]:
        try:
            return attempt()
        except Exception:
            continue
    raise RuntimeError(f"Đọc CSV thất bại: {file_path}")


# ============================================================================
# 3 NHÓM NGÀNH — GIỮ NGUYÊN
# ============================================================================
BANK_DATA_LATEST = {}
CORP_DATA_LATEST = {}
CORP_TICKERS = set()


def get_latest_bank_data(ticker):
    t = _canonical_ticker(ticker)
    if t in CORP_DATA_LATEST:
        return CORP_DATA_LATEST[t].copy()
    return BANK_DATA_LATEST.get(t, {}).copy()


def get_bank_fallback(ticker, metric, default=0):
    t = _canonical_ticker(ticker)
    metric_map = {'price': 'price_vnd', 'eps': 'eps_ttm_vnd', 'bvps': 'bvps_vnd',
                  'roe': 'roe_pct', 'roa': 'roa_pct', 'pe': 'pe_ttm', 'pb': 'pb',
                  'dividend': 'dividend_vnd', 'shares': 'shares'}
    if t in CORP_DATA_LATEST:
        d = CORP_DATA_LATEST[t]
        if metric in metric_map and metric_map[metric] in d:
            return d[metric_map[metric]]
        return default
    latest = BANK_DATA_LATEST.get(t, {})
    if metric in metric_map and metric_map[metric] in latest:
        return latest[metric_map[metric]]
    return default


def is_corp_ticker(ticker):
    return _canonical_ticker(ticker) in CORP_TICKERS


def get_corp_latest_data(ticker):
    return CORP_DATA_LATEST.get(_canonical_ticker(ticker), {}).copy()


# ============================================================================
# CONSTANTS — GIỮ NGUYÊN
# ============================================================================
GARBAGE_VALUES = {87.0, -87.0, 87, -87}
SUSPICIOUS_COL_IDS = {'87', '88', '89', '90', '91', '92', '93', '94'}
MIN_REAL_PRICE = 1_000
MIN_REAL_BVPS = 1_000
MIN_REAL_EPS = 100
MIN_REAL_DIVIDEND = 100
MIN_REAL_SHARES = 100_000
ROA_MIN_PCT, ROA_MAX_PCT = 0.1, 5.0
ROE_MIN_PCT, ROE_MAX_PCT = 3.0, 40.0
PE_MIN, PE_MAX = 1.0, 100.0
PB_MIN, PB_MAX = 0.1, 15.0


# ============================================================================
# PARSER SỐ VN/US — GIỮ NGUYÊN 100%
# ============================================================================
def _parse_vn_number(value):
    if value is None:
        return 0.0
    if isinstance(value, (int, float, np.integer, np.floating)):
        try:
            v = float(value)
            return 0.0 if (isinstance(v, float) and np.isnan(v)) else v
        except Exception:
            return 0.0
    if not isinstance(value, str):
        return 0.0
    s = value.strip()
    if s == '' or s.lower() in ['na', 'n/a', 'none', 'nan', 'null', '-', '--', '—']:
        return 0.0
    s = re.sub(r'[^\d,.\-]', '', s)
    if s == '' or s == '-':
        return 0.0
    is_neg = s.startswith('-')
    if is_neg:
        s = s[1:]
    has_dot = '.' in s
    has_comma = ',' in s
    try:
        if has_dot and has_comma:
            last_dot, last_comma = s.rfind('.'), s.rfind(',')
            if last_comma > last_dot:
                int_part = s[:last_comma].replace('.', '').replace(',', '')
                dec_part = s[last_comma + 1:]
                normalized = int_part + '.' + dec_part
            else:
                int_part = s[:last_dot].replace(',', '')
                dec_part = s[last_dot + 1:]
                normalized = int_part + '.' + dec_part
        elif has_comma:
            parts = s.split(',')
            last = parts[-1]
            if len(parts) >= 2 and len(last) <= 2 and last.isdigit():
                normalized = ''.join(parts[:-1]) + '.' + last
            else:
                normalized = s.replace(',', '')
        elif has_dot:
            if s.count('.') > 1:
                normalized = s.replace('.', '')
            else:
                parts = s.split('.')
                if len(parts) == 2 and len(parts[1]) == 3 and parts[1].isdigit() and parts[0].isdigit():
                    normalized = parts[0] + parts[1]
                else:
                    normalized = s
        else:
            normalized = s
        v = float(normalized)
        return -v if is_neg else v
    except Exception:
        return 0.0


def clean_numeric(value):
    return _parse_vn_number(value)


# ============================================================================
# HELPERS — GIỮ NGUYÊN 100%
# ============================================================================
def fix_duplicate_columns(df):
    if df.empty:
        return df
    cols = pd.Series(df.columns)
    for dup in cols[cols.duplicated()].unique():
        dup_indices = cols[cols == dup].index.values.tolist()
        for idx_pos, col_idx in enumerate(dup_indices):
            if idx_pos > 0:
                cols[col_idx] = f"{dup}_{idx_pos}"
    df.columns = cols
    return df


def _is_garbage(v):
    try:
        return float(v) in GARBAGE_VALUES
    except Exception:
        return False


def is_suspicious_column(col_name):
    if col_name is None:
        return False
    s = str(col_name).strip().lower()
    m = re.match(r'^(\d+)[\s_\-\.]', s)
    return bool(m and m.group(1) in SUSPICIOUS_COL_IDS)


def fix_price(p):
    try:
        p = float(p)
    except Exception:
        return 0.0
    if p <= 0 or _is_garbage(p):
        return 0.0
    if p < MIN_REAL_PRICE:
        p = p * 1000
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
    if b <= 0 or _is_garbage(b):
        return 0.0
    if b < MIN_REAL_BVPS:
        b = b * 1000
    if b < MIN_REAL_BVPS:
        return 0.0
    return round(b, 0)


def fix_eps(e, profit=0, shares=0):
    if profit and profit > 0 and shares and shares > 0:
        calc = profit / shares
        if MIN_REAL_EPS <= calc <= 1_000_000:
            return round(calc, 0)
    try:
        e = float(e)
    except Exception:
        return 0.0
    if e <= 0 or _is_garbage(e):
        return 0.0
    if 0 < e < MIN_REAL_EPS:
        e = e * 1000
    if e < MIN_REAL_EPS:
        return 0.0
    return round(e, 0)


def fix_dividend(d):
    try:
        d = float(d)
    except Exception:
        return 0.0
    if d <= 0 or _is_garbage(d):
        return 0.0
    if d < MIN_REAL_DIVIDEND:
        d = d * 1000
    if d < MIN_REAL_DIVIDEND:
        return 0.0
    return round(d, 0)


def fix_shares(s):
    try:
        s = float(s)
    except Exception:
        return 0.0
    if s <= 0 or _is_garbage(s):
        return 0.0
    if s < 1_000_000:
        s = s * 1000
    if s < MIN_REAL_SHARES:
        return 0.0
    return round(s, 0)


# ============================================================================
# [v54] MARKET TRIPLET RECONCILIATION
# ============================================================================
def _reconcile_market_triplet(data):
    p = float(data.get('price_vnd', 0) or 0)
    c = float(data.get('market_cap_ty', 0) or 0)
    s = float(data.get('shares', 0) or 0)
    if p <= 0 or c <= 0 or s <= 0:
        return data
    implied_cap = p * s / 1e9
    diff = abs(implied_cap - c) / c
    if diff <= CAP_SHARES_TOL:
        return data

    warnings = data.setdefault('_data_quality_warnings', [])
    if data.get('shares_is_official'):
        data['_market_cap_reported_ty'] = c
        data['market_cap_ty'] = round(implied_cap, 3)
        data['market_cap'] = implied_cap * 1e9
        data['_market_cap_reconciled'] = True
        warnings.append(
            f"MARKET_CAP_RECONCILED: reported={c:,.0f} tỷ vs price×official_shares="
            f"{implied_cap:,.0f} tỷ (lệch {diff*100:.2f}%)"
        )
    else:
        implied_shares = c * 1e9 / p
        data['_shares_reported'] = s
        data['shares'] = round(implied_shares, 0)
        data['_shares_reconciled'] = True
        data['shares_basis'] = 'estimated_market_cap_div_price'
        data['shares_is_estimated'] = True
        warnings.append(
            f"SHARES_RECONCILED: reported={s:,.0f} vs cap/price={implied_shares:,.0f} "
            f"(lệch {diff*100:.2f}%) — SLCP là ƯỚC TÍNH"
        )
    return data


_FINANCIAL_SNAPSHOT_KEYS = (
    'total_assets_ty',
    'lntt_6m_ty', 'lntt_2024_ty', 'lntt_2025_ty',
    'lnst_2024_ty', 'lnst_2025_ty', 'lnst_6t2026_ty',
    'lnst_me_2024_ty', 'lnst_me_2025_ty',
    'lnst_9t2026_me_ty', 'lntt_9t2026_ty',
    'lnst_q1_2026_ty', 'lnst_q2_2026_ty',
    'lnst_9m2024_ty', 'lnst_q4_2024_ty',
    'plan_lnst_2026_ty', 'plan_lntt_2026_ty', 'plan_lnst_me_2026_ty',
    'roe_pct', 'roa_pct',
)

_FINANCIAL_SIGNED_KEYS = {
    'profit_ty', 'lntt_6m_ty', 'lntt_2024_ty', 'lntt_2025_ty',
    'lnst_2024_ty', 'lnst_2025_ty', 'lnst_6t2026_ty',
    'lnst_me_2024_ty', 'lnst_me_2025_ty',
    'lnst_9t2026_me_ty', 'lntt_9t2026_ty',
    'lnst_q1_2026_ty', 'lnst_q2_2026_ty',
    'lnst_9m2024_ty', 'lnst_q4_2024_ty',
    'nii_ty', 'toi_ty',
}

_SNAPSHOT_META_KEYS = (
    'price_as_of', 'price_is_stale', 'price_is_materially_stale',
    'price_stale_days', 'price_is_missing',
    'shares_as_of', 'shares_is_official', 'shares_is_estimated',
    'shares_basis', 'shares_is_provisional',
    'dividend_cash_vnd', 'dividend_cash_per_event_vnd', 'dividend_stock_pct',
    'dividend_bonus_pct', 'dividend_rights_pct', 'dividend_rights_price_vnd',
    'dividend_rights_ratio', 'dividend_ex_date', 'dividend_note',
    'dividend_is_approx', 'dividend_is_zero_confirmed',
    'dividend_yield_reported_pct', 'dividend_yield_is_derived',
    'financial_as_of', 'financial_note',
    'snapshot_as_of', 'snapshot_build_date', 'snapshot_source',
    'pe_legacy_v37',
)

_KEY_RENAME_IN = {'roe_pct': 'roe', 'roa_pct': 'roa'}


def _apply_latest_market_snapshot(ticker, data, prioritize_csv_financials=True):
    if not isinstance(data, dict):
        return data
    t = _canonical_ticker(ticker)
    snap = _snap_for(t)
    if not snap:
        return data

    for k in _SNAPSHOT_META_KEYS:
        if k in snap and snap[k] is not None:
            if k not in data or k.startswith('_'):
                data[k] = snap[k]

    if snap.get('price_vnd'):
        data['price_vnd'] = float(snap['price_vnd'])
        data['gia_hien_tai'] = float(snap['price_vnd'])
    if snap.get('market_cap_ty'):
        data['market_cap_ty'] = float(snap['market_cap_ty'])
        data['market_cap'] = float(snap['market_cap_ty']) * 1e9
    if snap.get('shares'):
        data['shares'] = float(snap['shares'])

    _reconcile_market_triplet(data)

    cash = snap.get('dividend_cash_vnd')
    if cash is not None and float(cash) > 0:
        data['dividend_vnd'] = round(float(cash), 0)
        data['co_tuc_cp'] = data['dividend_vnd']
        data['_dividend_source'] = 'EXPLICIT_CASH'
        if snap.get('price_vnd'):
            implied_dy = float(cash) / float(snap['price_vnd']) * 100.0
            reported_dy = snap.get('dividend_yield_pct')
            if reported_dy is not None and abs(implied_dy - float(reported_dy)) > 0.5:
                data.setdefault('_data_quality_warnings', []).append(
                    f"DIVIDEND_YIELD_MISMATCH: cash={cash:,.0f}đ tại giá "
                    f"{snap['price_vnd']:,.0f}đ => {implied_dy:.2f}% "
                    f"nhưng bảng gốc ghi {reported_dy}%"
                )
    elif snap.get('dividend_yield_pct') is not None and float(snap['dividend_yield_pct']) > 0:
        dy = float(snap['dividend_yield_pct'])
        if data.get('price_vnd', 0) > 0:
            data['dividend_vnd'] = round(dy / 100.0 * data['price_vnd'], 0)
            data['co_tuc_cp'] = data['dividend_vnd']
            data['_dividend_source'] = 'YIELD_DERIVED'

    if snap.get('dividend_yield_pct') is not None:
        data['dividend_yield_pct'] = float(snap['dividend_yield_pct'])
        data['ty_le_co_tuc'] = float(snap['dividend_yield_pct'])

    if snap.get('casa_pct') is not None:
        data['casa_pct'] = float(snap['casa_pct'])

    def _has_valid(key, min_val=0):
        v = data.get(key, 0)
        if not isinstance(v, (int, float, np.integer, np.floating)):
            return False
        try:
            if not np.isfinite(float(v)):
                return False
        except Exception:
            return False
        if key in _FINANCIAL_SIGNED_KEYS:
            return float(v) != 0.0
        return float(v) > min_val

    def _should_override(key):
        if not prioritize_csv_financials:
            return True
        return not _has_valid(key)

    fin_snap = dict(snap)
    supp = LATEST_FINANCIAL_SUPPLEMENT.get(t, {}) if prioritize_csv_financials else {}
    for k, v in supp.items():
        if k in _FINANCIAL_SNAPSHOT_KEYS and isinstance(v, (int, float, np.number)):
            if np.isfinite(float(v)):
                fin_snap[k] = float(v)

    for src_key in _FINANCIAL_SNAPSHOT_KEYS:
        v = fin_snap.get(src_key)
        if v is None:
            continue
        try:
            v = float(v)
        except Exception:
            continue
        if not np.isfinite(v):
            continue
        dst = _KEY_RENAME_IN.get(src_key, src_key)
        if not _should_override(dst):
            continue
        data[dst] = v
        if dst == 'total_assets_ty':
            data['total_assets'] = v * 1e9
        if dst in ('roe', 'roa'):
            data[dst + '_pct'] = v

    if supp.get('eps_ttm_vnd') and _should_override('eps'):
        data['eps'] = float(supp['eps_ttm_vnd'])
        data['eps_ttm_vnd'] = data['eps']
        data['has_eps'] = True
        data['_eps_source'] = 'SUPPLEMENT_TTM'
    if supp.get('pe') and _should_override('pe'):
        data['pe'] = round(float(supp['pe']), 2)
        data['pe_ttm'] = data['pe']
        data['_pe_source'] = 'SUPPLEMENT_TTM'

    if not _has_valid('profit_ty') and _has_valid('lnst_6t2026_ty'):
        data['profit_ty'] = float(data['lnst_6t2026_ty'])
        data['profit'] = data['profit_ty'] * 1e9
    if not _has_valid('lnst_6t2026_ty') and _has_valid('profit_ty'):
        data['lnst_6t2026_ty'] = float(data['profit_ty'])

    if not _has_valid('pe') and data.get('_pe_source') != 'SUPPLEMENT_TTM':
        profit_basis = (data.get('lnst_me_2025_ty') or data.get('lnst_2025_ty') or 0)
        calc = 0.0
        if _has_valid('eps') and _has_valid('price_vnd'):
            calc = data['price_vnd'] / data['eps']
        elif _has_valid('market_cap_ty') and profit_basis > 0:
            calc = data['market_cap_ty'] / profit_basis
        if calc > 0 and PE_MIN <= calc <= PE_MAX * 3:
            data['pe'] = round(calc, 2)
            data['pe_ttm'] = data['pe']
            data['_pe_source'] = 'COMPUTED'
        elif snap.get('pe_legacy_v37'):
            data['pe'] = round(float(snap['pe_legacy_v37']), 2)
            data['pe_ttm'] = data['pe']
            data['_pe_source'] = 'LEGACY_V37'
            data['_pe_is_legacy'] = True
            data.setdefault('_data_quality_warnings', []).append(
                f"PE_LEGACY_V37: {data['pe']}x — chưa tính lại được từ CSV/supplement"
            )

    if not _has_valid('eps'):
        profit_basis = (data.get('lnst_me_2025_ty') or data.get('lnst_2025_ty') or 0)
        if profit_basis > 0 and data.get('shares', 0) > 0:
            calc = profit_basis * 1e9 / data['shares']
            if MIN_REAL_EPS <= abs(calc) <= 1_000_000:
                data['eps'] = round(calc, 0)
                data['eps_ttm_vnd'] = data['eps']
                data['has_eps'] = True
                data['_eps_source'] = 'COMPUTED_FY2025'

    if not _has_valid('bvps') and data.get('equity_ty', 0) > 0 and data.get('shares', 0) > 0:
        calc = data['equity_ty'] * 1e9 / data['shares']
        if MIN_REAL_BVPS <= calc <= 500_000:
            data['bvps'] = round(calc, 0)
            data['bvps_vnd'] = data['bvps']
            data['has_bvps'] = True

    if not _has_valid('pb') and data.get('price_vnd', 0) > 0 and data.get('bvps', 0) > 0:
        calc = data['price_vnd'] / data['bvps']
        if PB_MIN <= calc <= PB_MAX * 2:
            data['pb'] = round(calc, 2)

    if not _has_valid('roe'):
        profit_basis = (data.get('lnst_me_2025_ty') or data.get('lnst_2025_ty') or 0)
        if profit_basis > 0 and data.get('equity_ty', 0) > 0:
            calc = profit_basis / data['equity_ty'] * 100
            if 0 < calc <= 60:
                data['roe'] = round(calc, 2)
                data['roe_pct'] = data['roe']

    if not _has_valid('roa'):
        profit_basis = (data.get('lnst_me_2025_ty') or data.get('lnst_2025_ty') or 0)
        if profit_basis > 0 and data.get('total_assets_ty', 0) > 0:
            calc = profit_basis / data['total_assets_ty'] * 100
            if 0 < calc <= 10:
                data['roa'] = round(calc, 2)
                data['roa_pct'] = data['roa']

    if not _has_valid('market_cap_ty') and data.get('price_vnd', 0) > 0 and data.get('shares', 0) > 0:
        data['market_cap_ty'] = data['price_vnd'] * data['shares'] / 1e9
        data['market_cap'] = data['market_cap_ty'] * 1e9

    if snap.get('note'):
        data['_snapshot_note'] = snap['note']
    if supp.get('financial_note'):
        data['_supplement_note'] = supp['financial_note']
        data['financial_as_of'] = supp.get('financial_as_of', SNAPSHOT_BUILD_DATE)

    src = data.get('_data_source') or ''
    if 'SNAPSHOT' not in src:
        data['_data_source'] = (src + '+SNAPSHOT').strip('+')

    return data


def get_latest_market_snapshot(ticker, include_reference=False):
    t = _canonical_ticker(ticker)
    if t in LATEST_MARKET_SNAPSHOT:
        return LATEST_MARKET_SNAPSHOT[t].copy()
    if include_reference and t in REFERENCE_ONLY_MARKET_SNAPSHOT:
        return REFERENCE_ONLY_MARKET_SNAPSHOT[t].copy()
    return {}


def get_price_freshness(ticker):
    t = _canonical_ticker(ticker)
    d = _snap_for(t)
    pdate = d.get('price_as_of', '')
    days = _days_between(pdate) if pdate else 999
    return {
        'ticker': t,
        'price_vnd': d.get('price_vnd', 0),
        'price_as_of': pdate,
        'price_stale_days': days,
        'price_is_stale': bool(days > 0),
        'price_is_materially_stale': bool(days >= MATERIALLY_STALE_DAYS),
        'price_is_missing': not bool(d.get('price_vnd', 0)),
        'reference_date': SNAPSHOT_BUILD_DATE,
    }


def get_shares_status(ticker):
    t = _canonical_ticker(ticker)
    d = _snap_for(t)
    return {
        'ticker': t,
        'shares': d.get('shares', 0),
        'shares_mn': d.get('shares', 0) / 1e6,
        'shares_is_official': bool(d.get('shares_is_official', False)),
        'shares_is_estimated': bool(d.get('shares_is_estimated', True)),
        'shares_is_provisional': bool(d.get('shares_is_provisional', False)),
        'shares_basis': d.get('shares_basis', 'unknown'),
        'shares_as_of': d.get('shares_as_of', ''),
        'note': d.get('note', ''),
    }


def get_snapshot_as_of(ticker=None):
    if ticker is None:
        return {
            'price_date': SNAPSHOT_PRICE_DATE,
            'build_date': SNAPSHOT_BUILD_DATE,
            'source': SNAPSHOT_SOURCE,
            'n_tickers': len(LATEST_MARKET_SNAPSHOT),
        }
    d = _snap_for(ticker)
    return {
        'ticker': _canonical_ticker(ticker),
        'price_as_of': d.get('price_as_of', ''),
        'shares_as_of': d.get('shares_as_of', ''),
        'financial_as_of': d.get('financial_as_of',
                                  LATEST_FINANCIAL_SUPPLEMENT.get(
                                      _canonical_ticker(ticker), {}).get('financial_as_of', '')),
        'snapshot_as_of': d.get('snapshot_as_of', ''),
    }


def _detect_file_scale(long_df, quiet=False):
    if long_df is None or long_df.empty:
        return 1.0
    mask = long_df['metric_name'].astype(str).str.contains(
        r'tong_tai_san|total_assets', na=False, regex=True
    )
    if not mask.any():
        return 1.0
    vals = pd.to_numeric(long_df.loc[mask, 'value'], errors='coerce').dropna()
    vals = vals[vals > 0]
    if len(vals) == 0:
        return 1.0
    max_val = float(vals.max())
    if max_val >= 1e11:
        scale = 1e-9
        label = "RAW VND (÷ 1e9)"
    elif max_val >= 1e7:
        scale = 1e-3
        label = "TRIỆU VND (÷ 1e3)"
    else:
        scale = 1.0
        label = "TỶ VND (giữ nguyên)"
    if not quiet:
        print(f"[v54-CSV] 📏 File scale: {label} · max total_assets = {max_val:.3e}")
    return scale


def _extract_smart_v33(row, df, ticker=''):
    result = {'_matched_cols': {}}
    t = str(ticker).strip().upper()

    v, col = _get_val_strict(row, df, 'price')
    if v > 0:
        p = fix_price(v)
        if p > 0:
            result['price_vnd'] = p
            result['_matched_cols']['price_vnd'] = col

    v, col = _get_val_strict(row, df, 'shares')
    if v > 0:
        s = fix_shares(v)
        if s > 0:
            result['shares'] = s
            result['_matched_cols']['shares'] = col

    v, col = _get_val_strict(row, df, 'total_assets')
    if v > 0:
        ta = _to_ty(v, col)
        if ta > 0:
            result['total_assets_ty'] = ta
            result['_matched_cols']['total_assets_ty'] = col

    v, col = _get_val_strict(row, df, 'equity')
    if v > 0:
        eq = _to_ty(v, col)
        if eq > 0:
            result['equity_ty'] = eq
            result['_matched_cols']['equity_ty'] = col

    v, col = _get_val_strict(row, df, 'profit_6t')
    if v != 0:
        prof = _to_ty(abs(v), col)
        if prof > 0:
            result['profit_ty'] = prof if v > 0 else -prof
            result['_matched_cols']['profit_ty'] = col

    v, col = _get_val_strict(row, df, 'lntt_6t')
    if v != 0:
        lntt = _to_ty(abs(v), col)
        if lntt > 0:
            result['lntt_6m_ty'] = lntt if v > 0 else -lntt
            result['_matched_cols']['lntt_6m_ty'] = col

    v, col = _get_val_strict(row, df, 'revenue')
    if v > 0:
        rev = _to_ty(v, col)
        if rev > 0:
            result['nii_ty'] = rev
            result['_matched_cols']['nii_ty'] = col

    v, col = _get_val_strict(row, df, 'market_cap')
    if v > 0:
        mc = _to_ty(v, col)
        if mc > 0:
            result['market_cap_ty'] = mc
            result['_matched_cols']['market_cap_ty'] = col

    v, col = _get_val_strict(row, df, 'eps')
    if v != 0:
        e = fix_eps(abs(v), shares=result.get('shares', 0))
        if e > 0:
            result['eps'] = e if v > 0 else -e
            result['has_eps'] = True
            result['_matched_cols']['eps'] = col

    v, col = _get_val_strict(row, df, 'bvps')
    if v > 0:
        b = fix_bvps(v, equity=result.get('equity_ty', 0) * 1e9, shares=result.get('shares', 0))
        if b > 0:
            result['bvps'] = b
            result['has_bvps'] = True
            result['_matched_cols']['bvps'] = col

    v, col = _get_val_strict(row, df, 'pe')
    if PE_MIN <= v <= PE_MAX:
        result['pe'] = round(v, 2)
        result['_matched_cols']['pe'] = col

    v, col = _get_val_strict(row, df, 'pb')
    if PB_MIN <= v <= PB_MAX:
        result['pb'] = round(v, 2)
        result['_matched_cols']['pb'] = col

    v, col = _get_val_strict(row, df, 'roe')
    if ROE_MIN_PCT <= v <= ROE_MAX_PCT:
        result['roe'] = round(v, 2)
        result['_matched_cols']['roe'] = col

    v, col = _get_val_strict(row, df, 'roa')
    if ROA_MIN_PCT <= v <= ROA_MAX_PCT:
        result['roa'] = round(v, 2)
        result['_matched_cols']['roa'] = col

    v, col = _get_val_strict(row, df, 'casa')
    if 0 < v < 100:
        result['casa_pct'] = round(v, 2)
        result['_matched_cols']['casa_pct'] = col

    v, col = _get_val_strict(row, df, 'dividend')
    if v > 0:
        d = fix_dividend(v)
        if d > 0:
            result['dividend_vnd'] = d
            result['_matched_cols']['dividend_vnd'] = col

    v, col = _get_val_strict(row, df, 'growth_lnst')
    if v != 0:
        result['growth_lnst_pct'] = round(v, 2)
        result['_matched_cols']['growth_lnst_pct'] = col

    v, col = _get_val_strict(row, df, 'lnst_2024')
    if v > 0:
        lnst24 = _to_ty(v, col)
        if lnst24 > 0:
            result['lnst_2024_ty'] = lnst24
            result['_matched_cols']['lnst_2024_ty'] = col

    v, col = _get_val_strict(row, df, 'lnst_2025')
    if v > 0:
        lnst25 = _to_ty(v, col)
        if lnst25 > 0:
            result['lnst_2025_ty'] = lnst25
            result['_matched_cols']['lnst_2025_ty'] = col

    v, col = _get_val_strict(row, df, 'lntt_2025')
    if v != 0:
        result['lntt_2025_ty'] = _to_ty(v, col)
        result['_matched_cols']['lntt_2025_ty'] = col

    v, col = _get_val_strict(row, df, 'lnst_me_2025')
    if v != 0:
        result['lnst_me_2025_ty'] = _to_ty(v, col)
        result['_matched_cols']['lnst_me_2025_ty'] = col

    eq_ty = result.get('equity_ty', 0)
    shares = result.get('shares', 0)
    ta_ty = result.get('total_assets_ty', 0)
    profit_ty = result.get('profit_ty', 0)

    if result.get('bvps', 0) <= 0 and eq_ty > 0 and shares > 0:
        calc = (eq_ty * 1e9) / shares
        if MIN_REAL_BVPS <= calc <= 500_000:
            result['bvps'] = round(calc, 0)
            result['has_bvps'] = True
            result['bvps_source'] = 'computed (equity/shares)'

    if result.get('eps', 0) == 0 and profit_ty > 0 and shares > 0:
        calc = (profit_ty * 1e9) / shares
        if MIN_REAL_EPS <= calc <= 1_000_000:
            result['eps'] = round(calc, 0)
            result['has_eps'] = True

    if result.get('pe', 0) <= 0 and result.get('price_vnd', 0) > 0 and result.get('eps', 0) > 0:
        calc = result['price_vnd'] / result['eps']
        if PE_MIN <= calc <= PE_MAX:
            result['pe'] = round(calc, 2)

    if result.get('pb', 0) <= 0 and result.get('price_vnd', 0) > 0 and result.get('bvps', 0) > 0:
        calc = result['price_vnd'] / result['bvps']
        if PB_MIN <= calc <= PB_MAX:
            result['pb'] = round(calc, 2)

    if result.get('roe', 0) <= 0 and profit_ty > 0 and eq_ty > 0:
        calc = (profit_ty * 2 / eq_ty) * 100
        if ROE_MIN_PCT <= calc <= ROE_MAX_PCT:
            result['roe'] = round(calc, 2)

    if result.get('roa', 0) <= 0 and profit_ty > 0 and ta_ty > 0:
        calc = (profit_ty * 2 / ta_ty) * 100
        if ROA_MIN_PCT <= calc <= ROA_MAX_PCT:
            result['roa'] = round(calc, 2)

    if result.get('market_cap_ty', 0) <= 0 and result.get('price_vnd', 0) > 0 and shares > 0:
        result['market_cap_ty'] = (result['price_vnd'] * shares) / 1e9

    return result


def _merge_with_hardcoded(ticker, csv_data):
    t = _canonical_ticker(ticker)
    merged = {k: v for k, v in csv_data.items() if k != '_matched_cols'}
    latest = get_latest_bank_data(t)
    if latest:
        fallback_map = {
            'price_vnd': 'price_vnd', 'eps_ttm_vnd': 'eps', 'bvps_vnd': 'bvps',
            'pe_ttm': 'pe', 'pb': 'pb', 'roe_pct': 'roe', 'roa_pct': 'roa',
            'dividend_vnd': 'dividend_vnd', 'shares': 'shares',
            'market_cap_ty': 'market_cap_ty', 'total_assets_ty': 'total_assets_ty',
            'equity_ty': 'equity_ty', 'toi_ty': 'nii_ty', 'lntt_6m_ty': 'lntt_6m_ty',
            'lnst_6m_ty': 'profit_ty', 'lnst_2024_ty': 'lnst_2024_ty',
            'lnst_2025_ty': 'lnst_2025_ty', 'growth_lnst_pct': 'growth_lnst_pct',
            'casa_pct': 'casa_pct',
        }
        for src, dst in fallback_map.items():
            cur = merged.get(dst, 0)
            if isinstance(cur, (int, float, np.number)):
                try:
                    if np.isfinite(float(cur)) and float(cur) != 0:
                        continue
                except Exception:
                    pass
            v = latest.get(src, 0)
            if isinstance(v, (int, float, np.number)) and float(v) > 0:
                merged[dst] = v

        if merged.get('pe', 0) <= 0 and merged.get('price_vnd', 0) > 0 and merged.get('eps', 0) > 0:
            calc = merged['price_vnd'] / merged['eps']
            if PE_MIN <= calc <= PE_MAX:
                merged['pe'] = round(calc, 2)
        if merged.get('pb', 0) <= 0 and merged.get('price_vnd', 0) > 0 and merged.get('bvps', 0) > 0:
            calc = merged['price_vnd'] / merged.get('bvps', 0)
            if PB_MIN <= calc <= PB_MAX:
                merged['pb'] = round(calc, 2)
        if merged.get('eps', 0) == 0 and merged.get('profit_ty', 0) > 0 and merged.get('shares', 0) > 0:
            calc = (merged['profit_ty'] * 1e9) / merged['shares']
            if MIN_REAL_EPS <= calc <= 1_000_000:
                merged['eps'] = round(calc, 0)
        if merged.get('bvps', 0) <= 0 and merged.get('equity_ty', 0) > 0 and merged.get('shares', 0) > 0:
            calc = (merged['equity_ty'] * 1e9) / merged['shares']
            if MIN_REAL_BVPS <= calc <= 500_000:
                merged['bvps'] = round(calc, 0)

    merged = _apply_latest_market_snapshot(t, merged, prioritize_csv_financials=True)
    return merged


def _build_result_dict(extracted, ticker):
    t = _canonical_ticker(ticker)
    matched = extracted.get('_matched_cols', {})
    result = {
        'gia_hien_tai': extracted.get('price_vnd', 0.0),
        'eps': extracted.get('eps', 0.0),
        'bvps': extracted.get('bvps', 0.0),
        'co_tuc_cp': extracted.get('dividend_vnd', 0.0),
        'ty_le_co_tuc': extracted.get('ty_le_co_tuc', 0.0),
        'pe': extracted.get('pe', 0.0),
        'pb': extracted.get('pb', 0.0),
        'roe': extracted.get('roe', 0.0),
        'roa': extracted.get('roa', 0.0),
        'intrinsic_value': 0.0,
        'bank_revenue': extracted.get('nii_ty', 0.0),
        'bank_revenue_source': 'CSV' if extracted.get('nii_ty') else None,
        'profit': extracted.get('profit_ty', 0.0) * 1e9,
        'profit_ty': extracted.get('profit_ty', 0.0),
        'lntt_6m_ty': extracted.get('lntt_6m_ty', 0.0),
        'lntt_2025_ty': extracted.get('lntt_2025_ty', 0.0),
        'lntt_2024_ty': extracted.get('lntt_2024_ty', 0.0),
        'lnst_6t2026_ty': extracted.get('lnst_6t2026_ty', 0.0),
        'equity': extracted.get('equity_ty', 0.0) * 1e9,
        'equity_ty': extracted.get('equity_ty', 0.0),
        'total_assets': extracted.get('total_assets_ty', 0.0) * 1e9,
        'total_assets_ty': extracted.get('total_assets_ty', 0.0),
        'nii_ty': extracted.get('nii_ty', 0.0),
        'shares': extracted.get('shares', 0.0),
        'has_eps': extracted.get('has_eps', False),
        'has_bvps': extracted.get('has_bvps', False),
        'bvps_source': extracted.get('bvps_source', 'CSV'),
        'market_cap': extracted.get('market_cap_ty', 0.0) * 1e9,
        'market_cap_ty': extracted.get('market_cap_ty', 0.0),
        'lnst_2024_ty': extracted.get('lnst_2024_ty', 0.0),
        'lnst_2025_ty': extracted.get('lnst_2025_ty', 0.0),
        'lnst_me_2024_ty': extracted.get('lnst_me_2024_ty', 0.0),
        'lnst_me_2025_ty': extracted.get('lnst_me_2025_ty', 0.0),
        'lnst_9t2026_me_ty': extracted.get('lnst_9t2026_me_ty', 0.0),
        'lntt_9t2026_ty': extracted.get('lntt_9t2026_ty', 0.0),
        'lnst_q1_2026_ty': extracted.get('lnst_q1_2026_ty', 0.0),
        'lnst_q2_2026_ty': extracted.get('lnst_q2_2026_ty', 0.0),
        'plan_lnst_2026_ty': extracted.get('plan_lnst_2026_ty', 0.0),
        'plan_lntt_2026_ty': extracted.get('plan_lntt_2026_ty', 0.0),
        'plan_lnst_me_2026_ty': extracted.get('plan_lnst_me_2026_ty', 0.0),
        'growth_lnst_pct': extracted.get('growth_lnst_pct', 0.0),
        'casa_pct': extracted.get('casa_pct', 0.0),
        'dividend_yield_pct': extracted.get('dividend_yield_pct', 0.0),
        'dividend_cash_vnd': extracted.get('dividend_cash_vnd', 0.0),
        'dividend_stock_pct': extracted.get('dividend_stock_pct', 0.0),
        'dividend_note': extracted.get('dividend_note', ''),
        'dividend_ex_date': extracted.get('dividend_ex_date', ''),
        'price_as_of': extracted.get('price_as_of', ''),
        'price_stale_days': extracted.get('price_stale_days', 999),
        'price_is_stale': extracted.get('price_is_stale', True),
        'shares_is_official': extracted.get('shares_is_official', False),
        'shares_is_estimated': extracted.get('shares_is_estimated', True),
        'shares_is_provisional': extracted.get('shares_is_provisional', False),
        'shares_basis': extracted.get('shares_basis', 'unknown'),
        'shares_as_of': extracted.get('shares_as_of', ''),
        'financial_as_of': extracted.get('financial_as_of', ''),
        'financial_note': extracted.get('financial_note', ''),
        'snapshot_as_of': extracted.get('snapshot_as_of', SNAPSHOT_PRICE_DATE),
        '_pe_source': extracted.get('_pe_source', ''),
        '_eps_source': extracted.get('_eps_source', ''),
        '_data_source': extracted.get('_data_source', ''),
        '_data_quality_warnings': extracted.get('_data_quality_warnings', []),
        'sanity_warnings': [],
        '_matched_cols': matched,
    }
    if result['eps'] > 0 and result['bvps'] > 0:
        try:
            g = (22.5 * result['eps'] * result['bvps']) ** 0.5
            if 1_000 <= g <= 300_000:
                result['intrinsic_value'] = round(g, 0)
        except Exception:
            pass
    if result['gia_hien_tai'] > 0 and result['co_tuc_cp'] > 0:
        dy = (result['co_tuc_cp'] / result['gia_hien_tai']) * 100
        if 0 <= dy <= 30:
            result['ty_le_co_tuc'] = round(dy, 2)
    return result


_LONG_PERIOD_PRIORITY = ("2026H1", "2026", "2026Q1", "2025", "2024")

_LONG_METRIC_ALIASES = {
    "price": ("gia_thi_truong", "gia_co_phieu_hien_tai", "gia_co_phieu", "gia_hien_tai", "cp_hientai"),
    "shares": ("so_cp_luu_hanh", "so_co_phieu", "so_cp_hien_tai", "so_co_phieu_hien_tai",
               "so_co_phieu_lich_su", "cp_hientai"),
    "total_assets": ("tong_tai_san", "tong_tai_san_270", "tong_tai_san_co"),
    "equity": ("von_chu_so_huu", "vcsh_400", "von_csh"),
    "profit": ("lnst_cong_ty_me", "lnst_cot_loi", "loi_nhuan_csh",
               "loi_nhuan_sau_thue", "loi_nhuan_sau_thue_60", "profit",
               "lnst_me", "loi_nhuan_csh_me", "loi_nhuan_sau_thue_co_cong_ty_me"),
    "profit_before_tax": ("loi_nhuan_truoc_thue", "loi_nhuan_truoc_thue_50",
                          "lntt", "loi_nhuan_truoc_thue_co_cong_ty_me"),
    "revenue": ("doanh_thu_thuan", "doanh_thu_thuan_10", "thu_nhap_lai_thuan",
                "doanh_thu", "toi"),
    "market_cap": ("von_hoa_ty", "von_hoa_hien_tai_ty", "von_hoa_hien_tai"),
    "eps": ("eps_cong_ty_me", "eps_cty_me", "eps_tinh_toan", "eps_bao_cao", "eps"),
    "bvps": ("bvps_huu_tinh", "bvps_huu_tinh_h1_2026", "bvps_huu_tinh_q1_2026",
             "bvps_huu_hinh", "bvps"),
    "pe": ("pe",), "pb": ("pb",), "roe": ("roe",), "roa": ("roa",),
    "dividend": ("co_tuc_cp", "co_tuc", "co_tuc_tien_mat", "dividend_per_share"),
    "growth": ("tang_truong_lnst", "tang_truong_loi_nhuan"),
    "casa": ("casa", "casa_pct", "ty_le_casa"),
}

_PARENT_PROFIT_ALIASES = (
    "lnst_cong_ty_me", "lnst_me", "loi_nhuan_csh", "loi_nhuan_csh_me",
    "loi_nhuan_sau_thue_co_cong_ty_me",
)

_LONG_MONEY_KEYS = {"total_assets", "equity", "profit", "profit_before_tax", "revenue"}
_LONG_SHARE_KEYS = {"shares"}


def _is_long_financial_csv(df):
    if df is None or df.empty:
        return False
    cols = {str(c).strip().lower() for c in df.columns}
    return {"ticker", "metric_name", "period", "value"}.issubset(cols)


def _long_number(value):
    if value is None or (isinstance(value, float) and not np.isfinite(value)):
        return None
    if isinstance(value, (int, float, np.integer, np.floating)):
        return float(value)
    s = str(value).strip()
    if not s or s.lower() in {"na", "n/a", "none", "nan", "null", "-", "--", "—"}:
        return None
    return _parse_vn_number(s)


def _long_period_rank(period):
    p = str(period).strip().upper().replace(" ", "")
    try:
        return _LONG_PERIOD_PRIORITY.index(p)
    except ValueError:
        return len(_LONG_PERIOD_PRIORITY) + 1


def _long_get_value(sub, metric_aliases, periods=None):
    if sub is None or sub.empty:
        return None, None, None
    aliases = {str(x).strip().lower() for x in metric_aliases}
    tmp = sub[sub["_metric_norm"].isin(aliases)].copy()
    if tmp.empty:
        return None, None, None
    if periods is not None:
        wanted = {str(x).strip().upper() for x in periods}
        tmp = tmp[tmp["_period_norm"].isin(wanted)]
        if tmp.empty:
            return None, None, None
    tmp["_period_rank"] = tmp["_period_norm"].map(_long_period_rank)
    alias_rank = {str(name).strip().lower(): i for i, name in enumerate(metric_aliases)}
    tmp["_metric_rank"] = tmp["_metric_norm"].map(alias_rank).fillna(len(alias_rank))
    tmp = tmp.sort_values(["_period_rank", "_metric_rank"], kind="stable")
    row = tmp.iloc[0]
    return _long_number(row["value"]), str(row["metric_name"]), str(row["period"])


def _extract_long_csv_metrics(df, ticker, money_scale=None):
    t = _canonical_ticker(ticker)
    out = {"_matched_cols": {}, "_data_source": "CSV_LONG"}
    if not _is_long_financial_csv(df):
        return out
    work = df.copy()
    work["ticker"] = work["ticker"].astype(str).str.strip().str.upper()
    sub = work[work["ticker"] == t].copy()
    if sub.empty:
        out["_not_found"] = True
        return out
    sub["_metric_norm"] = sub["metric_name"].astype(str).str.strip().str.lower()
    sub["_period_norm"] = sub["period"].astype(str).str.strip().str.upper().str.replace(" ", "", regex=False)

    field_periods = {
        "price": ("2026H1", "2026", "2026Q1"),
        "shares": ("2026H1", "2026", "2026Q1", "2025"),
        "total_assets": ("2026H1", "2026Q1", "2026", "2025"),
        "equity": ("2026H1", "2026Q1", "2026", "2025"),
        "profit": ("2026H1", "2026Q1", "2026"),
        "profit_before_tax": ("2026H1", "2026Q1", "2026"),
        "revenue": ("2026H1", "2026Q1", "2026"),
        "market_cap": ("2026H1", "2026", "2026Q1"),
        "eps": ("2026H1", "2026", "2026Q1", "2025"),
        "bvps": ("2026H1", "2026", "2026Q1", "2025"),
        "pe": ("2026H1", "2026", "2026Q1", "2025"),
        "pb": ("2026H1", "2026", "2026Q1", "2025"),
        "roe": ("2026H1", "2026", "2026Q1", "2025"),
        "roa": ("2026H1", "2026", "2026Q1", "2025"),
        "dividend": ("2026H1", "2026", "2025", "2024"),
        "growth": ("2025",),
        "casa": ("2026H1", "2026", "2025"),
    }
    values = {}
    for key, aliases in _LONG_METRIC_ALIASES.items():
        val, metric, period = _long_get_value(sub, aliases, field_periods.get(key))
        if val is not None:
            values[key] = val
            out["_matched_cols"][key] = f"{metric}@{period}"

    if money_scale is None:
        ta_raw = values.get('total_assets', 0) or 0
        if ta_raw >= 1e11:
            money_scale = 1e-9
        elif ta_raw >= 1e7:
            money_scale = 1e-3
        else:
            money_scale = 1.0

    def money_ty(key):
        val = values.get(key)
        if val is None:
            return 0.0
        return val * money_scale

    if values.get("price", 0) and values["price"] > 0:
        out["price_vnd"] = fix_price(values["price"])
    if values.get("shares", 0) and values["shares"] > 0:
        out["shares"] = fix_shares(values["shares"])
    if values.get("total_assets", 0) > 0:
        out["total_assets_ty"] = money_ty("total_assets")
    if values.get("equity", 0) > 0:
        out["equity_ty"] = money_ty("equity")
    if values.get("profit") is not None:
        out["profit_ty"] = money_ty("profit")
    if values.get("profit_before_tax") is not None:
        out["lntt_6m_ty"] = money_ty("profit_before_tax")
    if values.get("revenue", 0) > 0:
        out["nii_ty"] = money_ty("revenue")
    if values.get("market_cap", 0) > 0:
        out["market_cap_ty"] = values["market_cap"]
    if values.get("eps") is not None and abs(values["eps"]) >= MIN_REAL_EPS:
        out["eps"] = round(values["eps"], 2)
        out["has_eps"] = True
    if values.get("bvps") is not None and values["bvps"] >= MIN_REAL_BVPS:
        out["bvps"] = round(values["bvps"], 2)
        out["has_bvps"] = True
    if values.get("pe") is not None and PE_MIN <= values["pe"] <= PE_MAX:
        out["pe"] = round(values["pe"], 2)
        out['_pe_source'] = 'CSV'
    if values.get("pb") is not None and PB_MIN <= values["pb"] <= PB_MAX:
        out["pb"] = round(values["pb"], 2)
    if values.get("roe") is not None and ROE_MIN_PCT <= values["roe"] <= ROE_MAX_PCT:
        out["roe"] = round(values["roe"], 2)
    if values.get("roa") is not None and ROA_MIN_PCT <= values["roa"] <= ROA_MAX_PCT:
        out["roa"] = round(values["roa"], 2)
    if values.get("dividend") is not None and values["dividend"] > 0:
        out["dividend_vnd"] = fix_dividend(values["dividend"])
    if values.get("growth") is not None:
        out["growth_lnst_pct"] = round(values["growth"], 2)
    if values.get("casa") is not None:
        out["casa_pct"] = round(values["casa"], 2)

    for year in ("2024", "2025"):
        v, metric, period = _long_get_value(sub, _LONG_METRIC_ALIASES["profit"], (year,))
        if v is not None:
            out[f"lnst_{year}_ty"] = v * money_scale
            out["_matched_cols"][f"lnst_{year}_ty"] = f"{metric}@{period}"

    v, m, p = _long_get_value(sub, _LONG_METRIC_ALIASES["profit_before_tax"], ("2025",))
    if v is not None:
        out["lntt_2025_ty"] = v * money_scale
        out["_matched_cols"]["lntt_2025_ty"] = f"{m}@{p}"

    v, m, p = _long_get_value(sub, _LONG_METRIC_ALIASES["profit"], ("2026H1",))
    if v is not None:
        out["lnst_6t2026_ty"] = v * money_scale
        out["_matched_cols"]["lnst_6t2026_ty"] = f"{m}@{p}"

    for year in ("2024", "2025"):
        v, m, p = _long_get_value(sub, _PARENT_PROFIT_ALIASES, (year,))
        if v is not None:
            out[f"lnst_me_{year}_ty"] = v * money_scale
            out["_matched_cols"][f"lnst_me_{year}_ty"] = f"{m}@{p}"

    v, m, p = _long_get_value(sub, _LONG_METRIC_ALIASES["profit_before_tax"], ("2024",))
    if v is not None:
        out["lntt_2024_ty"] = v * money_scale
        out["_matched_cols"]["lntt_2024_ty"] = f"{m}@{p}"

    v, m, p = _long_get_value(sub, _LONG_METRIC_ALIASES["profit"], ("2026Q1",))
    if v is not None:
        out["lnst_q1_2026_ty"] = v * money_scale
        out["_matched_cols"]["lnst_q1_2026_ty"] = f"{m}@{p}"

    shares = out.get("shares", 0)
    if not out.get("bvps") and out.get("equity_ty", 0) > 0 and shares > 0:
        calc = out["equity_ty"] * 1e9 / shares
        if MIN_REAL_BVPS <= calc <= 500_000:
            out["bvps"] = round(calc, 2)
            out["has_bvps"] = True
            out["bvps_source"] = "CSV computed: equity/shares"
    if not out.get("eps") and out.get("lnst_2025_ty", 0) and shares > 0:
        profit_basis = out.get("lnst_me_2025_ty") or out["lnst_2025_ty"]
        calc = profit_basis * 1e9 / shares
        if MIN_REAL_EPS <= abs(calc) <= 1_000_000:
            out["eps"] = round(calc, 2)
            out["has_eps"] = True
    if not out.get("pe") and out.get("price_vnd", 0) > 0 and out.get("eps", 0) > 0:
        calc = out["price_vnd"] / out["eps"]
        if PE_MIN <= calc <= PE_MAX:
            out["pe"] = round(calc, 2)
    if not out.get("pb") and out.get("price_vnd", 0) > 0 and out.get("bvps", 0) > 0:
        calc = out["price_vnd"] / out["bvps"]
        if PB_MIN <= calc <= PB_MAX:
            out["pb"] = round(calc, 2)

    out['_csv_fields'] = [k for k, v in out.items()
                          if not k.startswith('_') and k != '_matched_cols'
                          and isinstance(v, (int, float, np.number)) and v != 0]
    return out


_extract_smart = _extract_smart_v33
_extract_financial_metrics_v33_original = None


def _extract_financial_metrics_dispatch(row, df, ticker):
    t = _canonical_ticker(ticker)
    csv_data = {}
    try:
        if _is_long_financial_csv(df):
            csv_data = _extract_long_csv_metrics(df, t)
        else:
            csv_data = _extract_smart_v33(row, df, t)
    except Exception as e:
        print(f"[v54-CSV] ⚠️ Extract lỗi {t}: {e}")
    merged = _merge_with_hardcoded(t, csv_data)
    merged['_matched_cols'] = csv_data.get('_matched_cols', {})
    return _build_result_dict(merged, t)


def extract_financial_metrics_smart(row, df, ticker):
    return _extract_financial_metrics_dispatch(row, df, ticker)


def get_financial_metrics(row, df, ticker):
    return extract_financial_metrics_smart(row, df, ticker)


def extract_all_metrics(row, df, ticker):
    fm = extract_financial_metrics_smart(row, df, ticker)
    metrics = {}
    labels = [
        ("gia_hien_tai", "Giá hiện tại", "VND/cp"),
        ("eps", "EPS", "VND/cp"),
        ("bvps", "BVPS", "VND/cp"),
        ("pe", "P/E", "x"), ("pb", "P/B", "x"),
        ("roe", "ROE", "%"), ("roa", "ROA", "%"),
        ("profit_ty", "LNST 6T/2026", "tỷ VND"),
        ("lntt_6m_ty", "LNTT 6T/2026", "tỷ VND"),
        ("lntt_2025_ty", "LNTT 2025 (cả năm)", "tỷ VND"),
        ("lntt_2024_ty", "LNTT 2024 (cả năm)", "tỷ VND"),
        ("lnst_2024_ty", "LNST cả năm 2024", "tỷ VND"),
        ("lnst_2025_ty", "LNST cả năm 2025", "tỷ VND"),
        ("lnst_me_2025_ty", "LNST MẸ cả năm 2025", "tỷ VND"),
        ("lnst_6t2026_ty", "LNST 6T/2026", "tỷ VND"),
        ("lnst_9t2026_me_ty", "LNST MẸ 9T/2026", "tỷ VND"),
        ("lntt_9t2026_ty", "LNTT 9T/2026", "tỷ VND"),
        ("lnst_q1_2026_ty", "LNST Q1/2026", "tỷ VND"),
        ("equity_ty", "Vốn chủ sở hữu", "tỷ VND"),
        ("total_assets_ty", "Tổng tài sản", "tỷ VND"),
        ("nii_ty", "Doanh thu/TOI", "tỷ VND"),
        ("market_cap_ty", "Vốn hóa", "tỷ VND"),
        ("co_tuc_cp", "Cổ tức (VNĐ/cp)", "VND/cp"),
        ("ty_le_co_tuc", "Tỷ suất cổ tức", "%"),
        ("casa_pct", "CASA", "%"),
        ("growth_lnst_pct", "Tăng trưởng LNST 2025/2024", "%"),
        ("plan_lnst_2026_ty", "Kế hoạch LNST 2026", "tỷ VND"),
        ("plan_lntt_2026_ty", "Kế hoạch LNTT 2026", "tỷ VND"),
    ]
    for key, label, unit in labels:
        val = fm.get(key, 0)
        if isinstance(val, (int, float, np.number)) and np.isfinite(val) and val != 0:
            metrics[label] = (val, unit)
    return metrics


VN30_FILE_PATH = "du_lieu/vn30_41_fin_long.csv"
if not os.path.exists(VN30_FILE_PATH):
    VN30_FILE_PATH = "vn30_41_fin_long.csv"
    if not os.path.exists(VN30_FILE_PATH):
        VN30_FILE_PATH = None


def get_vn30_file_path():
    return VN30_FILE_PATH


def _aggressive_sanitize(df):
    if df is None or df.empty:
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
    return df


@st.cache_data(ttl=3600)
def load_data_optimized(file_path=None, ticker=None):
    if file_path is None:
        file_path = VN30_FILE_PATH
    if file_path is None or not os.path.exists(file_path):
        st.error(f"⚠️ Không tìm thấy file: {file_path}")
        return pd.DataFrame()
    try:
        if file_path.endswith('.parquet'):
            df = pl.read_parquet(file_path).to_pandas()
        else:
            df = _read_csv_multiencoding(file_path)
        df = fix_duplicate_columns(df)
        if 'ticker' not in df.columns and ticker is not None:
            df['ticker'] = str(ticker).strip().upper()
        text_cols = {'ky', 'date', 'ngay', 'ticker', 'Kỳ', 'STT', 'Mã',
                     'Ky_bao_cao', 'Loai_ky', 'metric_name', 'period'}
        for col in df.columns:
            if col in text_cols:
                continue
            try:
                df[col] = df[col].apply(_parse_vn_number)
            except Exception:
                continue
        df = _aggressive_sanitize(df)
        return df
    except Exception as e:
        st.error(f"❌ Lỗi đọc file: {e}")
        return pd.DataFrame()


def find_column_smart(df, target_keywords, threshold=92):
    return _find_col_strict(df, list(target_keywords))


def find_column_by_keywords(df, keywords, default=None):
    col = _find_col_strict(df, list(keywords))
    return col if col is not None else default


def find_column_value(row, df, keywords, default=0.0):
    col = find_column_by_keywords(df, keywords)
    if col:
        return clean_numeric(row.get(col, default))
    return default


def is_bank_ticker(ticker):
    t = _canonical_ticker(ticker)
    if t in BANK_TICKERS:
        return True
    return t in BANK_DATA_LATEST


def detect_sector(file_name, dataset_label):
    fn_low = str(file_name).lower()
    if any(k in fn_low for k in ['mwg', 'sab', 'mch', 'msn', 'frt',
                                 'hpg', 'vhm', 'gas', 'gvr', 'vpl', 'vic', 'vre',
                                 'bsr', 'tcx', 'ssi', 'vjc', 'vnm', 'gee', 'ree',
                                 'gmd', 'ksv', 'fpt', 'ctr', 'gex', 'pvi', 'pow', 'cmc',
                                 'cmg', 'gex', 'sab']):
        return "consumer"
    if "banking" in fn_low or "ngân hàng" in dataset_label.lower():
        return "banking"
    if "securities" in fn_low or "chứng khoán" in dataset_label.lower():
        return "securities"
    if "insurance" in fn_low or "bảo hiểm" in dataset_label.lower():
        return "insurance"
    return "general"


def detect_column_unit(col_name):
    if not col_name:
        return None
    cl = str(col_name).lower()
    if re.search(r'(?:^|_)vnd(?:_|$)', cl):   return 1
    if re.search(r'(?:^|_)nghin(?:_|$)', cl): return 1000
    if re.search(r'(?:^|_)ngan(?:_|$)', cl):  return 1000
    if re.search(r'(?:^|_)trieu(?:_|$)', cl): return 1_000_000
    if re.search(r'(?:^|_)trd(?:_|$)', cl):   return 1_000_000
    if re.search(r'(?:^|_)ty(?:_|$)', cl):    return 1_000_000_000
    return None


def infer_unit_from_value(value):
    if value == 0: return 1
    av = abs(value)
    if av >= 1e12: return 1
    if av >= 1e9:  return 1_000_000
    if av >= 1e6:  return 1_000_000
    return 1_000_000_000


def get_scaled_value(row, col):
    if col is None:
        return 0.0
    val = clean_numeric(row.get(col, 0.0))
    if val == 0 or _is_garbage(val):
        return 0.0
    unit = detect_column_unit(col)
    if unit is not None:
        return val * unit
    return val * infer_unit_from_value(val)


def get_value_in_billions(row, col):
    vnd = get_scaled_value(row, col)
    return vnd / 1e9 if vnd != 0 else 0.0


def get_bank_revenue(row, df):
    v, col = _get_val_strict(row, df, 'revenue')
    if col and v > 0:
        ty = _to_ty(v, col)
        return ty, f"TOI ({ty:.0f} tỷ)"
    return 0.0, "Không có"


def get_company_and_industry(ticker, row, df):
    t = _canonical_ticker(ticker)
    if t in COMPANY_MAPPING:
        return COMPANY_MAPPING[t]['name'], COMPANY_MAPPING[t]['sector']
    return "Công ty Cổ phần " + t, "Doanh nghiệp niêm yết"


def apply_fallback_if_missing(metrics, ticker):
    if not isinstance(metrics, dict):
        return metrics
    t = _canonical_ticker(ticker)
    latest = get_latest_bank_data(t)
    if not latest:
        return metrics
    mapping = {
        'gia_hien_tai': 'price_vnd', 'eps': 'eps_ttm_vnd', 'bvps': 'bvps_vnd',
        'pe': 'pe_ttm', 'pb': 'pb', 'roe': 'roe_pct', 'roa': 'roa_pct',
        'co_tuc_cp': 'dividend_vnd', 'shares': 'shares',
        'market_cap_ty': 'market_cap_ty', 'total_assets_ty': 'total_assets_ty',
        'equity_ty': 'equity_ty', 'nii_ty': 'toi_ty', 'lntt_6m_ty': 'lntt_6m_ty',
        'profit_ty': 'lnst_6m_ty', 'casa_pct': 'casa_pct',
        'growth_lnst_pct': 'growth_lnst_pct',
        'lnst_2024_ty': 'lnst_2024_ty', 'lnst_2025_ty': 'lnst_2025_ty',
    }
    for field, src_key in mapping.items():
        cur = metrics.get(field, 0)
        if isinstance(cur, (int, float, np.number)):
            try:
                if np.isfinite(float(cur)) and float(cur) != 0:
                    continue
            except Exception:
                pass
        v = latest.get(src_key, 0)
        if isinstance(v, (int, float, np.number)) and float(v) > 0:
            metrics[field] = v
    return metrics


def process_financial_statement(df):
    if df is None or df.empty:
        return df
    df = df.copy()
    text_cols = {'Ky_bao_cao', 'Loai_ky', 'ticker', 'ky', 'metric_name', 'period'}
    for col in df.columns:
        if col in text_cols:
            continue
        try:
            df[col] = df[col].apply(_parse_vn_number)
        except Exception:
            continue
    return df


def format_ty(value_ty, unit='tỷ'):
    if value_ty is None or value_ty == 0:
        return "N/A"
    if unit == 'nghin_ty':
        return f"{value_ty/1000:,.2f} nghìn tỷ"
    return f"{value_ty:,.0f} tỷ"


def format_ty_short(value_ty):
    if value_ty is None or value_ty == 0:
        return "N/A"
    if value_ty >= 1_000_000:
        return f"{value_ty/1_000_000:,.2f} triệu tỷ"
    if value_ty >= 1_000:
        return f"{value_ty/1_000:,.2f} nghìn tỷ"
    return f"{value_ty:,.0f} tỷ"


def get_latest_price_and_supplement(ticker, row=None, df=None):
    t = _canonical_ticker(ticker)
    is_bank = t in BANK_TICKERS or t in BANK_DATA_LATEST
    is_corp = t in CORP_TICKERS
    has_snapshot = t in LATEST_MARKET_SNAPSHOT

    if not (is_bank or is_corp or has_snapshot):
        return {"ticker": t, "kind": "unknown", "error": f"Mã {t} không có",
                "price_vnd": 0, "data_source": "N/A", "supplement": {}}

    kind = "bank" if is_bank else "corp"
    result = {
        "ticker": t, "kind": kind,
        "sector": COMPANY_MAPPING.get(t, {}).get("sector", ""),
        "price_vnd": 0, "eps_ttm_vnd": 0, "pe_ttm": 0, "pb": 0,
        "roe_pct": 0, "roa_pct": 0, "bvps_vnd": 0, "dividend_vnd": 0,
        "shares": 0, "market_cap_ty": 0, "data_source": "",
        "price_as_of": "", "price_stale_days": 999, "price_is_stale": True,
        "shares_is_official": False, "shares_is_estimated": True,
        "shares_basis": "unknown", "shares_as_of": "",
        "dividend_yield_pct": 0.0, "casa_pct": 0.0,
        "supplement": {"bank_q2_2026": None, "corp_latest": None, "snapshot": None},
    }

    if row is not None and df is not None:
        try:
            if _is_long_financial_csv(df):
                csv_data = _extract_long_csv_metrics(df, t)
            else:
                csv_data = _extract_smart_v33(row, df, t)
            csv_data = _merge_with_hardcoded(t, csv_data)
            for k_src, k_dst in [
                ('price_vnd', 'price_vnd'), ('eps', 'eps_ttm_vnd'),
                ('pe', 'pe_ttm'), ('pb', 'pb'), ('roe', 'roe_pct'),
                ('roa', 'roa_pct'), ('bvps', 'bvps_vnd'),
                ('dividend_vnd', 'dividend_vnd'), ('shares', 'shares'),
                ('market_cap_ty', 'market_cap_ty'),
            ]:
                v = csv_data.get(k_src, 0)
                if isinstance(v, (int, float, np.number)) and float(v) > 0:
                    result[k_dst] = v
            result["data_source"] = "CSV"
        except Exception as e:
            print(f"[v54-CSV] ⚠️ CSV extract lỗi {t}: {e}")

    latest = get_latest_bank_data(t)
    if latest:
        for k_src, k_dst in [
            ('price_vnd', 'price_vnd'), ('eps_ttm_vnd', 'eps_ttm_vnd'),
            ('pe_ttm', 'pe_ttm'), ('pb', 'pb'), ('roe_pct', 'roe_pct'),
            ('roa_pct', 'roa_pct'), ('bvps_vnd', 'bvps_vnd'),
            ('dividend_vnd', 'dividend_vnd'), ('shares', 'shares'),
            ('market_cap_ty', 'market_cap_ty'),
        ]:
            if result[k_dst] <= 0:
                v = latest.get(k_src, 0)
                if isinstance(v, (int, float, np.number)) and float(v) > 0:
                    result[k_dst] = v
        if not result["data_source"]:
            result["data_source"] = "CSV_FILE"
        result["supplement"]["corp_latest"] = latest if is_corp else None
        result["supplement"]["bank_q2_2026"] = latest if is_bank else None

    snap = get_latest_market_snapshot(t)
    if snap:
        tmp = dict(result)
        tmp['price_vnd'] = result['price_vnd']
        tmp['market_cap_ty'] = result['market_cap_ty']
        tmp['shares'] = result['shares']
        tmp['eps'] = result['eps_ttm_vnd']
        tmp['bvps'] = result['bvps_vnd']
        tmp['pe'] = result['pe_ttm']
        tmp['pb'] = result['pb']
        tmp['roe'] = result['roe_pct']
        tmp['roa'] = result['roa_pct']
        tmp = _apply_latest_market_snapshot(t, tmp, prioritize_csv_financials=True)
        result['price_vnd'] = tmp.get('price_vnd', result['price_vnd'])
        result['market_cap_ty'] = tmp.get('market_cap_ty', result['market_cap_ty'])
        result['shares'] = tmp.get('shares', result['shares'])
        result['eps_ttm_vnd'] = tmp.get('eps', result['eps_ttm_vnd'])
        result['bvps_vnd'] = tmp.get('bvps', result['bvps_vnd'])
        result['pe_ttm'] = tmp.get('pe', result['pe_ttm'])
        result['pb'] = tmp.get('pb', result['pb'])
        result['roe_pct'] = tmp.get('roe', result['roe_pct'])
        result['roa_pct'] = tmp.get('roa', result['roa_pct'])
        result['dividend_vnd'] = tmp.get('dividend_vnd', result['dividend_vnd'])
        for k in ('price_as_of', 'price_stale_days', 'price_is_stale',
                  'shares_is_official', 'shares_is_estimated', 'shares_basis',
                  'shares_as_of', 'dividend_yield_pct', 'casa_pct'):
            if k in tmp:
                result[k] = tmp[k]
        result["data_source"] = (result["data_source"] + "+SNAPSHOT").strip("+")
        result["supplement"]["snapshot"] = snap

    if not result.get("sector"):
        result["sector"] = "Ngân hàng" if is_bank else CORP_DATA_LATEST.get(t, {}).get("sector", "")
    return result


def get_all_latest_prices():
    prices = {}
    all_tk = list(BANK_DATA_LATEST.keys()) + list(CORP_DATA_LATEST.keys()) + list(LATEST_MARKET_SNAPSHOT.keys())
    all_tk = list(dict.fromkeys(all_tk))
    for tk in all_tk:
        r = get_latest_price_and_supplement(tk)
        prices[tk] = {
            "price_vnd": r.get("price_vnd", 0),
            "eps_ttm_vnd": r.get("eps_ttm_vnd", 0),
            "pe_ttm": r.get("pe_ttm", 0),
            "pb": r.get("pb", 0),
            "roe_pct": r.get("roe_pct", 0),
            "kind": r.get("kind", ""),
            "data_source": r.get("data_source", ""),
            "price_as_of": r.get("price_as_of", ""),
            "shares_is_official": r.get("shares_is_official", False),
        }
    return prices


def debug_latest_price(ticker):
    r = get_latest_price_and_supplement(ticker)
    return "\n".join([
        f"=== {r['ticker']} ===",
        f"Loại:       {r['kind']}",
        f"Nguồn:      {r['data_source']}",
        f"Giá:        {r.get('price_vnd', 0):>15,.0f}",
        f"Ngày giá:   {r.get('price_as_of', ''):>15}",
        f"EPS:        {r.get('eps_ttm_vnd', 0):>15,.0f}",
        f"P/E:        {r.get('pe_ttm', 0):>15.2f}",
        f"P/B:        {r.get('pb', 0):>15.2f}",
        f"ROE:        {r.get('roe_pct', 0):>15.2f}%",
        f"ROA:        {r.get('roa_pct', 0):>15.2f}%",
        f"BVPS:       {r.get('bvps_vnd', 0):>15,.0f}",
        f"SLCP:       {r.get('shares', 0):>15,.0f}"
        f"  [{'CHÍNH THỨC' if r.get('shares_is_official') else 'ƯỚC TÍNH'}]",
    ])


def calculate_altman_z(row, df): return None
def fetch_api_with_proxy(url, timeout=8): return None
def generate_mock_financial(ticker):
    r = get_latest_price_and_supplement(ticker)
    return {'ticker': ticker, 'price': r.get('price_vnd', 0),
            'eps': r.get('eps_ttm_vnd', 0), 'bvps': r.get('bvps_vnd', 0),
            'roe': r.get('roe_pct', 0), 'roa': r.get('roa_pct', 0),
            'pe': r.get('pe_ttm', 0), 'pb': r.get('pb', 0),
            'source': r.get('data_source', 'N/A')}
def normalize_tcbs_data(do, df_, ticker): return {'ticker': ticker, 'source': 'TCBS'}
def normalize_vnd_data(dv, ticker): return {'ticker': ticker, 'source': 'VNDirect'}
def fetch_stock_data(ticker): return generate_mock_financial(str(ticker).strip().upper())


def _load_csv_db_to_df(path):
    empty = pd.DataFrame(columns=['ticker', 'metric_name', 'period', 'value'])
    if not path:
        return empty
    if not os.path.exists(path):
        print(f"[v54-CSV] ❌ Không tồn tại: {path}")
        return empty
    size_kb = os.path.getsize(path) / 1024
    print(f"[v54-CSV] 📂 {os.path.basename(path)}  ({size_kb:.1f} KB)")
    with open(path, 'rb') as f:
        head = f.read(16)
    if head.startswith(b'SQLite format 3'):
        print(f"[v54-CSV] 🚨 FILE NÀY LÀ BINARY SQLITE")
        return empty
    try:
        df = _read_csv_multiencoding(path)
    except Exception as e:
        print(f"[v54-CSV] ❌ Đọc lỗi: {e}")
        return empty
    if df is None or df.empty:
        print(f"[v54-CSV] ⚠️  File rỗng")
        return empty
    original_cols = [str(c).strip() for c in df.columns]
    df.columns = original_cols
    lower_cols = {c.lower() for c in original_cols}
    print(f"[v54-CSV]    {len(df)} rows × {len(df.columns)} cols: {original_cols[:6]}")
    if {'ticker', 'metric_name', 'period', 'value'}.issubset(lower_cols):
        df.columns = [c.lower() for c in df.columns]
        ticker_aliases = ['ticker', 'ma', 'symbol', 'code', 'stock_code', 'ma_ck']
        period_aliases = ['period', 'ky', 'quarter', 'year', 'quy', 'nam', 'ky_bao_cao']
        metric_aliases = ['metric_name', 'metric', 'chi_tieu', 'chi_tieu_ten']
        value_aliases = ['value', 'gia_tri', 'val']
        tc = next((c for c in ticker_aliases if c in df.columns), None)
        pc = next((c for c in period_aliases if c in df.columns), None)
        mc = next((c for c in metric_aliases if c in df.columns), None)
        vc = next((c for c in value_aliases if c in df.columns), None)
        if not (tc and mc and vc):
            return empty
        out = df.rename(columns={tc: 'ticker', mc: 'metric_name', vc: 'value'})
        out['period'] = out[pc] if pc else '2026H1'
        out = out[['ticker', 'metric_name', 'period', 'value']].copy()
        out = out.dropna(subset=['ticker', 'metric_name'])
        out['ticker'] = out['ticker'].astype(str).str.strip().str.upper()
        out['metric_name'] = out['metric_name'].astype(str).str.strip().str.lower()
        out['period'] = out['period'].astype(str).str.strip()
        out['value'] = pd.to_numeric(out['value'], errors='coerce')
        out = out.dropna(subset=['value'])
        out = out.drop_duplicates(subset=['ticker', 'metric_name', 'period'], keep='last')
        print(f"[v54-CSV] ✅ LONG: {os.path.basename(path)}: {len(out)} rows")
        return out.reset_index(drop=True)
    if 'ticker' in lower_cols or 'Ticker' in original_cols:
        try:
            out = _wide_df_to_long(df)
            if not out.empty:
                print(f"[v54-CSV] ✅ WIDE: {os.path.basename(path)}: {len(out)} rows")
                return out
        except Exception as e:
            print(f"[v54-CSV] ❌ Wide parse lỗi: {e}")
    print(f"[v54-CSV] ⚠️  Định dạng không nhận diện được")
    return empty


@st.cache_data(ttl=3600)
def _load_csv_as_long_df():
    print("\n" + "=" * 78 + "\n[v54-CSV] 🔄 LOAD 3 FILE CSV (ƯỚC TIÊN 1)\n" + "=" * 78)
    frames = []
    for group, path in _CSV_DB_PATHS.items():
        df = _load_csv_db_to_df(path)
        if not df.empty:
            frames.append(df)
    if not frames:
        fallback_path = _find_fallback_csv()
        if fallback_path:
            df = _load_csv_db_to_df(fallback_path)
            if not df.empty:
                frames.append(df)
    if not frames:
        return pd.DataFrame(columns=['ticker', 'metric_name', 'period', 'value'])
    result = pd.concat(frames, ignore_index=True).drop_duplicates(
        subset=['ticker', 'metric_name', 'period'], keep='last').reset_index(drop=True)
    print(f"\n[v54-CSV] ✅ TOTAL: {len(result)} rows · {result['ticker'].nunique()} tickers")
    print("=" * 78 + "\n")
    return result


_load_sqlite_as_long_df = _load_csv_as_long_df


def _to_flat_dict(extracted):
    return {
        'price_vnd': extracted.get('price_vnd', 0),
        'eps_ttm_vnd': extracted.get('eps', 0),
        'bvps_vnd': extracted.get('bvps', 0),
        'pe_ttm': extracted.get('pe', 0),
        'pb': extracted.get('pb', 0),
        'roe_pct': extracted.get('roe', 0),
        'roa_pct': extracted.get('roa', 0),
        'dividend_vnd': extracted.get('dividend_vnd', 0),
        'shares': extracted.get('shares', 0),
        'market_cap_ty': extracted.get('market_cap_ty', 0),
        'total_assets_ty': extracted.get('total_assets_ty', 0),
        'equity_ty': extracted.get('equity_ty', 0),
        'toi_ty': extracted.get('nii_ty', 0),
        'nii_ty': extracted.get('nii_ty', 0),
        'lntt_6m_ty': extracted.get('lntt_6m_ty', 0),
        'lntt_2025_ty': extracted.get('lntt_2025_ty', 0),
        'lntt_2024_ty': extracted.get('lntt_2024_ty', 0),
        'lnst_6m_ty': extracted.get('profit_ty', 0),
        'lnst_6t2026_ty': extracted.get('lnst_6t2026_ty', 0),
        'lnst_2024_ty': extracted.get('lnst_2024_ty', 0),
        'lnst_2025_ty': extracted.get('lnst_2025_ty', 0),
        'lnst_me_2024_ty': extracted.get('lnst_me_2024_ty', 0),
        'lnst_me_2025_ty': extracted.get('lnst_me_2025_ty', 0),
        'lnst_9t2026_me_ty': extracted.get('lnst_9t2026_me_ty', 0),
        'lntt_9t2026_ty': extracted.get('lntt_9t2026_ty', 0),
        'lnst_q1_2026_ty': extracted.get('lnst_q1_2026_ty', 0),
        'lnst_q2_2026_ty': extracted.get('lnst_q2_2026_ty', 0),
        'plan_lnst_2026_ty': extracted.get('plan_lnst_2026_ty', 0),
        'plan_lntt_2026_ty': extracted.get('plan_lntt_2026_ty', 0),
        'plan_lnst_me_2026_ty': extracted.get('plan_lnst_me_2026_ty', 0),
        'growth_lnst_pct': extracted.get('growth_lnst_pct', 0),
        'casa_pct': extracted.get('casa_pct', 0),
        'dividend_yield_pct': extracted.get('dividend_yield_pct', 0),
        'dividend_cash_vnd': extracted.get('dividend_cash_vnd', 0),
        'dividend_stock_pct': extracted.get('dividend_stock_pct', 0),
        'dividend_note': extracted.get('dividend_note', ''),
        'dividend_ex_date': extracted.get('dividend_ex_date', ''),
        'price_as_of': extracted.get('price_as_of', ''),
        'price_stale_days': extracted.get('price_stale_days', 999),
        'price_is_stale': extracted.get('price_is_stale', True),
        'shares_is_official': extracted.get('shares_is_official', False),
        'shares_is_estimated': extracted.get('shares_is_estimated', True),
        'shares_is_provisional': extracted.get('shares_is_provisional', False),
        'shares_basis': extracted.get('shares_basis', 'unknown'),
        'shares_as_of': extracted.get('shares_as_of', ''),
        'financial_as_of': extracted.get('financial_as_of', ''),
        'financial_note': extracted.get('financial_note', ''),
        'snapshot_as_of': extracted.get('snapshot_as_of', SNAPSHOT_PRICE_DATE),
        '_pe_source': extracted.get('_pe_source', ''),
        '_eps_source': extracted.get('_eps_source', ''),
        '_data_source': extracted.get('_data_source', ''),
    }


def _populate_one_group(long_df, target_dict, default_sector, scale=None):
    if long_df is None or long_df.empty:
        return 0
    n_ok = 0
    for tk in long_df['ticker'].dropna().unique():
        tk = _canonical_ticker(tk)
        try:
            ext = _extract_long_csv_metrics(long_df, tk, money_scale=scale)
        except Exception as e:
            print(f"[v54-CSV] ⚠️ Extract {tk}: {e}")
            continue
        if ext.get('_not_found'):
            continue
        flat = _to_flat_dict(ext)
        flat = {k: v for k, v in flat.items()
                if v not in (0, 0.0, None) or isinstance(v, (bool, str))}
        if not any(isinstance(v, (int, float, np.number)) and v != 0 for v in flat.values()):
            continue

        ta_ty = flat.get('total_assets_ty', 0)
        if ta_ty > 0:
            if ta_ty < 100:
                factor = 1e3
            elif ta_ty > 100_000_000:
                factor = 1e-3
            else:
                factor = 1.0
            if factor != 1.0:
                money_keys = [
                    'total_assets_ty', 'equity_ty', 'toi_ty', 'nii_ty',
                    'lntt_6m_ty', 'lntt_2025_ty', 'lntt_2024_ty',
                    'lnst_6m_ty', 'lnst_6t2026_ty',
                    'lnst_2024_ty', 'lnst_2025_ty',
                    'lnst_me_2024_ty', 'lnst_me_2025_ty',
                    'lnst_9t2026_me_ty', 'lntt_9t2026_ty',
                    'lnst_q1_2026_ty', 'lnst_q2_2026_ty',
                    'plan_lnst_2026_ty', 'plan_lntt_2026_ty', 'plan_lnst_me_2026_ty',
                    'market_cap_ty',
                ]
                for k in money_keys:
                    if k in flat and isinstance(flat[k], (int, float, np.number)):
                        flat[k] = flat[k] * factor

        flat['sector'] = COMPANY_MAPPING.get(tk, {}).get('sector', default_sector)
        flat = _apply_latest_market_snapshot(tk, flat, prioritize_csv_financials=True)
        target_dict[tk] = flat
        n_ok += 1
    return n_ok


def _populate_from_csv():
    global CORP_TICKERS, BANK_TICKERS
    print("\n" + "=" * 78)
    print("[v54-CSV] 💾 POPULATE: CSV 100% TRƯỚC → SUPPLEMENT → SNAPSHOT fill gap")
    print(f"          Giá chốt: {SNAPSHOT_PRICE_DATE} | Build: {SNAPSHOT_BUILD_DATE}")
    print("=" * 78)

    bank_df = _load_csv_db_to_df(_CSV_DB_PATHS.get('ngan_hang_va_tai_chinh', ''))
    corp_frames = []
    for key in ['cong_nghe', 'san_xuat_va_khac']:
        d = _load_csv_db_to_df(_CSV_DB_PATHS.get(key, ''))
        if not d.empty:
            corp_frames.append(d)
    corp_df = pd.concat(corp_frames, ignore_index=True) if corp_frames else pd.DataFrame()

    if bank_df.empty and corp_df.empty:
        fallback_path = _find_fallback_csv()
        if fallback_path:
            df_all = _load_csv_db_to_df(fallback_path)
            if not df_all.empty:
                bank_like = ['VCB', 'BID', 'TCB', 'CTG', 'MBB', 'VPB', 'ACB', 'SSB',
                             'STB', 'LPB', 'VIB', 'EIB', 'HDB', 'SHB', 'TCX', 'SSI']
                bank_tickers_in_df = [t for t in df_all['ticker'].unique() if t in bank_like]
                bank_df = df_all[df_all['ticker'].isin(bank_tickers_in_df)]
                corp_df = df_all[~df_all['ticker'].isin(bank_tickers_in_df)]

    n_bank = _populate_one_group(bank_df, BANK_DATA_LATEST, "Ngân hàng & Tài chính", scale=None)
    n_corp = _populate_one_group(corp_df, CORP_DATA_LATEST, "Doanh nghiệp niêm yết", scale=None)

    try:
        BANK_TICKERS = set(BANK_TICKERS) | set(BANK_DATA_LATEST.keys())
    except Exception:
        BANK_TICKERS = set(BANK_DATA_LATEST.keys())
    CORP_TICKERS = set(CORP_DATA_LATEST.keys())

    added = 0
    for tk_snap in LATEST_MARKET_SNAPSHOT.keys():
        tk = _canonical_ticker(tk_snap)
        if tk in CORP_DATA_LATEST or tk in BANK_DATA_LATEST:
            continue
        tmp = _apply_latest_market_snapshot(tk, {}, prioritize_csv_financials=True)

        has_substance = (
            float(tmp.get('price_vnd', 0) or 0) > 0
            or float(tmp.get('market_cap_ty', 0) or 0) > 0
            or any(float(tmp.get(k, 0) or 0) != 0 for k in _FINANCIAL_SNAPSHOT_KEYS)
        )
        if not has_substance:
            print(f"[v54-CSV] ⏭  {tk}: snapshot thiếu giá/vốn hóa → chờ CSV, không inject")
            continue

        tmp['sector'] = COMPANY_MAPPING.get(tk, {}).get('sector', 'Doanh nghiệp niêm yết')
        if tk in _SNAPSHOT_BANK_SET:
            BANK_DATA_LATEST[tk] = tmp
            BANK_TICKERS.add(tk)
        else:
            CORP_DATA_LATEST[tk] = tmp
            CORP_TICKERS.add(tk)
        added += 1

    print(f"[v54-CSV] ✅ Populated: {n_bank} banks + {n_corp} corps (+{added} từ SNAPSHOT)")
    print(f"[v54-CSV] 📌 SLCP chính thức: "
          f"{sorted(t for t, d in LATEST_MARKET_SNAPSHOT.items() if d.get('shares_is_official'))}")
    print(f"[v54-CSV] ⏳ Giá thiếu: "
          f"{sorted(t for t, d in LATEST_MARKET_SNAPSHOT.items() if not d.get('price_vnd'))}")
    print("=" * 78 + "\n")


_populate_from_sqlite = _populate_from_csv


_PRIORITY_TRACE_KEYS = (
    'profit_ty', 'lntt_6m_ty', 'lntt_2025_ty', 'lnst_2024_ty', 'lnst_2025_ty',
    'lnst_6t2026_ty', 'lnst_me_2025_ty', 'lnst_me_2024_ty', 'lntt_2024_ty',
    'equity_ty', 'total_assets_ty', 'nii_ty', 'eps', 'bvps', 'pe', 'pb',
    'roe', 'roa', 'casa_pct', 'shares', 'market_cap_ty', 'price_vnd',
)


def get_financials_csv_first(ticker, csv_df=None, use_supplement=True):
    t = _canonical_ticker(ticker)

    if csv_df is None:
        try:
            csv_df = _load_csv_as_long_df()
        except Exception as e:
            print(f"[v54-PIPELINE] ⚠️ Không tải được CSV: {e}")
            csv_df = pd.DataFrame(columns=['ticker', 'metric_name', 'period', 'value'])

    ext = {}
    if _is_long_financial_csv(csv_df):
        try:
            ext = _extract_long_csv_metrics(csv_df, t)
        except Exception as e:
            print(f"[v54-PIPELINE] ⚠️ Extract CSV {t}: {e}")
            ext = {}
    csv_fields = [k for k in _PRIORITY_TRACE_KEYS
                  if isinstance(ext.get(k), (int, float, np.number)) and ext.get(k) != 0]

    if not use_supplement:
        saved = LATEST_FINANCIAL_SUPPLEMENT.pop(t, None)
        try:
            merged = _merge_with_hardcoded(t, ext)
        finally:
            if saved is not None:
                LATEST_FINANCIAL_SUPPLEMENT[t] = saved
    else:
        merged = _merge_with_hardcoded(t, ext)

    merged['_matched_cols'] = ext.get('_matched_cols', {})
    result = _build_result_dict(merged, t)

    final_fields = [k for k in _PRIORITY_TRACE_KEYS
                    if isinstance(result.get(k), (int, float, np.number)) and result.get(k) != 0]
    missing = [k for k in _PRIORITY_TRACE_KEYS if k not in final_fields]
    supp_fields = [k for k in final_fields
                   if k not in csv_fields and k in LATEST_FINANCIAL_SUPPLEMENT.get(t, {})]
    snap_fields = [k for k in final_fields if k not in csv_fields and k not in supp_fields]

    result['_priority_trace'] = {
        'ticker': t,
        'csv_file_found': bool(any(_CSV_DB_PATHS.values())),
        'csv_fields': csv_fields,
        'supplement_fields': supp_fields,
        'snapshot_or_computed_fields': snap_fields,
        'missing_fields': missing,
        'pe_source': result.get('_pe_source', ''),
        'eps_source': result.get('_eps_source', ''),
        'price_as_of': result.get('price_as_of', ''),
        'financial_as_of': result.get('financial_as_of', ''),
        'shares_is_official': result.get('shares_is_official', False),
        'warnings': result.get('_data_quality_warnings', []),
    }
    return result


def validate_snapshot():
    issues = []

    def _add(t, code, severity, msg):
        issues.append({'ticker': t, 'code': code, 'severity': severity, 'message': msg})

    for t, d in LATEST_MARKET_SNAPSHOT.items():
        p = float(d.get('price_vnd', 0) or 0)
        c = float(d.get('market_cap_ty', 0) or 0)
        s = float(d.get('shares', 0) or 0)

        if p <= 0:
            _add(t, 'MISSING_PRICE', 'HIGH',
                 'Chưa lấy được giá — cần bổ sung (không ghi đè CSV bằng 0).')
            continue

        if d.get('price_is_materially_stale'):
            _add(t, 'STALE_PRICE', 'MEDIUM',
                 f"Giá ngày {d.get('price_as_of')} — trễ {d.get('price_stale_days')} ngày "
                 f"so với {SNAPSHOT_BUILD_DATE}.")
        elif d.get('price_is_stale'):
            _add(t, 'PRICE_NOT_LATEST', 'LOW',
                 f"Giá ngày {d.get('price_as_of')}, chưa phải {SNAPSHOT_PRICE_DATE}.")

        if not d.get('shares_is_official'):
            _add(t, 'SHARES_ESTIMATED', 'LOW',
                 f"SLCP {s/1e6:,.1f} triệu là {d.get('shares_basis')} "
                 f"(CHƯA có số đăng ký chính thức).")

        if d.get('shares_is_provisional'):
            _add(t, 'SHARES_PROVISIONAL', 'MEDIUM',
                 'SLCP có thể thay đổi sau phát hành / thưởng cổ phiếu.')

        if p > 0 and c > 0 and s > 0:
            implied = p * s / 1e9
            diff = abs(implied - c) / c
            if diff > CAP_SHARES_TOL:
                _add(t, 'TRIPLET_MISMATCH', 'MEDIUM',
                     f"giá×SLCP={implied:,.0f} tỷ != vốn hóa={c:,.0f} tỷ "
                     f"(lệch {diff*100:.2f}%). Sẽ tự reconcile theo "
                     f"{'SLCP chính thức' if d.get('shares_is_official') else 'vốn hóa'}.")

        cash = d.get('dividend_cash_vnd')
        dy = d.get('dividend_yield_pct')
        if cash and p > 0 and dy is not None:
            implied_dy = float(cash) / p * 100.0
            if abs(implied_dy - float(dy)) > 0.5:
                _add(t, 'DIVIDEND_YIELD_MISMATCH', 'MEDIUM',
                     f"{float(cash):,.0f}đ/cp tại {p:,.0f}đ = {implied_dy:.2f}% "
                     f"nhưng bảng ghi {dy}%. Cần đối chiếu.")

        supp = LATEST_FINANCIAL_SUPPLEMENT.get(t, {})
        if supp.get('lnst_2024_is_approx'):
            _add(t, 'FINANCIAL_APPROX', 'LOW',
                 'LNST 2024 là số SUY RA / xấp xỉ, không phải số báo cáo trực tiếp.')
        if supp.get('financial_note') and t == 'FPT':
            _add(t, 'ACCOUNTING_CHANGE', 'MEDIUM',
                 'FPT đổi phương pháp hợp nhất FPT Telecom từ 2026 — không so sánh trực tiếp.')

    return issues


def get_snapshot_coverage_report():
    rows = []
    for t, d in LATEST_MARKET_SNAPSHOT.items():
        rows.append({
            'ticker': t,
            'price_vnd': d.get('price_vnd', 0),
            'price_as_of': d.get('price_as_of', ''),
            'price_stale_days': d.get('price_stale_days', 999),
            'price_is_missing': d.get('price_is_missing', True),
            'shares_mn': d.get('shares', 0) / 1e6,
            'shares_is_official': d.get('shares_is_official', False),
            'shares_basis': d.get('shares_basis', ''),
            'shares_is_provisional': d.get('shares_is_provisional', False),
            'market_cap_ty': d.get('market_cap_ty', 0),
            'dividend_yield_pct': d.get('dividend_yield_pct', 0),
            'dividend_cash_vnd': d.get('dividend_cash_vnd', 0),
            'dividend_stock_pct': d.get('dividend_stock_pct', 0),
            'casa_pct': d.get('casa_pct', None),
            'total_assets_ty': d.get('total_assets_ty', 0),
            'lnst_2025_ty': d.get('lnst_2025_ty',
                                  LATEST_FINANCIAL_SUPPLEMENT.get(t, {}).get('lnst_2025_ty', 0)),
            'lntt_2025_ty': d.get('lntt_2025_ty',
                                  LATEST_FINANCIAL_SUPPLEMENT.get(t, {}).get('lntt_2025_ty', 0)),
            'financial_as_of': LATEST_FINANCIAL_SUPPLEMENT.get(t, {}).get('financial_as_of', ''),
            'note': d.get('note', ''),
        })
    return pd.DataFrame(rows)


def print_snapshot_audit():
    print("\n" + "=" * 100)
    print(f"[v54-AUDIT] SNAPSHOT {SNAPSHOT_PRICE_DATE} | BUILD {SNAPSHOT_BUILD_DATE}")
    print("=" * 100)
    df = get_snapshot_coverage_report()
    print(f"Tổng: {len(df)} mã | "
          f"Giá thiếu: {int(df['price_is_missing'].sum())} | "
          f"SLCP chính thức: {int(df['shares_is_official'].sum())} | "
          f"SLCP ước tính: {int((~df['shares_is_official']).sum())}")
    print("-" * 100)
    for _, r in df.iterrows():
        flag = '✅' if not r['price_is_missing'] else '❌'
        off = 'CHINH THUC' if r['shares_is_official'] else 'UOC TINH'
        print(f"{flag} {r['ticker']:<5} "
              f"{r['price_vnd']:>10,.0f}  "
              f"{str(r['price_as_of']):<12} "
              f"{r['shares_mn']:>10,.2f}tr [{off:<10}] "
              f"{r['market_cap_ty']:>12,.0f} tỷ  "
              f"dy={r['dividend_yield_pct']:>5.2f}%")
    print("-" * 100)
    issues = validate_snapshot()
    print(f"[v54-AUDIT] {len(issues)} cảnh báo:")
    for it in issues:
        print(f"  [{it['severity']:<6}] {it['ticker']:<5} {it['code']:<26} {it['message']}")
    print("=" * 100 + "\n")
    return issues


__all__ = [
    'load_data_optimized', 'detect_sector',
    'extract_financial_metrics_smart', 'get_financial_metrics',
    'extract_all_metrics', 'find_column_by_keywords', 'find_column_smart',
    'find_column_value', 'clean_numeric', 'is_bank_ticker',
    'get_bank_revenue', 'get_company_and_industry',
    'get_scaled_value', 'get_value_in_billions',
    'fetch_stock_data', 'generate_mock_financial',
    'detect_column_unit', 'infer_unit_from_value',
    'fix_price', 'fix_bvps', 'fix_eps', 'fix_dividend', 'fix_shares',
    'is_suspicious_column', '_aggressive_sanitize', 'fix_duplicate_columns',
    'BANK_DATA_LATEST', 'get_bank_fallback', 'get_latest_bank_data',
    'process_financial_statement', '_parse_vn_number',
    'format_ty', 'format_ty_short',
    'apply_fallback_if_missing',
    'VN30_FILE_PATH', 'get_vn30_file_path', '_read_csv_multiencoding',
    'CORP_DATA_LATEST', 'CORP_TICKERS', 'is_corp_ticker', 'get_corp_latest_data',
    'get_latest_price_and_supplement', 'get_all_latest_prices', 'debug_latest_price',
    '_CSV_DB_PATHS', '_SQLITE_DB_PATHS', '_resolve_csv_db_paths',
    '_load_csv_as_long_df', '_populate_from_csv', '_populate_one_group',
    '_detect_file_scale',
    '_is_period_column', '_is_metric_column', '_wide_df_to_long',
    '_CSV_FILENAMES', '_DEFAULT_CSV_PATHS',
    'LATEST_MARKET_SNAPSHOT',
    'get_latest_market_snapshot',
    '_apply_latest_market_snapshot',
    'SNAPSHOT_PRICE_DATE', 'SNAPSHOT_BUILD_DATE', 'SNAPSHOT_SOURCE',
    'TICKER_ALIASES',
    'LATEST_FINANCIAL_SUPPLEMENT',
    'REFERENCE_ONLY_MARKET_SNAPSHOT',
    'get_financials_csv_first',
    'get_price_freshness',
    'get_shares_status',
    'get_snapshot_as_of',
    'get_snapshot_coverage_report',
    'validate_snapshot',
    'print_snapshot_audit',
    '_canonical_ticker',
    '_reconcile_market_triplet',
]


# ============================================================================
# ============================================================================
# [v55] BẮT ĐẦU PHẦN MỚI — TÍCH HỢP 9 FILE CSV GỐC (LCTT / KQKD / BCDKT)
# ----------------------------------------------------------------------------
# Đây là TOÀN BỘ phần mới. Không sửa code v54 ở trên.
# ============================================================================
# ============================================================================

import unicodedata


# ----------------------------------------------------------------------------
# [v55.1] 9 FILE MỚI + PHÂN LOẠI
# ----------------------------------------------------------------------------
_CSV_FILENAMES_V55 = {
    'lctt_san_xuat':   'LCTT_SanXuat.csv',
    'lctt_ngan_hang':  'LCTT_NganHang.csv',
    'lctt_cong_nghe':  'LCTT_CongNghe.csv',
    'kqkd_san_xuat':   'KQKD_SanXuat.csv',
    'kqkd_ngan_hang':  'KQKD_NganHang.csv',
    'kqkd_cong_nghe':  'KQKD_CongNghe.csv',
    'bcdkt_san_xuat':  'BCDKT_SanXuat.csv',
    'bcdkt_ngan_hang': 'BCDKT_NganHang.csv',
    'bcdkt_cong_nghe': 'BCDKT_CongNghe.csv',
}

_CSV_TYPE_BY_KEY_V55 = {
    'lctt_san_xuat':   ('LCTT',  'san_xuat'),
    'lctt_ngan_hang':  ('LCTT',  'ngan_hang'),
    'lctt_cong_nghe':  ('LCTT',  'cong_nghe'),
    'kqkd_san_xuat':   ('KQKD',  'san_xuat'),
    'kqkd_ngan_hang':  ('KQKD',  'ngan_hang'),
    'kqkd_cong_nghe':  ('KQKD',  'cong_nghe'),
    'bcdkt_san_xuat':  ('BCDKT', 'san_xuat'),
    'bcdkt_ngan_hang': ('BCDKT', 'ngan_hang'),
    'bcdkt_cong_nghe': ('BCDKT', 'cong_nghe'),
}


def _resolve_csv_paths_v55():
    """Giống hệt _resolve_csv_db_paths() v54, quét 9 file mới."""
    here   = os.path.dirname(os.path.abspath(__file__))
    parent = os.path.dirname(here)
    bases = [
        here, parent, os.getcwd(),
        os.path.join(os.getcwd(), 'du_lieu'),
        os.path.join(parent, 'du_lieu'),
        '/app', '/app/du_lieu',
        '/content', '/content/du_lieu',
        '/workspace', '/workspace/du_lieu',
    ]
    out = {}
    print("\n" + "=" * 78)
    print("[v55-CSV] 🔍 TÌM 9 FILE CSV GỐC MỚI (LCTT/KQKD/BCDKT × 3 NHÓM)")
    print("=" * 78)
    for key, fname in _CSV_FILENAMES_V55.items():
        found = None
        for base in bases:
            p = os.path.join(base, fname)
            try:
                if os.path.isfile(p) and os.path.getsize(p) > 0:
                    found = os.path.abspath(p)
                    break
            except OSError:
                continue
        out[key] = found
        if found:
            print(f"   ✅ {key:<20} {os.path.basename(found):<24}"
                  f" ({os.path.getsize(found)/1024:>7.1f} KB)")
        else:
            print(f"   ❌ {key:<20} {fname}")
    print(f"\n   📊 {sum(1 for v in out.values() if v)}/9 file tìm thấy")
    print("=" * 78 + "\n")
    return out


_CSV_DB_PATHS_V55 = _resolve_csv_paths_v55()


# ----------------------------------------------------------------------------
# [v55.2] CHUẨN HOÁ TIẾNG VIỆT + BẢN ĐỒ CỘT → METRIC NỘI BỘ
# ----------------------------------------------------------------------------
def _remove_diacritics(s):
    try:
        nfd = unicodedata.normalize('NFD', str(s))
        return ''.join(c for c in nfd if unicodedata.category(c) != 'Mn')
    except Exception:
        return str(s)


def _norm_v55(s):
    """Lowercase, gộp mọi dấu câu (giữ dấu tiếng Việt) -> space đơn."""
    s = str(s).strip().lower()
    s = re.sub(r'[\s\-\.\,\(\)\[\]\{\}/:]+', ' ', s)
    return re.sub(r'\s+', ' ', s).strip()


# Metric names nội bộ PHẢI TRÙNG khớp alias trong _LONG_METRIC_ALIASES v54
# để _extract_long_csv_metrics tự nhận ra.
_VI_HEADER_TO_METRIC_V55 = {
    # ---------- KQKD ----------
    'doanh thu thuần': 'doanh_thu_thuan',
    'tổng doanh thu': 'tong_doanh_thu',
    'doanh thu': 'doanh_thu',
    'thu nhập lãi thuần': 'thu_nhap_lai_thuan',
    'thu nhập lãi': 'thu_nhap_lai',
    'lợi nhuận sau thuế (lợi nhuận ròng)': 'loi_nhuan_sau_thue',
    'lợi nhuận sau thuế': 'loi_nhuan_sau_thue',
    'lợi nhuận kế toán trước thuế': 'loi_nhuan_truoc_thue',
    'lợi nhuận trước thuế': 'loi_nhuan_truoc_thue',
    'lợi nhuận ròng phân bổ cho cổ đông phổ thông': 'loi_nhuan_csh',
    'lợi nhuận ròng từ hoạt động tiếp tục phân bổ cổ đông': 'loi_nhuan_csh',
    'lợi nhuận từ hoạt động tiếp tục và không tiếp tục': 'loi_nhuan_tong',
    'lợi nhuận từ hoạt động liên tục': 'loi_nhuan_lien_tuc',
    'lợi nhuận chuẩn hóa': 'loi_nhuan_chuan_hoa',
    'lợi nhuận bao gồm cổ đông không kiểm soát': 'loi_nhuan_hop_nhat',
    'lãi cơ bản trên cổ phiếu (basic eps)': 'eps',
    'lãi suy giảm trên cổ phiếu (diluted eps)': 'eps_pha_loang',
    'chi phí lãi vay': 'chi_phi_lai_vay',
    'chi phí thuế thu nhập doanh nghiệp': 'chi_phi_thue_tndn',
    'chi phí bán hàng và quản lý doanh nghiệp': 'chi_phi_ban_hang_ql',
    'giá vốn hàng bán': 'gia_von_hang_ban',
    'lợi nhuận gộp': 'loi_nhuan_gop',
    'lợi nhuận thuần từ hoạt động kinh doanh': 'loi_nhuan_thuan_hdkd',
    'lợi nhuận': 'loi_nhuan',
    'chi phí': 'chi_phi',
    # ---------- BCDKT ----------
    'tổng tài sản': 'tong_tai_san',
    'tổng nguồn vốn': 'tong_nguon_von',
    'tổng nợ phải trả': 'tong_no_phai_tra',
    'vốn chủ sở hữu': 'von_chu_so_huu',
    'vốn chủ sở hữu phổ thông': 'von_chu_so_huu_pho_thong',
    'vốn cổ phần': 'von_co_phan',
    'vốn góp chủ sở hữu (cổ phiếu phổ thông)': 'von_gop_chu_so_huu',
    'hàng tồn kho': 'hang_ton_kho',
    'tiền và các khoản tương đương tiền': 'tien_va_tuong_duong_tien',
    'tiền và tương đương tiền': 'tien_va_tuong_duong_tien',
    'phải thu ngắn hạn của khách hàng': 'phai_thu_ngan_han_kh',
    'phải trả người bán ngắn hạn': 'phai_tra_nguoi_ban_ngan_han',
    'lợi nhuận sau thuế chưa phân phối': 'loi_nhuan_sau_thue_chua_phan_phoi',
    'thặng dư vốn cổ phần': 'thang_du_von_co_phan',
    'tài sản ngắn hạn': 'tai_san_ngan_han',
    'tài sản dài hạn': 'tai_san_dai_han',
    'nợ ngắn hạn': 'no_ngan_han',
    'nợ dài hạn': 'no_dai_han',
    'vay và nợ thuê tài chính ngắn hạn': 'vay_va_no_thue_tai_chinh_ngan_han',
    'vay và nợ thuê tài chính dài hạn': 'vay_va_no_thue_tai_chinh_dai_han',
    'tổng nợ vay': 'tong_no_vay',
    'chi phí xây dựng cơ bản dở dang': 'chi_phi_xay_dung_co_ban_do_dang',
    'tài sản cố định thuần': 'tai_san_co_dinh_thuan',
    'nguyên giá tài sản cố định': 'nguyen_gia_tai_san_co_dinh',
    'hao mòn lũy kế tài sản cố định': 'hao_mon_luy_ke_tai_san_co_dinh',
    # ---------- LCTT ----------
    'lưu chuyển tiền thuần từ hoạt động kinh doanh': 'luu_chuyen_tien_hdkd',
    'lưu chuyển tiền thuần từ hoạt động đầu tư': 'luu_chuyen_tien_hdt',
    'lưu chuyển tiền thuần từ hoạt động tài chính': 'luu_chuyen_tien_hdtc',
    'lưu chuyển tiền thuần trong kỳ': 'luu_chuyen_tien_thuan_ky',
    'biến động tiền và tương đương tiền': 'bien_dong_tien',
    'dòng tiền tự do (fcf)': 'dong_tien_tu_do',
    'chi phí đầu tư tài sản cố định (capex)': 'capex',
    'mua sắm tài sản cố định': 'mua_sam_tai_san_co_dinh',
    'tiền và tương đương tiền đầu kỳ': 'tien_dau_ky',
    'tiền và tương đương tiền cuối kỳ': 'tien_cuoi_ky',
    'cổ tức đã chi trả': 'co_tuc_da_chi_tra',
    'cổ tức đã nhận từ hoạt động đầu tư': 'co_tuc_da_nhan',
    'trả nợ gốc vay': 'tra_no_goc_vay',
    'phát hành nợ vay': 'phat_hanh_no_vay',
    'thanh lý tài sản cố định': 'thanh_ly_tai_san_co_dinh',
    'khấu hao tài sản cố định và phân bổ': 'khau_hao',
    'thu/chi thuần từ phát hành/trả nợ': 'thu_chi_phat_hanh_tra_no',
    'thuế': 'thue',
}

# 2 bảng lookup: có dấu + không dấu (dự phòng CSV header bị mất dấu)
_VI_HEADER_NORM_MAP   = {_norm_v55(k): v for k, v in _VI_HEADER_TO_METRIC_V55.items()}
_VI_HEADER_NODIAC_MAP = {_remove_diacritics(k): v for k, v in _VI_HEADER_NORM_MAP.items()}


# ----------------------------------------------------------------------------
# [v55.3] QUY ĐỔI (Loại kỳ, Năm, Ngày kỳ) → period nội bộ
# ----------------------------------------------------------------------------
def _parse_period_v55(row, statement_type):
    """
    BCDKT (điểm cân đối):  Q2 → YYYYH1, Q4 → YYYY
    KQKD / LCTT (dòng chảy): Qn → YYYYQn  (H1 sẽ được cộng dồn riêng)
    """
    try:
        loai = _norm_v55(row.get('_period_type', ''))
        nam  = row.get('_year')
        ngay = str(row.get('_date', '') or '').strip()

        if nam is None or pd.isna(nam):
            return None
        nam = int(float(nam))

        if 'năm' in loai or 'year' in loai:
            return str(nam)

        if not ngay:
            return None
        parts = ngay.split('-')
        if len(parts) < 2:
            return None
        month = int(parts[1])
        q = (month - 1) // 3 + 1

        if statement_type == 'BCDKT':
            return {1: f'{nam}Q1', 2: f'{nam}H1',
                    3: f'{nam}Q3', 4: str(nam)}.get(q)
        return f'{nam}Q{q}'
    except Exception:
        return None


# ----------------------------------------------------------------------------
# [v55.4] READER CHO 1 FILE CSV GỐC MỚI → LONG-DF CHUẨN
# ----------------------------------------------------------------------------
def _read_statement_csv_v55(file_path):
    """
    Đọc 1 trong 9 file: trả về DataFrame long-format
        columns = [ticker, metric_name, period, value]
    """
    empty = pd.DataFrame(columns=['ticker', 'metric_name', 'period', 'value'])
    if not file_path or not os.path.exists(file_path):
        return empty

    fname = os.path.basename(file_path).lower()
    if   'bcdkt' in fname: statement_type = 'BCDKT'
    elif 'kqkd' in fname: statement_type = 'KQKD'
    elif 'lctt' in fname: statement_type = 'LCTT'
    else: return empty

    try:
        df = pd.read_csv(file_path, encoding='utf-8-sig', low_memory=False)
    except Exception:
        try:
            df = pd.read_csv(file_path, encoding='utf-8', low_memory=False)
        except Exception as e:
            print(f"[v55-CSV] ❌ Đọc {fname}: {e}")
            return empty

    # --- Đổi tên cột: meta cố định + metric có trong map ---
    col_rename = {}
    for c in df.columns:
        cl = _norm_v55(c)
        if cl in ('mã chứng khoán', 'ma chung khoan'):
            col_rename[c] = '_ticker'
        elif cl in ('nhóm ngành', 'nhom nganh'):
            col_rename[c] = '_sector'
        elif cl in ('loại kỳ', 'loai ky'):
            col_rename[c] = '_period_type'
        elif cl in ('năm', 'nam'):
            col_rename[c] = '_year'
        elif cl in ('ngày kỳ', 'ngay ky'):
            col_rename[c] = '_date'
        else:
            if cl in _VI_HEADER_NORM_MAP:
                col_rename[c] = _VI_HEADER_NORM_MAP[cl]
            else:
                diac = _remove_diacritics(cl)
                if diac in _VI_HEADER_NODIAC_MAP:
                    col_rename[c] = _VI_HEADER_NODIAC_MAP[diac]
                else:
                    fb = re.sub(r'[^a-z0-9]+', '_', diac).strip('_')
                    if fb and fb not in ('tai_san',):
                        col_rename[c] = fb
    df = df.rename(columns=col_rename)

    if '_ticker' not in df.columns:
        return empty

    # --- Build records ---
    records = []
    for _, row in df.iterrows():
        tk = _canonical_ticker(str(row.get('_ticker', '')).strip())
        if not tk or tk in ('NAN', 'NONE'):
            continue
        period = _parse_period_v55(row, statement_type)
        if not period:
            continue
        for col in df.columns:
            if col.startswith('_'):
                continue
            val = row.get(col)
            if pd.isna(val):
                continue
            try:
                fv = float(val)
            except (TypeError, ValueError):
                continue
            if not np.isfinite(fv):
                continue
            records.append({'ticker': tk, 'metric_name': col,
                            'period': period, 'value': fv})

    if not records:
        return empty

    out = pd.DataFrame(records)

    # --- Cộng dồn H1 cho KQKD/LCTT ---
    if statement_type in ('KQKD', 'LCTT'):
        out = _aggregate_h1_v55(out, statement_type)

    out = out.drop_duplicates(
        subset=['ticker', 'metric_name', 'period'], keep='last'
    ).reset_index(drop=True)

    print(f"[v55-CSV] ✅ {fname:<24} {len(out):>7} rows · "
          f"{out['ticker'].nunique():>3} tickers")
    return out


def _aggregate_h1_v55(df, statement_type):
    """
    KQKD: dữ liệu quý là lũy kế từng quý riêng lẻ (standalone)
          → H1 = Q1 + Q2 (đúng cho dòng chảy doanh thu/LN).
    LCTT: trong BCTC Việt Nam thường là LŨY KẾ
          → H1 = giá trị Q2 (đã bao gồm Q1).
    """
    if df.empty:
        return df

    q1 = df[df['period'].str.endswith('Q1')].copy()
    q2 = df[df['period'].str.endswith('Q2')].copy()
    if q1.empty or q2.empty:
        return df

    q1['_year'] = q1['period'].str[:-2]
    q2['_year'] = q2['period'].str[:-2]

    if statement_type == 'KQKD':
        merged = q1.merge(q2, on=['ticker', 'metric_name', '_year'],
                          suffixes=('_q1', '_q2'))
        if not merged.empty:
            merged['period'] = merged['_year'] + 'H1'
            merged['value']  = merged['value_q1'] + merged['value_q2']
            h1 = merged[['ticker', 'metric_name', 'period', 'value']]
            df = pd.concat([df, h1], ignore_index=True)
    else:  # LCTT
        q2 = q2.copy()
        q2['period'] = q2['_year'] + 'H1'
        h1 = q2[['ticker', 'metric_name', 'period', 'value']]
        df = pd.concat([df, h1], ignore_index=True)

    return df.drop_duplicates(
        subset=['ticker', 'metric_name', 'period'], keep='last'
    )


# ----------------------------------------------------------------------------
# [v55.5] NẠP TOÀN BỘ 12 CSV (3 cũ + 9 mới) THÀNH 1 LONG-DF DUY NHẤT
# ----------------------------------------------------------------------------
@st.cache_data(ttl=3600)
def _load_csv_as_long_df_v55():
    """Nạp 12 file (3 cũ + 9 mới). Ưu tiên dòng cuối khi trùng (period mới nhất)."""
    frames = []

    # 3 file cũ qua pipeline v54 (KHÔNG sửa)
    for _, path in _CSV_DB_PATHS.items():
        df = _load_csv_db_to_df(path)
        if df is not None and not df.empty:
            frames.append(df)

    # 9 file mới qua reader v55
    for _, path in _CSV_DB_PATHS_V55.items():
        if path:
            df = _read_statement_csv_v55(path)
            if not df.empty:
                frames.append(df)

    if not frames:
        return pd.DataFrame(columns=['ticker', 'metric_name', 'period', 'value'])

    merged = pd.concat(frames, ignore_index=True).drop_duplicates(
        subset=['ticker', 'metric_name', 'period'], keep='last'
    ).reset_index(drop=True)

    print(f"\n[v55-CSV] ✅ TỔNG: {len(merged):,} rows · "
          f"{merged['ticker'].nunique()} tickers · "
          f"{merged['period'].nunique()} kỳ\n")
    return merged


# ----------------------------------------------------------------------------
# [v55.6] MERGE 9 CSV MỚI VÀO HAI DICT TOÀN CỤC (KHÔNG ĐÈ SỐ CŨ)
# ----------------------------------------------------------------------------
def _populate_one_group_v55(long_df, target_dict, default_sector):
    """Chỉ fill gap: field nào target_dict đã có (≠0) thì giữ nguyên."""
    if long_df is None or long_df.empty:
        return 0

    n_ok = 0
    for tk in long_df['ticker'].dropna().unique():
        tk = _canonical_ticker(tk)
        try:
            ext = _extract_long_csv_metrics(long_df, tk, money_scale=None)
        except Exception:
            continue
        if ext.get('_not_found'):
            continue

        existing = target_dict.get(tk, {}).copy()
        flat = _to_flat_dict(ext)

        for k, v in flat.items():
            if isinstance(v, (int, float, np.number)) and v == 0:
                continue
            if isinstance(v, str) and not v:
                continue
            if k in existing and existing[k] not in (0, 0.0, None, '', False):
                continue  # giữ số cũ
            existing[k] = v

        existing['sector'] = (existing.get('sector')
                              or COMPANY_MAPPING.get(tk, {}).get('sector', default_sector))

        # Snapshot v54 vẫn luôn thắng về GIÁ / SLCP / CASA / CỔ TỨC
        existing = _apply_latest_market_snapshot(
            tk, existing, prioritize_csv_financials=True
        )
        target_dict[tk] = existing
        n_ok += 1
    return n_ok


def _populate_from_csv_v55():
    """
    Pipeline đầy đủ v55:
      1) Gọi _populate_from_csv() gốc (3 CSV cũ) — giữ nguyên hành vi v54.
      2) Đọc 9 CSV mới — merge vào dict (chỉ fill gap).
    """
    global CORP_TICKERS, BANK_TICKERS

    # --- Bước 1: v54 gốc ---
    try:
        _populate_from_csv()
    except Exception as e:
        print(f"[v55-CSV] ⚠️ _populate_from_csv v54 lỗi: {e}")

    # --- Bước 2: 9 CSV mới ---
    print("\n" + "=" * 78)
    print("[v55-CSV] 📂 MERGE 9 CSV GỐC MỚI VÀO DICT TOÀN CỤC")
    print("=" * 78)

    bank_frames, corp_frames = [], []
    for key, path in _CSV_DB_PATHS_V55.items():
        if not path:
            continue
        df = _read_statement_csv_v55(path)
        if df.empty:
            continue
        _, sector = _CSV_TYPE_BY_KEY_V55[key]
        (bank_frames if sector == 'ngan_hang' else corp_frames).append(df)

    bank_v55 = pd.concat(bank_frames, ignore_index=True) if bank_frames else pd.DataFrame()
    corp_v55 = pd.concat(corp_frames, ignore_index=True) if corp_frames else pd.DataFrame()

    n_b = _populate_one_group_v55(bank_v55, BANK_DATA_LATEST, "Ngân hàng & Tài chính")
    n_c = _populate_one_group_v55(corp_v55, CORP_DATA_LATEST, "Doanh nghiệp niêm yết")

    try:
        BANK_TICKERS = set(BANK_TICKERS) | set(BANK_DATA_LATEST.keys())
    except Exception:
        BANK_TICKERS = set(BANK_DATA_LATEST.keys())
    CORP_TICKERS = set(CORP_DATA_LATEST.keys())

    print(f"[v55-CSV] ✅ Bổ sung: {n_b:>3} banks  +  {n_c:>3} corps từ 9 CSV mới")
    print(f"[v55-CSV] 📊 Tổng cuối: BANK={len(BANK_DATA_LATEST)}  "
          f"CORP={len(CORP_DATA_LATEST)}")
    print("=" * 78 + "\n")


# ----------------------------------------------------------------------------
# [v55.7] PIPELINE CSV-FIRST ĐẦY ĐỦ (12 FILE) — API CÔNG KHAI MỚI
# ----------------------------------------------------------------------------
def get_financials_csv_first_v55(ticker, csv_df=None, use_supplement=True):
    """
    Giống get_financials_csv_first() v54 nhưng nạp đủ 12 file
    (3 file cũ + 9 file mới). Không đụng code v54.
    """
    if csv_df is None:
        csv_df = _load_csv_as_long_df_v55()
    return get_financials_csv_first(ticker, csv_df=csv_df,
                                    use_supplement=use_supplement)


# ----------------------------------------------------------------------------
# [v55.8] BÁO CÁO ĐỘ PHỦ 9 FILE MỚI
# ----------------------------------------------------------------------------
def get_csv_v55_coverage_report():
    """DataFrame 9 dòng: key / statement / sector / file / found / n_rows / n_tickers."""
    rows = []
    for key, path in _CSV_DB_PATHS_V55.items():
        stmt, sector = _CSV_TYPE_BY_KEY_V55[key]
        exists = bool(path and os.path.exists(path))
        n_rows = n_tk = 0
        if exists:
            df = _read_statement_csv_v55(path)
            n_rows = len(df)
            n_tk   = df['ticker'].nunique() if not df.empty else 0
        rows.append({
            'key': key, 'statement': stmt, 'sector': sector,
            'file': os.path.basename(path) if path else _CSV_FILENAMES_V55[key],
            'found': exists,
            'n_rows': n_rows,
            'n_tickers': n_tk,
        })
    return pd.DataFrame(rows)


def print_csv_v55_audit():
    """In bảng độ phủ 9 file ra console (dùng 1 lần khi khởi động)."""
    print("\n" + "=" * 92)
    print("[v55-AUDIT] ĐỘ PHỦ 9 CSV GỐC MỚI")
    print("=" * 92)
    df = get_csv_v55_coverage_report()
    for _, r in df.iterrows():
        flag = '✅' if r['found'] else '❌'
        print(f"{flag} {r['key']:<18} {r['statement']:<6} {r['sector']:<10} "
              f"{r['file']:<20} rows={r['n_rows']:>7} tickers={r['n_tickers']:>3}")
    print("-" * 92)
    total_rows = int(df['n_rows'].sum())
    print(f"  Tổng dòng: {total_rows:>9,} | Tổng file OK: {int(df['found'].sum())}/9")
    print("=" * 92 + "\n")
    return df


# ----------------------------------------------------------------------------
# [v55.9] MỞ RỘNG __all__ (không xoá mục cũ)
# ----------------------------------------------------------------------------
__all__ = list(__all__) + [
    '_CSV_FILENAMES_V55', '_CSV_DB_PATHS_V55', '_CSV_TYPE_BY_KEY_V55',
    '_resolve_csv_paths_v55',
    '_norm_v55', '_remove_diacritics', '_VI_HEADER_TO_METRIC_V55',
    '_VI_HEADER_NORM_MAP', '_VI_HEADER_NODIAC_MAP',
    '_parse_period_v55', '_aggregate_h1_v55',
    '_read_statement_csv_v55',
    '_load_csv_as_long_df_v55',
    '_populate_from_csv_v55', '_populate_one_group_v55',
    'get_financials_csv_first_v55',
    'get_csv_v55_coverage_report', 'print_csv_v55_audit',
]


# ============================================================================
# GHI CHÚ KHỞI ĐỘNG
# ----------------------------------------------------------------------------
# Trong app.py dùng:
#
#   from du_lieu.doc_bctc_goc import (
#       _populate_from_csv_v55, print_csv_v55_audit,
#       get_financials_csv_first_v55,
#   )
#
#   _populate_from_csv_v55()     # 3 CSV cũ + 9 CSV mới
#   print_csv_v55_audit()        # báo cáo độ phủ 9 file
#
#   fpt = get_financials_csv_first_v55('FPT')
#   print(fpt['_priority_trace'])
# ============================================================================
