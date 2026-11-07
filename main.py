import os
import time
import random
from datetime import datetime
import pandas as pd
import requests
import re
from concurrent.futures import ThreadPoolExecutor, as_completed

# ==========================================
# 1. TÍCH HỢP API KEY VÀ CÀI ĐẶT THƯ VIỆN
# ==========================================
os.environ["VNSTOCK_API_KEY"] = "vnstock_533590cc17b6737ceb7c9f147471f31f"

try:
    import vnfinancialdata as vnf
except ImportError:
    print("⚙️ Đang cài đặt thư viện vnfinancialdata...")
    os.system("pip install vnfinancialdata --quiet")
    import vnfinancialdata as vnf

try:
    import yfinance as yf
except ImportError:
    os.system("pip install yfinance --quiet")
    import yfinance as yf

try:
    from vnstock import Fundamental, Market
except ImportError:
    os.system("pip install -U --extra-index-url https://vnstocks.com/api/packages vnstock --quiet")
    from vnstock import Fundamental, Market

USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
]
session = requests.Session()
session.headers.update({'User-Agent': random.choice(USER_AGENTS)})

# ==========================================
# 2. DANH SÁCH 242 MÃ (GIỮ NGUYÊN)
# ==========================================
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
    return {t.strip().upper(): "VIETNAM_MARKET" for t in raw_tickers if t.strip()}

def get_company_profile(symbol):
    return f"Công ty Cổ phần {symbol}", "Chưa phân loại"

# ==========================================
# 3. BỘ TỪ ĐIỂN DỊCH THUẬT (PHỤC HỒI 100% TỪ GỐC CỦA BẠN)
# ==========================================
TRANSLATION_MAP = {
    'Balance_Sheet': 'Bảng cân đối kế toán', 'Income_Statement': 'Báo cáo kết quả kinh doanh',
    'Cash_Flow': 'Báo cáo lưu chuyển tiền tệ', 'Market_Metrics': 'Chỉ số thị trường, Định giá & Cổ tức',
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
    'Gross Margins': 'Biên lợi nhuận gộp (%)', 'Historical Dividend Cash': 'Lịch sử trả cổ tức bằng tiền (VND/Cổ phiếu)'
}

# ==========================================
# 4. LÀM SẠCH DỮ LIỆU & ĐỊNH DẠNG FLOAT
# ==========================================
def clean_text(text):
    if pd.isna(text): return ""
    return re.sub(r'[\n\r\t]+', ' ', str(text)).strip()

def format_value(x):
    """Trả về dạng Float (giữ dấu thập phân cho Machine Learning)"""
    if pd.isna(x): return None
    try:
        val = float(x)
        if val == 0 or val != val or val in [float('inf'), float('-inf')]: 
            return None
        return round(val, 4)
    except: 
        return None

def translate_metric(metric_original, is_vn=False):
    cleaned_key = clean_text(metric_original)
    if is_vn or any(char in cleaned_key for char in ['à','á','ả','ã','ạ','ă','â','đ','ê','ô','ơ','ư','ý']): 
        return cleaned_key
    if cleaned_key in TRANSLATION_MAP: return TRANSLATION_MAP[cleaned_key]
    for eng_k, vie_v in TRANSLATION_MAP.items():
        if cleaned_key.lower() == eng_k.lower(): return vie_v
        
    k_lower = cleaned_key.lower()
    if 'revenue' in k_lower or 'sales' in k_lower: return 'Tổng doanh thu / Doanh thu thuần'
    if 'cost of' in k_lower or 'cogs' in k_lower: return 'Giá vốn hàng bán'
    if 'profit' in k_lower or 'income' in k_lower: return 'Lợi nhuận'
    if 'asset' in k_lower: return 'Tài sản'
    if 'liability' in k_lower or 'debt' in k_lower: return 'Nợ phải trả'
    if 'equity' in k_lower: return 'Vốn chủ sở hữu'
    if 'cash' in k_lower: return 'Tiền và tương đương tiền'
    if 'eps' in k_lower: return 'Lãi trên cổ phiếu (EPS)'
    return cleaned_key

