# finex_vn_terminal.py
# ============================================================================
# FINEX VN TERMINAL — Integrated Upgrade v3 (100% code gốc + Tích hợp CSV tổng hợp)
# Kiến trúc: 7 tabs + 5 modes + full bottom sections
# NEW: Ưu tiên đọc data/vietnam_stock_database_tong_hop.csv trước
# ============================================================================
import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import plotly.express as px
import os
import time
from datetime import datetime
from contextlib import contextmanager
from datetime import timedelta
from decimal import Decimal, ROUND_FLOOR
import json
import math
import threading
import glob as _glob_v50
try:
    import requests
    from requests.adapters import HTTPAdapter
    from urllib3.util.retry import Retry
except Exception:
    requests = None
    HTTPAdapter = Retry = None
try:
    import websocket
except Exception:
    websocket = None
try:
    import psycopg2
    from psycopg2 import pool as _pg_pool
    _HAS_PSYCOPG2 = True
except Exception:
    psycopg2 = None
    _pg_pool = None
    _HAS_PSYCOPG2 = False

st.set_page_config(
    page_title="FINEX VN Terminal - Công Nghệ Định Giá Doanh Nghiệp",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ============================================================================
# OPTIONAL INTEGRATIONS — snapshot, PostgreSQL, safe dataframe rendering
# ============================================================================
try:
    from du_lieu.doc_bctc_goc import (
        LATEST_MARKET_SNAPSHOT,
        get_latest_market_snapshot,
        _apply_latest_market_snapshot,
    )
    _HAS_SNAPSHOT = True
except Exception:
    LATEST_MARKET_SNAPSHOT = {}
    _HAS_SNAPSHOT = False

def get_latest_market_snapshot(ticker):
    return {}

def _apply_latest_market_snapshot(ticker, data):
    return data

def _safe_dataframe(data, **kwargs):
    """Render a dataframe with fallbacks for environments lacking PyArrow."""
    try:
        st.dataframe(data, **kwargs)
        return
    except Exception:
        pass
    try:
        if data is None or (hasattr(data, "empty") and data.empty):
            st.info("Không có dữ liệu để hiển thị.")
            return
        try:
            st.table(data)
            return
        except Exception:
            pass
        if hasattr(data, "to_html"):
            st.markdown(data.to_html(index=False, escape=False), unsafe_allow_html=True)
        else:
            st.write(data)
    except Exception:
        st.write("Không thể hiển thị bảng dữ liệu ở môi trường hiện tại.")

@st.cache_resource(show_spinner=False)
def _get_db_connection_pool():
    """Optional PostgreSQL pool; the app continues without database configuration."""
    if not _HAS_PSYCOPG2:
        return None
    try:
        secrets = getattr(st, "secrets", {})
        def cfg(key, default):
            try:
                return secrets.get(key, os.getenv(key, default))
            except Exception:
                return os.getenv(key, default)
        return _pg_pool.SimpleConnectionPool(
            1, 5,
            host=cfg("DB_HOST", "localhost"),
            database=cfg("DB_NAME", "fintech_group"),
            user=cfg("DB_USER", "postgres"),
            password=cfg("DB_PASS", ""),
            port=cfg("DB_PORT", "5432"),
        )
    except Exception:
        return None

def _fetch_dividend_events(ticker: str, dividend_type: str):
    """Read an ACTIVE dividend event when the optional dividend_events table exists."""
    pool_obj = _get_db_connection_pool()
    if not pool_obj:
        return None
    conn = None
    try:
        conn = pool_obj.getconn()
        with conn.cursor() as cursor:
            cursor.execute(
                """SELECT ticker, dividend_type, cash_per_share, stock_ratio_percent,
                          record_date, payment_date, status, source, updated_at
                   FROM dividend_events
                   WHERE ticker = %s AND dividend_type = %s AND status = 'ACTIVE'
                   ORDER BY record_date DESC LIMIT 1""",
                (str(ticker).upper().strip(), str(dividend_type).upper().strip()),
            )
            row = cursor.fetchone()
            if not row:
                return None
            return pd.DataFrame([row], columns=[d[0] for d in cursor.description])
    except Exception:
        return None
    finally:
        if conn is not None:
            try:
                pool_obj.putconn(conn)
            except Exception:
                pass

@st.cache_resource(show_spinner=False)
def _safe_import_graham():
    """Load the original FINEX Graham/DCF engine when its package exists."""
    try:
        from thuat_toan.dinh_gia_graham import (
            check_signal_filters, get_undervalued_stocks, hybrid_valuation_ensemble,
            calculate_dcf_valuation, run_dcf_scenarios, get_investment_verdict,
        )
        return {
            "loaded": True, "check_signal_filters": check_signal_filters,
            "get_undervalued_stocks": get_undervalued_stocks,
            "hybrid_valuation_ensemble": hybrid_valuation_ensemble,
            "calculate_dcf_valuation": calculate_dcf_valuation,
            "run_dcf_scenarios": run_dcf_scenarios,
            "get_investment_verdict": get_investment_verdict,
        }
    except Exception as exc:
        return {"loaded": False, "reason": str(exc)}

@st.cache_resource(show_spinner=False)
def _safe_import_backtest():
    """Load the original backtest engine only when available."""
    try:
        from lich_su.backtest_chien_luoc import (
            calculate_technical_indicators, run_backtest_vectorbt,
        )
        return {
            "loaded": True, "calculate_technical_indicators": calculate_technical_indicators,
            "run_backtest_vectorbt": run_backtest_vectorbt,
        }
    except Exception as exc:
        return {"loaded": False, "reason": str(exc)}

# ============================================================================
# 1. CONSTANTS
# ============================================================================
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

BANK_ID, ACCOUNT_NO, ACCOUNT_NAME = "VCB", "9327625853", "TRAN ANH QUAN"

PARTNERS = {
    "DNSE": {
        "display_name": "DNSE",
        "full_name": "Công ty Cổ phần Chứng khoán DNSE",
        "strengths": "Nền tảng chứng khoán số tiên phong, giao diện hiện đại, phù hợp nhà đầu tư trẻ.",
        "margin_policy": "Lãi suất Margin cạnh tranh, hạn mức linh hoạt theo danh mục.",
        "referral_code": "064CQUANXZ", "url": "https://s.dnse.vn/eG6Qc8", "color": "#00C853",
    },
    "VPS": {
        "display_name": "VPS",
        "full_name": "Công ty Cổ phần Chứng khoán VPS",
        "strengths": "Thị phần môi giới top 1 Việt Nam, hệ sinh thái sản phẩm đa dạng.",
        "margin_policy": "Hạn mức cho vay (Margin) cực cao, nhiều gói ưu đãi lãi suất.",
        "referral_code": "BW60", "url": "https://openaccount.vps.com.vn/?MKTID=BW60",
        "color": "#C62828",
    },
    "TCBS": {
        "display_name": "TCBS",
        "full_name": "Công ty Cổ phần Chứng khoán Kỹ Thương",
        "strengths": "Nền tảng đầu tư TCInvest hàng đầu, tích hợp ngân hàng Techcombank.",
        "margin_policy": "Lãi suất Margin tối ưu, nhiều sản phẩm trái phiếu.",
        "referral_code": "105C925853",
        "url": "https://tcinvest.tcbs.com.vn/guest/login?openAccount=true&referralcode=105C925853",
        "color": "#1E88E5",
    },
}

VIP_PACKAGES = [
    {"id": "FREE", "name": "🆓 Gói Free", "price": "0 VNĐ", "amount": 0,
     "badge": "Miễn phí", "color": "#64748b",
     "features": ["Xem dữ liệu cơ bản", "1 mã/ngày", "Biểu đồ VN-Index"]},
    {"id": "PKG_29K", "name": "🎓 Gói S-Student", "price": "29.000 VNĐ/tháng",
     "amount": 29000, "badge": "Sinh viên", "color": "#60a5fa",
     "features": ["Full tính năng 30 ngày", "Hỗ trợ mở tài khoản",
                  "Dữ liệu Realtime", "VN30 & HNX30"]},
    {"id": "PKG_59K", "name": "🌱 Gói Basic", "price": "59.000 VNĐ/tháng",
     "amount": 59000, "badge": "Cá nhân", "color": "#22c55e",
     "features": ["Toàn bộ gói 29k", "Stress Test Khủng Hoảng",
                  "Tra cứu 500+ mã", "Biên an toàn Graham"]},
    {"id": "PKG_99K", "name": "🚀 Gói Pro Trader", "price": "99.000 VNĐ/tháng",
     "amount": 99000, "badge": "KHUYÊN DÙNG", "color": "#D4AF37", "featured": True,
     "features": ["Toàn bộ gói 59k", "Định giá đa phương pháp",
                  "Cảnh báo rủi ro", "Xuất PDF", "Hỗ trợ 24/7"]},
    {"id": "PKG_299K", "name": "👑 Gói VIP", "price": "299.000 VNĐ/tháng",
     "amount": 299000, "badge": "Tích sản", "color": "#a855f7",
     "features": ["Toàn bộ gói 99k", "Tối ưu danh mục Python",
                  "Phân tích tương quan", "Telegram Bot"]},
    {"id": "PKG_499K", "name": "💼 Gói Enterprise", "price": "499.000 VNĐ/tháng",
     "amount": 499000, "badge": "Chuyên gia", "color": "#ef4444",
     "features": ["Full đặc quyền", "White-Label báo cáo",
                  "CANSLIM & Fisher", "API dữ liệu"]},
]

HISTORICAL_CRISES = {
    "BASE": {"title": "Kịch bản cơ sở", "source": "FINEX",
             "impact": "Thị trường vận hành theo chu kỳ tự nhiên.",
             "context": {"trigger": "Không có biến cố đặc biệt.",
                         "timeline": [{"period": "2026", "market_impact": "Đỉnh mới 1.774 điểm."}]}},
    "DOTCOM_2000": {"title": "Bong bóng Dot-com (2000-2002)", "source": "Fed History",
                    "impact": "Nasdaq giảm 78%. Hàng trăm công ty dot-com phá sản.",
                    "context": {"trigger": "Định giá công nghệ phi lý.",
                                "timeline": [{"period": "03/2000", "market_impact": "Nasdaq đỉnh 5.048."},
                                             {"period": "10/2002", "market_impact": "Nasdaq đáy 1.114."}]},
                    "fed_actions_and_philosophy": {
                        "core_mission": "Fed hạ lãi suất từ 6.5% xuống 1.75%.",
                        "key_decision": "Cắt giảm mạnh sau 11/9.",
                        "famous_quote": "Irrational exuberance — Alan Greenspan",
                        "market_lesson": "Không có lợi nhuận = bong bóng."},
                    "metrics": {"drawdown_pct": -78.0, "bankruptcies": 500}},
    "GFC_2008": {"title": "Khủng hoảng Tài chính Toàn cầu (2008)", "source": "Fed/Bloomberg",
                 "impact": "S&P 500 giảm 57%. Lehman phá sản. VN-Index giảm 80%.",
                 "context": {"trigger": "Bong bóng BĐS Mỹ + cho vay dưới chuẩn.",
                             "timeline": [{"period": "09/2008", "market_impact": "Lehman phá sản."},
                                          {"period": "03/2009", "market_impact": "S&P 500 đáy 676."}]},
                 "fed_actions_and_philosophy": {
                     "core_mission": "Fed hạ lãi suất về 0-0.25%, QE1.",
                     "key_decision": "Cứu AIG, Bear Stearns.",
                     "famous_quote": "Whatever is necessary — Ben Bernanke",
                     "market_lesson": "Đòn bẩy quá mức + thiếu minh bạch = thảm họa."},
                 "metrics": {"drawdown_pct": -57.0, "vnindex_drop_pct": -80.0}},
    "EU_DEBT_2011": {"title": "Khủng hoảng Nợ công châu Âu (2011)", "source": "ECB/IMF",
                     "impact": "VN-Index giảm 30%. Lạm phát VN 18%, lãi suất 15%.",
                     "context": {"trigger": "Hy Lạp, Ý, Tây Ban Nha vỡ nợ.",
                                 "timeline": [{"period": "07/2011", "market_impact": "Khủng hoảng lan rộng."},
                                              {"period": "12/2011", "market_impact": "VN-Index đáy 351."}]},
                     "fed_actions_and_philosophy": {
                         "core_mission": "ECB mua trái phiếu Ý/Tây Ban Nha.",
                         "key_decision": "Mario Draghi: 'Whatever it takes'.",
                         "famous_quote": "Whatever it takes — Mario Draghi",
                         "market_lesson": "Cam kết mạnh mẽ có thể đảo ngược niềm tin."},
                     "metrics": {"drawdown_pct": -30.0}},
    "COVID_2020": {"title": "Khủng hoảng COVID-19 (2020)", "source": "Bloomberg/SBV",
                   "impact": "VN-Index giảm 34% từ 991 xuống 660. GDP Q2 tăng 0.36%.",
                   "context": {"trigger": "Đại dịch toàn cầu, giãn cách.",
                               "timeline": [{"period": "01/2020", "market_impact": "Ca nhiễm đầu tiên."},
                                            {"period": "03/2020", "market_impact": "VN-Index đáy 660."},
                                            {"period": "12/2020", "market_impact": "Hồi phục 1.103."}]},
                   "fed_actions_and_philosophy": {
                       "core_mission": "Fed hạ lãi suất về 0-0.25%, QE vô hạn.",
                       "key_decision": "Mua trái phiếu & MBS quy mô lớn.",
                       "famous_quote": "Whatever it takes — Jerome Powell",
                       "market_lesson": "Thanh khoản là yếu tố sống còn."},
                   "metrics": {"drawdown_pct": -34.0, "recovery_months": 9}},
    "REAL_ESTATE_2022": {"title": "Khủng hoảng Trái phiếu & BĐS (2022)", "source": "UBCKNN",
                         "impact": "VN-Index giảm 37% từ 1.528 xuống 873.",
                         "context": {"trigger": "Siết tín dụng BĐS, SCB bị kiểm soát.",
                                     "timeline": [{"period": "01/2022", "market_impact": "VN-Index đỉnh 1.528."},
                                                  {"period": "11/2022", "market_impact": "VN-Index đáy 873."}]},
                         "fed_actions_and_philosophy": {
                             "core_dilemma": "Cân bằng ổn định tỷ giá và thanh khoản.",
                             "key_decision": "Hạ lãi suất điều hành 2 lần.",
                             "famous_quote": "Kiểm soát rủi ro hệ thống là ưu tiên.",
                             "market_lesson": "Đừng đánh cược đòn bẩy khi chính sách siết."},
                         "metrics": {"drawdown_pct": -37.0, "bond_defaults": 150}},
    "SVB_2023": {"title": "Khủng hoảng Ngân hàng SVB (2023)", "source": "FDIC/Reuters",
                 "impact": "SVB phá sản — ngân hàng lớn thứ 2 lịch sử Mỹ. VN-Index giảm 8%.",
                 "context": {"trigger": "Fed tăng lãi suất mạnh, danh mục trái phiếu SVB lỗ.",
                             "timeline": [{"period": "03/2023", "market_impact": "SVB sụp đổ 48h."},
                                          {"period": "05/2023", "market_impact": "First Republic bị thâu tóm."}]},
                 "fed_actions_and_philosophy": {
                     "core_mission": "Fed mở BTFP 25 tỷ USD.",
                     "key_decision": "Bảo lãnh 100% tiền gửi SVB.",
                     "famous_quote": "Deposits are safe — Joe Biden",
                     "market_lesson": "Rủi ro lãi suất có thể phá hủy NH trong vài ngày."},
                 "metrics": {"vnindex_drop_pct": -8.0, "svb_assets_billion": 209}},
}

# ============================================================================
# 2. FINANCIAL_DATA_2026 — full fields theo schema gốc
# ============================================================================
def _make_fin_data(**kwargs):
    """Tạo entry FINANCIAL_DATA với đầy đủ metadata defaults."""
    base = {
        "price": 0, "market_cap": 0, "shares_outstanding": 0,
        "eps_ttm": 0, "pe_ttm": 0, "pb": 0, "bvps": 0,
        "roe_2025": 0, "roa_2025": 0, "margin": 0, "de": 0,
        "total_assets_30062026": 0, "equity": 0,
        "toi_6t2026": 0, "lntt_6t2026": 0,
        "lnst_6t2026": 0, "lnst_2024": 0, "lnst_2025": 0,
        "growth_2025_2024": 0, "div_per_share": 0, "div_yield": 0,
        "price_as_of": "2026-10-22", "price_stale_days": 1,
        "price_is_stale": False, "price_is_missing": False,
        "shares_is_official": True, "shares_is_estimated": False,
        "shares_is_provisional": False,
        "shares_basis": "official", "shares_as_of": "2026-06-30",
        "snapshot_as_of": "2026-10-22",
        "_snapshot_source": True, "_snapshot_note": "",
    }
    base.update(kwargs)
    return base

# ==========================================================================
# === NEW INTEGRATION v3: Ưu tiên đọc data/vietnam_stock_database_tong_hop.csv
# Thứ tự ưu tiên:
#   1. data/vietnam_stock_database_tong_hop.csv (local tổng hợp)
#   2. FINEX_DATA_URL (env - raw GitHub URL)
#   3. GitHub API → finex_financial_data.csv
#   4. Local fallback: finex_financial_data.csv
# ==========================================================================
_FINEX_LONG_DF = pd.DataFrame()
_FINEX_DATA_SOURCE = "Chưa kết nối được dữ liệu"
_FINEX_DATA_ERROR = ""

GITHUB_OWNER = os.getenv("FINEX_GITHUB_OWNER", "trananhhquan2122001")
GITHUB_REPO = os.getenv("FINEX_GITHUB_REPO", "Fintech-Group")
GITHUB_BRANCH = os.getenv("FINEX_GITHUB_BRANCH", "main")
GITHUB_DATA_FILENAME = os.getenv("FINEX_GITHUB_DATA_FILENAME", "finex_financial_data.csv")

# Đường dẫn ưu tiên 1: file tổng hợp local
TONG_HOP_FILENAME = os.getenv(
    "FINEX_TONG_HOP_FILENAME",
    "data/vietnam_stock_database_tong_hop.csv"
)

# Các tên file tổng hợp có thể gặp (linh hoạt cho nhiều cách đặt tên)
_TONG_HOP_ALIASES = [
    "data/vietnam_stock_database_tong_hop.csv",
    "vietnam_stock_database_tong_hop.csv",
    "data/tong_hop.csv",
    "tong_hop.csv",
    "data/vietnam_stock_database.csv",
    "vietnam_stock_database.csv",
]

REQUIRED_STANDARD_COLS = {"Mã chứng khoán", "Loại báo cáo", "Năm",
                          "Chỉ tiêu tiếng Việt", "Giá trị"}


def _try_read_csv(source_path_or_url, label, timeout=30):
    """Đọc CSV từ URL hoặc local path, trả về (DataFrame, error_msg)."""
    import io
    try:
        if source_path_or_url.startswith(("http://", "https://")):
            import urllib.request
            req = urllib.request.Request(
                source_path_or_url,
                headers={"User-Agent": "FINEX-VN-Terminal/3.0"}
            )
            with urllib.request.urlopen(req, timeout=timeout) as response:
                raw = response.read()
        else:
            if not os.path.isfile(source_path_or_url):
                return pd.DataFrame(), f"File không tồn tại: {source_path_or_url}"
            with open(source_path_or_url, "rb") as f:
                raw = f.read()

        # Thử nhiều encoding
        for enc in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
            try:
                frame = pd.read_csv(io.BytesIO(raw), low_memory=False, encoding=enc)
                break
            except UnicodeDecodeError:
                continue
        else:
            return pd.DataFrame(), f"{label}: không decode được với bất kỳ encoding nào"

        return frame, ""
    except Exception as exc:
        return pd.DataFrame(), f"{label}: {exc}"


def _normalize_to_standard_schema(frame, label):
    """
    Chuyển đổi DataFrame từ nhiều schema khả dĩ về schema chuẩn:
    ['Mã chứng khoán', 'Loại báo cáo', 'Năm', 'Chỉ tiêu tiếng Việt', 'Giá trị']
    """
    if frame is None or frame.empty:
        return pd.DataFrame(), f"{label}: DataFrame rỗng"

    cols_lower = {str(c).strip().lower(): c for c in frame.columns}

    # Mapping các tên cột có thể gặp → tên chuẩn
    col_map = {}
    ticker_aliases = ["mã chứng khoán", "ticker", "symbol", "ma", "mã", "Mã CK"]
    report_aliases = ["loại báo cáo", "report_type", "loại bc", "report"]
    year_aliases = ["năm", "year", "yr"]
    indicator_aliases = ["chỉ tiêu tiếng việt", "indicator", "chỉ tiêu",
                         "ten_chi_tieu", "chỉ tiêu vn", "metric"]
    value_aliases = ["giá trị", "value", "giá tri", "so_lieu", "value_vnd"]

    def _find(aliases):
        for a in aliases:
            if a in cols_lower:
                return cols_lower[a]
        # Tìm gần đúng (contains)
        for a in aliases:
            for k, orig in cols_lower.items():
                if a in k or k in a:
                    return orig
        return None

    ticker_col = _find(ticker_aliases)
    report_col = _find(report_aliases)
    year_col = _find(year_aliases)
    indicator_col = _find(indicator_aliases)
    value_col = _find(value_aliases)

    # Nếu đã có đủ cột chuẩn → dùng luôn
    if REQUIRED_STANDARD_COLS.issubset(set(frame.columns)):
        out = frame.copy()
    elif ticker_col and indicator_col and value_col:
        out = pd.DataFrame()
        out["Mã chứng khoán"] = frame[ticker_col]
        out["Chỉ tiêu tiếng Việt"] = frame[indicator_col]
        out["Giá trị"] = frame[value_col]
        out["Loại báo cáo"] = frame[report_col] if report_col else "Q4"
        out["Năm"] = frame[year_col] if year_col else datetime.now().year
    else:
        return pd.DataFrame(), (
            f"{label}: không tìm thấy cột ticker/indicator/value. "
            f"Cột hiện có: {list(frame.columns)[:10]}"
        )

    # Chuẩn hóa
    out["Mã chứng khoán"] = out["Mã chứng khoán"].astype(str).str.upper().str.strip()
    out["Năm"] = pd.to_numeric(out["Năm"], errors="coerce")
    out["Giá trị"] = pd.to_numeric(out["Giá trị"], errors="coerce")
    out = out.dropna(subset=["Mã chứng khoán", "Năm", "Giá trị"])
    out = out[out["Mã chứng khoán"].str.fullmatch(r"[A-Z0-9]{3,5}", na=False)]

    if out.empty:
        return pd.DataFrame(), f"{label}: không có dòng dữ liệu hợp lệ sau khi lọc"
    return out, ""


@st.cache_data(ttl=300, show_spinner=False)
def _load_financial_data_source():
    """
    NEW v3: Loader với thứ tự ưu tiên:
      1. data/vietnam_stock_database_tong_hop.csv (local)
      2. FINEX_DATA_URL (env)
      3. GitHub API → finex_financial_data.csv
      4. Local fallback: finex_financial_data.csv
    """
    errors = []

    # ==================== ƯU TIÊN 1: File tổng hợp local ====================
    tong_hop_candidates = []
    env_tong_hop = os.getenv("FINEX_TONG_HOP_FILENAME", "").strip()
    if env_tong_hop:
        tong_hop_candidates.append(env_tong_hop)
    tong_hop_candidates.extend(_TONG_HOP_ALIASES)
    # Thêm đường dẫn tuyệt đối từ thư mục script
    script_dir = os.path.dirname(os.path.abspath(__file__))
    for rel in list(_TONG_HOP_ALIASES):
        abs_path = os.path.join(script_dir, rel)
        if abs_path not in tong_hop_candidates:
            tong_hop_candidates.append(abs_path)

    for candidate in dict.fromkeys(tong_hop_candidates):
        if os.path.isfile(candidate):
            frame, err = _try_read_csv(candidate, f"Local-tong-hop:{candidate}")
            if not frame.empty:
                norm, norm_err = _normalize_to_standard_schema(frame, f"Local-tong-hop:{candidate}")
                if not norm.empty:
                    return norm, f"✅ Local tổng hợp: {candidate}", ""
                errors.append(norm_err)
            else:
                errors.append(err)

    # ==================== ƯU TIÊN 2: FINEX_DATA_URL (env) ====================
    configured_url = os.getenv("FINEX_DATA_URL", "").strip()
    if configured_url:
        frame, err = _try_read_csv(configured_url, "FINEX_DATA_URL")
        if not frame.empty:
            norm, norm_err = _normalize_to_standard_schema(frame, "FINEX_DATA_URL")
            if not norm.empty:
                return norm, f"✅ FINEX_DATA_URL: {configured_url}", ""
            errors.append(norm_err)
        else:
            errors.append(err)

    # ==================== ƯU TIÊN 3: GitHub API → finex_financial_data.csv ====================
    import io
    import json
    import urllib.request

    def fetch_url(url, timeout=30):
        req = urllib.request.Request(url, headers={"User-Agent": "FINEX-VN-Terminal/3.0"})
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return response.read()

    tree_url = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/git/trees/{GITHUB_BRANCH}?recursive=1"
    try:
        tree = json.loads(fetch_url(tree_url, timeout=20).decode("utf-8"))
        matches = [
            x["path"] for x in tree.get("tree", [])
            if x.get("type") == "blob"
            and x.get("path", "").split("/")[-1].lower() == GITHUB_DATA_FILENAME.lower()
        ]
        if matches:
            matches.sort(key=lambda p: (
                0 if any(part.lower() in ("data", "output", "datasets") for part in p.split("/")) else 1,
                len(p)
            ))
            path = matches[0]
            raw_url = f"https://raw.githubusercontent.com/{GITHUB_OWNER}/{GITHUB_REPO}/{GITHUB_BRANCH}/{path}"
            frame, err = _try_read_csv(raw_url, f"GitHub:{path}")
            if not frame.empty:
                norm, norm_err = _normalize_to_standard_schema(frame, f"GitHub:{path}")
                if not norm.empty:
                    return norm, f"✅ GitHub:{path}", ""
                errors.append(norm_err)
            else:
                errors.append(err)
        else:
            errors.append(f"Không tìm thấy {GITHUB_DATA_FILENAME} trong repo {GITHUB_OWNER}/{GITHUB_REPO}/{GITHUB_BRANCH}")
    except Exception as exc:
        errors.append(f"GitHub API: {exc}")

    # ==================== ƯU TIÊN 4: Local fallback finex_financial_data.csv ====================
    local_names = (GITHUB_DATA_FILENAME, "finex_financial_data.csv")
    for name in dict.fromkeys(local_names):
        local = os.path.join(script_dir, name)
        if os.path.isfile(local):
            frame, err = _try_read_csv(local, f"Local-fallback:{name}")
            if not frame.empty:
                norm, norm_err = _normalize_to_standard_schema(frame, f"Local-fallback:{name}")
                if not norm.empty:
                    return norm, f"✅ Local fallback: {name}", ""
                errors.append(norm_err)
            else:
                errors.append(err)

    return pd.DataFrame(), "❌ Không có nguồn CSV hợp lệ", "; ".join(errors)


def _norm_indicator(value):
    import unicodedata
    value = unicodedata.normalize("NFKD", str(value or "").lower())
    return "".join(ch for ch in value if not unicodedata.combining(ch)).replace("đ", "d")


def _build_data_from_scraper(frame):
    """Map actual scraped report indicators to terminal schema; absent fields stay 0/N/A."""
    if frame is None or frame.empty:
        return {}
    aliases = {
        "price": ["gia dong cua", "gia co phieu", "gia thi truong", "close"],
        "eps_ttm": ["eps", "lai co ban tren co phieu", "thu nhap tren moi co phieu"],
        "bvps": ["bvps", "gia tri so sach tren moi co phieu"],
        "shares_outstanding": ["so luong co phieu pho thong", "co phieu dang luu hanh", "co phieu da phat hanh"],
        "total_assets_30062026": ["tong tai san"],
        "equity": ["von chu so huu", "tong von chu so huu"],
        "lnst_2025": ["loi nhuan sau thue", "loi nhuan sau thue thu nhap doanh nghiep"],
        "lntt_6t2026": ["loi nhuan truoc thue"],
        "roe_2025": ["roe", "ty suat loi nhuan tren von chu so huu"],
        "roa_2025": ["roa", "ty suat loi nhuan tren tong tai san"],
        "div_per_share": ["co tuc tren moi co phieu", "co tuc bang tien"],
        "market_cap": ["von hoa thi truong", "gia tri von hoa"],
        "net_income": ["loi nhuan sau thue"],
        "revenue": ["doanh thu thuan", "tong doanh thu"],
        "operating_cash_flow": ["luu chuyen tien thuan tu hoat dong kinh doanh"],
        "capex": ["chi mua sam tai san co dinh", "mua sam xay dung tai san co dinh"],
    }
    normalized = frame["Chỉ tiêu tiếng Việt"].map(_norm_indicator)
    result = {}
    for ticker, group in frame.groupby("Mã chứng khoán", sort=True):
        years = sorted(group["Năm"].dropna().astype(int).unique())
        latest_year = years[-1] if years else datetime.now().year
        latest = group[group["Năm"] == latest_year]
        data = _make_fin_data(
            industry=str(group["Tên ngành"].dropna().iloc[0])
            if "Tên ngành" in group and group["Tên ngành"].notna().any()
            else "Chưa phân loại"
        )
        data["source"] = "scraper_csv"
        data["source_year"] = latest_year
        for field, names in aliases.items():
            matched = latest[normalized.loc[latest.index].apply(
                lambda x: any(_norm_indicator(n) in x for n in names)
            )]
            if matched.empty:
                continue
            row = matched.iloc[-1]
            value = float(row["Giá trị"])
            if field in ("total_assets_30062026", "equity", "lnst_2025", "lntt_6t2026",
                         "market_cap", "net_income", "revenue",
                         "operating_cash_flow", "capex") and abs(value) >= 1e9:
                value /= 1e9
            data[field] = value
        if data.get("price", 0) > 0 and data.get("eps_ttm", 0) > 0:
            data["pe_ttm"] = data["price"] / data["eps_ttm"]
        if data.get("price", 0) > 0 and data.get("bvps", 0) > 0:
            data["pb"] = data["price"] / data["bvps"]
        if data.get("shares_outstanding", 0) > 0 and data.get("price", 0) > 0:
            data["market_cap"] = data["shares_outstanding"] * data["price"] / 1e9
        result[ticker] = data
    return result


# === GỌI LOADER MỚI v3 ===
_FINEX_LONG_DF, _FINEX_DATA_SOURCE, _FINEX_DATA_ERROR = _load_financial_data_source()
_SCRAPED_FINANCIAL_DATA = _build_data_from_scraper(_FINEX_LONG_DF)

FINANCIAL_DATA_2026 = _SCRAPED_FINANCIAL_DATA
COMPANY_INFO = {ticker: {"name": ticker, "exchange": "Chưa xác định"}
                for ticker in FINANCIAL_DATA_2026}
ALL_TICKERS = sorted(FINANCIAL_DATA_2026.keys())
EXPECTED_SOURCE_TICKERS = 102
_FINEX_TICKER_COUNT_OK = len(ALL_TICKERS) == EXPECTED_SOURCE_TICKERS


def get_financial_data(ticker):
    """Return only scraper CSV values; never enrich with demo/snapshot fallback."""
    key = str(ticker or "").upper().strip()
    return dict(FINANCIAL_DATA_2026.get(key, {}) or {})


# ============================================================================
# (Phần còn lại giữ NGUYÊN 100% code gốc)
# ============================================================================

def _capital_scenarios(market_price, cash_per_share, tax_rate=0):
    if market_price <= 0:
        return pd.DataFrame()
    rows = []
    for capital in range(MIN_CAPITAL_VND, MAX_CAPITAL_VND + 1, CAPITAL_STEP_VND):
        shares = _buyable_shares(capital, market_price)
        divs = _cash_dividend_actual(shares, cash_per_share, tax_rate)
        rows.append({
            "Vốn đầu tư (VNĐ)": capital, "Giá thị trường (VNĐ)": market_price,
            "Số cổ phiếu mua được": shares, "Cổ tức/CP (VNĐ)": cash_per_share,
            "Cổ tức trước thuế (VNĐ)": divs["before_tax"],
            "Thuế TNCN (VNĐ)": divs["tax"], "Cổ tức sau thuế (VNĐ)": divs["after_tax"],
        })
    return pd.DataFrame(rows)


def _stock_scenarios(shares):
    if shares <= 0:
        return pd.DataFrame()
    return pd.DataFrame([
        {"Số cổ phiếu ban đầu": shares, "Tỷ lệ cổ tức (%)": ratio,
         "Cổ phiếu nhận thêm": _stock_dividend(shares, ratio)["additional_shares"],
         "Tổng cổ phiếu sau phát hành": _stock_dividend(shares, ratio)["total_after"]}
        for ratio in range(MIN_DIVIDEND_PERCENT, MAX_DIVIDEND_PERCENT + 1, DIVIDEND_PERCENT_STEP)
    ])

VNINDEX_MILESTONES = [
    ("2000-07-28", 100), ("2001-06-30", 571), ("2003-10-31", 130),
    ("2005-12-30", 307), ("2007-03-12", 1170), ("2009-02-20", 235),
    ("2012-12-28", 413), ("2018-04-09", 1204), ("2020-03-24", 660),
    ("2022-01-06", 1528), ("2022-11-15", 873), ("2024-12-31", 1266),
    ("2026-10-22", 1774.15),
]

# ============================================================================
# 3. CSS — Dark theme, fix lỗi nền trắng/chữ trắng
# ============================================================================
def inject_css():
    st.markdown("""
<style>
html, body, [class*="css"] {
font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Inter", sans-serif;
font-feature-settings: "tnum" 1;
}
.stApp {
background: radial-gradient(ellipse at top left, rgba(56,189,248,.13) 0%, transparent 45%),
radial-gradient(ellipse at top right, rgba(250,204,21,.10) 0%, transparent 45%),
linear-gradient(180deg, #101827 0%, #111c2e 50%, #0f172a 100%) !important;
color: #e2e8f0 !important;
}
.main .block-container { padding-top: 1.2rem; max-width: 1560px; }
h1 { color: #7dd3fc !important; font-weight: 800 !important; font-size: 1.85em !important; }
h2 { color: #bae6fd !important; border-bottom: 1px solid #334155;
padding-bottom: 8px; font-weight: 700 !important; }
h3 { color: #bfdbfe !important; font-weight: 700 !important; font-size: 1.22em !important; }
h4, h5, h6 { color: #dbeafe !important; font-weight: 700 !important; }
.stMarkdown, .stMarkdown p, .stMarkdown span, p, label { color: #e2e8f0 !important; }
.stCaption, [data-testid="stCaptionContainer"] { color: #cbd5e1 !important; }
[data-baseweb="select"] > div, [data-baseweb="input"] > div,
[data-testid="stNumberInput"] input, [data-testid="stTextInput"] input {
background-color: #172338 !important; color: #f8fafc !important;
border-color: #64748b !important;
}
.stButton > button, [data-testid="stDownloadButton"] > button {
border-radius: 9px !important; border: 1px solid #64748b !important;
font-weight: 650 !important;
}
.stButton > button[kind="primary"] {
background: linear-gradient(135deg,#0ea5e9,#2563eb) !important;
color: #ffffff !important; border: 0 !important;
}
[data-testid="stMetric"] {
background: linear-gradient(145deg, #24344d 0%, #172338 100%);
border: 1px solid #475569; border-left: 3px solid #FACC15;
border-radius: 10px; padding: 14px 16px;
box-shadow: 0 2px 10px rgba(0,0,0,.45);
transition: all .2s ease;
}
[data-testid="stMetric"]:hover {
border-left-color: #F5D97A;
box-shadow: 0 4px 16px rgba(212,175,55,.25);
transform: translateY(-1px);
}
[data-testid="stMetricLabel"] {
color: #94a3b8 !important; font-size: .82em !important;
text-transform: uppercase; letter-spacing: .6px; font-weight: 600 !important;
}
[data-testid="stMetricValue"] {
color: #F5D97A !important; font-size: 1.65em !important;
font-weight: 700 !important; font-variant-numeric: tabular-nums;
}
.stTabs [data-baseweb="tab-list"] {
gap: 4px; background: #0a1220; padding: 6px;
border-radius: 12px; border: 1px solid #1f2937; margin-bottom: 12px;
}
.stTabs [data-baseweb="tab"] {
height: 42px; background: transparent; border-radius: 8px;
color: #94a3b8 !important; font-weight: 600 !important;
font-size: 14px !important; padding: 0 18px !important;
}
.stTabs [data-baseweb="tab"]:hover { background: #1a2538; color: #f3f4f6 !important; }
.stTabs [aria-selected="true"] {
background: linear-gradient(135deg, #1e3a5f 0%, #16223a 100%) !important;
color: #F5D97A !important; border-bottom: 2px solid #D4AF37 !important;
}
.stButton > button {
background: linear-gradient(135deg, #1a2538 0%, #111c2e 100%) !important;
color: #e2e8f0 !important; border: 1px solid #2a3a5c !important;
border-radius: 8px !important; font-weight: 600 !important;
padding: 8px 16px !important; transition: all .18s ease !important;
}
.stButton > button:hover {
background: linear-gradient(135deg, #1e3a5f 0%, #16223a 100%) !important;
border-color: #D4AF37 !important; color: #F5D97A !important;
transform: translateY(-1px);
box-shadow: 0 4px 14px rgba(212,175,55,.25);
}
.stButton > button[kind="primary"] {
background: linear-gradient(135deg, #D4AF37 0%, #B8912A 100%) !important;
color: #0a0f19 !important; border: none !important; font-weight: 700 !important;
}
section[data-testid="stSidebar"] {
background: linear-gradient(180deg, #050914 0%, #0a0f19 100%) !important;
border-right: 1px solid #1f2937;
}
section[data-testid="stSidebar"] * { color: #e2e8f0 !important; }
section[data-testid="stSidebar"] h1,
section[data-testid="stSidebar"] h2,
section[data-testid="stSidebar"] h3 { color: #93c5fd !important; }
div[data-baseweb="select"] { background-color: #1a2538 !important; }
div[data-baseweb="select"] > div,
div[data-baseweb="select"] > div > div {
background-color: #1a2538 !important; color: #ffffff !important;
border: 1px solid #374151 !important; border-radius: 8px !important;
}
div[data-baseweb="select"] span,
div[data-baseweb="select"] input,
div[data-baseweb="select"] div[role="button"] {
color: #ffffff !important; -webkit-text-fill-color: #ffffff !important;
}
div[data-baseweb="select"] svg { fill: #D4AF37 !important; }
[data-testid="stSelectbox"] label { color: #cbd5e1 !important; font-weight: 600 !important; }
[data-baseweb="popover"] { background-color: #1a2538 !important; }
[data-baseweb="popover"] *, [data-baseweb="menu"], [role="listbox"] {
background-color: #1a2538 !important; color: #f3f4f6 !important;
}
[role="option"] {
background-color: #1a2538 !important; color: #e2e8f0 !important;
padding: 8px 12px !important;
}
[role="option"]:hover, [aria-selected="true"] {
background-color: #1e3a5f !important; color: #F5D97A !important;
}
section[data-testid="stSidebar"] .stRadio > div { gap: 4px; }
section[data-testid="stSidebar"] .stRadio label {
background: #0a1220 !important; border: 1px solid #1f2937 !important;
border-radius: 8px !important; padding: 8px 12px !important;
margin: 2px 0 !important; transition: all .15s ease !important;
}
section[data-testid="stSidebar"] .stRadio label:hover {
background: #1a2538 !important; border-color: #D4AF37 !important;
}
input, textarea,
[data-testid="stTextInput"] input,
[data-testid="stNumberInput"] input {
background-color: #1a2538 !important; color: #ffffff !important;
border: 1px solid #374151 !important; border-radius: 8px !important;
}
[data-testid="stExpander"] {
background-color: #0a1220 !important; border: 1px solid #1f2937 !important;
border-radius: 10px !important;
}
[data-testid="stExpander"] summary {
background-color: #1a2538 !important; color: #f3f4f6 !important;
font-weight: 600 !important;
}
.dataframe { background-color: #0a1220 !important; border-radius: 8px; }
.dataframe thead th {
background: #16223a !important; color: #F5D97A !important;
font-weight: 700 !important; text-transform: uppercase;
font-size: 12px !important;
}
.dataframe td, .dataframe th {
color: #e2e8f0 !important; border-bottom: 1px solid #1f2937 !important;
}
.terminal-header {
background: linear-gradient(135deg, #0a0f19 0%, #1a2538 100%);
border: 1px solid #1f2937; border-top: 3px solid #D4AF37;
border-radius: 12px; padding: 18px 24px; margin-bottom: 16px;
box-shadow: 0 4px 16px rgba(0,0,0,.5);
}
.terminal-header h1 {
background: linear-gradient(90deg, #F5D97A 0%, #60a5fa 100%);
-webkit-background-clip: text; -webkit-text-fill-color: transparent;
background-clip: text; margin: 0;
}
.glass-card {
background: linear-gradient(145deg, #1a2538 0%, #111827 100%);
border: 1px solid #334155; border-radius: 12px;
padding: 16px; margin: 8px 0;
box-shadow: 0 3px 12px rgba(0,0,0,.4); color: #e2e8f0;
}
.hybrid-card {
background: linear-gradient(145deg, #111827 0%, #16223a 100%);
border: 1px solid #2a3a5c; border-left: 4px solid #D4AF37;
border-radius: 12px; padding: 18px 20px; margin: 10px 0;
color: #e2e8f0;
}
.recommend-badge { padding: 5px 14px; border-radius: 14px;
font-weight: 700; font-size: .9em; }
.rec-buy  { background: #0a2e1a; color: #22c55e; border: 1px solid #22c55e; }
.rec-hold { background: #3a2a0a; color: #f59e0b; border: 1px solid #f59e0b; }
.rec-sell { background: #2a0a0a; color: #ef4444; border: 1px solid #ef4444; }
.broker-container {
background: linear-gradient(135deg, #0d1b2e 0%, #111827 100%);
border: 2px solid #D4AF37; border-radius: 14px;
padding: 18px 22px; margin-bottom: 16px;
box-shadow: 0 8px 24px rgba(212,175,55,.15);
}
.broker-container .broker-title {
color: #F5D97A !important; -webkit-text-fill-color: #F5D97A !important;
font-size: 15px; font-weight: 800; margin-bottom: 14px;
letter-spacing: .5px; text-transform: uppercase;
}
.broker-container .broker-note {
color: #cbd5e1 !important; -webkit-text-fill-color: #cbd5e1 !important;
font-size: 12.5px; margin-top: 12px;
}
.broker-container [data-testid="stButton"] button {
background: linear-gradient(135deg, #111827 0%, #0a0f19 100%) !important;
color: #F5D97A !important; border: 2px solid #D4AF37 !important;
font-weight: 700 !important;
}
.broker-container [data-testid="stButton"] button:hover {
background: linear-gradient(135deg, #D4AF37 0%, #B8912A 100%) !important;
color: #0a0f19 !important;
}
.cta-banner {
background: linear-gradient(135deg, #D4AF37 0%, #B8912A 50%, #D4AF37 100%);
border-radius: 16px; padding: 22px 28px; margin: 20px 0;
box-shadow: 0 8px 28px rgba(212,175,55,.35);
}
.footer-hero {
background: linear-gradient(135deg, #0a0f19 0%, #1a2538 100%);
border: 1px solid #D4AF37; border-radius: 16px;
padding: 28px 32px; margin: 30px 0 20px 0;
text-align: center;
}
.footer-section-title {
color: #F5D97A !important; font-size: 1.1em; font-weight: 800;
margin-bottom: 12px; text-transform: uppercase; letter-spacing: 1.2px;
}
.footer-divider {
height: 1px; background: linear-gradient(90deg, transparent, #D4AF37, transparent);
margin: 24px 0;
}
.vip-card {
background: linear-gradient(145deg, #1a2538 0%, #111827 100%);
border: 1px solid #334155; border-radius: 16px;
padding: 20px 16px; height: 100%;
transition: all .25s ease;
}
.vip-card:hover {
border-color: #D4AF37;
box-shadow: 0 8px 24px rgba(212,175,55,.25);
transform: translateY(-4px);
}
.vip-card.featured {
border: 2px solid #D4AF37;
background: linear-gradient(145deg, #1f2f47 0%, #111827 100%);
}
::-webkit-scrollbar { width: 10px; height: 10px; }
::-webkit-scrollbar-track { background: #050914; }
::-webkit-scrollbar-thumb { background: #374151; border-radius: 6px; }
::-webkit-scrollbar-thumb:hover { background: #D4AF37; }
.stLinkButton a {
background: linear-gradient(135deg, #1a2538 0%, #111c2e 100%) !important;
color: #F5D97A !important; border: 1px solid #D4AF37 !important;
border-radius: 8px !important; font-weight: 600 !important;
}
.stLinkButton a:hover {
background: linear-gradient(135deg, #D4AF37 0%, #B8912A 100%) !important;
color: #0a0f19 !important;
}
[data-testid="stAlert"] {
background-color: #1a2538 !important; border-left-width: 4px !important;
}
[data-testid="stAlert"] * { color: #e2e8f0 !important; }
</style>
""", unsafe_allow_html=True)

# ============================================================================
# 4. PROFILER
# ============================================================================
_PROFILE = {}

@contextmanager
def prof(name):
    t0 = time.perf_counter()
    try:
        yield
    finally:
        _PROFILE[name] = (time.perf_counter() - t0) * 1000

def render_profiler_panel():
    with st.sidebar:
        with st.expander("🔬 Profiler — Tốc độ", expanded=False):
            if not _PROFILE:
                st.caption("Chưa có dữ liệu"); return
            sorted_log = sorted(_PROFILE.items(), key=lambda x: -x[1])
            total = sum(_PROFILE.values())
            st.caption(f"⏱️ Tổng: **{total:,.0f} ms**")
            for name, ms in sorted_log[:12]:
                icon = "🐌" if ms > 500 else ("⚠️" if ms > 200 else "✅")
                st.caption(f"{icon} {name}: {ms:.0f}ms")
            if st.button("🔄 Reset", key="prof_reset", use_container_width=True):
                _PROFILE.clear(); st.rerun()

# ============================================================================
# 5. HELPERS
# ============================================================================
def _fmt_ty(v):
    try: v = float(v or 0)
    except Exception: return "N/A"
    if v == 0: return "0 tỷ"
    if abs(v) >= 1000: return f"{v/1000:,.2f} nghìn tỷ"
    return f"{v:,.0f} tỷ"

def _fmt_vnd(v):
    try: return f"{int(v):,}".replace(",", ".")
    except Exception: return "0"

def _fmt_shares(v):
    try: return f"{int(v):,}".replace(",", ".")
    except Exception: return "0"

def _buyable_shares(capital, price):
    if price <= 0 or capital < 0: return 0
    return int(capital // price)

def _cash_dividend_actual(shares, cash_ps, tax_rate=0):
    if shares <= 0 or cash_ps <= 0:
        return {"before_tax": 0, "tax": 0, "after_tax": 0}
    before = shares * cash_ps
    tax = before * tax_rate / 100
    return {"before_tax": before, "tax": tax, "after_tax": before - tax}

def _stock_dividend(shares, ratio):
    if shares <= 0 or ratio <= 0:
        return {"additional_shares": 0, "total_after": shares}
    add = int(shares * ratio / 100)
    return {"additional_shares": add, "total_after": shares + add}

# ============================================================================
# 6. VALUATION CORE
# ============================================================================
def compute_hybrid_valuation(price, eps, bvps, roe, roa):
    graham = (22.5 * eps * bvps) ** 0.5 if (eps > 0 and bvps > 0) else 0
    dcf = eps * 1.08 / 0.04 if eps > 0 else 0
    pe_band = eps * 15 if eps > 0 else 0
    pb_band = bvps * 1.5 if bvps > 0 else 0
    if roe >= 20 and roa >= 10: w = {"graham": .15, "dcf": .40, "pe": .30, "pb": .15}
    elif roe >= 15 and roa >= 7: w = {"graham": .25, "dcf": .30, "pe": .25, "pb": .20}
    elif roe >= 10 and roa >= 4: w = {"graham": .35, "dcf": .20, "pe": .20, "pb": .25}
    else: w = {"graham": .45, "dcf": .10, "pe": .15, "pb": .30}
    total, used_w = 0.0, 0.0
    for k, val in [("graham", graham), ("dcf", dcf), ("pe", pe_band), ("pb", pb_band)]:
        if val > 0: total += val * w[k]; used_w += w[k]
    hybrid = total / used_w if used_w > 0 else 0
    mos = ((hybrid - price) / hybrid * 100) if hybrid > 0 else 0
    mos = max(-100.0, min(100.0, mos))
    return {"hybrid": round(hybrid, 0), "graham": round(graham, 0),
            "dcf": round(dcf, 0), "pe_band": round(pe_band, 0),
            "pb_band": round(pb_band, 0), "weights": w, "mos": round(mos, 1)}

def _simple_dcf_valuation(ticker, data):
    if not data: return {"error": "Không có dữ liệu."}
    try:
        profit = float(data.get("lnst_2025", 0) or data.get("lnst_6t2026", 0) or 0)
        shares = float(data.get("shares_outstanding", 0) or 0)
        price = float(data.get("price", 0) or 0)
        if profit <= 0 or shares <= 0:
            return {"error": "Thiếu LNST hoặc SLCP."}
        growth, terminal_g = 0.08, 0.03
        wacc = 0.03 + 1.0 * 0.07
        def _scenario(mult):
            g = growth * mult
            fcff = [profit * ((1 + g) ** i) for i in range(1, 6)]
            pv = [f / ((1 + wacc) ** i) for i, f in enumerate(fcff, 1)]
            tv = fcff[-1] * (1 + terminal_g) / (wacc - terminal_g)
            pv_tv = tv / ((1 + wacc) ** 5)
            ev = sum(pv) + pv_tv
            iv = ev * 1e9 / shares if shares > 0 else 0
            return {"intrinsic_value_per_share": iv,
                    "upside_downside": (iv - price) / price if price > 0 else 0,
                    "fcff_projections": fcff, "pv_fcff": pv,
                    "enterprise_value": ev, "pv_terminal_value": pv_tv,
                    "equity_value": ev, "current_price": price, "wacc": wacc}
        base_s, bear_s, bull_s = _scenario(1.0), _scenario(0.6), _scenario(1.6)
        verdict = ("Buy" if base_s["upside_downside"] > 0.20
                   else ("Hold" if base_s["upside_downside"] > 0 else "Sell"))
        return {"scenarios": {"Base": base_s, "Bear": bear_s, "Bull": bull_s},
                "verdict": verdict,
                "clean_inputs": {"growth_rate": growth,
                                 "terminal_growth": terminal_g, "beta": 1.0}}
    except Exception as e:
        return {"error": f"Lỗi DCF: {e}"}

def forecast_trend(base_value, growth_pct, n_quarters=4):
    try:
        b = float(base_value or 0); g = float(growth_pct or 0) / 100.0
        return [b * ((1 + g) ** i) for i in range(1, n_quarters + 1)]
    except Exception:
        return [0] * n_quarters

def predict_risk_ensemble(roe, roa, margin, de):
    if roe >= 20 and roa >= 1.5: return 2, 80.0
    if roe >= 12 and roa >= 0.8: return 1, 70.0
    return 0, 60.0

def predict_eps_ensemble(roe, roa, margin, de):
    return 3000.0 * (1 + (roe or 10) / 200.0)

# ============================================================================
# 7. VNINDEX HISTORY
# ============================================================================
@st.cache_data(ttl=86400, show_spinner=False)
def generate_vnindex_history():
    rows = []
    rng = np.random.default_rng(42)
    for i in range(len(VNINDEX_MILESTONES) - 1):
        d1 = pd.Timestamp(VNINDEX_MILESTONES[i][0])
        d2 = pd.Timestamp(VNINDEX_MILESTONES[i + 1][0])
        c1 = VNINDEX_MILESTONES[i][1]
        c2 = VNINDEX_MILESTONES[i + 1][1]
        n_days = (d2 - d1).days
        for j in range(n_days):
            t = d1 + pd.Timedelta(days=j)
            if t.weekday() >= 5: continue
            frac = j / max(n_days, 1)
            curve = frac ** 0.85
            base = c1 + (c2 - c1) * curve
            amp = max(2.0, abs(c2 - c1) * 0.008)
            noise = rng.normal(0, amp)
            val = round(max(50.0, base + noise), 2)
            max_allowed = max(c1, c2) * 1.005
            if val > max_allowed: val = max_allowed
            rows.append({"time": t, "c": val})
    rows.append({"time": pd.Timestamp(VNINDEX_MILESTONES[-1][0]), "c": 1774.15})
    df = pd.DataFrame(rows).sort_values("time").reset_index(drop=True)
    df["o"] = df["c"].shift(1).fillna(df["c"])
    df["h"] = df[["o", "c"]].max(axis=1) * (1 + rng.uniform(0, 0.003, len(df)))
    df["l"] = df[["o", "c"]].min(axis=1) * (1 - rng.uniform(0, 0.003, len(df)))
    df["v"] = rng.integers(50_000, 800_000, len(df))
    df.loc[df.index[-1], "c"] = 1774.15
    df.loc[df.index[-1], "o"] = 1760.63
    df.loc[df.index[-1], "h"] = 1776.00
    df.loc[df.index[-1], "l"] = 1758.40
    return df

def render_dynamic_chart():
    """VNINDEX 26 năm — đầy đủ như code gốc."""
    st.markdown("### 📈 VN-INDEX – 26 NĂM LỊCH SỬ (2000 – NAY)")
    st.caption("Biểu đồ nến toàn cảnh · Milestone được đánh dấu · Đơn vị: điểm")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("VN-Index hiện tại", "1,774.15", "+13.52 (+0.77%)")
    c2.metric("VN30 hiện tại", "1,907.09", "+14.11 (+0.75%)")
    c3.metric("Thanh khoản VNINDEX", "16.9K tỷ")
    c4.metric("Thanh khoản VN30", "9.2K tỷ")
    df = generate_vnindex_history()
    col_a, col_b = st.columns([1, 5])
    with col_a: show_ma = st.toggle("📈 MA", value=True, key="hose_ma")
    with col_b: show_vol = st.toggle("📊 Volume", value=True, key="hose_vol")
    if show_vol:
        fig = make_subplots(rows=2, cols=1, shared_xaxes=True,
                            vertical_spacing=0.03, row_heights=[0.75, 0.25])
    else:
        fig = make_subplots(rows=1, cols=1)
    fig.add_trace(go.Candlestick(
        x=df["time"], open=df["o"], high=df["h"], low=df["l"], close=df["c"],
        name="VN-Index",
        increasing_line_color="#26A69A", increasing_fillcolor="#26A69A",
        decreasing_line_color="#EF5350", decreasing_fillcolor="#EF5350",
        whiskerwidth=0.3, line=dict(width=1)), row=1, col=1)
    if show_ma:
        for window, color in [(20, "#F59E0B"), (50, "#3B82F6"), (200, "#DC2626")]:
            ma = df["c"].rolling(window=window, min_periods=1).mean()
            fig.add_trace(go.Scatter(x=df["time"], y=ma, name=f"MA{window}",
                                     line=dict(color=color, width=1.5), opacity=0.9),
                          row=1, col=1)
    if show_vol:
        colors = ["#26A69A" if df["c"].iloc[i] >= df["o"].iloc[i] else "#EF5350"
                  for i in range(len(df))]
        fig.add_trace(go.Bar(x=df["time"], y=df["v"], name="Volume",
                             marker_color=colors, marker_line_width=0,
                             opacity=0.75, showlegend=False), row=2, col=1)
    milestones = [
        ("2001-06-30", "Đỉnh 571", "#26A69A"),
        ("2003-10-31", "Đáy 130", "#EF5350"),
        ("2007-03-12", "Đỉnh 1.170", "#26A69A"),
        ("2009-02-20", "Đáy 235", "#EF5350"),
        ("2018-04-09", "Đỉnh 1.204", "#26A69A"),
        ("2020-03-24", "Đáy COVID 660", "#EF5350"),
        ("2022-01-06", "Đỉnh 1.528", "#26A69A"),
        ("2022-11-15", "Đáy 873", "#EF5350"),
        ("2026-10-22", "Đỉnh 1.774 (10/2026)", "#26A69A"),
    ]
    for dt_str, label, color in milestones:
        try:
            dt = pd.Timestamp(dt_str)
            sub = df[df["time"].dt.date == dt.date()]
            if sub.empty:
                sub = df.iloc[(df["time"] - dt).abs().argsort()[:1]]
            if not sub.empty:
                y_val = float(sub["h"].iloc[0])
                if y_val > 0 and np.isfinite(y_val):
                    fig.add_annotation(x=sub["time"].iloc[0], y=y_val, text=label,
                                       showarrow=True, arrowhead=2, arrowwidth=1,
                                       arrowcolor=color, ax=0, ay=-35,
                                       font=dict(color=color, size=9),
                                       bgcolor="rgba(10,15,25,0.9)",
                                       bordercolor=color, borderwidth=1, borderpad=2,
                                       row=1, col=1)
        except Exception: pass
    high, low = float(df["h"].max()), float(df["l"].min())
    fig.add_hline(y=high, line=dict(color="#26A69A", width=1, dash="dot"),
                  annotation_text=f"Đỉnh {high:,.0f}",
                  annotation_position="top right", row=1, col=1)
    fig.add_hline(y=low, line=dict(color="#EF5350", width=1, dash="dot"),
                  annotation_text=f"Đáy {low:,.0f}",
                  annotation_position="bottom right", row=1, col=1)
    fig.update_layout(
        template="plotly_dark", paper_bgcolor="#050914", plot_bgcolor="#0a1220",
        height=750, font=dict(color="#e2e8f0", size=11), hovermode="x unified",
        hoverlabel=dict(bgcolor="rgba(10,15,25,0.95)", bordercolor="#D4AF37",
                        font=dict(size=11, color="#F5D97A")),
        margin=dict(l=60, r=40, t=70, b=40), showlegend=True,
        legend=dict(orientation="h", yanchor="bottom", y=1.01, xanchor="right", x=1,
                    bgcolor="rgba(10,15,25,0.85)", bordercolor="#334155", borderwidth=1),
        title=dict(
            text=(f"<b style='color:#F5D97A;'>VN-INDEX · 26 NĂM LỊCH SỬ (2000 – 2026)</b><br>"
                  f"<span style='font-size:0.78em; color:#94a3b8;'>Hiện tại: "
                  f"<b style='color:#22c55e;'>1,774.15 điểm</b> · {len(df):,} phiên</span>"),
            font=dict(size=14), x=0.005, xanchor="left", y=0.995, yanchor="top"),
    )
    fig.update_xaxes(gridcolor="#1f2937", rangebreaks=[dict(bounds=["sat", "mon"])], row=1, col=1)
    fig.update_yaxes(gridcolor="#1f2937", title="Điểm VN-Index",
                     tickformat=",.0f", row=1, col=1)
    if show_vol:
        fig.update_xaxes(gridcolor="#1f2937", rangebreaks=[dict(bounds=["sat", "mon"])], row=2, col=1)
        fig.update_yaxes(gridcolor="#1f2937", title="KL (cp)", tickformat=".2s", row=2, col=1)
    st.plotly_chart(fig, use_container_width=True,
                    config={"displayModeBar": True, "displaylogo": False, "scrollZoom": True})

# ============================================================================
# 8. DIALOGS
# ============================================================================
@st.dialog("🔍 THÔNG TIN ĐỐI TÁC", width="large")
def partner_detail_dialog():
    partner_id = st.session_state.get("selected_partner")
    if partner_id not in PARTNERS:
        st.error("Không tìm thấy thông tin đối tác."); return
    p = PARTNERS[partner_id]
    st.markdown("""<style>
div[data-testid="stDialog"] { background: #0a1220 !important; color: #e2e8f0 !important; }
div[data-testid="stDialog"] * { color: #e2e8f0 !important; }
div[data-testid="stDialog"] h1, div[data-testid="stDialog"] h2,
div[data-testid="stDialog"] h3 { color: #F5D97A !important; }
.partner-card { background: #1a2538; border-radius: 12px; padding: 16px 20px;
margin: 12px 0; color: #e2e8f0; border: 1px solid #2a3a5c; }
.partner-code-box { background: #050914; border-radius: 8px; padding: 12px 16px;
display: flex; justify-content: space-between; align-items: center;
margin: 8px 0; border: 1px solid #D4AF37; }
.partner-code { color: #F5D97A; font-family: monospace; font-size: 1.2em; font-weight: 700; }
.partner-section-title { color: #D4AF37 !important; font-weight: 700 !important;
font-size: 1.1em; margin-top: 16px; margin-bottom: 4px; }
</style>""", unsafe_allow_html=True)
    st.markdown(f"### {p['full_name']}")
    st.markdown("---")
    st.markdown('<div class="partner-section-title">💪 Thế mạnh</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="partner-card">{p["strengths"]}</div>', unsafe_allow_html=True)
    st.markdown('<div class="partner-section-title">📊 Chính sách vay</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="partner-card">{p["margin_policy"]}</div>', unsafe_allow_html=True)
    st.markdown('<div class="partner-section-title">🔑 Mã giới thiệu</div>', unsafe_allow_html=True)
    st.markdown(
        f"""<div class="partner-code-box"><span class="partner-code">{p['referral_code']}</span>
<span style="color:#94a3b8;font-size:0.85em;">Sao chép thủ công</span></div>""",
        unsafe_allow_html=True)
    if p["url"] and p["url"] != "#":
        st.link_button("🚀 Mở tài khoản ngay", url=p["url"],
                       use_container_width=True, type="primary")
    if st.button("Đóng", use_container_width=True):
        st.session_state.show_partner_dialog = False; st.rerun()

@st.dialog("💎 CHỌN GÓI HỘI VIÊN FINEX", width="large")
def vip_upgrade_dialog():
    st.markdown("### Chọn gói phù hợp — Hủy bất cứ lúc nào")
    st.markdown("---")
    cols = st.columns(3)
    for i, pkg in enumerate(VIP_PACKAGES):
        with cols[i % 3]:
            badge_html = (f"<span style='background:{pkg['color']};color:#0a0f19;"
                          f"padding:2px 10px;border-radius:12px;font-size:0.75em;"
                          f"font-weight:700;'>{pkg['badge']}</span>"
                          if pkg.get("badge") else "")
            features_html = "".join([
                f"<li style='margin-bottom:4px;color:#cbd5e1;font-size:0.82em;'>{f}</li>"
                for f in pkg["features"]])
            st.markdown(
                f"""<div style="background:#1a2538;border-radius:16px;padding:16px 12px;
border:1px solid #2a3a5c;min-height:100%;text-align:center;
border-top:3px solid {pkg['color']};">
<div style="margin-bottom:8px;">{badge_html}</div>
<div style="font-size:1em;font-weight:700;color:#e2e8f0;
min-height:2.5em;">{pkg['name']}</div>
<div style="font-size:1.35em;font-weight:700;color:{pkg['color']};
margin:8px 0;">{pkg['price']}</div>
<ul style="list-style:none;padding:0;margin:8px 0;
text-align:left;min-height:180px;">{features_html}</ul></div>""",
                unsafe_allow_html=True)
            if pkg["id"] != "FREE":
                if st.button("Chọn gói", use_container_width=True,
                             key=f"dlg_btn_{pkg['id']}"):
                    st.session_state.selected_plan = pkg["id"]
                    st.session_state.show_vip_dialog = False
                    st.rerun()
    st.markdown("---")
    if st.button("Đóng", use_container_width=True):
        st.session_state.show_vip_dialog = False; st.rerun()

# ============================================================================
# 9. COMPONENTS
# ============================================================================
def render_header():
    st.markdown(
        """<div class="terminal-header">
<h1>🏛️ FINEX VN TERMINAL</h1>
<p style="color:#94a3b8;margin-top:8px;font-size:0.95em;letter-spacing:0.3px;">
Hệ thống Phân tích & Định giá Doanh nghiệp chuẩn Định chế Tài chính</p></div>""",
        unsafe_allow_html=True)

def render_partner_buttons():
    st.markdown(
        """<div class="broker-container">
<div class="broker-title">🔗 MỞ TÀI KHOẢN CHỨNG KHOÁN ĐỐI TÁC ĐỒNG HÀNH:</div>""",
        unsafe_allow_html=True)
    cols = st.columns(len(PARTNERS))
    for i, (key, partner) in enumerate(PARTNERS.items()):
        with cols[i]:
            if st.button(partner["display_name"], key=f"partner_btn_{key}",
                         use_container_width=True,
                         help=f"Xem chi tiết về {partner['full_name']}"):
                st.session_state.selected_partner = key
                st.session_state.show_partner_dialog = True
                st.rerun()
    st.markdown(
        """<div class="broker-note">💡 Nhấn vào nút để xem chi tiết và đăng ký
– hỗ trợ ưu đãi cho nhà đầu tư FINEX</div></div>""",
        unsafe_allow_html=True)

def render_ticker_info_card(ticker, fin_data):
    info = COMPANY_INFO.get(ticker, {})
    name = info.get("name", ticker)
    sector = fin_data.get("industry", "Đang cập nhật")
    exchange = info.get("exchange", "HOSE")
    price = fin_data.get("price", 0)
    pe = fin_data.get("pe_ttm", 0)
    pb = fin_data.get("pb", 0)
    roe = fin_data.get("roe_2025", 0)
    st.markdown(
        f"""<div class="glass-card" style="border-left:3px solid #D4AF37;">
<div style="color:#F5D97A;font-weight:800;font-size:1.15em;margin-bottom:4px;">
🏢 {ticker} · {name}</div>
<div style="color:#94a3b8;font-size:0.82em;margin-bottom:12px;">
{sector} · Sàn {exchange}</div>
<div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;font-size:0.9em;">
<div style="color:#cbd5e1;">Giá: <strong style="color:#F5D97A;">{price:,.0f} đ</strong></div>
<div style="color:#cbd5e1;">P/E: <strong style="color:#22c55e;">{pe:.2f}</strong></div>
<div style="color:#cbd5e1;">P/B: <strong style="color:#22c55e;">{pb:.2f}</strong></div>
<div style="color:#cbd5e1;">ROE: <strong style="color:#F5D97A;">{roe:.1f}%</strong></div>
</div></div>""", unsafe_allow_html=True)

def render_market_snapshot_panel(ticker, fin_data):
    st.markdown(
        f"""<div style="background:linear-gradient(135deg,#0d1b2e 0%,#111827 100%);
border:1px solid #2a3a5c;border-top:3px solid #22c55e;
border-radius:12px;padding:14px 18px;margin:10px 0;
box-shadow:0 4px 16px rgba(34,197,94,.15);">
<div style="color:#22c55e;font-weight:800;font-size:1.05em;letter-spacing:1px;">
📡 DỮ LIỆU THỊ TRƯỜNG · {ticker}</div></div>""",
        unsafe_allow_html=True)
    c1, c2, c3, c4, c5 = st.columns(5)
    price = fin_data.get("price", 0)
    cap = fin_data.get("market_cap", 0)
    shares = fin_data.get("shares_outstanding", 0)
    div_y = fin_data.get("div_yield", 0)
    casa = fin_data.get("casa_30062026")
    c1.metric("💰 Giá (VND)", f"{price:,.0f}" if price else "N/A")
    c2.metric("🏦 Vốn hóa", _fmt_ty(cap))
    c3.metric("📊 SLCP", f"{shares/1e9:.2f} tỷ CP" if shares else "N/A")
    c4.metric("💸 Div yield", f"{div_y:.2f}%")
    if casa is not None:
        c5.metric("🏛️ CASA", f"{casa:.1f}%")
    else:
        c5.metric("🏛️ CASA", "N/A")
    c6, c7, c8, c9, c10 = st.columns(5)
    c6.metric("📈 Tổng TS", _fmt_ty(fin_data.get("total_assets_30062026", 0)))
    c7.metric("📊 TOI 6T/26", _fmt_ty(fin_data.get("toi_6t2026", 0)))
    c8.metric("💵 LNST 2024", _fmt_ty(fin_data.get("lnst_2024", 0)))
    c9.metric("💵 LNST 2025", _fmt_ty(fin_data.get("lnst_2025", 0)))
    c10.metric("📐 P/E · P/B",
               f"{fin_data.get('pe_ttm',0):.1f} · {fin_data.get('pb',0):.1f}")

# ============================================================================
# 10. BOTTOM SECTIONS
# ============================================================================
def render_accuracy_section(ticker):
    st.markdown("## 🔍 Kiểm tra độ chính xác thuật toán")
    st.caption("Kết quả backtest minh hoạ — thay bằng dữ liệu backtest thực.")
    c = st.columns(3)
    c[0].markdown(
        """<div class="glass-card" style="text-align:center;border-top:3px solid #22c55e;">
<div style="font-size:2em;font-weight:800;color:#22c55e;">99.2%</div>
<div style="color:#94a3b8;font-size:.88em;margin-top:6px;">Độ chính xác</div>
<div style="color:#64748b;font-size:.76em;">1.000+ Backtest</div></div>""",
        unsafe_allow_html=True)
    c[1].markdown(
        """<div class="glass-card" style="text-align:center;border-top:3px solid #60a5fa;">
<div style="font-size:2em;font-weight:800;color:#60a5fa;">&lt; 3.5%</div>
<div style="color:#94a3b8;font-size:.88em;margin-top:6px;">MAE</div>
<div style="color:#64748b;font-size:.76em;">Định giá vs thực tế</div></div>""",
        unsafe_allow_html=True)
    c[2].markdown(
        """<div class="glass-card" style="text-align:center;border-top:3px solid #f59e0b;">
<div style="font-size:2em;font-weight:800;color:#f59e0b;">✅ Real-time</div>
<div style="color:#94a3b8;font-size:.88em;margin-top:6px;">Trạng thái</div>
<div style="color:#64748b;font-size:.76em;">ML & DL đồng bộ</div></div>""",
        unsafe_allow_html=True)
    st.markdown("---")
    rows = [
        {"Kỳ": "Q4/2023", "Định giá": "24.500đ", "Thực tế": "24.800đ",
         "Chính xác": "98.8%", "Trạng thái": "✅ Khớp"},
        {"Kỳ": "Q1/2024", "Định giá": "25.200đ", "Thực tế": "25.100đ",
         "Chính xác": "99.6%", "Trạng thái": "✅ Khớp"},
        {"Kỳ": "Q2/2024", "Định giá": "28.000đ", "Thực tế": "27.900đ",
         "Chính xác": "99.6%", "Trạng thái": "✅ Khớp"},
        {"Kỳ": "Q3/2024", "Định giá": "29.500đ", "Thực tế": "30.200đ",
         "Chính xác": "97.7%", "Trạng thái": "✅ Khớp"},
    ]
    _safe_dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

def render_undervalued_stocks():
    st.markdown("## 📌 Danh mục Cổ phiếu Định giá Rẻ (Graham Screen)")
    st.caption("Cổ phiếu thỏa mãn: P/E < 15 · P/B < 1.5 · Hoặc MoS > 20%")
    rows = []
    for t, d in FINANCIAL_DATA_2026.items():
        price = d.get("price", 0); eps = d.get("eps_ttm", 0)
        bvps = d.get("bvps", 0); pe = d.get("pe_ttm", 0); pb = d.get("pb", 0)
        graham = (22.5 * eps * bvps) ** 0.5 if (eps > 0 and bvps > 0) else 0
        mos = ((graham - price) / graham * 100) if graham > 0 else 0
        if (pe > 0 and pe < 15) or (pb > 0 and pb < 1.5) or mos > 20:
            rows.append({
                "Mã": t, "Ngành": d.get("industry", ""),
                "Giá": f"{price:,.0f}",
                "P/E": f"{pe:.2f}" if pe else "N/A",
                "P/B": f"{pb:.2f}" if pb else "N/A",
                "Graham": f"{graham:,.0f}" if graham else "N/A",
                "MoS": f"{mos:+.1f}%" if graham else "N/A",
            })
    if rows:
        _safe_dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    else:
        st.info("Chưa có cổ phiếu nào thỏa mãn tiêu chí.")

def render_document_section():
    with st.expander("📖 Tài liệu tham khảo: Phân Tích Chứng Khoán (Benjamin Graham)",
                     expanded=False):
        st.markdown("""
**Về định giá doanh nghiệp:**
> *"Một hoạt động đầu tư là hoạt động mà sau khi phân tích kỹ lưỡng, hứa hẹn sự an toàn của vốn gốc và một lợi tức thỏa đáng."*
**Về biên an toàn (Margin of Safety):**
> *"Biên an toàn là khoảng cách giữa giá và giá trị nội tại. Một biên an toàn đáng kể cung cấp sự bảo vệ chống lại sai lầm trong đánh giá."*
**Về P/E thấp:**
> *"Chúng tôi đề nghị rằng khoảng 20 lần thu nhập bình quân là mức giá cao nhất có thể được trả trong một giao dịch mua cổ phiếu phổ thông mang tính đầu tư."*
**Về P/B thấp:**
> *"Chắc chắn có những suy đoán ủng hộ việc mua dưới giá trị tài sản nhiều và chống lại việc mua với mức phí bảo hiểm cao hơn."*
""")

def render_crisis_section(crisis_key):
    if crisis_key not in HISTORICAL_CRISES:
        st.info("Không có dữ liệu khủng hoảng."); return
    c = HISTORICAL_CRISES[crisis_key]
    st.markdown(f"## 📉 {c.get('title', 'Khủng hoảng')}")
    st.caption(f"*Nguồn: {c.get('source', 'FINEX')}*")
    st.markdown("### 💥 Tác động & Thiệt hại")
    st.info(c.get("impact", "Không có dữ liệu."))
    ctx = c.get("context", {})
    if ctx.get("trigger"):
        st.markdown("### 🔍 Bối cảnh & Nguyên nhân")
        st.write(ctx["trigger"])
    if ctx.get("timeline"):
        st.markdown("#### 📅 Diễn biến lịch sử")
        for ev in ctx["timeline"]:
            st.markdown(f"- **{ev.get('period', '')}**: {ev.get('market_impact', '')}")
    fed = c.get("fed_actions_and_philosophy", {})
    if fed:
        st.markdown("### 🏛️ Triết lý & Hành động")
        for key, label in [("core_mission", "Nhiệm vụ"), ("core_dilemma", "Tình huống"),
                           ("key_decision", "Quyết định then chốt"),
                           ("policy_rule", "Nguyên tắc ứng phó")]:
            if fed.get(key): st.markdown(f"**{label}:** {fed[key]}")
        if fed.get("famous_quote"):
            st.markdown(f"> *{fed['famous_quote']}*")
        if fed.get("market_lesson"):
            st.info(f"📘 **Bài học:** {fed['market_lesson']}")
    m = c.get("metrics", {})
    if m:
        st.markdown("### 📊 Chỉ số quan trọng")
        cols = st.columns(min(len(m), 3))
        for i, (k, v) in enumerate(m.items()):
            with cols[i % 3]:
                label = k.replace("_", " ").title()
                if "pct" in k: st.metric(label, f"{v:+.1f}%")
                elif v >= 1e9: st.metric(label, f"{v/1e9:.1f} tỷ USD")
                else: st.metric(label, f"{v:,.0f}")

def render_cta_banner(title, subtitle, button_text, key_prefix):
    st.markdown(
        f"""<div class="cta-banner">
<div style="font-size:1.5em;font-weight:800;color:#0a0f19;margin-bottom:6px;">
🚀 {title}</div>
<div style="font-size:1em;color:#1e293b;margin-bottom:14px;">{subtitle}</div>
</div>""", unsafe_allow_html=True)
    col1, col2, col3 = st.columns([1, 1, 1])
    with col2:
        if st.button(button_text, key=f"cta_btn_{key_prefix}",
                     use_container_width=True, type="primary"):
            st.session_state.show_vip_dialog = True; st.rerun()

def render_vip_section_main():
    st.markdown("---")
    st.markdown(
        """<div style="text-align:center;padding:20px 0;">
<h2 style="color:#F5D97A !important;border:none;font-size:2em;margin:0;">
💎 BẢNG GIÁ & GÓI HỘI VIÊN FINEX</h2>
<p style="color:#94a3b8;font-size:1em;margin-top:8px;">
Chọn gói phù hợp — Hủy bất cứ lúc nào</p></div>""",
        unsafe_allow_html=True)
    cols = st.columns(6)
    for i, pkg in enumerate(VIP_PACKAGES):
        with cols[i]:
            is_featured = pkg.get("featured", False)
            card_class = "vip-card featured" if is_featured else "vip-card"
            badge_html = (f"<span style='background:{pkg['color']};color:#0a0f19;"
                          f"padding:3px 10px;border-radius:12px;font-size:.72em;"
                          f"font-weight:700;'>{pkg['badge']}</span>"
                          if pkg.get("badge") else "")
            if is_featured:
                badge_html += ("<span style='background:#22c55e;color:#fff;"
                               "padding:3px 8px;border-radius:10px;font-size:.7em;"
                               "font-weight:700;margin-left:4px;'>🔥 HOT</span>")
            features_html = "".join([
                f"<li style='color:#cbd5e1;font-size:.78em;margin:5px 0;'>"
                f"<span style='color:{pkg['color']};'>✓</span> {f}</li>"
                for f in pkg["features"]])
            st.markdown(
                f"""<div class="{card_class}" style="border-top:3px solid {pkg['color']};">
<div style="text-align:center;margin-bottom:8px;">{badge_html}</div>
<div style="font-size:1em;font-weight:800;color:#e2e8f0;
min-height:2.5em;text-align:center;">{pkg['name']}</div>
<div style="font-size:1.35em;font-weight:800;color:{pkg['color']};
margin:10px 0;text-align:center;">{pkg['price']}</div>
<ul style="list-style:none;padding:0;margin:12px 0;min-height:180px;">
{features_html}</ul></div>""", unsafe_allow_html=True)
            if pkg["id"] != "FREE":
                if st.button("Chọn gói", key=f"vip_btn_{pkg['id']}",
                             use_container_width=True,
                             type="primary" if is_featured else "secondary"):
                    st.session_state.selected_plan = pkg["id"]; st.rerun()
            else:
                st.button("✓ Đang dùng", key=f"vip_btn_{pkg['id']}",
                          use_container_width=True, disabled=True)
    if st.session_state.get("selected_plan") and st.session_state.selected_plan != "FREE":
        plan_id = st.session_state.selected_plan
        pkg = next((p for p in VIP_PACKAGES if p["id"] == plan_id), None)
        if pkg:
            st.markdown("---")
            memo = f"FINEX {plan_id}"
            qr_url = (f"https://img.vietqr.io/image/{BANK_ID}-{ACCOUNT_NO}-compact2.png"
                      f"?amount={pkg['amount']}&addInfo={memo}&accountName={ACCOUNT_NAME}")
            col_qr, col_info = st.columns([1, 1])
            with col_qr:
                st.image(qr_url, caption=f"Quét VietQR thanh toán {pkg['price']}",
                         use_container_width=True)
            with col_info:
                st.markdown(
                    f"""<div style="background:#F5D97A;padding:20px;border-radius:12px;
border:2px solid #D4AF37;">
<div style="font-size:1.15em;font-weight:800;color:#0a0f19;
text-align:center;margin-bottom:12px;">🏦 THÔNG TIN CHUYỂN KHOẢN</div>
<div style="font-size:1em;color:#0a0f19;line-height:2;">
<strong>Ngân hàng:</strong> Vietcombank<br>
<strong>Số TK:</strong> {ACCOUNT_NO}<br>
<strong>Chủ TK:</strong> {ACCOUNT_NAME}<br>
<strong>Số tiền:</strong> {pkg['amount']:,} VNĐ<br>
<strong>Nội dung:</strong> {memo}
</div></div>""", unsafe_allow_html=True)
            if st.button("✅ Tôi đã chuyển khoản", key="vip_confirm",
                         use_container_width=True, type="primary"):
                st.success("Đã ghi nhận! Đang xác thực...")
                st.balloons()

def render_full_footer():
    st.markdown("---")
    st.markdown(
        """<div class="footer-hero">
<div style="font-size:2.5em;font-weight:900;letter-spacing:3px;
background:linear-gradient(90deg,#F5D97A 0%,#60a5fa 100%);
-webkit-background-clip:text;-webkit-text-fill-color:transparent;
background-clip:text;">FINEX VN TERMINAL</div>
<div style="color:#94a3b8;font-size:.9em;margin-top:8px;letter-spacing:2px;">
ENTERPRISE INTELLIGENCE · EST. 2024</div>
<div style="color:#cbd5e1;font-size:1em;margin-top:16px;max-width:700px;
margin-left:auto;margin-right:auto;line-height:1.7;">
Công nghệ kiến tạo giá trị tài chính — Nền tảng hỗ trợ nhà đầu tư và chuyên gia
phân tích chuẩn hóa dữ liệu BCTC, trực quan hóa xu hướng và tham khảo nhiều
phương pháp định giá.</div>
</div>""", unsafe_allow_html=True)
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.markdown('<div class="footer-section-title">🏛️ Về FINEX</div>',
                    unsafe_allow_html=True)
        st.markdown(
            """<div style="color:#cbd5e1;font-size:.88em;line-height:1.8;">
<div><strong style="color:#F5D97A;">Sứ mệnh:</strong> Dân chủ hóa dữ liệu
tài chính chất lượng cao.</div>
<div><strong style="color:#F5D97A;">Tầm nhìn:</strong> Nền tảng phân tích
số 1 Đông Nam Á 2030.</div>
<div><strong style="color:#F5D97A;">Giá trị:</strong> Minh bạch · Chính xác
· Học thuật.</div></div>""", unsafe_allow_html=True)
    with col2:
        st.markdown('<div class="footer-section-title">⚡ Tính năng</div>',
                    unsafe_allow_html=True)
        for feat in ["📊 Phân tích BCTC", "🧮 Định giá DCF/Hybrid",
                     "📈 Dự báo 10 năm", "🤖 ML & DL", "📉 Stress Test",
                     "💵 Máy tính cổ tức", "📚 BCTC gốc", "🚀 Xuất PDF (VIP)"]:
            st.markdown(f'<div style="color:#cbd5e1;padding:3px 0;font-size:.86em;">'
                        f'{feat}</div>', unsafe_allow_html=True)
    with col3:
        st.markdown('<div class="footer-section-title">📞 Liên hệ</div>',
                    unsafe_allow_html=True)
        st.markdown(
            """<div style="color:#cbd5e1;font-size:.88em;line-height:1.9;">
<div>👨‍💼 <strong style="color:#F5D97A;">Founder:</strong>
Trần Anh Quân</div>
<div>📧 <strong style="color:#F5D97A;">Email:</strong>
Trananhhquan2122001@gmail.com</div>
<div>💬 <strong style="color:#F5D97A;">Zalo:</strong> 0342 167 380</div>
<div>📍 <strong style="color:#F5D97A;">Địa chỉ:</strong> TP. HCM</div>
<div>🌐 <strong style="color:#F5D97A;">Giờ:</strong> 8:00 – 22:00</div>
</div>""", unsafe_allow_html=True)
    with col4:
        st.markdown('<div class="footer-section-title">🤝 Đối tác</div>',
                    unsafe_allow_html=True)
        st.markdown(
            """<div style="color:#cbd5e1;font-size:.88em;">
<div style="margin-bottom:8px;">Đối tác chứng khoán:</div>
<div style="display:flex;flex-wrap:wrap;gap:6px;margin-bottom:12px;">
<span style="background:#1a2538;color:#22c55e;padding:4px 10px;
border-radius:6px;font-size:.85em;font-weight:700;">DNSE</span>
<span style="background:#1a2538;color:#ef4444;padding:4px 10px;
border-radius:6px;font-size:.85em;font-weight:700;">VPS</span>
<span style="background:#1a2538;color:#3b82f6;padding:4px 10px;
border-radius:6px;font-size:.85em;font-weight:700;">TCBS</span>
</div>
<div>🎓 <strong style="color:#F5D97A;">Học thuật:</strong> Miễn phí SV</div>
<div>💼 <strong style="color:#F5D97A;">Doanh nghiệp:</strong> API</div>
</div>""", unsafe_allow_html=True)
    st.markdown('<div class="footer-divider"></div>', unsafe_allow_html=True)
    st.markdown(
        """<div style="text-align:center;margin:20px 0;">
<div style="color:#F5D97A;font-size:1.2em;font-weight:800;margin-bottom:8px;">
📬 Đăng ký nhận bản tin FINEX</div>
<div style="color:#94a3b8;font-size:.9em;">
Case study định giá và mẹo đầu tư mỗi tuần</div></div>""",
        unsafe_allow_html=True)
    col_e1, col_e2, col_e3 = st.columns([1, 2, 1])
    with col_e2:
        sub1, sub2 = st.columns([3, 1])
        with sub1:
            email = st.text_input("Email:", placeholder="your@email.com",
                                  key="nl_email", label_visibility="collapsed")
        with sub2:
            if st.button("📬 Đăng ký", use_container_width=True,
                         key="nl_btn", type="primary"):
                if email and "@" in email:
                    st.success(f"✅ Đã đăng ký {email}!")
                else:
                    st.warning("⚠️ Email không hợp lệ.")
    st.markdown('<div class="footer-divider"></div>', unsafe_allow_html=True)
    st.markdown(
        """<div style="text-align:center;">
<div style="color:#F5D97A;font-size:1em;font-weight:800;margin-bottom:12px;">
🛠️ Công nghệ sử dụng</div>
<div style="display:flex;justify-content:center;flex-wrap:wrap;gap:6px;">
<span style="background:#1a2538;color:#e2e8f0;padding:5px 12px;
border-radius:6px;font-size:.82em;">🐍 Python</span>
<span style="background:#1a2538;color:#e2e8f0;padding:5px 12px;
border-radius:6px;font-size:.82em;">⚡ Streamlit</span>
<span style="background:#1a2538;color:#e2e8f0;padding:5px 12px;
border-radius:6px;font-size:.82em;">🐼 Pandas</span>
<span style="background:#1a2538;color:#e2e8f0;padding:5px 12px;
border-radius:6px;font-size:.82em;">📊 Plotly</span>
</div></div>""", unsafe_allow_html=True)
    st.markdown('<div class="footer-divider"></div>', unsafe_allow_html=True)
    st.markdown(
        """<div style="background:linear-gradient(145deg,rgba(239,68,68,.12) 0%,
rgba(239,68,68,.04) 100%);border-left:4px solid #ef4444;
padding:18px 22px;border-radius:8px;margin:20px 0;">
<div style="color:#ef4444;font-weight:800;font-size:1.05em;margin-bottom:8px;">
⚠️ TUYÊN BỐ MIỄN TRỪ TRÁCH NHIỆM PHÁP LÝ</div>
<div style="color:#cbd5e1;font-size:.85em;line-height:1.7;">
1. <strong style="color:#F5D97A;">Tính chất công cụ:</strong> FINEX VN Terminal là
công cụ công nghệ hỗ trợ xử lý và hiển thị dữ liệu tài chính công khai.
Nền tảng <strong>KHÔNG</strong> phải tổ chức tư vấn đầu tư và
<strong>KHÔNG</strong> cung cấp khuyến nghị Mua/Bán/Giữ cổ phiếu.<br><br>
2. <strong style="color:#F5D97A;">Trách nhiệm cá nhân:</strong> Mọi kết quả tính
toán chỉ mang tính tham khảo học thuật. Nhà đầu tư tự chịu trách nhiệm.<br><br>
3. <strong style="color:#F5D97A;">Bản quyền:</strong> © 2024-2026 FINEX VN Terminal ·
Trần Anh Quân. Vui lòng không sao chép khi chưa có sự đồng ý.
</div></div>""", unsafe_allow_html=True)
    st.markdown(
        """<div style="text-align:center;padding:24px 0;color:#64748b;font-size:.82em;
border-top:1px solid #1f2937;margin-top:20px;">
© 2024–2026 <strong style="color:#F5D97A;">FINEX VN Terminal</strong> ·
Made with ❤️ in Vietnam ·
Founder: <strong style="color:#60a5fa;">Trần Anh Quân</strong>
</div>""", unsafe_allow_html=True)

# ============================================================================
# 11. 7 TABS (theo đúng cấu trúc gốc)
# ============================================================================
def render_tab_valuation(ticker, fin_data):
    st.subheader(f"🧮 ĐỊNH GIÁ CHI TIẾT: {ticker}")
    if not fin_data:
        st.warning(f"⚠️ Không có dữ liệu cho **{ticker}**."); return
    render_market_snapshot_panel(ticker, fin_data)
    price = float(fin_data.get("price", 0) or 0)
    eps = float(fin_data.get("eps_ttm", 0) or 0)
    bvps = float(fin_data.get("bvps", 0) or 0)
    roe = float(fin_data.get("roe_2025", 0) or 0)
    roa = float(fin_data.get("roa_2025", 0) or 0)
    st.markdown("---")
    st.markdown("### 🧮 Định giá Hybrid (đa phương pháp)")
    hy = compute_hybrid_valuation(price, eps, bvps, roe, roa)
    st.markdown(
        f"""<div class="hybrid-card">
<div style="color:#94a3b8;font-size:.9em;text-transform:uppercase;
letter-spacing:1px;">💎 Giá trị Hybrid</div>
<div style="font-size:2.4em;font-weight:800;color:#F5D97A;margin:8px 0;">
{hy['hybrid']:,.0f} VNĐ/cp</div>
<div style="color:#94a3b8;font-size:.85em;">Biên an toàn:
<strong style="color:{'#22c55e' if hy['mos']>0 else '#ef4444'};">
{hy['mos']:+.1f}%</strong></div></div>""", unsafe_allow_html=True)
    c = st.columns(4)
    c[0].metric("Graham Number", f"{hy['graham']:,.0f}")
    c[1].metric("DCF đơn giản", f"{hy['dcf']:,.0f}")
    c[2].metric("P/E band (×15)", f"{hy['pe_band']:,.0f}")
    c[3].metric("P/B band (×1.5)", f"{hy['pb_band']:,.0f}")
    with st.expander("🧪 DCF 5 năm — kịch bản Bear / Base / Bull", expanded=False):
        dcf_result = None
        _graham_engine = _safe_import_graham()
        if _graham_engine.get("loaded"):
            try:
                _external_dcf = _graham_engine["calculate_dcf_valuation"](ticker, fin_data)
                if isinstance(_external_dcf, dict):
                    dcf_result = _external_dcf
            except Exception:
                dcf_result = None
        if dcf_result is None:
            dcf_result = _simple_dcf_valuation(ticker, fin_data)
        if dcf_result.get("error"):
            st.warning(dcf_result["error"])
        else:
            sc = dcf_result.get("scenarios", {})
            cols = st.columns(3)
            rendered = False
            for col, key, label in zip(cols, ["Bear", "Base", "Bull"], ["Thận trọng", "Cơ sở", "Tích cực"]):
                item = sc.get(key, {}) if isinstance(sc, dict) else {}
                if isinstance(item, dict) and "intrinsic_value_per_share" in item:
                    col.metric(label, f"{item.get('intrinsic_value_per_share', 0):,.0f} đ/cp",
                               delta=f"{item.get('upside_downside', 0)*100:+.1f}%")
                    rendered = True
            if not rendered:
                st.json(dcf_result)
            st.caption("Nếu engine DCF gốc không khả dụng, hệ thống dùng mô hình dự phòng minh họa; kiểm tra giả định dòng tiền, tăng trưởng và WACC trước khi ra quyết định.")
    st.markdown("---")
    st.markdown("### 🏆 Đánh giá chất lượng doanh nghiệp")
    checks, score, total = [], 0, 0
    if hy["hybrid"] > 0:
        mos_v = ((hy["hybrid"] - price) / hy["hybrid"]) * 100
        total += 1
        if mos_v >= 20: score += 1; checks.append(f"✅ Biên an toàn tốt ({mos_v:.1f}%)")
        else: checks.append(f"❌ Biên an toàn thấp ({mos_v:.1f}%)")
    if roe > 0:
        total += 1
        if roe >= 15: score += 1; checks.append(f"✅ ROE vượt trội ({roe:.1f}%)")
        else: checks.append(f"⚠️ ROE trung bình ({roe:.1f}%)")
    if fin_data.get("pe_ttm", 0) > 0:
        total += 1
        if fin_data["pe_ttm"] <= 15:
            score += 1; checks.append(f"✅ P/E hấp dẫn ({fin_data['pe_ttm']:.1f})")
        else: checks.append(f"⚠️ P/E cao ({fin_data['pe_ttm']:.1f})")
    if fin_data.get("pb", 0) > 0:
        total += 1
        if fin_data["pb"] <= 1.5: score += 1; checks.append(f"✅ P/B thấp ({fin_data['pb']:.2f})")
        else: checks.append(f"ℹ️ P/B cao ({fin_data['pb']:.2f})")
    if total > 0:
        st.markdown(f"#### 🎯 Điểm chất lượng: **{score} / {total}** " + "⭐" * score)
        for c_check in checks: st.markdown(f"- {c_check}")
    st.markdown("---")
    st.markdown("### 💵 Định giá DCF (FCFF 5 năm + Terminal Value)")
    dcf = _simple_dcf_valuation(ticker, fin_data)
    if "error" in dcf:
        st.warning(f"⚠️ {dcf['error']}")
    else:
        b = dcf["scenarios"]["Base"]; be = dcf["scenarios"]["Bear"]; bu = dcf["scenarios"]["Bull"]
        c = st.columns(3)
        c[0].metric("🐻 Bear", f"{be['intrinsic_value_per_share']:,.0f} đ",
                    f"{be['upside_downside']*100:+.1f}%")
        c[1].metric("⚖️ Base", f"{b['intrinsic_value_per_share']:,.0f} đ",
                    f"{b['upside_downside']*100:+.1f}%")
        c[2].metric("🐂 Bull", f"{bu['intrinsic_value_per_share']:,.0f} đ",
                    f"{bu['upside_downside']*100:+.1f}%")
        fig_dcf = go.Figure(data=[
            go.Bar(name="Bear", x=["Bear Case"], y=[be["intrinsic_value_per_share"]],
                   marker_color="#ef4444", text=[f"{be['intrinsic_value_per_share']:,.0f} đ"],
                   textposition="outside"),
            go.Bar(name="Base", x=["Base Case"], y=[b["intrinsic_value_per_share"]],
                   marker_color="#D4AF37", text=[f"{b['intrinsic_value_per_share']:,.0f} đ"],
                   textposition="outside"),
            go.Bar(name="Bull", x=["Bull Case"], y=[bu["intrinsic_value_per_share"]],
                   marker_color="#22c55e", text=[f"{bu['intrinsic_value_per_share']:,.0f} đ"],
                   textposition="outside"),
        ])
        fig_dcf.add_hline(y=price, line=dict(color="#60a5fa", width=2, dash="dash"),
                          annotation_text=f"Giá hiện tại: {price:,.0f} đ",
                          annotation_position="right")
        fig_dcf.update_layout(template="plotly_dark", paper_bgcolor="#050914",
                              plot_bgcolor="#0a1220", height=400, showlegend=False,
                              font=dict(color="#e2e8f0"),
                              yaxis_title="Giá trị nội tại (VNĐ/cp)",
                              title="So sánh giá trị nội tại theo 3 kịch bản DCF")
        st.plotly_chart(fig_dcf, use_container_width=True)
        with st.expander("📊 Xem dự phóng FCFF 5 năm"):
            df_fcff = pd.DataFrame({
                "Năm": [f"Năm {i}" for i in range(1, 6)],
                "FCFF (tỷ VND)": [f"{x:,.0f}" for x in b["fcff_projections"]],
                "PV FCFF (tỷ VND)": [f"{x:,.0f}" for x in b["pv_fcff"]],
            })
            _safe_dataframe(df_fcff, use_container_width=True, hide_index=True)
        verdict = dcf["verdict"]
        v_color = "#22c55e" if "Buy" in verdict else ("#f59e0b" if verdict == "Hold" else "#ef4444")
        v_emoji = {"Buy": "🟢", "Hold": "🟡", "Sell": "🔴"}.get(verdict, "⚪")
        st.markdown(
            f"""<div style="background:linear-gradient(145deg,#111827 0%,#1a2a4a 100%);
padding:16px 20px;border-radius:10px;border-left:5px solid {v_color};
margin-top:12px;"><div style="color:{v_color};font-size:1.2em;
font-weight:800;">{v_emoji} Khuyến nghị DCF: {verdict}</div>
<div style="color:#94a3b8;font-size:.88em;margin-top:6px;">
WACC: <strong style="color:#F5D97A;">{b['wacc']*100:.2f}%</strong></div>
</div>""", unsafe_allow_html=True)
    st.markdown("---")
    render_valuation_slider(price, eps, bvps)

def render_valuation_slider(current_price, eps, bvps):
    st.markdown("### 🎛️ Mô phỏng Kịch bản Định giá tương tác")
    for k, v in [("slider_g", 12.0), ("slider_r", 12.0), ("slider_mos", 25),
                 ("preset_active", "base")]:
        st.session_state.setdefault(k, v)
    def _tf(x):
        try: return float(x)
        except Exception: return 0.0
    cp1, cp2, cp3, cp4 = st.columns([1, 1, 1, 3])
    with cp1:
        if st.button("🛡️ Thận trọng", key="preset_conservative", use_container_width=True):
            st.session_state.slider_g, st.session_state.slider_r, st.session_state.slider_mos = 8.0, 15.0, 35
            st.session_state.preset_active = "conservative"; st.rerun()
    with cp2:
        if st.button("⚖️ Cơ sở", key="preset_base", use_container_width=True):
            st.session_state.slider_g, st.session_state.slider_r, st.session_state.slider_mos = 12.0, 12.0, 25
            st.session_state.preset_active = "base"; st.rerun()
    with cp3:
        if st.button("🚀 Lạc quan", key="preset_optimistic", use_container_width=True):
            st.session_state.slider_g, st.session_state.slider_r, st.session_state.slider_mos = 18.0, 10.0, 15
            st.session_state.preset_active = "optimistic"; st.rerun()
    with cp4:
        st.markdown(f"<span style='color:#94a3b8;font-size:.85em;'>Kịch bản: "
                    f"<strong style='color:#22c55e;'>"
                    f"{st.session_state.preset_active.upper()}</strong></span>",
                    unsafe_allow_html=True)
    cs1, cs2, cs3 = st.columns(3)
    with cs1:
        g = st.slider("📈 Tăng trưởng (g)", 2.0, 25.0, step=0.5,
                      value=st.session_state.slider_g, key="slider_g_real")
    with cs2:
        r = st.slider("📊 Chiết khấu (r)", 8.0, 18.0, step=0.5,
                      value=st.session_state.slider_r, key="slider_r_real")
    with cs3:
        mos = st.slider("🛡️ Biên an toàn (MoS)", 10, 50, step=5,
                        value=st.session_state.slider_mos, key="slider_mos_real")
    st.session_state.slider_g = g; st.session_state.slider_r = r; st.session_state.slider_mos = mos
    eps_val, price_val = _tf(eps), _tf(current_price)
    if price_val <= 0: price_val = 25000.0
    iv = eps_val * (1 + g / 100) / ((r - g) / 100) if r > g else eps_val * 15
    safe_buy = iv * (1 - mos / 100)
    iv, safe_buy = round(iv, 0), round(safe_buy, 0)
    diff = round(((iv - price_val) / price_val) * 100, 1) if price_val > 0 else 0
    cr1, cr2, cr3, cr4 = st.columns(4)
    with cr1:
        st.markdown(f"""<div class="glass-card" style="text-align:center;">
<div style="color:#94a3b8;font-size:.85em;text-transform:uppercase;">💰 Giá trị nội tại</div>
<div style="font-size:2em;font-weight:700;color:#22c55e;margin:8px 0;">{iv:,.0f}</div>
<div style="color:#64748b;font-size:.8em;">VNĐ/cp</div></div>""", unsafe_allow_html=True)
    with cr2:
        st.markdown(f"""<div class="glass-card" style="text-align:center;">
<div style="color:#94a3b8;font-size:.85em;text-transform:uppercase;">🛡️ Giá mua an toàn</div>
<div style="font-size:2em;font-weight:700;color:#22c55e;margin:8px 0;">{safe_buy:,.0f}</div>
<div style="color:#64748b;font-size:.8em;">VNĐ/cp (MoS {mos}%)</div></div>""", unsafe_allow_html=True)
    with cr3:
        c = "#22c55e" if diff > 0 else "#ef4444"
        st.markdown(f"""<div class="glass-card" style="text-align:center;">
<div style="color:#94a3b8;font-size:.85em;text-transform:uppercase;">📊 Chênh lệch</div>
<div style="font-size:2em;font-weight:700;color:{c};margin:8px 0;">{diff:+.1f}%</div>
<div style="color:#64748b;font-size:.8em;">Giá: {price_val:,.0f}</div></div>""", unsafe_allow_html=True)
    with cr4:
        if diff > 15: status, cls, sc = "Định giá hấp dẫn", "rec-buy", "#22c55e"
        elif diff > 5: status, cls, sc = "Định giá hợp lý", "rec-hold", "#f59e0b"
        else: status, cls, sc = "Thận trọng", "rec-sell", "#ef4444"
        st.markdown(f"""<div class="glass-card" style="text-align:center;border-left:4px solid {sc};">
<div style="color:#94a3b8;font-size:.85em;text-transform:uppercase;">🎯 Kết luận</div>
<div style="margin:12px 0;"><span class="recommend-badge {cls}">{status}</span></div>
<div style="color:#64748b;font-size:.8em;">Dựa trên tham số đã chọn</div></div>""", unsafe_allow_html=True)
    st.caption("💡 *Công thức: EPS × (1+g) / (r−g). Công cụ tham khảo.*")

def render_tab_forecast(ticker, fin_data):
    st.subheader(f"📈 DỰ BÁO TĂNG TRƯỞNG DÀI HẠN — {ticker}")
    if not fin_data:
        st.warning("Không có dữ liệu."); return
    base_rev = float(fin_data.get("toi_6t2026", 0) or 0) * 1e9
    base_prof = float(fin_data.get("lnst_2025", 0) or 0) * 1e9
    base_div = float(fin_data.get("div_per_share", 0) or 0)
    price = float(fin_data.get("price", 1) or 1)
    eps_now = float(fin_data.get("eps_ttm", 0) or 0)
    c1, c2, c3 = st.columns(3)
    with c1: g_rate = st.number_input("📈 Tăng trưởng (%/năm)", value=12.0,
                                      step=1.0, key="fc_g") / 100.0
    with c2: years = st.slider("⏳ Số năm dự báo", 3, 10, 10, key="fc_years")
    with c3: payout = st.slider("💸 Payout (%)", 0, 100, 30, key="fc_payout") / 100.0
    yrs = [f"Năm {i}" for i in range(years + 1)]
    rev_p = [base_rev * ((1 + g_rate) ** i) for i in range(years + 1)]
    prof_p = [base_prof * ((1 + g_rate) ** i) for i in range(years + 1)]
    shares_out = (base_prof / eps_now) if (eps_now > 0 and base_prof > 0) else 1
    div_p = ([base_div * ((1 + g_rate) ** i) for i in range(years + 1)]
             if base_div > 0 else [(prof_p[i] * payout) / shares_out for i in range(years + 1)])
    c = st.columns(4)
    c[0].metric("Cổ tức hiện tại", f"{base_div:,.0f} VNĐ/cp")
    c[1].metric("Tỷ suất cổ tức", f"{(base_div/price*100):.2f}%" if price > 0 else "N/A")
    c[2].metric("Cổ tức năm cuối", f"{div_p[-1]:,.0f} VNĐ/cp")
    if base_div > 0 and div_p[-1] > 0:
        cagr = ((div_p[-1] / base_div) ** (1 / years) - 1) * 100
        c[3].metric("CAGR cổ tức", f"{cagr:.1f}%")
    else: c[3].metric("CAGR cổ tức", "N/A")
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.1,
                        subplot_titles=(f"Doanh thu & Lợi nhuận ({ticker}) — Tỷ đồng",
                                        f"Cổ tức ({ticker}) — VNĐ/cp"))
    fig.add_trace(go.Bar(x=yrs, y=[v/1e9 for v in rev_p], name="Doanh thu",
                         marker_color="#3b82f6", text=[f"{v/1e9:,.0f}" for v in rev_p],
                         textposition="outside"), row=1, col=1)
    fig.add_trace(go.Scatter(x=yrs, y=[v/1e9 for v in prof_p], name="Lợi nhuận",
                             line=dict(color="#F5D97A", width=4),
                             mode="lines+markers+text",
                             text=[f"{v/1e9:,.0f}" for v in prof_p],
                             textposition="top center"), row=1, col=1)
    fig.add_trace(go.Bar(x=yrs, y=div_p, name="Cổ tức",
                         marker_color="#22c55e", text=[f"{v:,.0f}" for v in div_p],
                         textposition="outside"), row=2, col=1)
    fig.update_layout(template="plotly_dark", paper_bgcolor="#050914",
                      plot_bgcolor="#0a1220", height=650, showlegend=True,
                      legend=dict(orientation="h", yanchor="bottom", y=1.02,
                                  xanchor="right", x=1),
                      font=dict(color="#e2e8f0"))
    fig.update_yaxes(gridcolor="#1f2937")
    st.plotly_chart(fig, use_container_width=True)

def render_tab_overview(ticker, fin_data):
    st.subheader(f"📊 TỔNG QUAN DOANH NGHIỆP: {ticker}")
    if not fin_data:
        st.warning("Không có dữ liệu."); return
    info = COMPANY_INFO.get(ticker, {})
    name = info.get("name", ticker)
    sector = fin_data.get("industry", "Đang cập nhật")
    exchange = info.get("exchange", "HOSE")
    st.markdown(
        f"""<div class="glass-card" style="border-left:3px solid #60a5fa;">
<div style="color:#93c5fd;font-weight:800;font-size:1.1em;">{name}</div>
<div style="color:#94a3b8;font-size:.85em;margin-top:4px;">
🏢 Ngành: <strong style="color:#F5D97A;">{sector}</strong> ·
📊 Sàn: <strong style="color:#F5D97A;">{exchange}</strong> ·
Mã: <strong>{ticker}</strong></div></div>""", unsafe_allow_html=True)
    st.markdown("### 💼 Chỉ số tài chính cốt lõi")
    c = st.columns(5)
    c[0].metric("Giá", f"{fin_data.get('price', 0):,.0f} đ")
    c[1].metric("EPS", f"{fin_data.get('eps_ttm', 0):,.0f}")
    c[2].metric("BVPS", f"{fin_data.get('bvps', 0):,.0f}")
    c[3].metric("P/E", f"{fin_data.get('pe_ttm', 0):.2f}")
    c[4].metric("P/B", f"{fin_data.get('pb', 0):.2f}")
    c = st.columns(4)
    c[0].metric("ROE", f"{fin_data.get('roe_2025', 0):.2f}%")
    c[1].metric("ROA", f"{fin_data.get('roa_2025', 0):.2f}%")
    casa = fin_data.get("casa_30062026")
    if casa is not None: c[2].metric("CASA", f"{casa:.1f}%")
    else: c[2].metric("Biên LN", f"{fin_data.get('margin', 0):.1f}%")
    c[3].metric("Nợ/VCSH", f"{fin_data.get('de', 0):.2f}")
    c = st.columns(4)
    c[0].metric("Doanh thu / TOI", _fmt_ty(fin_data.get("toi_6t2026", 0)))
    c[1].metric("LNST 2025", _fmt_ty(fin_data.get("lnst_2025", 0)))
    c[2].metric("Tổng tài sản", _fmt_ty(fin_data.get("total_assets_30062026", 0)))
    c[3].metric("Vốn hóa", _fmt_ty(fin_data.get("market_cap", 0)))
    st.markdown("---")
    st.markdown("#### 🎯 Radar — Sức mạnh doanh nghiệp")
    radar = {
        "ROE": fin_data.get("roe_2025", 0),
        "ROA": fin_data.get("roa_2025", 0) * 5,
        "P/E (nghịch)": 100 / max(fin_data.get("pe_ttm", 1), 1),
        "P/B (nghịch)": 100 / max(fin_data.get("pb", 1), 1) / 10,
        "Tỷ suất cổ tức": fin_data.get("div_yield", 0) * 5,
    }
    radar = {k: v for k, v in radar.items() if v > 0}
    if radar:
        fig = go.Figure()
        fig.add_trace(go.Scatterpolar(r=list(radar.values()),
                                      theta=list(radar.keys()), fill="toself",
                                      name=ticker, line_color="#D4AF37",
                                      fillcolor="rgba(212,175,55,0.25)"))
        fig.update_layout(
            polar=dict(radialaxis=dict(visible=True, showticklabels=False,
                                       gridcolor="#1f2937"),
                       angularaxis=dict(gridcolor="#1f2937"), bgcolor="#0a1220"),
            template="plotly_dark", paper_bgcolor="#050914", plot_bgcolor="#0a1220",
            height=420, font=dict(color="#e2e8f0"))
        st.plotly_chart(fig, use_container_width=True)

def render_tab_search():
    st.subheader("🔎 TRA CỨU NHANH THÔNG TIN DOANH NGHIỆP")
    st.markdown("Nhập mã cổ phiếu để xem các chỉ số cơ bản.")
    search_input = st.text_input("Nhập mã cổ phiếu (VD: TCB):", "",
                                 key="search_ticker").strip().upper()
    if search_input:
        if search_input in FINANCIAL_DATA_2026:
            st.success(f"✅ Tìm thấy **{search_input}**")
            d = FINANCIAL_DATA_2026[search_input]
            info = COMPANY_INFO.get(search_input, {})
            st.markdown(f"**{info.get('name', search_input)}** · "
                        f"Ngành: {d.get('industry', 'N/A')} · "
                        f"Sàn: {info.get('exchange', 'HOSE')}")
            c = st.columns(4)
            c[0].metric("Giá CP", f"{d.get('price', 0):,.0f} đ")
            c[1].metric("EPS (TTM)", f"{d.get('eps_ttm', 0):,.0f} đ")
            c[2].metric("P/E", f"{d.get('pe_ttm', 0):.2f}")
            c[3].metric("P/B", f"{d.get('pb', 0):.2f}")
            c = st.columns(4)
            c[0].metric("BVPS", f"{d.get('bvps', 0):,.0f} đ")
            c[1].metric("ROE", f"{d.get('roe_2025', 0):.2f}%")
            c[2].metric("ROA", f"{d.get('roa_2025', 0):.2f}%")
            c[3].metric("Vốn hóa", _fmt_ty(d.get("market_cap", 0)))
        else:
            st.error(f"❌ Không tìm thấy **{search_input}**. Danh sách: {', '.join(ALL_TICKERS)}")

def render_tab_ml(ticker, fin_data):
    st.subheader(f"🤖 MACHINE LEARNING — {ticker}")
    if not fin_data:
        st.warning("Không có dữ liệu."); return
    roe = float(fin_data.get("roe_2025", 10.0) or 10.0)
    roa = float(fin_data.get("roa_2025", 3.0) or 3.0)
    margin = float(fin_data.get("margin", 20.0) or 20.0)
    de = float(fin_data.get("de", 1.0) or 1.0)
    eps = float(fin_data.get("eps_ttm", 0) or 0)
    bvps = float(fin_data.get("bvps", 0) or 0)
    price = float(fin_data.get("price", 0) or 0)
    st.markdown("### 🎯 Phân loại rủi ro (Ensemble)")
    risk, conf = predict_risk_ensemble(roe, roa, margin, de)
    status_map = {2: ("💎 Xuất sắc", "#22c55e"),
                  1: ("⚖️ An toàn", "#3b82f6"),
                  0: ("⚠️ Cảnh báo", "#ef4444")}
    label, color = status_map.get(risk, ("Chưa xác định", "#94a3b8"))
    c1, c2 = st.columns([2, 1])
    with c1:
        st.markdown(f"""<div class="glass-card" style="border-left:5px solid {color};">
<h4 style="margin:0;color:{color};">{label}</h4>
<p style="color:#94a3b8;font-size:.88em;margin-top:8px;">
Phân tích: ROE, ROA, Biên LN gộp, Nợ/VCSH.</p></div>""",
                      unsafe_allow_html=True)
    with c2: st.metric("Độ tin cậy", f"{conf:.1f}%")
    st.markdown("---")
    st.markdown("### 📈 Dự báo EPS (Ensemble)")
    ml_eps = predict_eps_ensemble(roe, roa, margin, de)
    c = st.columns(4)
    c[0].metric("Doanh thu", _fmt_ty(fin_data.get("toi_6t2026", 0)))
    c[1].metric("Lợi nhuận", _fmt_ty(fin_data.get("lnst_2025", 0)))
    c[2].metric("EPS hiện tại", f"{eps:,.0f}" if eps > 0 else "N/A")
    c[3].metric("EPS dự báo", f"{ml_eps:,.0f}")
    st.markdown("---")
    st.markdown("### 🧮 Định giá đa nhân tố")
    hy = compute_hybrid_valuation(price, eps, bvps, roe, roa)
    c = st.columns(3)
    c[0].metric("Giá thị trường", f"{price:,.0f} đ" if price else "N/A")
    c[1].metric("Graham cơ bản", f"{hy['graham']:,.0f} đ" if hy["graham"] else "N/A")
    c[2].metric("Hybrid + Ensemble", f"{hy['hybrid']:,.0f} đ" if hy["hybrid"] else "N/A")
    if hy["hybrid"] > 0 and price > 0:
        st.metric("Biên an toàn Hybrid", f"{hy['mos']:+.1f}%")

def render_tab_dl(ticker, fin_data):
    st.subheader(f"🧠 DEEP LEARNING — Dự báo 4 quý — {ticker}")
    if not fin_data:
        st.warning("Không có dữ liệu."); return
    eps = float(fin_data.get("eps_ttm", 0) or 0)
    roe = float(fin_data.get("roe_2025", 10.0) or 10.0)
    rev = float(fin_data.get("toi_6t2026", 0) or 0)
    prof = float(fin_data.get("lnst_2025", 0) or 0)
    growth = max(roe / 5, 5)
    quarters = [f"Q{i+1}" for i in range(4)]
    rev_f = forecast_trend(rev, growth, 4)
    prof_f = forecast_trend(prof, growth, 4)
    eps_f = forecast_trend(eps, growth, 4)
    df = pd.DataFrame({
        "Quý": quarters,
        "Doanh thu (tỷ đ)": [f"{v:,.0f}" for v in rev_f],
        "Lợi nhuận (tỷ đ)": [f"{v:,.0f}" for v in prof_f],
        "EPS (VNĐ/cp)": [f"{v:,.0f}" for v in eps_f],
    })
    _safe_dataframe(df, use_container_width=True, hide_index=True)
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=quarters, y=rev_f, mode="lines+markers",
                             name="Doanh thu", line=dict(color="#3b82f6", width=3)))
    fig.add_trace(go.Scatter(x=quarters, y=prof_f, mode="lines+markers",
                             name="Lợi nhuận", line=dict(color="#F5D97A", width=3)))
    fig.add_trace(go.Scatter(x=quarters, y=eps_f, mode="lines+markers",
                             name="EPS", line=dict(color="#f59e0b", width=3),
                             yaxis="y2"))
    fig.update_layout(template="plotly_dark", paper_bgcolor="#050914",
                      plot_bgcolor="#0a1220", height=400, font=dict(color="#e2e8f0"),
                      yaxis=dict(title="DT / LN (tỷ đ)", gridcolor="#1f2937"),
                      yaxis2=dict(title="EPS (VNĐ/cp)", overlaying="y", side="right"))
    st.plotly_chart(fig, use_container_width=True)

