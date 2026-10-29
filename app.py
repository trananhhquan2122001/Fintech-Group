import streamlit as st
import pandas as pd
import plotly.express as px
import os

# 1. Cấu hình giao diện tổng thể
st.set_page_config(
    page_title="FINEX VN Terminal — Enterprise Intelligence", 
    page_icon="🏛️", 
    layout="wide",
    initial_sidebar_state="expanded"
)

# Tùy chỉnh CSS giao diện phong cách Bloomberg Terminal / Dark Financial UI
st.markdown("""
    <style>
        .main { background-color: #0b0f19; color: #f3f4f6; }
        [data-testid="stSidebar"] { background-color: #111827; border-right: 1px solid #1f2937; }
        .metric-card {
            background-color: #1f2937;
            border: 1px solid #374151;
            padding: 18px;
            border-radius: 12px;
            box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
        }
        h1, h2, h3 { color: #60a5fa !important; font-family: 'Inter', sans-serif; }
        .stSelectbox, .stMultiSelect, .stTextInput { border-radius: 8px; }
    </style>
""", unsafe_allow_html=True)

# Tiêu đề hệ thống
st.title("🏛️ FINEX VN Terminal — Nền Tảng Tài Chính Định Lượng")
st.markdown("Hệ thống khai thác, trực quan hóa và phân tích dữ liệu tài chính doanh nghiệp chuẩn mực dành cho thế hệ nhà đầu tư mới.")
st.markdown("---")

# ============================================================================
# 2. HÀM TẢI DỮ LIỆU ĐẢM BẢO AN TOÀN ĐƯỜNG DẪN
# ============================================================================
@st.cache_data(ttl=3600, show_spinner=False)
def load_database():
    possible_paths = [
        "data/vietnam_stock_database_tong_hop.csv",
        "vietnam_stock_database_tong_hop.csv",
        "../data/vietnam_stock_database_tong_hop.csv"
    ]
    
    for path in possible_paths:
        if os.path.exists(path) and os.path.getsize(path) > 0:
            try:
                df_load = pd.read_csv(path, low_memory=False)
                return df_load
            except Exception:
                continue
    return pd.DataFrame()

df = load_database()

# ============================================================================
# 3. XỬ LÝ GIAO DIỆN & LOGIC NGHIỆP VỤ
# ============================================================================
if df.empty:
    st.warning("⚠️ Hiện chưa tìm thấy file cơ sở dữ liệu tổng hợp tại thư mục `data/`. Hãy kiểm tra lại tiến trình GitHub Actions trên kho của bạn!")
