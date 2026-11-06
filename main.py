# -*- coding: utf-8 -*-
"""
FINEX VN TERMINAL — PIPELINE THU THẬP & LÀM SẠCH DỮ LIỆU 200 CỔ PHIẾU
Giữ danh sách 200 mã, phân ngành, tên doanh nghiệp và bản đồ dịch từ code gốc.

Đầu ra:
  data/vietnam_stock_database_tong_hop.csv
  data/vietnam_stock.db
Bảng SQLite chính: stock_financials_master (dạng long/tidy)
Bảng phụ: stock_ticker_status, stock_collection_log

Cài đặt:
  pip install -U yfinance pandas requests urllib3
"""

import os
import re
import time
import math
import sqlite3
import logging
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd
import requests
import yfinance as yf
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


# ========================= CẤU HÌNH =========================
DATA_DIR = "data"
CSV_PATH = os.path.join(DATA_DIR, "vietnam_stock_database_tong_hop.csv")
DB_PATH = os.path.join(DATA_DIR, "vietnam_stock.db")
TABLE_NAME = "stock_financials_master"

# Yahoo Finance thường chỉ cung cấp một số năm dữ liệu; có thể chỉnh mốc này.
MIN_YEAR = int(os.getenv("FINEX_MIN_YEAR", "2016"))
MAX_WORKERS = int(os.getenv("FINEX_MAX_WORKERS", "4"))
REQUEST_TIMEOUT = 25
RETRY_PER_SYMBOL = 2

BASE_COLUMNS = [
    "Mã chứng khoán", "Tên doanh nghiệp", "Tên ngành", "Loại báo cáo",
    "Loại kỳ", "Năm", "Ngày kỳ", "Chỉ tiêu tiếng Việt", "Giá trị",
    "Nguồn dữ liệu", "Thời điểm thu thập", "Trạng thái dữ liệu"
]

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("FINEX_PIPELINE")


def create_robust_session():
    """Session có retry/backoff; không tạo session dùng chung giữa nhiều luồng."""
    session = requests.Session()
    retry = Retry(
        total=4, connect=4, read=3, status=4,
        backoff_factor=1.2,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=frozenset(["GET", "HEAD"]),
        raise_on_status=False
    )
    adapter = HTTPAdapter(
        max_retries=retry,
        pool_connections=20,
        pool_maxsize=20
    )
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    session.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/122.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "en-US,en;q=0.9,vi;q=0.8"
    })
    return session


def to_finite_float(value):
    """Chuyển số an toàn; trả None nếu thiếu, không hợp lệ hoặc vô cực."""
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    if not math.isfinite(number):
        return None
    return number


def get_statement(ticker, attribute):
    """Lấy DataFrame báo cáo; xử lý khác biệt phiên bản yfinance."""
    try:
        value = getattr(ticker, attribute, None)
        return value if isinstance(value, pd.DataFrame) and not value.empty else pd.DataFrame()
    except Exception as exc:
        logger.debug("Không đọc được %s: %s", attribute, exc)
        return pd.DataFrame()


def append_metric(records, symbol, metric_key, value, period_type="Real-time",
                  report_type=None, date_str=None, source="Yahoo Finance"):
    """Chỉ ghi giá trị số có thật; không biến dữ liệu thiếu thành số 0."""
    number = to_finite_float(value)
    if number is None:
        return
    company_name, sector_name = get_company_profile(symbol)
    today = datetime.now().strftime("%Y-%m-%d")
    metric_vn = TRANSLATION_MAP.get(metric_key, translate_metric(metric_key))
    if report_type is None:
        report_type = "Chỉ số thị trường, Định giá & Cổ tức"
    if date_str is None:
        date_str = today
    records.append({
        "Mã chứng khoán": symbol,
        "Tên doanh nghiệp": company_name,
        "Tên ngành": sector_name,
        "Loại báo cáo": report_type,
        "Loại kỳ": period_type,
        "Năm": str(date_str)[:4],
        "Ngày kỳ": str(date_str)[:10],
        "Chỉ tiêu tiếng Việt": metric_vn,
        "Giá trị": number,
        "Nguồn dữ liệu": source,
        "Thời điểm thu thập": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "Trạng thái dữ liệu": "OK"
    })


def parse_financial_df(symbol, df, statement_type_raw, period_label, min_year=MIN_YEAR):
    """Chuẩn hóa toàn bộ dòng chỉ tiêu và các kỳ có trong DataFrame gốc."""
    records = []
    if df is None or not isinstance(df, pd.DataFrame) or df.empty:
        return records

    report_type = TRANSLATION_MAP.get(statement_type_raw, statement_type_raw)
    company_name, sector_name = get_company_profile(symbol)

    for col in df.columns:
        try:
            period = pd.to_datetime(col, errors="coerce")
            if pd.isna(period) or period.year < min_year:
                continue
            date_str = period.strftime("%Y-%m-%d")
            for raw_metric, raw_value in df[col].items():
                number = to_finite_float(raw_value)
                if number is None:
                    continue
                raw_name = str(raw_metric).strip()
                if not raw_name or raw_name.lower() in {"nan", "none"}:
                    continue
                records.append({
                    "Mã chứng khoán": symbol,
                    "Tên doanh nghiệp": company_name,
                    "Tên ngành": sector_name,
                    "Loại báo cáo": report_type,
                    "Loại kỳ": period_label,
                    "Năm": str(period.year),
                    "Ngày kỳ": date_str,
                    "Chỉ tiêu tiếng Việt": translate_metric(raw_name),
                    "Giá trị": number,
                    "Nguồn dữ liệu": "Yahoo Finance - Financial Statements",
                    "Thời điểm thu thập": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                    "Trạng thái dữ liệu": "OK"
                })
        except Exception as exc:
            logger.debug("%s | lỗi cột kỳ %s: %s", symbol, col, exc)
    return records