# ==========================================
# 5. CÀO DỮ LIỆU TỪ YFINANCE (CÓ FALLBACK)
# ==========================================
def parse_financial_df(symbol, df, statement_type_vn, ky_bao_cao):
    records = []
    company_name, _ = get_company_profile(symbol)
    try:
        if df is not None and not df.empty:
            for col in df.columns:
                date_str = str(col).split('T')[0].split(' ')[0]
                year_val = date_str.split('-')[0]
                if year_val.isdigit() and int(year_val) >= 2000:
                    for row_idx, val in df[col].items():
                        f_val = format_value(val)
                        if f_val is not None:
                            metric_vn = translate_metric(str(row_idx).strip())
                            records.append({
                                'Mã chứng khoán': symbol, 'Tên doanh nghiệp': company_name,
                                'Tên ngành': "Chưa phân loại", 'Loại báo cáo': statement_type_vn,
                                'Loại kỳ': ky_bao_cao, 'Năm': year_val, 'Ngày kỳ': date_str,
                                'Chỉ tiêu tiếng Việt': metric_vn, 'Giá trị': f_val
                            })
    except Exception: pass
    return records

def process_yfinance_ticker(symbol):
    recs = []
    try:
        ticker = yf.Ticker(f"{symbol}.VN", session=session)
        bs_df = ticker.balance_sheet
        
        if bs_df is not None and not bs_df.empty:
            # Lấy sạch 3 bảng (Năm & Quý)
            recs.extend(parse_financial_df(symbol, bs_df, 'Bảng cân đối kế toán', 'Năm'))
            recs.extend(parse_financial_df(symbol, ticker.quarterly_balance_sheet, 'Bảng cân đối kế toán', 'Quý'))
            recs.extend(parse_financial_df(symbol, ticker.financials, 'Báo cáo kết quả kinh doanh', 'Năm'))
            recs.extend(parse_financial_df(symbol, ticker.quarterly_financials, 'Báo cáo kết quả kinh doanh', 'Quý'))
            recs.extend(parse_financial_df(symbol, ticker.cashflow, 'Báo cáo lưu chuyển tiền tệ', 'Năm'))
            recs.extend(parse_financial_df(symbol, ticker.quarterly_cashflow, 'Báo cáo lưu chuyển tiền tệ', 'Quý'))
            
            # Chỉ số thị trường & Fallback tính toán
            info = ticker.info if ticker.info else {}
            price = info.get('currentPrice') or info.get('regularMarketPrice')
            shares = info.get('sharesOutstanding')
            market_cap = info.get('marketCap')
            
            # Nếu yfinance không có shares hoặc market_cap, tự động tính từ BCTC
            if not shares and bs_df is not None:
                for idx in ['Ordinary Shares Number', 'Share Issued']:
                    if idx in bs_df.index:
                        val = format_value(bs_df.loc[idx].iloc[0])
                        if val: shares = val; break
                        
            if price and shares and not market_cap:
                market_cap = price * shares

            metrics = [
                ('Current Price', price),
                ('Shares Outstanding', shares),
                ('Market Capitalization', market_cap),
                ('Dividend Yield', info.get('dividendYield'))
            ]
            for k, v in metrics:
                f_val = format_value(v)
                if f_val is not None:
                    recs.append({
                        'Mã chứng khoán': symbol, 'Tên doanh nghiệp': get_company_profile(symbol)[0],
                        'Tên ngành': "Chưa phân loại", 'Loại báo cáo': 'Chỉ số thị trường, Định giá & Cổ tức',
                        'Loại kỳ': 'Real-time', 'Năm': str(datetime.now().year), 'Ngày kỳ': datetime.today().strftime('%Y-%m-%d'),
                        'Chỉ tiêu tiếng Việt': TRANSLATION_MAP.get(k, k), 'Giá trị': f_val
                    })
    except Exception: pass
    return recs

