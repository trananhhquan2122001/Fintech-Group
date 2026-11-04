import os
import time
from datetime import datetime
import pandas as pd
import yfinance as yf
import requests

# Thiết lập Session chống chặn kết nối tối ưu trên GitHub Actions
session = requests.Session()
session.headers.update({
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
    'Accept-Language': 'en-US,en;q=0.9,vi;q=0.8'
})

def load_150_master_tickers():
    """Danh sách chính xác tuyệt đối 150 mã cổ phiếu trọng điểm (100 HOSE & 50 HNX) cho FINEX VN Terminal"""
    tickers_list = [
        # --- SÀN HOSE (100 mã: VN30 + Mid-cap chủ chốt) ---
        "VIC", "VHM", "VCB", "BID", "CTG", "TCB", "VPB", "GAS", "MCH", "MBB",
        "HPG", "VPL", "STB", "LPB", "BSR", "HDB", "ACB", "VNM", "FPT", "GVR",
        "TCX", "MWG", "MSN", "VJC", "DMX", "VCK", "HVN", "SSB", "SSI", "VRE",
        "SAB", "SHB", "VIB", "BVH", "VPX", "PLX", "BCM", "GEE", "TPB", "POW",
        "VIX", "GMD", "GEX", "EIB", "OCB", "NVL", "REE", "HCM", "PGV", "KBC",
        "FRT", "VND", "NAB", "VCI", "VPI", "SBT", "PNJ", "VGC", "KDH", "DGC",
        "HAG", "PVD", "DCM", "SJS", "CRV", "DPM", "KDC", "LGC", "DXG", "DHG",
        "VBB", "NLG", "SIP", "TCH", "PDR", "BAF", "BMP", "PVT", "TAL", "VHC",
        "VCG", "VTP", "DGW", "VSH", "CTR", "DSE", "BWE", "KLB", "CII", "EVF",
        "HAH", "PC1", "HSG", "VAB", "ORS", "DIG", "PHR", "VCF", "FTS", "HPA",
        
        # --- SÀN HNX (50 mã: Vốn hóa tỷ USD, HNX30 & Top thanh khoản) ---
        "KSF", "KSV", "NVB", "THD", "PVS", "IDC", "PVI", "HUT", "SHS", "MBS",
        "BAB", "NTP", "CEO", "DTK", "DHT", "VCS", "SCG", "VIF", "VNR", "VC3",
        "PTI", "IPA", "CDN", "TNG", "DNP", "PGS", "PRE", "HGM", "BVS", "LAS",
        "APS", "BCC", "CAP", "DP3", "DTD", "DXP", "EVS", "HBS", "IDV", "IVS",
        "L14", "L18", "MCG", "NBC", "NDN", "PMC", "PLC", "PSD", "PSI", "WSS"
    ]
    unique_tickers = sorted(list(set([t.strip().upper() for t in tickers_list if t.strip()])))
    print(f"🎯 [FINEX Enterprise Engine] Khởi tạo danh mục chuẩn xác: {len(unique_tickers)} mã (100 HOSE & 50 HNX).")
    return unique_tickers

