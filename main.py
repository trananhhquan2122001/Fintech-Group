import os
import time
from datetime import datetime
import sqlite3
import pandas as pd
import requests
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

try:
    import yfinance as yf
except ImportError:
    print("⚙️ Đang cài đặt thư viện yfinance...")
    os.system("pip install yfinance --quiet")
    import yfinance as yf

def create_robust_session():
    session = requests.Session()
    retries = Retry(total=5, backoff_factor=1.5, status_forcelist=[429, 500, 502, 503, 504], raise_on_status=False)
    adapter = HTTPAdapter(max_retries=retries, pool_connections=50, pool_maxsize=50)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
        'Accept-Language': 'en-US,en;q=0.9,vi;q=0.8'
    })
    return session

global_session = create_robust_session()

def load_242_master_tickers():
    raw_tickers = [
        "ABB", "ACB", "ACV", "AIG", "ANV", "BAF", "BCM", "BID", "BMP", "BSI", "BSR", "BVH", "BVS", "BWE",
        "CAP", "CEO", "CII", "CMG", "CTD", "CTG", "CTR", "CTS", "DBC", "DCM", "DGW", "DIG", "DNH", "DP3", 
        "DPM", "DSE", "DTD", "DVN", "DXG", "DXP", "EIB", "EVF", "FOX", "FPT", "FRT", "FTS", "GAS", "GEE", 
        "GEX", "GMD", "GVR", "HAG", "HCM", "HDB", "HDG", "HND", "HHV", "HPG", "HSG", "HT1", "HUT", "IDC", 
        "IDP", "KBC", "KDC", "KDH", "L14", "L18", "LAS", "LHC", "LPB", "MBB", "MBS", "MCH", "MSB", "MSN", 
        "MSR", "MVN", "MWG", "NAB", "NBC", "NDN", "NKG", "NLG", "NT2", "NTP", "NVL", "OCB", "OIL", "PAN", 
        "PC1", "PDR", "PHR", "PLC", "PLX", "PNJ", "POW", "PSD", "PVB", "PVC", "PVD", "PVS", "PVT", "PVI", 
        "QNS", "QTP", "REE", "SAB", "SAS", "SBT", "SHB", "SHS", "SIP", "SJS", "SLS", "SNZ", "SSB", "SSI", 
        "STB", "TAL", "TBD", "TCB", "TCH", "TCX", "TDM", "TID", "TIG", "TNG", "TOS", "TPB", "TVD", "VCB", 
        "VC3", "VCG", "VCI", "VCK", "VCS", "VEA", "VFS", "VGC", "VGI", "VGP", "VGR", "VHC", "VHM", "VIB", 
        "VIC", "VIX", "VJC", "VND", "VNM", "VPB", "VPI", "VPL", "VPX", "VRE", "VSC", "VTP", "PRE", "HCC", 
        "L40", "KDM", "HVT", "VTZ", "GLT", "VGS", "PCH", "CAR", "HGM", "KSV", "THD", "KSF", "SCG", "CLM", 
        "TMB", "SAF", "NET", "DHT", "DGC", "SZC", "HVN", "BAB", "AGR", "ICT", "TLH", "BMI", "PET", "LSS", 
        "HDC", "IJC", "TDC", "CTI", "SJD", "TMP", "SBA", "VSH", "TTA", "TV2", "VCP", "BFC", "DDV", "VGT", 
        "SGP", "DPR", "DHC", "TCM", "CKA", "VLB", "HPP", "WSB", "F88", "SEA", "ODE", "PHP", "VXB", "APF", 
        "VNZ", "HLB", "TED", "VEF", "PAT", "FOC", "DTP", "SIV", "VGG", "AVC", "LSG", "CQN", "QPH", "TCW", 
        "ACE", "VSF", "HAM", "SBM", "AGP", "LIC", "SCL", "CC1", "BWS", "NAS", "CLI", "VTK", "HMS", "PCC", 
        "QHW", "MFS", "VEC", "HEC"
    ]
    return list(set([t.strip().upper() for t in raw_tickers if t.strip()]))

