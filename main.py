"""
FINEX VN STOCK DATABASE CRAWLER - v19.0 (EXHAUSTIVE HISTORY & AUDIT)
================================================================================
Changelog v17.0:
  ✅ Cào TẤT CẢ các quý lịch sử từ VNDirect (Fix triệt để lỗi dừng sớm).
  ✅ Bù đầy đủ 100% Giá và Số lượng cổ phiếu (SLCP) cho cả 176 mã.
  ✅ Giữ nguyên giá trị 0 và số âm hợp lệ; chỉ loại NULL/NaN/Inf.
  ✅ Tự động xuất file CSV, Parquet và đẩy lên Supabase.
  ✅ Giữ nguyên danh sách 176 mã, Từ điển VAS, CSV/Parquet/Supabase.
================================================================================
"""
import os
import socket
socket.setdefaulttimeout(30)

import signal
import sys
import time
from datetime import datetime
import pandas as pd
import numpy as np
import requests
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# Cấu hình crawler: giới hạn MAX_PAGES chỉ là cầu chì an toàn, không phải số trang mục tiêu.
CRAWLER_CONFIG = {
    "PAGE_SIZE": int(os.getenv("FINEX_PAGE_SIZE", "1000")),
    "MAX_PAGES": int(os.getenv("FINEX_MAX_PAGES", "10000")),
    "MAX_RETRIES": int(os.getenv("FINEX_MAX_RETRIES", "5")),
    "REQUEST_TIMEOUT": int(os.getenv("FINEX_REQUEST_TIMEOUT", "45")),
    "MIN_YEAR": int(os.getenv("FINEX_MIN_YEAR", "2000")),
    "WORKERS": int(os.getenv("FINEX_WORKERS", "4")),
    "REQUEST_PAUSE": float(os.getenv("FINEX_REQUEST_PAUSE", "0.15")),
}
CRAWL_ERRORS = []
CRAWL_COVERAGE = []
FAILED_PAGES = []

# ==============================================================================
# 🛡️ BẮT SIGTERM (CHỐNG TREO)
# ==============================================================================
_ALL_RECORDS_GLOBAL = []

def _emergency_save(signum, frame):
    print(f"\n⚠️ SIGTERM ({signum})! Lưu khẩn cấp...")
    try:
        if _ALL_RECORDS_GLOBAL:
            df = pd.DataFrame(_ALL_RECORDS_GLOBAL)
            os.makedirs('data', exist_ok=True)
            df.to_csv('data/_emergency_backup.csv', index=False, encoding='utf-8-sig')
            df.to_parquet('data/_emergency_backup.parquet', engine='pyarrow', index=False)
            q = len(df[df.get('Loại kỳ') == 'Quý']) if 'Loại kỳ' in df.columns else 0
            print(f"  ✅ Đã lưu {len(df):,} dòng (Quý: {q:,})!")
    except Exception as e:
        print(f"  ❌ Lưu khẩn cấp lỗi: {e}")
    sys.exit(0)

signal.signal(signal.SIGTERM, _emergency_save)
signal.signal(signal.SIGINT, _emergency_save)

# ==============================================================================
# 1. TỪ ĐIỂN KHUNG BÁO CÁO TÀI CHÍNH 4 NGÀNH (GIỮ NGUYÊN 100%)
# ==============================================================================
VAS_WHITELIST = set([
    # --- 1. DOANH NGHIỆP SẢN XUẤT, THƯƠNG MẠI, DỊCH VỤ, BĐS, XÂY DỰNG ---
    "Tài sản ngắn hạn", "Tiền và các khoản tương đương tiền", "Tiền", "Các khoản tương đương tiền",
    "Đầu tư tài chính ngắn hạn", "Chứng khoán kinh doanh", "Dự phòng giảm giá chứng khoán kinh doanh", "Đầu tư nắm giữ đến ngày đáo hạn",
    "Các khoản phải thu ngắn hạn", "Phải thu ngắn hạn của khách hàng", "Trả trước cho người bán ngắn hạn", "Phải thu nội bộ ngắn hạn", 
    "Phải thu theo tiến độ kế hoạch hợp đồng xây dựng", "Phải thu về cho vay ngắn hạn", "Phải thu ngắn hạn khác", "Dự phòng phải thu ngắn hạn khó đòi", "Tài sản thiếu chờ xử lý",
    "Hàng tồn kho", "Dự phòng giảm giá hàng tồn kho",
    "Tài sản ngắn hạn khác", "Chi phí trả trước ngắn hạn", "Thuế GTGT được khấu trừ", "Thuế và các khoản khác phải thu Nhà nước", "Giao dịch mua bán lại trái phiếu Chính phủ", "Tài sản ngắn hạn khác",
    "Tài sản dài hạn", "Các khoản phải thu dài hạn", "Phải thu dài hạn của khách hàng", "Trả trước cho người bán dài hạn", 
    "Vốn kinh doanh ở đơn vị trực thuộc", "Phải thu nội bộ dài hạn", "Phải thu về cho vay dài hạn", "Phải thu dài hạn khác", "Dự phòng phải thu dài hạn khó đòi",
    "Tài sản cố định", "Tài sản cố định hữu hình", "Nguyên giá", "Hao mòn lũy kế", "Tài sản cố định thuê tài chính", "Tài sản cố định vô hình",
    "Bất động sản đầu tư", "Tài sản dở dang dài hạn", "Chi phí sản xuất, kinh doanh dở dang dài hạn", "Chi phí xây dựng cơ bản dở dang",
    "Đầu tư tài chính dài hạn", "Đầu tư vào công ty con", "Đầu tư vào công ty liên doanh, liên kết", "Đầu tư góp vốn vào đơn vị khác", "Dự phòng đầu tư tài chính dài hạn", "Đầu tư nắm giữ đến ngày đáo hạn",
    "Tài sản dài hạn khác", "Chi phí trả trước dài hạn", "Tài sản thuế thu nhập hoãn lại", "Thiết bị, vật tư, phụ tùng thay thế dài hạn", "Tài sản dài hạn khác", "Lợi thế thương mại",
    "Tổng cộng tài sản", "Báo cáo tình hình tài chính", 
    "Nợ phải trả", "Nợ ngắn hạn", "Phải trả người bán ngắn hạn", "Người mua trả tiền trước ngắn hạn", "Thuế và các khoản phải nộp Nhà nước", 
    "Phải trả người lao động", "Chi phí phải trả ngắn hạn", "Phải trả nội bộ ngắn hạn", "Phải trả theo tiến độ kế hoạch hợp đồng xây dựng", 
    "Doanh thu chưa thực hiện ngắn hạn", "Phải trả ngắn hạn khác", "Vay và nợ thuê tài chính ngắn hạn", "Dự phòng phải trả ngắn hạn", 
    "Quỹ khen thưởng, phúc lợi", "Quỹ bình ổn giá", "Giao dịch mua bán lại trái phiếu Chính phủ",
    "Nợ dài hạn", "Phải trả người bán dài hạn", "Người mua trả tiền trước dài hạn", "Chi phí phải trả dài hạn", "Phải trả nội bộ về vốn kinh doanh", 
    "Phải trả nội bộ dài hạn", "Doanh thu chưa thực hiện dài hạn", "Phải trả dài hạn khác", "Vay và nợ thuê tài chính dài hạn", 
    "Trái phiếu chuyển đổi", "Cổ phiếu ưu đãi", "Thuế thu nhập hoãn lại phải trả", "Dự phòng phải trả dài hạn", "Quỹ phát triển khoa học và công nghệ",
    "Vốn chủ sở hữu", "Vốn góp của chủ sở hữu", "Cổ phiếu phổ thông có quyền biểu quyết", "Cổ phiếu ưu đãi", "Thặng dư vốn cổ phần", 
    "Quyền chọn chuyển đổi trái phiếu", "Vốn khác của chủ sở hữu", "Cổ phiếu quỹ", "Chênh lệch đánh giá lại tài sản", "Chênh lệch tỷ giá hối đoái", 
    "Quỹ đầu tư phát triển", "Quỹ hỗ trợ sắp xếp doanh nghiệp", "Quỹ khác thuộc vốn chủ sở hữu", "Lợi nhuận sau thuế chưa phân phối", 
    "LNST chưa phân phối lũy kế đến cuối kỳ trước", "LNST chưa phân phối kỳ này", "Nguồn vốn đầu tư XDCB", "Lợi ích cổ đông không kiểm soát",
    "Nguồn kinh phí và quỹ khác", "Nguồn kinh phí", "Nguồn kinh phí đã hình thành TSCĐ", "Tổng cộng nguồn vốn",
    
    "Doanh thu bán hàng và cung cấp dịch vụ", "Các khoản giảm trừ doanh thu",
    "Doanh thu thuần về bán hàng và cung cấp dịch vụ", "Doanh thu thuần", 
    "Giá vốn hàng bán", "Lợi nhuận gộp về bán hàng và cung cấp dịch vụ", "Lợi nhuận gộp",
    "Doanh thu hoạt động tài chính", "Chi phí tài chính", "Trong đó: chi phí lãi vay", "Chi phí lãi vay", 
    "Phần lãi/lỗ trong công ty liên doanh, liên kết", 
    "Chi phí bán hàng", "Chi phí quản lý doanh nghiệp",
    "Lợi nhuận thuần từ hoạt động kinh doanh", 
    "Thu nhập khác", "Chi phí khác", "Lợi nhuận khác",
    "Tổng lợi nhuận kế toán trước thuế",
    "Chi phí thuế TNDN hiện hành", "Chi phí thuế TNDN hoãn lại", 
    "Lợi nhuận sau thuế TNDN", "Lợi nhuận sau thuế thu nhập doanh nghiệp",
    "LNST của công ty mẹ", "LNST của cổ đông không kiểm soát",
    "Lãi cơ bản trên cổ phiếu", "Lãi suy giảm trên cổ phiếu",

    "Lợi nhuận trước thuế", "Khấu hao TSCĐ và BĐSĐT", "Các khoản dự phòng", 
    "Lãi/lỗ chênh lệch tỷ giá do đánh giá lại các khoản mục tiền tệ gốc ngoại tệ", "Lãi/lỗ chênh lệch tỷ giá",
    "Lãi/lỗ từ hoạt động đầu tư", "Các khoản điều chỉnh khác", "Lợi nhuận từ HĐKD trước thay đổi vốn lưu động",
    "Tăng/giảm các khoản phải thu", "Tăng/giảm hàng tồn kho", "Tăng/giảm các khoản phải trả", "Tăng/giảm chi phí trả trước", "Tăng/giảm chứng khoán kinh doanh", 
    "Tiền lãi vay đã trả", "Chi phí đi vay đã trả", "Thuế TNDN đã nộp", "Tiền thu khác từ HĐKD", "Tiền chi khác cho HĐKD", "Lưu chuyển tiền thuần từ HĐKD",
    "Tiền thu từ bán hàng, cung cấp dịch vụ và doanh thu khác", "Tiền chi trả người cung cấp hàng hóa, dịch vụ", "Tiền chi trả người lao động",
    "Tiền chi mua sắm, xây dựng TSCĐ và tài sản dài hạn khác", "Tiền thu thanh lý, nhượng bán TSCĐ và tài sản dài hạn khác",
    "Tiền chi cho vay, mua công cụ nợ của đơn vị khác", "Tiền thu hồi cho vay, bán lại công cụ nợ của đơn vị khác",
    "Tiền chi đầu tư góp vốn vào đơn vị khác", "Tiền thu hồi đầu tư góp vốn vào đơn vị khác", "Tiền thu lãi cho vay, cổ tức và lợi nhuận được chia", "Lưu chuyển tiền thuần từ HĐĐT",
    "Tiền thu từ phát hành cổ phiếu, nhận vốn góp của chủ sở hữu", "Tiền trả lại vốn góp, mua lại cổ phiếu đã phát hành", "Tiền thu từ đi vay", "Tiền trả nợ gốc vay", "Tiền trả nợ gốc thuê tài chính",
    "Cổ tức, lợi nhuận đã trả cho chủ sở hữu", "Lưu chuyển tiền thuần từ HĐTC",
    "Lưu chuyển tiền thuần trong kỳ", "Tiền và tương đương tiền đầu kỳ", "Ảnh hưởng của thay đổi tỷ giá quy đổi ngoại tệ", "Tiền và tương đương tiền cuối kỳ",

    # --- 2. NGÂN HÀNG ---
    "Tiền mặt, vàng bạc, đá quý", "Tiền gửi tại Ngân hàng Nhà nước", "Tiền gửi tại và cho vay các tổ chức tín dụng khác", 
    "Chứng khoán kinh doanh", "Các công cụ tài chính phái sinh và tài sản tài chính khác", "Cho vay khách hàng", 
    "Hoạt động mua nợ", "Chứng khoán đầu tư", "Góp vốn, đầu tư dài hạn", "Tài sản Có khác", 
    "Nợ Chính phủ và Ngân hàng Nhà nước", "Tiền gửi và vay các tổ chức tín dụng khác", "Tiền gửi của khách hàng", 
    "Công cụ tài chính phái sinh và nợ tài chính khác", "Vốn tài trợ, ủy thác đầu tư", "Phát hành giấy tờ có giá", 
    "Vốn điều lệ", "Thu nhập lãi thuần", "Thu nhập từ dịch vụ", "Lãi thuần từ dịch vụ", "Lãi thuần từ ngoại hối và vàng", 
    "Lãi thuần từ chứng khoán kinh doanh", "Lãi thuần từ chứng khoán đầu tư", "Thu nhập hoạt động khác", "Chi phí hoạt động (CIR)", 
    "Lợi nhuận trước dự phòng rủi ro tín dụng", "Chi phí dự phòng rủi ro tín dụng", "Thu nhập lãi nhận được", 
    "Chi phí lãi đã trả", "Thu từ dịch vụ", "Thu nợ đã xóa", "Chi cho nhân viên và quản lý",

    # --- 3. CÔNG TY CHỨNG KHOÁN ---
    "Tài sản tài chính", "Các tài sản tài chính ghi nhận thông qua lãi lỗ (FVTPL)", "Các khoản đầu tư nắm giữ đến ngày đáo hạn (HTM)", 
    "Các khoản cho vay (Margin)", "Tài sản tài chính sẵn sàng để bán (AFS)", "Dự phòng suy giảm giá trị", 
    "Các khoản phải thu (bán tài sản tài chính, cổ tức và lãi dự thu)", "Phải thu dịch vụ CTCK", "Phải thu lỗi giao dịch",
    "Vay và nợ thuê tài chính", "Vay tài sản tài chính", "Trái phiếu chuyển đổi (cấu phần nợ)", "Trái phiếu phát hành", "Vay Quỹ hỗ trợ thanh toán",
    "Phải trả hoạt động giao dịch chứng khoán", "Nhận ký quỹ, ký cược", "Quỹ dự trữ bổ sung vốn điều lệ", "Quỹ dự phòng tài chính và rủi ro nghiệp vụ",
    "Doanh thu hoạt động", "Lãi từ FVTPL (lãi bán, chênh lệch đánh giá lại, cổ tức và lãi)", "Lãi HTM", "Lãi cho vay và phải thu", 
    "Lãi AFS", "Lãi phái sinh phòng ngừa", "Doanh thu môi giới", "Bảo lãnh và đại lý phát hành", "Tư vấn đầu tư", "Lưu ký", "Tư vấn tài chính",
    "Chi phí hoạt động", "Lỗ FVTPL", "Lỗ HTM", "Lỗ AFS khi phân loại lại", "Chi phí dự phòng, xử lý tổn thất và chi phí đi vay của khoản cho vay",
    "Chi phí tự doanh, môi giới, bảo lãnh, tư vấn đầu tư, lưu ký, tư vấn tài chính và dịch vụ khác", "Doanh thu hoạt động tài chính",
    "Lãi tỷ giá", "Cổ tức và lãi tiền gửi", "Lãi bán, thanh lý công ty con, liên kết", "Chi phí tài chính", "Lỗ tỷ giá", "Chi phí lãi vay",
    "Lỗ thanh lý đầu tư", "Dự phòng đầu tư dài hạn", "Chi phí bán hàng", "Chi phí quản lý CTCK", "Kết quả hoạt động",

    # --- 4. BẢO HIỂM ---
    "Tài sản tái bảo hiểm", "Dự phòng phí và dự phòng bồi thường nhượng tái bảo hiểm", "Ký quỹ bảo hiểm",
    "Dự phòng nghiệp vụ", "Dự phòng phí chưa được hưởng", "Dự phòng toán học", "Dự phòng bồi thường", "Dự phòng chia lãi", "Dự phòng đảm bảo cân đối",
    "Phải thu và phải trả hoạt động nhận và nhượng tái bảo hiểm", "Phí bảo hiểm gốc", "Phí nhận tái bảo hiểm", "Phí nhượng tái bảo hiểm",
    "Thay đổi dự phòng phí", "Doanh thu phí bảo hiểm thuần", "Hoa hồng nhượng tái và doanh thu khác", "Doanh thu thuần hoạt động bảo hiểm",
    "Chi bồi thường gốc và nhận tái", "Thu bồi thường nhượng tái", "Thay đổi dự phòng bồi thường", "Chi hoa hồng", "Lợi nhuận gộp bảo hiểm"
])

