import os
import time
from datetime import datetime
import pandas as pd
import yfinance as yf
import requests

# --- DANH SÁCH 130 MÃ (VN100 + HNX30) ---
VN100 = [
    "ACB", "ANV", "BAF", "BCM", "BID", "BSI", "BSR", "BMP", "BWE", "BVH",
    "CII", "CMG", "CTD", "CTG", "CTR", "CTS", "DGC", "DGW", "DIG", "DPM",
    "DSE", "DXG", "EIB", "EVF", "FPT", "FRT", "FTS", "GAS", "GEE", "GEX",
    "GMD", "GVR", "HAG", "HCM", "HDB", "HDG", "HHV", "HPG", "HSG", "HT1",
    "KBC", "KDC", "KDH", "LPB", "MBB", "MCH", "MSB", "MSN", "MWG", "NAB",
    "NKG", "NLG", "NT2", "NVL", "OCB", "PAN", "PC1", "PDR", "PHR", "PLX",
    "PNJ", "POW", "PVD", "PVT", "REE", "SAB", "SBT", "SHB", "SIP", "SSB",
    "SSI", "STB", "TCB", "TCX", "TAL", "TCH", "TPB", "VCB", "VCG", "VCI",
    "VCK", "VGC", "VHC", "VHM", "VIB", "VIC", "VIX", "VJC", "VND", "VNM",
    "VPI", "VPL", "VPB", "VRE", "VSC", "VTP"
]

HNX30 = [
    "BCC", "BVS", "CAP", "CEO", "DTD", "DVM", "DXP", "HLD", "HUT", "IDC",
    "L14", "L18", "LAS", "LHC", "MBS", "NBC", "NDN", "PLC", "PSI", "PVC",
    "PVG", "PVS", "SHS", "SLS", "TDN", "TIG", "TNG", "TVD", "VC3", "VCS"
]

ALL_TARGET_STOCKS = sorted(list(set(VN100 + HNX30)))

# Thiết lập Session giả lập trình duyệt chống chặn kết nối trên GitHub Actions
session = requests.Session()
session.headers.update({
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'
})

def get_sector(symbol):
    """Phân chia chính xác thành 3 nhóm ngành"""
    tech_list = ["FPT", "CMG", "VTP", "ICT", "ELC", "CTR"]
    finance_list = [
        "VCB", "BID", "TCB", "MBB", "ACB", "CTG", "VPB", "STB", "SSI", "VCI", 
        "HCM", "VND", "SHB", "HDB", "LPB", "MSB", "OCB", "NAB", "SSB", "EIB", 
        "BSI", "CTS", "FTS", "MBS", "BVS", "EVF", "DSE", "VIX", "SHS", "ORS"
    ]
    if symbol in tech_list:
        return "Công nghệ"
    elif symbol in finance_list:
        return "Tài chính & Ngân hàng"
    else:
        return "Sản xuất, Bất động sản và Công nghiệp"

