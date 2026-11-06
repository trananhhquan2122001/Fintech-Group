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
    import yfinance as yf
except ImportError:
    print("⚙️ Đang cài đặt thư viện yfinance...")
    os.system("pip install yfinance --quiet")
    import yfinance as yf

try:
    from vnstock import Fundamental, Market, Reference
except ImportError:
    print("⚙️ Đang cài đặt thư viện vnstock (v5)...")
    os.system("pip install -U --extra-index-url https://vnstocks.com/api/packages vnstock --quiet")
    from vnstock import Fundamental, Market, Reference

session = requests.Session()
session.headers.update({
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
    'Accept-Language': 'en-US,en;q=0.9,vi;q=0.8'
})

# ==========================================
# 2. DANH SÁCH 242 MÃ VÀ THÔNG TIN DOANH NGHIỆP
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
        "CKA": "Công ty CP Xuất nhập khẩu Thủy sản Cà Mau", "VLB": "Công ty CP Xây dựng và Sản xuất Vật liệu Xây dựng Biên Hòa",
        "HPP": "Công ty CP Sơn Hải Phòng", "WSB": "Công ty CP Bia Sài Gòn - Miền Tây", "F88": "Công ty CP Đầu tư Kinh doanh F88",
        "SEA": "Tổng Công ty Thủy sản Việt Nam - CTCP", "ODE": "Công ty CP Dịch vụ Dầu khí Biển", "PHP": "Công ty CP Cảng Hải Phòng",
        "VXB": "Công ty CP Vật liệu Xây dựng Bến Tre", "APF": "Công ty CP Nông sản Thực phẩm Quảng Ngãi", "VNZ": "Công ty CP VNG",
        "HLB": "Công ty CP Hữu Liên", "TED": "Công ty CP Xây dựng và Công nghệ Tiến Đạt", "VEF": "Công ty CP Trung tâm Hội chợ Triển lãm Việt Nam",
        "PAT": "Công ty CP Phốt pho Apatit Việt Nam", "FOC": "Công ty CP Dịch vụ Trực tuyến FPT", "DTP": "Công ty CP Dược phẩm CPC1 Hà Nội",
        "SIV": "Công ty CP SIVICO", "VGG": "Công ty CP May Vĩnh Phú", "AVC": "Công ty CP Thủy điện A Vương",
        "LSG": "Công ty CP Mía đường Lam Sơn", "CQN": "Công ty CP Cảng Quảng Ninh", "QPH": "Công ty CP Quảng Ninh",
        "TCW": "Công ty CP Kho vận Tân Cảng", "ACE": "Công ty CP Bê tông Hà Thanh", "VSF": "Công ty CP Giống cây trồng Trung ương",
        "HAM": "Công ty CP Vật tư Hà Nội", "SBM": "Công ty CP Đầu tư Phát triển Bắc Minh", "AGP": "Công ty CP Dược phẩm Agimexpharm",
        "LIC": "Công ty CP Sản xuất Kinh doanh Xuất nhập khẩu Lam Sơn", "SCL": "Công ty CP Sứ Cao Lãnh", "CC1": "Tổng Công ty Xây dựng số 1 - CTCP",
        "BWS": "Công ty CP Bia Sài Gòn - Sông Lam", "NAS": "Công ty CP Phân bón Hà Bắc", "CLI": "Công ty CP XNK & Xây dựng Giao thông",
        "VTK": "Công ty CP Tư vấn và Dịch vụ Viettel", "HMS": "Công ty CP Cơ khí Hà Nội", "PCC": "Công ty CP Tập đoàn Xây dựng PCC1",
        "QHW": "Công ty CP Nước Khoáng Quảng Ninh", "MFS": "Công ty CP Dịch vụ Kỹ thuật Mobifone", "VEC": "Tổng Công ty Cổ phần Điện tử và Tin học Việt Nam",
        "HEC": "Công ty CP Tư vấn Xây dựng Thủy lợi và Môi trường",
        "DGC": "Công ty Cổ phần Tập đoàn Hóa chất Đức Giang", "SZC": "Công ty Cổ phần Sonadezi Châu Đức",
        "HVN": "Tổng Công ty Hàng không Việt Nam - CTCP (Vietnam Airlines)", "BAB": "Ngân hàng TMCP Bắc Á",
        "AGR": "Công ty Cổ phần Chứng khoán Agribank", "ICT": "Công ty Cổ phần Viễn thông - Giống cây trồng",
        "TLH": "Công ty Cổ phần Tập đoàn Thép Tiến Lên", "BMI": "Tổng Công ty Cổ phần Bảo hiểm Bảo Minh",
        "PET": "Tổng Công ty cổ phần Dịch vụ Tổng hợp Dầu khí", "LSS": "Công ty Cổ phần Mía đường Lam Sơn",
        "HDC": "Công ty Cổ phần Phát triển Nhà Bà Rịa - Vũng Tàu", "IJC": "Công ty Cổ phần Phát triển Hạ tầng Kỹ thuật",
        "TDC": "Công ty Cổ phần Kinh doanh và Phát triển Bình Dương", "CTI": "Công ty Cổ phần Đầu tư Phát triển C&T",
        "SJD": "Công ty Cổ phần Thủy điện Cần Đơn", "TMP": "Công ty Cổ phần Thủy điện Thác Mơ",
        "SBA": "Công ty Cổ phần Thủy điện Sông Ba Hạ", "VSH": "Công ty Cổ phần Thủy điện Vĩnh Sơn - Sông Hinh",
        "TTA": "Công ty Cổ phần Đầu tư Trường Thành Việt Nam", "TV2": "Công ty Cổ phần Tư vấn Xây dựng Điện 2",
        "VCP": "Công ty Cổ phần Xây dựng điện VNECO 3", "BFC": "Công ty Cổ phần Phân bón Bình Điền",
        "DDV": "Công ty Cổ phần DAP - VINACHEM", "VGT": "Tập đoàn Dệt May Việt Nam - CTCP",
        "SGP": "Tổng Công ty Cảng Sài Gòn - CTCP", "DPR": "Công ty Cổ phần Cao su Đồng Phú",
        "DHC": "Công ty Cổ phần Đông Hải Bến Tre", "TCM": "Công ty Cổ phần Dệt mão Thành Công",
        "ABB": "Ngân hàng TMCP An Bình", "ACB": "Ngân hàng TMCP Á Châu", "ACV": "Tổng công ty Cảng hàng không Việt Nam",
        "AIG": "Công ty Cổ phần Tập đoàn Hóa chất Hùng Phát", "ANV": "Công ty Cổ phần Nam Việt", "BAF": "Công ty Cổ phần Nông nghiệp BAF Việt Nam",
        "BCM": "Tổng công ty Đầu tư và Phát triển Công nghiệp - CTCP", "BID": "Ngân hàng TMCP Đầu tư và Phát triển Việt Nam",
        "BMP": "Công ty Cổ phần Nhựa Bình Minh", "BSI": "Công ty Cổ phần Chứng khoán Ngân hàng Đầu tư và Phát triển Việt Nam",
        "BSR": "Công ty Cổ phần Lọc hóa dầu Bình Sơn", "BVH": "Tập đoàn Bảo Việt", "BVS": "Công ty Cổ phần Chứng khoán Bảo Việt",
        "BWE": "Công ty Cổ phần Nước - Môi trường Bình Dương", "CAP": "Công ty Cổ phần Lâm nông sản thực phẩm Yên Bái",
        "CEO": "Công ty Cổ phần Tập đoàn C.E.O", "CII": "Công ty Cổ phần Đầu tư Hạ tầng Kỹ thuật Thành phố Hồ Chí Minh",
        "CMG": "Công ty Cổ phần Tập đoàn Công nghệ CMC", "CTD": "Công ty Cổ phần Xây dựng Coteccons",
        "CTG": "Ngân hàng TMCP Công Thương Việt Nam", "CTR": "Tổng Công ty Cổ phần Công trình Viettel",
        "CTS": "Công ty Cổ phần Chứng khoán Ngân hàng Công Thương Việt Nam", "DBC": "Công ty Cổ phần Tập đoàn Dabaco Việt Nam",
        "DCM": "Công ty Cổ phần Phân bón Dầu khí Cà Mau", "DGW": "Công ty Cổ phần Thế giới Số", "DIG": "Tổng công ty Cổ phần Đầu tư Phát triển Xây dựng",
        "DNH": "Công ty Cổ phần Thủy điện Đa Nhim - Hàm Thuận - Đa Mi", "DP3": "Công ty Cổ phần Dược phẩm Trung ương 3",
        "DPM": "Tổng công ty Phân bón và Hóa chất Dầu khí - CTCP", "DSE": "Công ty Cổ phần Chứng khoán DNSE",
        "DTD": "Công ty Cổ phần Đầu tư Phát triển Thành Đạt", "DVN": "Tổng Công ty Dược Việt Nam - CTCP",
        "DXG": "Công ty Cổ phần Tập đoàn Đất Xanh", "DXP": "Công ty Cổ phần Cảng Đình Vũ", "EIB": "Ngân hàng TMCP Xuất Nhập khẩu Việt Nam",
        "EVF": "Công ty Cổ phần Tài chính Điện lực", "FOX": "Công ty Cổ phần Viễn thông FPT", "FPT": "Công ty Cổ phần FPT",
        "FRT": "Công ty Cổ phần Bán lẻ Kỹ thuật Số FPT", "FTS": "Công ty Cổ phần Chứng khoán FPT", "GAS": "Tổng Công ty Khí Việt Nam - CTCP",
        "GEE": "Công ty Cổ phần Thiết bị Điện Gelex", "GEX": "Công ty Cổ phần Tập đoàn Gelex", "GMD": "Công ty Cổ phần Gemadept",
        "GVR": "Tập đoàn Công nghiệp Cao su Việt Nam - CTCP", "HAG": "Công ty Cổ phần Hoàng Anh Gia Lai", "HCM": "Công ty Cổ phần Chứng khoán Thành phố Hồ Chí Minh",
        "HDB": "Ngân hàng TMCP Phát triển Thành phố Hồ Chí Minh", "HDG": "Công ty Cổ phần Tập đoàn Hà Đô", "HND": "Công ty Cổ phần Nhiệt điện Hải Phòng",
        "HHV": "Công ty Cổ phần Đầu tư Hạ tầng giao thông Đèo Cả", "HPG": "Công ty Cổ phần Tập đoàn Hòa Phát",
        "HSG": "Công ty Cổ phần Tập đoàn Hoa Sen", "HT1": "Công ty Cổ phần Xi măng Vicem Hà Tiên", "HUT": "Công ty Cổ phần Tasco",
        "IDC": "Tổng công ty IDICO - CTCP", "IDP": "Công ty Cổ phần Sữa Quốc tế IDP", "KBC": "Tổng Công ty Phát triển Đô thị Kinh Bắc - CTCP",
        "KDC": "Công ty Cổ phần Tập đoàn Kido", "KDH": "Công ty Cổ phần Đầu tư và Kinh doanh Nhà Khang Điền", "L14": "Công ty Cổ phần Licogi 14",
        "L18": "Công ty Cổ phần Đầu tư và Xây dựng số 18", "LAS": "Công ty Cổ phần Supe Phốt phát và Hóa chất Lâm Thao",
        "LHC": "Công ty Cổ phần Đầu tư và Xây dựng Lắp máy IDICO", "LPB": "Ngân hàng TMCP Lộc Phát Việt Nam",
        "MBB": "Ngân hàng TMCP Quân đội", "MBS": "Công ty Cổ phần Chứng khoán MB", "MCH": "Công ty Cổ phần Hàng tiêu dùng Masan",
        "MSB": "Ngân hàng TMCP Hàng Hải Việt Nam", "MSN": "Công ty Cổ phần Tập đoàn Masan", "MSR": "Công ty Cổ phần Masan High-Tech Materials",
        "MVN": "Tổng Công ty Hàng hải Việt Nam - CTCP", "MWG": "Công ty Cổ phần Đầu tư Thế Giới Di Động", "NAB": "Ngân hàng TMCP Nam Á",
        "NBC": "Công ty Cổ phần Than Núi Béo - Vinacomin", "NDN": "Công ty Cổ phần Đầu tư Phát triển Nhà Đà Nẵng",
        "NKG": "Công ty Cổ phần Thép Nam Kim", "NLG": "Công ty Cổ phần Đầu tư Nam Long", "NT2": "Công ty Cổ phần Điện lực Dầu khí Nhơn Trạch 2",
        "NTP": "Công ty Cổ phần Nhựa Thiếu niên Tiền Phong", "NVL": "Công ty Cổ phần Tập đoàn Đầu tư Địa đạo No Va (Novaland)",
        "OCB": "Ngân hàng TMCP Phương Đông", "OIL": "Tổng Công ty Dầu Việt Nam - CTCP", "PAN": "Công ty Cổ phần Tập đoàn PAN",
        "PC1": "Công ty Cổ phần Tập đoàn PC1", "PDR": "Công ty Cổ phần Phát triển Bất động sản Phát Đạt",
        "PHR": "Công ty Cổ phần Cao su Phước Hòa", "PLC": "Tổng Công ty Hóa dầu Petrolimex - CTCP", "PLX": "Tập đoàn Xăng dầu Việt Nam",
        "PNJ": "Công ty Cổ phần Vàng bạc Đá quý Phú Nhuận", "POW": "Tổng Công ty Điện lực Dầu khí Việt Nam - CTCP",
        "PSD": "Công ty Cổ phần Dịch vụ Tổng hợp Dầu khí", "PVB": "Công ty Cổ phần bọc ống Dầu khí Việt Nam",
        "PVC": "Tổng Công ty Hóa chất và Dung dịch Khoan Dầu khí - CTCP", "PVD": "Tổng Công ty Cổ phần Khoan và Dịch vụ Khoan Dầu khí",
        "PVS": "Tổng công ty Cổ phần Dịch vụ Kỹ thuật Dầu khí Việt Nam", "PVT": "Tổng Công ty Cổ phần Vận tải Dầu khí",
        "PVI": "Công ty Cổ phần PVI", "QNS": "Công ty Cổ phần Đường Quảng Ngãi", "QTP": "Công ty Cổ phần Nhiệt điện Quảng Ninh",
        "REE": "Công ty Cổ phần Cơ Điện Lạnh", "SAB": "Tổng công ty CP Bia - Rượu - Nước giải khát Sài Gòn",
        "SAS": "Công ty Cổ phần Dịch vụ Hàng không Sân bay Tân Sơn Nhất", "SBT": "Công ty Cổ phần Thành Thành Công - Biên Hòa",
        "SHB": "Ngân hàng TMCP Sài Gòn - Hà Nội", "SHS": "Công ty Cổ phần Chứng khoán Sài Gòn - Hà Nội",
        "SIP": "Công ty Cổ phần Đầu tư Sài Gòn VRG", "SJS": "Công ty Cổ phần Đầu tư Phát triển Đô thị và Khu công nghiệp Sông Đà",
        "SLS": "Công ty Cổ phần Mía đường Sơn La", "SNZ": "Tổng Công ty Sonadezi - CTCP", "SSB": "Ngân hàng TMCP Đông Nam Á",
        "SSI": "Công ty Cổ phần Chứng khoán SSI", "STB": "Ngân hàng TMCP Sài Gòn Thương Tín", "TAL": "Công ty Cổ phần Đầu tư Bất động sản Taseco",
        "TBD": "Công ty Cổ phần Chế tạo Thiết bị Điện Đông Anh", "TCB": "Ngân hàng TMCP Kỹ Thương Việt Nam",
        "TCH": "Công ty Cổ phần Đầu tư Dịch vụ Tài chính Hoàng Huy", "TCX": "Công ty Cổ phần Công nghiệp Tàu thủy",
        "TDM": "Công ty Cổ phần Nước Thủ Dầu Một", "TID": "Tổng Công ty Đầu tư Phát triển Hạ tầng Urban", "TIG": "Công ty Cổ phần Tập đoàn Đầu tư Thăng Long",
        "TNG": "Công ty Cổ phần Đầu tư và Thương mại TNG", "TOS": "Công ty Cổ phần Dịch vụ biển Tân Cảng", "TPB": "Ngân hàng TMCP Tiên Phong",
        "TVD": "Công ty Cổ phần Than Vàng Danh - Vinacomin", "VCB": "Ngân hàng TMCP Ngoại thương Việt Nam", "VC3": "Công ty Cổ phần Tập đoàn Nam Cường",
        "VCG": "Tổng công ty Cổ phần Xuất nhập khẩu và Xây dựng Việt Nam", "VCI": "Công ty Cổ phần Chứng khoán Vietcap",
        "VCK": "Công ty Cổ phần Chứng khoán Vina", "VCS": "Công ty Cổ phần Vicosstone", "VEA": "Tổng công ty Máy động lực và máy nông nghiệp Việt Nam - CTCP",
        "VFS": "Công ty Cổ phần Chứng khoất Nhất Việt", "VGC": "Tổng Công ty Viglacera - CTCP", "VGI": "Tổng Công ty Cổ phần Đầu tư Quốc tế Viettel",
        "VGP": "Công ty Cổ phần Cảng Cần Giuộc", "VGR": "Công ty Cổ phần Vận tải và Xếp dỡ Hải An", "VHC": "Công ty Cổ phần Vĩnh Hoàn",
        "VHM": "Công ty Cổ phần Vinhomes", "VIB": "Ngân hàng TMCP Quốc tế Việt Nam", "VIC": "Tập đoàn Vingroup - CTCP",
        "VIX": "Công ty Cổ phần Chứng khoán VIX", "VJC": "Công ty Cổ phần Hàng không VietJet", "VND": "Công ty Cổ phần Chứng khoán VNDIRECT",
        "VNM": "Công ty Cổ phần Sữa Việt Nam", "VPB": "Ngân hàng TMCP Việt Nam Thịnh Vượng", "VPI": "Công ty Cổ phần Đầu tư Văn Phú - Invest",
        "VPL": "Công ty Cổ phần Vinpearl", "VPX": "Công ty Cổ phần Xây dựng Vận tải Phát Xá", "VRE": "Công ty Cổ phần Vincom Retail",
        "VSC": "Công ty Cổ phần Container Việt Nam", "VTP": "Tổng Công ty Cổ phần Bưu chính Viettel",
        "HGM": "Công ty Cổ phần Cơ khí và Khoáng sản Hà Giang", "PRE": "Tổng công ty cổ phần Tái bảo hiểm PVI",
        "HCC": "Công ty Cổ phần Bê tông Hòa Cầm - Intimex", "L40": "Công ty Cổ phần Licogi 40",
        "KDM": "Công ty Cổ phần ĐT&PT Dương Minh", "HVT": "Công ty Cổ phần Hóa chất Việt Trì",
        "VTZ": "Công ty Cổ phần Thương mại và Đầu tư Vạn Tường", "GLT": "Công ty Cổ phần Kỹ thuật Điện chiếu sáng G.L.T",
        "VGS": "Công ty Cổ phần ống thép Việt Đức VG PIPE", "PCH": "Công ty Cổ phần Thạch cao Cần Thơ",
        "CAR": "Công ty Cổ phần Tập đoàn Đầu tư Địa ốc No Va", "KSV": "Tổng công ty Khoáng sản TKV - CTCP",
        "THD": "Công ty Cổ phần Tập đoàn ThaiHoldings", "KSF": "Công ty Cổ phần Tập đoàn Sunshine Homes",
        "SCG": "Công ty Cổ phần Xây dựng Sông Đà 1.01", "CLM": "Công ty Cổ phần Than Cọc Sáu - Vinacomin",
        "TMB": "Công ty Cổ phần Kinh doanh Than miền Nam - Vinacomin", "SAF": "Công ty Cổ phần lương thực thực phẩm Safoco",
        "NET": "Công ty Cổ phần Bột giặt Net", "DHT": "Công ty Cổ phần Dược phẩm Hà Tây"
    }
    return company_names.get(symbol, f"Công ty Cổ phần {symbol}"), sector

