# dieu_phoi/dieu_phoi_chinh.py
"""
[v54-DISPATCH] Module điều phối chính – Entry point toàn hệ thống.

[v54-DISPATCH] TÍCH HỢP TOÀN DIỆN v53 & v54:
    - 100% CSV: 3 file du_lieu_cong_nghe.csv / du_lieu_ngan_hang_va_tai_chinh.csv / du_lieu_san_xuat_va_khac.csv
    - Kết hợp Snapshot 21/10/2026 (VNINDEX 1738.67, VN30 1880.57, 32 mã cổ phiếu)
    - Delegate loader cho du_lieu/doc_bctc_goc v53 (đã fix lỗi ưu tiên BCTC gốc vs Snapshot)
    - KHÔNG còn bất kỳ dòng sqlite3.connect() nào
    - Fallback: CSV 3 nhóm → vn30_41_fin_long.csv → template
    - Debug panel hiển thị rõ nguồn CSV và Snapshot
"""

import os
import sys
import re
import traceback

import streamlit as st
import pandas as pd
import numpy as np

# ============================================================================
# [v54-DISPATCH] IMPORT CẤU HÌNH — TỪ CAU_HINH_DANH_MUC v54
# ============================================================================
from tien_ich.cau_hinh_danh_muc import (
    COMPANY_MAPPING, TICKER_DISPLAY, THRESHOLDS, BANK_TICKERS,
    to_float_scalar, safe_divide, round_float,
    format_currency_vn, format_currency_vn_advanced,
    format_eps_value, format_pe_pb,
    GARBAGE_VALUES, SUSPICIOUS_COL_IDS,
    MIN_REAL_PRICE, MIN_REAL_BVPS, MIN_REAL_EPS,
    MIN_REAL_DIVIDEND, MIN_REAL_MARKET_CAP, MIN_REAL_SHARES,
    is_suspicious_column,
    fix_price, fix_bvps, fix_eps, fix_dividend, fix_shares,
    sanitize_dataframe, sanitize_financial_inputs,
    # [v54] Reuse CSV paths + loaded tickers từ cau_hinh v54
    _CSV_DB_PATHS as _CM_CSV_PATHS,
    _LOADED_TICKERS as _CM_LOADED_TICKERS,
    _IS_USING_SQLITE as _CM_IS_USING_CSV,
    _DEFAULT_SECTOR_BY_DB as _CM_DEFAULT_SECTOR_BY_DB,
    _SNAPSHOT_TICKERS_MAP as _CM_SNAPSHOT_TICKERS, # [v54] Import danh sách mã Snapshot
)

# Alias tương thích ngược với v44
_CM_SQLITE_PATHS = _CM_CSV_PATHS

# ============================================================================
# [v54-DISPATCH] IMPORT TỪ doc_bctc_goc v53 (Đã tích hợp ưu tiên BCTC gốc)
# ============================================================================
from du_lieu.doc_bctc_goc import (
    load_data_optimized, detect_sector,
    extract_financial_metrics_smart, get_financial_metrics,
    extract_all_metrics,
    find_column_by_keywords, find_column_value, find_column_smart,
    clean_numeric, is_bank_ticker,
    get_bank_revenue, get_company_and_industry,
    calculate_altman_z,
    get_scaled_value, get_value_in_billions,
    fetch_stock_data, generate_mock_financial,
    normalize_tcbs_data, normalize_vnd_data, fetch_api_with_proxy,
    detect_column_unit, infer_unit_from_value,
    _load_sqlite_as_long_df as _dcg_load_csv_long,  # alias nhưng là CSV
    _CSV_DB_PATHS as _DCG_CSV_PATHS,
    LATEST_MARKET_SNAPSHOT, # [v54] Import Snapshot
)

# Alias tương thích ngược
_DCG_SQLITE_PATHS = _DCG_CSV_PATHS

