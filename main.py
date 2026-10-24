
# ============================================================================
# FINEX VN TERMINAL — HISTORICAL FINANCIAL STATEMENTS v3.0
#
# Phạm vi:
#   - VN30 + VN100 + HNX30
#   - Năm tài chính 2016–2026
#   - 3 báo cáo: Cân đối kế toán, Kết quả kinh doanh, Lưu chuyển tiền tệ
#   - BCTC năm: 2016–2026 nếu nguồn có dữ liệu
#   - BCTC quý năm 2026: lưu riêng, không cộng/trộn vào BCTC năm
#
# Tệp đầu ra:
#   data_finex/finex_universe.csv
#   data_finex/bctc_lich_su_2016_2026.csv
#   data_finex/bao_cao_thieu_du_lieu.csv
#   data_finex/loi_thu_thap.csv
#
# Cài đặt:
#   pip install -U pandas yfinance
#
# LƯU Ý:
#   Yahoo Finance không đảm bảo đủ dữ liệu lịch sử cho mọi mã Việt Nam.
#   Code không tự tạo số liệu hoặc coi dữ liệu thiếu là 0.
# ============================================================================

import os
import time
from datetime import datetime
from collections import defaultdict

import pandas as pd
import yfinance as yf


# ============================================================================
# 1. CẤU HÌNH
# ============================================================================

START_YEAR = 2016
END_YEAR = 2026

OUTPUT_DIR = "data_finex"
os.makedirs(OUTPUT_DIR, exist_ok=True)

OUTPUT_UNIVERSE = os.path.join(
    OUTPUT_DIR, "finex_universe.csv"
)

OUTPUT_DATA = os.path.join(
    OUTPUT_DIR, "bctc_lich_su_2016_2026.csv"
)

OUTPUT_MISSING = os.path.join(
    OUTPUT_DIR, "bao_cao_thieu_du_lieu.csv"
)

OUTPUT_ERRORS = os.path.join(
    OUTPUT_DIR, "loi_thu_thap.csv"
)

REQUEST_DELAY = 0.5
SCRAPE_TIME = datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# ============================================================================
# 2. DANH SÁCH CHỈ SỐ
# Đây là danh sách nghiên cứu đầu vào; cần xác minh thành phần chỉ số
# chính thức theo từng kỳ cơ cấu.
# ============================================================================

VN30 = [
    "ACB", "BCM", "BID", "CTG", "DGC", "FPT", "GAS", "GVR",
    "HDB", "HPG", "LPB", "MBB", "MCH", "MSN", "MWG", "SAB",
    "SHB", "SSB", "SSI", "STB", "TCB", "TCX", "VCB", "VHM",
    "VIB", "VIC", "VJC", "VNM", "VPB", "VRE"
]

VN100 = [
    "VIC", "VHM", "VCB", "BID", "TCB", "VPB", "CTG", "GAS",
    "MCH", "MBB", "HPG", "VPL", "BSR", "GVR", "STB", "VNM",
    "ACB", "LPB", "MSN", "MWG", "HDB", "FPT", "VJC", "TCX",
    "SSI", "VCK", "MSB", "SHB", "VRE", "SAB", "SSB", "VIB",
    "BVH", "GEE", "PLX", "VPX", "BCM", "TPB", "POW", "GMD",
    "VIX", "EIB", "OCB", "GEX", "REE", "FRT", "HCM", "NAB",
    "NVL", "KBC", "VCI", "VND", "VGC", "SBT", "VPI", "HAG",
    "DCM", "KDH", "PVD", "SJS", "DPM", "KDC", "DXG", "SIP",
    "PVT", "PDR", "TCH", "BAF", "BMP", "TAL", "NLG", "VHC",
    "VCG", "BWE", "DGW", "VTP", "PNJ", "EVF", "CII", "CTR",
    "HSG", "DIG", "DSE", "PC1", "PHR", "CTD", "FTS", "BSI",
    "NT2", "DBC", "HDG", "CTS", "NKG", "HHV", "VSC", "HT1",
    "ANV", "CMG", "PAN", "KOS"
]

HNX30 = [
    "BCC", "BVS", "CAP", "CEO", "DTD", "DVM", "DXP", "HLD",
    "HUT", "IDC", "L14", "L18", "LAS", "LHC", "MBS", "NBC",
    "NDN", "PLC", "PSI", "PVC", "PVG", "PVS", "SHS", "SLS",
    "TIG", "TNG", "TVD", "VC3", "VCS", "VFS"
]


