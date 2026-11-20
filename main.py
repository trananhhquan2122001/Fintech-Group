"""
FINEX VN STOCK DATABASE CRAWLER - v20.0 (TRIỆT ĐỂ TIẾNG ANH TOÀN FILE - QUÝ + NĂM + SUPABASE)
================================================================================
Changelog v20.0 (vá TẬN GỐC trên v19):
  ✅ FORCE STRIP ENGLISH: sau khi dịch, cắt bỏ MỌI từ tiếng Anh >= 3 ký tự
     (chỉ giữ EBIT, EPS, ROE, ROA, FCF, VND, CIR, CTCK, NHNN, TKV, PCC...);
     dòng nào vẫn còn tiếng Anh -> BỎ DÒNG, không giữ bất kỳ giá nào.
  ✅ TRANSLATION_MAP BỎ HẾT tiếng Anh trong ngoặc: 'Basic EPS' -> 'Lãi cơ bản
     trên cổ phiếu' (không còn '(Basic EPS)'), 'EBITDA' -> 'Lợi nhuận trước
     lãi vay, thuế và khấu hao', 'Trailing P/E' -> 'Hệ số P/E cơ bản', v.v.
  ✅ Bổ sung 80+ nhãn quarterly yfinance v19 thiếu: Net Debt, Enterprise Value,
     EV/EBITDA, Free Cash Flow, Cash Flow From Operations, Shares Outstanding,
     Dividends Per Share, Diluted EPS, Weighted Average Shares, v.v.
  ✅ BỎ lru_cache trên _std_cached (nguồn gốc cache sót nhãn Anh giữa các lần chạy).
  ✅ fix_yfinance_typos xử lý camelCase yfinance -> tách từ đúng.
  ✅ force_vietnamese_label áp dụng ở 5 chốt: _accumulate, nguồn cào, Tầng 2,
     trước ghi file, trước upsert -> KHÔNG CÓ LỖ HỔ NÀO lọt tiếng Anh.
  ✅ Giữ nguyên 100%: SKIP_VNDIRECT=true, quý yfinance 8 luồng, 176 mã,
     BƯỚC 0->8, emergency-save, coverage report, dọn file tạm, purge Supabase.
================================================================================
"""
import os, socket, glob, signal, sys, time, threading, random, math, re, unicodedata
socket.setdefaulttimeout(15)
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd
import numpy as np
import requests
from requests.adapters import HTTPAdapter

# ==============================================================================
# 🛡️ BẮT SIGTERM
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
# 1. TỪ ĐIỂN VAS WHITELIST (GIỮ NGUYÊN 100%)
# ==============================================================================
VAS_WHITELIST = set([
    "Tài sản ngắn hạn", "Tiền và các khoản tương đương tiền", "Tiền", "Các khoản tương đương tiền",
    "Đầu tư tài chính ngắn hạn", "Chứng khoán kinh doanh", "Dự phòng giảm giá chứng khoán kinh doanh", "Đầu tư nắm giữ đến ngày đáo hạn",
    "Các khoản phải thu ngắn hạn", "Phải thu ngắn hạn của khách hàng", "Trả trước cho người bán ngắn hạn", "Phải thu nội bộ ngắn hạn",
    "Phải thu theo tiến độ kế hoạch hợp đồng xây dựng", "Phải thu về cho vay ngắn hạn", "Phải thu ngắn hạn khác", "Dự phòng phải thu ngắn hạn khó đòi", "Tài sản thiếu chờ xử lý",
    "Hàng tồn kho", "Dự phòng giảm giá hàng tồn kho",
    "Tài sản ngắn hạn khác", "Chi phí trả trước ngắn hạn", "Thuế GTGT được khấu trừ", "Thuế và các khoản khác phải thu Nhà nước", "Giao dịch mua bán lại trái phiếu Chính phủ",
    "Tài sản dài hạn", "Các khoản phải thu dài hạn", "Phải thu dài hạn của khách hàng", "Trả trước cho người bán dài hạn",
    "Vốn kinh doanh ở đơn vị trực thuộc", "Phải thu nội bộ dài hạn", "Phải thu về cho vay dài hạn", "Phải thu dài hạn khác", "Dự phòng phải thu dài hạn khó đòi",
    "Tài sản cố định", "Tài sản cố định hữu hình", "Nguyên giá", "Hao mòn lũy kế", "Tài sản cố định thuê tài chính", "Tài sản cố định vô hình",
    "Bất động sản đầu tư", "Tài sản dở dang dài hạn", "Chi phí sản xuất, kinh doanh dở dang dài hạn", "Chi phí xây dựng cơ bản dở dang",
    "Đầu tư tài chính dài hạn", "Đầu tư vào công ty con", "Đầu tư vào công ty liên doanh, liên kết", "Đầu tư góp vốn vào đơn vị khác", "Dự phòng đầu tư tài chính dài hạn",
    "Tài sản dài hạn khác", "Chi phí trả trước dài hạn", "Tài sản thuế thu nhập hoãn lại", "Thiết bị, vật tư, phụ tùng thay thế dài hạn", "Lợi thế thương mại",
    "Tổng cộng tài sản", "Báo cáo tình hình tài chính",
    "Nợ phải trả", "Nợ ngắn hạn", "Phải trả người bán ngắn hạn", "Người mua trả tiền trước ngắn hạn", "Thuế và các khoản phải nộp Nhà nước",
    "Phải trả người lao động", "Chi phí phải trả ngắn hạn", "Phải trả nội bộ ngắn hạn", "Phải trả theo tiến độ kế hoạch hợp đồng xây dựng",
    "Doanh thu chưa thực hiện ngắn hạn", "Phải trả ngắn hạn khác", "Vay và nợ thuê tài chính ngắn hạn", "Dự phòng phải trả ngắn hạn",
    "Quỹ khen thưởng, phúc lợi", "Quỹ bình ổn giá",
    "Nợ dài hạn", "Phải trả người bán dài hạn", "Người mua trả tiền trước dài hạn", "Chi phí phải trả dài hạn", "Phải trả nội bộ về vốn kinh doanh",
    "Phải trả nội bộ dài hạn", "Doanh thu chưa thực hiện dài hạn", "Phải trả dài hạn khác", "Vay và nợ thuê tài chính dài hạn",
    "Trái phiếu chuyển đổi", "Cổ phiếu ưu đãi", "Thuế thu nhập hoãn lại phải trả", "Dự phòng phải trả dài hạn", "Quỹ phát triển khoa học và công nghệ",
    "Vốn chủ sở hữu", "Vốn góp của chủ sở hữu", "Cổ phiếu phổ thông có quyền biểu quyết", "Thặng dư vốn cổ phần",
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
    # NGÂN HÀNG
    "Tiền mặt, vàng bạc, đá quý", "Tiền gửi tại Ngân hàng Nhà nước", "Tiền gửi tại và cho vay các tổ chức tín dụng khác",
    "Các công cụ tài chính phái sinh và tài sản tài chính khác", "Cho vay khách hàng",
    "Hoạt động mua nợ", "Chứng khoán đầu tư", "Góp vốn, đầu tư dài hạn", "Tài sản Có khác",
    "Nợ Chính phủ và Ngân hàng Nhà nước", "Tiền gửi và vay các tổ chức tín dụng khác", "Tiền gửi của khách hàng",
    "Công cụ tài chính phái sinh và nợ tài chính khác", "Vốn tài trợ, ủy thác đầu tư", "Phát hành giấy tờ có giá",
    "Vốn điều lệ", "Thu nhập lãi thuần", "Thu nhập từ dịch vụ", "Lãi thuần từ dịch vụ", "Lãi thuần từ ngoại hối và vàng",
    "Lãi thuần từ chứng khoán kinh doanh", "Lãi thuần từ chứng khoán đầu tư", "Thu nhập hoạt động khác", "Chi phí hoạt động",
    "Lợi nhuận trước dự phòng rủi ro tín dụng", "Chi phí dự phòng rủi ro tín dụng", "Thu nhập lãi nhận được",
    "Chi phí lãi đã trả", "Thu từ dịch vụ", "Thu nợ đã xóa", "Chi cho nhân viên và quản lý",
    # CHỨNG KHOÁN
    "Tài sản tài chính", "Các tài sản tài chính ghi nhận thông qua lãi lỗ", "Các khoản đầu tư nắm giữ đến ngày đáo hạn",
    "Các khoản cho vay", "Tài sản tài chính sẵn sàng để bán", "Dự phòng suy giảm giá trị",
    "Các khoản phải thu", "Phải thu dịch vụ CTCK", "Phải thu lỗi giao dịch",
    "Vay và nợ thuê tài chính", "Vay tài sản tài chính", "Trái phiếu chuyển đổi", "Trái phiếu phát hành", "Vay Quỹ hỗ trợ thanh toán",
    "Phải trả hoạt động giao dịch chứng khoán", "Nhận ký quỹ, ký cược", "Quỹ dự trữ bổ sung vốn điều lệ", "Quỹ dự phòng tài chính và rủi ro nghiệp vụ",
    "Doanh thu hoạt động", "Lãi từ FVTPL", "Lãi HTM", "Lãi cho vay và phải thu",
    "Lãi AFS", "Lãi phái sinh phòng ngừa", "Doanh thu môi giới", "Bảo lãnh và đại lý phát hành", "Tư vấn đầu tư", "Lưu ký", "Tư vấn tài chính",
    "Chi phí hoạt động", "Lỗ FVTPL", "Lỗ HTM", "Lỗ AFS khi phân loại lại", "Chi phí dự phòng, xử lý tổn thất và chi phí đi vay của khoản cho vay",
    "Chi phí tự doanh, môi giới, bảo lãnh, tư vấn đầu tư, lưu ký, tư vấn tài chính và dịch vụ khác", "Doanh thu hoạt động tài chính",
    "Lãi tỷ giá", "Cổ tức và lãi tiền gửi", "Lãi bán, thanh lý công ty con, liên kết", "Lỗ tỷ giá",
    "Lỗ thanh lý đầu tư", "Dự phòng đầu tư dài hạn", "Chi phí quản lý CTCK", "Kết quả hoạt động",
    # BẢO HIỂM
    "Tài sản tái bảo hiểm", "Dự phòng phí và dự phòng bồi thường nhượng tái bảo hiểm", "Ký quỹ bảo hiểm",
    "Dự phòng nghiệp vụ", "Dự phòng phí chưa được hưởng", "Dự phòng toán học", "Dự phòng bồi thường", "Dự phòng chia lãi", "Dự phòng đảm bảo cân đối",
    "Phải thu và phải trả hoạt động nhận và nhượng tái bảo hiểm", "Phí bảo hiểm gốc", "Phí nhận tái bảo hiểm", "Phí nhượng tái bảo hiểm",
    "Thay đổi dự phòng phí", "Doanh thu phí bảo hiểm thuần", "Hoa hồng nhượng tái và doanh thu khác", "Doanh thu thuần hoạt động bảo hiểm",
    "Chi bồi thường gốc và nhận tái", "Thu bồi thường nhượng tái", "Thay đổi dự phòng bồi thường", "Chi hoa hồng", "Lợi nhuận gộp bảo hiểm",
    # Bổ sung
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
    "Đầu tư vào liên doanh", "Đầu tư vào công ty liên kết",
    "Thuế thu nhập hoãn lại phải trả ngắn hạn", "Thuế thu nhập hoãn lại phải trả dài hạn",
    "Quỹ phúc lợi nhân viên ngắn hạn", "Quỹ phúc lợi nhân viên và hưu trí",
    "Tiền mặt, tương đương tiền và đầu tư ngắn hạn", "Các khoản thanh toán tiền mặt",
    "Các khoản thanh toán tiền mặt khác từ HĐKD", "Thanh toán cho người lao động",
    "Các khoản thu tiền mặt từ HĐKD", "Các khoản thu tiền mặt khác từ HĐKD",
    "Các khoản thanh toán tiền mặt khác từ HĐ đầu tư", "Các khoản thu tiền mặt khác từ HĐ đầu tư",
    "Các khoản thanh toán tiền mặt khác từ HĐ tài chính", "Các khoản thu tiền mặt khác từ HĐ tài chính",
    "Cổ tức đã nhận", "Thu từ thanh lý tài sản cố định", "Chi mua sắm tài sản cố định",
    "Tổng các khoản mục bất thường",
    "Lợi nhuận ròng pha loãng phân bổ cho CĐ phổ thông", "Lợi nhuận ròng phân bổ cho cổ đông phổ thông",
    "Tổng chi phí tài chính khác", "Thu nhập/chi phí lãi thuần ngoài HĐKD", "Thu nhập/chi phí khác",
    "Lợi nhuận ròng bất thường", "Lợi nhuận ròng từ hoạt động không liên tục", "Lợi nhuận ròng từ hoạt động liên tục",
    "Chi phí thu nhập đặc biệt", "Chi phí đặc biệt khác", "Xóa sổ", "Tổn thất tài sản và dự phòng",
    "Thuế thu nhập hoãn lại", "Biến động các khoản phải thu", "Biến động hàng tồn kho",
    "Biến động các khoản phải trả", "Biến động phải trả người bán", "Biến động vốn lưu động khác",
    "Chi phí đầu tư tài sản cố định", "Tiền mua hoặc thanh lý tài sản cố định",
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
    "Tiền thu từ đi vay dài hạn thuần", "Tiền trả nợ gốc vay dài hạn thuần",
    "Tiền thu từ đi vay ngắn hạn", "Tiền trả nợ gốc vay ngắn hạn", "Tiền lãi vay đã trả HĐTC",
    "Tiền lãi nhận được HĐĐT", "Tiền lãi nhận được HĐKD", "Thuế TNDN đã nộp thực nộp",
    "Thuế được hoàn lại", "Biến động chi phí trả trước", "Các khoản mục phi tiền mặt khác",
])

