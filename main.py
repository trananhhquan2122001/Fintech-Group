import os
import time
from datetime import datetime
import pandas as pd
import yfinance as yf
import requests

# Thiết lập Session giả lập trình duyệt chống chặn kết nối tối ưu trên GitHub Actions
session = requests.Session()
session.headers.update({
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
    'Accept-Language': 'en-US,en;q=0.9,vi;q=0.8'
})

def load_500_tickers():
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
        "NAW", "NBC", "NBP", "NBT", "NCA", "NCB", "NCL", "NCS", "ND2", "NDN",
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
    print(f"🎯 [FINEX Enterprise Engine] Tổng số mã duy nhất chuẩn hóa cần xử lý: {len(unique_tickers)}")
    return unique_tickers

def get_sector(symbol):
    tech_list = ["FPT", "CMG", "VTP", "ICT", "ELC", "CTR", "VGI", "VNZ"]
    bank_list = ["VCB", "BID", "TCB", "MBB", "ACB", "CTG", "VPB", "STB", "SHB", "HDB", "LPB", "MSB", "OCB", "NAB", "SSB", "EIB", "TPB"]
    securities_list = ["SSI", "VCI", "HCM", "VND", "SHS", "MBS", "FTS", "BSI", "CTS", "VIX", "VDS", "ORS", "AGR", "VFS", "DSE", "BVS", "EVF"]
    realestate_list = ["VIC", "VHM", "VRE", "BCM", "KBC", "IDC", "SIP", "SZC", "KDH", "NLG", "DXG", "PDR", "DIG", "CEO", "HDC", "NVL", "TCH"]
    retail_list = ["MWG", "FRT", "DGW", "PNJ", "PET", "VTP"]
    oil_gas_list = ["GAS", "PLX", "PVD", "PVS", "PVT", "PVB", "BSR", "OIL", "POW"]
    steel_materials = ["HPG", "HSG", "NKG", "GDA", "BMP", "NTP", "AAA", "DGC", "CSV"]

    if symbol in tech_list: return "Công nghệ thông tin"
    elif symbol in bank_list: return "Ngân hàng"
    elif symbol in securities_list: return "Chứng khoán"
    elif symbol in realestate_list: return "Bất động sản"
    elif symbol in retail_list: return "Bán lẻ & Dịch vụ tiêu dùng"
    elif symbol in oil_gas_list: return "Dầu khí & Năng lượng"
    elif symbol in steel_materials: return "Vật liệu xây dựng & Hóa chất"
    else: return "Công nghiệp, Sản xuất & Hàng tiêu dùng"

