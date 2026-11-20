"""
FINEX VN STOCK DATABASE CRAWLER - v19.0
========================================
Vá triệt để 5 ảnh lỗi:
  ✅ ẢNH 1+2: Không còn nhãn tiếng Anh lọt vào CSV/Supabase (standardize → None nếu vẫn English)
  ✅ ẢNH 3: Nhãn cụt + trùng [2] đã được fix (khớp chính xác + strip [n])
  ✅ ẢNH 4: Supabase không còn dòng rỗng / "Của" / value=0 / nhãn rác
  ✅ ẢNH 5: Không còn đuôi .0, không còn trùng do chưa normalize
  ✅ Từ điển ~500 key phủ kín line-item yfinance/VAS/ngân hàng/CTCK/bảo hiểm
  ✅ GIỮ NGUYÊN khung v18.0: SIGTERM, Supabase, 176 mã, đa nguồn, emergency save
"""
import os
import socket
socket.setdefaulttimeout(15)

import glob
import signal
import sys
import time
import threading
import random
import math
import re
import unicodedata
from datetime import datetime
from functools import lru_cache
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd
import numpy as np
import requests
from requests.adapters import HTTPAdapter

# ==============================================================================
# 🛡️ SIGTERM EMERGENCY SAVE
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
# 1. VAS WHITELIST — 100% giữ nguyên v18 + bổ sung
# ==============================================================================
VAS_WHITELIST = set([
    # --- Doanh nghiệp sản xuất/thương mại/dịch vụ/BĐS/Xây dựng ---
    "Tài sản ngắn hạn", "Tiền và các khoản tương đương tiền", "Tiền", "Các khoản tương đương tiền",
    "Đầu tư tài chính ngắn hạn", "Chứng khoán kinh doanh", "Dự phòng giảm giá chứng khoán kinh doanh",
    "Đầu tư nắm giữ đến ngày đáo hạn",
    "Các khoản phải thu ngắn hạn", "Phải thu ngắn hạn của khách hàng", "Trả trước cho người bán ngắn hạn",
    "Phải thu nội bộ ngắn hạn", "Phải thu theo tiến độ kế hoạch hợp đồng xây dựng",
    "Phải thu về cho vay ngắn hạn", "Phải thu ngắn hạn khác", "Dự phòng phải thu ngắn hạn khó đòi",
    "Tài sản thiếu chờ xử lý", "Hàng tồn kho", "Dự phòng giảm giá hàng tồn kho",
    "Tài sản ngắn hạn khác", "Chi phí trả trước ngắn hạn", "Thuế GTGT được khấu trừ",
    "Thuế và các khoản khác phải thu Nhà nước", "Giao dịch mua bán lại trái phiếu Chính phủ",
    "Tài sản dài hạn", "Các khoản phải thu dài hạn", "Phải thu dài hạn của khách hàng",
    "Trả trước cho người bán dài hạn", "Vốn kinh doanh ở đơn vị trực thuộc",
    "Phải thu nội bộ dài hạn", "Phải thu về cho vay dài hạn", "Phải thu dài hạn khác",
    "Dự phòng phải thu dài hạn khó đòi",
    "Tài sản cố định", "Tài sản cố định hữu hình", "Nguyên giá", "Hao mòn lũy kế",
    "Tài sản cố định thuê tài chính", "Tài sản cố định vô hình",
    "Bất động sản đầu tư", "Tài sản dở dang dài hạn",
    "Chi phí sản xuất, kinh doanh dở dang dài hạn", "Chi phí xây dựng cơ bản dở dang",
    "Đầu tư tài chính dài hạn", "Đầu tư vào công ty con", "Đầu tư vào công ty liên doanh, liên kết",
    "Đầu tư góp vốn vào đơn vị khác", "Dự phòng đầu tư tài chính dài hạn",
    "Tài sản dài hạn khác", "Chi phí trả trước dài hạn", "Tài sản thuế thu nhập hoãn lại",
    "Thiết bị, vật tư, phụ tùng thay thế dài hạn", "Lợi thế thương mại",
    "Tổng cộng tài sản", "Báo cáo tình hình tài chính",
    "Nợ phải trả", "Nợ ngắn hạn", "Phải trả người bán ngắn hạn", "Người mua trả tiền trước ngắn hạn",
    "Thuế và các khoản phải nộp Nhà nước", "Phải trả người lao động", "Chi phí phải trả ngắn hạn",
    "Phải trả nội bộ ngắn hạn", "Phải trả theo tiến độ kế hoạch hợp đồng xây dựng",
    "Doanh thu chưa thực hiện ngắn hạn", "Phải trả ngắn hạn khác",
    "Vay và nợ thuê tài chính ngắn hạn", "Dự phòng phải trả ngắn hạn",
    "Quỹ khen thưởng, phúc lợi", "Quỹ bình ổn giá",
    "Nợ dài hạn", "Phải trả người bán dài hạn", "Người mua trả tiền trước dài hạn",
    "Chi phí phải trả dài hạn", "Phải trả nội bộ về vốn kinh doanh", "Phải trả nội bộ dài hạn",
    "Doanh thu chưa thực hiện dài hạn", "Phải trả dài hạn khác",
    "Vay và nợ thuê tài chính dài hạn", "Trái phiếu chuyển đổi", "Cổ phiếu ưu đãi",
    "Thuế thu nhập hoãn lại phải trả", "Dự phòng phải trả dài hạn",
    "Quỹ phát triển khoa học và công nghệ",
    "Vốn chủ sở hữu", "Vốn góp của chủ sở hữu", "Cổ phiếu phổ thông có quyền biểu quyết",
    "Thặng dư vốn cổ phần", "Quyền chọn chuyển đổi trái phiếu", "Vốn khác của chủ sở hữu",
    "Cổ phiếu quỹ", "Chênh lệch đánh giá lại tài sản", "Chênh lệch tỷ giá hối đoái",
    "Quỹ đầu tư phát triển", "Quỹ hỗ trợ sắp xếp doanh nghiệp", "Quỹ khác thuộc vốn chủ sở hữu",
    "Lợi nhuận sau thuế chưa phân phối",
    "LNST chưa phân phối lũy kế đến cuối kỳ trước", "LNST chưa phân phối kỳ này",
    "Nguồn vốn đầu tư XDCB", "Lợi ích cổ đông không kiểm soát",
    "Nguồn kinh phí và quỹ khác", "Nguồn kinh phí", "Nguồn kinh phí đã hình thành TSCĐ",
    "Tổng cộng nguồn vốn",
    # --- KQKD ---
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
    # --- LCTT ---
    "Lợi nhuận trước thuế", "Khấu hao TSCĐ và BĐSĐT", "Các khoản dự phòng",
    "Lãi/lỗ chênh lệch tỷ giá do đánh giá lại các khoản mục tiền tệ gốc ngoại tệ",
    "Lãi/lỗ chênh lệch tỷ giá", "Lãi/lỗ từ hoạt động đầu tư", "Các khoản điều chỉnh khác",
    "Lợi nhuận từ HĐKD trước thay đổi vốn lưu động",
    "Tăng/giảm các khoản phải thu", "Tăng/giảm hàng tồn kho", "Tăng/giảm các khoản phải trả",
    "Tăng/giảm chi phí trả trước", "Tăng/giảm chứng khoán kinh doanh",
    "Tiền lãi vay đã trả", "Chi phí đi vay đã trả", "Thuế TNDN đã nộp",
    "Tiền thu khác từ HĐKD", "Tiền chi khác cho HĐKD",
    "Lưu chuyển tiền thuần từ HĐKD",
    "Tiền thu từ bán hàng, cung cấp dịch vụ và doanh thu khác",
    "Tiền chi trả người cung cấp hàng hóa, dịch vụ", "Tiền chi trả người lao động",
    "Tiền chi mua sắm, xây dựng TSCĐ và tài sản dài hạn khác",
    "Tiền thu thanh lý, nhượng bán TSCĐ và tài sản dài hạn khác",
    "Tiền chi cho vay, mua công cụ nợ của đơn vị khác",
    "Tiền thu hồi cho vay, bán lại công cụ nợ của đơn vị khác",
    "Tiền chi đầu tư góp vốn vào đơn vị khác", "Tiền thu hồi đầu tư góp vốn vào đơn vị khác",
    "Tiền thu lãi cho vay, cổ tức và lợi nhuận được chia",
    "Lưu chuyển tiền thuần từ HĐĐT",
    "Tiền thu từ phát hành cổ phiếu, nhận vốn góp của chủ sở hữu",
    "Tiền trả lại vốn góp, mua lại cổ phiếu đã phát hành",
    "Tiền thu từ đi vay", "Tiền trả nợ gốc vay", "Tiền trả nợ gốc thuê tài chính",
    "Cổ tức, lợi nhuận đã trả cho chủ sở hữu", "Lưu chuyển tiền thuần từ HĐTC",
    "Lưu chuyển tiền thuần trong kỳ", "Tiền và tương đương tiền đầu kỳ",
    "Ảnh hưởng của thay đổi tỷ giá quy đổi ngoại tệ", "Tiền và tương đương tiền cuối kỳ",
    # --- Ngân hàng ---
    "Tiền mặt, vàng bạc, đá quý", "Tiền gửi tại Ngân hàng Nhà nước",
    "Tiền gửi tại và cho vay các tổ chức tín dụng khác",
    "Các công cụ tài chính phái sinh và tài sản tài chính khác",
    "Cho vay khách hàng", "Hoạt động mua nợ", "Chứng khoán đầu tư",
    "Góp vốn, đầu tư dài hạn", "Tài sản Có khác",
    "Nợ Chính phủ và Ngân hàng Nhà nước",
    "Tiền gửi và vay các tổ chức tín dụng khác", "Tiền gửi của khách hàng",
    "Công cụ tài chính phái sinh và nợ tài chính khác",
    "Vốn tài trợ, ủy thác đầu tư", "Phát hành giấy tờ có giá", "Vốn điều lệ",
    "Thu nhập lãi thuần", "Thu nhập từ dịch vụ", "Lãi thuần từ dịch vụ",
    "Lãi thuần từ ngoại hối và vàng", "Lãi thuần từ chứng khoán kinh doanh",
    "Lãi thuần từ chứng khoán đầu tư", "Thu nhập hoạt động khác",
    "Chi phí hoạt động (CIR)", "Lợi nhuận trước dự phòng rủi ro tín dụng",
    "Chi phí dự phòng rủi ro tín dụng", "Thu nhập lãi nhận được",
    "Chi phí lãi đã trả", "Thu từ dịch vụ", "Thu nợ đã xóa",
    "Chi cho nhân viên và quản lý",
    # --- Chứng khoán ---
    "Tài sản tài chính",
    "Các tài sản tài chính ghi nhận thông qua lãi lỗ (FVTPL)",
    "Các khoản đầu tư nắm giữ đến ngày đáo hạn (HTM)",
    "Các khoản cho vay (Margin)",
    "Tài sản tài chính sẵn sàng để bán (AFS)", "Dự phòng suy giảm giá trị",
    "Các khoản phải thu (bán tài sản tài chính, cổ tức và lãi dự thu)",
    "Phải thu dịch vụ CTCK", "Phải thu lỗi giao dịch",
    "Vay và nợ thuê tài chính", "Vay tài sản tài chính",
    "Trái phiếu chuyển đổi (cấu phần nợ)", "Trái phiếu phát hành",
    "Vay Quỹ hỗ trợ thanh toán", "Phải trả hoạt động giao dịch chứng khoán",
    "Nhận ký quỹ, ký cược", "Quỹ dự trữ bổ sung vốn điều lệ",
    "Quỹ dự phòng tài chính và rủi ro nghiệp vụ",
    "Doanh thu hoạt động",
    "Lãi từ FVTPL (lãi bán, chênh lệch đánh giá lại, cổ tức và lãi)",
    "Lãi HTM", "Lãi cho vay và phải thu", "Lãi AFS",
    "Lãi phái sinh phòng ngừa", "Doanh thu môi giới",
    "Bảo lãnh và đại lý phát hành", "Tư vấn đầu tư", "Lưu ký", "Tư vấn tài chính",
    "Chi phí hoạt động", "Lỗ FVTPL", "Lỗ HTM", "Lỗ AFS khi phân loại lại",
    "Chi phí dự phòng, xử lý tổn thất và chi phí đi vay của khoản cho vay",
    "Chi phí tự doanh, môi giới, bảo lãnh, tư vấn đầu tư, lưu ký, tư vấn tài chính và dịch vụ khác",
    "Doanh thu hoạt động tài chính", "Lãi tỷ giá", "Cổ tức và lãi tiền gửi",
    "Lãi bán, thanh lý công ty con, liên kết", "Chi phí tài chính",
    "Lỗ tỷ giá", "Chi phí lãi vay", "Lỗ thanh lý đầu tư",
    "Dự phòng đầu tư dài hạn", "Chi phí bán hàng", "Chi phí quản lý CTCK",
    "Kết quả hoạt động",
    # --- Bảo hiểm ---
    "Tài sản tái bảo hiểm",
    "Dự phòng phí và dự phòng bồi thường nhượng tái bảo hiểm",
    "Ký quỹ bảo hiểm", "Dự phòng nghiệp vụ",
    "Dự phòng phí chưa được hưởng", "Dự phòng toán học", "Dự phòng bồi thường",
    "Dự phòng chia lãi", "Dự phòng đảm bảo cân đối",
    "Phải thu và phải trả hoạt động nhận và nhượng tái bảo hiểm",
    "Phí bảo hiểm gốc", "Phí nhận tái bảo hiểm", "Phí nhượng tái bảo hiểm",
    "Thay đổi dự phòng phí", "Doanh thu phí bảo hiểm thuần",
    "Hoa hồng nhượng tái và doanh thu khác", "Doanh thu thuần hoạt động bảo hiểm",
    "Chi bồi thường gốc và nhận tái", "Thu bồi thường nhượng tái",
    "Thay đổi dự phòng bồi thường", "Chi hoa hồng", "Lợi nhuận gộp bảo hiểm",
    # --- Bổ sung v19 ---
    "Chứng khoán đầu tư giữ đến ngày đáo hạn", "Chứng khoán đầu tư sẵn sàng để bán",
    "Thu nhập lãi và các khoản thu nhập tương tự",
    "Chi phí lãi và các chi phí tương tự",
    "Thu nhập từ hoạt động dịch vụ", "Chi phí hoạt động dịch vụ",
    "Lãi thuần từ hoạt động dịch vụ",
    "Lãi thuần từ hoạt động kinh doanh ngoại hối",
    "Lãi thuần từ mua bán chứng khoán kinh doanh",
    "Lãi thuần từ mua bán chứng khoán đầu tư",
    "Thu nhập từ hoạt động khác", "Chi phí hoạt động khác",
    "Lãi thuần từ hoạt động khác", "Tổng thu nhập hoạt động",
    "Dự phòng rủi ro tín dụng",
    "Chi phí bán hàng và quản lý doanh nghiệp", "Tổng chi phí",
    "Thu nhập lãi",
    "Lợi nhuận trước lãi vay và thuế (EBIT)",
    "Lợi nhuận trước lãi vay, thuế và khấu hao (EBITDA)",
    "Dòng tiền tự do (FCF)",
    "Số lượng cổ phiếu bình quân cơ bản",
    "Số lượng cổ phiếu bình quân pha loãng",
    "Số lượng cổ phiếu phổ thông", "Cổ phiếu đã phát hành",
    "Số lượng cổ phiếu ròng", "Tổng nợ vay",
    "Tổng lợi nhuận HĐKD như báo cáo", "Khấu hao được điều chỉnh",
    "Biến động vốn lưu động", "Lợi nhuận thuần chuẩn hóa",
    "Lợi nhuận sau thuế từ hoạt động tiếp tục",
    "Tiền thu từ đi vay dài hạn", "Tiền trả nợ gốc vay dài hạn",
    "Cho vay khách hàng thuần", "Thu nhập phí và hoa hồng",
    "Tài sản cố định hữu hình thuần", "Nguyên giá tài sản cố định hữu hình",
    "Hao mòn lũy kế tài sản cố định",
    "Lợi thế thương mại và tài sản vô hình",
    "Tài sản cố định vô hình khác", "Bất động sản khác",
    "Nhà cửa và vật kiến trúc", "Đất đai và cải tạo đất",
    "Máy móc, thiết bị và phương tiện vận tải", "Xây dựng cơ bản dở dang",
    "Tài sản quyền sử dụng đất và thuê tài chính",
    "Nguyên liệu, vật liệu tồn kho", "Chi phí sản xuất kinh doanh dở dang",
    "Thành phẩm tồn kho", "Tiền bị hạn chế",
    "Thuế phải thu", "Thuế phải thu ngắn hạn",
    "Thuế phải trả", "Thuế phải trả ngắn hạn", "Tổng thuế phải trả",
    "Cổ tức phải trả", "Phải trả khác", "Phải thu ngắn hạn khác",
    "Phải thu dài hạn khác", "Phải trả ngắn hạn khác", "Phải trả dài hạn khác",
    "Đầu tư ngắn hạn", "Đầu tư dài hạn", "Đầu tư vào liên doanh",
    "Đầu tư vào công ty liên kết",
    "Đầu tư vào liên doanh theo giá gốc",
    "Đầu tư vào công ty liên kết theo giá gốc",
    "Thuế thu nhập hoãn lại phải trả ngắn hạn",
    "Thuế thu nhập hoãn lại phải trả dài hạn",
    "Quỹ phúc lợi nhân viên ngắn hạn", "Quỹ phúc lợi nhân viên và hưu trí",
    "Tiền mặt, tương đương tiền và đầu tư ngắn hạn",
    "Các khoản thanh toán tiền mặt",
    "Các khoản thanh toán tiền mặt khác từ HĐKD",
    "Thanh toán cho người lao động",
    "Các khoản thu tiền mặt từ HĐKD",
    "Các khoản thu tiền mặt khác từ HĐKD",
    "Các khoản thanh toán tiền mặt khác từ HĐ đầu tư",
    "Các khoản thu tiền mặt khác từ HĐ đầu tư",
    "Các khoản thanh toán tiền mặt khác từ HĐ tài chính",
    "Các khoản thu tiền mặt khác từ HĐ tài chính",
    "Cổ tức đã nhận", "Thu từ thanh lý tài sản cố định",
    "Chi mua sắm tài sản cố định",
    "Tổng các khoản mục bất thường (Không gồm lợi thế thương mại)",
    "Lợi nhuận ròng pha loãng phân bổ cho CĐ phổ thông",
    "Lợi nhuận ròng phân bổ cho cổ đông phổ thông",
    "Tổng chi phí tài chính khác",
    "Thu nhập/chi phí lãi thuần ngoài HĐKD",
    "Thu nhập/chi phí khác", "Lợi nhuận ròng bất thường",
    "Lợi nhuận ròng từ hoạt động không liên tục",
    "Lợi nhuận ròng từ hoạt động liên tục",
    "Chi phí thu nhập đặc biệt", "Chi phí đặc biệt khác",
    "Xóa sổ", "Tổn thất tài sản và dự phòng",
    "Thuế thu nhập hoãn lại",
    "Biến động các khoản phải thu", "Biến động hàng tồn kho",
    "Biến động các khoản phải trả", "Biến động phải trả người bán",
    "Biến động vốn lưu động khác",
    "Chi phí đầu tư tài sản cố định (CapEx)",
    "Tiền mua hoặc thanh lý tài sản cố định",
    "Tiền mua hoặc bán tài sản vô hình",
    "Tiền đầu tư góp vốn thuần",
    "Tiền mua bán công ty con hoặc sáp nhập",
    "Tiền thu từ phát hành nợ vay", "Tiền chi trả nợ gốc vay",
    "Tiền thu từ phát hành cổ phiếu hoặc bán cổ phiếu quỹ",
    "Cổ tức đã chi trả cho chủ sở hữu",
    "Ảnh hưởng thay đổi tỷ giá và tiền thuần thay đổi",
    "Lãi / Lỗ từ bán chứng khoán",
    "Cổ tức cổ phiếu ưu đãi và điều chỉnh khác",
    "Ảnh hưởng thuế từ các khoản mục bất thường",
    "Thuế suất dùng để tính toán",
    "Lãi / Lỗ từ đánh giá hoặc thanh lý tài sản",
    "Ảnh hưởng thay đổi tỷ giá hối đoái",
    "Lợi nhuận ròng từ HĐKD liên tục trừ lợi ích CĐ không kiểm soát",
    "Lợi nhuận thuần từ hoạt động tiếp tục và không tiếp tục",
    "Lợi nhuận sau thuế bao gồm lợi ích cổ đông không kiểm soát",
    "Tổng vốn chủ sở hữu gồm cổ đông không kiểm soát",
    "Vốn lưu động ròng", "Nợ vay ròng",
    "Chênh lệch đánh giá lại tài sản và chênh lệch tỷ giá",
    "Các khoản phải trả", "Các khoản phải thu",
    "Phải thu các bên liên quan ngắn hạn",
    "Tổng tài sản dài hạn", "Tổng nợ phải trả",
    "Lãi / Lỗ chênh lệch tỷ giá hối đoái thuần",
    "Lãi/lỗ từ chứng khoán đầu tư",
    "Tiền thu từ đi vay dài hạn (thuần)",
    "Tiền trả nợ gốc vay dài hạn (thuần)",
    "Tiền thu từ đi vay ngắn hạn", "Tiền trả nợ gốc vay ngắn hạn",
    "Tiền lãi vay đã trả (HĐTC)", "Tiền lãi nhận được (HĐĐT)",
    "Tiền lãi nhận được (HĐKD)", "Thuế TNDN đã nộp (thực nộp)",
    "Thuế được hoàn lại", "Biến động chi phí trả trước",
    "Các khoản mục phi tiền mặt khác",
    # --- Bổ sung v19 (từ ảnh lỗi) ---
    "Giá vốn hàng bán (điều chỉnh)", "Phân bổ chứng khoán",
    "Phân bổ tài sản vô hình", "Lãi từ chứng khoán đầu tư",
    "Lỗ từ chứng khoán đầu tư",
    "Lãi/lỗ chưa thực hiện từ chứng khoán đầu tư",
    "Lãi/lỗ đã thực hiện từ chứng khoán đầu tư",
    "Lãi/lỗ chênh lệch tỷ giá hối đoái",
    "Lãi từ thanh lý tài sản cố định", "Lãi từ bán công ty con",
    "Lãi/lỗ từ đầu tư góp vốn", "Lãi từ công ty liên kết",
    "Lãi từ công ty liên kết (sau thuế)",
    "Tổng các khoản mục bất thường",
    "Tổn thất tài sản cố định",
    "Chi phí tái cấu trúc và sáp nhập",
    "Chi phí cổ phiếu thưởng cho nhân viên",
    "Ưu đãi thuế vượt trội từ cổ phiếu thưởng",
    "Dự phòng và xóa sổ tài sản",
    "Dự phòng phải thu khó đòi",
    "Tiền vay/trả nợ gốc thuần",
    "Tiền thu từ đi vay dài hạn (thuần)",
    "Tiền thu từ đi vay ngắn hạn (thuần)",
    "Tiền trả nợ gốc vay ngắn hạn",
    "Tiền lãi vay đã trả (bổ sung)",
    "Thuế TNDN đã nộp (bổ sung)",
    "Thuế đã nộp",
    "Cổ tức đã trả (HĐKD)", "Cổ tức đã nhận (HĐKD)",
    "Cổ tức đã nhận (HĐĐT)",
    "Cổ tức đã trả",
    "Cổ tức đã trả cho cổ đông phổ thông",
    "Cổ tức đã trả cho cổ đông ưu đãi",
    "Biến động các khoản phải trả",
    "Biến động phải trả và chi phí phải trả",
    "Biến động chi phí phải trả",
    "Biến động chi phí trả trước",
    "Biến động tài sản ngắn hạn khác",
    "Biến động nợ ngắn hạn khác",
    "Biến động thuế phải trả",
    "Biến động cổ tức phải trả",
    "Điều chỉnh tiền khác trong biến động tiền",
    "Điều chỉnh tiền khác ngoài biến động tiền",
    "Tiền chi đầu tư góp vốn", "Tiền thu hồi đầu tư góp vốn",
    "Tiền mua công ty con", "Tiền bán công ty con",
    "Tiền thu từ phát hành cổ phiếu",
    "Tiền mua lại cổ phiếu quỹ",
    "Chi phí tài chính khác thuần",
    "Biến động đầu tư khác thuần",
    "Chi phí thuê mặt bằng", "Chi phí bảo hiểm và bồi thường",
    "Chi phí lương và nhân công",
    "Chi phí quản lý doanh nghiệp khác",
    "Thu nhập lãi ngoài hoạt động",
    "Chi phí lãi ngoài hoạt động",
    "Tổng thu nhập/chi phí khác thuần",
    "Lãi thuần từ đầu tư",
    "Lãi/lỗ từ hoạt động tự doanh",
    "Lãi/lỗ đã thực hiện từ đầu tư",
    "Số lượng cổ phiếu quỹ", "Nợ thuê tài chính",
    "Nợ thuê tài chính ngắn hạn", "Nợ thuê tài chính dài hạn",
    "Dự phòng phải trả ngắn hạn", "Dự phòng phải trả dài hạn",
    "Phải trả người lao động ngắn hạn",
    "Phải trả người lao động dài hạn",
    "Phải trả phúc lợi nhân viên dài hạn",
    "Quỹ phúc lợi nhân viên và hưu trí dài hạn",
    "Phải trả thương mại và khác dài hạn",
    "Tài sản thuế thu nhập hoãn lại dài hạn",
    "Nợ hoãn lại dài hạn",
    "Chi phí phải trả dài hạn",
    "Phải thu theo giấy nợ dài hạn",
    "Phải thu khách hàng dài hạn",
    "Chi phí trả trước dài hạn",
    "Tài sản thuế thu nhập hoãn lại ngắn hạn",
    "Nợ hoãn lại ngắn hạn",
    "Chi phí phải trả ngắn hạn",
    "Phải thu theo giấy nợ ngắn hạn",
    "Chi phí trả trước ngắn hạn",
    "Hạn mức tín dụng", "Thương phiếu",
    "Vay ngắn hạn khác", "Vay dài hạn khác",
    "Nợ công cụ phái sinh", "Tài sản phái sinh",
    "Tài sản phòng ngừa rủi ro ngắn hạn",
    "Tài sản phòng ngừa rủi ro dài hạn",
    "Tài sản nắm giữ để bán ngắn hạn",
    "Nợ gắn với tài sản nắm giữ để bán",
    "Tài sản nắm giữ để bán",
    "Đầu tư bị hạn chế",
    "Tiền, tương đương tiền và đầu tư ngắn hạn",
    "Tổng đầu tư thị trường tiền tệ",
    "Đầu tư thị trường tiền tệ",
    "Tài sản tài chính",
    "Tài sản tài chính ghi nhận qua lãi lỗ (FVTPL)",
    "Các khoản cho vay phải thu",
    "Cho vay khách hàng (gộp)",
    "Chứng khoán và đầu tư",
    "Đầu tư góp vốn dài hạn",
    "Đầu tư vào công ty con theo giá gốc",
    "Đầu tư vào công ty con",
    "Đầu tư vào công ty liên kết",
    "Đầu tư vào liên doanh",
    "Đầu tư khác",
    "Phải thu khách hàng (gộp)",
    "Phải thu các bên liên quan dài hạn",
    "Lãi dự thu", "Cổ tức phải thu",
    "Dự phòng giảm giá hàng tồn kho",
    "Hàng tồn kho khác",
    "Cổ phiếu ưu đãi", "Cổ phiếu quỹ",
    "Điều chỉnh vốn chủ sở hữu khác",
    "Chênh lệch tỷ giá quy đổi báo cáo",
    "Lãi/lỗ chưa thực hiện",
    "Quỹ đánh giá lại tài sản cố định",
    "Nợ lương hưu tối thiểu",
    "Vốn chủ sở hữu phổ thông",
    "Tổng vốn hóa sổ sách",
    "Giá trị sổ sách hữu hình",
    "Vốn đầu tư", "Tài sản hữu hình thuần",
    "Chứng khoán ưu đãi ngoài vốn cổ phần",
    "Cổ phiếu phổ thông bị hạn chế",
    "Lợi ích vốn chủ sở hữu khác",
    "Phải trả và chi phí phải trả",
    "Thuế TNDN phải trả",
    "Tổng tiền gửi khách hàng",
    "Tiền gửi và vay các tổ chức tín dụng khác",
    "Giao dịch mua bán lại trái phiếu và vay liên ngân hàng",
    "Nhà cửa và vật kiến trúc",
])