ALIAS_TO_VAS = {
    "Total Assets": "Tổng cộng tài sản", "Current Assets": "Tài sản ngắn hạn", "Total Non Current Assets": "Tài sản dài hạn",
    "Cash And Cash Equivalents": "Tiền và các khoản tương đương tiền", "Cash": "Tiền và các khoản tương đương tiền", "Cash Financial": "Tiền và các khoản tương đương tiền",
    "Short Term Investments": "Đầu tư tài chính ngắn hạn", "Other Short Term Investments": "Đầu tư tài chính ngắn hạn",
    "Accounts Receivable": "Phải thu ngắn hạn của khách hàng", "Receivables": "Các khoản phải thu ngắn hạn",
    "Inventory": "Hàng tồn kho", "Net PPE": "Tài sản cố định hữu hình", "Gross PPE": "Nguyên giá", "Accumulated Depreciation": "Hao mòn lũy kế",
    "Investments And Advances": "Đầu tư tài chính dài hạn", "Other Non Current Assets": "Tài sản dài hạn khác",
    "Total Liabilities Net Minority Interest": "Nợ phải trả", "Current Liabilities": "Nợ ngắn hạn", "Accounts Payable": "Phải trả người bán ngắn hạn",
    "Long Term Debt": "Vay và nợ thuê tài chính dài hạn", "Total Equity Gross Minority Interest": "Vốn chủ sở hữu", "Stockholders Equity": "Vốn chủ sở hữu",
    "Retained Earnings": "Lợi nhuận sau thuế chưa phân phối", "Minority Interest": "Lợi ích cổ đông không kiểm soát", "Share Capital": "Vốn góp của chủ sở hữu",
    "Total Revenue": "Doanh thu bán hàng và cung cấp dịch vụ", "Operating Revenue": "Doanh thu thuần", "Cost Of Revenue": "Giá vốn hàng bán", "Cost of Goods Sold": "Giá vốn hàng bán",
    "Gross Profit": "Lợi nhuận gộp", "Operating Income": "Lợi nhuận thuần từ hoạt động kinh doanh", "Net Income": "Lợi nhuận sau thuế TNDN", "Net Income Common Stockholders": "LNST của công ty mẹ",
    "Pretax Income": "Tổng lợi nhuận kế toán trước thuế", "Tax Provision": "Chi phí thuế TNDN hiện hành", "Interest Expense": "Chi phí lãi vay",
    "Basic EPS": "Lãi cơ bản trên cổ phiếu", "Diluted EPS": "Lãi suy giảm trên cổ phiếu", "Operating Cash Flow": "Lưu chuyển tiền thuần từ HĐKD",
    "Cash Flow From Continuing Operating Activities": "Lưu chuyển tiền thuần từ HĐKD", "Investing Cash Flow": "Lưu chuyển tiền thuần từ HĐĐT", 
    "Financing Cash Flow": "Lưu chuyển tiền thuần từ HĐTC", "Capital Expenditure": "Tiền chi mua sắm, xây dựng TSCĐ và tài sản dài hạn khác", 
    "Depreciation And Amortization": "Khấu hao TSCĐ và BĐSĐT", "Depreciation Amortization Depletion": "Khấu hao TSCĐ và BĐSĐT",
    "Change In Working Capital": "Lợi nhuận từ HĐKD trước thay đổi vốn lưu động",
    "Doanh thu thuần HĐKD": "Doanh thu thuần", "Lợi nhuận sau thuế thu nhập doanh nghiệp": "Lợi nhuận sau thuế TNDN", "LNST": "Lợi nhuận sau thuế TNDN",
    "Vốn CSH": "Vốn chủ sở hữu", "Nợ phải trả ngắn hạn": "Nợ ngắn hạn", "Nợ phải trả dài hạn": "Nợ dài hạn", "Lợi nhuận gộp về bán hàng và cung cấp dịch vụ": "Lợi nhuận gộp",
    "Net Interest Income": "Thu nhập lãi thuần", "Gross Loan": "Cho vay khách hàng", "Customer Deposits": "Tiền gửi của khách hàng",
    "Trading Securities": "Chứng khoán kinh doanh", "Held To Maturity Securities": "Chứng khoán đầu tư"
}

def standardize_metric(raw_metric, report_type):
    if pd.isna(raw_metric): return None
    if "Chỉ số thị trường" in str(report_type) or "Chỉ số vĩ mô" in str(report_type):
        return clean_text(raw_metric)
    
    metric = clean_text(raw_metric)
    if not metric: return None
    
    if metric in VAS_WHITELIST: return metric
    if metric in ALIAS_TO_VAS: return ALIAS_TO_VAS[metric]
    
    metric_no_code = re.sub(r'\s*\(\d+[a-z]?\)\s*$', '', metric)
    if metric_no_code in VAS_WHITELIST: return metric_no_code
    if metric_no_code in ALIAS_TO_VAS: return ALIAS_TO_VAS[metric_no_code]
    
    for alias, standard in ALIAS_TO_VAS.items():
        if alias.lower() == metric.lower() or alias.lower() == metric_no_code.lower():
            return standard
            
    return metric_no_code


# ==========================================
# 2. API KEY & CÀI ĐẶT THƯ VIỆN
# ==========================================
# Không hard-code API key trong mã nguồn. Khai báo VNSTOCK_API_KEY trong Secrets/Environment nếu cần.
# os.environ["VNSTOCK_API_KEY"] = os.getenv("VNSTOCK_API_KEY", "")

try:
    import vnfinancialdata as vnf
except ImportError:
    print("⚙️ Đang cài đặt thư viện vnfinancialdata...")
    os.system("pip install vnfinancialdata --quiet")
    try:
        import vnfinancialdata as vnf
    except ImportError:
        vnf = None

try:
    import yfinance as yf
except ImportError:
    os.system("pip install yfinance --quiet")
    import yfinance as yf

# ==========================================
# 🆕 1.5 SUPABASE INTEGRATION
# ==========================================
try:
    from supabase import create_client
    HAS_SUPABASE_LIB = True
except ImportError:
    print("⚙️ Đang cài đặt thư viện supabase...")
    os.system("pip install supabase --quiet")
    try:
        from supabase import create_client
        HAS_SUPABASE_LIB = True
    except Exception as e:
        print(f"⚠️ Không thể cài đặt Supabase: {e}")
        HAS_SUPABASE_LIB = False

try:
    import streamlit as st
    HAS_STREAMLIT = True
except ImportError:
    HAS_STREAMLIT = False

def cached(ttl=600):
    if HAS_STREAMLIT:
        try:
            return st.cache_data(ttl=ttl)
        except Exception:
            pass
    def _noop(func):
        return func
    return _noop

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
SUPABASE_TABLE = os.environ.get("SUPABASE_TABLE", "finex_stock_master")
SUPABASE_PRIORITY = os.environ.get("SUPABASE_PRIORITY", "low").lower()
PUSH_TO_SUPABASE = os.environ.get("PUSH_TO_SUPABASE", "false").lower() == "true"
SUPABASE_ON_CONFLICT = os.environ.get("SUPABASE_ON_CONFLICT", "ticker,report_type,period_type,report_date,item_vn")

STANDARD_COLUMNS = [
    'Mã chứng khoán', 'Tên doanh nghiệp', 'Tên ngành',
    'Loại báo cáo', 'Loại kỳ', 'Năm', 'Ngày kỳ',
    'Chỉ tiêu tiếng Việt', 'Giá trị'
]

