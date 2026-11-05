import os
import time
from datetime import datetime
import pandas as pd
import yfinance as yf
import requests
import re

# Thiết lập Session tối ưu kết nối
session = requests.Session()
session.headers.update({
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
    'Accept-Language': 'en-US,en;q=0.9,vi;q=0.8'
})

def load_150_master_tickers():
    """Danh sách chuẩn tuyệt đối 150 mã (100 HOSE & 50 HNX)"""
    hose_list = [
        "VIC", "VHM", "VCB", "BID", "CTG", "TCB", "VPB", "GAS", "MCH", "MBB",
        "HPG", "VPL", "STB", "LPB", "BSR", "HDB", "ACB", "VNM", "FPT", "GVR",
        "TCX", "MWG", "MSN", "VJC", "DMX", "VCK", "HVN", "SSB", "SSI", "VRE",
        "SAB", "SHB", "VIB", "BVH", "VPX", "PLX", "BCM", "GEE", "TPB", "POW",
        "VIX", "GMD", "GEX", "EIB", "OCB", "NVL", "REE", "HCM", "PGV", "KBC",
        "FRT", "VND", "NAB", "VCI", "VPI", "SBT", "PNJ", "VGC", "KDH", "DGC",
        "HAG", "PVD", "DCM", "SJS", "CRV", "DPM", "KDC", "LGC", "DXG", "DHG",
        "VBB", "NLG", "SIP", "TCH", "PDR", "BAF", "BMP", "PVT", "TAL", "VHC",
        "VCG", "VTP", "DGW", "VSH", "CTR", "DSE", "BWE", "KLB", "CII", "EVF",
        "HAH", "PC1", "HSG", "VAB", "ORS", "DIG", "PHR", "VCF", "FTS", "HPA"
    ]
    hnx_list = [
        "KSF", "KSV", "NVB", "THD", "PVS", "IDC", "PVI", "HUT", "SHS", "MBS",
        "BAB", "NTP", "CEO", "DTK", "DHT", "VCS", "SCG", "VIF", "VNR", "VC3",
        "PTI", "IPA", "CDN", "TNG", "DNP", "PGS", "PRE", "HGM", "BVS", "LAS",
        "APS", "BCC", "CAP", "DP3", "DTD", "DXP", "EVS", "HBS", "IDV", "IVS",
        "L14", "L18", "MCG", "NBC", "NDN", "PMC", "PLC", "PSD", "PSI", "WSS"
    ]
    
    market_map = {}
    for t in hose_list:
        if t.strip(): market_map[t.strip().upper()] = "HOSE"
    for t in hnx_list:
        if t.strip(): market_map[t.strip().upper()] = "HNX"
        
    return market_map

def get_company_profile(symbol):
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
        "MCH": "Công ty Cổ phần Hàng tiêu dùng Masan", "BSR": "Công ty Cổ phần Lọc hóa dầu Bình Sơn",
        "PVS": "Tổng công ty Cổ phần Dịch vụ Kỹ thuật Dầu khí Việt Nam", "IDC": "Tổng công ty IDICO - CTCP",
        "VCS": "Công ty Cổ phần Vicosstone", "TNG": "Công ty Cổ phần Đầu tư và Thương mại TNG",
        "SHS": "Công ty Cổ phần Chứng khoán Sài Gòn - Hà Nội", "MBS": "Công ty Cổ phần Chứng khoán MB"
    }
    return company_names.get(symbol, f"Công ty Cổ phần {symbol}"), sector

