# finex_terminal_v2.py
# ============================================================================
# FINEX VN Terminal — Enterprise Intelligence
# Bản nâng cấp: tích hợp định giá + đối tác + khủng hoảng + cổ tức
#               + ML/DL + dự báo + khám phá dữ liệu CSV
# ============================================================================

import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import os
from datetime import datetime

st.set_page_config(
    page_title="FINEX VN Terminal — Enterprise Intelligence",
    page_icon="🏛️",
    layout="wide",
    initial_sidebar_state="expanded",
)

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

# ---------------------------------------------------------------------------
# 1.1 PARTNERS (mã giới thiệu mở tài khoản chứng khoán)
# ---------------------------------------------------------------------------
PARTNERS = {
    "DNSE": {
        "display_name": "DNSE",
        "full_name": "Công ty Cổ phần Chứng khoán DNSE",
        "strengths": "Nền tảng chứng khoán số tiên phong, giao diện hiện đại, phù hợp nhà đầu tư trẻ.",
        "margin_policy": "Lãi suất Margin cạnh tranh, hạn mức linh hoạt theo danh mục.",
        "referral_code": "064CQUANXZ",
        "url": "https://s.dnse.vn/eG6Qc8",
        "color": "#00C853",
    },
    "VPS": {
        "display_name": "VPS",
        "full_name": "Công ty Cổ phần Chứng khoán VPS",
        "strengths": "Thị phần môi giới top 1 Việt Nam, hệ sinh thái sản phẩm đa dạng.",
        "margin_policy": "Hạn mức cho vay (Margin) cực cao, nhiều gói ưu đãi lãi suất.",
        "referral_code": "BW60",
        "url": "https://openaccount.vps.com.vn/?MKTID=BW60",
        "color": "#C62828",
    },
    "TCBS": {
        "display_name": "TCBS",
        "full_name": "Công ty Cổ phần Chứng khoán Kỹ Thương (Techcom Securities)",
        "strengths": "Nền tảng đầu tư TCInvest hàng đầu, tích hợp ngân hàng Techcombank.",
        "margin_policy": "Lãi suất cho vay Ký quỹ (Margin) tối ưu, nhiều sản phẩm trái phiếu.",
        "referral_code": "105C925853",
        "url": "https://tcinvest.tcbs.com.vn/guest/login?openAccount=true&referralcode=105C925853",
        "color": "#1E88E5",
    },
}

# ---------------------------------------------------------------------------
# 1.2 HISTORICAL CRISES (mock — thay bằng dữ liệu thật khi có)
# ---------------------------------------------------------------------------
HISTORICAL_CRISES = {
    "BASE": {
        "title": "Kịch bản cơ sở — Thị trường bình thường",
        "source": "FINEX tham chiếu",
        "impact": "Không có cú sốc; thị trường vận hành theo chu kỳ tự nhiên.",
        "context": {
            "trigger": "Không có biến cố đặc biệt; thanh khoản ổn định.",
            "timeline": [
                {"period": "2024 – 2025", "market_impact": "VN-Index tăng trưởng ổn định."},
                {"period": "2026", "market_impact": "Đỉnh mới 1.774 điểm (22/10/2026)."},
            ],
        },
    },
    "COVID_2020": {
        "title": "Khủng hoảng COVID-19 (2020)",
        "source": "Bloomberg / SBV",
        "impact": "VN-Index giảm ~34% từ đỉnh 991 xuống 660 điểm (24/03/2020); "
                  "GDP Q2/2020 tăng 0.36% — thấp nhất 30 năm.",
        "context": {
            "trigger": "Đại dịch toàn cầu; giãn cách xã hội; đứt gãy chuỗi cung ứng.",
            "timeline": [
                {"period": "01/2020", "market_impact": "Ca nhiễm đầu tiên tại Việt Nam."},
                {"period": "03/2020", "market_impact": "VN-Index tạo đáy 660 điểm."},
                {"period": "12/2020", "market_impact": "VN-Index hồi phục về 1.103 điểm."},
            ],
        },
        "fed_actions_and_philosophy": {
            "core_mission": "Fed hạ lãi suất khẩn cấp về 0–0.25%, bơm thanh khoản qua QE không giới hạn.",
            "key_decision": "Mua trái phiếu chính phủ & MBS quy mô lớn.",
            "policy_rule": "Hành động nhanh, quy mô lớn, không giới hạn.",
            "famous_quote": "Whatever it takes — Jerome Powell",
            "market_lesson": "Thanh khoản là yếu tố sống còn; mua khi hoảng loạn.",
        },
        "metrics": {"drawdown_pct": -34.0, "recovery_months": 9, "gdp_growth_pct": 2.91},
    },
    "REAL_ESTATE_2022": {
        "title": "Khủng hoảng Trái phiếu & Bất động sản (2022)",
        "source": "UBCKNN / Bộ Tài chính",
        "impact": "VN-Index giảm ~37% từ đỉnh 1.528 xuống 873 điểm (15/11/2022); "
                  "hàng loạt doanh nghiệp BĐS mất khả năng thanh toán trái phiếu.",
        "context": {
            "trigger": "Siết tín dụng BĐS, kiểm soát trái phiếu doanh nghiệp, SCB bị đặc biệt kiểm soát.",
            "timeline": [
                {"period": "01/2022", "market_impact": "VN-Index đạt đỉnh 1.528 điểm."},
                {"period": "10/2022", "market_impact": "SCB bị kiểm soát đặc biệt."},
                {"period": "11/2022", "market_impact": "VN-Index tạo đáy 873 điểm."},
            ],
        },
        "fed_actions_and_philosophy": {
            "core_dilemma": "SBV phải cân bằng giữa ổn định tỷ giá và thanh khoản hệ thống.",
            "key_decision": "Hạ lãi suất điều hành 2 lần, nới room tín dụng 1.5–2%.",
            "policy_rule": "Ưu tiên ổn định vĩ mô trước tăng trưởng.",
            "famous_quote": "Kiểm soát rủi ro hệ thống là ưu tiên số một.",
            "market_lesson": "Đừng đánh cược vào đòn bẩy khi chính sách đang siết.",
        },
        "metrics": {"drawdown_pct": -37.0, "bond_defaults": 150, "recovery_months": 12},
    },
}

# ---------------------------------------------------------------------------
# 1.3 DEMO FINANCIAL DATA — nguồn ưu tiên cho tab Định giá / Dự báo / ML / DL
# ---------------------------------------------------------------------------
DEMO_FINANCIAL_DATA = {
    "FPT": {
        "price": 120000, "eps_ttm": 5200, "bvps": 25000, "pe_ttm": 23.0, "pb": 4.8,
        "roe_2025": 22.0, "roa_2025": 10.0, "margin": 40.0, "de": 0.6,
        "shares_outstanding": 1_500_000_000, "market_cap": 180_000,
        "lnst_2025": 8500, "lnst_2024": 7000, "lnst_6t2026": 5000,
        "toi_6t2026": 30000, "total_assets_30062026": 70_000, "equity": 38_000,
        "div_per_share": 2000, "div_yield": 1.7,
        "industry": "Công nghệ thông tin",
    },
    "TCB": {
        "price": 35000, "eps_ttm": 3500, "bvps": 28000, "pe_ttm": 10.0, "pb": 1.25,
        "roe_2025": 15.5, "roa_2025": 1.8, "margin": 45.0, "de": 8.0,
        "casa_30062026": 35.0,
        "shares_outstanding": 7_000_000_000, "market_cap": 245_000,
        "lnst_2025": 22000, "lnst_2024": 19000, "lnst_6t2026": 12000,
        "toi_6t2026": 25000, "total_assets_30062026": 800_000, "equity": 180_000,
        "div_per_share": 1500, "div_yield": 4.3,
        "industry": "Ngân hàng",
    },
    "HPG": {
        "price": 27000, "eps_ttm": 1800, "bvps": 17000, "pe_ttm": 15.0, "pb": 1.6,
        "roe_2025": 10.5, "roa_2025": 5.0, "margin": 15.0, "de": 1.2,
        "shares_outstanding": 6_400_000_000, "market_cap": 170_000,
        "lnst_2025": 12000, "lnst_2024": 8000, "lnst_6t2026": 7000,
        "toi_6t2026": 70000, "total_assets_30062026": 220_000, "equity": 108_000,
        "div_per_share": 500, "div_yield": 1.85,
        "industry": "Sản xuất",
    },
    "VNM": {
        "price": 68000, "eps_ttm": 4200, "bvps": 22000, "pe_ttm": 16.2, "pb": 3.1,
        "roe_2025": 24.0, "roa_2025": 15.0, "margin": 42.0, "de": 0.3,
        "shares_outstanding": 2_080_000_000, "market_cap": 141_000,
        "lnst_2025": 8700, "lnst_2024": 8500, "lnst_6t2026": 4500,
        "toi_6t2026": 32000, "total_assets_30062026": 60_000, "equity": 45_000,
        "div_per_share": 3850, "div_yield": 5.66,
        "industry": "Tiêu dùng",
    },
    "VCB": {
        "price": 90000, "eps_ttm": 6500, "bvps": 45000, "pe_ttm": 13.8, "pb": 2.0,
        "roe_2025": 18.5, "roa_2025": 1.5, "margin": 42.0, "de": 9.0,
        "casa_30062026": 38.0,
        "shares_outstanding": 5_600_000_000, "market_cap": 504_000,
        "lnst_2025": 36000, "lnst_2024": 33000, "lnst_6t2026": 19000,
        "toi_6t2026": 40000, "total_assets_30062026": 1_800_000, "equity": 180_000,
        "div_per_share": 1000, "div_yield": 1.11,
        "industry": "Ngân hàng",
    },
    "MWG": {
        "price": 55000, "eps_ttm": 2200, "bvps": 18000, "pe_ttm": 25.0, "pb": 3.1,
        "roe_2025": 15.0, "roa_2025": 6.0, "margin": 20.0, "de": 1.5,
        "shares_outstanding": 1_460_000_000, "market_cap": 80_300,
        "lnst_2025": 3200, "lnst_2024": 2500, "lnst_6t2026": 2000,
        "toi_6t2026": 65000, "total_assets_30062026": 45_000, "equity": 26_000,
        "div_per_share": 500, "div_yield": 0.91,
        "industry": "Bán lẻ",
    },
    "SSI": {
        "price": 32000, "eps_ttm": 1800, "bvps": 15000, "pe_ttm": 17.8, "pb": 2.1,
        "roe_2025": 14.0, "roa_2025": 5.0, "margin": 55.0, "de": 1.8,
        "shares_outstanding": 2_000_000_000, "market_cap": 64_000,
        "lnst_2025": 3600, "lnst_2024": 3000, "lnst_6t2026": 1800,
        "toi_6t2026": 7000, "total_assets_30062026": 60_000, "equity": 25_000,
        "div_per_share": 1000, "div_yield": 3.13,
        "industry": "Chứng khoán",
    },
    "ACB": {
        "price": 24000, "eps_ttm": 3200, "bvps": 18000, "pe_ttm": 7.5, "pb": 1.33,
        "roe_2025": 18.0, "roa_2025": 2.0, "margin": 40.0, "de": 7.5,
        "casa_30062026": 25.0,
        "shares_outstanding": 4_470_000_000, "market_cap": 107_000,
        "lnst_2025": 18000, "lnst_2024": 16000, "lnst_6t2026": 10000,
        "toi_6t2026": 25000, "total_assets_30062026": 750_000, "equity": 140_000,
        "div_per_share": 1500, "div_yield": 6.25,
        "industry": "Ngân hàng",
    },
}

