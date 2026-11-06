import os
import time
import re
from datetime import datetime
import pandas as pd
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed

# Tự động kiểm tra và cài đặt thư viện yfinance nếu chưa có
try:
    import yfinance as yf
except ImportError:
    print("⚙️ Đang cài đặt thư viện yfinance...")
    os.system("pip install yfinance --quiet")
    import yfinance as yf

# Thiết lập Session tối ưu kết nối mạng
session = requests.Session()
session.headers.update({
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
    'Accept-Language': 'en-US,en;q=0.9,vi;q=0.8'
})

# ==========================================
# 1. DANH SÁCH 242 MÃ CỔ PHIẾU
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
        "TMB", "SAF", "NET", "DHT",
        "DGC", "SZC", "HVN", "BAB", "AGR", "ICT", "TLH", "BMI", "PET", "LSS", 
        "HDC", "IJC", "TDC", "CTI", "SJD", "TMP", "SBA", "VSH", "TTA", "TV2", 
        "VCP", "BFC", "DDV", "VGT", "SGP", "DPR", "DHC", "TCM",
        # 42 mã UPCOM bổ sung
        "CKA", "VLB", "HPP", "WSB", "F88", "SEA", "ODE", "PHP", "VXB", "APF",
        "VNZ", "HLB", "TED", "VEF", "PAT", "FOC", "DTP", "SIV", "VGG", "AVC", 
        "LSG", "CQN", "QPH", "TCW", "ACE", "VSF", "HAM", "SBM", "AGP", "LIC", 
        "SCL", "CC1", "BWS", "NAS", "CLI", "VTK", "HMS", "PCC", "QHW", "MFS", 
        "VEC", "HEC"
    ]
    return {t.strip().upper(): "VIETNAM_MARKET" for t in raw_tickers if t.strip()}

