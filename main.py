import os
import time
from datetime import datetime
import pandas as pd
import yfinance as yf
import requests

# Thiết lập Session giả lập trình duyệt chống chặn kết nối trên GitHub Actions
session = requests.Session()
session.headers.update({
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'
})

def load_tickers_from_module():
    """Đọc danh sách mã cổ phiếu trực tiếp từ module/file tickers.txt"""
    tickers_file = 'tickers.txt'
    if os.path.exists(tickers_file):
        with open(tickers_file, 'r', encoding='utf-8') as f:
            tickers = [line.strip().upper() for line in f if line.strip()]
            # Loại bỏ trùng lặp và giữ thứ tự sạch sẽ
            return sorted(list(set(tickers)))
    else:
        print("⚠️ Không tìm thấy file tickers.txt, sử dụng danh sách mặc định dự phòng.")
        return ['VIC', 'VHM', 'VCB', 'FPT', 'TCB', 'HPG']

def get_sector(symbol):
    """Phân chia chính xác thành các nhóm ngành chính"""
    tech_list = ["FPT", "CMG", "VTP", "ICT", "ELC", "CTR", "VNZ", "VTC"]
    finance_list = [
        "VCB", "BID", "TCB", "MBB", "ACB", "CTG", "VPB", "STB", "SSI", "VCI", 
        "HCM", "VND", "SHB", "HDB", "LPB", "MSB", "OCB", "NAB", "SSB", "EIB", 
        "BSI", "CTS", "FTS", "MBS", "BVS", "EVF", "DSE", "VIX", "SHS", "ORS", "BVH",
        "ABI", "BIC", "BMI", "MIG", "BLI", "AAS", "ABW", "BMS", "PHS", "TCI"
    ]
    if symbol in tech_list:
        return "Công nghệ"
    elif symbol in finance_list or any(f in symbol for f in ["ACB", "BID", "CTG", "MBB", "TCB", "VPB", "STB", "SSI", "SHB", "VCB", "VIB", "HDB"]):
        return "Tài chính & Ngân hàng"
    else:
        return "Sản xuất, Bất động sản và Công nghiệp"

