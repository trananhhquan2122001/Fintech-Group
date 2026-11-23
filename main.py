"""
FINEX VN STOCK DATABASE CRAWLER - v23.1 (BẢN HỢP NHẤT: SẠCH TIẾNG ANH + CHUẨN ĐƠN VỊ + CHỈ SỐ DẪN XUẤT + SUPABASE BỀN VỮNG)
================================================================================
Changelog v23.1 (nâng cấp từ v23.0, giữ nguyên khung xử lý và từ điển):
  ✅ UNIVERSE: đồng bộ danh sách 132 mã người dùng cung cấp; kiểm tra số lượng và mã trùng ngay khi khởi tạo.
  ✅ GIỮ NGUYÊN v19.0: cổng dịch duy nhất force_vietnamese_label() 5 chốt
     (_accumulate, nguồn cào, Tầng 2, trước ghi file, trước upsert); fix_yfinance_typos
     an toàn; blacklist nhãn rác; purge Supabase; bóc [2]/(2); hết đuôi .0; lru_cache.
  ✅ 🆕 CHUẨN ĐƠN VỊ NGAY KHI CÀO (chặn giá 14 chữ số kiểu 36.166.511.658.185):
     norm_price (100 -> 5.000.000 VNĐ/cp), norm_shares (nguồn trả "triệu cp" -> x1e6,
     thang 1e6..5e11), norm_market_cap (nguồn trả "tỷ đồng" -> x1e9, lệch giá x SLCP
     >50% -> lấy giá x SLCP). Ngoài thang -> BỎ. Áp tại: fetch_market_and_valuation_metrics,
     fetch_vndirect_fallback, fetch_vps_fallback VÀ Tầng 1 cleaning (chặn cả dữ liệu cũ).
  ✅ 🆕 BƯỚC 6.5: compute_derived_valuation_metrics() dùng pandas pivot + numpy tính
     EPS, BVPS, ROE, ROA, biên ròng/gộp, P/E, P/B, vốn hoá cho từng (mã, kỳ, ngày kỳ);
     np.errstate chống chia 0; CHỈ sinh dòng khi mẫu số khác 0 -> hết cảnh P/E=0, ROE=0;
     dedup keep='last' nên chỉ số dẫn xuất ĐÈ lên giá trị 0/sai cũ.
  ✅ 🆕 SUPABASE BỀN VỮNG (chặn ConnectionTerminated error_code:0 / GOAWAY):
     batch khởi đầu 200 (tự chia nửa khi lỗi, min 25), payload <=600KB/request,
     retry 6 lần backoff+jitter, TỰ TẠO CLIENT MỚI khi lỗi mạng, đổi client mỗi 40
     batch thành công, nghỉ 0.35s/batch, ClientOptions(postgrest_client_timeout=90).
     Batch chết KHÔNG giết job (lần chạy sau upsert lại toàn bộ nên tự bù).
  ✅ 🆕 CỔNG VÀO CHẶN MỌI EXCEPTION -> workflow luôn exit 0; emergency backup nếu crash.
  ✅ CHỈ LƯU ĐÚNG 2 FILE: data/vietnam_stock_database_tong_hop.csv + .parquet
     (coverage report chỉ chạy khi env COVERAGE_REPORT=true).
  ✅ GIỮ NGUYÊN: SKIP_VNDIRECT=true, quý yfinance 8 luồng, bỏ ^UPCOM, 132 mã,
     BƯỚC 0->8, emergency save, dọn file tạm, purge Supabase dòng 0/rỗng/rác/Anh.
================================================================================
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
import json
import unicodedata
import traceback
from datetime import datetime
from functools import lru_cache
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd
import numpy as np
import requests
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
# 1. TỪ ĐIỂN KHUNG BÁO CÁO TÀI CHÍNH 4 NGÀNH (GIỮ NGUYÊN 100% + BỔ SUNG)
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

VAS_WHITELIST.update([
    "Chứng khoán đầu tư giữ đến ngày đáo hạn", "Chứng khoán đầu tư sẵn sàng để bán",
    "Thu nhập lãi và các khoản thu nhập tương tự", "Chi phí lãi và các chi phí tương tự",
    "Thu nhập từ hoạt động dịch vụ", "Chi phí hoạt động dịch vụ", "Lãi thuần từ hoạt động dịch vụ",
    "Lãi thuần từ hoạt động kinh doanh ngoại hối", "Lãi thuần từ mua bán chứng khoán kinh doanh",
    "Lãi thuần từ mua bán chứng khoán đầu tư", "Thu nhập từ hoạt động khác", "Chi phí hoạt động khác",
    "Lãi thuần từ hoạt động khác", "Tổng thu nhập hoạt động", "Dự phòng rủi ro tín dụng",
    "Chi phí bán hàng và quản lý doanh nghiệp", "Tổng chi phí", "Thu nhập lãi",
    "Lợi nhuận trước lãi vay và thuế", "Lợi nhuận trước lãi vay, thuế và khấu hao",
    "Dòng tiền tự do", "Số lượng cổ phiếu bình quân cơ bản", "Số lượng cổ phiếu bình quân pha loãng",
    "Số lượng cổ phiếu phổ thông", "Cổ phiếu đã phát hành", "Số lượng cổ phiếu ròng", "Tổng nợ vay",
    "Tổng lợi nhuận HĐKD như báo cáo", "Khấu hao được điều chỉnh", "Biến động vốn lưu động",
    "Lợi nhuận thuần chuẩn hóa", "Lợi nhuận sau thuế từ hoạt động tiếp tục",
    "Tiền thu từ đi vay dài hạn", "Tiền trả nợ gốc vay dài hạn", "Cho vay khách hàng thuần",
    "Thu nhập phí và hoa hồng", "Tài sản cố định hữu hình thuần", "Nguyên giá tài sản cố định hữu hình",
    "Hao mòn lũy kế tài sản cố định", "Lợi thế thương mại và tài sản vô hình", "Tài sản cố định vô hình khác",
    "Bất động sản khác", "Nhà cửa và vật kiến trúc", "Đất đai và cải tạo đất",
    "Máy móc, thiết bị và phương tiện vận tải", "Xây dựng cơ bản dở dang", "Tài sản quyền sử dụng đất và thuê tài chính",
    "Nguyên liệu, vật liệu tồn kho", "Chi phí sản xuất kinh doanh dở dang", "Thành phẩm tồn kho",
    "Tiền bị hạn chế", "Thuế phải thu", "Thuế phải thu ngắn hạn", "Thuế phải trả", "Thuế phải trả ngắn hạn",
    "Tổng thuế phải trả", "Cổ tức phải trả", "Phải trả khác", "Phải thu ngắn hạn khác", "Phải thu dài hạn khác",
    "Phải trả ngắn hạn khác", "Phải trả dài hạn khác", "Đầu tư ngắn hạn", "Đầu tư dài hạn",
    "Đầu tư vào liên doanh", "Đầu tư vào công ty liên kết", "Đầu tư vào liên doanh theo giá gốc",
    "Đầu tư vào công ty liên kết theo giá gốc", "Thuế thu nhập hoãn lại phải trả ngắn hạn",
    "Thuế thu nhập hoãn lại phải trả dài hạn", "Quỹ phúc lợi nhân viên ngắn hạn", "Quỹ phúc lợi nhân viên và hưu trí",
    "Tiền mặt, tương đương tiền và đầu tư ngắn hạn", "Các khoản thanh toán tiền mặt",
    "Các khoản thanh toán tiền mặt khác từ HĐKD", "Thanh toán cho người lao động",
    "Các khoản thu tiền mặt từ HĐKD", "Các khoản thu tiền mặt khác từ HĐKD",
    "Các khoản thanh toán tiền mặt khác từ HĐ đầu tư", "Các khoản thu tiền mặt khác từ HĐ đầu tư",
    "Các khoản thanh toán tiền mặt khác từ HĐ tài chính", "Các khoản thu tiền mặt khác từ HĐ tài chính",
    "Cổ tức đã nhận", "Thu từ thanh lý tài sản cố định", "Chi mua sắm tài sản cố định",
    "Tổng các khoản mục bất thường (Không gồm lợi thế thương mại)",
    "Lợi nhuận ròng pha loãng phân bổ cho CĐ phổ thông", "Lợi nhuận ròng phân bổ cho cổ đông phổ thông",
    "Tổng chi phí tài chính khác", "Thu nhập/chi phí lãi thuần ngoài HĐKD", "Thu nhập/chi phí khác",
    "Lợi nhuận ròng bất thường", "Lợi nhuận ròng từ hoạt động không liên tục", "Lợi nhuận ròng từ hoạt động liên tục",
    "Chi phí thu nhập đặc biệt", "Chi phí đặc biệt khác", "Xóa sổ", "Tổn thất tài sản và dự phòng",
    "Thuế thu nhập hoãn lại", "Biến động các khoản phải thu", "Biến động hàng tồn kho",
    "Biến động các khoản phải trả", "Biến động phải trả người bán", "Biến động vốn lưu động khác",
    "Chi phí đầu tư tài sản cố định (CapEx)", "Tiền mua hoặc thanh lý tài sản cố định",
    "Tiền mua hoặc bán tài sản vô hình", "Tiền đầu tư góp vốn thuần", "Tiền mua bán công ty con hoặc sáp nhập",
    "Tiền thu từ phát hành nợ vay", "Tiền chi trả nợ gốc vay", "Tiền thu từ phát hành cổ phiếu hoặc bán cổ phiếu quỹ",
    "Cổ tức đã chi trả cho chủ sở hữu", "Ảnh hưởng thay đổi tỷ giá và tiền thuần thay đổi",
    "Lãi / Lỗ từ bán chứng khoán", "Cổ tức cổ phiếu ưu đãi và điều chỉnh khác",
    "Ảnh hưởng thuế từ các khoản mục bất thường", "Thuế suất dùng để tính toán",
    "Lãi / Lỗ từ đánh giá hoặc thanh lý tài sản", "Ảnh hưởng thay đổi tỷ giá hối đoái",
    "Lợi nhuận ròng từ HĐKD liên tục trừ lợi ích CĐ không kiểm soát",
    "Lợi nhuận thuần từ hoạt động tiếp tục và không tiếp tục", "Lợi nhuận sau thuế bao gồm lợi ích cổ đông không kiểm soát",
    "Tổng vốn chủ sở hữu gồm cổ đông không kiểm soát", "Vốn lưu động ròng", "Nợ vay ròng",
    "Chênh lệch đánh giá lại tài sản và chênh lệch tỷ giá", "Các khoản phải trả", "Các khoản phải thu",
    "Phải thu các bên liên quan ngắn hạn", "Tổng tài sản dài hạn", "Tổng nợ phải trả",
    "Lãi / Lỗ chênh lệch tỷ giá hối đoái thuần", "Lãi/lỗ từ chứng khoán đầu tư",
    "Tiền thu từ đi vay dài hạn (thuần)", "Tiền trả nợ gốc vay dài hạn (thuần)",
    "Tiền thu từ đi vay ngắn hạn", "Tiền trả nợ gốc vay ngắn hạn", "Tiền lãi vay đã trả (HĐTC)",
    "Tiền lãi nhận được (HĐĐT)", "Tiền lãi nhận được (HĐKD)", "Thuế TNDN đã nộp (thực nộp)",
    "Thuế được hoàn lại", "Biến động chi phí trả trước", "Các khoản mục phi tiền mặt khác",
    "Tài sản khác", "Nợ phải trả khác",
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
    "Doanh thu thuần HĐKD": "Doanh thu thuần", "Lợi nhuận sau thuế thu nhập doanh nghiệp": "Lợi nhuận sau thuế TNDN", "LNST": "Lợi nhuận sau thuế TNDN",
    "Vốn CSH": "Vốn chủ sở hữu", "Nợ phải trả ngắn hạn": "Nợ ngắn hạn", "Nợ phải trả dài hạn": "Nợ dài hạn", "Lợi nhuận gộp về bán hàng và cung cấp dịch vụ": "Lợi nhuận gộp",
    "Net Interest Income": "Thu nhập lãi thuần", "Gross Loan": "Cho vay khách hàng", "Customer Deposits": "Tiền gửi của khách hàng",
    "Trading Securities": "Chứng khoán kinh doanh", "Held To Maturity Securities": "Chứng khoán đầu tư giữ đến ngày đáo hạn"
}

ALIAS_TO_VAS.update({
    "Depreciation": "Khấu hao TSCĐ và BĐSĐT",
    "Reconciled Depreciation": "Khấu hao TSCĐ và BĐSĐT",
    "Reconciled Cost Of Revenue": "Giá vốn hàng bán",
    "Cost Of Goods Sold": "Giá vốn hàng bán",
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
    "Other Assets": "Tài sản khác",
    "Other Liabilities": "Nợ phải trả khác",
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
    "other assets": "Tài sản khác",
    "other liabilities": "Nợ phải trả khác",
})

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
    if s in TRANSLATION_MAP:
        return TRANSLATION_MAP[s]
    if low in _TRANS_LOWER:
        return _TRANS_LOWER[low]
    fixed = fix_truncated_text(s)
    if fixed != s:
        for cand in (fixed, fixed.lower()):
            if cand in VAS_WHITELIST: return fixed
            if cand in _WHITELIST_LOWER: return _WHITELIST_LOWER[cand]
            if cand in ALIAS_TO_VAS: return ALIAS_TO_VAS[cand]
            if cand in _ALIAS_LOWER: return _ALIAS_LOWER[cand]
            if cand in TRANSLATION_MAP: return TRANSLATION_MAP[cand]
            if cand in _TRANS_LOWER: return _TRANS_LOWER[cand]
        s = fixed
        low = s.lower()
    if _looks_english(s):
        t = translate_metric(s)
        if t is None or is_junk_label(t):
            return None
        for cand in (t, t.lower()):
            if cand in VAS_WHITELIST: return t
            if cand in _WHITELIST_LOWER: return _WHITELIST_LOWER[cand]
            if cand in ALIAS_TO_VAS: return ALIAS_TO_VAS[cand]
            if cand in _ALIAS_LOWER: return _ALIAS_LOWER[cand]
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

def force_vietnamese_label(metric, report_type):
    """🆕 v19/v22: CỔNG DỊCH DUY NHẤT — mọi nhãn đi qua đây đều phải là tiếng Việt."""
    std = standardize_metric(metric, report_type)
    if std is None or is_junk_label(std):
        return None
    if _looks_english(std):
        t = translate_metric(std)
        if t is None or is_junk_label(t) or _looks_english(t):
            return None
        std = t
    return std

def sweep_labels(df, label_col='Chỉ tiêu tiếng Việt', type_col='Loại báo cáo'):
    if df is None or df.empty:
        return df, 0
    before = len(df)
    df = df.copy()
    df[label_col] = [force_vietnamese_label(m, rt) for m, rt in zip(df[label_col], df[type_col])]
    df = df.dropna(subset=[label_col])
    df = df[df[label_col].astype(str).str.strip().ne('')]
    return df, before - len(df)

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

# ==========================================
# 1.5 SUPABASE INTEGRATION (GIỮ KHUNG + 🆕 v22 ENGINE BỀN VỮNG)
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
PURGE_SUPABASE_BAD = os.environ.get("PURGE_SUPABASE_BAD", "true").strip().lower() in ("1", "true", "yes", "y")
SKIP_VNDIRECT = os.environ.get("SKIP_VNDIRECT", "false").strip().lower() in ("1", "true", "yes", "y")
COVERAGE_REPORT = os.environ.get("COVERAGE_REPORT", "false").strip().lower() in ("1", "true", "yes", "y")

# 🆕 v22: tham số engine upsert chống ConnectionTerminated / GOAWAY HTTP2
UPSERT_BATCH_START = int(os.environ.get("UPSERT_BATCH_START", "200"))
UPSERT_BATCH_MIN = 25
UPSERT_MAX_ATTEMPTS = 6
UPSERT_BATCH_PAUSE = 0.35
UPSERT_MAX_PAYLOAD_BYTES = 600_000
UPSERT_CLIENT_REFRESH_EVERY = 40

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

# 🆕 v22: quản lý client tập trung — tạo lại khi dính lỗi mạng
_SUPABASE_STATE = {'client': None}

def init_supabase(force_new=False):
    if not force_new and _SUPABASE_STATE['client'] is not None:
        return _SUPABASE_STATE['client']
    if not HAS_SUPABASE_LIB:
        print("⚠️ [SUPABASE] Thiếu thư viện supabase.")
        return None
    if not SUPABASE_URL or not SUPABASE_KEY:
        print("⚠️ [SUPABASE] Thiếu URL / KEY.")
        return None
    try:
        try:
            from supabase import create_client as _cc, ClientOptions
            opts = None
            try:
                opts = ClientOptions(postgrest_client_timeout=90)
            except Exception:
                opts = None
            _SUPABASE_STATE['client'] = _cc(SUPABASE_URL, SUPABASE_KEY, options=opts) if opts else _cc(SUPABASE_URL, SUPABASE_KEY)
        except Exception:
            from supabase import create_client as _cc
            _SUPABASE_STATE['client'] = _cc(SUPABASE_URL, SUPABASE_KEY)
        print("✅ [SUPABASE] Đã kết nối (client mới).")
        return _SUPABASE_STATE['client']
    except Exception as e:
        print(f"❌ [SUPABASE] Lỗi kết nối: {e}")
        return None

_NETWORK_KEYS = ('connectionterminated', 'connection', 'timeout', 'timed out', 'reset',
                 'broken pipe', 'goaway', 'go away', 'server disconnected', 'protocolerror',
                 'remoteprotocolerror', 'streamid', 'eof', 'closed')

def _is_network_err(e):
    if type(e).__name__ in ('ConnectionTerminated', 'ConnectionError', 'ConnectError', 'ReadError',
                            'WriteError', 'RemoteProtocolError', 'ProtocolError', 'ReadTimeout',
                            'ConnectTimeout', 'PoolTimeout', 'TimeoutException', 'OSError', 'IOError'):
        return True
    s = str(e).lower()
    return any(k in s for k in _NETWORK_KEYS)

def _retry(fn, max_retries=3, backoff=2, label="SUPABASE", refresh_client=False):
    last_err = None
    for attempt in range(max_retries):
        try:
            return fn()
        except Exception as e:
            last_err = e
            if refresh_client and _is_network_err(e):
                init_supabase(force_new=True)
            if attempt == max_retries - 1: break
            print(f"⚠️ [{label}] Lỗi lần {attempt+1} ({type(e).__name__}), thử lại sau {backoff**attempt}s...")
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
            resp = _retry(lambda s=start: client.table(SUPABASE_TABLE).select("*").range(s, s + page_size - 1).execute(),
                          max_retries=3, label="SUPABASE_SELECT", refresh_client=True)
            batch = resp.data or []
            rows.extend(batch)
            if len(batch) < page_size: break
            start += page_size
        return rows
    try:
        all_rows = _retry(_fetch_all, label="SUPABASE", refresh_client=True)
        if not all_rows: return pd.DataFrame(columns=STANDARD_COLUMNS)
        df = pd.DataFrame(all_rows).rename(columns=EN_TO_VN_MAP)
        df = _normalize_to_standard(df, fill_company=False)

        before = len(df)
        df['Giá trị'] = pd.to_numeric(df['Giá trị'], errors='coerce')
        df = df.dropna(subset=['Mã chứng khoán', 'Chỉ tiêu tiếng Việt', 'Giá trị'])
        df = df[df['Giá trị'] != 0]
        df['Mã chứng khoán'] = df['Mã chứng khoán'].astype(str).str.strip().str.upper()
        df = df[~df['Mã chứng khoán'].isin(['', 'NAN', 'NONE', 'NULL'])]
        df['Loại báo cáo'] = df['Loại báo cáo'].map(lambda x: TRANSLATION_MAP.get(clean_text(x), clean_text(x)))
        _ky_map = {'quarter': 'Quý', 'quarterly': 'Quý', 'year': 'Năm', 'annual': 'Năm'}
        df['Loại kỳ'] = df['Loại kỳ'].map(lambda x: _ky_map.get(str(x).strip().lower(), x))
        df, n_drop = sweep_labels(df)
        print(f"✅ [SUPABASE] Đã tải {len(df):,} dòng (🧹 lọc bỏ {before - len(df):,} dòng bẩn/Anh/rác).")
        return df
    except Exception as e:
        print(f"❌ [SUPABASE] Lỗi tải: {type(e).__name__}: {e}")
        return pd.DataFrame(columns=STANDARD_COLUMNS)

# 🆕 v22: helpers payload upsert
def _est_bytes(records):
    try:
        return len(json.dumps(records, ensure_ascii=False).encode('utf-8'))
    except Exception:
        return len(records) * 300

def _split_by_size(records, max_bytes):
    if _est_bytes(records) <= max_bytes: return [records]
    out = []
    def rec(chunk):
        if len(chunk) <= 1 or _est_bytes(chunk) <= max_bytes:
            out.append(chunk); return
        mid = len(chunk) // 2
        rec(chunk[:mid]); rec(chunk[mid:])
    rec(records)
    return out

def upsert_to_supabase(df, batch_size=UPSERT_BATCH_START):
    """🆕 v22: upsert bền vững — batch nhỏ, chia theo size, retry + đổi client, KHÔNG fail job."""
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
        skipped_bad = 0
        for row in payload.to_dict('records'):
            ticker = str(row['ticker']).strip() if pd.notna(row['ticker']) else ''
            if not ticker: continue

            val = pd.to_numeric(row['value'], errors='coerce')
            if pd.isna(val) or val == 0: continue

            item = force_vietnamese_label(row['item_vn'], row['report_type'])
            if not item:
                skipped_bad += 1
                continue

            yr = pd.to_numeric(row['year'], errors='coerce')
            if pd.isna(yr):
                m = re.match(r'(\d{4})', str(row['report_date'] or ''))
                yr = int(m.group(1)) if m else datetime.now().year
            yr = int(yr)

            def clean_str(s):
                if pd.isna(s): return None
                s = str(s).strip()
                return s if s else None

            records.append({
                'ticker': ticker,
                'company_name': clean_str(row['company_name']),
                'sector': clean_str(row['sector']),
                'report_type': clean_str(row['report_type']),
                'period_type': clean_str(row['period_type']),
                'year': yr,
                'report_date': clean_str(row['report_date']),
                'item_vn': item,
                'value': float(val)
            })

        total = len(records)
        if skipped_bad:
            print(f"🧹 [SUPABASE] Chặn {skipped_bad:,} dòng rác/trống/Anh trước khi upsert.")
        if total == 0:
            print("⚠️ [SUPABASE] Không có bản ghi hợp lệ sau khi làm sạch.")
            return False

        chunks = []
        for i in range(0, total, batch_size):
            chunks.extend(_split_by_size(records[i:i+batch_size], UPSERT_MAX_PAYLOAD_BYTES))
        done_rows = 0; ok_batches = 0; failed_rows = 0
        print(f"📤 [SUPABASE] Upsert {total:,} bản ghi trong {len(chunks)} batch (≤{UPSERT_MAX_PAYLOAD_BYTES//1000}KB/batch)...")

        qi = 0
        while qi < len(chunks):
            chunk = chunks[qi]; qi += 1
            attempt = 0
            while True:
                try:
                    if SUPABASE_ON_CONFLICT:
                        client.table(SUPABASE_TABLE).upsert(chunk, on_conflict=SUPABASE_ON_CONFLICT).execute()
                    else:
                        client.table(SUPABASE_TABLE).upsert(chunk).execute()
                    ok_batches += 1; done_rows += len(chunk)
                    if ok_batches % 10 == 0 or done_rows == total:
                        print(f"   ✓ {done_rows:,}/{total:,} (batch {len(chunk)})")
                    if ok_batches % UPSERT_CLIENT_REFRESH_EVERY == 0:
                        client = init_supabase(force_new=True)
                    time.sleep(UPSERT_BATCH_PAUSE)
                    break
                except Exception as e:
                    attempt += 1
                    ename = type(e).__name__
                    if attempt > UPSERT_MAX_ATTEMPTS:
                        print(f"  ❌ Batch {len(chunk)} bản ghi lỗi vĩnh viễn: {ename}: {e} (sẽ đẩy lại lần chạy sau)")
                        failed_rows += len(chunk)
                        break
                    if _is_network_err(e):
                        client = init_supabase(force_new=True)
                    sl = str(e).lower()
                    if len(chunk) > UPSERT_BATCH_MIN and (_is_network_err(e) or '413' in sl or 'payload' in sl or 'too large' in sl):
                        mid = len(chunk) // 2
                        chunks.insert(qi, chunk[mid:])
                        chunk = chunk[:mid]
                        print(f"  ↘️ Chia nhỏ batch còn {len(chunk)} bản ghi (lỗi {ename})")
                        continue
                    wait = min(2 ** attempt, 30) + random.uniform(0, 1.5)
                    print(f"  ⚠️ Batch lỗi lần {attempt}/{UPSERT_MAX_ATTEMPTS} ({ename}): thử lại sau {wait:.1f}s")
                    time.sleep(wait)

        print(f"✅ [SUPABASE] Upsert xong {done_rows:,}/{total:,} bản ghi; chưa đẩy được: {failed_rows:,}")
        return done_rows > 0
    except Exception as e:
        print(f"❌ [SUPABASE] Lỗi upsert tổng: {type(e).__name__}: {e}")
        return False

def purge_supabase_bad_rows():
    client = init_supabase()
    if client is None: return
    print("🧽 [SUPABASE] Purge dòng bẩn: value=0/NULL, item_vn rỗng/NULL, nhãn rác, nhãn Anh, nhãn [n]...")
    T = SUPABASE_TABLE

    def _run(label, fn):
        try:
            resp = _retry(fn, max_retries=2, backoff=2, label="SUPABASE_PURGE", refresh_client=True)
            n = len(getattr(resp, 'data', None) or [])
            print(f"   ✓ {label}: xoá {n:,} dòng")
        except Exception as e:
            print(f"   ⚠️ {label}: {type(e).__name__}: {e}")

    _run("value = 0",        lambda: client.table(T).delete().eq('value', 0).execute())
    _run("value NULL",       lambda: client.table(T).delete().is_('value', 'null').execute())
    _run("item_vn NULL",     lambda: client.table(T).delete().is_('item_vn', 'null').execute())
    _run("item_vn rỗng",     lambda: client.table(T).delete().eq('item_vn', '').execute())
    junk_variants = sorted({j for j in JUNK_EXACT if j} | {j.capitalize() for j in JUNK_EXACT if j} | {j.title() for j in JUNK_EXACT if j})
    _run("nhãn rác (Của...)", lambda: client.table(T).delete().in_('item_vn', junk_variants).execute())
    _run("nhãn 'chưa xác định'", lambda: client.table(T).delete().like('item_vn', '%chưa xác định%').execute())
    _run("nhãn dính [n]",    lambda: client.table(T).delete().like('item_vn', '%[%]').execute())
    en = sorted(_ENGLISH_PURGE)
    for i in range(0, len(en), 40):
        chunk = en[i:i+40]
        _run(f"nhãn tiếng Anh đợt {i//40+1}", lambda c=chunk: client.table(T).delete().in_('item_vn', c).execute())
    print("✅ [SUPABASE] Purge hoàn tất.")

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
# 3. DANH SÁCH 132 MÃ & THÔNG TIN DOANH NGHIỆP (GIỮ NGUYÊN 100%)
# ==========================================
def load_132_master_tickers():
    # Universe follows the user's curated 132-symbol HOSE list.
    # Keep known HNX classifications only for any symbol still in the universe.
    hnx_tickers = {
        'BVS','CEO','DTD','DXP','HGM','HUT','IDC','KSF','L14','L18','LAS','MBS',
        'NBC','NDN','NET','NTP','PLC','PVB','PVC','PVI','PVS','SHS','SLS','THD',
        'TIG','TMB','TNG','TVD','VCS','VC3','VGS','DHT','DDV','HMS'
    }
    raw_tickers = [
        'ACB','AGR','ANV','BAF','BCM','BFC','BID','BMI','BMP','BSI',
        'BSR','BVH','BWE','CAP','CII','CMG','CTD','CTG','CTI','CTR',
        'CTS','DBC','DCM','DGC','DGW','DHC','DIG','DP3','DPM','DPR',
        'DSE','DTP','DXG','EIB','EVF','FPT','FRT','FTS','GAS','GEE',
        'GEX','GMD','GVR','HAG','HCM','HDB','HDC','HDG','HHV','HPG',
        'HPP','HSG','HT1','HVN','IJC','KBC','KDC','KDH','LHC','LPB',
        'LSS','MBB','MCH','MSB','MSN','MWG','NAB','NKG','NLG','NT2',
        'NVL','OCB','PAN','PAT','PC1','PDR','PET','PHR','PLX','POW',
        'PSD','PVD','PVT','REE','SAB','SBA','SBT','SCL','SGP','SHB',
        'SIP','SJD','SJS','SSB','SSI','STB','SZC','TAL','TCB','TCH',
        'TCM','TCX','TDC','TDM','TMP','TPB','TTA','TV2','VCB','VCG',
        'VCI','VCK','VCP','VFS','VGC','VGP','VHC','VHM','VIB','VIC',
        'VIX','VJC','VND','VNM','VPB','VPI','VPL','VPX','VRE','VSC',
        'VSH','VTP',
    ]
    if len(raw_tickers) != 132 or len(set(raw_tickers)) != 132:
        raise ValueError(f"Danh sách mã phải có đúng 132 mã duy nhất, hiện có {len(raw_tickers)} mã / {len(set(raw_tickers))} mã duy nhất.")
    return {t.strip().upper(): ("HNX" if t.strip().upper() in hnx_tickers else "HOSE_OR_OTHER")
            for t in raw_tickers if t.strip()}

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
# 4. TRANSLATION MAP (GIỮ NGUYÊN 100% + BỔ SUNG ~170 KEY)
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

TRANSLATION_MAP.update({
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
})

# ==========================================
# 4.5 BẢNG TRA LOWERCASE DỰNG 1 LẦN (TỐI ƯU TỐC ĐỘ)
# ==========================================
_WHITELIST_LOWER = {v.lower(): v for v in VAS_WHITELIST}
_ALIAS_LOWER = {k.lower(): v for k, v in ALIAS_TO_VAS.items()}
_TRANS_LOWER = {k.lower(): v for k, v in TRANSLATION_MAP.items()}

_EXTRA_ENGLISH_LABELS = [
    'Depreciation And Amortization', 'Depreciation', 'Gain Loss On Investment Securities',
    'Net Foreign Currency Exchange Gain', 'Net Income From Continuing Operation Net Minority Interest',
    'Free Cash Flow', 'Repayment Of Debt', 'End Cash Position', 'Beginning Cash Position',
    'Changes In Cash', 'Financing Cash Flow', 'Net Issuance Payments Of Debt',
    'Net Long Term Debt Issuance', 'Long Term Debt Payments', 'Long Term Debt Issuance',
    'Investing Cash Flow', 'Interest Received Cfi', 'Operating Cash Flow', 'Taxes Refund Paid',
    'Interest Paid Cfo', 'Change In Working Capital', 'Change In Payable', 'Change In Prepaid Assets',
    'Change In Inventory', 'Change In Receivables', 'Other Non Cash Items', 'Gross Profit',
    'Cost Of Revenue', 'Total Revenue', 'Operating Revenue', 'Diluted Average Shares',
    'Basic Average Shares', 'Diluted EPS', 'Basic EPS', 'Selling General And Administration',
    'General And Administrative Expense', 'Tax Rate For Calcs', 'Normalized EBITDA',
    'Reconciled Depreciation', 'Reconciled Cost Of Revenue', 'EBITDA', 'EBIT',
    'Net Interest Income', 'Interest Expense', 'Interest Income', 'Normalized Income',
    'Total Expenses', 'Total Operating Income As Reported',
    'Net Income From Continuing And Discontinued Operation', 'Other assets',
]
_ENGLISH_PURGE = {k for k in list(TRANSLATION_MAP.keys()) + list(ALIAS_TO_VAS.keys())
                  if k.isascii() and re.search(r'[A-Za-z]', k)} | set(_EXTRA_ENGLISH_LABELS)

# ==========================================
# 5. LÀM SẠCH CHUYÊN SÂU (GIỮ NGUYÊN + VÁ)
# ==========================================
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
    r = round(val, 4)
    if r == int(r) and abs(r) < 9.007e15:
        return int(r)
    return r

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
    'Tiền và các khoản tương đương tiền': 'Tiền và các khoản tương đương tiền',
}

def fix_truncated_text(text):
    t = clean_text(text)
    return _TRUNCATED_FIX.get(t, t)

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
    text = re.sub(r'(?<=[a-z])(?=[A-Z])', ' ', text)
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
FALLBACK_MAP.update({
    'issuance':'phát hành','repayment':'trả nợ','refund':'hoàn lại','paid':'đã trả','received':'đã nhận',
    'cfi':'HĐĐT','cfo':'HĐKD','cff':'HĐTC','prepaid':'trả trước','payables':'phải trả','receivables':'phải thu',
    'continuing':'tiếp tục','discontinued':'không tiếp tục','discontinuous':'không tiếp tục','normalized':'chuẩn hóa',
    'reconciled':'điều chỉnh','unusual':'bất thường','impairment':'tổn thất','amortization':'phân bổ',
    'depletion':'khấu hao tài nguyên','securities':'chứng khoán','investment':'đầu tư','exchange':'tỷ giá',
    'foreign':'ngoại tệ','currency':'tiền tệ','gain':'lãi','loss':'lỗ','gains':'lãi','losses':'lỗ',
    'debt':'nợ vay','loan':'khoản vay','loans':'khoản vay','borrowings':'khoản vay','obligation':'nghĩa vụ',
    'obligations':'nghĩa vụ','stock':'cổ phiếu','shares':'cổ phiếu','average':'bình quân','diluted':'pha loãng',
    'basic':'cơ bản','eps':'EPS','dividend':'cổ tức','tax':'thuế','provision':'dự phòng','working':'lưu động',
    'change':'biến động','changes':'biến động','position':'số dư','beginning':'đầu kỳ','end':'cuối kỳ',
    'free':'tự do','flow':'lưu chuyển','flows':'lưu chuyển','statement':'báo cáo','balance':'cân đối',
    'sheet':'kế toán','expenses':'chi phí','accrued':'phải trả','restricted':'bị hạn chế','financial':'tài chính',
    'trading':'kinh doanh','held':'nắm giữ','maturity':'đáo hạn','available':'sẵn sàng','sale':'bán',
    'customer':'khách hàng','deposits':'tiền gửi','bank':'ngân hàng','fees':'phí','commissions':'hoa hồng',
    'fee':'phí','commission':'hoa hồng','compensation':'thù lao','wages':'lương','salaries':'lương',
    'rent':'thuê','insurance':'bảo hiểm','claims':'bồi thường','restructuring':'tái cấu trúc',
    'mergers':'sáp nhập','acquisition':'mua lại','business':'công ty con','purchase':'mua',
    'write':'xóa','off':'sổ','allowance':'dự phòng','doubtful':'khó đòi','related':'liên quan',
    'parties':'bên','due':'phải thu','notes':'giấy nợ','note':'giấy nợ','line':'hạn mức','credit':'tín dụng',
    'commercial':'thương mại','paper':'phiếu','hedging':'phòng ngừa rủi ro','derivative':'phái sinh',
    'employee':'nhân viên','benefits':'phúc lợi','treasury':'quỹ','preferred':'ưu đãi','common':'phổ thông',
    'additional':'bổ sung','translation':'quy đổi','adjustments':'điều chỉnh','adjustment':'điều chỉnh',
    'revaluation':'đánh giá lại','reserve':'quỹ','minimum':'tối thiểu','capitalization':'vốn hóa',
    'book':'sổ sách','value':'giá trị','invested':'đầu tư','outside':'ngoài',
    'money':'tiền','market':'thị trường','federal':'liên bang','funds':'quỹ','purchased':'mua',
    'sold':'bán','under':'theo','agreements':'hợp đồng','repurchase':'mua lại','land':'đất',
    'machinery':'máy móc','furniture':'nội thất','construction':'xây dựng','progress':'dở dang',
    'raw':'nguyên','materials':'vật liệu','work':'dở dang','process':'dở dang','finished':'thành phẩm',
    'goods':'hàng hóa','inventories':'hàng tồn kho','allowances':'dự phòng','leasing':'thuê',
    'supplemental':'bổ sung','data':'số liệu','effect':'ảnh hưởng','rate':'tỷ giá','unrealized':'chưa thực hiện',
    'realized':'đã thực hiện','attributable':'phân bổ','stockholders':'cổ đông',
    'noncontrolling':'không kiểm soát','interests':'lợi ích','including':'bao gồm','extraordinary':'bất thường',
    'special':'đặc biệt','charges':'chi phí','charge':'chi phí',
})

_VN_DIACRITIC_RE = re.compile(r'[àáảãạăắằẳẵặâấầẩẫậèéẻẽẹêếềểễệìíỉĩịòóỏõọôốồổỗộơớờởỡợùúủũụưứừửữựỳýỷỹỵđ]')
_ALLOWED_ASCII_VN = {'EBIT', 'EBITDA', 'FVTPL', 'HTM', 'AFS', 'EPS', 'ROE', 'ROA', 'FCF', 'VND', 'CIR',
                     'CTCK', 'NHNN', 'TKV', 'TNDN', 'GTGT', 'TMCP', 'CTCP', 'VN', 'HNX', 'HOSE', 'UPCOM'}

def translate_metric(metric_original, is_vn=False):
    cleaned_key = _norm_key(clean_text(metric_original))
    if not cleaned_key:
        return None
    if cleaned_key in TRANSLATION_MAP:
        return TRANSLATION_MAP[cleaned_key]
    low = cleaned_key.lower()
    if low in _TRANS_LOWER:
        return _TRANS_LOWER[low]
    if is_vn or _VN_DIACRITIC_RE.search(low):
        cleaned_key = re.sub(r'\bM\b', 'Lợi ích cổ đông không kiểm soát', cleaned_key)
        cleaned_key = re.sub(r'\bN s\b', 'Số lượng cổ phiếu ròng', cleaned_key)
        cleaned_key = cleaned_key.replace('f giá gốc', 'phí giá gốc')
        return None if is_junk_label(cleaned_key) else cleaned_key

    fixed_key = fix_yfinance_typos(cleaned_key)
    if fixed_key in TRANSLATION_MAP:
        return TRANSLATION_MAP[fixed_key]
    if fixed_key.lower() in _TRANS_LOWER:
        return _TRANS_LOWER[fixed_key.lower()]

    k = fixed_key.lower()
    if 'net interest income' in k: return 'Thu nhập lãi thuần'
    if 'interest expense' in k: return 'Chi phí lãi vay'
    if 'interest income' in k: return 'Thu nhập lãi'
    if 'interest' in k and 'paid' in k: return 'Tiền lãi vay đã trả'
    if 'interest' in k and 'received' in k: return 'Tiền lãi nhận được'
    if 'net income' in k and 'minority' in k: return 'LNST của công ty mẹ'
    if 'net income' in k and 'continuing' in k and 'discontinu' in k: return 'Lợi nhuận sau thuế TNDN'
    if 'net income' in k and 'continuing' in k: return 'Lợi nhuận sau thuế từ hoạt động tiếp tục'
    if 'net income' in k and 'discontinu' in k: return 'Lợi nhuận ròng từ hoạt động không liên tục'
    if 'net income' in k or 'net profit' in k: return 'Lợi nhuận sau thuế TNDN'
    if 'ebitda' in k: return 'Lợi nhuận trước lãi vay, thuế và khấu hao (EBITDA)'
    if re.search(r'\bebit\b', k): return 'Lợi nhuận trước lãi vay và thuế (EBIT)'
    if 'pretax' in k or 'before tax' in k: return 'Tổng lợi nhuận kế toán trước thuế'
    if 'gross profit' in k: return 'Lợi nhuận gộp'
    if 'operating income' in k or 'operating profit' in k: return 'Lợi nhuận thuần từ hoạt động kinh doanh'
    if 'cost of' in k or 'cogs' in k: return 'Giá vốn hàng bán'
    if 'revenue' in k or 'sales' in k: return 'Doanh thu thuần'
    if 'tax provision' in k or 'tax expense' in k or 'income tax' in k: return 'Chi phí thuế thu nhập doanh nghiệp'
    if 'taxes refund' in k or 'tax refund' in k: return 'Thuế được hoàn lại'
    if 'depreciation' in k or 'amortization' in k or 'depletion' in k: return 'Khấu hao TSCĐ và BĐSĐT'
    if 'gain' in k and 'loss' in k and ('securit' in k or 'investment' in k): return 'Lãi/lỗ từ chứng khoán đầu tư'
    if 'gain' in k and 'loss' in k: return 'Lãi / Lỗ từ đánh giá hoặc thanh lý tài sản'
    if 'exchange' in k or 'foreign currency' in k: return 'Lãi / Lỗ chênh lệch tỷ giá hối đoái thuần'
    if 'repayment of debt' in k or 'debt payments' in k: return 'Tiền trả nợ gốc vay'
    if 'issuance of debt' in k or 'debt issuance' in k: return 'Tiền thu từ đi vay'
    if 'dividend' in k and ('paid' in k or 'payable' in k): return 'Cổ tức, lợi nhuận đã trả cho chủ sở hữu'
    if 'dividend' in k and 'received' in k: return 'Cổ tức đã nhận'
    if 'dividend' in k: return 'Cổ tức'
    if 'cash flow' in k and 'operating' in k: return 'Lưu chuyển tiền thuần từ HĐKD'
    if 'cash flow' in k and 'investing' in k: return 'Lưu chuyển tiền thuần từ HĐĐT'
    if 'cash flow' in k and 'financing' in k: return 'Lưu chuyển tiền thuần từ HĐTC'
    if 'cash flow' in k or 'free cash flow' in k: return 'Lưu chuyển tiền thuần'
    if 'beginning cash' in k: return 'Tiền và tương đương tiền đầu kỳ'
    if 'end cash' in k: return 'Tiền và tương đương tiền cuối kỳ'
    if 'changes in cash' in k: return 'Lưu chuyển tiền thuần trong kỳ'
    if 'working capital' in k: return 'Biến động vốn lưu động'
    if 'change in' in k and 'inventor' in k: return 'Tăng/giảm hàng tồn kho'
    if 'change in' in k and 'receivable' in k: return 'Tăng/giảm các khoản phải thu'
    if 'change in' in k and ('payable' in k or 'accrued' in k): return 'Tăng/giảm các khoản phải trả'
    if 'change in' in k and 'prepaid' in k: return 'Tăng/giảm chi phí trả trước'
    if 'non cash items' in k: return 'Các khoản mục phi tiền mặt khác'
    if 'shares' in k and ('average' in k or 'diluted' in k or 'basic' in k): return 'Số lượng cổ phiếu bình quân'
    if 'eps' in k: return 'Lãi cơ bản trên cổ phiếu'
    if 'other' in k and 'assets' in k: return 'Tài sản khác'
    if 'other' in k and 'liabilities' in k: return 'Nợ phải trả khác'

    words = fixed_key.split()
    translated_words = []
    n_translated = 0
    for w in words:
        if _VN_DIACRITIC_RE.search(w.lower()):
            translated_words.append(w); n_translated += 1; continue
        w_clean = re.sub(r'[^a-zA-Z]', '', w).lower()
        if w_clean in FALLBACK_MAP:
            translated_words.append(FALLBACK_MAP[w_clean]); n_translated += 1
        elif w.isupper() and len(w) <= 5 and w in _ALLOWED_ASCII_VN:
            translated_words.append(w)
    result = " ".join(translated_words)
    result = re.sub(r'\s{2,}', ' ', result).strip()
    if n_translated < 2 or len(result) < 4:
        return None
    if is_junk_label(result):
        return None
    if result.isascii() and result.upper() not in _ALLOWED_ASCII_VN:
        return None
    return result.capitalize()

# ==========================================
# 5.5 🆕 v23.1: CHUẨN HOÁ ĐƠN VỊ NGAY KHI CÀO (chặn giá/vốn hoá/SLCP sai thang)
# ==========================================
PRICE_MIN, PRICE_MAX = 100.0, 5_000_000.0        # VNĐ/cổ phiếu
SHARES_MIN, SHARES_MAX = 1_000_000.0, 5e11      # số cổ phiếu
MCAP_MIN, MCAP_MAX = 1e9, 5e16                  # VNĐ

def norm_price(v):
    fv = format_value(v)
    if fv is None: return None
    fv = float(fv)
    if not (PRICE_MIN <= fv <= PRICE_MAX): return None
    return int(fv) if fv == int(fv) else round(fv, 2)

def norm_shares(v):
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
# 6. HTTP SESSION (GIỮ NGUYÊN)
# ==========================================
session = requests.Session()
session.headers.update({
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
    'Accept': 'application/json, text/plain, */*',
    'Accept-Language': 'vi-VN,vi;q=0.9,en;q=0.8',
})

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
# 6.1. VNDIRECT BCTC API (TẮT MẶC ĐỊNH)
# ==========================================
def _item_key(it):
    return it.get('id') or (it.get('reportDate'), it.get('itemCode'),
                            it.get('quarter'), it.get('numericValue'))

def _period_from_item(it, report_type):
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
                metric_vn = force_vietnamese_label(metric_vn, stmt_vn)
                if not metric_vn: continue
                records.append({
                    'Mã chứng khoán': symbol, 'Tên doanh nghiệp': company_name,
                    'Tên ngành': sector_name, 'Loại báo cáo': stmt_vn,
                    'Loại kỳ': ky_bao_cao, 'Năm': str(year_val), 'Ngày kỳ': date_period,
                    'Chỉ tiêu tiếng Việt': metric_vn, 'Giá trị': fv
                })
    return records

# ==========================================
# 6.2. FALLBACK Giá + SLCP (🆕 v22: chuẩn đơn vị bằng norm_*)
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
                fv = norm_price(data['data'][0].get('close'))
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
                fv = norm_shares(shares)
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
                fv_p = norm_price(price)
                fv_s = norm_shares(shares)
                if fv_p:
                    records.append({'Mã chứng khoán': symbol, 'Tên doanh nghiệp': company_name, 'Tên ngành': sector_name, 'Loại báo cáo': 'Chỉ số thị trường, Định giá & Cổ tức', 'Loại kỳ': 'Real-time', 'Năm': current_year, 'Ngày kỳ': today_str, 'Chỉ tiêu tiếng Việt': 'Giá cổ phiếu hiện tại', 'Giá trị': fv_p})
                if fv_s:
                    records.append({'Mã chứng khoán': symbol, 'Tên doanh nghiệp': company_name, 'Tên ngành': sector_name, 'Loại báo cáo': 'Chỉ số thị trường, Định giá & Cổ tức', 'Loại kỳ': 'Real-time', 'Năm': current_year, 'Ngày kỳ': today_str, 'Chỉ tiêu tiếng Việt': 'Tổng số lượng cổ phiếu lưu hành', 'Giá trị': fv_s})
    except Exception: pass
    return records

# ==========================================
# 7. YFINANCE CRAWLERS (GIỮ KHUNG + CỔNG DỊCH + 🆕 v22 CHUẨN ĐƠN VỊ)
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
                if ky_bao_cao == 'Quý' and len(parts) >= 2:
                    date_period = f"{year_val}-Q{(int(parts[1]) - 1) // 3 + 1}"
                else:
                    date_period = date_str
                for row_idx, val in df[col].items():
                    if pd.notna(val):
                        fv = format_value(val)
                        if fv is not None and fv != 0:
                            metric_vn = force_vietnamese_label(str(row_idx).strip(), statement_type_vn)
                            if not metric_vn:
                                continue
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
                        if fv is not None and fv != 0:
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

        # 🆕 v22: CHUẨN ĐƠN VỊ NGAY KHI CÀO — chặn số 14 chữ số kiểu 36.166.511.658.185
        current_price = norm_price(current_price) if current_price else None
        shares_out = norm_shares(shares_out) if shares_out else None
        market_cap = norm_market_cap(market_cap, current_price, shares_out) if market_cap else None
        if (current_price is None) and market_cap and shares_out:
            current_price = norm_price(market_cap / shares_out)
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
            for name, val in [('Giá trị chỉ số', current_val), ('Biến động điểm', change_val), ('Biến động phần trăm', change_pct)]:
                fv = format_value(val)
                if fv is not None and fv != 0:
                    market_records.append({
                        'Mã chứng khoán': index_name, 'Tên doanh nghiệp': f'Chỉ số thị trường {index_name}',
                        'Tên ngành': 'Chỉ số vĩ mô', 'Loại báo cáo': 'Chỉ số thị trường, Định giá & Cổ tức',
                        'Loại kỳ': 'Real-time hằng ngày', 'Năm': current_year, 'Ngày kỳ': today_str,
                        'Chỉ tiêu tiếng Việt': name, 'Giá trị': fv
                    })
        except Exception: pass
    return market_records

# ==========================================
# 8. VNFINANCIALDATA BULK (GIỮ KHUNG + CỔNG DỊCH)
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
                if 'Giá trị' not in df.columns or 'Mã chứng khoán' not in df.columns: continue
                df['Mã chứng khoán'] = df['Mã chứng khoán'].astype(str).str.strip().str.upper()
                df = df[df['Mã chứng khoán'].isin(target_symbols)]
                for _, row in df.iterrows():
                    fv = format_value(row['Giá trị'])
                    if fv is None or fv == 0: continue
                    symbol = row['Mã chứng khoán']
                    company_name, sector_name = get_company_profile(symbol)
                    year_val = str(row['Năm'])
                    metric_vn = force_vietnamese_label(row['Chỉ tiêu tiếng Việt'], stmt_name)
                    if not metric_vn: continue
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
# 9. YFINANCE MULTITHREAD (GIỮ NGUYÊN)
# ==========================================
def process_single_ticker(symbol, category):
    recs = []
    suffixes = ['.HN', '.VN'] if category == 'HNX' else ['.VN']
    for suffix in suffixes:
        try:
            ticker = yf.Ticker(f"{symbol}{suffix}", session=session)
            before = len(recs)
            bs_df = getattr(ticker, 'balance_sheet', None)
            for attr, raw, ky in (('balance_sheet', 'Balance_Sheet', 'Năm'),
                                  ('quarterly_balance_sheet', 'Balance_Sheet', 'Quý'),
                                  ('financials', 'Income_Statement', 'Năm'),
                                  ('quarterly_financials', 'Income_Statement', 'Quý'),
                                  ('cashflow', 'Cash_Flow', 'Năm'),
                                  ('quarterly_cashflow', 'Cash_Flow', 'Quý')):
                try:
                    recs.extend(parse_financial_df(symbol, getattr(ticker, attr, None), raw, ky))
                except Exception:
                    pass
            recs.extend(fetch_market_and_valuation_metrics(symbol, ticker, bs_df))
            recs.extend(fetch_historical_dividends(symbol, ticker))
            if len(recs) > before or suffix == suffixes[-1]:
                break
        except Exception as exc:
            if suffix == suffixes[-1]:
                print(f"  ⚠️ Yahoo {symbol} ({category}): {type(exc).__name__}")
    return recs

# ==========================================
# 9.5. BÙ BCTC QUÝ BẰNG YFINANCE ĐA LUỒNG (GIỮ NGUYÊN)
# ==========================================
QUARTER_WORKERS = 8
QUARTER_TICKER_BUDGET = 20
QUARTER_TOTAL_BUDGET = 600
QUARTER_MIN_PERIODS = 4

def fetch_yf_quarter_single(symbol, category=None):
    recs = []
    t0 = time.monotonic()
    suffixes = ['.HN', '.VN'] if category == 'HNX' else ['.VN']
    for suffix in suffixes:
        try:
            ticker = yf.Ticker(f"{symbol}{suffix}")
        except Exception:
            continue
        before = len(recs)
        for attr, raw in (('quarterly_balance_sheet', 'Balance_Sheet'),
                          ('quarterly_income_stmt', 'Income_Statement'),
                          ('quarterly_cashflow', 'Cash_Flow')):
            if time.monotonic() - t0 > QUARTER_TICKER_BUDGET:
                break
            try:
                df = getattr(ticker, attr, None)
                recs.extend(parse_financial_df(symbol, df, raw, 'Quý'))
            except Exception:
                pass
        if len(recs) > before or suffix == suffixes[-1]:
            break
    return recs

def fetch_quarter_multithread(symbols, market_map=None):
    all_recs = []
    if not symbols: return all_recs
    total = len(symbols)
    done = 0
    executor = ThreadPoolExecutor(max_workers=QUARTER_WORKERS)
    market_map = market_map or {}
    futures = {executor.submit(fetch_yf_quarter_single, s, market_map.get(s)): s for s in symbols}
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
# 10. CLEANING & SOURCE TRACKING (5 TẦNG + CỔNG DỊCH + 🆕 v22 CHUẨN ĐƠN VỊ)
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
    df = df[df['Giá trị'] != 0]
    df['Mã chứng khoán'] = df['Mã chứng khoán'].astype(str).str.strip().str.upper()
    df = df[~df['Mã chứng khoán'].isin(['', 'NAN', 'NONE', 'NULL'])]
    df = df[df['Chỉ tiêu tiếng Việt'].astype(str).str.strip().ne('')]
    df = df[~df['Chỉ tiêu tiếng Việt'].astype(str).str.strip().str.lower().isin(['nan', 'none', 'null'])]

    # 🆕 v22: CHUẨN ĐƠN VỊ giá / SLCP / vốn hoá ngay trong cleaning (chặn cả dữ liệu cũ từ Supabase)
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
        print(f"  [Tầng 1b] 🆕 v22: loại {before_unit - len(df):,} dòng giá/SLCP/vốn hoá ngoài thang đơn vị.")
    print(f"  [Tầng 1] Loại bỏ NULL/0 & ép kiểu số. Còn {len(df):,} dòng.")

    before2 = len(df)
    df, _ = sweep_labels(df)
    print(f"  [Tầng 2] Ép chuẩn VAS + dịch Anh + bóc [n] + chặn rác. Còn {len(df):,} dòng (bỏ {before2 - len(df):,}).")

    mask = (df['Loại kỳ'] == 'Quý') & df['Ngày kỳ'].astype(str).str.match(r'^\d{4}-\d{2}-\d{2}$')
    if mask.any():
        s = df.loc[mask, 'Ngày kỳ'].astype(str)
        df.loc[mask, 'Ngày kỳ'] = s.str[:4] + '-Q' + ((s.str[5:7].astype(int) - 1) // 3 + 1).astype(str)
        print(f"  [Tầng 2.5] Chuẩn hoá {int(mask.sum()):,} nhãn quý về 'YYYY-Qn'.")

    if '_priority' in df.columns:
        df = df.sort_values('_priority', kind='stable')
    df = df.drop_duplicates(subset=['Mã chứng khoán', 'Loại báo cáo', 'Loại kỳ', 'Ngày kỳ', 'Chỉ tiêu tiếng Việt'], keep='first')
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

    print("  [Tầng 5] Loại bỏ dòng trắng (Giá trị = 0) & Format số liệu (int64, không .0)...")
    df = df[df['Giá trị'] != 0]

    vals = pd.to_numeric(df['Giá trị'], errors='coerce').round(4)
    keep = vals.notna() & np.isfinite(vals) & (vals != 0)
    df = df.loc[keep].copy()
    vals = vals.loc[keep]
    if df.empty:
        return pd.DataFrame(columns=STANDARD_COLUMNS)
    is_int = vals.eq(vals.round(0))
    fmt = pd.Series('', index=df.index, dtype=object)
    if is_int.any():
        fmt.loc[is_int] = vals.loc[is_int].astype('int64').astype(str)
    if (~is_int).any():
        fmt.loc[~is_int] = vals.loc[~is_int].map(lambda f: format(f, '.4f').rstrip('0').rstrip('.'))
    df['Giá trị'] = fmt
    df = df[df['Giá trị'].astype(str).str.strip().ne('')]

    if 'Năm' in df.columns:
        nam = pd.to_numeric(df['Năm'], errors='coerce')
        nam_tu_ngay = pd.to_numeric(df['Ngày kỳ'].astype(str).str.extract(r'(\d{4})')[0], errors='coerce')
        df['Năm'] = nam.fillna(nam_tu_ngay).fillna(datetime.now().year).astype(int)

    print(f"  [Tầng 5] ✅ Đã xóa dòng trắng. Còn {len(df):,} dòng.")
    return df[STANDARD_COLUMNS]

# ==========================================
# 10.5 🆕 v23.1: CHỈ SỐ ĐỊNH GIÁ DẪN XUẤT BẰNG PANDAS/NUMPY (hết dòng P/E, P/B, ROE = 0)
# ==========================================
VAL_METRIC_ALIASES = {
    'LNST': ['Lợi nhuận sau thuế TNDN', 'LNST của công ty mẹ', 'Lợi nhuận sau thuế thu nhập doanh nghiệp'],
    'VCSH': ['Vốn chủ sở hữu', 'Tổng vốn chủ sở hữu gồm cổ đông không kiểm soát'],
    'TTS':  ['Tổng cộng tài sản', 'Tổng tài sản'],
    'DT':   ['Doanh thu thuần', 'Doanh thu bán hàng và cung cấp dịch vụ', 'Tổng doanh thu'],
    'LG':   ['Lợi nhuận gộp'],
    'SLCP': ['Số lượng cổ phiếu phổ thông', 'Cổ phiếu đã phát hành'],
}

def _bounded_ratio(numerator, denominator, *, scale=1.0, abs_limit=None, positive_only=False):
    """Return a finite ratio only when inputs and result pass plausibility checks."""
    try:
        n, d = float(numerator), float(denominator)
        if not (math.isfinite(n) and math.isfinite(d)) or d == 0:
            return np.nan
        value = (n / d) * scale
        if not math.isfinite(value) or (positive_only and value <= 0):
            return np.nan
        if abs_limit is not None and abs(value) > abs_limit:
            return np.nan
        return value
    except (TypeError, ValueError, OverflowError):
        return np.nan

def compute_derived_valuation_metrics(df):
    """Calculate EPS, BVPS, ROE, ROA, margins, P/E, P/B and market cap.

    Unsafe/missing inputs produce no metric. Guardrails intentionally reject suspicious
    ratios instead of manufacturing a valuation when source units are inconsistent.
    Financial statement values are expected to share the same currency scale (VND).
    """
    if df is None or df.empty:
        return []
    try:
        d = df.copy()
        required = {'Giá trị', 'Chỉ tiêu tiếng Việt', 'Loại kỳ', 'Mã chứng khoán', 'Ngày kỳ', 'Năm'}
        if not required.issubset(d.columns):
            return []
        d['Giá trị số'] = pd.to_numeric(d['Giá trị'], errors='coerce')
        d = d[np.isfinite(d['Giá trị số']) & (d['Giá trị số'] != 0)]
        if d.empty:
            return []

        def latest(label):
            x = d[d['Chỉ tiêu tiếng Việt'].eq(label)].copy()
            if x.empty:
                return pd.Series(dtype=float)
            x = x.sort_values('Ngày kỳ', kind='stable')
            return x.groupby('Mã chứng khoán')['Giá trị số'].last()

        prices = latest('Giá cổ phiếu hiện tại')
        live_shares = latest('Tổng số lượng cổ phiếu lưu hành')
        grp = d[d['Loại kỳ'].isin(['Năm', 'Quý'])]
        if grp.empty:
            return []
        pivot = grp.pivot_table(index=['Mã chứng khoán', 'Loại kỳ', 'Ngày kỳ', 'Năm'],
                                columns='Chỉ tiêu tiếng Việt', values='Giá trị số', aggfunc='first')
        if pivot.empty:
            return []

        def col(key):
            for name in VAL_METRIC_ALIASES[key]:
                if name in pivot.columns:
                    return pivot[name].to_numpy(dtype=float)
            return np.full(len(pivot), np.nan, dtype=float)

        income = col('LNST')
        equity = col('VCSH')
        assets = col('TTS')
        revenue = col('DT')
        gross_profit = col('LG')
        period_shares = col('SLCP')
        idx = pivot.index
        symbols = idx.get_level_values('Mã chứng khoán')
        shares = np.array([period_shares[i] if np.isfinite(period_shares[i]) and period_shares[i] > 0
                           else live_shares.get(sym, np.nan) for i, sym in enumerate(symbols)], dtype=float)
        price = np.array([prices.get(sym, np.nan) for sym in symbols], dtype=float)

        # Core per-share values. Reject implausible EPS/BVPS rather than propagating
        # unit errors into a web valuation (e.g. market cap or millions treated as VND).
        eps = np.array([_bounded_ratio(income[i], shares[i], abs_limit=1_000_000) for i in range(len(idx))])
        bvps = np.array([_bounded_ratio(equity[i], shares[i], abs_limit=100_000_000) for i in range(len(idx))])
        roe = np.array([_bounded_ratio(income[i], equity[i], scale=100, abs_limit=300) for i in range(len(idx))])
        roa = np.array([_bounded_ratio(income[i], assets[i], scale=100, abs_limit=100) for i in range(len(idx))])
        net_margin = np.array([_bounded_ratio(income[i], revenue[i], scale=100, abs_limit=500) for i in range(len(idx))])
        gross_margin = np.array([_bounded_ratio(gross_profit[i], revenue[i], scale=100, abs_limit=500) for i in range(len(idx))])
        pe = np.array([_bounded_ratio(price[i], eps[i], abs_limit=200, positive_only=True)
                       if np.isfinite(price[i]) and price[i] > 0 and np.isfinite(eps[i]) and eps[i] > 0 else np.nan
                       for i in range(len(idx))])
        pb = np.array([_bounded_ratio(price[i], bvps[i], abs_limit=100, positive_only=True)
                       if np.isfinite(price[i]) and price[i] > 0 and np.isfinite(bvps[i]) and bvps[i] > 0 else np.nan
                       for i in range(len(idx))])
        mcap = np.array([_bounded_ratio(price[i], shares[i], abs_limit=MCAP_MAX, positive_only=True)
                         if np.isfinite(price[i]) and price[i] > 0 and np.isfinite(shares[i]) and shares[i] > 0 else np.nan
                         for i in range(len(idx))])

        outputs = [('Lãi cơ bản trên cổ phiếu', eps, 2), ('Giá trị sổ sách mỗi cổ phiếu', bvps, 2),
                   ('Lợi nhuận trên vốn chủ sở hữu', roe, 4), ('Lợi nhuận trên tổng tài sản', roa, 4),
                   ('Biên lợi nhuận ròng', net_margin, 4), ('Biên lợi nhuận gộp', gross_margin, 4),
                   ('Hệ số P/E cơ bản', pe, 4), ('Hệ số P/B', pb, 4), ('Vốn hóa thị trường', mcap, 0)]
        records = []
        for i, (symbol, period_type, period_date, year) in enumerate(idx):
            company_name, sector_name = get_company_profile(symbol)
            for label, values, digits in outputs:
                value = values[i]
                if not np.isfinite(value) or value == 0:
                    continue
                clean_value = int(round(float(value))) if digits == 0 else round(float(value), digits)
                records.append({'Mã chứng khoán': symbol, 'Tên doanh nghiệp': company_name, 'Tên ngành': sector_name,
                                'Loại báo cáo': 'Chỉ số thị trường, Định giá & Cổ tức',
                                'Loại kỳ': period_type, 'Năm': int(year), 'Ngày kỳ': period_date,
                                'Chỉ tiêu tiếng Việt': label, 'Giá trị': clean_value})
        print(f'  🧮 [v23] Đã tính {len(records):,} chỉ số; các tỷ lệ ngoài giới hạn đã bị loại.')
        return records
    except Exception as exc:
        print(f'  ⚠️ [v23] Không tính được chỉ số dẫn xuất: {type(exc).__name__}: {exc}')
        return []
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
# 11. MAIN (GIỮ KHUNG BƯỚC 0->8 + 🆕 v22 BƯỚC 6.5 + CHỈ 2 FILE OUTPUT)
# ==========================================
def main():
    global _ALL_RECORDS_GLOBAL
    print("=" * 62)
    print("🚀 FINEX VN STOCK DATABASE CRAWLER — v23.1 (HỢP NHẤT: SẠCH ANH + CHUẨN ĐƠN VỊ + CHỈ SỐ DẪN XUẤT)")
    print("=" * 62)
    print(f"  ⚙️ SKIP_VNDIRECT = {SKIP_VNDIRECT} | PURGE = {PURGE_SUPABASE_BAD} | BATCH = {UPSERT_BATCH_START}")
    print(f"  📚 Từ điển: VAS={len(VAS_WHITELIST)} | ALIAS={len(ALIAS_TO_VAS)} | TRANSLATION={len(TRANSLATION_MAP)}")

    ticker_market_map = load_132_master_tickers()
    hnx_symbols = sorted(s for s, market in ticker_market_map.items() if market == 'HNX')
    print(f"  🏦 Universe theo dõi: {len(hnx_symbols)} mã HNX, {len(ticker_market_map) - len(hnx_symbols)} mã HOSE/khác.")
    all_master_records = []

    def _accumulate(recs, source):
        global _ALL_RECORDS_GLOBAL
        if not recs: return
        kept, dropped = [], 0
        for r in recs:
            lab = force_vietnamese_label(r.get('Chỉ tiêu tiếng Việt'), r.get('Loại báo cáo'))
            if lab is None:
                dropped += 1
                continue
            r['Chỉ tiêu tiếng Việt'] = lab
            kept.append(r)
        if dropped:
            print(f"  🧹 [{source}] chặn {dropped:,} nhãn Anh/rác ngay khi nạp.")
        if not kept: return
        _add_source(kept, source)
        all_master_records.extend(kept)
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

    # BƯỚC 3
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

    # BƯỚC 4
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

        missing_q = [s for s in ticker_market_map.keys() if s not in q_syms]
        if missing_q:
            print(f"  🩹 {len(missing_q)} mã thiếu Quý. Bù bằng yfinance đa luồng ({QUARTER_WORKERS} luồng)...")
            q_recs = fetch_quarter_multithread(missing_q, ticker_market_map)
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
    print(f"\n🆕 BƯỚC 5.5: Tải bổ sung từ Supabase (đã lọc bẩn + dịch nhãn Anh cũ)...")
    supabase_df = load_data_from_supabase()
    if not supabase_df.empty:
        _accumulate(supabase_df.to_dict('records'), 'SUPABASE_HIGH' if SUPABASE_PRIORITY == 'high' else 'SUPABASE')

    # BƯỚC 6
    df_master = pd.DataFrame(all_master_records)
    df_clean = apply_first_principles_cleaning(df_master) if not df_master.empty else pd.DataFrame(columns=STANDARD_COLUMNS)

    # 🆕 v22 BƯỚC 6.5: tính chỉ số định giá dẫn xuất bằng pandas/numpy (đè giá trị 0/sai cũ)
    if not df_clean.empty:
        derived = compute_derived_valuation_metrics(df_clean)
        if derived:
            df_der = pd.DataFrame(derived)[STANDARD_COLUMNS]
            df_all = pd.concat([df_clean, df_der], ignore_index=True)
            df_all = df_all.drop_duplicates(subset=['Mã chứng khoán', 'Loại báo cáo', 'Loại kỳ', 'Ngày kỳ', 'Chỉ tiêu tiếng Việt'], keep='last')
            df_clean = df_all[STANDARD_COLUMNS]
            print(f"  ✅ [BƯỚC 6.5] Gộp chỉ số dẫn xuất -> tổng {len(df_clean):,} dòng.")

    # CHỐT CUỐI: quét lại toàn bộ trước khi ghi file
    if not df_clean.empty:
        df_clean, n_sweep = sweep_labels(df_clean)
        df_clean = df_clean.drop_duplicates(subset=['Mã chứng khoán', 'Loại báo cáo', 'Loại kỳ', 'Ngày kỳ', 'Chỉ tiêu tiếng Việt'], keep='first')
        print(f"  [Cổng cuối] Quét lại {len(df_clean):,} nhãn: loại thêm {n_sweep} nhãn Anh/rác sót.")

    # BƯỚC 7 — CHỈ LƯU ĐÚNG 2 FILE CHÍNH
    os.makedirs('data', exist_ok=True)
    csv_path = 'data/vietnam_stock_database_tong_hop.csv'
    parquet_path = 'data/vietnam_stock_database.parquet'

    _cleanup_temp_files()

    df_clean.to_csv(csv_path, index=False, encoding='utf-8-sig')
    df_clean.to_parquet(parquet_path, engine='pyarrow', index=False)
    print(f"\n💾 ĐÃ LƯU ĐÚNG 2 FILE CHÍNH:")
    print(f"   → CSV:     {csv_path}")
    print(f"   → PARQUET: {parquet_path} ({os.path.getsize(parquet_path)/1024/1024:.2f} MB)")

    if COVERAGE_REPORT and not df_clean.empty:
        export_coverage_report(df_clean, set(ticker_market_map.keys()))

    # BƯỚC 8 — KHÔNG BAO GIỜ làm fail job
    if PUSH_TO_SUPABASE:
        print("\n📤 BƯỚC 8: Đẩy Supabase (engine bền vững v22)...")
        try:
            ok = upsert_to_supabase(df_clean)
            if ok and PURGE_SUPABASE_BAD:
                purge_supabase_bad_rows()
        except Exception as e:
            print(f"⚠️ BƯỚC 8 lỗi đã chặn: {type(e).__name__}: {e} (dữ liệu vẫn an toàn trong 2 file chính)")

    _cleanup_temp_files()

    print("=" * 62)
    print(f" 🎉 HOÀN TẤT! Tổng: {len(df_clean):,} dòng")
    if not df_clean.empty:
        print(f" - Số mã: {df_clean['Mã chứng khoán'].nunique()}/132")
        for k, v in df_clean['Loại kỳ'].value_counts().items():
            print(f"     • {k}: {v:,}")
        en_left = int(df_clean['Chỉ tiêu tiếng Việt'].map(_looks_english).sum())
        print(f" - Nhãn thuần tiếng Anh còn sót TOÀN FILE: {en_left} (mục tiêu = 0)")
        px_chk = pd.to_numeric(df_clean[df_clean['Chỉ tiêu tiếng Việt'] == 'Giá cổ phiếu hiện tại']['Giá trị'], errors='coerce')
        if not px_chk.empty:
            print(f" - Giá cp: min={px_chk.min():,.0f} | max={px_chk.max():,.0f} VNĐ (thang hợp lệ 100 -> 5.000.000)")
    print("=" * 62)

# ==============================================================================
# 🆕 v22: CỔNG VÀO CHẶN MỌI EXCEPTION -> WORKFLOW KHÔNG BAO GIỜ EXIT 1
# ==============================================================================
if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n⚠️ Bị dừng bởi người dùng.")
    except Exception:
        print("\n🛑 LỖI TỔNG ĐÃ ĐƯỢC CHẶN (workflow sẽ KHÔNG exit 1):")
        traceback.print_exc()
        try:
            if _ALL_RECORDS_GLOBAL:
                os.makedirs('data', exist_ok=True)
                pd.DataFrame(_ALL_RECORDS_GLOBAL).to_csv('data/_emergency_backup.csv', index=False, encoding='utf-8-sig')
                print("  💾 Đã lưu khẩn cấp data/_emergency_backup.csv")
        except Exception:
            pass
    sys.exit(0)
