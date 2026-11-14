import os
import time
from datetime import datetime
import pandas as pd
import requests
import re
from concurrent.futures import ThreadPoolExecutor, as_completed

# ==========================================
# 1. TÍCH HỢP API KEY VÀ CÀI ĐẶT THƯ VIỆN
# ==========================================
os.environ["VNSTOCK_API_KEY"] = "vnstock_533590cc17b6737ceb7c9f147471f31f"

try:
    import vnfinancialdata as vnf
except ImportError:
    print("⚙️ Đang cài đặt thư viện vnfinancialdata...")
    os.system("pip install vnfinancialdata --quiet")
    import vnfinancialdata as vnf

try:
    import yfinance as yf
except ImportError:
    os.system("pip install yfinance --quiet")
    import yfinance as yf

try:
    from vnstock import Fundamental, Market
except ImportError:
    os.system("pip install -U --extra-index-url https://vnstocks.com/api/packages vnstock --quiet")
    from vnstock import Fundamental, Market

session = requests.Session()
session.headers.update({
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'
})

# ==========================================
# 🆕 0. TÍCH HỢP HUGGING FACE DATASET (MỚI)
# ==========================================
def load_daily_data_hf():
    """Tải dữ liệu hàng ngày trực tiếp từ Hugging Face Dataset."""
    DATA_URL = "https://huggingface.co/datasets/trananhquan2001/finex-vn-dataset/raw/main/dulieu_hang_ngay.csv"
    try:
        df = pd.read_csv(DATA_URL)
        print(f"✅ Đã tải thành công {len(df)} dòng dữ liệu hàng ngày từ Hugging Face!")
        return df
    except Exception as e:
        print(f"⚠️ Lỗi khi tải dữ liệu từ Hugging Face: {e}")
        return pd.DataFrame()

# ==========================================
# 2. DANH SÁCH 242 MÃ VÀ THÔNG TIN DOANH NGHIỆP (GIỮ NGUYÊN)
# ==========================================
def load_176_master_tickers():
    raw_tickers = raw_tickers = [
        'ACB', 'ANV', 'BAF', 'BCM', 'BID', 'BMP', 'BSI', 'BSR', 'BVH', 'BVS', 'BWE', 'CAP',
        'CEO', 'CII', 'CMG', 'CTD', 'CTG', 'CTR', 'CTS', 'DBC', 'DCM', 'DGW', 'DIG', 'DP3',
        'DPM', 'DSE', 'DTD', 'DXG', 'DXP', 'EIB', 'EVF', 'FPT', 'FRT', 'FTS', 'GAS', 'GEE',
        'GEX', 'GMD', 'GVR', 'HAG', 'HCM', 'HDB', 'HDG', 'HHV', 'HPG', 'HSG', 'HT1', 'HUT',
        'IDC', 'KBC', 'KDC', 'KDH', 'L14', 'L18', 'LAS', 'LHC', 'LPB', 'MBB', 'MBS', 'MCH',
        'MSB', 'MSN', 'MWG', 'NAB', 'NBC', 'NDN', 'NKG', 'NLG', 'NT2', 'NTP', 'NVL', 'OCB',
        'PAN', 'PC1', 'PDR', 'PHR', 'PLC', 'PLX', 'PNJ', 'POW', 'PSD', 'PVB', 'PVC', 'PVD',
        'PVS', 'PVT', 'PVI', 'REE', 'SAB', 'SBT', 'SHB', 'SHS', 'SIP', 'SJS', 'SLS', 'SSB',
        'SSI', 'STB', 'TAL', 'TCB', 'TCH', 'TCX', 'TDM', 'TIG', 'TNG', 'TPB', 'TVD', 'VCB',
        'VC3', 'VCG', 'VCI', 'VCK', 'VCS', 'VFS', 'VGC', 'VGP', 'VHC', 'VHM', 'VIB', 'VIC',
        'VIX', 'VJC', 'VND', 'VNM', 'VPB', 'VPI', 'VPL', 'VPX', 'VRE', 'VSC', 'VTP', 'L40',
        'HVT', 'GLT', 'VGS', 'HGM', 'KSV', 'THD', 'KSF', 'SCG', 'CLM', 'TMB', 'SAF', 'NET',
        'DHT', 'DGC', 'SZC', 'HVN', 'BAB', 'AGR', 'TLH', 'BMI', 'PET', 'LSS', 'HDC', 'IJC',
        'TDC', 'CTI', 'SJD', 'TMP', 'SBA', 'VSH', 'TTA', 'TV2', 'VCP', 'BFC', 'DDV', 'SGP',
        'DPR', 'DHC', 'TCM', 'HPP', 'PAT', 'DTP', 'SCL', 'HMS',
    ]
    ticker_map = {t.strip().upper(): "VIETNAM_MARKET" for t in raw_tickers if t.strip()}
    if len(ticker_map) != 176:
        raise ValueError(f"Danh sách mã không hợp lệ: kỳ vọng 176, thực tế {len(ticker_map)}")
    print(f"\n📌 Danh sách mục tiêu FINEX: {len(ticker_map)} mã (đã loại 66 mã UPCoM theo bộ lọc hiện tại).")
    return ticker_map