# ==========================================
# 3. TỪ ĐIỂN DỊCH THUẬT VÀ HÀM DỊCH (GIỮ NGUYÊN)
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

def translate_metric(metric_original):
    cleaned_key = str(metric_original).strip()
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
    cleaned_viet = re.sub(r'[^a-zA-Zà-ỹÀ-Ỹ0-9\s]', ' ', cleaned_key)
    return f"Chỉ tiêu tài chính: {cleaned_viet.strip()}"

# ==========================================
# 4. HÀM CÀO DỮ LIỆU TỪ YFINANCE (DỰ PHÒNG)
# ==========================================
def parse_financial_df(symbol, df, statement_type_raw, ky_bao_cao, min_year=2020):
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
                            if pd.isna(float_val) or float_val == float('inf') or float_val == float('-inf'): continue
                            metric_vn = translate_metric(str(row_idx).strip())
                            records.append({
                                'Mã chứng khoán': symbol, 'Tên doanh nghiệp': company_name,
                                'Tên ngành': sector_name, 'Loại báo cáo': statement_type_vn,
                                'Loại kỳ': ky_bao_cao, 'Năm': year_val, 'Ngày kỳ': date_str,
                                'Chỉ tiêu tiếng Việt': metric_vn, 'Giá trị': float_val
                            })
    except Exception: pass
    return records

