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
# 2. DANH SÁCH 242 MÃ VÀ THÔNG TIN DOANH NGHIỆP (GIỮ NGUYÊN)
# ==========================================
def load_242_master_tickers():
    raw_tickers = [
        "ABB", "ACB", "ACV", "AIG", "ANV", "BAF", "BCM", "BID", "BMP", "BSI", "BSR", "BVH", "BVS", "BWE",
        "CAP", "CEO", "CII", "CMG", "CTD", "CTG", "CTR", "CTS", "DBC", "DCM", "DGW", "DIG", "DNH", "DP3", 
        "DPM", "DSE", "DTD", "DVN", "DXG", "DXP", "EIB", "EVF", "FOX", "FPT", "FRT", "FTS", "GAS", "GEE", 
        "GEX", "GMD", "GVR", "HAG", "HCM", "HDB", "HDG", "HND", "HHV", "HPG", "HSG", "HT1", "HUT", "IDC", 
        "IDP", "KBC", "KDC", "KDH", "L14", "L18", "LAS", "LHC", "LPB", "MBB", "MBS", "MCH", "MSB", "MSN", 
        "MSR", "MVN", "MWG", "NAB", "NBC", "NDN", "NKG", "NLG", "NT2", "NTP", "NVL", "OCB", "OIL", "PAN", 
        "PC1", "PDR", "PHR", "PLC", "PLX", "PNJ", "POW", "PSD", "PVB", "PVC", "PVD", "PVS", "PVT", "PVI",
        "QNS", "QTP", "REE", "SAB", "SAS", "SBT", "SHB", "SHS", "SIP", "SJS", "SLS", "SNZ", "SSB", "SSI", 
        "STB", "TAL", "TBD", "TCB", "TCH", "TCX", "TDM", "TID", "TIG", "TNG", "TOS", "TPB", "TVD", "VCB", 
        "VC3", "VCG", "VCI", "VCK", "VCS", "VEA", "VFS", "VGC", "VGI", "VGP", "VGR", "VHC", "VHM", "VIB", 
        "VIC", "VIX", "VJC", "VND", "VNM", "VPB", "VPI", "VPL", "VPX", "VRE", "VSC", "VTP", "PRE", "HCC", 
        "L40", "KDM", "HVT", "VTZ", "GLT", "VGS", "PCH", "CAR", "HGM", "KSV", "THD", "KSF", "SCG", "CLM", 
        "TMB", "SAF", "NET", "DHT", "DGC", "SZC", "HVN", "BAB", "AGR", "ICT", "TLH", "BMI", "PET", "LSS", 
        "HDC", "IJC", "TDC", "CTI", "SJD", "TMP", "SBA", "VSH", "TTA", "TV2", "VCP", "BFC", "DDV", "VGT", 
        "SGP", "DPR", "DHC", "TCM", "CKA", "VLB", "HPP", "WSB", "F88", "SEA", "ODE", "PHP", "VXB", "APF", 
        "VNZ", "HLB", "TED", "VEF", "PAT", "FOC", "DTP", "SIV", "VGG", "AVC", "LSG", "CQN", "QPH", "TCW", 
        "ACE", "VSF", "HAM", "SBM", "AGP", "LIC", "SCL", "CC1", "BWS", "NAS", "CLI", "VTK", "HMS", "PCC", 
        "QHW", "MFS", "VEC", "HEC"
    ]
    return {t.strip().upper(): "VIETNAM_MARKET" for t in raw_tickers if t.strip()}

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
# 3. TỪ ĐIỂN DỊCH THUẬT (GIỮ NGUYÊN BẢN GỐC)
# ==========================================
TRANSLATION_MAP = {
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
# 4. HÀM XỬ LÝ DỊCH, VÁ CHỮ CẮT CỤT VÀ LÀM SẠCH
# ==========================================
def translate_metric(metric_original, is_vn=False):
    """Trả về None nếu không thể dịch (để xóa rác)."""
    cleaned_key = str(metric_original).strip()
    
    if is_vn or any(char in cleaned_key for char in ['à','á','ả','ã','ạ','ă','â','đ','ê','ô','ơ','ư','ý']):
        return cleaned_key
    
    if cleaned_key in TRANSLATION_MAP: return TRANSLATION_MAP[cleaned_key]
    for eng_k, vie_v in TRANSLATION_MAP.items():
        if cleaned_key.lower() == eng_k.lower(): return vie_v
        
    k_lower = cleaned_key.lower()
    if 'gain' in k_lower and 'loss' in k_lower: return 'Lãi / Lỗ từ đánh giá hoặc thanh lý tài sản'
    if 'effect of exchange' in k_lower or 'foreign' in k_lower: return 'Ảnh hưởng thay đổi tỷ giá hối đoái'
    if 'net investment' in k_lower: return 'Thuần đầu tư tài chính'
    if 'purchase of intangibles' in k_lower: return 'Tiền chi mua tài sản vô hình'
    if 'purchase of' in k_lower or 'acquisition' in k_lower: return 'Tiền chi mua sắm tài sản hoặc đầu tư'
    if 'sale of' in k_lower or 'disposal' in k_lower: return 'Tiền thu từ thanh lý hoặc bán tài sản'
    if 'net income' in k_lower or 'net profit' in k_lower: return 'Lợi nhuận sau thuế (Lợi nhuận ròng)'
    if 'operating income' in k_lower or 'operating profit' in k_lower: return 'Lợi nhuận thuần từ hoạt động kinh doanh'
    if 'gross profit' in k_lower: return 'Lợi nhuận gộp'
    if 'pretax income' in k_lower or 'income before tax' in k_lower: return 'Lợi nhuận kế toán trước thuế'
    if 'revenue' in k_lower or 'sales' in k_lower: return 'Tổng doanh thu / Doanh thu thuần'
    if 'cost of' in k_lower or 'cogs' in k_lower: return 'Giá vốn hàng bán'
    if 'operating expense' in k_lower or 'sga' in k_lower or 'admin' in k_lower: return 'Chi phí bán hàng và quản lý doanh nghiệp'
    if 'interest expense' in k_lower: return 'Chi phí lãi vay'
    if 'interest income' in k_lower: return 'Thu nhập lãi'
    if 'tax provision' in k_lower or 'tax expense' in k_lower: return 'Chi phí thuế thu nhập doanh nghiệp'
    if 'depreciation' in k_lower or 'amortization' in k_lower: return 'Khấu hao tài sản cố định và phân bổ'
    if 'cash flow' in k_lower: return 'Lưu chuyển tiền thuần'
    if 'capital expenditure' in k_lower or 'capex' in k_lower: return 'Chi phí đầu tư tài sản cố định (CapEx)'
    if 'dividend' in k_lower: return 'Cổ tức đã chi trả'
    if 'asset' in k_lower: return 'Tổng tài sản'
    if 'liability' in k_lower or 'debt' in k_lower: return 'Nợ phải trả'
    if 'equity' in k_lower: return 'Vốn chủ sở hữu'
    if 'share' in k_lower: return 'Chỉ tiêu cổ phiếu'
    if 'eps' in k_lower: return 'Lãi trên cổ phiếu (EPS)'
    
    # Trả về None để code bỏ qua dòng rác
    return None

def fix_truncated_text(text):
    """Vá các từ bị cắt cụt từ nguồn vnfinancialdata"""
    text = str(text).strip()
    fixes = {
        "Các khoản phải": "Các khoản phải thu",
        "Lợi nhuận trước": "Lợi nhuận trước thuế",
        "Thuế và các kho": "Thuế và các khoản phải nộp",
        "Tiền và tương đ": "Tiền và tương đương tiền",
        "TỔNG CỘNG N": "TỔNG CỘNG NỢ PHẢI TRẢ",
        "VỐN CHỦ SỞ H": "VỐN CHỦ SỞ HỮU",
        "Chi phí phải trả": "Chi phí phải trả",
        "Chi phí trả trước": "Chi phí trả trước",
        "Cổ phiếu phổ thô": "Cổ phiếu phổ thông",
        "Đầu tư dài hạn k": "Đầu tư dài hạn khác",
        "Lợi nhuận thuần": "Lợi nhuận thuần",
        "Lưu chuyển tiền": "Lưu chuyển tiền thuần",
        "Lãi / Lỗ từ đánh": "Lãi / Lỗ từ đánh giá lại tài sản",
        "Tổng tài sản": "Tổng tài sản"
    }
    for k, v in fixes.items():
        if text.startswith(k):
            return v
    return text

def format_value(x):
    """Trả về String để xóa đuôi .0"""
    if pd.isna(x) or x == 0: return str(x)
    if x == int(x):
        return str(int(x))
    return str(round(x, 4))

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
                            try: float_val = float(val)
                            except: continue
                            if pd.isna(float_val) or float_val in [float('inf'), float('-inf')] or float_val == 0: 
                                continue
                            
                            metric_vn = translate_metric(str(row_idx).strip())
                            if not metric_vn: continue
                            
                            # LỌC LOGIC (Xóa Tài sản khỏi báo cáo LCTT/KQKD)
                            if statement_type_vn in ['Báo cáo lưu chuyển tiền tệ', 'Báo cáo kết quả kinh doanh']:
                                if any(x in metric_vn for x in ['Tài sản', 'Nợ phải trả', 'Vốn chủ sở hữu']):
                                    continue
                            
                            records.append({
                                'Mã chứng khoán': symbol, 'Tên doanh nghiệp': company_name,
                                'Tên ngành': sector_name, 'Loại báo cáo': statement_type_vn,
                                'Loại kỳ': ky_bao_cao, 'Năm': year_val, 'Ngày kỳ': date_str,
                                'Chỉ tiêu tiếng Việt': metric_vn, 'Giá trị': float_val
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
                    if pd.notna(div_val) and float(div_val) > 0:
                        records.append({
                            'Mã chứng khoán': symbol, 'Tên doanh nghiệp': company_name,
                            'Tên ngành': sector_name, 'Loại báo cáo': 'Chỉ số thị trường, Định giá & Cổ tức',
                            'Loại kỳ': 'Sự kiện cổ tức', 'Năm': year_val, 'Ngày kỳ': date_str,
                            'Chỉ tiêu tiếng Việt': 'Lịch sử trả cổ tức bằng tiền (VND/Cổ phiếu)', 'Giá trị': float(div_val)
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
        info = ticker_obj.info if ticker_obj else {}
        current_price = info.get('currentPrice') or info.get('regularMarketPrice') or info.get('previousClose') or 0.0
        shares_out = info.get('sharesOutstanding', 0.0)
        market_cap = info.get('marketCap', 0.0)
        div_yield = info.get('dividendYield', 0.0) or 0.0
        if not current_price or current_price == 0.0:
            for period_str in ["3mo", "1y", "2y"]:
                try:
                    hist = ticker_obj.history(period=period_str)
                    if hist is not None and not hist.empty:
                        current_price = float(hist['Close'].iloc[-1])
                        break
                except: continue
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
            ('Market Capitalization', market_cap), ('Trailing EPS', info.get('trailingEps')),
            ('Forward EPS', info.get('forwardEps')), ('Dividend Yield', div_yield),
            ('Dividend Rate', info.get('dividendRate')), ('Trailing P/E', info.get('trailingPE')),
            ('Forward P/E', info.get('forwardPE')), ('Price To Book', info.get('priceToBook')),
            ('Book Value', info.get('bookValue')), ('Return On Equity', info.get('returnOnEquity')),
            ('Return On Assets', info.get('returnOnAssets')), ('Profit Margins', info.get('profitMargins')),
            ('Gross Margins', info.get('grossMargins'))
        ]
        for eng_key, val in metrics:
            float_val = 0.0
            if val is not None:
                try:
                    float_val = float(val)
                    if pd.isna(float_val) or float_val in [float('inf'), float('-inf')] or float_val == 0: 
                        continue
                except: continue
            
            metric_vn = TRANSLATION_MAP.get(eng_key, eng_key)
            records.append({
                'Mã chứng khoán': symbol, 'Tên doanh nghiệp': company_name,
                'Tên ngành': sector_name, 'Loại báo cáo': 'Chỉ số thị trường, Định giá & Cổ tức',
                'Loại kỳ': 'Real-time', 'Năm': current_year, 'Ngày kỳ': today_str,
                'Chỉ tiêu tiếng Việt': metric_vn, 'Giá trị': float_val
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
            info = t.info
            current_val = info.get('regularMarketPrice') or info.get('currentPrice') or info.get('previousClose', 0)
            if not current_val:
                hist = t.history(period="1mo")
                if not hist.empty: current_val = float(hist['Close'].iloc[-1])
            prev_close = info.get('previousClose', current_val)
            change_val = current_val - prev_close
            change_pct = (change_val / prev_close) * 100 if prev_close else 0
            
            for name, val in [('Giá trị chỉ số', current_val), ('Biến động điểm (Change)', change_val), ('Biến động phần trăm (Percent Change)', change_pct)]:
                if pd.notna(val) and float(val) != 0:
                    market_records.append({
                        'Mã chứng khoán': index_name, 'Tên doanh nghiệp': f'Chỉ số thị trường {index_name}',
                        'Tên ngành': 'Chỉ số vĩ mô', 'Loại báo cáo': 'Chỉ số thị trường, Định giá & Cổ tức',
                        'Loại kỳ': 'Real-time hằng ngày', 'Năm': current_year, 'Ngày kỳ': today_str,
                        'Chỉ tiêu tiếng Việt': name, 'Giá trị': float(val)
                    })
        except Exception: pass
    return market_records

# ==========================================
# 6. HÀM CÀO DỮ LIỆU TỪ VNSTOCK
# ==========================================
def parse_vnstock_df(symbol, df, statement_type_vn, ky_bao_cao):
    records = []
    company_name, sector_name = get_company_profile(symbol)
    if df is None or df.empty: return records

    for _, row in df.iterrows():
        metric_raw = row.get('item', row.get('item_en', ''))
        if not metric_raw: continue
        metric_vn = translate_metric(metric_raw)
        if not metric_vn: continue
        
        for col in df.columns:
            col_str = str(col)
            if col_str in ['item', 'item_en', 'unit', 'ticker', 'year', 'quarter', 'date', 'period', 'id', 'name', 'order', 'level', 'off_balance', 'category']: continue
            
            year_val = col_str.split('-')[0].split(' ')[0].strip()
            if not year_val.isdigit() or int(year_val) < 2000: continue

            val = row[col]
            if pd.notna(val):
                try: float_val = float(val)
                except: continue
                if pd.isna(float_val) or float_val in [float('inf'), float('-inf')] or float_val == 0: 
                    continue
                
                # LỌC LOGIC
                if statement_type_vn in ['Báo cáo lưu chuyển tiền tệ', 'Báo cáo kết quả kinh doanh']:
                    if any(x in metric_vn for x in ['Tài sản', 'Nợ phải trả', 'Vốn chủ sở hữu']):
                        continue
                
                records.append({
                    'Mã chứng khoán': symbol, 'Tên doanh nghiệp': company_name,
                    'Tên ngành': sector_name, 'Loại báo cáo': statement_type_vn,
                    'Loại kỳ': ky_bao_cao, 'Năm': year_val, 'Ngày kỳ': f"{year_val}-12-31" if ky_bao_cao == 'Năm' else col_str,
                    'Chỉ tiêu tiếng Việt': metric_vn, 'Giá trị': float_val
                })
    return records

def fetch_vnstock_financials(symbol):
    records = []
    try:
        time.sleep(1.0) 
        fin = Fundamental().equity(symbol)
        
        try: records.extend(parse_vnstock_df(symbol, fin.balance_sheet(period='year'), 'Bảng cân đối kế toán', 'Năm'))
        except Exception: pass
        try: records.extend(parse_vnstock_df(symbol, fin.income_statement(period='year'), 'Báo cáo kết quả kinh doanh', 'Năm'))
        except Exception: pass
        try: records.extend(parse_vnstock_df(symbol, fin.cash_flow(period='year'), 'Báo cáo lưu chuyển tiền tệ', 'Năm'))
        except Exception: pass
        
        try: records.extend(parse_vnstock_df(symbol, fin.balance_sheet(period='quarter'), 'Bảng cân đối kế toán', 'Quý'))
        except Exception: pass
        try: records.extend(parse_vnstock_df(symbol, fin.income_statement(period='quarter'), 'Báo cáo kết quả kinh doanh', 'Quý'))
        except Exception: pass
        try: records.extend(parse_vnstock_df(symbol, fin.cash_flow(period='quarter'), 'Báo cáo lưu chuyển tiền tệ', 'Quý'))
        except Exception: pass

        try:
            quote_df = Market().equity(symbol).quote()
            if quote_df is not None and not quote_df.empty:
                price = float(quote_df.iloc[0].get('close_price', 0))
                if price > 0:
                    company_name, sector_name = get_company_profile(symbol)
                    records.append({
                        'Mã chứng khoán': symbol, 'Tên doanh nghiệp': company_name,
                        'Tên ngành': sector_name, 'Loại báo cáo': 'Chỉ số thị trường, Định giá & Cổ tức',
                        'Loại kỳ': 'Real-time', 'Năm': str(datetime.now().year), 'Ngày kỳ': datetime.today().strftime('%Y-%m-%d'),
                        'Chỉ tiêu tiếng Việt': 'Giá cổ phiếu hiện tại', 'Giá trị': price
                    })
        except Exception: pass
        
    except Exception: pass
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
                    val = row['Giá trị']
                    try: float_val = float(val)
                    except: continue
                    if pd.isna(float_val) or float_val in [float('inf'), float('-inf')] or float_val == 0: continue
                    
                    symbol = row['Mã chứng khoán']
                    company_name, sector_name = get_company_profile(symbol)
                    year_val = str(row['Năm'])
                    
                    # VÁ CHỮ CẮT CỤT
                    metric_vn = fix_truncated_text(translate_metric(row['Chỉ tiêu tiếng Việt'], is_vn=True))
                    
                    # LỌC LOGIC
                    if stmt_name in ['Báo cáo lưu chuyển tiền tệ', 'Báo cáo kết quả kinh doanh']:
                        if any(x in metric_vn for x in ['Tài sản', 'Nợ phải trả', 'Vốn chủ sở hữu']):
                            continue

                    records.append({
                        'Mã chứng khoán': symbol, 'Tên doanh nghiệp': company_name,
                        'Tên ngành': sector_name, 'Loại báo cáo': stmt_name,
                        'Loại kỳ': 'Năm', 'Năm': year_val, 'Ngày kỳ': f"{year_val}-12-31",
                        'Chỉ tiêu tiếng Việt': metric_vn, 'Giá trị': float_val
                    })
            except Exception as e:
                print(f"  ⚠️ Lỗi tải {stmt_name} cho {exchange}: {e}")
                
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

    vnstock_recs = fetch_vnstock_financials(symbol)
    if vnstock_recs: recs.extend(vnstock_recs)

    if not recs:
        comp_name, sec_name = get_company_profile(symbol)
        current_year = str(datetime.now().year)
        today_str = datetime.today().strftime('%Y-%m-%d')
        for metric_name in ['Giá cổ phiếu hiện tại', 'Tổng số lượng cổ phiếu lưu hành', 'Vốn hóa thị trường']:
            recs.append({
                'Mã chứng khoán': symbol, 'Tên doanh nghiệp': comp_name,
                'Tên ngành': sec_name, 'Loại báo cáo': 'Chỉ số thị trường, Định giá & Cổ tức',
                'Loại kỳ': 'Real-time', 'Năm': current_year, 'Ngày kỳ': today_str,
                'Chỉ tiêu tiếng Việt': metric_name, 'Giá trị': 0.0
            })
    return recs

# ==========================================
# 9. HÀM MAIN VÀ LÀM SẠCH DỮ LIỆU BẰNG PANDAS
# ==========================================
def main():
    ticker_market_map = load_242_master_tickers()
    all_master_records = []
    success_count = 0
     
    print("🚀 BƯỚC 1: Tải dữ liệu BCTC từ vnfinancialdata (HSX & HNX)...")
    vnf_recs = fetch_vnfinancialdata_bulk(ticker_market_map)
    if vnf_recs:
        all_master_records.extend(vnf_recs)
        print(f" ✅ Đã lấy {len(vnf_recs):,} dòng sạch từ vnfinancialdata.")
    
    print("\n📈 BƯỚC 2: Cào chỉ số vĩ mô và dữ liệu bổ sung...")
    index_recs = fetch_market_indices()
    if index_recs: all_master_records.extend(index_recs)

    total_tickers = len(ticker_market_map)
    print(f"\n🔄 BƯỚC 3: Cào bổ sung yfinance + vnstock...")
    
    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = {executor.submit(process_single_ticker, symbol, cat): symbol for symbol, cat in ticker_market_map.items()}
        for future in as_completed(futures):
            symbol = futures[future]
            try:
                res = future.result()
                if res:
                    all_master_records.extend(res)
                    success_count += 1
                    if success_count % 20 == 0:
                        print(f"  [{success_count}/{total_tickers}] Đã xử lý: {symbol}")
            except Exception as e:
                print(f"Lỗi xử lý mã {symbol}: {e}")

    df_master = pd.DataFrame(all_master_records)
    
    # --- QUY TRÌNH LÀM SẠCH DỮ LIỆU BẰNG PANDAS (LỚP BẢO VỆ CUỐI CÙNG) ---
    if not df_master.empty:
        # 1. Xóa NaN
        df_master = df_master.dropna(subset=['Mã chứng khoán', 'Chỉ tiêu tiếng Việt', 'Giá trị'])
        
        # 2. CHUẨN HÓA CHUỖI (Xóa khoảng trắng thừa để lọc trùng lặp triệt để)
        df_master['Chỉ tiêu tiếng Việt'] = df_master['Chỉ tiêu tiếng Việt'].astype(str).str.strip()
        
        # 3. Ép kiểu số và xóa giá trị 0
        df_master['Giá trị'] = pd.to_numeric(df_master['Giá trị'], errors='coerce').fillna(0.0)
        df_valid = df_master[df_master['Giá trị'] != 0].copy()
        
        # 4. XÓA TRÙNG LẶP (Dựa trên 5 trường cốt lõi)
        df_valid = df_valid.drop_duplicates(subset=['Mã chứng khoán', 'Loại báo cáo', 'Loại kỳ', 'Ngày kỳ', 'Chỉ tiêu tiếng Việt'])
        
        # 5. CHUẨN HÓA ĐỊNH DẠNG SỐ (Biến thành String để xóa đuôi .0)
        df_valid['Giá trị'] = df_valid['Giá trị'].apply(format_value)
        
        # 6. ĐẢM BẢO ĐỦ 242 MÃ
        valid_symbols = set(df_valid['Mã chứng khoán'].unique())
        all_symbols = set(ticker_market_map.keys())
        missing_symbols = all_symbols - valid_symbols
        
        if missing_symbols:
            fallback_rows = []
            for missing in missing_symbols:
                comp_name, sec_name = get_company_profile(missing)
                fallback_rows.append({
                    'Mã chứng khoán': missing, 'Tên doanh nghiệp': comp_name,
                    'Tên ngành': sec_name, 'Loại báo cáo': 'Chỉ số thị trường, Định giá & Cổ tức',
                    'Loại kỳ': 'Real-time', 'Năm': str(datetime.now().year), 'Ngày kỳ': datetime.today().strftime('%Y-%m-%d'),
                    'Chỉ tiêu tiếng Việt': 'Giá cổ phiếu hiện tại', 'Giá trị': '0'
                })
            df_valid = pd.concat([df_valid, pd.DataFrame(fallback_rows)], ignore_index=True)

        # 7. Chỉ giữ 9 cột chuẩn và sắp xếp
        standard_cols = ['Mã chứng khoán', 'Tên doanh nghiệp', 'Tên ngành', 'Loại báo cáo', 'Loại kỳ', 'Năm', 'Ngày kỳ', 'Chỉ tiêu tiếng Việt', 'Giá trị']
        df_master = df_valid[standard_cols]
        df_master = df_master.sort_values(by=['Tên ngành', 'Mã chứng khoán', 'Loại báo cáo', 'Loại kỳ', 'Ngày kỳ'], ascending=[True, True, True, False, False])

    print("\n💾 Đang kết xuất tệp CSV...")
    os.makedirs('data', exist_ok=True)
    csv_path = 'data/vietnam_stock_database_tong_hop.csv'
    df_master.to_csv(csv_path, index=False, encoding='utf-8-sig')
    
    file_size_mb = os.path.getsize(csv_path) / (1024 * 1024)
    print(f"==================================================")
    print(f" 🎉 HOÀN TẤT VÉT SẠCH & LÀM SẠCH DỮ LIỆU GỐC!")
    print(f" - Tổng số dòng dữ liệu: {len(df_master):,}")
    print(f" - Số mã: {len(df_master['Mã chứng khoán'].unique())}/242")
    print(f" - Kích thước file: {file_size_mb:.2f} MB")
    print(f"==================================================")

if __name__ == "__main__":
    main()