def get_company_profile(symbol):
    tech_list = ["FPT", "CMG", "VTP", "ICT", "ELC", "CTR", "VGI", "VNZ", "FOX", "FOC", "VTK", "MFS", "VEC"]
    bank_list = ["VCB", "BID", "TCB", "MBB", "ACB", "CTG", "VPB", "STB", "SHB", "HDB", "LPB", "MSB", "OCB", "NAB", "SSB", "EIB", "TPB", "ABB", "BAB"]
    securities_list = ["SSI", "VCI", "HCM", "VND", "SHS", "MBS", "FTS", "BSI", "CTS", "VIX", "VDS", "ORS", "AGR", "VFS", "DSE", "BVS", "EVF", "IPA", "EVS", "HBS", "PSI", "WSS", "F88"]
    realestate_list = ["VIC", "VHM", "VRE", "BCM", "KBC", "IDC", "SIP", "SZC", "KDH", "NLG", "DXG", "PDR", "DIG", "CEO", "HDC", "NVL", "TCH", "VC3", "VPI", "SJS", "L14", "L18", "NDN", "THD", "KSF", "IJC", "TDC", "CTI", "VEF", "TED", "CC1", "PCC", "LIC", "CLI", "HEC"]
    retail_list = ["MWG", "FRT", "DGW", "PNJ", "PET", "DMX"]
    oil_gas_list = ["GAS", "PLX", "PVD", "PVS", "PVT", "PVB", "BSR", "OIL", "POW", "DTK", "PGV", "NT2", "PGI", "PLC", "PSD", "PVC", "SJD", "TMP", "SBA", "VSH", "TTA", "TV2", "VCP", "ODE", "AVC"]
    steel_materials = ["HPG", "HSG", "NKG", "GDA", "BMP", "NTP", "AAA", "DGC", "CSV", "LAS", "PHR", "DPM", "DCM", "BFC", "HPA", "VGS", "HT1", "LHC", "HGM", "KSV", "TLH", "DDV", "BFC", "DPR", "DHC", "VLB", "HPP", "VXB", "PAT", "SIV", "ACE", "HAM", "SBM", "SCL", "NAS", "HMS", "QPH"]
    agriculture_list = ["HAG", "ANV", "BAF", "DBC", "CAP", "IDP", "KDC", "MCH", "MSN", "QNS", "SAB", "SBT", "SLS", "VHC", "CKA", "SEA", "APF", "LSG", "VSF", "AGP", "DTP", "WSB", "BWS", "QHW", "HLB"]

    if symbol in tech_list: sector = "Công nghệ thông tin"
    elif symbol in bank_list: sector = "Ngân hàng"
    elif symbol in securities_list: sector = "Chứng khoán"
    elif symbol in realestate_list: sector = "Bất động sản & Xây dựng"
    elif symbol in retail_list: sector = "Bán lẻ & Dịch vụ tiêu dùng"
    elif symbol in oil_gas_list: sector = "Dầu khí, Điện & Năng lượng"
    elif symbol in steel_materials: sector = "Vật liệu xây dựng, Thép & Hóa chất"
    elif symbol in agriculture_list: sector = "Nông - Lâm - Thủy sản & Thực phẩm"
    else: sector = "Công nghiệp, Sản xuất & Hàng tiêu dùng"

    company_names = {
        "CKA": "Công ty CP XNK Thủy sản Cà Mau", "VLB": "Công ty CP XD và SX Vật liệu XD Biên Hòa", "HPP": "Công ty CP Sơn Hải Phòng", 
        "WSB": "Công ty CP Bia Sài Gòn - Miền Tây", "F88": "Công ty CP Đầu tư Kinh doanh F88", "SEA": "Tổng Công ty Thủy sản Việt Nam", 
        "ODE": "Công ty CP Dịch vụ Dầu khí Biển", "PHP": "Công ty CP Cảng Hải Phòng", "VXB": "Công ty CP Vật liệu XD Bến Tre", 
        "APF": "Công ty CP Nông sản Thực phẩm Quảng Ngãi", "VNZ": "Công ty CP VNG", "HLB": "Công ty CP Hữu Liên", 
        "TED": "Công ty CP XD và Công nghệ Tiến Đạt", "VEF": "Công ty CP Trung tâm Hội chợ Triển lãm VN", "PAT": "Công ty CP Phốt pho Apatit VN", 
        "FOC": "Công ty CP Dịch vụ Trực tuyến FPT", "DTP": "Công ty CP Dược phẩm CPC1 Hà Nội", "SIV": "Công ty CP SIVICO", 
        "VGG": "Công ty CP May Vĩnh Phú", "AVC": "Công ty CP Thủy điện A Vương", "LSG": "Công ty CP Mía đường Lam Sơn", 
        "CQN": "Công ty CP Cảng Quảng Ninh", "QPH": "Công ty CP Quảng Ninh", "TCW": "Công ty CP Kho vận Tân Cảng", 
        "ACE": "Công ty CP Bê tông Hà Thanh", "VSF": "Công ty CP Giống cây trồng TW", "HAM": "Công ty CP Vật tư Hà Nội", 
        "SBM": "Công ty CP Đầu tư Phát triển Bắc Minh", "AGP": "Công ty CP Dược phẩm Agimexpharm", "LIC": "Công ty CP SX KD XNK Lam Sơn", 
        "SCL": "Công ty CP Sứ Cao Lãnh", "CC1": "Tổng Công ty Xây dựng số 1", "BWS": "Công ty CP Bia Sài Gòn - Sông Lam", 
        "NAS": "Công ty CP Phân bón Hà Bắc", "CLI": "Công ty CP XNK & XD Giao thông", "VTK": "Công ty CP Tư vấn và Dịch vụ Viettel", 
        "HMS": "Công ty CP Cơ khí Hà Nội", "PCC": "Công ty CP Tập đoàn XD PCC1", "QHW": "Công ty CP Nước Khoáng Quảng Ninh", 
        "MFS": "Công ty CP Dịch vụ Kỹ thuật Mobifone", "VEC": "Tổng Công ty Điện tử và Tin học VN", "HEC": "Công ty CP Tư vấn XD Thủy lợi và Môi trường",
        "ABB": "Ngân hàng TMCP An Bình", "ACB": "Ngân hàng TMCP Á Châu", "ACV": "TCT Cảng hàng không VN", "BVS": "CTCP Chứng khoán Bảo Việt", 
        "CAP": "CTCP Lâm nông sản thực phẩm Yên Bái", "CEO": "CTCP Tập đoàn C.E.O", "DNH": "CTCP Thủy điện Đa Nhim", 
        "DP3": "CTCP Dược phẩm Trung ương 3", "DTD": "CTCP Đầu tư Phát triển Thành Đạt", "DVN": "Tổng Công ty Dược Việt Nam", 
        "DXP": "CTCP Cảng Đình Vũ", "FOX": "CTCP Viễn thông FPT", "HND": "CTCP Nhiệt điện Hải Phòng", "HUT": "CTCP Tasco", 
        "IDC": "Tổng công ty IDICO", "IDP": "CTCP Sữa Quốc tế IDP", "L14": "CTCP Licogi 14", "L18": "CTCP Đầu tư và Xây dựng số 18",
        "LAS": "CTCP Supe Phốt phát và Hóa chất Lâm Thao", "LHC": "CTCP Đầu tư và Xây dựng Lắp máy IDICO", "MBS": "CTCP Chứng khoán MB", 
        "MSR": "CTCP Masan High-Tech Materials", "MVN": "Tổng Công ty Hàng hải Việt Nam", "NBC": "CTCP Than Núi Béo", 
        "NDN": "CTCP Đầu tư Phát triển Nhà Đà Nẵng", "NTP": "CTCP Nhựa Thiếu niên Tiền Phong", "OIL": "Tổng Công ty Dầu Việt Nam", 
        "PLC": "Tổng Công ty Hóa dầu Petrolimex", "PSD": "CTCP Dịch vụ Tổng hợp Dầu khí", "PVB": "CTCP bọc ống Dầu khí Việt Nam", 
        "PVC": "Tổng Công ty Hóa chất và Dung dịch Khoan Dầu khí", "PVS": "Tổng công ty CP Dịch vụ Kỹ thuật Dầu khí Việt Nam", 
        "PVI": "CTCP PVI", "QNS": "CTCP Đường Quảng Ngãi", "QTP": "CTCP Nhiệt điện Quảng Ninh", "SAS": "CTCP Dịch vụ Hàng không Sân bay Tân Sơn Nhất",
        "SHS": "CTCP Chứng khoán Sài Gòn - Hà Nội", "SLS": "CTCP Mía đường Sơn La", "SNZ": "Tổng Công ty Sonadezi",
        "TBD": "CTCP Chế tạo Thiết bị Điện Đông Anh", "TID": "Tổng Công ty Đầu tư Phát triển Hạ tầng Urban",
        "TIG": "CTCP Tập đoàn Đầu tư Thăng Long", "TNG": "CTCP Đầu tư và Thương mại TNG", "TOS": "CTCP Dịch vụ biển Tân Cảng", 
        "TVD": "CTCP Than Vàng Danh", "VC3": "CTCP Tập đoàn Nam Cường", "VCS": "CTCP Vicosstone", 
        "VEA": "Tổng công ty Máy động lực và máy nông nghiệp VN", "VFS": "CTCP Chứng khoất Nhất Việt", "VGI": "Tổng Công ty CP Đầu tư Quốc tế Viettel",
        "VGP": "CTCP Cảng Cần Giuộc", "VGR": "CTCP Vận tải và Xếp dỡ Hải An", "PRE": "Tổng công ty CP Tái bảo hiểm PVI",
        "HCC": "CTCP Bê tông Hòa Cầm - Intimex", "L40": "CTCP Licogi 40", "KDM": "CTCP ĐT&PT Dương Minh", "HVT": "CTCP Hóa chất Việt Trì", 
        "VTZ": "CTCP Thương mại và Đầu tư Vạn Tường", "GLT": "CTCP Kỹ thuật Điện chiếu sáng G.L.T", "VGS": "CTCP ống thép Việt Đức VG PIPE",
        "PCH": "CTCP Thạch cao Cần Thơ", "CAR": "CTCP Tập đoàn Đầu tư Địa ốc No Va", "HGM": "CTCP Cơ khí và Khoáng sản Hà Giang", 
        "KSV": "Tổng công ty Khoáng sản TKV", "THD": "CTCP Tập đoàn ThaiHoldings", "KSF": "CTCP Tập đoàn Sunshine Homes",
        "SCG": "CTCP Xây dựng Sông Đà 1.01", "CLM": "CTCP Than Cọc Sáu", "TMB": "CTCP Kinh doanh Than miền Nam",
        "SAF": "CTCP lương thực thực phẩm Safoco", "NET": "CTCP Bột giặt Net", "DHT": "CTCP Dược phẩm Hà Tây",
        "BAB": "Ngân hàng TMCP Bắc Á", "TV2": "CTCP Tư vấn Xây dựng Điện 2", "VCP": "CTCP Xây dựng điện VNECO 3",
        "DDV": "CTCP DAP - VINACHEM", "VGT": "Tập đoàn Dệt May Việt Nam", "SGP": "Tổng Công ty Cảng Sài Gòn",
        "DPR": "CTCP Cao su Đồng Phú", "DHC": "CTCP Đông Hải Bến Tre", "TCM": "CTCP Dệt mão Thành Công"
    }
    return company_names.get(symbol, f"Công ty Cổ phần {symbol}"), sector

