import os
import time
from datetime import datetime
import pandas as pd
import yfinance as yf
import requests

# Thiết lập Session giả lập trình duyệt chống chặn kết nối tối ưu trên GitHub Actions
session = requests.Session()
session.headers.update({
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
    'Accept-Language': 'en-US,en;q=0.9,vi;q=0.8'
})

def load_130_tickers():
    """Danh sách 130 mã cổ phiếu trọng điểm (Top 100 HOSE & Top 30 HNX theo vốn hóa)"""
    tickers_list = [
        # --- Top 100 HOSE ---
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
        # --- Top 30 HNX ---
        "KSF", "KSV", "NVB", "PVS", "IDC", "PVI", "HUT", "SHS", "MBS", "BAB",
        "THD", "NTP", "CEO", "DTK", "DHT", "VCS", "SCG", "VIF", "VNR", "VC3",
        "PTI", "IPA", "CDN", "TNG", "DNP", "PGS", "PRE", "HGM", "BVS", "LAS"
    ]
    unique_tickers = sorted(list(set([t.strip().upper() for t in tickers_list if t.strip()])))
    print(f"🎯 [FINEX Enterprise Engine] Tổng số mã duy nhất chuẩn hóa (130 mã trọng điểm): {len(unique_tickers)}")
    return unique_tickers

def get_company_profile(symbol):
    """Hàm ánh xạ tên doanh nghiệp và tên ngành tối ưu cho thị trường Việt Nam"""
    tech_list = ["FPT", "CMG", "VTP", "ICT", "ELC", "CTR", "VGI", "VNZ"]
    bank_list = ["VCB", "BID", "TCB", "MBB", "ACB", "CTG", "VPB", "STB", "SHB", "HDB", "LPB", "MSB", "OCB", "NAB", "SSB", "EIB", "TPB", "BAB", "NVB"]
    securities_list = ["SSI", "VCI", "HCM", "VND", "SHS", "MBS", "FTS", "BSI", "CTS", "VIX", "VDS", "ORS", "AGR", "VFS", "DSE", "BVS", "EVF", "IPA"]
    realestate_list = ["VIC", "VHM", "VRE", "BCM", "KBC", "IDC", "SIP", "SZC", "KDH", "NLG", "DXG", "PDR", "DIG", "CEO", "HDC", "NVL", "TCH", "KSF", "VC3"]
    retail_list = ["MWG", "FRT", "DGW", "PNJ", "PET", "VTP"]
    oil_gas_list = ["GAS", "PLX", "PVD", "PVS", "PVT", "PVB", "BSR", "OIL", "POW"]
    steel_materials = ["HPG", "HSG", "NKG", "GDA", "BMP", "NTP", "AAA", "DGC", "CSV", "LAS"]

    if symbol in tech_list: sector = "Công nghệ thông tin"
    elif symbol in bank_list: sector = "Ngân hàng"
    elif symbol in securities_list: sector = "Chứng khoán"
    elif symbol in realestate_list: sector = "Bất động sản"
    elif symbol in retail_list: sector = "Bán lẻ & Dịch vụ tiêu dùng"
    elif symbol in oil_gas_list: sector = "Dầu khí & Năng lượng"
    elif symbol in steel_materials: sector = "Vật liệu xây dựng & Hóa chất"
    else: sector = "Công nghiệp, Sản xuất & Hàng tiêu dùng"

    company_names = {
        "HPG": "Công ty Cổ phần Tập đoàn Hòa Phát",
        "VCB": "Ngân hàng Thương mại Cổ phần Ngoại thương Việt Nam",
        "VHM": "Công ty Cổ phần Vinhomes",
        "VIC": "Tập đoàn Vingroup - Công ty Cổ phần",
        "FPT": "Công ty Cổ phần FPT",
        "MWG": "Công ty Cổ phần Đầu tư Thế Giới Di Động",
        "MSN": "Công ty Cổ phần Tập đoàn Masan",
        "TCB": "Ngân hàng Thương mại Cổ phần Kỹ Thương Việt Nam",
        "BID": "Ngân hàng Thương mại Cổ phần Đầu tư và Phát triển Việt Nam",
        "CTG": "Ngân hàng Thương mại Cổ phần Công Thương Việt Nam",
        "MBB": "Ngân hàng Thương mại Cổ phần Quân đội",
        "ACB": "Ngân hàng Thương mại Cổ phần Á Châu",
        "VPB": "Ngân hàng Thương mại Cổ phần Việt Nam Thịnh Vượng",
        "GAS": "Tổng Công ty Khí Việt Nam - CTCP",
        "VRE": "Công ty Cổ phần Vincom Retail",
        "PNJ": "Công ty Cổ phần Vàng bạc Đá quý Phú Nhuận",
        "SSI": "Công ty Cổ phần Chứng khoán SSI",
        "VND": "Công ty Cổ phần Chứng khoán VNDIRECT",
        "POW": "Tổng Công ty Điện lực Dầu khí Việt Nam - CTCP",
        "SAB": "Tổng công ty Cổ phần Bia - Rượu - Nước giải khát Sài Gòn"
    }
    
    company_name = company_names.get(symbol, f"Công ty Cổ phần {symbol}")
    return company_name, sector