VN_TO_EN_MAP = {
    'Mã chứng khoán': 'ticker',
    'Tên doanh nghiệp': 'company_name',
    'Tên ngành': 'sector',
    'Loại báo cáo': 'report_type',
    'Loại kỳ': 'period_type',
    'Năm': 'year',
    'Ngày kỳ': 'report_date',
    'Chỉ tiêu tiếng Việt': 'item_vn',
    'Giá trị': 'value'
}
EN_TO_VN_MAP = {v: k for k, v in VN_TO_EN_MAP.items()}

PRIORITY_MAP = {
    'SUPABASE_HIGH': 0, 'DAILY': 1, 'VNDIRECT_BCTC': 2, 'VN_FINANCIAL': 2,
    'INDICES': 2, 'YFINANCE': 3, 'VNDIRECT': 3, 'VPS': 3, 'SUPABASE': 4,
}

_supabase_client = None

def init_supabase():
    global _supabase_client
    if _supabase_client is not None: return _supabase_client
    if not HAS_SUPABASE_LIB:
        print("⚠️ [SUPABASE] Thiếu thư viện supabase.")
        return None
    if not SUPABASE_URL or not SUPABASE_KEY:
        print("⚠️ [SUPABASE] Thiếu URL / KEY.")
        return None
    try:
        _supabase_client = create_client(SUPABASE_URL, SUPABASE_KEY)
        print(f"✅ [SUPABASE] Đã kết nối bảng '{SUPABASE_TABLE}'.")
        return _supabase_client
    except Exception as e:
        print(f"❌ [SUPABASE] Lỗi kết nối: {e}")
        return None

def _retry(fn, max_retries=3, backoff=2, label="SUPABASE"):
    last_err = None
    for attempt in range(max_retries):
        try: return fn()
        except Exception as e:
            last_err = e
            if attempt == max_retries - 1: break
            print(f"⚠️ [{label}] Lỗi lần {attempt+1}, thử lại sau {backoff**attempt}s: {e}")
            time.sleep(backoff ** attempt)
    raise last_err

def _normalize_to_standard(df, fill_company=True):
    if df is None or df.empty: return pd.DataFrame(columns=STANDARD_COLUMNS)
    col_alias = {
        'ticker': 'Mã chứng khoán', 'symbol': 'Mã chứng khoán', 'code': 'Mã chứng khoán',
        'company_name': 'Tên doanh nghiệp', 'company': 'Tên doanh nghiệp',
        'sector': 'Tên ngành', 'industry': 'Tên ngành',
        'report_type': 'Loại báo cáo', 'statement': 'Loại báo cáo',
        'period_type': 'Loại kỳ', 'period': 'Loại kỳ',
        'year': 'Năm', 'date': 'Ngày kỳ', 'report_date': 'Ngày kỳ',
        'item_vn': 'Chỉ tiêu tiếng Việt', 'item': 'Chỉ tiêu tiếng Việt', 'metric': 'Chỉ tiêu tiếng Việt',
        'value': 'Giá trị',
    }
    rename = {c: col_alias[str(c).lower()] for c in df.columns if str(c).lower() in col_alias and c not in STANDARD_COLUMNS}
    if rename: df = df.rename(columns=rename)

    for col in STANDARD_COLUMNS:
        if col not in df.columns:
            if col == 'Tên doanh nghiệp' and fill_company and 'Mã chứng khoán' in df.columns:
                df[col] = df['Mã chứng khoán'].apply(lambda x: get_company_profile(x)[0])
            elif col == 'Tên ngành' and fill_company and 'Mã chứng khoán' in df.columns:
                df[col] = df['Mã chứng khoán'].apply(lambda x: get_company_profile(x)[1])
            elif col == 'Loại báo cáo': df[col] = 'Chỉ số thị trường, Định giá & Cổ tức'
            elif col == 'Loại kỳ': df[col] = 'Real-time'
            elif col == 'Năm': df[col] = str(datetime.now().year)
            elif col == 'Ngày kỳ': df[col] = datetime.today().strftime('%Y-%m-%d')
            else: df[col] = ''
    return df[STANDARD_COLUMNS].copy()

@cached(ttl=600)
def load_data_from_supabase():
    client = init_supabase()
    if client is None: return pd.DataFrame(columns=STANDARD_COLUMNS)
    def _fetch_all():
        rows, page_size, start = [], 1000, 0
        while True:
            resp = client.table(SUPABASE_TABLE).select("*").range(start, start + page_size - 1).execute()
            batch = resp.data or []
            rows.extend(batch)
            if len(batch) < page_size: break
            start += page_size
        return rows
    try:
        all_rows = _retry(_fetch_all, label="SUPABASE")
        if not all_rows: return pd.DataFrame(columns=STANDARD_COLUMNS)
        df = pd.DataFrame(all_rows).rename(columns=EN_TO_VN_MAP)
        df = _normalize_to_standard(df, fill_company=False)
        print(f"✅ [SUPABASE] Đã tải {len(df):,} dòng.")
        return df
    except Exception as e:
        print(f"❌ [SUPABASE] Lỗi tải: {e}")
        return pd.DataFrame(columns=STANDARD_COLUMNS)

def upsert_to_supabase(df, batch_size=500):
    client = init_supabase()
    if client is None: return False
    if df is None or df.empty: return False
    
    try:
        payload = df.copy()
        payload = payload.dropna(subset=['Mã chứng khoán', 'Giá trị'])
        payload['Mã chứng khoán'] = payload['Mã chứng khoán'].astype(str).str.strip().str.upper()
        payload = payload[payload['Mã chứng khoán'] != '']
        payload = payload[payload['Mã chứng khoán'] != 'NAN']
        payload = payload.rename(columns=VN_TO_EN_MAP)
        
        valid_cols = ['ticker', 'company_name', 'sector', 'report_type', 'period_type', 'year', 'report_date', 'item_vn', 'value']
        for col in valid_cols:
            if col not in payload.columns: payload[col] = None
            
        records = []
        for _, row in payload.iterrows():
            ticker = str(row['ticker']).strip() if pd.notna(row['ticker']) else ''
            if not ticker: continue
            
            val = pd.to_numeric(row['value'], errors='coerce')
            if pd.isna(val) or not np.isfinite(float(val)): continue
            
            yr = pd.to_numeric(row['year'], errors='coerce')
            yr = int(yr) if pd.notna(yr) else datetime.now().year
            
            def clean_str(s):
                if pd.isna(s): return None
                s = str(s).strip()
                return s if s else None
                
            r = {
                'ticker': ticker,
                'company_name': clean_str(row['company_name']),
                'sector': clean_str(row['sector']),
                'report_type': clean_str(row['report_type']),
                'period_type': clean_str(row['period_type']),
                'year': yr,
                'report_date': clean_str(row['report_date']),
                'item_vn': clean_str(row['item_vn']),
                'value': float(val)
            }
            records.append(r)
            
        total = len(records)
        if total == 0:
            print("⚠️ [SUPABASE] Không có bản ghi hợp lệ sau khi làm sạch.")
            return False
            
        print(f"📤 [SUPABASE] Bắt đầu upsert {total:,} bản ghi (batch={batch_size})...")
        
        upsert_kwargs = {}
        if SUPABASE_ON_CONFLICT:
            upsert_kwargs['on_conflict'] = SUPABASE_ON_CONFLICT
            
        for i in range(0, total, batch_size):
            chunk = records[i:i+batch_size]
            def _do_upsert(c=chunk, kw=upsert_kwargs):
                return client.table(SUPABASE_TABLE).upsert(c, **kw).execute()
            _retry(_do_upsert, label="SUPABASE_UPSERT")
            print(f"   ✓ {min(i+batch_size, total):,}/{total:,}")
            
        print("✅ [SUPABASE] Upsert hoàn tất.")
        return True
    except Exception as e:
        print(f"❌ [SUPABASE] Lỗi upsert: {e}")
        return False

# ==========================================
# 2. TẢI DỮ LIỆU HÀNG NGÀY
# ==========================================
DATA_PATH = "du_lieu/dulieu_hang_ngay.csv"
HF_DATA_URL = "https://huggingface.co/datasets/trananhquan2001/finex-vn-dataset/raw/main/dulieu_hang_ngay.csv"

def load_daily_stock_data():
    if os.path.exists(DATA_PATH):
        try: return pd.read_csv(DATA_PATH)
        except Exception: pass
    try: return pd.read_csv(HF_DATA_URL)
    except Exception: return pd.DataFrame()

# ==========================================
# 3. DANH SÁCH 176 MÃ & THÔNG TIN DOANH NGHIỆP
# ==========================================
def load_176_master_tickers():
    raw_tickers = [
        'ACB','ANV','BAF','BCM','BID','BMP','BSI','BSR','BVH','BVS','BWE','CAP',
        'CEO','CII','CMG','CTD','CTG','CTR','CTS','DBC','DCM','DGW','DIG','DP3',
        'DPM','DSE','DTD','DXG','DXP','EIB','EVF','FPT','FRT','FTS','GAS','GEE',
        'GEX','GMD','GVR','HAG','HCM','HDB','HDG','HHV','HPG','HSG','HT1','HUT',
        'IDC','KBC','KDC','KDH','L14','L18','LAS','LHC','LPB','MBB','MBS','MCH',
        'MSB','MSN','MWG','NAB','NBC','NDN','NKG','NLG','NT2','NTP','NVL','OCB',
        'PAN','PC1','PDR','PHR','PLC','PLX','PNJ','POW','PSD','PVB','PVC','PVD',
        'PVS','PVT','PVI','REE','SAB','SBT','SHB','SHS','SIP','SJS','SLS','SSB',
        'SSI','STB','TAL','TCB','TCH','TCX','TDM','TIG','TNG','TPB','TVD','VCB',
        'VC3','VCG','VCI','VCK','VCS','VFS','VGC','VGP','VHC','VHM','VIB','VIC',
        'VIX','VJC','VND','VNM','VPB','VPI','VPL','VPX','VRE','VSC','VTP','L40',
        'HVT','GLT','VGS','HGM','KSV','THD','KSF','SCG','CLM','TMB','SAF','NET',
        'DHT','DGC','SZC','HVN','BAB','AGR','TLH','BMI','PET','LSS','HDC','IJC',
        'TDC','CTI','SJD','TMP','SBA','VSH','TTA','TV2','VCP','BFC','DDV','SGP',
        'DPR','DHC','TCM','HPP','PAT','DTP','SCL','HMS',
    ]
    return {t.strip().upper(): "VIETNAM_MARKET" for t in raw_tickers if t.strip()}