# --- TỪ ĐIỂN VIỆT HÓA TOÀN DIỆN & VÉT CẠN 100% ---
TRANSLATION_MAP = {
    'Balance_Sheet': 'Bảng cân đối kế toán',
    'Income_Statement': 'Báo cáo kết quả kinh doanh',
    'Cash_Flow': 'Báo cáo lưu chuyển tiền tệ',
    'Năm': 'Năm',
    'Quý': 'Quý',

    # Cân đối kế toán
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
    'Long Term Debt And Capital Lease Obligation': 'Nợ dài hạn và nghĩa vụ thuê tài chính',
    'Payables': 'Các khoản phải trả',
    'Accounts Payable': 'Phải trả người bán ngắn hạn',
    'Total Assets': 'Tổng tài sản',
    'Current Assets': 'Tài sản ngắn hạn',
    'Cash And Cash Equivalents': 'Tiền và các khoản tương đương tiền',
    'Cash Equivalents': 'Các khoản tương đương tiền',
    'Net Loan': 'Cho vay khách hàng thuần',
    'Receivables': 'Các khoản phải thu',
    'Accounts Receivable': 'Phải thu ngắn hạn của khách hàng',
    'Inventory': 'Hàng tồn kho',
    'Finished Goods': 'Thành phẩm',
    'Work In Process': 'Chi phí sản xuất kinh doanh dở dang',
    'Other Receivables': 'Các khoản phải thu khác',
    'Prepaid Assets': 'Chi phí trả trước',
    'Total Non Current Assets': 'Tổng tài sản dài hạn',
    'Net PPE': 'Tài sản cố định thuần',
    'Gross PPE': 'Nguyên giá tài sản cố định',
    'Accumulated Depreciation': 'Hao mòn lũy kế tài sản cố định',
    'Goodwill And Other Intangible Assets': 'Lợi thế thương mại và tài sản vô hình khác',
    'Investments And Advances': 'Đầu tư tài chính dài hạn',
    'Investment Properties': 'Bất động sản đầu tư',
    'Current Liabilities': 'Nợ ngắn hạn',
    'Current Debt': 'Vay và nợ thuê tài chính ngắn hạn',
    'Total Non Current Liabilities Net Minority Interest': 'Nợ dài hạn',
    'Long Term Debt': 'Vay và nợ thuê tài chính dài hạn',
    'Net Debt': 'Nợ vay ròng',
    'Working Capital': 'Vốn lưu động ròng',
    'Construction In Progress': 'Chi phí xây dựng cơ bản dở dang',

    # Kết quả kinh doanh
    'Normalized EBITDA': 'Lợi nhuận trước lãi vay, thuế, khấu hao chuẩn hóa (Normalized EBITDA)',
    'Net Interest Income': 'Thu nhập lãi thuần',
    'Interest Expense': 'Chi phí lãi vay',
    'Interest Income': 'Thu nhập lãi',
    'Normalized Income': 'Lợi nhuận chuẩn hóa',
    'Diluted EPS': 'Lãi suy giảm trên cổ phiếu (Diluted EPS)',
    'Basic EPS': 'Lãi cơ bản trên cổ phiếu (Basic EPS)',
    'Net Income Common Stockholders': 'Lợi nhuận ròng phân bổ cho cổ đông phổ thông',
    'Net Income': 'Lợi nhuận sau thuế (Lợi nhuận ròng)',
    'Minority Interests': 'Lợi ích cổ đông thiểu số',
    'Tax Provision': 'Chi phí thuế thu nhập doanh nghiệp',
    'Total Revenue': 'Tổng doanh thu',
    'Operating Revenue': 'Doanh thu thuần',
    'Cost Of Revenue': 'Giá vốn hàng bán',
    'Gross Profit': 'Lợi nhuận gộp',
    'Operating Income': 'Lợi nhuận thuần từ hoạt động kinh doanh',
    'Operating Expense': 'Chi phí hoạt động',
    'Depreciation And Amortization': 'Khấu hao và phân bổ',
    'Selling General And Administration': 'Chi phí bán hàng và quản lý doanh nghiệp',
    'Research And Development': 'Chi phí nghiên cứu và phát triển',
    'EBIT': 'Lợi nhuận trước lãi vay và thuế (EBIT)',
    'EBITDA': 'Lợi nhuận trước lãi vay, thuế và khấu hao (EBITDA)',
    'Pretax Income': 'Lợi nhuận kế toán trước thuế',
    'Total Operating Expenses': 'Tổng chi phí hoạt động',

    # Lưu chuyển tiền tệ
    'Free Cash Flow': 'Dòng tiền tự do (FCF)',
    'Repayment Of Debt': 'Trả nợ gốc vay',
    'Issuance Of Debt': 'Phát hành nợ vay',
    'Capital Expenditure': 'Chi phí đầu tư tài sản cố định (CapEx)',
    'End Cash Position': 'Tiền và tương đương tiền cuối kỳ',
    'Beginning Cash Position': 'Tiền và tương đương tiền đầu kỳ',
    'Financing Cash Flow': 'Lưu chuyển tiền thuần từ hoạt động tài chính',
    'Cash Dividends Paid': 'Cổ tức đã chi trả',
    'Investing Cash Flow': 'Lưu chuyển tiền thuần từ hoạt động đầu tư',
    'Operating Cash Flow': 'Lưu chuyển tiền thuần từ hoạt động kinh doanh'
}

def translate_metric(metric_original):
    cleaned_key = str(metric_original).strip()
    if cleaned_key in TRANSLATION_MAP:
        return TRANSLATION_MAP[cleaned_key]
    for eng_k, vie_v in TRANSLATION_MAP.items():
        if cleaned_key.lower() == eng_k.lower():
            return vie_v
            
    lower_key = cleaned_key.lower()
    if 'ebitda' in lower_key: return 'Lợi nhuận trước lãi vay, thuế và khấu hao (EBITDA)'
    if 'revenue' in lower_key or 'sales' in lower_key: return 'Doanh thu'
    if 'income' in lower_key or 'profit' in lower_key: return 'Lợi nhuận'
    if 'asset' in lower_key: return 'Tài sản'
    if 'liability' in lower_key or 'debt' in lower_key: return 'Nợ phải trả / Nợ vay'
    if 'equity' in lower_key: return 'Vốn chủ sở hữu'
    if 'cash' in lower_key: return 'Tiền và lưu chuyển tiền tệ'
    if 'expense' in lower_key or 'cost' in lower_key: return 'Chi phí'
    if 'tax' in lower_key: return 'Thuế'
    if 'dividend' in lower_key: return 'Cổ tức'
    return f"Chỉ tiêu tài chính ({cleaned_key})"