# ==========================================
# 3. TỪ ĐIỂN DỊCH THUẬT (NÂNG CẤP TOÀN DIỆN)
# ==========================================
TRANSLATION_MAP = {
    # --- BỔ SUNG CÁC LỖI TỪ ẢNH MỚI NHẤT ---
    'N s': 'Số lượng cổ phiếu ròng',
    'M': 'Lợi ích cổ đông không kiểm soát',
    'Tổng khác f giá gốc': 'Tổng chi phí khác theo giá gốc',
    
    'N on ngắn hạn deferred taxes liabilities': 'Thuế thu nhập hoãn lại phải trả ngắn hạn',
    'Pensi onand khác post retirement benefit plans ngắn hạn': 'Quỹ phúc lợi nhân viên ngắn hạn',
    'Khác payable': 'Phải trả khác', 'Dividends payable': 'Cổ tức phải trả',
    'Tổng thuê payable': 'Tổng thuế phải trả',
    'Investmentsin joint venturesat cost': 'Đầu tư vào liên doanh theo giá gốc',
    'Investmentsin associatesat cost': 'Đầu tư vào công ty liên kết theo giá gốc',
    'Khác properties': 'Bất động sản khác', 'Buildings and improvements': 'Nhà cửa và vật kiến trúc',
    'Tiền mặt tiền mặt equivalents and short term investments': 'Tiền mặt, tương đương tiền và đầu tư ngắn hạn',
    'Taxes receivable': 'Thuế phải thu',
    'Investments in joint ventures at cost': 'Đầu tư vào liên doanh theo giá gốc',
    'Investments in associates at cost': 'Đầu tư vào công ty liên kết theo giá gốc',
    'Non ngắn hạn deferred taxes liabilities': 'Thuế thu nhập hoãn lại phải trả ngắn hạn',
    'Non current deferred taxes liabilities': 'Thuế thu nhập hoãn lại phải trả dài hạn',
    'Current deferred taxes liabilities': 'Thuế thu nhập hoãn lại phải trả ngắn hạn',
    'Other payable': 'Phải trả khác', 'Other payables': 'Phải trả khác', 'Other properties': 'Bất động sản khác',
    'Total tax payable': 'Tổng thuế phải trả', 'Total lease payable': 'Tổng tiền thuê phải trả',
    'Pension and other post retirement benefit plans current': 'Quỹ phúc lợi nhân viên ngắn hạn',
    'Pension and other post-retirement benefit plans current': 'Quỹ phúc lợi nhân viên ngắn hạn',
    'Pension and other post retirement benefit plans': 'Quỹ phúc lợi nhân viên và hưu trí',
    'Pension and other post-retirement benefit plans': 'Quỹ phúc lợi nhân viên và hưu trí',
    'Cash cash equivalents and short term investments': 'Tiền mặt, tương đương tiền và đầu tư ngắn hạn',
    'Current tax payable': 'Thuế phải trả ngắn hạn', 'Current tax receivables': 'Thuế phải thu ngắn hạn',
    'Investments in joint ventures': 'Đầu tư vào liên doanh', 'Investments in associates': 'Đầu tư vào công ty liên kết',
    'Tax payable': 'Thuế phải trả', 'Deferred taxes liabilities': 'Thuế thu nhập hoãn lại phải trả',
    'Other current payables': 'Phải trả ngắn hạn khác', 'Other non current payables': 'Phải trả dài hạn khác',
    'Other current receivables': 'Phải thu ngắn hạn khác', 'Other non current receivables': 'Phải thu dài hạn khác',
    'Net property plant and equipment': 'Tài sản cố định hữu hình thuần',
    'Gross property plant and equipment': 'Nguyên giá tài sản cố định hữu hình',
    'Property plant and equipment': 'Tài sản cố định hữu hình',
    'Accumulated depreciation': 'Hao mòn lũy kế tài sản cố định',
    'Other intangible assets': 'Tài sản cố định vô hình khác',
    'Goodwill and other intangible assets': 'Lợi thế thương mại và tài sản vô hình',
    'Short term investments': 'Đầu tư ngắn hạn', 'Long term investments': 'Đầu tư dài hạn',
    'Accounts receivable': 'Phải thu khách hàng', 'Accounts payable': 'Phải trả người bán',
    'Retained earnings': 'Lợi nhuận sau thuế chưa phân phối', 'Share premium': 'Thặng dư vốn cổ phần',
    'Share capital': 'Vốn góp chủ sở hữu', 'Total equity': 'Tổng vốn chủ sở hữu',
    'Minority interest': 'Lợi ích cổ đông không kiểm soát',

    # --- CÁC LỖI CŨ TỪ YFINANCE ĐÃ MAP ---
    'Total Expenses': 'Tổng chi phí', 'Classesof Cash Payments': 'Các khoản thanh toán tiền mặt',
    'Other Cash Paymentsfrom Operating Activities': 'Các khoản thanh toán tiền mặt khác từ HĐKD',
    'Paymentson Behalfof Employees': 'Thanh toán cho người lao động',
    'Classesof Cash Receiptsfrom Operating Activities': 'Các khoản thu tiền mặt từ HĐKD',
    'Other Cash Receiptsfrom Operating Activities': 'Các khoản thu tiền mặt khác từ HĐKD',
    'Dividends Received Cf': 'Cổ tức đã nhận', 'Sale Of PPE': 'Thu từ thanh lý tài sản cố định',
    'Purchase Of PPE': 'Chi mua sắm tài sản cố định',
    'Total Unusual Items Excluding Goodwill': 'Tổng các khoản mục bất thường (Không gồm lợi thế thương mại)',
    'Diluted NI Availto Com Stockholders': 'Lợi nhuận ròng pha loãng phân bổ cho CĐ phổ thông',
    'Other Cash Paymentsfrom Investing Activities': 'Các khoản thanh toán tiền mặt khác từ HĐ đầu tư',
    'Other Cash Receiptsfrom Investing Activities': 'Các khoản thu tiền mặt khác từ HĐ đầu tư',
    'Other Cash Paymentsfrom Financing Activities': 'Các khoản thanh toán tiền mặt khác từ HĐ tài chính',
    'Other Cash Receiptsfrom Financing Activities': 'Các khoản thu tiền mặt khác từ HĐ tài chính',
    'Classesof Cash Paymentsfrom Investing Activities': 'Các khoản thanh toán tiền mặt từ HĐ đầu tư',
    'Classesof Cash Receiptsfrom Investing Activities': 'Các khoản thu tiền mặt từ HĐ đầu tư',
    'Classesof Cash Paymentsfrom Financing Activities': 'Các khoản thanh toán tiền mặt từ HĐ tài chính',
    'Classesof Cash Receiptsfrom Financing Activities': 'Các khoản thu tiền mặt từ HĐ tài chính',
    'Diluted NI Available to Com Stockholders': 'Lợi nhuận ròng pha loãng phân bổ cho CĐ phổ thông',
    'Net Income from Continuing Operation Net Minority Interest': 'Lợi nhuận ròng từ HĐKD liên tục trừ lợi ích CĐ không kiểm soát',
    'Total Unusual Items Excluding Good': 'Tổng các khoản mục bất thường (Không gồm lợi thế thương mại)',
    'Net Income Common Stockholders': 'Lợi nhuận ròng phân bổ cho cổ đông phổ thông',
    'Total Other Finance Cost': 'Tổng chi phí tài chính khác',
    'Net Non Operating Interest Income Expense': 'Thu nhập/chi phí lãi thuần ngoài HĐKD',
    'Other Income Expense': 'Thu nhập/chi phí khác', 'Total Operating Income As Reported': 'Tổng lợi nhuận HĐKD như báo cáo',
    'Reconciled Depreciation': 'Khấu hao được điều chỉnh', 'Net Income Extraordinary': 'Lợi nhuận ròng bất thường',
    'Net Income Discontinuous Operations': 'Lợi nhuận ròng từ hoạt động không liên tục',
    'Net Income Continuous Operations': 'Lợi nhuận ròng từ hoạt động liên tục',
    'Minority Interests': 'Lợi ích cổ đông không kiểm soát', 'Special Income Charges': 'Chi phí thu nhập đặc biệt',
    'Other Special Charges': 'Chi phí đặc biệt khác', 'Write Off': 'Xóa sổ',

    # --- CÁC TỪ KHÓA CHUẨN ---
    'Balance_Sheet': 'Bảng cân đối kế toán', 'Income_Statement': 'Báo cáo kết quả kinh doanh',
    'Cash_Flow': 'Báo cáo lưu chuyển tiền tệ', 'Market_Metrics': 'Chỉ số thị trường, Định giá & Cổ tức',
    'Ordinary Shares Number': 'Số lượng cổ phiếu phổ thông', 'Share Issued': 'Cổ phiếu đã phát hành',
    'Total Assets': 'Tổng tài sản', 'Current Assets': 'Tài sản ngắn hạn',
    'Cash And Cash Equivalents': 'Tiền và các khoản tương đương tiền', 'Cash Financial': 'Tiền và đầu tư tài chính ngắn hạn',
    'Cash Equivalents': 'Các khoản tương đương tiền', 'Cash': 'Tiền mặt',
    'Other Short Term Investments': 'Đầu tư tài chính ngắn hạn khác', 'Receivables': 'Các khoản phải thu',
    'Accounts Receivable': 'Phải thu ngắn hạn khách hàng', 'Allowance For Doubtful Accounts Receivable': 'Dự phòng phải thu ngắn hạn khó đòi',
    'Due From Related Parties Current': 'Phải thu các bên liên quan ngắn hạn', 'Other Receivables': 'Các khoản phải thu ngắn hạn khác',
    'Inventory': 'Hàng tồn kho', 'Raw Materials': 'Nguyên liệu, vật liệu tồn kho',
    'Work In Process': 'Chi phí sản xuất kinh doanh dở dang', 'Finished Goods': 'Thành phẩm tồn kho',
    'Prepaid Assets': 'Chi phí trả trước ngắn hạn', 'Restricted Cash': 'Tiền bị hạn chế',
    'Total Non Current Assets': 'Tổng tài sản dài hạn', 'Net PPE': 'Tài sản cố định thuần',
    'Gross PPE': 'Nguyên giá tài sản cố định', 'Accumulated Depreciation': 'Hao mòn lũy kế tài sản cố định',
    'Machinery Furniture Equipment': 'Máy móc, thiết bị và phương tiện vận tải', 'Land And Improvements': 'Đất đai và cải tạo đất',
    'Properties': 'Bất động sản', 'Leases': 'Tài sản quyền sử dụng đất và thuê tài chính',
    'Construction In Progress': 'Xây dựng cơ bản dở dang', 'Goodwill And Other Intangible Assets': 'Lợi thế thương mại và tài sản vô hình',
    'Goodwill': 'Lợi thế thương mại', 'Other Intangible Assets': 'Tài sản cố định vô hình khác',
    'Investments And Advances': 'Đầu tư tài chính dài hạn', 'Investment in Financial Assets': 'Đầu tư tài chính dài hạn',
    'Held To Maturity Securities': 'Chứng khoán giữ đến ngày đáo hạn', 'Available For Sale Securities': 'Chứng khoán sẵn sàng để bán',
    'Investment Properties': 'Bất động sản đầu tư', 'Other Non Current Assets': 'Tài sản dài hạn khác',
    'Deferred Tax Assets': 'Tài sản thuế thu nhập hoãn lại',
    'Current Liabilities': 'Nợ ngắn hạn', 'Current Debt': 'Vay và nợ thuê tài chính ngắn hạn',
    'Payables': 'Các khoản phải trả', 'Accounts Payable': 'Phải trả người bán ngắn hạn',
    'Taxes Payable': 'Thuế và các khoản phải nộp nhà nước', 'Accrued Liabilities': 'Chi phí phải trả ngắn hạn',
    'Pension and Other Post-Retirement Benefit Plans Current': 'Quỹ phúc lợi nhân viên ngắn hạn',
    'Other Current Liabilities': 'Phải trả, phải nộp ngắn hạn khác', 'Total Liabilities Net Minority Interest': 'Tổng nợ phải trả',
    'Total Non Current Liabilities Net Minority Interest': 'Nợ dài hạn', 'Long Term Debt': 'Vay và nợ thuê tài chính dài hạn',
    'Total Debt': 'Tổng nợ vay', 'Net Debt': 'Nợ vay ròng', 'Deferred Revenue': 'Doanh thu chưa thực hiện dài hạn',
    'Deferred Tax Liabilities': 'Thuế thu nhập hoãn lại phải trả', 'Other Non Current Liabilities': 'Nợ dài hạn khác',
    'Stockholders Equity': 'Vốn chủ sở hữu', 'Capital Stock': 'Vốn góp chủ sở hữu', 'Common Stock': 'Cổ phiếu phổ thông',
    'Retained Earnings': 'Lợi nhuận sau thuế chưa phân phối', 'Additional Paid In Capital': 'Thặng dư vốn cổ phần',
    'Gains Losses Not Affecting Retained Earnings': 'Chênh lệch đánh giá lại tài sản và chênh lệch tỷ giá',
    'Minority Interest': 'Lợi ích cổ đông không kiểm soát', 'Total Equity Gross Minority Interest': 'Tổng vốn chủ sở hữu gồm cổ đông không kiểm soát',
    'Working Capital': 'Vốn lưu động ròng',
    'Total Revenue': 'Tổng doanh thu', 'Operating Revenue': 'Doanh thu thuần',
    'Cost Of Revenue': 'Giá vốn hàng bán', 'Gross Profit': 'Lợi nhuận gộp',
    'Operating Expense': 'Chi phí hoạt động', 'Selling General And Administration': 'Chi phí bán hàng và quản lý doanh nghiệp',
    'Selling And Marketing Expense': 'Chi phí bán hàng', 'General And Administrative Expense': 'Chi phí quản lý doanh nghiệp',
    'Research And Development': 'Chi phí nghiên cứu và phát triển', 'Other Operating Expenses': 'Chi phí hoạt động khác',
    'Operating Income': 'Lợi nhuận thuần từ hoạt động kinh doanh', 'Net Interest Income': 'Thu nhập lãi thuần',
    'Interest Expense': 'Chi phí lãi vay', 'Interest Income': 'Thu nhập lãi',
    'EBIT': 'Lợi nhuận trước lãi vay và thuế (EBIT)', 'EBITDA': 'Lợi nhuận trước lãi vay, thuế và khấu hao (EBITDA)',
    'Normalized EBITDA': 'Lợi nhuận trước lãi vay, thuế, khấu hao chuẩn hóa',
    'Normalized Income': 'Lợi nhuận thuần chuẩn hóa', 'Pretax Income': 'Lợi nhuận kế toán trước thuế',
    'Tax Provision': 'Chi phí thuế thu nhập doanh nghiệp', 'Net Income': 'Lợi nhuận sau thuế (Lợi nhuận ròng)',
    'Net Income Common Stockholders': 'Lợi nhuận ròng phân bổ cho cổ đông phổ thông',
    'Net Income Including Noncontrolling Interests': 'Lợi nhuận sau thuế bao gồm lợi ích cổ đông không kiểm soát',
    'Net Income From Continuing Operation': 'Lợi nhuận sau thuế từ hoạt động tiếp tục',
    'Net Income From Continuing And Discontinued Operation': 'Lợi nhuận thuần từ hoạt động tiếp tục và không tiếp tục',
    'Tax Effect Of Unusual Items': 'Ảnh hưởng thuế từ các khoản mục bất thường', 'Tax Rate For Calcs': 'Thuế suất dùng để tính toán',
    'Gain On Sale Of Security': 'Lãi / Lỗ từ bán chứng khoán', 'Other Under Preferred Stock Dividend': 'Cổ tức cổ phiếu ưu đãi và điều chỉnh khác',
    'Basic EPS': 'Lãi cơ bản trên cổ phiếu (Basic EPS)', 'Diluted EPS': 'Lãi suy giảm trên cổ phiếu (Diluted EPS)',
    'Diluted Average Shares': 'Số lượng cổ phiếu bình quân pha loãng', 'Basic Average Shares': 'Số lượng cổ phiếu bình quân cơ bản',
    'Operating Cash Flow': 'Lưu chuyển tiền thuần từ hoạt động kinh doanh',
    'Cash Flow From Continuing Operating Activities': 'Lưu chuyển tiền thuần từ hoạt động kinh doanh tiếp tục',
    'Depreciation Amortization Depletion': 'Khấu hao tài sản cố định và phân bổ',
    'Depreciation And Amortization': 'Khấu hao và phân bổ', 'Asset Impairment Charge': 'Tổn thất tài sản và dự phòng',
    'Deferred Income Tax': 'Thuế thu nhập hoãn lại', 'Change In Working Capital': 'Biến động vốn lưu động',
    'Change In Receivables': 'Biến động các khoản phải thu', 'Change In Inventory': 'Biến động hàng tồn kho',
    'Change In Payables': 'Biến động các khoản phải trả', 'Change In Account Payable': 'Biến động phải trả người bán',
    'Change In Other Working Capital': 'Biến động vốn lưu động khác',
    'Investing Cash Flow': 'Lưu chuyển tiền thuần từ hoạt động đầu tư',
    'Cash Flow From Continuing Investing Activities': 'Lưu chuyển tiền thuần từ hoạt động đầu tư tiếp tục',
    'Capital Expenditure': 'Chi phí đầu tư tài sản cố định (CapEx)', 'Net PPE Purchase And Sale': 'Tiền mua hoặc thanh lý tài sản cố định',
    'Net Intangibles Purchase And Sale': 'Tiền mua hoặc bán tài sản vô hình', 'Net Investment Purchase And Sale': 'Tiền đầu tư góp vốn thuần',
    'Net Business Purchase And Sale': 'Tiền mua bán công ty con hoặc sáp nhập', 'Free Cash Flow': 'Dòng tiền tự do (FCF)',
    'Financing Cash Flow': 'Lưu chuyển tiền thuần từ hoạt động tài chính',
    'Cash Flow From Continuing Financing Activities': 'Lưu chuyển tiền thuần từ hoạt động tài chính tiếp tục',
    'Issuance Of Debt': 'Tiền thu từ phát hành nợ vay', 'Repayment Of Debt': 'Tiền chi trả nợ gốc vay',
    'Net Common Stock Issuance': 'Tiền thu từ phát hành cổ phiếu hoặc bán cổ phiếu quỹ',
    'Cash Dividends Paid': 'Cổ tức đã chi trả cho chủ sở hữu', 'Beginning Cash Position': 'Tiền và tương đương tiền đầu kỳ',
    'End Cash Position': 'Tiền và tương đương tiền cuối kỳ', 'Changes In Cash': 'Ảnh hưởng thay đổi tỷ giá và tiền thuần thay đổi',
    'Current Price': 'Giá cổ phiếu hiện tại', 'Shares Outstanding': 'Tổng số lượng cổ phiếu lưu hành',
    'Market Capitalization': 'Vốn hóa thị trường', 'Trailing EPS': 'EPS cơ bản 4 quý gần nhất (Trailing EPS)',
    'Forward EPS': 'EPS dự phóng (Forward EPS)', 'Dividend Yield': 'Tỷ suất cổ tức (% Dividend Yield)',
    'Dividend Rate': 'Cổ tức tiền mặt trên mỗi cổ phiếu', 'Trailing P/E': 'Hệ số P/E cơ bản (Trailing P/E)',
    'Forward P/E': 'Hệ số P/E dự phóng (Forward P/E)', 'Price To Book': 'Hệ số P/B (Price to Book)',
    'Book Value': 'Giá trị sổ sách mỗi cổ phiếu (BVPS)', 'Return On Equity': 'Lợi nhuận trên vốn chủ sở hữu (ROE)',
    'Return On Assets': 'Lợi nhuận trên tổng tài sản (ROA)', 'Profit Margins': 'Biên lợi nhuận ròng (%)',
    'Gross Margins': 'Biên lợi nhuận gộp (%)', 'Historical Dividend Cash': 'Lịch sử trả cổ tức bằng tiền (VND/Cổ phiếu)'
}

