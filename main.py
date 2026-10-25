import os
import sqlite3
import time
from datetime import datetime
import pandas as pd
import yfinance as yf

# --- 1. DANH SÁCH ĐẦY ĐỦ 130 MÃ (VN100 + HNX30) ---
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

def get_sector(symbol):
    if symbol in ["FPT", "CMG", "VTP", "ICT", "ELC"]:
        return "Công nghệ"
    elif symbol in ["VCB", "BID", "TCB", "MBB", "ACB", "CTG", "VPB", "STB", "SSI", "VCI", "HCM", "VND", "SHB", "HDB", "LPB", "MSB", "OCB", "NAB", "SSB", "EIB", "BSI", "CTS", "FTS", "MBS", "BVS"]:
        return "Tài chính & Ngân hàng"
    else:
        return "Sản xuất, Bất động sản và Công nghiệp"

# --- 2. TỪ ĐIỂN VIỆT HÓA TOÀN DIỆN (Bao phủ 3 bảng báo cáo & thị trường) ---
TRANSLATION_MAP = {
    # Loại báo cáo
    'Income_Statement': 'Báo cáo kết quả kinh doanh',
    'Balance_Sheet': 'Bảng cân đối kế toán',
    'Cash_Flow': 'Báo cáo lưu chuyển tiền tệ',
    'Market_Data': 'Dữ liệu thị trường',

    # --- BẢNG CÂN ĐỐI KẾ TOÁN (Balance Sheet) ---
    'Total Assets': 'Tổng tài sản',
    'Current Assets': 'Tài sản ngắn hạn',
    'Cash And Cash Equivalents': 'Tiền và các khoản tương đương tiền',
    'Cash Cash Equivalents And Short Term Investments': 'Tiền, tương đương tiền và đầu tư ngắn hạn',
    'Receivables': 'Các khoản phải thu',
    'Accounts Receivable': 'Phải thu ngắn hạn khách hàng',
    'Inventory': 'Hàng tồn kho',
    'Total Non Current Assets': 'Tổng tài sản dài hạn',
    'Net PPE': 'Tài sản cố định thuần',
    'Long Term Equity Investment': 'Đầu tư tài chính dài hạn',
    
    'Total Liabilities Net Minority Interest': 'Tổng nợ phải trả',
    'Current Liabilities': 'Nợ ngắn hạn',
    'Payables And Accrued Expenses': 'Phải trả người bán và chi phí phải trả',
    'Accounts Payable': 'Phải trả người bán ngắn hạn',
    'Current Debt': 'Vay và nợ thuê tài chính ngắn hạn',
    'Total Non Current Liabilities Net Minority Interest': 'Nợ dài hạn',
    'Long Term Debt': 'Vay và nợ thuê tài chính dài hạn',
    
    'Stockholders Equity': 'Vốn chủ sở hữu',
    'Common Stock Equity': 'Vốn góp cổ phần phổ thông',
    'Retained Earnings': 'Lợi nhuận sau thuế chưa phân phối',
    'Capital Stock': 'Vốn đầu tư của chủ sở hữu',
    'Total Capitalization': 'Tổng nguồn vốn',

    # --- BÁO CÁO KẾT QUẢ KINH DOANH (Income Statement) ---
    'Total Revenue': 'Tổng doanh thu',
    'Operating Revenue': 'Doanh thu hoạt động',
    'Cost Of Revenue': 'Giá vốn hàng bán',
    'Gross Profit': 'Lợi nhuận gộp',
    'Operating Income': 'Lợi nhuận thuần từ hoạt động kinh doanh',
    'Net Income': 'Lợi nhuận sau thuế (Lợi nhuận ròng)',
    'Net Income Common Stockholders': 'Lợi nhuận sau thuế cổ đông công ty mẹ',
    'EBIT': 'Lợi nhuận trước lãi vay và thuế (EBIT)',
    'EBITDA': 'Lợi nhuận trước thuế, lãi vay và khấu hao (EBITDA)',
    'Interest Expense': 'Chi phí lãi vay',
    'Selling General And Administration': 'Chi phí bán hàng và quản lý doanh nghiệp',
    'Normalized Income': 'Lợi nhuận chuẩn hóa',
    'Tax Provision': 'Chi phí thuế thu nhập doanh nghiệp',
    'Pretax Income': 'Lợi nhuận kế toán trước thuế',
    'Diluted EPS': 'Lãi suy giảm trên cổ phiếu (Diluted EPS)',
    'Basic EPS': 'Lãi cơ bản trên cổ phiếu (Basic EPS)',

    # --- BÁO CÁO LƯU CHUYỂN TIỀN TỆ (Cash Flow) ---
    'Operating Cash Flow': 'Lưu chuyển tiền thuần từ hoạt động kinh doanh',
    'Investing Cash Flow': 'Lưu chuyển tiền thuần từ hoạt động đầu tư',
    'Financing Cash Flow': 'Lưu chuyển tiền thuần từ hoạt động tài chính',
    'End Cash Position': 'Tiền và tương đương tiền cuối kỳ',
    'Beginning Cash Position': 'Tiền và tương đương tiền đầu kỳ',
    'Changes In Cash': 'Biến động tiền thuần trong kỳ',
    'Capital Expenditure': 'Chi phí đầu tư tài sản cố định (CapEx)',
    'Free Cash Flow': 'Dòng tiền tự do (FCF)',
    'Repayment Of Debt': 'Trả nợ gốc vay',
    'Issuance Of Debt': 'Phát hành nợ vay',

    # --- DỮ LIỆU THỊ TRƯỜNG ---
    'Close Price': 'Giá đóng cửa',
    'Volume': 'Khối lượng giao dịch'
}