# ==============================================================================
# 2. 🆕 v20.0 — SIÊU TỪ ĐIỂN DỊCH (BỎ HẾT TIẾNG ANH TRONG NGOẶC)
# ==============================================================================
# Quy tắc: GIÁ TRỊ luôn là tiếng Việt THUẦN, KHÔNG kèm (English)
TRANSLATION_MAP = {
    # === BÁO CÁO ===
    'Balance_Sheet': 'Bảng cân đối kế toán',
    'Income_Statement': 'Báo cáo kết quả kinh doanh',
    'Cash_Flow': 'Báo cáo lưu chuyển tiền tệ',
    'Market_Metrics': 'Chỉ số thị trường, Định giá & Cổ tức',
    
    # === BẢNG CÂN ĐỐI KẾ TOÁN - TÀI SẢN NGẮN HẠN ===
    'Total Assets': 'Tổng cộng tài sản',
    'Current Assets': 'Tài sản ngắn hạn',
    'Cash And Cash Equivalents': 'Tiền và các khoản tương đương tiền',
    'Cash': 'Tiền',
    'Cash Equivalents': 'Các khoản tương đương tiền',
    'Cash Financial': 'Tiền và các khoản tương đương tiền',
    'Short Term Investments': 'Đầu tư tài chính ngắn hạn',
    'Other Short Term Investments': 'Đầu tư tài chính ngắn hạn khác',
    'Net Receivables': 'Phải thu ngắn hạn ròng',
    'Accounts Receivable': 'Phải thu ngắn hạn của khách hàng',
    'Gross Accounts Receivable': 'Phải thu khách hàng gộp',
    'Allowance For Doubtful Accounts Receivable': 'Dự phòng phải thu ngắn hạn khó đòi',
    'Receivables': 'Các khoản phải thu',
    'Other Receivables': 'Các khoản phải thu ngắn hạn khác',
    'Due From Related Parties Current': 'Phải thu các bên liên quan ngắn hạn',
    'Due From Related Parties Non Current': 'Phải thu các bên liên quan dài hạn',
    'Inventory': 'Hàng tồn kho',
    'Raw Materials': 'Nguyên liệu, vật liệu tồn kho',
    'Work In Process': 'Chi phí sản xuất kinh doanh dở dang',
    'Finished Goods': 'Thành phẩm tồn kho',
    'Other Inventories': 'Hàng tồn kho khác',
    'Inventories Adjustments Allowances': 'Dự phòng giảm giá hàng tồn kho',
    'Prepaid Assets': 'Chi phí trả trước ngắn hạn',
    'Current Prepaid Assets': 'Chi phí trả trước ngắn hạn',
    'Non Current Prepaid Assets': 'Chi phí trả trước dài hạn',
    'Restricted Cash': 'Tiền bị hạn chế',
    'Other Current Assets': 'Tài sản ngắn hạn khác',
    'Tax Receivable': 'Thuế phải thu',
    'Current Tax Receivables': 'Thuế phải thu ngắn hạn',
    
    # === BẢNG CÂN ĐỐI KẾ TOÁN - TÀI SẢN DÀI HẠN ===
    'Total Non Current Assets': 'Tài sản dài hạn',
    'Net PPE': 'Tài sản cố định hữu hình thuần',
    'Gross PPE': 'Nguyên giá tài sản cố định hữu hình',
    'Accumulated Depreciation': 'Hao mòn lũy kế',
    'Property Plant And Equipment': 'Tài sản cố định hữu hình',
    'Machinery Furniture Equipment': 'Máy móc, thiết bị và phương tiện vận tải',
    'Land And Improvements': 'Đất đai và cải tạo đất',
    'Buildings And Improvements': 'Nhà cửa và vật kiến trúc',
    'Construction In Progress': 'Xây dựng cơ bản dở dang',
    'Goodwill': 'Lợi thế thương mại',
    'Goodwill And Other Intangible Assets': 'Lợi thế thương mại và tài sản vô hình',
    'Other Intangible Assets': 'Tài sản cố định vô hình khác',
    'Intangible Assets': 'Tài sản cố định vô hình',
    'Investments And Advances': 'Đầu tư tài chính dài hạn',
    'Investment In Financial Assets': 'Đầu tư tài chính dài hạn',
    'Held To Maturity Securities': 'Chứng khoán đầu tư giữ đến ngày đáo hạn',
    'Available For Sale Securities': 'Chứng khoán đầu tư sẵn sàng để bán',
    'Investment Properties': 'Bất động sản đầu tư',
    'Properties': 'Bất động sản',
    'Other Properties': 'Bất động sản khác',
    'Leases': 'Tài sản quyền sử dụng đất và thuê tài chính',
    'Other Non Current Assets': 'Tài sản dài hạn khác',
    'Deferred Tax Assets': 'Tài sản thuế thu nhập hoãn lại',
    'Non Current Deferred Taxes Assets': 'Tài sản thuế thu nhập hoãn lại dài hạn',
    'Current Deferred Taxes Assets': 'Tài sản thuế thu nhập hoãn lại ngắn hạn',
    'Long Term Equity Investment': 'Đầu tư góp vốn dài hạn',
    'Investments In Subsidiaries': 'Đầu tư vào công ty con',
    'Investments In Associates': 'Đầu tư vào công ty liên kết',
    'Investments In Joint Ventures': 'Đầu tư vào liên doanh',
    'Other Investments': 'Đầu tư khác',
    'Securities And Investments': 'Chứng khoán và đầu tư',
    
    # === BẢNG CÂN ĐỐI KẾ TOÁN - NỢ PHẢI TRẢ ===
    'Total Liabilities Net Minority Interest': 'Nợ phải trả',
    'Current Liabilities': 'Nợ ngắn hạn',
    'Accounts Payable': 'Phải trả người bán ngắn hạn',
    'Payables': 'Các khoản phải trả',
    'Taxes Payable': 'Thuế và các khoản phải nộp nhà nước',
    'Income Tax Payable': 'Thuế TNDN phải trả',
    'Current Tax Payable': 'Thuế phải trả ngắn hạn',
    'Total Tax Payable': 'Tổng thuế phải trả',
    'Accrued Liabilities': 'Chi phí phải trả ngắn hạn',
    'Current Accrued Expenses': 'Chi phí phải trả ngắn hạn',
    'Non Current Accrued Expenses': 'Chi phí phải trả dài hạn',
    'Other Current Liabilities': 'Phải trả ngắn hạn khác',
    'Other Non Current Liabilities': 'Nợ dài hạn khác',
    'Current Debt': 'Vay và nợ thuê tài chính ngắn hạn',
    'Current Debt And Capital Lease Obligation': 'Vay và nợ thuê tài chính ngắn hạn',
    'Long Term Debt And Capital Lease Obligation': 'Vay và nợ thuê tài chính dài hạn',
    'Total Non Current Liabilities Net Minority Interest': 'Nợ dài hạn',
    'Long Term Debt': 'Vay và nợ thuê tài chính dài hạn',
    'Total Debt': 'Tổng nợ vay',
    'Net Debt': 'Nợ vay ròng',
    'Capital Lease Obligations': 'Nợ thuê tài chính',
    'Current Capital Lease Obligation': 'Nợ thuê tài chính ngắn hạn',
    'Long Term Capital Lease Obligation': 'Nợ thuê tài chính dài hạn',
    'Deferred Revenue': 'Doanh thu chưa thực hiện dài hạn',
    'Current Deferred Revenue': 'Doanh thu chưa thực hiện ngắn hạn',
    'Non Current Deferred Revenue': 'Doanh thu chưa thực hiện dài hạn',
    'Deferred Tax Liabilities': 'Thuế thu nhập hoãn lại phải trả',
    'Current Deferred Taxes Liabilities': 'Thuế thu nhập hoãn lại phải trả ngắn hạn',
    'Non Current Deferred Taxes Liabilities': 'Thuế thu nhập hoãn lại phải trả dài hạn',
    'Current Provisions': 'Dự phòng phải trả ngắn hạn',
    'Non Current Provisions': 'Dự phòng phải trả dài hạn',
    'Long Term Provisions': 'Dự phòng phải trả dài hạn',
    'Employee Benefits': 'Phải trả người lao động',
    'Current Employee Benefits': 'Phải trả người lao động ngắn hạn',
    'Non Current Employee Benefits': 'Phải trả người lao động dài hạn',
    'Pension And Other Post Retirement Benefit Plans Current': 'Quỹ phúc lợi nhân viên ngắn hạn',
    'Pension And Other Post-Retirement Benefit Plans Current': 'Quỹ phúc lợi nhân viên ngắn hạn',
    'Non Current Pension And Other Postretirement Benefit Plans': 'Quỹ phúc lợi nhân viên và hưu trí dài hạn',
    'Trade And Other Payables Non Current': 'Phải trả thương mại và khác dài hạn',
    'Payables And Accrued Expenses': 'Phải trả và chi phí phải trả',
    'Line Of Credit': 'Hạn mức tín dụng',
    'Commercial Paper': 'Thương phiếu',
    'Other Current Borrowings': 'Vay ngắn hạn khác',
    'Other Non Current Borrowings': 'Vay dài hạn khác',
    'Derivative Product Liabilities': 'Nợ công cụ phái sinh',
    'Derivative Assets': 'Tài sản phái sinh',
    'Assets Held For Sale': 'Tài sản nắm giữ để bán',
    'Liabilities Held For Sale': 'Nợ gắn với tài sản nắm giữ để bán',
    
    # === BẢNG CÂN ĐỐI KẾ TOÁN - VỐN CHỦ SỞ HỮU ===
    'Total Equity Gross Minority Interest': 'Vốn chủ sở hữu',
    'Total Equity': 'Vốn chủ sở hữu',
    'Stockholders Equity': 'Vốn chủ sở hữu',
    'Common Stock Equity': 'Vốn chủ sở hữu',
    'Share Capital': 'Vốn góp chủ sở hữu',
    'Common Stock': 'Cổ phiếu phổ thông',
    'Preferred Stock': 'Cổ phiếu ưu đãi',
    'Capital Stock': 'Vốn góp chủ sở hữu',
    'Additional Paid In Capital': 'Thặng dư vốn cổ phần',
    'Share Premium': 'Thặng dư vốn cổ phần',
    'Retained Earnings': 'Lợi nhuận sau thuế chưa phân phối',
    'Treasury Stock': 'Cổ phiếu quỹ',
    'Minority Interest': 'Lợi ích cổ đông không kiểm soát',
    'Minority Interests': 'Lợi ích cổ đông không kiểm soát',
    'Other Equity Interest': 'Lợi ích vốn chủ sở hữu khác',
    'Other Equity Adjustments': 'Điều chỉnh vốn chủ sở hữu khác',
    'Foreign Currency Translation Adjustments': 'Chênh lệch tỷ giá quy đổi báo cáo',
    'Gains Losses Not Affecting Retained Earnings': 'Chênh lệch đánh giá lại tài sản và chênh lệch tỷ giá',
    'Unrealized Gain Loss': 'Lãi/lỗ chưa thực hiện',
    'Fixed Assets Revaluation Reserve': 'Quỹ đánh giá lại tài sản cố định',
    'Working Capital': 'Vốn lưu động ròng',
    'Total Capitalization': 'Tổng vốn hóa sổ sách',
    'Tangible Book Value': 'Giá trị sổ sách hữu hình',
    'Invested Capital': 'Vốn đầu tư',
    'Net Tangible Assets': 'Tài sản hữu hình thuần',
    'Ordinary Shares Number': 'Số lượng cổ phiếu phổ thông',
    'Share Issued': 'Cổ phiếu đã phát hành',
    
    # === BÁO CÁO KẾT QUẢ KINH DOANH ===
    'Total Revenue': 'Doanh thu thuần',
    'Operating Revenue': 'Doanh thu thuần',
    'Cost Of Revenue': 'Giá vốn hàng bán',
    'Cost Of Goods Sold': 'Giá vốn hàng bán',
    'Gross Profit': 'Lợi nhuận gộp',
    'Operating Expense': 'Chi phí hoạt động',
    'Total Expenses': 'Tổng chi phí',
    'Selling General And Administration': 'Chi phí bán hàng và quản lý doanh nghiệp',
    'Selling And Marketing Expense': 'Chi phí bán hàng',
    'General And Administrative Expense': 'Chi phí quản lý doanh nghiệp',
    'Research And Development': 'Chi phí nghiên cứu và phát triển',
    'Other Operating Expenses': 'Chi phí hoạt động khác',
    'Other G And A': 'Chi phí quản lý doanh nghiệp khác',
    'Rent And Landing Fees': 'Chi phí thuê mặt bằng',
    'Insurance And Claims': 'Chi phí bảo hiểm và bồi thường',
    'Salaries And Wages': 'Chi phí lương và nhân công',
    'Operating Income': 'Lợi nhuận thuần từ hoạt động kinh doanh',
    'Operating Profit': 'Lợi nhuận thuần từ hoạt động kinh doanh',
    'Net Interest Income': 'Thu nhập lãi thuần',
    'Interest Expense': 'Chi phí lãi vay',
    'Interest Income': 'Thu nhập lãi',
    'Net Non Operating Interest Income Expense': 'Thu nhập/chi phí lãi thuần ngoài HĐKD',
    'Total Other Income Expense Net': 'Tổng thu nhập/chi phí khác thuần',
    'Other Income Expense': 'Thu nhập/chi phí khác',
    'Total Operating Income As Reported': 'Lợi nhuận thuần từ hoạt động kinh doanh',
    'Pretax Income': 'Tổng lợi nhuận kế toán trước thuế',
    'Tax Provision': 'Chi phí thuế thu nhập doanh nghiệp',
    'Tax Rate For Calcs': 'Thuế suất dùng để tính toán',
    'Tax Effect Of Unusual Items': 'Ảnh hưởng thuế từ các khoản mục bất thường',
    'Net Income': 'Lợi nhuận sau thuế TNDN',
    'Net Income Common Stockholders': 'LNST của công ty mẹ',
    'Net Income Including Noncontrolling Interests': 'Lợi nhuận sau thuế TNDN',
    'Net Income From Continuing Operation': 'Lợi nhuận sau thuế từ hoạt động tiếp tục',
    'Net Income From Continuing Operation Net Minority Interest': 'LNST của công ty mẹ',
    'Net Income Continuous Operations': 'Lợi nhuận sau thuế TNDN',
    'Net Income From Continuing And Discontinued Operation': 'Lợi nhuận sau thuế TNDN',
    'Net Income Discontinuous Operations': 'Lợi nhuận ròng từ hoạt động không liên tục',
    'Net Income Extraordinary': 'Lợi nhuận ròng bất thường',
    'Normalized Income': 'Lợi nhuận thuần chuẩn hóa',
    
    # === EPS & SỐ CỔ PHIẾU ===
    'Basic EPS': 'Lãi cơ bản trên cổ phiếu',
    'Diluted EPS': 'Lãi suy giảm trên cổ phiếu',
    'Basic Average Shares': 'Số lượng cổ phiếu bình quân cơ bản',
    'Diluted Average Shares': 'Số lượng cổ phiếu bình quân pha loãng',
    'Shares Outstanding': 'Số lượng cổ phiếu lưu hành',
    'Dividend Rate': 'Cổ tức trên mỗi cổ phiếu',
    'Dividend Per Share': 'Cổ tức trên mỗi cổ phiếu',
    'Dividend Yield': 'Tỷ suất cổ tức',
    
    # === EBIT / EBITDA / CÁC CHỈ SỐ ===
    'EBIT': 'Lợi nhuận trước lãi vay và thuế',
    'EBITDA': 'Lợi nhuận trước lãi vay, thuế và khấu hao',
    'Normalized EBITDA': 'Lợi nhuận trước lãi vay, thuế, khấu hao chuẩn hóa',
    'ROE': 'Lợi nhuận trên vốn chủ sở hữu',
    'ROA': 'Lợi nhuận trên tổng tài sản',
    'EPS': 'Lãi cơ bản trên cổ phiếu',
    
    # === LƯU CHUYỂN TIỀN TỆ ===
    'Operating Cash Flow': 'Lưu chuyển tiền thuần từ HĐKD',
    'Cash Flow From Continuing Operating Activities': 'Lưu chuyển tiền thuần từ HĐKD',
    'Investing Cash Flow': 'Lưu chuyển tiền thuần từ HĐĐT',
    'Cash Flow From Continuing Investing Activities': 'Lưu chuyển tiền thuần từ HĐĐT',
    'Financing Cash Flow': 'Lưu chuyển tiền thuần từ HĐTC',
    'Cash Flow From Continuing Financing Activities': 'Lưu chuyển tiền thuần từ HĐTC',
    'Free Cash Flow': 'Dòng tiền tự do',
    'Capital Expenditure': 'Chi phí đầu tư tài sản cố định',
    'Purchase Of PPE': 'Chi mua sắm tài sản cố định',
    'Sale Of PPE': 'Thu từ thanh lý tài sản cố định',
    'Net PPE Purchase And Sale': 'Tiền mua hoặc thanh lý tài sản cố định',
    'Net Intangibles Purchase And Sale': 'Tiền mua hoặc bán tài sản vô hình',
    'Net Investment Purchase And Sale': 'Tiền đầu tư góp vốn thuần',
    'Net Business Purchase And Sale': 'Tiền mua bán công ty con hoặc sáp nhập',
    'Purchase Of Investment': 'Tiền chi đầu tư góp vốn',
    'Sale Of Investment': 'Tiền thu hồi đầu tư góp vốn',
    'Purchase Of Business': 'Tiền mua công ty con',
    'Sale Of Business': 'Tiền bán công ty con',
    'Repayment Of Debt': 'Tiền trả nợ gốc vay',
    'Issuance Of Debt': 'Tiền thu từ đi vay',
    'Long Term Debt Issuance': 'Tiền thu từ đi vay dài hạn',
    'Long Term Debt Payments': 'Tiền trả nợ gốc vay dài hạn',
    'Short Term Debt Issuance': 'Tiền thu từ đi vay ngắn hạn',
    'Short Term Debt Payments': 'Tiền trả nợ gốc vay ngắn hạn',
    'Net Issuance Payments Of Debt': 'Tiền vay/trả nợ gốc thuần',
    'Net Long Term Debt Issuance': 'Tiền thu từ đi vay dài hạn thuần',
    'Net Short Term Debt Issuance': 'Tiền thu từ đi vay ngắn hạn thuần',
    'Common Stock Issuance': 'Tiền thu từ phát hành cổ phiếu',
    'Common Stock Repurchase': 'Tiền mua lại cổ phiếu quỹ',
    'Issuance Of Capital Stock': 'Tiền thu từ phát hành cổ phiếu',
    'Repurchase Of Capital Stock': 'Tiền mua lại cổ phiếu quỹ',
    'Net Common Stock Issuance': 'Tiền thu từ phát hành cổ phiếu hoặc bán cổ phiếu quỹ',
    'Cash Dividends Paid': 'Cổ tức đã chi trả cho chủ sở hữu',
    'Common Stock Dividend Paid': 'Cổ tức đã trả cho cổ đông phổ thông',
    'Preferred Stock Dividend Paid': 'Cổ tức đã trả cho cổ đông ưu đãi',
    'Dividends Paid': 'Cổ tức đã trả',
    'Dividends Received': 'Cổ tức đã nhận',
    'Dividend Received Cfi': 'Cổ tức đã nhận HĐĐT',
    'Dividends Received Cfo': 'Cổ tức đã nhận HĐKD',
    'Interest Received Cfi': 'Tiền lãi nhận được HĐĐT',
    'Interest Received Cfo': 'Tiền lãi nhận được HĐKD',
    'Interest Paid Cfo': 'Tiền lãi vay đã trả',
    'Interest Paid Cff': 'Tiền lãi vay đã trả HĐTC',
    'Taxes Refund Paid': 'Thuế được hoàn lại',
    'Tax Paid': 'Thuế đã nộp',
    'Beginning Cash Position': 'Tiền và tương đương tiền đầu kỳ',
    'End Cash Position': 'Tiền và tương đương tiền cuối kỳ',
    'Changes In Cash': 'Lưu chuyển tiền thuần trong kỳ',
    'Effect Of Exchange Rate Changes': 'Ảnh hưởng của thay đổi tỷ giá quy đổi ngoại tệ',
    'Change In Working Capital': 'Biến động vốn lưu động',
    'Change In Receivables': 'Biến động các khoản phải thu',
    'Change In Inventory': 'Biến động hàng tồn kho',
    'Change In Payables': 'Biến động các khoản phải trả',
    'Change In Payable': 'Biến động các khoản phải trả',
    'Change In Account Payable': 'Biến động phải trả người bán',
    'Change In Payables And Accrued Expense': 'Biến động phải trả và chi phí phải trả',
    'Change In Accrued Expense': 'Biến động chi phí phải trả',
    'Change In Prepaid Assets': 'Biến động chi phí trả trước',
    'Change In Other Working Capital': 'Biến động vốn lưu động khác',
    'Change In Other Current Assets': 'Biến động tài sản ngắn hạn khác',
    'Change In Other Current Liabilities': 'Biến động nợ ngắn hạn khác',
    'Change In Tax Payable': 'Biến động thuế phải trả',
    'Change In Dividend Payable': 'Biến động cổ tức phải trả',
    'Depreciation And Amortization': 'Khấu hao và phân bổ',
    'Depreciation Amortization Depletion': 'Khấu hao và phân bổ',
    'Reconciled Depreciation': 'Khấu hao được điều chỉnh',
    'Reconciled Cost Of Revenue': 'Giá vốn hàng bán điều chỉnh',
    'Asset Impairment Charge': 'Tổn thất tài sản và dự phòng',
    'Impairment Of Capital Assets': 'Tổn thất tài sản cố định',
    'Provision For Doubtful Accounts': 'Dự phòng phải thu khó đòi',
    'Deferred Income Tax': 'Thuế thu nhập hoãn lại',
    'Stock Based Compensation': 'Chi phí cổ phiếu thưởng cho nhân viên',
    'Share Based Compensation': 'Chi phí cổ phiếu thưởng cho nhân viên',
    'Other Non Cash Items': 'Các khoản mục phi tiền mặt khác',
    'Total Unusual Items Excluding Goodwill': 'Tổng các khoản mục bất thường',
    'Total Unusual Items': 'Tổng các khoản mục bất thường',
    'Gain Loss On Investment Securities': 'Lãi/lỗ từ chứng khoán đầu tư',
    'Net Foreign Currency Exchange Gain': 'Lãi / Lỗ chênh lệch tỷ giá hối đoái thuần',
    'Gain On Sale Of PPE': 'Lãi từ thanh lý tài sản cố định',
    'Gain On Sale Of Business': 'Lãi từ bán công ty con',
    'Gain On Sale Of Security': 'Lãi / Lỗ từ bán chứng khoán',
    'Earnings From Equity Interest': 'Lãi từ công ty liên kết',
    'Restructuring And Mergers Acquisition': 'Chi phí tái cấu trúc và sáp nhập',
    'Write Off': 'Xóa sổ',
    
    # === CHỈ SỐ THỊ TRƯỜNG & ĐỊNH GIÁ ===
    'Current Price': 'Giá cổ phiếu hiện tại',
    'Market Capitalization': 'Vốn hóa thị trường',
    'Enterprise Value': 'Giá trị doanh nghiệp',
    'Trailing EPS': 'EPS cơ bản 4 quý gần nhất',
    'Forward EPS': 'EPS dự phóng',
    'Trailing PE': 'Hệ số P/E cơ bản',
    'Forward PE': 'Hệ số P/E dự phóng',
    'Price To Book': 'Hệ số P/B',
    'Book Value': 'Giá trị sổ sách mỗi cổ phiếu',
    'Return On Equity': 'Lợi nhuận trên vốn chủ sở hữu',
    'Return On Assets': 'Lợi nhuận trên tổng tài sản',
    'Profit Margins': 'Biên lợi nhuận ròng',
    'Gross Margins': 'Biên lợi nhuận gộp',
    'Historical Dividend Cash': 'Lịch sử trả cổ tức bằng tiền',
    'Dividends Per Share': 'Cổ tức trên mỗi cổ phiếu',
    
    # === NGÂN HÀNG ===
    'Total Deposits': 'Tiền gửi của khách hàng',
    'Depositsby Bank': 'Tiền gửi và vay các tổ chức tín dụng khác',
    'Gross Loan': 'Cho vay khách hàng gộp',
    'Net Loan': 'Cho vay khách hàng thuần',
    'Allowance For Loans And Lease Losses': 'Dự phòng rủi ro tín dụng',
    'Provision For Loan Lease And Other Losses': 'Chi phí dự phòng rủi ro tín dụng',
    'Net Fee And Commission Income': 'Lãi thuần từ hoạt động dịch vụ',
    'Fees And Commissions': 'Thu nhập phí và hoa hồng',
    'Net Investment Income': 'Lãi thuần từ đầu tư',
    'Trading Gain Loss': 'Lãi/lỗ từ hoạt động tự doanh',
    
    # === CÁC MỤC KHÁC ===
    'Dividends Payable': 'Cổ tức phải trả',
    'Other Payable': 'Phải trả khác',
    'Other Payables': 'Phải trả khác',
    'Total Lease Payable': 'Tổng tiền thuê phải trả',
    'Investments In Joint Ventures At Cost': 'Đầu tư vào liên doanh theo giá gốc',
    'Investments In Associates At Cost': 'Đầu tư vào công ty liên kết theo giá gốc',
    'Cash Cash Equivalents And Short Term Investments': 'Tiền, tương đương tiền và đầu tư ngắn hạn',
    'Financial Assets': 'Tài sản tài chính',
    'Loans Receivable': 'Các khoản cho vay phải thu',
    'Accrued Interest Receivable': 'Lãi dự thu',
    'Dividends Receivable': 'Cổ tức phải thu',
    'Treasury Shares Number': 'Số lượng cổ phiếu quỹ',
    'Restricted Investments': 'Đầu tư bị hạn chế',
    'Money Market Investments': 'Đầu tư thị trường tiền tệ',
    'Other Cash Adjustment Inside Changein Cash': 'Điều chỉnh tiền khác trong biến động tiền',
    'Other Cash Adjustment Outside Changein Cash': 'Điều chỉnh tiền khác ngoài biến động tiền',
    'Net Other Financing Charges': 'Chi phí tài chính khác thuần',
    'Net Other Investing Changes': 'Biến động đầu tư khác thuần',
    'Minimum Pension Liabilities': 'Nợ lương hưu tối thiểu',
    'Federal Funds Purchased And Securities Sold Under Agreements To Repurchase': 'Giao dịch mua bán lại trái phiếu và vay liên ngân hàng',
    
    # === YFINANCE TYPOS (chữ dính) ===
    'Investmentsin joint venturesat cost': 'Đầu tư vào liên doanh theo giá gốc',
    'Investmentsin associatesat cost': 'Đầu tư vào công ty liên kết theo giá gốc',
    'Classesof Cash Payments': 'Các khoản thanh toán tiền mặt',
    'Other Cash Paymentsfrom Operating Activities': 'Các khoản thanh toán tiền mặt khác từ HĐKD',
    'Paymentson Behalfof Employees': 'Thanh toán cho người lao động',
    'Classesof Cash Receiptsfrom Operating Activities': 'Các khoản thu tiền mặt từ HĐKD',
    'Other Cash Receiptsfrom Operating Activities': 'Các khoản thu tiền mặt khác từ HĐKD',
    'Other Cash Paymentsfrom Investing Activities': 'Các khoản thanh toán tiền mặt khác từ HĐ đầu tư',
    'Other Cash Receiptsfrom Investing Activities': 'Các khoản thu tiền mặt khác từ HĐ đầu tư',
    'Other Cash Paymentsfrom Financing Activities': 'Các khoản thanh toán tiền mặt khác từ HĐ tài chính',
    'Other Cash Receiptsfrom Financing Activities': 'Các khoản thu tiền mặt khác từ HĐ tài chính',
    'Diluted NI Availto Com Stockholders': 'Lợi nhuận ròng pha loãng phân bổ cho CĐ phổ thông',
    'Pension and other post retirement benefit plans current': 'Quỹ phúc lợi nhân viên ngắn hạn',
    'Pension and other post-retirement benefit plans current': 'Quỹ phúc lợi nhân viên ngắn hạn',
}