# ============================================================================
# 3. PHÂN LOẠI NGÀNH FINEX
# Phân loại 3 nhóm phục vụ nghiên cứu, không phải phân ngành chính thức.
# Các mã phi tài chính còn lại được xếp vào nhóm tổng hợp sản xuất/công nghiệp.
# ============================================================================

FINANCIAL = {
    "VCB", "BID", "TCB", "VPB", "CTG", "MBB", "STB", "ACB",
    "LPB", "HDB", "SHB", "SSB", "SSI", "TPB", "VIB", "MSB",
    "BVH", "VIX", "EIB", "OCB", "HCM", "NAB", "VCI", "VND",
    "VCK", "DSE", "EVF", "FTS", "BSI", "CTS", "BVS", "MBS",
    "PSI", "SHS", "VFS"
}

TECHNOLOGY = {
    "FPT", "CMG", "CTR", "DGW", "VTP"
}


def classify_sector(symbol):
    if symbol in FINANCIAL:
        return "Tài chính"
    if symbol in TECHNOLOGY:
        return "Công nghệ"
    return "Sản xuất và công nghiệp"


# ============================================================================
# 4. TẠO DANH SÁCH MASTER KHÔNG LÀM MẤT MÃ GIAO NHAU
# ============================================================================

membership = defaultdict(set)

for symbol in VN30:
    membership[symbol].add("VN30")

for symbol in VN100:
    membership[symbol].add("VN100")

for symbol in HNX30:
    membership[symbol].add("HNX30")


def get_yahoo_symbol(symbol, indexes):
    """
    Mã trên Yahoo Finance có thể dùng hậu tố khác nhau theo sàn.
    HNX thường dùng .HN; HOSE thường dùng .VN.
    Nếu mã nằm ở nhiều danh sách, cần xác minh sàn thực tế.
    """

    if "HNX30" in indexes and "VN30" not in indexes and "VN100" not in indexes:
        return f"{symbol}.HN"

    return f"{symbol}.VN"


universe = []

for symbol, index_set in sorted(membership.items()):
    indexes = sorted(index_set)

    universe.append({
        "ma_chung_khoan": symbol,
        "chi_so": "|".join(indexes),
        "nhom_nganh_finex": classify_sector(symbol),
        "yahoo_symbol": get_yahoo_symbol(symbol, index_set)
    })

universe_columns = [
    "ma_chung_khoan",
    "chi_so",
    "nhom_nganh_finex",
    "yahoo_symbol"
]

df_universe = pd.DataFrame(universe, columns=universe_columns)

df_universe.to_csv(
    OUTPUT_UNIVERSE,
    index=False,
    encoding="utf-8-sig"
)

print(f"Tổng mã duy nhất: {len(df_universe)}")
print(df_universe["nhom_nganh_finex"].value_counts().to_string())


# ============================================================================
# 5. CHUẨN HÓA TÊN KHOẢN MỤC
#
# Lưu cả:
#   - khoan_muc_goc: tên do Yahoo Finance trả về
#   - khoan_muc_tieng_viet: tên dịch nếu đã xác định được
#
# Không xóa tên gốc, vì một số khoản mục có thể khác nhau theo ngành.
# ============================================================================

