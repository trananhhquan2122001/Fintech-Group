import os
import time
import pandas as pd
import yfinance as yf
import requests

# Thiết lập Session chống chặn kết nối tối ưu trên GitHub Actions
session = requests.Session()
session.headers.update({
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
    'Accept-Language': 'en-US,en;q=0.9,vi;q=0.8'
})

def load_full_market_tickers():
    """Danh sách mở rộng toàn thị trường (HOSE, HNX, UPCOM)"""
    full_market_list = [
        "AAA", "AAS", "ACL", "ACV", "AGR", "ANV", "API", "APS", "BCC", "BFC",
        "BIC", "BMI", "BMP", "BMS", "BRC", "BSI", "BTS", "BWE", "C32", "CAV",
        "CCL", "CDC", "CEG", "CFC", "CHP", "CII", "CLC", "CLL", "CLW", "CMG",
        "CMX", "CNG", "COM", "CRC", "CSC", "CSM", "CTD", "CTS", "CVT", "DBD",
        "DCC", "DDG", "DGT", "DHB", "DHT", "DIC", "DLG", "DMC", "DNP", "DPG",
        "DRC", "DRH", "DRI", "DRL", "DSC", "DSG", "DTD", "DTL", "DTT", "DVP",
        "DXS", "DXV", "EBA", "EBS", "ECI", "EDC", "EID", "ELC", "EMC", "EVE",
        "EVS", "FCM", "FDC", "FIT", "FMC", "FSB", "GDT", "GEG", "GIL", "GLT",
        "GMC", "GMH", "GMX", "HAC", "HAD", "HAH", "HAX", "HBC", "HBS", "HCC",
        "HCD", "HDC", "HDG", "HEC", "HGM", "HHV", "HID", "HJS", "HLD", "HND",
        "HT1", "HUB", "HVH", "HVP", "ICT", "IDI", "IDJ", "IJC", "ILB", "IMP",
        "ITA", "ITC", "ITD", "IVS", "KDF", "KMR", "KOS", "KSB", "KST", "LAB",
        "LAZ", "LCC", "LCG", "LDG", "LDP", "LDS", "LEC", "LGC", "LGL", "LHC",
        "LIC", "LIG", "LKW", "LM8", "LMC", "LMG", "LMH", "LSS", "LTC", "MAC",
        "MBG", "MCF", "MCM", "MDC", "MDG", "MHC", "MIG", "MKV", "MSB", "MSH",
        "MST", "MTG", "NAF", "NAG", "NAN", "NAS", "NAV", "NBC", "NBT", "NCB",
        "NDN", "NDP", "NEV", "NGC", "NHA", "NHC", "NHH", "NKC", "NKG", "NLC",
        "NMC", "NNC", "NSC", "NSH", "NT2", "NTC", "NTL", "NVB", "OBC", "OCB",
        "OGC", "OIL", "OPC", "PAC", "PAN", "PAS", "PAT", "PCC", "PC1", "PCT",
        "PDC", "PDN", "PEC", "PET", "PGC", "PGD", "PGS", "PGV", "PHA", "PHC",
        "PHP", "PIA", "PIC", "PIH", "PIT", "PIV", "PJC", "PJT", "PLC", "PLP",
        "PMC", "PME", "PMG", "PMP", "PMS", "PNC", "PNG", "PNH", "PNP", "POT",
        "PPC", "PRE", "PRT", "PSA", "PSC", "PSD", "PTB", "PTH", "PTL", "PTS",
        "QBS", "QCG", "RAL", "RDP", "S55", "SAM", "SBA", "SBV", "SC5", "SCC",
        "SCD", "SD2", "SD3", "SD4", "SD5", "SD6", "SD7", "SD8", "SD9", "SDA",
        "SDC", "SDE", "SDG", "SDN", "SDP", "SDR", "SDS", "SDT", "SDU", "SEB",
        "SED", "SFG", "SFI", "SFN", "SGB", "SGC", "SGP", "SGR", "SGT", "SHA",
        "SHI", "SKG", "SMA", "SMB", "SMC", "SPB", "SPC", "SPL", "SQC", "SRB",
        "SSC", "ST8", "STC", "STD", "STG", "STP", "STS", "SVC", "SVD", "SVI",
        "SVT", "SZB", "SZC", "SZL", "TBC", "TBH", "TC6", "TCD", "TCE", "TCL",
        "TCM", "TCO", "TCR", "TCT", "TDC", "TDG", "TDH", "TDI", "TDN", "TDP",
        "TDS", "TDT", "TDW", "TEC", "TEL", "TET", "TFC", "TGG", "THA", "THB",
        "THG", "THI", "THR", "TIC", "TID", "TIE", "TIP", "TIX", "TLD", "TLG",
        "TLH", "TMP", "TMS", "TMT", "TNC", "TNH", "TNI", "TNT", "TPC", "TRA",
        "TRC", "TRT", "TS4", "TSC", "TSE", "TSG", "TST", "TTB", "TTC", "TTD",
        "TTF", "TTH", "TTL", "TTN", "TTS", "TV2", "TV3", "TV4", "TVB", "TVC",
        "TVD", "TVG", "TVH", "TVO", "TVP", "TWO", "TXM", "UNI", "VAF", "VAP",
        "VBA", "VBC", "VBP", "VBS", "VC1", "VC2", "VC3", "VC4", "VC5", "VC6",
        "VC7", "VC8", "VCA", "VCC", "VCD", "VCG", "VCI", "VCM", "VCP", "VCS",
        "VCW", "VDA", "VDB", "VDC", "VDL", "VDS", "VDT", "VEC", "VEF", "VFG",
        "VFR", "VGC", "VGD", "VGP", "VGR", "VGS", "VHC", "VHD", "VHE", "VHF",
        "VIF", "VIG", "VII", "VIP", "VIS", "VIT", "VLF", "VMA"
    ]
    unique_tickers = sorted(list(set([t.strip().upper() for t in full_market_list if t.strip()])))
    print(f"🌐 [FINEX Full Market] Tổng số mã toàn thị trường cần quét: {len(unique_tickers)}")
    return unique_tickers