else:
    # Chuẩn hóa tên cột không phân biệt chữ hoa/thường
    col_map = {str(c).strip().lower(): c for c in df.columns}
    
    ticker_col = col_map.get('mã chứng khoán')
    industry_col = col_map.get('tên ngành')
    period_col = col_map.get('năm') or col_map.get('ngày kỳ')
    metric_col = col_map.get('chỉ tiêu tiếng việt')
    value_col = col_map.get('giá trị')

    if not ticker_col or not metric_col or not value_col:
        st.error(f"❌ Cấu trúc cột dữ liệu không khớp. Các cột hiện có: {list(df.columns)}")
    else:
        # Làm sạch dữ liệu mã chứng khoán và ngành
        df[ticker_col] = df[ticker_col].astype(str).str.strip().str.upper()
        if industry_col:
            df[industry_col] = df[industry_col].astype(str).str.strip()

        all_tickers = sorted([t for t in df[ticker_col].unique() if t and t != 'NAN'])

        # --- SIDEBAR: BỘ LỌC ĐIỀU HƯỚNG THÔNG MINH ---
        st.sidebar.header("🎯 Bộ Lọc & Tra Cứu")
        
        # Bộ lọc theo ngành nếu có cột ngành
        selected_industry = "Tất cả"
        if industry_col:
            industries = ["Tất cả"] + sorted([i for i in df[industry_col].unique() if i and i != 'NAN'])
            selected_industry = st.sidebar.selectbox("🏢 Chọn nhóm ngành:", industries)
            
            if selected_industry != "Tất cả":
                filtered_df = df[df[industry_col] == selected_industry]
                all_tickers = sorted(filtered_df[ticker_col].unique())

        # Chọn mã chứng khoán
        default_idx = all_tickers.index("FPT") if "FPT" in all_tickers else 0
        if default_idx >= len(all_tickers): 
            default_idx = 0
            
        selected_ticker = st.sidebar.selectbox("📈 Chọn mã cổ phiếu:", all_tickers, index=default_idx)
        
        st.sidebar.markdown("---")
        st.sidebar.info(f"💡 **Hệ thống:** Đang quản lý `{len(all_tickers)}` mã trong phân khúc lựa chọn.")

        # Lọc dữ liệu theo mã được chọn
        df_sub = df[df[ticker_col] == selected_ticker]
        
        # Lấy thông tin ngành của mã đang chọn
        company_industry = df_sub[industry_col].iloc[0] if industry_col and not df_sub.empty else "Đang cập nhật"

        # --- MAIN DISPLAY: KHU VỰC THÔNG TIN TỔNG QUAN ---
        st.subheader(f"📊 Hồ Sơ Doanh Nghiệp: **{selected_ticker}**")
        st.caption(f"🏢 Nhóm ngành: **{company_industry}**")
        
        # Thẻ KPI Metrics hiện đại
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric(label="Tổng bản ghi dữ liệu", value=f"{len(df_sub):,}")
        with col2:
            unique_periods = df_sub[period_col].nunique() if period_col else 0
            st.metric(label="Số kỳ báo cáo theo dõi", value=unique_periods)
        with col3:
            unique_metrics = df_sub[metric_col].nunique() if metric_col else 0
            st.metric(label="Chỉ tiêu tài chính", value=unique_metrics)
        with col4:
            latest_year = df_sub[period_col].max() if period_col else "N/A"
            st.metric(label="Kỳ dữ liệu mới nhất", value=latest_year)

        st.markdown("")

        # --- KHU VỰC TRỰC QUAN HÓA BIỂU ĐỒ NÂNG CAO ---
        if not df_sub.empty and period_col and metric_col and value_col:
            st.markdown("### 📈 Trực Quan Hóa & Phân Tích Chỉ Số Tài Chính")
            
            # Ép kiểu dữ liệu giá trị sang dạng số an toàn tuyệt đối
            df_sub[value_col] = pd.to_numeric(df_sub[value_col].astype(str).str.replace(',', ''), errors='coerce')
            
            available_metrics = sorted(df_sub[metric_col].dropna().unique())
            
            # Gợi ý mặc định các chỉ tiêu tài chính cốt lõi nếu có
            default_selection = [m for m in available_metrics if any(k in m.lower() for k in ['doanh thu', 'lợi nhuận', 'lãi', 'tài sản'])]
            if not default_selection:
                default_selection = available_metrics[:3]

            selected_metrics = st.multiselect(
                "🧩 Tùy chọn các chỉ tiêu tài chính hiển thị trên biểu đồ:",
                options=available_metrics,
                default=default_selection[:5] # Giới hạn mặc định 5 chỉ tiêu đầu cho gọn
            )
            
            if selected_metrics:
                df_chart = df_sub[df_sub[metric_col].isin(selected_metrics)]
                
                # Thanh cấu hình biểu đồ
                ch_col1, ch_col2 = st.columns([2, 2])
                with ch_col1:
                    chart_type = st.radio(
                        "🎨 Dạng biểu đồ:", 
                        ["Cột nhóm (Bar Chart)", "Đường xu hướng (Line Chart)"], 
                        horizontal=True
                    )
                
                if "Bar" in chart_type:
                    fig = px.bar(
                        df_chart.dropna(subset=[value_col]),
                        x=period_col,
                        y=value_col,
                        color=metric_col,
                        barmode='group',
                        title=f"Biểu đồ so sánh các chỉ tiêu tài chính - {selected_ticker}",
                        template="plotly_dark"
                    )
                else:
                    fig = px.line(
                        df_chart.dropna(subset=[value_col]),
                        x=period_col,
                        y=value_col,
                        color=metric_col,
                        markers=True,
                        title=f"Biểu đồ xu hướng tài chính - {selected_ticker}",
                        template="plotly_dark"
                    )
                
                fig.update_layout(
                    xaxis_title="Năm / Kỳ báo cáo",
                    yaxis_title="Giá trị (VND / Tỷ lệ)",
                    legend_title="Chỉ tiêu tài chính",
                    hovermode="x unified",
                    height=520,
                    plot_bgcolor="#0b0f19",
                    paper_bgcolor="#0b0f19"
                )
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("👈 Vui lòng chọn ít nhất một chỉ tiêu tài chính ở phía trên để hệ thống vẽ biểu đồ.")

        # --- KHU VỰC BẢNG DỮ LIỆU CHI TIẾT & TRA CỨU ---
        st.markdown("---")
        st.markdown(f"### 📋 Kho Dữ Liệu Chi Tiết — {selected_ticker}")
        
        search_query = st.text_input("🔍 Lọc nhanh chỉ tiêu trong bảng:", placeholder="Nhập từ khóa (Ví dụ: Doanh thu, Nợ, Vốn...)...")
        
        if search_query:
            mask = df_sub.astype(str).apply(lambda x: x.str.contains(search_query, case=False, na=False)).any(axis=1)
            df_display = df_sub[mask]
        else:
            df_display = df_sub

        st.dataframe(df_display, use_container_width=True, height=420)

        # Nút tải xuống dữ liệu cá nhân hóa cho từng mã
        col_dl1, col_dl2 = st.columns([1, 3])
        with col_dl1:
            csv_data = df_sub.to_csv(index=False).encode('utf-8')
            st.download_button(
                label=f"📥 Tải CSV ({selected_ticker})",
                data=csv_data,
                file_name=f"FINEX_Terminal_{selected_ticker}.csv",
                mime="text/csv",
            )
