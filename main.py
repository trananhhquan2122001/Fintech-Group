"""
FINEX VN STOCK DATABASE CRAWLER - v17.4 (GIỮ NGUYÊN 100% KHUNG v17.3 — CHUẨN ĐƠN VỊ KHI CÀO + TÍNH CHỈ SỐ ĐỊNH GIÁ)
================================================================================
Changelog v17.4 (nâng cấp tại chỗ trên khung v17.3, KHÔNG cắt dòng gốc nào):
  ✅ FIX ảnh 1 (giá 36.166.511.658.185 VNĐ/cp): chuẩn đơn vị NGAY KHI CÀO —
     norm_price (100 -> 5.000.000 VNĐ/cp), norm_shares (nguồn trả "triệu cp" -> x1e6,
     ngoài 1e6..5e11 -> bỏ), norm_market_cap (nguồn trả "tỷ đồng" -> x1e9, lệch
     giá x SLCP >50% -> lấy giá x SLCP). Ngoài thang -> BỎ, không vào DB/Supabase.
  ✅ FIX ảnh 2 (P/E, P/B, ROE đầy số 0 / vốn hoá 31.648.108 tỷ): BƯỚC 6.5 mới
     compute_derived_valuation_metrics() dùng pandas/numpy tính EPS, BVPS, ROE,
     ROA, biên ròng/gộp, P/E, P/B, vốn hoá cho từng (mã, kỳ, ngày kỳ);
     np.errstate chống chia 0; CHỈ sinh dòng khi mẫu số khác 0 -> hết dòng 0.
  ✅ Cleaning Tầng 1 chuẩn đơn vị lại lần nữa cho 3 nhãn giá/SLCP/vốn hoá
     (chặn cả dữ liệu cũ nạp từ Supabase).
  ✅ fetch_market_and_valuation_metrics / fallback VNDirect+VPS dùng norm_*;
     thiếu giá nhưng có vốn hoá+SLCP -> suy ra giá = vốn hoá / SLCP (có kiểm thang).
  ✅ Giữ nguyên 100%: từ điển VAS/ALIAS/TRANSLATION/EXTRA v17.3, purge Supabase,
     SKIP_VNDIRECT, bù quý 8 luồng, 5 tầng cleaning, coverage + unmapped report,
     dọn file tạm, emergency save, khung BƯỚC 0->8.
================================================================================
Changelog v17.3 (giữ nguyên):
  ✅ Mọi chỉ tiêu đi qua bộ dịch ở BƯỚC 6 (Tầng 2) -> không còn nhãn tiếng Anh.
  ✅ EXTRA_TRANSLATION_MAP ~300 nhãn; tra cứu không phân biệt hoa/thường.
  ✅ fix_yfinance_typos không chẻ chữ đúng; translate_metric chống nhãn rác + cache.
  ✅ standardize_metric bỏ [2], gộp chữ HOA; format_value int không đuôi .0.
  ✅ Supabase: purge dòng 0/NULL/rác/tiếng Anh trước upsert; tải bỏ sẵn value=0.
================================================================================
"""
import os
import socket
socket.setdefaulttimeout(15)   # v17.2: timeout ngắn để mã lỗi bị bỏ qua nhanh

import glob
import signal
import sys
import time
import threading
import random
from datetime import datetime
import pandas as pd
import numpy as np
import requests
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from requests.adapters import HTTPAdapter

# ==============================================================================
# 🛡️ BẮT SIGTERM (CHỐNG TREO) — GIỮ NGUYÊN
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

# 🆕 v17.3: bổ sung alias tiếng Việt (nhãn chữ HOA của ngân hàng / nhãn đã dịch từ Yahoo) về chuẩn VAS
ALIAS_TO_VAS.update({
    "Nợ phải trả và vốn chủ sở hữu": "Tổng cộng nguồn vốn",
    "Tổng cộng nợ phải trả và vốn chủ sở hữu": "Tổng cộng nguồn vốn",
    "Tổng nguồn vốn": "Tổng cộng nguồn vốn",
    "Tổng tài sản": "Tổng cộng tài sản",
    "Tổng nợ phải trả": "Nợ phải trả",
})

# 🆕 v17.3: bảng tra không phân biệt hoa/thường + nhận diện nhãn tiếng Anh
_VAS_LOWER = {m.lower(): m for m in VAS_WHITELIST}
_ALIAS_LOWER = {k.lower(): v for k, v in ALIAS_TO_VAS.items()}
_VN_CHARS = re.compile(r'[àáảãạăằắẳẵặâầấẩẫậèéẻẽẹêềếểễệìíỉĩịòóỏõọôồốổỗộơờớởỡợùúủũụưừứửữựỳýỷỹỵđ]', re.IGNORECASE)
UNKNOWN_METRIC = "Chỉ tiêu chưa xác định"
_STOP_VN = {'của', 'và', 'trên', 'cho', 'tại', 'trong', 'sau', 'hạn'}
_JUNK_METRICS = {'', 'của', 'và', 'trên', 'cho', 'tại', 'trong', 'nan', 'none', 'null', UNKNOWN_METRIC.lower()}
_UNMAPPED_METRICS = set()   # nhãn tiếng Anh chưa có trong từ điển (xuất ra data/_unmapped_metrics.csv)

def _looks_english(s):
    s = str(s)
    return (not _VN_CHARS.search(s)) and re.search(r'[A-Za-z]{3,}', s) is not None

def standardize_metric(raw_metric, report_type):
    if pd.isna(raw_metric): return None
    metric = clean_text(raw_metric)
    if not metric: return None
    metric = re.sub(r'\s*\[\d+\]\s*$', '', metric).strip()   # 🆕 v17.3: bỏ hậu tố [2] của vnfinancialdata
    if not metric: return None

    if "Chỉ số thị trường" in str(report_type) or "Chỉ số vĩ mô" in str(report_type):
        return translate_metric(metric) if _looks_english(metric) else metric
    
    if metric in VAS_WHITELIST: return metric
    if metric in ALIAS_TO_VAS: return ALIAS_TO_VAS[metric]
    
    metric_no_code = re.sub(r'\s*\(\d+[a-z]?\)\s*$', '', metric)
    if metric_no_code in VAS_WHITELIST: return metric_no_code
    if metric_no_code in ALIAS_TO_VAS: return ALIAS_TO_VAS[metric_no_code]
    
    # 🆕 v17.3: so khớp không phân biệt hoa/thường (thay vòng for chậm, kết quả tương đương)
    for cand in (metric.lower(), metric_no_code.lower()):
        if cand in _ALIAS_LOWER: return _ALIAS_LOWER[cand]
        if cand in _VAS_LOWER: return _VAS_LOWER[cand]

    # 🆕 v17.3: nhãn CHỮ HOA -> thường rồi so khớp lại
    if metric_no_code.isupper() and len(metric_no_code) > 3:
        metric_no_code = metric_no_code[:1] + metric_no_code[1:].lower()
        if metric_no_code in VAS_WHITELIST: return metric_no_code
        if metric_no_code in ALIAS_TO_VAS: return ALIAS_TO_VAS[metric_no_code]

    # 🆕 v17.3: còn tiếng Anh -> dịch qua từ điển rồi chuẩn VAS lần nữa
    if _looks_english(metric_no_code):
        vi = translate_metric(metric_no_code)
        if vi in VAS_WHITELIST: return vi
        if vi in ALIAS_TO_VAS: return ALIAS_TO_VAS[vi]
        if vi.lower() in _ALIAS_LOWER: return _ALIAS_LOWER[vi.lower()]
        if vi.lower() in _VAS_LOWER: return _VAS_LOWER[vi.lower()]
        return vi
            
    return metric_no_code


# ==========================================
# 2. API KEY & CÀI ĐẶT THƯ VIỆN (GIỮ NGUYÊN)
# ==========================================
os.environ["VNSTOCK_API_KEY"] = "vnstock_533590cc17b6737ceb7c9f147471f31f"

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

# v17.2: ĐÃ XOÁ khối tự động `pip install vnstock`.

# ==========================================
# 🆕 1.5 SUPABASE INTEGRATION (GIỮ NGUYÊN, thêm dọn dòng rác)
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
# 🆕 v17.3: tự dọn dòng value=0 / NULL / item_vn rỗng-rác-tiếng Anh trên Supabase trước khi upsert (chỉ chạy khi PUSH_TO_SUPABASE=true)
SUPABASE_PURGE = os.environ.get("SUPABASE_PURGE", "true").strip().lower() in ("1", "true", "yes", "y")

# CÔNG TẮC TẮT NHÁNH VNDIRECT (BCTC + fallback giá/SLCP qua api-finfo). Mặc định = TẮT.
SKIP_VNDIRECT = os.environ.get("SKIP_VNDIRECT", "true").strip().lower() in ("1", "true", "yes", "y")

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
    'INDICES': 2, 'YF_QUARTER': 3, 'YFINANCE': 3, 'VNDIRECT': 3, 'VPS': 3, 'SUPABASE': 4,
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
            # 🆕 v17.3: bỏ sẵn các dòng value = 0 ngay khi tải
            resp = client.table(SUPABASE_TABLE).select("*").neq("value", 0).range(start, start + page_size - 1).execute()
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

# 🆕 v17.3: DỌN DÒNG TRỐNG / RÁC / TIẾNG ANH TRÊN SUPABASE
_DB_JUNK_ITEMS = ['Của', 'Và', 'Trên', 'Cho', 'Tại', 'Trong', UNKNOWN_METRIC]
_ASCII_ONLY_REGEX = r"^[A-Za-z0-9 ,.&()/:'%+\[\]\-]+$"   # item_vn chỉ gồm ký tự ASCII = nhãn tiếng Anh