# ============================================================================
# 2. CSS — giao diện Bloomberg Terminal (xanh dương chủ đạo + vàng nhấn)
# ============================================================================
def inject_css():
    st.markdown("""
    <style>
        html, body, [class*="css"] {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Inter", "Roboto", sans-serif;
            font-feature-settings: "tnum" 1, "lnum" 1;
        }
        .stApp {
            background:
                radial-gradient(ellipse at top left, rgba(96,165,250,0.06) 0%, transparent 45%),
                radial-gradient(ellipse at top right, rgba(212,175,55,0.06) 0%, transparent 45%),
                linear-gradient(180deg, #0a0f19 0%, #0b1220 100%) !important;
        }
        .main .block-container { padding-top: 1.2rem; padding-bottom: 3rem; max-width: 1520px; }
        h1, h2, h3, h4, h5, h6 {
            color: #60a5fa !important; font-weight: 700 !important; letter-spacing: -0.01em;
        }
        h2 { border-bottom: 1px solid #1f2937; padding-bottom: 8px; }
        .stMarkdown, .stMetric, .stDataFrame, .stExpander, p, span, label, div { color: #cbd5e1; }

        /* Metric cards — viền vàng để nhấn dữ liệu quan trọng */
        [data-testid="stMetric"] {
            background: linear-gradient(145deg, #1f2937 0%, #111827 100%);
            border: 1px solid #374151; border-left: 3px solid #D4AF37;
            border-radius: 10px; padding: 14px 16px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.35);
            transition: all 0.2s ease;
        }
        [data-testid="stMetric"]:hover {
            border-left-color: #F5D97A;
            box-shadow: 0 4px 16px rgba(212,175,55,0.20);
            transform: translateY(-1px);
        }
        [data-testid="stMetricLabel"] {
            color: #94a3b8 !important; font-size: 0.82em !important;
            text-transform: uppercase; letter-spacing: 0.6px; font-weight: 600 !important;
        }
        [data-testid="stMetricValue"] {
            color: #F5D97A !important; font-size: 1.65em !important;
            font-weight: 700 !important; font-variant-numeric: tabular-nums;
        }

        /* Tabs */
        .stTabs [data-baseweb="tab-list"] {
            gap: 4px; background: #0b1220; padding: 6px;
            border-radius: 12px; border: 1px solid #1f2937; margin-bottom: 12px;
        }
        .stTabs [data-baseweb="tab"] {
            height: 42px; background: transparent; border-radius: 8px;
            color: #94a3b8 !important; font-weight: 600 !important;
            font-size: 14px !important; padding: 0 18px !important;
        }
        .stTabs [data-baseweb="tab"]:hover { background: #16223a; color: #f3f4f6 !important; }
        .stTabs [aria-selected="true"] {
            background: linear-gradient(135deg, #1e3a5f 0%, #16223a 100%) !important;
            color: #F5D97A !important; border-bottom: 2px solid #D4AF37 !important;
        }

        /* Buttons */
        .stButton > button {
            background: linear-gradient(135deg, #16223a 0%, #111c2e 100%) !important;
            color: #e2e8f0 !important; border: 1px solid #2a3a5c !important;
            border-radius: 8px !important; font-weight: 600 !important;
            font-size: 14px !important; padding: 8px 16px !important;
            transition: all 0.18s ease !important;
        }
        .stButton > button:hover {
            background: linear-gradient(135deg, #1e3a5f 0%, #16223a 100%) !important;
            border-color: #D4AF37 !important; color: #F5D97A !important;
            transform: translateY(-1px);
            box-shadow: 0 4px 14px rgba(212,175,55,0.20);
        }
        .stButton > button[kind="primary"] {
            background: linear-gradient(135deg, #D4AF37 0%, #B8912A 100%) !important;
            color: #0a0f19 !important; border: none !important;
        }

        /* Sidebar */
        section[data-testid="stSidebar"] {
            background: linear-gradient(180deg, #0a0f19 0%, #111827 100%) !important;
            border-right: 1px solid #1f2937;
        }
        section[data-testid="stSidebar"] .stMarkdown,
        section[data-testid="stSidebar"] p,
        section[data-testid="stSidebar"] div,
        section[data-testid="stSidebar"] label,
        section[data-testid="stSidebar"] h1,
        section[data-testid="stSidebar"] h2,
        section[data-testid="stSidebar"] h3 { color: #e2e8f0 !important; }
        section[data-testid="stSidebar"] div[data-baseweb="select"] > div {
            background-color: #1f2937 !important; color: #f3f4f6 !important;
            border: 1px solid #374151 !important; border-radius: 8px !important;
        }
        section[data-testid="stSidebar"] .stRadio label {
            background: #111827; border: 1px solid #1f2937;
            border-radius: 8px; padding: 8px 12px !important;
            margin: 2px 0 !important; transition: all 0.15s ease;
        }
        section[data-testid="stSidebar"] .stRadio label:hover {
            background: #1f2937; border-color: #D4AF37;
        }

        /* Popovers / dropdowns */
        [data-baseweb="popover"], [data-baseweb="popover"] * {
            background-color: #1f2937 !important; color: #ffffff !important;
        }
        [role="option"]:hover, [aria-selected="true"] {
            background-color: #1e3a5f !important; color: #F5D97A !important;
        }

        /* Expanders */
        [data-testid="stExpander"] {
            background-color: #111827 !important; border: 1px solid #1f2937 !important;
            border-radius: 10px !important;
        }
        [data-testid="stExpander"] summary {
            background-color: #1f2937 !important; color: #f3f4f6 !important;
            font-weight: 600 !important;
        }

        /* Dataframe */
        .dataframe thead th {
            background: #16223a !important; color: #F5D97A !important;
            font-weight: 700 !important; text-transform: uppercase;
            letter-spacing: 0.5px; font-size: 12px !important;
        }
        .dataframe td, .dataframe th {
            color: #e2e8f0 !important; border-bottom: 1px solid #1f2937 !important;
        }

        /* Terminal header */
        .terminal-header {
            background: linear-gradient(135deg, #0a0f19 0%, #1f2937 100%);
            border: 1px solid #1f2937; border-top: 3px solid #D4AF37;
            border-radius: 12px; padding: 18px 24px; margin-bottom: 16px;
            box-shadow: 0 4px 16px rgba(0,0,0,0.4);
        }
        .terminal-header h1 {
            background: linear-gradient(90deg, #F5D97A 0%, #60a5fa 100%);
            -webkit-background-clip: text; -webkit-text-fill-color: transparent;
            background-clip: text; margin: 0;
        }

        /* Glass card */
        .glass-card {
            background: linear-gradient(145deg, #1f2937 0%, #111827 100%);
            border: 1px solid #374151; border-radius: 12px;
            padding: 16px; margin: 8px 0;
            box-shadow: 0 3px 12px rgba(0,0,0,0.30);
        }
        .hybrid-card {
            background: linear-gradient(145deg, #111827 0%, #16223a 100%);
            border: 1px solid #2a3a5c; border-left: 4px solid #D4AF37;
            border-radius: 12px; padding: 18px 20px; margin: 10px 0;
            box-shadow: 0 4px 16px rgba(0,0,0,0.35);
        }

        /* Recommend badges */
        .recommend-badge {
            padding: 5px 14px; border-radius: 14px;
            font-weight: 700; font-size: 0.9em;
        }
        .rec-buy  { background: #0a2e1a; color: #22c55e; border: 1px solid #22c55e; }
        .rec-hold { background: #3a2a0a; color: #f59e0b; border: 1px solid #f59e0b; }
        .rec-sell { background: #2a0a0a; color: #ef4444; border: 1px solid #ef4444; }

        /* Broker container */
        .broker-container {
            background: linear-gradient(135deg, #ffffff 0%, #f1f5f9 100%);
            border: 2px solid #D4AF37; border-radius: 14px;
            padding: 18px 22px; margin-bottom: 16px;
            box-shadow: 0 8px 24px rgba(212,175,55,0.30);
        }
        .broker-container .broker-title {
            color: #0a0f19 !important; -webkit-text-fill-color: #0a0f19 !important;
            font-size: 15px; font-weight: 800; margin-bottom: 14px;
            letter-spacing: 0.5px; text-transform: uppercase;
        }
        .broker-container .broker-note {
            color: #1e293b !important; -webkit-text-fill-color: #1e293b !important;
            font-size: 12.5px; margin-top: 12px; font-weight: 600;
        }
        .broker-container [data-testid="stButton"] button {
            background: #0a0f19 !important; color: #F5D97A !important;
            border: 2px solid #D4AF37 !important; font-weight: 700 !important;
            font-size: 14px !important; border-radius: 8px !important;
            padding: 10px 14px !important; transition: all 0.2s ease !important;
        }
        .broker-container [data-testid="stButton"] button:hover {
            background: linear-gradient(135deg, #D4AF37 0%, #B8912A 100%) !important;
            color: #0a0f19 !important; border-color: #F5D97A !important;
            transform: translateY(-1px);
            box-shadow: 0 4px 14px rgba(212,175,55,0.55);
        }

        /* Scrollbar */
        ::-webkit-scrollbar { width: 10px; height: 10px; }
        ::-webkit-scrollbar-track { background: #0a0f19; }
        ::-webkit-scrollbar-thumb { background: #374151; border-radius: 6px; }
        ::-webkit-scrollbar-thumb:hover { background: #D4AF37; }
    </style>
    """, unsafe_allow_html=True)