# ==========================================
# 4. LÕI LÀM SẠCH CHUYÊN SÂU (DEEP CLEANING CORE)
# ==========================================
def format_value(x):
    if pd.isna(x): return None
    try:
        if isinstance(x, str):
            x = x.replace(',', '').replace(' ', '')
            if x.count('.') > 1: 
                x = x.replace('.', '')
        val = float(x)
        if abs(val) > 1e15: return None
        if val == 0 or val != val or val in [float('inf'), float('-inf')]: return None
        return round(val, 4)
    except:
        return None

def clean_text(text):
    if pd.isna(text): return ""
    text = str(text)
    text = re.sub(r'[\n\r\t]+', ' ', text) 
    text = re.sub(r'\s{2,}', ' ', text)    
    return text.strip()

def fix_truncated_text(text):
    text = clean_text(text)
    fixes = {
        "Các khoản phải": "Các khoản phải thu",
        "Lợi nhuận trước": "Lợi nhuận trước thuế",
        "Thuế và các kho": "Thuế và các khoản phải nộp",
        "Tiền và tương đ": "Tiền và tương đương tiền",
        "TỔNG CỘNG N": "TỔNG CỘNG NỢ PHẢI TRẢ",
        "VỐN CHỦ SỞ H": "VỐN CHỦ SỞ HỮU",
        "Cổ phiếu phổ thô": "Cổ phiếu phổ thông",
        "Đầu tư dài hạn k": "Đầu tư dài hạn khác",
        "Lợi nhuận thuần": "Lợi nhuận thuần từ HĐKD",
        "Lưu chuyển tiền": "Lưu chuyển tiền thuần",
        "Lãi / Lỗ từ đánh": "Lãi / Lỗ từ đánh giá lại tài sản",
        "Tổng tài sản": "Tổng tài sản",
        "Tổng khác f giá gốc": "Tổng chi phí khác theo giá gốc"
    }
    for k, v in fixes.items():
        if text.startswith(k):
            return v
    return text