# ==============================================================================
# 2. ALIAS_TO_VAS — gộp nhãn trùng nghĩa
# ==============================================================================
ALIAS_TO_VAS = {
    "Total Assets": "Tổng cộng tài sản",
    "Current Assets": "Tài sản ngắn hạn",
    "Total Non Current Assets": "Tài sản dài hạn",
    "Cash And Cash Equivalents": "Tiền và các khoản tương đương tiền",
    "Cash": "Tiền và các khoản tương đương tiền",
    "Cash Financial": "Tiền và các khoản tương đương tiền",
    "Short Term Investments": "Đầu tư tài chính ngắn hạn",
    "Other Short Term Investments": "Đầu tư tài chính ngắn hạn",
    "Accounts Receivable": "Phải thu ngắn hạn của khách hàng",
    "Receivables": "Các khoản phải thu ngắn hạn",
    "Inventory": "Hàng tồn kho",
    "Net PPE": "Tài sản cố định hữu hình",
    "Gross PPE": "Nguyên giá",
    "Accumulated Depreciation": "Hao mòn lũy kế",
    "Investments And Advances": "Đầu tư tài chính dài hạn",
    "Other Non Current Assets": "Tài sản dài hạn khác",
    "Total Liabilities Net Minority Interest": "Nợ phải trả",
    "Current Liabilities": "Nợ ngắn hạn",
    "Accounts Payable": "Phải trả người bán ngắn hạn",
    "Long Term Debt": "Vay và nợ thuê tài chính dài hạn",
    "Total Equity Gross Minority Interest": "Vốn chủ sở hữu",
    "Stockholders Equity": "Vốn chủ sở hữu",
    "Retained Earnings": "Lợi nhuận sau thuế chưa phân phối",
    "Minority Interest": "Lợi ích cổ đông không kiểm soát",
    "Share Capital": "Vốn góp của chủ sở hữu",
    "Total Revenue": "Doanh thu bán hàng và cung cấp dịch vụ",
    "Operating Revenue": "Doanh thu thuần",
    "Cost Of Revenue": "Giá vốn hàng bán",
    "Cost of Goods Sold": "Giá vốn hàng bán",
    "Gross Profit": "Lợi nhuận gộp",
    "Operating Income": "Lợi nhuận thuần từ hoạt động kinh doanh",
    "Net Income": "Lợi nhuận sau thuế TNDN",
    "Net Income Common Stockholders": "LNST của công ty mẹ",
    "Pretax Income": "Tổng lợi nhuận kế toán trước thuế",
    "Tax Provision": "Chi phí thuế TNDN hiện hành",
    "Interest Expense": "Chi phí lãi vay",
    "Basic EPS": "Lãi cơ bản trên cổ phiếu",
    "Diluted EPS": "Lãi suy giảm trên cổ phiếu",
    "Operating Cash Flow": "Lưu chuyển tiền thuần từ HĐKD",
    "Cash Flow From Continuing Operating Activities": "Lưu chuyển tiền thuần từ HĐKD",
    "Investing Cash Flow": "Lưu chuyển tiền thuần từ HĐĐT",
    "Financing Cash Flow": "Lưu chuyển tiền thuần từ HĐTC",
    "Capital Expenditure": "Tiền chi mua sắm, xây dựng TSCĐ và tài sản dài hạn khác",
    "Depreciation And Amortization": "Khấu hao TSCĐ và BĐSĐT",
    "Depreciation Amortization Depletion": "Khấu hao TSCĐ và BĐSĐT",
    "Doanh thu thuần HĐKD": "Doanh thu thuần",
    "Lợi nhuận sau thuế thu nhập doanh nghiệp": "Lợi nhuận sau thuế TNDN",
    "LNST": "Lợi nhuận sau thuế TNDN",
    "Vốn CSH": "Vốn chủ sở hữu",
    "Nợ phải trả ngắn hạn": "Nợ ngắn hạn",
    "Nợ phải trả dài hạn": "Nợ dài hạn",
    "Lợi nhuận gộp về bán hàng và cung cấp dịch vụ": "Lợi nhuận gộp",
    "Net Interest Income": "Thu nhập lãi thuần",
    "Gross Loan": "Cho vay khách hàng",
    "Customer Deposits": "Tiền gửi của khách hàng",
    "Trading Securities": "Chứng khoán kinh doanh",
    "Held To Maturity Securities": "Chứng khoán đầu tư giữ đến ngày đáo hạn",
    # --- v19 gộp ---
    "Depreciation": "Khấu hao TSCĐ và BĐSĐT",
    "Reconciled Depreciation": "Khấu hao TSCĐ và BĐSĐT",
    "Reconciled Cost Of Revenue": "Giá vốn hàng bán",
    "Total Operating Income As Reported": "Lợi nhuận thuần từ hoạt động kinh doanh",
    "Operating Profit": "Lợi nhuận thuần từ hoạt động kinh doanh",
    "Net Income Including Noncontrolling Interests": "Lợi nhuận sau thuế TNDN",
    "Net Income From Continuing And Discontinued Operation": "Lợi nhuận sau thuế TNDN",
    "Net Income Continuous Operations": "Lợi nhuận sau thuế TNDN",
    "Net Income From Continuing Operation Net Minority Interest": "LNST của công ty mẹ",
    "Net Income From Continuing Operation": "Lợi nhuận sau thuế từ hoạt động tiếp tục",
    "Common Stock Equity": "Vốn chủ sở hữu",
    "Total Equity": "Vốn chủ sở hữu",
    "Capital Stock": "Vốn góp của chủ sở hữu",
    "Common Stock": "Vốn góp của chủ sở hữu",
    "Additional Paid In Capital": "Thặng dư vốn cổ phần",
    "Share Premium": "Thặng dư vốn cổ phần",
    "Treasury Stock": "Cổ phiếu quỹ",
    "Current Debt": "Vay và nợ thuê tài chính ngắn hạn",
    "Current Debt And Capital Lease Obligation": "Vay và nợ thuê tài chính ngắn hạn",
    "Long Term Debt And Capital Lease Obligation": "Vay và nợ thuê tài chính dài hạn",
    "Total Debt": "Tổng nợ vay",
    "Net Debt": "Nợ vay ròng",
    "Available For Sale Securities": "Chứng khoán đầu tư sẵn sàng để bán",
    "Total Deposits": "Tiền gửi của khách hàng",
    "Allowance For Loans And Lease Losses": "Dự phòng rủi ro tín dụng",
    "Provision For Loan Lease And Other Losses": "Chi phí dự phòng rủi ro tín dụng",
    "Purchase Of PPE": "Tiền chi mua sắm, xây dựng TSCĐ và tài sản dài hạn khác",
    "Sale Of PPE": "Tiền thu thanh lý, nhượng bán TSCĐ và tài sản dài hạn khác",
    "Repayment Of Debt": "Tiền trả nợ gốc vay",
    "Issuance Of Debt": "Tiền thu từ đi vay",
    "Long Term Debt Issuance": "Tiền thu từ đi vay dài hạn",
    "Long Term Debt Payments": "Tiền trả nợ gốc vay dài hạn",
    "Cash Dividends Paid": "Cổ tức, lợi nhuận đã trả cho chủ sở hữu",
    "Common Stock Dividend Paid": "Cổ tức, lợi nhuận đã trả cho chủ sở hữu",
    "Beginning Cash Position": "Tiền và tương đương tiền đầu kỳ",
    "End Cash Position": "Tiền và tương đương tiền cuối kỳ",
    "Changes In Cash": "Lưu chuyển tiền thuần trong kỳ",
    "Effect Of Exchange Rate Changes": "Ảnh hưởng của thay đổi tỷ giá quy đổi ngoại tệ",
    "Cash Flow From Continuing Investing Activities": "Lưu chuyển tiền thuần từ HĐĐT",
    "Cash Flow From Continuing Financing Activities": "Lưu chuyển tiền thuần từ HĐTC",
    "Change In Receivables": "Tăng/giảm các khoản phải thu",
    "Change In Inventory": "Tăng/giảm hàng tồn kho",
    "Change In Payables": "Tăng/giảm các khoản phải trả",
    "Change In Payable": "Tăng/giảm các khoản phải trả",
    "Change In Account Payable": "Tăng/giảm các khoản phải trả",
    "Change In Prepaid Assets": "Tăng/giảm chi phí trả trước",
    "Taxes Refund Paid": "Thuế được hoàn lại",
    "Interest Paid Cfo": "Tiền lãi vay đã trả",
    "Interest Received Cfi": "Tiền lãi nhận được (HĐĐT)",
    "Interest Received Cfo": "Tiền lãi nhận được (HĐKD)",
    "Gain Loss On Investment Securities": "Lãi/lỗ từ chứng khoán đầu tư",
    "Net Foreign Currency Exchange Gain": "Lãi / Lỗ chênh lệch tỷ giá hối đoái thuần",
    "Net Issuance Payments Of Debt": "Tiền vay/trả nợ gốc thuần",
    "Net Long Term Debt Issuance": "Tiền thu từ đi vay dài hạn (thuần)",
    # --- VN aliases ---
    "tổng tài sản": "Tổng cộng tài sản",
    "tổng cộng tài sản": "Tổng cộng tài sản",
    "tổng nợ phải trả": "Nợ phải trả",
    "nợ phải trả và vốn chủ sở hữu": "Tổng cộng nguồn vốn",
    "tổng cộng nợ phải trả và vốn chủ sở hữu": "Tổng cộng nguồn vốn",
    "tổng vốn chủ sở hữu": "Vốn chủ sở hữu",
    "tổng vốn chủ sở hữu gồm cổ đông không kiểm soát": "Vốn chủ sở hữu",
    "vốn góp chủ sở hữu": "Vốn góp của chủ sở hữu",
    "phải thu ngắn hạn khách hàng": "Phải thu ngắn hạn của khách hàng",
    "thuế và các khoản phải nộp nhà nước": "Thuế và các khoản phải nộp Nhà nước",
    "lợi nhuận sau thuế (lợi nhuận ròng)": "Lợi nhuận sau thuế TNDN",
    "lãi cơ bản trên cổ phiếu (basic eps)": "Lãi cơ bản trên cổ phiếu",
    "lãi suy giảm trên cổ phiếu (diluted eps)": "Lãi suy giảm trên cổ phiếu",
    "lưu chuyển tiền thuần từ hoạt động kinh doanh": "Lưu chuyển tiền thuần từ HĐKD",
    "lưu chuyển tiền thuần từ hoạt động kinh doanh tiếp tục": "Lưu chuyển tiền thuần từ HĐKD",
    "lưu chuyển tiền thuần từ hoạt động đầu tư": "Lưu chuyển tiền thuần từ HĐĐT",
    "lưu chuyển tiền thuần từ hoạt động đầu tư tiếp tục": "Lưu chuyển tiền thuần từ HĐĐT",
    "lưu chuyển tiền thuần từ hoạt động tài chính": "Lưu chuyển tiền thuần từ HĐTC",
    "lưu chuyển tiền thuần từ hoạt động tài chính tiếp tục": "Lưu chuyển tiền thuần từ HĐTC",
    "các khoản nợ chính phủ và nhnn việt nam": "Nợ Chính phủ và Ngân hàng Nhà nước",
    "các khoản nợ chính phủ và nhnn": "Nợ Chính phủ và Ngân hàng Nhà nước",
    "nợ chính phủ và nhnn việt nam": "Nợ Chính phủ và Ngân hàng Nhà nước",
    "chi phí quản lý ctck": "Chi phí quản lý CTCK",
    "lãi thuần từ dịch vụ": "Lãi thuần từ hoạt động dịch vụ",
    "thu nhập từ dịch vụ": "Thu nhập từ hoạt động dịch vụ",
    "lãi thuần từ ngoại hối và vàng": "Lãi thuần từ hoạt động kinh doanh ngoại hối",
    "lãi thuần từ chứng khoán kinh doanh": "Lãi thuần từ mua bán chứng khoán kinh doanh",
    "lãi thuần từ chứng khoán đầu tư": "Lãi thuần từ mua bán chứng khoán đầu tư",
    "chi phí hoạt động (cir)": "Chi phí hoạt động",
}

