import os
import pandas as pd
from datetime import datetime
import yfinance as yf
import time

# Danh sách master cổ phiếu theo mô hình phân loại FINEX (VN30, VN100, HNX30)
FINEX_UNIVERSE = [
    # --- VN30 & VN100 Nhóm Sản xuất & Phi tài chính ---
    ('VIC', 'VN30', 'Sản xuất và công nghiệp'),
    ('VHM', 'VN30', 'Sản xuất và công nghiệp'),
    ('GAS', 'VN30', 'Sản xuất và công nghiệp'),
    ('HPG', 'VN30', 'Sản xuất và công nghiệp'),
    ('MSN', 'VN30', 'Sản xuất và công nghiệp'),
    ('MWG', 'VN30', 'Sản xuất và công nghiệp'),
    ('PLX', 'VN30', 'Sản xuất và công nghiệp'),
    ('SAB', 'VN30', 'Sản xuất và công nghiệp'),
    ('VJC', 'VN30', 'Sản xuất và công nghiệp'),
    ('VNM', 'VN30', 'Sản xuất và công nghiệp'),
    ('VPL', 'VN30', 'Sản xuất và công nghiệp'),
    ('VRE', 'VN30', 'Sản xuất và công nghiệp'),
    ('DGC', 'VN30', 'Sản xuất và công nghiệp'),
    ('GVR', 'VN30', 'Sản xuất và công nghiệp'),
    
    # --- VN30 Nhóm Công nghệ ---
    ('FPT', 'VN30', 'Công nghệ'),
    
    # --- VN30 Nhóm Tài chính ---
    ('VCB', 'VN30', 'Tài chính'),
    ('BID', 'VN30', 'Tài chính'),
    ('TCB', 'VN30', 'Tài chính'),
    ('VPB', 'VN30', 'Tài chính'),
    ('CTG', 'VN30', 'Tài chính'),
    ('MBB', 'VN30', 'Tài chính'),
    ('STB', 'VN30', 'Tài chính'),
    ('ACB', 'VN30', 'Tài chính'),
    ('LPB', 'VN30', 'Tài chính'),
    ('HDB', 'VN30', 'Tài chính'),
    ('SHB', 'VN30', 'Tài chính'),
    ('SSB', 'VN30', 'Tài chính'),
    ('SSI', 'VN30', 'Tài chính'),
    ('TPB', 'VN30', 'Tài chính'),
    ('VIB', 'VN30', 'Tài chính'),

    # --- Bổ sung các mã tiêu biểu trong VN100 & HNX30 ---
    ('BSR', 'VN100', 'Sản xuất và công nghiệp'),
    ('POW', 'VN100', 'Sản xuất và công nghiệp'),
    ('GMD', 'VN100', 'Sản xuất và công nghiệp'),
    ('GEX', 'VN100', 'Sản xuất và công nghiệp'),
    ('REE', 'VN100', 'Sản xuất và công nghiệp'),
    ('FRT', 'VN100', 'Sản xuất và công nghiệp'),
    ('KBC', 'VN100', 'Sản xuất và công nghiệp'),
    ('PNJ', 'VN100', 'Sản xuất và công nghiệp'),
    ('HSG', 'VN100', 'Sản xuất và công nghiệp'),
    ('DIG', 'VN100', 'Sản suất và công nghiệp'),
    ('IDC', 'HNX30', 'Sản xuất và công nghiệp'),
    ('PVS', 'HNX30', 'Sản xuất và công nghiệp'),
    ('CEO', 'HNX30', 'Sản xuất và công nghiệp'),
    ('TNG', 'HNX30', 'Sản xuất và công nghiệp'),
    ('SHS', 'HNX30', 'Tài chính'),
    ('MBS', 'HNX30', 'Tài chính'),
    ('VFS', 'HNX30', 'Tài chính'),
    ('CMG', 'VN100', 'Công nghệ'),
    ('CTR', 'VN100', 'Công nghệ'),
    ('DGW', 'VN100', 'Công nghệ'),
    ('VTP', 'VN100', 'Công nghệ')
]