# TỪ ĐIỂN VIỆT HÓA CHUYÊN SÂU 3 BÁO CÁO TÀI CHÍNH
TRANSLATION_MAP = {
    'Balance_Sheet': 'Bảng cân đối kế toán',
    'Income_Statement': 'Báo cáo kết quả kinh doanh',
    'Cash_Flow': 'Báo cáo lưu chuyển tiền tệ',

    # Cân đối kế toán
    'Ordinary Shares Number': 'Số lượng cổ phiếu phổ thông',
    'Share Issued': 'Cổ phiếu đã phát hành',
    'Total Assets': 'Tổng tài sản',
    'Current Assets': 'Tài sản ngắn hạn',
    'Cash And Cash Equivalents': 'Tiền và các khoản tương đương tiền',
    'Cash Equivalents': 'Các khoản tương đương tiền',
    'Net Loan': 'Cho vay khách hàng thuần',
    'Receivables': 'Các khoản phải thu',
    'Accounts Receivable': 'Phải thu ngắn hạn khách hàng',
    'Inventory': 'Hàng tồn kho',
    'Total Non Current Assets': 'Tổng tài sản dài hạn',
    'Net PPE': 'Tài sản cố định thuần',
    'Gross PPE': 'Nguyên giá tài sản cố định',
    'Accumulated Depreciation': 'Hao mòn lũy kế TSCĐ',
    'Goodwill And Other Intangible Assets': 'Lợi thế thương mại và tài sản vô hình',
    'Investments And Advances': 'Đầu tư tài chính dài hạn',
    'Investment Properties': 'Bất động sản đầu tư',
    'Current Liabilities': 'Nợ ngắn hạn',
    'Current Debt': 'Vay và nợ thuê tài chính ngắn hạn',
    'Payables': 'Các khoản phải trả',
    'Accounts Payable': 'Phải trả người bán ngắn hạn',
    'Total Liabilities Net Minority Interest': 'Tổng nợ phải trả',
    'Total Non Current Liabilities Net Minority Interest': 'Nợ dài hạn',
    'Long Term Debt': 'Vay và nợ thuê tài chính dài hạn',
    'Total Debt': 'Tổng nợ vay',
    'Net Debt': 'Nợ vay ròng',
    'Stockholders Equity': 'Vốn chủ sở hữu',
    'Capital Stock': 'Vốn góp chủ sở hữu',
    'Retained Earnings': 'Lợi nhuận sau thuế chưa phân phối',
    'Additional Paid In Capital': 'Thặng dư vốn cổ phần',
    'Working Capital': 'Vốn lưu động ròng',

    # Kết quả kinh doanh
    'Total Revenue': 'Tổng doanh thu',
    'Operating Revenue': 'Doanh thu thuần',
    'Cost Of Revenue': 'Giá vốn hàng bán',
    'Gross Profit': 'Lợi nhuận gộp',
    'Operating Expense': 'Chi phí hoạt động',
    'Selling General And Administration': 'Chi phí bán hàng và quản lý doanh nghiệp',
    'Research And Development': 'Chi phí nghiên cứu và phát triển',
    'Operating Income': 'Lợi nhuận thuần từ hoạt động kinh doanh',
    'Net Interest Income': 'Thu nhập lãi thuần',
    'Interest Expense': 'Chi phí lãi vay',
    'Interest Income': 'Thu nhập lãi',
    'EBIT': 'Lợi nhuận trước lãi vay và thuế (EBIT)',
    'EBITDA': 'Lợi nhuận trước lãi vay, thuế và khấu hao (EBITDA)',
    'Normalized EBITDA': 'Lợi nhuận trước lãi vay, thuế, khấu hao chuẩn hóa',
    'Pretax Income': 'Lợi nhuận kế toán trước thuế',
    'Tax Provision': 'Chi phí thuế TNDN',
    'Net Income': 'Lợi nhuận sau thuế (Lợi nhuận ròng)',
    'Net Income Common Stockholders': 'Lợi nhuận ròng phân bổ cổ đông phổ thông',
    'Basic EPS': 'Lãi cơ bản trên cổ phiếu (Basic EPS)',
    'Diluted EPS': 'Lãi suy giảm trên cổ phiếu (Diluted EPS)',

    # Lưu chuyển tiền tệ
    'Operating Cash Flow': 'Lưu chuyển tiền thuần từ hoạt động kinh doanh',
    'Investing Cash Flow': 'Lưu chuyển tiền thuần từ hoạt động đầu tư',
    'Financing Cash Flow': 'Lưu chuyển tiền thuần từ hoạt động tài chính',
    'Capital Expenditure': 'Chi phí đầu tư tài sản cố định (CapEx)',
    'Free Cash Flow': 'Dòng tiền tự do (FCF)',
    'Issuance Of Debt': 'Phát hành nợ vay',
    'Repayment Of Debt': 'Trả nợ gốc vay',
    'Cash Dividends Paid': 'Cổ tức đã chi trả',
    'Beginning Cash Position': 'Tiền và tương đương tiền đầu kỳ',
    'End Cash Position': 'Tiền và tương đương tiền cuối kỳ'
}

def translate_metric(metric_original):
    cleaned_key = str(metric_original).strip()
    if cleaned_key in TRANSLATION_MAP: return TRANSLATION_MAP[cleaned_key]
    for eng_k, vie_v in TRANSLATION_MAP.items():
        if cleaned_key.lower() == eng_k.lower(): return vie_v
    
    lower_key = cleaned_key.lower()
    if 'shares' in lower_key: return 'Số lượng cổ phiếu / Khối lượng niêm yết'
    if 'revenue' in lower_key or 'sales' in lower_key: return 'Doanh thu'
    if 'income' in lower_key or 'profit' in lower_key: return 'Lợi nhuận'
    if 'asset' in lower_key: return 'Tài sản'
    if 'debt' in lower_key: return 'Nợ vay'
    if 'cash' in lower_key: return 'Tiền và lưu chuyển tiền tệ'
    if 'expense' in lower_key or 'cost' in lower_key: return 'Chi phí'
    return f"Chỉ tiêu tài chính ({cleaned_key})"