# ============================================================================
# [v54-DISPATCH] v35 OPTIONAL LOADER
# ============================================================================
_V35_AVAILABLE = False
try:
    from du_lieu.doc_bctc_goc_v35 import (
        load_long_csv as _v35_load_long_csv,
        build_wide_long_df as _v35_build_wide,
        metric_to_ty as _v35_metric_to_ty,
        get_latest_row_for_ticker_v35 as _v35_get_latest_row,
        get_latest_price_and_supplement as _v35_get_price,
        debug_v35 as _v35_debug,
    )
    _V35_AVAILABLE = True
    print("[v54-DISPATCH] ✅ Module v35 loaded — dùng unit-aware CSV loader")
except ImportError as _e:
    print(f"[v54-DISPATCH] ⚠️ Module v35 KHÔNG tìm thấy: {_e}")
    print("[v54-DISPATCH] → Fallback sang bản gốc v33. App vẫn chạy được.")
    _V35_AVAILABLE = False

    def _v35_load_long_csv(csv_path=None):
        if csv_path is None or not os.path.exists(csv_path):
            return pd.DataFrame()
        try:
            df = pd.read_csv(csv_path, encoding='utf-8-sig')
        except UnicodeDecodeError:
            df = pd.read_csv(csv_path, encoding='utf-8', errors='replace')
        df.columns = [str(c).strip().lower() for c in df.columns]
        if 'value' in df.columns:
            df['value'] = pd.to_numeric(df['value'], errors='coerce').fillna(0.0)
        if 'ticker' in df.columns:
            df['ticker'] = df['ticker'].astype(str).str.upper().str.strip()
        return df

    def _v35_build_wide(csv_path=None):
        long_df = _v35_load_long_csv(csv_path)
        if long_df.empty:
            return pd.DataFrame()
        wide = long_df.pivot_table(
            index=['ticker', 'period'],
            columns='metric_name',
            values='value',
            aggfunc='first',
        ).reset_index()
        wide.columns.name = None
        return wide

    def _v35_metric_to_ty(value, metric_name):
        try:
            v = float(value)
        except (TypeError, ValueError):
            return 0.0
        if not np.isfinite(v) or v == 0:
            return 0.0
        av = abs(v)
        if av >= 1e13:
            return v * 1e-9
        if av >= 1e11:
            return v * 1e-6
        if av >= 1e6:
            return v * 1e-3
        return v

    def _v35_get_latest_row(wide_df, ticker):
        if wide_df is None or wide_df.empty:
            return None
        sub = wide_df[wide_df['ticker'].astype(str).str.upper() == str(ticker).upper()]
        if sub.empty:
            return None
        return sub.iloc[-1].to_dict()

    def _v35_get_price(ticker, df=None):
        return {"ticker": ticker, "kind": "unknown", "data_source": "N/A",
                "price_vnd": 0, "supplement": {}}

    def _v35_debug(*args, **kwargs):
        print("[v54-DISPATCH] debug_v35 không khả dụng (thiếu module v35)")


# ============================================================================
# [v54-DISPATCH] IMPORT THUẬT TOÁN — GIỮ NGUYÊN 100%
# ============================================================================
from thuat_toan.dinh_gia_graham import (
    calculate_pe_safe, calculate_pb_safe, calculate_roe_safe,
    calculate_roic_safe, calculate_debt_to_equity_safe,
    calculate_dividend_yield_safe, calculate_cagr,
    calculate_ncav, calculate_liquidation_value, get_ncav_from_row,
    calculate_normalized_eps, calculate_fcf, calculate_fcf_per_share,
    calculate_management_score, calculate_moat_score,
    get_peer_metrics, compare_with_peers,
    buffett_intrinsic_value, hybrid_valuation_enhanced,
    hybrid_valuation_ensemble, hybrid_valuation_bank,
    BankValuationEngine,
    label_rule, train_risk_classifier_ensemble, predict_risk_ensemble,
    train_eps_regressor_ensemble, predict_eps_with_huggingface,
    train_eps_model_advanced, predict_eps_advanced, predict_eps_ensemble,
    analyze_stock_graham_dodd,
    get_undervalued_stocks_enhanced, get_undervalued_stocks,
    check_signal_filters, check_signal_filters_advanced,
    show_graham_dodd_analysis,
    apply_crisis_simulation, forecast_trend, check_ai_availability,
    eps_model_advanced_trainer, eps_advanced_predictor,
)


