import os
import pandas as pd
from datetime import datetime
import yfinance as yf
import time

# Danh sách Master Universe đầy đủ theo mô hình phân loại FINEX (VN30, VN100, HNX30)
FINEX_UNIVERSE = [
    # --- NHÓM 1: SẢN XUẤT VÀ CÔNG NGHIỆP & PHI TÀI CHÍNH ---
    ('VIC', 'VN30', 'Sản xuất và công nghiệp'),
    ('VHM', 'VN30', 'Sản xuất và công nghiệp'),
    ('GAS', 'VN30', 'Sản xuất và công nghiệp'),
    ('MCH', 'VN100', 'Sản xuất và công nghiệp'),
    ('HPG', 'VN30', 'Sản xuất và công nghiệp'),
    ('VPL', 'VN30', 'Sản xuất và công nghiệp'),
    ('BSR', 'VN100', 'Sản xuất và công nghiệp'),
    ('GVR', 'VN30', 'Sản xuất và công nghiệp'),
    ('VNM', 'VN30', 'Sản xuất và công nghiệp'),
    ('MSN', 'VN30', 'Sản xuất và công nghiệp'),
    ('MWG', 'VN30', 'Sản xuất và công nghiệp'),
    ('VJC', 'VN30', 'Sản xuất và công nghiệp'),
    ('VRE', 'VN30', 'Sản xuất và công nghiệp'),
    ('SAB', 'VN30', 'Sản xuất và công nghiệp'),
    ('PLX', 'VN30', 'Sản xuất và công nghiệp'),
    ('BCM', 'VN100', 'Sản xuất và công nghiệp'),
    ('POW', 'VN100', 'Sản xuất và công nghiệp'),
    ('GMD', 'VN100', 'Sản xuất và công nghiệp'),
    ('GEX', 'VN100', 'Sản xuất và công nghiệp'),
    ('REE', 'VN100', 'Sản xuất và công nghiệp'),
    ('FRT', 'VN100', 'Sản xuất và công nghiệp'),
    ('NVL', 'VN100', 'Sản xuất và công nghiệp'),
    ('KBC', 'VN100', 'Sản xuất và công nghiệp'),
    ('VGC', 'VN100', 'Sản xuất và công nghiệp'),
    ('SBT', 'VN100', 'Sản xuất và công nghiệp'),
    ('VPI', 'VN100', 'Sản xuất và công nghiệp'),
    ('HAG', 'VN100', 'Sản xuất và công nghiệp'),
    ('DCM', 'VN100', 'Sản xuất và công nghiệp'),
    ('KDH', 'VN100', 'Sản xuất và công nghiệp'),
    ('PVD', 'VN100', 'Sản xuất và công nghiệp'),
    ('SJS', 'VN100', 'Sản xuất và công nghiệp'),
    ('DPM', 'VN100', 'Sản xuất và công nghiệp'),
    ('KDC', 'VN100', 'Sản xuất và công nghiệp'),
    ('DXG', 'VN100', 'Sản xuất và công nghiệp'),
    ('SIP', 'VN100', 'Sản xuất và công nghiệp'),
    ('PVT', 'VN100', 'Sản xuất và công nghiệp'),
    ('PDR', 'VN100', 'Sản xuất và công nghiệp'),
    ('TCH', 'VN100', 'Sản xuất và công nghiệp'),
    ('BAF', 'VN100', 'Sản xuất và công nghiệp'),
    ('BMP', 'VN100', 'Sản xuất và công nghiệp'),
    ('TAL', 'VN100', 'Sản xuất và công nghiệp'),
    ('NLG', 'VN100', 'Sản xuất và công nghiệp'),
    ('VHC', 'VN100', 'Sản xuất và công nghiệp'),
    ('VCG', 'VN100', 'Sản xuất và công nghiệp'),
    ('BWE', 'VN100', 'Sản xuất và công nghiệp'),
    ('PNJ', 'VN100', 'Sản xuất và công nghiệp'),
    ('CII', 'VN100', 'Sản xuất và công nghiệp'),
    ('HSG', 'VN100', 'Sản xuất và công nghiệp'),
    ('DIG', 'VN100', 'Sản xuất và công nghiệp'),
    ('PC1', 'VN100', 'Sản xuất và công nghiệp'),
    ('PHR', 'VN100', 'Sản xuất và công nghiệp'),
    ('CTD', 'VN100', 'Sản xuất và công nghiệp'),
    ('NT2', 'VN100', 'Sản xuất và công nghiệp'),
    ('DBC', 'VN100', 'Sản xuất và công nghiệp'),
    ('HDG', 'VN100', 'Sản xuất và công nghiệp'),
    ('NKG', 'VN100', 'Sản xuất và công nghiệp'),
    ('HHV', 'VN100', 'Sản xuất và công nghiệp'),
    ('VSC', 'VN100', 'Sản xuất và công nghiệp'),
    ('HT1', 'VN100', 'Sản xuất và công nghiệp'),
    ('ANV', 'VN100', 'Sản xuất và công nghiệp'),
    ('PAN', 'VN100', 'Sản xuất và công nghiệp'),
    ('KOS', 'VN100', 'Sản xuất và công nghiệp'),
    ('GEE', 'VN100', 'Sản xuất và công nghiệp'),
    ('DGC', 'VN30', 'Sản xuất và công nghiệp'),
    ('IDC', 'HNX30', 'Sản xuất và công nghiệp'),
    ('CAP', 'HNX30', 'Sản xuất và công nghiệp'),
    ('LAS', 'HNX30', 'Sản xuất và công nghiệp'),
    ('BCC', 'HNX30', 'Sản xuất và công nghiệp'),
    ('CEO', 'HNX30', 'Sản xuất và công nghiệp'),
    ('DTD', 'HNX30', 'Sản xuất và công nghiệp'),
    ('DVM', 'HNX30', 'Sản xuất và công nghiệp'),
    ('DXP', 'HNX30', 'Sản xuất và công nghiệp'),
    ('HLD', 'HNX30', 'Sản xuất và công nghiệp'),
    ('HUT', 'HNX30', 'Sản xuất và công nghiệp'),
    ('L14', 'HNX30', 'Sản xuất và công nghiệp'),
    ('L18', 'HNX30', 'Sản xuất và công nghiệp'),
    ('LHC', 'HNX30', 'Sản xuất và công nghiệp'),
    ('NBC', 'HNX30', 'Sản xuất và công nghiệp'),
    ('NDN', 'HNX30', 'Sản xuất và công nghiệp'),
    ('PLC', 'HNX30', 'Sản xuất và công nghiệp'),
    ('PVC', 'HNX30', 'Sản xuất và công nghiệp'),
    ('PVG', 'HNX30', 'Sản xuất và công nghiệp'),
    ('PVS', 'HNX30', 'Sản xuất và công nghiệp'),
    ('SLS', 'HNX30', 'Sản xuất và công nghiệp'),
    ('TIG', 'HNX30', 'Sản xuất và công nghiệp'),
    ('TNG', 'HNX30', 'Sản xuất và công nghiệp'),
    ('TVD', 'HNX30', 'Sản xuất và công nghiệp'),
    ('VC3', 'HNX30', 'Sản xuất và công nghiệp'),
    ('VCS', 'HNX30', 'Sản xuất và công nghiệp'),

    # --- NHÓM 2: CÔNG NGHỆ ---
    ('FPT', 'VN30', 'Công nghệ'),
    ('CMG', 'VN100', 'Công nghệ'),
    ('CTR', 'VN100', 'Công nghệ'),
    ('DGW', 'VN100', 'Công nghệ'),
    ('VTP', 'VN100', 'Công nghệ'),

    # --- NHÓM 3: TÀI CHÍNH (Ngân hàng, Chứng khoán, Bảo hiểm) ---
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
    ('MSB', 'VN100', 'Tài chính'),
    ('SHB', 'VN30', 'Tài chính'),
    ('SSB', 'VN30', 'Tài chính'),
    ('VIB', 'VN30', 'Tài chính'),
    ('TPB', 'VN30', 'Tài chính'),
    ('EIB', 'VN100', 'Tài chính'),
    ('OCB', 'VN100', 'Tài chính'),
    ('NAB', 'VN100', 'Tài chính'),
    ('SSI', 'VN30', 'Tài chính'),
    ('VCI', 'VN100', 'Tài chính'),
    ('HCM', 'VN100', 'Tài chính'),
    ('VND', 'VN100', 'Tài chính'),
    ('VIX', 'VN100', 'Tài chính'),
    ('FTS', 'VN100', 'Tài chính'),
    ('BSI', 'VN100', 'Tài chính'),
    ('CTS', 'VN100', 'Tài chính'),
    ('DSE', 'VN100', 'Tài chính'),
    ('EVF', 'VN100', 'Tài chính'),
    ('BVH', 'VN100', 'Tài chính'),
    ('BVS', 'HNX30', 'Tài chính'),
    ('MBS', 'HNX30', 'Tài chính'),
    ('PSI', 'HNX30', 'Tài chính'),
    ('SHS', 'HNX30', 'Tài chính'),
    ('VFS', 'HNX30', 'Tài chính')
]