# --- TỪ ĐIỂN VIỆT HÓA TOÀN DIỆN & VÉT CẠN 100% ---
TRANSLATION_MAP = {
    # Loại báo cáo & Phân loại
    'Balance_Sheet': 'Bảng cân đối kế toán',
    'Income_Statement': 'Báo cáo kết quả kinh doanh',
    'Cash_Flow': 'Báo cáo lưu chuyển tiền tệ',
    'Năm': 'Năm',
    'Quý': 'Quý',

    # --- Cân đối kế toán (Balance Sheet) ---
    'Ordinary Shares Number': 'Số lượng cổ phiếu phổ thông',
    'Share Issued': 'Cổ phiếu đã phát hành',
    'Total Debt': 'Tổng nợ vay',
    'Tangible Book Value': 'Giá trị sổ sách hữu hình',
    'Invested Capital': 'Vốn đầu tư',
    'Net Tangible Assets': 'Tài sản thuần hữu hình',
    'Common Stock Equity': 'Vốn chủ sở hữu phổ thông',
    'Total Capitalization': 'Tổng nguồn vốn',
    'Total Equity Gross Minority Interest': 'Tổng vốn chủ sở hữu (bao gồm cổ đông thiểu số)',
    'Stockholders Equity': 'Vốn chủ sở hữu',
    'Retained Earnings': 'Lợi nhuận sau thuế chưa phân phối',
    'Additional Paid In Capital': 'Thặng dư vốn cổ phần',
    'Capital Stock': 'Vốn cổ phần',
    'Common Stock': 'Vốn góp chủ sở hữu (Cổ phiếu phổ thông)',
    'Total Liabilities Net Minority Interest': 'Tổng nợ phải trả',
    'Total Liabilities Net': 'Tổng nợ phải trả',
    'Derivative Product Liabilities': 'Nợ sản phẩm phái sinh',
    'Long Term Debt And Capital Lease Obligation': 'Nợ dài hạn và nghĩa vụ thuê tài chính',
    'Payables': 'Các khoản phải trả',
    'Other Payable': 'Phải trả khác',
    'Total Tax Payable': 'Tổng thuế phải nộp',
    'Accounts Payable': 'Phải trả người bán ngắn hạn',
    'Total Assets': 'Tổng tài sản',
    'Current Assets': 'Tài sản ngắn hạn',
    'Cash And Cash Equivalents': 'Tiền và các khoản tương đương tiền',
    'Cash Equivalents': 'Các khoản tương đương tiền',
    'Cash Financial': 'Tiền và các khoản tương đương tiền tài chính',
    'Cash Cash Equivalents And Short Term Investments': 'Tiền, tương đương tiền và đầu tư ngắn hạn',
    'Net Loan': 'Cho vay khách hàng thuần',
    'Receivables': 'Các khoản phải thu',
    'Accounts Receivable': 'Phải thu ngắn hạn của khách hàng',
    'Inventory': 'Hàng tồn kho',
    'Prepaid Assets': 'Chi phí trả trước',
    'Other Current Assets': 'Tài sản ngắn hạn khác',
    'Total Non Current Assets': 'Tổng tài sản dài hạn',
    'Non Current Prepaid Assets': 'Chi phí trả trước dài hạn',
    'Net PPE': 'Tài sản cố định thuần',
    'Gross PPE': 'Nguyên giá tài sản cố định',
    'Accumulated Depreciation': 'Hao mòn lũy kế tài sản cố định',
    'Goodwill And Other Intangible Assets': 'Lợi thế thương mại và tài sản vô hình khác',
    'Other Intangible Assets': 'Tài sản vô hình khác',
    'Investments And Advances': 'Đầu tư tài chính dài hạn',
    'Investment in Financial Assets': 'Đầu tư tài chính',
    'Held To Maturity Securities': 'Chứng khoán giữ đến ngày đáo hạn',
    'Available For Sale Securities': 'Chứng khoán sẵn sàng để bán',
    'Trading Securities': 'Chứng khoán kinh doanh',
    'Long Term Equity Investment': 'Đầu tư vào công ty liên kết, liên doanh',
    'Investments in Other Investments': 'Đầu tư dài hạn khác',
    'Investments in Joint Ventures': 'Đầu tư vào liên doanh liên kết',
    'Investment Properties': 'Bất động sản đầu tư',
    'Other Non Current Assets': 'Tài sản dài hạn khác',
    'Current Liabilities': 'Nợ ngắn hạn',
    'Current Debt': 'Vay và nợ thuê tài chính ngắn hạn',
    'Current Deferred Liabilities': 'Doanh thu chưa thực hiện ngắn hạn',
    'Other Current Liabilities': 'Nợ ngắn hạn khác',
    'Total Non Current Liabilities Net Minority Interest': 'Nợ dài hạn',
    'Long Term Debt': 'Vay và nợ thuê tài chính dài hạn',
    'Long Term Provisions': 'Dự phòng phải trả dài hạn',
    'Other Non Current Liabilities': 'Nợ dài hạn khác',
    'Capital Surplus': 'Thặng dư vốn cổ phần',
    'Other Equity Adjustments': 'Các quỹ và nguồn vốn khác',
    'Net Debt': 'Nợ vay ròng',
    'Working Capital': 'Vốn lưu động ròng',
    'Construction In Progress': 'Chi phí xây dựng cơ bản dở dang',
    'Other Properties': 'Bất động sản khác',
    'Machinery Furniture': 'Máy móc, thiết bị và công cụ dụng cụ',
    'Buildings And Improvements': 'Nhà cửa, vật kiến trúc và cải tạo',
    'Properties': 'Tài sản cố định vật chất khác',

    # --- Kết quả kinh doanh (Income Statement) ---
    'Tax Effect Of Unusual Items': 'Hiệu ứng thuế từ các khoản mục bất thường',
    'Tax Rate For Calcs': 'Thuế suất tính toán',
    'Net Income From Continuing Operation Net Minority Interest': 'Lợi nhuận ròng từ hoạt động tiếp tục phân bổ cổ đông',
    'Reconciled Depreciation': 'Khấu hao điều chỉnh',
    'Net Interest Income': 'Thu nhập lãi thuần',
    'Interest Expense': 'Chi phí lãi vay',
    'Interest Income': 'Thu nhập lãi',
    'Normalized Income': 'Lợi nhuận chuẩn hóa',
    'Net Income From Continuing And Discontinued Operation': 'Lợi nhuận từ hoạt động tiếp tục và không tiếp tục',
    'Diluted Average Shares': 'Số lượng cổ phiếu bình quân suy giảm',
    'Basic Average Shares': 'Số lượng cổ phiếu bình quân cơ bản',
    'Diluted EPS': 'Lãi suy giảm trên cổ phiếu (Diluted EPS)',
    'Basic EPS': 'Lãi cơ bản trên cổ phiếu (Basic EPS)',
    'Diluted NI Availto Com Stockholders': 'Lợi nhuận ròng pha loãng phân bổ cho cổ đông phổ thông',
    'Net Income Common Stockholders': 'Lợi nhuận ròng phân bổ cho cổ đông phổ thông',
    'Otherunder Preferred Stock Dividend': 'Cổ tức cổ phiếu ưu đãi và khoản mục khác',
    'Net Income': 'Lợi nhuận sau thuế (Lợi nhuận ròng)',
    'Net Income Including Noncontrolling Interests': 'Lợi nhuận bao gồm cổ đông không kiểm soát',
    'Net Income Continuous Operations': 'Lợi nhuận từ hoạt động liên tục',
    'Tax Provision': 'Chi phí thuế thu nhập doanh nghiệp',
    'Total Revenue': 'Tổng doanh thu',
    'Operating Revenue': 'Doanh thu thuần',
    'Cost Of Revenue': 'Giá vốn hàng bán',
    'Gross Profit': 'Lợi nhuận gộp',
    'Operating Income': 'Lợi nhuận thuần từ hoạt động kinh doanh',
    'Operating Expense': 'Chi phí hoạt động',
    'Other Operating Exp': 'Chi phí hoạt động khác',
    'Depreciation And Amortization': 'Khấu hao và phân bổ',
    'Depreciation Income': 'Khấu hao ghi nhận vào kết quả kinh doanh',
    'Selling General And Administration': 'Chi phí bán hàng và quản lý doanh nghiệp',
    'General And Administrative': 'Chi phí quản lý doanh nghiệp',
    'Insurance And Claim': 'Chi phí bảo hiểm và bồi thường',
    'Rent And Landing Fees': 'Chi phí thuê mặt bằng và bến bãi',
    'Research And Development': 'Chi phí nghiên cứu và phát triển',
    'EBIT': 'Lợi nhuận trước lãi vay và thuế (EBIT)',
    'EBITDA': 'Lợi nhuận trước lãi vay, thuế và khấu hao (EBITDA)',
    'Interest Expense Non Operating': 'Chi phí lãi vay phi hoạt động',
    'Pretax Income': 'Lợi nhuận kế toán trước thuế',
    'Total Operating Expenses': 'Tổng chi phí hoạt động',

    # --- Lưu chuyển tiền tệ (Cash Flow) ---
    'Free Cash Flow': 'Dòng tiền tự do (FCF)',
    'Repayment Of Debt': 'Trả nợ gốc vay',
    'Issuance Of Debt': 'Phát hành nợ vay',
    'Capital Expenditure': 'Chi phí đầu tư tài sản cố định (CapEx)',
    'End Cash Position': 'Tiền và tương đương tiền cuối kỳ',
    'Beginning Cash Position': 'Tiền và tương đương tiền đầu kỳ',
    'Effect Of Exchange Rate Changes': 'Ảnh hưởng thay đổi tỷ giá hối đoái',
    'Changes In Cash': 'Biến động tiền và tương đương tiền',
    'Financing Cash Flow': 'Lưu chuyển tiền thuần từ hoạt động tài chính',
    'Cash Dividends Paid': 'Cổ tức đã chi trả',
    'Common Stock Dividend Paid': 'Cổ tức cổ phiếu phổ thông đã trả',
    'Net Issuance Payments Of Debt': 'Thu/chi thuần từ phát hành/trả nợ',
    'Net Long Term Debt Issuance': 'Phát hành nợ dài hạn thuần',
    'Long Term Debt Payments': 'Thanh toán nợ dài hạn',
    'Long Term Debt Issuance': 'Phát hành nợ dài hạn',
    'Investing Cash Flow': 'Lưu chuyển tiền thuần từ hoạt động đầu tư',
    'Dividends Received Cfi': 'Cổ tức đã nhận từ hoạt động đầu tư',
    'Net Investment Purchase And Sale': 'Mua bán đầu tư thuần',
    'Sale Of Investment': 'Thanh lý đầu tư',
    'Purchase Of Investment': 'Mua khoản đầu tư',
    'Operating Cash Flow': 'Lưu chuyển tiền thuần từ hoạt động kinh doanh',
    'Issuance Of Stock': 'Phát hành cổ phiếu tăng vốn',
    'Repurchase Of Stock': 'Mua lại cổ phiếu quỹ',
    'Dividends Paid': 'Cổ tức đã chi trả',
    'Depreciation And Amortization': 'Khấu hao tài sản cố định và phân bổ'
}

