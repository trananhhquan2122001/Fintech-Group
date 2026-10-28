import os
import time
from datetime import datetime
import pandas as pd
import yfinance as yf
import requests

# Thiết lập Session giả lập trình duyệt chống chặn kết nối trên GitHub Actions
session = requests.Session()
session.headers.update({
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'
})

def load_500_tickers():
    """
    Đọc danh sách 500 mã cổ phiếu chuẩn hóa cho FINEX VN Terminal.
    """
    tickers_list = [
        "AAA", "AAS", "ABB", "ABI", "ABW", "ACB", "ACL", "ACV", "ADS", "AGR",
        "AIG", "AMV", "ANV", "API", "APS", "BAB", "BAF", "BCC", "BCM", "BED",
        "BFC", "BGE", "BHN", "BIC", "BID", "BLI", "BMI", "BMP", "BMS", "BPP",
        "BRC", "BSG", "BSI", "BSR", "BTS", "BWE", "CAD", "CAF", "CAP", "CAV",
        "CCI", "CCL", "CCM", "CDC", "CEG", "CEO", "CFC", "CHG", "CHP", "CII",
        "CKA", "CLC", "CLL", "CLW", "CMG", "CMX", "CNG", "COM", "CRC", "CSC",
        "CSG", "CSM", "CTD", "CTG", "CTR", "CTS", "CVT", "DAD", "DAE", "DAT",
        "DBD", "DBT", "DCC", "DCM", "DDG", "DGC", "DGT", "DHB", "DHG", "DHT",
        "DIC", "DIG", "DLG", "DMC", "DND", "DNE", "DNP", "DNR", "DNS", "DPM",
        "DPV", "DRC", "DRH", "DRI", "DRL", "DSC", "DSG", "DST", "DTD", "DTK",
        "DTL", "DTT", "DVH", "DVM", "DVP", "DXG", "DXS", "DXV", "DZM", "EBA",
        "EBS", "ECI", "EDC", "EIB", "EID", "ELC", "EME", "EMC", "EPD", "EVE",
        "EVS", "FCM", "FCS", "FDC", "FIT", "FMC", "FPT", "FRT", "FSB", "FTS",
        "GAD", "GAS", "GCC", "GCD", "GDT", "GED", "GEG", "GEE", "GEX", "GIL",
        "GJS", "GLT", "GMC", "GMD", "GMH", "GMX", "GND", "GON", "GPT", "GRM",
        "GSW", "GTD", "GTH", "GTM", "GVR", "HAC", "HAD", "HAH", "HAJ", "HAN",
        "HAP", "HAR", "HAT", "HAX", "HBC", "HBD", "HBS", "HCC", "HCD", "HCI",
        "HCM", "HDB", "HDC", "HDG", "HDO", "HDS", "HEC", "HEX", "HFC", "HGG",
        "HGI", "HGL", "HGM", "HGN", "HGR", "HGS", "HHG", "HHN", "HHV", "HID",
        "HJS", "HLB", "HLD", "HNA", "HND", "HPA", "HPG", "HQS", "HTP", "HT1",
        "HUB", "HVH", "HVN", "HVP", "HVS", "HZL", "ICT", "IDC", "IDI", "IDJ",
        "IDS", "IJC", "ILB", "IMP", "INC", "INM", "ITA", "ITC", "ITD", "ITQ",
        "IVS", "KBC", "KDC", "KDH", "KDF", "KHS", "KID", "KLC", "KLB", "KMR",
        "KMT", "KOS", "KSB", "KSF", "KSS", "KST", "KTB", "KTT", "KVG", "LAB",
        "LAS", "LAZ", "LBE", "LCC", "LCD", "LCG", "LCM", "LCS", "LDG", "LDP",
        "LDS", "LEC", "LEO", "LGC", "LGL", "LHC", "LHN", "LIC", "LIG", "LKW",
        "LLA", "LLM", "LM8", "LMC", "LMG", "LMH", "LNC", "LPB", "LQN", "LSS",
        "LTC", "MAC", "MAI", "MBB", "MBG", "MBS", "MCF", "MCH", "MCL", "MCM",
        "MCO", "MCP", "MCS", "MDC", "MDG", "MEC", "MED", "MEF", "MEL", "MES",
        "MET", "MFC", "MFM", "MGN", "MHC", "MHL", "MIB", "MIC", "MIE", "MIG",
        "MKV", "MLC", "MMC", "MMO", "MNC", "MND", "MNE", "MNF", "MNG", "MNS",
        "MNV", "MOF", "MPC", "MPL", "MQH", "MRC", "MRF", "MSB", "MSC", "MSH",
        "MSN", "MSP", "MSR", "MSS", "MST", "MTA", "MTB", "MTC", "MTG", "MTH",
        "MTL", "MTP", "MTR", "MTS", "MVB", "MVC", "MVN", "MWG", "MXC", "MYA",
        "NAB", "NAC", "NAD", "NAF", "NAG", "NAH", "NAN", "NAP", "NAS", "NAV",
        "NAW", "NBC", "NBP", "NBT", "NCA", NCB", "NCL", "NCS", "ND2", "NDN",
        "NDP", "NEV", "NGC", "NGL", "NGO", "NGS", "NHA", "NHC", "NHH", "NHT",
        "NIC", "NKC", "NKG", "NKT", "NLC", "NLG", "NLM", "NLS", "NLT", "NMC",
        "NMD", "NMH", "NMM", "NMS", "NMT", "NNC", "NNG", "NNM", "NNT", "NOF",
        "NOS", "NOT", "NPD", "NPS", "NRC", "NSC", "NSH", "NSL", "NST", "NSV",
        "NT2", "NTA", "NTB", "NTC", "NTD", "NTE", "NTF", "NTI", "NTL", "NTP",
        "NTR", "NTS", "NTV", "NVB", "NVC", "NVD", "NVL", "NVP", "NVR", "NVT",
        "NYH", "OAD", "OBC", "OCB", "OGC", "OID", "OIL", "ONE", "ONT", "OPC",
        "ORS", "PAC", "PAI", "PAN", "PAS", "PAT", "PCC", "PCD", "PCF", "PCG",
        "PCH", "PC1", "PCT", "PCW", "PDC", "PDN", "PDR", "PEC", "PED", "PEG",
        "PEL", "PEM", "PEN", "PEP", "PET", "PFC", "PFD", "PFL", "PFS", "PGC",
        "PGD", "PGE", "PGF", "PGG", "PGH", "PGI", "PGN", "PGP", "PGR", "PGS",
        "PGT", "PGV", "PHA", "PHC", "PHN", "PHP", "PHR", "PIA", "PIC", "PIH",
        "PIS", "PIT", "PIV", "PJC", "PJS", "PJT", "PLC", "PLI", "PLP", "PLS",
        "PLX", "PMC", "PMD", "PME", "PMG", "PMP", "PMS", "PMT", "PMW", "PNC",
        "PNG", "PNH", "PNJ", "PNP", "PNS", "POT", "POW", "PPC", "PPI", "PPM",
        "PPP", "PPS", "PPT", "PPY", "PRA", "PRB", "PRE", "PRK", "PRN", "PRO",
        "PRT", "PSA", "PSB", "PSC", "PSD", "PSE", "PSG", "PSI", "PSK", "PSO"
    ]
    unique_tickers = sorted(list(set([t.strip().upper() for t in tickers_list if t.strip()])))
    print(f"🎯 [FINEX Engine] Tổng số lượng mã độc nhất cần cào: {len(unique_tickers)}")
    return unique_tickers