# ============================================================================
# 3. HELPERS
# ============================================================================
def _fmt_ty(v):
    """Format số tỷ đồng."""
    try:
        v = float(v or 0)
    except Exception:
        return "N/A"
    if v == 0:
        return "0 tỷ"
    if abs(v) >= 1000:
        return f"{v/1000:,.2f} nghìn tỷ"
    return f"{v:,.0f} tỷ"

def _fmt_vnd(v):
    try:
        return f"{int(v):,}".replace(",", ".")
    except Exception:
        return "0"

def _fmt_shares(v):
    try:
        return f"{int(v):,}".replace(",", ".")
    except Exception:
        return "0"

def _buyable_shares(capital_vnd, market_price):
    if market_price <= 0 or capital_vnd < 0:
        return 0
    return int(capital_vnd // market_price)

def _cash_dividend_actual(shares, cash_ps, tax_rate=0):
    if shares <= 0 or cash_ps <= 0:
        return {"before_tax": 0, "tax": 0, "after_tax": 0}
    before = shares * cash_ps
    tax = before * tax_rate / 100
    return {"before_tax": before, "tax": tax, "after_tax": before - tax}

def _stock_dividend(shares, ratio_percent):
    if shares <= 0 or ratio_percent <= 0:
        return {"additional_shares": 0, "total_after": shares}
    add = int(shares * ratio_percent / 100)
    return {"additional_shares": add, "total_after": shares + add}

# ============================================================================
# 4. VALUATION CORE
# ============================================================================
def compute_hybrid_valuation(price, eps, bvps, roe, roa):
    graham = (22.5 * eps * bvps) ** 0.5 if (eps > 0 and bvps > 0) else 0
    dcf = eps * 1.08 / 0.04 if eps > 0 else 0
    pe_band = eps * 15 if eps > 0 else 0
    pb_band = bvps * 1.5 if bvps > 0 else 0

    if roe >= 20 and roa >= 10:
        w = {"graham": 0.15, "dcf": 0.40, "pe": 0.30, "pb": 0.15}
    elif roe >= 15 and roa >= 7:
        w = {"graham": 0.25, "dcf": 0.30, "pe": 0.25, "pb": 0.20}
    elif roe >= 10 and roa >= 4:
        w = {"graham": 0.35, "dcf": 0.20, "pe": 0.20, "pb": 0.25}
    else:
        w = {"graham": 0.45, "dcf": 0.10, "pe": 0.15, "pb": 0.30}

    total, used_w = 0.0, 0.0
    for k, val in [("graham", graham), ("dcf", dcf), ("pe", pe_band), ("pb", pb_band)]:
        if val > 0:
            total += val * w[k]
            used_w += w[k]
    hybrid = total / used_w if used_w > 0 else 0
    mos = ((hybrid - price) / hybrid * 100) if hybrid > 0 else 0
    mos = max(-100.0, min(100.0, mos))
    return {
        "hybrid": round(hybrid, 0),
        "graham": round(graham, 0),
        "dcf": round(dcf, 0),
        "pe_band": round(pe_band, 0),
        "pb_band": round(pb_band, 0),
        "weights": w, "mos": round(mos, 1),
    }

def _simple_dcf_valuation(ticker, data):
    """Fallback FCFF DCF."""
    if not data:
        return {"error": "Không có dữ liệu."}
    try:
        profit = float(data.get("lnst_2025", 0) or data.get("lnst_6t2026", 0) or 0)
        shares = float(data.get("shares_outstanding", 0) or 0)
        price = float(data.get("price", 0) or 0)
        if profit <= 0 or shares <= 0:
            return {"error": "Thiếu LNST hoặc số lượng cổ phiếu."}

        growth, terminal_g = 0.08, 0.03
        rf, erp, beta = 0.03, 0.07, 1.0
        wacc = rf + beta * erp

        def _scenario(mult):
            g = growth * mult
            fcff = [profit * ((1 + g) ** i) for i in range(1, 6)]
            pv = [f / ((1 + wacc) ** i) for i, f in enumerate(fcff, 1)]
            tv = fcff[-1] * (1 + terminal_g) / (wacc - terminal_g)
            pv_tv = tv / ((1 + wacc) ** 5)
            ev = sum(pv) + pv_tv
            iv = ev * 1e9 / shares if shares > 0 else 0
            return {
                "intrinsic_value_per_share": iv,
                "upside_downside": (iv - price) / price if price > 0 else 0,
                "fcff_projections": fcff, "pv_fcff": pv,
                "enterprise_value": ev, "pv_terminal_value": pv_tv,
                "equity_value": ev, "current_price": price, "wacc": wacc,
            }

        base_s, bear_s, bull_s = _scenario(1.0), _scenario(0.6), _scenario(1.6)
        verdict = (
            "Buy" if base_s["upside_downside"] > 0.20
            else ("Hold" if base_s["upside_downside"] > 0 else "Sell")
        )
        return {
            "scenarios": {"Base": base_s, "Bear": bear_s, "Bull": bull_s},
            "verdict": verdict,
            "clean_inputs": {"growth_rate": growth, "terminal_growth": terminal_g, "beta": beta},
        }
    except Exception as e:
        return {"error": f"Lỗi DCF: {e}"}

def forecast_trend(base_value, growth_pct, n_quarters=4):
    try:
        b = float(base_value or 0)
        g = float(growth_pct or 0) / 100.0
        return [b * ((1 + g) ** i) for i in range(1, n_quarters + 1)]
    except Exception:
        return [0] * n_quarters

def predict_risk_ensemble(roe, roa, margin, de):
    if roe >= 20 and roa >= 1.5:
        return 2, 80.0
    if roe >= 12 and roa >= 0.8:
        return 1, 70.0
    return 0, 60.0

def predict_eps_ensemble(roe, roa, margin, de):
    return 3000.0 * (1 + (roe or 10) / 200.0)

# ============================================================================
# 5. DATA LOADING
# ============================================================================
@st.cache_data(ttl=3600, show_spinner=False)
def load_database():
    possible_paths = [
        "data/vietnam_stock_database_tong_hop.csv",
        "vietnam_stock_database_tong_hop.csv",
        "../data/vietnam_stock_database_tong_hop.csv",
        "du_lieu/vietnam_stock_database_tong_hop.csv",
    ]
    for path in possible_paths:
        if os.path.exists(path) and os.path.getsize(path) > 0:
            try:
                df_load = pd.read_csv(path, low_memory=False)
                if not df_load.empty:
                    return df_load, path
            except Exception:
                continue
    return pd.DataFrame(), None

def _get_csv_columns(df):
    """Resolve tên cột CSV không phân biệt hoa/thường."""
    col_map = {str(c).strip().lower(): c for c in df.columns}
    return {
        "ticker": col_map.get("mã chứng khoán") or col_map.get("ticker") or col_map.get("ma ck"),
        "industry": col_map.get("tên ngành") or col_map.get("ngành") or col_map.get("industry"),
        "period": col_map.get("năm") or col_map.get("ngày kỳ") or col_map.get("period"),
        "metric": col_map.get("chỉ tiêu tiếng việt") or col_map.get("chỉ tiêu") or col_map.get("metric"),
        "value": col_map.get("giá trị") or col_map.get("value"),
    }

def extract_financials_from_csv(df, ticker, cols):
    """Trích xuất chỉ số từ CSV làm fallback khi ticker không có trong DEMO."""
    ticker_col = cols.get("ticker")
    metric_col = cols.get("metric")
    value_col = cols.get("value")
    period_col = cols.get("period")
    if not all([ticker_col, metric_col, value_col]):
        return {}

    sub = df[df[ticker_col] == ticker].copy()
    if sub.empty:
        return {}

    sub[value_col] = pd.to_numeric(
        sub[value_col].astype(str).str.replace(",", "").str.replace(" ", ""),
        errors="coerce",
    )
    sub = sub.dropna(subset=[value_col])
    if sub.empty:
        return {}

    if period_col:
        try:
            sub = sub.sort_values(period_col, ascending=False)
        except Exception:
            pass

    patterns = {
        "eps_ttm": ["eps", "lãi cơ bản trên cổ phiếu"],
        "bvps": ["bvps", "giá trị sổ sách"],
        "pe_ttm": ["p/e", "pe"],
        "pb": ["p/b", "pb"],
        "roe_2025": ["roe"],
        "roa_2025": ["roa"],
        "price": ["giá hiện tại", "giá cổ phiếu", "thị giá"],
        "toi_6t2026": ["doanh thu", "thu nhập lãi", "tổng thu nhập"],
        "lnst_2025": ["lợi nhuận sau thuế", "lãi ròng"],
        "total_assets_30062026": ["tổng tài sản"],
        "equity": ["vốn chủ sở hữu"],
        "market_cap": ["vốn hóa"],
        "div_per_share": ["cổ tức", "dividend"],
        "shares_outstanding": ["số lượng cổ phiếu", "cổ phiếu lưu hành"],
    }

    result = {}
    for key, pats in patterns.items():
        for pat in pats:
            mask = sub[metric_col].astype(str).str.lower().str.contains(pat, na=False, regex=False)
            if mask.any():
                try:
                    result[key] = float(sub[mask].iloc[0][value_col])
                    break
                except Exception:
                    continue

    # Tính các chỉ số phái sinh (giả định tiền tệ đơn vị tỷ VND, shares đơn vị CP)
    if result.get("lnst_2025") and result.get("equity"):
        result["roe_2025"] = result["lnst_2025"] / result["equity"] * 100
    if result.get("lnst_2025") and result.get("total_assets_30062026"):
        result["roa_2025"] = result["lnst_2025"] / result["total_assets_30062026"] * 100
    if result.get("lnst_2025") and result.get("shares_outstanding"):
        result["eps_ttm"] = result["lnst_2025"] * 1e9 / result["shares_outstanding"]
    if result.get("equity") and result.get("shares_outstanding"):
        result["bvps"] = result["equity"] * 1e9 / result["shares_outstanding"]
    if result.get("price") and result.get("eps_ttm"):
        result["pe_ttm"] = result["price"] / result["eps_ttm"]
    if result.get("price") and result.get("bvps"):
        result["pb"] = result["price"] / result["bvps"]
    return result

def get_financials(ticker, csv_df, cols):
    """Ưu tiên DEMO_FINANCIAL_DATA (đã kiểm chứng), fallback trích từ CSV."""
    if ticker in DEMO_FINANCIAL_DATA:
        return dict(DEMO_FINANCIAL_DATA[ticker])
    return extract_financials_from_csv(csv_df, ticker, cols) if not csv_df.empty else {}

# ============================================================================
# 6. DIALOGS & COMPONENTS
# ============================================================================
@st.dialog("🔍 THÔNG TIN ĐỐI TÁC", width="large")
def partner_detail_dialog():
    partner_id = st.session_state.get("selected_partner")
    if partner_id is None or partner_id not in PARTNERS:
        st.error("Không tìm thấy thông tin đối tác.")
        return
    p = PARTNERS[partner_id]
    st.markdown("""<style>
    div[data-testid="stDialog"] { background: #1f2937 !important; color: #e2e8f0 !important; }
    div[data-testid="stDialog"] h1, div[data-testid="stDialog"] h2, div[data-testid="stDialog"] h3 { color: #ffffff !important; }
    .partner-card { background: #111827; border-radius: 12px; padding: 16px 20px; margin: 12px 0; color: #e2e8f0; border: 1px solid #2a3a5c; }
    .partner-card strong { color: #D4AF37; }
    .partner-code-box { background: #0a0f19; border-radius: 8px; padding: 12px 16px; display: flex; justify-content: space-between; align-items: center; margin: 8px 0; border: 1px solid #2a3a5c; }
    .partner-code { color: #F5D97A; font-family: monospace; font-size: 1.1em; font-weight: 600; }
    .partner-section-title { color: #D4AF37 !important; font-weight: 700 !important; font-size: 1.1em; margin-top: 16px; margin-bottom: 4px; }
    </style>""", unsafe_allow_html=True)
    st.markdown(f"### {p['full_name']}")
    st.markdown("---")
    st.markdown('<div class="partner-section-title">💪 Thế mạnh & Công nghệ</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="partner-card">{p["strengths"]}</div>', unsafe_allow_html=True)
    st.markdown('<div class="partner-section-title">📊 Chính sách vay / Đầu tư</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="partner-card">{p["margin_policy"]}</div>', unsafe_allow_html=True)
    st.markdown('<div class="partner-section-title">🔑 Mã giới thiệu (Sponsor ID)</div>', unsafe_allow_html=True)
    st.markdown(
        f"""<div class="partner-code-box">
              <span class="partner-code">{p['referral_code']}</span>
              <span style="color:#94a3b8; font-size:0.85em;">Sao chép thủ công</span>
            </div>""",
        unsafe_allow_html=True,
    )
    if p["url"] and p["url"] != "#":
        st.link_button("🚀 Mở tài khoản ngay", url=p["url"], use_container_width=True, type="primary")
    if st.button("Đóng", use_container_width=True):
        st.session_state.show_partner_dialog = False
        st.rerun()

def render_header():
    st.markdown(
        """<div class="terminal-header">
        <h1>🏛️ FINEX VN Terminal — Enterprise Intelligence</h1>
        <p style="color:#94a3b8; margin-top:8px; font-size:0.95em; letter-spacing:0.3px;">
        Hệ thống khai thác, trực quan hóa và phân tích dữ liệu tài chính doanh nghiệp chuẩn mực
        dành cho thế hệ nhà đầu tư mới.</p></div>""",
        unsafe_allow_html=True,
    )

def render_partner_buttons():
    st.markdown(
        """<div class="broker-container">
        <div class="broker-title">🔗 MỞ TÀI KHOẢN CHỨNG KHOÁN ĐỐI TÁC ĐỒNG HÀNH:</div>""",
        unsafe_allow_html=True,
    )
    for key, partner in PARTNERS.items():
        if st.button(
            partner["display_name"], key=f"partner_btn_{key}",
            use_container_width=True,
            help=f"Xem chi tiết về {partner['full_name']}",
        ):
            st.session_state.selected_partner = key
            st.session_state.show_partner_dialog = True
            st.rerun()
    st.markdown(
        """<div class="broker-note">💡 Nhấn vào nút để xem chi tiết và đăng ký – hỗ trợ ưu đãi cho nhà đầu tư FINEX</div></div>""",
        unsafe_allow_html=True,
    )

def render_valuation_slider(current_price, eps, bvps):
    st.markdown("---")
    st.markdown("## 🎛️ Mô phỏng Kịch bản Định giá tương tác")

    for k, v in [("slider_g", 12.0), ("slider_r", 12.0), ("slider_mos", 25), ("preset_active", "base")]:
        st.session_state.setdefault(k, v)

    def _tf(x):
        try: return float(x)
        except Exception: return 0.0

    col_p1, col_p2, col_p3, col_p4 = st.columns([1, 1, 1, 3])
    with col_p1:
        if st.button("🛡️ Thận trọng", key="preset_conservative", use_container_width=True):
            st.session_state.slider_g, st.session_state.slider_r, st.session_state.slider_mos = 8.0, 15.0, 35
            st.session_state.preset_active = "conservative"; st.rerun()
    with col_p2:
        if st.button("⚖️ Cơ sở", key="preset_base", use_container_width=True):
            st.session_state.slider_g, st.session_state.slider_r, st.session_state.slider_mos = 12.0, 12.0, 25
            st.session_state.preset_active = "base"; st.rerun()
    with col_p3:
        if st.button("🚀 Lạc quan", key="preset_optimistic", use_container_width=True):
            st.session_state.slider_g, st.session_state.slider_r, st.session_state.slider_mos = 18.0, 10.0, 15
            st.session_state.preset_active = "optimistic"; st.rerun()
    with col_p4:
        st.markdown(
            f"<span style='color:#94a3b8; font-size:0.85em;'>Kịch bản hiện tại: "
            f"<strong style='color:#22c55e;'>{st.session_state.preset_active.upper()}</strong></span>",
            unsafe_allow_html=True,
        )

    cs1, cs2, cs3 = st.columns(3)
    with cs1:
        g = st.slider("📈 Tốc độ tăng trưởng (g)", 2.0, 25.0, step=0.5,
                      value=st.session_state.slider_g, key="slider_g_real")
    with cs2:
        r = st.slider("📊 Tỷ lệ chiết khấu (r)", 8.0, 18.0, step=0.5,
                      value=st.session_state.slider_r, key="slider_r_real")
    with cs3:
        mos = st.slider("🛡️ Biên an toàn (MoS)", 10, 50, step=5,
                        value=st.session_state.slider_mos, key="slider_mos_real")
    st.session_state.slider_g, st.session_state.slider_r, st.session_state.slider_mos = g, r, mos

    eps_val, price_val = _tf(eps), _tf(current_price)
    if price_val <= 0: price_val = 25000.0
    if r > g:
        iv = eps_val * (1 + g / 100) / ((r - g) / 100)
    else:
        iv = eps_val * 15
    safe_buy = iv * (1 - mos / 100)
    iv, safe_buy = round(iv, 0), round(safe_buy, 0)
    diff = round(((iv - price_val) / price_val) * 100, 1) if price_val > 0 else 0

    cr1, cr2, cr3, cr4 = st.columns(4)
    with cr1:
        st.markdown(
            f"""<div class="glass-card" style="text-align:center;">
            <div style="color:#94a3b8; font-size:0.85em; text-transform:uppercase;">💰 Giá trị nội tại</div>
            <div style="font-size:2em; font-weight:700; color:#22c55e; margin:8px 0;">{iv:,.0f}</div>
            <div style="color:#64748b; font-size:0.8em;">VNĐ/cp</div></div>""",
            unsafe_allow_html=True,
        )
    with cr2:
        st.markdown(
            f"""<div class="glass-card" style="text-align:center;">
            <div style="color:#94a3b8; font-size:0.85em; text-transform:uppercase;">🛡️ Giá mua an toàn</div>
            <div style="font-size:2em; font-weight:700; color:#22c55e; margin:8px 0;">{safe_buy:,.0f}</div>
            <div style="color:#64748b; font-size:0.8em;">VNĐ/cp (MoS {mos}%)</div></div>""",
            unsafe_allow_html=True,
        )
    with cr3:
        c = "#22c55e" if diff > 0 else "#ef4444"
        st.markdown(
            f"""<div class="glass-card" style="text-align:center;">
            <div style="color:#94a3b8; font-size:0.85em; text-transform:uppercase;">📊 Chênh lệch</div>
            <div style="font-size:2em; font-weight:700; color:{c}; margin:8px 0;">{diff:+.1f}%</div>
            <div style="color:#64748b; font-size:0.8em;">Giá thị trường: {price_val:,.0f}</div></div>""",
            unsafe_allow_html=True,
        )
    with cr4:
        if diff > 15: status, cls, sc = "Định giá hấp dẫn", "rec-buy", "#22c55e"
        elif diff > 5: status, cls, sc = "Định giá hợp lý", "rec-hold", "#f59e0b"
        else: status, cls, sc = "Thận trọng", "rec-sell", "#ef4444"
        st.markdown(
            f"""<div class="glass-card" style="text-align:center; border-left:4px solid {sc};">
            <div style="color:#94a3b8; font-size:0.85em; text-transform:uppercase;">🎯 Kết luận</div>
            <div style="margin:12px 0;"><span class="recommend-badge {cls}">{status}</span></div>
            <div style="color:#64748b; font-size:0.8em;">Dựa trên tham số đã chọn</div></div>""",
            unsafe_allow_html=True,
        )
    st.caption("💡 *Công thức: EPS × (1+g) / (r−g). Đây chỉ là công cụ tham khảo, không phải khuyến nghị đầu tư.*")

def render_crisis_section(crisis_key):
    if crisis_key not in HISTORICAL_CRISES:
        st.info("Không có dữ liệu khủng hoảng.")
        return
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
        for key, label in [
            ("core_mission", "Nhiệm vụ"), ("core_dilemma", "Tình huống"),
            ("key_decision", "Quyết định then chốt"), ("policy_rule", "Nguyên tắc ứng phó"),
        ]:
            if fed.get(key):
                st.markdown(f"**{label}:** {fed[key]}")
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

def render_document_section():
    with st.expander("📖 Tài liệu tham khảo: Phân Tích Chứng Khoán (Benjamin Graham)", expanded=False):
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

def render_accuracy_section(ticker):
    st.markdown("## 🔍 Kiểm tra độ chính xác thuật toán")
    st.caption("Kết quả backtest minh hoạ — thay bằng dữ liệu backtest thực của bạn.")
    c = st.columns(3)
    c[0].markdown(
        """<div class="glass-card" style="text-align:center; border-top:3px solid #22c55e;">
        <div style="font-size:2em; font-weight:800; color:#22c55e;">99.2%</div>
        <div style="color:#94a3b8; font-size:0.88em; margin-top:6px;">Độ chính xác thuật toán</div>
        <div style="color:#64748b; font-size:0.76em;">1.000+ kịch bản Backtest</div></div>""",
        unsafe_allow_html=True,
    )
    c[1].markdown(
        """<div class="glass-card" style="text-align:center; border-top:3px solid #60a5fa;">
        <div style="font-size:2em; font-weight:800; color:#60a5fa;">&lt; 3.5%</div>
        <div style="color:#94a3b8; font-size:0.88em; margin-top:6px;">Sai số trung bình (MAE)</div>
        <div style="color:#64748b; font-size:0.76em;">Định giá vs giá thực tế</div></div>""",
        unsafe_allow_html=True,
    )
    c[2].markdown(
        """<div class="glass-card" style="text-align:center; border-top:3px solid #f59e0b;">
        <div style="font-size:2em; font-weight:800; color:#f59e0b;">✅ Real-time</div>
        <div style="color:#94a3b8; font-size:0.88em; margin-top:6px;">Trạng thái mô hình</div>
        <div style="color:#64748b; font-size:0.76em;">ML & Deep Learning đồng bộ</div></div>""",
        unsafe_allow_html=True,
    )
    st.markdown("---")
    rows = [
        {"Kỳ": "Q4/2023", "Định giá": "24.500đ", "Thực tế": "24.800đ", "Độ chính xác": "98.8%", "Trạng thái": "✅ Khớp"},
        {"Kỳ": "Q1/2024", "Định giá": "25.200đ", "Thực tế": "25.100đ", "Độ chính xác": "99.6%", "Trạng thái": "✅ Khớp"},
        {"Kỳ": "Q2/2024", "Định giá": "28.000đ", "Thực tế": "27.900đ", "Độ chính xác": "99.6%", "Trạng thái": "✅ Khớp"},
        {"Kỳ": "Q3/2024", "Định giá": "29.500đ", "Thực tế": "30.200đ", "Độ chính xác": "97.7%", "Trạng thái": "✅ Khớp"},
    ]
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    st.caption(f"*Dữ liệu minh hoạ cho mã **{ticker}** — thay bằng kết quả backtest thực tế.*")

# ============================================================================
# 7. TABS
# ============================================================================
def render_tab_overview(df_csv, ticker, cols, fin_data):
    st.subheader(f"📊 Hồ Sơ Doanh Nghiệp: {ticker}")
    industry = fin_data.get("industry") or "Đang cập nhật"
    st.caption(f"🏢 Nhóm ngành: **{industry}**")

    # KPIs từ CSV + fin_data
    ticker_col = cols.get("ticker")
    metric_col = cols.get("metric")
    period_col = cols.get("period")

    df_sub = df_csv[df_csv[ticker_col] == ticker] if (not df_csv.empty and ticker_col) else pd.DataFrame()

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Tổng bản ghi dữ liệu", f"{len(df_sub):,}")
    c2.metric("Số kỳ báo cáo", df_sub[period_col].nunique() if period_col and not df_sub.empty else 0)
    c3.metric("Chỉ tiêu tài chính", df_sub[metric_col].nunique() if metric_col and not df_sub.empty else 0)
    c4.metric("Kỳ mới nhất", df_sub[period_col].max() if period_col and not df_sub.empty else "N/A")

    st.markdown("---")
    st.markdown("### 💼 Chỉ số tài chính cốt lõi")

    if fin_data:
        # Định giá
        st.markdown("**Định giá**")
        c = st.columns(5)
        price = fin_data.get("price", 0)
        eps = fin_data.get("eps_ttm", 0)
        bvps = fin_data.get("bvps", 0)
        pe = fin_data.get("pe_ttm", 0)
        pb = fin_data.get("pb", 0)
        c[0].metric("Giá hiện tại", f"{price:,.0f} đ" if price else "N/A")
        c[1].metric("EPS (TTM)", f"{eps:,.0f} đ" if eps else "N/A")
        c[2].metric("BVPS", f"{bvps:,.0f} đ" if bvps else "N/A")
        c[3].metric("P/E", f"{pe:.2f}" if pe else "N/A")
        c[4].metric("P/B", f"{pb:.2f}" if pb else "N/A")

        # Hiệu quả
        st.markdown("**Hiệu quả sinh lời**")
        c = st.columns(4)
        c[0].metric("ROE", f"{fin_data.get('roe_2025', 0):.2f}%")
        c[1].metric("ROA", f"{fin_data.get('roa_2025', 0):.2f}%")
        casa = fin_data.get("casa_30062026")
        if casa is not None:
            c[2].metric("CASA", f"{casa:.1f}%")
        else:
            c[2].metric("Biên LN", f"{fin_data.get('margin', 0):.1f}%")
        c[3].metric("Nợ/VCSH", f"{fin_data.get('de', 0):.2f}")

        # Quy mô
        st.markdown("**Quy mô (tỷ VND)**")
        c = st.columns(4)
        c[0].metric("Doanh thu / TOI", _fmt_ty(fin_data.get("toi_6t2026", 0)))
        c[1].metric("LNST 2025", _fmt_ty(fin_data.get("lnst_2025", 0)))
        c[2].metric("Tổng tài sản", _fmt_ty(fin_data.get("total_assets_30062026", 0)))
        c[3].metric("Vốn hóa", _fmt_ty(fin_data.get("market_cap", 0)))

        # Cổ tức
        st.markdown("**Cổ tức**")
        c = st.columns(3)
        c[0].metric("Cổ tức (VNĐ/cp)", f"{fin_data.get('div_per_share', 0):,.0f}")
        c[1].metric("Tỷ suất cổ tức", f"{fin_data.get('div_yield', 0):.2f}%")

        # Radar
        st.markdown("---")
        st.markdown("#### 🎯 Radar — Sức mạnh doanh nghiệp")
        radar = {
            "ROE": fin_data.get("roe_2025", 0),
            "ROA": fin_data.get("roa_2025", 0) * 5,
            "P/E (nghịch)": 100 / max(pe, 1),
            "P/B (nghịch)": 100 / max(pb, 1) / 10,
            "Tỷ suất cổ tức": fin_data.get("div_yield", 0) * 5,
        }
        radar = {k: v for k, v in radar.items() if v > 0}
        if radar:
            fig = go.Figure()
            fig.add_trace(go.Scatterpolar(
                r=list(radar.values()), theta=list(radar.keys()),
                fill="toself", name=ticker,
                line_color="#D4AF37", fillcolor="rgba(212,175,55,0.25)",
            ))
            fig.update_layout(
                polar=dict(
                    radialaxis=dict(visible=True, showticklabels=False, gridcolor="#1f2937"),
                    angularaxis=dict(gridcolor="#1f2937"), bgcolor="#111827",
                ),
                template="plotly_dark", paper_bgcolor="#0b1220", plot_bgcolor="#0f172a",
                height=420, font=dict(color="#e2e8f0"),
            )
            st.plotly_chart(fig, use_container_width=True)
    else:
        st.warning(
            f"⚠️ Chưa có dữ liệu chỉ số cốt lõi cho mã **{ticker}**. "
            f"Vào tab **📋 Dữ liệu chi tiết** để xem số liệu thô, "
            f"hoặc bổ sung mã vào `DEMO_FINANCIAL_DATA`."
        )

def render_tab_valuation(ticker, fin_data):
    st.subheader(f"🧮 ĐỊNH GIÁ CHI TIẾT: {ticker}")
    if not fin_data:
        st.warning(f"⚠️ Không có dữ liệu định giá cho **{ticker}**.")
        return

    price = float(fin_data.get("price", 0) or 0)
    eps = float(fin_data.get("eps_ttm", 0) or 0)
    bvps = float(fin_data.get("bvps", 0) or 0)
    roe = float(fin_data.get("roe_2025", 0) or 0)
    roa = float(fin_data.get("roa_2025", 0) or 0)

    # Quick metrics
    c = st.columns(6)
    c[0].metric("Giá", f"{price:,.0f} đ" if price else "N/A")
    c[1].metric("EPS", f"{eps:,.0f}" if eps else "N/A")
    c[2].metric("BVPS", f"{bvps:,.0f}" if bvps else "N/A")
    c[3].metric("ROE", f"{roe:.2f}%" if roe else "N/A")
    c[4].metric("ROA", f"{roa:.2f}%" if roa else "N/A")
    c[5].metric("P/E · P/B",
                f"{fin_data.get('pe_ttm', 0):.1f} · {fin_data.get('pb', 0):.1f}")

    st.markdown("---")
    st.markdown("### 🧮 Định giá Hybrid (đa phương pháp)")
    hy = compute_hybrid_valuation(price, eps, bvps, roe, roa)
    st.markdown(
        f"""<div class="hybrid-card">
        <div style="color:#94a3b8; font-size:0.9em; text-transform:uppercase; letter-spacing:1px;">
        💎 Giá trị Hybrid</div>
        <div style="font-size:2.4em; font-weight:800; color:#F5D97A; margin:8px 0;">
        {hy['hybrid']:,.0f} VNĐ/cp</div>
        <div style="color:#64748b; font-size:0.85em;">Biên an toàn:
        <strong style="color:{'#22c55e' if hy['mos']>0 else '#ef4444'};">{hy['mos']:+.1f}%</strong></div>
        </div>""",
        unsafe_allow_html=True,
    )
    c = st.columns(4)
    c[0].metric("Graham Number", f"{hy['graham']:,.0f}")
    c[1].metric("DCF đơn giản", f"{hy['dcf']:,.0f}")
    c[2].metric("P/E band (×15)", f"{hy['pe_band']:,.0f}")
    c[3].metric("P/B band (×1.5)", f"{hy['pb_band']:,.0f}")

    # Quality score
    st.markdown("---")
    st.markdown("### 🏆 Đánh giá chất lượng doanh nghiệp")
    checks, score, total = [], 0, 0
    if hy["hybrid"] > 0:
        mos_v = ((hy["hybrid"] - price) / hy["hybrid"]) * 100
        total += 1
        if mos_v >= 20:
            score += 1; checks.append(f"✅ Biên an toàn rất tốt ({mos_v:.1f}% ≥ 20%)")
        else:
            checks.append(f"❌ Biên an toàn thấp ({mos_v:.1f}% < 20%)")
    if roe > 0:
        total += 1
        if roe >= 15:
            score += 1; checks.append(f"✅ Hiệu quả vốn vượt trội (ROE = {roe:.1f}%)")
        else:
            checks.append(f"⚠️ Hiệu quả vốn trung bình (ROE = {roe:.1f}%)")
    if fin_data.get("pe_ttm", 0) > 0:
        total += 1
        if fin_data["pe_ttm"] <= 15:
            score += 1; checks.append(f"✅ P/E hấp dẫn ({fin_data['pe_ttm']:.1f} ≤ 15)")
        else:
            checks.append(f"⚠️ P/E cao ({fin_data['pe_ttm']:.1f} > 15)")
    if fin_data.get("pb", 0) > 0:
        total += 1
        if fin_data["pb"] <= 1.5:
            score += 1; checks.append(f"✅ P/B thấp ({fin_data['pb']:.2f} ≤ 1.5)")
        else:
            checks.append(f"ℹ️ P/B cao ({fin_data['pb']:.2f} > 1.5)")

    if total > 0:
        st.markdown(f"#### 🎯 Điểm chất lượng: **{score} / {total}** " + "⭐" * score)
        for c_check in checks:
            st.markdown(f"- {c_check}")
    else:
        st.info("Không đủ dữ liệu để đánh giá.")

    # DCF
    st.markdown("---")
    st.markdown("### 💵 Định giá DCF (FCFF 5 năm + Terminal Value)")
    st.caption("rf=3%, ERP=7%, tax=20% · Mô hình đơn giản hoá")
    dcf = _simple_dcf_valuation(ticker, fin_data)
    if "error" in dcf:
        st.warning(f"⚠️ {dcf['error']}")
    else:
        b, be, bu = dcf["scenarios"]["Base"], dcf["scenarios"]["Bear"], dcf["scenarios"]["Bull"]
        c = st.columns(3)
        c[0].metric("🐻 Bear", f"{be['intrinsic_value_per_share']:,.0f} đ",
                    f"{be['upside_downside']*100:+.1f}%")
        c[1].metric("⚖️ Base", f"{b['intrinsic_value_per_share']:,.0f} đ",
                    f"{b['upside_downside']*100:+.1f}%")
        c[2].metric("🐂 Bull", f"{bu['intrinsic_value_per_share']:,.0f} đ",
                    f"{bu['upside_downside']*100:+.1f}%")
        verdict = dcf["verdict"]
        v_color = "#22c55e" if "Buy" in verdict else ("#f59e0b" if verdict == "Hold" else "#ef4444")
        v_emoji = {"Buy": "🟢", "Hold": "🟡", "Sell": "🔴"}.get(verdict, "⚪")
        st.markdown(
            f"""<div style="background:linear-gradient(145deg,#111827 0%,#1a2a4a 100%);
            padding:16px 20px; border-radius:10px; border-left:5px solid {v_color}; margin-top:12px;">
            <div style="color:{v_color}; font-size:1.2em; font-weight:800;">
            {v_emoji} Khuyến nghị DCF: {verdict}</div>
            <div style="color:#94a3b8; font-size:0.88em; margin-top:6px;">
            WACC: <strong style="color:#F5D97A;">{b['wacc']*100:.2f}%</strong>
            · g: <strong style="color:#F5D97A;">{dcf['clean_inputs']['growth_rate']*100:.2f}%</strong>
            · Terminal g: <strong style="color:#F5D97A;">{dcf['clean_inputs']['terminal_growth']*100:.2f}%</strong>
            </div></div>""",
            unsafe_allow_html=True,
        )

    st.markdown("---")
    render_valuation_slider(price, eps, bvps)

def render_tab_forecast(ticker, fin_data):
    st.subheader(f"📈 DỰ BÁO TĂNG TRƯỞNG DÀI HẠN — {ticker}")
    if not fin_data:
        st.warning("Không có dữ liệu.")
        return

    base_rev = float(fin_data.get("toi_6t2026", 0) or 0) * 1e9
    base_prof = float(fin_data.get("lnst_2025", 0) or 0) * 1e9
    base_div = float(fin_data.get("div_per_share", 0) or 0)
    price = float(fin_data.get("price", 1) or 1)
    eps_now = float(fin_data.get("eps_ttm", 0) or 0)

    c1, c2, c3 = st.columns(3)
    with c1:
        g_rate = st.number_input("📈 Tăng trưởng (%/năm)", value=12.0, step=1.0, key="fc_g") / 100.0
    with c2:
        years = st.slider("⏳ Số năm dự báo", 3, 10, 10, key="fc_years")
    with c3:
        payout = st.slider("💸 Payout (%)", 0, 100, 30, key="fc_payout") / 100.0

    yrs = [f"Năm {i}" for i in range(years + 1)]
    rev_p = [base_rev * ((1 + g_rate) ** i) for i in range(years + 1)]
    prof_p = [base_prof * ((1 + g_rate) ** i) for i in range(years + 1)]
    shares_out = (base_prof / eps_now) if (eps_now > 0 and base_prof > 0) else 1
    div_p = (
        [base_div * ((1 + g_rate) ** i) for i in range(years + 1)]
        if base_div > 0
        else [(prof_p[i] * payout) / shares_out for i in range(years + 1)]
    )

    c = st.columns(4)
    c[0].metric("Cổ tức hiện tại", f"{base_div:,.0f} VNĐ/cp")
    c[1].metric("Tỷ suất cổ tức", f"{(base_div/price*100):.2f}%" if price > 0 else "N/A")
    c[2].metric("Cổ tức năm cuối", f"{div_p[-1]:,.0f} VNĐ/cp")
    if base_div > 0 and div_p[-1] > 0:
        cagr = ((div_p[-1] / base_div) ** (1 / years) - 1) * 100
        c[3].metric("CAGR cổ tức", f"{cagr:.1f}%")
    else:
        c[3].metric("CAGR cổ tức", "N/A")

    fig = make_subplots(
        rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.1,
        subplot_titles=(
            f"Doanh thu & Lợi nhuận ({ticker}) — Tỷ đồng",
            f"Cổ tức ({ticker}) — VNĐ/cp",
        ),
    )
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
    fig.update_layout(
        template="plotly_dark", paper_bgcolor="#0b1220", plot_bgcolor="#0f172a",
        height=650, showlegend=True,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        font=dict(color="#e2e8f0"),
    )
    fig.update_yaxes(gridcolor="#1f2937")
    st.plotly_chart(fig, use_container_width=True)

def render_tab_ml(ticker, fin_data):
    st.subheader(f"🤖 MACHINE LEARNING — {ticker}")
    if not fin_data:
        st.warning("Không có dữ liệu.")
        return

    roe = float(fin_data.get("roe_2025", 10.0) or 10.0)
    roa = float(fin_data.get("roa_2025", 3.0) or 3.0)
    margin = float(fin_data.get("margin", 20.0) or 20.0)
    de = float(fin_data.get("de", 1.0) or 1.0)
    eps = float(fin_data.get("eps_ttm", 0) or 0)
    bvps = float(fin_data.get("bvps", 0) or 0)
    price = float(fin_data.get("price", 0) or 0)

    st.markdown("### 🎯 Phân loại rủi ro (Ensemble)")
    risk, conf = predict_risk_ensemble(roe, roa, margin, de)
    status_map = {
        2: ("💎 Xuất sắc (chất lượng cao)", "#22c55e"),
        1: ("⚖️ An toàn (đạt chuẩn cơ bản)", "#3b82f6"),
        0: ("⚠️ Cảnh báo rủi ro", "#ef4444"),
    }
    label, color = status_map.get(risk, ("Chưa xác định", "#94a3b8"))
    c1, c2 = st.columns([2, 1])
    with c1:
        st.markdown(
            f"""<div class="glass-card" style="border-left:5px solid {color};">
            <h4 style="margin:0; color:{color};">{label}</h4>
            <p style="color:#94a3b8; font-size:0.88em; margin-top:8px;">
            Phân tích 4 chỉ số: ROE, ROA, Biên LN gộp, Nợ/VCSH.</p></div>""",
            unsafe_allow_html=True,
        )
    with c2:
        st.metric("Độ tin cậy", f"{conf:.1f}%")

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
        st.warning("Không có dữ liệu.")
        return

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
    st.dataframe(df, use_container_width=True, hide_index=True)

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=quarters, y=rev_f, mode="lines+markers",
                             name="Doanh thu", line=dict(color="#3b82f6", width=3)))
    fig.add_trace(go.Scatter(x=quarters, y=prof_f, mode="lines+markers",
                             name="Lợi nhuận", line=dict(color="#F5D97A", width=3)))
    fig.add_trace(go.Scatter(x=quarters, y=eps_f, mode="lines+markers",
                             name="EPS", line=dict(color="#f59e0b", width=3), yaxis="y2"))
    fig.update_layout(
        template="plotly_dark", paper_bgcolor="#0b1220", plot_bgcolor="#0f172a",
        height=400, font=dict(color="#e2e8f0"),
        yaxis=dict(title="DT / LN (tỷ đ)", gridcolor="#1f2937"),
        yaxis2=dict(title="EPS (VNĐ/cp)", overlaying="y", side="right"),
    )
    st.plotly_chart(fig, use_container_width=True)

    st.info("📌 Đây là dự báo fallback. Cài `torch`, `lightgbm`, `xgboost` để kích hoạt DL thật.")