# ==========================================
# 2. TỪ ĐIỂN DỊCH THUẬT CHUYÊN NGÀNH
# ==========================================
TRANSLATION_MAP = {
    'Balance_Sheet': 'Bảng cân đối kế toán', 'Income_Statement': 'Báo cáo kết quả kinh doanh',
    'Cash_Flow': 'Báo cáo lưu chuyển tiền tệ', 'Market_Metrics': 'Chỉ số thị trường, Định giá & Cổ tức',
    
    # Chỉ số thị trường & Định giá
    'Current Price': 'Giá cổ phiếu hiện tại', 'Shares Outstanding': 'Tổng số lượng cổ phiếu lưu hành',
    'Market Capitalization': 'Vốn hóa thị trường', 'Trailing EPS': 'EPS cơ bản 4 quý gần nhất (Trailing EPS)',
    'Forward EPS': 'EPS dự phóng (Forward EPS)', 'Dividend Yield': 'Tỷ suất cổ tức (% Dividend Yield)',
    'Dividend Rate': 'Cổ tức tiền mặt trên mỗi cổ phiếu', 'Trailing P/E': 'Hệ số P/E cơ bản (Trailing P/E)',
    'Forward P/E': 'Hệ số P/E dự phóng (Forward P/E)', 'Price To Book': 'Hệ số P/B (Price to Book)',
    'Book Value': 'Giá trị sổ sách mỗi cổ phiếu (BVPS)', 'Return On Equity': 'Lợi nhuận trên vốn chủ sở hữu (ROE)',
    'Return On Assets': 'Lợi nhuận trên tổng tài sản (ROA)', 'Profit Margins': 'Biên lợi nhuận ròng (%)',
    'Gross Margins': 'Biên lợi nhuận gộp (%)', 'Historical Dividend Cash': 'Lịch sử trả cổ tức bằng tiền (VND/Cổ phiếu)',

    # Bảng cân đối kế toán
    'Ordinary Shares Number': 'Số lượng cổ phiếu phổ thông', 'Share Issued': 'Cổ phiếu đã phát hành',
    'Total Assets': 'Tổng tài sản', 'Current Assets': 'Tài sản ngắn hạn', 
    'Cash And Cash Equivalents': 'Tiền và các khoản tương đương tiền', 'Cash Financial': 'Tiền và đầu tư tài chính ngắn hạn', 
    'Cash Equivalents': 'Các khoản tương đương tiền', 'Cash': 'Tiền mặt',
    'Other Short Term Investments': 'Đầu tư tài chính ngắn hạn khác', 'Receivables': 'Các khoản phải thu',
    'Accounts Receivable': 'Phải thu ngắn hạn khách hàng', 'Allowance For Doubtful Accounts Receivable': 'Dự phòng phải thu ngắn hạn khó đòi',
    'Due From Related Parties Current': 'Phải thu các bên liên quan ngắn hạn', 'Other Receivables': 'Các khoản phải thu ngắn hạn khác',
    'Inventory': 'Hàng tồn kho', 'Raw Materials': 'Nguyên liệu, vật liệu tồn kho', 'Work In Process': 'Chi phí sản xuất kinh doanh dở dang', 
    'Finished Goods': 'Thành phẩm tồn kho', 'Prepaid Assets': 'Chi phí trả trước ngắn hạn', 'Restricted Cash': 'Tiền bị hạn chế',
    'Total Non Current Assets': 'Tổng tài sản dài hạn', 'Net PPE': 'Tài sản cố định thuần', 'Gross PPE': 'Nguyên giá tài sản cố định', 
    'Accumulated Depreciation': 'Hao mòn lũy kế tài sản cố định', 'Machinery Furniture Equipment': 'Máy móc, thiết bị và phương tiện vận tải', 
    'Land And Improvements': 'Đất đai và cải tạo đất', 'Properties': 'Bất động sản', 'Leases': 'Tài sản quyền sử dụng đất và thuê tài chính',
    'Construction In Progress': 'Xây dựng cơ bản dở dang', 'Goodwill And Other Intangible Assets': 'Lợi thế thương mại và tài sản vô hình',
    'Goodwill': 'Lợi thế thương mại', 'Other Intangible Assets': 'Tài sản cố định vô hình khác', 'Investments And Advances': 'Đầu tư tài chính dài hạn', 
    'Investment in Financial Assets': 'Đầu tư tài chính dài hạn', 'Held To Maturity Securities': 'Chứng khoán giữ đến ngày đáo hạn', 
    'Available For Sale Securities': 'Chứng khoán sẵn sàng để bán', 'Investment Properties': 'Bất động sản đầu tư', 
    'Other Non Current Assets': 'Tài sản dài hạn khác', 'Deferred Tax Assets': 'Tài sản thuế thu nhập hoãn lại',
    'Current Liabilities': 'Nợ ngắn hạn', 'Current Debt': 'Vay và nợ thuê tài chính ngắn hạn', 'Payables': 'Các khoản phải trả', 
    'Accounts Payable': 'Phải trả người bán ngắn hạn', 'Taxes Payable': 'Thuế và các khoản phải nộp nhà nước', 
    'Accrued Liabilities': 'Chi phí phải trả ngắn hạn', 'Pension and Other Post-Retirement Benefit Plans Current': 'Quỹ phúc lợi nhân viên ngắn hạn',
    'Other Current Liabilities': 'Phải trả, phải nộp ngắn hạn khác', 'Total Liabilities Net Minority Interest': 'Tổng nợ phải trả',
    'Total Non Current Liabilities Net Minority Interest': 'Nợ dài hạn', 'Long Term Debt': 'Vay và nợ thuê tài chính dài hạn',
    'Total Debt': 'Tổng nợ vay', 'Net Debt': 'Nợ vay ròng', 'Deferred Revenue': 'Doanh thu chưa thực hiện dài hạn',
    'Deferred Tax Liabilities': 'Thuế thu nhập hoãn lại phải trả', 'Other Non Current Liabilities': 'Nợ dài hạn khác',
    'Stockholders Equity': 'Vốn chủ sở hữu', 'Capital Stock': 'Vốn góp chủ sở hữu', 'Common Stock': 'Cổ phiếu phổ thông',
    'Retained Earnings': 'Lợi nhuận sau thuế chưa phân phối', 'Additional Paid In Capital': 'Thặng dư vốn cổ phần',
    'Gains Losses Not Affecting Retained Earnings': 'Chênh lệch đánh giá lại tài sản và chênh lệch tỷ giá',
    'Minority Interest': 'Lợi ích cổ đông không kiểm soát', 'Total Equity Gross Minority Interest': 'Tổng vốn chủ sở hữu gồm cổ đông không kiểm soát',
    'Working Capital': 'Vốn lưu động ròng',

    # Báo cáo KQKD
    'Total Revenue': 'Tổng doanh thu', 'Operating Revenue': 'Doanh thu thuần',
    'Cost Of Revenue': 'Giá vốn hàng bán', 'Gross Profit': 'Lợi nhuận gộp', 'Operating Expense': 'Chi phí hoạt động', 
    'Selling General And Administration': 'Chi phí bán hàng và quản lý doanh nghiệp', 'Selling And Marketing Expense': 'Chi phí bán hàng', 
    'General And Administrative Expense': 'Chi phí quản lý doanh nghiệp', 'Research And Development': 'Chi phí nghiên cứu và phát triển', 
    'Other Operating Expenses': 'Chi phí hoạt động khác', 'Operating Income': 'Lợi nhuận thuần từ hoạt động kinh doanh', 
    'Net Interest Income': 'Thu nhập lãi thuần', 'Interest Expense': 'Chi phí lãi vay', 'Interest Income': 'Thu nhập lãi',
    'EBIT': 'Lợi nhuận trước lãi vay và thuế (EBIT)', 'EBITDA': 'Lợi nhuận trước lãi vay, thuế và khấu hao (EBITDA)',
    'Normalized EBITDA': 'Lợi nhuận trước lãi vay, thuế, khấu hao chuẩn hóa', 'Normalized Income': 'Lợi nhuận thuần chuẩn hóa', 
    'Pretax Income': 'Lợi nhuận kế toán trước thuế', 'Tax Provision': 'Chi phí thuế thu nhập doanh nghiệp', 
    'Net Income': 'Lợi nhuận sau thuế (Lợi nhuận ròng)', 'Net Income Common Stockholders': 'Lợi nhuận ròng phân bổ cho cổ đông phổ thông',
    'Net Income Including Noncontrolling Interests': 'Lợi nhuận sau thuế bao gồm lợi ích cổ đông không kiểm soát',
    'Net Income From Continuing Operation': 'Lợi nhuận sau thuế từ hoạt động tiếp tục', 
    'Net Income From Continuing And Discontinued Operation': 'Lợi nhuận thuần từ hoạt động tiếp tục và không tiếp tục',
    'Tax Effect Of Unusual Items': 'Ảnh hưởng thuế từ các khoản mục bất thường', 'Tax Rate For Calcs': 'Thuế suất dùng để tính toán', 
    'Gain On Sale Of Security': 'Lãi / Lỗ từ bán chứng khoán', 'Other Under Preferred Stock Dividend': 'Cổ tức cổ phiếu ưu đãi và điều chỉnh khác',
    'Basic EPS': 'Lãi cơ bản trên cổ phiếu (Basic EPS)', 'Diluted EPS': 'Lãi suy giảm trên cổ phiếu (Diluted EPS)',
    'Diluted Average Shares': 'Số lượng cổ phiếu bình quân pha loãng', 'Basic Average Shares': 'Số lượng cổ phiếu bình quân cơ bản',

    # Lưu chuyển tiền tệ
    'Operating Cash Flow': 'Lưu chuyển tiền thuần từ hoạt động kinh doanh', 
    'Cash Flow From Continuing Operating Activities': 'Lưu chuyển tiền thuần từ hoạt động kinh doanh tiếp tục',
    'Depreciation Amortization Depletion': 'Khấu hao tài sản cố định và phân bổ', 'Depreciation And Amortization': 'Khấu hao và phân bổ', 
    'Asset Impairment Charge': 'Tổn thất tài sản và dự phòng', 'Deferred Income Tax': 'Thuế thu nhập hoãn lại', 
    'Change In Working Capital': 'Biến động vốn lưu động', 'Change In Receivables': 'Biến động các khoản phải thu', 
    'Change In Inventory': 'Biến động hàng tồn kho', 'Change In Payables': 'Biến động các khoản phải trả', 
    'Change In Account Payable': 'Biến động phải trả người bán', 'Change In Other Working Capital': 'Biến động vốn lưu động khác',
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
    'End Cash Position': 'Tiền và tương đương tiền cuối kỳ', 'Changes In Cash': 'Ảnh hưởng thay đổi tỷ giá và tiền thuần thay đổi'
}