def purge_bad_rows_supabase():
    """Xoá: value=0, value NULL, item_vn rỗng/NULL, item_vn rác, item_vn tiếng Anh. Lỗi bước nào bỏ qua bước đó."""
    client = init_supabase()
    if client is None: return False
    T = SUPABASE_TABLE
    tasks = [
        ("value = 0",             lambda: client.table(T).delete().eq('value', 0)),
        ("value NULL",            lambda: client.table(T).delete().is_('value', 'null')),
        ("item_vn rỗng",          lambda: client.table(T).delete().eq('item_vn', '')),
        ("item_vn NULL",          lambda: client.table(T).delete().is_('item_vn', 'null')),
        ("item_vn rác (Của/Và…)", lambda: client.table(T).delete().in_('item_vn', _DB_JUNK_ITEMS)),
        ("item_vn tiếng Anh",     lambda: client.table(T).delete().filter('item_vn', 'match', _ASCII_ONLY_REGEX)),
    ]
    print("\n🧽 [SUPABASE] Dọn dòng trống/rác/tiếng Anh...")
    ok_all = True
    for label, build in tasks:
        try:
            _retry(lambda b=build: b().execute(), max_retries=2, label=f"SUPABASE_PURGE:{label}")
            print(f"   ✓ Đã dọn: {label}")
        except Exception as e:
            ok_all = False
            print(f"   ⚠️ Bỏ qua '{label}' ({type(e).__name__}: {str(e)[:120]}) — có thể chạy SQL thủ công trong Supabase SQL Editor.")
    return ok_all

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
            if pd.isna(val) or val == 0: continue
            
            yr = pd.to_numeric(row['year'], errors='coerce')
            yr = int(yr) if pd.notna(yr) else datetime.now().year
            
            def clean_str(s):
                if pd.isna(s): return None
                s = str(s).strip()
                return s if s else None

            item_clean = clean_str(row['item_vn'])
            if not item_clean or item_clean.lower() in _JUNK_METRICS: continue   # 🆕 v17.3: không đẩy dòng nhãn trống/rác lên Supabase
                
            r = {
                'ticker': ticker,
                'company_name': clean_str(row['company_name']),
                'sector': clean_str(row['sector']),
                'report_type': clean_str(row['report_type']),
                'period_type': clean_str(row['period_type']),
                'year': yr,
                'report_date': clean_str(row['report_date']),
                'item_vn': item_clean,
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
# 2. TẢI DỮ LIỆU HÀNG NGÀY (GIỮ NGUYÊN)
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
# 3. DANH SÁCH 176 MÃ & THÔNG TIN DOANH NGHIỆP (GIỮ NGUYÊN 100%)
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
# 4. TRANSLATION MAP (GIỮ NGUYÊN 100%) + 🆕 v17.3 EXTRA_TRANSLATION_MAP
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

# 🆕 v17.3: BỘ TỪ ĐIỂN BỔ SUNG — toàn bộ nhãn yfinance còn thiếu + nhãn tiếng Anh của ngân hàng/vnfinancialdata.
#           Chỉ THÊM khóa chưa có (không ghi đè từ điển gốc).
EXTRA_TRANSLATION_MAP = {
    # ---- Bảng cân đối kế toán ----
    'Treasury Shares Number':'Số lượng cổ phiếu quỹ','Treasury Stock':'Cổ phiếu quỹ',
    'Tangible Book Value':'Giá trị sổ sách hữu hình','Invested Capital':'Vốn đầu tư',
    'Net Tangible Assets':'Tài sản hữu hình ròng','Capital Lease Obligations':'Nghĩa vụ thuê tài chính',
    'Common Stock Equity':'Vốn chủ sở hữu cổ phiếu phổ thông',
    'Total Capitalization':'Tổng vốn hóa (vốn chủ sở hữu và nợ dài hạn)',
    'Other Equity Adjustments':'Điều chỉnh vốn chủ sở hữu khác','Preferred Stock':'Cổ phiếu ưu đãi',
    'Other Capital Stock':'Vốn cổ phần khác','Preferred Securities Outside Stock Equity':'Chứng khoán ưu đãi ngoài vốn chủ sở hữu',
    'Non Current Deferred Liabilities':'Nợ hoãn lại dài hạn','Non Current Deferred Revenue':'Doanh thu chưa thực hiện dài hạn',
    'Non Current Deferred Taxes Liabilities':'Thuế thu nhập hoãn lại phải trả dài hạn',
    'Long Term Debt And Capital Lease Obligation':'Vay và nợ thuê tài chính dài hạn (gồm thuê tài chính)',
    'Long Term Capital Lease Obligation':'Nợ thuê tài chính dài hạn',
    'Current Deferred Liabilities':'Nợ hoãn lại ngắn hạn','Current Deferred Revenue':'Doanh thu chưa thực hiện ngắn hạn',
    'Current Debt And Capital Lease Obligation':'Vay và nợ thuê tài chính ngắn hạn (gồm thuê tài chính)',
    'Current Capital Lease Obligation':'Nợ thuê tài chính ngắn hạn','Other Current Borrowings':'Vay ngắn hạn khác',
    'Commercial Paper':'Thương phiếu','Line Of Credit':'Hạn mức tín dụng',
    'Pensionand Other Post Retirement Benefit Plans Current':'Quỹ phúc lợi nhân viên ngắn hạn',
    'Payables And Accrued Expenses':'Phải trả và chi phí phải trả','Income Tax Payable':'Thuế thu nhập doanh nghiệp phải nộp',
    'Current Accrued Expenses':'Chi phí phải trả ngắn hạn','Interest Payable':'Lãi vay phải trả',
    'Current Provisions':'Dự phòng ngắn hạn','Employee Benefits':'Phúc lợi nhân viên',
    'Non Current Prepaid Assets':'Chi phí trả trước dài hạn','Non Current Deferred Assets':'Tài sản hoãn lại dài hạn',
    'Non Current Deferred Taxes Assets':'Tài sản thuế thu nhập hoãn lại dài hạn','Defined Pension Benefit':'Quỹ lương hưu xác định',
    'Long Term Equity Investment':'Đầu tư vốn chủ sở hữu dài hạn','Investmentin Financial Assets':'Đầu tư vào tài sản tài chính',
    'Financial Assets Designatedas Fair Value Through Profitor Loss Total':'Tài sản tài chính ghi nhận theo giá trị hợp lý qua lãi lỗ',
    'Investments In Other Ventures Under Equity Method':'Đầu tư vào đơn vị khác theo phương pháp vốn chủ sở hữu',
    'Other Current Assets':'Tài sản ngắn hạn khác','Hedging Assets Current':'Tài sản phòng ngừa rủi ro ngắn hạn',
    'Assets Held For Sale Current':'Tài sản nắm giữ để bán ngắn hạn',
    'Inventories Adjustments Allowances':'Dự phòng giảm giá hàng tồn kho','Other Inventories':'Hàng tồn kho khác',
    'Receivables Adjustments Allowances':'Dự phòng các khoản phải thu','Accrued Interest Receivable':'Lãi dự thu',
    'Notes Receivable':'Phải thu thương phiếu','Loans Receivable':'Phải thu cho vay',
    'Gross Accounts Receivable':'Phải thu khách hàng (gộp)',
    'Duefrom Related Parties Non Current':'Phải thu các bên liên quan dài hạn',
    'Due From Related Parties Non Current':'Phải thu các bên liên quan dài hạn',
    'Total Partnership Capital':'Tổng vốn góp đối tác',
    # ---- Báo cáo kết quả kinh doanh ----
    'Total Unusual Items':'Tổng các khoản mục bất thường','Reconciled Cost Of Revenue':'Giá vốn hàng bán được điều chỉnh',
    'Normalized Basic EPS':'EPS cơ bản chuẩn hóa','Other Non Operating Income Expenses':'Thu nhập/chi phí ngoài hoạt động khác',
    'Interest Expense Non Operating':'Chi phí lãi vay ngoài hoạt động','Interest Income Non Operating':'Thu nhập lãi ngoài hoạt động',
    'Depreciation Amortization Depletion Income Statement':'Khấu hao và phân bổ (báo cáo kết quả kinh doanh)',
    'Depreciation And Amortization In Income Statement':'Khấu hao và phân bổ (báo cáo kết quả kinh doanh)',
    'Other Gand A':'Chi phí quản lý khác','Salaries And Wages':'Lương và tiền công',
    'Rent And Landing Fees':'Chi phí thuê và phí hạ cánh','Other Taxes':'Thuế khác',
    'Provision For Doubtful Accounts':'Dự phòng phải thu khó đòi','Gain On Sale Of PPE':'Lãi từ thanh lý tài sản cố định',
    'Impairment Of Capital Assets':'Tổn thất tài sản vốn','Restructuring And Mergern Acquisition':'Chi phí tái cấu trúc và sáp nhập',
    'Earnings From Equity Interest':'Lãi từ đầu tư vốn chủ sở hữu',
    'Earnings From Equity Interest Net Of Tax':'Lãi từ đầu tư vốn chủ sở hữu sau thuế',
    'Insurance And Claims':'Bảo hiểm và bồi thường','Securities Amortization':'Phân bổ chứng khoán',
    'Occupancy And Equipment':'Chi phí cơ sở vật chất và thiết bị',
    'Professional Expense And Contract Services Expense':'Chi phí dịch vụ chuyên môn và hợp đồng',
    'Dilution Effect':'Ảnh hưởng pha loãng','Preferred Stock Dividends':'Cổ tức cổ phiếu ưu đãi',
    'Average Dilution Earnings':'Lợi nhuận pha loãng bình quân',
    'Otherunder Preferred Stock Dividend':'Cổ tức cổ phiếu ưu đãi và điều chỉnh khác',
    'Net Income From Continuing Operations':'Lợi nhuận ròng từ hoạt động liên tục',
    'Non Interest Income':'Thu nhập ngoài lãi','Non Interest Expense':'Chi phí ngoài lãi',
    'Other Non Interest Income':'Thu nhập ngoài lãi khác','Fees And Commissions':'Thu nhập phí và hoa hồng',
    'Credit Losses Provision':'Chi phí dự phòng rủi ro tín dụng',
    'Interest Income After Provision For Loan Loss':'Thu nhập lãi thuần sau dự phòng rủi ro tín dụng',
    'Total Premiums Earned':'Tổng phí bảo hiểm đã thu','Net Policyholder Benefits And Claims':'Chi bồi thường và quyền lợi bảo hiểm thuần',
    # ---- Báo cáo lưu chuyển tiền tệ ----
    'Repurchase Of Capital Stock':'Tiền chi mua lại cổ phiếu','Issuance Of Capital Stock':'Tiền thu từ phát hành cổ phiếu',
    'Interest Paid Supplemental Data':'Lãi vay đã trả (bổ sung)','Income Tax Paid Supplemental Data':'Thuế thu nhập doanh nghiệp đã nộp (bổ sung)',
    'Effect Of Exchange Rate Changes':'Ảnh hưởng của thay đổi tỷ giá hối đoái','Net Other Financing Charges':'Chênh lệch dòng tiền tài chính khác',
    'Common Stock Dividend Paid':'Cổ tức cổ phiếu phổ thông đã trả','Common Stock Payments':'Tiền chi mua cổ phiếu phổ thông',
    'Common Stock Issuance':'Tiền thu từ phát hành cổ phiếu phổ thông','Net Preferred Stock Issuance':'Phát hành cổ phiếu ưu đãi thuần',
    'Net Issuance Payments Of Debt':'Tiền vay và trả nợ thuần','Net Short Term Debt Issuance':'Vay ngắn hạn thuần',
    'Net Long Term Debt Issuance':'Vay dài hạn thuần','Long Term Debt Payments':'Tiền trả nợ vay dài hạn',
    'Long Term Debt Issuance':'Tiền thu từ vay dài hạn','Short Term Debt Payments':'Tiền trả nợ vay ngắn hạn',
    'Short Term Debt Issuance':'Tiền thu từ vay ngắn hạn','Net Other Investing Changes':'Chênh lệch dòng tiền đầu tư khác',
    'Interest Received Cfi':'Lãi đã nhận từ hoạt động đầu tư','Dividends Received Cfi':'Cổ tức đã nhận từ hoạt động đầu tư',
    'Sale Of Investment':'Tiền thu từ bán khoản đầu tư','Purchase Of Investment':'Tiền chi mua khoản đầu tư',
    'Sale Of Business':'Tiền thu từ bán doanh nghiệp','Purchase Of Business':'Tiền chi mua doanh nghiệp',
    'Purchase Of Intangibles':'Tiền chi mua tài sản vô hình','Sale Of Intangibles':'Tiền thu từ bán tài sản vô hình',
    'Capital Expenditure Reported':'Chi đầu tư tài sản cố định (đã báo cáo)',
    'Change In Other Current Liabilities':'Biến động nợ ngắn hạn khác','Change In Other Current Assets':'Biến động tài sản ngắn hạn khác',
    'Change In Payables And Accrued Expense':'Biến động phải trả và chi phí phải trả','Change In Payable':'Biến động các khoản phải trả',
    'Change In Tax Payable':'Biến động thuế phải nộp','Change In Income Tax Payable':'Biến động thuế thu nhập phải nộp',
    'Change In Interest Payable':'Biến động lãi vay phải trả','Change In Prepaid Assets':'Biến động chi phí trả trước',
    'Changes In Account Receivables':'Biến động phải thu khách hàng','Other Non Cash Items':'Các khoản phi tiền mặt khác',
    'Excess Tax Benefit From Stock Based Compensation':'Lợi ích thuế vượt mức từ thưởng cổ phiếu',
    'Stock Based Compensation':'Chi phí thưởng bằng cổ phiếu',
    'Unrealized Gain Loss On Investment Securities':'Lãi/lỗ chưa thực hiện từ chứng khoán đầu tư',
    'Provision And Write Off Of Assets':'Dự phòng và xóa sổ tài sản','Amortization Of Securities':'Phân bổ chứng khoán',
    'Deferred Tax':'Thuế hoãn lại','Depreciation':'Khấu hao','Amortization Cash Flow':'Phân bổ',
    'Operating Gains Losses':'Lãi/lỗ từ hoạt động kinh doanh','Pension And Employee Benefit Expense':'Chi phí lương hưu và phúc lợi nhân viên',
    'Earnings Losses From Equity Investments':'Lãi/lỗ từ đầu tư vốn chủ sở hữu',
    'Gain Loss On Investment Securities':'Lãi/lỗ từ chứng khoán đầu tư','Gain Loss On Sale Of PPE':'Lãi/lỗ từ thanh lý tài sản cố định',
    'Gain Loss On Sale Of Business':'Lãi/lỗ từ bán doanh nghiệp','Net Foreign Currency Exchange Gain Loss':'Lãi/lỗ tỷ giá hối đoái thuần',
    'Net Foreign Currency Exchange Gain':'Lãi tỷ giá hối đoái thuần','Net Foreign Currency Exchange Loss':'Lỗ tỷ giá hối đoái thuần',
    'Taxes Refund Paid':'Thuế đã nộp/hoàn','Interest Paid Cfo':'Lãi vay đã trả (HĐKD)','Interest Received Cfo':'Lãi đã nhận (HĐKD)',
    'Dividend Received Cfo':'Cổ tức đã nhận (HĐKD)','Dividend Paid Cfo':'Cổ tức đã trả (HĐKD)','Interest Paid Cff':'Lãi vay đã trả (HĐTC)',
    'Other Cash Adjustment Outside Changein Cash':'Điều chỉnh tiền khác ngoài thay đổi tiền',
    'Other Cash Adjustment Inside Changein Cash':'Điều chỉnh tiền khác trong thay đổi tiền',
    'Cash From Discontinued Financing Activities':'Tiền từ hoạt động tài chính không liên tục',
    'Cash From Discontinued Investing Activities':'Tiền từ hoạt động đầu tư không liên tục',
    'Cash From Discontinued Operating Activities':'Tiền từ hoạt động kinh doanh không liên tục',
    # ---- Nhãn tiếng Anh của ngân hàng / vnfinancialdata / nguồn cũ ----
    'Other assets':'Tài sản Có khác','Other liabilities':'Nợ phải trả khác','Total assets':'Tổng cộng tài sản',
    'Total liabilities':'Nợ phải trả','Total liabilities and equity':'Tổng cộng nguồn vốn',
    'Customer deposits':'Tiền gửi của khách hàng','Loans to customers':'Cho vay khách hàng','Fixed assets':'Tài sản cố định',
    'Investment securities':'Chứng khoán đầu tư','Trading securities':'Chứng khoán kinh doanh','Net revenue':'Doanh thu thuần',
}
for _k, _v in EXTRA_TRANSLATION_MAP.items():
    TRANSLATION_MAP.setdefault(_k, _v)

_TR_LOWER = {}
for _k, _v in TRANSLATION_MAP.items():
    _TR_LOWER.setdefault(_k.lower(), _v)

# ==========================================
# 5. LÀM SẠCH CHUYÊN SÂU (GIỮ NGUYÊN, 🆕 v17.3 sạch đuôi .0 ngay khi cào)
# ==========================================
def format_value(x):
    if pd.isna(x): return None
    try:
        if isinstance(x, str):
            x = x.replace(',', '').replace(' ', '')   # v17.2: sửa .replace(' ') thiếu đối số
            if x.count('.') > 1: x = x.replace('.', '')
        val = float(x)
        if abs(val) > 1e18: return None   # v17.1: 1e15 -> 1e18 (cứu Tổng tài sản ngân hàng ~2e15 VND)
        if val != val or val in [float('inf'), float('-inf')]: return None
        r = round(val, 4)
        # 🆕 v17.3: số nguyên trả về int (không đuôi .0); số thập phân giữ tối đa 4 chữ số
        return int(r) if r == int(r) else r
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
    # 🆕 v17.3: quy tắc tách từ chỉ áp dụng khi từ nối là chữ thường dính liền và đứng trước chữ HOA/khoảng trắng/cuối chuỗi
    #           (bản cũ chèn khoảng trắng bừa vào từ lạ: "Depreciation" -> "Depreci ation")
    text = re.sub(r'([a-z])(from|to|of|on|for|and|at|in)(?=[A-Z\s]|$)', r'\1 \2', text)
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
# 🆕 v17.3: bổ sung từ vựng cho cơ chế dịch từng từ (chỉ thêm, không ghi đè)
for _k, _v in {
    'amortization':'phân bổ','gain':'lãi','loss':'lỗ','foreign':'ngoại tệ','currency':'tiền tệ','exchange':'tỷ giá',
    'continuing':'liên tục','operations':'hoạt động','securities':'chứng khoán','refund':'hoàn','paid':'đã trả',
    'received':'đã nhận','prepaid':'trả trước','working':'lưu động','change':'thay đổi','changes':'thay đổi',
    'payables':'phải trả','receivables':'phải thu','issuance':'phát hành','repayment':'trả nợ','debt':'nợ vay',
    'stock':'cổ phiếu','common':'phổ thông','dividend':'cổ tức','tax':'thuế','profit':'lợi nhuận','loan':'cho vay',
    'loans':'cho vay','deposits':'tiền gửi','customer':'khách hàng','customers':'khách hàng','provision':'dự phòng',
    'purchase':'mua','sale':'bán','business':'doanh nghiệp','investment':'đầu tư','units':'đơn vị',
    'reported':'đã báo cáo','items':'khoản mục','adjustments':'điều chỉnh','unusual':'bất thường','special':'đặc biệt',
    'charges':'chi phí','fees':'phí','commissions':'hoa hồng','services':'dịch vụ','salaries':'lương',
    'wages':'tiền công','insurance':'bảo hiểm','claims':'bồi thường','margin':'biên','price':'giá','book':'sổ sách',
    'value':'giá trị','average':'bình quân','shares':'cổ phiếu','basic':'cơ bản','diluted':'pha loãng',
}.items():
    FALLBACK_MAP.setdefault(_k, _v)

_TR_CACHE = {}

def _translate_metric_core(metric_original, is_vn=False):
    cleaned_key = clean_text(metric_original)
    if cleaned_key in TRANSLATION_MAP: return TRANSLATION_MAP[cleaned_key]
    if cleaned_key.lower() in _TR_LOWER: return _TR_LOWER[cleaned_key.lower()]   # 🆕 v17.3: tra bảng thường, thay vòng for chậm
    if is_vn or any(char in cleaned_key for char in ['à','á','ả','ã','ạ','ă','â','đ','ê','ô','ơ','ư','ý']):
        cleaned_key = re.sub(r'\bM\b', 'Lợi ích cổ đông không kiểm soát', cleaned_key)
        cleaned_key = re.sub(r'\bN s\b', 'Số lượng cổ phiếu ròng', cleaned_key)
        cleaned_key = cleaned_key.replace('f giá gốc', 'phí giá gốc')
        return cleaned_key
    fixed_key = fix_yfinance_typos(cleaned_key)
    if fixed_key in TRANSLATION_MAP: return TRANSLATION_MAP[fixed_key]
    if fixed_key.lower() in _TR_LOWER: return _TR_LOWER[fixed_key.lower()]
    _UNMAPPED_METRICS.add(cleaned_key)   # 🆕 v17.3: ghi nhãn chưa có trong từ điển để bổ sung sau
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
    # 🆕 v17.3: chặn nhãn rác chỉ gồm từ nối ("Của", "Và"...) -> đánh dấu chưa xác định để bị loại ở Tầng 1
    if not result or set(result.lower().split()) <= _STOP_VN: result = UNKNOWN_METRIC
    return result.capitalize()

def translate_metric(metric_original, is_vn=False):
    """🆕 v17.3: bọc cache (mỗi nhãn chỉ dịch 1 lần) — logic dịch giữ nguyên."""
    key = (str(metric_original), bool(is_vn))
    r = _TR_CACHE.get(key)
    if r is None:
        r = _translate_metric_core(metric_original, is_vn)
        _TR_CACHE[key] = r
    return r

# ==========================================
# 5.5 🆕 v17.4: CHUẨN HOÁ ĐƠN VỊ NGAY KHI CÀO (chặn giá/vốn hoá/SLCP sai thang)
# ==========================================
PRICE_MIN, PRICE_MAX = 100.0, 5_000_000.0        # VNĐ/cổ phiếu (VNZ từng giao dịch >1 triệu)
SHARES_MIN, SHARES_MAX = 1_000_000.0, 5e11      # số cổ phiếu
MCAP_MIN, MCAP_MAX = 1e9, 5e16                  # VNĐ

def norm_price(v):
    """Giá phải nằm trong thang VNĐ/cp hợp lý; ngoài thang -> None (bỏ)."""
    fv = format_value(v)
    if fv is None: return None
    fv = float(fv)
    if not (PRICE_MIN <= fv <= PRICE_MAX): return None
    return int(fv) if fv == int(fv) else round(fv, 2)

def norm_shares(v):
    """SLCP: nguồn trả đơn vị TRIỆU cp (<1e6) -> x1e6; ngoài thang -> None."""
    fv = format_value(v)
    if fv is None: return None
    fv = float(fv)
    if 1.0 <= fv < SHARES_MIN:
        fv *= 1_000_000.0
    elif fv < 1.0:
        return None
    if not (SHARES_MIN <= fv <= SHARES_MAX): return None
    return int(round(fv))

def norm_market_cap(v, price=None, shares=None):
    """Vốn hoá: nguồn trả đơn vị TỶ đồng (<1e9) -> x1e9; lệch giá x SLCP >50% -> lấy giá x SLCP."""
    fv = format_value(v)
    if fv is None: return None
    fv = float(fv)
    if 1.0 <= fv < 1e9:
        fv *= 1e9
    if price and shares:
        ref = float(price) * float(shares)
        if ref > 0 and abs(fv - ref) / ref > 0.5:
            fv = ref
    if not (MCAP_MIN <= fv <= MCAP_MAX): return None
    return int(round(fv))

# ==========================================
# 6. HTTP SESSION (GIỮ NGUYÊN session gốc)
# ==========================================
session = requests.Session()
session.headers.update({
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
    'Accept': 'application/json, text/plain, */*',
    'Accept-Language': 'vi-VN,vi;q=0.9,en;q=0.8',
})

# ===== ENGINE HTTP CHO VNDIRECT (thread-safe) — CHỈ CHẠY KHI SKIP_VNDIRECT=false =====
VND_HOSTS = ["https://finfo-api.vndirect.com.vn", "https://api-finfo.vndirect.com.vn"]
VND_PAGE_SIZE = 1000
VND_MAX_PAGES = 60
VND_MIN_YEAR = 2000
VND_REQ_INTERVAL = 0.15
VND_TIMEOUT = 8

_thread_local = threading.local()
def get_session():
    s = getattr(_thread_local, 'session', None)
    if s is None:
        s = requests.Session()
        s.headers.update(session.headers)
        s.mount('https://', HTTPAdapter(pool_connections=8, pool_maxsize=8))
        _thread_local.session = s
    return s

_throttle_lock = threading.Lock()
_next_slot = [0.0]
def _throttle():
    with _throttle_lock:
        wait = _next_slot[0] - time.monotonic()
        if wait > 0: time.sleep(wait)
        _next_slot[0] = time.monotonic() + VND_REQ_INTERVAL

_vnd_host_idx = 0
_vnd_lock = threading.Lock()
def vnd_get(path, params, max_retries=1, label=""):
    """GET VNDirect. Mặc định 1 lần thử (KHÔNG retry 4 lần), lỗi là bỏ qua ngay."""
    global _vnd_host_idx
    if SKIP_VNDIRECT: return None
    last_err = None
    for attempt in range(max_retries):
        with _vnd_lock:
            host = VND_HOSTS[_vnd_host_idx]
        _throttle()
        try:
            r = get_session().get(host + path, params=params, timeout=VND_TIMEOUT)
            if r.status_code == 200:
                return r.json()
            if r.status_code in (400, 404, 422):
                return None
            last_err = f"HTTP {r.status_code}"
        except Exception as e:
            last_err = type(e).__name__
        with _vnd_lock:
            _vnd_host_idx = (_vnd_host_idx + 1) % len(VND_HOSTS)
        if attempt == max_retries - 1: break
        time.sleep(min(2 ** attempt, 8) + random.uniform(0, 0.5))
    print(f"  ⚠️ [VND] {label}: bỏ qua sau {max_retries} lần thử ({last_err})")
    return None

# ==========================================
# 6.1. VNDIRECT BCTC API — VÔ HIỆU HOÁ MẶC ĐỊNH (SKIP_VNDIRECT=true)
# ==========================================
def _item_key(it):
    return it.get('id') or (it.get('reportDate'), it.get('itemCode'),
                            it.get('quarter'), it.get('numericValue'))

def _period_from_item(it, report_type):
    """(năm, nhãn kỳ). Quý: ưu tiên 'quarter' > lengthReport 6/9 > tháng > lr12."""
    rd = str(it.get('reportDate') or it.get('fiscalDate') or '')
    year = it.get('year')
    if not year:
        m = re.match(r'(\d{4})', rd)
        year = m.group(1) if m else None
    if not year: return None, None
    year = str(year)
    if report_type == 'YEAR':
        return year, f"{year}-12-31"
    q = None
    try: q = int(it.get('quarter'))
    except (TypeError, ValueError): pass
    if q not in (1, 2, 3, 4):
        lr = None
        try: lr = int(it.get('lengthReport'))
        except (TypeError, ValueError): pass
        if lr in (6, 9):
            q = lr // 3
        else:
            m = re.match(r'\d{4}-(\d{2})', rd)
            if m and int(m.group(1)) in (3, 6, 9, 12):
                q = int(m.group(1)) // 3
            elif lr == 12:
                q = 4
    if q not in (1, 2, 3, 4): return year, None
    return year, f"{year}-Q{q}"

def _fetch_vnd_by_year(symbol, stmt_code, report_type, base_q):
    """Fallback khi API phớt lờ tham số page: cắt lát từng năm (mỗi năm < 1 trang)."""
    out, seen = [], set()
    for y in range(VND_MIN_YEAR, datetime.now().year + 1):
        q = f"{base_q}~reportDate:gte:{y}-01-01~reportDate:lte:{y}-12-31"
        data = vnd_get('/v4/financial_statements',
                       {'q': q, 'sort': 'reportDate:asc', 'size': VND_PAGE_SIZE, 'page': 1},
                       label=f"{symbol}/{stmt_code}/{report_type}/{y}")
        for it in (data or {}).get('data') or []:
            k = _item_key(it)
            if k not in seen:
                seen.add(k); out.append(it)
    return out

def _fetch_vnd_statement(symbol, stmt_code, report_type):
    """Lật HẾT trang của 1 mã x 1 báo cáo x 1 loại kỳ. Không break thầm lặng."""
    base_q = f"code:{symbol}~reportType:{report_type}~financialStatement:{stmt_code}"
    out, seen = [], set()
    total_hint, page = None, 1
    while page <= VND_MAX_PAGES:
        data = vnd_get('/v4/financial_statements',
                       {'q': base_q, 'sort': 'reportDate:asc', 'size': VND_PAGE_SIZE, 'page': page},
                       label=f"{symbol}/{stmt_code}/{report_type}/p{page}")
        if data is None: break
        batch = data.get('data') or []
        if not batch: break
        if total_hint is None:
            total_hint = data.get('total') or data.get('hits')
        fresh = 0
        for it in batch:
            k = _item_key(it)
            if k in seen: continue
            seen.add(k); out.append(it); fresh += 1
        tp = data.get('totalPages')
        if tp and page >= int(tp): break
        if total_hint and len(out) >= int(total_hint): break
        if len(batch) < VND_PAGE_SIZE: break
        if fresh == 0:
            return _fetch_vnd_by_year(symbol, stmt_code, report_type, base_q)
        page += 1
    return out

def fetch_vndirect_bctc_financials(symbol):
    """⭐ (TẮT MẶC ĐỊNH) Nguồn BCTC Quý + Năm từ VNDirect. Chỉ chạy khi SKIP_VNDIRECT=false."""
    if SKIP_VNDIRECT: return []
    records = []
    company_name, sector_name = get_company_profile(symbol)
    statement_map = {
        'BALANCE_SHEET': 'Bảng cân đối kế toán',
        'INCOME_STATEMENT': 'Báo cáo kết quả kinh doanh',
        'CASH_FLOW': 'Báo cáo lưu chuyển tiền tệ'
    }
    for stmt_code, stmt_vn in statement_map.items():
        for report_type, ky_bao_cao in (('QUARTER', 'Quý'), ('YEAR', 'Năm')):
            for item in _fetch_vnd_statement(symbol, stmt_code, report_type):
                year_val, date_period = _period_from_item(item, report_type)
                if not date_period: continue
                fv = format_value(item.get('numericValue'))
                if fv is None or fv == 0: continue
                metric_vn = clean_text(item.get('itemName', ''))
                if not metric_vn:
                    metric_vn = fix_truncated_text(item.get('itemCode', ''))
                if not metric_vn: continue
                records.append({
                    'Mã chứng khoán': symbol, 'Tên doanh nghiệp': company_name,
                    'Tên ngành': sector_name, 'Loại báo cáo': stmt_vn,
                    'Loại kỳ': ky_bao_cao, 'Năm': str(year_val), 'Ngày kỳ': date_period,
                    'Chỉ tiêu tiếng Việt': metric_vn, 'Giá trị': fv
                })
    return records

# ==========================================
# 6.2. FALLBACK Giá + SLCP (🆕 v17.4: chuẩn đơn vị bằng norm_*)
# ==========================================
def fetch_vndirect_fallback(symbol):
    if SKIP_VNDIRECT: return []
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
                fv = norm_price(price)   # 🆕 v17.4
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
                fv = norm_shares(shares)   # 🆕 v17.4
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
                fv_p = norm_price(price)     # 🆕 v17.4
                fv_s = norm_shares(shares)   # 🆕 v17.4
                if fv_p:
                    records.append({'Mã chứng khoán': symbol, 'Tên doanh nghiệp': company_name, 'Tên ngành': sector_name, 'Loại báo cáo': 'Chỉ số thị trường, Định giá & Cổ tức', 'Loại kỳ': 'Real-time', 'Năm': current_year, 'Ngày kỳ': today_str, 'Chỉ tiêu tiếng Việt': 'Giá cổ phiếu hiện tại', 'Giá trị': fv_p})
                if fv_s:
                    records.append({'Mã chứng khoán': symbol, 'Tên doanh nghiệp': company_name, 'Tên ngành': sector_name, 'Loại báo cáo': 'Chỉ số thị trường, Định giá & Cổ tức', 'Loại kỳ': 'Real-time', 'Năm': current_year, 'Ngày kỳ': today_str, 'Chỉ tiêu tiếng Việt': 'Tổng số lượng cổ phiếu lưu hành', 'Giá trị': fv_s})
    except Exception: pass
    return records

# ==========================================
# 7. YFINANCE CRAWLERS (🆕 v17.3: bỏ dòng nhãn chưa xác định; 🆕 v17.4: chuẩn đơn vị)
# ==========================================
def parse_financial_df(symbol, df, statement_type_raw, ky_bao_cao, min_year=2000):
    records = []
    company_name, sector_name = get_company_profile(symbol)
    statement_type_vn = TRANSLATION_MAP.get(statement_type_raw, statement_type_raw)
    try:
        if df is not None and not df.empty:
            for col in df.columns:
                date_str = str(col).split('T')[0].split(' ')[0]
                parts = date_str.split('-')
                if not parts[0].isdigit() or int(parts[0]) < min_year: continue
                year_val = parts[0]
                # v17.1: nhãn quý thống nhất 'YYYY-Qn' để dedup chéo nguồn đúng
                if ky_bao_cao == 'Quý' and len(parts) >= 2:
                    date_period = f"{year_val}-Q{(int(parts[1]) - 1) // 3 + 1}"
                else:
                    date_period = date_str
                for row_idx, val in df[col].items():
                    if pd.notna(val):
                        fv = format_value(val)
                        if fv is not None and fv != 0:   # v17.1: bỏ số 0 ngay từ nguồn
                            metric_vn = translate_metric(str(row_idx).strip())
                            if metric_vn == UNKNOWN_METRIC: continue   # 🆕 v17.3: không nhận nhãn rác/chưa xác định
                            records.append({
                                'Mã chứng khoán': symbol, 'Tên doanh nghiệp': company_name,
                                'Tên ngành': sector_name, 'Loại báo cáo': statement_type_vn,
                                'Loại kỳ': ky_bao_cao, 'Năm': year_val, 'Ngày kỳ': date_period,
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
                if year_val.isdigit() and int(year_val) >= min_year:
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
                market_cap = float(info.get('marketCap', 0) or 0)
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

        # 🆕 v17.4: CHUẨN ĐƠN VỊ NGAY KHI CÀO — chặn số 14 chữ số kiểu 36.166.511.658.185
        current_price = norm_price(current_price) if current_price else None
        shares_out = norm_shares(shares_out) if shares_out else None
        market_cap = norm_market_cap(market_cap, current_price, shares_out) if market_cap else None
        if (current_price is None) and market_cap and shares_out:
            current_price = norm_price(market_cap / shares_out)      # suy ra giá từ vốn hoá / SLCP
        if (market_cap is None) and current_price and shares_out:
            market_cap = norm_market_cap(current_price * shares_out, current_price, shares_out)
        if div_yield is not None and not (0.0 <= float(div_yield) <= 30.0):
            div_yield = 0.0

        metrics = [('Current Price', current_price), ('Shares Outstanding', shares_out), ('Market Capitalization', market_cap), ('Dividend Yield', div_yield)]
        for eng_key, val in metrics:
            if val is not None and val != 0:
                fv = format_value(val)
                if fv is not None and fv != 0:
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
    # v17.2: BỎ "UPCOM-INDEX": "^UPCOM" (Yahoo không có dữ liệu -> cảnh báo "symbol may be delisted")
    indices = {"VN-INDEX": "^VNINDEX", "HNX-INDEX": "^HNX"}
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
# 8. VNFINANCIALDATA BULK (GIỮ NGUYÊN, chỉ bỏ 'ratio')
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
    # v17.1: bỏ 'ratio' — vnfinancialdata chỉ hỗ trợ 3 báo cáo, chỉ có kỳ NĂM
    statements = {"balance_sheet": "Bảng cân đối kế toán", "income_statement": "Báo cáo kết quả kinh doanh", "cash_flow": "Báo cáo lưu chuyển tiền tệ"}
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
                    if fv is None or fv == 0: continue   # 🆕 v17.3: bỏ dòng 0 ngay từ nguồn
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
        # v17.1: cào từng báo cáo ĐỘC LẬP
        for attr, raw, ky in (('balance_sheet', 'Balance_Sheet', 'Năm'),
                              ('quarterly_balance_sheet', 'Balance_Sheet', 'Quý'),
                              ('financials', 'Income_Statement', 'Năm'),
                              ('quarterly_financials', 'Income_Statement', 'Quý'),
                              ('cashflow', 'Cash_Flow', 'Năm'),
                              ('quarterly_cashflow', 'Cash_Flow', 'Quý')):
            try:
                recs.extend(parse_financial_df(symbol, getattr(ticker, attr, None), raw, ky))
            except Exception: pass
        recs.extend(fetch_market_and_valuation_metrics(symbol, ticker, bs_df))
        recs.extend(fetch_historical_dividends(symbol, ticker))
    except Exception: pass
    return recs

# ==========================================
# 9.5. BÙ BCTC QUÝ BẰNG YFINANCE ĐA LUỒNG (v17.2)
#      Không retry; mã lỗi/chậm bị bỏ qua ngay; vnfinancialdata chỉ có kỳ NĂM nên không dùng cho quý.
# ==========================================
QUARTER_WORKERS = 8
QUARTER_TICKER_BUDGET = 20
QUARTER_TOTAL_BUDGET = 600
QUARTER_MIN_PERIODS = 4

def fetch_yf_quarter_single(symbol):
    """1 mã: quarterly_balance_sheet / quarterly_income_stmt / quarterly_cashflow. Lỗi -> bỏ qua ngay."""
    recs = []
    t0 = time.monotonic()
    try:
        ticker = yf.Ticker(f"{symbol}.VN")
    except Exception:
        return recs
    for attr, raw in (('quarterly_balance_sheet', 'Balance_Sheet'),
                      ('quarterly_income_stmt', 'Income_Statement'),
                      ('quarterly_cashflow', 'Cash_Flow')):
        if time.monotonic() - t0 > QUARTER_TICKER_BUDGET:
            break
        try:
            df = getattr(ticker, attr, None)
        except Exception:
            break
        try:
            recs.extend(parse_financial_df(symbol, df, raw, 'Quý'))
        except Exception:
            pass
    return recs

def fetch_quarter_multithread(symbols):
    """Chạy ThreadPoolExecutor(max_workers=8). Trả về list bản ghi quý của tất cả mã."""
    all_recs = []
    if not symbols: return all_recs
    total = len(symbols)
    done = 0
    executor = ThreadPoolExecutor(max_workers=QUARTER_WORKERS)
    futures = {executor.submit(fetch_yf_quarter_single, s): s for s in symbols}
    try:
        for future in as_completed(futures, timeout=QUARTER_TOTAL_BUDGET):
            done += 1
            sym = futures[future]
            try:
                res = future.result()
                if res:
                    all_recs.extend(res)
                    if done % 20 == 0 or done == total:
                        print(f"  ✓ [{done}/{total}] {sym}: +{len(res):,} dòng quý")
            except Exception:
                pass
    except Exception as e:
        print(f"  ⚠️ Hết ngân sách thời gian bù quý ({type(e).__name__}) — dùng phần đã cào được ({done}/{total}).")
    finally:
        executor.shutdown(wait=False, cancel_futures=True)
    return all_recs

# ==========================================
# 10. CLEANING & SOURCE TRACKING (🆕 v17.3: làm lại 5 tầng, giữ khung; 🆕 v17.4: chuẩn đơn vị)
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

    # ---------- TẦNG 1: loại NULL / rỗng / 0 / rác, ép kiểu số ----------
    df['Giá trị'] = pd.to_numeric(df['Giá trị'].astype(str).str.replace(',', '').str.strip(), errors='coerce')
    df = df.dropna(subset=['Mã chứng khoán', 'Chỉ tiêu tiếng Việt', 'Giá trị'])
    df = df[np.isfinite(df['Giá trị']) & (df['Giá trị'] != 0)]
    df['Mã chứng khoán'] = df['Mã chứng khoán'].astype(str).str.strip().str.upper()
    df = df[~df['Mã chứng khoán'].isin(['', 'NAN', 'NONE', 'NULL'])]
    df['Chỉ tiêu tiếng Việt'] = df['Chỉ tiêu tiếng Việt'].astype(str).str.strip()
    df = df[~df['Chỉ tiêu tiếng Việt'].str.lower().isin(_JUNK_METRICS)]
    df['Loại báo cáo'] = df['Loại báo cáo'].fillna('').astype(str)
    df['Loại kỳ'] = df['Loại kỳ'].fillna('').astype(str).str.strip()
    # Ngày kỳ trống: nếu có Năm thì gán 31/12 của năm đó, không thì bỏ dòng
    ngay = df['Ngày kỳ'].fillna('').astype(str).str.strip()
    nam_tmp = pd.to_numeric(df['Năm'], errors='coerce')
    thieu = ngay.isin(['', 'nan', 'None', 'NaT'])
    ngay = ngay.where(~thieu, nam_tmp.map(lambda y: f"{int(y)}-12-31" if pd.notna(y) else ''))
    df['Ngày kỳ'] = ngay
    df = df[df['Ngày kỳ'] != '']

    # 🆕 v17.4: CHUẨN ĐƠN VỊ giá / SLCP / vốn hoá ngay trong cleaning (chặn cả dữ liệu cũ từ Supabase)
    m_price = df['Chỉ tiêu tiếng Việt'] == 'Giá cổ phiếu hiện tại'
    if m_price.any():
        df.loc[m_price, 'Giá trị'] = df.loc[m_price, 'Giá trị'].map(norm_price)
    m_sh = df['Chỉ tiêu tiếng Việt'] == 'Tổng số lượng cổ phiếu lưu hành'
    if m_sh.any():
        df.loc[m_sh, 'Giá trị'] = df.loc[m_sh, 'Giá trị'].map(norm_shares)
    m_mc = df['Chỉ tiêu tiếng Việt'] == 'Vốn hóa thị trường'
    if m_mc.any():
        df.loc[m_mc, 'Giá trị'] = df.loc[m_mc, 'Giá trị'].map(norm_market_cap)
    before_unit = len(df)
    df = df.dropna(subset=['Giá trị'])
    df = df[df['Giá trị'] != 0]
    if before_unit - len(df):
        print(f"  [Tầng 1b] 🆕 v17.4: loại {before_unit - len(df):,} dòng giá/SLCP/vốn hoá ngoài thang đơn vị.")
    print(f"  [Tầng 1] Loại bỏ NULL/rỗng/0/rác & ép kiểu Float. Còn {len(df):,} dòng.")
    
    # ---------- TẦNG 2: Việt hoá + ép chuẩn VAS (xử lý theo nhãn duy nhất cho nhanh) ----------
    uniq = df[['Chỉ tiêu tiếng Việt', 'Loại báo cáo']].drop_duplicates()
    std_cache = {(m, r): standardize_metric(m, r) for m, r in zip(uniq['Chỉ tiêu tiếng Việt'], uniq['Loại báo cáo'])}
    df['Chỉ tiêu tiếng Việt'] = [std_cache[(m, r)] for m, r in zip(df['Chỉ tiêu tiếng Việt'], df['Loại báo cáo'])]
    df = df.dropna(subset=['Chỉ tiêu tiếng Việt'])
    df['Chỉ tiêu tiếng Việt'] = df['Chỉ tiêu tiếng Việt'].astype(str).str.strip()
    df = df[~df['Chỉ tiêu tiếng Việt'].str.lower().isin(_JUNK_METRICS)]
    still_en = sorted({m for m in df['Chỉ tiêu tiếng Việt'].unique() if _looks_english(m) and not m.isupper()})
    for m in still_en: _UNMAPPED_METRICS.add(m)
    print(f"  [Tầng 2] Việt hoá + ép chuẩn VAS Dictionary. Còn {len(df):,} dòng. (Nhãn còn nghi tiếng Anh: {len(still_en)})")

    # Tầng 2.5 (v17.1): chữa nhãn quý cũ dạng ngày (Yahoo/Supabase đời trước) -> 'YYYY-Qn'
    mask = (df['Loại kỳ'] == 'Quý') & df['Ngày kỳ'].astype(str).str.match(r'^\d{4}-\d{2}-\d{2}$')
    if mask.any():
        s = df.loc[mask, 'Ngày kỳ'].astype(str)
        df.loc[mask, 'Ngày kỳ'] = s.str[:4] + '-Q' + ((s.str[5:7].astype(int) - 1) // 3 + 1).astype(str)
        print(f"  [Tầng 2.5] Chuẩn hoá {int(mask.sum()):,} nhãn quý về 'YYYY-Qn'.")

    # ---------- TẦNG 3: Deduplication (nguồn ưu tiên cao thắng) ----------
    if '_priority' in df.columns:
        df = df.sort_values('_priority', kind='stable')
    df = df.drop_duplicates(subset=['Mã chứng khoán', 'Loại báo cáo', 'Loại kỳ', 'Ngày kỳ', 'Chỉ tiêu tiếng Việt'], keep='first')
    print(f"  [Tầng 3] Deduplication. Còn {len(df):,} dòng.")
    
    # ---------- TẦNG 4: kiểm tra cân đối (chỉ cảnh báo) ----------
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
    
    # ---------- TẦNG 5: bỏ dòng 0, ép số nguyên int64 / số thập phân bỏ 0 thừa, điền Năm ----------
    print("  [Tầng 5] Loại bỏ các dòng trắng (Giá trị = 0) & Format số liệu...")
    vals = pd.to_numeric(df['Giá trị'], errors='coerce').round(4)
    keep = vals.notna() & np.isfinite(vals) & (vals != 0)
    df = df.loc[keep].copy()
    vals = vals.loc[keep]
    if df.empty:
        return pd.DataFrame(columns=STANDARD_COLUMNS)
    is_int = vals.eq(vals.round(0))
    fmt = pd.Series('', index=df.index, dtype=object)
    if is_int.any():
        fmt.loc[is_int] = vals.loc[is_int].astype('int64').astype(str)          # số nguyên -> int64, không đuôi .0
    if (~is_int).any():
        fmt.loc[~is_int] = vals.loc[~is_int].map(lambda f: format(f, '.4f').rstrip('0').rstrip('.'))   # bỏ số 0 thừa
    df['Giá trị'] = fmt
    df = df[df['Giá trị'].astype(str).str.strip().ne('')]

    # tự điền 'Năm' từ 'Ngày kỳ' nếu thiếu (còn thiếu nữa mới dùng năm hiện tại)
    nam = pd.to_numeric(df['Năm'], errors='coerce')
    nam_tu_ngay = pd.to_numeric(df['Ngày kỳ'].astype(str).str.extract(r'(\d{4})')[0], errors='coerce')
    df['Năm'] = nam.fillna(nam_tu_ngay).fillna(datetime.now().year).astype(int)
        
    print(f"  [Tầng 5] ✅ Đã xóa dòng trắng. Còn {len(df):,} dòng.")
    return df[STANDARD_COLUMNS]

# ==========================================
# 10.5 🆕 v17.4: TÍNH CHỈ SỐ ĐỊNH GIÁ DẪN XUẤT BẰNG PANDAS/NUMPY (hết dòng P/E, P/B, ROE = 0)
# ==========================================
VAL_METRIC_ALIASES = {
    'LNST': ['Lợi nhuận sau thuế TNDN', 'LNST của công ty mẹ', 'Lợi nhuận sau thuế thu nhập doanh nghiệp'],
    'VCSH': ['Vốn chủ sở hữu', 'Tổng vốn chủ sở hữu gồm cổ đông không kiểm soát'],
    'TTS':  ['Tổng cộng tài sản', 'Tổng tài sản'],
    'DT':   ['Doanh thu thuần', 'Doanh thu bán hàng và cung cấp dịch vụ', 'Tổng doanh thu'],
    'LG':   ['Lợi nhuận gộp'],
    'SLCP': ['Số lượng cổ phiếu phổ thông', 'Cổ phiếu đã phát hành'],
}

def compute_derived_valuation_metrics(df):
    """🆕 v17.4: EPS, BVPS, ROE, ROA, biên ròng/gộp, P/E, P/B, vốn hoá cho từng (mã, kỳ, ngày kỳ).
       Dùng pandas pivot + numpy; np.errstate chống chia 0; CHỈ sinh dòng khi mẫu số khác 0."""
    if df is None or df.empty: return []
    try:
        d = df.copy()
        d['Giá trị số'] = pd.to_numeric(d['Giá trị'], errors='coerce')
        d = d[d['Giá trị số'].notna() & (d['Giá trị số'] != 0)]
        if d.empty: return []

        # giá & SLCP real-time mới nhất mỗi mã
        px_df = d[d['Chỉ tiêu tiếng Việt'] == 'Giá cổ phiếu hiện tại'].sort_values('Ngày kỳ')
        px = px_df.groupby('Mã chứng khoán')['Giá trị số'].last()
        sh_df = d[d['Chỉ tiêu tiếng Việt'] == 'Tổng số lượng cổ phiếu lưu hành'].sort_values('Ngày kỳ')
        sh_rt = sh_df.groupby('Mã chứng khoán')['Giá trị số'].last()

        grp = d[d['Loại kỳ'].isin(['Năm', 'Quý'])]
        if grp.empty: return []
        pivot = grp.pivot_table(index=['Mã chứng khoán', 'Loại kỳ', 'Ngày kỳ', 'Năm'],
                                columns='Chỉ tiêu tiếng Việt', values='Giá trị số', aggfunc='first')
        if pivot.empty: return []

        def col(names):
            for n in names:
                if n in pivot.columns: return pivot[n]
            return pd.Series(np.nan, index=pivot.index)

        lnst = col(VAL_METRIC_ALIASES['LNST']); vcsh = col(VAL_METRIC_ALIASES['VCSH'])
        tts = col(VAL_METRIC_ALIASES['TTS']); dt = col(VAL_METRIC_ALIASES['DT'])
        lg = col(VAL_METRIC_ALIASES['LG']); slcp = col(VAL_METRIC_ALIASES['SLCP'])

        idx = pivot.index
        sym = idx.get_level_values('Mã chứng khoán')
        shares = slcp.fillna(pd.Series(sh_rt).reindex(sym).values).to_numpy(dtype=float)
        price = pd.Series(px).reindex(sym).to_numpy(dtype=float)
        lnst_v = lnst.to_numpy(dtype=float); vcsh_v = vcsh.to_numpy(dtype=float)
        tts_v = tts.to_numpy(dtype=float); dt_v = dt.to_numpy(dtype=float); lg_v = lg.to_numpy(dtype=float)

        with np.errstate(divide='ignore', invalid='ignore'):
            eps  = np.where(shares > 0, lnst_v / shares, np.nan)
            bvps = np.where(shares > 0, vcsh_v / shares, np.nan)
            roe  = np.where(vcsh_v != 0, lnst_v / vcsh_v * 100.0, np.nan)
            roa  = np.where(tts_v != 0, lnst_v / tts_v * 100.0, np.nan)
            nmgn = np.where(dt_v != 0, lnst_v / dt_v * 100.0, np.nan)
            gmgn = np.where(dt_v != 0, lg_v / dt_v * 100.0, np.nan)
            pe   = np.where(np.isfinite(eps) & (eps > 0) & np.isfinite(price) & (price > 0), price / np.where(eps > 0, eps, np.nan), np.nan)
            pb   = np.where(np.isfinite(bvps) & (bvps > 0) & np.isfinite(price) & (price > 0), price / np.where(bvps > 0, bvps, np.nan), np.nan)
            mcap = np.where(np.isfinite(price) & (price > 0) & (shares > 0), price * shares, np.nan)

        names = [('Lãi cơ bản trên cổ phiếu', eps, 2), ('Giá trị sổ sách mỗi cổ phiếu', bvps, 2),
                 ('Lợi nhuận trên vốn chủ sở hữu', roe, 4), ('Lợi nhuận trên tổng tài sản', roa, 4),
                 ('Biên lợi nhuận ròng', nmgn, 4), ('Biên lợi nhuận gộp', gmgn, 4),
                 ('Hệ số P/E cơ bản', pe, 4), ('Hệ số P/B', pb, 4), ('Vốn hóa thị trường', mcap, 0)]
        out = []
        for i, (s, ky, nk, nmv) in enumerate(idx):
            company_name, sector_name = get_company_profile(s)
            for label, arr, rnd in names:
                v = arr[i]
                if v is None or not np.isfinite(v) or v == 0: continue   # không sinh dòng 0 / NaN
                fv = int(round(float(v))) if rnd == 0 else round(float(v), rnd)
                out.append({'Mã chứng khoán': s, 'Tên doanh nghiệp': company_name, 'Tên ngành': sector_name,
                            'Loại báo cáo': 'Chỉ số thị trường, Định giá & Cổ tức',
                            'Loại kỳ': ky, 'Năm': int(nmv), 'Ngày kỳ': nk,
                            'Chỉ tiêu tiếng Việt': label, 'Giá trị': fv})
        print(f"  🧮 [v17.4] Đã tính {len(out):,} chỉ số định giá dẫn xuất (EPS/BVPS/ROE/ROA/P/E/P/B/vốn hoá).")
        return out
    except Exception as e:
        print(f"  ⚠️ [v17.4] Lỗi tính chỉ số dẫn xuất (đã chặn): {type(e).__name__}: {e}")
        return []

# v17.1: Báo cáo độ phủ QUÝ từng mã (gọi ở BƯỚC 7)
def export_coverage_report(df, tickers):
    q = df[df['Loại kỳ'] == 'Quý']
    g = df.groupby(['Mã chứng khoán', 'Loại kỳ']).size().unstack(fill_value=0)
    qp = q.groupby('Mã chứng khoán')['Ngày kỳ'].agg(['nunique', 'min', 'max'])
    rep = pd.DataFrame({'ticker': sorted(tickers)}).set_index('ticker')
    rep['so_ky_quy'] = qp['nunique'].reindex(rep.index).fillna(0).astype(int)
    rep['quy_dau'] = qp['min'].reindex(rep.index).fillna('')
    rep['quy_cuoi'] = qp['max'].reindex(rep.index).fillna('')
    rep['so_dong_quy'] = g.get('Quý', pd.Series(dtype=int)).reindex(rep.index).fillna(0).astype(int)
    rep['so_dong_nam'] = g.get('Năm', pd.Series(dtype=int)).reindex(rep.index).fillna(0).astype(int)
    rep = rep.sort_values('so_ky_quy').reset_index()
    rep.to_csv('data/_coverage_report.csv', index=False, encoding='utf-8-sig')
    weak = rep[rep['so_ky_quy'] < QUARTER_MIN_PERIODS]
    print(f"  📋 Coverage: {len(rep) - len(weak)}/{len(rep)} mã có ≥ {QUARTER_MIN_PERIODS} kỳ quý.")
    if not weak.empty:
        print("  ⚠️ Mã thiếu quý:", ", ".join(f"{r.ticker}({r.so_ky_quy})" for r in weak.itertuples()))
    return rep

# 🆕 v17.3: xuất danh sách nhãn tiếng Anh chưa có trong từ điển để bổ sung lần sau
def export_unmapped_report():
    try:
        if _UNMAPPED_METRICS:
            os.makedirs('data', exist_ok=True)
            pd.DataFrame({'nhan_chua_co_trong_tu_dien': sorted(_UNMAPPED_METRICS)}).to_csv(
                'data/_unmapped_metrics.csv', index=False, encoding='utf-8-sig')
            print(f"  📝 {len(_UNMAPPED_METRICS)} nhãn chưa có trong từ điển -> data/_unmapped_metrics.csv")
        else:
            print("  📝 Tất cả nhãn đều đã có trong từ điển.")
    except Exception as e:
        print(f"  ⚠️ Không ghi được _unmapped_metrics.csv: {e}")

# v17.2: dọn sạch file tạm
def _cleanup_temp_files():
    targets = ['data/_checkpoint.csv', 'data/_emergency_backup.csv', 'data/_emergency_backup.parquet',
               '_checkpoint.csv']
    for pattern in ('data/bao_cao_*.csv', 'bao_cao_*.csv', 'du_lieu/bao_cao_*.csv'):
        targets.extend(glob.glob(pattern))
    removed = 0
    for f in targets:
        if os.path.exists(f):
            try:
                os.remove(f)
                removed += 1
            except Exception:
                pass
    if removed:
        print(f"  🧽 Đã dọn {removed} file tạm.")

# ==========================================
# 11. MAIN (GIỮ NGUYÊN KHUNG BƯỚC 0->8 + 🆕 v17.4 BƯỚC 6.5)
# ==========================================
def main():
    global _ALL_RECORDS_GLOBAL
    print("=" * 62)
    print("🚀 FINEX VN STOCK DATABASE CRAWLER — v17.4 (CHUẨN ĐƠN VỊ + CHỈ SỐ ĐỊNH GIÁ DẪN XUẤT)")
    print("=" * 62)
    print(f"  ⚙️ SKIP_VNDIRECT = {SKIP_VNDIRECT} | SUPABASE_PURGE = {SUPABASE_PURGE} | PUSH_TO_SUPABASE = {PUSH_TO_SUPABASE}")

    ticker_market_map = load_176_master_tickers()
    all_master_records = []

    def _accumulate(recs, source):
        global _ALL_RECORDS_GLOBAL
        if not recs: return
        _add_source(recs, source)
        all_master_records.extend(recs)
        _ALL_RECORDS_GLOBAL = all_master_records

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

    # BƯỚC 3 — VNDIRECT BCTC (mặc định BỎ QUA)
    if SKIP_VNDIRECT:
        print("\n⏭️ BƯỚC 3: BỎ QUA [VNDIRECT_BCTC] (SKIP_VNDIRECT=true).")
    else:
        print(f"\n⭐ BƯỚC 3: Cào BCTC Quý + Năm [VNDIRECT_BCTC] cho {len(ticker_market_map)} mã...")
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = {executor.submit(fetch_vndirect_bctc_financials, symbol): symbol for symbol in ticker_market_map.keys()}
            done = 0
            for future in as_completed(futures):
                done += 1
                sym = futures[future]
                try:
                    res = future.result()
                    if res:
                        _accumulate(res, 'VNDIRECT_BCTC')
                        nq = len({r['Ngày kỳ'] for r in res if r['Loại kỳ'] == 'Quý'})
                        print(f"  ✓ [{done}/{len(ticker_market_map)}] {sym}: {nq} kỳ Quý | {len(res):,} dòng")
                    else:
                        print(f"  ✗ [{done}/{len(ticker_market_map)}] {sym}: 0 dòng")
                except Exception as e:
                    print(f"  ✗ {sym}: {type(e).__name__}: {e}")
                if done % 25 == 0:
                    _save_checkpoint(f"VNDIRECT_{done}/{len(ticker_market_map)}")
        _save_checkpoint("sau_VNDIRECT_BCTC")

    # BƯỚC 4 — Yfinance backup
    print(f"\n🔄 BƯỚC 4: Cào Yfinance song song [YFINANCE]...")
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = {executor.submit(process_single_ticker, symbol, cat): symbol for symbol, cat in ticker_market_map.items()}
        for future in as_completed(futures):
            try:
                res = future.result()
                if res: _accumulate(res, 'YFINANCE')
            except Exception: pass
    _save_checkpoint("sau_YFINANCE")

    # BƯỚC 5
    print(f"\n🐢 BƯỚC 5: Kiểm tra thiếu + fallback Giá/SLCP...")
    df_temp = pd.DataFrame(all_master_records)

    if not df_temp.empty:
        q_periods = df_temp[df_temp['Loại kỳ'] == 'Quý'].groupby('Mã chứng khoán')['Ngày kỳ'].nunique()
        q_syms = set(q_periods[q_periods >= QUARTER_MIN_PERIODS].index)
        print(f"  📊 Đã có {len(q_syms)}/{len(ticker_market_map)} mã có ≥ {QUARTER_MIN_PERIODS} kỳ Quý.")

        # v17.2: bù QUÝ bằng yfinance đa luồng (8 luồng, timeout ngắn, không retry)
        missing_q = [s for s in ticker_market_map.keys() if s not in q_syms]
        if missing_q:
            print(f"  🩹 {len(missing_q)} mã thiếu Quý. Bù bằng yfinance đa luồng ({QUARTER_WORKERS} luồng)...")
            q_recs = fetch_quarter_multithread(missing_q)
            if q_recs:
                _accumulate(q_recs, 'YF_QUARTER')
                print(f"  ✅ Bù quý xong: +{len(q_recs):,} dòng.")
            _save_checkpoint("sau_YF_QUARTER_BU_QUY")

        prices = df_temp[(df_temp['Chỉ tiêu tiếng Việt'] == 'Giá cổ phiếu hiện tại') & (pd.to_numeric(df_temp['Giá trị'], errors='coerce') > 0)]
        symbols_with_price = set(prices['Mã chứng khoán'].unique()) if not prices.empty else set()
        shares = df_temp[(df_temp['Chỉ tiêu tiếng Việt'] == 'Tổng số lượng cổ phiếu lưu hành') & (pd.to_numeric(df_temp['Giá trị'], errors='coerce') > 0)]
        symbols_with_shares = set(shares['Mã chứng khoán'].unique()) if not shares.empty else set()

        missing_price_shares = [s for s in ticker_market_map.keys() if s not in symbols_with_price or s not in symbols_with_shares]
        if missing_price_shares:
            print(f"  🎯 {len(missing_price_shares)} mã thiếu Giá/SLCP. Cào bù VNDirect + VPS...")
            with ThreadPoolExecutor(max_workers=5) as executor:
                futures = {}
                for s in missing_price_shares:
                    futures[executor.submit(fetch_vndirect_fallback, s)] = s
                    futures[executor.submit(fetch_vps_fallback, s)] = s
                for future in as_completed(futures):
                    try:
                        res = future.result()
                        if res: _accumulate(res, 'VNDIRECT')
                    except Exception: pass

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

    # 🆕 v17.4 BƯỚC 6.5: tính chỉ số định giá dẫn xuất bằng pandas/numpy (chèn/đè giá trị 0-sai cũ)
    if not df_clean.empty:
        derived = compute_derived_valuation_metrics(df_clean)
        if derived:
            df_der = pd.DataFrame(derived)[STANDARD_COLUMNS]
            df_all = pd.concat([df_clean, df_der], ignore_index=True)
            df_all = df_all.drop_duplicates(subset=['Mã chứng khoán', 'Loại báo cáo', 'Loại kỳ', 'Ngày kỳ', 'Chỉ tiêu tiếng Việt'], keep='last')
            df_clean = df_all[STANDARD_COLUMNS]
            print(f"  ✅ [BƯỚC 6.5] Gộp chỉ số dẫn xuất -> tổng {len(df_clean):,} dòng.")

    # BƯỚC 7
    os.makedirs('data', exist_ok=True)
    csv_path = 'data/vietnam_stock_database_tong_hop.csv'
    parquet_path = 'data/vietnam_stock_database.parquet'

    _cleanup_temp_files()

    df_clean.to_csv(csv_path, index=False, encoding='utf-8-sig')
    df_clean.to_parquet(parquet_path, engine='pyarrow', index=False)
    print(f"\n💾 ĐÃ LƯU FILE:")
    print(f"   → CSV:     {csv_path}")
    print(f"   → PARQUET: {parquet_path} ({os.path.getsize(parquet_path)/1024/1024:.2f} MB)")

    if not df_clean.empty:
        export_coverage_report(df_clean, set(ticker_market_map.keys()))
    export_unmapped_report()   # 🆕 v17.3

    # BƯỚC 8
    if PUSH_TO_SUPABASE:
        print("\n📤 BƯỚC 8: Đẩy Supabase...")
        if SUPABASE_PURGE:
            purge_bad_rows_supabase()   # 🆕 v17.3: dọn dòng 0 / trống / rác / tiếng Anh trước khi upsert
        upsert_to_supabase(df_clean)

    _cleanup_temp_files()

    print("=" * 62)
    print(f" 🎉 HOÀN TẤT! Tổng: {len(df_clean):,} dòng")
    if not df_clean.empty:
        print(f" - Số mã: {df_clean['Mã chứng khoán'].nunique()}/176")
        for k, v in df_clean['Loại kỳ'].value_counts().items():
            print(f"     • {k}: {v:,}")
        # 🆕 v17.4: kiểm chứng thang giá trị
        px_chk = pd.to_numeric(df_clean[df_clean['Chỉ tiêu tiếng Việt'] == 'Giá cổ phiếu hiện tại']['Giá trị'], errors='coerce')
        if not px_chk.empty:
            print(f" - Giá cp: min={px_chk.min():,.0f} | max={px_chk.max():,.0f} VNĐ (thang hợp lệ 100 -> 5.000.000)")
    print("=" * 62)

if __name__ == "__main__":
    main()