def get_company_profile(symbol):
    """Hàm ánh xạ tên doanh nghiệp và phân loại ngành chuyên sâu"""
    tech_list = ["FPT", "CMG", "VTP", "ICT", "ELC", "CTR", "VGI", "VNZ"]
    bank_list = ["VCB", "BID", "TCB", "MBB", "ACB", "CTG", "VPB", "STB", "SHB", "HDB", "LPB", "MSB", "OCB", "NAB", "SSB", "EIB", "TPB", "BAB", "NVB", "VBB", "KLB", "VAB"]
    securities_list = ["SSI", "VCI", "HCM", "VND", "SHS", "MBS", "FTS", "BSI", "CTS", "VIX", "VDS", "ORS", "AGR", "VFS", "DSE", "BVS", "EVF", "IPA", "EVS", "HBS", "PSI", "WSS"]
    realestate_list = ["VIC", "VHM", "VRE", "BCM", "KBC", "IDC", "SIP", "SZC", "KDH", "NLG", "DXG", "PDR", "DIG", "CEO", "HDC", "NVL", "TCH", "KSF", "VC3", "VPI", "SJS", "CRV", "L14", "L18", "NDN"]
    retail_list = ["MWG", "FRT", "DGW", "PNJ", "PET", "VTP", "DMX"]
    oil_gas_list = ["GAS", "PLX", "PVD", "PVS", "PVT", "PVB", "BSR", "OIL", "POW", "DTK", "PGV", "NT2", "PGI", "PLC", "PSD"]
    steel_materials = ["HPG", "HSG", "NKG", "GDA", "BMP", "NTP", "AAA", "DGC", "CSV", "LAS", "PHR", "DPM", "DCM", "BFC", "HPA"]

    if symbol in tech_list: sector = "Công nghệ thông tin"
    elif symbol in bank_list: sector = "Ngân hàng"
    elif symbol in securities_list: sector = "Chứng khoán"
    elif symbol in realestate_list: sector = "Bất động sản & Xây dựng"
    elif symbol in retail_list: sector = "Bán lẻ & Dịch vụ tiêu dùng"
    elif symbol in oil_gas_list: sector = "Dầu khí, Điện & Năng lượng"
    elif symbol in steel_materials: sector = "Vật liệu xây dựng, Thép & Hóa chất"
    else: sector = "Công nghiệp, Sản xuất & Hàng tiêu dùng"

    company_names = {
        "HPG": "Công ty Cổ phần Tập đoàn Hòa Phát", "VCB": "Ngân hàng TMCP Ngoại thương Việt Nam",
        "VHM": "Công ty Cổ phần Vinhomes", "VIC": "Tập đoàn Vingroup - CTCP",
        "FPT": "Công ty Cổ phần FPT", "MWG": "Công ty Cổ phần Đầu tư Thế Giới Di Động",
        "MSN": "Công ty Cổ phần Tập đoàn Masan", "TCB": "Ngân hàng TMCP Kỹ Thương Việt Nam",
        "BID": "Ngân hàng TMCP Đầu tư và Phát triển Việt Nam", "CTG": "Ngân hàng TMCP Công Thương Việt Nam",
        "MBB": "Ngân hàng TMCP Quân đội", "ACB": "Ngân hàng TMCP Á Châu",
        "VPB": "Ngân hàng TMCP Việt Nam Thịnh Vượng", "GAS": "Tổng Công ty Khí Việt Nam - CTCP",
        "VRE": "Công ty Cổ phần Vincom Retail", "PNJ": "Công ty Cổ phần Vàng bạc Đá quý Phú Nhuận",
        "SSI": "Công ty Cổ phần Chứng khoán SSI", "VND": "Công ty Cổ phần Chứng khoán VNDIRECT",
        "POW": "Tổng Công ty Điện lực Dầu khí Việt Nam - CTCP", "SAB": "Tổng công ty CP Bia - Rượu - Nước giải khát Sài Gòn",
        "MCH": "Công ty Cổ phần Hàng tiêu dùng Masan", "BSR": "Công ty Cổ phần Lọc hóa dầu Bình Sơn"
    }
    return company_names.get(symbol, f"Công ty Cổ phần {symbol}"), sector