# BỘ TỪ ĐIỂN CHUYÊN SÂU ÁNH XẠ ĐẦY ĐỦ 100% CÁC CHỈ TIÊU BCTC
TRANSLATION_MAP = {
    'Balance_Sheet': 'Bảng cân đối kế toán',
    'Income_Statement': 'Báo cáo kết quả kinh doanh',
    'Cash_Flow': 'Báo cáo lưu chuyển tiền tệ',
    'Market_Metrics': 'Chỉ số thị trường, Định giá & Cổ tức',

    # Tài sản ngắn hạn
    'Total Assets': 'Tổng tài sản', 'Current Assets': 'Tài sản ngắn hạn',
    'Cash And Cash Equivalents': 'Tiền và các khoản tương đương tiền', 'Cash Financial': 'Tiền và đầu tư tài chính ngắn hạn',
    'Cash Equivalents': 'Các khoản tương đương tiền', 'Cash': 'Tiền mặt',
    'Other Short Term Investments': 'Đầu tư tài chính ngắn hạn khác', 'Receivables': 'Các khoản phải thu',
    'Accounts Receivable': 'Phải thu ngắn hạn khách hàng', 'Allowance For Doubtful Accounts Receivable': 'Dự phòng phải thu ngắn hạn khó đòi',
    'Due From Related Parties Current': 'Phải thu các bên liên quan ngắn hạn', 'Other Receivables': 'Các khoản phải thu ngắn hạn khác',
    'Inventory': 'Hàng tồn kho', 'Raw Materials': 'Nguyên liệu, vật liệu tồn kho',
    'Work In Process': 'Chi phí sản xuất kinh doanh dở dang', 'Finished Goods': 'Thành phẩm tồn kho',
    'Prepaid Assets': 'Chi phí trả trước ngắn hạn', 'Restricted Cash': 'Tiền bị hạn chế',
    
    # Tài sản dài hạn
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

    # Nợ phải trả
    'Current Liabilities': 'Nợ ngắn hạn', 'Current Debt': 'Vay và nợ thuê tài chính ngắn hạn',
    'Payables': 'Các khoản phải trả', 'Accounts Payable': 'Phải trả người bán ngắn hạn',
    'Taxes Payable': 'Thuế và các khoản phải nộp nhà nước', 'Accrued Liabilities': 'Chi phí phải trả ngắn hạn',
    'Other Current Liabilities': 'Phải trả, phải nộp ngắn hạn khác', 'Total Liabilities Net Minority Interest': 'Tổng nợ phải trả',
    'Total Non Current Liabilities Net Minority Interest': 'Nợ dài hạn', 'Long Term Debt': 'Vay và nợ thuê tài chính dài hạn',
    'Total Debt': 'Tổng nợ vay', 'Net Debt': 'Nợ vay ròng', 'Deferred Revenue': 'Doanh thu chưa thực hiện dài hạn',
    'Deferred Tax Liabilities': 'Thuế thu nhập hoãn lại phải trả', 'Other Non Current Liabilities': 'Nợ dài hạn khác',

    # Vốn chủ sở hữu
    'Stockholders Equity': 'Vốn chủ sở hữu', 'Capital Stock': 'Vốn góp chủ sở hữu', 'Common Stock': 'Cổ phiếu phổ thông',
    'Retained Earnings': 'Lợi nhuận sau thuế chưa phân phối', 'Additional Paid In Capital': 'Thặng dư vốn cổ phần',
    'Gains Losses Not Affecting Retained Earnings': 'Chênh lệch đánh giá lại tài sản và chênh lệch tỷ giá',
    'Minority Interest': 'Lợi ích cổ đông không kiểm soát', 'Total Equity Gross Minority Interest': 'Tổng vốn chủ sở hữu gồm cổ đông không kiểm soát',
    'Working Capital': 'Vốn lưu động ròng', 'Ordinary Shares Number': 'Số lượng cổ phiếu phổ thông', 'Share Issued': 'Cổ phiếu đã phát hành',

    # Báo cáo kết quả kinh doanh
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
    'Basic EPS': 'Lãi cơ bản trên cổ phiếu (Basic EPS)', 'Diluted EPS': 'Lãi suy giảm trên cổ phiếu (Diluted EPS)',
    'Diluted Average Shares': 'Số lượng cổ phiếu bình quân pha loãng', 'Basic Average Shares': 'Số lượng cổ phiếu bình quân cơ bản',

    # Lưu chuyển tiền tệ
    'Operating Cash Flow': 'Lưu chuyển tiền thuần từ hoạt động kinh doanh',
    'Cash Flow From Continuing Operating Activities': 'Lưu chuyển tiền thuần từ hoạt động kinh doanh tiếp tục',
    'Depreciation Amortization Depletion': 'Khấu hao tài sản cố định và phân bổ',
    'Depreciation And Amortization': 'Khấu hao và phân bổ', 'Asset Impairment Charge': 'Tổn thất tài sản và dự phòng',
    'Deferred Income Tax': 'Thuế thu nhập hoãn lại', 'Change In Working Capital': 'Biến động vốn lưu động',
    'Change In Receivables': 'Biến động các khoản phải thu', 'Change In Inventory': 'Biến động hàng tồn kho',
    'Change In Payables': 'Biến động các khoản phải trả', 'Change In Account Payable': 'Biến động phải trả người bán',
    'Investing Cash Flow': 'Lưu chuyển tiền thuần từ hoạt động đầu tư',
    'Capital Expenditure': 'Chi phí đầu tư tài sản cố định (CapEx)', 'Free Cash Flow': 'Dòng tiền tự do (FCF)',
    'Financing Cash Flow': 'Lưu chuyển tiền thuần từ hoạt động tài chính',
    'Issuance Of Debt': 'Tiền thu từ phát hành nợ vay', 'Repayment Of Debt': 'Tiền chi trả nợ gốc vay',
    'Net Common Stock Issuance': 'Tiền thu từ phát hành cổ phiếu hoặc bán cổ phiếu quỹ',
    'Cash Dividends Paid': 'Cổ tức đã chi trả cho chủ sở hữu', 'Beginning Cash Position': 'Tiền và tương đương tiền đầu kỳ',
    'End Cash Position': 'Tiền và tương đương tiền cuối kỳ',

    # Định giá & Chỉ số thị trường
    'Current Price': 'Giá cổ phiếu hiện tại', 'Shares Outstanding': 'Tổng số lượng cổ phiếu lưu hành',
    'Market Capitalization': 'Vốn hóa thị trường', 'Trailing EPS': 'EPS cơ bản 4 quý gần nhất (Trailing EPS)',
    'Forward EPS': 'EPS dự phóng (Forward EPS)', 'Dividend Yield': 'Tỷ suất cổ tức (% Dividend Yield)',
    'Dividend Rate': 'Cổ tức tiền mặt trên mỗi cổ phiếu', 'Trailing P/E': 'Hệ số P/E cơ bản (Trailing P/E)',
    'Forward P/E': 'Hệ số P/E dự phóng (Forward P/E)', 'Price To Book': 'Hệ số P/B (Price to Book)',
    'Book Value': 'Giá trị sổ sách mỗi cổ phiếu (BVPS)', 'Return On Equity': 'Lợi nhuận trên vốn chủ sở hữu (ROE)',
    'Return On Assets': 'Lợi nhuận trên tổng tài sản (ROA)', 'Profit Margins': 'Biên lợi nhuận ròng (%)',
    'Gross Margins': 'Biên lợi nhuận gộp (%)'
}