def translate_metric(metric_name):
    """Hàm ánh xạ thông minh, tự động tra từ điển hoặc giữ nguyên dạng sạch nếu chưa có."""
    clean_name = str(metric_name).strip()
    if clean_name in TRANSLATION_MAP:
        return TRANSLATION_MAP[clean_name]
    # Fallback thông minh: nếu không có trong từ điển, giữ nguyên nhưng loại bỏ các ký tự rác
    return clean_name

def main():
    print(f"==================================================")
    print(f" [FINEX Terminal] Khởi chạy đường ống cào dữ liệu toàn diện")
    print(f" Tổng số mã mục tiêu: {len(ALL_TARGET_STOCKS)} mã (VN100 + HNX30)")
    print(f"==================================================")
    
    all_records = []
    current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    current_year = str(datetime.now().year)
    
    success_count = 0
    fail_count = 0
    
    for idx, symbol in enumerate(ALL_TARGET_STOCKS, 1):
        print(f"⏳ [{idx}/{len(ALL_TARGET_STOCKS)}] Đang xử lý triệt để mã: {symbol}...")
        try:
            ticker = yf.Ticker(f"{symbol}.VN")
            
            # 1. Cào Dữ liệu thị trường (Market Data)
            hist = ticker.history(period="5d")
            if hist is not None and not hist.empty:
                latest = hist.iloc[-1]
                date_str = str(hist.index[-1]).split('T')[0].split(' ')[0]
                
                all_records.append({
                    'ma_chung_khoan': symbol,
                    'nhom_nganh': get_sector(symbol),
                    'loai_bao_cao': TRANSLATION_MAP['Market_Data'],
                    'nam': current_year,
                    'ngay_ky': date_str,
                    'chi_tieu_goc': 'Close Price',
                    'chi_tieu_tieng_viet': TRANSLATION_MAP['Close Price'],
                    'gia_tri': float(latest['Close']),
                    'thoi_gian_cap_nhat': current_time
                })
                all_records.append({
                    'ma_chung_khoan': symbol,
                    'nhom_nganh': get_sector(symbol),
                    'loai_bao_cao': TRANSLATION_MAP['Market_Data'],
                    'nam': current_year,
                    'ngay_ky': date_str,
                    'chi_tieu_goc': 'Volume',
                    'chi_tieu_tieng_viet': TRANSLATION_MAP['Volume'],
                    'gia_tri': float(latest['Volume']),
                    'thoi_gian_cap_nhat': current_time
                })

            # 2. Cào Triệt để 3 Báo cáo tài chính (Income Statement, Balance Sheet, Cash Flow)
            statements_dict = {
                'Income_Statement': getattr(ticker, 'financials', None),
                'Balance_Sheet': getattr(ticker, 'balance_sheet', None),
                'Cash_Flow': getattr(ticker, 'cashflow', None)
            }
            
            for stmt_key, df_stmt in statements_dict.items():
                if df_stmt is not None and not df_stmt.empty:
                    vn_stmt_name = TRANSLATION_MAP.get(stmt_key, stmt_key)
                    
                    # Duyệt qua từng cột (từng kỳ báo cáo)
                    for col in df_stmt.columns:
                        date_str = str(col).split('T')[0].split(' ')[0]
                        year_val = date_str.split('-')[0]
                        
                        # Duyệt qua từng dòng chỉ tiêu tài chính
                        for row_idx, val in df_stmt[col].items():
                            if pd.notna(val):
                                metric_original = str(row_idx)
                                translated_metric = translate_metric(metric_original)
                                
                                all_records.append({
                                    'ma_chung_khoan': symbol,
                                    'nhom_nganh': get_sector(symbol),
                                    'loai_bao_cao': vn_stmt_name,
                                    'nam': year_val,
                                    'ngay_ky': date_str,
                                    'chi_tieu_goc': metric_original,
                                    'chi_tieu_tieng_viet': translated_metric,
                                    'gia_tri': float(val),
                                    'thoi_gian_cap_nhat': current_time
                                })
            
            success_count += 1
            time.sleep(0.15) # Nghỉ ngắn an toàn chống quá tải kết nối
            
        except Exception as e:
            fail_count += 1
            print(f"⚠️ Cảnh báo: Lỗi khi xử lý mã {symbol}: {e}")
            continue

    # --- 3. LÀM SẠCH VÀ CHUẨN HÓA DỮ LIỆU 100% ---
    if all_records:
        df_final = pd.DataFrame(all_records)
    else:
        df_final = pd.DataFrame(columns=[
            'ma_chung_khoan', 'nhom_nganh', 'loai_bao_cao', 'nam', 
            'ngay_ky', 'chi_tieu_goc', 'chi_tieu_tieng_viet', 'gia_tri', 'thoi_gian_cap_nhat'
        ])

    # Làm sạch dữ liệu: Loại bỏ bản ghi trùng lặp, xử lý giá trị NaN/Null
    df_final = df_final.drop_duplicates()
    df_final['gia_tri'] = df_final['gia_tri'].fillna(0)
    
    # Sắp xếp lại trật tự dữ liệu khoa học
    df_final = df_final.sort_values(
        by=['ma_chung_khoan', 'nam', 'loai_bao_cao'], 
        ascending=[True, False, True]
    )

    # --- 4. LƯU TRỮ VÀ XUẤT KẾT QUẢ ---
    # Xuất file CSV dự phòng
    csv_filename = 'vietnam_financial_statements_full.csv'
    df_final.to_csv(csv_filename, index=False, encoding='utf-8-sig')
    print(f"✅ Đã xuất file CSV thành công: {csv_filename} ({len(df_final)} dòng dữ liệu).")

    # Lưu trữ triệt để vào SQLite Database (vietnam_stock_database.db)
    db_filename = 'vietnam_stock_database.db'
    conn = sqlite3.connect(db_filename)
    df_final.to_sql('financial_statements', conn, if_exists='replace', index=False)
    conn.close()
    
    print(f"==================================================")
    print(f" 🎉 HOÀN TẤT TOÀN BỘ QUÁ TRÌNH CÀO VÀ LÀM SẠCH!")
    print(f" - Thành công: {success_count} mã")
    print(f" - Thất bại/Bỏ qua: {fail_count} mã")
    print(f" - Cơ sở dữ liệu: {db_filename} (Bảng: financial_statements)")
    print(f"==================================================")

if __name__ == "__main__":
    main()