# ==========================================
# 3. HÀM DỊCH THÔNG MINH (Dịch 100% sang tiếng Việt)
# ==========================================
def translate_metric(metric_original):
    cleaned_key = str(metric_original).strip()
    
    # 1. Tra từ điển chính xác
    if cleaned_key in TRANSLATION_MAP: 
        return TRANSLATION_MAP[cleaned_key]
    
    # 2. Tra không phân biệt hoa thường
    for eng_k, vie_v in TRANSLATION_MAP.items():
        if cleaned_key.lower() == eng_k.lower(): 
            return vie_v
            
    # 3. Tách chữ CamelCase (VD: NetIncome -> Net Income)
    split_key = re.sub(r'(?<!^)(?=[A-Z])', ' ', cleaned_key)
    if split_key in TRANSLATION_MAP: 
        return TRANSLATION_MAP[split_key]
    
    # 4. Dịch theo từ khóa (Keyword Matching)
    k_lower = split_key.lower()
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

    # 5. Fallback cuối cùng
    return f"Chỉ tiêu tài chính khác: {split_key}"

# ==========================================
# 4. HÀM LÀM SẠCH DỮ LIỆU BẰNG PANDAS
# ==========================================
def clean_data_pipeline(df):
    if df.empty:
        return df
        
    print("🧹 Đang làm sạch dữ liệu tự động bằng Pandas...")
    
    # 1. Xóa trùng lặp (Giữ lại dựa trên Mã, Báo cáo, Ngày và Chỉ tiêu GỐC để không mất dòng)
    df = df.drop_duplicates(subset=['Mã chứng khoán', 'Loại báo cáo', 'Loại kỳ', 'Ngày kỳ', 'Chỉ tiêu gốc (English)'])
    
    # 2. Ép kiểu cột Giá trị sang số thực (Xử lý dấu phẩy và chuỗi lỗi)
    df['Giá trị'] = pd.to_numeric(df['Giá trị'].astype(str).str.replace(',', ''), errors='coerce')
    
    # 3. Loại bỏ NaN, Vô cực
    df = df[df['Giá trị'].notna()]
    df = df[~df['Giá trị'].isin([float('inf'), float('-inf')])]
    
    # 4. Sắp xếp
    df = df.sort_values(by=['Tên ngành', 'Mã chứng khoán', 'Loại báo cáo', 'Loại kỳ', 'Ngày kỳ'], ascending=[True, True, True, False, False])
    return df.reset_index(drop=True)