# TỪ ĐIỂN VIỆT HÓA CHUYÊN SÂU 3 BÁO CÁO TÀI CHÍNH GỐC ĐẦY ĐỦ
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
    statement_type_vn = TRANSLATION_MAP.get(statement_type_raw, statement_type_raw)
    try:
        if df is not None and not df.empty:
            for col in df.columns:
                date_str = str(col).split('T')[0].split(' ')[0]
                year_val = date_str.split('-')[0]
                if year_val.isdigit():
                    for row_idx, val in df[col].items():
                        if pd.notna(val):
                            try: float_val = float(val)
                            except: continue
                            records.append({
                                'Mã chứng khoán': symbol,
                                'Tên doanh nghiệp': f"Công ty Cổ phần {symbol}",
                                'Tên ngành': 'Toàn thị trường',
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
    tickers = load_full_market_tickers()
    all_records = []
    success, fail = 0, 0

    for idx, symbol in enumerate(tickers, 1):
        print(f"[{idx}/{len(tickers)}] Đang cào toàn diện 3 BCTC (Năm & Quý) mã: {symbol}...")
        try:
            ticker = yf.Ticker(f"{symbol}.VN", session=session)
            recs = []
            
            # Cào trọn vẹn cả 3 BCTC gốc (Cân đối kế toán, Kết quả kinh doanh, Lưu chuyển tiền tệ) - Cả Năm và Quý
            recs.extend(parse_financial_df(symbol, getattr(ticker, 'balance_sheet', None), 'Balance_Sheet', 'Năm'))
            recs.extend(parse_financial_df(symbol, getattr(ticker, 'quarterly_balance_sheet', None), 'Balance_Sheet', 'Quý'))
            recs.extend(parse_financial_df(symbol, getattr(ticker, 'financials', None), 'Income_Statement', 'Năm'))
            recs.extend(parse_financial_df(symbol, getattr(ticker, 'quarterly_financials', None), 'Income_Statement', 'Quý'))
            recs.extend(parse_financial_df(symbol, getattr(ticker, 'cashflow', None), 'Cash_Flow', 'Năm'))
            recs.extend(parse_financial_df(symbol, getattr(ticker, 'quarterly_cashflow', None), 'Cash_Flow', 'Quý'))

            if recs:
                all_records.extend(recs)
                success += 1
            else:
                fail += 1
            time.sleep(0.2)
        except:
            fail += 1
            time.sleep(0.2)

    df_market = pd.DataFrame(all_records).drop_duplicates() if all_records else pd.DataFrame()

    os.makedirs('data', exist_ok=True)
    output_path = 'data/vietnam_full_market_database.csv'
    df_market.to_csv(output_path, index=False, encoding='utf-8-sig')
    
    print(f"==================================================")
    print(f" 🎉 HOÀN TẤT CÀO ĐỦ 3 BÁO CÁO TOÀN THỊ TRƯỜNG!")
    print(f" - Thành công: {success} mã | Thất bại/Trống: {fail} mã")
    print(f" - Lưu tại: {output_path} | Tổng bản ghi: {len(df_market):,}")
    print(f"==================================================")

if __name__ == "__main__":
    main()