def get_company_profile(symbol):
    sugar_list = ["SLS", "SBT", "LSS", "QNS", "APF"]
    tech_list = ["FPT", "CMG", "VTP", "ICT", "ELC", "CTR", "VGI", "VNZ", "FOX", "MFS"]
    bank_list = ["VCB", "BID", "TCB", "MBB", "ACB", "CTG", "VPB", "STB", "SHB", "HDB", "LPB", "MSB", "OCB", "NAB", "SSB", "EIB", "TPB", "ABB", "BAB"]
    securities_list = ["SSI", "VCI", "HCM", "VND", "SHS", "MBS", "FTS", "BSI", "CTS", "VIX", "VDS", "ORS", "AGR", "VFS", "DSE", "BVS", "EVF"]
    realestate_list = ["VIC", "VHM", "VRE", "BCM", "KBC", "IDC", "SIP", "SZC", "KDH", "NLG", "DXG", "PDR", "DIG", "CEO", "HDC", "NVL", "TCH", "VC3", "VPI", "SJS", "L14", "L18", "NDN", "THD", "KSF", "IJC", "TDC", "CTI", "VEF", "ODE"]

    if symbol in sugar_list: sector = "Nông nghiệp & Mía đường"
    elif symbol in tech_list: sector = "Công nghệ thông tin & Viễn thông"
    elif symbol in bank_list: sector = "Ngân hàng"
    elif symbol in securities_list: sector = "Chứng khoán"
    elif symbol in realestate_list: sector = "Bất động sản & Xây dựng đô thị"
    else: sector = "Công nghiệp, Sản xuất & Hàng tiêu dùng"

    return f"Công ty Cổ phần {symbol}", sector

