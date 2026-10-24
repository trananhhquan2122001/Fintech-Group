import os
import pandas as pd
from datetime import datetime
import yfinance as yf
import time
import sqlite3

# --- DANH MỤC TRỌNG TÂM VN100 (Đầu ngành, thanh khoản cao, dữ liệu chuẩn) ---
VN100_LIST = [
    # Ngân hàng & Tài chính
    "ACB", "BID", "CTG", "EIB", "HDB", "LPB", "MBB", "MSB", "NAB", "OCB", 
    "SHB", "SSB", "STB", "TCB", "TPB", "VCB", "VIB", "VPB", "SSI", "VCI", 
    "HCM", "VND", "VIX", "FTS", "BSI", "CTS", "MBS", "EVF", "BVH", "DSE",
    
    # Bất động sản & Xây dựng
    "VIC", "VHM", "VRE", "BCM", "NVL", "KBC", "KDH", "NLG", "PDR", "DIG", 
    "DXG", "TCH", "VPI", "SJS", "KOS", "HDG", "HHV", "VCG", "CII", "CTR",
    
    # Sản xuất, Tiêu dùng, Bán lẻ & Năng lượng / Công nghệ
    "FPT", "HPG", "MSN", "VNM", "MWG", "GAS", "GVR", "SAB", "PLX", "POW", 
    "PNJ", "DGC", "FRT", "DPM", "DCM", "BSR", "GMD", "GEX", "REE", "CMG", 
    "VTP", "DGW", "VHC", "ANV", "BAF", "BMP", "DBC", "HSG", "NKG", "PC1", 
    "PHR", "SZC", "VSC", "MCH", "ACV", "QNS"
]

# Phân loại nhóm ngành FINEX
TECH_SECTOR = {"FPT", "CMG", "CTR", "DGW", "VTP"}
FINANCE_SECTOR = {
    "ACB", "BID", "CTG", "EIB", "HDB", "LPB", "MBB", "MSB", "NAB", "OCB", 
    "SHB", "SSB", "STB", "TCB", "TPB", "VCB", "VIB", "VPB", "SSI", "VCI", 
    "HCM", "VND", "VIX", "FTS", "BSI", "CTS", "MBS", "EVF", "BVH", "DSE"
}

def classify_sector(symbol):
    if symbol in TECH_SECTOR:
        return 'Công nghệ'
    elif symbol in FINANCE_SECTOR:
        return 'Tài chính'
    else:
        return 'Sản xuất và công nghiệp'

FINEX_UNIVERSE = [(s, classify_sector(s)) for s in VN100_LIST]

# Từ điển Việt hóa cốt lõi
TRANSLATION_MAP = {
    'Income_Statement': 'Báo cáo kết quả kinh doanh',
    'Balance_Sheet': 'Bảng cân đối kế toán',
    'Cash_Flow': 'Báo cáo lưu chuyển tiền tệ',
    'Market_Data': 'Dữ liệu thị trường',
    'Dividend_Data': 'Lịch sử cổ tức',
    
    # Chỉ tiêu trọng yếu
    'Total Revenue': 'Tổng doanh thu',
    'Gross Profit': 'Lợi nhuận gộp',
    'Operating Income': 'Lợi nhuận thuần từ hoạt động kinh doanh',
    'Net Income': 'Lợi nhuận sau thuế (Lợi nhuận ròng)',
    'EBIT': 'Lợi nhuận trước lãi vay và thuế (EBIT)',
    'EBITDA': 'Lợi nhuận trước thuế, lãi vay và khấu hao (EBITDA)',
    'Pretax Income': 'Lợi nhuận trước thuế',
    'Total Assets': 'Tổng tài sản',
    'Current Assets': 'Tài sản ngắn hạn',
    'Total Liabilities Net Minority Interest': 'Tổng nợ phải trả',
    'Stockholders Equity': 'Vốn chủ sở hữu',
    'Total Debt': 'Tổng nợ vay',
    'Operating Cash Flow': 'Lưu chuyển tiền thuần từ hoạt động kinh doanh',
    'Investing Cash Flow': 'Lưu chuyển tiền thuần từ hoạt động đầu tư',
    'Financing Cash Flow': 'Lưu chuyển tiền thuần từ hoạt động tài chính',
    'Free Cash Flow': 'Dòng tiền tự do (FCF)',
    'Ordinary Shares Number': 'Số lượng cổ phiếu lưu hành',
    'Close Price': 'Giá đóng cửa',
    'Volume': 'Khối lượng giao dịch',
    'Dividend Payout': 'Cổ tức tiền mặt'
}