def fetch_market_metrics(symbol, ticker, balance_sheet):
    """Giá, số cổ phiếu, vốn hóa, định giá và cổ tức; không bịa số 0."""
    records = []
    info = {}
    try:
        info = ticker.get_info() or {}
    except Exception:
        try:
            info = ticker.info or {}
        except Exception:
            info = {}

    # Giá: ưu tiên currentPrice/regularMarketPrice; fallback giá đóng cửa gần nhất.
    price = (
        to_finite_float(info.get("currentPrice"))
        or to_finite_float(info.get("regularMarketPrice"))
        or to_finite_float(info.get("previousClose"))
    )
    if not price or price <= 0:
        try:
            hist = ticker.history(period="5d", auto_adjust=False, timeout=REQUEST_TIMEOUT)
            if hist is not None and not hist.empty:
                close_series = pd.to_numeric(hist["Close"], errors="coerce").dropna()
                if not close_series.empty:
                    candidate = to_finite_float(close_series.iloc[-1])
                    if candidate and candidate > 0:
                        price = candidate

        except Exception as exc:
            logger.debug("%s | không lấy được giá lịch sử: %s", symbol, exc)

    shares = to_finite_float(info.get("sharesOutstanding"))
    if not shares or shares <= 0:
        # Chỉ nhận các dòng thực sự biểu thị số cổ phiếu; KHÔNG lấy vốn điều lệ chia tùy tiện.
        if balance_sheet is not None and not balance_sheet.empty:
            aliases = (
                "ordinary shares number",
                "ordinary shares outstanding",
                "shares outstanding",
                "share issued"
            )
            for row in balance_sheet.index:
                row_norm = re.sub(r"[^a-z0-9 ]", " ", str(row).lower()).strip()
                if any(alias in row_norm for alias in aliases):
                    vals = pd.to_numeric(balance_sheet.loc[row], errors="coerce").dropna()
                    vals = vals[vals > 0]
                    if not vals.empty:
                        shares = to_finite_float(vals.iloc[0])
                        break

    market_cap = to_finite_float(info.get("marketCap"))
    if (not market_cap or market_cap <= 0) and price and shares and shares > 0:
        market_cap = price * shares

    # yfinance dividendYield thường ở dạng tỷ lệ thập phân (0.04 = 4%).
    dividend_yield = to_finite_float(info.get("dividendYield"))
    if dividend_yield is not None:
        dividend_yield *= 100.0

    metric_values = [
        ("Current Price", price),
        ("Shares Outstanding", shares),
        ("Market Capitalization", market_cap),
        ("Trailing EPS", info.get("trailingEps")),
        ("Forward EPS", info.get("forwardEps")),
        ("Dividend Yield", dividend_yield),
        ("Dividend Rate", info.get("dividendRate")),
        ("Trailing P/E", info.get("trailingPE")),
        ("Forward P/E", info.get("forwardPE")),
        ("Price To Book", info.get("priceToBook")),
        ("Book Value", info.get("bookValue")),
        ("Return On Equity", info.get("returnOnEquity")),
        ("Return On Assets", info.get("returnOnAssets")),
        ("Profit Margins", info.get("profitMargins")),
        ("Gross Margins", info.get("grossMargins")),
        ("Payout Ratio", (
            to_finite_float(info.get("payoutRatio")) * 100
            if to_finite_float(info.get("payoutRatio")) is not None else None
        ))
    ]

    today = datetime.now().strftime("%Y-%m-%d")
    for key, value in metric_values:
        append_metric(records, symbol, key, value, date_str=today)

    return records


def fetch_historical_dividends(symbol, ticker, min_year=MIN_YEAR):
    """Lưu từng sự kiện cổ tức tiền mặt theo ngày; không cộng gộp sai kỳ."""
    records = []
    try:
        dividends = ticker.dividends
        if dividends is None or dividends.empty:
            return records
        for date_index, value in dividends.items():
            date = pd.to_datetime(date_index, errors="coerce")
            number = to_finite_float(value)
            if pd.isna(date) or date.year < min_year or number is None or number <= 0:
                continue
            append_metric(
                records, symbol, "Historical Dividend Cash", number,
                period_type="Sự kiện cổ tức",
                date_str=date.strftime("%Y-%m-%d"),
                source="Yahoo Finance - Dividend History"
            )
    except Exception as exc:
        logger.debug("%s | lỗi lịch sử cổ tức: %s", symbol, exc)
    return records


def process_single_ticker(symbol, category):
    """Thử các hậu tố sàn; chọn nguồn có dữ liệu tốt nhất, không ghi dữ liệu giả."""
    suffixes = [".VN", ".HN", ".UPCOM", ".HA", ".HM", ""]
    best_records = []
    best_status = {
        "Mã chứng khoán": symbol,
        "Trạng thái": "FAILED",
        "Mã Yahoo": None,
        "Số bản ghi": 0,
        "Thông báo": "Không lấy được dữ liệu"
    }

    for suffix in suffixes:
        yahoo_symbol = f"{symbol}{suffix}"
        for attempt in range(RETRY_PER_SYMBOL):
            try:
                ticker = yf.Ticker(yahoo_symbol, session=create_robust_session())

                bs_a = get_statement(ticker, "balance_sheet")
                bs_q = get_statement(ticker, "quarterly_balance_sheet")
                is_a = get_statement(ticker, "financials")
                is_q = get_statement(ticker, "quarterly_financials")
                cf_a = get_statement(ticker, "cashflow")
                cf_q = get_statement(ticker, "quarterly_cashflow")

                candidate = []
                candidate += parse_financial_df(symbol, bs_a, "Balance_Sheet", "Năm")
                candidate += parse_financial_df(symbol, bs_q, "Balance_Sheet", "Quý")
                candidate += parse_financial_df(symbol, is_a, "Income_Statement", "Năm")
                candidate += parse_financial_df(symbol, is_q, "Income_Statement", "Quý")
                candidate += parse_financial_df(symbol, cf_a, "Cash_Flow", "Năm")
                candidate += parse_financial_df(symbol, cf_q, "Cash_Flow", "Quý")

                # Thử lấy thông tin thị trường kể cả khi nhà cung cấp không có BCTC.
                candidate += fetch_market_metrics(
                    symbol, ticker, bs_a if not bs_a.empty else bs_q
                )
                candidate += fetch_historical_dividends(symbol, ticker)

                score = len(candidate)
                if score > len(best_records):
                    best_records = candidate
                    best_status = {
                        "Mã chứng khoán": symbol,
                        "Trạng thái": "SUCCESS" if score else "NO_DATA",
                        "Mã Yahoo": yahoo_symbol,
                        "Số bản ghi": score,
                        "Thông báo": "Đã thu thập dữ liệu"
                    }

                # Nếu có BCTC hoặc dữ liệu thị trường thì dừng thử hậu tố.
                if score > 0:
                    return best_records, best_status

            except Exception as exc:
                best_status["Thông báo"] = f"{type(exc).__name__}: {str(exc)[:250]}"
                logger.warning("%s (%s) lần %s lỗi: %s",
                               symbol, yahoo_symbol, attempt + 1, exc)
                time.sleep(1.0 * (attempt + 1))

    return best_records, best_status


def clean_master_data(df):
    """Làm sạch có kiểm soát: giữ số âm hợp lệ, không fillna(0)."""
    if df is None or df.empty:
        return pd.DataFrame(columns=BASE_COLUMNS)

    result = df.copy()
    for col in BASE_COLUMNS:
        if col not in result.columns:
            result[col] = None

    result["Mã chứng khoán"] = (
        result["Mã chứng khoán"].astype("string").str.strip().str.upper()
    )
    text_cols = [
        "Tên doanh nghiệp", "Tên ngành", "Loại báo cáo", "Loại kỳ",
        "Ngày kỳ", "Chỉ tiêu tiếng Việt", "Nguồn dữ liệu", "Trạng thái dữ liệu"
    ]
    for col in text_cols:
        result[col] = result[col].astype("string").str.strip()

    result["Giá trị"] = pd.to_numeric(result["Giá trị"], errors="coerce")
    result["Năm"] = result["Năm"].astype("string").str.extract(r"(\d{4})", expand=False)

    # Loại bản ghi không có khóa hoặc giá trị số; không loại giá trị âm.
    result = result.dropna(subset=[
        "Mã chứng khoán", "Loại báo cáo", "Loại kỳ",
        "Ngày kỳ", "Chỉ tiêu tiếng Việt", "Giá trị"
    ])
    result = result[result["Mã chứng khoán"].str.fullmatch(r"[A-Z0-9]{2,6}", na=False)]
    result = result[result["Giá trị"].map(lambda x: math.isfinite(float(x)))]
    result = result[result["Chỉ tiêu tiếng Việt"].ne("")]
    result = result.drop_duplicates(
        subset=[
            "Mã chứng khoán", "Loại báo cáo", "Loại kỳ",
            "Ngày kỳ", "Chỉ tiêu tiếng Việt"
        ],
        keep="last"
    )
    result = result.sort_values(
        ["Mã chứng khoán", "Loại báo cáo", "Loại kỳ", "Ngày kỳ", "Chỉ tiêu tiếng Việt"],
        ascending=[True, True, True, False, True],
        kind="stable"
    ).reset_index(drop=True)

    return result[BASE_COLUMNS]