def get_sector(symbol):
    """Phân định chính xác tên ngành phục vụ nhận diện trên trang web/terminal"""
    tech_list = ["FPT", "CMG", "VTP", "ICT", "ELC", "CTR", "VGI", "VNZ", "ELC"]
    bank_list = ["VCB", "BID", "TCB", "MBB", "ACB", "CTG", "VPB", "STB", "SHB", "HDB", "LPB", "MSB", "OCB", "NAB", "SSB", "EIB", "TPB"]
    securities_list = ["SSI", "VCI", "HCM", "VND", "SHS", "MBS", "FTS", "BSI", "CTS", "VIX", "VDS", "ORS", "AGR", "VFS", "DSE", "BVS", "EVF"]
    realestate_list = ["VIC", "VHM", "VRE", "BCM", "KBC", "IDC", "SIP", "SZC", "KDH", "NLG", "DXG", "PDR", "DIG", "CEO", "HDC", "NVL", "TCH"]
    retail_list = ["MWG", "FRT", "DGW", "PNJ", "PET", "VTP"]
    oil_gas_list = ["GAS", "PLX", "PVD", "PVS", "PVT", "PVB", "BSR", "OIL", "POW"]
    steel_materials = ["HPG", "HSG", "NKG", "GDA", "BMP", "NTP", "AAA", "DGC", "CSV"]

    if symbol in tech_list:
        return "Công nghệ thông tin"
    elif symbol in bank_list:
        return "Ngân hàng"
    elif symbol in securities_list:
        return "Chứng khoán"
    elif symbol in realestate_list:
        return "Bất động sản"
    elif symbol in retail_list:
        return "Bán lẻ & Dịch vụ tiêu dùng"
    elif symbol in oil_gas_list:
        return "Dầu khí & Năng lượng"
    elif symbol in steel_materials:
        return "Vật liệu xây dựng & Hóa chất"
    else:
        return "Công nghiệp, Sản xuất & Hàng tiêu dùng"