def fix_yfinance_typos(text):
    text = re.sub(r'([a-z])(from|to|of|on|for|and|at|in)', r'\1 \2', text, flags=re.IGNORECASE)
    text = re.sub(r'Investmentsin', 'Investments in', text, flags=re.IGNORECASE)
    text = re.sub(r'venturesat', 'ventures at', text, flags=re.IGNORECASE)
    text = re.sub(r'associatesat', 'associates at', text, flags=re.IGNORECASE)
    text = re.sub(r'Pensi onand', 'Pension and', text, flags=re.IGNORECASE)
    text = re.sub(r'\bN on\b', 'Non', text, flags=re.IGNORECASE)
    text = re.sub(r'Classesof', 'Classes of', text, flags=re.IGNORECASE)
    text = re.sub(r'Receiptsfrom', 'Receipts from', text, flags=re.IGNORECASE)
    text = re.sub(r'Paymentsfrom', 'Payments from', text, flags=re.IGNORECASE)
    text = re.sub(r'Paymentson', 'Payments on', text, flags=re.IGNORECASE)
    text = re.sub(r'Behalfof', 'Behalf of', text, flags=re.IGNORECASE)
    text = re.sub(r'([a-z])([A-Z])', r'\1 \2', text)
    text = re.sub(r'\bf\b', 'phí', text, flags=re.IGNORECASE)
    return re.sub(r'\s{2,}', ' ', text).strip()

FALLBACK_MAP = {
    'deferred': 'hoãn lại', 'taxes': 'thuế', 'liabilities': 'nợ phải trả',
    'payable': 'phải trả', 'receivable': 'phải thu', 'dividends': 'cổ tức',
    'pension': 'lương hưu', 'post': 'sau', 'retirement': 'nghỉ hưu',
    'benefit': 'phúc lợi', 'plans': 'kế hoạch', 'joint': 'liên doanh',
    'ventures': 'liên doanh', 'associates': 'liên kết', 'cost': 'giá gốc',
    'current': 'ngắn hạn', 'non': 'dài hạn', 'fixed': 'cố định',
    'intangible': 'vô hình', 'tangible': 'hữu hình', 'assets': 'tài sản',
    'equity': 'vốn chủ sở hữu', 'revenue': 'doanh thu', 'expense': 'chi phí',
    'income': 'thu nhập', 'sales': 'bán hàng', 'operating': 'hoạt động',
    'activities': 'kinh doanh', 'investing': 'đầu tư', 'financing': 'tài chính',
    'cash': 'tiền mặt', 'equivalents': 'tương đương tiền', 'short': 'ngắn hạn',
    'term': 'hạn', 'long': 'dài hạn', 'properties': 'bất động sản',
    'buildings': 'nhà cửa', 'improvements': 'cải tạo', 'lease': 'thuê',
    'total': 'tổng', 'other': 'khác', 'investments': 'đầu tư',
    'in': 'trong', 'at': 'tại', 'and': 'và', 'of': 'của', 'on': 'trên', 'for': 'cho',
    'gross': 'tổng', 'net': 'ròng', 'property': 'tài sản', 'plant': 'nhà máy',
    'equipment': 'thiết bị', 'accumulated': 'lũy kế', 'depreciation': 'khấu hao',
    'goodwill': 'lợi thế thương mại', 'inventory': 'hàng tồn kho',
    'accounts': 'các khoản', 'retained': 'giữ lại', 'earnings': 'thu nhập',
    'share': 'cổ phiếu', 'capital': 'vốn', 'premium': 'thặng dư',
    'minority': 'thiểu số', 'interest': 'lợi ích'
}

def translate_metric(metric_original, is_vn=False):
    cleaned_key = clean_text(metric_original)
    
    # 1. Kiểm tra từ điển chính xác trước (áp dụng cho cả tiếng Anh lẫn tiếng Việt lỗi)
    if cleaned_key in TRANSLATION_MAP: return TRANSLATION_MAP[cleaned_key]
    for eng_k, vie_v in TRANSLATION_MAP.items():
        if cleaned_key.lower() == eng_k.lower(): return vie_v

    # 2. Nếu là tiếng Việt, tiến hành làm sạch các từ tiếng Anh lọt lưới (như M, N s)
    if is_vn or any(char in cleaned_key for char in ['à','á','ả','ã','ạ','ă','â','đ','ê','ô','ơ','ư','ý']):
        cleaned_key = re.sub(r'\bM\b', 'Lợi ích cổ đông không kiểm soát', cleaned_key)
        cleaned_key = re.sub(r'\bN s\b', 'Số lượng cổ phiếu ròng', cleaned_key)
        cleaned_key = cleaned_key.replace('f giá gốc', 'phí giá gốc')
        return cleaned_key

    # 3. Tiếp tục xử lý cho tiếng Anh
    fixed_key = fix_yfinance_typos(cleaned_key)
    if fixed_key in TRANSLATION_MAP: return TRANSLATION_MAP[fixed_key]
    for eng_k, vie_v in TRANSLATION_MAP.items():
        if fixed_key.lower() == eng_k.lower(): return vie_v
        
    k_lower = fixed_key.lower()
    
    if 'gain' in k_lower and 'loss' in k_lower: return 'Lãi / Lỗ từ đánh giá hoặc thanh lý tài sản'
    if 'effect of exchange' in k_lower or 'foreign' in k_lower: return 'Ảnh hưởng thay đổi tỷ giá hối đoái'
    if 'net income' in k_lower or 'net profit' in k_lower: return 'Lợi nhuận sau thuế (Lợi nhuận ròng)'
    if 'operating income' in k_lower or 'operating profit' in k_lower: return 'Lợi nhuận thuần từ hoạt động kinh doanh'
    if 'gross profit' in k_lower: return 'Lợi nhuận gộp'
    if 'pretax income' in k_lower or 'income before tax' in k_lower: return 'Lợi nhuận kế toán trước thuế'
    if 'revenue' in k_lower or 'sales' in k_lower: return 'Tổng doanh thu / Doanh thu thuần'
    if 'cost of' in k_lower or 'cogs' in k_lower: return 'Giá vốn hàng bán'
    if 'interest expense' in k_lower: return 'Chi phí lãi vay'
    if 'interest income' in k_lower: return 'Thu nhập lãi'
    if 'tax provision' in k_lower or 'tax expense' in k_lower: return 'Chi phí thuế thu nhập doanh nghiệp'
    if 'depreciation' in k_lower or 'amortization' in k_lower: return 'Khấu hao tài sản cố định và phân bổ'
    if 'cash flow' in k_lower: return 'Lưu chuyển tiền thuần'
    
    words = fixed_key.split()
    translated_words = []
    for w in words:
        if any(char in w for char in ['à','á','ả','ã','ạ','ă','â','đ','ê','ô','ơ','ư','ý']):
            translated_words.append(w)
            continue
            
        w_clean = re.sub(r'[^a-zA-Z]', '', w).lower()
        if w_clean in FALLBACK_MAP:
            translated_words.append(FALLBACK_MAP[w_clean])
        elif w.isupper() and len(w) <= 5:
            translated_words.append(w)
            
    result = " ".join(translated_words)
    
    # Xóa sạch các ký tự tiếng Anh đơn lẻ như 'M', 'N', 'f'
    result = re.sub(r'\b[a-zA-Z]\b', '', result)
    result = re.sub(r'\s{2,}', ' ', result).strip()
    
    if not result:
        result = "Chỉ tiêu chưa xác định"
        
    return result.capitalize()

def final_format_for_csv(x):
    if pd.isna(x): return ""
    val = float(x)
    if val.is_integer():
        return str(int(val))
    return str(round(val, 4))

# ==========================================
# [NÂNG CẤP TỬ THẦN] CÁC HÀM FALLBACK API
# ==========================================
def fetch_tcbs_fallback(symbol):
    records = []
    company_name, sector_name = get_company_profile(symbol)
    current_year = str(datetime.now().year)
    today_str = datetime.today().strftime('%Y-%m-%d')
    try:
        url_price = f"https://apipubaws.tcbs.com.vn/stock-insight/v2/stock/{symbol}/day-summary"
        res = session.get(url_price, timeout=10)
        if res.status_code == 200:
            data = res.json()
            price = data.get('close') or data.get('price')
            if price and float(price) > 0:
                formatted_val = format_value(price)
                if formatted_val:
                    records.append({'Mã chứng khoán': symbol, 'Tên doanh nghiệp': company_name, 'Tên ngành': sector_name, 'Loại báo cáo': 'Chỉ số thị trường, Định giá & Cổ tức', 'Loại kỳ': 'Real-time', 'Năm': current_year, 'Ngày kỳ': today_str, 'Chỉ tiêu tiếng Việt': 'Giá cổ phiếu hiện tại', 'Giá trị': formatted_val})
    except Exception: pass
    try:
        url_ov = f"https://apipubaws.tcbs.com.vn/tcanalysis/v1/ticker/{symbol}/overview"
        res = session.get(url_ov, timeout=10)
        if res.status_code == 200:
            data = res.json()
            shares = data.get('outstandingShare') or data.get('issueShare')
            if shares and float(shares) > 0:
                formatted_val = format_value(shares)
                if formatted_val:
                    records.append({'Mã chứng khoán': symbol, 'Tên doanh nghiệp': company_name, 'Tên ngành': sector_name, 'Loại báo cáo': 'Chỉ số thị trường, Định giá & Cổ tức', 'Loại kỳ': 'Real-time', 'Năm': current_year, 'Ngày kỳ': today_str, 'Chỉ tiêu tiếng Việt': 'Tổng số lượng cổ phiếu lưu hành', 'Giá trị': formatted_val})
    except Exception: pass
    return records