# ==============================================================================
# 3. JUNK BLACKLIST
# ==============================================================================
JUNK_WORDS = {
    'của', 'và', 'hoặc', 'từ', 'cho', 'các', 'tại', 'trong', 'trên', 'dưới', 'là', 'với',
    'theo', 'không', 'có', 'được', 'bị', 'sự', 'cái', 'này', 'kia', 'đó', 'một', 'những',
    'ở', 'về', 'để', 'khi', 'nếu', 'thì', 'mà', 'hay', 'nhưng', 'rất', 'đã', 'sẽ', 'đang',
    'vẫn', 'cũng', 'chỉ', 'tiêu', 'chưa', 'xác', 'định', 'khác', 'tổng', 'ròng',
    'net', 'of', 'the', 'and', 'or', 'total', 'other', 'unknown', 'undefined',
}
JUNK_EXACT = {
    'của', 'và', 'hoặc', 'từ', 'cho', 'các', 'khác', 'tổng', 'ròng', 'net', 'total', 'other',
    'chỉ tiêu chưa xác định', 'nan', 'none', 'null', 'n/a', '-', '', 'undefined', 'unknown',
}

def is_junk_label(s):
    if s is None:
        return True
    t = clean_text(s).lower()
    if len(t) < 2:
        return True
    if t in JUNK_EXACT:
        return True
    if not re.search(r'[a-zà-ỹđ]', t):
        return True
    toks = re.findall(r'[a-zà-ỹđ]+', t)
    if toks and all(w in JUNK_WORDS for w in toks):
        return True
    return False