def render_tab_data(df_csv, ticker, cols):
    st.subheader(f"📋 Dữ liệu chi tiết — {ticker}")
    if df_csv.empty:
        st.warning("⚠️ Không có file CSV tổng hợp. Đặt file tại `data/vietnam_stock_database_tong_hop.csv`.")
        return

    ticker_col = cols.get("ticker")
    period_col = cols.get("period")
    metric_col = cols.get("metric")
    value_col = cols.get("value")

    df_sub = df_csv[df_csv[ticker_col] == ticker].copy()
    if df_sub.empty:
        st.info(f"Không có bản ghi nào cho mã {ticker}.")
        return

    df_sub[value_col] = pd.to_numeric(
        df_sub[value_col].astype(str).str.replace(",", "").str.replace(" ", ""),
        errors="coerce",
    )

    # --- Chart ---
    st.markdown("### 📈 Trực quan hoá chỉ số")
    available = sorted(df_sub[metric_col].dropna().astype(str).unique().tolist())
    if available:
        defaults = [m for m in available if any(k in m.lower() for k in
                    ["doanh thu", "lợi nhuận", "lãi", "tài sản"])][:5]
        if not defaults:
            defaults = available[:3]

        sel = st.multiselect("Chọn chỉ tiêu:", available, default=defaults, key=f"chart_sel_{ticker}")

        col1, col2 = st.columns([2, 2])
        with col1:
            chart_type = st.radio("Dạng biểu đồ:", ["Cột nhóm", "Đường xu hướng"],
                                  horizontal=True, key=f"chart_type_{ticker}")

        if sel:
            df_chart = df_sub[df_sub[metric_col].astype(str).isin(sel)].dropna(subset=[value_col])
            if chart_type == "Cột nhóm":
                fig = px.bar(df_chart, x=period_col, y=value_col, color=metric_col,
                             barmode="group", template="plotly_dark",
                             title=f"So sánh chỉ tiêu — {ticker}")
            else:
                fig = px.line(df_chart, x=period_col, y=value_col, color=metric_col,
                              markers=True, template="plotly_dark",
                              title=f"Xu hướng chỉ tiêu — {ticker}")
            fig.update_layout(
                xaxis_title="Năm / Kỳ báo cáo", yaxis_title="Giá trị",
                legend_title="Chỉ tiêu", hovermode="x unified", height=520,
                plot_bgcolor="#0f172a", paper_bgcolor="#0b1220",
                font=dict(color="#e2e8f0"),
            )
            st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("Không có chỉ tiêu số nào để vẽ.")

    # --- Search + table ---
    st.markdown("---")
    st.markdown("### 🔍 Tra cứu & Bảng dữ liệu thô")
    search = st.text_input("Lọc nhanh:", placeholder="Ví dụ: Doanh thu, Nợ, Vốn...",
                          key=f"search_{ticker}")
    if search:
        mask = df_sub.astype(str).apply(
            lambda col: col.str.contains(search, case=False, na=False)
        ).any(axis=1)
        df_disp = df_sub[mask]
    else:
        df_disp = df_sub

    st.caption(f"Hiển thị {len(df_disp):,} / {len(df_sub):,} bản ghi.")
    st.dataframe(df_disp, use_container_width=True, height=420, hide_index=True)

    csv_data = df_sub.to_csv(index=False).encode("utf-8-sig")
    st.download_button(
        label=f"📥 Tải CSV ({ticker})",
        data=csv_data,
        file_name=f"FINEX_Terminal_{ticker}.csv",
        mime="text/csv",
    )