# TỪ ĐIỂN VIỆT HÓA CHUYÊN SÂU 3 BÁO CÁO TÀI CHÍNH GỐC
TRANSLATION_MAP = {
    'Balance_Sheet': 'Bảng cân đối kế toán',
    'Income_Statement': 'Báo cáo kết quả kinh doanh',
    'Cash_Flow': 'Báo cáo lưu chuyển tiền tệ',

    # Cân đối kế toán
    'Ordinary Shares Number': 'Số lượng cổ phiếu phổ thông',
    'Share Issued': 'Cổ phiếu đã phát hành',
    'Total Assets': 'Tổng tài sản',
    'Current Assets': 'Tài sản ngắn hạn',
    'Cash And Cash Equivalents': 'Tiền và các khoản tương đương tiền',
    'Cash Equivalents': 'Các khoản tương đương tiền',
    'Net Loan': 'Cho vay khách hàng thuần',
    'Receivables': 'Các khoản phải thu',
    'Accounts Receivable': 'Phải thu ngắn hạn khách hàng',
    'Inventory': 'Hàng tồn kho',
    'Total Non Current Assets': 'Tổng tài sản dài hạn',
    'Net PPE': 'Tài sản cố định thuần',
    'Gross PPE': 'Nguyên giá tài sản cố định',
    'Accumulated Depreciation': 'Hao mòn lũy kế TSCĐ',
    'Goodwill And Other Intangible Assets': 'Lợi thế thương mại và tài sản vô hình',
    'Investments And Advances': 'Đầu tư tài chính dài hạn',
    'Investment Properties': 'Bất động sản đầu tư',
    'Current Liabilities': 'Nợ ngắn hạn',
    'Current Debt': 'Vay và nợ thuê tài chính ngắn hạn',
    'Payables': 'Các khoản phải trả',
    'Accounts Payable': 'Phải trả người bán ngắn hạn',
    'Total Liabilities Net Minority Interest': 'Tổng nợ phải trả',
    'Total Non Current Liabilities Net Minority Interest': 'Nợ dài hạn',
    'Long Term Debt': 'Vay và nợ thuê tài chính dài hạn',
    'Total Debt': 'Tổng nợ vay',
    'Net Debt': 'Nợ vay ròng',
    'Stockholders Equity': 'Vốn chủ sở hữu',
    'Capital Stock': 'Vốn góp chủ sở hữu',
    'Retained Earnings': 'Lợi nhuận sau thuế chưa phân phối',
    'Additional Paid In Capital': 'Thặng dư vốn cổ phần',
    'Working Capital': 'Vốn lưu động ròng',

    # Kết quả kinh doanh
    'Total Revenue': 'Tổng doanh thu',
    'Operating Revenue': 'Doanh thu thuần',
    'Cost Of Revenue': 'Giá vốn hàng bán',
    'Gross Profit': 'Lợi nhuận gộp',
    'Operating Expense': 'Chi phí hoạt động',
    'Selling General And Administration': 'Chi phí bán hàng và quản lý doanh nghiệp',
    'Research And Development': 'Chi phí nghiên cứu và phát triển',
    'Operating Income': 'Lợi nhuận thuần từ hoạt động kinh doanh',
    'Net Interest Income': 'Thu nhập lãi thuần',
    'Interest Expense': 'Chi phí lãi vay',
    'Interest Income': 'Thu nhập lãi',
    'EBIT': 'Lợi nhuận trước lãi vay và thuế (EBIT)',
    'EBITDA': 'Lợi nhuận trước lãi vay, thuế và khấu hao (EBITDA)',
    'Normalized EBITDA': 'Lợi nhuận trước lãi vay, thuế, khấu hao chuẩn hóa',
    'Pretax Income': 'Lợi nhuận kế toán trước thuế',
    'Tax Provision': 'Chi phí thuế TNDN',
    'Net Income': 'Lợi nhuận sau thuế (Lợi nhuận ròng)',
    'Net Income Common Stockholders': 'Lợi nhuận ròng phân bổ cổ đông phổ thông',
    'Basic EPS': 'Lãi cơ bản trên cổ phiếu (Basic EPS)',
    'Diluted EPS': 'Lãi suy giảm trên cổ phiếu (Diluted EPS)',

    # Lưu chuyển tiền tệ
    'Operating Cash Flow': 'Lưu chuyển tiền thuần từ hoạt động kinh doanh',
    'Investing Cash Flow': 'Lưu chuyển tiền thuần từ hoạt động đầu tư',
    'Financing Cash Flow': 'Lưu chuyển tiền thuần từ hoạt động tài chính',
    'Capital Expenditure': 'Chi phí đầu tư tài sản cố định (CapEx)',
    'Free Cash Flow': 'Dòng tiền tự do (FCF)',
    'Issuance Of Debt': 'Phát hành nợ vay',
    'Repayment Of Debt': 'Trả nợ gốc vay',
    'Cash Dividends Paid': 'Cổ tức đã chi trả',
    'Beginning Cash Position': 'Tiền và tương đương tiền đầu kỳ',
    'End Cash Position': 'Tiền và tương đương tiền cuối kỳ'
}