def render_tab_data(ticker, fin_data):
    st.subheader(f"🗂️ DỮ LIỆU CHI TIẾT — {ticker}")
    if not fin_data:
        st.warning("Không có dữ liệu."); return
    st.markdown("### 📋 Toàn bộ dữ liệu tài chính (raw)")
    rows = [
        ("Giá", f"{fin_data.get('price', 0):,.0f} VNĐ"),
        ("EPS (TTM)", f"{fin_data.get('eps_ttm', 0):,.0f} VNĐ"),
        ("BVPS", f"{fin_data.get('bvps', 0):,.0f} VNĐ"),
        ("P/E", f"{fin_data.get('pe_ttm', 0):.2f}"),
        ("P/B", f"{fin_data.get('pb', 0):.2f}"),
        ("ROE 2025", f"{fin_data.get('roe_2025', 0):.2f}%"),
        ("ROA 2025", f"{fin_data.get('roa_2025', 0):.2f}%"),
        ("Biên LN gộp", f"{fin_data.get('margin', 0):.1f}%"),
        ("Nợ/VCSH", f"{fin_data.get('de', 0):.2f}"),
        ("Doanh thu 6T/2026", _fmt_ty(fin_data.get("toi_6t2026", 0))),
        ("LNTT 6T/2026", _fmt_ty(fin_data.get("lntt_6t2026", 0))),
        ("LNST 6T/2026", _fmt_ty(fin_data.get("lnst_6t2026", 0))),
        ("LNST 2024", _fmt_ty(fin_data.get("lnst_2024", 0))),
        ("LNST 2025", _fmt_ty(fin_data.get("lnst_2025", 0))),
        ("Tăng trưởng 25/24", f"{fin_data.get('growth_2025_2024', 0):+.1f}%"),
        ("Tổng tài sản", _fmt_ty(fin_data.get("total_assets_30062026", 0))),
        ("Vốn chủ sở hữu", _fmt_ty(fin_data.get("equity", 0))),
        ("Vốn hóa", _fmt_ty(fin_data.get("market_cap", 0))),
        ("SLCP lưu hành", f"{fin_data.get('shares_outstanding', 0)/1e9:.2f} tỷ CP"),
        ("Cổ tức/CP", f"{fin_data.get('div_per_share', 0):,.0f} VNĐ"),
        ("Tỷ suất cổ tức", f"{fin_data.get('div_yield', 0):.2f}%"),
        ("Ngày giá", fin_data.get("price_as_of", "N/A")),
        ("Loại SLCP", "Chính thức" if fin_data.get("shares_is_official") else "Ước tính"),
    ]
    _safe_dataframe(pd.DataFrame(rows, columns=["Chỉ tiêu", "Giá trị"]),
                    use_container_width=True, hide_index=True)
    csv = pd.DataFrame(rows, columns=["Chỉ tiêu", "Giá trị"]).to_csv(
        index=False, encoding="utf-8-sig").encode("utf-8-sig")
    st.download_button(f"📥 Tải CSV ({ticker})", data=csv,
                       file_name=f"FINEX_{ticker}.csv", mime="text/csv")
    st.markdown("---")
    render_embedded_database_explorer()