# --- TỪ ĐIỂN VIỆT HÓA TOÀN DIỆN & VÉT CẠN 100% ---
TRANSLATION_MAP = {
    'Balance_Sheet': 'Bảng cân đối kế toán',
    'Income_Statement': 'Báo cáo kết quả kinh doanh',
    'Cash_Flow': 'Báo cáo lưu chuyển tiền tệ',

    # Cân đối kế toán & Khối lượng cổ phiếu
    'Ordinary Shares Number': 'Số lượng cổ phiếu phổ thông',
    'Share Issued': 'Cổ phiếu đã phát hành',
    'Total Debt': 'Tổng nợ vay',
    'Tangible Book Value': 'Giá trị sổ sách hữu hình',
    'Invested Capital': 'Vốn đầu tư',
    'Net Tangible Assets': 'Tài sản thuần hữu hình',
    'Common Stock Equity': 'Vốn chủ sở hữu phổ thông',
    'Total Capitalization': 'Tổng nguồn vốn',
    'Stockholders Equity': 'Vốn chủ sở hữu',
    'Retained Earnings': 'Lợi nhuận sau thuế chưa phân phối',
    'Additional Paid In Capital': 'Thặng dư vốn cổ phần',
    'Capital Stock': 'Vốn cổ phần',
    'Common Stock': 'Vốn góp chủ sở hữu (Cổ phiếu phổ thông)',
    'Total Liabilities Net Minority Interest': 'Tổng nợ phải trả',
    'Total Assets': 'Tổng tài sản',
    'Current Assets': 'Tài sản ngắn hạn',
    'Cash And Cash Equivalents': 'Tiền và các khoản tương đương tiền',
    'Net Loan': 'Cho vay khách hàng thuần',
    'Receivables': 'Các khoản phải thu',
    'Inventory': 'Hàng tồn kho',
    'Total Non Current Assets': 'Tổng tài sản dài hạn',
    'Net PPE': 'Tài sản cố định thuần',
    'Current Liabilities': 'Nợ ngắn hạn',
    'Current Debt': 'Vay và nợ thuê tài chính ngắn hạn',
    'Long Term Debt': 'Vay và nợ thuê tài chính dài hạn',
    'Net Debt': 'Nợ vay ròng',
    'Working Capital': 'Vốn lưu động ròng',

    # Kết quả kinh doanh
    'Normalized EBITDA': 'Lợi nhuận trước lãi vay, thuế, khấu hao chuẩn hóa (Normalized EBITDA)',
    'Net Interest Income': 'Thu nhập lãi thuần',
    'Interest Expense': 'Chi phí lãi vay',
    'Diluted EPS': 'Lãi suy giảm trên cổ phiếu (Diluted EPS)',
    'Basic EPS': 'Lãi cơ bản trên cổ phiếu (Basic EPS)',
    'Net Income Common Stockholders': 'Lợi nhuận ròng phân bổ cho cổ đông phổ thông',
    'Net Income': 'Lợi nhuận sau thuế (Lợi nhuận ròng)',
    'Total Revenue': 'Tổng doanh thu',
    'Operating Revenue': 'Doanh thu thuần',
    'Cost Of Revenue': 'Giá vốn hàng bán',
    'Gross Profit': 'Lợi nhuận gộp',
    'Operating Income': 'Lợi nhuận thuần từ hoạt động kinh doanh',
    'EBIT': 'Lợi nhuận trước lãi vay và thuế (EBIT)',
    'EBITDA': 'Lợi nhuận trước lãi vay, thuế và khấu hao (EBITDA)',
    'Pretax Income': 'Lợi nhuận kế toán trước thuế',

    # Lưu chuyển tiền tệ
    'Free Cash Flow': 'Dòng tiền tự do (FCF)',
    'Capital Expenditure': 'Chi phí đầu tư tài sản cố định (CapEx)',
    'End Cash Position': 'Tiền và tương đương tiền cuối kỳ',
    'Financing Cash Flow': 'Lưu chuyển tiền thuần từ hoạt động tài chính',
    'Cash Dividends Paid': 'Cổ tức đã chi trả',
    'Investing Cash Flow': 'Lưu chuyển tiền thuần từ hoạt động đầu tư',
    'Operating Cash Flow': 'Lưu chuyển tiền thuần từ hoạt động kinh doanh'
}