def fetch_vps_fallback(symbol):
    records = []
    company_name, sector_name = get_company_profile(symbol)
    current_year = str(datetime.now().year)
    today_str = datetime.today().strftime('%Y-%m-%d')
    try:
        url = f"https://bgapidatafeed.vps.com.vn/getliststockdata/{symbol}"
        res = session.get(url, timeout=10)
        if res.status_code == 200:
            data = res.json()
            if isinstance(data, list) and len(data) > 0:
                item = data[0]
                price = item.get('lastPrice') or item.get('closePrice')
                shares = item.get('listedShare') or item.get('issueShare')
                
                if price and float(price) > 0:
                    formatted_val = format_value(price)
                    if formatted_val:
                        records.append({'Mã chứng khoán': symbol, 'Tên doanh nghiệp': company_name, 'Tên ngành': sector_name, 'Loại báo cáo': 'Chỉ số thị trường, Định giá & Cổ tức', 'Loại kỳ': 'Real-time', 'Năm': current_year, 'Ngày kỳ': today_str, 'Chỉ tiêu tiếng Việt': 'Giá cổ phiếu hiện tại', 'Giá trị': formatted_val})
                if shares and float(shares) > 0:
                    formatted_val = format_value(shares)
                    if formatted_val:
                        records.append({'Mã chứng khoán': symbol, 'Tên doanh nghiệp': company_name, 'Tên ngành': sector_name, 'Loại báo cáo': 'Chỉ số thị trường, Định giá & Cổ tức', 'Loại kỳ': 'Real-time', 'Năm': current_year, 'Ngày kỳ': today_str, 'Chỉ tiêu tiếng Việt': 'Tổng số lượng cổ phiếu lưu hành', 'Giá trị': formatted_val})
    except Exception: pass
    return records

def fetch_vndirect_fallback(symbol):
    records = []
    company_name, sector_name = get_company_profile(symbol)
    current_year = str(datetime.now().year)
    today_str = datetime.today().strftime('%Y-%m-%d')
    try:
        url_p = f"https://api-finfo.vndirect.com.vn/v4/stock_prices?sort=date:desc&q=code:{symbol}&size=1"
        res = session.get(url_p, timeout=10)
        if res.status_code == 200:
            data = res.json()
            if data.get('data') and len(data['data']) > 0:
                price = data['data'][0].get('close')
                if price and float(price) > 0:
                    formatted_val = format_value(price)
                    if formatted_val:
                        records.append({'Mã chứng khoán': symbol, 'Tên doanh nghiệp': company_name, 'Tên ngành': sector_name, 'Loại báo cáo': 'Chỉ số thị trường, Định giá & Cổ tức', 'Loại kỳ': 'Real-time', 'Năm': current_year, 'Ngày kỳ': today_str, 'Chỉ tiêu tiếng Việt': 'Giá cổ phiếu hiện tại', 'Giá trị': formatted_val})
    except Exception: pass
    try:
        url_s = f"https://api-finfo.vndirect.com.vn/v4/company_statistics?q=code:{symbol}"
        res = session.get(url_s, timeout=10)
        if res.status_code == 200:
            data = res.json()
            if data.get('data') and len(data['data']) > 0:
                shares = data['data'][0].get('listedShare') or data['data'][0].get('issueShare')
                if shares and float(shares) > 0:
                    formatted_val = format_value(shares)
                    if formatted_val:
                        records.append({'Mã chứng khoán': symbol, 'Tên doanh nghiệp': company_name, 'Tên ngành': sector_name, 'Loại báo cáo': 'Chỉ số thị trường, Định giá & Cổ tức', 'Loại kỳ': 'Real-time', 'Năm': current_year, 'Ngày kỳ': today_str, 'Chỉ tiêu tiếng Việt': 'Tổng số lượng cổ phiếu lưu hành', 'Giá trị': formatted_val})
    except Exception: pass
    return records

# ==========================================
# 5. CÁC HÀM CÀO DỮ LIỆU TỪ YFINANCE
# ==========================================
def parse_financial_df(symbol, df, statement_type_raw, ky_bao_cao, min_year=2000):
    records = []
    company_name, sector_name = get_company_profile(symbol)
    statement_type_vn = TRANSLATION_MAP.get(statement_type_raw, statement_type_raw)
    try:
        if df is not None and not df.empty:
            for col in df.columns:
                date_str = str(col).split('T')[0].split(' ')[0]
                year_val = date_str.split('-')[0]
                if year_val.isdigit() and int(year_val) >= min_year:
                    for row_idx, val in df[col].items():
                        if pd.notna(val):
                            formatted_val = format_value(val)
                            if formatted_val is not None:
                                metric_vn = translate_metric(str(row_idx).strip())
                                records.append({
                                    'Mã chứng khoán': symbol, 'Tên doanh nghiệp': company_name,
                                    'Tên ngành': sector_name, 'Loại báo cáo': statement_type_vn,
                                    'Loại kỳ': ky_bao_cao, 'Năm': year_val, 'Ngày kỳ': date_str,
                                    'Chỉ tiêu tiếng Việt': metric_vn, 'Giá trị': formatted_val
                                })
    except Exception: pass
    return records

def fetch_historical_dividends(symbol, ticker_obj, min_year=2000):
    records = []
    company_name, sector_name = get_company_profile(symbol)
    try:
        divs = ticker_obj.dividends
        if divs is not None and not divs.empty:
            for date_idx, div_val in divs.items():
                date_str = str(date_idx).split('T')[0].split(' ')[0]
                year_val = date_str.split('-')[0]
                if year_val.isdigit() and int(year_val) >= min_year:
                    if pd.notna(div_val):
                        formatted_val = format_value(div_val)
                        if formatted_val is not None:
                            records.append({
                                'Mã chứng khoán': symbol, 'Tên doanh nghiệp': company_name,
                                'Tên ngành': sector_name, 'Loại báo cáo': 'Chỉ số thị trường, Định giá & Cổ tức',
                                'Loại kỳ': 'Sự kiện cổ tức', 'Năm': year_val, 'Ngày kỳ': date_str,
                                'Chỉ tiêu tiếng Việt': 'Lịch sử trả cổ tức bằng tiền (VND/Cổ phiếu)', 'Giá trị': formatted_val
                            })
    except Exception: pass
    return records

def fetch_market_and_valuation_metrics(symbol, ticker_obj, balance_sheet_df):
    records = []
    company_name, sector_name = get_company_profile(symbol)
    current_year = str(datetime.now().year)
    today_str = datetime.today().strftime('%Y-%m-%d')
    current_price = 0.0; shares_out = 0.0; market_cap = 0.0; div_yield = 0.0
    
    try:
        if ticker_obj:
            try:
                hist = ticker_obj.history(period="5d")
                if not hist.empty:
                    current_price = float(hist['Close'].iloc[-1])
            except: pass
                
            try:
                info = ticker_obj.info
                if not current_price:
                    current_price = float(info.get('regularMarketPrice', 0) or info.get('previousClose', 0) or 0)
                shares_out = float(info.get('sharesOutstanding', 0) or 0)
                div_yield = float(info.get('dividendYield', 0) or 0) * 100 if info.get('dividendYield') else 0.0
            except: pass

        if (not shares_out or shares_out == 0.0) and balance_sheet_df is not None and not balance_sheet_df.empty:
            for row_idx in balance_sheet_df.index:
                row_str = str(row_idx).lower()
                if 'ordinary shares number' in row_str or 'share issued' in row_str or 'common stock' in row_str:
                    for col in balance_sheet_df.columns:
                        val = balance_sheet_df.loc[row_idx, col]
                        if pd.notna(val) and float(val) > 0:
                            shares_out = float(val)
                            break
                    if shares_out: break
                    
        if (not market_cap or market_cap == 0.0) and current_price > 0 and shares_out > 0:
            market_cap = current_price * shares_out
            
        metrics = [
            ('Current Price', current_price), ('Shares Outstanding', shares_out),
            ('Market Capitalization', market_cap), ('Dividend Yield', div_yield)
        ]
        for eng_key, val in metrics:
            if val is not None:
                formatted_val = format_value(val)
                if formatted_val is not None:
                    metric_vn = TRANSLATION_MAP.get(eng_key, eng_key)
                    records.append({
                        'Mã chứng khoán': symbol, 'Tên doanh nghiệp': company_name,
                        'Tên ngành': sector_name, 'Loại báo cáo': 'Chỉ số thị trường, Định giá & Cổ tức',
                        'Loại kỳ': 'Real-time', 'Năm': current_year, 'Ngày kỳ': today_str,
                        'Chỉ tiêu tiếng Việt': metric_vn, 'Giá trị': formatted_val
                    })
    except Exception: pass
    return records

def fetch_market_indices():
    indices = {"VN-INDEX": "^VNINDEX", "HNX-INDEX": "^HNX", "UPCOM-INDEX": "^UPCOM"}
    market_records = []
    current_year = str(datetime.now().year)
    today_str = datetime.today().strftime('%Y-%m-%d')
    for index_name, ticker_symbol in indices.items():
        try:
            t = yf.Ticker(ticker_symbol, session=session)
            hist = t.history(period="5d")
            current_val = float(hist['Close'].iloc[-1]) if not hist.empty else 0
            prev_close = float(hist['Close'].iloc[-2]) if len(hist) > 1 else current_val
            change_val = current_val - prev_close
            change_pct = (change_val / prev_close) * 100 if prev_close else 0
            
            for name, val in [('Giá trị chỉ số', current_val), ('Biến động điểm (Change)', change_val), ('Biến động phần trăm (Percent Change)', change_pct)]:
                formatted_val = format_value(val)
                if formatted_val is not None:
                    market_records.append({
                        'Mã chứng khoán': index_name, 'Tên doanh nghiệp': f'Chỉ số thị trường {index_name}',
                        'Tên ngành': 'Chỉ số vĩ mô', 'Loại báo cáo': 'Chỉ số thị trường, Định giá & Cổ tức',
                        'Loại kỳ': 'Real-time hằng ngày', 'Năm': current_year, 'Ngày kỳ': today_str,
                        'Chỉ tiêu tiếng Việt': name, 'Giá trị': formatted_val
                    })
        except Exception: pass
    return market_records