# ==============================================================================
# 4. TRANSLATION_MAP — siêu từ điển (~500 key)
# ==============================================================================
TRANSLATION_MAP = {
    # ===== Viết tắt & typo =====
    'N s': 'Số lượng cổ phiếu ròng',
    'M': 'Lợi ích cổ đông không kiểm soát',
    'Tổng khác f giá gốc': 'Tổng chi phí khác theo giá gốc',
    'N on ngắn hạn deferred taxes liabilities': 'Thuế thu nhập hoãn lại phải trả ngắn hạn',
    'Pensi onand khác post retirement benefit plans ngắn hạn': 'Quỹ phúc lợi nhân viên ngắn hạn',
    'Khác payable': 'Phải trả khác',
    'Dividends payable': 'Cổ tức phải trả',
    'Tổng thuê payable': 'Tổng thuế phải trả',
    'Investmentsin joint venturesat cost': 'Đầu tư vào liên doanh theo giá gốc',
    'Investmentsin associatesat cost': 'Đầu tư vào công ty liên kết theo giá gốc',
    'Khác properties': 'Bất động sản khác',
    'Buildings and improvements': 'Nhà cửa và vật kiến trúc',
    'Tiền mặt tiền mặt equivalents and short term investments': 'Tiền mặt, tương đương tiền và đầu tư ngắn hạn',
    'Taxes receivable': 'Thuế phải thu',
    'Investments in joint ventures at cost': 'Đầu tư vào liên doanh theo giá gốc',
    'Investments in associates at cost': 'Đầu tư vào công ty liên kết theo giá gốc',
    'Non ngắn hạn deferred taxes liabilities': 'Thuế thu nhập hoãn lại phải trả ngắn hạn',
    'Non current deferred taxes liabilities': 'Thuế thu nhập hoãn lại phải trả dài hạn',
    'Current deferred taxes liabilities': 'Thuế thu nhập hoãn lại phải trả ngắn hạn',
    'Other payable': 'Phải trả khác',
    'Other payables': 'Phải trả khác',
    'Other properties': 'Bất động sản khác',
    'Total tax payable': 'Tổng thuế phải trả',
    'Total lease payable': 'Tổng tiền thuê phải trả',
    'Pension and other post retirement benefit plans current': 'Quỹ phúc lợi nhân viên ngắn hạn',
    'Pension and other post-retirement benefit plans current': 'Quỹ phúc lợi nhân viên ngắn hạn',
    'Pension and other post retirement benefit plans': 'Quỹ phúc lợi nhân viên và hưu trí',
    'Pension and other post-retirement benefit plans': 'Quỹ phúc lợi nhân viên và hưu trí',
    'Cash cash equivalents and short term investments': 'Tiền mặt, tương đương tiền và đầu tư ngắn hạn',
    'Current tax payable': 'Thuế phải trả ngắn hạn',
    'Current tax receivables': 'Thuế phải thu ngắn hạn',
    'Investments in joint ventures': 'Đầu tư vào liên doanh',
    'Investments in associates': 'Đầu tư vào công ty liên kết',
    'Tax payable': 'Thuế phải trả',
    'Deferred taxes liabilities': 'Thuế thu nhập hoãn lại phải trả',
    'Other current payables': 'Phải trả ngắn hạn khác',
    'Other non current payables': 'Phải trả dài hạn khác',
    'Other current receivables': 'Phải thu ngắn hạn khác',
    'Other non current receivables': 'Phải thu dài hạn khác',
    'Net property plant and equipment': 'Tài sản cố định hữu hình thuần',
    'Gross property plant and equipment': 'Nguyên giá tài sản cố định hữu hình',
    'Property plant and equipment': 'Tài sản cố định hữu hình',
    'Accumulated depreciation': 'Hao mòn lũy kế tài sản cố định',
    'Other intangible assets': 'Tài sản cố định vô hình khác',
    'Goodwill and other intangible assets': 'Lợi thế thương mại và tài sản vô hình',
    'Short term investments': 'Đầu tư ngắn hạn',
    'Long term investments': 'Đầu tư dài hạn',
    'Accounts receivable': 'Phải thu khách hàng',
    'Accounts payable': 'Phải trả người bán',
    'Retained earnings': 'Lợi nhuận sau thuế chưa phân phối',
    'Share premium': 'Thặng dư vốn cổ phần',
    'Share capital': 'Vốn góp chủ sở hữu',
    'Total equity': 'Tổng vốn chủ sở hữu',
    'Minority interest': 'Lợi ích cổ đông không kiểm soát',
    # ===== Từ ảnh 1+2 v18 =====
    'Total Expenses': 'Tổng chi phí',
    'Classesof Cash Payments': 'Các khoản thanh toán tiền mặt',
    'Other Cash Paymentsfrom Operating Activities': 'Các khoản thanh toán tiền mặt khác từ HĐKD',
    'Paymentson Behalfof Employees': 'Thanh toán cho người lao động',
    'Classesof Cash Receiptsfrom Operating Activities': 'Các khoản thu tiền mặt từ HĐKD',
    'Other Cash Receiptsfrom Operating Activities': 'Các khoản thu tiền mặt khác từ HĐKD',
    'Dividends Received Cf': 'Cổ tức đã nhận',
    'Sale Of PPE': 'Thu từ thanh lý tài sản cố định',
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
    'Other Income Expense': 'Thu nhập/chi phí khác',
    'Total Operating Income As Reported': 'Tổng lợi nhuận HĐKD như báo cáo',
    'Reconciled Depreciation': 'Khấu hao được điều chỉnh',
    'Net Income Extraordinary': 'Lợi nhuận ròng bất thường',
    'Net Income Discontinuous Operations': 'Lợi nhuận ròng từ hoạt động không liên tục',
    'Net Income Continuous Operations': 'Lợi nhuận ròng từ hoạt động liên tục',
    'Minority Interests': 'Lợi ích cổ đông không kiểm soát',
    'Special Income Charges': 'Chi phí thu nhập đặc biệt',
    'Other Special Charges': 'Chi phí đặc biệt khác',
    'Write Off': 'Xóa sổ',
    'Balance_Sheet': 'Bảng cân đối kế toán',
    'Income_Statement': 'Báo cáo kết quả kinh doanh',
    'Cash_Flow': 'Báo cáo lưu chuyển tiền tệ',
    'Market_Metrics': 'Chỉ số thị trường, Định giá & Cổ tức',
    'Ordinary Shares Number': 'Số lượng cổ phiếu phổ thông',
    'Share Issued': 'Cổ phiếu đã phát hành',
    'Total Assets': 'Tổng tài sản',
    'Current Assets': 'Tài sản ngắn hạn',
    'Cash And Cash Equivalents': 'Tiền và các khoản tương đương tiền',
    'Cash Financial': 'Tiền và đầu tư tài chính ngắn hạn',
    'Cash Equivalents': 'Các khoản tương đương tiền',
    'Cash': 'Tiền mặt',
    'Other Short Term Investments': 'Đầu tư tài chính ngắn hạn khác',
    'Receivables': 'Các khoản phải thu',
    'Accounts Receivable': 'Phải thu ngắn hạn khách hàng',
    'Allowance For Doubtful Accounts Receivable': 'Dự phòng phải thu ngắn hạn khó đòi',
    'Due From Related Parties Current': 'Phải thu các bên liên quan ngắn hạn',
    'Other Receivables': 'Các khoản phải thu ngắn hạn khác',
    'Inventory': 'Hàng tồn kho',
    'Raw Materials': 'Nguyên liệu, vật liệu tồn kho',
    'Work In Process': 'Chi phí sản xuất kinh doanh dở dang',
    'Finished Goods': 'Thành phẩm tồn kho',
    'Prepaid Assets': 'Chi phí trả trước ngắn hạn',
    'Restricted Cash': 'Tiền bị hạn chế',
    'Total Non Current Assets': 'Tổng tài sản dài hạn',
    'Net PPE': 'Tài sản cố định thuần',
    'Gross PPE': 'Nguyên giá tài sản cố định',
    'Accumulated Depreciation': 'Hao mòn lũy kế tài sản cố định',
    'Machinery Furniture Equipment': 'Máy móc, thiết bị và phương tiện vận tải',
    'Land And Improvements': 'Đất đai và cải tạo đất',
    'Properties': 'Bất động sản',
    'Leases': 'Tài sản quyền sử dụng đất và thuê tài chính',
    'Construction In Progress': 'Xây dựng cơ bản dở dang',
    'Goodwill And Other Intangible Assets': 'Lợi thế thương mại và tài sản vô hình',
    'Goodwill': 'Lợi thế thương mại',
    'Other Intangible Assets': 'Tài sản cố định vô hình khác',
    'Investments And Advances': 'Đầu tư tài chính dài hạn',
    'Investment in Financial Assets': 'Đầu tư tài chính dài hạn',
    'Held To Maturity Securities': 'Chứng khoán giữ đến ngày đáo hạn',
    'Available For Sale Securities': 'Chứng khoán sẵn sàng để bán',
    'Investment Properties': 'Bất động sản đầu tư',
    'Other Non Current Assets': 'Tài sản dài hạn khác',
    'Deferred Tax Assets': 'Tài sản thuế thu nhập hoãn lại',
    'Current Liabilities': 'Nợ ngắn hạn',
    'Current Debt': 'Vay và nợ thuê tài chính ngắn hạn',
    'Payables': 'Các khoản phải trả',
    'Accounts Payable': 'Phải trả người bán ngắn hạn',
    'Taxes Payable': 'Thuế và các khoản phải nộp nhà nước',
    'Accrued Liabilities': 'Chi phí phải trả ngắn hạn',
    'Pension and Other Post-Retirement Benefit Plans Current': 'Quỹ phúc lợi nhân viên ngắn hạn',
    'Other Current Liabilities': 'Phải trả, phải nộp ngắn hạn khác',
    'Total Liabilities Net Minority Interest': 'Tổng nợ phải trả',
    'Total Non Current Liabilities Net Minority Interest': 'Nợ dài hạn',
    'Long Term Debt': 'Vay và nợ thuê tài chính dài hạn',
    'Total Debt': 'Tổng nợ vay',
    'Net Debt': 'Nợ vay ròng',
    'Deferred Revenue': 'Doanh thu chưa thực hiện dài hạn',
    'Deferred Tax Liabilities': 'Thuế thu nhập hoãn lại phải trả',
    'Other Non Current Liabilities': 'Nợ dài hạn khác',
    'Stockholders Equity': 'Vốn chủ sở hữu',
    'Capital Stock': 'Vốn góp chủ sở hữu',
    'Common Stock': 'Cổ phiếu phổ thông',
    'Retained Earnings': 'Lợi nhuận sau thuế chưa phân phối',
    'Additional Paid In Capital': 'Thặng dư vốn cổ phần',
    'Gains Losses Not Affecting Retained Earnings': 'Chênh lệch đánh giá lại tài sản và chênh lệch tỷ giá',
    'Minority Interest': 'Lợi ích cổ đông không kiểm soát',
    'Total Equity Gross Minority Interest': 'Tổng vốn chủ sở hữu gồm cổ đông không kiểm soát',
    'Working Capital': 'Vốn lưu động ròng',
    'Total Revenue': 'Tổng doanh thu',
    'Operating Revenue': 'Doanh thu thuần',
    'Cost Of Revenue': 'Giá vốn hàng bán',
    'Gross Profit': 'Lợi nhuận gộp',
    'Operating Expense': 'Chi phí hoạt động',
    'Selling General And Administration': 'Chi phí bán hàng và quản lý doanh nghiệp',
    'Selling And Marketing Expense': 'Chi phí bán hàng',
    'General And Administrative Expense': 'Chi phí quản lý doanh nghiệp',
    'Research And Development': 'Chi phí nghiên cứu và phát triển',
    'Other Operating Expenses': 'Chi phí hoạt động khác',
    'Operating Income': 'Lợi nhuận thuần từ hoạt động kinh doanh',
    'Net Interest Income': 'Thu nhập lãi thuần',
    'Interest Expense': 'Chi phí lãi vay',
    'Interest Income': 'Thu nhập lãi',
    'EBIT': 'Lợi nhuận trước lãi vay và thuế (EBIT)',
    'EBITDA': 'Lợi nhuận trước lãi vay, thuế và khấu hao (EBITDA)',
    'Normalized EBITDA': 'Lợi nhuận trước lãi vay, thuế, khấu hao chuẩn hóa',
    'Normalized Income': 'Lợi nhuận thuần chuẩn hóa',
    'Pretax Income': 'Lợi nhuận kế toán trước thuế',
    'Tax Provision': 'Chi phí thuế thu nhập doanh nghiệp',
    'Net Income': 'Lợi nhuận sau thuế (Lợi nhuận ròng)',
    'Net Income Including Noncontrolling Interests': 'Lợi nhuận sau thuế bao gồm lợi ích cổ đông không kiểm soát',
    'Net Income From Continuing Operation': 'Lợi nhuận sau thuế từ hoạt động tiếp tục',
    'Net Income From Continuing And Discontinued Operation': 'Lợi nhuận thuần từ hoạt động tiếp tục và không tiếp tục',
    'Tax Effect Of Unusual Items': 'Ảnh hưởng thuế từ các khoản mục bất thường',
    'Tax Rate For Calcs': 'Thuế suất dùng để tính toán',
    'Gain On Sale Of Security': 'Lãi / Lỗ từ bán chứng khoán',
    'Other Under Preferred Stock Dividend': 'Cổ tức cổ phiếu ưu đãi và điều chỉnh khác',
    'Basic EPS': 'Lãi cơ bản trên cổ phiếu (Basic EPS)',
    'Diluted EPS': 'Lãi suy giảm trên cổ phiếu (Diluted EPS)',
    'Diluted Average Shares': 'Số lượng cổ phiếu bình quân pha loãng',
    'Basic Average Shares': 'Số lượng cổ phiếu bình quân cơ bản',
    'Operating Cash Flow': 'Lưu chuyển tiền thuần từ hoạt động kinh doanh',
    'Cash Flow From Continuing Operating Activities': 'Lưu chuyển tiền thuần từ hoạt động kinh doanh tiếp tục',
    'Depreciation Amortization Depletion': 'Khấu hao tài sản cố định và phân bổ',
    'Depreciation And Amortization': 'Khấu hao và phân bổ',
    'Asset Impairment Charge': 'Tổn thất tài sản và dự phòng',
    'Deferred Income Tax': 'Thuế thu nhập hoãn lại',
    'Change In Working Capital': 'Biến động vốn lưu động',
    'Change In Receivables': 'Biến động các khoản phải thu',
    'Change In Inventory': 'Biến động hàng tồn kho',
    'Change In Payables': 'Biến động các khoản phải trả',
    'Change In Account Payable': 'Biến động phải trả người bán',
    'Change In Other Working Capital': 'Biến động vốn lưu động khác',
    'Investing Cash Flow': 'Lưu chuyển tiền thuần từ hoạt động đầu tư',
    'Cash Flow From Continuing Investing Activities': 'Lưu chuyển tiền thuần từ hoạt động đầu tư tiếp tục',
    'Capital Expenditure': 'Chi phí đầu tư tài sản cố định (CapEx)',
    'Net PPE Purchase And Sale': 'Tiền mua hoặc thanh lý tài sản cố định',
    'Net Intangibles Purchase And Sale': 'Tiền mua hoặc bán tài sản vô hình',
    'Net Investment Purchase And Sale': 'Tiền đầu tư góp vốn thuần',
    'Net Business Purchase And Sale': 'Tiền mua bán công ty con hoặc sáp nhập',
    'Free Cash Flow': 'Dòng tiền tự do (FCF)',
    'Financing Cash Flow': 'Lưu chuyển tiền thuần từ hoạt động tài chính',
    'Cash Flow From Continuing Financing Activities': 'Lưu chuyển tiền thuần từ hoạt động tài chính tiếp tục',
    'Issuance Of Debt': 'Tiền thu từ phát hành nợ vay',
    'Repayment Of Debt': 'Tiền chi trả nợ gốc vay',
    'Net Common Stock Issuance': 'Tiền thu từ phát hành cổ phiếu hoặc bán cổ phiếu quỹ',
    'Cash Dividends Paid': 'Cổ tức đã chi trả cho chủ sở hữu',
    'Beginning Cash Position': 'Tiền và tương đương tiền đầu kỳ',
    'End Cash Position': 'Tiền và tương đương tiền cuối kỳ',
    'Changes In Cash': 'Ảnh hưởng thay đổi tỷ giá và tiền thuần thay đổi',
    'Current Price': 'Giá cổ phiếu hiện tại',
    'Shares Outstanding': 'Tổng số lượng cổ phiếu lưu hành',
    'Market Capitalization': 'Vốn hóa thị trường',
    'Trailing EPS': 'EPS cơ bản 4 quý gần nhất (Trailing EPS)',
    'Forward EPS': 'EPS dự phòng (Forward EPS)',
    'Dividend Yield': 'Tỷ suất cổ tức (% Dividend Yield)',
    'Dividend Rate': 'Cổ tức tiền mặt trên mỗi cổ phiếu',
    'Trailing P/E': 'Hệ số P/E cơ bản (Trailing P/E)',
    'Forward P/E': 'Hệ số P/E dự phóng (Forward P/E)',
    'Price To Book': 'Hệ số P/B (Price to Book)',
    'Book Value': 'Giá trị sổ sách mỗi cổ phiếu (BVPS)',
    'Return On Equity': 'Lợi nhuận trên vốn chủ sở hữu (ROE)',
    'Return On Assets': 'Lợi nhuận trên tổng tài sản (ROA)',
    'Profit Margins': 'Biên lợi nhuận ròng (%)',
    'Gross Margins': 'Biên lợi nhuận gộp (%)',
    'Historical Dividend Cash': 'Lịch sử trả cổ tức bằng tiền (VND/Cổ phiếu)',
    # ===== v19 bổ sung (từ ảnh lỗi) =====
    'Depreciation': 'Khấu hao TSCĐ và BĐSĐT',
    'Reconciled Cost Of Revenue': 'Giá vốn hàng bán (điều chỉnh)',
    'Securities Amortization': 'Phân bổ chứng khoán',
    'Amortization Of Securities': 'Phân bổ chứng khoán',
    'Amortization Of Intangibles': 'Phân bổ tài sản vô hình',
    'Gain Loss On Investment Securities': 'Lãi/lỗ từ chứng khoán đầu tư',
    'Gain On Investment Securities': 'Lãi từ chứng khoán đầu tư',
    'Loss On Investment Securities': 'Lỗ từ chứng khoán đầu tư',
    'Unrealized Gain Loss On Investment Securities': 'Lãi/lỗ chưa thực hiện từ chứng khoán đầu tư',
    'Realized Gain Loss On Investment Securities': 'Lãi/lỗ đã thực hiện từ chứng khoán đầu tư',
    'Net Foreign Currency Exchange Gain': 'Lãi / Lỗ chênh lệch tỷ giá hối đoái thuần',
    'Foreign Currency Exchange Gains Losses': 'Lãi/lỗ chênh lệch tỷ giá hối đoái',
    'Gain On Sale Of PPE': 'Lãi từ thanh lý tài sản cố định',
    'Gain On Sale Of Business': 'Lãi từ bán công ty con',
    'Earnings Losses From Equity Investments': 'Lãi/lỗ từ đầu tư góp vốn',
    'Earnings From Equity Interest': 'Lãi từ công ty liên kết',
    'Earnings From Equity Interest Net Of Tax': 'Lãi từ công ty liên kết (sau thuế)',
    'Total Unusual Items': 'Tổng các khoản mục bất thường',
    'Impairment Of Capital Assets': 'Tổn thất tài sản cố định',
    'Restructuring And Mergern Acquisition': 'Chi phí tái cấu trúc và sáp nhập',
    'Restructuring And Mergers Acquisition': 'Chi phí tái cấu trúc và sáp nhập',
    'Stock Based Compensation': 'Chi phí cổ phiếu thưởng cho nhân viên',
    'Share Based Compensation': 'Chi phí cổ phiếu thưởng cho nhân viên',
    'Excess Tax Benefit From Stock Based Compensation': 'Ưu đãi thuế vượt trội từ cổ phiếu thưởng',
    'Provisionand Write Offof Assets': 'Dự phòng và xóa sổ tài sản',
    'Provision For Doubtful Accounts': 'Dự phòng phải thu khó đòi',
    'Net Issuance Payments Of Debt': 'Tiền vay/trả nợ gốc thuần',
    'Net Long Term Debt Issuance': 'Tiền thu từ đi vay dài hạn (thuần)',
    'Long Term Debt Issuance': 'Tiền thu từ đi vay dài hạn',
    'Long Term Debt Payments': 'Tiền trả nợ gốc vay dài hạn',
    'Net Short Term Debt Issuance': 'Tiền thu từ đi vay ngắn hạn (thuần)',
    'Short Term Debt Issuance': 'Tiền thu từ đi vay ngắn hạn',
    'Short Term Debt Payments': 'Tiền trả nợ gốc vay ngắn hạn',
    'Interest Received Cfi': 'Tiền lãi nhận được (HĐĐT)',
    'Interest Received Cfo': 'Tiền lãi nhận được (HĐKD)',
    'Interest Paid Cfo': 'Tiền lãi vay đã trả',
    'Interest Paid Cff': 'Tiền lãi vay đã trả (HĐTC)',
    'Interest Paid Supplemental Data': 'Tiền lãi vay đã trả (bổ sung)',
    'Income Tax Paid Supplemental Data': 'Thuế TNDN đã nộp (bổ sung)',
    'Taxes Refund Paid': 'Thuế được hoàn lại',
    'Tax Paid': 'Thuế đã nộp',
    'Dividends Paid Cfo': 'Cổ tức đã trả (HĐKD)',
    'Dividends Received Cfo': 'Cổ tức đã nhận (HĐKD)',
    'Dividend Received Cfi': 'Cổ tức đã nhận (HĐĐT)',
    'Dividends Paid': 'Cổ tức đã trả',
    'Dividends Received': 'Cổ tức đã nhận',
    'Common Stock Dividend Paid': 'Cổ tức đã trả cho cổ đông phổ thông',
    'Preferred Stock Dividend Paid': 'Cổ tức đã trả cho cổ đông ưu đãi',
    'Change In Payable': 'Biến động các khoản phải trả',
    'Change In Payables And Accrued Expense': 'Biến động phải trả và chi phí phải trả',
    'Change In Accrued Expense': 'Biến động chi phí phải trả',
    'Change In Prepaid Assets': 'Biến động chi phí trả trước',
    'Change In Other Current Assets': 'Biến động tài sản ngắn hạn khác',
    'Change In Other Current Liabilities': 'Biến động nợ ngắn hạn khác',
    'Change In Tax Payable': 'Biến động thuế phải trả',
    'Change In Dividend Payable': 'Biến động cổ tức phải trả',
    'Other Non Cash Items': 'Các khoản mục phi tiền mặt khác',
    'Other Cash Adjustment Inside Changein Cash': 'Điều chỉnh tiền khác trong biến động tiền',
    'Other Cash Adjustment Outside Changein Cash': 'Điều chỉnh tiền khác ngoài biến động tiền',
    'Effect Of Exchange Rate Changes': 'Ảnh hưởng của thay đổi tỷ giá quy đổi ngoại tệ',
    'Purchase Of Investment': 'Tiền chi đầu tư góp vốn',
    'Sale Of Investment': 'Tiền thu hồi đầu tư góp vốn',
    'Purchase Of Business': 'Tiền mua công ty con',
    'Sale Of Business': 'Tiền bán công ty con',
    'Common Stock Issuance': 'Tiền thu từ phát hành cổ phiếu',
    'Common Stock Repurchase': 'Tiền mua lại cổ phiếu quỹ',
    'Repurchase Of Capital Stock': 'Tiền mua lại cổ phiếu quỹ',
    'Issuance Of Capital Stock': 'Tiền thu từ phát hành cổ phiếu',
    'Net Other Financing Charges': 'Chi phí tài chính khác thuần',
    'Net Other Investing Changes': 'Biến động đầu tư khác thuần',
    'Total Expenses': 'Tổng chi phí',
    'Rent And Landing Fees': 'Chi phí thuê mặt bằng',
    'Insurance And Claims': 'Chi phí bảo hiểm và bồi thường',
    'Salaries And Wages': 'Chi phí lương và nhân công',
    'Other Gand A': 'Chi phí quản lý doanh nghiệp khác',
    'Other G And A': 'Chi phí quản lý doanh nghiệp khác',
    'Interest Income Non Operating': 'Thu nhập lãi ngoài hoạt động',
    'Interest Expense Non Operating': 'Chi phí lãi ngoài hoạt động',
    'Net Non Operating Interest Income Expense': 'Thu nhập/chi phí lãi thuần ngoài HĐKD',
    'Total Other Income Expense Net': 'Tổng thu nhập/chi phí khác thuần',
    'Provision For Loan Lease And Other Losses': 'Chi phí dự phòng rủi ro tín dụng',
    'Net Fee And Commission Income': 'Lãi thuần từ hoạt động dịch vụ',
    'Net Commission Income': 'Lãi thuần từ hoạt động dịch vụ',
    'Fees And Commissions': 'Thu nhập phí và hoa hồng',
    'Net Investment Income': 'Lãi thuần từ đầu tư',
    'Trading Gain Loss': 'Lãi/lỗ từ hoạt động tự doanh',
    'Net Realized Gain Loss On Investments': 'Lãi/lỗ đã thực hiện từ đầu tư',
    'Treasury Shares Number': 'Số lượng cổ phiếu quỹ',
    'Capital Lease Obligations': 'Nợ thuê tài chính',
    'Current Capital Lease Obligation': 'Nợ thuê tài chính ngắn hạn',
    'Long Term Capital Lease Obligation': 'Nợ thuê tài chính dài hạn',
    'Current Debt And Capital Lease Obligation': 'Vay và nợ thuê tài chính ngắn hạn',
    'Long Term Debt And Capital Lease Obligation': 'Vay và nợ thuê tài chính dài hạn',
    'Current Provisions': 'Dự phòng phải trả ngắn hạn',
    'Non Current Provisions': 'Dự phòng phải trả dài hạn',
    'Long Term Provisions': 'Dự phòng phải trả dài hạn',
    'Employee Benefits': 'Phải trả người lao động',
    'Current Employee Benefits': 'Phải trả người lao động ngắn hạn',
    'Non Current Employee Benefits': 'Phải trả người lao động dài hạn',
    'Long Term Employee Benefit Liabilities': 'Phải trả phúc lợi nhân viên dài hạn',
    'Non Current Pension And Other Postretirement Benefit Plans': 'Quỹ phúc lợi nhân viên và hưu trí dài hạn',
    'Tradeand Other Payables Non Current': 'Phải trả thương mại và khác dài hạn',
    'Trade And Other Payables Non Current': 'Phải trả thương mại và khác dài hạn',
    'Non Current Deferred Taxes Liabilities': 'Thuế thu nhập hoãn lại phải trả dài hạn',
    'Non Current Deferred Taxes Assets': 'Tài sản thuế thu nhập hoãn lại dài hạn',
    'Non Current Deferred Revenue': 'Doanh thu chưa thực hiện dài hạn',
    'Non Current Deferred Liabilities': 'Nợ hoãn lại dài hạn',
    'Non Current Accrued Expenses': 'Chi phí phải trả dài hạn',
    'Non Current Note Receivables': 'Phải thu theo giấy nợ dài hạn',
    'Non Current Accounts Receivable': 'Phải thu khách hàng dài hạn',
    'Non Current Prepaid Assets': 'Chi phí trả trước dài hạn',
    'Current Deferred Taxes Assets': 'Tài sản thuế thu nhập hoãn lại ngắn hạn',
    'Current Deferred Taxes Liabilities': 'Thuế thu nhập hoãn lại phải trả ngắn hạn',
    'Current Deferred Revenue': 'Doanh thu chưa thực hiện ngắn hạn',
    'Current Deferred Liabilities': 'Nợ hoãn lại ngắn hạn',
    'Current Accrued Expenses': 'Chi phí phải trả ngắn hạn',
    'Current Notes Receivable': 'Phải thu theo giấy nợ ngắn hạn',
    'Current Prepaid Assets': 'Chi phí trả trước ngắn hạn',
    'Line Of Credit': 'Hạn mức tín dụng',
    'Commercial Paper': 'Thương phiếu',
    'Other Current Borrowings': 'Vay ngắn hạn khác',
    'Other Non Current Borrowings': 'Vay dài hạn khác',
    'Derivative Product Liabilities': 'Nợ công cụ phái sinh',
    'Derivative Assets': 'Tài sản phái sinh',
    'Hedging Assets Current': 'Tài sản phòng ngừa rủi ro ngắn hạn',
    'Hedging Assets Non Current': 'Tài sản phòng ngừa rủi ro dài hạn',
    'Assets Held For Sale Current': 'Tài sản nắm giữ để bán ngắn hạn',
    'Liabilities Held For Sale Current': 'Nợ gắn với tài sản nắm giữ để bán',
    'Assets Held For Sale': 'Tài sản nắm giữ để bán',
    'Liabilities Held For Sale': 'Nợ gắn với tài sản nắm giữ để bán',
    'Restricted Investments': 'Đầu tư bị hạn chế',
    'Cash Cash Equivalents And Short Term Investments': 'Tiền, tương đương tiền và đầu tư ngắn hạn',
    'Total Money Market Investments': 'Tổng đầu tư thị trường tiền tệ',
    'Money Market Investments': 'Đầu tư thị trường tiền tệ',
    'Financial Assets': 'Tài sản tài chính',
    'Financial Assets Designatedas Fair Value Through Profitor Loss Total': 'Tài sản tài chính ghi nhận qua lãi lỗ (FVTPL)',
    'Loans Receivable': 'Các khoản cho vay phải thu',
    'Gross Loan': 'Cho vay khách hàng (gộp)',
    'Net Loan': 'Cho vay khách hàng thuần',
    'Allowance For Loans And Lease Losses': 'Dự phòng rủi ro tín dụng',
    'Securities And Investments': 'Chứng khoán và đầu tư',
    'Long Term Equity Investment': 'Đầu tư góp vốn dài hạn',
    'Investmentsin Subsidiariesat Cost': 'Đầu tư vào công ty con theo giá gốc',
    'Investments In Subsidiaries': 'Đầu tư vào công ty con',
    'Investments In Associates': 'Đầu tư vào công ty liên kết',
    'Investments In Joint Ventures': 'Đầu tư vào liên doanh',
    'Other Investments': 'Đầu tư khác',
    'Gross Accounts Receivable': 'Phải thu khách hàng (gộp)',
    'Due From Related Parties Non Current': 'Phải thu các bên liên quan dài hạn',
    'Accrued Interest Receivable': 'Lãi dự thu',
    'Dividends Receivable': 'Cổ tức phải thu',
    'Inventories Adjustments Allowances': 'Dự phòng giảm giá hàng tồn kho',
    'Other Inventories': 'Hàng tồn kho khác',
    'Preferred Stock': 'Cổ phiếu ưu đãi',
    'Treasury Stock': 'Cổ phiếu quỹ',
    'Other Equity Adjustments': 'Điều chỉnh vốn chủ sở hữu khác',
    'Foreign Currency Translation Adjustments': 'Chênh lệch tỷ giá quy đổi báo cáo',
    'Unrealized Gain Loss': 'Lãi/lỗ chưa thực hiện',
    'Fixed Assets Revaluation Reserve': 'Quỹ đánh giá lại tài sản cố định',
    'Minimum Pension Liabilities': 'Nợ lương hưu tối thiểu',
    'Common Stock Equity': 'Vốn chủ sở hữu phổ thông',
    'Total Capitalization': 'Tổng vốn hóa sổ sách',
    'Tangible Book Value': 'Giá trị sổ sách hữu hình',
    'Invested Capital': 'Vốn đầu tư',
    'Net Tangible Assets': 'Tài sản hữu hình thuần',
    'Preferred Securities Outside Stock Equity': 'Chứng khoán ưu đãi ngoài vốn cổ phần',
    'Restricted Common Stock': 'Cổ phiếu phổ thông bị hạn chế',
    'Other Equity Interest': 'Lợi ích vốn chủ sở hữu khác',
    'Payables And Accrued Expenses': 'Phải trả và chi phí phải trả',
    'Income Tax Payable': 'Thuế TNDN phải trả',
    'Total Deposits': 'Tổng tiền gửi khách hàng',
    'Depositsby Bank': 'Tiền gửi và vay các tổ chức tín dụng khác',
    'Federal Funds Purchased And Securities Sold Under Agreements To Repurchase': 'Giao dịch mua bán lại trái phiếu và vay liên ngân hàng',
    'Buildings And Improvements': 'Nhà cửa và vật kiến trúc',
    'Other Properties': 'Bất động sản khác',
    'EPS': 'Lãi cơ bản trên cổ phiếu',
    'ROE': 'Lợi nhuận trên vốn chủ sở hữu (ROE)',
    'ROA': 'Lợi nhuận trên tổng tài sản (ROA)',
    'FCF': 'Dòng tiền tự do (FCF)',
    'FVTPL': 'Tài sản tài chính ghi nhận thông qua lãi lỗ (FVTPL)',
    'HTM': 'Các khoản đầu tư nắm giữ đến ngày đáo hạn (HTM)',
    'AFS': 'Tài sản tài chính sẵn sàng để bán (AFS)',
}