def save_to_database(df, statuses, db_path=DB_PATH):
    """Ghi SQLite theo transaction; tạo index và bảng trạng thái chạy."""
    os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
    conn = sqlite3.connect(db_path, timeout=60)
    try:
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        conn.execute("PRAGMA foreign_keys=ON;")
        conn.execute("BEGIN")
        df.to_sql(TABLE_NAME, conn, if_exists="replace", index=False)
        pd.DataFrame(statuses).to_sql(
            "stock_ticker_status", conn, if_exists="replace", index=False
        )
        conn.execute("""
            CREATE TABLE IF NOT EXISTS stock_collection_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                collected_at TEXT NOT NULL,
                total_tickers INTEGER,
                success_tickers INTEGER,
                failed_tickers INTEGER,
                total_records INTEGER
            )
        """)
        success = sum(1 for x in statuses if x.get("Trạng thái") == "SUCCESS")
        failed = len(statuses) - success
        conn.execute(
            """INSERT INTO stock_collection_log
               (collected_at,total_tickers,success_tickers,failed_tickers,total_records)
               VALUES (?,?,?,?,?)""",
            (datetime.now(timezone.utc).isoformat(timespec="seconds"),
             len(statuses), success, failed, len(df))
        )
        conn.execute(
            f'CREATE INDEX IF NOT EXISTS idx_fin_symbol ON "{TABLE_NAME}" ("Mã chứng khoán")'
        )
        conn.execute(
            f'CREATE INDEX IF NOT EXISTS idx_fin_report ON "{TABLE_NAME}" ("Loại báo cáo")'
        )
        conn.execute(
            f'CREATE INDEX IF NOT EXISTS idx_fin_period ON "{TABLE_NAME}" ("Năm","Ngày kỳ")'
        )
        conn.execute(
            f'CREATE INDEX IF NOT EXISTS idx_fin_metric ON "{TABLE_NAME}" ("Chỉ tiêu tiếng Việt")'
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def main():
    os.makedirs(DATA_DIR, exist_ok=True)
    ticker_market_map = load_200_master_tickers()
    symbols = list(ticker_market_map.keys())
    all_records = []
    statuses = []

    logger.info("FINEX bắt đầu thu thập %s mã; số luồng=%s",
                len(symbols), MAX_WORKERS)

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {
            executor.submit(process_single_ticker, symbol, category): symbol
            for symbol, category in ticker_market_map.items()
        }
        completed = 0
        for future in as_completed(futures):
            symbol = futures[future]
            completed += 1
            try:
                records, status = future.result()
                all_records.extend(records)
                statuses.append(status)
                logger.info("[%s/%s] %s: %s bản ghi | %s",
                            completed, len(symbols), symbol,
                            len(records), status.get("Trạng thái"))
            except Exception as exc:
                statuses.append({
                    "Mã chứng khoán": symbol,
                    "Trạng thái": "FAILED",
                    "Mã Yahoo": None,
                    "Số bản ghi": 0,
                    "Thông báo": str(exc)[:250]
                })
                logger.exception("%s: lỗi ngoài dự kiến", symbol)

    df_master = clean_master_data(pd.DataFrame(all_records, columns=BASE_COLUMNS))
    df_master.to_csv(CSV_PATH, index=False, encoding="utf-8-sig")
    save_to_database(df_master, statuses, DB_PATH)

    success_count = sum(1 for x in statuses if x.get("Trạng thái") == "SUCCESS")
    failed = [x["Mã chứng khoán"] for x in statuses if x.get("Trạng thái") != "SUCCESS"]

    print("\\n" + "=" * 68)
    print("FINEX VN TERMINAL — BÁO CÁO THU THẬP DỮ LIỆU")
    print(f"Tổng mã trong danh sách: {len(symbols)}")
    print(f"Mã có dữ liệu: {success_count}")
    print(f"Mã chưa lấy được dữ liệu: {len(failed)}")
    print(f"Tổng bản ghi sạch: {len(df_master):,}")
    print(f"CSV: {CSV_PATH}")
    print(f"SQLite: {DB_PATH}")
    print("Các báo cáo: Bảng cân đối kế toán | Kết quả kinh doanh | Lưu chuyển tiền tệ")
    print("Dữ liệu thị trường: Giá | Số cổ phiếu | Vốn hóa | Định giá | Cổ tức")
    if failed:
        print("Mã cần kiểm tra:", ", ".join(failed))
    print("=" * 68)


if __name__ == "__main__":
    main()


def load_200_master_tickers():
    """Danh sách chính thức toàn diện 200 mã cổ phiếu chất lượng cao (172 mã cũ + 28 mã mới bổ sung)"""
    raw_tickers = [
        # 172 mã trước đó
        "ABB", "ACB", "ACV", "AIG", "ANV",
        "BAF", "BCM", "BID", "BMP", "BSI", "BSR", "BVH", "BVS", "BWE",
        "CAP", "CEO", "CII", "CMG", "CTD", "CTG", "CTR", "CTS",
        "DBC", "DCM", "DGW", "DIG", "DNH", "DP3", "DPM", "DSE", "DTD", "DVN", "DXG", "DXP",
        "EIB", "EVF",
        "FOX", "FPT", "FRT", "FTS",
        "GAS", "GEE", "GEX", "GMD", "GVR",
        "HAG", "HCM", "HDB", "HDG", "HND", "HHV", "HPG", "HSG", "HT1", "HUT",
        "IDC", "IDP",
        "KBC", "KDC", "KDH",
        "L14", "L18", "LAS", "LHC", "LPB",
        "MBB", "MBS", "MCH", "MSB", "MSN", "MSR", "MVN", "MWG",
        "NAB", "NBC", "NDN", "NKG", "NLG", "NT2", "NTP", "NVL",
        "OCB", "OIL",
        "PAN", "PC1", "PDR", "PHR", "PLC", "PLX", "PNJ", "POW", "PSD", "PVB", "PVC", "PVD", "PVS", "PVT", "PVI",
        "QNS", "QTP",
        "REE",
        "SAB", "SAS", "SBT", "SHB", "SHS", "SIP", "SJS", "SLS", "SNZ", "SSB", "SSI", "STB",
        "TAL", "TBD", "TCB", "TCH", "TCX", "TDM", "TID", "TIG", "TNG", "TOS", "TPB", "TVD",
        "VCB", "VC3", "VCG", "VCI", "VCK", "VCS", "VEA", "VFS", "VGC", "VGI", "VGP", "VGR", "VHC", "VHM", "VIB", "VIC", "VIX", "VJC", "VND", "VNM", "VPB", "VPI", "VPL", "VPX", "VRE", "VSC", "VTP",
        "PRE", "HCC", "L40", "KDM", "HVT", "VTZ", "GLT", "VGS", "PCH", 
        "CAR", "HGM", "KSV", "THD", "KSF", "SCG", "CLM", "TMB", "SAF", "NET", "DHT",
        
        # 28 mã mới bổ sung chính thức
        "DGC", "SZC", "HVN", "BAB", "AGR", "ICT", "TLH", "BMI", "PET", "LSS", 
        "HDC", "IJC", "TDC", "CTI", "SJD", "TMP", "SBA", "VSH", "TTA", "TV2", 
        "VCP", "BFC", "DDV", "VGT", "SGP", "DPR", "DHC", "TCM"
    ]
    
    market_map = {}
    for t in raw_tickers:
        if t.strip(): 
            market_map[t.strip().upper()] = "VIETNAM_MARKET"
    return market_map



def get_company_profile(symbol):
    """Phân nhóm ngành chuẩn xác và tra cứu tên doanh nghiệp cho 200 mã"""
    tech_list = ["FPT", "CMG", "VTP", "ICT", "ELC", "CTR", "VGI", "VNZ", "FOX"]
    bank_list = ["VCB", "BID", "TCB", "MBB", "ACB", "CTG", "VPB", "STB", "SHB", "HDB", "LPB", "MSB", "OCB", "NAB", "SSB", "EIB", "TPB", "ABB", "BAB"]
    securities_list = ["SSI", "VCI", "HCM", "VND", "SHS", "MBS", "FTS", "BSI", "CTS", "VIX", "VDS", "ORS", "AGR", "VFS", "DSE", "BVS", "EVF", "IPA", "EVS", "HBS", "PSI", "WSS"]
    realestate_list = ["VIC", "VHM", "VRE", "BCM", "KBC", "IDC", "SIP", "SZC", "KDH", "NLG", "DXG", "PDR", "DIG", "CEO", "HDC", "NVL", "TCH", "VC3", "VPI", "SJS", "L14", "L18", "NDN", "THD", "KSF", "IJC", "TDC", "CTI"]
    retail_list = ["MWG", "FRT", "DGW", "PNJ", "PET", "DMX"]
    oil_gas_list = ["GAS", "PLX", "PVD", "PVS", "PVT", "PVB", "BSR", "OIL", "POW", "DTK", "PGV", "NT2", "PGI", "PLC", "PSD", "PVC", "SJD", "TMP", "SBA", "VSH", "TTA", "TV2", "VCP"]
    steel_materials = ["HPG", "HSG", "NKG", "GDA", "BMP", "NTP", "AAA", "DGC", "CSV", "LAS", "PHR", "DPM", "DCM", "BFC", "HPA", "VGS", "HT1", "LHC", "HGM", "KSV", "TLH", "DDV", "BFC", "DPR", "DHC"]

    if symbol in tech_list: sector = "Công nghệ thông tin"
    elif symbol in bank_list: sector = "Ngân hàng"
    elif symbol in securities_list: sector = "Chứng khoán"
    elif symbol in realestate_list: sector = "Bất động sản & Xây dựng"
    elif symbol in retail_list: sector = "Bán lẻ & Dịch vụ tiêu dùng"
    elif symbol in oil_gas_list: sector = "Dầu khí, Điện & Năng lượng"
    elif symbol in steel_materials: sector = "Vật liệu xây dựng, Thép & Hóa chất"
    else: sector = "Công nghiệp, Sản xuất & Hàng tiêu dùng"

    company_names = {
        "DGC": "Công ty Cổ phần Tập đoàn Hóa chất Đức Giang", "SZC": "Công ty Cổ phần Sonadezi Châu Đức",
        "HVN": "Tổng Công ty Hàng không Việt Nam - CTCP (Vietnam Airlines)", "BAB": "Ngân hàng TMCP Bắc Á",
        "AGR": "Công ty Cổ phần Chứng khoán Agribank", "ICT": "Công ty Cổ phần Viễn thông - Giống cây trồng",
        "TLH": "Công ty Cổ phần Tập đoàn Thép Tiến Lên", "BMI": "Tổng Công ty Cổ phần Bảo hiểm Bảo Minh",
        "PET": "Tổng Công ty cổ phần Dịch vụ Tổng hợp Dầu khí", "LSS": "Công ty Cổ phần Mía đường Lam Sơn",
        "HDC": "Công ty Cổ phần Phát triển Nhà Bà Rịa - Vũng Tàu", "IJC": "Công ty Cổ phần Phát triển Hạ tầng Kỹ thuật",
        "TDC": "Công ty Cổ phần Kinh doanh và Phát triển Bình Dương", "CTI": "Công ty Cổ phần Đầu tư Phát triển C&T",
        "SJD": "Công ty Cổ phần Thủy điện Cần Đơn", "TMP": "Công ty Cổ phần Thủy điện Thác Mơ",
        "SBA": "Công ty Cổ phần Thủy điện Sông Ba Hạ", "VSH": "Công ty Cổ phần Thủy điện Vĩnh Sơn - Sông Hinh",
        "TTA": "Công ty Cổ phần Đầu tư Trường Thành Việt Nam", "TV2": "Công ty Cổ phần Tư vấn Xây dựng Điện 2",
        "VCP": "Công ty Cổ phần Xây dựng điện VNECO 3", "BFC": "Công ty Cổ phần Phân bón Bình Điền",
        "DDV": "Công ty Cổ phần DAP - VINACHEM", "VGT": "Tập đoàn Dệt May Việt Nam - CTCP",
        "SGP": "Tổng Công ty Cảng Sài Gòn - CTCP", "DPR": "Công ty Cổ phần Cao su Đồng Phú",
        "DHC": "Công ty Cổ phần Đông Hải Bến Tre", "TCM": "Công ty Cổ phần Dệt mão Thành Công",
        
        "ABB": "Ngân hàng TMCP An Bình", "ACB": "Ngân hàng TMCP Á Châu", "ACV": "Tổng công ty Cảng hàng không Việt Nam",
        "AIG": "Công ty Cổ phần Tập đoàn Hóa chất Hùng Phát", "ANV": "Công ty Cổ phần Nam Việt", "BAF": "Công ty Cổ phần Nông nghiệp BAF Việt Nam",
        "BCM": "Tổng công ty Đầu tư và Phát triển Công nghiệp - CTCP", "BID": "Ngân hàng TMCP Đầu tư và Phát triển Việt Nam",
        "BMP": "Công ty Cổ phần Nhựa Bình Minh", "BSI": "Công ty Cổ phần Chứng khoán Ngân hàng Đầu tư và Phát triển Việt Nam",
        "BSR": "Công ty Cổ phần Lọc hóa dầu Bình Sơn", "BVH": "Tập đoàn Bảo Việt", "BVS": "Công ty Cổ phần Chứng khoán Bảo Việt",
        "BWE": "Công ty Cổ phần Nước - Môi trường Bình Dương", "CAP": "Công ty Cổ phần Lâm nông sản thực phẩm Yên Bái",
        "CEO": "Công ty Cổ phần Tập đoàn C.E.O", "CII": "Công ty Cổ phần Đầu tư Hạ tầng Kỹ thuật Thành phố Hồ Chí Minh",
        "CMG": "Công ty Cổ phần Tập đoàn Công nghệ CMC", "CTD": "Công ty Cổ phần Xây dựng Coteccons",
        "CTG": "Ngân hàng TMCP Công Thương Việt Nam", "CTR": "Tổng Công ty Cổ phần Công trình Viettel",
        "CTS": "Công ty Cổ phần Chứng khoán Ngân hàng Công Thương Việt Nam", "DBC": "Công ty Cổ phần Tập đoàn Dabaco Việt Nam",
        "DCM": "Công ty Cổ phần Phân bón Dầu khí Cà Mau", "DGW": "Công ty Cổ phần Thế giới Số", "DIG": "Tổng công ty Cổ phần Đầu tư Phát triển Xây dựng",
        "DNH": "Công ty Cổ phần Thủy điện Đa Nhim - Hàm Thuận - Đa Mi", "DP3": "Công ty Cổ phần Dược phẩm Trung ương 3",
        "DPM": "Tổng công ty Phân bón và Hóa chất Dầu khí - CTCP", "DSE": "Công ty Cổ phần Chứng khoán DNSE",
        "DTD": "Công ty Cổ phần Đầu tư Phát triển Thành Đạt", "DVN": "Tổng Công ty Dược Việt Nam - CTCP",
        "DXG": "Công ty Cổ phần Tập đoàn Đất Xanh", "DXP": "Công ty Cổ phần Cảng Đình Vũ", "EIB": "Ngân hàng TMCP Xuất Nhập khẩu Việt Nam",
        "EVF": "Công ty Cổ phần Tài chính Điện lực", "FOX": "Công ty Cổ phần Viễn thông FPT", "FPT": "Công ty Cổ phần FPT",
        "FRT": "Công ty Cổ phần Bán lẻ Kỹ thuật Số FPT", "FTS": "Công ty Cổ phần Chứng khoán FPT", "GAS": "Tổng Công ty Khí Việt Nam - CTCP",
        "GEE": "Công ty Cổ phần Thiết bị Điện Gelex", "GEX": "Công ty Cổ phần Tập đoàn Gelex", "GMD": "Công ty Cổ phần Gemadept",
        "GVR": "Tập đoàn Công nghiệp Cao su Việt Nam - CTCP", "HAG": "Công ty Cổ phần Hoàng Anh Gia Lai", "HCM": "Công ty Cổ phần Chứng khoán Thành phố Hồ Chí Minh",
        "HDB": "Ngân hàng TMCP Phát triển Thành phố Hồ Chí Minh", "HDG": "Công ty Cổ phần Tập đoàn Hà Đô", "HND": "Công ty Cổ phần Nhiệt điện Hải Phòng",
        "HHV": "Công ty Cổ phần Đầu tư Hạ tầng giao thông Đèo Cả", "HPG": "Công ty Cổ phần Tập đoàn Hòa Phát",
        "HSG": "Công ty Cổ phần Tập đoàn Hoa Sen", "HT1": "Công ty Cổ phần Xi măng Vicem Hà Tiên", "HUT": "Công ty Cổ phần Tasco",
        "IDC": "Tổng công ty IDICO - CTCP", "IDP": "Công ty Cổ phần Sữa Quốc tế IDP", "KBC": "Tổng Công ty Phát triển Đô thị Kinh Bắc - CTCP",
        "KDC": "Công ty Cổ phần Tập đoàn Kido", "KDH": "Công ty Cổ phần Đầu tư và Kinh doanh Nhà Khang Điền", "L14": "Công ty Cổ phần Licogi 14",
        "L18": "Công ty Cổ phần Đầu tư và Xây dựng số 18", "LAS": "Công ty Cổ phần Supe Phốt phát và Hóa chất Lâm Thao",
        "LHC": "Công ty Cổ phần Đầu tư và Xây dựng Lắp máy IDICO", "LPB": "Ngân hàng TMCP Lộc Phát Việt Nam",
        "MBB": "Ngân hàng TMCP Quân đội", "MBS": "Công ty Cổ phần Chứng khoán MB", "MCH": "Công ty Cổ phần Hàng tiêu dùng Masan",
        "MSB": "Ngân hàng TMCP Hàng Hải Việt Nam", "MSN": "Công ty Cổ phần Tập đoàn Masan", "MSR": "Công ty Cổ phần Masan High-Tech Materials",
        "MVN": "Tổng Công ty Hàng hải Việt Nam - CTCP", "MWG": "Công ty Cổ phần Đầu tư Thế Giới Di Động", "NAB": "Ngân hàng TMCP Nam Á",
        "NBC": "Công ty Cổ phần Than Núi Béo - Vinacomin", "NDN": "Công ty Cổ phần Đầu tư Phát triển Nhà Đà Nẵng",
        "NKG": "Công ty Cổ phần Thép Nam Kim", "NLG": "Công ty Cổ phần Đầu tư Nam Long", "NT2": "Công ty Cổ phần Điện lực Dầu khí Nhơn Trạch 2",
        "NTP": "Công ty Cổ phần Nhựa Thiếu niên Tiền Phong", "NVL": "Công ty Cổ phần Tập đoàn Đầu tư Địa đạo No Va",
        "OCB": "Ngân hàng TMCP Phương Đông", "OIL": "Tổng Công ty Dầu Việt Nam - CTCP", "PAN": "Công ty Cổ phần Tập đoàn PAN",
        "PC1": "Công ty Cổ phần Tập đoàn PC1", "PDR": "Công ty Cổ phần Phát triển Bất động sản Phát Đạt",
        "PHR": "Công ty Cổ phần Cao su Phước Hòa", "PLC": "Tổng Công ty Hóa dầu Petrolimex - CTCP", "PLX": "Tập đoàn Xăng dầu Việt Nam",
        "PNJ": "Công ty Cổ phần Vàng bạc Đá quý Phú Nhuận", "POW": "Tổng Công ty Điện lực Dầu khí Việt Nam - CTCP",
        "PSD": "Công ty Cổ phần Dịch vụ Tổng hợp Dầu khí", "PVB": "Công ty Cổ phần bọc ống Dầu khí Việt Nam",
        "PVC": "Tổng Công ty Hóa chất và Dung dịch Khoan Dầu khí - CTCP", "PVD": "Tổng Công ty Cổ phần Khoan và Dịch vụ Khoan Dầu khí",
        "PVS": "Tổng công ty Cổ phần Dịch vụ Kỹ thuật Dầu khí Việt Nam", "PVT": "Tổng Công ty Cổ phần Vận tải Dầu khí",
        "PVI": "Công ty Cổ phần PVI", "QNS": "Công ty Cổ phần Đường Quảng Ngãi", "QTP": "Công ty Cổ phần Nhiệt điện Quảng Ninh",
        "REE": "Công ty Cổ phần Cơ Điện Lạnh", "SAB": "Tổng công ty CP Bia - Rượu - Nước giải khát Sài Gòn",
        "SAS": "Công ty Cổ phần Dịch vụ Hàng không Sân bay Tân Sơn Nhất", "SBT": "Công ty Cổ phần Thành Thành Công - Biên Hòa",
        "SHB": "Ngân hàng TMCP Sài Gòn - Hà Nội", "SHS": "Công ty Cổ phần Chứng khoán Sài Gòn - Hà Nội",
        "SIP": "Công ty Cổ phần Đầu tư Sài Gòn VRG", "SJS": "Công ty Cổ phần Đầu tư Phát triển Đô thị và Khu công nghiệp Sông Đà",
        "SLS": "Công ty Cổ phần Mía đường Sơn La", "SNZ": "Tổng Công ty Sonadezi - CTCP", "SSB": "Ngân hàng TMCP Đông Nam Á",
        "SSI": "Công ty Cổ phần Chứng khoán SSI", "STB": "Ngân hàng TMCP Sài Gòn Thương Tín", "TAL": "Công ty Cổ phần Đầu tư Bất động sản Taseco",
        "TBD": "Công ty Cổ phần Chế tạo Thiết bị Điện Đông Anh", "TCB": "Ngân hàng TMCP Kỹ Thương Việt Nam",
        "TCH": "Công ty Cổ phần Đầu tư Dịch vụ Tài chính Hoàng Huy", "TCX": "Công ty Cổ phần Công nghiệp Tàu thủy",
        "TDM": "Công ty Cổ phần Nước Thủ Dầu Một", "TID": "Tổng Công ty Đầu tư Phát triển Hạ tầng Urban", "TIG": "Công ty Cổ phần Tập đoàn Đầu tư Thăng Long",
        "TNG": "Công ty Cổ phần Đầu tư và Thương mại TNG", "TOS": "Công ty Cổ phần Dịch vụ biển Tân Cảng", "TPB": "Ngân hàng TMCP Tiên Phong",
        "TVD": "Công ty Cổ phần Than Vàng Danh - Vinacomin", "VCB": "Ngân hàng TMCP Ngoại thương Việt Nam", "VC3": "Công ty Cổ phần Tập đoàn Nam Cường",
        "VCG": "Tổng công ty Cổ phần Xuất nhập khẩu và Xây dựng Việt Nam", "VCI": "Công ty Cổ phần Chứng khoán Vietcap",
        "VCK": "Công ty Cổ phần Chứng khoán Vina", "VCS": "Công ty Cổ phần Vicosstone", "VEA": "Tổng công ty Máy động lực và máy nông nghiệp Việt Nam - CTCP",
        "VFS": "Công ty Cổ phần Chứng khoất Nhất Việt", "VGC": "Tổng Công ty Viglacera - CTCP", "VGI": "Tổng Công ty Cổ phần Đầu tư Quốc tế Viettel",
        "VGP": "Công ty Cổ phần Cảng Cần Giuộc", "VGR": "Công ty Cổ phần Vận tải và Xếp dỡ Hải An", "VHC": "Công ty Cổ phần Vĩnh Hoàn",
        "VHM": "Công ty Cổ phần Vinhomes", "VIB": "Ngân hàng TMCP Quốc tế Việt Nam", "VIC": "Tập đoàn Vingroup - CTCP",
        "VIX": "Công ty Cổ phần Chứng khoán VIX", "VJC": "Công ty Cổ phần Hàng không VietJet", "VND": "Công ty Cổ phần Chứng khoán VNDIRECT",
        "VNM": "Công ty Cổ phần Sữa Việt Nam", "VPB": "Ngân hàng TMCP Việt Nam Thịnh Vượng", "VPI": "Công ty Cổ phần Đầu tư Văn Phú - Invest",
        "VPL": "Công ty Cổ phần Vinpearl", "VPX": "Công ty Cổ phần Xây dựng Vận tải Phát Xá", "VRE": "Công ty Cổ phần Vincom Retail",
        "VSC": "Công ty Cổ phần Container Việt Nam", "VTP": "Tổng Công ty Cổ phần Bưu chính Viettel",
        "HGM": "Công ty Cổ phần Cơ khí và Khoáng sản Hà Giang", "PRE": "Tổng công ty cổ phần Tái bảo hiểm PVI",
        "HCC": "Công ty Cổ phần Bê tông Hòa Cầm - Intimex", "L40": "Công ty Cổ phần Licogi 40",
        "KDM": "Công ty Cổ phần ĐT&PT Dương Minh", "HVT": "Công ty Cổ phần Hóa chất Việt Trì",
        "VTZ": "Công ty Cổ phần Thương mại và Đầu tư Vạn Tường", "GLT": "Công ty Cổ phần Kỹ thuật Điện chiếu sáng G.L.T",
        "VGS": "Công ty Cổ phần ống thép Việt Đức VG PIPE", "PCH": "Công ty Cổ phần Thạch cao Cần Thơ",
        "CAR": "Công ty Cổ phần Tập đoàn Đầu tư Địa ốc No Va", "KSV": "Tổng công ty Khoáng sản TKV - CTCP",
        "THD": "Công ty Cổ phần Tập đoàn ThaiHoldings", "KSF": "Công ty Cổ phần Tập đoàn Sunshine Homes",
        "SCG": "Công ty Cổ phần Xây dựng Sông Đà 1.01", "CLM": "Công ty Cổ phần Than Cọc Sáu - Vinacomin",
        "TMB": "Công ty Cổ phần Kinh doanh Than miền Nam - Vinacomin", "SAF": "Công ty Cổ phần lương thực thực phẩm Safoco",
        "NET": "Công ty Cổ phần Bột giặt Net", "DHT": "Công ty Cổ phần Dược phẩm Hà Tây"
    }
    return company_names.get(symbol, f"Công ty Cổ phần {symbol}"), sector



TRANSLATION_MAP = {
    'Balance_Sheet': 'Bảng cân đối kế toán',
    'Income_Statement': 'Báo cáo kết quả kinh doanh',
    'Cash_Flow': 'Báo cáo lưu chuyển tiền tệ',
    'Market_Metrics': 'Chỉ số thị trường, Định giá & Cổ tức',

    'Ordinary Shares Number': 'Số lượng cổ phiếu phổ thông', 'Share Issued': 'Cổ phiếu đã phát hành',
    'Total Assets': 'Tổng tài sản', 'Current Assets': 'Tài sản ngắn hạn',
    'Cash And Cash Equivalents': 'Tiền và các khoản tương đương tiền', 'Cash Financial': 'Tiền và đầu tư tài chính ngắn hạn',
    'Cash Equivalents': 'Các khoản tương đương tiền', 'Cash': 'Tiền mặt',
    'Other Short Term Investments': 'Đầu tư tài chính ngắn hạn khác', 'Receivables': 'Các khoản phải thu',
    'Accounts Receivable': 'Phải thu ngắn hạn khách hàng', 'Allowance For Doubtful Accounts Receivable': 'Dự phòng phải thu ngắn hạn khó đòi',
    'Due From Related Parties Current': 'Phải thu các bên liên quan ngắn hạn', 'Other Receivables': 'Các khoản phải thu ngắn hạn khác',
    'Inventory': 'Hàng tồn kho', 'Raw Materials': 'Nguyên liệu, vật liệu tồn kho',
    'Work In Process': 'Chi phí sản xuất kinh doanh dở dang', 'Finished Goods': 'Thành phẩm tồn kho',
    'Prepaid Assets': 'Chi phí trả trước ngắn hạn', 'Restricted Cash': 'Tiền bị hạn chế',
    'Total Non Current Assets': 'Tổng tài sản dài hạn', 'Net PPE': 'Tài sản cố định thuần',
    'Gross PPE': 'Nguyên giá tài sản cố định', 'Accumulated Depreciation': 'Hao mòn lũy kế tài sản cố định',
    'Machinery Furniture Equipment': 'Máy móc, thiết bị và phương tiện vận tải', 'Land And Improvements': 'Đất đai và cải tạo đất',
    'Properties': 'Bất động sản', 'Leases': 'Tài sản quyền sử dụng đất và thuê tài chính',
    'Construction In Progress': 'Xây dựng cơ bản dở dang', 'Goodwill And Other Intangible Assets': 'Lợi thế thương mại và tài sản vô hình',
    'Goodwill': 'Lợi thế thương mại', 'Other Intangible Assets': 'Tài sản cố định vô hình khác',
    'Investments And Advances': 'Đầu tư tài chính dài hạn', 'Investment in Financial Assets': 'Đầu tư tài chính dài hạn',
    'Held To Maturity Securities': 'Chứng khoán giữ đến ngày đáo hạn', 'Available For Sale Securities': 'Chứng khoán sẵn sàng để bán',
    'Investment Properties': 'Bất động sản đầu tư', 'Other Non Current Assets': 'Tài sản dài hạn khác',
    'Deferred Tax Assets': 'Tài sản thuế thu nhập hoãn lại',
    
    'Current Liabilities': 'Nợ ngắn hạn', 'Current Debt': 'Vay và nợ thuê tài chính ngắn hạn',
    'Payables': 'Các khoản phải trả', 'Accounts Payable': 'Phải trả người bán ngắn hạn',
    'Taxes Payable': 'Thuế và các khoản phải nộp nhà nước', 'Accrued Liabilities': 'Chi phí phải trả ngắn hạn',
    'Pension and Other Post-Retirement Benefit Plans Current': 'Quỹ phúc lợi nhân viên ngắn hạn',
    'Other Current Liabilities': 'Phải trả, phải nộp ngắn hạn khác', 'Total Liabilities Net Minority Interest': 'Tổng nợ phải trả',
    'Total Non Current Liabilities Net Minority Interest': 'Nợ dài hạn', 'Long Term Debt': 'Vay và nợ thuê tài chính dài hạn',
    'Total Debt': 'Tổng nợ vay', 'Net Debt': 'Nợ vay ròng', 'Deferred Revenue': 'Doanh thu chưa thực hiện dài hạn',
    'Deferred Tax Liabilities': 'Thuế thu nhập hoãn lại phải trả', 'Other Non Current Liabilities': 'Nợ dài hạn khác',
    
    'Stockholders Equity': 'Vốn chủ sở hữu', 'Capital Stock': 'Vốn góp chủ sở hữu', 'Common Stock': 'Cổ phiếu phổ thông',
    'Retained Earnings': 'Lợi nhuận sau thuế chưa phân phối', 'Additional Paid In Capital': 'Thặng dư vốn cổ phần',
    'Gains Losses Not Affecting Retained Earnings': 'Chênh lệch đánh giá lại tài sản và chênh lệch tỷ giá',
    'Minority Interest': 'Lợi ích cổ đông không kiểm soát', 'Total Equity Gross Minority Interest': 'Tổng vốn chủ sở hữu gồm cổ đông không kiểm soát',
    'Working Capital': 'Vốn lưu động ròng',

    'Total Revenue': 'Tổng doanh thu', 'Operating Revenue': 'Doanh thu thuần',
    'Cost Of Revenue': 'Giá vốn hàng bán', 'Gross Profit': 'Lợi nhuận gộp',
    'Operating Expense': 'Chi phí hoạt động', 'Selling General And Administration': 'Chi phí bán hàng và quản lý doanh nghiệp',
    'Selling And Marketing Expense': 'Chi phí bán hàng', 'General And Administrative Expense': 'Chi phí quản lý doanh nghiệp',
    'Research And Development': 'Chi phí nghiên cứu và phát triển', 'Other Operating Expenses': 'Chi phí hoạt động khác',
    'Operating Income': 'Lợi nhuận thuần từ hoạt động kinh doanh', 'Net Interest Income': 'Thu nhập lãi thuần',
    'Interest Expense': 'Chi phí lãi vay', 'Interest Income': 'Thu nhập lãi',
    'EBIT': 'Lợi nhuận trước lãi vay và thuế (EBIT)', 'EBITDA': 'Lợi nhuận trước lãi vay, thuế và khấu hao (EBITDA)',
    'Normalized EBITDA': 'Lợi nhuận trước lãi vay, thuế, khấu hao chuẩn hóa',
    'Normalized Income': 'Lợi nhuận thuần chuẩn hóa', 'Pretax Income': 'Lợi nhuận kế toán trước thuế',
    'Tax Provision': 'Chi phí thuế thu nhập doanh nghiệp', 'Net Income': 'Lợi nhuận sau thuế (Lợi nhuận ròng)',
    'Net Income Common Stockholders': 'Lợi nhuận ròng phân bổ cho cổ đông phổ thông',
    'Net Income Including Noncontrolling Interests': 'Lợi nhuận sau thuế bao gồm lợi ích cổ đông không kiểm soát',
    'Net Income From Continuing Operation': 'Lợi nhuận sau thuế từ hoạt động tiếp tục',
    'Net Income From Continuing And Discontinued Operation': 'Lợi nhuận thuần từ hoạt động tiếp tục và không tiếp tục',
    'Tax Effect Of Unusual Items': 'Ảnh hưởng thuế từ các khoản mục bất thường', 'Tax Rate For Calcs': 'Thuế suất dùng để tính toán',
    'Gain On Sale Of Security': 'Lãi / Lỗ từ bán chứng khoán', 'Other Under Preferred Stock Dividend': 'Cổ tức cổ phiếu ưu đãi và điều chỉnh khác',
    'Basic EPS': 'Lãi cơ bản trên cổ phiếu (Basic EPS)', 'Diluted EPS': 'Lãi suy giảm trên cổ phiếu (Diluted EPS)',
    'Diluted Average Shares': 'Số lượng cổ phiếu bình quân pha loãng', 'Basic Average Shares': 'Số lượng cổ phiếu bình quân cơ bản',

    'Operating Cash Flow': 'Lưu chuyển tiền thuần từ hoạt động kinh doanh',
    'Cash Flow From Continuing Operating Activities': 'Lưu chuyển tiền thuần từ hoạt động kinh doanh tiếp tục',
    'Depreciation Amortization Depletion': 'Khấu hao tài sản cố định và phân bổ',
    'Depreciation And Amortization': 'Khấu hao và phân bổ', 'Asset Impairment Charge': 'Tổn thất tài sản và dự phòng',
    'Deferred Income Tax': 'Thuế thu nhập hoãn lại', 'Change In Working Capital': 'Biến động vốn lưu động',
    'Change In Receivables': 'Biến động các khoản phải thu', 'Change In Inventory': 'Biến động hàng tồn kho',
    'Change In Payables': 'Biến động các khoản phải trả', 'Change In Account Payable': 'Biến động phải trả người bán',
    'Change In Other Working Capital': 'Biến động vốn lưu động khác',
    
    'Investing Cash Flow': 'Lưu chuyển tiền thuần từ hoạt động đầu tư',
    'Cash Flow From Continuing Investing Activities': 'Lưu chuyển tiền thuần từ hoạt động đầu tư tiếp tục',
    'Capital Expenditure': 'Chi phí đầu tư tài sản cố định (CapEx)', 'Net PPE Purchase And Sale': 'Tiền mua hoặc thanh lý tài sản cố định',
    'Net Intangibles Purchase And Sale': 'Tiền mua hoặc bán tài sản vô hình', 'Net Investment Purchase And Sale': 'Tiền đầu tư góp vốn thuần',
    'Net Business Purchase And Sale': 'Tiền mua bán công ty con hoặc sáp nhập', 'Free Cash Flow': 'Dòng tiền tự do (FCF)',

    'Financing Cash Flow': 'Lưu chuyển tiền thuần từ hoạt động tài chính',
    'Cash Flow From Continuing Financing Activities': 'Lưu chuyển tiền thuần từ hoạt động tài chính tiếp tục',
    'Issuance Of Debt': 'Tiền thu từ phát hành nợ vay', 'Repayment Of Debt': 'Tiền chi trả nợ gốc vay',
    'Net Common Stock Issuance': 'Tiền thu từ phát hành cổ phiếu hoặc bán cổ phiếu quỹ',
    'Cash Dividends Paid': 'Cổ tức đã chi trả cho chủ sở hữu', 'Beginning Cash Position': 'Tiền và tương đương tiền đầu kỳ',
    'End Cash Position': 'Tiền và tương đương tiền cuối kỳ', 'Changes In Cash': 'Ảnh hưởng thay đổi tỷ giá và tiền thuần thay đổi',

    'Current Price': 'Giá cổ phiếu hiện tại', 'Shares Outstanding': 'Tổng số lượng cổ phiếu lưu hành',
    'Market Capitalization': 'Vốn hóa thị trường', 'Trailing EPS': 'EPS cơ bản 4 quý gần nhất (Trailing EPS)',
    'Forward EPS': 'EPS dự phóng (Forward EPS)', 'Dividend Yield': 'Tỷ suất cổ tức (% Dividend Yield)',
    'Dividend Rate': 'Cổ tức tiền mặt trên mỗi cổ phiếu', 'Trailing P/E': 'Hệ số P/E cơ bản (Trailing P/E)',
    'Forward P/E': 'Hệ số P/E dự phóng (Forward P/E)', 'Price To Book': 'Hệ số P/B (Price to Book)',
    'Book Value': 'Giá trị sổ sách mỗi cổ phiếu (BVPS)', 'Return On Equity': 'Lợi nhuận trên vốn chủ sở hữu (ROE)',
    'Return On Assets': 'Lợi nhuận trên tổng tài sản (ROA)', 'Profit Margins': 'Biên lợi nhuận ròng (%)',
    'Gross Margins': 'Biên lợi nhuận gộp (%)',
    'Historical Dividend Cash': 'Lịch sử trả cổ tức bằng tiền (VND/Cổ phiếu)'
}



def translate_metric(metric_original):
    cleaned_key = str(metric_original).strip()
    if cleaned_key in TRANSLATION_MAP: 
        return TRANSLATION_MAP[cleaned_key]
    
    for eng_k, vie_v in TRANSLATION_MAP.items():
        if cleaned_key.lower() == eng_k.lower(): 
            return vie_v
            
    k_lower = cleaned_key.lower()
    if 'gain' in k_lower and 'loss' in k_lower: return 'Lãi / Lỗ từ đánh giá hoặc thanh lý tài sản'
    if 'effect of exchange' in k_lower or 'foreign' in k_lower: return 'Ảnh hưởng thay đổi tỷ giá hối đoái'
    if 'net investment' in k_lower: return 'Thuần đầu tư tài chính'
    if 'purchase of intangibles' in k_lower: return 'Tiền chi mua tài sản vô hình'
    if 'purchase of' in k_lower or 'acquisition' in k_lower: return 'Tiền chi mua sắm tài sản hoặc đầu tư'
    if 'sale of' in k_lower or 'disposal' in k_lower: return 'Tiền thu từ thanh lý hoặc bán tài sản'
    if 'net income' in k_lower or 'net profit' in k_lower: return 'Lợi nhuận sau thuế (Lợi nhuận ròng)'
    if 'operating income' in k_lower or 'operating profit' in k_lower: return 'Lợi nhuận thuần từ hoạt động kinh doanh'
    if 'gross profit' in k_lower: return 'Lợi nhuận gộp'
    if 'pretax income' in k_lower or 'income before tax' in k_lower: return 'Lợi nhuận kế toán trước thuế'
    if 'revenue' in k_lower or 'sales' in k_lower: return 'Tổng doanh thu / Doanh thu thuần'
    if 'cost of' in k_lower or 'cogs' in k_lower: return 'Giá vốn hàng bán'
    if 'operating expense' in k_lower or 'sga' in k_lower or 'admin' in k_lower: return 'Chi phí bán hàng và quản lý doanh nghiệp'
    if 'interest expense' in k_lower: return 'Chi phí lãi vay'
    if 'interest income' in k_lower: return 'Thu nhập lãi'
    if 'tax provision' in k_lower or 'tax expense' in k_lower: return 'Chi phí thuế thu nhập doanh nghiệp'
    if 'depreciation' in k_lower or 'amortization' in k_lower: return 'Khấu hao tài sản cố định và phân bổ'
    if 'cash flow' in k_lower: return 'Lưu chuyển tiền thuần'
    if 'capital expenditure' in k_lower or 'capex' in k_lower: return 'Chi phí đầu tư tài sản cố định (CapEx)'
    if 'dividend' in k_lower: return 'Cổ tức đã chi trả'
    if 'asset' in k_lower: return 'Tổng tài sản'
    if 'liability' in k_lower or 'debt' in k_lower: return 'Nợ phải trả'
    if 'equity' in k_lower: return 'Vốn chủ sở hữu'
    if 'share' in k_lower: return 'Chỉ tiêu cổ phiếu'
    if 'eps' in k_lower: return 'Lãi trên cổ phiếu (EPS)'

    cleaned_viet = re.sub(r'[^a-zA-Zà-ỹÀ-Ỹ0-9\s]', ' ', cleaned_key)
    return f"Chỉ tiêu tài chính: {cleaned_viet.strip()}"




# Bổ sung chỉ tiêu thị trường/cổ tức cho pipeline nâng cấp.
TRANSLATION_MAP.update({
    "Payout Ratio": "Tỷ lệ chi trả cổ tức trên lợi nhuận (%)",
})