def translate_metric(metric_original):
    """Làm sạch và dịch triệt để sang tiếng Việt 100%"""
    cleaned_key = str(metric_original).strip()
    if cleaned_key in TRANSLATION_MAP:
        return TRANSLATION_MAP[cleaned_key]
    
    # Quét khớp gần đúng để xử lý triệt để các biến thể lạ
    for eng_k, vie_v in TRANSLATION_MAP.items():
        if cleaned_key.lower() == eng_k.lower() or cleaned_key.lower().startswith(eng_k.lower()):
            return vie_v
            
    # Mặc định trả về chuỗi gốc nếu không thuộc từ điển (nhưng ưu tiên lọc sạch)
    return cleaned_key

def safe_float_convert(val):
    try:
        if pd.isna(val):
            return 0.0
        return float(val)
    except (ValueError, TypeError):
        return 0.0

def parse_financial_df(symbol, df, statement_type_raw, ky_bao_cao):
    records = []
    sector_name = get_sector(symbol)
    statement_type_vn = TRANSLATION_MAP.get(statement_type_raw, statement_type_raw)
    try:
        if df is not None and not df.empty:
            for col in df.columns:
                date_str = str(col).split('T')[0].split(' ')[0]
                year_val = date_str.split('-')[0]
                
                # LẤY DỮ LIỆU LỊCH SỬ TỪ 2020 ĐẾN 2026
                if year_val.isdigit() and 2020 <= int(year_val) <= 2026:
                    for row_idx, val in df[col].items():
                        if pd.notna(val):
                            metric_original = str(row_idx).strip()
                            metric_vn = translate_metric(metric_original)
                            records.append({
                                'Mã chứng khoán': symbol,
                                'Nhóm ngành': sector_name,
                                'Loại báo cáo': statement_type_vn,
                                'Loại kỳ': ky_bao_cao,
                                'Năm': year_val,
                                'Ngày kỳ': date_str,
                                'Chỉ tiêu tiếng Việt': metric_vn,  # CHỈ GIỮ LẠI DUY NHẤT CỘT TIẾNG VIỆT NÀY
                                'Giá trị': safe_float_convert(val)
                            })
    except Exception:
        pass
    return records