def fetch_market_metrics_yfinance(symbol, ticker_obj, balance_sheet_df):
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
                    if pd.isna(float_val) or float_val == float('inf') or float_val == float('-inf'): float_val = 0.0
                except: float_val = 0.0
            metric_vn = TRANSLATION_MAP.get(eng_key, eng_key)
            records.append({
                'Mã chứng khoán': symbol, 'Tên doanh nghiệp': company_name,
                'Tên ngành': sector_name, 'Loại báo cáo': 'Chỉ số thị trường, Định giá & Cổ tức',
                'Loại kỳ': 'Real-time', 'Năm': current_year, 'Ngày kỳ': today_str,
                'Chỉ tiêu tiếng Việt': metric_vn, 'Giá trị': float_val
            })
    except Exception:
        pass
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
                market_records.append({
                    'Mã chứng khoán': index_name, 'Tên doanh nghiệp': f'Chỉ số thị trường {index_name}',
                    'Tên ngành': 'Chỉ số vĩ mô', 'Loại báo cáo': 'Chỉ số thị trường, Định giá & Cổ tức',
                    'Loại kỳ': 'Real-time hằng ngày', 'Năm': current_year, 'Ngày kỳ': today_str,
                    'Chỉ tiêu tiếng Việt': name, 'Giá trị': float(val)
                })
        except Exception: pass
    return market_records

