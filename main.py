import os
import pandas as pd
from datetime import datetime
import yfinance as yf
import time
import sqlite3

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

FINEX_UNIVERSE = [(s, 'HOSE', classify_sector(s)) for s in HOSE_LIST] + [(s, 'HNX', classify_sector(s)) for s in HNX_LIST]

TRANSLATION_MAP = {
    'Income_Statement': 'Báo cáo kết quả kinh doanh',
    'Balance_Sheet': 'Bảng cân đối kế toán',
    'Cash_Flow': 'Báo cáo lưu chuyển tiền tệ',
    'Market_Data': 'Dữ liệu thị trường',
    'Dividend_Data': 'Lịch sử cổ tức',
    'Total Revenue': 'Tổng doanh thu',
    'Gross Profit': 'Lợi nhuận gộp',
    'Net Income': 'Lợi nhuận sau thuế (Lợi nhuận ròng)',
    'Total Assets': 'Tổng tài sản',
    'Stockholders Equity': 'Vốn chủ sở hữu',
    'Operating Cash Flow': 'Lưu chuyển tiền thuần từ hoạt động kinh doanh',
    'Close Price': 'Giá đóng cửa',
    'Volume': 'Khối lượng giao dịch',
    'Ordinary Shares Number': 'Số lượng cổ phiếu lưu hành'
}

def main():
    print(f"🚀 [FINEX Engine] Chạy cào dữ liệu an toàn cho {len(FINEX_UNIVERSE)} mã...")
    all_data = []
    current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    current_year = str(datetime.now().year)

    for symbol, san_gd, nhom_nganh in FINEX_UNIVERSE:
        try:
            ticker = yf.Ticker(f"{symbol}.VN")
            
            # Lấy giá thị trường cơ bản
            hist = ticker.history(period="1d")
            if hist is not None and not hist.empty:
                latest = hist.iloc[-1]
                all_data.append({
                    'ma_chung_khoan': symbol, 'san_giao_dich': san_gd, 'nhom_nganh_finex': nhom_nganh,
                    'statement_type': TRANSLATION_MAP['Market_Data'], 'nam': current_year,
                    'period_date': datetime.now().strftime('%Y-%m-%d'), 'metric': TRANSLATION_MAP['Close Price'],
                    'value': float(latest['Close']), 'scrape_time': current_time
                })

            # Lấy Báo cáo tài chính
            for key, name in [('financials', 'Income_Statement'), ('balance_sheet', 'Balance_Sheet'), ('cashflow', 'Cash_Flow')]:
                df_stmt = getattr(ticker, key, None)
                if df_stmt is not None and not df_stmt.empty:
                    for col in df_stmt.columns:
                        date_str = str(col).split('T')[0]
                        year_val = date_str.split('-')[0]
                        for idx, val in df_stmt[col].items():
                            if pd.notna(val) and val != 0 and str(idx) in TRANSLATION_MAP:
                                all_data.append({
                                    'ma_chung_khoan': symbol, 'san_giao_dich': san_gd, 'nhom_nganh_finex': nhom_nganh,
                                    'statement_type': TRANSLATION_MAP[key], 'nam': year_val,
                                    'period_date': date_str, 'metric': TRANSLATION_MAP[str(idx)],
                                    'value': float(val), 'scrape_time': current_time
                                })
            time.sleep(0.1)
        except Exception:
            continue # Bỏ qua mã lỗi, tiếp tục chạy mã khác không làm sập pipeline

    # Lưu file bắt buộc dù dữ liệu ít hay nhiều
    if all_data:
        df_final = pd.DataFrame(all_data)
    else:
        df_final = pd.DataFrame(columns=['ma_chung_khoan', 'san_giao_dich', 'nhom_nganh_finex', 'statement_type', 'nam', 'period_date', 'metric', 'value', 'scrape_time'])

    df_final.to_csv('vietnam_financial_statements.csv', index=False)
    conn = sqlite3.connect('vietnam_stock_database.db')
    df_final.to_sql('financial_statements', conn, if_exists='replace', index=False)
    conn.close()
    print("✅ Hoàn tất xuất file CSV và SQLite thành công!")

if __name__ == "__main__":
    main()