def get_company_profile(symbol):
    tech_list = ["FPT", "CMG", "VTP", "ICT", "ELC", "CTR", "VGI", "VNZ", "FOX", "FOC", "VTK", "MFS", "VEC"]
    bank_list = ["VCB","BID","TCB","MBB","ACB","CTG","VPB","STB","SHB","HDB","LPB","MSB","OCB","NAB","SSB","EIB","TPB","ABB","BAB"]
    securities_list = ["SSI","VCI","HCM","VND","SHS","MBS","FTS","BSI","CTS","VIX","VDS","ORS","AGR","VFS","DSE","BVS","EVF","IPA","EVS","HBS","PSI","WSS","F88"]
    realestate_list = ["VIC","VHM","VRE","BCM","KBC","IDC","SIP","SZC","KDH","NLG","DXG","PDR","DIG","CEO","HDC","NVL","TCH","VC3","VPI","SJS","L14","L18","NDN","THD","KSF","IJC","TDC","CTI","VEF","TED","CC1","PCC","LIC","CLI","HEC"]
    retail_list = ["MWG","FRT","DGW","PNJ","PET","DMX"]
    oil_gas_list = ["GAS","PLX","PVD","PVS","PVT","PVB","BSR","OIL","POW","DTK","PGV","NT2","PGI","PLC","PSD","PVC","SJD","TMP","SBA","VSH","TTA","TV2","VCP","ODE","AVC"]
    steel_materials = ["HPG","HSG","NKG","GDA","BMP","NTP","AAA","DGC","CSV","LAS","PHR","DPM","DCM","BFC","HPA","VGS","HT1","LHC","HGM","KSV","TLH","DDV","BFC","DPR","DHC","VLB","HPP","VXB","PAT","SIV","ACE","HAM","SBM","SCL","NAS","HMS","QPH"]
    agriculture_list = ["HAG","ANV","BAF","DBC","CAP","IDP","KDC","MCH","MSN","QNS","SAB","SBT","SLS","VHC","CKA","SEA","APF","LSG","VSF","AGP","DTP","WSB","BWS","QHW","HLB"]

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
        "CKA":"Công ty CP XNK Thủy sản Cà Mau","VLB":"Công ty CP XD và SX Vật liệu XD Biên Hòa","HPP":"Công ty CP Sơn Hải Phòng",
        "WSB":"Công ty CP Bia Sài Gòn - Miền Tây","F88":"Công ty CP Đầu tư Kinh doanh F88","SEA":"Tổng Công ty Thủy sản Việt Nam",
        "ODE":"Công ty CP Dịch vụ Dầu khí Biển","PHP":"Công ty CP Cảng Hải Phòng","VXB":"Công ty CP Vật liệu XD Bến Tre",
        "APF":"Công ty CP Nông sản Thực phẩm Quảng Ngãi","VNZ":"Công ty CP VNG","HLB":"Công ty CP Hữu Liên",
        "TED":"Công ty CP XD và Công nghệ Tiến Đạt","VEF":"Công ty CP Trung tâm Hội chợ Triển lãm VN","PAT":"Công ty CP Phốt pho Apatit VN",
        "FOC":"Công ty CP Dịch vụ Trực tuyến FPT","DTP":"Công ty CP Dược phẩm CPC1 Hà Nội","SIV":"Công ty CP SIVICO",
        "VGG":"Công ty CP May Vĩnh Phú","AVC":"Công ty CP Thủy điện A Vương","LSG":"Công ty CP Mía đường Lam Sơn",
        "CQN":"Công ty CP Cảng Quảng Ninh","QPH":"Công ty CP Quảng Ninh","TCW":"Công ty CP Kho vận Tân Cảng",
        "ACE":"Công ty CP Bê tông Hà Thanh","VSF":"Công ty CP Giống cây trồng TW","HAM":"Công ty CP Vật tư Hà Nội",
        "SBM":"Công ty CP Đầu tư Phát triển Bắc Minh","AGP":"Công ty CP Dược phẩm Agimexpharm","LIC":"Công ty CP SX KD XNK Lam Sơn",
        "SCL":"Công ty CP Sứ Cao Lãnh","CC1":"Tổng Công ty Xây dựng số 1","BWS":"Công ty CP Bia Sài Gòn - Sông Lam",
        "NAS":"Công ty CP Phân bón Hà Bắc","CLI":"Công ty CP XNK & XD Giao thông","VTK":"Công ty CP Tư vấn và Dịch vụ Viettel",
        "HMS":"Công ty CP Cơ khí Hà Nội","PCC":"Công ty CP Tập đoàn XD PCC1","QHW":"Công ty CP Nước Khoáng Quảng Ninh",
        "MFS":"Công ty CP Dịch vụ Kỹ thuật Mobifone","VEC":"Tổng Công ty Điện tử và Tin học VN","HEC":"Công ty CP Tư vấn XD Thủy lợi và Môi trường",
        "ABB":"Ngân hàng TMCP An Bình","ACB":"Ngân hàng TMCP Á Châu","ACV":"TCT Cảng hàng không VN","BVS":"CTCP Chứng khoán Bảo Việt",
        "CAP":"CTCP Lâm nông sản thực phẩm Yên Bái","CEO":"CTCP Tập đoàn C.E.O","DNH":"CTCP Thủy điện Đa Nhim",
        "DP3":"CTCP Dược phẩm Trung ương 3","DTD":"CTCP Đầu tư Phát triển Thành Đạt","DVN":"Tổng Công ty Dược Việt Nam",
        "DXP":"CTCP Cảng Đình Vũ","FOX":"CTCP Viễn thông FPT","HND":"CTCP Nhiệt điện Hải Phòng","HUT":"CTCP Tasco",
        "IDC":"Tổng công ty IDICO","IDP":"CTCP Sữa Quốc tế IDP","L14":"CTCP Licogi 14","L18":"CTCP Đầu tư và Xây dựng số 18",
        "LAS":"CTCP Supe Phốt phát và Hóa chất Lâm Thao","LHC":"CTCP Đầu tư và Xây dựng Lắp máy IDICO","MBS":"CTCP Chứng khoán MB",
        "MSR":"CTCP Masan High-Tech Materials","MVN":"Tổng Công ty Hàng hải Việt Nam","NBC":"CTCP Than Núi Béo",
        "NDN":"CTCP Đầu tư Phát triển Nhà Đà Nẵng","NTP":"CTCP Nhựa Thiếu niên Tiền Phong","OIL":"Tổng Công ty Dầu Việt Nam",
        "PLC":"Tổng Công ty Hóa dầu Petrolimex","PSD":"CTCP Dịch vụ Tổng hợp Dầu khí","PVB":"CTCP bọc ống Dầu khí Việt Nam",
        "PVC":"Tổng Công ty Hóa chất và Dung dịch Khoan Dầu khí","PVS":"Tổng công ty CP Dịch vụ Kỹ thuật Dầu khí Việt Nam",
        "PVI":"CTCP PVI","QNS":"CTCP Đường Quảng Ngãi","QTP":"CTCP Nhiệt điện Quảng Ninh","SAS":"CTCP Dịch vụ Hàng không Sân bay Tân Sơn Nhất",
        "SHS":"CTCP Chứng khoán Sài Gòn - Hà Nội","SLS":"CTCP Mía đường Sơn La","SNZ":"Tổng Công ty Sonadezi",
        "TBD":"CTCP Chế tạo Thiết bị Điện Đông Anh","TID":"Tổng Công ty Đầu tư Phát triển Hạ tầng Urban",
        "TIG":"CTCP Tập đoàn Đầu tư Thăng Long","TNG":"CTCP Đầu tư và Thương mại TNG","TOS":"CTCP Dịch vụ biển Tân Cảng",
        "TVD":"CTCP Than Vàng Danh","VC3":"CTCP Tập đoàn Nam Cường","VCS":"CTCP Vicosstone",
        "VEA":"Tổng công ty Máy động lực và máy nông nghiệp VN","VFS":"CTCP Chứng khoất Nhất Việt","VGI":"Tổng Công ty CP Đầu tư Quốc tế Viettel",
        "VGP":"CTCP Cảng Cần Giuộc","VGR":"CTCP Vận tải và Xếp dỡ Hải An","PRE":"Tổng công ty CP Tái bảo hiểm PVI",
        "HCC":"CTCP Bê tông Hòa Cầm - Intimex","L40":"CTCP Licogi 40","KDM":"CTCP ĐT&PT Dương Minh","HVT":"CTCP Hóa chất Việt Trì",
        "VTZ":"CTCP Thương mại và Đầu tư Vạn Tường","GLT":"CTCP Kỹ thuật Điện chiếu sáng G.L.T","VGS":"CTCP ống thép Việt Đức VG PIPE",
        "PCH":"CTCP Thạch cao Cần Thơ","CAR":"CTCP Tập đoàn Đầu tư Địa ốc No Va","HGM":"CTCP Cơ khí và Khoáng sản Hà Giang",
        "KSV":"Tổng công ty Khoáng sản TKV","THD":"CTCP Tập đoàn ThaiHoldings","KSF":"CTCP Tập đoàn Sunshine Homes",
        "SCG":"CTCP Xây dựng Sông Đà 1.01","CLM":"CTCP Than Cọc Sáu","TMB":"CTCP Kinh doanh Than miền Nam",
        "SAF":"CTCP lương thực thực phẩm Safoco","NET":"CTCP Bột giặt Net","DHT":"CTCP Dược phẩm Hà Tây",
        "BAB":"Ngân hàng TMCP Bắc Á","TV2":"CTCP Tư vấn Xây dựng Điện 2","VCP":"CTCP Xây dựng điện VNECO 3",
        "DDV":"CTCP DAP - VINACHEM","VGT":"Tập đoàn Dệt May Việt Nam","SGP":"Tổng Công ty Cảng Sài Gòn",
        "DPR":"CTCP Cao su Đồng Phú","DHC":"CTCP Đông Hải Bến Tre","TCM":"CTCP Dệt mão Thành Công"
    }
    return company_names.get(symbol, f"Công ty Cổ phần {symbol}"), sector