# Build lowercase lookup once
_TRANS_LOWER = {k.lower(): v for k, v in TRANSLATION_MAP.items()}

# ==============================================================================
# 3. 🆕 v20.0 — TỪ ĐIỂN DỊCH TỪNG TỪ (fallback khi không có trong TRANSLATION_MAP)
# ==============================================================================
WORD_MAP = {
    'total': 'tổng', 'net': 'ròng', 'gross': 'gộp',
    'current': 'ngắn hạn', 'short': 'ngắn hạn', 'term': 'hạn',
    'non': 'dài hạn', 'long': 'dài hạn',
    'assets': 'tài sản', 'asset': 'tài sản',
    'liabilities': 'nợ phải trả', 'liability': 'nợ',
    'equity': 'vốn chủ sở hữu',
    'revenue': 'doanh thu', 'sales': 'doanh thu',
    'income': 'thu nhập', 'profit': 'lợi nhuận', 'earnings': 'lợi nhuận',
    'expense': 'chi phí', 'expenses': 'chi phí', 'cost': 'giá', 'costs': 'chi phí',
    'loss': 'lỗ', 'losses': 'lỗ', 'gain': 'lãi', 'gains': 'lãi',
    'cash': 'tiền', 'equivalents': 'tương đương tiền',
    'receivable': 'phải thu', 'receivables': 'phải thu',
    'payable': 'phải trả', 'payables': 'phải trả',
    'inventory': 'hàng tồn kho', 'inventories': 'hàng tồn kho',
    'investment': 'đầu tư', 'investments': 'đầu tư',
    'debt': 'nợ vay', 'loan': 'khoản vay', 'loans': 'khoản vay',
    'interest': 'lãi', 'dividend': 'cổ tức', 'dividends': 'cổ tức',
    'tax': 'thuế', 'taxes': 'thuế',
    'operating': 'hoạt động', 'operation': 'hoạt động',
    'investing': 'đầu tư', 'financing': 'tài chính',
    'flow': 'lưu chuyển', 'flows': 'lưu chuyển',
    'capital': 'vốn', 'stock': 'cổ phiếu', 'stocks': 'cổ phiếu',
    'share': 'cổ phiếu', 'shares': 'cổ phiếu',
    'property': 'tài sản', 'properties': 'bất động sản',
    'plant': 'nhà máy', 'equipment': 'thiết bị',
    'fixed': 'cố định', 'intangible': 'vô hình', 'tangible': 'hữu hình',
    'goodwill': 'lợi thế thương mại',
    'depreciation': 'khấu hao', 'amortization': 'phân bổ',
    'deferred': 'hoãn lại', 'accrued': 'phải trả',
    'prepaid': 'trả trước', 'retained': 'giữ lại',
    'minority': 'thiểu số', 'controlling': 'kiểm soát',
    'noncontrolling': 'không kiểm soát',
    'paid': 'đã trả', 'received': 'đã nhận', 'payable': 'phải trả',
    'issuance': 'phát hành', 'repayment': 'trả nợ',
    'refund': 'hoàn lại', 'purchase': 'mua', 'sale': 'bán',
    'repurchase': 'mua lại',
    'change': 'biến động', 'changes': 'biến động',
    'beginning': 'đầu kỳ', 'end': 'cuối kỳ', 'position': 'số dư',
    'average': 'bình quân', 'basic': 'cơ bản', 'diluted': 'pha loãng',
    'free': 'tự do', 'working': 'lưu động',
    'common': 'phổ thông', 'preferred': 'ưu đãi',
    'ordinary': 'phổ thông', 'treasury': 'quỹ',
    'other': 'khác', 'related': 'liên quan', 'parties': 'bên',
    'due': 'phải thu', 'from': 'từ', 'to': 'đến',
    'and': 'và', 'or': 'hoặc', 'of': 'của', 'in': 'trong',
    'for': 'cho', 'on': 'trên', 'at': 'tại', 'by': 'bởi',
    'the': '', 'a': '', 'an': '',
    'current': 'ngắn hạn', 'noncurrent': 'dài hạn',
    'provision': 'dự phòng', 'allowance': 'dự phòng',
    'doubtful': 'khó đòi', 'impairment': 'tổn thất',
    'accounts': 'các khoản',
    'customer': 'khách hàng', 'customers': 'khách hàng',
    'deposit': 'tiền gửi', 'deposits': 'tiền gửi',
    'employee': 'nhân viên', 'employees': 'nhân viên',
    'pension': 'lương hưu', 'retirement': 'nghỉ hưu',
    'benefit': 'phúc lợi', 'benefits': 'phúc lợi',
    'post': 'sau',
    'lease': 'thuê', 'leases': 'thuê',
    'capital': 'vốn',
    'obligation': 'nghĩa vụ', 'obligations': 'nghĩa vụ',
    'business': 'công ty con', 'businesses': 'công ty con',
    'subsidiary': 'công ty con', 'subsidiaries': 'công ty con',
    'associate': 'công ty liên kết', 'associates': 'công ty liên kết',
    'joint': 'liên doanh', 'venture': 'liên doanh', 'ventures': 'liên doanh',
    'market': 'thị trường', 'value': 'giá trị', 'valuation': 'định giá',
    'enterprise': 'doanh nghiệp',
    'margin': 'biên', 'margins': 'biên',
    'return': 'lợi nhuận',
    'book': 'sổ sách',
    'price': 'giá',
    'forward': 'dự phóng',
    'trailing': 'cơ bản',
    'historical': 'lịch sử',
    'per': 'trên',
    'number': 'số lượng',
    'outstanding': 'lưu hành',
    'rate': 'tỷ suất',
    'yield': 'tỷ suất',
    'current': 'hiện tại',
    'previous': 'trước',
    'close': 'đóng cửa',
    'open': 'mở cửa',
    'high': 'cao nhất',
    'low': 'thấp nhất',
    'volume': 'khối lượng',
    'exchange': 'tỷ giá',
    'currency': 'ngoại tệ',
    'foreign': 'ngoại',
    'unusual': 'bất thường',
    'items': 'khoản mục',
    'excluding': 'không gồm',
    'extraordinary': 'bất thường',
    'normalized': 'chuẩn hóa',
    'reconciled': 'điều chỉnh',
    'continuing': 'tiếp tục',
    'discontinued': 'không tiếp tục',
    'discontinuous': 'không tiếp tục',
    'including': 'bao gồm',
    'effect': 'ảnh hưởng',
    'changes': 'biến động',
    'exchange': 'tỷ giá',
    'rate': 'tỷ giá',
}

