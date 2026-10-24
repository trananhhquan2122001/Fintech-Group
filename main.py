import os
import pandas as pd
from datetime import datetime
import yfinance as yf

# Danh sách 10 mã doanh nghiệp VN30 (bao gồm cả Ngân hàng và Doanh nghiệp sản xuất/phiên bản chuẩn)
SYMBOLS = ['VCB', 'TCB', 'FPT', 'HPG', 'VIC', 'VHM', 'MBB', 'VPB', 'BID', 'STB']

# Từ điển ánh xạ tiếng Anh sang tiếng Việt toàn diện (Đã bao phủ cả Ngân hàng & Doanh nghiệp)
TRANSLATION_MAP = {
    # --- Loại báo cáo ---
    'Income_Statement': 'Báo cáo kết quả kinh doanh',
    'Balance_Sheet': 'Bảng cân đối kế toán',
    'Cash_Flow': 'Báo cáo lưu chuyển tiền tệ',
    
    # --- Báo cáo kết quả kinh doanh (Income Statement) ---
    'Total Revenue': 'Tổng doanh thu',
    'Operating Revenue': 'Doanh thu hoạt động',
    'Cost Of Revenue': 'Giá vốn hàng bán',
    'Gross Profit': 'Lợi nhuận gộp',
    'Operating Income': 'Lợi nhuận thuần từ hoạt động kinh doanh',
    'Net Income': 'Lợi nhuận sau thuế (Lợi nhuận ròng)',
    'Net Income Common Stockholders': 'Lợi nhuận phân bổ cho cổ đông phổ thông',
    'EBIT': 'Lợi nhuận trước lãi vay và thuế (EBIT)',
    'EBITDA': 'Lợi nhuận trước thuế, lãi vay và khấu hao (EBITDA)',
    'Pretax Income': 'Lợi nhuận trước thuế',
    'Operating Expense': 'Chi phí hoạt động',
    'Research And Development': 'Chi phí nghiên cứu & phát triển',
    'Selling General And Administration': 'Chi phí bán hàng và quản lý doanh nghiệp',
    'Net Interest Income': 'Thu nhập lãi thuần',
    'Interest Income': 'Thu nhập lãi và các khoản thu nhập tương tự',
    'Interest Expense': 'Chi phí lãi và các chi phí tương tự',
    'Diluted EPS': 'Lãi suy giảm trên cổ phiếu (Diluted EPS)',
    'Basic EPS': 'Lãi cơ bản trên cổ phiếu (Basic EPS)',
    'Tax Provision': 'Chi phí thuế thu nhập doanh nghiệp',
    
    # --- Bảng cân đối kế toán (Balance Sheet) ---
    'Total Assets': 'Tổng tài sản',
    'Current Assets': 'Tài sản ngắn hạn',
    'Total Non Current Assets': 'Tài sản dài hạn',
    'Cash And Cash Equivalents': 'Tiền và các khoản tương đương tiền',
    'Inventory': 'Hàng tồn kho',
    'Accounts Receivable': 'Phải thu ngắn hạn của khách hàng',
    'Net Loan': 'Cho vay khách hàng (Cho vay ròng)',
    'Total Liabilities Net Minority Interest': 'Tổng nợ phải trả',
    'Current Liabilities': 'Nợ ngắn hạn',
    'Total Non Current Liabilities Net Minority Interest': 'Nợ dài hạn',
    'Stockholders Equity': 'Vốn chủ sở hữu',
    'Common Stock Equity': 'Vốn cổ phần phổ thông',
    'Total Debt': 'Tổng nợ vay',
    'Retained Earnings': 'Lợi nhuận chưa phân phối',
    'Net PPE': 'Tài sản cố định hữu hình (ròng)',
    'Gross PPE': 'Nguyên giá tài sản cố định hữu hình',
    'Accumulated Depreciation': 'Hao mòn lũy kế',
    'Construction In Progress': 'Chi phí xây dựng cơ bản dở dang',
    'Goodwill And Other Intangible Assets': 'Lợi thế thương mại và tài sản vô hình',
    
    # --- Báo cáo lưu chuyển tiền tệ (Cash Flow) ---
    'Operating Cash Flow': 'Lưu chuyển tiền thuần từ hoạt động kinh doanh',
    'Investing Cash Flow': 'Lưu chuyển tiền thuần từ hoạt động đầu tư',
    'Financing Cash Flow': 'Lưu chuyển tiền thuần từ hoạt động tài chính',
    'Free Cash Flow': 'Dòng tiền tự do',
    'Capital Expenditure': 'Chi phí đầu tư tài sản cố định (CapEx)',
    'Repayment Of Debt': 'Trả nợ gốc vay',
    'Issuance Of Debt': 'Phát hành thêm nợ vay',
    'Cash Dividends Paid': 'Cổ tức đã trả bằng tiền'
}

def translate_metric(metric_name):
    """Hàm ánh xạ tên chỉ tiêu, nếu không có trong từ điển sẽ giữ nguyên bản sạch"""
    return TRANSLATION_MAP.get(metric_name, metric_name)

def main():
    print("🚀 [FINEX Engine] Bắt đầu thu thập và làm sạch Báo cáo tài chính VN30...")
    
    all_data = []
    current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    for symbol in SYMBOLS:
        print(f"🔄 Đang xử lý dữ liệu chuẩn hóa cho mã: {symbol}...")
        try:
            ticker = yf.Ticker(f"{symbol}.VN")
            
            # Danh sách các báo cáo cần cào
            statements = {
                'Income_Statement': ticker.financials,
                'Balance_Sheet': ticker.balance_sheet,
                'Cash_Flow': ticker.cashflow
            }
            
            for stmt_key, df_stmt in statements.items():
                if df_stmt is not None and not df_stmt.empty:
                    vn_stmt_name = TRANSLATION_MAP.get(stmt_key, stmt_key)
                    
                    for date_col in df_stmt.columns:
                        date_str = str(date_col).split('T')[0]
                        for idx, val in df_stmt[date_col].items():
                            # Lọc sạch: Chỉ lấy giá trị hợp lệ, không phải NaN và khác 0 (nếu cần tối ưu dung lượng)
                            if pd.notna(val) and val != 0:
                                clean_metric = translate_metric(str(idx))
                                all_data.append({
                                    'symbol': symbol,
                                    'statement_type': vn_stmt_name,
                                    'metric': clean_metric,
                                    'period_date': date_str,
                                    'value': float(val),
                                    'scrape_time': current_time
                                })
                                
        except Exception as e:
            print(f"❌ Lỗi xử lý mã {symbol}: {e}")
            
    if all_data:
        df_final = pd.DataFrame(all_data)
        
        # Sắp xếp lại thứ tự cột cho chuyên nghiệp
        df_final = df_final[['symbol', 'statement_type', 'metric', 'period_date', 'value', 'scrape_time']]
        
        file_path = 'vietnam_financial_statements.csv'
        df_final.to_csv(file_path, index=False)
        print(f"✅ Hoàn tất! Đã lưu {len(df_final)} bản ghi tài chính sạch vào '{file_path}'.")
    else:
        print("⚠️ Cảnh báo: Không thu thập được dữ liệu tài chính nào.")

if __name__ == "__main__":
    main()