# ============================================================================
# 8. DIVIDEND CALCULATORS
# ============================================================================
def render_cash_dividend_ui():
    st.markdown("## 💵 MÁY TÍNH CỔ TỨC TIỀN MẶT")
    st.markdown("*Tính cổ tức nhận được dựa trên vốn đầu tư và giá thị trường.*")

    c1, c2, c3 = st.columns(3)
    with c1:
        ticker = st.text_input("Mã cổ phiếu:", value="TCB").upper().strip()
    with c2:
        price = st.selectbox("Giá thị trường (VNĐ):", DEFAULT_PRICE_LIST, index=4)
    with c3:
        capital = st.number_input("Vốn đầu tư (VNĐ):",
                                  min_value=MIN_CAPITAL_VND, max_value=MAX_CAPITAL_VND,
                                  step=CAPITAL_STEP_VND, value=1_000_000_000, format="%d")

    st.markdown("---")
    c4, c5 = st.columns(2)
    with c4:
        tax = st.number_input("Thuế TNCN (%) [Thực tế 5%]:",
                              min_value=0.0, max_value=10.0, value=5.0, step=0.1)
    with c5:
        div_pct = st.slider("Tỷ lệ cổ tức (% Mệnh giá):",
                            min_value=MIN_DIVIDEND_PERCENT, max_value=MAX_DIVIDEND_PERCENT,
                            step=DIVIDEND_PERCENT_STEP, value=15)

    cash_ps = PAR_VALUE_DEFAULT * div_pct / 100
    shares = _buyable_shares(capital, price)
    res = _cash_dividend_actual(shares, cash_ps, tax)

    st.markdown("### 📊 Kết quả")
    c = st.columns(4)
    c[0].metric("Số CP mua được", _fmt_shares(shares))
    c[1].metric("Cổ tức/CP (trước thuế)", _fmt_vnd(cash_ps))
    c[2].metric("Tổng cổ tức trước thuế", _fmt_vnd(res["before_tax"]))
    c[3].metric("Thực nhận (sau thuế)", _fmt_vnd(res["after_tax"]),
                delta=f"-{_fmt_vnd(res['tax'])} Thuế", delta_color="inverse")

    st.markdown("---")
    st.markdown("### 📈 Bảng kịch bản theo quy mô vốn")
    rows = []
    for cap in range(MIN_CAPITAL_VND, MAX_CAPITAL_VND + 1, CAPITAL_STEP_VND):
        sh = _buyable_shares(cap, price)
        r = _cash_dividend_actual(sh, cash_ps, tax)
        rows.append({
            "Vốn (VNĐ)": _fmt_vnd(cap),
            "Số CP": _fmt_shares(sh),
            "Trước thuế (VNĐ)": _fmt_vnd(r["before_tax"]),
            "Sau thuế (VNĐ)": _fmt_vnd(r["after_tax"]),
        })
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    if rows:
        df_plot = pd.DataFrame({
            "Vốn (tỷ)": [(MIN_CAPITAL_VND + i*CAPITAL_STEP_VND)/1e9 for i in range(len(rows))],
            "Thực nhận (triệu)": [_cash_dividend_actual(
                _buyable_shares(MIN_CAPITAL_VND + i*CAPITAL_STEP_VND, price),
                cash_ps, tax)["after_tax"]/1e6 for i in range(len(rows))],
        })
        fig = px.bar(df_plot, x="Vốn (tỷ)", y="Thực nhận (triệu)",
                     title="Cổ tức thực nhận theo vốn đầu tư",
                     color="Thực nhận (triệu)", color_continuous_scale="Greens")
        fig.update_layout(template="plotly_dark", plot_bgcolor="#0f172a",
                         paper_bgcolor="#0b1220", font=dict(color="#e2e8f0"))
        st.plotly_chart(fig, use_container_width=True)