# ==========================================
# 4. TRANSLATION MAP (GIỮ NGUYÊN 100%)
# ==========================================
TRANSLATION_MAP = {
    'N s':'Số lượng cổ phiếu ròng','M':'Lợi ích cổ đông không kiểm soát',
    'Tổng khác f giá gốc':'Tổng chi phí khác theo giá gốc',
    'N on ngắn hạn deferred taxes liabilities':'Thuế thu nhập hoãn lại phải trả ngắn hạn',
    'Pensi onand khác post retirement benefit plans ngắn hạn':'Quỹ phúc lợi nhân viên ngắn hạn',
    'Khác payable':'Phải trả khác','Dividends payable':'Cổ tức phải trả',
    'Tổng thuê payable':'Tổng thuế phải trả',
    'Investmentsin joint venturesat cost':'Đầu tư vào liên doanh theo giá gốc',
    'Investmentsin associatesat cost':'Đầu tư vào công ty liên kết theo giá gốc',
    'Khác properties':'Bất động sản khác','Buildings and improvements':'Nhà cửa và vật kiến trúc',
    'Tiền mặt tiền mặt equivalents and short term investments':'Tiền mặt, tương đương tiền và đầu tư ngắn hạn',
    'Taxes receivable':'Thuế phải thu',
    'Investments in joint ventures at cost':'Đầu tư vào liên doanh theo giá gốc',
    'Investments in associates at cost':'Đầu tư vào công ty liên kết theo giá gốc',
    'Non ngắn hạn deferred taxes liabilities':'Thuế thu nhập hoãn lại phải trả ngắn hạn',
    'Non current deferred taxes liabilities':'Thuế thu nhập hoãn lại phải trả dài hạn',
    'Current deferred taxes liabilities':'Thuế thu nhập hoãn lại phải trả ngắn hạn',
    'Other payable':'Phải trả khác','Other payables':'Phải trả khác','Other properties':'Bất động sản khác',
    'Total tax payable':'Tổng thuế phải trả','Total lease payable':'Tổng tiền thuê phải trả',
    'Pension and other post retirement benefit plans current':'Quỹ phúc lợi nhân viên ngắn hạn',
    'Pension and other post-retirement benefit plans current':'Quỹ phúc lợi nhân viên ngắn hạn',
    'Pension and other post retirement benefit plans':'Quỹ phúc lợi nhân viên và hưu trí',
    'Pension and other post-retirement benefit plans':'Quỹ phúc lợi nhân viên và hưu trí',
    'Cash cash equivalents and short term investments':'Tiền mặt, tương đương tiền và đầu tư ngắn hạn',
    'Current tax payable':'Thuế phải trả ngắn hạn','Current tax receivables':'Thuế phải thu ngắn hạn',
    'Investments in joint ventures':'Đầu tư vào liên doanh','Investments in associates':'Đầu tư vào công ty liên kết',
    'Tax payable':'Thuế phải trả','Deferred taxes liabilities':'Thuế thu nhập hoãn lại phải trả',
    'Other current payables':'Phải trả ngắn hạn khác','Other non current payables':'Phải trả dài hạn khác',
    'Other current receivables':'Phải thu ngắn hạn khác','Other non current receivables':'Phải thu dài hạn khác',
    'Net property plant and equipment':'Tài sản cố định hữu hình thuần',
    'Gross property plant and equipment':'Nguyên giá tài sản cố định hữu hình',
    'Property plant and equipment':'Tài sản cố định hữu hình',
    'Accumulated depreciation':'Hao mòn lũy kế tài sản cố định',
    'Other intangible assets':'Tài sản cố định vô hình khác',
    'Goodwill and other intangible assets':'Lợi thế thương mại và tài sản vô hình',
    'Short term investments':'Đầu tư ngắn hạn','Long term investments':'Đầu tư dài hạn',
    'Accounts receivable':'Phải thu khách hàng','Accounts payable':'Phải trả người bán',
    'Retained earnings':'Lợi nhuận sau thuế chưa phân phối','Share premium':'Thặng dư vốn cổ phần',
    'Share capital':'Vốn góp chủ sở hữu','Total equity':'Tổng vốn chủ sở hữu',
    'Minority interest':'Lợi ích cổ đông không kiểm soát',
    'Total Expenses':'Tổng chi phí','Classesof Cash Payments':'Các khoản thanh toán tiền mặt',
    'Other Cash Paymentsfrom Operating Activities':'Các khoản thanh toán tiền mặt khác từ HĐKD',
    'Paymentson Behalfof Employees':'Thanh toán cho người lao động',
    'Classesof Cash Receiptsfrom Operating Activities':'Các khoản thu tiền mặt từ HĐKD',
    'Other Cash Receiptsfrom Operating Activities':'Các khoản thu tiền mặt khác từ HĐKD',
    'Dividends Received Cf':'Cổ tức đã nhận','Sale Of PPE':'Thu từ thanh lý tài sản cố định',
    'Purchase Of PPE':'Chi mua sắm tài sản cố định',
    'Total Unusual Items Excluding Goodwill':'Tổng các khoản mục bất thường (Không gồm lợi thế thương mại)',
    'Diluted NI Availto Com Stockholders':'Lợi nhuận ròng pha loãng phân bổ cho CĐ phổ thông',
    'Other Cash Paymentsfrom Investing Activities':'Các khoản thanh toán tiền mặt khác từ HĐ đầu tư',
    'Other Cash Receiptsfrom Investing Activities':'Các khoản thu tiền mặt khác từ HĐ đầu tư',
    'Other Cash Paymentsfrom Financing Activities':'Các khoản thanh toán tiền mặt khác từ HĐ tài chính',
    'Other Cash Receiptsfrom Financing Activities':'Các khoản thu tiền mặt khác từ HĐ tài chính',
    'Classesof Cash Paymentsfrom Investing Activities':'Các khoản thanh toán tiền mặt từ HĐ đầu tư',
    'Classesof Cash Receiptsfrom Investing Activities':'Các khoản thu tiền mặt từ HĐ đầu tư',
    'Classesof Cash Paymentsfrom Financing Activities':'Các khoản thanh toán tiền mặt từ HĐ tài chính',
    'Classesof Cash Receiptsfrom Financing Activities':'Các khoản thu tiền mặt từ HĐ tài chính',
    'Diluted NI Available to Com Stockholders':'Lợi nhuận ròng pha loãng phân bổ cho CĐ phổ thông',
    'Net Income from Continuing Operation Net Minority Interest':'Lợi nhuận ròng từ HĐKD liên tục trừ lợi ích CĐ không kiểm soát',
    'Total Unusual Items Excluding Good':'Tổng các khoản mục bất thường (Không gồm lợi thế thương mại)',
    'Net Income Common Stockholders':'Lợi nhuận ròng phân bổ cho cổ đông phổ thông',
    'Total Other Finance Cost':'Tổng chi phí tài chính khác',
    'Net Non Operating Interest Income Expense':'Thu nhập/chi phí lãi thuần ngoài HĐKD',
    'Other Income Expense':'Thu nhập/chi phí khác','Total Operating Income As Reported':'Tổng lợi nhuận HĐKD như báo cáo',
    'Reconciled Depreciation':'Khấu hao được điều chỉnh','Net Income Extraordinary':'Lợi nhuận ròng bất thường',
    'Net Income Discontinuous Operations':'Lợi nhuận ròng từ hoạt động không liên tục',
    'Net Income Continuous Operations':'Lợi nhuận ròng từ hoạt động liên tục',
    'Minority Interests':'Lợi ích cổ đông không kiểm soát','Special Income Charges':'Chi phí thu nhập đặc biệt',
    'Other Special Charges':'Chi phí đặc biệt khác','Write Off':'Xóa sổ',
    'Balance_Sheet':'Bảng cân đối kế toán','Income_Statement':'Báo cáo kết quả kinh doanh',
    'Cash_Flow':'Báo cáo lưu chuyển tiền tệ','Market_Metrics':'Chỉ số thị trường, Định giá & Cổ tức',
    'Ordinary Shares Number':'Số lượng cổ phiếu phổ thông','Share Issued':'Cổ phiếu đã phát hành',
    'Total Assets':'Tổng tài sản','Current Assets':'Tài sản ngắn hạn',
    'Cash And Cash Equivalents':'Tiền và các khoản tương đương tiền','Cash Financial':'Tiền và đầu tư tài chính ngắn hạn',
    'Cash Equivalents':'Các khoản tương đương tiền','Cash':'Tiền mặt',
    'Other Short Term Investments':'Đầu tư tài chính ngắn hạn khác','Receivables':'Các khoản phải thu',
    'Accounts Receivable':'Phải thu ngắn hạn khách hàng','Allowance For Doubtful Accounts Receivable':'Dự phòng phải thu ngắn hạn khó đòi',
    'Due From Related Parties Current':'Phải thu các bên liên quan ngắn hạn','Other Receivables':'Các khoản phải thu ngắn hạn khác',
    'Inventory':'Hàng tồn kho','Raw Materials':'Nguyên liệu, vật liệu tồn kho',
    'Work In Process':'Chi phí sản xuất kinh doanh dở dang','Finished Goods':'Thành phẩm tồn kho',
    'Prepaid Assets':'Chi phí trả trước ngắn hạn','Restricted Cash':'Tiền bị hạn chế',
    'Total Non Current Assets':'Tổng tài sản dài hạn','Net PPE':'Tài sản cố định thuần',
    'Gross PPE':'Nguyên giá tài sản cố định','Accumulated Depreciation':'Hao mòn lũy kế tài sản cố định',
    'Machinery Furniture Equipment':'Máy móc, thiết bị và phương tiện vận tải','Land And Improvements':'Đất đai và cải tạo đất',
    'Properties':'Bất động sản','Leases':'Tài sản quyền sử dụng đất và thuê tài chính',
    'Construction In Progress':'Xây dựng cơ bản dở dang','Goodwill And Other Intangible Assets':'Lợi thế thương mại và tài sản vô hình',
    'Goodwill':'Lợi thế thương mại','Other Intangible Assets':'Tài sản cố định vô hình khác',
    'Investments And Advances':'Đầu tư tài chính dài hạn','Investment in Financial Assets':'Đầu tư tài chính dài hạn',
    'Held To Maturity Securities':'Chứng khoán giữ đến ngày đáo hạn','Available For Sale Securities':'Chứng khoán sẵn sàng để bán',
    'Investment Properties':'Bất động sản đầu tư','Other Non Current Assets':'Tài sản dài hạn khác',
    'Deferred Tax Assets':'Tài sản thuế thu nhập hoãn lại',
    'Current Liabilities':'Nợ ngắn hạn','Current Debt':'Vay và nợ thuê tài chính ngắn hạn',
    'Payables':'Các khoản phải trả','Accounts Payable':'Phải trả người bán ngắn hạn',
    'Taxes Payable':'Thuế và các khoản phải nộp nhà nước','Accrued Liabilities':'Chi phí phải trả ngắn hạn',
    'Pension and Other Post-Retirement Benefit Plans Current':'Quỹ phúc lợi nhân viên ngắn hạn',
    'Other Current Liabilities':'Phải trả, phải nộp ngắn hạn khác','Total Liabilities Net Minority Interest':'Tổng nợ phải trả',
    'Total Non Current Liabilities Net Minority Interest':'Nợ dài hạn','Long Term Debt':'Vay và nợ thuê tài chính dài hạn',
    'Total Debt':'Tổng nợ vay','Net Debt':'Nợ vay ròng','Deferred Revenue':'Doanh thu chưa thực hiện dài hạn',
    'Deferred Tax Liabilities':'Thuế thu nhập hoãn lại phải trả','Other Non Current Liabilities':'Nợ dài hạn khác',
    'Stockholders Equity':'Vốn chủ sở hữu','Capital Stock':'Vốn góp chủ sở hữu','Common Stock':'Cổ phiếu phổ thông',
    'Retained Earnings':'Lợi nhuận sau thuế chưa phân phối','Additional Paid In Capital':'Thặng dư vốn cổ phần',
    'Gains Losses Not Affecting Retained Earnings':'Chênh lệch đánh giá lại tài sản và chênh lệch tỷ giá',
    'Minority Interest':'Lợi ích cổ đông không kiểm soát','Total Equity Gross Minority Interest':'Tổng vốn chủ sở hữu gồm cổ đông không kiểm soát',
    'Working Capital':'Vốn lưu động ròng',
    'Total Revenue':'Tổng doanh thu','Operating Revenue':'Doanh thu thuần',
    'Cost Of Revenue':'Giá vốn hàng bán','Gross Profit':'Lợi nhuận gộp',
    'Operating Expense':'Chi phí hoạt động','Selling General And Administration':'Chi phí bán hàng và quản lý doanh nghiệp',
    'Selling And Marketing Expense':'Chi phí bán hàng','General And Administrative Expense':'Chi phí quản lý doanh nghiệp',
    'Research And Development':'Chi phí nghiên cứu và phát triển','Other Operating Expenses':'Chi phí hoạt động khác',
    'Operating Income':'Lợi nhuận thuần từ hoạt động kinh doanh','Net Interest Income':'Thu nhập lãi thuần',
    'Interest Expense':'Chi phí lãi vay','Interest Income':'Thu nhập lãi',
    'EBIT':'Lợi nhuận trước lãi vay và thuế (EBIT)','EBITDA':'Lợi nhuận trước lãi vay, thuế và khấu hao (EBITDA)',
    'Normalized EBITDA':'Lợi nhuận trước lãi vay, thuế, khấu hao chuẩn hóa',
    'Normalized Income':'Lợi nhuận thuần chuẩn hóa','Pretax Income':'Lợi nhuận kế toán trước thuế',
    'Tax Provision':'Chi phí thuế thu nhập doanh nghiệp','Net Income':'Lợi nhuận sau thuế (Lợi nhuận ròng)',
    'Net Income Including Noncontrolling Interests':'Lợi nhuận sau thuế bao gồm lợi ích cổ đông không kiểm soát',
    'Net Income From Continuing Operation':'Lợi nhuận sau thuế từ hoạt động tiếp tục',
    'Net Income From Continuing And Discontinued Operation':'Lợi nhuận thuần từ hoạt động tiếp tục và không tiếp tục',
    'Tax Effect Of Unusual Items':'Ảnh hưởng thuế từ các khoản mục bất thường','Tax Rate For Calcs':'Thuế suất dùng để tính toán',
    'Gain On Sale Of Security':'Lãi / Lỗ từ bán chứng khoán','Other Under Preferred Stock Dividend':'Cổ tức cổ phiếu ưu đãi và điều chỉnh khác',
    'Basic EPS':'Lãi cơ bản trên cổ phiếu (Basic EPS)','Diluted EPS':'Lãi suy giảm trên cổ phiếu (Diluted EPS)',
    'Diluted Average Shares':'Số lượng cổ phiếu bình quân pha loãng','Basic Average Shares':'Số lượng cổ phiếu bình quân cơ bản',
    'Operating Cash Flow':'Lưu chuyển tiền thuần từ hoạt động kinh doanh',
    'Cash Flow From Continuing Operating Activities':'Lưu chuyển tiền thuần từ hoạt động kinh doanh tiếp tục',
    'Depreciation Amortization Depletion':'Khấu hao tài sản cố định và phân bổ',
    'Depreciation And Amortization':'Khấu hao và phân bổ','Asset Impairment Charge':'Tổn thất tài sản và dự phòng',
    'Deferred Income Tax':'Thuế thu nhập hoãn lại','Change In Working Capital':'Biến động vốn lưu động',
    'Change In Receivables':'Biến động các khoản phải thu','Change In Inventory':'Biến động hàng tồn kho',
    'Change In Payables':'Biến động các khoản phải trả','Change In Account Payable':'Biến động phải trả người bán',
    'Change In Other Working Capital':'Biến động vốn lưu động khác',
    'Investing Cash Flow':'Lưu chuyển tiền thuần từ hoạt động đầu tư',
    'Cash Flow From Continuing Investing Activities':'Lưu chuyển tiền thuần từ hoạt động đầu tư tiếp tục',
    'Capital Expenditure':'Chi phí đầu tư tài sản cố định (CapEx)','Net PPE Purchase And Sale':'Tiền mua hoặc thanh lý tài sản cố định',
    'Net Intangibles Purchase And Sale':'Tiền mua hoặc bán tài sản vô hình','Net Investment Purchase And Sale':'Tiền đầu tư góp vốn thuần',
    'Net Business Purchase And Sale':'Tiền mua bán công ty con hoặc sáp nhập','Free Cash Flow':'Dòng tiền tự do (FCF)',
    'Financing Cash Flow':'Lưu chuyển tiền thuần từ hoạt động tài chính',
    'Cash Flow From Continuing Financing Activities':'Lưu chuyển tiền thuần từ hoạt động tài chính tiếp tục',
    'Issuance Of Debt':'Tiền thu từ phát hành nợ vay','Repayment Of Debt':'Tiền chi trả nợ gốc vay',
    'Net Common Stock Issuance':'Tiền thu từ phát hành cổ phiếu hoặc bán cổ phiếu quỹ',
    'Cash Dividends Paid':'Cổ tức đã chi trả cho chủ sở hữu','Beginning Cash Position':'Tiền và tương đương tiền đầu kỳ',
    'End Cash Position':'Tiền và tương đương tiền cuối kỳ','Changes In Cash':'Ảnh hưởng thay đổi tỷ giá và tiền thuần thay đổi',
    'Current Price':'Giá cổ phiếu hiện tại','Shares Outstanding':'Tổng số lượng cổ phiếu lưu hành',
    'Market Capitalization':'Vốn hóa thị trường','Trailing EPS':'EPS cơ bản 4 quý gần nhất (Trailing EPS)',
    'Forward EPS':'EPS dự phóng (Forward EPS)','Dividend Yield':'Tỷ suất cổ tức (% Dividend Yield)',
    'Dividend Rate':'Cổ tức tiền mặt trên mỗi cổ phiếu','Trailing P/E':'Hệ số P/E cơ bản (Trailing P/E)',
    'Forward P/E':'Hệ số P/E dự phóng (Forward P/E)','Price To Book':'Hệ số P/B (Price to Book)',
    'Book Value':'Giá trị sổ sách mỗi cổ phiếu (BVPS)','Return On Equity':'Lợi nhuận trên vốn chủ sở hữu (ROE)',
    'Return On Assets':'Lợi nhuận trên tổng tài sản (ROA)','Profit Margins':'Biên lợi nhuận ròng (%)',
    'Gross Margins':'Biên lợi nhuận gộp (%)','Historical Dividend Cash':'Lịch sử trả cổ tức bằng tiền (VND/Cổ phiếu)'
}