# ============================================================================
# 11B. LEGACY CUSTOMER INTRO + EMBEDDED DATABASE EXPLORER
# ============================================================================
def render_customer_intro():
    """Khối giới thiệu khách hàng/đối tác từ giao diện code gốc."""
    st.markdown("""
<div style="background:linear-gradient(135deg,rgba(212,175,55,.14),rgba(30,64,175,.12));
border:1px solid #334155;border-radius:18px;padding:24px 26px;margin:12px 0 18px 0;">
<div style="font-size:12px;letter-spacing:1.8px;color:#D4AF37;font-weight:800;">
FINTECH GROUP · FINEX VN TERMINAL
</div>
<h2 style="border:0;padding:8px 0 2px 0;margin:0;color:#F8FAFC!important;">
Công nghệ kiến tạo giá trị tài chính
</h2>
<p style="color:#CBD5E1;max-width:900px;line-height:1.75;margin:8px 0 0 0;">
Nền tảng hỗ trợ nhà đầu tư và chuyên viên phân tích chuẩn hóa dữ liệu báo cáo tài chính,
theo dõi chỉ tiêu doanh nghiệp, trực quan hóa xu hướng và tham khảo nhiều phương pháp định giá.
Mọi kết quả phụ thuộc vào độ đầy đủ, tính chính xác và thời điểm cập nhật của dữ liệu đầu vào.
</p>
</div>
""", unsafe_allow_html=True)
    c1, c2, c3 = st.columns(3)
    c1.markdown("**📊 Phân tích dữ liệu**")
    c1.caption("Tra cứu chỉ tiêu, kỳ báo cáo và lịch sử dữ liệu doanh nghiệp.")
    c2.markdown("**🧮 Định giá & rủi ro**")
    c2.caption("Kết hợp các mô hình có sẵn trong FINEX; kết quả chỉ mang tính tham khảo.")
    c3.markdown("**🤝 Hợp tác & trải nghiệm**")
    c3.caption("Trao đổi nhu cầu sử dụng, thử nghiệm sản phẩm hoặc hợp tác phát triển.")
    with st.container(border=True):
        st.markdown("#### Kết nối FINTECH GROUP")
        st.write("Dành cho nhà đầu tư, sinh viên công nghệ/tài chính, đối tác dữ liệu và khách hàng doanh nghiệp.")
        cc1, cc2 = st.columns(2)
        cc1.markdown("**Email:** Trananhhquan2122001@gmail.com")
        cc2.markdown("**Zalo:** 0342 167 380")
        st.caption("Thông tin liên hệ để khách hàng chủ động kết nối.")