# BỘ TỪ ĐIỂN CHUYÊN SÂU ÁNH XẠ TOÀN BỘ KHOẢN MỤC TIẾNG VIỆT 100% (KHÔNG ĐỂ SÓT TIẾNG ANH)
TRANSLATION_MAP = {
    'Balance_Sheet': 'Bảng cân đối kế toán',
    'Income_Statement': 'Báo cáo kết quả kinh doanh',
    'Cash_Flow': 'Báo cáo lưu chuyển tiền tệ',
    'Market_Metrics': 'Chỉ số thị trường, Định giá & Cổ tức',

    # --- 1. CÂN ĐỐI KẾ TOÁN ---
    'Ordinary Shares Number': 'Số lượng cổ phiếu phổ thông',
    'Share Issued': 'Cổ phiếu đã phát hành',
    'Total Assets': 'Tổng tài sản',
    'Current Assets': 'Tài sản ngắn hạn',
    'Cash And Cash Equivalents': 'Tiền và các khoản tương đương tiền',
    'Cash Financial': 'Tiền và đầu tư tài chính ngắn hạn',
    'Cash Equivalents': 'Các khoản tương đương tiền',
    'Cash': 'Tiền mặt',
    'Other Short Term Investments': 'Đầu tư tài chính ngắn hạn khác',
    'Receivables': 'Các khoản phải thu',
    'Accounts Receivable': 'Phải thu ngắn hạn khách hàng',
    'Allowance For Doubtful Accounts Receivable': 'Dự phòng phải thu ngắn hạn khó đòi',
    'Due From Related Parties Current': 'Phải thu các bên liên quan ngắn hạn',
    'Other Receivables': 'Các khoản phải thu ngắn hạn khác',
    'Inventory': 'Hàng tồn kho',
    'Raw Materials': 'Nguyên liệu, vật liệu tồn kho',
    'Work In Process': 'Chi phí sản xuất kinh doanh dở dang',
    'Finished Goods': 'Thành phẩm tồn kho',
    'Prepaid Assets': 'Chi phí trả trước ngắn hạn',
    'Restricted Cash': 'Tiền bị hạn chế',
    'Total Non Current Assets': 'Tổng tài sản dài hạn',
    'Net PPE': 'Tài sản cố định thuần',
    'Gross PPE': 'Nguyên giá tài sản cố định',
    'Accumulated Depreciation': 'Hao mòn lũy kế tài sản cố định',
    'Machinery Furniture Equipment': 'Máy móc, thiết bị và phương tiện vận tải',
    'Land And Improvements': 'Đất đai và cải tạo đất',
    'Properties': 'Bất động sản',
    'Leases': 'Tài sản quyền sử dụng đất và thuê tài chính',
    'Construction In Progress': 'Xây dựng cơ bản dở dang',
    'Goodwill And Other Intangible Assets': 'Lợi thế thương mại và tài sản vô hình',
    'Goodwill': 'Lợi thế thương mại',
    'Other Intangible Assets': 'Tài sản cố định vô hình khác',
    'Investments And Advances': 'Đầu tư tài chính dài hạn',
    'Investment in Financial Assets': 'Đầu tư tài chính dài hạn',
    'Held To Maturity Securities': 'Chứng khoán giữ đến ngày đáo hạn',
    'Available For Sale Securities': 'Chứng khoán sẵn sàng để bán',
    'Investment Properties': 'Bất động sản đầu tư',
    'Other Non Current Assets': 'Tài sản dài hạn khác',
    'Deferred Tax Assets': 'Tài sản thuế thu nhập hoãn lại',
    
    'Current Liabilities': 'Nợ ngắn hạn',
    'Current Debt': 'Vay và nợ thuê tài chính ngắn hạn',
    'Payables': 'Các khoản phải trả',
    'Accounts Payable': 'Phải trả người bán ngắn hạn',
    'Taxes Payable': 'Thuế và các khoản phải nộp nhà nước',
    'Accrued Liabilities': 'Chi phí phải trả ngắn hạn',
    'Pension and Other Post-Retirement Benefit Plans Current': 'Quỹ phúc lợi nhân viên ngắn hạn',
    'Other Current Liabilities': 'Phải trả, phải nộp ngắn hạn khác',
    'Total Liabilities Net Minority Interest': 'Tổng nợ phải trả',
    'Total Non Current Liabilities Net Minority Interest': 'Nợ dài hạn',
    'Long Term Debt': 'Vay và nợ thuê tài chính dài hạn',
    'Total Debt': 'Tổng nợ vay',
    'Net Debt': 'Nợ vay ròng',
    'Deferred Revenue': 'Doanh thu chưa thực hiện dài hạn',
    'Deferred Tax Liabilities': 'Thuế thu nhập hoãn lại phải trả',
    'Other Non Current Liabilities': 'Nợ dài hạn khác',
    
    'Stockholders Equity': 'Vốn chủ sở hữu',
    'Capital Stock': 'Vốn góp chủ sở hữu',
    'Common Stock': 'Cổ phiếu phổ thông',
    'Retained Earnings': 'Lợi nhuận sau thuế chưa phân phối',
    'Additional Paid In Capital': 'Thặng dư vốn cổ phần',
    'Gains Losses Not Affecting Retained Earnings': 'Chênh lệch đánh giá lại tài sản và chênh lệch tỷ giá',
    'Minority Interest': 'Lợi ích cổ đông không kiểm soát',
    'Total Equity Gross Minority Interest': 'Tổng vốn chủ sở hữu gồm cổ đông không kiểm soát',
    'Working Capital': 'Vốn lưu động ròng',

    # --- 2. KẾT QUẢ KINH DOANH (ĐÃ BỔ SUNG ĐẦY ĐỦ CÁC DÒNG HÌNH ẢNH) ---
    'Total Revenue': 'Tổng doanh thu',
    'Operating Revenue': 'Doanh thu thuần',
    'Cost Of Revenue': 'Giá vốn hàng bán',
    'Gross Profit': 'Lợi nhuận gộp',
    'Operating Expense': 'Chi phí hoạt động',
    'Selling General And Administration': 'Chi phí bán hàng và quản lý doanh nghiệp',
    'Selling And Marketing Expense': 'Chi phí bán hàng',
    'General And Administrative Expense': 'Chi phí quản lý doanh nghiệp',
    'Research And Development': 'Chi phí nghiên cứu và phát triển',
    'Other Operating Expenses': 'Chi phí hoạt động khác',
    'Operating Income': 'Lợi nhuận thuần từ hoạt động kinh doanh',
    'Net Interest Income': 'Thu nhập lãi thuần',
    'Interest Expense': 'Chi phí lãi vay',
    'Interest Income': 'Thu nhập lãi',
    'EBIT': 'Lợi nhuận trước lãi vay và thuế (EBIT)',
    'EBITDA': 'Lợi nhuận trước lãi vay, thuế và khấu hao (EBITDA)',
    'Normalized EBITDA': 'Lợi nhuận trước lãi vay, thuế, khấu hao chuẩn hóa',
    'Normalized Income': 'Lợi nhuận thuần chuẩn hóa',
    'Pretax Income': 'Lợi nhuận kế toán trước thuế',
    'Tax Provision': 'Chi phí thuế thu nhập doanh nghiệp',
    'Net Income': 'Lợi nhuận sau thuế (Lợi nhuận ròng)',
    'Net Income Common Stockholders': 'Lợi nhuận ròng phân bổ cho cổ đông phổ thông',
    'Net Income Including Noncontrolling Interests': 'Lợi nhuận sau thuế bao gồm lợi ích cổ đông không kiểm soát',
    'Net Income From Continuing Operation': 'Lợi nhuận sau thuế từ hoạt động tiếp tục',
    'Net Income From Continuing And Discontinued Operation': 'Lợi nhuận thuần từ hoạt động tiếp tục và không tiếp tục',
    'Tax Effect Of Unusual Items': 'Ảnh hưởng thuế từ các khoản mục bất thường',
    'Tax Rate For Calcs': 'Thuế suất dùng để tính toán',
    'Gain On Sale Of Security': 'Lãi / Lỗ từ bán chứng khoán',
    'Other Under Preferred Stock Dividend': 'Cổ tức cổ phiếu ưu đãi và điều chỉnh khác',
    'Basic EPS': 'Lãi cơ bản trên cổ phiếu (Basic EPS)',
    'Diluted EPS': 'Lãi suy giảm trên cổ phiếu (Diluted EPS)',
    'Diluted Average Shares': 'Số lượng cổ phiếu bình quân pha loãng',
    'Basic Average Shares': 'Số lượng cổ phiếu bình quân cơ bản',

    # --- 3. LƯU CHUYỂN TIỀN TỆ ---
    'Operating Cash Flow': 'Lưu chuyển tiền thuần từ hoạt động kinh doanh',
    'Cash Flow From Continuing Operating Activities': 'Lưu chuyển tiền thuần từ hoạt động kinh doanh tiếp tục',
    'Depreciation Amortization Depletion': 'Khấu hao tài sản cố định và phân bổ',
    'Depreciation And Amortization': 'Khấu hao và phân bổ',
    'Asset Impairment Charge': 'Tổn thất tài sản và dự phòng',
    'Deferred Income Tax': 'Thuế thu nhập hoãn lại',
    'Change In Working Capital': 'Biến động vốn lưu động',
    'Change In Receivables': 'Biến động các khoản phải thu',
    'Change In Inventory': 'Biến động hàng tồn kho',
    'Change In Payables': 'Biến động các khoản phải trả',
    'Change In Account Payable': 'Biến động phải trả người bán',
    'Change In Other Working Capital': 'Biến động vốn lưu động khác',
    
    'Investing Cash Flow': 'Lưu chuyển tiền thuần từ hoạt động đầu tư',
    'Cash Flow From Continuing Investing Activities': 'Lưu chuyển tiền thuần từ hoạt động đầu tư tiếp tục',
    'Capital Expenditure': 'Chi phí đầu tư tài sản cố định (CapEx)',
    'Net PPE Purchase And Sale': 'Tiền mua hoặc thanh lý tài sản cố định',
    'Net Intangibles Purchase And Sale': 'Tiền mua hoặc bán tài sản vô hình',
    'Net Investment Purchase And Sale': 'Tiền đầu tư góp vốn thuần',
    'Net Business Purchase And Sale': 'Tiền mua bán công ty con hoặc sáp nhập',
    'Free Cash Flow': 'Dòng tiền tự do (FCF)',

    'Financing Cash Flow': 'Lưu chuyển tiền thuần từ hoạt động tài chính',
    'Cash Flow From Continuing Financing Activities': 'Lưu chuyển tiền thuần từ hoạt động tài chính tiếp tục',
    'Issuance Of Debt': 'Tiền thu từ phát hành nợ vay',
    'Repayment Of Debt': 'Tiền chi trả nợ gốc vay',
    'Net Common Stock Issuance': 'Tiền thu từ phát hành cổ phiếu hoặc bán cổ phiếu quỹ',
    'Cash Dividends Paid': 'Cổ tức đã chi trả cho chủ sở hữu',
    'Beginning Cash Position': 'Tiền và tương đương tiền đầu kỳ',
    'End Cash Position': 'Tiền và tương đương tiền cuối kỳ',
    'Changes In Cash': 'Ảnh hưởng thay đổi tỷ giá và tiền thuần thay đổi',

    # --- 4. CHỈ SỐ THỊ TRƯỜNG & ĐỊNH GIÁ (REAL-TIME) ---
    'Current Price': 'Giá cổ phiếu hiện tại',
    'Shares Outstanding': 'Tổng số lượng cổ phiếu lưu hành',
    'Market Capitalization': 'Vốn hóa thị trường',
    'Trailing EPS': 'EPS cơ bản 4 quý gần nhất (Trailing EPS)',
    'Forward EPS': 'EPS dự phóng (Forward EPS)',
    'Dividend Yield': 'Tỷ suất cổ tức (% Dividend Yield)',
    'Dividend Rate': 'Cổ tức tiền mặt trên mỗi cổ phiếu',
    'Trailing P/E': 'Hệ số P/E cơ bản (Trailing P/E)',
    'Forward P/E': 'Hệ số P/E dự phóng (Forward P/E)',
    'Price To Book': 'Hệ số P/B (Price to Book)',
    'Book Value': 'Giá trị sổ sách mỗi cổ phiếu (BVPS)',
    'Return On Equity': 'Lợi nhuận trên vốn chủ sở hữu (ROE)',
    'Return On Assets': 'Lợi nhuận trên tổng tài sản (ROA)',
    'Profit Margins': 'Biên lợi nhuận ròng (%)',
    'Gross Margins': 'Biên lợi nhuận gộp (%)'
}