def translate_metric(metric_original):
    cleaned_key = str(metric_original).strip()
    if cleaned_key in TRANSLATION_MAP: return TRANSLATION_MAP[cleaned_key]
    for eng_k, vie_v in TRANSLATION_MAP.items():
        if cleaned_key.lower() == eng_k.lower(): return vie_v
     
    lower_key = cleaned_key.lower()
    if 'shares' in lower_key: return 'Số lượng cổ phiếu / Khối lượng niêm yết'
    if 'revenue' in lower_key or 'sales' in lower_key: return 'Doanh thu'
    if 'income' in lower_key or 'profit' in lower_key: return 'Lợi nhuận'
    if 'asset' in lower_key: return 'Tài sản'
    if 'debt' in lower_key: return 'Nợ vay'
    if 'cash' in lower_key: return 'Tiền và lưu chuyển tiền tệ'
    if 'expense' in lower_key or 'cost' in lower_key: return 'Chi phí'
    return f"Chỉ tiêu tài chính ({cleaned_key})"

def parse_financial_df(symbol, df, statement_type_raw, ky_bao_cao):
    records = []
    company_name, sector_name = get_company_profile(symbol)
    statement_type_vn = TRANSLATION_MAP.get(statement_type_raw, statement_type_raw)
    try:
        if df is not None and not df.empty:
            for col in df.columns:
                date_str = str(col).split('T')[0].split(' ')[0]
                year_val = date_str.split('-')[0]
                # Bỏ giới hạn năm cũ, chấp nhận toàn bộ dữ liệu lịch sử sâu nhất có sẵn trên nguồn
                if year_val.isdigit():
                    for row_idx, val in df[col].items():
                        if pd.notna(val):
                            try: float_val = float(val)
                            except: continue
                            records.append({
                                'Mã chứng khoán': symbol,
                                'Tên doanh nghiệp': company_name,
                                'Tên ngành': sector_name,
                                'Loại báo cáo': statement_type_vn,
                                'Loại kỳ': ky_bao_cao,
                                'Năm': year_val,
                                'Ngày kỳ': date_str,
                                'Chỉ tiêu tiếng Việt': translate_metric(str(row_idx).strip()),
                                'Giá trị': float_val
                            })
    except Exception:
        pass
    return records

def main():
    target_stocks = load_130_tickers()
    all_master_records = []
    success_count, fail_count = 0, 0
     
    batch_size = 30
    for i in range(0, len(target_stocks), batch_size):
        batch = target_stocks[i:i+batch_size]
        print(f"🔄 [FINEX Pipeline] Đang vét dữ liệu lịch sử sâu nhất cho batch từ {i+1} đến {min(i+batch_size, len(target_stocks))}/{len(target_stocks)}...")
         
        for symbol in batch:
            try:
                ticker = yf.Ticker(f"{symbol}.VN", session=session)
                 
                # Vét toàn bộ lịch sử Năm và Quý cho 3 BCTC gốc
                all_master_records.extend(parse_financial_df(symbol, getattr(ticker, 'balance_sheet', None), 'Balance_Sheet', 'Năm'))
                all_master_records.extend(parse_financial_df(symbol, getattr(ticker, 'quarterly_balance_sheet', None), 'Balance_Sheet', 'Quý'))
                all_master_records.extend(parse_financial_df(symbol, getattr(ticker, 'financials', None), 'Income_Statement', 'Năm'))
                all_master_records.extend(parse_financial_df(symbol, getattr(ticker, 'quarterly_financials', None), 'Income_Statement', 'Quý'))
                all_master_records.extend(parse_financial_df(symbol, getattr(ticker, 'cashflow', None), 'Cash_Flow', 'Năm'))
                all_master_records.extend(parse_financial_df(symbol, getattr(ticker, 'quarterly_cashflow', None), 'Cash_Flow', 'Quý'))
                 
                success_count += 1
                time.sleep(0.05)
            except Exception:
                fail_count += 1
                continue

    df_master = pd.DataFrame(all_master_records).drop_duplicates() if all_master_records else pd.DataFrame()

    print("\n💾 Đang kết xuất tệp CSV tổng hợp chuẩn hóa: vietnam_stock_database_tong_hop.csv...")
    os.makedirs('data', exist_ok=True)
     
    csv_path = 'data/vietnam_stock_database_tong_hop.csv'
    df_master.to_csv(csv_path, index=False, encoding='utf-8-sig')
     
    print(f"==================================================")
    print(f" 🎉 VÉT DỮ LIỆU LỊCH SỬ THÀNH CÔNG CHO 130 MÃ!")
    print(f" - Doanh nghiệp thành công: {success_count} | Lỗi/Bỏ qua: {fail_count}")
    print(f" - Tổng dung lượng bản ghi lịch sử: {len(df_master):,}")
    print(f"==================================================")

if __name__ == "__main__":
    main()
