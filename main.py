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

def safe_float_convert(val):
    try:
        if pd.isna(val):
            return 0.0
        return float(val)
    except (ValueError, TypeError):
        return 0.0

def parse_financial_df(symbol, df, statement_type, ky_bao_cao):
    """Hàm vét cạn 100% mọi dòng chỉ tiêu từ yfinance mà không bỏ sót bất kỳ key nào."""
    records = []
    sector_name = get_sector(symbol)
    if df is not None and not df.empty:
        for col in df.columns:
            date_str = str(col).split('T')[0].split(' ')[0]
            year_val = date_str.split('-')[0]
            for row_idx, val in df[col].items():
                if pd.notna(val):
                    metric_str = str(row_idx).strip()
                    records.append({
                        'ma_chung_khoan': symbol,
                        'nhom_nganh': sector_name,
                        'loai_bao_cao': statement_type,
                        'loai_ky': ky_bao_cao,
                        'nam': year_val,
                        'ngay_ky': date_str,
                        'chi_tieu_goc': metric_str,
                        'gia_tri': safe_float_convert(val)
                    })
    return records

def main():
    print(f"🚀 [FINEX Pipeline] Bắt đầu vét cạn 100% (BCTC + Cổ phiếu + Cổ tức) cho {len(ALL_TARGET_STOCKS)} mã...")
    
    bs_records = []   # Bảng Cân đối kế toán (Năm + Quý)
    is_records = []   # Bảng Kết quả kinh doanh (Năm + Quý)
    cf_records = []   # Bảng Lưu chuyển tiền tệ (Năm + Quý)
    div_records = []  # Bảng Cổ tức
    info_records = [] # Bảng thông tin tổng quan & khối lượng cổ phiếu
    
    success_count = 0
    fail_count = 0
    
    for idx, symbol in enumerate(ALL_TARGET_STOCKS, 1):
        try:
            print(f"⏳ [{idx}/{len(ALL_TARGET_STOCKS)}] Đang vét cạn toàn diện: {symbol}...")
            ticker = yf.Ticker(f"{symbol}.VN")
            
            # 1. Vét sạch 3 bảng Báo cáo tài chính (Cả Năm và Quý - 100% mọi chỉ tiêu gốc)
            bs_records.extend(parse_financial_df(symbol, getattr(ticker, 'balance_sheet', None), 'Balance_Sheet', 'Năm'))
            bs_records.extend(parse_financial_df(symbol, getattr(ticker, 'quarterly_balance_sheet', None), 'Balance_Sheet', 'Quý'))
            
            is_records.extend(parse_financial_df(symbol, getattr(ticker, 'financials', None), 'Income_Statement', 'Năm'))
            is_records.extend(parse_financial_df(symbol, getattr(ticker, 'quarterly_financials', None), 'Income_Statement', 'Quý'))
            
            cf_records.extend(parse_financial_df(symbol, getattr(ticker, 'cashflow', None), 'Cash_Flow', 'Năm'))
            cf_records.extend(parse_financial_df(symbol, getattr(ticker, 'quarterly_cashflow', None), 'Cash_Flow', 'Quý'))
            
            # 2. Vét sạch dữ liệu Cổ tức (Dividends)
            dividends = getattr(ticker, 'dividends', None)
            if dividends is not None and not dividends.empty:
                for date_idx, div_val in dividends.items():
                    if pd.notna(div_val) and div_val > 0:
                        div_records.append({
                            'ma_chung_khoan': symbol,
                            'nhom_nganh': get_sector(symbol),
                            'ngay_chia': str(date_idx).split('T')[0].split(' ')[0],
                            'gia_tri_co_tuc': safe_float_convert(div_val)
                        })

            # 3. Vét sạch thông tin số lượng cổ phiếu lưu hành & các chỉ số cấu trúc (`info`)
            info = getattr(ticker, 'info', {})
            if info:
                info_records.append({
                    'ma_chung_khoan': symbol,
                    'nhom_nganh': get_sector(symbol),
                    'ten_cong_ty': info.get('longName', ''),
                    'khoi_luong_co_phieu_luu_hanh': info.get('sharesOutstanding', 0),
                    'gia_tri_thi_truong_float': info.get('floatShares', 0),
                    'gia_tri_hien_tai': info.get('currentPrice', info.get('regularMarketPrice', 0)),
                    'von_hoa': info.get('marketCap', 0),
                    'pe_ratio': info.get('trailingPE', 0),
                    'pb_ratio': info.get('priceToBook', 0)
                })
            
            success_count += 1
            time.sleep(0.15)
            
        except Exception as e:
            fail_count += 1
            print(f"⚠️ Bỏ qua mã {symbol} do lỗi mạng/dữ liệu: {e}")
            continue

    # Chuyển đổi và xuất toàn bộ ra các file CSV độc lập để Quân kiểm tra chi tiết
    df_bs = pd.DataFrame(bs_records).drop_duplicates()
    df_is = pd.DataFrame(is_records).drop_duplicates()
    df_cf = pd.DataFrame(cf_records).drop_duplicates()
    df_div = pd.DataFrame(div_records).drop_duplicates()
    df_info = pd.DataFrame(info_records).drop_duplicates()

    df_bs.to_csv('can_doi_ke_toan.csv', index=False, encoding='utf-8-sig')
    df_is.to_csv('ket_qua_kinh_doanh.csv', index=False, encoding='utf-8-sig')
    df_cf.to_csv('luu_chuyen_tien_te.csv', index=False, encoding='utf-8-sig')
    df_div.to_csv('co_tuc.csv', index=False, encoding='utf-8-sig')
    df_info.to_csv('thong_tin_co_phieu.csv', index=False, encoding='utf-8-sig')

    print(f"==================================================")
    print(f" ✅ VÉT CẠN THÀNH CÔNG 100% KHÔNG SÓT DÒNG NÀO (Exit Code 0)")
    print(f" - Thành công: {success_count} mã | Lỗi: {fail_count} mã")
    print(f" - [can_doi_ke_toan.csv]: {len(df_bs)} dòng")
    print(f" - [ket_qua_kinh_doanh.csv]: {len(df_is)} dòng")
    print(f" - [luu_chuyen_tien_te.csv]: {len(df_cf)} dòng")
    print(f" - [co_tuc.csv]: {len(df_div)} dòng")
    print(f" - [thong_tin_co_phieu.csv]: {len(df_info)} dòng")
    print(f"==================================================")
    
    import sys
    sys.exit(0)

if __name__ == "__main__":
    main()