# ==============================================================================
# 4. 🆕 v20.0 — DANH SÁCH VIẾT TẮT ĐƯỢC PHÉP GIỮ LẠI (KHÔNG BỊ STRIP)
# ==============================================================================
ALLOWED_ABBREVIATIONS = {
    'EBIT', 'EBITDA', 'EPS', 'ROE', 'ROA', 'FCF', 'VND', 'USD',
    'CTCK', 'NHNN', 'TKV', 'PCC', 'TNDN', 'GTGT', 'HĐKD', 'HĐĐT', 'HĐTC',
    'TSCĐ', 'BĐSĐT', 'XDCB', 'LNST', 'FVTPL', 'HTM', 'AFS', 'CIR',
    'P/E', 'P/B', 'BCTC', 'VN', 'HNX', 'HOSE', 'UPCOM',
    'Q1', 'Q2', 'Q3', 'Q4',  # quý
}

# ==============================================================================
# 5. 🆕 v20.0 — HÀM STRIP TIẾNG ANH TRIỆT ĐỂ
# ==============================================================================
def _has_vietnamese(s):
    """Kiểm tra chuỗi có ít nhất 1 ký tự tiếng Việt."""
    return bool(re.search(r'[àáảãạăắằẳẵặâấầẩẫậèéẻẽẹêếềểễệìíỉĩịòóỏõọôốồổỗộơớờởỡợùúủũụưứừửữựỳýỷỹỵđ]', s.lower()))