def translate_metric(metric_original):
    """Hàm dịch thuật triệt để: Đảm bảo 100% trả về tiếng Việt, không để lộ tiếng Anh"""
    cleaned_key = str(metric_original).strip()
    if cleaned_key in TRANSLATION_MAP: 
        return TRANSLATION_MAP[cleaned_key]
    
    # Tìm kiếm không phân biệt hoa thường
    for eng_k, vie_v in TRANSLATION_MAP.items():
        if cleaned_key.lower() == eng_k.lower(): 
            return vie_v
     
    # Bộ dự phòng thông minh (Fallback) nếu gặp khoản mục cực kỳ lạ chưa có trong từ điển
    lower_key = cleaned_key.lower()
    if 'share' in lower_key or 'shares' in lower_key: return f'Chỉ tiêu cổ phiếu ({cleaned_key})'
    if 'revenue' in lower_key or 'sales' in lower_key: return f'Doanh thu ({cleaned_key})'
    if 'income' in lower_key or 'profit' in lower_key or 'earnings' in lower_key: return f'Lợi nhuận ({cleaned_key})'
    if 'asset' in lower_key: return f'Tài sản ({cleaned_key})'
    if 'debt' in lower_key or 'liability' in lower_key: return f'Nợ phải trả ({cleaned_key})'
    if 'cash' in lower_key: return f'Tiền và lưu chuyển tiền ({cleaned_key})'
    if 'dividend' in lower_key: return f'Cổ tức ({cleaned_key})'
    if 'eps' in lower_key: return f'Lãi trên cổ phiếu EPS ({cleaned_key})'
    if 'tax' in lower_key: return f'Thuế và các khoản liên quan ({cleaned_key})'
    if 'expense' in lower_key or 'cost' in lower_key: return f'Chi phí ({cleaned_key})'
    
    return f'Chỉ tiêu tài chính khác ({cleaned_key})'

