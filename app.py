# ============================================================================
# FINEX VN Terminal — app.py [v60-ULTRA-CLEAN]
# Chỉ đọc trực tiếp 3 file CSV gốc từ GitHub — Giao diện mượt mà, không rườm rà
# ============================================================================

import streamlit as st
import pandas as pd
import plotly.express as px
import os

# Cấu hình giao diện Streamlit
st.set_page_config(
    page_title="FINEX VN Terminal", 
    page_icon="📈", 
    layout="wide", 
    initial_sidebar_state="expanded"
)

st.title("🏛️ FINEX VN Terminal - Quản Trị Dữ Liệu Cổ Phiếu")
st.markdown("---")

# ============================================================================
# 1. HÀM TÌM VÀ ĐỌC TRỰC TIẾP 3 FILE CSV TRÊN GITHUB
# ============================================================================
@st.cache_data(ttl=3600, show_spinner=False)
def load_raw_csv_data():
    _HERE = os.path.dirname(os.path.abspath(__file__))
    _PARENT = os.path.dirname(_HERE)
    
    # 3 file CSV gốc theo đúng tên bạn đang lưu trên GitHub
    file_names = [
        'du_lieu_cong_nghe.csv', 
        'du_lieu_ngan_hang_va_tai_chinh.csv', 
        'du_lieu_san_xuat_va_khac.csv'
    ]
    
    search_dirs = [_PARENT, _HERE, os.getcwd(), "/app", "/app/du_lieu"]
    
    all_dfs = []
    for fname in file_names:
        found_path = None
        for d in search_dirs:
            path = os.path.join(d, fname)
            if os.path.isfile(path) and os.path.getsize(path) > 0:
                found_path = path
                break
        
        if found_path:
            try:
                df_temp = pd.read_csv(found_path, low_memory=False)
                if not df_temp.empty:
                    all_dfs.append(df_temp)
            except Exception:
                pass
                
    if all_dfs:
        combined = pd.concat(all_dfs, ignore_index=True)
        # Chuẩn hóa toàn bộ tên cột về dạng chữ thường, không dấu/khoảng trắng thừa
        combined.columns = [str(c).strip().lower() for c in combined.columns]
        return combined
        
    return pd.DataFrame()

# Tải dữ liệu vào bộ nhớ đệm
df_master = load_raw_csv_data()

# ============================================================================
# 2. XÂY DỰNG GIAO DIỆN TRỰC QUAN
# ============================================================================
if df_master.empty:
    st.error("❌ Không tìm thấy hoặc không đọc được 3 file CSV gốc trên GitHub. Vui lòng kiểm tra lại vị trí các file CSV!")
else:
    # Tự động nhận diện cột mã chứng khoán
    ticker_col = next((c for c in ['ticker', 'ma', 'symbol', 'ma_ck', 'ma_chung_khoan'] if c in df_master.columns), None)
    
    if not ticker_col:
        st.error(f"❌ Dữ liệu CSV không chứa cột mã chứng khoán hợp lệ. Các cột hiện có: {list(df_master.columns)}")
    else:
        # Làm sạch mã chứng khoán
        df_master[ticker_col] = df_master[ticker_col].astype(str).str.strip().str.upper()
        tickers_list = sorted([t for t in df_master[ticker_col].unique() if t and t != 'NAN'])
        
        # --- Sidebar ---
        st.sidebar.header("🔍 Tra Cứu Cổ Phiếu")
        default_index = tickers_list.index("FPT") if "FPT" in tickers_list else 0
        selected_ticker = st.sidebar.selectbox("Chọn mã chứng khoán:", tickers_list, index=default_index)
        
        # Lọc dữ liệu theo mã người dùng chọn
        df_ticker = df_master[df_master[ticker_col] == selected_ticker]
        
        # --- Main Screen ---
        st.subheader(f"📊 Dữ liệu chi tiết mã: **{selected_ticker}**")
        st.info(f"Tổng số bản ghi tìm thấy: **{len(df_ticker):,}** dòng.")
        
        if not df_ticker.empty:
            # Hiển thị bảng dữ liệu thô
            st.markdown("### 📋 Bảng số liệu gốc")
            st.dataframe(df_ticker, use_container_width=True)
            
            # Tự động vẽ biểu đồ nếu có cột kỳ báo cáo (period) và giá trị (value)
            period_col = next((c for c in ['period', 'ky', 'nam', 'quy', 'ky_bao_cao'] if c in df_ticker.columns), None)
            metric_col = next((c for c in ['metric_name', 'chi_tieu', 'chi_tieu_ten'] if c in df_ticker.columns), None)
            value_col = next((c for c in ['value', 'gia_tri'] if c in df_ticker.columns), None)
            
            if period_col and metric_col and value_col:
                st.markdown("---")
                st.markdown(f"### 📈 Biểu đồ trực quan các chỉ tiêu của {selected_ticker}")
                
                df_ticker[value_col] = pd.to_numeric(df_ticker[value_col], errors='coerce')
                
                fig = px.bar(
                    df_ticker.dropna(subset=[value_col]),
                    x=period_col,
                    y=value_col,
                    color=metric_col,
                    barmode='group',
                    title=f"Biểu đồ chỉ số tài chính - {selected_ticker}"
                )
                st.plotly_chart(fig, use_container_width=True)
        else:
            st.warning(f"Không có dữ liệu cho mã {selected_ticker}.")