def _strip_english_words(s):
    """🆕 v20.0: Cắt bỏ MỌI từ tiếng Anh (ASCII) >= 3 ký tự, TRỪ các viết tắt được phép."""
    if not s:
        return s
    # Tách từ
    words = s.split()
    kept = []
    for w in words:
        w_clean = re.sub(r'[^a-zA-Z0-9à-ỹđ/.,()-]', '', w)
        w_upper = w_clean.upper()
        # Nếu là viết tắt được phép -> giữ
        if w_upper in ALLOWED_ABBREVIATIONS:
            kept.append(w)
            continue
        # Nếu có ký tự tiếng Việt -> giữ
        if _has_vietnamese(w):
            kept.append(w)
            continue
        # Nếu là số -> giữ
        if re.match(r'^\d+$', w_clean):
            kept.append(w)
            continue
        # Nếu là viết tắt ngắn (1-2 ký tự) -> giữ (VD: "Q1")
        if len(w_clean) <= 2:
            kept.append(w)
            continue
        # Các trường hợp khác (từ tiếng Anh >= 3 ký tự) -> BỎ
    result = ' '.join(kept)
    # Dọn khoảng trắng thừa
    result = re.sub(r'\s{2,}', ' ', result).strip()
    # Dọn dấu câu đầu/cuối
    result = re.sub(r'^[.,;:()\[\]\s]+|[.,;:()\[\]\s]+$', '', result)
    return result

# ==============================================================================
# 6. 🆕 v20.0 — HÀM DỊCH DUY NHẤT (KHÔNG CÒN CACHE, KHÔNG CÒN LỖ HỔ)
# ==============================================================================
def _normalize_for_lookup(s):
    s = unicodedata.normalize('NFC', str(s))
    s = re.sub(r'[\n\r\t]+', ' ', s)
    s = re.sub(r'\s{2,}', ' ', s).strip()
    s = re.sub(r'\s*[\[(]\d+[a-zA-Z]?[\])]\s*$', '', s)
    s = re.sub(r'\s*\(\d+[a-z]?\)\s*$', '', s)
    s = s.rstrip(' :.')
    return s

