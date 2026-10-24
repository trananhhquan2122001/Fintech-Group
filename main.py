import os
import pandas as pd
from datetime import datetime
import yfinance as yf
import time
import sqlite3

# --- 1. DANH SÁCH 2 SÀN LỚN (HOSE & HNX) ---
HOSE_LIST = [
    "ACB", "BCM", "BID", "BSI", "BSR", "BVH", "BWE", "CII",
    "CMG", "CTD", "CTG", "CTR", "CTS", "DGC", "DGW", "DIG",
    "DPM", "DSE", "DXG", "EIB", "EVF", "FPT", "FRT", "FTS",
    "GAS", "GEE", "GEX", "GMD", "GVR", "HAG", "HCM", "HDB",
    "HDG", "HHV", "HSG", "HT1", "HPG", "KBC", "KDC", "KDH",
    "LPB", "MBB", "MCH", "MSB", "MSN", "MWG", "NAB", "NKG",
    "NLG", "NT2", "NVL", "OCB", "PAN", "PC1", "PDR", "PHR",
    "PLX", "PNJ", "POW", "PVD", "PVT", "REE", "SAB", "SBT",
    "SHB", "SIP", "SSB", "SSI", "STB", "TCB", "TCX", "TCH",
    "TPB", "VCB", "VCI", "VCG", "VCK", "VGC", "VHC", "VIB",
    "VIC", "VIX", "VJC", "VND", "VNM", "VPI", "VPB", "VRE",
    "VHM", "VPL", "VTP", "ANV", "BAF", "BMP", "DBC", "DCM",
    "FMC", "HDC", "KOS", "MPC", "QCG", "SZC", "TAL", "VSC",
    "VTO", "YEG"
]

HNX_LIST = [
    "BCC", "BVS", "CAP", "CEO", "DTD", "DVM", "DXP", "HLD",
    "HUT", "IDC", "L14", "L18", "LAS", "LHC", "MBS", "NBC",
    "NDN", "PLC", "PSI", "PVC", "PVG", "PVS", "SHS", "SLS",
    "TIG", "TNG", "TVD", "VC3", "VCS", "VFS"
]

TECH_SECTOR = {"FPT", "CMG", "CTR", "DGW", "VTP", "FOX"}
FINANCE_SECTOR = {
    "ACB", "BID", "CTG", "EIB", "HDB", "LPB", "MBB", "MSB", "NAB", "OCB", 
    "SHB", "SSB", "STB", "TCB", "TPB", "VCB", "VIB", "VPB", "SHS", "SSI", 
    "VCI", "HCM", "VND", "VIX", "FTS", "BSI", "CTS", "MBS", "BVS", "PSI", 
    "VFS", "EVF", "BVH", "DSE", "BSR"
]

def classify_sector(symbol):
    if symbol in TECH_SECTOR:
        return 'Công nghệ'
    elif symbol in FINANCE_SECTOR:
        return 'Tài chính'
    else:
        return 'Sản xuất và công nghiệp'

FINEX_UNIVERSE = []
for s in HOSE_LIST:
    FINEX_UNIVERSE.append((s, 'HOSE', classify_sector(s)))
for s in HNX_LIST:
    FINEX_UNIVERSE.append((s, 'HNX', classify_sector(s)))