# Từ điển Việt hóa toàn diện 100% các khoản mục BCTC và thị trường
TRANSLATION_MAP = {
    'Income_Statement': 'Báo cáo kết quả kinh doanh',
    'Balance_Sheet': 'Bảng cân đối kế toán',
    'Cash_Flow': 'Báo cáo lưu chuyển tiền tệ',
    'Market_Data': 'Dữ liệu thị trường',
    'Dividend_Data': 'Lịch sử cổ tức',
    
    # --- Kết quả kinh doanh ---
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
    'Interest Income': 'Thu nhập lãi và các khoản tương tự',
    'Interest Expense': 'Chi phí lãi và các chi phí tương tự',
    'Diluted EPS': 'Lãi suy giảm trên cổ phiếu (EPS)',
    'Basic EPS': 'Lãi cơ bản trên cổ phiếu (EPS)',
    'Tax Provision': 'Chi phí thuế thu nhập doanh nghiệp',
    
    # --- Bảng cân đối kế toán (Đã bao phủ toàn bộ các mục chi tiết) ---
    'Total Assets': 'Tổng tài sản',
    'Current Assets': 'Tài sản ngắn hạn',
    'Total Non Current Assets': 'Tài sản dài hạn',
    'Cash And Cash Equivalents': 'Tiền và các khoản tương đương tiền',
    'Cash Cash Equivalents And Federal Funds Sold': 'Tiền, tương đương tiền và tiền gửi liên ngân hàng',
    'Cash Equivalents': 'Các khoản tương đương tiền',
    'Cash Financial': 'Tiền mặt và tài sản tài chính tương đương',
    'Inventory': 'Hàng tồn kho',
    'Other Inventories': 'Hàng tồn kho khác',
    'Finished Goods': 'Thành phẩm',
    'Accounts Receivable': 'Phải thu ngắn hạn của khách hàng',
    'Gross Accounts Receivable': 'Phải thu khách hàng (nguyên giá)',
    'Other Receivables': 'Các khoản phải thu khác',
    'Taxes Receivable': 'Thuế và các khoản phải thu nhà nước',
    'Net Loan': 'Cho vay khách hàng (Cho vay ròng)',
    'Other Short Term Investments': 'Đầu tư tài chính ngắn hạn khác',
    
    'Gross PPE': 'Nguyên giá tài sản cố định hữu hình',
    'Accumulated Depreciation': 'Hao mòn tài sản cố định lũy kế',
    'Net PPE': 'Tài sản cố định hữu hình (ròng)',
    'Buildings And Improvements': 'Nhà cửa và vật kiến trúc',
    'Machinery Furniture Equipment': 'Máy móc, thiết bị và dụng cụ quản lý',
    'Construction In Progress': 'Chi phí xây dựng cơ bản dở dang',
    'Other Properties': 'Bất động sản và tài sản khác',
    'Prepaid Assets': 'Chi phí trả trước',
    
    'Total Liabilities Net Minority Interest': 'Tổng nợ phải trả',
    'Current Liabilities': 'Nợ ngắn hạn',
    'Total Non Current Liabilities Net Minority Interest': 'Nợ dài hạn',
    'Stockholders Equity': 'Vốn chủ sở hữu',
    'Common Stock Equity': 'Vốn cổ phần phổ thông',
    'Common Stock': 'Cổ phiếu phổ thông',
    'Capital Stock': 'Vốn điều lệ / Vốn góp chủ sở hữu',
    'Additional Paid In Capital': 'Thặng dư vốn cổ phần',
    'Retained Earnings': 'Lợi nhuận chưa phân phối',
    'Total Debt': 'Tổng nợ vay',
    'Net Debt': 'Nợ vay ròng',
    'Tangible Book Value': 'Giá trị sổ sách hữu hình',
    'Net Tangible Assets': 'Tài sản hữu hình ròng',
    
    'Payables': 'Các khoản phải trả',
    'Accounts Payable': 'Phải trả người bán ngắn hạn',
    'Total Tax Payable': 'Thuế và các khoản phải nộp nhà nước',
    'Other Payable': 'Các khoản phải trả khác',
    
    # --- Lưu chuyển tiền tệ ---
    'Operating Cash Flow': 'Lưu chuyển tiền thuần từ hoạt động kinh doanh',
    'Investing Cash Flow': 'Lưu chuyển tiền thuần từ hoạt động đầu tư',
    'Financing Cash Flow': 'Lưu chuyển tiền thuần từ hoạt động tài chính',
    'Free Cash Flow': 'Dòng tiền tự do (FCF)',
    'Capital Expenditure': 'Chi phí đầu tư tài sản cố định (CapEx)',
    
    # --- Dữ liệu thị trường & Cổ tức ---
    'Close Price': 'Giá đóng cửa',
    'Volume': 'Khối lượng giao dịch',
    'Dividend Payout': 'Cổ tức tiền mặt'
}