# ============================================================================
# [v54-DISPATCH] UI MODULE – OPTIONAL — GIỮ NGUYÊN 100%
# ============================================================================
UI_AVAILABLE = False
try:
    from giao_dien.man_hinh_chinh import (
        render_crisis_section,
        render_valuation_slider,
        render_document_section,
        render_accuracy_section,
        render_real_time_data,
        render_main,
        vip_upgrade_dialog,
    )
    UI_AVAILABLE = True
    print("[v54-DISPATCH] ✅ UI module loaded (v54 UI)")
except Exception as e:
    print(f"[v54-DISPATCH] ⚠️ UI module không load được: {e}")
    print("[v54-DISPATCH] Sẽ dùng UI fallback...")

    def render_crisis_section(*args, **kwargs):
        if args and args[0]:
            st.info(f"📉 Đang xem kịch bản stress test: **{args[0]}**")

    def render_valuation_slider(*args, **kwargs):
        st.write("📊 Thanh trượt định giá (chưa load UI module)")

    def render_document_section(*args, **kwargs):
        st.write("📄 Tài liệu phân tích (chưa load UI module)")

    def render_accuracy_section(*args, **kwargs):
        st.write("🎯 Độ chính xác dự báo (chưa load UI module)")

    def render_real_time_data(*args, **kwargs):
        st.write("⚡ Dữ liệu thời gian thực (chưa load UI module)")

    def render_main(df, ticker, crisis_key=None):
        _render_fallback_dashboard(df, ticker, crisis_key)

    def vip_upgrade_dialog():
        st.info("💎 **Nâng cấp VIP** – Liên hệ Zalo **0327 625 853**")
        st.markdown("""
        ### Quyền lợi VIP:
        - ✅ Mở khóa toàn bộ mã cổ phiếu
        - ✅ Dự báo AI nâng cao
        - ✅ Stress test đa kịch bản
        - ✅ Export báo cáo PDF
        """)


# ============================================================================
# [v54-DISPATCH] BACKTEST MODULE – OPTIONAL — GIỮ NGUYÊN 100%
# ============================================================================
HISTORICAL_CRISES = {}
try:
    from lich_su.backtest_chien_luoc import (
        HISTORICAL_CRISES as _HC,
        calculate_technical_indicators,
        run_backtest_vectorbt,
    )
    HISTORICAL_CRISES = _HC
    print(f"[v54-DISPATCH] ✅ Backtest module loaded: {len(HISTORICAL_CRISES)} crises")
except Exception as e:
    print(f"[v54-DISPATCH] ⚠️ Backtest module không load được: {e}")

    def calculate_technical_indicators(*args, **kwargs):
        return {}

    def run_backtest_vectorbt(*args, **kwargs):
        return {}


# ============================================================================
# [v54-DISPATCH] CSV FIRST — DELEGATE HOÀN TOÀN CHO doc_bctc_goc v53
# ============================================================================
_USE_CSV_PRIMARY = _CM_IS_USING_CSV  # True nếu CSV loaded
_USE_SQLITE_PRIMARY = _USE_CSV_PRIMARY  # alias tương thích ngược
_CSV_LONG_DF_CACHE = None
_SQLITE_LONG_DF_CACHE = None  # alias