# ==========================================
# 6. CÀO DỮ LIỆU TỪ VNSTOCK (CHỐNG BLOCK API BẰNG RANDOM SLEEP)
# ==========================================
def fetch_vnstock_financials(symbol):
    recs = []
    try:
        # Tăng thời gian nghỉ ngẫu nhiên 2-4s để không bị đánh dấu là bot
        time.sleep(random.uniform(2.0, 4.0))
        session.headers.update({'User-Agent': random.choice(USER_AGENTS)})
        
        fin = Fundamental().equity(symbol)
        company_name, _ = get_company_profile(symbol)

        for period, ky in [('year', 'Năm'), ('quarter', 'Quý')]:
            for df, rpt_name in [
                (fin.balance_sheet(period=period), 'Bảng cân đối kế toán'),
                (fin.income_statement(period=period), 'Báo cáo kết quả kinh doanh'),
                (fin.cash_flow(period=period), 'Báo cáo lưu chuyển tiền tệ')
            ]:
                if df is None or df.empty: continue
                for _, row in df.iterrows():
                    metric_vn = translate_metric(row.get('item', ''))
                    for col in df.columns:
                        c_str = str(col)
                        if c_str in ['item', 'item_en', 'unit', 'ticker', 'year', 'quarter']: continue
                        year_val = c_str.split('-')[0].split(' ')[0].strip()
                        if not year_val.isdigit() or int(year_val) < 2000: continue
                        
                        f_val = format_value(row[col])
                        if f_val is not None:
                            recs.append({
                                'Mã chứng khoán': symbol, 'Tên doanh nghiệp': company_name,
                                'Tên ngành': "Chưa phân loại", 'Loại báo cáo': rpt_name,
                                'Loại kỳ': ky, 'Năm': year_val, 'Ngày kỳ': f"{year_val}-12-31" if ky == 'Năm' else c_str,
                                'Chỉ tiêu tiếng Việt': metric_vn, 'Giá trị': f_val
                            })
        
        quote = Market().equity(symbol).quote()
        if not quote.empty:
            price = format_value(quote.iloc[0].get('close_price'))
            if price is not None:
                recs.append({
                    'Mã chứng khoán': symbol, 'Tên doanh nghiệp': company_name,
                    'Tên ngành': "Chưa phân loại", 'Loại báo cáo': 'Chỉ số thị trường, Định giá & Cổ tức',
                    'Loại kỳ': 'Real-time', 'Năm': str(datetime.now().year), 'Ngày kỳ': datetime.today().strftime('%Y-%m-%d'),
                    'Chỉ tiêu tiếng Việt': 'Giá cổ phiếu hiện tại', 'Giá trị': price
                })
    except Exception: pass
    return recs

# ==========================================
# 7. CÀO DỮ LIỆU TỪ VNFINANCIALDATA (3 BẢNG CHÍNH)
# ==========================================
def fetch_vnfinancialdata_bulk(ticker_market_map):
    records = []
    statements = {
        "balance_sheet": "Bảng cân đối kế toán",
        "income_statement": "Báo cáo kết quả kinh doanh",
        "cash_flow": "Báo cáo lưu chuyển tiền tệ"
    }
    target_symbols = set(ticker_market_map.keys())

    for exchange in ["HSX", "HNX"]:
        for stmt_key, stmt_name in statements.items():
            try:
                print(f"  📥 Đang tải {stmt_name} cho sàn {exchange}...")
                df = vnf.load(exchange=exchange, statement=stmt_key)
                if df is None or df.empty: continue
                
                # Dò tìm cột giá trị
                val_col = 'value'
                for c in ['value', 'ratio_value', 'Value', 'val']:
                    if c in df.columns:
                        val_col = c
                        break
                
                df = df.rename(columns={'ticker': 'Mã chứng khoán', 'year': 'Năm', 'item_name': 'Chỉ tiêu tiếng Việt', val_col: 'Giá trị'})
                df = df[df['Mã chứng khoán'].isin(target_symbols)]
                
                for _, row in df.iterrows():
                    f_val = format_value(row['Giá trị'])
                    if f_val is not None:
                        records.append({
                            'Mã chứng khoán': row['Mã chứng khoán'], 
                            'Tên doanh nghiệp': get_company_profile(row['Mã chứng khoán'])[0],
                            'Tên ngành': "Chưa phân loại", 
                            'Loại báo cáo': stmt_name,
                            'Loại kỳ': 'Năm', 'Năm': str(row['Năm']), 'Ngày kỳ': f"{row['Năm']}-12-31",
                            'Chỉ tiêu tiếng Việt': translate_metric(row['Chỉ tiêu tiếng Việt'], is_vn=True), 
                            'Giá trị': f_val
                        })
            except Exception as e:
                print(f"  ⚠️ Lỗi tải {stmt_name} cho {exchange}: {e}")
                
    return records