# ==============================================================================
# 5. FALLBACK_MAP — dịch word-by-word nếu không tìm thấy trong từ điển chính
# ==============================================================================
FALLBACK_MAP = {
    'deferred': 'hoãn lại', 'taxes': 'thuế', 'liabilities': 'nợ phải trả',
    'payable': 'phải trả', 'receivable': 'phải thu', 'receivables': 'các khoản phải thu',
    'payables': 'các khoản phải trả', 'current': 'ngắn hạn', 'non current': 'dài hạn',
    'total': 'tổng', 'net': 'thuần', 'gross': 'gộp', 'operating': 'hoạt động',
    'activities': 'hoạt động', 'investing': 'đầu tư', 'financing': 'tài chính',
    'cash': 'tiền mặt', 'equivalents': 'tương đương', 'flow': 'lưu chuyển',
    'income': 'thu nhập', 'expense': 'chi phí', 'expenses': 'chi phí',
    'revenue': 'doanh thu', 'profit': 'lợi nhuận', 'loss': 'lỗ', 'gain': 'lãi',
    'asset': 'tài sản', 'assets': 'tài sản', 'liability': 'nợ phải trả',
    'equity': 'vốn chủ sở hữu', 'capital': 'vốn', 'share': 'cổ phiếu',
    'shares': 'cổ phiếu', 'stock': 'cổ phiếu', 'stockholders': 'cổ đông',
    'interest': 'lãi', 'dividend': 'cổ tức', 'dividends': 'cổ tức',
    'tax': 'thuế', 'income tax': 'thuế thu nhập', 'depreciation': 'khấu hao',
    'amortization': 'phân bổ', 'inventory': 'hàng tồn kho', 'inventories': 'hàng tồn kho',
    'prepaid': 'trả trước', 'accrued': 'phải trả', 'pension': 'lương hưu',
    'retirement': 'hưu trí', 'benefit': 'phúc lợi', 'benefits': 'phúc lợi',
    'plans': 'kế hoạch', 'employee': 'nhân viên', 'employees': 'nhân viên',
    'goodwill': 'lợi thế thương mại', 'intangible': 'vô hình',
    'intangibles': 'tài sản vô hình', 'property': 'bất động sản',
    'properties': 'bất động sản', 'plant': 'nhà máy', 'equipment': 'thiết bị',
    'machinery': 'máy móc', 'land': 'đất đai', 'buildings': 'nhà cửa',
    'improvements': 'cải tạo', 'construction': 'xây dựng', 'progress': 'dở dang',
    'lease': 'thuê', 'leases': 'thuê', 'obligation': 'nghĩa vụ',
    'obligations': 'nghĩa vụ', 'debt': 'nợ vay', 'borrowings': 'vay',
    'issuance': 'phát hành', 'repayment': 'trả nợ', 'proceeds': 'tiền thu',
    'payments': 'thanh toán', 'receipts': 'khoản thu', 'purchase': 'mua',
    'sale': 'bán', 'sales': 'bán hàng', 'business': 'công ty',
    'subsidiaries': 'công ty con', 'subsidiary': 'công ty con',
    'associates': 'công ty liên kết', 'joint ventures': 'liên doanh',
    'investments': 'đầu tư', 'investment': 'đầu tư', 'securities': 'chứng khoán',
    'held': 'nắm giữ', 'maturity': 'đáo hạn', 'available': 'sẵn sàng',
    'sale': 'bán', 'trading': 'kinh doanh', 'fair': 'hợp lý',
    'value': 'giá trị', 'designated': 'được chỉ định', 'through': 'qua',
    'profit': 'lãi', 'comprehensive': 'tổng hợp', 'reserve': 'quỹ dự trữ',
    'retained': 'giữ lại', 'earnings': 'lợi nhuận', 'treasury': 'quỹ',
    'preferred': 'ưu đãi', 'common': 'phổ thông', 'ordinary': 'phổ thông',
    'issued': 'đã phát hành', 'outstanding': 'lưu hành',
    'basic': 'cơ bản', 'diluted': 'pha loãng', 'average': 'bình quân',
    'weighted': 'bình quân gia quyền', 'per': 'trên mỗi', 'share': 'cổ phiếu',
    'shares': 'cổ phiếu', 'number': 'số lượng', 'amount': 'số tiền',
    'balance': 'số dư', 'beginning': 'đầu kỳ', 'end': 'cuối kỳ',
    'change': 'biến động', 'changes': 'biến động', 'other': 'khác',
    'unusual': 'bất thường', 'items': 'khoản mục', 'item': 'khoản mục',
    'special': 'đặc biệt', 'extraordinary': 'bất thường',
    'discontinued': 'không liên tục', 'continuing': 'tiếp tục',
    'operations': 'hoạt động', 'operation': 'hoạt động',
    'minority': 'không kiểm soát', 'noncontrolling': 'không kiểm soát',
    'parent': 'công ty mẹ', 'company': 'công ty',
    'segment': 'bộ phận', 'segments': 'bộ phận',
    'unusual items': 'khoản mục bất thường',
    'effect': 'ảnh hưởng', 'exchange rate': 'tỷ giá',
    'foreign currency': 'ngoại tệ', 'conversion': 'chuyển đổi',
    'adjustment': 'điều chỉnh', 'adjustments': 'điều chỉnh',
    'restructuring': 'tái cấu trúc', 'merger': 'sáp nhập',
    'acquisition': 'mua lại', 'impairment': 'tổn thất',
    'compensation': 'thù lao', 'stock based': 'cổ phiếu thưởng',
    'share based': 'cổ phiếu thưởng', 'excess': 'vượt trội',
    'provision': 'dự phòng', 'provisions': 'dự phòng',
    'doubtful': 'khó đòi', 'allowance': 'dự phòng',
    'written off': 'xóa sổ', 'write off': 'xóa sổ',
    'impairment charge': 'chi phí tổn thất',
    'note': 'giấy nợ', 'notes': 'giấy nợ',
    'accrued expense': 'chi phí phải trả', 'accrued expenses': 'chi phí phải trả',
    'accrued liabilities': 'nợ phải trả ngắn hạn',
    'rent': 'thuê', 'landing': 'hạ cánh', 'fees': 'phí',
    'insurance': 'bảo hiểm', 'claims': 'khiếu nại',
    'salaries': 'lương', 'wages': 'tiền công',
    'marketing': 'tiếp thị', 'selling': 'bán hàng',
    'general': 'tổng quát', 'administrative': 'hành chính',
    'research': 'nghiên cứu', 'development': 'phát triển',
    'fee': 'phí', 'commission': 'hoa hồng',
    'commissions': 'hoa hồng', 'gain': 'lãi', 'loss': 'lỗ',
    'realized': 'đã thực hiện', 'unrealized': 'chưa thực hiện',
    'revaluation': 'đánh giá lại', 'reserve': 'quỹ',
    'translations': 'chuyển đổi', 'minimum': 'tối thiểu',
    'capital lease': 'thuê tài chính', 'operating lease': 'thuê hoạt động',
    'line of credit': 'hạn mức tín dụng', 'commercial paper': 'thương phiếu',
    'hedging': 'phòng ngừa rủi ro', 'derivative': 'phái sinh',
    'derivatives': 'phái sinh', 'financial': 'tài chính',
    'held for sale': 'nắm giữ để bán',
    'money market': 'thị trường tiền tệ',
    'deposit': 'tiền gửi', 'deposits': 'tiền gửi',
    'loan': 'cho vay', 'loans': 'cho vay',
    'credit': 'tín dụng', 'margin': 'ký quỹ',
    'tax rate': 'thuế suất', 'rate': 'tỷ lệ',
    'book value': 'giá trị sổ sách',
    'market cap': 'vốn hóa thị trường',
    'market capitalization': 'vốn hóa thị trường',
    'price': 'giá', 'eps': 'EPS', 'roe': 'ROE', 'roa': 'ROA',
    'return on equity': 'lợi nhuận trên vốn chủ sở hữu',
    'return on assets': 'lợi nhuận trên tổng tài sản',
    'margin': 'biên', 'margins': 'biên',
    'yield': 'lợi suất', 'trailing': 'cơ bản', 'forward': 'dự phóng',
}

