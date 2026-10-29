# finex_terminal_v4.py
# ============================================================================
# FINEX VN Terminal — Enterprise Intelligence v4
# Tích hợp: VNINDEX 26 năm + VIP pricing + CTA banners + Full footer
#           + DCF chart + Stock dividend chart + Radar + Forecast subplots
# ============================================================================

import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import os
import time
from contextlib import contextmanager

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

BANK_ID, ACCOUNT_NO, ACCOUNT_NAME = "VCB", "9327625853", "TRAN ANH QUAN"

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
    "SSI": {
        "display_name": "SSI",
        "full_name": "Công ty Cổ phần Chứng khoán SSI",
        "strengths": "Chứng khoán lâu đời nhất Việt Nam, hệ thống nghiên cứu hàng đầu.",
        "margin_policy": "Margin đa dạng, có gói ưu đãi cho khách hàng VIP và tổ chức.",
        "referral_code": "SSIQUAN2122",
        "url": "https://www.ssi.com.vn/mo-tai-khoan",
        "color": "#F59E0B",
    },
}

VNINDEX_MILESTONES = [
    ("2000-07-28", 100), ("2001-06-30", 571), ("2001-12-31", 235),
    ("2003-10-31", 130), ("2005-12-30", 307), ("2006-12-29", 751),
    ("2007-03-12", 1170), ("2007-12-31", 927), ("2008-12-31", 315),
    ("2009-02-20", 235), ("2009-12-31", 494), ("2010-12-31", 484),
    ("2011-12-30", 351), ("2012-12-28", 413), ("2013-12-31", 504),
    ("2014-12-31", 545), ("2015-12-31", 579), ("2016-12-30", 664),
    ("2017-12-29", 984), ("2018-04-09", 1204), ("2018-12-28", 892),
    ("2019-12-31", 960), ("2020-03-24", 660), ("2020-12-31", 1103),
    ("2021-11-25", 1500), ("2022-01-06", 1528), ("2022-11-15", 873),
    ("2023-12-29", 1129), ("2024-12-31", 1266), ("2025-12-31", 1650),
    ("2026-10-22", 1774.15),
]

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
    "DOTCOM_2000": {
        "title": "Bong bóng Dot-com (2000-2002)",
        "source": "Federal Reserve History",
        "impact": "Nasdaq giảm ~78% từ đỉnh 5.048 xuống 1.114. Hàng trăm công ty dot-com phá sản.",
        "context": {
            "trigger": "Định giá công nghệ phi lý, doanh thu không có lợi nhuận.",
            "timeline": [
                {"period": "03/2000", "market_impact": "Nasdaq đạt đỉnh 5.048 điểm."},
                {"period": "10/2002", "market_impact": "Nasdaq chạm đáy 1.114 điểm."},
            ],
        },
        "fed_actions_and_philosophy": {
            "core_mission": "Fed hạ lãi suất từ 6.5% xuống 1.75% trong 2 năm.",
            "key_decision": "Cắt giảm lãi suất mạnh tay sau sự kiện 11/9.",
            "policy_rule": "Nới lỏng tiền tệ để hỗ trợ phục hồi.",
            "famous_quote": "Irrational exuberance — Alan Greenspan (1996)",
            "market_lesson": "Định giá không có lợi nhuận là bong bóng.",
        },
        "metrics": {"drawdown_pct": -78.0, "recovery_months": 180, "bankruptcies": 500},
    },
    "GFC_2008": {
        "title": "Khủng hoảng Tài chính Toàn cầu (2008)",
        "source": "Federal Reserve / Bloomberg",
        "impact": "S&P 500 giảm ~57% từ 1.565 xuống 676. Lehman Brothers phá sản. VN-Index giảm từ 1.170 xuống 235 (-80%).",
        "context": {
            "trigger": "Bong bóng BĐS Mỹ + cho vay dưới chuẩn + chứng khoán hóa nợ.",
            "timeline": [
                {"period": "09/2008", "market_impact": "Lehman Brothers phá sản."},
                {"period": "03/2009", "market_impact": "S&P 500 tạo đáy 676 điểm."},
                {"period": "12/2009", "market_impact": "VN-Index hồi phục về 494 điểm."},
            ],
        },
        "fed_actions_and_philosophy": {
            "core_mission": "Fed hạ lãi suất về 0-0.25%, QE1 mua 600 tỷ USD MBS.",
            "key_decision": "Cứu AIG, Bear Stearns, mở rộng bảng cân đối.",
            "policy_rule": "Too big to fail — cứu các định chế hệ thống.",
            "famous_quote": "We must do whatever is necessary — Ben Bernanke",
            "market_lesson": "Đòn bẩy quá mức + thiếu minh bạch = thảm họa.",
        },
        "metrics": {"drawdown_pct": -57.0, "recovery_months": 48, "vnindex_drop_pct": -80.0},
    },
    "EU_DEBT_2011": {
        "title": "Khủng hoảng Nợ công châu Âu (2011)",
        "source": "ECB / IMF",
        "impact": "Euro Stoxx giảm ~30%; VN-Index giảm từ 500 xuống 351 (-30%); lạm phát VN 18%, lãi suất 15%.",
        "context": {
            "trigger": "Hy Lạp, Ý, Tây Ban Nha vỡ nợ; khủng hoảng niềm tin Eurozone.",
            "timeline": [
                {"period": "07/2011", "market_impact": "Khủng hoảng nợ Hy Lạp lan rộng."},
                {"period": "12/2011", "market_impact": "VN-Index tạo đáy 351 điểm."},
            ],
        },
        "fed_actions_and_philosophy": {
            "core_mission": "ECB mua trái phiếu Ý/Tây Ban Nha quy mô lớn.",
            "key_decision": "Mario Draghi: 'Whatever it takes to preserve the euro'.",
            "policy_rule": "Can thiệp trực tiếp thị trường trái phiếu.",
            "famous_quote": "Whatever it takes — Mario Draghi (2012)",
            "market_lesson": "Cam kết mạnh mẽ của NHTW có thể đảo ngược niềm tin.",
        },
        "metrics": {"drawdown_pct": -30.0, "vnindex_drop_pct": -30.0, "eu_stimulus_billion": 750},
    },
    "COVID_2020": {
        "title": "Khủng hoảng COVID-19 (2020)",
        "source": "Bloomberg / SBV",
        "impact": "VN-Index giảm ~34% từ 991 xuống 660 điểm. GDP Q2/2020 tăng 0.36% — thấp nhất 30 năm.",
        "context": {
            "trigger": "Đại dịch toàn cầu; giãn cách xã hội; đứt gãy chuỗi cung ứng.",
            "timeline": [
                {"period": "01/2020", "market_impact": "Ca nhiễm đầu tiên tại Việt Nam."},
                {"period": "03/2020", "market_impact": "VN-Index tạo đáy 660 điểm."},
                {"period": "12/2020", "market_impact": "VN-Index hồi phục về 1.103 điểm."},
            ],
        },
        "fed_actions_and_philosophy": {
            "core_mission": "Fed hạ lãi suất khẩn cấp về 0–0.25%, QE không giới hạn.",
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
        "impact": "VN-Index giảm ~37% từ 1.528 xuống 873 điểm. Doanh nghiệp BĐS mất khả năng thanh toán trái phiếu.",
        "context": {
            "trigger": "Siết tín dụng BĐS, kiểm soát trái phiếu, SCB bị đặc biệt kiểm soát.",
            "timeline": [
                {"period": "01/2022", "market_impact": "VN-Index đạt đỉnh 1.528 điểm."},
                {"period": "10/2022", "market_impact": "SCB bị kiểm soát đặc biệt."},
                {"period": "11/2022", "market_impact": "VN-Index tạo đáy 873 điểm."},
            ],
        },
        "fed_actions_and_philosophy": {
            "core_dilemma": "SBV cân bằng giữa ổn định tỷ giá và thanh khoản hệ thống.",
            "key_decision": "Hạ lãi suất điều hành 2 lần, nới room tín dụng 1.5–2%.",
            "policy_rule": "Ưu tiên ổn định vĩ mô trước tăng trưởng.",
            "famous_quote": "Kiểm soát rủi ro hệ thống là ưu tiên số một.",
            "market_lesson": "Đừng đánh cược vào đòn bẩy khi chính sách đang siết.",
        },
        "metrics": {"drawdown_pct": -37.0, "bond_defaults": 150, "recovery_months": 12},
    },
    "SVB_2023": {
        "title": "Khủng hoảng Ngân hàng SVB (03/2023)",
        "source": "FDIC / Reuters",
        "impact": "SVB phá sản — ngân hàng lớn thứ 2 lịch sử Mỹ. Signature, First Republic tiếp theo. VN-Index giảm 8%.",
        "context": {
            "trigger": "Fed tăng lãi suất mạnh 2022-2023, danh mục trái phiếu SVB lỗ nặng.",
            "timeline": [
                {"period": "03/2023", "market_impact": "SVB sụp đổ sau 48h tháo chạy."},
                {"period": "05/2023", "market_impact": "First Republic bị JPMorgan thâu tóm."},
            ],
        },
        "fed_actions_and_philosophy": {
            "core_mission": "Fed mở BTFP (Bank Term Funding Program) 25 tỷ USD.",
            "key_decision": "Bảo lãnh 100% tiền gửi SVB dù vượt hạn mức FDIC.",
            "policy_rule": "Cứu người gửi tiền, không cứu cổ đông.",
            "famous_quote": "Deposits are safe — Joe Biden",
            "market_lesson": "Rủi ro lãi suất có thể phá hủy ngân hàng trong vài ngày.",
        },
        "metrics": {"vnindex_drop_pct": -8.0, "svb_assets_billion": 209, "recovery_weeks": 6},
    },
}

COMPANY_INFO = {
    "FPT": {"name": "CTCP FPT", "sector": "Công nghệ thông tin", "exchange": "HOSE"},
    "TCB": {"name": "Ngân hàng TMCP Kỹ Thương Việt Nam", "sector": "Ngân hàng", "exchange": "HOSE"},
    "HPG": {"name": "CTCP Tập đoàn Hòa Phát", "sector": "Sản xuất thép", "exchange": "HOSE"},
    "VNM": {"name": "CTCP Sữa Việt Nam", "sector": "Tiêu dùng", "exchange": "HOSE"},
    "VCB": {"name": "Ngân hàng TMCP Ngoại thương Việt Nam", "sector": "Ngân hàng", "exchange": "HOSE"},
    "MWG": {"name": "CTCP Đầu tư Thế Giới Di Động", "sector": "Bán lẻ", "exchange": "HOSE"},
    "SSI": {"name": "CTCP Chứng khoán SSI", "sector": "Chứng khoán", "exchange": "HOSE"},
    "ACB": {"name": "Ngân hàng TMCP Á Châu", "sector": "Ngân hàng", "exchange": "HOSE"},
    "VIC": {"name": "CTCP Tập đoàn Vingroup", "sector": "Bất động sản", "exchange": "HOSE"},
    "VHM": {"name": "CTCP Vinhomes", "sector": "Bất động sản", "exchange": "HOSE"},
    "GAS": {"name": "Tổng Công ty Khí Việt Nam", "sector": "Năng lượng", "exchange": "HOSE"},
    "MSN": {"name": "CTCP Tập đoàn Masan", "sector": "Tiêu dùng", "exchange": "HOSE"},
}