def _load_csv_long_df():
    """
    [v54-DISPATCH] Load 3 file CSV → long df.
    Delegate HOÀN TOÀN cho doc_bctc_goc v53 (đã tích hợp Snapshot).
    """
    global _CSV_LONG_DF_CACHE, _SQLITE_LONG_DF_CACHE
    if _CSV_LONG_DF_CACHE is not None and not _CSV_LONG_DF_CACHE.empty:
        return _CSV_LONG_DF_CACHE

    try:
        df = _dcg_load_csv_long()
        if df is not None and not df.empty:
            _CSV_LONG_DF_CACHE = df
            _SQLITE_LONG_DF_CACHE = df  # alias
            print(f"[v54-DISPATCH] ✅ CSV long df (doc_bctc_goc v53): {df.shape}")
            return df
    except Exception as e:
        print(f"[v54-DISPATCH] ⚠️ doc_bctc_goc CSV loader fail: {e}")

    print(f"[v54-DISPATCH] ⚠️ Không load được CSV từ doc_bctc_goc — trả về empty")
    _CSV_LONG_DF_CACHE = pd.DataFrame(columns=['ticker', 'metric_name', 'period', 'value'])
    _SQLITE_LONG_DF_CACHE = _CSV_LONG_DF_CACHE
    return _CSV_LONG_DF_CACHE


def _load_sqlite_long_df():
    """[v54-DISPATCH] Alias cũ — gọi CSV loader."""
    return _load_csv_long_df()


# ============================================================================
# [v54-DISPATCH] FALLBACK DASHBOARD RENDER — TƯƠNG THÍCH DỮ LIỆU MỚI
# ============================================================================
def _render_fallback_dashboard(df, ticker, crisis_key=None):
    st.subheader(f"📊 Phân tích {ticker}")

    if crisis_key:
        st.warning(f"⚠️ Đang áp dụng stress test: **{crisis_key}**")

    try:
        if 'ticker' in df.columns:
            sub = df[df['ticker'].astype(str).str.upper() == str(ticker).upper()]
            row = sub.iloc[0] if not sub.empty else df.iloc[0]
        else:
            row = df.iloc[0]

        # [v54] Extract metrics từ v53 (đã bao gồm Snapshot & LNST mẹ)
        metrics = extract_financial_metrics_smart(row, df, ticker)

        c1, c2, c3 = st.columns(3)
        with c1:
            st.metric("💰 Giá hiện tại", format_currency_vn_advanced(metrics.get('gia_hien_tai', 0), per_share=True))
        with c2:
            st.metric("📈 EPS (TTM)", format_eps_value(metrics.get('eps', 0)))
        with c3:
            st.metric("📚 BVPS", format_eps_value(metrics.get('bvps', 0)))

        c1, c2, c3 = st.columns(3)
        with c1:
            st.metric("🔢 P/E", format_pe_pb(metrics.get('pe', 0)))
        with c2:
            st.metric("📊 P/B", format_pe_pb(metrics.get('pb', 0)))
        with c3:
            mc_ty = metrics.get('market_cap_ty', 0)
            st.metric("💎 Vốn hóa", f"{mc_ty:,.2f} Tỷ VNĐ")

        c1, c2, c3 = st.columns(3)
        with c1:
            st.metric("💹 ROE", f"{metrics.get('roe', 0):.2f}%")
        with c2:
            st.metric("📉 ROA", f"{metrics.get('roa', 0):.2f}%")
        with c3:
            st.metric("💵 Cổ tức", format_eps_value(metrics.get('co_tuc_cp', 0)))
            
        # [v54] Hiển thị thêm thông tin Lợi nhuận mới cập nhật (LNST mẹ & LNTT)
        lntt_25 = metrics.get('lntt_2025_ty', 0)
        lnst_25 = metrics.get('lnst_2025_ty', 0)
        if lntt_25 > 0 or lnst_25 > 0:
            st.markdown("---")
            st.markdown("**📊 Lợi nhuận cập nhật (BCTC gốc):**")
            c4, c5 = st.columns(2)
            if lntt_25 > 0:
                c4.metric("LNTT 2025 (tỷ)", f"{lntt_25:,.0f}")
            if lnst_25 > 0:
                c5.metric("LNST mẹ 2025 (tỷ)", f"{lnst_25:,.0f}")

        warnings = metrics.get('sanity_warnings', [])
        if warnings:
            with st.expander("⚠️ Cảnh báo dữ liệu"):
                for w in warnings:
                    st.warning(w)

        if is_bank_ticker(ticker) and metrics.get('bank_revenue'):
            st.info(
                f"🏦 **NII/TOI:** {format_currency_vn(metrics['bank_revenue'])} "
                f"({metrics.get('bank_revenue_source', 'N/A')})"
            )

    except Exception as e:
        st.error(f"❌ Lỗi render: {e}")
        st.code(traceback.format_exc())