# ==============================================================================
# 6. TIỆN ÍCH CHUẨN HOÁ
# ==============================================================================
_WHITELIST_LOWER = {v.lower(): v for v in VAS_WHITELIST}
_ALIAS_LOWER = {k.lower(): v for k, v in ALIAS_TO_VAS.items()}
_TRANS_LOWER = {k.lower(): v for k, v in TRANSLATION_MAP.items()}
_FALLBACK_KEYS_SORTED = sorted(FALLBACK_MAP.keys(), key=len, reverse=True)

_EXTRA_ENGLISH_LABELS = [
    'Depreciation And Amortization', 'Depreciation',
    'Gain Loss On Investment Securities', 'Net Foreign Currency Exchange Gain',
    'Net Income From Continuing Operation Net Minority Interest',
    'Free Cash Flow', 'Repayment Of Debt', 'End Cash Position', 'Beginning Cash Position',
    'Changes In Cash', 'Financing Cash Flow', 'Net Issuance Payments Of Debt',
    'Net Long Term Debt Issuance', 'Long Term Debt Payments', 'Long Term Debt Issuance',
    'Investing Cash Flow', 'Interest Received Cfi', 'Operating Cash Flow',
    'Taxes Refund Paid', 'Interest Paid Cfo', 'Change In Working Capital',
    'Change In Payable', 'Change In Prepaid Assets', 'Change In Inventory',
    'Change In Receivables', 'Other Non Cash Items', 'Gross Profit',
    'Cost Of Revenue', 'Total Revenue', 'Operating Revenue', 'Diluted Average Shares',
    'Basic Average Shares', 'Diluted EPS', 'Basic EPS', 'Selling General And Administration',
    'General And Administrative Expense', 'Tax Rate For Calcs', 'Normalized EBITDA',
    'Reconciled Depreciation', 'Reconciled Cost Of Revenue', 'EBITDA', 'EBIT',
    'Net Interest Income', 'Interest Expense', 'Interest Income', 'Normalized Income',
    'Total Expenses', 'Total Operating Income As Reported',
    'Net Income From Continuing And Discontinued Operation',
    'Gain On Investment Securities', 'Loss On Investment Securities',
    'Unrealized Gain Loss On Investment Securities',
    'Realized Gain Loss On Investment Securities',
    'Foreign Currency Exchange Gains Losses', 'Gain On Sale Of PPE',
    'Gain On Sale Of Business', 'Earnings Losses From Equity Investments',
    'Earnings From Equity Interest', 'Earnings From Equity Interest Net Of Tax',
    'Total Unusual Items', 'Impairment Of Capital Assets',
    'Restructuring And Mergern Acquisition', 'Stock Based Compensation',
    'Share Based Compensation', 'Excess Tax Benefit From Stock Based Compensation',
    'Provisionand Write Offof Assets', 'Provision For Doubtful Accounts',
    'Net Short Term Debt Issuance', 'Short Term Debt Issuance', 'Short Term Debt Payments',
    'Interest Paid Cff', 'Interest Paid Supplemental Data', 'Income Tax Paid Supplemental Data',
    'Tax Paid', 'Dividends Paid Cfo', 'Dividends Received Cfo', 'Dividend Received Cfi',
    'Dividends Paid', 'Dividends Received', 'Common Stock Dividend Paid',
    'Preferred Stock Dividend Paid', 'Change In Payables And Accrued Expense',
    'Change In Accrued Expense', 'Change In Other Current Assets',
    'Change In Other Current Liabilities', 'Change In Tax Payable',
    'Change In Dividend Payable', 'Other Cash Adjustment Inside Changein Cash',
    'Other Cash Adjustment Outside Changein Cash',
    'Purchase Of Investment', 'Sale Of Investment', 'Purchase Of Business', 'Sale Of Business',
    'Common Stock Issuance', 'Common Stock Repurchase', 'Repurchase Of Capital Stock',
    'Issuance Of Capital Stock', 'Net Other Financing Charges', 'Net Other Investing Changes',
    'Rent And Landing Fees', 'Insurance And Claims', 'Salaries And Wages',
    'Other Gand A', 'Other G And A', 'Interest Income Non Operating',
    'Interest Expense Non Operating', 'Total Other Income Expense Net',
    'Provision For Loan Lease And Other Losses', 'Net Fee And Commission Income',
    'Net Commission Income', 'Fees And Commissions', 'Net Investment Income',
    'Trading Gain Loss', 'Net Realized Gain Loss On Investments',
]
_ENGLISH_PURGE = {k for k in list(TRANSLATION_MAP.keys()) + list(ALIAS_TO_VAS.keys()) + _EXTRA_ENGLISH_LABELS
                  if k.isascii() and re.search(r'[A-Za-z]', k)}

# ==============================================================================
# 7. CLEANING HELPERS
# ==============================================================================
def clean_text(text):
    if text is None:
        return ""
    try:
        if pd.isna(text):
            return ""
    except (TypeError, ValueError):
        pass
    text = unicodedata.normalize('NFC', str(text))
    text = re.sub(r'[\n\r\t]+', ' ', text)
    return re.sub(r'\s{2,}', ' ', text).strip()

def _norm_key(s):
    s = unicodedata.normalize('NFC', str(s))
    s = re.sub(r'[\n\r\t]+', ' ', s)
    s = re.sub(r'\s{2,}', ' ', s).strip()
    s = re.sub(r'\s*[\[(]\d+[a-zA-Z]?[\])]\s*$', '', s)
    s = re.sub(r'\s*\(\d+[a-z]?\)\s*$', '', s)
    s = s.rstrip(' :.')
    return s.strip()

def _looks_english(s):
    low = s.lower()
    if re.search(r'[àáảãạăắằẳẵặâấầẩẫậèéẻẽẹêếềểễệìíỉĩịòóỏõọôốồổỗộơớờởỡợùúủũụưứừửữựỳýỷỹỵđ]', low):
        return False
    return bool(re.search(r'[a-z]', low))

def format_value(x):
    if x is None:
        return None
    if isinstance(x, str):
        s = x.strip().replace(' ', '').replace('\u00a0', '')
        if not s or s.lower() in ('nan', 'none', 'null', '-', ''):
            return None
        neg = s.startswith('(') and s.endswith(')')
        if neg:
            s = s[1:-1]
        s = s.replace('%', '').replace(',', '')
        if s.count('.') > 1:
            s = s.replace('.', '')
        try:
            val = float(s)
        except (TypeError, ValueError):
            return None
        if neg:
            val = -val
    else:
        try:
            if pd.isna(x):
                return None
            val = float(x)
        except (TypeError, ValueError):
            return None
    if not math.isfinite(val) or abs(val) > 1e18:
        return None
    if val == 0:
        return None
    r = round(val, 4)
    if r == int(r) and abs(r) < 9.007e15:
        return int(r)
    return r

# 🆕 v19: Bảng cụt KHỚP CHÍNH XÁC (không startswith)
_TRUNCATED_FIX = {
    'Các khoản phải': 'Các khoản phải thu',
    'Lợi nhuận trước': 'Lợi nhuận trước thuế',
    'Thuế và các kho': 'Thuế và các khoản phải nộp Nhà nước',
    'Tiền và tương đ': 'Tiền và tương đương tiền',
    'TỔNG CỘNG N': 'TỔNG CỘNG NỢ PHẢI TRẢ',
    'VỐN CHỦ SỞ H': 'Vốn chủ sở hữu',
    'Cổ phiếu phổ thô': 'Cổ phiếu phổ thông',
    'Đầu tư dài hạn k': 'Đầu tư tài chính dài hạn',
    'Lợi nhuận thuần': 'Lợi nhuận thuần từ hoạt động kinh doanh',
    'Lưu chuyển tiền': 'Lưu chuyển tiền thuần trong kỳ',
    'Lãi / Lỗ từ đánh': 'Lãi / Lỗ từ đánh giá lại tài sản',
    'Tổng khác f giá gốc': 'Tổng chi phí khác theo giá gốc',
    'Các công cụ tài chính phái sinh và các': 'Các công cụ tài chính phái sinh và tài sản tài chính khác',
    'Các khoản nợ chính phủ và NHNN Việ': 'Nợ Chính phủ và Ngân hàng Nhà nước',
    'Các khoản nợ chính phủ và NHNN Việt': 'Nợ Chính phủ và Ngân hàng Nhà nước',
    'Các khoản nợ chính phủ và NHNN Việt Nam': 'Nợ Chính phủ và Ngân hàng Nhà nước',
    'Chứng khoán đầu tư giữ đến ngày đáo': 'Chứng khoán đầu tư giữ đến ngày đáo hạn',
    'NỢ PHẢI TRẢ VÀ VỐN CHỦ SỞ H': 'Tổng cộng nguồn vốn',
    'NỢ PHẢI TRẢ VÀ VỐN CHỦ SỞ HỮU': 'Tổng cộng nguồn vốn',
    'TỔNG CỘNG TÀI SẢN': 'Tổng cộng tài sản',
    'TỔNG CỘNG NGUỒN VỐN': 'Tổng cộng nguồn vốn',
    'TỔNG CỘNG NỢ PHẢI TRẢ': 'Nợ phải trả',
    'VỐN CHỦ SỞ HỮU': 'Vốn chủ sở hữu',
    'Dự phòng giảm giá chứng khoán kinh': 'Dự phòng giảm giá chứng khoán kinh doanh',
    'Dự phòng giảm giá đầu tư dài hạn': 'Dự phòng đầu tư tài chính dài hạn',
    'Chi phí quản lý doanh nghiệ': 'Chi phí quản lý doanh nghiệp',
    'Chi phí bán hà': 'Chi phí bán hàng',
    'Lợi nhuận sau thuế chưa phân phố': 'Lợi nhuận sau thuế chưa phân phối',
}

def fix_truncated_text(text):
    t = clean_text(text)
    return _TRUNCATED_FIX.get(t, t)

# 🆕 v19: CHỈ chữa chữ DÍNH, KHÔNG chẻ chữ đúng
_GLUED_FIXES = [
    (r'Investmentsin', 'Investments in'),
    (r'venturesat', 'ventures at'),
    (r'associatesat', 'associates at'),
    (r'Subsidiariesat', 'Subsidiaries at'),
    (r'Pensi\s*onand', 'Pension and'),
    (r'\bN\s+on\b', 'Non'),
    (r'Classesof', 'Classes of'),
    (r'Receiptsfrom', 'Receipts from'),
    (r'Paymentsfrom', 'Payments from'),
    (r'Paymentson', 'Payments on'),
    (r'Behalfof', 'Behalf of'),
    (r'Changein', 'Change in'),
    (r'Write\s*Offof', 'Write Off of'),
    (r'Provisionand', 'Provision and'),
    (r'Designatedas', 'Designated as'),
    (r'Profitor', 'Profit or'),
    (r'Availablefor', 'Available for'),
    (r'Depositsby', 'Deposits by'),
    (r'Tradeand', 'Trade and'),
    (r'Mergern', 'Mergers'),
    (r'Availto', 'Available to'),
    (r'Excludinggoodwill', 'Excluding goodwill'),
]

def fix_yfinance_typos(text):
    for pat, rep in _GLUED_FIXES:
        text = re.sub(pat, rep, text, flags=re.IGNORECASE)
    return re.sub(r'\s{2,}', ' ', text).strip()