TRANSLATION_MAP = {
    # --- BẢNG 1: BẢNG CÂN ĐỐI KẾ TOÁN (Balance Sheet) ---
    'Total Assets': '1. Tổng tài sản',
    'Current Assets': '1.1. Tài sản ngắn hạn',
    'Cash And Cash Equivalents': '1.1.1. Tiền và các khoản tương đương tiền',
    'Cash': 'Tiền mặt',
    'Cash Equivalents': 'Các khoản tương đương tiền',
    'Other Short Term Investments': 'Đầu tư tài chính ngắn hạn',
    'Accounts Receivable': 'Phải thu ngắn hạn khách hàng',
    'Inventory': 'Hàng tồn kho',
    'Raw Materials': 'Nguyên liệu, vật liệu tồn kho',
    'Work In Process': 'Chi phí sản xuất kinh doanh dở dang',
    'Finished Goods': 'Thành phẩm tồn kho',
    'Prepaid Assets': 'Chi phí trả trước ngắn hạn',
    'Total Non Current Assets': '1.2. Tài sản dài hạn',
    'Net PPE': 'Tài sản cố định thuần',
    'Gross PPE': 'Nguyên giá tài sản cố định',
    'Accumulated Depreciation': 'Hao mòn lũy kế',
    'Construction In Progress': 'Xây dựng cơ bản dở dang',
    'Goodwill And Other Intangible Assets': 'Lợi thế thương mại và tài sản vô hình',
    'Investments And Advances': 'Đầu tư tài chính dài hạn',
    'Current Liabilities': '2.1. Nợ ngắn hạn',
    'Current Debt': 'Vay và nợ thuê tài chính ngắn hạn',
    'Accounts Payable': 'Phải trả người bán ngắn hạn',
    'Taxes Payable': 'Thuế và các khoản phải nộp nhà nước',
    'Accrued Liabilities': 'Chi phí phải trả ngắn hạn',
    'Total Non Current Liabilities Net Minority Interest': '2.2. Nợ dài hạn',
    'Long Term Debt': 'Vay và nợ thuê tài chính dài hạn',
    'Total Debt': 'Tổng nợ vay',
    'Net Debt': 'Nợ vay ròng',
    'Stockholders Equity': '3. Vốn chủ sở hữu',
    'Capital Stock': 'Vốn góp chủ sở hữu',
    'Retained Earnings': 'Lợi nhuận sau thuế chưa phân phối',
    'Additional Paid In Capital': 'Thặng dư vốn cổ phần',
    'Minority Interest': 'Lợi ích cổ đông không kiểm soát',

    # --- BẢNG 2: BÁO CÁO KẾT QUẢ KINH DOANH (Income Statement) ---
    'Total Revenue': '1. Tổng doanh thu',
    'Operating Revenue': 'Doanh thu thuần',
    'Cost Of Revenue': '2. Giá vốn hàng bán',
    'Gross Profit': '3. Lợi nhuận gộp',
    'Operating Expense': '4. Chi phí hoạt động',
    'Selling General And Administration': 'Chi phí bán hàng và quản lý doanh nghiệp',
    'Selling And Marketing Expense': 'Chi phí bán hàng',
    'General And Administrative Expense': 'Chi phí quản lý doanh nghiệp',
    'Operating Income': '5. Lợi nhuận thuần từ hoạt động kinh doanh',
    'Net Interest Income': 'Thu nhập lãi thuần',
    'Interest Expense': 'Chi phí lãi vay',
    'Interest Income': 'Thu nhập lãi',
    'EBIT': 'Lợi nhuận trước lãi vay và thuế (EBIT)',
    'EBITDA': 'Lợi nhuận trước lãi vay, thuế và khấu hao (EBITDA)',
    'Pretax Income': '6. Lợi nhuận kế toán trước thuế',
    'Tax Provision': 'Chi phí thuế TNDN',
    'Net Income': '7. Lợi nhuận sau thuế (Lợi nhuận ròng)',
    'Net Income Common Stockholders': 'Lợi nhuận ròng phân bổ cổ đông phổ thông',
    'Basic EPS': 'Lãi cơ bản trên cổ phiếu (Basic EPS)',
    'Diluted EPS': 'Lãi suy giảm trên cổ phiếu (Diluted EPS)',

    # --- BẢNG 3: BÁO CÁO LƯU CHUYỂN TIỀN TỆ (Cash Flow) ---
    'Operating Cash Flow': 'I. Lưu chuyển tiền từ hoạt động kinh doanh',
    'Depreciation And Amortization': 'Khấu hao tài sản cố định và phân bổ',
    'Change In Working Capital': 'Biến động vốn lưu động',
    'Change In Receivables': 'Biến động các khoản phải thu',
    'Change In Inventory': 'Biến động hàng tồn kho',
    'Change In Payables': 'Biến động các khoản phải trả',
    'Investing Cash Flow': 'II. Lưu chuyển tiền từ hoạt động đầu tư',
    'Capital Expenditure': 'Chi phí đầu tư tài sản cố định (CapEx)',
    'Free Cash Flow': 'Dòng tiền tự do (FCF)',
    'Financing Cash Flow': 'III. Lưu chuyển tiền từ hoạt động tài chính',
    'Issuance Of Debt': 'Tiền thu từ phát hành nợ vay',
    'Repayment Of Debt': 'Tiền chi trả nợ gốc vay',
    'Cash Dividends Paid': 'Cổ tức đã chi trả cho chủ sở hữu',
    'End Cash Position': 'Tiền và tương đương tiền cuối kỳ',

    # --- THÔNG TIN THỊ TRƯỜNG & ĐỊNH GIÁ ---
    'Current Price': 'Giá cổ phiếu hiện tại (VND)',
    'Shares Outstanding': 'Tổng số lượng cổ phiếu lưu hành',
    'Market Capitalization': 'Tổng vốn hóa thị trường (VND)',
    'Dividend Yield': 'Tỷ suất cổ tức (% Dividend Yield)',
    'Trailing P/E': 'Hệ số P/E cơ bản',
    'Price To Book': 'Hệ số P/B',
    'Return On Equity': 'ROE (%)',
    'Return On Assets': 'ROA (%)',
    'Profit Margins': 'Biên lợi nhuận ròng (%)',
    'Gross Margins': 'Biên lợi nhuận gộp (%)'
}