# ==========================================
# 5. CÁC HÀM CÀO DỮ LIỆU CHÍNH
# ==========================================
def get_company_profile(symbol):
    # Rút gọn để code chạy mượt, tự động gán ngành và tên nếu chưa cập nhật
    return f"Công ty Cổ phần {symbol}", "Chưa phân loại (Cập nhật sau)"

def parse_financial_df(symbol, df, statement_type_raw, ky_bao_cao, min_year=2020):
    records = []
    company_name, sector_name = get_company_profile(symbol)
    statement_type_vn = TRANSLATION_MAP.get(statement_type_raw, statement_type_raw)
    
    if df is not None and not df.empty:
        for col in df.columns:
            date_str = str(col).split('T')[0].split(' ')[0]
            year_val = date_str.split('-')[0]
            
            if year_val.isdigit() and int(year_val) >= min_year:
                for row_idx, val in df[col].items():
                    if pd.notna(val):
                        eng_metric = str(row_idx).strip()
                        metric_vn = translate_metric(eng_metric) # Dịch ngay lập tức
                        
                        records.append({
                            'Mã chứng khoán': symbol, 'Tên doanh nghiệp': company_name,
                            'Tên ngành': sector_name, 'Loại báo cáo': statement_type_vn,
                            'Loại kỳ': ky_bao_cao, 'Năm': year_val, 'Ngày kỳ': date_str,
                            'Chỉ tiêu gốc (English)': eng_metric, # Lưu gốc để check
                            'Chỉ tiêu tiếng Việt': metric_vn, 
                            'Giá trị': val
                        })
    return records