# ==========================================
# 8. HÀM MAIN (ĐIỀU PHỐI ĐỂ KHÔNG MẤT MÃ)
# ==========================================
def main():
    ticker_market_map = load_242_master_tickers()
    all_master_records = []
    
    print("🚀 BƯỚC 1: Tải dữ liệu BCTC từ vnfinancialdata...")
    vnf_recs = fetch_vnfinancialdata_bulk(ticker_market_map)
    if vnf_recs:
        all_master_records.extend(vnf_recs)
        print(f" ✅ Đã lấy {len(vnf_recs):,} dòng từ vnfinancialdata.")
    
    total_tickers = len(ticker_market_map)
    print(f"\n⚡ BƯỚC 2: Quét Yfinance (Max 3 luồng để tránh 429) cho {total_tickers} mã...")
    yf_success_symbols = set()
    
    # Giảm xuống 3 luồng để đảm bảo không bị chặn
    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = {executor.submit(process_yfinance_ticker, symbol): symbol for symbol in ticker_market_map.keys()}
        count = 0
        for future in as_completed(futures):
            symbol = futures[future]
            try:
                res = future.result()
                if res:
                    all_master_records.extend(res)
                    yf_success_symbols.add(symbol)
                    count += 1
                    if count % 20 == 0:
                        print(f"  [{count}/{total_tickers}] Yfinance OK: {symbol}")
            except Exception: pass
            
    print(f" ✅ Yfinance đã lấy được: {len(yf_success_symbols)}/{total_tickers} mã.")

    print(f"\n🐢 BƯỚC 3: Bổ sung Vnstock cho các mã còn thiếu (Nghỉ 2-4s mỗi mã)...")
    missing_symbols = [s for s in ticker_market_map.keys() if s not in yf_success_symbols]
    for idx, symbol in enumerate(missing_symbols):
        print(f"  [{idx+1}/{len(missing_symbols)}] Lấy Vnstock: {symbol}...")
        res = fetch_vnstock_financials(symbol)
        if res:
            all_master_records.extend(res)

    print("\n🧹 BƯỚC 4: Làm sạch và lưu dữ liệu...")
    df_master = pd.DataFrame(all_master_records)
    
    if not df_master.empty:
        df_master = df_master.dropna(subset=['Mã chứng khoán', 'Chỉ tiêu tiếng Việt', 'Giá trị'])
        df_master['Chỉ tiêu tiếng Việt'] = df_master['Chỉ tiêu tiếng Việt'].apply(clean_text)
        
        # Đảm bảo là Float
        df_master['Giá trị'] = pd.to_numeric(df_master['Giá trị'], errors='coerce')
        df_valid = df_master[df_master['Giá trị'].notna() & (df_master['Giá trị'] != 0)].copy()
        
        df_valid = df_valid.drop_duplicates(subset=['Mã chứng khoán', 'Loại báo cáo', 'Loại kỳ', 'Ngày kỳ', 'Chỉ tiêu tiếng Việt'])
        
        standard_cols = ['Mã chứng khoán', 'Tên doanh nghiệp', 'Tên ngành', 'Loại báo cáo', 'Loại kỳ', 'Năm', 'Ngày kỳ', 'Chỉ tiêu tiếng Việt', 'Giá trị']
        df_master = df_valid[standard_cols]
        df_master = df_master.sort_values(by=['Tên ngành', 'Mã chứng khoán', 'Loại báo cáo', 'Loại kỳ', 'Ngày kỳ'], ascending=[True, True, True, False, False])

    os.makedirs('data', exist_ok=True)
    csv_path = 'data/vietnam_stock_database_tong_hop.csv'
    df_master.to_csv(csv_path, index=False, encoding='utf-8-sig')
    
    print(f"==================================================")
    print(f" 🎉 HOÀN TẤT VÉT SẠCH & LÀM SẠCH DỮ LIỆU GỐC!")
    print(f" - Tổng số dòng dữ liệu: {len(df_master):,}")
    print(f" - Số mã: {len(df_master['Mã chứng khoán'].unique())}/242")
    print(f" - Kích thước file: {os.path.getsize(csv_path) / (1024 * 1024):.2f} MB")
    print(f"==================================================")

if __name__ == "__main__":
    main()