def safe_float_convert(val):
    try:
        if pd.isna(val): return 0.0
        return float(val)
    except:
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
                
                # Lịch sử từ 2020 đến 2026
                if year_val.isdigit() and 2020 <= int(year_val) <= 2026:
                    for row_idx, val in df[col].items():
                        if pd.notna(val):
                            metric_original = str(row_idx).strip()
                            records.append({
                                'Mã chứng khoán': symbol,
                                'Nhóm ngành': sector_name,
                                'Loại báo cáo': statement_type_vn,
                                'Loại kỳ': ky_bao_cao,
                                'Năm': year_val,
                                'Ngày kỳ': date_str,
                                'Chỉ tiêu tiếng Việt': translate_metric(metric_original),
                                'Giá trị': safe_float_convert(val)
                            })
    except Exception:
        pass
    return records

def main():
    target_stocks = load_tickers_from_module()
    print(f"🚀 [FINEX Pipeline 2020-2026] Đã nạp {len(target_stocks)} mã từ module tickers.txt, bắt đầu quét...")
    
    all_master_records = []
    success_count = 0
    fail_count = 0
    
    for idx, symbol in enumerate(target_stocks, 1):
        try:
            print(f"⏳ [{idx}/{len(target_stocks)}] Đang xử lý: {symbol}...")
            ticker = yf.Ticker(f"{symbol}.VN", session=session)
            
            all_master_records.extend(parse_financial_df(symbol, getattr(ticker, 'balance_sheet', None), 'Balance_Sheet', 'Năm'))
            all_master_records.extend(parse_financial_df(symbol, getattr(ticker, 'quarterly_balance_sheet', None), 'Balance_Sheet', 'Quý'))
            all_master_records.extend(parse_financial_df(symbol, getattr(ticker, 'financials', None), 'Income_Statement', 'Năm'))
            all_master_records.extend(parse_financial_df(symbol, getattr(ticker, 'quarterly_financials', None), 'Income_Statement', 'Quý'))
            all_master_records.extend(parse_financial_df(symbol, getattr(ticker, 'cashflow', None), 'Cash_Flow', 'Năm'))
            all_master_records.extend(parse_financial_df(symbol, getattr(ticker, 'quarterly_cashflow', None), 'Cash_Flow', 'Quý'))
            
            success_count += 1
            time.sleep(0.2)
        except Exception as e:
            fail_count += 1
            print(f"⚠️ Bỏ qua mã {symbol} do lỗi: {e}")
            continue

    df_master = pd.DataFrame(all_master_records).drop_duplicates() if all_master_records else pd.DataFrame()

    print("\n💾 Đang kết xuất ra bảng tổng hợp Excel & CSV...")
    os.makedirs('data', exist_ok=True)
    
    excel_path = 'vietnam_stock_database.xlsx'
    with pd.ExcelWriter(excel_path, engine='openpyxl') as writer:
        df_master.to_excel(writer, sheet_name='Tong_Hop_Tai_Chinh', index=False)
    
    csv_path = 'data/vietnam_stock_database_tong_hop.csv'
    df_master.to_csv(csv_path, index=False, encoding='utf-8-sig')
    
    print(f"\n==================================================")
    print(f" 🎉 HOÀN TẤT CÀO DỮ LIỆU & LÀM SẠCH 100% TIẾNG VIỆT")
    print(f" - Thành công: {success_count} mã | Lỗi: {fail_count} mã")
    print(f" - Tổng số bản ghi: {len(df_master):,}")
    print(f"==================================================")

if __name__ == "__main__":
    main()