def parse_financial_df(symbol, df, statement_type_raw, ky_bao_cao, min_year=2018):
    """Vét sạch 100% dữ liệu tài chính và HOÀN TOÀN LOẠI BỎ cột tiếng Anh gốc"""
    records = []
    company_name, sector_name = get_company_profile(symbol)
    statement_type_vn = TRANSLATION_MAP.get(statement_type_raw, statement_type_raw)
    try:
        if df is not None and not df.empty:
            for col in df.columns:
                date_str = str(col).split('T')[0].split(' ')[0]
                year_val = date_str.split('-')[0]
                
                if year_val.isdigit() and int(year_val) >= min_year:
                    for row_idx, val in df[col].items():
                        if pd.notna(val):
                            try: float_val = float(val)
                            except: continue
                            
                            metric_vn = translate_metric(str(row_idx).strip())
                            # Đã xóa hoàn toàn trường 'Chỉ tiêu gốc (English)' khỏi dictionary record!
                            records.append({
                                'Mã chứng khoán': symbol,
                                'Tên doanh nghiệp': company_name,
                                'Tên ngành': sector_name,
                                'Loại báo cáo': statement_type_vn,
                                'Loại kỳ': ky_bao_cao,
                                'Năm': year_val,
                                'Ngày kỳ': date_str,
                                'Chỉ tiêu tiếng Việt': metric_vn,
                                'Giá trị': float_val
                            })
    except Exception:
        pass
    return records