def parse_financial_df(symbol, df, statement_type_raw, ky_bao_cao):
    records = []
    sector_name = get_sector(symbol)
    statement_type_vn = TRANSLATION_MAP.get(statement_type_raw, statement_type_raw)
    try:
        if df is not None and not df.empty:
            for col in df.columns:
                date_str = str(col).split('T')[0].split(' ')[0]
                year_val = date_str.split('-')[0]
                if year_val.isdigit() and 2020 <= int(year_val) <= 2026:
                    for row_idx, val in df[col].items():
                        if pd.notna(val):
                            try: float_val = float(val)
                            except: continue
                            records.append({
                                'Mã chứng khoán': symbol,
                                'Tên ngành': sector_name,
                                'Loại báo cáo': statement_type_vn,
                                'Loại kỳ': ky_bao_cao,
                                'Năm': year_val,
                                'Ngày kỳ': date_str,
                                'Chỉ tiêu tiếng Việt': translate_metric(str(row_idx).strip()),
                                'Giá trị': float_val
                            })
    except Exception:
        pass
    return records

def main():
    target_stocks = load_500_tickers()
    all_master_records = []
    success_count, fail_count = 0, 0
    
    # Chia batch 50 mã, có cơ chế checkpoint an toàn
    batch_size = 50
    for i in range(0, len(target_stocks), batch_size):
        batch = target_stocks[i:i+batch_size]
        print(f"🔄 [FINEX Pipeline] Đang cào batch từ {i+1} đến {min(i+batch_size, len(target_stocks))}/{len(target_stocks)}...")
        
        for symbol in batch:
            try:
                ticker = yf.Ticker(f"{symbol}.VN", session=session)
                
                # Cào toàn diện đủ 3 BCTC (Cả Năm và Quý)
                all_master_records.extend(parse_financial_df(symbol, getattr(ticker, 'balance_sheet', None), 'Balance_Sheet', 'Năm'))
                all_master_records.extend(parse_financial_df(symbol, getattr(ticker, 'quarterly_balance_sheet', None), 'Balance_Sheet', 'Quý'))
                all_master_records.extend(parse_financial_df(symbol, getattr(ticker, 'financials', None), 'Income_Statement', 'Năm'))
                all_master_records.extend(parse_financial_df(symbol, getattr(ticker, 'quarterly_financials', None), 'Income_Statement', 'Quý'))
                all_master_records.extend(parse_financial_df(symbol, getattr(ticker, 'cashflow', None), 'Cash_Flow', 'Năm'))
                all_master_records.extend(parse_financial_df(symbol, getattr(ticker, 'quarterly_cashflow', None), 'Cash_Flow', 'Quý'))
                
                success_count += 1
                time.sleep(0.06)
            except Exception:
                fail_count += 1
                continue

    df_master = pd.DataFrame(all_master_records).drop_duplicates() if all_master_records else pd.DataFrame()

    print("\n💾 Đang kết xuất đồng thời tệp Excel & CSV nguyên bản cho FINEX Terminal...")
    os.makedirs('data', exist_ok=True)
    
    # Xuất file Excel chuẩn cấu trúc
    df_master.to_excel('vietnam_stock_database.xlsx', index=False, engine='openpyxl')
    
    # Xuất file CSV tổng hợp
    df_master.to_csv('data/vietnam_stock_database_tong_hop.csv', index=False, encoding='utf-8-sig')
    
    print(f"==================================================")
    print(f" 🎉 HOÀN TẤT TOÀN BỘ QUY TRÌNH QUY MÔ 500 MÃ!")
    print(f" - Doanh nghiệp thành công: {success_count} | Lỗi/Bỏ qua: {fail_count}")
    print(f" - Tổng dung lượng bản ghi chuẩn hóa: {len(df_master):,}")
    print(f"==================================================")

if __name__ == "__main__":
    main()