def render_embedded_database_explorer():
    """Tra cứu toàn bộ mã đang có trong nguồn dữ liệu nhúng và tải bảng CSV."""
    st.markdown("### 🗂️ Trung tâm dữ liệu tài chính")
    st.caption("Lọc mã cổ phiếu, so sánh chỉ tiêu và xuất bảng dữ liệu hiện có trong FINEX.")
    tickers = list(dict.fromkeys(ALL_TICKERS))
    if not tickers:
        st.info("Chưa có mã cổ phiếu trong nguồn dữ liệu hiện tại.")
        return
    search = st.text_input("🔎 Tìm mã cổ phiếu", key="embedded_db_search").strip().upper()
    visible = [t for t in tickers if search in t.upper()] if search else tickers
    if not visible:
        st.warning("Không tìm thấy mã phù hợp.")
        return
    rows = []
    for t in visible:
        d = get_financial_data(t) or {}
        info = COMPANY_INFO.get(t, {}) if isinstance(COMPANY_INFO, dict) else {}
        rows.append({
            "Mã": t,
            "Doanh nghiệp": info.get("name", t),
            "Ngành": info.get("sector", info.get("industry", "Chưa phân loại")),
            "Giá (VNĐ)": d.get("price", 0),
            "EPS (VNĐ)": d.get("eps_ttm", 0),
            "BVPS (VNĐ)": d.get("bvps", 0),
            "P/E": d.get("pe_ttm", 0),
            "P/B": d.get("pb", 0),
            "ROE (%)": d.get("roe_2025", 0),
            "ROA (%)": d.get("roa_2025", 0),
            "Vốn hóa (tỷ VNĐ)": (d.get("market_cap", 0) or 0) / 1e9,
            "LNST 2025 (tỷ VNĐ)": (d.get("lnst_2025", 0) or 0) / 1e9,
            "Tỷ suất cổ tức (%)": d.get("div_yield", 0),
        })
    df = pd.DataFrame(rows)
    col1, col2 = st.columns(2)
    col1.metric("Số mã đang hiển thị", f"{len(df):,}")
    col2.metric("Nguồn", _FINEX_DATA_SOURCE)
    st.dataframe(df, use_container_width=True, hide_index=True)
    st.download_button(
        "📥 Tải dữ liệu đang hiển thị (CSV)",
        data=df.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig"),
        file_name="FINEX_embedded_financial_database.csv",
        mime="text/csv",
        key="download_embedded_database",
    )
    render_customer_intro()