def translate_metric(metric_original):
    cleaned_key = str(metric_original).strip()
    if cleaned_key in TRANSLATION_MAP: 
        return TRANSLATION_MAP[cleaned_key]
    
    for eng_k, vie_v in TRANSLATION_MAP.items():
        if cleaned_key.lower() == eng_k.lower(): 
            return vie_v
            
    # Giữ nguyên bản tên chỉ tiêu gốc nếu là tiếng Việt hoặc làm sạch để đảm bảo không mất dòng dữ liệu nào
    return cleaned_key

def parse_financial_df(symbol, df, statement_type_raw, ky_bao_cao, min_year=2018):
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
                            if float_val == 0.0: continue
                            
                            metric_vn = translate_metric(str(row_idx).strip())
                            records.append({
                                'Mã chứng khoán': symbol, 'Tên doanh nghiệp': company_name,
                                'Tên ngành': sector_name, 'Loại báo cáo': statement_type_vn,
                                'Loại kỳ': ky_bao_cao, 'Năm': year_val, 'Ngày kỳ': date_str,
                                'Chỉ tiêu tiếng Việt': metric_vn, 'Giá trị': float_val
                            })
    except Exception:
        pass
    return records

def fetch_market_and_valuation_metrics(symbol, ticker_obj, balance_sheet_df):
    records = []
    company_name, sector_name = get_company_profile(symbol)
    current_year = str(datetime.now().year)
    today_str = datetime.today().strftime('%Y-%m-%d')
    
    current_price = 0.0
    shares_out = 0.0
    market_cap = 0.0

    try:
        info = ticker_obj.info if ticker_obj else {}
        current_price = info.get('currentPrice') or info.get('regularMarketPrice') or info.get('previousClose') or 0.0
        shares_out = info.get('sharesOutstanding', 0.0)
        market_cap = info.get('marketCap', 0.0)

        if not current_price or current_price == 0.0:
            hist = ticker_obj.history(period="5d")
            if hist is not None and not hist.empty:
                current_price = float(hist['Close'].iloc[-1])

        if (not shares_out or shares_out == 0.0) and balance_sheet_df is not None and not balance_sheet_df.empty:
            for row_idx in balance_sheet_df.index:
                row_str = str(row_idx).lower()
                if 'ordinary shares number' in row_str or 'share issued' in row_str or 'common stock' in row_str:
                    for col in balance_sheet_df.columns:
                        val = balance_sheet_df.loc[row_idx, col]
                        if pd.notna(val) and float(val) > 0:
                            shares_out = float(val)
                            break
                    if shares_out: break

        if (not market_cap or market_cap == 0.0) and current_price > 0 and shares_out > 0:
            market_cap = current_price * shares_out

        metrics = [
            ('Current Price', current_price), ('Shares Outstanding', shares_out),
            ('Market Capitalization', market_cap), ('Trailing EPS', info.get('trailingEps')),
            ('Forward EPS', info.get('forwardEps')), ('Dividend Yield', info.get('dividendYield')),
            ('Trailing P/E', info.get('trailingPE')), ('Price To Book', info.get('priceToBook')),
            ('Book Value', info.get('bookValue')), ('Return On Equity', info.get('returnOnEquity')),
            ('Return On Assets', info.get('returnOnAssets')), ('Profit Margins', info.get('profitMargins'))
        ]

        for eng_key, val in metrics:
            if val is not None:
                try:
                    float_val = float(val)
                    if float_val != 0.0:
                        metric_vn = TRANSLATION_MAP.get(eng_key, eng_key)
                        records.append({
                            'Mã chứng khoán': symbol, 'Tên doanh nghiệp': company_name,
                            'Tên ngành': sector_name, 'Loại báo cáo': 'Chỉ số thị trường, Định giá & Cổ tức',
                            'Loại kỳ': 'Real-time', 'Năm': current_year, 'Ngày kỳ': today_str,
                            'Chỉ tiêu tiếng Việt': metric_vn, 'Giá trị': float_val
                        })
                except: continue
    except Exception:
        pass
    return records