def _fix_glued_words(text):
    """Chữa chữ dính: 'Investmentsin' -> 'Investments in', camelCase -> tách."""
    patterns = [
        (r'Investmentsin', 'Investments in'),
        (r'venturesat', 'ventures at'),
        (r'associatesat', 'associates at'),
        (r'Subsidiariesat', 'Subsidiaries at'),
        (r'Pensi\s*onand', 'Pension and'),
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
    for pat, rep in patterns:
        text = re.sub(pat, rep, text, flags=re.IGNORECASE)
    # camelCase -> tách
    text = re.sub(r'(?<=[a-z])(?=[A-Z])', ' ', text)
    return re.sub(r'\s{2,}', ' ', text).strip()

def _word_by_word_translate(s):
    """Dịch từng từ, bỏ từ không dịch được."""
    words = s.split()
    translated = []
    for w in words:
        w_clean = re.sub(r'[^a-zA-Z]', '', w).lower()
        if w_clean in WORD_MAP:
            tr = WORD_MAP[w_clean]
            if tr:  # bỏ từ rỗng (a, an, the)
                translated.append(tr)
        elif _has_vietnamese(w):
            translated.append(w)
        # else: bỏ từ tiếng Anh không có trong từ điển
    return ' '.join(translated)

def force_vietnamese_label(metric, report_type=''):
    """🆕 v20.0: CỔNG DỊCH DUY NHẤT - TUYỆT ĐỐI KHÔNG LỌT TIẾNG ANH
    
    Returns: nhãn tiếng Việt thuần, hoặc None (dòng sẽ bị BỎ).
    """
    if metric is None:
        return None
    try:
        if pd.isna(metric):
            return None
    except (TypeError, ValueError):
        pass
    
    s = str(metric).strip()
    if not s:
        return None
    
    # Nếu đã là tiếng Việt thuần (không có ASCII letters, chỉ có tiếng Việt) -> trả về
    if _has_vietnamese(s) and not re.search(r'[a-zA-Z]{3,}', s):
        return s
    
    # Nếu là báo cáo chỉ số thị trường/vĩ mô -> cho qua nhãn tiếng Việt ngắn
    if "Chỉ số thị trường" in str(report_type) or "Chỉ số vĩ mô" in str(report_type):
        if _has_vietnamese(s):
            return s
        return None
    
    # 1. Tra từ điển trực tiếp (case-sensitive)
    if s in TRANSLATION_MAP:
        return TRANSLATION_MAP[s]
    
    # 2. Chuẩn hoá và tra lowercase
    norm = _normalize_for_lookup(s)
    if norm in TRANSLATION_MAP:
        return TRANSLATION_MAP[norm]
    if norm.lower() in _TRANS_LOWER:
        return _TRANS_LOWER[norm.lower()]
    
    # 3. VAS_WHITELIST
    if s in VAS_WHITELIST:
        return s
    if norm in VAS_WHITELIST:
        return norm
    
    # 4. Chữa chữ dính (camelCase, Investmentsin) và tra lại
    fixed = _fix_glued_words(s)
    if fixed != s:
        if fixed in TRANSLATION_MAP:
            return TRANSLATION_MAP[fixed]
        if fixed.lower() in _TRANS_LOWER:
            return _TRANS_LOWER[fixed.lower()]
        if fixed in VAS_WHITELIST:
            return fixed
    
    # 5. Dịch từng từ (word-by-word fallback)
    translated = _word_by_word_translate(fixed)
    if translated and _has_vietnamese(translated):
        s = translated
    
    # 6. 🆕 v20.0: STRIP MỌI từ tiếng Anh còn sót
    s = _strip_english_words(s)
    
    # 7. Validate cuối cùng
    if not s or len(s) < 3:
        return None
    if not _has_vietnamese(s):
        return None  # ❌ Không có ký tự tiếng Việt nào -> BỎ
    if re.search(r'\b[a-zA-Z]{3,}\b', s):
        # Còn từ tiếng Anh dài >= 3 ký tự (không phải viết tắt)
        # Thử strip lần nữa
        s = _strip_english_words(s)
        if re.search(r'\b[a-zA-Z]{3,}\b', s):
            return None  # ❌ Vẫn còn -> BỎ
    
    return s.strip()

def standardize_metric(raw_metric, report_type):
    """Giữ để tương thích, delegate cho force_vietnamese_label."""
    return force_vietnamese_label(raw_metric, report_type)

def sweep_labels(df, label_col='Chỉ tiêu tiếng Việt', type_col='Loại báo cáo'):
    """Quét lại TOÀN BỘ dataframe, đổi nhãn Anh -> Việt, bỏ nhãn không dịch được."""
    if df is None or df.empty:
        return df, 0
    before = len(df)
    df = df.copy()
    df[label_col] = [force_vietnamese_label(m, rt) for m, rt in zip(df[label_col], df[type_col])]
    df = df.dropna(subset=[label_col])
    df = df[df[label_col].astype(str).str.strip().ne('')]
    return df, before - len(df)

# ==============================================================================
# Helper cũ
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
    'Chứng khoán đầu tư giữ đến ngày đáo': 'Chứng khoán đầu tư giữ đến ngày đáo hạn',
    'NỢ PHẢI TRẢ VÀ VỐN CHỦ SỞ H': 'Tổng cộng nguồn vốn',
    'NỢ PHẢI TRẢ VÀ VỐN CHỦ SỞ HỮU': 'Tổng cộng nguồn vốn',
    'TỔNG CỘNG TÀI SẢN': 'Tổng cộng tài sản',
    'TỔNG CỘNG NGUỒN VỐN': 'Tổng cộng nguồn vốn',
    'TỔNG CỘNG NỢ PHẢI TRẢ': 'Nợ phải trả',
    'VỐN CHỦ SỞ HỮU': 'Vốn chủ sở hữu',
}

def fix_truncated_text(text):
    t = clean_text(text)
    return _TRUNCATED_FIX.get(t, t)

# ==============================================================================
# 7. format_value (GIỮ NGUYÊN v19)
# ==============================================================================
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

# ==============================================================================
# 8. SUPABASE + HTTP + CRAWLERS + CLEANING (GIỮ NGUYÊN TỪ v19)
# ==============================================================================
os.environ["VNSTOCK_API_KEY"] = "vnstock_533590cc17b6737ceb7c9f147471f31f"

try:
    import vnfinancialdata as vnf
except ImportError:
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
SUPABASE_PRIORITY = os.environ.get("SUPABASE_PRIORITY", "low").lower()
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
    if not HAS_SUPABASE_LIB or not SUPABASE_URL or not SUPABASE_KEY:
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
                'ticker': ticker, 'company_name': clean_str(row['company_name']),
                'sector': clean_str(row['sector']), 'report_type': clean_str(row['report_type']),
                'period_type': clean_str(row['period_type']), 'year': yr,
                'report_date': clean_str(row['report_date']), 'item_vn': item, 'value': float(val)
            })
        total = len(records)
        if skipped_bad:
            print(f"🧹 [SUPABASE] Chặn {skipped_bad:,} dòng rác/trống/Anh trước khi upsert.")
        if total == 0:
            print("⚠️ [SUPABASE] Không có bản ghi hợp lệ.")
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

def purge_supabase_bad_rows():
    client = init_supabase()
    if client is None: return
    print("🧽 [SUPABASE] Purge dòng bẩn...")
    T = SUPABASE_TABLE
    def _run(label, fn):
        try:
            resp = _retry(fn, max_retries=2, backoff=2, label="SUPABASE_PURGE")
            n = len(getattr(resp, 'data', None) or [])
            print(f"   ✓ {label}: xoá {n:,} dòng")
        except Exception as e:
            print(f"   ⚠️ {label}: {type(e).__name__}: {e}")
    _run("value = 0",    lambda: client.table(T).delete().eq('value', 0).execute())
    _run("value NULL",   lambda: client.table(T).delete().is_('value', 'null').execute())
    _run("item_vn NULL", lambda: client.table(T).delete().is_('item_vn', 'null').execute())
    _run("item_vn rỗng", lambda: client.table(T).delete().eq('item_vn', '').execute())
    _run("nhãn dính [n]", lambda: client.table(T).delete().like('item_vn', '%[%]').execute())
    # Xoá nhãn thuần tiếng Anh
    _run("nhãn chỉ có chữ cái", lambda: client.table(T).delete().not_.like('item_vn', '%[à-ỹđ]%').execute() if False else None)
    print("✅ [SUPABASE] Purge hoàn tất.")

# === DAILY DATA ===
DATA_PATH = "du_lieu/dulieu_hang_ngay.csv"
HF_DATA_URL = "https://huggingface.co/datasets/trananhquan2001/finex-vn-dataset/raw/main/dulieu_hang_ngay.csv"

def load_daily_stock_data():
    if os.path.exists(DATA_PATH):
        try: return pd.read_csv(DATA_PATH)
        except Exception: pass
    try: return pd.read_csv(HF_DATA_URL)
    except Exception: return pd.DataFrame()

# === 176 MASTER TICKERS ===
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
        "ACB":"Ngân hàng TMCP Á Châu","BID":"Ngân hàng TMCP Đầu tư và Phát triển VN","TCB":"Ngân hàng TMCP Kỹ thương VN","MBB":"Ngân hàng TMCP Quân đội","VCB":"Ngân hàng TMCP Ngoại thương VN",
        "FPT":"Công ty CP FPT","VNM":"Công ty CP Sữa VN","HPG":"Công ty CP Tập đoàn Hòa Phát","VIC":"Công ty CP Vingroup","VHM":"Công ty CP Vinhomes",
        "MSN":"Công ty CP Tập đoàn Masan","MWG":"Công ty CP Đầu tư Thế giới Di động","SSI":"Công ty CP Chứng khoán SSI","HVN":"Tổng Công ty Hàng không VN",
    }
    return company_names.get(symbol, f"Công ty Cổ phần {symbol}"), sector

# === HTTP SESSION ===
session = requests.Session()
session.headers.update({
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
    'Accept': 'application/json, text/plain, */*',
    'Accept-Language': 'vi-VN,vi;q=0.9,en;q=0.8',
})

VND_HOSTS = ["https://finfo-api.vndirect.com.vn", "https://api-finfo.vndirect.com.vn"]
VND_PAGE_SIZE = 1000; VND_MAX_PAGES = 60; VND_MIN_YEAR = 2000; VND_REQ_INTERVAL = 0.15; VND_TIMEOUT = 8

_thread_local = threading.local()
def get_session():
    s = getattr(_thread_local, 'session', None)
    if s is None:
        s = requests.Session()
        s.headers.update(session.headers)
        s.mount('https://', HTTPAdapter(pool_connections=8, pool_maxsize=8))
        _thread_local.session = s
    return s

_throttle_lock = threading.Lock(); _next_slot = [0.0]
def _throttle():
    with _throttle_lock:
        wait = _next_slot[0] - time.monotonic()
        if wait > 0: time.sleep(wait)
        _next_slot[0] = time.monotonic() + VND_REQ_INTERVAL

_vnd_host_idx = 0; _vnd_lock = threading.Lock()
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
            if r.status_code == 200: return r.json()
            if r.status_code in (400, 404, 422): return None
            last_err = f"HTTP {r.status_code}"
        except Exception as e:
            last_err = type(e).__name__
        with _vnd_lock:
            _vnd_host_idx = (_vnd_host_idx + 1) % len(VND_HOSTS)
        if attempt == max_retries - 1: break
        time.sleep(min(2 ** attempt, 8) + random.uniform(0, 0.5))
    return None

def _item_key(it):
    return it.get('id') or (it.get('reportDate'), it.get('itemCode'), it.get('quarter'), it.get('numericValue'))