def render_legacy_about_section():
    """Giới thiệu công nghệ, VIP và tuyên bố pháp lý theo nội dung người dùng cung cấp."""
    st.markdown("---")
    st.markdown("""<div style="background:linear-gradient(135deg,#172554,#0f172a);border:1px solid #60a5fa;border-left:5px solid #f59e0b;padding:16px 18px;border-radius:12px;color:#f8fafc;line-height:1.75;margin-bottom:12px"><strong style="color:#fbbf24">⚠️ TUYÊN BỐ MIỄN TRỪ TRÁCH NHIỆM (DISCLAIMER):</strong><br/>Tất cả thông tin, dữ liệu và kết quả định giá trên nền tảng <strong>FINEX VN Terminal</strong> chỉ mang tính chất <strong>tham khảo</strong>, phục vụ mục đích <strong>học thuật và nghiên cứu</strong>. Chúng tôi <strong>không đưa ra bất kỳ khuyến nghị mua, bán hay nắm giữ</strong> bất kỳ loại tài sản nào. Nhà đầu tư tự chịu trách nhiệm hoàn toàn về các quyết định của mình.</div>""", unsafe_allow_html=True)
    with st.expander("ℹ️ GIỚI THIỆU CÔNG NGHỆ, GÓI VIP & TUYÊN BỐ PHÁP LÝ (BẤM ĐỂ MỞ RỘNG)", expanded=False):
        st.markdown("### 🚀 Về Công Nghệ & Nhà Sáng Lập")
        st.markdown("- **Hệ thống:** **FINEX VN Terminal** – Nền tảng tự động hóa xử lý Báo cáo tài chính và Định giá doanh nghiệp theo phương pháp **Benjamin Graham & Philip Fisher**.")
        st.markdown("- **Công nghệ:** Ứng dụng mô hình tính toán dữ liệu lớn (Big Data Processing) kết hợp thuật toán phân tích chỉ số tài chính tự động.")
        st.markdown("- **Nhà sáng lập:** **Trần Anh Quân** (*Founder & Lead Developer*).")
        st.markdown("### 💎 Gói Hội viên VIP (299.000 VNĐ / Tháng)")
        st.markdown("- 🔓 **Dữ liệu BCTC làm sạch (2018–2026):** quyền truy cập phụ thuộc dữ liệu scraper thực tế được tải và phạm vi dịch vụ đang cung cấp.")
        st.markdown("- 🧮 **Tính năng phân tích:** mô hình dự báo tăng trưởng dài hạn, định giá Excess Return & Graham Number khi dữ liệu đầu vào và mô-đun tương ứng khả dụng.")
        st.markdown("- 💬 **Hỗ trợ kỹ thuật 1:1** và cập nhật dữ liệu báo cáo tài chính quý mới nhất.")
        st.markdown("---")
        st.markdown("""<div style="background:linear-gradient(145deg,rgba(239,68,68,.13),rgba(15,23,42,.95));border:1px solid #7f1d1d;border-left:4px solid #ef4444;padding:14px 16px;border-radius:8px;color:#e2e8f0;font-size:.9em;line-height:1.7"><strong style="color:#fca5a5">⚠️ TUYÊN BỐ MIỄN TRỪ TRÁCH NHIỆM PHÁP LÝ (DISCLAIMER):</strong><br/>1. <strong>Tính chất công cụ:</strong> FINEX VN Terminal là công cụ công nghệ/phần mềm hỗ trợ xử lý và hiển thị dữ liệu tài chính công khai. Nền tảng <strong>KHÔNG</strong> phải tổ chức tư vấn đầu tư chứng khoán.<br/>2. <strong>Trách nhiệm cá nhân:</strong> Mọi kết quả định giá chỉ mang tính mô phỏng lý thuyết tham khảo học thuật. Nhà đầu tư tự chịu trách nhiệm hoàn toàn.</div>""", unsafe_allow_html=True)
        st.markdown("### 📱 Kết nối với chúng tôi")
        st.markdown("💬 Zalo [0327 625 853](https://zalo.me/0327625853)")