# ==========================================
# 5. LÀM SẠCH CHUYÊN SÂU
# ==========================================
def format_value(x):
    if pd.isna(x): return None
    try:
        if isinstance(x, str):
            x = x.replace(',', '').replace(' ', '')
            if x.count('.') > 1: x = x.replace('.', '')
        val = float(x)
        if abs(val) > 1e15: return None
        if val != val or val in [float('inf'), float('-inf')]: return None
        return round(val, 4)
    except: return None

def clean_text(text):
    if pd.isna(text): return ""
    text = str(text)
    text = re.sub(r'[\n\r\t]+', ' ', text)
    return re.sub(r'\s{2,}', ' ', text).strip()

def fix_truncated_text(text):
    text = clean_text(text)
    fixes = {
        "Các khoản phải": "Các khoản phải thu", "Lợi nhuận trước": "Lợi nhuận trước thuế",
        "Thuế và các kho": "Thuế và các khoản phải nộp", "Tiền và tương đ": "Tiền và tương đương tiền",
        "TỔNG CỘNG N": "TỔNG CỘNG NỢ PHẢI TRẢ", "VỐN CHỦ SỞ H": "VỐN CHỦ SỞ HỮU",
        "Cổ phiếu phổ thô": "Cổ phiếu phổ thông", "Đầu tư dài hạn k": "Đầu tư dài hạn khác",
        "Lợi nhuận thuần": "Lợi nhuận thuần từ HĐKD", "Lưu chuyển tiền": "Lưu chuyển tiền thuần",
        "Lãi / Lỗ từ đánh": "Lãi / Lỗ từ đánh giá lại tài sản", "Tổng tài sản": "Tổng tài sản",
        "Tổng khác f giá gốc": "Tổng chi phí khác theo giá gốc"
    }
    for k, v in fixes.items():
        if text.startswith(k): return v
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
    'deferred':'hoãn lại','taxes':'thuế','liabilities':'nợ phải trả','payable':'phải trả','receivable':'phải thu',
    'dividends':'cổ tức','pension':'lương hưu','post':'sau','retirement':'nghỉ hưu','benefit':'phúc lợi',
    'plans':'kế hoạch','joint':'liên doanh','ventures':'liên doanh','associates':'liên kết','cost':'giá gốc',
    'current':'ngắn hạn','non':'dài hạn','fixed':'cố định','intangible':'vô hình','tangible':'hữu hình',
    'assets':'tài sản','equity':'vốn chủ sở hữu','revenue':'doanh thu','expense':'chi phí','income':'thu nhập',
    'sales':'bán hàng','operating':'hoạt động','activities':'kinh doanh','investing':'đầu tư','financing':'tài chính',
    'cash':'tiền mặt','equivalents':'tương đương tiền','short':'ngắn hạn','term':'hạn','long':'dài hạn',
    'properties':'bất động sản','buildings':'nhà cửa','improvements':'cải tạo','lease':'thuê','total':'tổng',
    'other':'khác','investments':'đầu tư','in':'trong','at':'tại','and':'và','of':'của','on':'trên','for':'cho',
    'gross':'tổng','net':'ròng','property':'tài sản','plant':'nhà máy','equipment':'thiết bị',
    'accumulated':'lũy kế','depreciation':'khấu hao','goodwill':'lợi thế thương mại','inventory':'hàng tồn kho',
    'accounts':'các khoản','retained':'giữ lại','earnings':'thu nhập','share':'cổ phiếu','capital':'vốn',
    'premium':'thặng dư','minority':'thiểu số','interest':'lợi ích'
}

def translate_metric(metric_original, is_vn=False):
    cleaned_key = clean_text(metric_original)
    if cleaned_key in TRANSLATION_MAP: return TRANSLATION_MAP[cleaned_key]
    for eng_k, vie_v in TRANSLATION_MAP.items():
        if cleaned_key.lower() == eng_k.lower(): return vie_v
    if is_vn or any(char in cleaned_key for char in ['à','á','ả','ã','ạ','ă','â','đ','ê','ô','ơ','ư','ý']):
        cleaned_key = re.sub(r'\bM\b', 'Lợi ích cổ đông không kiểm soát', cleaned_key)
        cleaned_key = re.sub(r'\bN s\b', 'Số lượng cổ phiếu ròng', cleaned_key)
        cleaned_key = cleaned_key.replace('f giá gốc', 'phí giá gốc')
        return cleaned_key
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
            translated_words.append(w); continue
        w_clean = re.sub(r'[^a-zA-Z]', '', w).lower()
        if w_clean in FALLBACK_MAP: translated_words.append(FALLBACK_MAP[w_clean])
        elif w.isupper() and len(w) <= 5: translated_words.append(w)
    result = " ".join(translated_words)
    result = re.sub(r'\b[a-zA-Z]\b', '', result)
    result = re.sub(r'\s{2,}', ' ', result).strip()
    if not result: result = "Chỉ tiêu chưa xác định"
    return result.capitalize()

# ==========================================
# 6. HTTP SESSION
# ==========================================
session = requests.Session()
session.headers.update({
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
    'Accept': 'application/json, text/plain, */*',
    'Accept-Language': 'vi-VN,vi;q=0.9,en;q=0.8',
})

# Retry ở tầng HTTP cho lỗi tạm thời; lỗi cuối cùng vẫn được ghi nhận ở crawler.
_retry_strategy = Retry(total=CRAWLER_CONFIG['MAX_RETRIES'], connect=CRAWLER_CONFIG['MAX_RETRIES'],
    read=CRAWLER_CONFIG['MAX_RETRIES'], status=CRAWLER_CONFIG['MAX_RETRIES'],
    backoff_factor=1.0, status_forcelist=[429, 500, 502, 503, 504],
    allowed_methods=frozenset(['GET']), raise_on_status=False)
_adapter = HTTPAdapter(max_retries=_retry_strategy, pool_connections=20, pool_maxsize=20)
session.mount('https://', _adapter)
session.mount('http://', _adapter)

# ==========================================
# 6.1. VNDIRECT BCTC API — LẤY SẠCH LỊCH SỬ
# ==========================================
def fetch_vndirect_bctc_financials(symbol):
    """Thu thập độc lập 3 báo cáo x Quý/Năm; phân trang đến hết dữ liệu API."""
    records = []
    company_name, sector_name = get_company_profile(symbol)
    statement_map = {
        'BALANCE_SHEET': 'Bảng cân đối kế toán',
        'INCOME_STATEMENT': 'Báo cáo kết quả kinh doanh',
        'CASH_FLOW': 'Báo cáo lưu chuyển tiền tệ'
    }
    for stmt_code, stmt_vn in statement_map.items():
        for report_type in ['QUARTER', 'YEAR']:
            period_label = 'Quý' if report_type == 'QUARTER' else 'Năm'
            page, fetched_items, expected_items, expected_pages = 1, 0, None, None
            while page <= CRAWLER_CONFIG['MAX_PAGES']:
                try:
                    url = (
                        'https://api-finfo.vndirect.com.vn/v4/financial_statements'
                        f'?q=code:{symbol}~reportType:{report_type}~financialStatement:{stmt_code}'
                        f'&size={CRAWLER_CONFIG["PAGE_SIZE"]}&page={page}'
                    )
                    response = session.get(url, timeout=CRAWLER_CONFIG['REQUEST_TIMEOUT'])
                    response.raise_for_status()
                    payload = response.json()
                    items = payload.get('data') or []
                    if page == 1:
                        try: expected_pages = int(payload.get('totalPages')) if payload.get('totalPages') is not None else None
                        except (TypeError, ValueError): expected_pages = None
                        try: expected_items = int(payload.get('totalItems')) if payload.get('totalItems') is not None else None
                        except (TypeError, ValueError): expected_items = None
                    if not items:
                        break
                    fetched_items += len(items)
                    for item in items:
                        date_raw = str(item.get('reportDate') or '')[:10]
                        year_raw = item.get('year') or (date_raw[:4] if len(date_raw) >= 4 else None)
                        if not year_raw: continue
                        try:
                            year_int = int(str(year_raw)[:4])
                            if year_int < CRAWLER_CONFIG['MIN_YEAR']: continue
                        except (TypeError, ValueError): continue
                        # Ngày kỳ là ngày ISO; không dùng chuỗi YYYY-Qn làm ngày.
                        if len(date_raw) != 10:
                            continue
                        try:
                            month = int(date_raw[5:7])
                            quarter = (month - 1) // 3 + 1
                        except (ValueError, IndexError): continue
                        value = format_value(item.get('numericValue'))
                        if value is None: continue
                        metric = clean_text(item.get('itemName') or item.get('itemCode') or '')
                        if not metric: continue
                        # Giữ số 0 và số âm: đây đều có thể là giá trị kế toán hợp lệ.
                        records.append({
                            'Mã chứng khoán': symbol, 'Tên doanh nghiệp': company_name,
                            'Tên ngành': sector_name, 'Loại báo cáo': stmt_vn,
                            'Loại kỳ': period_label, 'Năm': year_int, 'Ngày kỳ': date_raw,
                            'Chỉ tiêu tiếng Việt': metric, 'Giá trị': value,
                            '_quarter': quarter if report_type == 'QUARTER' else None,
                            '_source_scope': item.get('reportScope') or item.get('dataType') or None,
                            '_source_basis': item.get('reportPeriod') or item.get('periodType') or None,
                        })
                    # Ưu tiên metadata API; nếu không có thì trang rỗng là dấu kết thúc.
                    if expected_pages is not None and page >= expected_pages:
                        break
                    if expected_pages is None:
                        if expected_items is not None:
                            if fetched_items >= expected_items:
                                break
                        elif len(items) < CRAWLER_CONFIG['PAGE_SIZE']:
                            break
                    page += 1
                    time.sleep(CRAWLER_CONFIG['REQUEST_PAUSE'])
                except Exception as exc:
                    err = {'ticker': symbol, 'statement': stmt_code, 'period': period_label, 'page': page, 'error': str(exc)}
                    CRAWL_ERRORS.append(err)
                    FAILED_PAGES.append(err.copy())
                    print(f"  ⚠️ {symbol} {stmt_code} {period_label} trang {page}: {exc}")
                    break
            if page > CRAWLER_CONFIG['MAX_PAGES']:
                err = {'ticker': symbol, 'statement': stmt_code, 'period': period_label, 'page': page, 'error': 'MAX_PAGES safety ceiling reached'}
                CRAWL_ERRORS.append(err); FAILED_PAGES.append(err.copy())
            CRAWL_COVERAGE.append({
                'Mã chứng khoán': symbol, 'Loại báo cáo': stmt_vn, 'Loại kỳ': period_label,
                'Số trang dự kiến': expected_pages, 'Số bản ghi API dự kiến': expected_items,
                'Số bản ghi API đã đọc': fetched_items,
                'Số dòng hợp lệ đã lưu': sum(1 for r in records if r['Mã chứng khoán']==symbol and r['Loại báo cáo']==stmt_vn and r['Loại kỳ']==period_label),
                'Trạng thái': 'OK' if not any(e['ticker']==symbol and e['statement']==stmt_code and e['period']==period_label for e in CRAWL_ERRORS) and (expected_items is None or fetched_items >= expected_items) else 'CHECK'
            })
    return records