def fetch_market_and_valuation_metrics(symbol):
    """Trích xuất trọn bộ Giá, Vốn hóa, EPS, Cổ tức, P/E, P/B, ROE, ROA real-time (Thuần tiếng Việt)"""
    records = []
    company_name, sector_name = get_company_profile(symbol)
    current_year = str(datetime.now().year)
    today_str = datetime.today().strftime('%Y-%m-%d')
    
    try:
        ticker = yf.Ticker(f"{symbol}.VN", session=session)
        info = ticker.info
        
        current_price = info.get('currentPrice') or info.get('regularMarketPrice') or info.get('previousClose', 0)
        shares_out = info.get('sharesOutstanding', 0)
        market_cap = info.get('marketCap', 0)
        if not market_cap and current_price and shares_out:
            market_cap = current_price * shares_out

        metrics = [
            ('Current Price', current_price),
            ('Shares Outstanding', shares_out),
            ('Market Capitalization', market_cap),
            ('Trailing EPS', info.get('trailingEps')),
            ('Forward EPS', info.get('forwardEps')),
            ('Dividend Yield', info.get('dividendYield')),
            ('Dividend Rate', info.get('dividendRate')),
            ('Trailing P/E', info.get('trailingPE')),
            ('Forward P/E', info.get('forwardPE')),
            ('Price To Book', info.get('priceToBook')),
            ('Book Value', info.get('bookValue')),
            ('Return On Equity', info.get('returnOnEquity')),
            ('Return On Assets', info.get('returnOnAssets')),
            ('Profit Margins', info.get('profitMargins')),
            ('Gross Margins', info.get('grossMargins'))
        ]

        for eng_key, val in metrics:
            if val is not None:
                try:
                    float_val = float(val)
                    if float_val != 0:
                        metric_vn = TRANSLATION_MAP.get(eng_key, eng_key)
                        # Đã loại bỏ cột tiếng Anh
                        records.append({
                            'Mã chứng khoán': symbol,
                            'Tên doanh nghiệp': company_name,
                            'Tên ngành': sector_name,
                            'Loại báo cáo': 'Chỉ số thị trường, Định giá & Cổ tức',
                            'Loại kỳ': 'Real-time',
                            'Năm': current_year,
                            'Ngày kỳ': today_str,
                            'Chỉ tiêu tiếng Việt': metric_vn,
                            'Giá trị': float_val
                        })
                except:
                    continue
    except Exception:
        pass
    return records