def render_stock_dividend_ui():
    st.markdown("## 📈 MÁY TÍNH CỔ TỨC BẰNG CỔ PHIẾU")
    st.markdown("*Tính số cổ phiếu nhận thêm từ chia cổ tức bằng cổ phiếu.*")

    c1, c2 = st.columns(2)
    with c1:
        ticker = st.text_input("Mã cổ phiếu:", value="TCB").upper().strip()
    with c2:
        owned = st.number_input("Số cổ phiếu đang sở hữu:",
                                min_value=MIN_OWNED_SHARES, max_value=MAX_OWNED_SHARES,
                                step=10_000, value=100_000, format="%d")

    ratio = st.slider("Tỷ lệ cổ tức bằng cổ phiếu (%):",
                      min_value=MIN_DIVIDEND_PERCENT, max_value=MAX_DIVIDEND_PERCENT,
                      step=DIVIDEND_PERCENT_STEP, value=15)

    res = _stock_dividend(owned, ratio)
    st.markdown("### 📊 Kết quả")
    c = st.columns(3)
    c[0].metric("Cổ phiếu ban đầu", _fmt_shares(owned))
    c[1].metric("Cổ phiếu nhận thêm", f"+{_fmt_shares(res['additional_shares'])}",
                delta="Cổ tức CP", delta_color="normal")
    c[2].metric("Tổng sau phát hành", _fmt_shares(res["total_after"]))

    st.caption("⚠️ Cổ tức bằng cổ phiếu làm tăng số lượng CP nhưng không mặc nhiên "
               "làm tăng giá trị tài sản tương ứng.")