def translate_metric(metric_name):
    """Hàm ánh xạ chuyển đổi tên chỉ tiêu sang tiếng Việt chuẩn xác"""
    return TRANSLATION_MAP.get(metric_name, metric_name)

def main():
    print(f"🚀 [FINEX Pipeline] Bắt đầu thu thập, làm sạch và chuẩn hóa nhãn cho {len(FINEX_UNIVERSE)} mã chứng khoán...")
    
    all_data = []
    current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    for symbol, chi_so, nhom_nganh in FINEX_UNIVERSE:
        print(f"🔄 Đang xử lý: [{chi_so}] {symbol} - {nhom_nganh}...")
        try:
            ticker = yf.Ticker(f"{symbol}.VN")
            
            # 1. Thu thập dữ liệu thị trường sạch
            hist = ticker.history(period="1d")
            if not hist.empty:
                latest = hist.iloc[-1]
                current_year = str(datetime.now().year)
                all_data.append({
                    'ma_chung_khoan': symbol,
                    'chi_so': chi_so,
                    'nhom_nganh_finex': nhom_nganh,
                    'statement_type': TRANSLATION_MAP['Market_Data'],
                    'nam': current_year,
                    'period_date': datetime.now().strftime('%Y-%m-%d'),
                    'metric': TRANSLATION_MAP['Close Price'],
                    'value': float(latest['Close']),
                    'scrape_time': current_time
                })
                all_data.append({
                    'ma_chung_khoan': symbol,
                    'chi_so': chi_so,
                    'nhom_nganh_finex': nhom_nganh,
                    'statement_type': TRANSLATION_MAP['Market_Data'],
                    'nam': current_year,
                    'period_date': datetime.now().strftime('%Y-%m-%d'),
                    'metric': TRANSLATION_MAP['Volume'],
                    'value': float(latest['Volume']),
                    'scrape_time': current_time
                })

            # 2. Thu thập lịch sử cổ tức sạch
            dividends = ticker.dividends
            if dividends is not None and not dividends.empty:
                for date_idx, div_val in dividends.items():
                    if pd.notna(div_val) and div_val > 0:
                        date_str = str(date_idx).split('T')[0].split(' ')[0]
                        year_val = date_str.split('-')[0]
                        all_data.append({
                            'ma_chung_khoan': symbol,
                            'chi_so': chi_so,
                            'nhom_nganh_finex': nhom_nganh,
                            'statement_type': TRANSLATION_MAP['Dividend_Data'],
                            'nam': year_val,
                            'period_date': date_str,
                            'metric': TRANSLATION_MAP['Dividend Payout'],
                            'value': float(div_val),
                            'scrape_time': current_time
                        })

            # 3. Thu thập Báo cáo tài chính (Làm sạch: lọc bỏ NaN, giá trị 0 và chuẩn hóa nhãn Việt hóa)
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
                        year_val = date_str.split('-')[0]
                        
                        for idx, val in df_stmt[date_col].items():
                            # Lọc dữ liệu sạch theo chuẩn MLOps: Bỏ qua NaN và giá trị bằng 0
                            if pd.notna(val) and val != 0:
                                raw_metric = str(idx)
                                clean_metric = translate_metric(raw_metric)
                                
                                # Chỉ đưa vào dữ liệu nếu chỉ tiêu đã được định danh rõ ràng
                                all_data.append({
                                    'ma_chung_khoan': symbol,
                                    'chi_so': chi_so,
                                    'nhom_nganh_finex': nhom_nganh,
                                    'statement_type': vn_stmt_name,
                                    'nam': year_val,
                                    'period_date': date_str,
                                    'metric': clean_metric,
                                    'value': float(val),
                                    'scrape_time': current_time
                                })
                                
            time.sleep(0.3)
        except Exception as e:
            print(f"❌ Lỗi xử lý mã {symbol}: {e}")
            
    if all_data:
        df_final = pd.DataFrame(all_data)
        
        # Sắp xếp đúng chuẩn cấu trúc trường dữ liệu FINEX đề xuất
        df_final = df_final[[
            'ma_chung_khoan', 'chi_so', 'nhom_nganh_finex', 
            'statement_type', 'nam', 'period_date', 'metric', 'value', 'scrape_time'
        ]]
        
        file_path = 'vietnam_financial_statements.csv'
        df_final.to_csv(file_path, index=False)
        print(f"✅ Hoàn tất đường ống dữ liệu! Đã lưu thành công {len(df_final)} bản ghi chuẩn sạch vào '{file_path}'.")
    else:
        print("⚠️ Không thu thập được dữ liệu.")

if __name__ == "__main__":
    main()