# ============================================================================
# [v54-DISPATCH] DEBUG PANEL — HIỂN THỊ CSV & SNAPSHOT
# ============================================================================
def _render_debug_panel(df, ticker):
    with st.sidebar.expander("🔍 Debug Dữ liệu (v54)", expanded=False):
        st.write(f"**Ticker:** {ticker}")
        st.write(f"**Số dòng:** {len(df)}")
        st.write(f"**Số cột:** {len(df.columns)}")

        if _USE_CSV_PRIMARY:
            st.success("✅ Nguồn chính: 3 file CSV gốc")
        else:
            st.warning("⚠️ Nguồn: CSV fallback (vn30_41_fin_long.csv)")

        st.write(f"**Module v35:** {'✅ Có' if _V35_AVAILABLE else '❌ Không (fallback v33)'}")
        st.write(f"**UI module:** {'✅ Có (v54)' if UI_AVAILABLE else '❌ Fallback'}")
        st.write(f"**Crisis module:** {'✅ ' + str(len(HISTORICAL_CRISES)) + ' kịch bản' if HISTORICAL_CRISES else '❌ Fallback'}")

        # [v54] Snapshot info
        st.markdown("**📸 Snapshot 21/10/2026:**")
        st.write(f"  ✅ Đã tải {len(LATEST_MARKET_SNAPSHOT)} mã")
        
        # [v54] CSV files status
        st.markdown("**📁 CSV files:**")
        for _k, _p in _CM_CSV_PATHS.items():
            _e = "✅" if _p and os.path.exists(_p) else "❌"
            _bn = os.path.basename(_p) if _p else "(không tìm thấy)"
            st.write(f"  {_e} `{_bn}`")

        st.markdown(f"**📊 Tickers loaded:** {len(_CM_LOADED_TICKERS)}")
        _bank_count = sum(1 for v in _CM_LOADED_TICKERS.values() if v.get('db') == 'ngan_hang_va_tai_chinh')
        _corp_count = len(_CM_LOADED_TICKERS) - _bank_count
        st.write(f"  🏦 Banks: {_bank_count}")
        st.write(f"  🏢 Corps: {_corp_count}")

        try:
            if 'ticker' in df.columns:
                sub = df[df['ticker'].astype(str).str.upper() == str(ticker).upper()]
                row0 = sub.iloc[0] if not sub.empty else df.iloc[0]
            else:
                row0 = df.iloc[0]
            m = extract_financial_metrics_smart(row0, df, ticker)
            st.markdown("**📊 Metrics đã chuẩn hóa (v53):**")
            st.json({
                'gia_hien_tai': m.get('gia_hien_tai', 0),
                'eps': m.get('eps', 0),
                'bvps': m.get('bvps', 0),
                'co_tuc_cp': m.get('co_tuc_cp', 0),
                'pe': m.get('pe', 0),
                'pb': m.get('pb', 0),
                'market_cap_ty': m.get('market_cap_ty', 0),
                'roe': m.get('roe', 0),
                'shares': m.get('shares', 0),
                'equity_ty': m.get('equity_ty', 0),
                'lntt_2025_ty': m.get('lntt_2025_ty', 0),
                'lnst_2025_ty': m.get('lnst_2025_ty', 0),
            })
        except Exception as e:
            st.error(f"Lỗi extract: {e}")

        st.markdown("**📋 Preview 3 dòng đầu:**")
        try:
            st.dataframe(df.head(3))
        except Exception:
            pass