# ==========================================
# 5. HÀM CÀO DỮ LIỆU TỪ VNSTOCK V5 (NGUỒN CHÍNH)
# ==========================================
def parse_vnstock_df(symbol, df, statement_type_vn, ky_bao_cao):
    records = []
    company_name, sector_name = get_company_profile(symbol)
    if df is None or df.empty: return records
    for _, row in df.iterrows():
        metric_raw = row.get('item', row.get('item_en', ''))
        metric_vn = translate_metric(metric_raw)
        for col in df.columns:
            if col in ['item', 'item_en', 'unit', 'ticker', 'year', 'quarter', 'date', 'period', 'id', 'name', 'order', 'level', 'off_balance', 'category']: continue
            year_val = str(col).split('-')[0].strip()
            if not year_val.isdigit() or int(year_val) < 2020: continue
            val = row[col]
            if pd.notna(val):
                try: float_val = float(val)
                except: continue
                if pd.isna(float_val) or float_val in [float('inf'), float('-inf')]: continue
                records.append({
                    'Mã chứng khoán': symbol, 'Tên doanh nghiệp': company_name,
                    'Tên ngành': sector_name, 'Loại báo cáo': statement_type_vn,
                    'Loại kỳ': ky_bao_cao, 'Năm': year_val, 'Ngày kỳ': f"{year_val}-12-31" if ky_bao_cao == 'Năm' else str(col),
                    'Chỉ tiêu tiếng Việt': metric_vn, 'Giá trị': float_val
                })
    return records