# Từ điển ánh xạ tiếng Anh sang tiếng Việt toàn diện cho BCTC và thị trường
TRANSLATION_MAP = {
    'Income_Statement': 'Báo cáo kết quả kinh doanh',
    'Balance_Sheet': 'Bảng cân đối kế toán',
    'Cash_Flow': 'Báo cáo lưu chuyển tiền tệ',
    'Market_Data': 'Dữ liệu thị trường',
    'Dividend_Data': 'Lịch sử cổ tức',
    
    # Kết quả kinh doanh & Chỉ tiêu cốt lõi
    'Total Revenue': 'Tổng doanh thu',
    'Operating Revenue': 'Doanh thu hoạt động',
    'Cost Of Revenue': 'Giá vốn hàng bán',
    'Gross Profit': 'Lợi nhuận gộp',
    'Operating Income': 'Lợi nhuận thuần từ hoạt động kinh doanh',
    'Net Income': 'Lợi nhuận sau thuế (Lợi nhuận ròng)',
    'EBIT': 'Lợi nhuận trước lãi vay và thuế (EBIT)',
    'EBITDA': 'Lợi nhuận trước thuế, lãi vay và khấu hao (EBITDA)',
    'Pretax Income': 'Lợi nhuận trước thuế',
    'Net Interest Income': 'Thu nhập lãi thuần',
    'Interest Income': 'Thu nhập lãi và các khoản thu nhập tương tự',
    'Interest Expense': 'Chi phí lãi và các chi phí tương tự',
    'Diluted EPS': 'Lãi suy giảm trên cổ phiếu',
    'Basic EPS': 'Lãi cơ bản trên cổ phiếu',
    'Tax Provision': 'Chi phí thuế TNDN',
    
    # Cân đối kế toán
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
    
    # Lưu chuyển tiền tệ
    'Operating Cash Flow': 'Lưu chuyển tiền thuần từ hoạt động kinh doanh',
    'Investing Cash Flow': 'Lưu chuyển tiền thuần từ hoạt động đầu tư',
    'Financing Cash Flow': 'Lưu chuyển tiền thuần từ hoạt động tài chính',
    'Free Cash Flow': 'Dòng tiền tự do',
    'Capital Expenditure': 'Chi phí đầu tư TSCĐ (CapEx)',
    
    # Dữ liệu thị trường & Cổ tức
    'Close Price': 'Giá đóng cửa phiên gần nhất',
    'Volume': 'Khối lượng giao dịch phiên gần nhất',
    'Dividend Payout': 'Cổ tức chi trả bằng tiền'
}

def translate_metric(metric_name):
    return TRANSLATION_MAP.get(metric_name, metric_name)

def main():
    print("🚀 [FINEX Engine] Bắt đầu thu thập toàn diện: BCTC, Giá, Khối lượng và Cổ tức...")
    
    all_data = []
    current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    for symbol, chi_so, nhom_nganh in FINEX_UNIVERSE:
        print(f"🔄 Đang xử lý: [{chi_so}] {symbol} - {nhom_nganh}...")
        try:
            ticker = yf.Ticker(f"{symbol}.VN")
            
            # 1. Thu thập Dữ liệu thị trường (Giá & Khối lượng mới nhất)
            hist = ticker.history(period="1d")
            if not hist.empty:
                latest = hist.iloc[-1]
                all_data.append({
                    'ma_chung_khoan': symbol,
                    'chi_so': chi_so,
                    'nhom_nganh_finex': nhom_nganh,
                    'statement_type': TRANSLATION_MAP['Market_Data'],
                    'metric': TRANSLATION_MAP['Close Price'],
                    'period_date': datetime.now().strftime('%Y-%m-%d'),
                    'value': float(latest['Close']),
                    'scrape_time': current_time
                })
                all_data.append({
                    'ma_chung_khoan': symbol,
                    'chi_so': chi_so,
                    'nhom_nganh_finex': nhom_nganh,
                    'statement_type': TRANSLATION_MAP['Market_Data'],
                    'metric': TRANSLATION_MAP['Volume'],
                    'period_date': datetime.now().strftime('%Y-%m-%d'),
                    'value': float(latest['Volume']),
                    'scrape_time': current_time
                })

            # 2. Thu thập Lịch sử Cổ tức (Dividends)
            dividends = ticker.dividends
            if dividends is not None and not dividends.empty:
                for date_idx, div_val in dividends.items():
                    if pd.notna(div_val) and div_val > 0:
                        date_str = str(date_idx).split('T')[0].split(' ')[0]
                        all_data.append({
                            'ma_chung_khoan': symbol,
                            'chi_so': chi_so,
                            'nhom_nganh_finex': nhom_nganh,
                            'statement_type': TRANSLATION_MAP['Dividend_Data'],
                            'metric': TRANSLATION_MAP['Dividend Payout'],
                            'period_date': date_str,
                            'value': float(div_val),
                            'scrape_time': current_time
                        })

            # 3. Thu thập Báo cáo tài chính (Cân đối kế toán, KQKD, Lưu chuyển tiền tệ)
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
                            if pd.notna(val) and val != 0:
                                clean_metric = translate_metric(str(idx))
                                all_data.append({
                                    'ma_chung_khoan': symbol,
                                    'chi_so': chi_so,
                                    'nhom_nganh_finex': nhom_nganh,
                                    'statement_type': vn_stmt_name,
                                    'metric': clean_metric,
                                    'period_date': date_str,
                                    'value': float(val),
                                    'scrape_time': current_time
                                })
                                
            time.sleep(0.5) # Nghỉ ngắn chống nghẽn request
        except Exception as e:
            print(f"❌ Lỗi xử lý mã {symbol}: {e}")
            
    if all_data:
        df_final = pd.DataFrame(all_data)
        
        # Sắp xếp đúng chuẩn cấu trúc trường dữ liệu FINEX đề xuất
        df_final = df_final[[
            'ma_chung_khoan', 'chi_so', 'nhom_nganh_finex', 
            'statement_type', 'metric', 'period_date', 'value', 'scrape_time'
        ]]
        
        file_path = 'vietnam_financial_statements.csv'
        df_final.to_csv(file_path, index=False)
        print(f"✅ Hoàn tất! Đã lưu thành công {len(df_final)} bản ghi (Giá, Khối lượng, Cổ tức, BCTC) vào '{file_path}'.")
    else:
        print("⚠️ Không thu thập được dữ liệu.")

if __name__ == "__main__":
    main()