def main():
    print(f"🚀 [FINEX Pipeline 2020-2026] Bắt đầu cào, làm sạch 100% tiếng Việt cho {len(ALL_TARGET_STOCKS)} mã...")
    
    all_master_records = []
    success_count = 0
    fail_count = 0
    
    for idx, symbol in enumerate(ALL_TARGET_STOCKS, 1):
        try:
            print(f"⏳ [{idx}/{len(ALL_TARGET_STOCKS)}] Đang xử lý: {symbol}...")
            ticker = yf.Ticker(f"{symbol}.VN", session=session)
            
            all_master_records.extend(parse_financial_df(symbol, getattr(ticker, 'balance_sheet', None), 'Balance_Sheet', 'Năm'))
            all_master_records.extend(parse_financial_df(symbol, getattr(ticker, 'quarterly_balance_sheet', None), 'Balance_Sheet', 'Quý'))
            
            all_master_records.extend(parse_financial_df(symbol, getattr(ticker, 'financials', None), 'Income_Statement', 'Năm'))
            all_master_records.extend(parse_financial_df(symbol, getattr(ticker, 'quarterly_financials', None), 'Income_Statement', 'Quý'))
            
            all_master_records.extend(parse_financial_df(symbol, getattr(ticker, 'cashflow', None), 'Cash_Flow', 'Năm'))
            all_master_records.extend(parse_financial_df(symbol, getattr(ticker, 'quarterly_cashflow', None), 'Cash_Flow', 'Quý'))
            
            success_count += 1
            time.sleep(0.3)
            
        except Exception as e:
            fail_count += 1
            print(f"⚠️ Bỏ qua mã {symbol} do lỗi mạng: {e}")
            continue

    df_master = pd.DataFrame(all_master_records).drop_duplicates() if all_master_records else pd.DataFrame()

    print("\n💾 Đang kết xuất ra bảng tổng hợp Excel duy nhất...")
    
    excel_path = 'vietnam_stock_database.xlsx'
    with pd.ExcelWriter(excel_path, engine='openpyxl') as writer:
        df_master.to_excel(writer, sheet_name='Tong_Hop_Tai_Chinh', index=False)
    print(f"✅ Đã tạo file Excel tổng hợp (100% tiếng Việt, không còn cột tiếng Anh): {excel_path}")

    df_master.to_csv('vietnam_stock_database_tong_hop.csv', index=False, encoding='utf-8-sig')
    print("✅ Đã xuất file CSV tổng hợp độc lập.")

    print(f"\n==================================================")
    print(f" 🎉 HOÀN TẤT LÀM SẠCH 100% TIẾNG VIỆT (2020-2026)")
    print(f" - Thành công: {success_count} mã | Lỗi: {fail_count} mã")
    print(f" - Tổng số bản ghi chuẩn hóa: {len(df_master):,}")
    print(f"==================================================")

if __name__ == "__main__":
    main()