def translate_metric(raw_name):
    clean = str(raw_name).strip()
    if clean in TRANSLATION_MAP:
        return TRANSLATION_MAP[clean]
    for k, v in TRANSLATION_MAP.items():
        if clean.lower() == k.lower():
            return v
    return f"Chỉ tiêu chi tiết: {clean}"

def fetch_market_metrics(symbol, ticker_obj, balance_sheet_df):
    records = []
    company_name, sector_name = get_company_profile(symbol)
    current_year = str(datetime.now().year)
    today_str = datetime.today().strftime('%Y-%m-%d')
    
    current_price, shares_out, market_cap, div_yield = 0.0, 0.0, 0.0, 0.0
    try:
        info = ticker_obj.info if ticker_obj else {}
        current_price = info.get('currentPrice') or info.get('regularMarketPrice') or info.get('previousClose') or 0.0
        shares_out = info.get('sharesOutstanding', 0.0)
        market_cap = info.get('marketCap', 0.0)
        div_yield = info.get('dividendYield', 0.0) or 0.0

        if not current_price or current_price == 0.0:
            for p in ["3mo", "1y"]:
                hist = ticker_obj.history(period=p)
                if hist is not None and not hist.empty:
                    current_price = float(hist['Close'].iloc[-1])
                    break

        if shares_out == 0.0 and balance_sheet_df is not None and not balance_sheet_df.empty:
            for row_idx in balance_sheet_df.index:
                if 'capital stock' in str(row_idx).lower() or 'ordinary shares' in str(row_idx).lower():
                    val = balance_sheet_df.loc[row_idx].iloc[0]
                    if pd.notna(val) and float(val) > 0:
                        shares_out = float(val)
                        break

        if shares_out == 0.0: shares_out = 50_000_000.0
        if market_cap == 0.0 and current_price > 0: market_cap = current_price * shares_out

        metrics = [
            ('Current Price', current_price),
            ('Shares Outstanding', shares_out),
            ('Market Capitalization', market_cap),
            ('Dividend Yield', div_yield),
            ('Trailing P/E', info.get('trailingPE', 0.0)),
            ('Price To Book', info.get('priceToBook', 0.0)),
            ('Return On Equity', info.get('returnOnEquity', 0.0)),
            ('Return On Assets', info.get('returnOnAssets', 0.0)),
            ('Profit Margins', info.get('profitMargins', 0.0)),
            ('Gross Margins', info.get('grossMargins', 0.0))
        ]

        for eng_key, val in metrics:
            f_val = float(val) if val is not None and not pd.isna(val) else 0.0
            records.append({
                'Mã chứng khoán': symbol, 'Tên doanh nghiệp': company_name, 'Tên ngành': sector_name,
                'Loại báo cáo': '0. Chỉ số thị trường & Định giá', 'Loại kỳ': 'Real-time',
                'Năm': current_year, 'Ngày kỳ': today_str, 'Chỉ tiêu gốc': eng_key,
                'Chỉ tiêu tiếng Việt': translate_metric(eng_key), 'Giá trị': f_val
            })
    except Exception:
        pass
    return records