# ==========================================
# 6. HÀM CÀO DỮ LIỆU TỪ VNSTOCK & FALLBACK
# ==========================================
def parse_vnstock_df(symbol, df, statement_type_vn, ky_bao_cao):
    records = []
    company_name, sector_name = get_company_profile(symbol)
    if df is None or df.empty: return records

    for _, row in df.iterrows():
        metric_raw = row.get('item', row.get('item_en', ''))
        metric_vn = translate_metric(metric_raw)
        
        for col in df.columns:
            col_str = str(col)
            if col_str in ['item', 'item_en', 'unit', 'ticker', 'year', 'quarter', 'date', 'period', 'id', 'name', 'order', 'level', 'off_balance', 'category']: continue
            
            year_val = col_str.split('-')[0].split(' ')[0].strip()
            if not year_val.isdigit() or int(year_val) < 2000: continue

            val = row[col]
            if pd.notna(val):
                formatted_val = format_value(val)
                if formatted_val is not None:
                    records.append({
                        'Mã chứng khoán': symbol, 'Tên doanh nghiệp': company_name,
                        'Tên ngành': sector_name, 'Loại báo cáo': statement_type_vn,
                        'Loại kỳ': ky_bao_cao, 'Năm': year_val, 'Ngày kỳ': f"{year_val}-12-31" if ky_bao_cao == 'Năm' else col_str,
                        'Chỉ tiêu tiếng Việt': metric_vn, 'Giá trị': formatted_val
                    })
    return records

def fetch_vnstock_financials(symbol):
    records = []
    # 1. Thử lấy qua vnstock VCI
    try:
        fin = Fundamental(source='VCI')
        try: records.extend(parse_vnstock_df(symbol, fin.balance_sheet(symbol=symbol, period='year'), 'Bảng cân đối kế toán', 'Năm'))
        except Exception: pass
        try: records.extend(parse_vnstock_df(symbol, fin.income_statement(symbol=symbol, period='year'), 'Báo cáo kết quả kinh doanh', 'Năm'))
        except Exception: pass
        try: records.extend(parse_vnstock_df(symbol, fin.cash_flow(symbol=symbol, period='year'), 'Báo cáo lưu chuyển tiền tệ', 'Năm'))
        except Exception: pass
        
        try: records.extend(parse_vnstock_df(symbol, fin.balance_sheet(symbol=symbol, period='quarter'), 'Bảng cân đối kế toán', 'Quý'))
        except Exception: pass
        try: records.extend(parse_vnstock_df(symbol, fin.income_statement(symbol=symbol, period='quarter'), 'Báo cáo kết quả kinh doanh', 'Quý'))
        except Exception: pass
        try: records.extend(parse_vnstock_df(symbol, fin.cash_flow(symbol=symbol, period='quarter'), 'Báo cáo lưu chuyển tiền tệ', 'Quý'))
        except Exception: pass

        try:
            market = Market(source='VCI')
            quote_df = market.quote(symbol=symbol)
            if quote_df is not None and not quote_df.empty:
                q = quote_df.iloc[0]
                price = q.get('close_price') or q.get('match_price') or q.get('price')
                if price and float(price) > 0:
                    formatted_price = format_value(price)
                    if formatted_price is not None:
                        company_name, sector_name = get_company_profile(symbol)
                        records.append({
                            'Mã chứng khoán': symbol, 'Tên doanh nghiệp': company_name,
                            'Tên ngành': sector_name, 'Loại báo cáo': 'Chỉ số thị trường, Định giá & Cổ tức',
                            'Loại kỳ': 'Real-time', 'Năm': str(datetime.now().year), 'Ngày kỳ': datetime.today().strftime('%Y-%m-%d'),
                            'Chỉ tiêu tiếng Việt': 'Giá cổ phiếu hiện tại', 'Giá trị': formatted_price
                        })
        except Exception: pass
        
        try:
            ratio_df = fin.ratio(symbol=symbol)
            if ratio_df is not None and not ratio_df.empty:
                shares = None
                for col in ['outstanding_shares', 'issue_share', 'Ordinary Shares Number']:
                    if col in ratio_df.columns:
                        shares = ratio_df[col].iloc[0]
                        break
                if shares and float(shares) > 0:
                    formatted_shares = format_value(shares)
                    if formatted_shares is not None:
                        company_name, sector_name = get_company_profile(symbol)
                        records.append({
                            'Mã chứng khoán': symbol, 'Tên doanh nghiệp': company_name,
                            'Tên ngành': sector_name, 'Loại báo cáo': 'Chỉ số thị trường, Định giá & Cổ tức',
                            'Loại kỳ': 'Real-time', 'Năm': str(datetime.now().year), 'Ngày kỳ': datetime.today().strftime('%Y-%m-%d'),
                            'Chỉ tiêu tiếng Việt': 'Tổng số lượng cổ phiếu lưu hành', 'Giá trị': formatted_shares
                        })
        except Exception: pass
    except Exception: pass

    # 2. NÂNG CẤP: Nếu vnstock không lấy được Giá hoặc SLCP, gọi API Fallback
    has_price = any(r['Chỉ tiêu tiếng Việt'] == 'Giá cổ phiếu hiện tại' for r in records)
    has_shares = any(r['Chỉ tiêu tiếng Việt'] == 'Tổng số lượng cổ phiếu lưu hành' for r in records)
    
    if not has_price or not has_shares:
        # Thử VPS trước (Rất ít khi chặn IP)
        vps_recs = fetch_vps_fallback(symbol)
        for vr in vps_recs:
            if not any(r['Chỉ tiêu tiếng Việt'] == vr['Chỉ tiêu tiếng Việt'] for r in records):
                records.append(vr)
                
    has_price = any(r['Chỉ tiêu tiếng Việt'] == 'Giá cổ phiếu hiện tại' for r in records)
    has_shares = any(r['Chỉ tiêu tiếng Việt'] == 'Tổng số lượng cổ phiếu lưu hành' for r in records)

    if not has_price or not has_shares:
        # Thử VNDirect
        vnd_recs = fetch_vndirect_fallback(symbol)
        for vr in vnd_recs:
            if not any(r['Chỉ tiêu tiếng Việt'] == vr['Chỉ tiêu tiếng Việt'] for r in records):
                records.append(vr)

    has_price = any(r['Chỉ tiêu tiếng Việt'] == 'Giá cổ phiếu hiện tại' for r in records)
    has_shares = any(r['Chỉ tiêu tiếng Việt'] == 'Tổng số lượng cổ phiếu lưu hành' for r in records)

    if not has_price or not has_shares:
        # Thử TCBS
        tcbs_records = fetch_tcbs_fallback(symbol)
        for tr in tcbs_records:
            if not any(r['Chỉ tiêu tiếng Việt'] == tr['Chỉ tiêu tiếng Việt'] for r in records):
                records.append(tr)
                
    return records

# ==========================================
# 7. HÀM CÀO DỮ LIỆU TỪ VNFINANCIALDATA
# ==========================================
def find_value_column(df):
    for name in ['value', 'ratio_value', 'value_ratio', 'Value', 'ratio', 'val']:
        if name in df.columns: return name
    for col in df.columns:
        if df[col].dtype in ['float64', 'int64']: return col
    return None

def fetch_vnfinancialdata_bulk(ticker_market_map):
    records = []
    statements = {
        "balance_sheet": "Bảng cân đối kế toán",
        "income_statement": "Báo cáo kết quả kinh doanh",
        "cash_flow": "Báo cáo lưu chuyển tiền tệ",
        "ratio": "Chỉ số tài chính & Định giá"
    }
    target_symbols = set(ticker_market_map.keys())

    for exchange in ["HSX", "HNX"]:
        for stmt_key, stmt_name in statements.items():
            try:
                print(f"  📥 Đang tải {stmt_name} cho sàn {exchange}...")
                df = vnf.load(exchange=exchange, statement=stmt_key)
                if df is None or df.empty: continue
                
                value_col = find_value_column(df)
                if not value_col: continue
                
                rename_map = {'ticker': 'Mã chứng khoán', 'year': 'Năm', 'item_name': 'Chỉ tiêu tiếng Việt'}
                if value_col != 'value': rename_map[value_col] = 'Giá trị'
                else: rename_map['value'] = 'Giá trị'
                if 'item_name' not in df.columns and 'item' in df.columns: rename_map['item'] = 'Chỉ tiêu tiếng Việt'
                
                df = df.rename(columns=rename_map)
                if 'Giá trị' not in df.columns: continue
                
                df = df[df['Mã chứng khoán'].isin(target_symbols)]
                
                for _, row in df.iterrows():
                    formatted_val = format_value(row['Giá trị'])
                    if formatted_val is None: continue
                    
                    symbol = row['Mã chứng khoán']
                    company_name, sector_name = get_company_profile(symbol)
                    year_val = str(row['Năm'])
                    
                    metric_vn = fix_truncated_text(translate_metric(row['Chỉ tiêu tiếng Việt'], is_vn=True))

                    records.append({
                        'Mã chứng khoán': symbol, 'Tên doanh nghiệp': company_name,
                        'Tên ngành': sector_name, 'Loại báo cáo': stmt_name,
                        'Loại kỳ': 'Năm', 'Năm': year_val, 'Ngày kỳ': f"{year_val}-12-31",
                        'Chỉ tiêu tiếng Việt': metric_vn, 'Giá trị': formatted_val
                    })
            except Exception as e:
                pass
                
    return records

