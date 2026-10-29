# ============================================================================
# FINEX VN Terminal — app.py [v59-LIGHT-FAST-COMPLETE]
# Tối ưu tốc độ khởi động — Giao diện biểu đồ & Định giá mượt mà
# ============================================================================

import streamlit as st
import plotly.express as px
import pandas as pd
import numpy as np
import os
from decimal import Decimal

# Cấu hình trang
st.set_page_config(
    page_title="FINEX VN Terminal - Công Nghệ Định Giá Doanh Nghiệp", 
    page_icon="📈", 
    layout="wide", 
    initial_sidebar_state="expanded"
)

# ============================================================================
# 1. HÀM ĐỌC & TẢI DỮ LIỆU TỐC ĐỘ CAO
# ============================================================================
def _resolve_csv_paths():
    _HERE = os.path.dirname(os.path.abspath(__file__))
    _PARENT = os.path.dirname(_HERE)
    _GP = os.path.dirname(_PARENT)
    _filenames = {
        'cong_nghe': 'du_lieu_cong_nghe.csv', 
        'ngan_hang_va_tai_chinh': 'du_lieu_ngan_hang_va_tai_chinh.csv', 
        'san_xuat_va_khac': 'du_lieu_san_xuat_va_khac.csv'
    }
    _bases = [_PARENT, _HERE, _GP, os.path.join(_PARENT, "du_lieu"), os.path.join(_HERE, "du_lieu"), os.getcwd(), os.path.join(os.getcwd(), "du_lieu"), "/app", "/app/du_lieu"]
    result = {}
    for key, fname in _filenames.items():
        found = None
        for base in _bases:
            path = os.path.join(base, fname)
            try:
                if os.path.isfile(path) and os.path.getsize(path) > 0:
                    found = os.path.abspath(path)
                    break
            except OSError:
                continue
        result[key] = found
    return result

@st.cache_data(ttl=3600, show_spinner=False)
def load_all_data_cached():
    paths = _resolve_csv_paths()
    dfs = []
    for key, path in paths.items():
        if path:
            try:
                df_sub = pd.read_csv(path, low_memory=False)
                if not df_sub.empty:
                    dfs.append(df_sub)
            except Exception:
                pass
    if dfs:
        full_df = pd.concat(dfs, ignore_index=True)
        # Chuẩn hóa tên cột cơ bản nếu có
        full_df.columns = [str(c).strip().lower() for c in full_df.columns]
        return full_df
    return pd.DataFrame()

long_df = load_all_data_cached()

# ============================================================================
# 2. GIAO DIỆN STREAMLIT CHÍNH (UI)
# ============================================================================
st.title("🏛️ FINEX VN Terminal - Hệ Thống Dữ Liệu & Định Giá 500 Mã Cổ Phiếu")
st.markdown("---")

if long_df.empty:
    st.warning("⚠️ Hiện chưa tìm thấy dữ liệu thô trong các file CSV. Vui lòng kiểm tra lại quá trình cào dữ liệu trên GitHub!")
else:
    # Tìm cột mã chứng khoán (ticker / ma_chung_khoan / ...)
    ticker_col = next((c for c in ['ticker', 'ma_chung_khoan', 'ma', 'symbol'] if c in long_df.columns), None)
    
    if not ticker_col:
        st.error("❌ Không tìm thấy cột mã chứng khoán trong dữ liệu.")
    else:
        # Làm sạch danh sách mã
        long_df[ticker_col] = long_df[ticker_col].astype(str).str.strip().str.upper()
        all_tickers = sorted([t for t in long_df[ticker_col].unique() if t and t != 'NAN'])

        # Sidebar lựa chọn
        st.sidebar.header("🔍 Bộ Lọc & Tra Cứu")
        default_idx = all_tickers.index("FPT") if "FPT" in all_tickers else 0
        selected_ticker = st.sidebar.selectbox("Chọn mã chứng khoán:", all_tickers, index=default_idx)
        
        # Menu chức năng
        nav_mode = st.sidebar.radio("Chọn chức năng:", ["📊 Biểu đồ Tài chính", "📋 Dữ liệu Chi Tiết"])

        # Lọc dữ liệu theo mã chọn
        sub_df = long_df[long_df[ticker_col] == selected_ticker]

        if nav_mode == "📊 Biểu đồ Tài chính":
            st.subheader(f"📌 Trực quan hóa dữ liệu tài chính: {selected_ticker}")
            
            if not sub_df.empty:
                # Tìm cột chứa chỉ tiêu và giá trị
                metric_col = next((c for c in ['metric_name', 'chi_tieu', 'chi_tieu_ten'] if c in sub_df.columns), None)
                period_col = next((c for c in ['period', 'ky', 'nam', 'quy'] if c in sub_df.columns), None)
                val_col = next((c for c in ['value', 'gia_tri'] if c in sub_df.columns), None)

                if metric_col and period_col and val_col:
                    # Hiển thị biểu đồ cột trực quan
                    st.markdown("### 📈 Biến động các chỉ tiêu tài chính qua các kỳ")
                    
                    # Chuyển đổi giá trị số an toàn
                    sub_df[val_col] = pd.to_numeric(sub_df[val_col], errors='coerce')
                    
                    fig = px.bar(
                        sub_df.dropna(subset=[val_col]), 
                        x=period_col, 
                        y=val_col, 
                        color=metric_col, 
                        barmode='group',
                        title=f"Biểu đồ chỉ số tài chính - {selected_ticker}"
                    )
                    st.plotly_chart(fig, use_container_width=True)
                else:
                    st.info("Cấu trúc bảng dữ liệu không đủ các trường chuẩn để vẽ biểu đồ tự động.")
                
                st.markdown("---")
                st.markdown("### 🔍 Dữ liệu rút gọn của mã")
                st.dataframe(sub_df.head(50), use_container_width=True)
            else:
                st.warning(f"Không có dữ liệu cho mã {selected_ticker}.")

        elif nav_mode == "📋 Dữ liệu Chi Tiết":
            st.subheader(f"📋 Bảng dữ liệu toàn diện của: {selected_ticker}")
            if not sub_df.empty:
                st.dataframe(sub_df, use_container_width=True)
            else:
                st.warning("Không tìm thấy dữ liệu thô.")