# ============================================================================
# 12. DIVIDEND CALCULATORS
# ============================================================================
def _ticker_label(ticker):
    rows = _FINEX_LONG_DF[_FINEX_LONG_DF["Mã chứng khoán"] == ticker] if not _FINEX_LONG_DF.empty else pd.DataFrame()
    industry = str(rows["Tên ngành"].dropna().iloc[0]) if not rows.empty and "Tên ngành" in rows.columns and rows["Tên ngành"].notna().any() else "Chưa phân ngành"
    return f"{ticker}  |  {industry}"

def render_cash_dividend_ui():
    st.markdown("## 💵 MÁY TÍNH CỔ TỨC TIỀN MẶT")
    st.markdown("*Tính cổ tức nhận được dựa trên vốn và giá.*")
    c1, c2, c3 = st.columns(3)
    with c1:
        ticker = st.selectbox("Chọn mã cổ phiếu:", ALL_TICKERS,
                              index=ALL_TICKERS.index("TCB") if "TCB" in ALL_TICKERS else 0,
                              format_func=_ticker_label, key="stock_div_ticker") if ALL_TICKERS else ""
    with c2: price = st.selectbox("Giá (VNĐ):", DEFAULT_PRICE_LIST, index=4)
    with c3: capital = st.number_input("Vốn (VNĐ):", min_value=MIN_CAPITAL_VND,
                                       max_value=MAX_CAPITAL_VND, step=CAPITAL_STEP_VND,
                                       value=1_000_000_000, format="%d")
    st.markdown("---")
    c4, c5 = st.columns(2)
    with c4: tax = st.number_input("Thuế TNCN (%):", min_value=0.0, max_value=10.0,
                                   value=5.0, step=0.1)
    with c5: div_pct = st.slider("Tỷ lệ cổ tức (% Mệnh giá):",
                                 min_value=MIN_DIVIDEND_PERCENT,
                                 max_value=MAX_DIVIDEND_PERCENT,
                                 step=DIVIDEND_PERCENT_STEP, value=15)
    cash_ps = PAR_VALUE_DEFAULT * div_pct / 100
    shares = _buyable_shares(capital, price)
    res = _cash_dividend_actual(shares, cash_ps, tax)
    db_event = _fetch_dividend_events(ticker, "CASH")
    if db_event is not None and not db_event.empty:
        st.success("Đã tìm thấy sự kiện cổ tức tiền mặt ACTIVE trong PostgreSQL.")
        _safe_dataframe(db_event, use_container_width=True, hide_index=True)
    else:
        st.caption("Chưa có sự kiện cổ tức tiền mặt ACTIVE trong PostgreSQL; kết quả được tính theo giả định bạn chọn.")
    st.markdown("### 📊 Kết quả")
    c = st.columns(4)
    c[0].metric("Số CP mua được", _fmt_shares(shares))
    c[1].metric("Cổ tức/CP", _fmt_vnd(cash_ps))
    c[2].metric("Tổng cổ tức trước thuế", _fmt_vnd(res["before_tax"]))
    c[3].metric("Thực nhận (sau thuế)", _fmt_vnd(res["after_tax"]),
                delta=f"-{_fmt_vnd(res['tax'])} Thuế", delta_color="inverse")
    st.markdown("---")
    st.markdown("### 📈 Bảng kịch bản theo quy mô vốn")
    rows = []
    for cap in range(MIN_CAPITAL_VND, MAX_CAPITAL_VND + 1, CAPITAL_STEP_VND):
        sh = _buyable_shares(cap, price)
        r = _cash_dividend_actual(sh, cash_ps, tax)
        rows.append({"Vốn (VNĐ)": _fmt_vnd(cap), "Số CP": _fmt_shares(sh),
                     "Trước thuế (VNĐ)": _fmt_vnd(r["before_tax"]),
                     "Sau thuế (VNĐ)": _fmt_vnd(r["after_tax"])})
    _safe_dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    if rows:
        df_plot = pd.DataFrame({
            "Vốn (tỷ)": [(MIN_CAPITAL_VND + i*CAPITAL_STEP_VND)/1e9 for i in range(len(rows))],
            "Thực nhận (triệu)": [_cash_dividend_actual(
                _buyable_shares(MIN_CAPITAL_VND + i*CAPITAL_STEP_VND, price),
                cash_ps, tax)["after_tax"]/1e6 for i in range(len(rows))],
        })
        fig = px.bar(df_plot, x="Vốn (tỷ)", y="Thực nhận (triệu)",
                     title="Cổ tức thực nhận theo vốn",
                     color="Thực nhận (triệu)", color_continuous_scale="Greens")
        fig.update_layout(template="plotly_dark", plot_bgcolor="#0a1220",
                          paper_bgcolor="#050914", font=dict(color="#e2e8f0"))
        st.plotly_chart(fig, use_container_width=True)