# ============================================================================
# [v54-DISPATCH] HEADER + FOOTER — GIỮ NGUYÊN 100%
# ============================================================================
def _render_header():
    st.markdown("""
    <div class="header-box">
        <div style="display:flex; flex-direction:column;">
            <div class="header-title">📊 FINEX VN <span>TERMINAL</span></div>
            <div class="header-sub">Hệ Thống Phân Tích & Định Giá Doanh Nghiệp</div>
        </div>
        <div class="header-right">
            <div class="basic-badge">⭐ Gói 99K</div>
            <div class="vip-badge">💎 Gói VIP 299K</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        if st.button(
            "💎 NÂNG CẤP VIP – MỞ KHÓA TOÀN BỘ TÍNH NĂNG",
            use_container_width=True,
            type="primary",
            key="vip_top"
        ):
            try:
                vip_upgrade_dialog()
            except Exception:
                st.info("💎 Liên hệ Zalo 0327 625 853")
    st.markdown("---")


def _render_footer():
    st.markdown("---")
    st.markdown("""
    <div class="zalo-contact-bar">
        <div class="label">📱 Kết nối với chúng tôi</div>
        <div class="zalo-icon">
            <span>💬 Zalo</span>
            <a href="https://zalo.me/0327625853" target="_blank">0327 625 853</a>
        </div>
    </div>
    """, unsafe_allow_html=True)


# ============================================================================
# [v54-DISPATCH] CSV PATH — FALLBACK
# ============================================================================
VN30_LONG_CSV = "du_lieu/vn30_41_fin_long.csv"
if not os.path.exists(VN30_LONG_CSV):
    VN30_LONG_CSV = "vn30_41_fin_long.csv"


# ============================================================================
# [v54-DISPATCH] PERIOD RANK + PIVOT — GIỮ NGUYÊN 100%
# ============================================================================
def _period_rank(p):
    s = str(p).strip().upper()
    m = re.match(r'^(\d{4})H(\d)$', s)
    if m:
        return int(m.group(1)) * 1000 + 500 + int(m.group(2))
    m = re.match(r'^(\d{4})Q(\d)$', s)
    if m:
        return int(m.group(1)) * 1000 + int(m.group(2)) * 10
    m = re.match(r'^(\d{4})$', s)
    if m:
        return int(m.group(1)) * 1000
    return 0


@st.cache_data(ttl=3600, show_spinner=False)
def _load_and_pivot_vn30(csv_path):
    """
    [v54-DISPATCH] CSV FIRST — không còn SQLite.
    Returns: wide df (index=ticker, columns=metric_name).
    """
    long_df = None
    source = "UNKNOWN"

    # ===== 1. CSV 3 industry (qua doc_bctc_goc v53) =====
    try:
        long_df = _load_csv_long_df()
        if long_df is not None and not long_df.empty:
            source = "CSV_3_NHOM"
            print(f"[v54-DISPATCH] ✅ Using CSV 3 nhóm: {len(long_df)} rows")
    except Exception as e:
        print(f"[v54-DISPATCH] ⚠️ CSV 3 nhóm load fail: {e}")
        long_df = None

    # ===== 2. CSV fallback vn30_41_fin_long.csv =====
    if long_df is None or long_df.empty:
        if not csv_path or not os.path.exists(csv_path):
            print(f"[v54-DISPATCH] ❌ Không có CSV nào (3 nhóm + vn30_41)")
            return pd.DataFrame()
        long_df = _v35_load_long_csv(csv_path)
        source = "CSV_VN30_FALLBACK"

    if long_df is None or long_df.empty:
        return pd.DataFrame()

    # ===== 3. Chuẩn hóa + chọn period mới nhất =====
    long_df = long_df.copy()
    if 'period' not in long_df.columns or 'metric_name' not in long_df.columns:
        return long_df

    long_df['_r'] = long_df['period'].apply(_period_rank)
    long_df = long_df.sort_values(['ticker', 'metric_name', '_r'])
    long_df = long_df.drop_duplicates(subset=['ticker', 'metric_name'], keep='last')

    # ===== 4. Pivot =====
    try:
        wide = long_df.pivot(
            index='ticker',
            columns='metric_name',
            values='value',
        ).reset_index()
    except Exception as e:
        print(f"[v54-DISPATCH] ⚠️ pivot lỗi: {e}")
        return pd.DataFrame()

    wide.columns.name = None

    # ===== 5. Convert units (CHỈ cho CSV_VN30_FALLBACK) =====
    # CSV_3_NHOM đã được doc_bctc_goc v53 auto-scale chuẩn
    if source == "CSV_VN30_FALLBACK":
        for col in wide.columns:
            if col == 'ticker':
                continue
            try:
                wide[col] = wide[col].apply(
                    lambda v: _v35_metric_to_ty(v, col) if pd.notna(v) else 0.0
                )
            except Exception as e:
                print(f"[v54-DISPATCH] ⚠️ convert col '{col}' lỗi: {e}")

    print(f"[v54-DISPATCH] ✅ Loaded [{source}]: {wide.shape} | {wide['ticker'].nunique()} tickers")
    return wide


def _load_data_safe(ticker=None):
    """[v54-DISPATCH] Load an toàn."""
    try:
        df = _load_and_pivot_vn30(VN30_LONG_CSV)
    except Exception as e:
        st.error(f"❌ Lỗi load dữ liệu: {e}")
        return pd.DataFrame()

    if df is None or df.empty:
        st.error("❌ Không có dữ liệu CSV")
        st.info("💡 Kiểm tra 3 file CSV trong thư mục gốc hoặc `du_lieu/`:")
        st.markdown("""
        - `du_lieu_cong_nghe.csv`
        - `du_lieu_ngan_hang_va_tai_chinh.csv`
        - `du_lieu_san_xuat_va_khac.csv`
        """)
        return pd.DataFrame()

    try:
        df = sanitize_dataframe(df)
    except Exception as e:
        print(f"[v54-DISPATCH] ⚠️ sanitize_dataframe: {e}")

    return df


# ============================================================================
# [v54-DISPATCH] MAIN — GIỮ NGUYÊN 100% LOGIC
# ============================================================================
def main():
    # Default ticker = first from COMPANY_MAPPING
    if 'selected_ticker' not in st.session_state:
        _default_tk = next(iter(COMPANY_MAPPING.keys())) if COMPANY_MAPPING else 'TCB'
        st.session_state.selected_ticker = _default_tk
    if 'crisis_selected' not in st.session_state:
        st.session_state.crisis_selected = None
    if 'v54_initialized' not in st.session_state:
        st.session_state.v54_initialized = True
        _src_log = "CSV 3 nhóm" if _USE_CSV_PRIMARY else "CSV fallback"
        print(f"[v54-DISPATCH] Session initialized | source={_src_log} | v35={_V35_AVAILABLE}")

    _render_header()

    df_all = _load_data_safe()

    if df_all.empty:
        st.error("❌ Không có dữ liệu. Vui lòng kiểm tra 3 file CSV:")
        st.markdown("""
        - `du_lieu_cong_nghe.csv`
        - `du_lieu_ngan_hang_va_tai_chinh.csv`
        - `du_lieu_san_xuat_va_khac.csv`
        - Hoặc file CSV fallback: `du_lieu/vn30_41_fin_long.csv`
        """)
        st.stop()

    st.sidebar.header("🔍 CHỌN CỔ PHIẾU")

    ticker_options = list(TICKER_DISPLAY)
    if not ticker_options:
        st.error("❌ COMPANY_MAPPING rỗng! Kiểm tra 3 file CSV.")
        st.stop()

    try:
        selected_display = st.sidebar.selectbox(
            "Chọn mã cổ phiếu:",
            ticker_options,
            index=0,
            key="ticker_select",
        )
    except Exception as e:
        st.error(f"❌ Lỗi selectbox: {e}")
        st.stop()

    ticker_short = selected_display.split(" - ")[0].strip()
    st.session_state.selected_ticker = ticker_short

    if ticker_short not in COMPANY_MAPPING:
        st.error(f"❌ Ticker '{ticker_short}' không có trong COMPANY_MAPPING")
        st.stop()

    # Filter df cho ticker hiện tại
    if 'ticker' in df_all.columns:
        df = df_all[df_all['ticker'].astype(str).str.upper() == ticker_short.upper()].copy()
        if df.empty:
            df = df_all.copy()
            if 'ticker' not in df.columns:
                df['ticker'] = ticker_short
    else:
        df = df_all.copy()
        df['ticker'] = ticker_short

    sector = detect_sector(f"{ticker_short.lower()}_financial_statement.csv", selected_display)

    st.session_state.df = df
    st.session_state.ticker_col = 'ticker'
    st.session_state.ticker_short = ticker_short
    st.session_state.sector = sector

    _render_debug_panel(df, ticker_short)

    # ---- Train EPS model ----
    try:
        try:
            eps_model = train_eps_model_advanced(df, forecast_years=10)
        except TypeError:
            eps_model = train_eps_model_advanced(df)
        st.session_state.eps_model_advanced = eps_model if eps_model is not None else None
    except Exception as e:
        print(f"[v54-DISPATCH] ⚠️ train_eps_model_advanced lỗi: {e}")
        st.session_state.eps_model_advanced = None

    # ---- Crisis section ----
    st.sidebar.markdown("---")
    st.sidebar.subheader("📉 STRESS TEST KHỦNG HOẢNG")

    if HISTORICAL_CRISES:
        crisis_options = ["Không chọn (Xem dữ liệu gốc)"] + list(HISTORICAL_CRISES.keys())
    else:
        crisis_options = ["Không chọn (Xem dữ liệu gốc)"]

    try:
        selected_display_crisis = st.sidebar.selectbox(
            "Chọn kịch bản stress test:",
            crisis_options,
            index=0,
            key="crisis_select",
        )
    except Exception:
        selected_display_crisis = crisis_options[0]

    if selected_display_crisis != "Không chọn (Xem dữ liệu gốc)":
        selected_crisis_key = selected_display_crisis
        st.session_state.crisis_selected = selected_crisis_key
    else:
        selected_crisis_key = None
        st.session_state.crisis_selected = None

    df_original = df.copy()
    if selected_crisis_key is not None and selected_crisis_key in HISTORICAL_CRISES:
        try:
            df_stress = apply_crisis_simulation(df_original, selected_crisis_key)
            if df_stress is not None:
                df = df_stress
                st.session_state.df = df
            else:
                st.warning("⚠️ Không thể áp dụng stress test. Giữ nguyên dữ liệu gốc.")
        except Exception as e:
            st.warning(f"⚠️ Stress test lỗi: {e}")

        try:
            render_crisis_section(selected_crisis_key)
        except Exception:
            pass

    try:
        try:
            render_main(df, ticker_short, selected_crisis_key)
        except TypeError:
            render_main(df, ticker_short)
    except Exception as e:
        st.error(f"❌ Lỗi render_main: {e}")
        st.code(traceback.format_exc())
        st.info("🔄 Đang dùng dashboard fallback...")
        _render_fallback_dashboard(df, ticker_short, selected_crisis_key)

    _render_footer()


__all__ = ['main']


if __name__ == "__main__":
    main()