TRANSLATION_MAP = {
    # ------------------------------------------------------------------------
    # BÁO CÁO KẾT QUẢ KINH DOANH
    # ------------------------------------------------------------------------
    "Total Revenue": "Tổng doanh thu",
    "Operating Revenue": "Doanh thu hoạt động",
    "Revenue": "Doanh thu",
    "Cost Of Revenue": "Giá vốn hàng bán",
    "Cost Of Goods Sold": "Giá vốn hàng bán",
    "Gross Profit": "Lợi nhuận gộp",
    "Operating Income": "Lợi nhuận thuần từ hoạt động kinh doanh",
    "Operating Expense": "Chi phí hoạt động",
    "Selling General And Administration": "Chi phí bán hàng và quản lý doanh nghiệp",
    "Research And Development": "Chi phí nghiên cứu và phát triển",
    "Depreciation And Amortization": "Chi phí khấu hao và phân bổ",
    "Interest Expense": "Chi phí lãi vay",
    "Interest Income": "Thu nhập lãi",
    "Net Interest Income": "Thu nhập lãi thuần",
    "Pretax Income": "Lợi nhuận trước thuế",
    "Tax Provision": "Chi phí thuế thu nhập doanh nghiệp",
    "Tax Effect Of Unusual Items": "Ảnh hưởng thuế của khoản mục bất thường",
    "Net Income": "Lợi nhuận sau thuế",
    "Net Income Common Stockholders": "Lợi nhuận sau thuế thuộc cổ đông phổ thông",
    "Diluted EPS": "Lãi suy giảm trên cổ phiếu",
    "Basic EPS": "Lãi cơ bản trên cổ phiếu",
    "Basic Average Shares": "Số cổ phiếu bình quân cơ bản",
    "Diluted Average Shares": "Số cổ phiếu bình quân pha loãng",
    "EBIT": "Lợi nhuận trước lãi vay và thuế",
    "EBITDA": "Lợi nhuận trước lãi vay, thuế và khấu hao",

    # ------------------------------------------------------------------------
    # BẢNG CÂN ĐỐI KẾ TOÁN
    # ------------------------------------------------------------------------
    "Total Assets": "Tổng tài sản",
    "Current Assets": "Tài sản ngắn hạn",
    "Cash And Cash Equivalents": "Tiền và tương đương tiền",
    "Cash Cash Equivalents And Short Term Investments": "Tiền, tương đương tiền và đầu tư ngắn hạn",
    "Accounts Receivable": "Các khoản phải thu",
    "Inventory": "Hàng tồn kho",
    "Other Current Assets": "Tài sản ngắn hạn khác",
    "Total Non Current Assets": "Tài sản dài hạn",
    "Net PPE": "Tài sản cố định hữu hình ròng",
    "Goodwill": "Lợi thế thương mại",
    "Intangible Assets": "Tài sản vô hình",
    "Investments And Advances": "Các khoản đầu tư và góp vốn",
    "Total Liabilities Net Minority Interest": "Tổng nợ phải trả",
    "Current Liabilities": "Nợ ngắn hạn",
    "Total Non Current Liabilities Net Minority Interest": "Nợ dài hạn",
    "Long Term Debt": "Nợ vay dài hạn",
    "Current Debt": "Nợ vay ngắn hạn",
    "Total Debt": "Tổng nợ vay",
    "Stockholders Equity": "Vốn chủ sở hữu",
    "Common Stock Equity": "Vốn chủ sở hữu thuộc cổ đông phổ thông",
    "Capital Stock": "Vốn cổ phần",
    "Retained Earnings": "Lợi nhuận chưa phân phối",
    "Minority Interest": "Lợi ích cổ đông không kiểm soát",
    "Total Equity Gross Minority Interest": "Tổng vốn chủ sở hữu bao gồm lợi ích cổ đông không kiểm soát",
    "Accounts Payable": "Các khoản phải trả",

    # ------------------------------------------------------------------------
    # BÁO CÁO LƯU CHUYỂN TIỀN TỆ
    # ------------------------------------------------------------------------
    "Operating Cash Flow": "Lưu chuyển tiền thuần từ hoạt động kinh doanh",
    "Cash Flow From Continuing Operating Activities": "Lưu chuyển tiền từ hoạt động kinh doanh tiếp tục",
    "Investing Cash Flow": "Lưu chuyển tiền thuần từ hoạt động đầu tư",
    "Cash Flow From Continuing Investing Activities": "Lưu chuyển tiền từ hoạt động đầu tư tiếp tục",
    "Financing Cash Flow": "Lưu chuyển tiền thuần từ hoạt động tài chính",
    "Cash Flow From Continuing Financing Activities": "Lưu chuyển tiền từ hoạt động tài chính tiếp tục",
    "Capital Expenditure": "Chi đầu tư tài sản cố định",
    "Free Cash Flow": "Dòng tiền tự do",
    "Depreciation And Amortization": "Khấu hao và phân bổ",
    "Changes In Working Capital": "Thay đổi vốn lưu động",
    "Stock Based Compensation": "Chi phí trả bằng cổ phiếu",
    "Issuance Of Debt": "Tiền thu từ phát hành nợ",
    "Repayment Of Debt": "Tiền chi trả nợ",
    "Repurchase Of Capital Stock": "Tiền chi mua lại cổ phiếu",
    "Cash Dividends Paid": "Tiền chi trả cổ tức",
    "Beginning Cash Position": "Tiền đầu kỳ",
    "End Cash Position": "Tiền cuối kỳ",
    "Changes In Cash": "Thay đổi tiền trong kỳ"
}