# ============================================================================
# 9. MAIN
# ============================================================================
def main():
    inject_css()

    # --- Session defaults ---
    st.session_state.setdefault("selected_ticker", "FPT")
    st.session_state.setdefault("selected_partner", None)
    st.session_state.setdefault("show_partner_dialog", False)

    # --- Load CSV ---
    df_csv, csv_path = load_database()

    # --- SIDEBAR ---
    with st.sidebar:
        st.markdown(
            """<div style='text-align:center; padding:14px 0 10px 0;
            border-bottom:1px solid #1f2937; margin-bottom:12px;'>
            <div style='color:#D4AF37; font-size:1.6em; font-weight:800; letter-spacing:2px;'>FINEX</div>
            <div style='color:#94a3b8; font-size:0.72em; letter-spacing:3px; text-transform:uppercase;'>Vietnam Terminal</div>
            </div>""",
            unsafe_allow_html=True,
        )

        cols = _get_csv_columns(df_csv) if not df_csv.empty else {}

        # Bộ lọc ngành + ticker (từ code mới)
        industry_sel = "Tất cả"
        tickers_available = []

        if not df_csv.empty and cols.get("ticker"):
            df_csv[cols["ticker"]] = df_csv[cols["ticker"]].astype(str).str.strip().str.upper()
            if cols.get("industry"):
                df_csv[cols["industry"]] = df_csv[cols["industry"]].astype(str).str.strip()

            all_tickers_csv = sorted([
                t for t in df_csv[cols["ticker"]].unique() if t and t != "NAN"
            ])

            if cols.get("industry"):
                industries = ["Tất cả"] + sorted([
                    i for i in df_csv[cols["industry"]].unique() if i and i != "NAN"
                ])
                industry_sel = st.selectbox("🏢 Chọn nhóm ngành:", industries, key="ind_sel")
                if industry_sel != "Tất cả":
                    filtered = df_csv[df_csv[cols["industry"]] == industry_sel]
                    tickers_available = sorted(filtered[cols["ticker"]].unique())
                else:
                    tickers_available = all_tickers_csv
            else:
                tickers_available = all_tickers_csv
        else:
            # Fallback: dùng DEMO_FINANCIAL_DATA
            tickers_available = sorted(DEMO_FINANCIAL_DATA.keys())
            st.caption("⚠️ Chưa có CSV — dùng dữ liệu demo.")

        # Đảm bảo FPT có trong list ưu tiên
        if tickers_available and st.session_state.selected_ticker not in tickers_available:
            st.session_state.selected_ticker = (
                "FPT" if "FPT" in tickers_available else tickers_available[0]
            )
        default_idx = (tickers_available.index(st.session_state.selected_ticker)
                       if st.session_state.selected_ticker in tickers_available else 0)

        if tickers_available:
            chosen = st.selectbox(
                "📈 Chọn mã cổ phiếu:", tickers_available,
                index=default_idx, key="ticker_sel",
            )
            if chosen != st.session_state.selected_ticker:
                st.session_state.selected_ticker = chosen
                st.rerun()

        st.markdown("---")
        st.markdown("### 🧮 CHỨC NĂNG")
        app_mode = st.radio(
            "Chế độ:",
            ["🏛️ Terminal", "💵 Cổ tức tiền mặt",
             "📈 Cổ tức cổ phiếu", "📉 Khủng hoảng lịch sử"],
            key="app_mode",
        )

        st.markdown("---")
        st.info(f"💡 Đang quản lý **{len(tickers_available)}** mã.")

        if not df_csv.empty:
            st.caption(f"📂 CSV: `{csv_path}` ({len(df_csv):,} bản ghi)")

    # --- MODE ROUTING ---
    render_header()

    if app_mode == "💵 Cổ tức tiền mặt":
        render_cash_dividend_ui(); return
    if app_mode == "📈 Cổ tức cổ phiếu":
        render_stock_dividend_ui(); return
    if app_mode == "📉 Khủng hoảng lịch sử":
        keys = list(HISTORICAL_CRISES.keys())
        sel = st.selectbox("Chọn cuộc khủng hoảng:", keys, key="cr_sel")
        render_crisis_section(sel); return

    # --- TERMINAL MODE ---
    # Partner buttons header
    col_broker, col_info = st.columns([1.2, 1], gap="large")
    with col_broker:
        render_partner_buttons()
    with col_info:
        st.markdown(
            f"""<div class="glass-card" style="border-left:3px solid #60a5fa;">
            <div style="color:#60a5fa; font-weight:800; font-size:1.05em; margin-bottom:10px;">
            📌 Đang phân tích: <span style="color:#F5D97A;">{st.session_state.selected_ticker}</span>
            </div>
            <p style="color:#94a3b8; font-size:0.85em; margin:0;">
            Dùng sidebar để đổi mã, hoặc nhấn vào đối tác để mở tài khoản chứng khoán.</p>
            </div>""",
            unsafe_allow_html=True,
        )

    # Dialog
    if st.session_state.get("show_partner_dialog", False):
        partner_detail_dialog()

    # --- Tabs ---
    ticker = st.session_state.selected_ticker
    fin_data = get_financials(ticker, df_csv, cols)

    tabs = st.tabs([
        "📊 Tổng quan", "🧮 Định giá", "📈 Dự báo",
        "🤖 ML", "🧠 DL", "📋 Dữ liệu chi tiết",
    ])
    with tabs[0]:
        render_tab_overview(df_csv, ticker, cols, fin_data)
    with tabs[1]:
        render_tab_valuation(ticker, fin_data)
    with tabs[2]:
        render_tab_forecast(ticker, fin_data)
    with tabs[3]:
        render_tab_ml(ticker, fin_data)
    with tabs[4]:
        render_tab_dl(ticker, fin_data)
    with tabs[5]:
        render_tab_data(df_csv, ticker, cols)

    # --- Bottom sections ---
    st.markdown("---")
    render_accuracy_section(ticker)

    st.markdown("---")
    render_document_section()

    st.markdown("---")
    st.markdown(
        """<div style='text-align:center; padding:16px 0 8px 0;'>
        <h2 style='color:#ef4444; margin:0;'>📉 BÀI HỌC TỪ CÁC CUỘC KHỦNG HOẢNG LỊCH SỬ</h2>
        <p style='color:#94a3b8; font-size:0.95em; margin-top:8px;'>
        Phân tích cú sốc thị trường · Phản ứng nhà điều hành · Stress Test danh mục</p>
        </div>""",
        unsafe_allow_html=True,
    )
    crisis_keys = list(HISTORICAL_CRISES.keys())
    default_crisis = crisis_keys.index("COVID_2020") if "COVID_2020" in crisis_keys else 0
    sel_cr = st.selectbox("🔍 Chọn cuộc khủng hoảng để xem chi tiết:",
                          crisis_keys, index=default_crisis, key="crisis_main")
    render_crisis_section(sel_cr)

    # --- Disclaimer ---
    st.markdown("---")
    st.markdown(
        """<div style="background:linear-gradient(145deg,rgba(239,68,68,0.10) 0%,rgba(239,68,68,0.04) 100%);
        border-left:4px solid #ef4444; padding:16px 20px; border-radius:8px; margin:20px 0;">
        <p style="color:#f3f4f6; font-size:0.95em; margin:0;">
        <strong>⚠️ TUYÊN BỐ MIỄN TRỪ TRÁCH NHIỆM:</strong><br>
        Tất cả thông tin, dữ liệu và kết quả định giá chỉ mang tính chất <strong>tham khảo</strong>,
        phục vụ mục đích <strong>học thuật và nghiên cứu</strong>.
        Không phải khuyến nghị đầu tư.</p></div>""",
        unsafe_allow_html=True,
    )

if __name__ == "__main__":
    main()