def main():
    print(f"🚀 [FINEX Engine] Bắt đầu cào dữ liệu rổ VN100 tối ưu cho {len(FINEX_UNIVERSE)} mã...")
    
    all_data = []
    current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    current_calendar_year = str(datetime.now().year)
    
    for symbol, nhom_nganh in FINEX_UNIVERSE:
        try:
            ticker = yf.Ticker(f"{symbol}.VN")
            
            # 1. Dữ liệu thị trường
            hist = ticker.history(period="1d")
            if hist is not None and not hist.empty:
                latest = hist.iloc[-1]
                all_data.append({
                    'ma_chung_khoan': symbol, 'nhom_nganh_finex': nhom_nganh,
                    'statement_type': TRANSLATION_MAP['Market_Data'], 'nam': current_calendar_year,
                    'period_date': datetime.now().strftime('%Y-%m-%d'), 'metric': TRANSLATION_MAP['Close Price'],
                    'value': float(latest['Close']), 'scrape_time': current_time
                })
                all_data.append({
                    'ma_chung_khoan': symbol, 'nhom_nganh_finex': nhom_nganh,
                    'statement_type': TRANSLATION_MAP['Market_Data'], 'nam': current_calendar_year,
                    'period_date': datetime.now().strftime('%Y-%m-%d'), 'metric': TRANSLATION_MAP['Volume'],
                    'value': float(latest['Volume']), 'scrape_time': current_time
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
                                'ma_chung_khoan': symbol, 'nhom_nganh_finex': nhom_nganh,
                                'statement_type': TRANSLATION_MAP['Dividend_Data'], 'nam': year_val,
                                'period_date': date_str, 'metric': TRANSLATION_MAP['Dividend Payout'],
                                'value': float(div_val), 'scrape_time': current_time
                            })
            except Exception:
                pass

            # 3. 3 Báo cáo tài chính cốt lõi
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
                            if pd.notna(val) and val != 0 and str(idx) in TRANSLATION_MAP:
                                all_data.append({
                                    'ma_chung_khoan': symbol, 'nhom_nganh_finex': nhom_nganh,
                                    'statement_type': vn_stmt_name, 'nam': year_val,
                                    'period_date': date_str, 'metric': TRANSLATION_MAP[str(idx)],
                                    'value': float(val), 'scrape_time': current_time
                                })
            time.sleep(0.1)
        except Exception as e:
            print(f"⚠️ Bỏ qua lỗi nhỏ ở mã {symbol}: {e}")
            continue
            
    if all_data:
        df_final = pd.DataFrame(all_data)
        df_final = df_final[[
            'ma_chung_khoan', 'nhom_nganh_finex', 'statement_type', 
            'nam', 'period_date', 'metric', 'value', 'scrape_time'
        ]]
        df_final = df_final.sort_values(by=['ma_chung_khoan', 'nam', 'statement_type'], ascending=[True, False, True])
        
        # Xuất CSV
        df_final.to_csv('vietnam_financial_statements.csv', index=False)
        print(f"✅ Đã xuất CSV thành công: {len(df_final)} bản ghi.")
        
        # Lưu SQLite
        conn = sqlite3.connect('vietnam_stock_database.db')
        df_final.to_sql('financial_statements', conn, if_exists='replace', index=False)
        conn.close()
        print("✅ Đã lưu SQLite Database thành công!")
    else:
        print("⚠️ Không thu thập được dữ liệu.")

if __name__ == "__main__":
    main()
