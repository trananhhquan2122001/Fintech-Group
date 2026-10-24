import os
import pandas as pd
from datetime import datetime
import yfinance as yf

# Danh sách 10 mã doanh nghiệp VN30
SYMBOLS = ['VCB', 'TCB', 'FPT', 'HPG', 'VIC', 'VHM', 'MBB', 'VPB', 'BID', 'STB']

# Từ điển ánh xạ tên tiếng Anh sang tiếng Việt cho các BCTC và chỉ tiêu phổ biến
TRANSLATION_MAP = {
    # Loại báo cáo
    'Income_Statement': 'Báo cáo kết quả kinh doanh',
    'Balance_Sheet': 'Bảng cân đối kế toán',
    'Cash_Flow': 'Báo cáo lưu chuyển tiền tệ',
    
    # Báo cáo kết quả kinh doanh (Income Statement)
    'Total Revenue': 'Tổng doanh thu',
    'Cost Of Revenue': 'Giá vốn hàng bán',
    'Gross Profit': 'Lợi nhuận gộp',
    'Operating Income': 'Lợi nhuận thuần từ hoạt động kinh doanh',
    'Net Income': 'Lợi nhuận sau thuế (Lợi nhuận ròng)',
    'EBIT': 'Lợi nhuận trước lãi vay và thuế (EBIT)',
    'EBITDA': 'Lợi nhuận trước thuế, lãi vay và khấu hao (EBITDA)',
    'Pretax Income': 'Lợi nhuận trước thuế',
    'Operating Expense': 'Chi phí hoạt động',
    'Research And Development': 'Chi phí nghiên cứu & phát triển',
    'Selling General And Administration': 'Chi phí bán hàng và quản lý doanh nghiệp',
    
    # Bảng cân đối kế toán (Balance Sheet)
    'Total Assets': 'Tổng tài sản',
    'Current Assets': 'Tài sản ngắn hạn',
    'Total Non Current Assets': 'Tài sản dài hạn',
    'Cash And Cash Equivalents': 'Tiền và các khoản tương đương tiền',
    'Inventory': 'Hàng tồn kho',
    'Accounts Receivable': 'Phải thu ngắn hạn của khách hàng',
    'Total Liabilities Net Minority Interest': 'Tổng nợ phải trả',
    'Current Liabilities': 'Nợ ngắn hạn',
    'Total Non Current Liabilities Net Minority Interest': 'Nợ dài hạn',
    'Stockholders Equity': 'Vốn chủ sở hữu',
    'Common Stock Equity': 'Vốn cổ phần phổ thông',
    'Total Debt': 'Tổng nợ vay',
    'Retained Earnings': 'Lợi nhuận chưa phân phối',
    
    # Báo cáo lưu chuyển tiền tệ (Cash Flow)
    'Operating Cash Flow': 'Lưu chuyển tiền thuần từ hoạt động kinh doanh',
    'Investing Cash Flow': 'Lưu chuyển tiền thuần từ hoạt động đầu tư',
    'Financing Cash Flow': 'Lưu chuyển tiền thuần từ hoạt động tài chính',
    'Free Cash Flow': 'Dòng tiền tự do',
    'Capital Expenditure': 'Chi phí đầu tư tài sản cố định (CapEx)',
    'Repayment Of Debt': 'Trả nợ gốc vay',
    'Issuance Of Debt': 'Phát hành thêm nợ vay',
    'Cash Dividends Paid': 'Cổ tức đã trả'
}

def translate_text(text):
    """Hàm chuyển đổi tên chỉ tiêu sang tiếng Việt, nếu không có giữ nguyên"""
    return TRANSLATION_MAP.get(text, text)

def main():
    print("🚀 Bắt đầu thu thập và Viết hóa Báo cáo tài chính cho VN30...")
    
    all_data = []
    current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    for symbol in SYMBOLS:
        print(f"Đang xử lý BCTC tiếng Việt cho mã: {symbol}...")
        try:
            ticker = yf.Ticker(f"{symbol}.VN")
            
            # 1. Kết quả kinh doanh
            income_stmt = ticker.financials
            if not income_stmt.empty:
                for date_col in income_stmt.columns:
                    date_str = str(date_col).split('T')[0]
                    for idx, val in income_stmt[date_col].items():
                        if pd.notna(val):
                            all_data.append({
                                'symbol': symbol,
                                'statement_type': translate_text('Income_Statement'),
                                'metric': translate_text(str(idx)),
                                'period_date': date_str,
                                'value': float(val),
                                'scrape_time': current_time
                            })
            
            # 2. Cân đối kế toán
            balance_sheet = ticker.balance_sheet
            if not balance_sheet.empty:
                for date_col in balance_sheet.columns:
                    date_str = str(date_col).split('T')[0]
                    for idx, val in balance_sheet[date_col].items():
                        if pd.notna(val):
                            all_data.append({
                                'symbol': symbol,
                                'statement_type': translate_text('Balance_Sheet'),
                                'metric': translate_text(str(idx)),
                                'period_date': date_str,
                                'value': float(val),
                                'scrape_time': current_time
                            })
                            
            # 3. Lưu chuyển tiền tệ
            cash_flow = ticker.cashflow
            if not cash_flow.empty:
                for date_col in cash_flow.columns:
                    date_str = str(date_col).split('T')[0]
                    for idx, val in cash_flow[date_col].items():
                        if pd.notna(val):
                            all_data.append({
                                'symbol': symbol,
                                'statement_type': translate_text('Cash_Flow'),
                                'metric': translate_text(str(idx)),
                                'period_date': date_str,
                                'value': float(val),
                                'scrape_time': current_time
                            })
                                
        except Exception as e:
            print(f"Lỗi khi lấy BCTC mã {symbol}: {e}")
            
    if all_data:
        df = pd.DataFrame(all_data)
        file_path = 'vietnam_financial_statements.csv'
        df.to_csv(file_path, index=False)
        print(f"✅ Đã lưu toàn bộ BCTC tiếng Việt vào file '{file_path}' thành công!")
    else:
        print("⚠️ Không thu thập được dữ liệu BCTC.")

if __name__ == "__main__":
    main()