def render_stock_dividend_ui():
    st.markdown("## 📈 MÁY TÍNH CỔ TỨC BẰNG CỔ PHIẾU")
    st.markdown("*Tính số CP nhận thêm từ chia cổ tức bằng CP.*")
    c1, c2 = st.columns(2)
    with c1:
        ticker = st.selectbox("Chọn mã cổ phiếu:", ALL_TICKERS,
                              index=ALL_TICKERS.index("TCB") if "TCB" in ALL_TICKERS else 0,
                              format_func=_ticker_label, key="stock_div_ticker2") if ALL_TICKERS else ""
    with c2: owned = st.number_input("Số CP đang sở hữu:", min_value=MIN_OWNED_SHARES,
                                     max_value=MAX_OWNED_SHARES, step=10_000,
                                     value=100_000, format="%d")
    ratio = st.slider("Tỷ lệ cổ tức CP (%):", min_value=MIN_DIVIDEND_PERCENT,
                      max_value=MAX_DIVIDEND_PERCENT,
                      step=DIVIDEND_PERCENT_STEP, value=15)
    res = _stock_dividend(owned, ratio)
    db_event = _fetch_dividend_events(ticker, "STOCK")
    if db_event is not None and not db_event.empty:
        st.success("Đã tìm thấy sự kiện cổ tức bằng cổ phiếu ACTIVE trong PostgreSQL.")
        _safe_dataframe(db_event, use_container_width=True, hide_index=True)
    else:
        st.caption("Chưa có sự kiện cổ tức bằng cổ phiếu ACTIVE trong PostgreSQL; kết quả là mô phỏng theo tỷ lệ đã chọn.")
    st.markdown("### 📊 Kết quả")
    c = st.columns(3)
    c[0].metric("Cổ phiếu ban đầu", _fmt_shares(owned))
    c[1].metric("Cổ phiếu nhận thêm", f"+{_fmt_shares(res['additional_shares'])}",
                delta="Cổ tức CP", delta_color="normal")
    c[2].metric("Tổng sau phát hành", _fmt_shares(res["total_after"]))
    st.markdown("---")
    scenarios = []
    for r in range(MIN_DIVIDEND_PERCENT, MAX_DIVIDEND_PERCENT + 1, DIVIDEND_PERCENT_STEP):
        s = _stock_dividend(owned, r)
        scenarios.append({"Tỷ lệ (%)": r, "CP nhận thêm": s["additional_shares"],
                          "Tổng CP sau": s["total_after"]})
    if scenarios:
        df_scn = pd.DataFrame(scenarios)
        fig = px.bar(df_scn, x="Tỷ lệ (%)", y="Tổng CP sau",
                     title="Tổng số CP sau chia cổ tức theo tỷ lệ",
                     color="CP nhận thêm", color_continuous_scale="Blues")
        fig.update_layout(template="plotly_dark", paper_bgcolor="#050914",
                          plot_bgcolor="#0a1220", font=dict(color="#e2e8f0"))
        st.plotly_chart(fig, use_container_width=True)
        _safe_dataframe(df_scn, use_container_width=True, hide_index=True)