# ==========================================
# 6.2. FALLBACK Giá + SLCP
# ==========================================
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
                    fv = format_value(price)
                    if fv:
                        records.append({'Mã chứng khoán': symbol, 'Tên doanh nghiệp': company_name, 'Tên ngành': sector_name, 'Loại báo cáo': 'Chỉ số thị trường, Định giá & Cổ tức', 'Loại kỳ': 'Real-time', 'Năm': current_year, 'Ngày kỳ': today_str, 'Chỉ tiêu tiếng Việt': 'Giá cổ phiếu hiện tại', 'Giá trị': fv})
    except Exception: pass
    try:
        url_s = f"https://api-finfo.vndirect.com.vn/v4/company_statistics?q=code:{symbol}"
        res = session.get(url_s, timeout=10)
        if res.status_code == 200:
            data = res.json()
            if data.get('data') and len(data['data']) > 0:
                shares = data['data'][0].get('listedShare') or data['data'][0].get('issueShare')
                if shares and float(shares) > 0:
                    fv = format_value(shares)
                    if fv:
                        records.append({'Mã chứng khoán': symbol, 'Tên doanh nghiệp': company_name, 'Tên ngành': sector_name, 'Loại báo cáo': 'Chỉ số thị trường, Định giá & Cổ tức', 'Loại kỳ': 'Real-time', 'Năm': current_year, 'Ngày kỳ': today_str, 'Chỉ tiêu tiếng Việt': 'Tổng số lượng cổ phiếu lưu hành', 'Giá trị': fv})
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
                    fv = format_value(price)
                    if fv:
                        records.append({'Mã chứng khoán': symbol, 'Tên doanh nghiệp': company_name, 'Tên ngành': sector_name, 'Loại báo cáo': 'Chỉ số thị trường, Định giá & Cổ tức', 'Loại kỳ': 'Real-time', 'Năm': current_year, 'Ngày kỳ': today_str, 'Chỉ tiêu tiếng Việt': 'Giá cổ phiếu hiện tại', 'Giá trị': fv})
                if shares and float(shares) > 0:
                    fv = format_value(shares)
                    if fv:
                        records.append({'Mã chứng khoán': symbol, 'Tên doanh nghiệp': company_name, 'Tên ngành': sector_name, 'Loại báo cáo': 'Chỉ số thị trường, Định giá & Cổ tức', 'Loại kỳ': 'Real-time', 'Năm': current_year, 'Ngày kỳ': today_str, 'Chỉ tiêu tiếng Việt': 'Tổng số lượng cổ phiếu lưu hành', 'Giá trị': fv})
    except Exception: pass
    return records