# --- 2. TỪ ĐIỂN VIỆT HÓA TOÀN DIỆN ---
TRANSLATION_MAP = {
    'Income_Statement': 'Báo cáo kết quả kinh doanh',
    'Balance_Sheet': 'Bảng cân đối kế toán',
    'Cash_Flow': 'Báo cáo lưu chuyển tiền tệ',
    'Market_Data': 'Dữ liệu thị trường',
    'Dividend_Data': 'Lịch sử cổ tức',
    
    # Kết quả kinh doanh
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
    'Diluted EPS': 'Lãi suy giảm trên cổ phiếu (EPS pha loãng)',
    'Basic EPS': 'Lãi cơ bản trên cổ phiếu (EPS cơ bản)',
    'Tax Provision': 'Chi phí thuế thu nhập doanh nghiệp',
    'Operating Expense': 'Chi phí hoạt động',
    'Selling General And Administration': 'Chi phí bán hàng và quản lý doanh nghiệp',
    'General And Administrative Expense': 'Chi phí quản lý doanh nghiệp',
    'Research And Development': 'Chi phí nghiên cứu và phát triển',
    'Net Income Common Stockholders': 'Lợi nhuận phân bổ cho cổ đông phổ thông',
    'Minority Interests': 'Lợi ích cổ đông không kiểm soát',

    # Cân đối kế toán & Cổ phiếu
    'Total Assets': 'Tổng tài sản',
    'Current Assets': 'Tài sản ngắn hạn',
    'Total Non Current Assets': 'Tài sản dài hạn',
    'Cash And Cash Equivalents': 'Tiền và các khoản tương đương tiền',
    'Cash Equivalents': 'Các khoản tương đương tiền',
    'Inventory': 'Hàng tồn kho',
    'Accounts Receivable': 'Phải thu ngắn hạn của khách hàng',
    'Net Loan': 'Cho vay khách hàng (Cho vay ròng)',
    'Total Liabilities Net Minority Interest': 'Tổng nợ phải trả',
    'Current Liabilities': 'Nợ ngắn hạn',
    'Total Non Current Liabilities Net Minority Interest': 'Nợ dài hạn',
    'Stockholders Equity': 'Vốn chủ sở hữu',
    'Common Stock Equity': 'Vốn cổ phần phổ thông',
    'Common Stock': 'Cổ phiếu phổ thông',
    'Capital Stock': 'Vốn điều lệ / Vốn góp',
    'Additional Paid In Capital': 'Thặng dư vốn cổ phần',
    'Retained Earnings': 'Lợi nhuận chưa phân phối',
    'Total Debt': 'Tổng nợ vay',
    'Net Debt': 'Nợ vay ròng',
    'Net PPE': 'Tài sản cố định hữu hình (ròng)',
    'Gross PPE': 'Nguyên giá tài sản cố định hữu hình',
    'Accumulated Depreciation': 'Hao mòn tài sản cố định lũy kế',
    'Construction In Progress': 'Chi phí xây dựng cơ bản dở dang',
    'Goodwill And Other Intangible Assets': 'Lợi thế thương mại và tài sản vô hình',
    'Payables': 'Các khoản phải trả',
    'Accounts Payable': 'Phải trả người bán ngắn hạn',
    
    'Ordinary Shares Number': 'Số lượng cổ phiếu lưu hành',
    'Share Issued': 'Số lượng cổ phiếu phát hành',
    'Ordinary Shares': 'Cổ phiếu phổ thông (Số lượng)',
    'Diluted Average Shares': 'Cổ phiếu bình quân suy giảm',
    'Basic Average Shares': 'Cổ phiếu bình quân cơ bản',

    # Lưu chuyển tiền tệ
    'Operating Cash Flow': 'Lưu chuyển tiền thuần từ hoạt động kinh doanh',
    'Investing Cash Flow': 'Lưu chuyển tiền thuần từ hoạt động đầu tư',
    'Financing Cash Flow': 'Lưu chuyển tiền thuần từ hoạt động tài chính',
    'Free Cash Flow': 'Dòng tiền tự do (FCF)',
    'Capital Expenditure': 'Chi phí đầu tư tài sản cố định (CapEx)',
    'Repayment Of Debt': 'Trả nợ gốc vay',
    'Issuance Of Debt': 'Phát hành thêm nợ vay',
    'Cash Dividends Paid': 'Cổ tức đã trả bằng tiền',

    # Thị trường & Cổ tức
    'Close Price': 'Giá đóng cửa',
    'Volume': 'Khối lượng giao dịch',
    'Dividend Payout': 'Cổ tức tiền mặt'
}

def translate_metric(metric_name):
    return TRANSLATION_MAP.get(metric_name, None)