def process_single_ticker(symbol, category):
    recs = []
    suffixes = [".VN", ".HN", ".UPCOM", ".HA", ".HM", ""]
    success = False

    for suffix in suffixes:
        if success: break
        full_ticker = f"{symbol}{suffix}"
        for attempt in range(2):
            try:
                ticker = yf.Ticker(full_ticker, session=session)
                bs_df = getattr(ticker, 'balance_sheet', None)
                
                # Cào BCTC (Năm & Quý)
                recs.extend(parse_financial_df(symbol, bs_df, 'Balance_Sheet', 'Năm'))
                recs.extend(parse_financial_df(symbol, getattr(ticker, 'quarterly_balance_sheet', None), 'Balance_Sheet', 'Quý'))
                recs.extend(parse_financial_df(symbol, getattr(ticker, 'financials', None), 'Income_Statement', 'Năm'))
                recs.extend(parse_financial_df(symbol, getattr(ticker, 'quarterly_financials', None), 'Income_Statement', 'Quý'))
                recs.extend(parse_financial_df(symbol, getattr(ticker, 'cashflow', None), 'Cash_Flow', 'Năm'))
                recs.extend(parse_financial_df(symbol, getattr(ticker, 'quarterly_cashflow', None), 'Cash_Flow', 'Quý'))
                
                # Cào Chỉ số thị trường
                info = ticker.info if ticker else {}
                current_price = info.get('currentPrice') or info.get('regularMarketPrice') or info.get('previousClose') or 0.0
                shares_out = info.get('sharesOutstanding', 0.0)
                market_cap = info.get('marketCap', 0.0)
                
                if (not current_price) and ticker:
                    hist = ticker.history(period="1y")
                    if not hist.empty: current_price = float(hist['Close'].iloc[-1])
                if (not market_cap) and current_price > 0 and shares_out > 0:
                    market_cap = current_price * shares_out

                current_year = str(datetime.now().year)
                today_str = datetime.today().strftime('%Y-%m-%d')
                company_name, sector_name = get_company_profile(symbol)
                
                metrics = [
                    ('Current Price', current_price), ('Shares Outstanding', shares_out),
                    ('Market Capitalization', market_cap), ('Trailing EPS', info.get('trailingEps')),
                    ('Forward EPS', info.get('forwardEps')), ('Dividend Yield', info.get('dividendYield')),
                    ('Trailing P/E', info.get('trailingPE')), ('Forward P/E', info.get('forwardPE')), 
                    ('Price To Book', info.get('priceToBook')), ('Book Value', info.get('bookValue')), 
                    ('Return On Equity', info.get('returnOnEquity')), ('Return On Assets', info.get('returnOnAssets')), 
                    ('Profit Margins', info.get('profitMargins')), ('Gross Margins', info.get('grossMargins'))
                ]

                for eng_key, val in metrics:
                    recs.append({
                        'Mã chứng khoán': symbol, 'Tên doanh nghiệp': company_name,
                        'Tên ngành': sector_name, 'Loại báo cáo': 'Chỉ số thị trường, Định giá & Cổ tức',
                        'Loại kỳ': 'Real-time', 'Năm': current_year, 'Ngày kỳ': today_str,
                        'Chỉ tiêu gốc (English)': eng_key,
                        'Chỉ tiêu tiếng Việt': TRANSLATION_MAP.get(eng_key, eng_key), 
                        'Giá trị': val if val is not None else 0.0
                    })
                 
                if recs:
                    success = True
                    break
            except Exception:
                time.sleep(0.2)
    return recs

# ==========================================
# 6. CHẠY CHƯƠNG TRÌNH CHÍNH
# ==========================================
def main():
    ticker_market_map = load_242_master_tickers()
    all_master_records = []
    success_count = 0

    total_tickers = len(ticker_market_map)
    print(f"🚀 Bắt đầu cào dữ liệu sạch cho {total_tickers} mã cổ phiếu...")

    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = {executor.submit(process_single_ticker, symbol, cat): symbol for symbol, cat in ticker_market_map.items()}
        
        for future in as_completed(futures):
            symbol = futures[future]
            try:
                res = future.result()
                if res:
                    all_master_records.extend(res)
                    success_count += 1
                    print(f"[{success_count}/{total_tickers}] Đã cào & dịch xong: {symbol} ({len(res)} dòng)")
            except Exception:
                pass

    print(f"\n📊 Tổng hợp được {len(all_master_records):,} dòng dữ liệu thô.")
    print("⏳ Đang chạy Pipeline làm sạch dữ liệu...")
    
    df_raw = pd.DataFrame(all_master_records)
    df_clean = clean_data_pipeline(df_raw)

    print("\n💾 Đang lưu vào Cơ sở dữ liệu (File CSV)...")
    os.makedirs('data', exist_ok=True)
    csv_path = 'data/database_242_ma_cleaned.csv'
    df_clean.to_csv(csv_path, index=False, encoding='utf-8-sig')
     
    print(f"==================================================")
    print(f" 🎉 HOÀN TẤT TOÀN DIỆN!")
    print(f" - Số mã thành công: {success_count}/{total_tickers}")
    print(f" - Dữ liệu thô ban đầu: {len(df_raw):,} dòng")
    print(f" - Dữ liệu sạch sau khi xử lý: {len(df_clean):,} dòng")
    print(f" - File lưu trữ: {csv_path}")
    print(f"==================================================")

if __name__ == "__main__":
    main()