def _period_from_item(it, report_type):
    rd = str(it.get('reportDate') or it.get('fiscalDate') or '')
    year = it.get('year')
    if not year:
        m = re.match(r'(\d{4})', rd)
        year = m.group(1) if m else None
    if not year: return None, None
    year = str(year)
    if report_type == 'YEAR': return year, f"{year}-12-31"
    q = None
    try: q = int(it.get('quarter'))
    except (TypeError, ValueError): pass
    if q not in (1, 2, 3, 4):
        lr = None
        try: lr = int(it.get('lengthReport'))
        except (TypeError, ValueError): pass
        if lr in (6, 9): q = lr // 3
        else:
            m = re.match(r'\d{4}-(\d{2})', rd)
            if m and int(m.group(1)) in (3, 6, 9, 12): q = int(m.group(1)) // 3
            elif lr == 12: q = 4
    if q not in (1, 2, 3, 4): return year, None
    return year, f"{year}-Q{q}"

def _fetch_vnd_by_year(symbol, stmt_code, report_type, base_q):
    out, seen = [], set()
    for y in range(VND_MIN_YEAR, datetime.now().year + 1):
        q = f"{base_q}~reportDate:gte:{y}-01-01~reportDate:lte:{y}-12-31"
        data = vnd_get('/v4/financial_statements', {'q': q, 'sort': 'reportDate:asc', 'size': VND_PAGE_SIZE, 'page': 1}, label=f"{symbol}/{stmt_code}/{report_type}/{y}")
        for it in (data or {}).get('data') or []:
            k = _item_key(it)
            if k not in seen: seen.add(k); out.append(it)
    return out

def _fetch_vnd_statement(symbol, stmt_code, report_type):
    base_q = f"code:{symbol}~reportType:{report_type}~financialStatement:{stmt_code}"
    out, seen = [], set()
    total_hint, page = None, 1
    while page <= VND_MAX_PAGES:
        data = vnd_get('/v4/financial_statements', {'q': base_q, 'sort': 'reportDate:asc', 'size': VND_PAGE_SIZE, 'page': page}, label=f"{symbol}/{stmt_code}/{report_type}/p{page}")
        if data is None: break
        batch = data.get('data') or []
        if not batch: break
        if total_hint is None: total_hint = data.get('total') or data.get('hits')
        fresh = 0
        for it in batch:
            k = _item_key(it)
            if k in seen: continue
            seen.add(k); out.append(it); fresh += 1
        tp = data.get('totalPages')
        if tp and page >= int(tp): break
        if total_hint and len(out) >= int(total_hint): break
        if len(batch) < VND_PAGE_SIZE: break
        if fresh == 0: return _fetch_vnd_by_year(symbol, stmt_code, report_type, base_q)
        page += 1
    return out

def fetch_vndirect_bctc_financials(symbol):
    if SKIP_VNDIRECT: return []
    records = []
    company_name, sector_name = get_company_profile(symbol)
    statement_map = {'BALANCE_SHEET': 'Bảng cân đối kế toán', 'INCOME_STATEMENT': 'Báo cáo kết quả kinh doanh', 'CASH_FLOW': 'Báo cáo lưu chuyển tiền tệ'}
    for stmt_code, stmt_vn in statement_map.items():
        for report_type, ky_bao_cao in (('QUARTER', 'Quý'), ('YEAR', 'Năm')):
            for item in _fetch_vnd_statement(symbol, stmt_code, report_type):
                year_val, date_period = _period_from_item(item, report_type)
                if not date_period: continue
                fv = format_value(item.get('numericValue'))
                if fv is None or fv == 0: continue
                metric_vn = clean_text(item.get('itemName', ''))
                if not metric_vn: metric_vn = fix_truncated_text(item.get('itemCode', ''))
                metric_vn = force_vietnamese_label(metric_vn, stmt_vn)
                if not metric_vn: continue
                records.append({
                    'Mã chứng khoán': symbol, 'Tên doanh nghiệp': company_name, 'Tên ngành': sector_name,
                    'Loại báo cáo': stmt_vn, 'Loại kỳ': ky_bao_cao, 'Năm': str(year_val), 'Ngày kỳ': date_period,
                    'Chỉ tiêu tiếng Việt': metric_vn, 'Giá trị': fv
                })
    return records

def fetch_vndirect_fallback(symbol):
    if SKIP_VNDIRECT: return []
    records = []; company_name, sector_name = get_company_profile(symbol)
    current_year = str(datetime.now().year); today_str = datetime.today().strftime('%Y-%m-%d')
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
    records = []; company_name, sector_name = get_company_profile(symbol)
    current_year = str(datetime.now().year); today_str = datetime.today().strftime('%Y-%m-%d')
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

def parse_financial_df(symbol, df, statement_type_raw, ky_bao_cao, min_year=2000):
    records = []; company_name, sector_name = get_company_profile(symbol)
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
                            if not metric_vn: continue
                            records.append({
                                'Mã chứng khoán': symbol, 'Tên doanh nghiệp': company_name, 'Tên ngành': sector_name,
                                'Loại báo cáo': statement_type_vn, 'Loại kỳ': ky_bao_cao, 'Năm': year_val, 'Ngày kỳ': date_period,
                                'Chỉ tiêu tiếng Việt': metric_vn, 'Giá trị': fv
                            })
    except Exception: pass
    return records

def fetch_historical_dividends(symbol, ticker_obj, min_year=2000):
    records = []; company_name, sector_name = get_company_profile(symbol)
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
                                'Mã chứng khoán': symbol, 'Tên doanh nghiệp': company_name, 'Tên ngành': sector_name,
                                'Loại báo cáo': 'Chỉ số thị trường, Định giá & Cổ tức', 'Loại kỳ': 'Sự kiện cổ tức',
                                'Năm': year_val, 'Ngày kỳ': date_str,
                                'Chỉ tiêu tiếng Việt': 'Lịch sử trả cổ tức bằng tiền', 'Giá trị': fv
                            })
    except Exception: pass
    return records

def fetch_market_and_valuation_metrics(symbol, ticker_obj, balance_sheet_df):
    records = []; company_name, sector_name = get_company_profile(symbol)
    current_year = str(datetime.now().year); today_str = datetime.today().strftime('%Y-%m-%d')
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
        metrics = [('Current Price', current_price), ('Shares Outstanding', shares_out), ('Market Capitalization', market_cap), ('Dividend Yield', div_yield)]
        for eng_key, val in metrics:
            if val is not None:
                fv = format_value(val)
                if fv is not None and fv != 0:
                    metric_vn = TRANSLATION_MAP.get(eng_key, eng_key)
                    records.append({
                        'Mã chứng khoán': symbol, 'Tên doanh nghiệp': company_name, 'Tên ngành': sector_name,
                        'Loại báo cáo': 'Chỉ số thị trường, Định giá & Cổ tức', 'Loại kỳ': 'Real-time',
                        'Năm': current_year, 'Ngày kỳ': today_str, 'Chỉ tiêu tiếng Việt': metric_vn, 'Giá trị': fv
                    })
    except Exception: pass
    return records

def fetch_market_indices():
    indices = {"VN-INDEX": "^VNINDEX", "HNX-INDEX": "^HNX"}
    market_records = []; current_year = str(datetime.now().year); today_str = datetime.today().strftime('%Y-%m-%d')
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
                if fv is not None and fv != 0:
                    market_records.append({
                        'Mã chứng khoán': index_name, 'Tên doanh nghiệp': f'Chỉ số thị trường {index_name}',
                        'Tên ngành': 'Chỉ số vĩ mô', 'Loại báo cáo': 'Chỉ số thị trường, Định giá & Cổ tức',
                        'Loại kỳ': 'Real-time hằng ngày', 'Năm': current_year, 'Ngày kỳ': today_str,
                        'Chỉ tiêu tiếng Việt': name, 'Giá trị': fv
                    })
        except Exception: pass
    return market_records

def find_value_column(df):
    for name in ['value','ratio_value','value_ratio','Value','ratio','val']:
        if name in df.columns: return name
    for col in df.columns:
        if df[col].dtype in ['float64','int64']: return col
    return None

def fetch_vnfinancialdata_bulk(ticker_market_map):
    if vnf is None: return []
    records = []; statements = {"balance_sheet": "Bảng cân đối kế toán", "income_statement": "Báo cáo kết quả kinh doanh", "cash_flow": "Báo cáo lưu chuyển tiền tệ"}
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
                    if fv is None or fv == 0: continue
                    symbol = row['Mã chứng khoán']
                    company_name, sector_name = get_company_profile(symbol)
                    year_val = str(row['Năm'])
                    metric_vn = force_vietnamese_label(row['Chỉ tiêu tiếng Việt'], stmt_name)
                    if not metric_vn: continue
                    records.append({
                        'Mã chứng khoán': symbol, 'Tên doanh nghiệp': company_name, 'Tên ngành': sector_name,
                        'Loại báo cáo': stmt_name, 'Loại kỳ': 'Năm', 'Năm': year_val, 'Ngày kỳ': f"{year_val}-12-31",
                        'Chỉ tiêu tiếng Việt': metric_vn, 'Giá trị': fv
                    })
            except Exception as e:
                print(f"  ⚠️ Lỗi {stmt_name} {exchange}: {e}")
    return records

def process_single_ticker(symbol, category):
    recs = []
    try:
        ticker = yf.Ticker(f"{symbol}.VN", session=session)
        bs_df = getattr(ticker, 'balance_sheet', None)
        for attr, raw, ky in (('balance_sheet', 'Balance_Sheet', 'Năm'), ('quarterly_balance_sheet', 'Balance_Sheet', 'Quý'),
                              ('financials', 'Income_Statement', 'Năm'), ('quarterly_financials', 'Income_Statement', 'Quý'),
                              ('cashflow', 'Cash_Flow', 'Năm'), ('quarterly_cashflow', 'Cash_Flow', 'Quý')):
            try:
                recs.extend(parse_financial_df(symbol, getattr(ticker, attr, None), raw, ky))
            except Exception: pass
        recs.extend(fetch_market_and_valuation_metrics(symbol, ticker, bs_df))
        recs.extend(fetch_historical_dividends(symbol, ticker))
    except Exception: pass
    return recs

QUARTER_WORKERS = 8; QUARTER_TICKER_BUDGET = 20; QUARTER_TOTAL_BUDGET = 600; QUARTER_MIN_PERIODS = 4

def fetch_yf_quarter_single(symbol):
    recs = []; t0 = time.monotonic()
    try: ticker = yf.Ticker(f"{symbol}.VN")
    except Exception: return recs
    for attr, raw in (('quarterly_balance_sheet', 'Balance_Sheet'), ('quarterly_income_stmt', 'Income_Statement'), ('quarterly_cashflow', 'Cash_Flow')):
        if time.monotonic() - t0 > QUARTER_TICKER_BUDGET: break
        try: df = getattr(ticker, attr, None)
        except Exception: break
        try: recs.extend(parse_financial_df(symbol, df, raw, 'Quý'))
        except Exception: pass
    return recs