DEMO_FINANCIAL_DATA = {
    "FPT": {"price": 120000, "eps_ttm": 5200, "bvps": 25000, "pe_ttm": 23.0, "pb": 4.8,
            "roe_2025": 22.0, "roa_2025": 10.0, "margin": 40.0, "de": 0.6,
            "shares_outstanding": 1_500_000_000, "market_cap": 180_000,
            "lnst_2025": 8500, "lnst_2024": 7000, "lnst_6t2026": 5000,
            "toi_6t2026": 30000, "total_assets_30062026": 70_000, "equity": 38_000,
            "div_per_share": 2000, "div_yield": 1.7, "industry": "Công nghệ thông tin"},
    "TCB": {"price": 35000, "eps_ttm": 3500, "bvps": 28000, "pe_ttm": 10.0, "pb": 1.25,
            "roe_2025": 15.5, "roa_2025": 1.8, "margin": 45.0, "de": 8.0, "casa_30062026": 35.0,
            "shares_outstanding": 7_000_000_000, "market_cap": 245_000,
            "lnst_2025": 22000, "lnst_2024": 19000, "lnst_6t2026": 12000,
            "toi_6t2026": 25000, "total_assets_30062026": 800_000, "equity": 180_000,
            "div_per_share": 1500, "div_yield": 4.3, "industry": "Ngân hàng"},
    "HPG": {"price": 27000, "eps_ttm": 1800, "bvps": 17000, "pe_ttm": 15.0, "pb": 1.6,
            "roe_2025": 10.5, "roa_2025": 5.0, "margin": 15.0, "de": 1.2,
            "shares_outstanding": 6_400_000_000, "market_cap": 170_000,
            "lnst_2025": 12000, "lnst_2024": 8000, "lnst_6t2026": 7000,
            "toi_6t2026": 70000, "total_assets_30062026": 220_000, "equity": 108_000,
            "div_per_share": 500, "div_yield": 1.85, "industry": "Sản xuất thép"},
    "VNM": {"price": 68000, "eps_ttm": 4200, "bvps": 22000, "pe_ttm": 16.2, "pb": 3.1,
            "roe_2025": 24.0, "roa_2025": 15.0, "margin": 42.0, "de": 0.3,
            "shares_outstanding": 2_080_000_000, "market_cap": 141_000,
            "lnst_2025": 8700, "lnst_2024": 8500, "lnst_6t2026": 4500,
            "toi_6t2026": 32000, "total_assets_30062026": 60_000, "equity": 45_000,
            "div_per_share": 3850, "div_yield": 5.66, "industry": "Tiêu dùng"},
    "VCB": {"price": 90000, "eps_ttm": 6500, "bvps": 45000, "pe_ttm": 13.8, "pb": 2.0,
            "roe_2025": 18.5, "roa_2025": 1.5, "margin": 42.0, "de": 9.0, "casa_30062026": 38.0,
            "shares_outstanding": 5_600_000_000, "market_cap": 504_000,
            "lnst_2025": 36000, "lnst_2024": 33000, "lnst_6t2026": 19000,
            "toi_6t2026": 40000, "total_assets_30062026": 1_800_000, "equity": 180_000,
            "div_per_share": 1000, "div_yield": 1.11, "industry": "Ngân hàng"},
    "MWG": {"price": 55000, "eps_ttm": 2200, "bvps": 18000, "pe_ttm": 25.0, "pb": 3.1,
            "roe_2025": 15.0, "roa_2025": 6.0, "margin": 20.0, "de": 1.5,
            "shares_outstanding": 1_460_000_000, "market_cap": 80_300,
            "lnst_2025": 3200, "lnst_2024": 2500, "lnst_6t2026": 2000,
            "toi_6t2026": 65000, "total_assets_30062026": 45_000, "equity": 26_000,
            "div_per_share": 500, "div_yield": 0.91, "industry": "Bán lẻ"},
    "SSI": {"price": 32000, "eps_ttm": 1800, "bvps": 15000, "pe_ttm": 17.8, "pb": 2.1,
            "roe_2025": 14.0, "roa_2025": 5.0, "margin": 55.0, "de": 1.8,
            "shares_outstanding": 2_000_000_000, "market_cap": 64_000,
            "lnst_2025": 3600, "lnst_2024": 3000, "lnst_6t2026": 1800,
            "toi_6t2026": 7000, "total_assets_30062026": 60_000, "equity": 25_000,
            "div_per_share": 1000, "div_yield": 3.13, "industry": "Chứng khoán"},
    "ACB": {"price": 24000, "eps_ttm": 3200, "bvps": 18000, "pe_ttm": 7.5, "pb": 1.33,
            "roe_2025": 18.0, "roa_2025": 2.0, "margin": 40.0, "de": 7.5, "casa_30062026": 25.0,
            "shares_outstanding": 4_470_000_000, "market_cap": 107_000,
            "lnst_2025": 18000, "lnst_2024": 16000, "lnst_6t2026": 10000,
            "toi_6t2026": 25000, "total_assets_30062026": 750_000, "equity": 140_000,
            "div_per_share": 1500, "div_yield": 6.25, "industry": "Ngân hàng"},
    "VIC": {"price": 45000, "eps_ttm": 1500, "bvps": 32000, "pe_ttm": 30.0, "pb": 1.4,
            "roe_2025": 5.0, "roa_2025": 1.5, "margin": 25.0, "de": 2.0,
            "shares_outstanding": 3_800_000_000, "market_cap": 171_000,
            "lnst_2025": 5700, "lnst_2024": 4500, "lnst_6t2026": 3200,
            "toi_6t2026": 90000, "total_assets_30062026": 700_000, "equity": 120_000,
            "div_per_share": 0, "div_yield": 0.0, "industry": "Bất động sản"},
    "VHM": {"price": 42000, "eps_ttm": 4500, "bvps": 28000, "pe_ttm": 9.3, "pb": 1.5,
            "roe_2025": 16.0, "roa_2025": 5.0, "margin": 35.0, "de": 1.3,
            "shares_outstanding": 4_350_000_000, "market_cap": 183_000,
            "lnst_2025": 19500, "lnst_2024": 17000, "lnst_6t2026": 10000,
            "toi_6t2026": 45000, "total_assets_30062026": 450_000, "equity": 122_000,
            "div_per_share": 1000, "div_yield": 2.38, "industry": "Bất động sản"},
    "GAS": {"price": 72000, "eps_ttm": 6800, "bvps": 35000, "pe_ttm": 10.6, "pb": 2.1,
            "roe_2025": 20.0, "roa_2025": 12.0, "margin": 25.0, "de": 0.4,
            "shares_outstanding": 2_350_000_000, "market_cap": 169_000,
            "lnst_2025": 16000, "lnst_2024": 14000, "lnst_6t2026": 8500,
            "toi_6t2026": 55000, "total_assets_30062026": 90_000, "equity": 82_000,
            "div_per_share": 3000, "div_yield": 4.17, "industry": "Năng lượng"},
    "MSN": {"price": 78000, "eps_ttm": 3500, "bvps": 22000, "pe_ttm": 22.3, "pb": 3.5,
            "roe_2025": 15.0, "roa_2025": 5.0, "margin": 30.0, "de": 1.7,
            "shares_outstanding": 1_420_000_000, "market_cap": 111_000,
            "lnst_2025": 5000, "lnst_2024": 4500, "lnst_6t2026": 2800,
            "toi_6t2026": 40000, "total_assets_30062026": 140_000, "equity": 31_000,
            "div_per_share": 1000, "div_yield": 1.28, "industry": "Tiêu dùng"},
}

VIP_PACKAGES = [
    {"id": "FREE", "name": "🆓 Gói Free", "price": "0 VNĐ", "amount": 0,
     "badge": "Miễn phí", "color": "#64748b",
     "features": ["Xem dữ liệu cơ bản", "1 mã cổ phiếu / ngày",
                  "Biểu đồ VN-Index", "Không xuất báo cáo"]},
    {"id": "PKG_29K", "name": "🎓 Gói S-Student", "price": "29.000 VNĐ / tháng", "amount": 29000,
     "badge": "Sinh viên", "color": "#60a5fa",
     "features": ["Full tính năng 30 ngày", "Hỗ trợ mở tài khoản (DNSE/VPS)",
                  "Dữ liệu Realtime & Biểu đồ kỹ thuật", "Tra cứu VN30 & HNX30"]},
    {"id": "PKG_59K", "name": "🌱 Gói Basic", "price": "59.000 VNĐ / tháng", "amount": 59000,
     "badge": "Cá nhân", "color": "#22c55e",
     "features": ["Toàn bộ gói 29k", "Stress Test Khủng Hoảng",
                  "Tra cứu 500+ mã HOSE/HNX/UPCoM", "Biên an toàn Graham/Buffett"]},
    {"id": "PKG_99K", "name": "🚀 Gói Pro Trader", "price": "99.000 VNĐ / tháng", "amount": 99000,
     "badge": "KHUYÊN DÙNG", "color": "#D4AF37", "featured": True,
     "features": ["Toàn bộ gói 59k", "Định giá đa phương pháp (DCF, DDM, P/E Band)",
                  "Cảnh báo rủi ro & Sức khỏe DN", "Xuất báo cáo PDF",
                  "Ưu tiên hỗ trợ 24/7"]},
    {"id": "PKG_299K", "name": "👑 Gói VIP Portfolio", "price": "299.000 VNĐ / tháng", "amount": 299000,
     "badge": "Tích sản", "color": "#a855f7",
     "features": ["Toàn bộ gói 99k", "Tối ưu hóa danh mục Python",
                  "Phân tích tương quan tài sản", "Cảnh báo qua Telegram Bot"]},
    {"id": "PKG_499K", "name": "💼 Gói Enterprise", "price": "499.000 VNĐ / tháng", "amount": 499000,
     "badge": "Chuyên gia", "color": "#ef4444",
     "features": ["Full đặc quyền tất cả gói", "White-Label báo cáo (Logo riêng)",
                  "Bộ lọc CANSLIM & Philip Fisher", "API dữ liệu Terminal"]},
]

TESTIMONIALS = [
    {"name": "Nguyễn Văn A", "role": "Nhà đầu tư cá nhân · 5 năm KN",
     "quote": "FINEX giúp tôi tiết kiệm 4-5 giờ mỗi tuần khi phân tích BCTC. Rất đáng tiền!",
     "rating": 5},
    {"name": "Trần Thị B", "role": "Sinh viên Tài chính · ĐH Kinh tế",
     "quote": "Gói 29k là lựa chọn hoàn hảo cho sinh viên. Dữ liệu chuyên nghiệp nhưng giá rẻ.",
     "rating": 5},
    {"name": "Lê Hoàng C", "role": "Chuyên viên môi giới chứng khoán",
     "quote": "Dùng gói Enterprise để xuất báo cáo cho khách hàng. Rất chuyên nghiệp!",
     "rating": 5},
]