# ==========================================
# 8. HÀM ĐIỀU PHỐI
# ==========================================
def process_single_ticker(symbol, category):
    recs = []
    suffixes = [".VN", ".HN", ""]
    for suffix in suffixes:
        try:
            ticker = yf.Ticker(f"{symbol}{suffix}", session=session)
            bs_df = getattr(ticker, 'balance_sheet', None)
            if bs_df is not None and not bs_df.empty:
                recs.extend(parse_financial_df(symbol, bs_df, 'Balance_Sheet', 'Năm'))
                recs.extend(parse_financial_df(symbol, getattr(ticker, 'quarterly_balance_sheet', None), 'Balance_Sheet', 'Quý'))
                recs.extend(parse_financial_df(symbol, getattr(ticker, 'financials', None), 'Income_Statement', 'Năm'))
                recs.extend(parse_financial_df(symbol, getattr(ticker, 'quarterly_financials', None), 'Income_Statement', 'Quý'))
                recs.extend(parse_financial_df(symbol, getattr(ticker, 'cashflow', None), 'Cash_Flow', 'Năm'))
                recs.extend(parse_financial_df(symbol, getattr(ticker, 'quarterly_cashflow', None), 'Cash_Flow', 'Quý'))
                recs.extend(fetch_market_and_valuation_metrics(symbol, ticker, bs_df))
                recs.extend(fetch_historical_dividends(symbol, ticker))
                break
        except Exception: pass
    return recs

# ==========================================
# 9. HÀM MAIN VÀ LÀM SẠCH DỮ LIỆU BẰNG PANDAS
# ==========================================
def main():
    ticker_market_map = load_176_master_tickers()
    all_master_records = []
    success_count = 0

    # 🆕 BƯỚC 0: TẢI DỮ LIỆU TỪ HUGGING FACE
    print("🚀 BƯỚC 0: Tải dữ liệu hàng ngày từ Hugging Face Dataset...")
    hf_df = load_daily_data_hf()
    if not hf_df.empty:
        standard_cols = ['Mã chứng khoán', 'Tên doanh nghiệp', 'Tên ngành', 'Loại báo cáo', 'Loại kỳ', 'Năm', 'Ngày kỳ', 'Chỉ tiêu tiếng Việt', 'Giá trị']
        if all(col in hf_df.columns for col in standard_cols):
            all_master_records.extend(hf_df.to_dict('records'))
            print(f" ✅ Đã nạp {len(hf_df):,} dòng từ Hugging Face vào Master Records.")
        else:
            print(" ⚠️ Schema của Hugging Face không khớp hoàn toàn với crawler (thiếu cột chuẩn). Sẽ thử map...")
            try:
                if 'Mã chứng khoán' in hf_df.columns and 'Chỉ tiêu tiếng Việt' in hf_df.columns and 'Giá trị' in hf_df.columns:
                    if 'Tên doanh nghiệp' not in hf_df.columns:
                        hf_df['Tên doanh nghiệp'] = hf_df['Mã chứng khoán'].apply(lambda x: get_company_profile(x)[0])
                    if 'Tên ngành' not in hf_df.columns:
                        hf_df['Tên ngành'] = hf_df['Mã chứng khoán'].apply(lambda x: get_company_profile(x)[1])
                    if 'Loại báo cáo' not in hf_df.columns:
                        hf_df['Loại báo cáo'] = 'Chỉ số thị trường, Định giá & Cổ tức'
                    if 'Loại kỳ' not in hf_df.columns:
                        hf_df['Loại kỳ'] = 'Real-time'
                    if 'Năm' not in hf_df.columns:
                        hf_df['Năm'] = str(datetime.now().year)
                    if 'Ngày kỳ' not in hf_df.columns:
                        hf_df['Ngày kỳ'] = datetime.today().strftime('%Y-%m-%d')
                    
                    all_master_records.extend(hf_df[standard_cols].to_dict('records'))
                    print(f" ✅ Đã map và nạp {len(hf_df):,} dòng từ Hugging Face.")
                else:
                    print(" ❌ Không thể tự động map schema Hugging Face. Bỏ qua.")
            except Exception as e:
                print(f" ❌ Lỗi khi map schema Hugging Face: {e}")

    print("\n🚀 BƯỚC 1: Tải dữ liệu BCTC từ vnfinancialdata (HSX & HNX)...")
    vnf_recs = fetch_vnfinancialdata_bulk(ticker_market_map)
    if vnf_recs:
        all_master_records.extend(vnf_recs)
        print(f" ✅ Đã lấy {len(vnf_recs):,} dòng sạch từ vnfinancialdata.")
    
    print("\n📈 BƯỚC 2: Cào chỉ số vĩ mô và dữ liệu bổ sung...")
    index_recs = fetch_market_indices()
    if index_recs: all_master_records.extend(index_recs)

    total_tickers = len(ticker_market_map)
    print(f"\n🔄 BƯỚC 3: Cào Yfinance (max_workers=5)...")
    
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = {executor.submit(process_single_ticker, symbol, cat): symbol for symbol, cat in ticker_market_map.items()}
        for future in as_completed(futures):
            symbol = futures[future]
            try:
                res = future.result()
                if res:
                    all_master_records.extend(res)
                    success_count += 1
                    if success_count % 20 == 0:
                        print(f"  [{success_count}/{total_tickers}] Đã xử lý Yfinance: {symbol}")
            except Exception as e:
                pass

    print(f"\n🐢 BƯỚC 4: Kiểm tra & Quét bù Vnstock/VPS/VNDirect/TCBS cho các mã khuyết thiếu dữ liệu...")
    
    df_temp = pd.DataFrame(all_master_records)
    
    existing_symbols = set(df_temp['Mã chứng khoán'].unique()) if not df_temp.empty else set()
    completely_missing = [s for s in ticker_market_map.keys() if s not in existing_symbols]
    
    symbols_with_price = set()
    if not df_temp.empty:
        prices = df_temp[(df_temp['Chỉ tiêu tiếng Việt'] == 'Giá cổ phiếu hiện tại') & (df_temp['Giá trị'].astype(float) > 0)]
        symbols_with_price = set(prices['Mã chứng khoán'].unique())
        
    missing_symbols = list(set([s for s in ticker_market_map.keys() if s not in symbols_with_price] + completely_missing))
    print(f" -> Có {len(missing_symbols)} mã cần bổ sung (thiếu giá hoặc thiếu hoàn toàn data).")
    
    for idx, symbol in enumerate(missing_symbols):
        res = fetch_vnstock_financials(symbol)
        if res:
            all_master_records.extend(res)
            print(f"  [{idx+1}/{len(missing_symbols)}] Đã bù dữ liệu: {symbol}")

    print("\n🧹 BƯỚC 5: Làm sạch dữ liệu và định dạng số...")
    df_master = pd.DataFrame(all_master_records)
    
    if not df_master.empty:
        df_master = df_master.dropna(subset=['Mã chứng khoán', 'Chỉ tiêu tiếng Việt', 'Giá trị'])
        df_master['Chỉ tiêu tiếng Việt'] = df_master['Chỉ tiêu tiếng Việt'].apply(clean_text)
        
        df_master['Giá trị'] = pd.to_numeric(df_master['Giá trị'], errors='coerce')
        df_valid = df_master[df_master['Giá trị'].notna() & (df_master['Giá trị'] != 0)].copy()
        
        df_valid = df_valid.drop_duplicates(subset=['Mã chứng khoán', 'Loại báo cáo', 'Loại kỳ', 'Ngày kỳ', 'Chỉ tiêu tiếng Việt'], keep='first')
        
        df_valid['Giá trị'] = df_valid['Giá trị'].apply(final_format_for_csv)
        
        standard_cols = ['Mã chứng khoán', 'Tên doanh nghiệp', 'Tên ngành', 'Loại báo cáo', 'Loại kỳ', 'Năm', 'Ngày kỳ', 'Chỉ tiêu tiếng Việt', 'Giá trị']
        df_master = df_valid[standard_cols]
        df_master = df_master.sort_values(by=['Tên ngành', 'Mã chứng khoán', 'Loại báo cáo', 'Loại kỳ', 'Ngày kỳ'], ascending=[True, True, True, False, False])

    os.makedirs('data', exist_ok=True)
    csv_path = 'data/vietnam_stock_database_tong_hop.csv'
    df_master.to_csv(csv_path, index=False, encoding='utf-8-sig')
    
    # BÁO CÁO KIỂM TRA CHI TIẾT
    df_check = pd.read_csv(csv_path)
    prices = df_check[df_check['Chỉ tiêu tiếng Việt'] == 'Giá cổ phiếu hiện tại']
    shares = df_check[df_check['Chỉ tiêu tiếng Việt'] == 'Tổng số lượng cổ phiếu lưu hành']
    valid_p = set(prices[prices['Giá trị'].astype(float) > 0]['Mã chứng khoán'].unique())
    valid_s = set(shares[shares['Giá trị'].astype(float) > 0]['Mã chứng khoán'].unique())
    both = valid_p.intersection(valid_s)
    
    unique_tickers_in_csv = df_check['Mã chứng khoán'].nunique()
    
    # Tìm danh sách các mã vẫn còn thiếu (nếu có) để in ra log Github
    all_targets = set(ticker_market_map.keys())
    still_missing_both = list(all_targets - both)
    
    print(f"==================================================")
    print(f" 🎉 HOÀN TẤT! Tổng số dòng: {len(df_master):,}")
    print(f" - Kích thước file: {os.path.getsize(csv_path) / (1024 * 1024):.2f} MB")
    print(f" - Số mã có dữ liệu: {unique_tickers_in_csv}/176 mã")
    print(f"--------------------------------------------------")
    print(f" 🔍 KIỂM TRA CHẤT LƯỢNG GIÁ & SLCP:")
    print(f" - Mã có Giá (>0): {len(valid_p)}/176 mã")
    print(f" - Mã có SLCP (>0): {len(valid_s)}/176 mã")
    print(f" - Mã có CẢ 2: {len(both)}/176 mã")
    
    if still_missing_both:
        print(f" ⚠️ CÁC MÃ VẪN THIẾU CẢ 2 CHỈ SỐ: {', '.join(still_missing_both)}")
    else:
        print(f" ✅ TUYỆT VỜI! ĐÃ LẤY ĐƯỢC 100% GIÁ VÀ SLCP CỦA 242 MÃ.")
    print(f"==================================================")

if __name__ == "__main__":
    main()