def translate_metric(raw_name):
    """
    Dịch theo tên khớp chính xác trước.
    Nếu không có tên tương ứng, giữ nguyên tên nguồn.
    """

    raw_name = str(raw_name).strip()

    if raw_name in TRANSLATION_MAP:
        return TRANSLATION_MAP[raw_name]

    # Tìm khớp không phân biệt chữ hoa/chữ thường.
    lower_map = {
        key.lower(): value
        for key, value in TRANSLATION_MAP.items()
    }

    return lower_map.get(raw_name.lower(), raw_name)


# ============================================================================
# 6. HÀM CHUẨN HÓA
# ============================================================================

def normalize_date(value):
    try:
        dt = pd.Timestamp(value)

        if pd.isna(dt):
            return None

        if dt.tzinfo is not None:
            dt = dt.tz_localize(None)

        return dt.strftime("%Y-%m-%d")

    except Exception:
        return None


def to_number(value):
    try:
        if pd.isna(value):
            return None

        return float(value)

    except (ValueError, TypeError, OverflowError):
        return None


def report_year(period_date):
    if not period_date:
        return None

    return int(period_date[:4])


# ============================================================================
# 7. HÀM LẤY BCTC NĂM VÀ QUÝ
# ============================================================================

STATEMENTS = [
    {
        "kind": "income",
        "name": "Báo cáo kết quả kinh doanh",
        "annual_method": "get_income_stmt",
        "fallback_attr": "financials"
    },
    {
        "kind": "balance",
        "name": "Bảng cân đối kế toán",
        "annual_method": "get_balance_sheet",
        "fallback_attr": "balance_sheet"
    },
    {
        "kind": "cashflow",
        "name": "Báo cáo lưu chuyển tiền tệ",
        "annual_method": "get_cash_flow",
        "fallback_attr": "cashflow"
    }
]


def fetch_statement(ticker, config, frequency):
    """
    frequency='yearly' hoặc 'quarterly'.

    Fallback property của yfinance thường là báo cáo năm.
    Không dùng fallback này để gắn nhãn báo cáo quý.
    """

    method_name = config["annual_method"]

    if hasattr(ticker, method_name):
        method = getattr(ticker, method_name)

        try:
            return method(freq=frequency)
        except Exception:
            pass

    if frequency == "yearly":
        try:
            return getattr(ticker, config["fallback_attr"])
        except Exception:
            return pd.DataFrame()

    return pd.DataFrame()


def extract_statement_rows(
    ticker,
    stock,
    config,
    frequency,
    year_min,
    year_max
):
    records = []
    errors = []

    symbol = stock["ma_chung_khoan"]
    indexes = stock["chi_so"]
    sector = stock["nhom_nganh_finex"]
    yahoo_symbol = stock["yahoo_symbol"]

    try:
        statement_df = fetch_statement(
            ticker,
            config,
            frequency
        )

        if statement_df is None or statement_df.empty:
            return records, errors, False

        for period_col in statement_df.columns:
            period_date = normalize_date(period_col)

            if not period_date:
                continue

            year = report_year(period_date)

            if year is None or year < year_min or year > year_max:
                continue

            # Chỉ thu thập báo cáo quý trong năm 2026.
            if frequency == "quarterly" and year != 2026:
                continue

            for raw_metric, raw_value in statement_df[period_col].items():
                value = to_number(raw_value)

                # Không loại bỏ giá trị 0 nếu nguồn thực sự trả về 0.
                if value is None:
                    continue

                raw_metric = str(raw_metric).strip()

                records.append({
                    "ma_chung_khoan": symbol,
                    "chi_so": indexes,
                    "nhom_nganh_finex": sector,
                    "ma_nguon": yahoo_symbol,

                    "loai_bao_cao": config["name"],
                    "tan_suat_bao_cao": (
                        "Năm" if frequency == "yearly" else "Quý"
                    ),

                    # Năm được lấy từ ngày kết thúc kỳ do nguồn cung cấp.
                    "nam_tai_chinh": year,
                    "ngay_ket_thuc_ky": period_date,

                    # Lưu nguyên tên nguồn để có thể kiểm tra và dịch lại.
                    "khoan_muc_goc": raw_metric,
                    "khoan_muc_tieng_viet": translate_metric(raw_metric),

                    # Không giả định đơn vị là đồng, nghìn đồng hay triệu đồng.
                    "gia_tri_nguon": value,
                    "don_vi_tien_te": "Chưa xác minh đơn vị nguồn",
                    "nguon_du_lieu": "Yahoo Finance",
                    "thoi_gian_thu_thap": SCRAPE_TIME
                })

        return records, errors, True

    except Exception as exc:
        errors.append({
            "ma_chung_khoan": symbol,
            "chi_so": indexes,
            "loai_bao_cao": config["name"],
            "tan_suat_bao_cao": frequency,
            "nam_yeu_cau": f"{year_min}-{year_max}",
            "ma_nguon": yahoo_symbol,
            "loi": str(exc),
            "thoi_gian_thu_thap": SCRAPE_TIME
        })

        return records, errors, False