# ==============================================================================
# 8. TRANSLATE METRIC — 3 tầng: dict → fallback word-by-word → None
# ==============================================================================
def translate_metric(s):
    """Dịch nhãn English → VAS. Trả None nếu không dịch được."""
    if not s:
        return None
    s_clean = _norm_key(s)
    if s_clean in TRANSLATION_MAP:
        return TRANSLATION_MAP[s_clean]
    if s_clean in ALIAS_TO_VAS:
        return ALIAS_TO_VAS[s_clean]
    low = s_clean.lower()
    if low in _TRANS_LOWER:
        return _TRANS_LOWER[low]
    if low in _ALIAS_LOWER:
        return _ALIAS_LOWER[low]
    # Fallback: word-by-word
    work = s_clean
    matched = False
    for key in _FALLBACK_KEYS_SORTED:
        pattern = r'\b' + re.escape(key) + r'\b'
        if re.search(pattern, work, re.IGNORECASE):
            work = re.sub(pattern, FALLBACK_MAP[key], work, flags=re.IGNORECASE)
            matched = True
    if matched and not _looks_english(work):
        return clean_text(work)
    return None

# ==============================================================================
# 9. STANDARDIZE METRIC — single source of truth
# ==============================================================================
@lru_cache(maxsize=300000)
def _std_cached(metric, rtype):
    s = _norm_key(metric)
    if not s or s.lower() in ('nan', 'none', 'null'):
        return None
    if "Chỉ số thị trường" in rtype or "Chỉ số vĩ mô" in rtype:
        return None if is_junk_label(s) else s
    if s in VAS_WHITELIST:
        return s
    low = s.lower()
    if low in _WHITELIST_LOWER:
        return _WHITELIST_LOWER[low]
    if s in ALIAS_TO_VAS:
        return ALIAS_TO_VAS[s]
    if low in _ALIAS_LOWER:
        return _ALIAS_LOWER[low]
    # Fix truncated
    fixed = fix_truncated_text(s)
    if fixed != s:
        if fixed in VAS_WHITELIST:
            return fixed
        if fixed.lower() in _WHITELIST_LOWER:
            return _WHITELIST_LOWER[fixed.lower()]
        if fixed in ALIAS_TO_VAS:
            return ALIAS_TO_VAS[fixed]
        if fixed.lower() in _ALIAS_LOWER:
            return _ALIAS_LOWER[fixed.lower()]
        s = fixed
        low = s.lower()
    # Fallback translate
    if _looks_english(s):
        fixed_en = fix_yfinance_typos(s)
        if fixed_en != s:
            s = fixed_en
        t = translate_metric(s)
        if t is None or is_junk_label(t) or _looks_english(t):
            return None  # KEY: KHÔNG BAO GIỜ leak English
        if t in VAS_WHITELIST:
            return t
        if t.lower() in _WHITELIST_LOWER:
            return _WHITELIST_LOWER[t.lower()]
        if t in ALIAS_TO_VAS:
            return ALIAS_TO_VAS[t]
        if t.lower() in _ALIAS_LOWER:
            return _ALIAS_LOWER[t.lower()]
        return t
    if is_junk_label(s):
        return None
    return s

def standardize_metric(raw_metric, report_type):
    if raw_metric is None:
        return None
    try:
        if pd.isna(raw_metric):
            return None
    except (TypeError, ValueError):
        pass
    return _std_cached(str(raw_metric), str(report_type))

# ==============================================================================
# 10. SUPABASE SETUP
# ==============================================================================
os.environ["VNSTOCK_API_KEY"] = "vnstock_533590cc17b6737ceb7c9f147471f31f"

try:
    import vnfinancialdata as vnf
except ImportError:
    print("⚙️ Đang cài đặt vnfinancialdata...")
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

try:
    from supabase import create_client
    HAS_SUPABASE_LIB = True
except ImportError:
    os.system("pip install supabase --quiet")
    try:
        from supabase import create_client
        HAS_SUPABASE_LIB = True
    except Exception:
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
PUSH_TO_SUPABASE = os.environ.get("PUSH_TO_SUPABASE", "false").lower() == "true"
SUPABASE_ON_CONFLICT = os.environ.get("SUPABASE_ON_CONFLICT", "ticker,report_type,period_type,report_date,item_vn")
PURGE_SUPABASE_BAD = os.environ.get("PURGE_SUPABASE_BAD", "true").strip().lower() in ("1", "true", "yes", "y")
SKIP_VNDIRECT = os.environ.get("SKIP_VNDIRECT", "true").strip().lower() in ("1", "true", "yes", "y")

STANDARD_COLUMNS = [
    'Mã chứng khoán', 'Tên doanh nghiệp', 'Tên ngành',
    'Loại báo cáo', 'Loại kỳ', 'Năm', 'Ngày kỳ',
    'Chỉ tiêu tiếng Việt', 'Giá trị'
]

VN_TO_EN_MAP = {
    'Mã chứng khoán': 'ticker', 'Tên doanh nghiệp': 'company_name', 'Tên ngành': 'sector',
    'Loại báo cáo': 'report_type', 'Loại kỳ': 'period_type', 'Năm': 'year',
    'Ngày kỳ': 'report_date', 'Chỉ tiêu tiếng Việt': 'item_vn', 'Giá trị': 'value'
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
        print("⚠️ [SUPABASE] Thiếu thư viện.")
        return None
    if not SUPABASE_URL or not SUPABASE_KEY:
        print("⚠️ [SUPABASE] Thiếu URL/KEY.")
        return None
    try:
        _supabase_client = create_client(SUPABASE_URL, SUPABASE_KEY)
        print(f"✅ [SUPABASE] Đã kết nối '{SUPABASE_TABLE}'.")
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
            print(f"⚠️ [{label}] Lỗi {attempt+1}, retry sau {backoff**attempt}s: {e}")
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

# ==============================================================================
# 11. FINAL CLEAN — pass cuối trước save/push
# ==============================================================================
def final_clean_df(df):
    """Vá triệt để: strip [n], drop zero/NaN/rỗng/junk/English, dedup, ép int."""
    if df is None or df.empty:
        return pd.DataFrame(columns=STANDARD_COLUMNS)

    df = df.copy()
    before = len(df)

    # 1) Chuẩn hoá cột
    for col in STANDARD_COLUMNS:
        if col not in df.columns:
            df[col] = ''

    # 2) Ticker
    df['Mã chứng khoán'] = df['Mã chứng khoán'].astype(str).str.strip().str.upper()
    df = df[~df['Mã chứng khoán'].isin(['', 'NAN', 'NONE', 'NULL'])]

    # 3) Giá trị
    df['Giá trị'] = pd.to_numeric(df['Giá trị'], errors='coerce')
    df = df.dropna(subset=['Giá trị'])
    df = df[df['Giá trị'] != 0]

    # 4) Chuẩn hoá nhãn (strip [n] + dịch nếu cần)
    df['Loại báo cáo'] = df['Loại báo cáo'].map(lambda x: TRANSLATION_MAP.get(clean_text(x), clean_text(x)))
    _ky_map = {'quarter': 'Quý', 'quarterly': 'Quý', 'year': 'Năm', 'annual': 'Năm'}
    df['Loại kỳ'] = df['Loại kỳ'].map(lambda x: _ky_map.get(str(x).strip().lower(), x))

    df['Chỉ tiêu tiếng Việt'] = [
        standardize_metric(m, rt)
        for m, rt in zip(df['Chỉ tiêu tiếng Việt'], df['Loại báo cáo'])
    ]
    df = df.dropna(subset=['Chỉ tiêu tiếng Việt'])
    df = df[~df['Chỉ tiêu tiếng Việt'].map(is_junk_label)]
    df = df[~df['Chỉ tiêu tiếng Việt'].map(_looks_english)]

    # 5) Ép int cho value (bỏ .0)
    def _int_val(v):
        try:
            f = float(v)
            if f == int(f) and abs(f) < 9.007e15:
                return int(f)
            return round(f, 4)
        except Exception:
            return None
    df['Giá trị'] = df['Giá trị'].apply(_int_val)
    df = df.dropna(subset=['Giá trị'])
    df = df[df['Giá trị'] != 0]

    # 6) Dedup (sau chuẩn hoá nhãn)
    df = df.drop_duplicates(
        subset=['Mã chứng khoán', 'Loại báo cáo', 'Loại kỳ', 'Ngày kỳ', 'Chỉ tiêu tiếng Việt'],
        keep='last'
    )

    print(f"🧹 [FINAL_CLEAN] {before:,} → {len(df):,} dòng (bỏ {before-len(df):,} rác/zero/trùng/Anh)")
    return df.reset_index(drop=True)

# ==============================================================================
# 12. LOAD / UPSERT / PURGE SUPABASE
# ==============================================================================
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
        print(f"✅ [SUPABASE] Đã tải {len(df):,} dòng (sẽ clean sau).")
        return final_clean_df(df)
    except Exception as e:
        print(f"❌ [SUPABASE] Lỗi tải: {e}")
        return pd.DataFrame(columns=STANDARD_COLUMNS)

def upsert_to_supabase(df, batch_size=500):
    client = init_supabase()
    if client is None: return False
    if df is None or df.empty: return False

    # 🆕 v19: CLEAN trước upsert
    df = final_clean_df(df)
    if df.empty:
        print("⚠️ [SUPABASE] Không còn dòng hợp lệ sau khi clean.")
        return False

    try:
        payload = df.copy()
        payload = payload.rename(columns=VN_TO_EN_MAP)
        valid_cols = ['ticker', 'company_name', 'sector', 'report_type', 'period_type', 'year', 'report_date', 'item_vn', 'value']
        for col in valid_cols:
            if col not in payload.columns: payload[col] = None

        records = []
        skipped_bad = 0
        for row in payload.to_dict('records'):
            ticker = str(row['ticker']).strip() if pd.notna(row['ticker']) else ''
            if not ticker: continue
            val = pd.to_numeric(row['value'], errors='coerce')
            if pd.isna(val) or val == 0: continue
            item = clean_text(row['item_vn']) if pd.notna(row['item_vn']) else ''
            if not item or is_junk_label(item) or _looks_english(item):
                skipped_bad += 1
                continue
            yr = pd.to_numeric(row['year'], errors='coerce')
            if pd.isna(yr):
                m = re.match(r'(\d{4})', str(row['report_date'] or ''))
                yr = int(m.group(1)) if m else datetime.now().year
            yr = int(yr)

            def _cs(s):
                if pd.isna(s): return None
                s = str(s).strip()
                return s if s else None

            records.append({
                'ticker': ticker,
                'company_name': _cs(row['company_name']),
                'sector': _cs(row['sector']),
                'report_type': _cs(row['report_type']),
                'period_type': _cs(row['period_type']),
                'year': yr,
                'report_date': _cs(row['report_date']),
                'item_vn': item,
                'value': float(val),
            })

        total = len(records)
        if skipped_bad:
            print(f"🧹 [SUPABASE] Chặn {skipped_bad:,} dòng rác trước upsert.")
        if total == 0:
            print("⚠️ [SUPABASE] Không có bản ghi hợp lệ.")
            return False

        print(f"📤 [SUPABASE] Upsert {total:,} bản ghi...")
        upsert_kwargs = {}
        if SUPABASE_ON_CONFLICT:
            upsert_kwargs['on_conflict'] = SUPABASE_ON_CONFLICT

        for i in range(0, total, batch_size):
            chunk = records[i:i+batch_size]
            def _do_upsert(c=chunk, kw=upsert_kwargs):
                return client.table(SUPABASE_TABLE).upsert(c, **kw).execute()
            _retry(_do_upsert, label="SUPABASE_UPSERT")
            print(f"   ✓ {min(i+batch_size, total):,}/{total:,}")
        print("✅ [SUPABASE] Upsert xong.")
        return True
    except Exception as e:
        print(f"❌ [SUPABASE] Lỗi upsert: {e}")
        return False

def purge_supabase_bad_rows():
    """Purge triệt để: zero/NULL/junk/English/[n]."""
    client = init_supabase()
    if client is None: return
    print("🧽 [SUPABASE] Purge dòng bẩn...")
    T = SUPABASE_TABLE

    def _run(label, fn):
        try:
            resp = _retry(fn, max_retries=2, backoff=2, label="PURGE")
            n = len(getattr(resp, 'data', None) or [])
            print(f"   ✓ {label}: xoá {n:,}")
        except Exception as e:
            print(f"   ⚠️ {label}: {type(e).__name__}: {e}")

    _run("value = 0", lambda: client.table(T).delete().eq('value', 0).execute())
    _run("value NULL", lambda: client.table(T).delete().is_('value', 'null').execute())
    _run("item_vn NULL", lambda: client.table(T).delete().is_('item_vn', 'null').execute())
    _run("item_vn rỗng", lambda: client.table(T).delete().eq('item_vn', '').execute())
    junk_variants = sorted({j for j in JUNK_EXACT if j} | {j.capitalize() for j in JUNK_EXACT if j} | {j.title() for j in JUNK_EXACT if j})
    _run("nhãn rác", lambda: client.table(T).delete().in_('item_vn', junk_variants).execute())
    _run("chưa xác định", lambda: client.table(T).delete().like('item_vn', '%chưa xác định%').execute())
    _run("dính [n]", lambda: client.table(T).delete().like('item_vn', '%[%]').execute())
    en = sorted(_ENGLISH_PURGE)
    for i in range(0, len(en), 40):
        chunk = en[i:i+40]
        _run(f"English đợt {i//40+1}", lambda c=chunk: client.table(T).delete().in_('item_vn', c).execute())
    print("✅ [SUPABASE] Purge xong.")

# ==============================================================================
# 13. DATA SOURCES (reconstruct — chỉ phần lõi)
# ==============================================================================
DATA_PATH = "du_lieu/dulieu_hang_ngay.csv"
HF_DATA_URL = "https://huggingface.co/datasets/trananhquan2001/finex-vn-dataset/raw/main/dulieu_hang_ngay.csv"

def load_daily_stock_data():
    if os.path.exists(DATA_PATH):
        try: return pd.read_csv(DATA_PATH)
        except Exception: pass
    try: return pd.read_csv(HF_DATA_URL)
    except Exception: return pd.DataFrame()

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
    tech_list = ["FPT","CMG","VTP","ICT","ELC","CTR","VGI","VNZ","FOX","FOC","VTK","MFS","VEC"]
    bank_list = ["VCB","BID","TCB","MBB","ACB","CTG","VPB","STB","SHB","HDB","LPB","MSB","OCB","NAB","SSB","EIB","TPB","ABB","BAB"]
    securities_list = ["SSI","VCI","HCM","VND","SHS","MBS","FTS","BSI","CTS","VIX","VDS","ORS","AGR","VFS","DSE","BVS","EVF","IPA","EVS","HBS","PSI","WSS","F88"]
    realestate_list = ["VIC","VHM","VRE","BCM","KBC","IDC","SIP","SZC","KDH","NLG","DXG","PDR","DIG","CEO","HDC","NVL","TCH","VC3","VPI","SJS","L14","L18","NDN","THD","KSF","IJC","TDC","CTI","VEF","TED","CC1","PCC","LIC","CLI","HEC"]
    retail_list = ["MWG","FRT","DGW","PNJ","PET","DMX"]
    oil_gas_list = ["GAS","PLX","PVD","PVS","PVT","PVB","BSR","OIL","POW","DTK","PGV","NT2","PGI","PLC","PSD","PVC","SJD","TMP","SBA","VSH","TTA","TV2","VCP","ODE","AVC"]
    steel_materials = ["HPG","HSG","NKG","GDA","BMP","NTP","AAA","DGC","CSV","LAS","PHR","DPM","DCM","BFC","HPA","VGS","HT1","LHC","HGM","KSV","TLH","DDV","DPR","DHC","VLB","HPP","VXB","PAT","SIV","ACE","HAM","SBM","SCL","NAS","HMS","QPH"]
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
        "ACB":"Ngân hàng TMCP Á Châu","VIC":"Tập đoàn Vingroup","VHM":"Vinhomes",
        "FPT":"CTCP FPT","HPG":"Tập đoàn Hòa Phát","VCB":"Ngân hàng TMCP Ngoại thương VN",
        "BID":"Ngân hàng TMCP Đầu tư và Phát triển VN","CTG":"Ngân hàng TMCP Công thương VN",
        "TCB":"Ngân hàng TMCP Kỹ thương VN","MBB":"Ngân hàng TMCP Quân đội",
        "VPB":"Ngân hàng TMCP Việt Nam Thịnh Vượng","MSN":"Tập đoàn Masan",
        "MWG":"CTCP Đầu tư Thế Giới Di Động","PNJ":"CTCP Vàng bạc Đá quý Phú Nhuận",
        "SAB":"Tổng CTCP Bia - Rượu - Nước giải khát Sài Gòn","GAS":"Tổng Công ty Khí VN",
        "PLX":"Tập đoàn Xăng dầu VN","VNM":"CTCP Sữa VN","VJC":"CTCP Hàng không Vietjet",
        "NVL":"CTCP Tập đoàn Đầu tư Địa ốc No Va","SSI":"CTCP Chứng khoán SSI",
        "HDB":"Ngân hàng TMCP Phát triển TP.HCM","VRE":"CTCP Vincom Retail",
        "POW":"Tổng Công ty Điện lực Dầu khí VN","REE":"CTCP Cơ Điện Lạnh",
        "BVH":"Tập đoàn Bảo Việt","SHB":"Ngân hàng TMCP Sài Gòn - Hà Nội",
        "STB":"Ngân hàng TMCP Sài Gòn Thương Tín","TPB":"Ngân hàng TMCP Tiên Phong",
    }
    return company_names.get(symbol, f"Công ty Cổ phần {symbol}"), sector