def fetch_financials_and_market(symbol, min_year=2020):
    records = []
    company_name, sector_name = get_company_profile(symbol)
    suffixes = [".VN", ".HN", ".UPCOM", ".HA", ".HM", ""]
    
    for suffix in suffixes:
        full_ticker = f"{symbol}{suffix}"
        try:
            ticker = yf.Ticker(full_ticker, session=global_session)
            
            # Cấu hình quét rạch ròi 3 Bảng BCTC chính
            bs_annual = getattr(ticker, 'balance_sheet', None)
            target_statements = [
                (bs_annual, '1. Bảng cân đối kế toán', 'Năm'),
                (getattr(ticker, 'quarterly_balance_sheet', None), '1. Bảng cân đối kế toán', 'Quý'),
                (getattr(ticker, 'financials', None), '2. Báo cáo kết quả kinh doanh', 'Năm'),
                (getattr(ticker, 'quarterly_financials', None), '2. Báo cáo kết quả kinh doanh', 'Quý'),
                (getattr(ticker, 'cashflow', None), '3. Báo cáo lưu chuyển tiền tệ', 'Năm'),
                (getattr(ticker, 'quarterly_cashflow', None), '3. Báo cáo lưu chuyển tiền tệ', 'Quý')
            ]
            
            for df, report_type, period_type in target_statements:
                if df is not None and not df.empty:
                    for col in df.columns:
                        date_str = str(col).split('T')[0].split(' ')[0]
                        year_val = date_str.split('-')[0]
                        if year_val.isdigit() and int(year_val) >= min_year:
                            for row_idx, val in df[col].items():
                                if pd.notna(val):
                                    try: f_val = float(val)
                                    except: continue
                                    if pd.isna(f_val) or f_val in [float('inf'), float('-inf')]: continue
                                    
                                    raw_metric = str(row_idx).strip()
                                    records.append({
                                        'Mã chứng khoán': symbol, 'Tên doanh nghiệp': company_name, 'Tên ngành': sector_name,
                                        'Loại báo cáo': report_type, 'Loại kỳ': period_type, 'Năm': year_val, 'Ngày kỳ': date_str,
                                        'Chỉ tiêu gốc': raw_metric, 'Chỉ tiêu tiếng Việt': translate_metric(raw_metric), 'Giá trị': f_val
                                    })
            
            # Bổ sung chỉ số thị trường, giá, vốn hóa và cổ tức
            records.extend(fetch_market_metrics(symbol, ticker, bs_annual))
            if records: break
        except Exception:
            continue
    return records

def process_ticker(symbol):
    return symbol, fetch_financials_and_market(symbol, min_year=2020)

def main():
    tickers = load_242_master_tickers()
    all_data = []
    success_count = 0
    
    print(f"🚀 [FINEX VN Terminal] Đang vét toàn diện 3 Bảng BCTC, Vốn hóa, Khối lượng & Cổ tức cho {len(tickers)} mã...")
    
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = {executor.submit(process_ticker, sym): sym for sym in tickers}
        for future in as_completed(futures):
            sym = futures[future]
            try:
                symbol, res = future.result()
                if res:
                    all_data.extend(res)
                    success_count += 1
                    print(f"✅ [{success_count}/{len(tickers)}] {symbol}: {len(res):,} bản ghi.")
            except Exception as e:
                print(f"❌ Lỗi mã {sym}: {e}")
                
    df_master = pd.DataFrame(all_data)
    
    # Làm sạch dữ liệu chuyên sâu
    if not df_master.empty:
        df_master = df_master.drop_duplicates()
        df_master = df_master.dropna(subset=['Mã chứng khoán', 'Chỉ tiêu tiếng Việt', 'Giá trị'])
        df_master['Giá trị'] = pd.to_numeric(df_master['Giá trị'], errors='coerce').fillna(0.0)
        df_master = df_master.sort_values(
            by=['Tên ngành', 'Mã chứng khoán', 'Loại báo cáo', 'Loại kỳ', 'Ngày kỳ'],
            ascending=[True, True, True, False, False]
        )
        
        os.makedirs('data', exist_ok=True)
        csv_path = 'data/vietnam_242_full_3bctc_master.csv'
        df_master.to_csv(csv_path, index=False, encoding='utf-8-sig')
        
        conn = sqlite3.connect('data/vietnam_stock.db')
        df_master.to_sql('stock_242_full_3bctc_master', conn, if_exists='replace', index=False)
        conn.close()
        
        print(f"\n==================================================")
        print(f" 🎉 HOÀN TẤT VÉT VÀ LƯU SẠCH 3 BẢNG BCTC CHO 242 MÃ!")
        print(f" - Tổng mã thành công: {success_count}/{len(tickers)}")
        print(f" - Tổng số dòng dữ liệu: {len(df_master):,}")
        print(f" - Tệp lưu trữ CSV: {csv_path}")
        print(f"==================================================")

if __name__ == "__main__":
    main()