def fetch_vnstock_metrics(symbol):
    """Lấy Giá, Vốn hóa, Số lượng cổ phiếu, Tỷ lệ cổ tức từ vnstock v5"""
    records = []
    company_name, sector_name = get_company_profile(symbol)
    current_year = str(datetime.now().year)
    today_str = datetime.today().strftime('%Y-%m-%d')
    
    # 1. Lấy Giá từ Market().equity().quote()
    price = 0.0
    try:
        quote_df = Market().equity(symbol).quote()
        if quote_df is not None and not quote_df.empty:
            # Cột giá có thể là 'close_price', 'match_price', 'price'
            for price_col in ['close_price', 'match_price', 'price', 'close']:
                if price_col in quote_df.columns:
                    price = float(quote_df.iloc[0][price_col])
                    break
    except Exception: pass

    # 2. Lấy Vốn hóa và Số lượng cổ phiếu từ Reference().company().overview()
    shares_out = 0.0
    market_cap = 0.0
    div_yield = 0.0
    try:
        overview_df = Reference().company(symbol).overview()
        if overview_df is not None and not overview_df.empty:
            row = overview_df.iloc[0]
            # Các cột có thể có: outstanding_shares, issue_share, market_cap, dividend_yield
            shares_out = float(row.get('outstanding_shares', row.get('issue_share', 0.0)))
            market_cap = float(row.get('market_cap', 0.0))
            div_yield = float(row.get('dividend_yield', 0.0))
    except Exception: pass

    # 3. Nếu thiếu vốn hóa, tự tính
    if (not market_cap or market_cap == 0.0) and price > 0 and shares_out > 0:
        market_cap = price * shares_out

    # 4. Tạo bản ghi
    metrics = [
        ('Current Price', price), ('Shares Outstanding', shares_out),
        ('Market Capitalization', market_cap), ('Dividend Yield', div_yield)
    ]
    for eng_key, val in metrics:
        metric_vn = TRANSLATION_MAP.get(eng_key, eng_key)
        records.append({
            'Mã chứng khoán': symbol, 'Tên doanh nghiệp': company_name,
            'Tên ngành': sector_name, 'Loại báo cáo': 'Chỉ số thị trường, Định giá & Cổ tức',
            'Loại kỳ': 'Real-time', 'Năm': current_year, 'Ngày kỳ': today_str,
            'Chỉ tiêu tiếng Việt': metric_vn, 'Giá trị': float(val) if pd.notna(val) else 0.0
        })
    return records