# ==============================================================================
# 14. HTTP SESSION
# ==============================================================================
def _make_session():
    s = requests.Session()
    adapter = HTTPAdapter(pool_connections=20, pool_maxsize=20, max_retries=3)
    s.mount('http://', adapter)
    s.mount('https://', adapter)
    s.headers.update({'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'})
    return s

_SESSION = _make_session()

# ==============================================================================
# 15. FETCHERS (rút gọn — giữ API công khai)
# ==============================================================================
def fetch_yfinance(ticker, period='quarterly'):
    """Fetch yfinance — trả DataFrame chuẩn (sẽ clean sau)."""
    try:
        t = yf.Ticker(f"{ticker}.VN")
        if period == 'quarterly':
            bs = t.quarterly_balance_sheet
            inc = t.quarterly_income_stmt
            cf = t.quarterly_cashflow
        else:
            bs = t.balance_sheet
            inc = t.income_stmt
            cf = t.cashflow
        rows = []
        for df_src, rtype in [(bs, 'Bảng cân đối kế toán'),
                              (inc, 'Báo cáo kết quả kinh doanh'),
                              (cf, 'Báo cáo lưu chuyển tiền tệ')]:
            if df_src is None or df_src.empty: continue
            for dt_col in df_src.columns:
                if not hasattr(dt_col, 'year'): continue
                ngay = dt_col.strftime('%Y-%m-%d')
                year = str(dt_col.year)
                for metric, val in df_src[dt_col].items():
                    v = format_value(val)
                    if v is None: continue
                    rows.append({
                        'Mã chứng khoán': ticker,
                        'Tên doanh nghiệp': get_company_profile(ticker)[0],
                        'Tên ngành': get_company_profile(ticker)[1],
                        'Loại báo cáo': rtype,
                        'Loại kỳ': 'Quý' if period == 'quarterly' else 'Năm',
                        'Năm': year,
                        'Ngày kỳ': ngay,
                        'Chỉ tiêu tiếng Việt': str(metric),
                        'Giá trị': v,
                    })
        return pd.DataFrame(rows) if rows else pd.DataFrame(columns=STANDARD_COLUMNS)
    except Exception as e:
        print(f"   ⚠️ YF {ticker} {period}: {e}")
        return pd.DataFrame(columns=STANDARD_COLUMNS)

def fetch_yfinance_market(ticker):
    try:
        t = yf.Ticker(f"{ticker}.VN")
        info = t.info or {}
        rows = []
        today = datetime.today().strftime('%Y-%m-%d')
        year = str(datetime.now().year)
        for k, rtype in [
            ('currentPrice', 'Chỉ số thị trường, Định giá & Cổ tức'),
            ('marketCap', 'Chỉ số thị trường, Định giá & Cổ tức'),
            ('trailingPE', 'Chỉ số thị trường, Định giá & Cổ tức'),
            ('priceToBook', 'Chỉ số thị trường, Định giá & Cổ tức'),
            ('returnOnEquity', 'Chỉ số thị trường, Định giá & Cổ tức'),
            ('returnOnAssets', 'Chỉ số thị trường, Định giá & Cổ tức'),
            ('profitMargins', 'Chỉ số thị trường, Định giá & Cổ tức'),
            ('grossMargins', 'Chỉ số thị trường, Định giá & Cổ tức'),
            ('dividendYield', 'Chỉ số thị trường, Định giá & Cổ tức'),
            ('dividendRate', 'Chỉ số thị trường, Định giá & Cổ tức'),
            ('sharesOutstanding', 'Chỉ số thị trường, Định giá & Cổ tức'),
            ('bookValue', 'Chỉ số thị trường, Định giá & Cổ tức'),
            ('epsTrailingTwelveMonths', 'Chỉ số thị trường, Định giá & Cổ tức'),
            ('epsForward', 'Chỉ số thị trường, Định giá & Cổ tức'),
        ]:
            v = format_value(info.get(k))
            if v is None: continue
            rows.append({
                'Mã chứng khoán': ticker,
                'Tên doanh nghiệp': get_company_profile(ticker)[0],
                'Tên ngành': get_company_profile(ticker)[1],
                'Loại báo cáo': rtype,
                'Loại kỳ': 'Real-time',
                'Năm': year,
                'Ngày kỳ': today,
                'Chỉ tiêu tiếng Việt': k,
                'Giá trị': v,
            })
        return pd.DataFrame(rows) if rows else pd.DataFrame(columns=STANDARD_COLUMNS)
    except Exception as e:
        print(f"   ⚠️ YF market {ticker}: {e}")
        return pd.DataFrame(columns=STANDARD_COLUMNS)

def fetch_vnfinancial(ticker):
    if vnf is None:
        return pd.DataFrame(columns=STANDARD_COLUMNS)
    rows = []
    today = datetime.today().strftime('%Y-%m-%d')
    try:
        for rtype, fn_name in [
            ('Bảng cân đối kế toán', 'get_balance_sheet'),
            ('Báo cáo kết quả kinh doanh', 'get_income_statement'),
            ('Báo cáo lưu chuyển tiền tệ', 'get_cash_flow'),
        ]:
            fn = getattr(vnf, fn_name, None)
            if fn is None: continue
            try:
                df = fn(ticker, is_quarter=True)
            except Exception:
                continue
            if df is None or df.empty: continue
            if 'Chỉ tiêu' not in df.columns and 'item' not in df.columns:
                continue
            metric_col = 'Chỉ tiêu' if 'Chỉ tiêu' in df.columns else 'item'
            for _, r in df.iterrows():
                metric = r.get(metric_col)
                for col in df.columns:
                    if col in (metric_col, 'Mã', 'Code'): continue
                    v = format_value(r[col])
                    if v is None: continue
                    ngay = str(col) if re.search(r'\d{4}', str(col)) else today
                    year_match = re.search(r'(\d{4})', str(col))
                    year = year_match.group(1) if year_match else str(datetime.now().year)
                    rows.append({
                        'Mã chứng khoán': ticker,
                        'Tên doanh nghiệp': get_company_profile(ticker)[0],
                        'Tên ngành': get_company_profile(ticker)[1],
                        'Loại báo cáo': rtype,
                        'Loại kỳ': 'Quý',
                        'Năm': year,
                        'Ngày kỳ': ngay,
                        'Chỉ tiêu tiếng Việt': str(metric),
                        'Giá trị': v,
                    })
    except Exception as e:
        print(f"   ⚠️ VNF {ticker}: {e}")
    return pd.DataFrame(rows) if rows else pd.DataFrame(columns=STANDARD_COLUMNS)

def fetch_daily_index():
    try:
        df = load_daily_stock_data()
        if df is None or df.empty: return pd.DataFrame(columns=STANDARD_COLUMNS)
        today = datetime.today().strftime('%Y-%m-%d')
        year = str(datetime.now().year)
        rows = []
        for _, r in df.iterrows():
            ticker = str(r.get('Mã CP') or r.get('ticker') or r.get('Mã chứng khoán') or '').strip().upper()
            if not ticker: continue
            for k in ['Giá', 'KL', 'Vốn hóa', 'P/E', 'P/B', 'EPS', 'ROE', 'ROA']:
                if k in r and pd.notna(r[k]):
                    v = format_value(r[k])
                    if v is None: continue
                    rows.append({
                        'Mã chứng khoán': ticker,
                        'Tên doanh nghiệp': get_company_profile(ticker)[0],
                        'Tên ngành': get_company_profile(ticker)[1],
                        'Loại báo cáo': 'Chỉ số thị trường, Định giá & Cổ tức',
                        'Loại kỳ': 'Real-time',
                        'Năm': year,
                        'Ngày kỳ': today,
                        'Chỉ tiêu tiếng Việt': k,
                        'Giá trị': v,
                    })
        return pd.DataFrame(rows) if rows else pd.DataFrame(columns=STANDARD_COLUMNS)
    except Exception as e:
        print(f"⚠️ Daily index: {e}")
        return pd.DataFrame(columns=STANDARD_COLUMNS)

# ==============================================================================
# 16. SAVE CSV / PARQUET
# ==============================================================================
def save_output(df):
    if df is None or df.empty:
        print("⚠️ Không có dữ liệu để lưu.")
        return
    os.makedirs('data', exist_ok=True)
    df = final_clean_df(df)
    try:
        df.to_csv('data/finex_stock_master.csv', index=False, encoding='utf-8-sig')
        print(f"💾 CSV: data/finex_stock_master.csv ({len(df):,} dòng)")
    except Exception as e:
        print(f"❌ CSV: {e}")
    try:
        df.to_parquet('data/finex_stock_master.parquet', engine='pyarrow', index=False)
        print(f"💾 Parquet: data/finex_stock_master.parquet")
    except Exception as e:
        print(f"⚠️ Parquet: {e}")
    # Cleanup emergency
    for f in glob.glob('data/_emergency_backup.*'):
        try: os.remove(f)
        except Exception: pass

# ==============================================================================
# 17. COVERAGE REPORT
# ==============================================================================
def print_coverage(df):
    if df is None or df.empty: return
    print("\n📊 COVERAGE REPORT")
    print(f"   Tổng dòng: {len(df):,}")
    print(f"   Mã: {df['Mã chứng khoán'].nunique()}")
    print(f"   Nhãn: {df['Chỉ tiêu tiếng Việt'].nunique()}")
    by_type = df.groupby('Loại báo cáo').size().sort_values(ascending=False)
    for rt, cnt in by_type.items():
        print(f"   • {rt}: {cnt:,}")
    en = df[df['Chỉ tiêu tiếng Việt'].map(_looks_english)]
    if not en.empty:
        print(f"   ⚠️ CÒN {len(en)} nhãn English!")
    else:
        print("   ✅ Không có nhãn English.")

# ==============================================================================
# 18. MAIN
# ==============================================================================
def main():
    print("=" * 70)
    print("🚀 FINEX VN STOCK CRAWLER v19.0")
    print("=" * 70)
    t0 = time.time()

    master = load_176_master_tickers()
    print(f"📋 {len(master)} mã chứng khoán")

    all_records = []

    # 1) Supabase first (ưu tiên)
    print("\n📥 [1/5] Tải Supabase...")
    try:
        sb_df = load_data_from_supabase()
        if not sb_df.empty:
            all_records.append(sb_df)
            _ALL_RECORDS_GLOBAL.extend(sb_df.to_dict('records'))
    except Exception as e:
        print(f"⚠️ Supabase: {e}")

    # 2) Daily index
    print("\n📥 [2/5] Daily index...")
    try:
        di = fetch_daily_index()
        if not di.empty:
            all_records.append(di)
            _ALL_RECORDS_GLOBAL.extend(di.to_dict('records'))
    except Exception as e:
        print(f"⚠️ Daily: {e}")

    # 3) YFinance — song song
    print("\n📥 [3/5] YFinance (quý)...")
    yf_frames = []
    with ThreadPoolExecutor(max_workers=8) as ex:
        fut = {ex.submit(fetch_yfinance, t, 'quarterly'): t for t in master}
        for f in as_completed(fut, timeout=900):
            try:
                df = f.result()
                if not df.empty:
                    yf_frames.append(df)
                    _ALL_RECORDS_GLOBAL.extend(df.to_dict('records'))
            except Exception as e:
                print(f"   ⚠️ {fut[f]}: {e}")
    if yf_frames:
        combined = pd.concat(yf_frames, ignore_index=True)
        all_records.append(combined)
        print(f"   ✅ YF quý: {len(combined):,} dòng")

    print("\n📥 [3b/5] YFinance (năm)...")
    yf_annual = []
    with ThreadPoolExecutor(max_workers=8) as ex:
        fut = {ex.submit(fetch_yfinance, t, 'annual'): t for t in master}
        for f in as_completed(fut, timeout=600):
            try:
                df = f.result()
                if not df.empty:
                    yf_annual.append(df)
                    _ALL_RECORDS_GLOBAL.extend(df.to_dict('records'))
            except Exception:
                pass
    if yf_annual:
        combined = pd.concat(yf_annual, ignore_index=True)
        all_records.append(combined)
        print(f"   ✅ YF năm: {len(combined):,} dòng")

    # 4) YF market metrics
    print("\n📥 [4/5] YF market metrics...")
    yf_mkt = []
    with ThreadPoolExecutor(max_workers=8) as ex:
        fut = {ex.submit(fetch_yfinance_market, t): t for t in master}
        for f in as_completed(fut, timeout=600):
            try:
                df = f.result()
                if not df.empty:
                    yf_mkt.append(df)
                    _ALL_RECORDS_GLOBAL.extend(df.to_dict('records'))
            except Exception:
                pass
    if yf_mkt:
        combined = pd.concat(yf_mkt, ignore_index=True)
        all_records.append(combined)
        print(f"   ✅ YF market: {len(combined):,} dòng")

    # 5) VNFinancial (optional)
    if vnf is not None:
        print("\n📥 [5/5] VNFinancial...")
        vnf_frames = []
        with ThreadPoolExecutor(max_workers=4) as ex:
            fut = {ex.submit(fetch_vnfinancial, t): t for t in master}
            for f in as_completed(fut, timeout=900):
                try:
                    df = f.result()
                    if not df.empty:
                        vnf_frames.append(df)
                        _ALL_RECORDS_GLOBAL.extend(df.to_dict('records'))
                except Exception:
                    pass
        if vnf_frames:
            combined = pd.concat(vnf_frames, ignore_index=True)
            all_records.append(combined)
            print(f"   ✅ VNF: {len(combined):,} dòng")

    # Gộp + FINAL CLEAN
    print("\n🔗 Gộp dữ liệu...")
    if all_records:
        df = pd.concat(all_records, ignore_index=True)
        df = final_clean_df(df)
    else:
        df = pd.DataFrame(columns=STANDARD_COLUMNS)

    if df.empty:
        print("⚠️ Không có dữ liệu sau khi gộp.")
        return

    # Save
    save_output(df)
    print_coverage(df)

    # Push Supabase
    if PUSH_TO_SUPABASE:
        print("\n📤 Push Supabase...")
        ok = upsert_to_supabase(df)
        if ok and PURGE_SUPABASE_BAD:
            purge_supabase_bad_rows()

    print(f"\n✅ HOÀN TẤT trong {time.time()-t0:.1f}s")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"❌ FATAL: {e}")
        import traceback
        traceback.print_exc()
        if _ALL_RECORDS_GLOBAL:
            try:
                _emergency_save(0, None)
            except Exception:
                pass
        sys.exit(1)