def translate_metric(metric_original):
    cleaned_key = str(metric_original).strip()
    if cleaned_key in TRANSLATION_MAP:
        return TRANSLATION_MAP[cleaned_key]
    for eng_k, vie_v in TRANSLATION_MAP.items():
        if cleaned_key.lower() == eng_k.lower():
            return vie_v
            
    lower_key = cleaned_key.lower()
    if 'shares' in lower_key or 'share' in lower_key: return 'Số lượng cổ phiếu / Khối lượng niêm yết'
    if 'ebitda' in lower_key: return 'Lợi nhuận trước lãi vay, thuế và khấu hao (EBITDA)'
    if 'revenue' in lower_key or 'sales' in lower_key: return 'Doanh thu'
    if 'income' in lower_key or 'profit' in lower_key: return 'Lợi nhuận'
    if 'asset' in lower_key: return 'Tài sản'
    if 'liability' in lower_key or 'debt' in lower_key: return 'Nợ phải trả / Nợ vay'
    if 'equity' in lower_key: return 'Vốn chủ sở hữu'
    if 'cash' in lower_key: return 'Tiền và lưu chuyển tiền tệ'
    if 'expense' in lower_key or 'cost' in lower_key: return 'Chi phí'
    return f"Chỉ tiêu tài chính ({cleaned_key})"

def safe_float_convert(val):
    try:
        if pd.isna(val): return 0.0
        return float(val)
    except:
        return 0.0

def parse_financial_df(symbol, df, statement_type_raw, ky_bao_cao):
    records = []
    sector_name = get_sector(symbol)
    statement_type_vn = TRANSLATION_MAP.get(statement_type_raw, statement_type_raw)
    try:
        if df is not None and not df.empty:
            for col in df.columns:
                date_str = str(col).split('T')[0].split(' ')[0]
                year_val = date_str.split('-')[0]
                
                # Lọc đúng dải thời gian từ 2020 đến 2026
                if year_val.isdigit() and 2020 <= int(year_val) <= 2026:
                    for row_idx, val in df[col].items():
                        if pd.notna(val):
                            metric_original = str(row_idx).strip()
                            records.append({
                                'Mã chứng khoán': symbol,
                                'Tên ngành': sector_name,
                                'Loại báo cáo': statement_type_vn,
                                'Loại kỳ': ky_bao_cao,
                                'Năm': year_val,
                                'Ngày kỳ': date_str,
                                'Chỉ tiêu tiếng Việt': translate_metric(metric_original),
                                'Giá trị': safe_float_convert(val)
                            })
    except Exception:
        pass
    return records

def main():
    target_stocks = load_500_tickers()
    print(f"🚀 [FINEX Pipeline 2020-2026] Bắt đầu cào dữ liệu cho {len(target_stocks)} mã kèm định danh Ngành và Khối lượng cổ phiếu...")
    
    all_master_records = []
    success_count = 0
    fail_count = 0
    
    for idx, symbol in enumerate(target_stocks, 1):
        try:
            ticker = yf.Ticker(f"{symbol}.VN", session=session)
            
            all_master_records.extend(parse_financial_df(symbol, getattr(ticker, 'balance_sheet', None), 'Balance_Sheet', 'Năm'))
            all_master_records.extend(parse_financial_df(symbol, getattr(ticker, 'quarterly_balance_sheet', None), 'Balance_Sheet', 'Quý'))
            all_master_records.extend(parse_financial_df(symbol, getattr(ticker, 'financials', None), 'Income_Statement', 'Năm'))
            all_master_records.extend(parse_financial_df(symbol, getattr(ticker, 'quarterly_financials', None), 'Income_Statement', 'Quý'))
            all_master_records.extend(parse_financial_df(symbol, getattr(ticker, 'cashflow', None), 'Cash_Flow', 'Năm'))
            all_master_records.extend(parse_financial_df(symbol, getattr(ticker, 'quarterly_cashflow', None), 'Cash_Flow', 'Quý'))
            
            success_count += 1
            time.sleep(0.12)
        except Exception:
            fail_count += 1
            continue

    df_master = pd.DataFrame(all_master_records).drop_duplicates() if all_master_records else pd.DataFrame()

    print("\n💾 Đang kết xuất ra cơ sở dữ liệu Excel & CSV chuẩn hóa...")
    os.makedirs('data', exist_ok=True)
    
    excel_path = 'vietnam_stock_database.xlsx'
    with pd.ExcelWriter(excel_path, engine='openpyxl') as writer:
        df_master.to_excel(writer, sheet_name='Tong_Hop_Tai_Chinh', index=False)
    
    csv_path = 'data/vietnam_stock_database_tong_hop.csv'
    df_master.to_csv(csv_path, index=False, encoding='utf-8-sig')
    
    print(f"\n==================================================")
    print(f" 🎉 HOÀN TẤT: CÀO 500 MÃ KÈM TÊN NGÀNH & SỐ LƯỢNG CỔ PHIẾU")
    print(f" - Thành công: {success_count} mã | Bỏ qua/Lỗi: {fail_count} mã")
    print(f" - Tổng số bản ghi chuẩn hóa: {len(df_master):,}")
    print(f"==================================================")

if __name__ == "__main__":
    main()