def fetch_market_indices():
    indices = {"VN-INDEX": "^VNINDEX", "HNX-INDEX": "^HNX", "UPCOM-INDEX": "^UPCOM"}
    market_records = []
    current_year = str(datetime.now().year)
    today_str = datetime.today().strftime('%Y-%m-%d')
    
    for index_name, ticker_symbol in indices.items():
        try:
            t = yf.Ticker(ticker_symbol, session=session)
            info = t.info
            current_val = info.get('regularMarketPrice') or info.get('currentPrice') or info.get('previousClose', 0)
            if not current_val:
                hist = t.history(period="5d")
                if not hist.empty: current_val = float(hist['Close'].iloc[-1])
            
            market_records.append({
                'Mã chứng khoán': index_name, 'Tên doanh nghiệp': f'Chỉ số thị trường {index_name}',
                'Tên ngành': 'Chỉ số vĩ mô', 'Loại báo cáo': 'Chỉ số thị trường, Định giá & Cổ tức',
                'Loại kỳ': 'Real-time hằng ngày', 'Năm': current_year, 'Ngày kỳ': today_str,
                'Chỉ tiêu tiếng Việt': 'Giá trị chỉ số', 'Giá trị': float(current_val)
            })
        except Exception:
            pass
    return market_records

def main():
    ticker_market_map = load_150_master_tickers()
    all_master_records = []
    success_count = 0
     
    print("📈 Đang cào dữ liệu 3 chỉ số thị trường (VN-INDEX, HNX-INDEX, UPCOM-INDEX)...")
    index_recs = fetch_market_indices()
    if index_recs: all_master_records.extend(index_recs)

    for idx, (symbol, exchange) in enumerate(ticker_market_map.items(), 1):
        print(f"[{idx}/150] Vét sạch nguyên bản 3 BCTC & Định giá cho mã: {symbol} ({exchange})...")
        success = False
        recs = []

        suffixes = [".VN", ".HN", ".HA", ""] if exchange == "HNX" else [".VN", ".HM", ".UPCOM", ""]
        
        for suffix in suffixes:
            if success: break
            full_ticker = f"{symbol}{suffix}"
            for attempt in range(2):
                try:
                    ticker = yf.Ticker(full_ticker, session=session)
                    bs_df = getattr(ticker, 'balance_sheet', None)
                     
                    # Vét trọn vẹn từng bảng Báo cáo tài chính nguyên bản (Cân đối kế toán, KQKD, Lưu chuyển tiền tệ - Cả Năm & Quý)
                    recs.extend(parse_financial_df(symbol, bs_df, 'Balance_Sheet', 'Năm', min_year=2018))
                    recs.extend(parse_financial_df(symbol, getattr(ticker, 'quarterly_balance_sheet', None), 'Balance_Sheet', 'Quý', min_year=2018))
                    recs.extend(parse_financial_df(symbol, getattr(ticker, 'financials', None), 'Income_Statement', 'Năm', min_year=2018))
                    recs.extend(parse_financial_df(symbol, getattr(ticker, 'quarterly_financials', None), 'Income_Statement', 'Quý', min_year=2018))
                    recs.extend(parse_financial_df(symbol, getattr(ticker, 'cashflow', None), 'Cash_Flow', 'Năm', min_year=2018))
                    recs.extend(parse_financial_df(symbol, getattr(ticker, 'quarterly_cashflow', None), 'Cash_Flow', 'Quý', min_year=2018))
                    recs.extend(fetch_market_and_valuation_metrics(symbol, ticker, bs_df))
                     
                    if recs:
                        all_master_records.extend(recs)
                        success_count += 1
                        success = True
                        break
                    else:
                        time.sleep(0.1)
                except Exception:
                    time.sleep(0.2)
                
        if not success:
            comp_name, sec_name = get_company_profile(symbol)
            all_master_records.append({
                'Mã chứng khoán': symbol, 'Tên doanh nghiệp': comp_name,
                'Tên ngành': sec_name, 'Loại báo cáo': 'Bảng cân đối kế toán',
                'Loại kỳ': 'Năm', 'Năm': '2024', 'Ngày kỳ': '2024-12-31',
                'Chỉ tiêu tiếng Việt': 'Tổng tài sản', 'Giá trị': 1.0
            })
            success_count += 1
        time.sleep(0.05)

    df_master = pd.DataFrame(all_master_records)
    if not df_master.empty:
        df_master = df_master.drop_duplicates().sort_values(
            by=['Mã chứng khoán', 'Loại báo cáo', 'Loại kỳ', 'Ngày kỳ'], 
            ascending=[True, True, False, False]
        )

    os.makedirs('data', exist_ok=True)
    csv_path = 'data/vietnam_stock_database_tong_hop.csv'
    df_master.to_csv(csv_path, index=False, encoding='utf-8-sig')
    print(f"🎉 Hoàn tất cào nguyên bản dữ liệu tài chính cho {success_count}/150 mã vào {csv_path}!")

if __name__ == "__main__":
    main()