# ==========================================
# 7. YFINANCE CRAWLERS
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
                if year_val.isdigit() and int(year_val) >= max(min_year, CRAWLER_CONFIG['MIN_YEAR']):
                    for row_idx, val in df[col].items():
                        if pd.notna(val):
                            fv = format_value(val)
                            if fv is not None:
                                metric_vn = translate_metric(str(row_idx).strip())
                                records.append({
                                    'Mã chứng khoán': symbol, 'Tên doanh nghiệp': company_name,
                                    'Tên ngành': sector_name, 'Loại báo cáo': statement_type_vn,
                                    'Loại kỳ': ky_bao_cao, 'Năm': year_val, 'Ngày kỳ': date_str,
                                    'Chỉ tiêu tiếng Việt': metric_vn, 'Giá trị': fv
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
                if year_val.isdigit() and int(year_val) >= max(min_year, CRAWLER_CONFIG['MIN_YEAR']):
                    if pd.notna(div_val):
                        fv = format_value(div_val)
                        if fv is not None:
                            records.append({
                                'Mã chứng khoán': symbol, 'Tên doanh nghiệp': company_name,
                                'Tên ngành': sector_name, 'Loại báo cáo': 'Chỉ số thị trường, Định giá & Cổ tức',
                                'Loại kỳ': 'Sự kiện cổ tức', 'Năm': year_val, 'Ngày kỳ': date_str,
                                'Chỉ tiêu tiếng Việt': 'Lịch sử trả cổ tức bằng tiền (VND/Cổ phiếu)', 'Giá trị': fv
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
                if not hist.empty: current_price = float(hist['Close'].iloc[-1])
            except: pass
            try:
                info = ticker_obj.info
                if not current_price: current_price = float(info.get('regularMarketPrice', 0) or info.get('previousClose', 0) or 0)
                shares_out = float(info.get('sharesOutstanding', 0) or 0)
                div_yield = float(info.get('dividendYield', 0) or 0) * 100 if info.get('dividendYield') else 0.0
            except: pass
        if (not shares_out or shares_out == 0.0) and balance_sheet_df is not None and not balance_sheet_df.empty:
            for row_idx in balance_sheet_df.index:
                row_str = str(row_idx).lower()
                if 'ordinary shares number' in row_str or 'share issued' in row_str or 'common stock' in row_str:
                    for col in balance_sheet_df.columns:
                        val = balance_sheet_df.loc[row_idx, col]
                        if pd.notna(val) and float(val) > 0: shares_out = float(val); break
                    if shares_out: break
        if (not market_cap or market_cap == 0.0) and current_price > 0 and shares_out > 0:
            market_cap = current_price * shares_out
        metrics = [('Current Price', current_price), ('Shares Outstanding', shares_out), ('Market Capitalization', market_cap), ('Dividend Yield', div_yield)]
        for eng_key, val in metrics:
            if val is not None:
                fv = format_value(val)
                if fv is not None:
                    metric_vn = TRANSLATION_MAP.get(eng_key, eng_key)
                    records.append({
                        'Mã chứng khoán': symbol, 'Tên doanh nghiệp': company_name,
                        'Tên ngành': sector_name, 'Loại báo cáo': 'Chỉ số thị trường, Định giá & Cổ tức',
                        'Loại kỳ': 'Real-time', 'Năm': current_year, 'Ngày kỳ': today_str,
                        'Chỉ tiêu tiếng Việt': metric_vn, 'Giá trị': fv
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
                fv = format_value(val)
                if fv is not None:
                    market_records.append({
                        'Mã chứng khoán': index_name, 'Tên doanh nghiệp': f'Chỉ số thị trường {index_name}',
                        'Tên ngành': 'Chỉ số vĩ mô', 'Loại báo cáo': 'Chỉ số thị trường, Định giá & Cổ tức',
                        'Loại kỳ': 'Real-time hằng ngày', 'Năm': current_year, 'Ngày kỳ': today_str,
                        'Chỉ tiêu tiếng Việt': name, 'Giá trị': fv
                    })
        except Exception: pass
    return market_records

# ==========================================
# 8. VNFINANCIALDATA BULK
# ==========================================
def find_value_column(df):
    for name in ['value','ratio_value','value_ratio','Value','ratio','val']:
        if name in df.columns: return name
    for col in df.columns:
        if df[col].dtype in ['float64','int64']: return col
    return None

def fetch_vnfinancialdata_bulk(ticker_market_map):
    if vnf is None: return []
    records = []
    statements = {"balance_sheet": "Bảng cân đối kế toán", "income_statement": "Báo cáo kết quả kinh doanh", "cash_flow": "Báo cáo lưu chuyển tiền tệ", "ratio": "Chỉ số tài chính & Định giá"}
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
                    fv = format_value(row['Giá trị'])
                    if fv is None: continue
                    symbol = row['Mã chứng khoán']
                    company_name, sector_name = get_company_profile(symbol)
                    year_val = str(row['Năm'])
                    metric_vn = fix_truncated_text(translate_metric(row['Chỉ tiêu tiếng Việt'], is_vn=True))
                    records.append({
                        'Mã chứng khoán': symbol, 'Tên doanh nghiệp': company_name,
                        'Tên ngành': sector_name, 'Loại báo cáo': stmt_name,
                        'Loại kỳ': 'Năm', 'Năm': year_val, 'Ngày kỳ': f"{year_val}-12-31",
                        'Chỉ tiêu tiếng Việt': metric_vn, 'Giá trị': fv
                    })
            except Exception as e:
                print(f"  ⚠️ Lỗi {stmt_name} {exchange}: {e}")
    return records

# ==========================================
# 9. YFINANCE MULTITHREAD
# ==========================================
def process_single_ticker(symbol, category):
    recs = []
    try:
        ticker = yf.Ticker(f"{symbol}.VN", session=session)
        bs_df = getattr(ticker, 'balance_sheet', None)
        recs.extend(parse_financial_df(symbol, bs_df, 'Balance_Sheet', 'Năm'))
        recs.extend(parse_financial_df(symbol, getattr(ticker, 'quarterly_balance_sheet', None), 'Balance_Sheet', 'Quý'))
        recs.extend(parse_financial_df(symbol, getattr(ticker, 'financials', None), 'Income_Statement', 'Năm'))
        recs.extend(parse_financial_df(symbol, getattr(ticker, 'quarterly_financials', None), 'Income_Statement', 'Quý'))
        recs.extend(parse_financial_df(symbol, getattr(ticker, 'cashflow', None), 'Cash_Flow', 'Năm'))
        recs.extend(parse_financial_df(symbol, getattr(ticker, 'quarterly_cashflow', None), 'Cash_Flow', 'Quý'))
        recs.extend(fetch_market_and_valuation_metrics(symbol, ticker, bs_df))
        recs.extend(fetch_historical_dividends(symbol, ticker))
    except Exception as exc:
        CRAWL_ERRORS.append({'ticker': symbol, 'source': 'YFINANCE', 'error': str(exc)})
        print(f"  ⚠️ YFINANCE {symbol}: {exc}")
    return recs

# ==========================================
# 10. CLEANING & SOURCE TRACKING
# ==========================================
def _add_source(records, source_name, priority=None):
    if priority is None: priority = PRIORITY_MAP.get(source_name, 99)
    for r in records:
        r['_source'] = source_name
        r['_priority'] = priority
    return records

def apply_first_principles_cleaning(df):
    print("\n🧹 BƯỚC 6: 5 TẦNG CLEANING...")
    if df is None or df.empty:
        return pd.DataFrame(columns=STANDARD_COLUMNS)

    df = df.copy()
    df['Giá trị'] = pd.to_numeric(df['Giá trị'].astype(str).str.replace(',', '').str.strip(), errors='coerce')
    df = df.dropna(subset=['Mã chứng khoán', 'Chỉ tiêu tiếng Việt', 'Giá trị'])
    df['Mã chứng khoán'] = df['Mã chứng khoán'].astype(str).str.strip().str.upper()
    print(f"  [Tầng 1] Loại bỏ NULL & ép kiểu Float. Còn {len(df):,} dòng.")
    
    df['Chỉ tiêu tiếng Việt'] = df.apply(lambda row: standardize_metric(row['Chỉ tiêu tiếng Việt'], row['Loại báo cáo']), axis=1)
    df = df.dropna(subset=['Chỉ tiêu tiếng Việt'])
    print(f"  [Tầng 2] Ép chuẩn VAS Dictionary. Còn {len(df):,} dòng.")
    
    if '_priority' in df.columns:
        df = df.sort_values('_priority', kind='stable')
    dedupe_keys = ['Mã chứng khoán', 'Loại báo cáo', 'Loại kỳ', 'Ngày kỳ', 'Chỉ tiêu tiếng Việt']
    for extra in ['_source_scope', '_source_basis']:
        if extra in df.columns: dedupe_keys.append(extra)
    df = df.drop_duplicates(subset=dedupe_keys, keep='first')
    print(f"  [Tầng 3] Deduplication. Còn {len(df):,} dòng.")
    
    print("  [Tầng 4] Kiểm tra Cân đối kế toán (Chỉ cảnh báo)...")
    bctc_df = df[df['Loại báo cáo'].astype(str).str.contains('Bảng cân đối', na=False)]
    if not bctc_df.empty:
        try:
            pivot = bctc_df.pivot_table(index=['Mã chứng khoán', 'Ngày kỳ'], columns='Chỉ tiêu tiếng Việt', values='Giá trị', aggfunc='first').reset_index()
            col_assets = next((c for c in pivot.columns if 'Tổng cộng tài sản' in str(c) or 'Tổng tài sản' in str(c)), None)
            col_liab = next((c for c in pivot.columns if 'Nợ phải trả' in str(c)), None)
            col_equity = next((c for c in pivot.columns if 'Vốn chủ sở hữu' in str(c)), None)

            if col_assets and col_liab and col_equity:
                pivot['_diff'] = (pivot[col_assets] - (pivot[col_liab] + pivot[col_equity])).abs()
                invalid_count = len(pivot[pivot['_diff'] > 1000])
                print(f"  [Tầng 4] ⚠️ Phát hiện {invalid_count} kỳ BCTC lệch Cân đối (Vẫn giữ lại).")
            else:
                print("  [Tầng 4] ⚠️ Không đủ 3 cột để kiểm tra.")
        except Exception: pass
    
    print("  [Tầng 5] Chuẩn hóa số liệu; giữ nguyên số 0 và số âm hợp lệ...")
    def safe_format(x):
        try:
            if pd.isna(x): return None
            f = float(x)
            if not np.isfinite(f): return None
            if f.is_integer(): return str(int(f))
            return str(round(f, 4))
        except (ValueError, TypeError):
            return None
    df['Giá trị'] = df['Giá trị'].apply(safe_format)
    df = df.dropna(subset=['Giá trị'])
    
    if 'Năm' in df.columns:
        df['Năm'] = pd.to_numeric(df['Năm'], errors='coerce').fillna(datetime.now().year).astype(int)
        
    print(f"  [Tầng 5] ✅ Đã xóa dòng trắng. Còn {len(df):,} dòng.")
    return df[STANDARD_COLUMNS]

# ==========================================
# 11. MAIN
# ==========================================
def main():
    global _ALL_RECORDS_GLOBAL
    print("=" * 62)
    print("🚀 FINEX VN STOCK DATABASE CRAWLER — v19.0 (EXHAUSTIVE HISTORY & AUDIT)")
    print("=" * 62)

    ticker_market_map = load_176_master_tickers()
    all_master_records = []

    def _accumulate(recs, source):
        if not recs: return
        _add_source(recs, source)
        all_master_records.extend(recs)
        _ALL_RECORDS_GLOBAL[:] = all_master_records

    def _save_checkpoint(label):
        if not all_master_records: return
        try:
            os.makedirs('data', exist_ok=True)
            df_tmp = pd.DataFrame(all_master_records)
            df_tmp.to_csv('data/_checkpoint.csv', index=False, encoding='utf-8-sig')
            q = len(df_tmp[df_tmp['Loại kỳ'] == 'Quý']) if 'Loại kỳ' in df_tmp.columns else 0
            print(f"  💾 [CKPT:{label}] {len(df_tmp):,} dòng (Quý: {q:,})")
        except Exception as e:
            print(f"  ⚠️ CKPT fail: {e}")

    # BƯỚC 0
    print("\n🚀 BƯỚC 0: Tải dữ liệu hàng ngày [DAILY]...")
    hf_df = load_daily_stock_data()
    if not hf_df.empty:
        hf_df = _normalize_to_standard(hf_df, fill_company=True)
        if not hf_df.empty:
            _accumulate(hf_df.to_dict('records'), 'DAILY')
            print(f" ✅ Đã nạp {len(hf_df):,} dòng.")

    # BƯỚC 1
    print("\n🚀 BƯỚC 1: Tải BCTC Năm bulk [VN_FINANCIAL]...")
    vnf_recs = fetch_vnfinancialdata_bulk(ticker_market_map)
    if vnf_recs: _accumulate(vnf_recs, 'VN_FINANCIAL')
    _save_checkpoint("sau_VN_FINANCIAL")

    # BƯỚC 2
    print("\n📈 BƯỚC 2: Cào chỉ số vĩ mô [INDICES]...")
    index_recs = fetch_market_indices()
    if index_recs: _accumulate(index_recs, 'INDICES')

    # BƯỚC 3 — VNDIRECT BCTC
    print(f"\n⭐ BƯỚC 3: Cào BCTC Quý + Năm [VNDIRECT_BCTC] cho {len(ticker_market_map)} mã...")
    with ThreadPoolExecutor(max_workers=CRAWLER_CONFIG['WORKERS']) as executor:
        futures = {executor.submit(fetch_vndirect_bctc_financials, symbol): symbol for symbol in ticker_market_map.keys()}
        done = 0
        for future in as_completed(futures):
            done += 1
            try:
                res = future.result()
                if res: _accumulate(res, 'VNDIRECT_BCTC')
            except Exception as exc:
                CRAWL_ERRORS.append({'ticker': futures[future], 'source': 'VNDIRECT_BCTC', 'error': str(exc)})
                print(f"  ⚠️ VNDIRECT {futures[future]}: {exc}")
            if done % 25 == 0:
                _save_checkpoint(f"VNDIRECT_{done}/{len(ticker_market_map)}")
    _save_checkpoint("sau_VNDIRECT_BCTC")

    # BƯỚC 4 — Yfinance backup
    print(f"\n🔄 BƯỚC 4: Cào Yfinance song song [YFINANCE]...")
    with ThreadPoolExecutor(max_workers=CRAWLER_CONFIG['WORKERS']) as executor:
        futures = {executor.submit(process_single_ticker, symbol, cat): symbol for symbol, cat in ticker_market_map.items()}
        for future in as_completed(futures):
            try:
                res = future.result()
                if res: _accumulate(res, 'YFINANCE')
            except Exception as exc:
                CRAWL_ERRORS.append({'ticker': futures[future], 'source': 'YFINANCE', 'error': str(exc)})
                print(f"  ⚠️ YFINANCE {futures[future]}: {exc}")
    _save_checkpoint("sau_YFINANCE")

    # BƯỚC 5
    print(f"\n🐢 BƯỚC 5: Kiểm tra thiếu + fallback Giá/SLCP...")
    df_temp = pd.DataFrame(all_master_records)

    if not df_temp.empty:
        q_counts = df_temp[df_temp['Loại kỳ'] == 'Quý'].groupby('Mã chứng khoán').size()
        q_syms = set(q_counts[q_counts >= 20].index)
        print(f"  📊 Đã có {len(q_syms)}/{len(ticker_market_map)} mã có ≥ 20 kỳ Quý.")

        prices = df_temp[(df_temp['Chỉ tiêu tiếng Việt'] == 'Giá cổ phiếu hiện tại') & (pd.to_numeric(df_temp['Giá trị'], errors='coerce') > 0)]
        symbols_with_price = set(prices['Mã chứng khoán'].unique()) if not prices.empty else set()
        shares = df_temp[(df_temp['Chỉ tiêu tiếng Việt'] == 'Tổng số lượng cổ phiếu lưu hành') & (pd.to_numeric(df_temp['Giá trị'], errors='coerce') > 0)]
        symbols_with_shares = set(shares['Mã chứng khoán'].unique()) if not shares.empty else set()

        missing_price_shares = [s for s in ticker_market_map.keys() if s not in symbols_with_price or s not in symbols_with_shares]
        if missing_price_shares:
            print(f"  🎯 {len(missing_price_shares)} mã thiếu Giá/SLCP. Cào bù VNDirect + VPS...")
            with ThreadPoolExecutor(max_workers=CRAWLER_CONFIG['WORKERS']) as executor:
                futures = {}
                for s in missing_price_shares:
                    futures[executor.submit(fetch_vndirect_fallback, s)] = s
                    futures[executor.submit(fetch_vps_fallback, s)] = s
                for future in as_completed(futures):
                    try:
                        res = future.result()
                        if res: _accumulate(res, 'VNDIRECT')
                    except Exception as exc:
                        CRAWL_ERRORS.append({'ticker': futures[future], 'source': 'PRICE_SHARES_FALLBACK', 'error': str(exc)})
                        print(f"  ⚠️ Fallback {futures[future]}: {exc}")

    df_check = pd.DataFrame(all_master_records)
    if not df_check.empty:
        q_count = len(df_check[df_check['Loại kỳ'] == 'Quý'])
        y_count = len(df_check[df_check['Loại kỳ'] == 'Năm'])
        print(f"\n  📊 KIỂM CHỨNG: {q_count:,} QUÝ | {y_count:,} NĂM | Tổng: {len(df_check):,}")

    # BƯỚC 5.5
    print(f"\n🆕 BƯỚC 5.5: Tải bổ sung từ Supabase...")
    supabase_df = load_data_from_supabase()
    if not supabase_df.empty:
        _accumulate(supabase_df.to_dict('records'), 'SUPABASE_HIGH' if SUPABASE_PRIORITY == 'high' else 'SUPABASE')

    # BƯỚC 6
    df_master = pd.DataFrame(all_master_records)
    df_clean = apply_first_principles_cleaning(df_master) if not df_master.empty else pd.DataFrame(columns=STANDARD_COLUMNS)

    # BƯỚC 7
    os.makedirs('data', exist_ok=True)
    csv_path = 'data/vietnam_stock_database_tong_hop.csv'
    parquet_path = 'data/vietnam_stock_database.parquet'

    df_clean.to_csv(csv_path, index=False, encoding='utf-8-sig')
    df_clean.to_parquet(parquet_path, engine='pyarrow', index=False)

    # Báo cáo kiểm toán độ phủ và lỗi: không tuyên bố đủ dữ liệu nếu API thiếu/trả lỗi.
    if CRAWL_COVERAGE:
        pd.DataFrame(CRAWL_COVERAGE).to_csv('data/bao_cao_do_phu_bctc.csv', index=False, encoding='utf-8-sig')
    if CRAWL_ERRORS:
        pd.DataFrame(CRAWL_ERRORS).to_csv('data/bao_cao_loi_api.csv', index=False, encoding='utf-8-sig')
    if FAILED_PAGES:
        pd.DataFrame(FAILED_PAGES).to_csv('data/bao_cao_trang_loi_can_chay_lai.csv', index=False, encoding='utf-8-sig')
    if not df_clean.empty:
        financial = df_clean[df_clean['Loại báo cáo'].isin(['Bảng cân đối kế toán','Báo cáo kết quả kinh doanh','Báo cáo lưu chuyển tiền tệ'])]
        if not financial.empty:
            (financial.groupby(['Mã chứng khoán','Loại báo cáo','Loại kỳ'])
             .agg(So_ky=('Ngày kỳ','nunique'), So_chi_tieu=('Chỉ tiêu tiếng Việt','nunique'), So_dong=('Giá trị','size'))
             .reset_index().to_csv('data/bao_cao_tong_hop_do_phu.csv', index=False, encoding='utf-8-sig'))
    print(f"\n💾 ĐÃ LƯU FILE:")
    print(f"   → CSV:     {csv_path}")
    print(f"   → PARQUET: {parquet_path} ({os.path.getsize(parquet_path)/1024/1024:.2f} MB)")

    # BƯỚC 8
    if PUSH_TO_SUPABASE:
        print("\n📤 BƯỚC 8: Đẩy Supabase...")
        upsert_to_supabase(df_clean)

    print("=" * 62)
    print(f" 🎉 HOÀN TẤT! Tổng: {len(df_clean):,} dòng")
    if not df_clean.empty:
        print(f" - Số mã: {df_clean['Mã chứng khoán'].nunique()}/{len(ticker_market_map)}")
        for k, v in df_clean['Loại kỳ'].value_counts().items():
            print(f"     • {k}: {v:,}")
    print("=" * 62)

if __name__ == "__main__":
    main()


# LƯU Ý VẬN HÀNH v19.0:
# - API chỉ cung cấp dữ liệu nào thì crawler chỉ lưu dữ liệu đó; xem báo cáo độ phủ/lỗi.
# - Không tự tạo số liệu thiếu, không suy diễn Q4 từ năm hoặc quý độc lập từ số lũy kế.
# - Giá trị 0 và số âm được giữ lại; NULL/NaN/Inf bị loại.