def main():
    print(f"🚀 [FINEX Engine] Bắt đầu cào 2 sàn (HOSE, HNX) cho {len(FINEX_UNIVERSE)} mã...")
    
    all_data = []
    current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    current_calendar_year = datetime.now().year
    
    for symbol, san_gd, nhom_nganh in FINEX_UNIVERSE:
        try:
            ticker = yf.Ticker(f"{symbol}.VN")
            
            # 1. Dữ liệu thị trường
            hist = ticker.history(period="1d")
            if hist is not None and not hist.empty:
                latest = hist.iloc[-1]
                all_data.append({
                    'ma_chung_khoan': symbol,
                    'san_giao_dich': san_gd,
                    'nhom_nganh_finex': nhom_nganh,
                    'statement_type': TRANSLATION_MAP['Market_Data'],
                    'nam': str(current_calendar_year),
                    'period_date': datetime.now().strftime('%Y-%m-%d'),
                    'metric': TRANSLATION_MAP['Close Price'],
                    'value': float(latest['Close']),
                    'scrape_time': current_time
                })
                all_data.append({
                    'ma_chung_khoan': symbol,
                    'san_giao_dich': san_gd,
                    'nhom_nganh_finex': nhom_nganh,
                    'statement_type': TRANSLATION_MAP['Market_Data'],
                    'nam': str(current_calendar_year),
                    'period_date': datetime.now().strftime('%Y-%m-%d'),
                    'metric': TRANSLATION_MAP['Volume'],
                    'value': float(latest['Volume']),
                    'scrape_time': current_time
                })

            # 2. Cổ tức
            try:
                dividends = ticker.dividends
                if dividends is not None and not dividends.empty:
                    for date_idx, div_val in dividends.items():
                        if pd.notna(div_val) and div_val > 0:
                            date_str = str(date_idx).split('T')[0].split(' ')[0]
                            year_val = date_str.split('-')[0]
                            all_data.append({
                                'ma_chung_khoan': symbol,
                                'san_giao_dich': san_gd,
                                'nhom_nganh_finex': nhom_nganh,
                                'statement_type': TRANSLATION_MAP['Dividend_Data'],
                                'nam': year_val,
                                'period_date': date_str,
                                'metric': TRANSLATION_MAP['Dividend Payout'],
                                'value': float(div_val),
                                'scrape_time': current_time
                            })
            except Exception:
                pass

            # 3. 3 Báo cáo tài chính
            statements = {
                'Income_Statement': getattr(ticker, 'financials', None),
                'Balance_Sheet': getattr(ticker, 'balance_sheet', None),
                'Cash_Flow': getattr(ticker, 'cashflow', None)
            }
            
            for stmt_key, df_stmt in statements.items():
                if df_stmt is not None and not df_stmt.empty:
                    vn_stmt_name = TRANSLATION_MAP.get(stmt_key, stmt_key)
                    
                    for date_col in df_stmt.columns:
                        date_str = str(date_col).split('T')[0]
                        year_val = date_str.split('-')[0]
                        
                        for idx, val in df_stmt[date_col].items():
                            if pd.notna(val) and val != 0:
                                clean_metric = translate_metric(str(idx))
                                if clean_metric is not None:
                                    all_data.append({
                                        'ma_chung_khoan': symbol,
                                        'san_giao_dich': san_gd,
                                        'nhom_nganh_finex': nhom_nganh,
                                        'statement_type': vn_stmt_name,
                                        'nam': year_val,
                                        'period_date': date_str,
                                        'metric': clean_metric,
                                        'value': float(val),
                                        'scrape_time': current_time
                                    })
                                    
            time.sleep(0.1)
        except Exception as e:
            print(f"⚠️ Bỏ qua lỗi nhỏ ở mã {symbol}: {e}")
            continue
            
    if all_data:
        df_final = pd.DataFrame(all_data)
        
        df_final = df_final[[
            'ma_chung_khoan', 'san_giao_dich', 'nhom_nganh_finex', 
            'statement_type', 'nam', 'period_date', 'metric', 'value', 'scrape_time'
        ]]
        
        df_final = df_final.sort_values(by=['ma_chung_khoan', 'nam', 'statement_type'], ascending=[True, False, True])
        
        # 1. CSV
        csv_path = 'vietnam_financial_statements.csv'
        df_final.to_csv(csv_path, index=False)
        print(f"✅ Đã xuất thành công file CSV: {len(df_final)} bản ghi.")
        
        # 2. SQLite
        db_path = 'vietnam_stock_database.db'
        conn = sqlite3.connect(db_path)
        df_final.to_sql('financial_statements', conn, if_exists='replace', index=False)
        conn.close()
        print(f"✅ Đã lưu đồng thời vào SQLite Database '{db_path}' thành công!")
        
    else:
        print("⚠️ Không thu thập được dữ liệu.")

if __name__ == "__main__":
    main()