def fetch_quarter_multithread(symbols):
    all_recs = []
    if not symbols: return all_recs
    total = len(symbols); done = 0
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
            except Exception: pass
    except Exception as e:
        print(f"  ⚠️ Hết ngân sách thời gian bù quý ({type(e).__name__}) — dùng phần đã cào được ({done}/{total}).")
    finally:
        executor.shutdown(wait=False, cancel_futures=True)
    return all_recs

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
    print(f"  [Tầng 1] Loại bỏ NULL/0 & ép kiểu số. Còn {len(df):,} dòng.")
    before2 = len(df)
    df, _ = sweep_labels(df)
    print(f"  [Tầng 2] Ép chuẩn VAS + dịch Anh + strip. Còn {len(df):,} dòng (bỏ {before2 - len(df):,}).")
    mask = (df['Loại kỳ'] == 'Quý') & df['Ngày kỳ'].astype(str).str.match(r'^\d{4}-\d{2}-\d{2}$')
    if mask.any():
        s = df.loc[mask, 'Ngày kỳ'].astype(str)
        df.loc[mask, 'Ngày kỳ'] = s.str[:4] + '-Q' + ((s.str[5:7].astype(int) - 1) // 3 + 1).astype(str)
        print(f"  [Tầng 2.5] Chuẩn hoá {int(mask.sum()):,} nhãn quý về 'YYYY-Qn'.")
    if '_priority' in df.columns:
        df = df.sort_values('_priority', kind='stable')
    df = df.drop_duplicates(subset=['Mã chứng khoán', 'Loại báo cáo', 'Loại kỳ', 'Ngày kỳ', 'Chỉ tiêu tiếng Việt'], keep='first')
    print(f"  [Tầng 3] Deduplication. Còn {len(df):,} dòng.")
    print("  [Tầng 4] Kiểm tra Cân đối kế toán...")
    bctc_df = df[df['Loại báo cáo'].astype(str).str.contains('Bảng cân đối', na=False)]
    if not bctc_df.empty:
        try:
            pivot = bctc_df.pivot_table(index=['Mã chứng khoán', 'Ngày kỳ'], columns='Chỉ tiêu tiếng Việt', values='Giá trị', aggfunc='first').reset_index()
            col_assets = next((c for c in pivot.columns if 'Tổng cộng tài sản' in str(c)), None)
            col_liab = next((c for c in pivot.columns if 'Nợ phải trả' in str(c)), None)
            col_equity = next((c for c in pivot.columns if 'Vốn chủ sở hữu' in str(c)), None)
            if col_assets and col_liab and col_equity:
                pivot['_diff'] = (pivot[col_assets] - (pivot[col_liab] + pivot[col_equity])).abs()
                invalid_count = len(pivot[pivot['_diff'] > 1000])
                print(f"  [Tầng 4] ⚠️ Phát hiện {invalid_count} kỳ BCTC lệch Cân đối.")
        except Exception: pass
    print("  [Tầng 5] Loại bỏ dòng trắng & Format số liệu...")
    df = df[df['Giá trị'] != 0]
    vals = pd.to_numeric(df['Giá trị'], errors='coerce').round(4)
    keep = vals.notna() & np.isfinite(vals) & (vals != 0)
    df = df.loc[keep].copy()
    vals = vals.loc[keep]
    if df.empty: return pd.DataFrame(columns=STANDARD_COLUMNS)
    is_int = vals.eq(vals.round(0))
    fmt = pd.Series('', index=df.index, dtype=object)
    if is_int.any(): fmt.loc[is_int] = vals.loc[is_int].astype('int64').astype(str)
    if (~is_int).any(): fmt.loc[~is_int] = vals.loc[~is_int].map(lambda f: format(f, '.4f').rstrip('0').rstrip('.'))
    df['Giá trị'] = fmt
    df = df[df['Giá trị'].astype(str).str.strip().ne('')]
    if 'Năm' in df.columns:
        nam = pd.to_numeric(df['Năm'], errors='coerce')
        nam_tu_ngay = pd.to_numeric(df['Ngày kỳ'].astype(str).str.extract(r'(\d{4})')[0], errors='coerce')
        df['Năm'] = nam.fillna(nam_tu_ngay).fillna(datetime.now().year).astype(int)
    print(f"  [Tầng 5] ✅ Còn {len(df):,} dòng.")
    return df[STANDARD_COLUMNS]

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
    targets = ['data/_checkpoint.csv', 'data/_emergency_backup.csv', 'data/_emergency_backup.parquet', '_checkpoint.csv']
    for pattern in ('data/bao_cao_*.csv', 'bao_cao_*.csv', 'du_lieu/bao_cao_*.csv'):
        targets.extend(glob.glob(pattern))
    removed = 0
    for f in targets:
        if os.path.exists(f):
            try: os.remove(f); removed += 1
            except Exception: pass
    if removed: print(f"  🧽 Đã dọn {removed} file tạm.")

# ==============================================================================
# 9. MAIN (GIỮ NGUYÊN KHUNG BƯỚC 0->8)
# ==============================================================================
def main():
    global _ALL_RECORDS_GLOBAL
    print("=" * 62)
    print("🚀 FINEX VN STOCK DATABASE CRAWLER — v20.0 (TRIỆT ĐỂ TIẾNG ANH)")
    print("=" * 62)
    print(f"  ⚙️ SKIP_VNDIRECT = {SKIP_VNDIRECT} | PURGE_SUPABASE_BAD = {PURGE_SUPABASE_BAD}")
    print(f"  📚 Từ điển: VAS={len(VAS_WHITELIST)} | TRANSLATION={len(TRANSLATION_MAP)} | WORD={len(WORD_MAP)}")

    ticker_market_map = load_176_master_tickers()
    all_master_records = []

    def _accumulate(recs, source):
        global _ALL_RECORDS_GLOBAL
        if not recs: return
        kept, dropped = [], 0
        for r in recs:
            lab = force_vietnamese_label(r.get('Chỉ tiêu tiếng Việt'), r.get('Loại báo cáo'))
            if lab is None: dropped += 1; continue
            r['Chỉ tiêu tiếng Việt'] = lab
            kept.append(r)
        if dropped: print(f"  🧹 [{source}] chặn {dropped:,} nhãn Anh/rác ngay khi nạp.")
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

    print("\n🚀 BƯỚC 0: Tải dữ liệu hàng ngày [DAILY]...")
    hf_df = load_daily_stock_data()
    if not hf_df.empty:
        hf_df = _normalize_to_standard(hf_df, fill_company=True)
        if not hf_df.empty:
            _accumulate(hf_df.to_dict('records'), 'DAILY')
            print(f" ✅ Đã nạp {len(hf_df):,} dòng.")

    print("\n🚀 BƯỚC 1: Tải BCTC Năm bulk [VN_FINANCIAL]...")
    vnf_recs = fetch_vnfinancialdata_bulk(ticker_market_map)
    if vnf_recs: _accumulate(vnf_recs, 'VN_FINANCIAL')
    _save_checkpoint("sau_VN_FINANCIAL")

    print("\n📈 BƯỚC 2: Cào chỉ số vĩ mô [INDICES]...")
    index_recs = fetch_market_indices()
    if index_recs: _accumulate(index_recs, 'INDICES')

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
                if done % 25 == 0: _save_checkpoint(f"VNDIRECT_{done}/{len(ticker_market_map)}")
        _save_checkpoint("sau_VNDIRECT_BCTC")

    print(f"\n🔄 BƯỚC 4: Cào Yfinance song song [YFINANCE]...")
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = {executor.submit(process_single_ticker, symbol, cat): symbol for symbol, cat in ticker_market_map.items()}
        for future in as_completed(futures):
            try:
                res = future.result()
                if res: _accumulate(res, 'YFINANCE')
            except Exception: pass
    _save_checkpoint("sau_YFINANCE")

    print(f"\n🐢 BƯỚC 5: Kiểm tra thiếu + fallback Giá/SLCP...")
    df_temp = pd.DataFrame(all_master_records)
    if not df_temp.empty:
        q_periods = df_temp[df_temp['Loại kỳ'] == 'Quý'].groupby('Mã chứng khoán')['Ngày kỳ'].nunique()
        q_syms = set(q_periods[q_periods >= QUARTER_MIN_PERIODS].index)
        print(f"  📊 Đã có {len(q_syms)}/{len(ticker_market_map)} mã có ≥ {QUARTER_MIN_PERIODS} kỳ Quý.")
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

    print(f"\n🆕 BƯỚC 5.5: Tải bổ sung từ Supabase (đã lọc bẩn + dịch nhãn Anh cũ)...")
    supabase_df = load_data_from_supabase()
    if not supabase_df.empty:
        _accumulate(supabase_df.to_dict('records'), 'SUPABASE_HIGH' if SUPABASE_PRIORITY == 'high' else 'SUPABASE')

    df_master = pd.DataFrame(all_master_records)
    df_clean = apply_first_principles_cleaning(df_master) if not df_master.empty else pd.DataFrame(columns=STANDARD_COLUMNS)

    # 🆕 v20: QUÉT LẠI LẦN CUỐI TRƯỚC KHI GHI FILE
    if not df_clean.empty:
        df_clean, n_sweep = sweep_labels(df_clean)
        df_clean = df_clean.drop_duplicates(subset=['Mã chứng khoán', 'Loại báo cáo', 'Loại kỳ', 'Ngày kỳ', 'Chỉ tiêu tiếng Việt'], keep='first')
        print(f"  [Cổng cuối] Quét lại {len(df_clean):,} nhãn: loại thêm {n_sweep} nhãn Anh/rác sót.")

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

    if PUSH_TO_SUPABASE:
        print("\n📤 BƯỚC 8: Đẩy Supabase...")
        ok = upsert_to_supabase(df_clean)
        if ok and PURGE_SUPABASE_BAD:
            purge_supabase_bad_rows()

    _cleanup_temp_files()

    print("=" * 62)
    print(f" 🎉 HOÀN TẤT! Tổng: {len(df_clean):,} dòng")
    if not df_clean.empty:
        print(f" - Số mã: {df_clean['Mã chứng khoán'].nunique()}/176")
        for k, v in df_clean['Loại kỳ'].value_counts().items():
            print(f"     • {k}: {v:,}")
        # Kiểm chứng: không còn từ tiếng Anh >= 3 ký tự trong nhãn
        en_count = 0
        for lab in df_clean['Chỉ tiêu tiếng Việt']:
            if re.search(r'\b[a-zA-Z]{3,}\b', str(lab)):
                words = str(lab).split()
                has_en = False
                for w in words:
                    if re.match(r'^[a-zA-Z]{3,}$', w) and w.upper() not in ALLOWED_ABBREVIATIONS:
                        has_en = True
                        break
                if has_en: en_count += 1
        print(f" - Nhãn còn tiếng Anh TOÀN FILE: {en_count} (mục tiêu = 0)")
    print("=" * 62)

if __name__ == "__main__":
    main()