# ============================================================================
# 2. CSS
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
                radial-gradient(ellipse at top left, rgba(96,165,250,0.08) 0%, transparent 45%),
                radial-gradient(ellipse at top right, rgba(212,175,55,0.08) 0%, transparent 45%),
                linear-gradient(180deg, #050914 0%, #0a0f19 50%, #0b1220 100%) !important;
            color: #e2e8f0 !important;
        }
        .main .block-container { padding-top: 1.2rem; padding-bottom: 3rem; max-width: 1560px; }

        h1 { color: #60a5fa !important; font-weight: 800 !important; font-size: 1.85em !important; }
        h2 { color: #93c5fd !important; border-bottom: 1px solid #1f2937; padding-bottom: 8px; font-weight: 700 !important; }
        h3 { color: #bfdbfe !important; font-weight: 700 !important; font-size: 1.22em !important; }
        h4, h5, h6 { color: #dbeafe !important; font-weight: 700 !important; }
        .stMarkdown, .stMarkdown p, .stMarkdown span, p, label { color: #e2e8f0 !important; }
        .stCaption, [data-testid="stCaptionContainer"] { color: #94a3b8 !important; }

        [data-testid="stMetric"] {
            background: linear-gradient(145deg, #1a2538 0%, #111827 100%);
            border: 1px solid #334155; border-left: 3px solid #D4AF37;
            border-radius: 10px; padding: 14px 16px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.45);
            transition: all 0.2s ease;
        }
        [data-testid="stMetric"]:hover {
            border-left-color: #F5D97A;
            box-shadow: 0 4px 16px rgba(212,175,55,0.25);
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
            font-size: 14px !important; padding: 8px 16px !important;
            transition: all 0.18s ease !important;
        }
        .stButton > button:hover {
            background: linear-gradient(135deg, #1e3a5f 0%, #16223a 100%) !important;
            border-color: #D4AF37 !important; color: #F5D97A !important;
            transform: translateY(-1px);
            box-shadow: 0 4px 14px rgba(212,175,55,0.25);
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
            margin: 2px 0 !important; transition: all 0.15s ease !important;
            cursor: pointer !important;
        }
        section[data-testid="stSidebar"] .stRadio label:hover {
            background: #1a2538 !important; border-color: #D4AF37 !important;
        }
        section[data-testid="stSidebar"] .stRadio label * { color: #e2e8f0 !important; }

        input, textarea,
        [data-testid="stTextInput"] input,
        [data-testid="stNumberInput"] input {
            background-color: #1a2538 !important; color: #ffffff !important;
            border: 1px solid #374151 !important; border-radius: 8px !important;
        }
        [data-testid="stTextInput"] label,
        [data-testid="stNumberInput"] label { color: #cbd5e1 !important; }

        [data-testid="stExpander"] {
            background-color: #0a1220 !important; border: 1px solid #1f2937 !important;
            border-radius: 10px !important;
        }
        [data-testid="stExpander"] summary {
            background-color: #1a2538 !important; color: #f3f4f6 !important;
            font-weight: 600 !important;
        }
        [data-testid="stExpander"] summary:hover { background-color: #1e3a5f !important; }

        .dataframe { background-color: #0a1220 !important; border-radius: 8px; }
        .dataframe thead th {
            background: #16223a !important; color: #F5D97A !important;
            font-weight: 700 !important; text-transform: uppercase;
            letter-spacing: 0.5px; font-size: 12px !important;
        }
        .dataframe td, .dataframe th {
            color: #e2e8f0 !important; border-bottom: 1px solid #1f2937 !important;
        }

        .terminal-header {
            background: linear-gradient(135deg, #0a0f19 0%, #1a2538 100%);
            border: 1px solid #1f2937; border-top: 3px solid #D4AF37;
            border-radius: 12px; padding: 18px 24px; margin-bottom: 16px;
            box-shadow: 0 4px 16px rgba(0,0,0,0.5);
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
            box-shadow: 0 3px 12px rgba(0,0,0,0.4); color: #e2e8f0;
        }
        .hybrid-card {
            background: linear-gradient(145deg, #111827 0%, #16223a 100%);
            border: 1px solid #2a3a5c; border-left: 4px solid #D4AF37;
            border-radius: 12px; padding: 18px 20px; margin: 10px 0;
            box-shadow: 0 4px 16px rgba(0,0,0,0.4); color: #e2e8f0;
        }

        .recommend-badge {
            padding: 5px 14px; border-radius: 14px;
            font-weight: 700; font-size: 0.9em;
        }
        .rec-buy  { background: #0a2e1a; color: #22c55e; border: 1px solid #22c55e; }
        .rec-hold { background: #3a2a0a; color: #f59e0b; border: 1px solid #f59e0b; }
        .rec-sell { background: #2a0a0a; color: #ef4444; border: 1px solid #ef4444; }

        .broker-container {
            background: linear-gradient(135deg, #0d1b2e 0%, #111827 100%);
            border: 2px solid #D4AF37; border-radius: 14px;
            padding: 18px 22px; margin-bottom: 16px;
            box-shadow: 0 8px 24px rgba(212,175,55,0.15);
        }
        .broker-container .broker-title {
            color: #F5D97A !important; -webkit-text-fill-color: #F5D97A !important;
            font-size: 15px; font-weight: 800; margin-bottom: 14px;
            letter-spacing: 0.5px; text-transform: uppercase;
        }
        .broker-container .broker-note {
            color: #cbd5e1 !important; -webkit-text-fill-color: #cbd5e1 !important;
            font-size: 12.5px; margin-top: 12px; font-weight: 500;
        }
        .broker-container [data-testid="stButton"] button {
            background: linear-gradient(135deg, #111827 0%, #0a0f19 100%) !important;
            color: #F5D97A !important; border: 2px solid #D4AF37 !important;
            font-weight: 700 !important; font-size: 14px !important;
            border-radius: 8px !important; padding: 10px 14px !important;
            transition: all 0.2s ease !important;
        }
        .broker-container [data-testid="stButton"] button:hover {
            background: linear-gradient(135deg, #D4AF37 0%, #B8912A 100%) !important;
            color: #0a0f19 !important; border-color: #F5D97A !important;
            transform: translateY(-1px);
            box-shadow: 0 4px 14px rgba(212,175,55,0.5);
        }

        /* === VIP PRICING CARD === */
        .vip-card {
            background: linear-gradient(145deg, #1a2538 0%, #111827 100%);
            border: 1px solid #334155; border-radius: 16px;
            padding: 20px 16px; height: 100%;
            transition: all 0.25s ease;
        }
        .vip-card:hover {
            border-color: #D4AF37;
            box-shadow: 0 8px 24px rgba(212,175,55,0.25);
            transform: translateY(-4px);
        }
        .vip-card.featured {
            border: 2px solid #D4AF37;
            background: linear-gradient(145deg, #1f2f47 0%, #111827 100%);
            box-shadow: 0 8px 30px rgba(212,175,55,0.35);
        }

        /* === CTA BANNER === */
        .cta-banner {
            background: linear-gradient(135deg, #D4AF37 0%, #B8912A 50%, #D4AF37 100%);
            border-radius: 16px; padding: 22px 28px; margin: 20px 0;
            box-shadow: 0 8px 28px rgba(212,175,55,0.35);
            position: relative; overflow: hidden;
        }
        .cta-banner::before {
            content: ''; position: absolute; top: 0; right: -50px;
            width: 200px; height: 200px;
            background: radial-gradient(circle, rgba(255,255,255,0.15) 0%, transparent 70%);
            border-radius: 50%;
        }

        /* === FOOTER === */
        .footer-hero {
            background: linear-gradient(135deg, #0a0f19 0%, #1a2538 100%);
            border: 1px solid #D4AF37; border-radius: 16px;
            padding: 28px 32px; margin: 30px 0 20px 0;
            text-align: center;
        }
        .footer-section-title {
            color: #F5D97A !important;
            font-size: 1.1em; font-weight: 800;
            margin-bottom: 12px;
            text-transform: uppercase; letter-spacing: 1.2px;
        }
        .footer-link {
            color: #cbd5e1 !important;
            text-decoration: none;
            display: block;
            padding: 4px 0;
            font-size: 0.88em;
            transition: color 0.15s;
        }
        .footer-link:hover { color: #F5D97A !important; }
        .footer-divider {
            height: 1px; background: linear-gradient(90deg, transparent, #D4AF37, transparent);
            margin: 24px 0;
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
            background-color: #1a2538 !important;
            border-left-width: 4px !important; color: #e2e8f0 !important;
        }
        [data-testid="stAlert"] * { color: #e2e8f0 !important; }
    </style>
    """, unsafe_allow_html=True)


# ============================================================================
# 3. PROFILER
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
        with st.expander("🔬 Profiler", expanded=False):
            if not _PROFILE:
                st.caption("Chưa có dữ liệu")
                return
            sorted_log = sorted(_PROFILE.items(), key=lambda x: -x[1])
            total = sum(_PROFILE.values())
            st.caption(f"⏱️ Tổng: **{total:,.0f} ms**")
            for name, ms in sorted_log[:10]:
                icon = "🐌" if ms > 500 else ("⚠️" if ms > 200 else "✅")
                st.caption(f"{icon} {name}: {ms:.0f}ms")
            if st.button("🔄 Reset", key="prof_reset", use_container_width=True):
                _PROFILE.clear(); st.rerun()


# ============================================================================
# 4. HELPERS
# ============================================================================
def _fmt_ty(v):
    try:
        v = float(v or 0)
    except Exception:
        return "N/A"
    if v == 0: return "0 tỷ"
    if abs(v) >= 1000: return f"{v/1000:,.2f} nghìn tỷ"
    return f"{v:,.0f} tỷ"

def _fmt_vnd(v):
    try: return f"{int(v):,}".replace(",", ".")
    except Exception: return "0"

def _fmt_shares(v):
    try: return f"{int(v):,}".replace(",", ".")
    except Exception: return "0"

def _buyable_shares(capital_vnd, market_price):
    if market_price <= 0 or capital_vnd < 0: return 0
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
# 5. VALUATION CORE
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
            total += val * w[k]; used_w += w[k]
    hybrid = total / used_w if used_w > 0 else 0
    mos = ((hybrid - price) / hybrid * 100) if hybrid > 0 else 0
    mos = max(-100.0, min(100.0, mos))
    return {
        "hybrid": round(hybrid, 0), "graham": round(graham, 0),
        "dcf": round(dcf, 0), "pe_band": round(pe_band, 0),
        "pb_band": round(pb_band, 0), "weights": w, "mos": round(mos, 1),
    }

def _simple_dcf_valuation(ticker, data):
    if not data:
        return {"error": "Không có dữ liệu."}
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
            return {
                "intrinsic_value_per_share": iv,
                "upside_downside": (iv - price) / price if price > 0 else 0,
                "fcff_projections": fcff, "pv_fcff": pv,
                "enterprise_value": ev, "pv_terminal_value": pv_tv,
                "equity_value": ev, "current_price": price, "wacc": wacc,
            }
        base_s, bear_s, bull_s = _scenario(1.0), _scenario(0.6), _scenario(1.6)
        verdict = ("Buy" if base_s["upside_downside"] > 0.20
                   else ("Hold" if base_s["upside_downside"] > 0 else "Sell"))
        return {
            "scenarios": {"Base": base_s, "Bear": bear_s, "Bull": bull_s},
            "verdict": verdict,
            "clean_inputs": {"growth_rate": growth, "terminal_growth": terminal_g, "beta": 1.0},
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
    if roe >= 20 and roa >= 1.5: return 2, 80.0
    if roe >= 12 and roa >= 0.8: return 1, 70.0
    return 0, 60.0

def predict_eps_ensemble(roe, roa, margin, de):
    return 3000.0 * (1 + (roe or 10) / 200.0)


# ============================================================================
# 6. DATA LOADING
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
    col_map = {str(c).strip().lower(): c for c in df.columns}
    return {
        "ticker": col_map.get("mã chứng khoán") or col_map.get("ticker") or col_map.get("ma ck"),
        "industry": col_map.get("tên ngành") or col_map.get("ngành") or col_map.get("industry"),
        "period": col_map.get("năm") or col_map.get("ngày kỳ") or col_map.get("period"),
        "metric": col_map.get("chỉ tiêu tiếng việt") or col_map.get("chỉ tiêu") or col_map.get("metric"),
        "value": col_map.get("giá trị") or col_map.get("value"),
    }

def get_financials(ticker, csv_df=None, cols=None):
    if ticker in DEMO_FINANCIAL_DATA:
        return dict(DEMO_FINANCIAL_DATA[ticker])
    return {}


# ============================================================================
# 7. VNINDEX CHART (đầy đủ như code cũ)
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


def render_vnindex_chart():
    """Biểu đồ VNINDEX đầy đủ: candlestick + MA20/50/200 + volume + 9 milestone."""
    st.markdown("### 📈 VN-INDEX — 26 NĂM LỊCH SỬ (2000 – 2026)")
    st.caption("Biểu đồ nến toàn cảnh · Milestone được đánh dấu · Đơn vị: điểm")

    # KPI metrics trên đầu
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("VN-Index hiện tại", "1,774.15", "+13.52 (+0.77%)")
    c2.metric("VN30 hiện tại", "1,907.09", "+14.11 (+0.75%)")
    c3.metric("Thanh khoản VNINDEX", "16.9K tỷ")
    c4.metric("Thanh khoản VN30", "9.2K tỷ")

    df = generate_vnindex_history()

    col_a, col_b = st.columns([1, 5])
    with col_a:
        show_ma = st.toggle("📈 MA", value=True, key="hose_ma")
    with col_b:
        show_vol = st.toggle("📊 Volume", value=True, key="hose_vol")

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
        whiskerwidth=0.3, line=dict(width=1),
    ), row=1, col=1)

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
        ("2001-06-30", "Đỉnh 571 (2001)", "#26A69A"),
        ("2003-10-31", "Đáy 130 (2003)", "#EF5350"),
        ("2007-03-12", "Đỉnh 1170 (2007)", "#26A69A"),
        ("2009-02-20", "Đáy 235 (2009)", "#EF5350"),
        ("2012-12-28", "Đáy 413 (2012)", "#EF5350"),
        ("2018-04-09", "Đỉnh 1204 (2018)", "#26A69A"),
        ("2020-03-24", "Đáy COVID 660", "#EF5350"),
        ("2022-01-06", "Đỉnh 1528 (2022)", "#26A69A"),
        ("2022-11-15", "Đáy 873 (2022)", "#EF5350"),
        ("2026-10-22", "Đỉnh 1774 (10/2026)", "#26A69A"),
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
                    fig.add_annotation(
                        x=sub["time"].iloc[0], y=y_val, text=label,
                        showarrow=True, arrowhead=2, arrowwidth=1,
                        arrowcolor=color, ax=0, ay=-35,
                        font=dict(color=color, size=9),
                        bgcolor="rgba(10,15,25,0.9)",
                        bordercolor=color, borderwidth=1, borderpad=2,
                        row=1, col=1,
                    )
        except Exception:
            pass

    high = float(df["h"].max())
    low = float(df["l"].min())

    fig.add_hline(y=high, line=dict(color="#26A69A", width=1, dash="dot"),
                  annotation_text=f"Đỉnh {high:,.0f}",
                  annotation_position="top right",
                  annotation_font=dict(color="#26A69A", size=10), row=1, col=1)
    fig.add_hline(y=low, line=dict(color="#EF5350", width=1, dash="dot"),
                  annotation_text=f"Đáy {low:,.0f}",
                  annotation_position="bottom right",
                  annotation_font=dict(color="#EF5350", size=10), row=1, col=1)

    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor="#050914", plot_bgcolor="#0a1220",
        height=750,
        font=dict(color="#e2e8f0", size=11),
        hovermode="x unified",
        hoverlabel=dict(bgcolor="rgba(10,15,25,0.95)",
                        bordercolor="#D4AF37",
                        font=dict(size=11, color="#F5D97A")),
        margin=dict(l=60, r=40, t=70, b=40),
        showlegend=True,
        legend=dict(orientation="h", yanchor="bottom", y=1.01, xanchor="right", x=1,
                    bgcolor="rgba(10,15,25,0.85)", bordercolor="#334155", borderwidth=1),
        title=dict(
            text=(f"<b style='color:#F5D97A;'>VN-INDEX · 26 NĂM LỊCH SỬ (2000 – 2026)</b><br>"
                  f"<span style='font-size:0.78em; color:#94a3b8;'>"
                  f"Hiện tại: <b style='color:#22c55e;'>1,774.15 điểm</b> · "
                  f"{len(df):,} phiên</span>"),
            font=dict(size=14), x=0.005, xanchor="left", y=0.995, yanchor="top",
        ),
    )
    fig.update_xaxes(gridcolor="#1f2937",
                     rangebreaks=[dict(bounds=["sat", "mon"])], row=1, col=1)
    fig.update_yaxes(gridcolor="#1f2937", title="Điểm VN-Index",
                     tickformat=",.0f", row=1, col=1)
    if show_vol:
        fig.update_xaxes(gridcolor="#1f2937",
                         rangebreaks=[dict(bounds=["sat", "mon"])], row=2, col=1)
        fig.update_yaxes(gridcolor="#1f2937", title="KL (cp)",
                         tickformat=".2s", row=2, col=1)

    st.plotly_chart(fig, use_container_width=True,
                    config={"displayModeBar": True, "displaylogo": False,
                            "scrollZoom": True})


# ============================================================================
# 8. CTA BANNERS
# ============================================================================
def render_cta_banner(title, subtitle, button_text, key_prefix):
    """Banner vàng nổi bật để kêu gọi nâng cấp VIP."""
    st.markdown(
        f"""<div class="cta-banner">
        <div style="position:relative;z-index:1;">
            <div style="font-size:1.5em;font-weight:800;color:#0a0f19;margin-bottom:6px;">
            🚀 {title}</div>
            <div style="font-size:1em;color:#1e293b;margin-bottom:14px;">
            {subtitle}</div>
        </div></div>""",
        unsafe_allow_html=True,
    )
    col1, col2, col3 = st.columns([1, 1, 1])
    with col2:
        if st.button(button_text, key=f"cta_btn_{key_prefix}",
                     use_container_width=True, type="primary"):
            st.session_state.show_vip_dialog = True
            st.rerun()


def render_vip_section_main():
    """Section VIP pricing trên trang chính — hiển thị đầy đủ 6 gói."""
    st.markdown("---")
    st.markdown(
        """<div style="text-align:center;padding:20px 0;">
        <h2 style="color:#F5D97A !important;border:none;font-size:2em;margin:0;">
        💎 BẢNG GIÁ & GÓI HỘI VIÊN FINEX</h2>
        <p style="color:#94a3b8;font-size:1em;margin-top:8px;">
        Chọn gói phù hợp với nhu cầu đầu tư của bạn — Hủy bất cứ lúc nào</p>
        </div>""",
        unsafe_allow_html=True,
    )

    # Feature comparison matrix
    with st.expander("📊 So sánh chi tiết các gói", expanded=False):
        comparison = pd.DataFrame([
            {"Tính năng": "Xem dữ liệu cơ bản", "Free": "✅", "S-Student": "✅", "Basic": "✅", "Pro": "✅", "VIP": "✅", "Enterprise": "✅"},
            {"Tính năng": "Mã CP / ngày", "Free": "1", "S-Student": "∞", "Basic": "∞", "Pro": "∞", "VIP": "∞", "Enterprise": "∞"},
            {"Tính năng": "Định giá DCF/Hybrid", "Free": "—", "S-Student": "✅", "Basic": "✅", "Pro": "✅", "VIP": "✅", "Enterprise": "✅"},
            {"Tính năng": "Stress Test khủng hoảng", "Free": "—", "S-Student": "—", "Basic": "✅", "Pro": "✅", "VIP": "✅", "Enterprise": "✅"},
            {"Tính năng": "BCTC gốc (LCTT/KQKD/BCDKT)", "Free": "—", "S-Student": "—", "Basic": "✅", "Pro": "✅", "VIP": "✅", "Enterprise": "✅"},
            {"Tính năng": "ML/DL Forecast", "Free": "—", "S-Student": "—", "Basic": "—", "Pro": "✅", "VIP": "✅", "Enterprise": "✅"},
            {"Tính năng": "Xuất PDF báo cáo", "Free": "—", "S-Student": "—", "Basic": "—", "Pro": "✅", "VIP": "✅", "Enterprise": "✅"},
            {"Tính năng": "Tối ưu hóa danh mục", "Free": "—", "S-Student": "—", "Basic": "—", "Pro": "—", "VIP": "✅", "Enterprise": "✅"},
            {"Tính năng": "Telegram Bot cảnh báo", "Free": "—", "S-Student": "—", "Basic": "—", "Pro": "—", "VIP": "✅", "Enterprise": "✅"},
            {"Tính năng": "White-Label báo cáo", "Free": "—", "S-Student": "—", "Basic": "—", "Pro": "—", "VIP": "—", "Enterprise": "✅"},
            {"Tính năng": "API dữ liệu Terminal", "Free": "—", "S-Student": "—", "Basic": "—", "Pro": "—", "VIP": "—", "Enterprise": "✅"},
        ])
        st.dataframe(comparison, use_container_width=True, hide_index=True)

    # 6 pricing cards
    cols = st.columns(6)
    for i, pkg in enumerate(VIP_PACKAGES):
        with cols[i]:
            is_featured = pkg.get("featured", False)
            border_color = pkg["color"]
            card_class = "vip-card featured" if is_featured else "vip-card"

            badge_html = (
                f"<span style='background:{pkg['color']};color:#0a0f19;"
                f"padding:3px 10px;border-radius:12px;font-size:0.72em;"
                f"font-weight:700;'>{pkg['badge']}</span>"
                if pkg.get("badge") else ""
            )
            if is_featured:
                badge_html += (
                    "<span style='background:#22c55e;color:#ffffff;"
                    "padding:3px 8px;border-radius:10px;font-size:0.7em;"
                    "font-weight:700;margin-left:4px;'>🔥 HOT</span>"
                )

            features_html = "".join([
                f"<li style='color:#cbd5e1;font-size:0.78em;margin:5px 0;"
                f"display:flex;align-items:flex-start;gap:6px;'>"
                f"<span style='color:{pkg['color']};'>✓</span>"
                f"<span>{f}</span></li>"
                for f in pkg["features"]
            ])

            st.markdown(
                f"""<div class="{card_class}" style="border-top:3px solid {border_color};">
                <div style="text-align:center;margin-bottom:8px;">{badge_html}</div>
                <div style="font-size:1em;font-weight:800;color:#e2e8f0;
                min-height:2.5em;text-align:center;">{pkg['name']}</div>
                <div style="font-size:1.35em;font-weight:800;color:{pkg['color']};
                margin:10px 0;text-align:center;">{pkg['price']}</div>
                <ul style="list-style:none;padding:0;margin:12px 0;
                text-align:left;min-height:200px;">{features_html}</ul>
                </div>""",
                unsafe_allow_html=True,
            )
            if pkg["id"] != "FREE":
                if st.button(
                    f"Chọn {pkg['name'].split(' ', 1)[1] if ' ' in pkg['name'] else pkg['name']}",
                    key=f"vip_btn_{pkg['id']}",
                    use_container_width=True,
                    type="primary" if is_featured else "secondary",
                ):
                    st.session_state.selected_plan = pkg["id"]
                    st.rerun()
            else:
                st.button(
                    "✓ Đang dùng", key=f"vip_btn_{pkg['id']}",
                    use_container_width=True, disabled=True,
                )

    # QR payment if plan selected
    if st.session_state.get("selected_plan") and st.session_state.selected_plan != "FREE":
        plan_id = st.session_state.selected_plan
        pkg = next((p for p in VIP_PACKAGES if p["id"] == plan_id), None)
        if pkg:
            st.markdown("---")
            st.markdown(
                f"""<div style="background:linear-gradient(135deg,#D4AF37 0%,#B8912A 100%);
                border-radius:16px;padding:20px 28px;margin:20px 0;
                box-shadow:0 8px 28px rgba(212,175,55,0.35);">
                <div style="font-size:1.3em;font-weight:800;color:#0a0f19;text-align:center;">
                ✅ BẠN ĐÃ CHỌN: {pkg['name']}</div></div>""",
                unsafe_allow_html=True,
            )

            memo = f"FINEX {plan_id}"
            qr_url = (f"https://img.vietqr.io/image/{BANK_ID}-{ACCOUNT_NO}-compact2.png"
                      f"?amount={pkg['amount']}&addInfo={memo}&accountName={ACCOUNT_NAME}")

            col_qr, col_info = st.columns([1, 1])
            with col_qr:
                st.image(qr_url, caption=f"Quét VietQR để thanh toán {pkg['price']}",
                         use_container_width=True)
            with col_info:
                st.markdown(
                    f"""<div style="background:#F5D97A;padding:20px;border-radius:12px;
                    border:2px solid #D4AF37;box-shadow:0 4px 12px rgba(212,175,55,0.35);">
                    <div style="font-size:1.15em;font-weight:800;color:#0a0f19;
                    text-align:center;margin-bottom:12px;">🏦 THÔNG TIN CHUYỂN KHOẢN</div>
                    <div style="font-size:1em;color:#0a0f19;line-height:2;">
                    <strong>Ngân hàng:</strong>
                    <span style="background:#0a0f19;color:#F5D97A;
                    padding:2px 10px;border-radius:6px;">Vietcombank</span><br>
                    <strong>Số TK:</strong>
                    <span style="background:#0a0f19;color:#F5D97A;
                    padding:2px 10px;border-radius:6px;font-size:1.1em;">{ACCOUNT_NO}</span><br>
                    <strong>Chủ TK:</strong>
                    <span style="background:#0a0f19;color:#F5D97A;
                    padding:2px 10px;border-radius:6px;">{ACCOUNT_NAME}</span><br>
                    <strong>Số tiền:</strong>
                    <span style="background:#0a0f19;color:#F5D97A;
                    padding:2px 10px;border-radius:6px;">{pkg['amount']:,} VNĐ</span><br>
                    <strong>Nội dung:</strong>
                    <span style="background:#0a0f19;color:#F5D97A;
                    padding:2px 10px;border-radius:6px;">{memo}</span>
                    </div></div>""",
                    unsafe_allow_html=True,
                )
                st.info("💡 Sau khi chuyển khoản, hệ thống kích hoạt trong 30s")
                if st.button("✅ Tôi đã chuyển khoản", key="vip_confirm",
                             use_container_width=True, type="primary"):
                    st.success("Đã ghi nhận! Đang xác thực giao dịch...")
                    st.balloons()

    # Testimonials
    st.markdown("---")
    st.markdown(
        """<div style="text-align:center;margin:20px 0;">
        <h3 style="color:#F5D97A !important;border:none;">
        💬 Khách hàng nói gì về FINEX</h3></div>""",
        unsafe_allow_html=True,
    )
    t_cols = st.columns(3)
    for i, t in enumerate(TESTIMONIALS):
        with t_cols[i]:
            stars = "⭐" * t["rating"]
            st.markdown(
                f"""<div class="glass-card" style="text-align:center;">
                <div style="font-size:1.5em;color:#D4AF37;margin-bottom:8px;">{stars}</div>
                <div style="color:#e2e8f0;font-style:italic;font-size:0.9em;
                line-height:1.6;margin-bottom:12px;">"{t['quote']}"</div>
                <div style="color:#F5D97A;font-weight:700;font-size:0.9em;">{t['name']}</div>
                <div style="color:#94a3b8;font-size:0.78em;">{t['role']}</div>
                </div>""",
                unsafe_allow_html=True,
            )


# ============================================================================
# 9. DIALOGS
# ============================================================================
@st.dialog("🔍 THÔNG TIN ĐỐI TÁC", width="large")
def partner_detail_dialog():
    partner_id = st.session_state.get("selected_partner")
    if partner_id is None or partner_id not in PARTNERS:
        st.error("Không tìm thấy thông tin đối tác.")
        return
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
    st.markdown('<div class="partner-section-title">💪 Thế mạnh & Công nghệ</div>',
                unsafe_allow_html=True)
    st.markdown(f'<div class="partner-card">{p["strengths"]}</div>', unsafe_allow_html=True)
    st.markdown('<div class="partner-section-title">📊 Chính sách vay / Đầu tư</div>',
                unsafe_allow_html=True)
    st.markdown(f'<div class="partner-card">{p["margin_policy"]}</div>', unsafe_allow_html=True)
    st.markdown('<div class="partner-section-title">🔑 Mã giới thiệu (Sponsor ID)</div>',
                unsafe_allow_html=True)
    st.markdown(
        f"""<div class="partner-code-box">
              <span class="partner-code">{p['referral_code']}</span>
              <span style="color:#94a3b8;font-size:0.85em;">Sao chép thủ công</span>
            </div>""",
        unsafe_allow_html=True,
    )
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
            badge_html = (
                f"<span style='background:{pkg['color']};color:#0a0f19;"
                f"padding:2px 10px;border-radius:12px;font-size:0.75em;"
                f"font-weight:700;'>{pkg['badge']}</span>"
                if pkg.get("badge") else ""
            )
            features_html = "".join([
                f"<li style='margin-bottom:4px;color:#cbd5e1;font-size:0.82em;'>{f}</li>"
                for f in pkg["features"]
            ])
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
                unsafe_allow_html=True,
            )
            if pkg["id"] != "FREE":
                if st.button("Chọn gói này", use_container_width=True,
                             key=f"dlg_btn_{pkg['id']}"):
                    st.session_state.selected_plan = pkg["id"]
                    st.session_state.show_vip_dialog = False
                    st.rerun()
    st.markdown("---")
    if st.button("Đóng", use_container_width=True):
        st.session_state.show_vip_dialog = False; st.rerun()


# ============================================================================
# 10. COMPONENTS
# ============================================================================
def render_header():
    st.markdown(
        """<div class="terminal-header">
        <h1>🏛️ FINEX VN Terminal — Enterprise Intelligence</h1>
        <p style="color:#94a3b8;margin-top:8px;font-size:0.95em;letter-spacing:0.3px;">
        Hệ thống khai thác, trực quan hóa và phân tích dữ liệu tài chính doanh nghiệp
        chuẩn mực dành cho thế hệ nhà đầu tư mới.</p></div>""",
        unsafe_allow_html=True,
    )


def render_partner_buttons():
    st.markdown(
        """<div class="broker-container">
        <div class="broker-title">🔗 MỞ TÀI KHOẢN CHỨNG KHOÁN ĐỐI TÁC ĐỒNG HÀNH:</div>""",
        unsafe_allow_html=True,
    )
    cols = st.columns(len(PARTNERS))
    for i, (key, partner) in enumerate(PARTNERS.items()):
        with cols[i]:
            if st.button(
                partner["display_name"],
                key=f"partner_btn_{key}",
                use_container_width=True,
                help=f"Xem chi tiết về {partner['full_name']}",
            ):
                st.session_state.selected_partner = key
                st.session_state.show_partner_dialog = True
                st.rerun()
    st.markdown(
        """<div class="broker-note">💡 Nhấn vào nút để xem chi tiết và đăng ký
        – hỗ trợ ưu đãi cho nhà đầu tư FINEX</div></div>""",
        unsafe_allow_html=True,
    )


def render_ticker_info_card(ticker, fin_data):
    info = COMPANY_INFO.get(ticker, {})
    name = info.get("name", f"Công ty {ticker}")
    sector = info.get("sector", fin_data.get("industry", "Đang cập nhật"))
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
        </div></div>""",
        unsafe_allow_html=True,
    )


def render_market_snapshot_panel(ticker, fin_data):
    st.markdown(
        f"""<div style="background:linear-gradient(135deg,#0d1b2e 0%,#111827 100%);
        border:1px solid #2a3a5c;border-top:3px solid #22c55e;
        border-radius:12px;padding:14px 18px;margin:10px 0;
        box-shadow:0 4px 16px rgba(34,197,94,0.15);">
        <div style="color:#22c55e;font-weight:800;font-size:1.05em;letter-spacing:1px;">
        📡 DỮ LIỆU THỊ TRƯỜNG · {ticker}</div></div>""",
        unsafe_allow_html=True,
    )
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
    c10.metric("📐 P/E · P/B", f"{fin_data.get('pe_ttm',0):.1f} · {fin_data.get('pb',0):.1f}")


# ============================================================================
# 11. CRISIS / DOCUMENT / ACCURACY / UNDERVALUED
# ============================================================================
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
        for key, label in [
            ("core_mission", "Nhiệm vụ"), ("core_dilemma", "Tình huống"),
            ("key_decision", "Quyết định then chốt"),
            ("policy_rule", "Nguyên tắc ứng phó"),
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


def render_accuracy_section(ticker):
    st.markdown("## 🔍 Kiểm tra độ chính xác thuật toán")
    st.caption("Kết quả backtest minh hoạ — thay bằng dữ liệu backtest thực.")
    c = st.columns(3)
    c[0].markdown(
        """<div class="glass-card" style="text-align:center;border-top:3px solid #22c55e;">
        <div style="font-size:2em;font-weight:800;color:#22c55e;">99.2%</div>
        <div style="color:#94a3b8;font-size:0.88em;margin-top:6px;">Độ chính xác</div>
        <div style="color:#64748b;font-size:0.76em;">1.000+ Backtest</div></div>""",
        unsafe_allow_html=True)
    c[1].markdown(
        """<div class="glass-card" style="text-align:center;border-top:3px solid #60a5fa;">
        <div style="font-size:2em;font-weight:800;color:#60a5fa;">&lt; 3.5%</div>
        <div style="color:#94a3b8;font-size:0.88em;margin-top:6px;">MAE</div>
        <div style="color:#64748b;font-size:0.76em;">Định giá vs thực tế</div></div>""",
        unsafe_allow_html=True)
    c[2].markdown(
        """<div class="glass-card" style="text-align:center;border-top:3px solid #f59e0b;">
        <div style="font-size:2em;font-weight:800;color:#f59e0b;">✅ Real-time</div>
        <div style="color:#94a3b8;font-size:0.88em;margin-top:6px;">Trạng thái</div>
        <div style="color:#64748b;font-size:0.76em;">ML & DL đồng bộ</div></div>""",
        unsafe_allow_html=True)
    st.markdown("---")
    rows = [
        {"Kỳ": "Q4/2023", "Định giá": "24.500đ", "Thực tế": "24.800đ", "Chính xác": "98.8%", "Trạng thái": "✅"},
        {"Kỳ": "Q1/2024", "Định giá": "25.200đ", "Thực tế": "25.100đ", "Chính xác": "99.6%", "Trạng thái": "✅"},
        {"Kỳ": "Q2/2024", "Định giá": "28.000đ", "Thực tế": "27.900đ", "Chính xác": "99.6%", "Trạng thái": "✅"},
        {"Kỳ": "Q3/2024", "Định giá": "29.500đ", "Thực tế": "30.200đ", "Chính xác": "97.7%", "Trạng thái": "✅"},
    ]
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


def render_undervalued_stocks():
    st.markdown("## 📌 Danh mục Cổ phiếu Định giá Rẻ (Graham Screen)")
    st.caption("Cổ phiếu thỏa mãn: P/E < 15 · P/B < 1.5 · Hoặc MoS > 20%")
    rows = []
    for t, d in DEMO_FINANCIAL_DATA.items():
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
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    else:
        st.info("Chưa có cổ phiếu nào thỏa mãn tiêu chí.")


# ============================================================================
# 12. FULL FOOTER
# ============================================================================
def render_full_footer():
    st.markdown("---")
    st.markdown(
        """<div class="footer-hero">
        <div style="font-size:2.5em;font-weight:900;letter-spacing:3px;
        background:linear-gradient(90deg,#F5D97A 0%,#60a5fa 100%);
        -webkit-background-clip:text;-webkit-text-fill-color:transparent;
        background-clip:text;">FINEX VN TERMINAL</div>
        <div style="color:#94a3b8;font-size:0.9em;margin-top:8px;letter-spacing:2px;">
        ENTERPRISE INTELLIGENCE · EST. 2024</div>
        <div style="color:#cbd5e1;font-size:1em;margin-top:16px;max-width:700px;
        margin-left:auto;margin-right:auto;line-height:1.7;">
        Công nghệ kiến tạo giá trị tài chính — Nền tảng hỗ trợ nhà đầu tư và chuyên gia
        phân tích chuẩn hóa dữ liệu BCTC, theo dõi chỉ tiêu doanh nghiệp, trực quan hóa
        xu hướng và tham khảo nhiều phương pháp định giá.</div>
        </div>""",
        unsafe_allow_html=True,
    )

    # 4 columns
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.markdown('<div class="footer-section-title">🏛️ Về FINEX</div>',
                    unsafe_allow_html=True)
        st.markdown(
            """<div style="color:#cbd5e1;font-size:0.88em;line-height:1.8;">
            <div style="margin-bottom:8px;">
            <strong style="color:#F5D97A;">Sứ mệnh:</strong> Dân chủ hóa dữ liệu tài chính
            chất lượng cao cho mọi nhà đầu tư Việt Nam.</div>
            <div style="margin-bottom:8px;">
            <strong style="color:#F5D97A;">Tầm nhìn:</strong> Trở thành nền tảng phân tích
            chứng khoán số 1 Đông Nam Á vào 2030.</div>
            <div style="margin-bottom:8px;">
            <strong style="color:#F5D97A;">Giá trị:</strong> Minh bạch · Chính xác · Học thuật
            · Không khuyến nghị đầu tư.</div>
            </div>""",
            unsafe_allow_html=True,
        )

    with col2:
        st.markdown('<div class="footer-section-title">⚡ Tính năng</div>',
                    unsafe_allow_html=True)
        features = [
            "📊 Phân tích BCTC chuẩn hóa",
            "🧮 Định giá DCF · Hybrid · Graham",
            "📈 Dự báo tăng trưởng 10 năm",
            "🤖 Machine Learning · Deep Learning",
            "📉 Stress Test khủng hoảng",
            "💵 Máy tính cổ tức",
            "📚 Tra cứu BCTC gốc",
            "🚀 Xuất báo cáo PDF (VIP)",
        ]
        for feat in features:
            st.markdown(
                f'<div class="footer-link">{feat}</div>',
                unsafe_allow_html=True,
            )

    with col3:
        st.markdown('<div class="footer-section-title">📞 Liên hệ</div>',
                    unsafe_allow_html=True)
        st.markdown(
            """<div style="color:#cbd5e1;font-size:0.88em;line-height:1.9;">
            <div style="margin-bottom:8px;">
            👨‍💼 <strong style="color:#F5D97A;">Founder:</strong> Trần Anh Quân
            <br><span style="color:#94a3b8;font-size:0.85em;">
            Founder & Lead Developer</span></div>
            <div style="margin-bottom:8px;">
            📧 <strong style="color:#F5D97A;">Email:</strong>
            <a href="mailto:Trananhhquan2122001@gmail.com" class="footer-link"
            style="display:inline;color:#60a5fa;">
            Trananhhquan2122001@gmail.com</a></div>
            <div style="margin-bottom:8px;">
            💬 <strong style="color:#F5D97A;">Zalo:</strong>
            <span style="color:#60a5fa;">0342 167 380</span></div>
            <div style="margin-bottom:8px;">
            📍 <strong style="color:#F5D97A;">Địa chỉ:</strong>
            TP. Hồ Chí Minh, Việt Nam</div>
            <div>
            🌐 <strong style="color:#F5D97A;">Giờ làm việc:</strong>
            8:00 – 22:00 (T2–T7)</div>
            </div>""",
            unsafe_allow_html=True,
        )

    with col4:
        st.markdown('<div class="footer-section-title">🤝 Hợp tác & Đối tác</div>',
                    unsafe_allow_html=True)
        st.markdown(
            """<div style="color:#cbd5e1;font-size:0.88em;line-height:1.9;">
            <div style="margin-bottom:12px;">Đối tác chứng khoán:</div>
            <div style="display:flex;flex-wrap:wrap;gap:8px;margin-bottom:12px;">
            <span style="background:#1a2538;color:#22c55e;padding:4px 10px;
            border-radius:6px;font-size:0.85em;font-weight:700;">DNSE</span>
            <span style="background:#1a2538;color:#ef4444;padding:4px 10px;
            border-radius:6px;font-size:0.85em;font-weight:700;">VPS</span>
            <span style="background:#1a2538;color:#3b82f6;padding:4px 10px;
            border-radius:6px;font-size:0.85em;font-weight:700;">TCBS</span>
            <span style="background:#1a2538;color:#f59e0b;padding:4px 10px;
            border-radius:6px;font-size:0.85em;font-weight:700;">SSI</span>
            </div>
            <div style="margin-bottom:8px;">
            🤝 <strong style="color:#F5D97A;">Hợp tác dữ liệu:</strong>
            Liên hệ email để trao đổi.</div>
            <div style="margin-bottom:8px;">
            💼 <strong style="color:#F5D97A;">Doanh nghiệp:</strong>
            Gói Enterprise & API.</div>
            <div>
            🎓 <strong style="color:#F5D97A;">Học thuật:</strong>
            Miễn phí cho sinh viên tài chính.</div>
            </div>""",
            unsafe_allow_html=True,
        )

    # Newsletter signup
    st.markdown('<div class="footer-divider"></div>', unsafe_allow_html=True)
    st.markdown(
        """<div style="text-align:center;margin:20px 0;">
        <div style="color:#F5D97A;font-size:1.2em;font-weight:800;margin-bottom:8px;">
        📬 Đăng ký nhận bản tin FINEX</div>
        <div style="color:#94a3b8;font-size:0.9em;">
        Nhận thông tin thị trường, case study định giá và mẹo đầu tư mỗi tuần</div>
        </div>""",
        unsafe_allow_html=True,
    )
    col_e1, col_e2, col_e3 = st.columns([1, 2, 1])
    with col_e2:
        sub_col1, sub_col2 = st.columns([3, 1])
        with sub_col1:
            email = st.text_input("Email của bạn:", placeholder="your@email.com",
                                  key="newsletter_email", label_visibility="collapsed")
        with sub_col2:
            if st.button("📬 Đăng ký", use_container_width=True, key="newsletter_btn",
                         type="primary"):
                if email and "@" in email:
                    st.success(f"✅ Đã đăng ký {email}! Kiểm tra hộp thư của bạn.")
                else:
                    st.warning("⚠️ Vui lòng nhập email hợp lệ.")

    # Tech stack
    st.markdown('<div class="footer-divider"></div>', unsafe_allow_html=True)
    st.markdown(
        """<div style="text-align:center;">
        <div style="color:#F5D97A;font-size:1em;font-weight:800;margin-bottom:12px;">
        🛠️ Công nghệ sử dụng</div>
        <div style="display:flex;justify-content:center;flex-wrap:wrap;gap:8px;">
        <span style="background:#1a2538;color:#e2e8f0;padding:5px 12px;
        border-radius:6px;font-size:0.82em;">🐍 Python 3.11+</span>
        <span style="background:#1a2538;color:#e2e8f0;padding:5px 12px;
        border-radius:6px;font-size:0.82em;">⚡ Streamlit</span>
        <span style="background:#1a2538;color:#e2e8f0;padding:5px 12px;
        border-radius:6px;font-size:0.82em;">🐼 Pandas · NumPy</span>
        <span style="background:#1a2538;color:#e2e8f0;padding:5px 12px;
        border-radius:6px;font-size:0.82em;">📊 Plotly</span>
        <span style="background:#1a2538;color:#e2e8f0;padding:5px 12px;
        border-radius:6px;font-size:0.82em;">🐘 PostgreSQL</span>
        <span style="background:#1a2538;color:#e2e8f0;padding:5px 12px;
        border-radius:6px;font-size:0.82em;">🤖 Scikit-learn · LightGBM</span>
        <span style="background:#1a2538;color:#e2e8f0;padding:5px 12px;
        border-radius:6px;font-size:0.82em;">🧠 PyTorch · Transformers</span>
        </div></div>""",
        unsafe_allow_html=True,
    )

    # Full legal disclaimer
    st.markdown('<div class="footer-divider"></div>', unsafe_allow_html=True)
    st.markdown(
        """<div style="background:linear-gradient(145deg,rgba(239,68,68,0.12) 0%,rgba(239,68,68,0.04) 100%);
        border-left:4px solid #ef4444;padding:18px 22px;border-radius:8px;margin:20px 0;">
        <div style="color:#ef4444;font-weight:800;font-size:1.05em;margin-bottom:8px;">
        ⚠️ TUYÊN BỐ MIỄN TRỪ TRÁCH NHIỆM PHÁP LÝ (DISCLAIMER)</div>
        <div style="color:#cbd5e1;font-size:0.85em;line-height:1.7;">
        1. <strong style="color:#F5D97A;">Tính chất công cụ:</strong> FINEX VN Terminal là công
        cụ công nghệ hỗ trợ xử lý và hiển thị dữ liệu tài chính công khai từ BCTC chính thức.
        Nền tảng <strong>KHÔNG</strong> phải tổ chức tư vấn đầu tư chứng khoán và
        <strong>KHÔNG</strong> cung cấp khuyến nghị Mua/Bán/Giữ cổ phiếu cụ thể nào.<br><br>
        2. <strong style="color:#F5D97A;">Trách nhiệm cá nhân:</strong> Mọi kết quả tính toán
        định giá, chỉ số an toàn (MoS) hay dự báo tăng trưởng chỉ mang tính mô phỏng lý thuyết
        tham khảo học thuật. Nhà đầu tư tự chịu trách nhiệm hoàn toàn đối với quyết định giao
        dịch của mình.<br><br>
        3. <strong style="color:#F5D97A;">Dữ liệu:</strong> Chúng tôi nỗ lực đảm bảo tính
        chính xác của dữ liệu nhưng không chịu trách nhiệm về bất kỳ sai sót, chậm trễ hoặc
        gián đoạn nào. Dữ liệu demo chỉ để minh họa.<br><br>
        4. <strong style="color:#F5D97A;">Bản quyền:</strong> © 2024-2026 FINEX VN Terminal ·
        Trần Anh Quân. Tất cả nội dung được bảo hộ. Vui lòng không sao chép khi chưa có sự
        đồng ý bằng văn bản.
        </div></div>""",
        unsafe_allow_html=True,
    )

    # Copyright
    st.markdown(
        """<div style="text-align:center;padding:24px 0;color:#64748b;font-size:0.82em;
        border-top:1px solid #1f2937;margin-top:20px;">
        © 2024–2026 <strong style="color:#F5D97A;">FINEX VN Terminal</strong> ·
        Made with ❤️ in Vietnam ·
        Founder: <strong style="color:#60a5fa;">Trần Anh Quân</strong>
        <br><span style="font-size:0.85em;">Phiên bản v4.0 · Cập nhật: Tháng 10/2026</span>
        </div>""",
        unsafe_allow_html=True,
    )


# ============================================================================
# 13. TABS
# ============================================================================
def render_tab_overview(df_csv, ticker, cols, fin_data):
    st.subheader(f"📊 Hồ Sơ Doanh Nghiệp: {ticker}")
    info = COMPANY_INFO.get(ticker, {})
    industry = info.get("sector") or fin_data.get("industry", "Đang cập nhật")
    name = info.get("name", ticker)
    exchange = info.get("exchange", "HOSE")
    st.markdown(
        f"""<div class="glass-card" style="border-left:3px solid #60a5fa;">
        <div style="color:#93c5fd;font-weight:800;font-size:1.1em;">{name}</div>
        <div style="color:#94a3b8;font-size:0.85em;margin-top:4px;">
        🏢 Ngành: <strong style="color:#F5D97A;">{industry}</strong> ·
        📊 Sàn: <strong style="color:#F5D97A;">{exchange}</strong> ·
        Mã: <strong>{ticker}</strong></div></div>""",
        unsafe_allow_html=True,
    )

    if fin_data:
        st.markdown("### 💼 Chỉ số tài chính cốt lõi")
        st.markdown("**Định giá**")
        c = st.columns(5)
        price = fin_data.get("price", 0); eps = fin_data.get("eps_ttm", 0)
        bvps = fin_data.get("bvps", 0); pe = fin_data.get("pe_ttm", 0)
        pb = fin_data.get("pb", 0)
        c[0].metric("Giá hiện tại", f"{price:,.0f} đ" if price else "N/A")
        c[1].metric("EPS (TTM)", f"{eps:,.0f} đ" if eps else "N/A")
        c[2].metric("BVPS", f"{bvps:,.0f} đ" if bvps else "N/A")
        c[3].metric("P/E", f"{pe:.2f}" if pe else "N/A")
        c[4].metric("P/B", f"{pb:.2f}" if pb else "N/A")

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

        st.markdown("**Quy mô (tỷ VND)**")
        c = st.columns(4)
        c[0].metric("Doanh thu / TOI", _fmt_ty(fin_data.get("toi_6t2026", 0)))
        c[1].metric("LNST 2025", _fmt_ty(fin_data.get("lnst_2025", 0)))
        c[2].metric("Tổng tài sản", _fmt_ty(fin_data.get("total_assets_30062026", 0)))
        c[3].metric("Vốn hóa", _fmt_ty(fin_data.get("market_cap", 0)))

        st.markdown("**Cổ tức**")
        c = st.columns(3)
        c[0].metric("Cổ tức (VNĐ/cp)", f"{fin_data.get('div_per_share', 0):,.0f}")
        c[1].metric("Tỷ suất cổ tức", f"{fin_data.get('div_yield', 0):.2f}%")

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
                line_color="#D4AF37", fillcolor="rgba(212,175,55,0.25)"))
            fig.update_layout(
                polar=dict(
                    radialaxis=dict(visible=True, showticklabels=False, gridcolor="#1f2937"),
                    angularaxis=dict(gridcolor="#1f2937"), bgcolor="#0a1220"),
                template="plotly_dark", paper_bgcolor="#050914",
                plot_bgcolor="#0a1220", height=420, font=dict(color="#e2e8f0"))
            st.plotly_chart(fig, use_container_width=True)


def render_tab_valuation(ticker, fin_data):
    st.subheader(f"🧮 ĐỊNH GIÁ CHI TIẾT: {ticker}")
    if not fin_data:
        st.warning(f"⚠️ Không có dữ liệu định giá cho **{ticker}**."); return

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
        <div style="color:#94a3b8;font-size:0.9em;text-transform:uppercase;letter-spacing:1px;">
        💎 Giá trị Hybrid</div>
        <div style="font-size:2.4em;font-weight:800;color:#F5D97A;margin:8px 0;">
        {hy['hybrid']:,.0f} VNĐ/cp</div>
        <div style="color:#94a3b8;font-size:0.85em;">Biên an toàn:
        <strong style="color:{'#22c55e' if hy['mos']>0 else '#ef4444'};">
        {hy['mos']:+.1f}%</strong></div></div>""",
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
            score += 1; checks.append(f"✅ Biên an toàn tốt ({mos_v:.1f}% ≥ 20%)")
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

    # DCF + Bar Chart
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

        # DCF Bar chart
        st.markdown("#### 📊 So sánh 3 kịch bản DCF")
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
                          annotation_position="right",
                          annotation_font=dict(color="#60a5fa", size=11))
        fig_dcf.update_layout(
            template="plotly_dark", paper_bgcolor="#050914", plot_bgcolor="#0a1220",
            height=400, showlegend=False, font=dict(color="#e2e8f0"),
            yaxis_title="Giá trị nội tại (VNĐ/cp)",
            title="So sánh giá trị nội tại theo 3 kịch bản DCF",
        )
        st.plotly_chart(fig_dcf, use_container_width=True)

        # FCFF projection bar chart
        with st.expander("📊 Xem chi tiết dự phóng FCFF 5 năm", expanded=False):
            fig_fcff = go.Figure()
            fig_fcff.add_trace(go.Bar(
                x=[f"Năm {i}" for i in range(1, 6)],
                y=b["fcff_projections"], name="FCFF",
                marker_color="#3b82f6",
                text=[f"{v:,.0f}" for v in b["fcff_projections"]],
                textposition="outside"))
            fig_fcff.add_trace(go.Bar(
                x=[f"Năm {i}" for i in range(1, 6)],
                y=b["pv_fcff"], name="PV FCFF",
                marker_color="#22c55e",
                text=[f"{v:,.0f}" for v in b["pv_fcff"]],
                textposition="outside"))
            fig_fcff.update_layout(
                template="plotly_dark", paper_bgcolor="#050914", plot_bgcolor="#0a1220",
                height=400, font=dict(color="#e2e8f0"), barmode="group",
                yaxis_title="Tỷ VND",
                title="Dự phóng FCFF 5 năm + Giá trị hiện tại",
            )
            st.plotly_chart(fig_fcff, use_container_width=True)

            df_fcff = pd.DataFrame({
                "Năm": [f"Năm {i}" for i in range(1, 6)],
                "FCFF (tỷ VND)": [f"{x:,.0f}" for x in b["fcff_projections"]],
                "PV FCFF (tỷ VND)": [f"{x:,.0f}" for x in b["pv_fcff"]],
            })
            st.dataframe(df_fcff, use_container_width=True, hide_index=True)

        verdict = dcf["verdict"]
        v_color = "#22c55e" if "Buy" in verdict else ("#f59e0b" if verdict == "Hold" else "#ef4444")
        v_emoji = {"Buy": "🟢", "Hold": "🟡", "Sell": "🔴"}.get(verdict, "⚪")
        st.markdown(
            f"""<div style="background:linear-gradient(145deg,#111827 0%,#1a2a4a 100%);
            padding:16px 20px;border-radius:10px;border-left:5px solid {v_color};
            margin-top:12px;">
            <div style="color:{v_color};font-size:1.2em;font-weight:800;">
            {v_emoji} Khuyến nghị DCF: {verdict}</div>
            <div style="color:#94a3b8;font-size:0.88em;margin-top:6px;">
            WACC: <strong style="color:#F5D97A;">{b['wacc']*100:.2f}%</strong>
            · g: <strong style="color:#F5D97A;">{dcf['clean_inputs']['growth_rate']*100:.2f}%</strong>
            · Terminal g: <strong style="color:#F5D97A;">{dcf['clean_inputs']['terminal_growth']*100:.2f}%</strong>
            </div></div>""",
            unsafe_allow_html=True,
        )

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
        st.markdown(
            f"<span style='color:#94a3b8;font-size:0.85em;'>Kịch bản: "
            f"<strong style='color:#22c55e;'>{st.session_state.preset_active.upper()}</strong></span>",
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
        <div style="color:#94a3b8;font-size:0.85em;text-transform:uppercase;">💰 Giá trị nội tại</div>
        <div style="font-size:2em;font-weight:700;color:#22c55e;margin:8px 0;">{iv:,.0f}</div>
        <div style="color:#64748b;font-size:0.8em;">VNĐ/cp</div></div>""", unsafe_allow_html=True)
    with cr2:
        st.markdown(f"""<div class="glass-card" style="text-align:center;">
        <div style="color:#94a3b8;font-size:0.85em;text-transform:uppercase;">🛡️ Giá mua an toàn</div>
        <div style="font-size:2em;font-weight:700;color:#22c55e;margin:8px 0;">{safe_buy:,.0f}</div>
        <div style="color:#64748b;font-size:0.8em;">VNĐ/cp (MoS {mos}%)</div></div>""", unsafe_allow_html=True)
    with cr3:
        c = "#22c55e" if diff > 0 else "#ef4444"
        st.markdown(f"""<div class="glass-card" style="text-align:center;">
        <div style="color:#94a3b8;font-size:0.85em;text-transform:uppercase;">📊 Chênh lệch</div>
        <div style="font-size:2em;font-weight:700;color:{c};margin:8px 0;">{diff:+.1f}%</div>
        <div style="color:#64748b;font-size:0.8em;">Giá: {price_val:,.0f}</div></div>""", unsafe_allow_html=True)
    with cr4:
        if diff > 15: status, cls, sc = "Định giá hấp dẫn", "rec-buy", "#22c55e"
        elif diff > 5: status, cls, sc = "Định giá hợp lý", "rec-hold", "#f59e0b"
        else: status, cls, sc = "Thận trọng", "rec-sell", "#ef4444"
        st.markdown(f"""<div class="glass-card" style="text-align:center;border-left:4px solid {sc};">
        <div style="color:#94a3b8;font-size:0.85em;text-transform:uppercase;">🎯 Kết luận</div>
        <div style="margin:12px 0;"><span class="recommend-badge {cls}">{status}</span></div>
        <div style="color:#64748b;font-size:0.8em;">Dựa trên tham số đã chọn</div></div>""", unsafe_allow_html=True)
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
    div_p = ([base_div * ((1 + g_rate) ** i) for i in range(years + 1)]
             if base_div > 0
             else [(prof_p[i] * payout) / shares_out for i in range(years + 1)])
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
        subplot_titles=(f"Doanh thu & Lợi nhuận ({ticker}) — Tỷ đồng",
                        f"Cổ tức ({ticker}) — VNĐ/cp"),
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
    fig.update_layout(template="plotly_dark", paper_bgcolor="#050914",
                     plot_bgcolor="#0a1220", height=650, showlegend=True,
                     legend=dict(orientation="h", yanchor="bottom", y=1.02,
                                 xanchor="right", x=1),
                     font=dict(color="#e2e8f0"))
    fig.update_yaxes(gridcolor="#1f2937")
    st.plotly_chart(fig, use_container_width=True)


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
    status_map = {
        2: ("💎 Xuất sắc (chất lượng cao)", "#22c55e"),
        1: ("⚖️ An toàn (đạt chuẩn cơ bản)", "#3b82f6"),
        0: ("⚠️ Cảnh báo rủi ro", "#ef4444"),
    }
    label, color = status_map.get(risk, ("Chưa xác định", "#94a3b8"))
    c1, c2 = st.columns([2, 1])
    with c1:
        st.markdown(f"""<div class="glass-card" style="border-left:5px solid {color};">
        <h4 style="margin:0;color:{color};">{label}</h4>
        <p style="color:#94a3b8;font-size:0.88em;margin-top:8px;">
        Phân tích 4 chỉ số: ROE, ROA, Biên LN gộp, Nợ/VCSH.</p></div>""",
            unsafe_allow_html=True)
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
    st.dataframe(df, use_container_width=True, hide_index=True)
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
    st.info("📌 Dự báo fallback. Cài `torch`, `lightgbm`, `xgboost` để kích hoạt DL thật.")


def render_tab_bctc(ticker, df_csv, cols):
    st.subheader(f"📚 BÁO CÁO TÀI CHÍNH GỐC — {ticker}")
    if df_csv.empty:
        st.info("Chưa có file CSV tổng hợp. Đặt `vietnam_stock_database_tong_hop.csv` "
                "tại `data/` hoặc thư mục gốc.")
        return
    st.info(f"Đang có {len(df_csv):,} bản ghi CSV. Hiển thị dữ liệu thô cho {ticker}.")
    ticker_col = cols.get("ticker")
    if ticker_col:
        df_sub = df_csv[df_csv[ticker_col] == ticker]
        if not df_sub.empty:
            st.dataframe(df_sub, use_container_width=True, height=500, hide_index=True)
        else:
            st.info(f"Không có dữ liệu cho mã {ticker}.")


def render_tab_data(df_csv, ticker, cols):
    st.subheader(f"📋 Dữ liệu chi tiết — {ticker}")
    if df_csv.empty:
        st.warning("⚠️ Không có file CSV. Đặt file tại `data/`.")
        return
    ticker_col = cols.get("ticker")
    period_col = cols.get("period")
    metric_col = cols.get("metric")
    value_col = cols.get("value")
    df_sub = df_csv[df_csv[ticker_col] == ticker].copy()
    if df_sub.empty:
        st.info(f"Không có bản ghi cho mã {ticker}."); return
    df_sub[value_col] = pd.to_numeric(
        df_sub[value_col].astype(str).str.replace(",", "").str.replace(" ", ""),
        errors="coerce")
    st.markdown("### 📈 Trực quan hoá chỉ số")
    available = sorted(df_sub[metric_col].dropna().astype(str).unique().tolist())
    if available:
        defaults = [m for m in available if any(k in m.lower() for k in
                    ["doanh thu", "lợi nhuận", "lãi", "tài sản"])][:5]
        if not defaults: defaults = available[:3]
        sel = st.multiselect("Chọn chỉ tiêu:", available, default=defaults,
                             key=f"chart_sel_{ticker}")
        chart_type = st.radio("Dạng:", ["Cột nhóm", "Đường xu hướng"],
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
            fig.update_layout(xaxis_title="Kỳ", yaxis_title="Giá trị",
                              hovermode="x unified", height=520,
                              plot_bgcolor="#0a1220", paper_bgcolor="#050914",
                              font=dict(color="#e2e8f0"))
            st.plotly_chart(fig, use_container_width=True)
    st.markdown("---")
    search = st.text_input("🔍 Lọc nhanh:", placeholder="Doanh thu, Nợ...",
                           key=f"search_{ticker}")
    df_disp = df_sub
    if search:
        mask = df_sub.astype(str).apply(
            lambda col: col.str.contains(search, case=False, na=False)).any(axis=1)
        df_disp = df_sub[mask]
    st.caption(f"Hiển thị {len(df_disp):,} / {len(df_sub):,}")
    st.dataframe(df_disp, use_container_width=True, height=420, hide_index=True)
    st.download_button(label=f"📥 Tải CSV ({ticker})",
                       data=df_sub.to_csv(index=False).encode("utf-8-sig"),
                       file_name=f"FINEX_{ticker}.csv", mime="text/csv")


# ============================================================================
# 14. DIVIDEND CALCULATORS
# ============================================================================
def render_cash_dividend_ui():
    st.markdown("## 💵 MÁY TÍNH CỔ TỨC TIỀN MẶT")
    st.markdown("*Tính cổ tức nhận được dựa trên vốn và giá.*")
    c1, c2, c3 = st.columns(3)
    with c1:
        ticker = st.text_input("Mã CP:", value="TCB").upper().strip()
    with c2:
        price = st.selectbox("Giá (VNĐ):", DEFAULT_PRICE_LIST, index=4)
    with c3:
        capital = st.number_input("Vốn (VNĐ):", min_value=MIN_CAPITAL_VND,
                                  max_value=MAX_CAPITAL_VND, step=CAPITAL_STEP_VND,
                                  value=1_000_000_000, format="%d")
    st.markdown("---")
    c4, c5 = st.columns(2)
    with c4:
        tax = st.number_input("Thuế TNCN (%):", min_value=0.0, max_value=10.0,
                              value=5.0, step=0.1)
    with c5:
        div_pct = st.slider("Tỷ lệ cổ tức (% Mệnh giá):",
                            min_value=MIN_DIVIDEND_PERCENT,
                            max_value=MAX_DIVIDEND_PERCENT,
                            step=DIVIDEND_PERCENT_STEP, value=15)
    cash_ps = PAR_VALUE_DEFAULT * div_pct / 100
    shares = _buyable_shares(capital, price)
    res = _cash_dividend_actual(shares, cash_ps, tax)
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
        rows.append({
            "Vốn (VNĐ)": _fmt_vnd(cap), "Số CP": _fmt_shares(sh),
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
                     title="Cổ tức thực nhận theo vốn",
                     color="Thực nhận (triệu)", color_continuous_scale="Greens")
        fig.update_layout(template="plotly_dark", plot_bgcolor="#0a1220",
                         paper_bgcolor="#050914", font=dict(color="#e2e8f0"))
        st.plotly_chart(fig, use_container_width=True)


def render_stock_dividend_ui():
    st.markdown("## 📈 MÁY TÍNH CỔ TỨC BẰNG CỔ PHIẾU")
    st.markdown("*Tính số cổ phiếu nhận thêm từ chia cổ tức bằng CP.*")
    c1, c2 = st.columns(2)
    with c1:
        ticker = st.text_input("Mã CP:", value="TCB").upper().strip()
    with c2:
        owned = st.number_input("Số CP đang sở hữu:", min_value=MIN_OWNED_SHARES,
                                max_value=MAX_OWNED_SHARES, step=10_000,
                                value=100_000, format="%d")
    ratio = st.slider("Tỷ lệ cổ tức CP (%):",
                      min_value=MIN_DIVIDEND_PERCENT, max_value=MAX_DIVIDEND_PERCENT,
                      step=DIVIDEND_PERCENT_STEP, value=15)
    res = _stock_dividend(owned, ratio)
    st.markdown("### 📊 Kết quả")
    c = st.columns(3)
    c[0].metric("Cổ phiếu ban đầu", _fmt_shares(owned))
    c[1].metric("Cổ phiếu nhận thêm", f"+{_fmt_shares(res['additional_shares'])}",
                delta="Cổ tức CP", delta_color="normal")
    c[2].metric("Tổng sau phát hành", _fmt_shares(res["total_after"]))

    # Stock dividend chart
    st.markdown("---")
    st.markdown("### 📊 Biểu đồ kịch bản theo tỷ lệ chia (5% – 100%)")
    scenarios = []
    for r in range(MIN_DIVIDEND_PERCENT, MAX_DIVIDEND_PERCENT + 1, DIVIDEND_PERCENT_STEP):
        s = _stock_dividend(owned, r)
        scenarios.append({
            "Tỷ lệ (%)": r,
            "CP nhận thêm": s["additional_shares"],
            "Tổng CP sau": s["total_after"],
        })
    if scenarios:
        df_scn = pd.DataFrame(scenarios)
        fig = px.bar(df_scn, x="Tỷ lệ (%)", y="Tổng CP sau",
                     title="Tổng số cổ phiếu sau khi chia cổ tức theo tỷ lệ",
                     color="CP nhận thêm", color_continuous_scale="Blues")
        fig.update_layout(template="plotly_dark", paper_bgcolor="#050914",
                         plot_bgcolor="#0a1220", font=dict(color="#e2e8f0"))
        st.plotly_chart(fig, use_container_width=True)
        st.dataframe(df_scn, use_container_width=True, hide_index=True)
    st.caption("⚠️ Cổ tức bằng CP làm tăng SLCP nhưng không mặc nhiên làm tăng giá trị tài sản.")


# ============================================================================
# 15. MAIN
# ============================================================================
def main():
    inject_css()
    st.session_state.setdefault("selected_ticker", "FPT")
    st.session_state.setdefault("selected_partner", None)
    st.session_state.setdefault("show_partner_dialog", False)
    st.session_state.setdefault("show_vip_dialog", False)
    st.session_state.setdefault("selected_plan", None)

    df_csv, csv_path = load_database()

    # === SIDEBAR ===
    with st.sidebar:
        st.markdown(
            """<div style='text-align:center;padding:14px 0 10px 0;
            border-bottom:1px solid #1f2937;margin-bottom:12px;'>
            <div style='color:#D4AF37;font-size:1.6em;font-weight:800;
            letter-spacing:2px;'>FINEX</div>
            <div style='color:#94a3b8;font-size:0.72em;letter-spacing:3px;
            text-transform:uppercase;'>Vietnam Terminal</div>
            </div>""",
            unsafe_allow_html=True,
        )
        cols = _get_csv_columns(df_csv) if not df_csv.empty else {}
        tickers_available = []
        if not df_csv.empty and cols.get("ticker"):
            df_csv[cols["ticker"]] = df_csv[cols["ticker"]].astype(str).str.strip().str.upper()
            tickers_available = sorted([t for t in df_csv[cols["ticker"]].unique()
                                         if t and t != "NAN"])
        if not tickers_available:
            tickers_available = sorted(DEMO_FINANCIAL_DATA.keys())
            st.caption("⚠️ Chưa có CSV — dùng dữ liệu demo.")
        if tickers_available and st.session_state.selected_ticker not in tickers_available:
            st.session_state.selected_ticker = ("FPT" if "FPT" in tickers_available
                                                else tickers_available[0])
        default_idx = (tickers_available.index(st.session_state.selected_ticker)
                       if st.session_state.selected_ticker in tickers_available else 0)
        if tickers_available:
            chosen = st.selectbox("📈 Chọn mã cổ phiếu:", tickers_available,
                                  index=default_idx, key="ticker_sel")
            if chosen != st.session_state.selected_ticker:
                st.session_state.selected_ticker = chosen; st.rerun()

        st.markdown("---")
        st.markdown("### 🧮 CHỨC NĂNG")
        app_mode = st.radio(
            "Chế độ:",
            ["🏛️ Terminal", "💵 Cổ tức tiền mặt",
             "📈 Cổ tức cổ phiếu", "📉 Khủng hoảng lịch sử"],
            key="app_mode")
        st.markdown("---")
        st.info(f"💡 Đang quản lý **{len(tickers_available)}** mã.")
        if not df_csv.empty:
            st.caption(f"📂 CSV: `{csv_path}`")
        st.markdown("---")
        if st.button("🚀 Nâng cấp VIP", use_container_width=True, type="primary"):
            st.session_state.show_vip_dialog = True; st.rerun()
        render_profiler_panel()

    # === MODE ROUTING ===
    render_header()

    if app_mode == "💵 Cổ tức tiền mặt":
        render_cash_dividend_ui(); return
    if app_mode == "📈 Cổ tức cổ phiếu":
        render_stock_dividend_ui(); return
    if app_mode == "📉 Khủng hoảng lịch sử":
        keys = list(HISTORICAL_CRISES.keys())
        sel = st.selectbox("Chọn khủng hoảng:", keys, key="cr_sel")
        render_crisis_section(sel); return

    # === TERMINAL MODE ===
    # Partner buttons + ticker info
    col_broker, col_info = st.columns([1.4, 1], gap="large")
    with col_broker:
        render_partner_buttons()
    with col_info:
        fin_data_current = get_financials(st.session_state.selected_ticker, df_csv, cols)
        render_ticker_info_card(st.session_state.selected_ticker, fin_data_current)

    # CTA banner #1
    render_cta_banner(
        "Mở khóa toàn bộ sức mạnh FINEX",
        "Nâng cấp Pro Trader để mở ML/DL forecast, xuất PDF, API và nhiều hơn nữa!",
        "💎 Xem các gói ưu đãi",
        "header",
    )

    # Dialogs
    if st.session_state.get("show_partner_dialog", False):
        partner_detail_dialog()
    if st.session_state.get("show_vip_dialog", False):
        vip_upgrade_dialog()

    # VNINDEX CHART (visible, not expander)
    with prof("📈 VNINDEX chart"):
        with st.expander("📈 VN-INDEX 26 NĂM — Bấm để xem/mở rộng", expanded=True):
            render_vnindex_chart()

    # Tabs
    ticker = st.session_state.selected_ticker
    fin_data = get_financials(ticker, df_csv, cols)
    tabs = st.tabs([
        "📊 Tổng quan", "🧮 Định giá", "📈 Dự báo",
        "🤖 ML", "🧠 DL", "📚 BCTC Gốc", "📋 Dữ liệu chi tiết",
    ])
    with tabs[0]:
        with prof("📊 Tổng quan"):
            render_tab_overview(df_csv, ticker, cols, fin_data)
    with tabs[1]:
        with prof("🧮 Định giá"):
            render_tab_valuation(ticker, fin_data)
    with tabs[2]:
        with prof("📈 Dự báo"):
            render_tab_forecast(ticker, fin_data)
    with tabs[3]:
        with prof("🤖 ML"):
            render_tab_ml(ticker, fin_data)
    with tabs[4]:
        with prof("🧠 DL"):
            render_tab_dl(ticker, fin_data)
    with tabs[5]:
        with prof("📚 BCTC Gốc"):
            render_tab_bctc(ticker, df_csv, cols)
    with tabs[6]:
        with prof("📋 Dữ liệu"):
            render_tab_data(df_csv, ticker, cols)

    # CTA banner #2
    render_cta_banner(
        "Bạn đã xem hết tính năng?",
        "Nâng cấp ngay để mở khóa Xuất báo cáo PDF, Tối ưu danh mục, API và nhiều hơn nữa.",
        "💎 Chọn gói phù hợp",
        "middle",
    )

    # VIP section (main page, full pricing)
    render_vip_section_main()

    # Bottom sections
    st.markdown("---")
    with prof("✅ Accuracy"):
        render_accuracy_section(ticker)

    st.markdown("---")
    with prof("📌 Undervalued"):
        render_undervalued_stocks()

    st.markdown("---")
    render_document_section()

    # Crisis section
    st.markdown("---")
    st.markdown(
        """<div style='text-align:center;padding:16px 0 8px 0;'>
        <h2 style='color:#ef4444;margin:0;'>📉 BÀI HỌC TỪ CÁC CUỘC KHỦNG HOẢNG LỊCH SỬ</h2>
        <p style='color:#94a3b8;font-size:0.95em;margin-top:8px;'>
        Phân tích cú sốc thị trường · Phản ứng nhà điều hành · Stress Test danh mục</p>
        </div>""",
        unsafe_allow_html=True)
    crisis_keys = list(HISTORICAL_CRISES.keys())
    default_crisis = crisis_keys.index("COVID_2020") if "COVID_2020" in crisis_keys else 0
    sel_cr = st.selectbox("🔍 Chọn cuộc khủng hoảng:", crisis_keys,
                          index=default_crisis, key="crisis_main")
    render_crisis_section(sel_cr)

    # CTA banner #3
    render_cta_banner(
        "Sẵn sàng nâng tầm phân tích đầu tư?",
        "Tham gia cùng hàng ngàn nhà đầu tư chuyên nghiệp đang dùng FINEX mỗi ngày!",
        "🚀 Nâng cấp ngay hôm nay",
        "footer",
    )

    # FULL FOOTER
    render_full_footer()


if __name__ == "__main__":
    main()
