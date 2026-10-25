import os
import time
from datetime import datetime
import pandas as pd
import yfinance as yf

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

# Phân loại cụ thể thành 3 nhóm ngành yêu cầu
def get_sector(symbol):
    if symbol in ["FPT", "CMG", "VTP", "ICT", "ELC"]:
        return "Công nghệ"
    elif symbol in [
        "VCB", "BID", "TCB", "MBB", "ACB", "CTG", "VPB", "STB", "SSI", "VCI", 
        "HCM", "VND", "SHB", "HDB", "LPB", "MSB", "OCB", "NAB", "SSB", "EIB", 
        "BSI", "CTS", "FTS", "MBS", "BVS", "EVF", "DSE"
    ]:
        return "Tài chính & Ngân hàng"
    else:
        return "Sản xuất, Bất động sản và Công nghiệp"

# Từ điển Việt hóa toàn diện chỉ tiêu tài chính
TRANSLATION_MAP = {
    'Total Assets': 'Tổng tài sản',
    'Current Assets': 'Tài sản ngắn hạn',
    'Cash And Cash Equivalents': 'Tiền và các khoản tương đương tiền',
    'Receivables': 'Các khoản phải thu',
    'Inventory': 'Hàng tồn kho',
    'Total Non Current Assets': 'Tổng tài sản dài hạn',
    'Net PPE': 'Tài sản cố định thuần',
    'Total Liabilities Net Minority Interest': 'Tổng nợ phải trả',
    'Current Liabilities': 'Nợ ngắn hạn',
    'Accounts Payable': 'Phải trả người bán ngắn hạn',
    'Current Debt': 'Vay và nợ thuê tài chính ngắn hạn',
    'Total Non Current Liabilities Net Minority Interest': 'Nợ dài hạn',
    'Stockholders Equity': 'Vốn chủ sở hữu',
    'Retained Earnings': 'Lợi nhuận sau thuế chưa phân phối',
    'Total Capitalization': 'Tổng nguồn vốn',
    'Total Revenue': 'Tổng doanh thu',
    'Cost Of Revenue': 'Giá vốn hàng bán',
    'Gross Profit': 'Lợi nhuận gộp',
    'Operating Income': 'Lợi nhuận thuần từ hoạt động kinh doanh',
    'Net Income': 'Lợi nhuận sau thuế (Lợi nhuận ròng)',
    'EBIT': 'Lợi nhuận trước lãi vay và thuế (EBIT)',
    'Interest Expense': 'Chi phí lãi vay',
    'Pretax Income': 'Lợi nhuận kế toán trước thuế',
    'Tax Provision': 'Chi phí thuế TNDN',
    'Basic EPS': 'Lãi cơ bản trên cổ phiếu (Basic EPS)',
    'Operating Cash Flow': 'Lưu chuyển tiền thuần từ hoạt động kinh doanh',
    'Investing Cash Flow': 'Lưu chuyển tiền thuần từ hoạt động đầu tư',
    'Financing Cash Flow': 'Lưu chuyển tiền thuần từ hoạt động tài chính',
    'End Cash Position': 'Tiền và tương đương tiền cuối kỳ',
    'Beginning Cash Position': 'Tiền và tương đương tiền đầu kỳ',
    'Capital Expenditure': 'Chi phí đầu tư tài sản cố định (CapEx)',
    'Free Cash Flow': 'Dòng tiền tự do (FCF)'
}

def safe_float_convert(val):
    try:
        if pd.isna(val):
            return 0.0
        return float(val)
    except (ValueError, TypeError):
        return 0.0

def process_statement_df(symbol, df_annual, df_quarterly):
    records = []
    sector_name = get_sector(symbol)
    
    def parse_df(df, ky_bao_cao):
        if df is not None and not df.empty:
            for col in df.columns:
                date_str = str(col).split('T')[0].split(' ')[0]
                year_val = date_str.split('-')[0]
                for row_idx, val in df[col].items():
                    if pd.notna(val):
                        metric_str = str(row_idx).strip()
                        vn_metric = TRANSLATION_MAP.get(metric_str, metric_str)
                        records.append({
                            'ma_chung_khoan': symbol,
                            'nhom_nganh': sector_name,
                            'loai_ky': ky_bao_cao,
                            'nam': year_val,
                            'ngay_ky': date_str,
                            'chi_tieu_goc': metric_str,
                            'chi_tieu_tieng_viet': vn_metric,
                            'gia_tri': safe_float_convert(val)
                        })

    parse_df(df_annual, 'Năm')
    parse_df(df_quarterly, 'Quý')
    return records

def main():
    print(f"🚀 [FINEX Pipeline] Bắt đầu cào vét triệt để xuất 3 file CSV cho {len(ALL_TARGET_STOCKS)} mã...")
    
    bs_records = []
    is_records = []
    cf_records = []
    
    success_count = 0
    fail_count = 0
    
    for idx, symbol in enumerate(ALL_TARGET_STOCKS, 1):
        try:
            print(f"⏳ [{idx}/{len(ALL_TARGET_STOCKS)}] Đang xử lý [{get_sector(symbol)}] - {symbol}...")
            ticker = yf.Ticker(f"{symbol}.VN")
            
            bs_annual = getattr(ticker, 'balance_sheet', None)
            bs_quarterly = getattr(ticker, 'quarterly_balance_sheet', None)
            is_annual = getattr(ticker, 'financials', None)
            is_quarterly = getattr(ticker, 'quarterly_financials', None)
            cf_annual = getattr(ticker, 'cashflow', None)
            cf_quarterly = getattr(ticker, 'quarterly_cashflow', None)
            
            bs_records.extend(process_statement_df(symbol, bs_annual, bs_quarterly))
            is_records.extend(process_statement_df(symbol, is_annual, is_quarterly))
            cf_records.extend(process_statement_df(symbol, cf_annual, cf_quarterly))
            
            success_count += 1
            time.sleep(0.15)
            
        except Exception as e:
            fail_count += 1
            print(f"⚠️ Bỏ qua mã {symbol} do lỗi mạng: {e}")
            continue

    # Chuyển đổi sang DataFrame
    df_bs = pd.DataFrame(bs_records).drop_duplicates() if bs_records else pd.DataFrame()
    df_is = pd.DataFrame(is_records).drop_duplicates() if is_records else pd.DataFrame()
    df_cf = pd.DataFrame(cf_records).drop_duplicates() if cf_records else pd.DataFrame()

    # --- CHỈ XUẤT RA 3 FILE CSV RIÊNG BIỆT ---
    csv_bs = 'can_doi_ke_toan.csv'
    csv_is = 'ket_qua_kinh_doanh.csv'
    csv_cf = 'luu_chuyen_tien_te.csv'

    df_bs.to_csv(csv_bs, index=False, encoding='utf-8-sig')
    df_is.to_csv(csv_is, index=False, encoding='utf-8-sig')
    df_cf.to_csv(csv_cf, index=False, encoding='utf-8-sig')

    print(f"📁 Đã xuất thành công 3 file CSV tại:")
    print(f" - {os.path.abspath(csv_bs)} ({len(df_bs)} dòng)")
    print(f" - {os.path.abspath(csv_is)} ({len(df_is)} dòng)")
    print(f" - {os.path.abspath(csv_cf)} ({len(df_cf)} dòng)")

    print(f"==================================================")
    print(f" ✅ HOÀN TẤT XUẤT 3 FILE CSV (Exit Code 0)")
    print(f" - Thành công: {success_count} mã | Lỗi: {fail_count} mã")
    print(f"==================================================")
    
    import sys
    sys.exit(0)

if __name__ == "__main__":
    main()