def fetch_vnstock_financials(symbol):
    records = []
    try:
        fin = Fundamental().equity(symbol)
        try: records.extend(parse_vnstock_df(symbol, fin.balance_sheet(period='year'), 'Bảng cân đối kế toán', 'Năm'))
        except Exception: pass
        try: records.extend(parse_vnstock_df(symbol, fin.income_statement(period='year'), 'Báo cáo kết quả kinh doanh', 'Năm'))
        except Exception: pass
        try: records.extend(parse_vnstock_df(symbol, fin.cash_flow(period='year'), 'Báo cáo lưu chuyển tiền tệ', 'Năm'))
        except Exception: pass
    except Exception: pass
    return records

# ==========================================
# 6. HÀM ĐIỀU PHỐI (ƯU TIÊN VNSTOCK TRƯỚC)
# ==========================================
def process_single_ticker(symbol, category):
    recs = []
    success = False

    # --- BƯỚC 1: ƯU TIÊN VNSTOCK (Lấy Giá, Vốn hóa, BCTC) ---
    vnstock_metrics = fetch_vnstock_metrics(symbol)
    if vnstock_metrics:
        recs.extend(vnstock_metrics)
        # Chỉ khi vnstock lấy được giá > 0 mới coi là thành công
        if any(r['Chỉ tiêu tiếng Việt'] == 'Giá cổ phiếu hiện tại' and r['Giá trị'] > 0 for r in vnstock_metrics):
            success = True

    vnstock_fin = fetch_vnstock_financials(symbol)
    if vnstock_fin:
        recs.extend(vnstock_fin)
        success = True

    # --- BƯỚC 2: NẾU VNSTOCK THẤT BẠI, DÙNG YFINANCE LÀM DỰ PHÒNG ---
    if not success:
        print(f" 🔄 vnstock thất bại, chuyển sang yfinance cho mã: {symbol}...")
        suffixes = [".VN", ".HN", ".UPCOM", ".HA", ".HM", ""]
        for suffix in suffixes:
            if success: break
            try:
                ticker = yf.Ticker(f"{symbol}{suffix}", session=session)
                bs_df = getattr(ticker, 'balance_sheet', None)
                recs.extend(parse_financial_df(symbol, bs_df, 'Balance_Sheet', 'Năm', min_year=2020))
                recs.extend(parse_financial_df(symbol, getattr(ticker, 'financials', None), 'Income_Statement', 'Năm', min_year=2020))
                recs.extend(parse_financial_df(symbol, getattr(ticker, 'cashflow', None), 'Cash_Flow', 'Năm', min_year=2020))
                recs.extend(fetch_market_metrics_yfinance(symbol, ticker, bs_df))
                if recs: success = True; break
            except Exception: time.sleep(0.1)

    # --- BƯỚC 3: NẾU CẢ 2 ĐỀU THẤT BẠI ---
    if not success:
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
# 7. HÀM MAIN VÀ LÀM SẠCH DỮ LIỆU BẰNG PANDAS
# ==========================================
def main():
    ticker_market_map = load_242_master_tickers()
    all_master_records = []
    success_count = 0
     
    print("📈 Đang cào dữ liệu 3 chỉ số thị trường vĩ mô...")
    index_recs = fetch_market_indices()
    if index_recs: all_master_records.extend(index_recs)

    total_tickers = len(ticker_market_map)
    print(f"🚀 Khởi chạy hệ thống đa luồng cho {total_tickers} mã (Ưu tiên vnstock, dự phòng yfinance)...")

    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = {executor.submit(process_single_ticker, symbol, cat): symbol for symbol, cat in ticker_market_map.items()}
        for future in as_completed(futures):
            symbol = futures[future]
            try:
                res = future.result()
                if res:
                    all_master_records.extend(res)
                    success_count += 1
                    print(f"[{success_count}/{total_tickers}] Đã hoàn thành mã: {symbol} ({len(res)} bản ghi)")
            except Exception as e:
                print(f"Lỗi xử lý mã {symbol}: {e}")

    df_master = pd.DataFrame(all_master_records)
    
    # --- QUY TRÌNH LÀM SẠCH DỮ LIỆU BẰNG PANDAS ---
    if not df_master.empty:
        # 1. Ép kiểu số cho cột Giá trị, loại bỏ NaN và vô cực
        df_master['Giá trị'] = pd.to_numeric(df_master['Giá trị'], errors='coerce')
        df_master = df_master[df_master['Giá trị'].notna()]
        df_master = df_master[~df_master['Giá trị'].isin([float('inf'), float('-inf')])]

        # 2. Loại bỏ trùng lặp
        df_master = df_master.drop_duplicates(subset=['Mã chứng khoán', 'Loại báo cáo', 'Loại kỳ', 'Ngày kỳ', 'Chỉ tiêu tiếng Việt'])

        # 3. Chuẩn hóa cột chữ (xóa "Yahoo Finance" nếu có)
        for col in ['Tên doanh nghiệp', 'Tên ngành', 'Loại báo cáo', 'Chỉ tiêu tiếng Việt']:
            if col in df_master.columns:
                df_master[col] = df_master[col].astype(str).str.replace("Yahoo Finance", "", case=False).str.strip()

        # 4. Ép buộc chỉ giữ 9 cột chuẩn
        standard_cols = ['Mã chứng khoán', 'Tên doanh nghiệp', 'Tên ngành', 'Loại báo cáo', 'Loại kỳ', 'Năm', 'Ngày kỳ', 'Chỉ tiêu tiếng Việt', 'Giá trị']
        df_master = df_master[standard_cols]

        # 5. Sắp xếp khoa học
        df_master = df_master.sort_values(by=['Tên ngành', 'Mã chứng khoán', 'Loại báo cáo', 'Loại kỳ', 'Ngày kỳ'], ascending=[True, True, True, False, False])

    print("\n💾 Đang kết xuất tệp CSV chuẩn hóa sạch 100%...")
    os.makedirs('data', exist_ok=True)
    csv_path = 'data/vietnam_stock_database_tong_hop.csv'
    df_master.to_csv(csv_path, index=False, encoding='utf-8-sig')
     
    print(f"==================================================")
    print(f" 🎉 HOÀN TẤT VÉT SẠCH & LÀM SẠCH DỮ LIỆU GỐC CHO {total_tickers} MÃ!")
    print(f" - Tổng mã ghi nhận thành công: {success_count}/{total_tickers}")
    print(f" - Tổng dung lượng bản ghi lịch sử sạch 100%: {len(df_master):,}")
    print(f"==================================================")

if __name__ == "__main__":
    main()