# ============================================================================
# 8. THU THẬP TOÀN BỘ DANH SÁCH
# ============================================================================

def main():
    all_records = []
    all_errors = []
    missing_records = []

    print("\n" + "=" * 80)
    print("FINEX — THU THẬP BCTC LỊCH SỬ 2016–2026")
    print(f"Thời điểm: {SCRAPE_TIME}")
    print(f"Số mã master: {len(universe)}")
    print("=" * 80)

    for number, stock in enumerate(universe, start=1):
        symbol = stock["ma_chung_khoan"]
        yahoo_symbol = stock["yahoo_symbol"]

        print(
            f"\n[{number}/{len(universe)}] "
            f"{symbol} | {stock['chi_so']} | "
            f"{stock['nhom_nganh_finex']} | {yahoo_symbol}"
        )

        try:
            ticker = yf.Ticker(yahoo_symbol)
        except Exception as exc:
            all_errors.append({
                "ma_chung_khoan": symbol,
                "chi_so": stock["chi_so"],
                "loai_bao_cao": "Khởi tạo mã",
                "tan_suat_bao_cao": "",
                "nam_yeu_cau": f"{START_YEAR}-{END_YEAR}",
                "ma_nguon": yahoo_symbol,
                "loi": str(exc),
                "thoi_gian_thu_thap": SCRAPE_TIME
            })
            continue

        # ---------------------------------------------------------------
        # BCTC NĂM: 2016–2026
        # ---------------------------------------------------------------

        for config in STATEMENTS:
            records, errors, has_statement = extract_statement_rows(
                ticker=ticker,
                stock=stock,
                config=config,
                frequency="yearly",
                year_min=START_YEAR,
                year_max=END_YEAR
            )

            all_records.extend(records)
            all_errors.extend(errors)

            available_years = {
                row["nam_tai_chinh"]
                for row in records
            }

            for year in range(START_YEAR, END_YEAR + 1):
                if year not in available_years:
                    missing_records.append({
                        "ma_chung_khoan": symbol,
                        "chi_so": stock["chi_so"],
                        "nhom_nganh_finex": stock["nhom_nganh_finex"],
                        "loai_bao_cao": config["name"],
                        "tan_suat_bao_cao": "Năm",
                        "nam_can_kiem_tra": year,
                        "trang_thai": (
                            "Không thấy dữ liệu năm trong kết quả nguồn"
                        ),
                        "ghi_chu": (
                            "Có thể nguồn không cung cấp, "
                            "không đồng nghĩa doanh nghiệp chưa công bố"
                        )
                    })

        # ---------------------------------------------------------------
        # BCTC QUÝ NĂM 2026
        # Tách riêng, không coi quý là báo cáo năm.
        # ---------------------------------------------------------------

        for config in STATEMENTS:
            records, errors, has_statement = extract_statement_rows(
                ticker=ticker,
                stock=stock,
                config=config,
                frequency="quarterly",
                year_min=2026,
                year_max=2026
            )

            all_records.extend(records)
            all_errors.extend(errors)

            if not records:
                missing_records.append({
                    "ma_chung_khoan": symbol,
                    "chi_so": stock["chi_so"],
                    "nhom_nganh_finex": stock["nhom_nganh_finex"],
                    "loai_bao_cao": config["name"],
                    "tan_suat_bao_cao": "Quý",
                    "nam_can_kiem_tra": 2026,
                    "trang_thai": "Không có dữ liệu quý 2026 trong kết quả nguồn",
                    "ghi_chu": "Cần kiểm tra thêm nguồn công bố chính thức"
                })

            all_errors.extend(errors)

        print(
            f"  Tổng số dòng đã thu thập đến hiện tại: "
            f"{len(all_records):,}"
        )

        time.sleep(REQUEST_DELAY)

    # =========================================================================
    # 9. CHUẨN HÓA VÀ XUẤT DỮ LIỆU
    # =========================================================================

    data_columns = [
        "ma_chung_khoan",
        "chi_so",
        "nhom_nganh_finex",
        "ma_nguon",
        "loai_bao_cao",
        "tan_suat_bao_cao",
        "nam_tai_chinh",
        "ngay_ket_thuc_ky",
        "khoan_muc_goc",
        "khoan_muc_tieng_viet",
        "gia_tri_nguon",
        "don_vi_tien_te",
        "nguon_du_lieu",
        "thoi_gian_thu_thap"
    ]

    if all_records:
        df = pd.DataFrame(all_records, columns=data_columns)

        # Loại bản ghi trùng đúng theo mã + báo cáo + kỳ + khoản mục.
        # Năm và quý được phân biệt bằng tan_suat_bao_cao.
        df = df.drop_duplicates(
            subset=[
                "ma_chung_khoan",
                "loai_bao_cao",
                "tan_suat_bao_cao",
                "ngay_ket_thuc_ky",
                "khoan_muc_goc"
            ],
            keep="last"
        )

        df["nam_tai_chinh"] = pd.to_numeric(
            df["nam_tai_chinh"],
            errors="coerce"
        ).astype("Int64")

        df = df.sort_values(
            [
                "nhom_nganh_finex",
                "ma_chung_khoan",
                "loai_bao_cao",
                "tan_suat_bao_cao",
                "ngay_ket_thuc_ky",
                "khoan_muc_goc"
            ]
        )

        df.to_csv(
            OUTPUT_DATA,
            index=False,
            encoding="utf-8-sig"
        )

        print("\n" + "=" * 80)
        print("HOÀN THÀNH")
        print(f"Tổng số dòng BCTC: {len(df):,}")
        print(f"Số mã có dữ liệu: {df['ma_chung_khoan'].nunique()}")
        print(f"Tệp dữ liệu: {OUTPUT_DATA}")

        print("\nSố dòng theo nhóm ngành:")
        print(df["nhom_nganh_finex"].value_counts().to_string())

        print("\nSố dòng theo loại báo cáo:")
        print(df["loai_bao_cao"].value_counts().to_string())

        print("\nSố dòng theo năm:")
        print(
            df.groupby(["nam_tai_chinh", "tan_suat_bao_cao"])
              .size()
              .to_string()
        )

        print("=" * 80)

    else:
        print(
            "\nKhông có dữ liệu BCTC được thu thập. "
            "Kiểm tra kết nối, mã Yahoo và khả năng truy cập nguồn."
        )

        # Tạo CSV rỗng có đúng cột để giữ cấu trúc đầu ra.
        pd.DataFrame(columns=data_columns).to_csv(
            OUTPUT_DATA,
            index=False,
            encoding="utf-8-sig"
        )

    # =========================================================================
    # 10. XUẤT DANH SÁCH KỲ CHƯA CÓ DỮ LIỆU
    # =========================================================================

    missing_columns = [
        "ma_chung_khoan",
        "chi_so",
        "nhom_nganh_finex",
        "loai_bao_cao",
        "tan_suat_bao_cao",
        "nam_can_kiem_tra",
        "trang_thai",
        "ghi_chu"
    ]

    df_missing = pd.DataFrame(
        missing_records,
        columns=missing_columns
    )

    df_missing.to_csv(
        OUTPUT_MISSING,
        index=False,
        encoding="utf-8-sig"
    )

    # =========================================================================
    # 11. XUẤT LOG LỖI
    # =========================================================================

    error_columns = [
        "ma_chung_khoan",
        "chi_so",
        "loai_bao_cao",
        "tan_suat_bao_cao",
        "nam_yeu_cau",
        "ma_nguon",
        "loi",
        "thoi_gian_thu_thap"
    ]

    df_errors = pd.DataFrame(
        all_errors,
        columns=error_columns
    )

    df_errors.to_csv(
        OUTPUT_ERRORS,
        index=False,
        encoding="utf-8-sig"
    )

    print("\nCÁC TỆP ĐẦU RA")
    print(f"1. Master cổ phiếu: {OUTPUT_UNIVERSE}")
    print(f"2. BCTC lịch sử:   {OUTPUT_DATA}")
    print(f"3. Kỳ thiếu:       {OUTPUT_MISSING}")
    print(f"4. Lỗi thu thập:   {OUTPUT_ERRORS}")


if __name__ == "__main__":
    main()