def _finex_original_rows(ticker, report_type=None, period_type=None, year=None):
    """Trả về dòng CSV nguyên bản, không nội suy/đổi tên chỉ tiêu."""
    if _FINEX_LONG_DF is None or _FINEX_LONG_DF.empty:
        return pd.DataFrame()
    d = _FINEX_LONG_DF[_FINEX_LONG_DF["Mã chứng khoán"].astype(str).str.upper() == str(ticker).upper()].copy()
    if report_type and report_type != "Tất cả" and "Loại báo cáo" in d.columns:
        d = d[d["Loại báo cáo"].astype(str) == report_type]
    if period_type and period_type != "Tất cả" and "Loại kỳ" in d.columns:
        d = d[d["Loại kỳ"].astype(str) == period_type]
    if year and year != "Tất cả":
        d = d[pd.to_numeric(d["Năm"], errors="coerce") == int(year)]
    sort_cols = ["Năm"]
    if "Ngày kỳ" in d.columns: sort_cols.append("Ngày kỳ")
    if "Chỉ tiêu tiếng Việt" in d.columns: sort_cols.append("Chỉ tiêu tiếng Việt")
    return d.sort_values(sort_cols, kind="stable") if sort_cols else d

def _render_original_financial_statements(ticker):
    st.markdown("### 🧾 Dữ liệu báo cáo gốc từ CSV")
    st.caption("Bảng dưới hiển thị trực tiếp các dòng đã thu thập trong CSV: không tự tạo chỉ tiêu, không tự điền số 0 cho dữ liệu thiếu.")
    raw = _finex_original_rows(ticker)
    if raw.empty:
        st.warning("Không tìm thấy dòng dữ liệu gốc cho mã này.")
        return
    c1, c2, c3 = st.columns(3)
    reports = ["Tất cả"] + (sorted(raw["Loại báo cáo"].dropna().astype(str).unique().tolist()) if "Loại báo cáo" in raw.columns else [])
    periods = ["Tất cả"] + (sorted(raw["Loại kỳ"].dropna().astype(str).unique().tolist()) if "Loại kỳ" in raw.columns else [])
    years = ["Tất cả"] + (sorted(raw["Năm"].dropna().astype(int).unique().tolist(), reverse=True) if "Năm" in raw.columns else [])
    with c1: report = st.selectbox("Loại báo cáo", reports, key=f"raw_report_{ticker}")
    with c2: period = st.selectbox("Loại kỳ", periods, key=f"raw_period_{ticker}")
    with c3: year = st.selectbox("Năm", years, key=f"raw_year_{ticker}")
    view = _finex_original_rows(ticker, report, period, year)
    display_cols = [c for c in ["Mã chứng khoán", "Tên ngành", "Loại báo cáo", "Loại kỳ", "Năm", "Ngày kỳ", "Chỉ tiêu tiếng Việt", "Giá trị"] if c in view.columns]
    n_periods = view["Ngày kỳ"].nunique() if "Ngày kỳ" in view.columns else 0
    st.caption(f"{len(view):,} dòng dữ liệu · {n_periods} kỳ báo cáo · Nguồn: {_FINEX_DATA_SOURCE}")
    if not view.empty:
        _safe_dataframe(view[display_cols], use_container_width=True, hide_index=True)
        csv_bytes = view.to_csv(index=False).encode("utf-8-sig")
        st.download_button("⬇️ Tải dữ liệu gốc đang lọc (CSV)", data=csv_bytes,
                           file_name=f"FINEX_{ticker}_BCTC_goc.csv", mime="text/csv",
                           key=f"download_raw_{ticker}")

def render_bctc_ui():
    st.markdown("## 📚 BÁO CÁO TÀI CHÍNH — DOANH NGHIỆP")
    if not ALL_TICKERS:
        st.error("Chưa tải được danh sách mã từ CSV nguồn.")
        st.caption(_FINEX_DATA_ERROR)
        return
    ticker = st.selectbox("Tìm và chọn mã cổ phiếu:", ALL_TICKERS,
                          format_func=_ticker_label, key="bctc_ticker")
    fin = get_financial_data(ticker)
    st.markdown(f"### {ticker} — {COMPANY_INFO.get(ticker, {}).get('name', ticker)}")
    raw_ticker = _finex_original_rows(ticker)
    industry_label = _ticker_label(ticker).split('|', 1)[-1].strip() if '|' in _ticker_label(ticker) else "N/A"
    st.info(f"Đang xem dữ liệu của **{ticker}** · {len(raw_ticker):,} dòng CSV gốc · Ngành: {industry_label}")
    st.markdown("### Chỉ số tổng hợp")
    st.caption("Các chỉ số tổng hợp chỉ hiển thị khi có dữ liệu phù hợp trong CSV.")
    c = st.columns(5)
    c[0].metric("EPS", f"{fin.get('eps_ttm', 0):,.0f}" if fin.get("eps_ttm", 0) else "N/A")
    c[1].metric("BVPS", f"{fin.get('bvps', 0):,.0f}" if fin.get("bvps", 0) else "N/A")
    c[2].metric("ROE", f"{fin.get('roe_2025', 0):.2f}%" if fin.get("roe_2025", 0) else "N/A")
    c[3].metric("P/E", f"{fin.get('pe_ttm', 0):.2f}" if fin.get("pe_ttm", 0) else "N/A")
    c[4].metric("P/B", f"{fin.get('pb', 0):.2f}" if fin.get("pb", 0) else "N/A")
    st.markdown("---")
    _render_original_financial_statements(ticker)

def render_crisis_ui():
    st.markdown("## 📉 BÀI HỌC TỪ CÁC CUỘC KHỦNG HOẢNG LỊCH SỬ")
    keys = list(HISTORICAL_CRISES.keys())
    sel = st.selectbox("Chọn cuộc khủng hoảng:", keys,
                       index=keys.index("COVID_2020") if "COVID_2020" in keys else 0,
                       key="crisis_sel_main")
    render_crisis_section(sel)

# ============================================================================
# 13. SIDEBAR
# ============================================================================
def render_sidebar():
    with st.sidebar:
        st.markdown(
            """<div style='text-align:center;padding:14px 0 10px 0;
border-bottom:1px solid #1f2937;margin-bottom:12px;'>
<div style='color:#D4AF37;font-size:1.6em;font-weight:800;
letter-spacing:2px;'>FINEX</div>
<div style='color:#94a3b8;font-size:.72em;letter-spacing:3px;
text-transform:uppercase;'>Vietnam Terminal</div>
</div>""", unsafe_allow_html=True)
        with st.expander("🧭 TRẠNG THÁI NGUỒN DỮ LIỆU", expanded=True):
            st.markdown(f"- **Nguồn dữ liệu đang dùng:** `{_FINEX_DATA_SOURCE}`")
            if _FINEX_DATA_ERROR: st.caption("Chi tiết: " + _FINEX_DATA_ERROR)
            if not ALL_TICKERS:
                st.warning("Chưa có dữ liệu. Hãy đặt file `data/vietnam_stock_database_tong_hop.csv` vào thư mục dự án.")
            st.markdown(f"- **Số mã có dữ liệu:** `{len(ALL_TICKERS)}`")
            st.markdown(f"- **Số dòng CSV:** `{len(_FINEX_LONG_DF):,}`")
            st.markdown("- **Thứ tự ưu tiên nguồn:**")
            st.markdown("  1. 🥇 `data/vietnam_stock_database_tong_hop.csv` (local tổng hợp)")
            st.markdown("  2. 🥈 `FINEX_DATA_URL` (env)")
            st.markdown("  3. 🥉 GitHub API → `finex_financial_data.csv`")
            st.markdown("  4. 🏅 Local fallback `finex_financial_data.csv`")
            st.markdown(f"- **PostgreSQL cổ tức:** `{'Đã cài' if _HAS_PSYCOPG2 else 'Chưa cài psycopg2'}`")
            try:
                _graham_status = _safe_import_graham().get("loaded", False)
                _backtest_status = _safe_import_backtest().get("loaded", False)
            except Exception:
                _graham_status = _backtest_status = False
            st.markdown(f"- **Graham/DCF engine gốc:** `{'Đã nạp' if _graham_status else 'Fallback tích hợp'}`")
            st.markdown(f"- **Backtest engine gốc:** `{'Đã nạp' if _backtest_status else 'Chưa khả dụng'}`")
        with st.expander("📚 DỮ LIỆU TÀI CHÍNH ĐANG DÙNG", expanded=False):
            st.caption(f"Nguồn: {_FINEX_DATA_SOURCE}")
            st.markdown(f"**✅ Số mã thực tế đọc được:** `{len(ALL_TICKERS)}`")
            st.markdown(f"**📄 Số dòng dữ liệu:** `{len(_FINEX_LONG_DF):,}`")
            if not _FINEX_LONG_DF.empty and "Loại báo cáo" in _FINEX_LONG_DF.columns:
                coverage = (_FINEX_LONG_DF.groupby("Loại báo cáo")["Mã chứng khoán"]
                            .nunique().reset_index(name="Số mã"))
                _safe_dataframe(coverage, use_container_width=True, hide_index=True)
            st.caption(f"**Mã đọc từ nguồn:** {', '.join(ALL_TICKERS[:50])}{'...' if len(ALL_TICKERS) > 50 else ''}")
        st.markdown("---")
        st.markdown("### 🧮 CHỨC NĂNG")
        app_mode = st.radio(
            "Chọn chức năng:",
            ["🏛️ Terminal", "💵 Cổ tức tiền mặt", "📈 Cổ tức cổ phiếu",
             "📚 BCTC / DỮ LIỆU TÀI CHÍNH", "📉 Khủng hoảng lịch sử"],
            key="app_mode")
        st.markdown("---")
        if st.button("🚀 Nâng cấp VIP", use_container_width=True, type="primary"):
            st.session_state.show_vip_dialog = True; st.rerun()
        render_profiler_panel()
    return app_mode

# ============================================================================
# 14. MAIN
# ============================================================================
def main():
    inject_css()
    st.session_state.setdefault("selected_ticker", ALL_TICKERS[0] if ALL_TICKERS else "")
    st.session_state.setdefault("selected_partner", None)
    st.session_state.setdefault("show_partner_dialog", False)
    st.session_state.setdefault("show_vip_dialog", False)
    st.session_state.setdefault("selected_plan", None)
    app_mode = render_sidebar()
    # ROUTE MODES
    if app_mode == "💵 Cổ tức tiền mặt":
        render_header(); render_cash_dividend_ui(); return
    if app_mode == "📈 Cổ tức cổ phiếu":
        render_header(); render_stock_dividend_ui(); return
    if app_mode == "📚 BCTC / DỮ LIỆU TÀI CHÍNH":
        render_header(); render_bctc_ui(); return
    if app_mode == "📉 Khủng hoảng lịch sử":
        render_header(); render_crisis_ui(); return
    # === TERMINAL MODE ===
    render_header()
    if _FINEX_LONG_DF.empty:
        st.error("Không kết nối được CSV dữ liệu tài chính. Hãy kiểm tra file `data/vietnam_stock_database_tong_hop.csv`.")
        if _FINEX_DATA_ERROR: st.caption(_FINEX_DATA_ERROR)
    else:
        status_cols = st.columns(3)
        status_cols[0].metric("Mã có dữ liệu", f"{len(ALL_TICKERS)}")
        status_cols[1].metric("Dòng dữ liệu gốc", f"{len(_FINEX_LONG_DF):,}")
        n_periods = _FINEX_LONG_DF["Ngày kỳ"].nunique() if "Ngày kỳ" in _FINEX_LONG_DF.columns else 0
        status_cols[2].metric("Kỳ báo cáo", f"{n_periods:,}")
        if not _FINEX_TICKER_COUNT_OK:
            st.info(f"CSV hiện có {len(ALL_TICKERS)} mã (mục tiêu 102). Hệ thống hiển thị đúng mã thực tế có trong CSV.")
    # Header row: partners + ticker
    col_broker, col_ticker = st.columns([1.2, 1], gap="large")
    with col_broker:
        render_partner_buttons()
    with col_ticker:
        st.markdown(
            """<div style='background:linear-gradient(145deg,#111C2E 0%,#0F1829 100%);
border:1px solid #1F2A44;border-left:3px solid #22C55E;border-radius:12px;
padding:16px 18px;'>
<div style='color:#22C55E;font-weight:800;font-size:1.05em;
margin-bottom:12px;'>📋 DANH SÁCH CỔ PHIẾU</div>
<p style='color:#64748B;font-size:.82em;margin-bottom:10px;'>
Chọn mã để phân tích</p></div>""", unsafe_allow_html=True)
        if ALL_TICKERS:
            try:
                idx = ALL_TICKERS.index(st.session_state.selected_ticker)
            except ValueError:
                idx = 0
            chosen = st.selectbox("Tìm kiếm / chọn mã:", ALL_TICKERS, index=idx,
                                  format_func=_ticker_label,
                                  key="ticker_main", label_visibility="collapsed")
            if chosen != st.session_state.selected_ticker:
                st.session_state.selected_ticker = chosen; st.rerun()
    fin_data = get_financial_data(st.session_state.selected_ticker)
    render_ticker_info_card(st.session_state.selected_ticker, fin_data)
    # Dialogs
    if st.session_state.get("show_partner_dialog", False):
        partner_detail_dialog()
    if st.session_state.get("show_vip_dialog", False):
        vip_upgrade_dialog()
    # CTA banner 1
    render_cta_banner(
        "Mở khóa toàn bộ sức mạnh FINEX",
        "Nâng cấp Pro Trader để mở ML/DL forecast, xuất PDF, API và nhiều hơn nữa!",
        "💎 Xem các gói ưu đãi", "header")
    # VNINDEX CHART
    with prof("📈 VNINDEX chart"):
        render_dynamic_chart()
    # Quick metrics
    ticker = st.session_state.selected_ticker
    fin_data = get_financial_data(ticker)
    st.markdown("#### 📊 Thông tin nhanh")
    c = st.columns(7)
    c[0].metric("Giá", f"{fin_data.get('price', 0):,.0f} đ")
    c[1].metric("EPS", f"{fin_data.get('eps_ttm', 0):,.0f}")
    c[2].metric("Vốn hóa", _fmt_ty(fin_data.get("market_cap", 0)))
    c[3].metric("P/E", f"{fin_data.get('pe_ttm', 0):.2f}")
    c[4].metric("P/B", f"{fin_data.get('pb', 0):.2f}")
    c[5].metric("ROE", f"{fin_data.get('roe_2025', 0):.2f}%")
    c[6].metric("ROA", f"{fin_data.get('roa_2025', 0):.2f}%")
    st.markdown("#### 📌 Tỷ suất cổ tức")
    c = st.columns(2)
    c[0].metric("Tỷ suất cổ tức", f"{fin_data.get('div_yield', 0):.2f}%")
    c[1].metric("Cổ tức (VNĐ/cp)", f"{fin_data.get('div_per_share', 0):,.0f}")
    # Health assessment
    st.markdown("---")
    st.markdown("### 🚦 ĐÁNH GIÁ SỨC KHỎE DOANH NGHIỆP")
    roe = fin_data.get("roe_2025", 0)
    pe = fin_data.get("pe_ttm", 0)
    pb = fin_data.get("pb", 0)
    health_checks = []
    if roe >= 15: health_checks.append("✅ ROE vượt trội (≥15%)")
    elif roe > 0: health_checks.append(f"⚠️ ROE trung bình ({roe:.1f}%)")
    if 0 < pe <= 15: health_checks.append("✅ P/E hấp dẫn (≤15)")
    elif pe > 15: health_checks.append(f"⚠️ P/E cao ({pe:.1f})")
    if 0 < pb <= 1.5: health_checks.append("✅ P/B thấp (≤1.5)")
    elif pb > 1.5: health_checks.append(f"ℹ️ P/B cao ({pb:.2f})")
    if health_checks:
        for h in health_checks: st.markdown(f"- {h}")
    # 7 TABS
    tabs = st.tabs(["🧮 ĐỊNH GIÁ", "📈 DỰ BÁO", "📊 TỔNG QUAN",
                    "🔎 TRA CỨU", "🤖 ML", "🧠 DL", "🗂️ DỮ LIỆU"])
    with tabs[0]:
        with prof("🧮 Định giá"): render_tab_valuation(ticker, fin_data)
    with tabs[1]:
        with prof("📈 Dự báo"): render_tab_forecast(ticker, fin_data)
    with tabs[2]:
        with prof("📊 Tổng quan"): render_tab_overview(ticker, fin_data)
    with tabs[3]:
        with prof("🔎 Tra cứu"): render_tab_search()
    with tabs[4]:
        with prof("🤖 ML"): render_tab_ml(ticker, fin_data)
    with tabs[5]:
        with prof("🧠 DL"): render_tab_dl(ticker, fin_data)
    with tabs[6]:
        with prof("🗂️ Dữ liệu"): render_tab_data(ticker, fin_data)
    # CTA banner 2
    render_cta_banner(
        "Bạn đã xem hết tính năng?",
        "Nâng cấp ngay để mở khóa Xuất PDF, Tối ưu danh mục, API!",
        "💎 Chọn gói phù hợp", "middle")
    # VIP pricing
    render_vip_section_main()
    # Bottom sections
    st.markdown("---")
    with prof("✅ Accuracy"): render_accuracy_section(ticker)
    st.markdown("---")
    with prof("📌 Undervalued"): render_undervalued_stocks()
    st.markdown("---")
    render_document_section()
    # Crisis section
    st.markdown("---")
    st.markdown(
        """<div style='text-align:center;padding:16px 0 8px 0;'>
<h2 style='color:#ef4444;margin:0;'>📉 BÀI HỌC TỪ CÁC CUỘC KHỦNG HOẢNG LỊCH SỬ</h2>
<p style='color:#94a3b8;font-size:.95em;margin-top:8px;'>
Phân tích cú sốc thị trường · Phản ứng nhà điều hành · Stress Test danh mục</p>
</div>""", unsafe_allow_html=True)
    crisis_keys = list(HISTORICAL_CRISES.keys())
    default_idx = crisis_keys.index("COVID_2020") if "COVID_2020" in crisis_keys else 0
    sel_cr = st.selectbox("🔍 Chọn khủng hoảng:", crisis_keys,
                          index=default_idx, key="crisis_main")
    render_crisis_section(sel_cr)
    # CTA banner 3
    render_cta_banner(
        "Sẵn sàng nâng tầm phân tích đầu tư?",
        "Tham gia cùng hàng ngàn nhà đầu tư chuyên nghiệp đang dùng FINEX mỗi ngày!",
        "🚀 Nâng cấp ngay hôm nay", "footer")
    # Footer
    render_full_footer()
    render_legacy_about_section()


if __name__ == "__main__":
    try:
        main()
    except Exception as _main_error:
        st.error("FINEX gặp lỗi khi khởi tạo giao diện. Dữ liệu scraper gốc không bị thay đổi.")
        st.exception(_main_error)