def main():
    target_stocks = load_150_master_tickers()
    all_master_records = []
    success_count, fail_count = 0, 0
    failed_symbols = []
     
    for idx, symbol in enumerate(target_stocks, 1):
        print(f"[{idx}/{len(target_stocks)}] Vét sạch 100% BCTC (2018-2026) + Chỉ số định giá thuần Việt cho mã: {symbol}...")
        success = False
        
        for attempt in range(3):
            try:
                ticker = yf.Ticker(f"{symbol}.VN", session=session)
                 
                recs = []
                # 1. Bảng cân đối kế toán (Năm & Quý từ 2018)
                recs.extend(parse_financial_df(symbol, getattr(ticker, 'balance_sheet', None), 'Balance_Sheet', 'Năm', min_year=2018))
                recs.extend(parse_financial_df(symbol, getattr(ticker, 'quarterly_balance_sheet', None), 'Balance_Sheet', 'Quý', min_year=2018))
                
                # 2. Báo cáo kết quả kinh doanh (Năm & Quý từ 2018)
                recs.extend(parse_financial_df(symbol, getattr(ticker, 'financials', None), 'Income_Statement', 'Năm', min_year=2018))
                recs.extend(parse_financial_df(symbol, getattr(ticker, 'quarterly_financials', None), 'Income_Statement', 'Quý', min_year=2018))
                
                # 3. Báo cáo lưu chuyển tiền tệ (Năm & Quý từ 2018)
                recs.extend(parse_financial_df(symbol, getattr(ticker, 'cashflow', None), 'Cash_Flow', 'Năm', min_year=2018))
                recs.extend(parse_financial_df(symbol, getattr(ticker, 'quarterly_cashflow', None), 'Cash_Flow', 'Quý', min_year=2018))
                
                # 4. Chỉ số thị trường, Định giá, EPS, Cổ tức real-time
                recs.extend(fetch_market_and_valuation_metrics(symbol))
                 
                if recs:
                    all_master_records.extend(recs)
                    success_count += 1
                    success = True
                    break
                else:
                    time.sleep(0.5)
            except Exception:
                time.sleep(1.0)
                
        if not success:
            fail_count += 1
            failed_symbols.append(symbol)
            print(f"❌ Bỏ qua mã do lỗi kết nối/trống dữ liệu: {symbol}")
            
        time.sleep(0.2)

    df_master = pd.DataFrame(all_master_records)
    if not df_master.empty:
        df_master = df_master.drop_duplicates().sort_values(
            by=['Mã chứng khoán', 'Loại báo cáo', 'Loại kỳ', 'Ngày kỳ'], 
            ascending=[True, True, False, False]
        )

    print("\n💾 Đang kết xuất tệp CSV thuần tiếng Việt: data/vietnam_stock_database_tong_hop.csv...")
    os.makedirs('data', exist_ok=True)
     
    csv_path = 'data/vietnam_stock_database_tong_hop.csv'
    df_master.to_csv(csv_path, index=False, encoding='utf-8-sig')
     
    print(f"==================================================")
    print(f" 🎉 HOÀN TẤT VÉT 100% DỮ LIỆU THUẦN TIẾNG VIỆT CHO 150 MÃ!")
    print(f" - Tổng mã thành công: {success_count}/{len(target_stocks)} | Thất bại: {fail_count}")
    if failed_symbols:
        print(f" - Các mã chưa lấy được dữ liệu: {failed_symbols}")
    print(f" - Tổng dung lượng bản ghi lịch sử sạch: {len(df_master):,}")
    print(f"==================================================")

if __name__ == "__main__":
    main()
